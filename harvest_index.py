# Nova Hub - full rscripts index harvester
# Walks every page of /api/v2/scripts (q= enables pagination, ~2707 pages x 16)
# and aggregates scripts per Roblox placeId into catalog/catalog.json.
# Output per game: best 4 keyless + best 4 key-locked scripts.
import asyncio, json, time
from pathlib import Path

import aiohttp

ROOT = Path(__file__).parent
CATALOG = ROOT / "catalog"
CATALOG.mkdir(exist_ok=True)
CATALOG_FILE = CATALOG / "catalog.json"
GAMES_FILE = CATALOG / "games.json"
STATE_FILE = CATALOG / "index_state.json"

API = "https://rscripts.net/api/v2/scripts"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0"}
CONCURRENCY = 4
RETRIES = 3
CHUNK = 40
NOKEY_TARGET, KEY_TARGET = 4, 4


def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"next_page": 1, "max_pages": None, "placeIds": {}}


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")


def slim(s):
    g = s.get("game") or {}
    pid = g.get("placeId")
    if not pid:
        return None
    return {
        "placeId": str(pid),
        "gameName": (g.get("title") or "").strip() or f"place {pid}",
        "title": (s.get("title") or "").strip()[:90],
        "key": bool(s.get("keySystem", False)),
        "views": s.get("views", 0),
        "likes": s.get("likes", 0),
        "slug": s.get("slug"),
        "rawScript": s.get("rawScript"),
        "lastUpdated": s.get("lastUpdated"),
        "id": s.get("_id"),
    }


async def fetch_page(session, sem, page):
    for attempt in range(RETRIES):
        try:
            async with sem:
                async with session.get(API, params={"q": "", "page": str(page)}) as r:
                    if r.status == 429:
                        await asyncio.sleep(3 + attempt * 3)
                        continue
                    if r.status != 200:
                        await asyncio.sleep(1 + attempt * 1.5)
                        continue
                    return await r.json()
        except Exception:
            await asyncio.sleep(1 + attempt * 1.5)
    return None


def rank(x):
    return x["likes"] * 10 + x["views"]


async def main():
    state = load_state()
    pages = state["placeIds"]
    print(f"[start] page {state['next_page']}, {len(pages)} placeIds already collected")

    sem = asyncio.Semaphore(CONCURRENCY)
    t0 = time.time()
    empty_streak = 0

    async with aiohttp.ClientSession(headers=UA, timeout=aiohttp.ClientTimeout(total=30)) as session:
        first = await fetch_page(session, sem, 1)
        if first:
            state["max_pages"] = (first.get("info") or {}).get("maxPages") or state["max_pages"]
        max_pages = state["max_pages"] or 2707
        print(f"[plan] {max_pages} pages")

        page = state["next_page"]
        while page <= max_pages:
            batch = list(range(page, min(page + CHUNK, max_pages + 1)))
            results = await asyncio.gather(*[fetch_page(session, sem, p) for p in batch])

            got = 0
            for data in results:
                if not data:
                    continue
                got += 1
                for s in data.get("scripts") or []:
                    rec = slim(s)
                    if not rec:
                        continue
                    bucket = pages.setdefault(rec["placeId"], {"name": rec["gameName"], "items": []})
                    if not bucket.get("name") or bucket["name"].startswith("place "):
                        bucket["name"] = rec["gameName"]
                    bucket["items"].append(rec)

            empty_streak = empty_streak + 1 if got == 0 else 0
            page += CHUNK
            state["next_page"] = page
            save_state(state)

            done = min(page - 1, max_pages)
            elapsed = time.time() - t0
            print(f"[{done}/{max_pages}] pages ok {got}/{len(batch)} | placeIds {len(pages)} "
                  f"| {elapsed:.0f}s", flush=True)

            if empty_streak >= 3:
                print("[stop] three chunks in a row returned nothing, assuming the end")
                break

    # ---- build catalog -------------------------------------------------
    catalog = {}
    games = []
    total_nk = total_k = 0
    for pid, bucket in pages.items():
        items = bucket["items"]
        seen, uniq = set(), []
        for it in items:
            key = it.get("id") or it.get("slug") or (it.get("title"), it.get("rawScript"))
            if key in seen:
                continue
            seen.add(key)
            uniq.append(it)
        nk = sorted([x for x in uniq if not x["key"]], key=rank, reverse=True)
        kk = sorted([x for x in uniq if x["key"]], key=rank, reverse=True)
        if not nk and not kk:
            continue
        entry = {
            "placeId": pid,
            "name": bucket["name"],
            "noKey": nk[:NOKEY_TARGET],
            "key": kk[:KEY_TARGET],
            "totalNoKey": len(nk),
            "totalKey": len(kk),
        }
        catalog[pid] = entry
        total_nk += len(entry["noKey"])
        total_k += len(entry["key"])
        games.append({
            "placeId": pid,
            "name": bucket["name"],
            "scripts": len(nk) + len(kk),
            "players": 0,
        })

    ordered = sorted(catalog.values(), key=lambda g: g["totalNoKey"] + g["totalKey"], reverse=True)
    payload = {
        "generated": time.time(),
        "source": "rscripts.net full index",
        "count": len(ordered),
        "games": {g["placeId"]: g for g in ordered},
    }
    CATALOG_FILE.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    GAMES_FILE.write_text(json.dumps({
        "generated": time.time(),
        "count": len(games),
        "games": sorted(games, key=lambda x: x["scripts"], reverse=True),
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    size = CATALOG_FILE.stat().st_size / 1024 / 1024
    print(f"\n[done] {len(ordered)} games with scripts | {total_nk} no-key + {total_k} key "
          f"| catalog {size:.1f} MB | {time.time() - t0:.0f}s")


if __name__ == "__main__":
    asyncio.run(main())
