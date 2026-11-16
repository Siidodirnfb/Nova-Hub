# Nova Hub - fill the gaps so more games reach 4 keyless + 4 key
# Pass A: retry raw links that were dropped only because of HTTP 429 rate limiting.
# Pass B: for games still short, search ScriptBlox by game name and keep results
#         whose game.gameId matches that exact placeId.
import asyncio, json, re, time
from pathlib import Path

import aiohttp

from merge_sources import check_url, score

ROOT = Path(__file__).parent
CATALOG = ROOT / "catalog"
CATALOG_FILE = CATALOG / "catalog.json"
PARTIAL = CATALOG / "merge_partial.json"
FILL_STATE = CATALOG / "fill_state.json"

SEARCH = "https://scriptblox.com/api/script/search"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0"}
TARGET_FULL = 1200
PAGES_PER_QUERY = 3
SEARCH_CONCURRENCY = 6
URL_CONCURRENCY = 24

EMOJI = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F\u200d]")
URL_RE = re.compile(r'https?://[^\s"\'\)]+')


def clean_query(name):
    s = EMOJI.sub(" ", name or "")
    s = re.sub(r"[\[\](){}|*~<>/\\!?:,]+", " ", s)
    s = re.sub(r"\b(UPD|UPDATE|NEW|BETA|CODE|ALPHA)\b\s*\d*", " ", s, flags=re.I)
    s = re.sub(r"\s+", " ", s).strip()
    return s[:48]


def slim(s, pid):
    g = s.get("game") or {}
    if str(g.get("gameId")) != str(pid):
        return None
    if s.get("isPatched") or s.get("isUniversal"):
        return None
    if s.get("script"):
        m = URL_RE.search(s["script"])
        raw = m.group(0).rstrip(".,;") if m else None
    else:
        raw = None
    if not raw and s.get("slug"):
        raw = f"https://scriptblox.com/raw/{s['slug']}"
    if not raw:
        return None
    keyless = s.get("keyless")
    if keyless is None:
        keyless = not s.get("key", False)
    return {
        "placeId": str(pid),
        "gameName": (g.get("name") or "").strip() or f"place {pid}",
        "title": (s.get("title") or "").strip()[:90],
        "key": (not keyless),
        "views": s.get("views", 0) or 0,
        "likes": s.get("executes", 0) or 0,
        "executes": s.get("executes", 0) or 0,
        "verified": bool(s.get("verified")),
        "rawScript": raw,
        "lastUpdated": s.get("lastBump") or s.get("createdAt"),
        "source": "scriptblox",
        "id": s.get("_id"),
    }


def is_full(entry):
    return len(entry.get("noKey") or []) >= 4 and len(entry.get("key") or []) >= 4


def missing(entry):
    return max(0, 4 - len(entry.get("noKey") or [])) + max(0, 4 - len(entry.get("key") or []))


async def search_page(session, sem, query, page):
    for attempt in range(3):
        try:
            async with sem:
                async with session.get(SEARCH, params={"q": query, "page": str(page)}) as r:
                    if r.status == 200:
                        return await r.json()
                    if r.status == 400:
                        return None
                    await asyncio.sleep(1 + attempt * 2)
        except Exception:
            await asyncio.sleep(1 + attempt * 2)
    return None


