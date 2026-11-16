# Nova Hub - merge donors into one catalog and verify every raw script link.
# Sources: catalog/index_state.json (full rscripts pool) + catalog/scriptblox.json
# Ranking prefers working, popular, verified, recently updated scripts.
# Each raw URL is fetched once; dead/empty/HTML responses are dropped.
import asyncio, json, re, time
from pathlib import Path

import aiohttp

ROOT = Path(__file__).parent
CATALOG = ROOT / "catalog"
RSCRIPTS_STATE = CATALOG / "index_state.json"
SCRIPTBLOX = CATALOG / "scriptblox.json"
OUT = CATALOG / "catalog.json"
REJECTS = CATALOG / "rejected_urls.json"

OUT_PER_CATEGORY = 4
CANDIDATES_PER_CATEGORY = 9   # how many we try before giving up on 4
CONCURRENCY = 12
MIN_BODY = 40                 # bytes; anything shorter is an empty stub

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0"}


def load_candidates():
    pool = {}

    if RSCRIPTS_STATE.exists():
        state = json.loads(RSCRIPTS_STATE.read_text(encoding="utf-8"))
        for pid, bucket in (state.get("placeIds") or {}).items():
            for it in bucket.get("items") or []:
                if not it.get("rawScript"):
                    continue
                pool.setdefault(pid, []).append({
                    "placeId": pid,
                    "gameName": bucket.get("name") or it.get("gameName") or f"place {pid}",
                    "title": it.get("title") or "",
                    "key": bool(it.get("key")),
                    "views": it.get("views", 0) or 0,
                    "likes": it.get("likes", 0) or 0,
                    "executes": 0,
                    "verified": False,
                    "rawScript": it["rawScript"],
                    "lastUpdated": it.get("lastUpdated"),
                    "source": "rscripts",
                    "id": it.get("id") or it.get("slug"),
                })
        print(f"[load] rscripts: {len(pool)} games")

    if SCRIPTBLOX.exists():
        sb = json.loads(SCRIPTBLOX.read_text(encoding="utf-8"))
        added = 0
        for it in sb.get("scripts") or []:
            pid = it.get("placeId")
            if not pid:
                continue
            pool.setdefault(pid, []).append({
                "placeId": pid,
                "gameName": it.get("gameName") or f"place {pid}",
                "title": it.get("title") or "",
                "key": bool(it.get("key")),
                "views": it.get("views", 0) or 0,
                "likes": it.get("likes", 0) or 0,
                "executes": it.get("likes", 0) or 0,
                "verified": bool(it.get("verified")),
                "rawScript": it["rawScript"],
                "lastUpdated": it.get("lastUpdated"),
                "source": "scriptblox",
                "id": it.get("id") or it.get("slug"),
            })
            added += 1
        print(f"[load] scriptblox: {added} scripts, pool now {len(pool)} games")

    return pool


def recency_bonus(ts):
    if not ts:
        return 0
    try:
        s = str(ts).replace("Z", "+00:00")
        t = time.mktime(time.strptime(s[:19], "%Y-%m-%dT%H:%M:%S"))
    except Exception:
        return 0
    age_days = max(0, (time.time() - t) / 86400)
    return max(0, 30000 - age_days * 40)   # ~2 years until the bonus dies out


def score(it):
    s = it["views"] + it["likes"] * 12 + it["executes"] * 2
    if it.get("verified"):
        s += 60000
    s += recency_bonus(it.get("lastUpdated"))
    return s


def dedupe(items):
    seen, out = set(), []
    for it in items:
        norm = re.sub(r"[^a-z0-9]", "", (it["title"] or "").lower())[:40]
        key = (norm, it["rawScript"])
        if norm and norm in {k[0] for k in seen if k[0]}:
            continue
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out