async def main():
    data = json.loads(CATALOG_FILE.read_text(encoding="utf-8"))
    games = data["games"]
    print(f"[start] {len(games)} games, full 4+4: {sum(1 for g in games.values() if is_full(g))}")

    state = {}
    if FILL_STATE.exists():
        try:
            state = json.loads(FILL_STATE.read_text(encoding="utf-8"))
        except Exception:
            state = {}
    url_cache = {k: tuple(v) for k, v in (state.get("cache") or {}).items()}
    tried = set(state.get("tried") or [])
    url_sem = asyncio.Semaphore(URL_CONCURRENCY)

    async with aiohttp.ClientSession(headers=UA, timeout=aiohttp.ClientTimeout(total=20)) as session:
        # ---------- pass A: recover 429 casualties ----------
        if PARTIAL.exists() and not state.get("passA_done"):
            partial = json.loads(PARTIAL.read_text(encoding="utf-8"))
            cache = partial.get("cache") or {}
            retry = [u for u, (ok, why) in cache.items() if not ok and "429" in str(why)]
            print(f"[pass A] retrying {len(retry)} urls dropped by rate limiting")
            by_url = {}
            for pid, entry in games.items():
                for it in (entry.get("noKey") or []) + (entry.get("key") or []):
                    by_url.setdefault(it["rawScript"], []).append(pid)
            recovered = 0
            for i, url in enumerate(retry, 1):
                ok, why = await check_url(session, url_sem, url, url_cache)
                if ok:
                    recovered += 1
                if i % 50 == 0:
                    print(f"   {i}/{len(retry)} checked, {recovered} recovered", flush=True)
            print(f"[pass A] {recovered} links came back alive (they can be reused from the merge pool)")
            state["passA_done"] = True

        # ---------- pass B: targeted search ----------
        short = [(pid, e) for pid, e in games.items() if not is_full(e) and pid not in tried]
        short.sort(key=lambda x: (missing(x[1]), -(len(x[1].get("noKey") or []) + len(x[1].get("key") or []))))
        print(f"[pass B] {len(short)} games need scripts; target {TARGET_FULL} full games")

        search_sem = asyncio.Semaphore(SEARCH_CONCURRENCY)
        full_now = sum(1 for g in games.values() if is_full(g))
        t0 = time.time()
        processed = 0

        for pid, entry in short:
            if full_now >= TARGET_FULL:
                print(f"[pass B] target reached: {full_now} full games")
                break
            processed += 1
            query = clean_query(entry.get("name"))
            if len(query) < 3:
                tried.add(pid)
                continue

            found = []
            stop_pages = False
            for page in range(1, PAGES_PER_QUERY + 1):
                if stop_pages:
                    break
                res = await search_page(session, search_sem, query, page)
                if not res:
                    break
                sc = (res.get("result") or {}).get("scripts") or []
                if not sc:
                    break
                for s in sc:
                    rec = slim(s, pid)
                    if rec:
                        found.append(rec)
                if not (res.get("result") or {}).get("nextPage"):
                    stop_pages = True

            if found:
                seen_ids = {it.get("id") for it in (entry.get("noKey") or []) + (entry.get("key") or [])}
                fresh = [f for f in found if f.get("id") not in seen_ids]
                nk = sorted([f for f in fresh if not f["key"]], key=score, reverse=True)
                kk = sorted([f for f in fresh if f["key"]], key=score, reverse=True)

                async def take(cands, current):
                    need = 4 - len(current)
                    taken = []
                    for cand in cands[:max(need * 3, need)]:
                        if len(taken) >= need:
                            break
                        ok, why = await check_url(session, url_sem, cand["rawScript"], url_cache)
                        if ok:
                            taken.append(cand)
                    return current + taken

                entry["noKey"] = await take(nk, entry.get("noKey") or [])
                entry["key"] = await take(kk, entry.get("key") or [])

            tried.add(pid)
            if is_full(entry):
                full_now += 1

            if processed % 25 == 0:
                print(f"[{processed}/{len(short)}] full {full_now} | tried {len(tried)} | "
                      f"{time.time() - t0:.0f}s", flush=True)
                CATALOG_FILE.write_text(json.dumps({
                    "generated": data.get("generated"),
                    "source": data.get("source"),
                    "count": len(games),
                    "games": games,
                }, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
                FILL_STATE.write_text(json.dumps({
                    "cache": {k: list(v) for k, v in url_cache.items()},
                    "tried": sorted(tried),
                    "passA_done": state.get("passA_done", False),
                }, ensure_ascii=False), encoding="utf-8")

    games = {pid: e for pid, e in games.items() if e.get("noKey") or e.get("key")}
    CATALOG_FILE.write_text(json.dumps({
        "generated": time.time(),
        "source": "rscripts.net + scriptblox.com (raw links verified)",
        "count": len(games),
        "games": games,
    }, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    FILL_STATE.write_text(json.dumps({
        "cache": {k: list(v) for k, v in url_cache.items()},
        "tried": sorted(tried),
        "passA_done": state.get("passA_done", False),
    }, ensure_ascii=False), encoding="utf-8")

    full = sum(1 for g in games.values() if is_full(g))
    print(f"\n[done] games {len(games)} | full 4+4 {full} "
          f"| no-key {sum(len(g.get('noKey') or []) for g in games.values())} "
          f"| key {sum(len(g.get('key') or []) for g in games.values())}")


if __name__ == "__main__":
    asyncio.run(main())