async def check_url(session, sem, url, cache):
    """Return (alive, reason). Network errors are retried; only real answers are cached as dead."""
    if url in cache:
        return cache[url]
    last_err = None
    for attempt in range(3):
        try:
            async with sem:
                async with session.get(url, allow_redirects=True) as r:
                    if r.status in (408, 429, 500, 502, 503, 504):
                        last_err = f"http {r.status}"
                        await asyncio.sleep(1 + attempt * 2)
                        continue
                    if r.status != 200:
                        cache[url] = (False, f"http {r.status}")
                        return cache[url]
                    body = await r.content.read(800)
            text = body.decode("utf-8", "ignore").strip()
            low = text[:200].lower()
            if len(text) < MIN_BODY:
                cache[url] = (False, f"empty ({len(text)}b)")
            elif low.startswith("<!doctype") or low.startswith("<html") or "<head>" in low:
                cache[url] = (False, "html page")
            elif "not found" in low and len(text) < 200:
                cache[url] = (False, "not found page")
            else:
                cache[url] = (True, f"{len(text)}b")
            return cache[url]
        except Exception as e:
            last_err = type(e).__name__
            await asyncio.sleep(1 + attempt * 2)
    cache[url] = (False, f"unreachable ({last_err})")
    return cache[url]


async def main():
    pool = load_candidates()
    if not pool:
        print("nothing to merge")
        return

    t0 = time.time()
    url_cache = {}
    rejects = {}
    catalog = {}
    sem = asyncio.Semaphore(CONCURRENCY)
    total = len(pool)

    async with aiohttp.ClientSession(headers=UA, timeout=aiohttp.ClientTimeout(total=20)) as session:
        for i, (pid, items) in enumerate(pool.items(), 1):
            items = dedupe(items)
            nk = sorted([x for x in items if not x["key"]], key=score, reverse=True)
            kk = sorted([x for x in items if x["key"]], key=score, reverse=True)

            async def pick(cands):
                good = []
                for cand in cands[:CANDIDATES_PER_CATEGORY]:
                    ok, why = await check_url(session, sem, cand["rawScript"], url_cache)
                    if ok:
                        good.append(cand)
                    else:
                        rejects.setdefault(why, []).append(cand["rawScript"])
                    if len(good) >= OUT_PER_CATEGORY:
                        break
                return good

            nk_good = await pick(nk)
            kk_good = await pick(kk)
            if not nk_good and not kk_good:
                continue
            name = next((x["gameName"] for x in items if x.get("gameName") and not x["gameName"].startswith("place ")), None)
            name = name or items[0]["gameName"]
            catalog[pid] = {
                "placeId": pid,
                "name": name,
                "noKey": nk_good,
                "key": kk_good,
                "totalNoKey": len(nk),
                "totalKey": len(kk),
            }
            if i % 200 == 0:
                print(f"[{i}/{total}] games kept {len(catalog)} | urls checked {len(url_cache)} "
                      f"| {time.time() - t0:.0f}s", flush=True)

    payload = {
        "generated": time.time(),
        "source": "rscripts.net + scriptblox.com (raw links verified)",
        "count": len(catalog),
        "games": catalog,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    REJECTS.write_text(json.dumps({k: v[:50] for k, v in rejects.items()}, ensure_ascii=False, indent=1), encoding="utf-8")

    full = sum(1 for g in catalog.values() if len(g["noKey"]) >= 4 and len(g["key"]) >= 4)
    nk4 = sum(1 for g in catalog.values() if len(g["noKey"]) >= 4)
    k4 = sum(1 for g in catalog.values() if len(g["key"]) >= 4)
    tnk = sum(len(g["noKey"]) for g in catalog.values())
    tk = sum(len(g["key"]) for g in catalog.values())
    dead = sum(len(v) for v in rejects.values())

    print(f"\n[done] {time.time() - t0:.0f}s")
    print(f"       games kept        {len(catalog)}")
    print(f"       4 no-key + 4 key  {full}")
    print(f"       >=4 no-key        {nk4}")
    print(f"       >=4 key           {k4}")
    print(f"       scripts shipped   {tnk} no-key + {tk} key")
    print(f"       urls verified     {len(url_cache)} ({dead} rejected)")
    for reason, urls in sorted(rejects.items(), key=lambda x: -len(x[1]))[:5]:
        print(f"         {reason}: {len(urls)}")


if __name__ == "__main__":
    asyncio.run(main())
