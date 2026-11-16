# Nova Hub - game harvester v2
# Builds catalog/games.json with up to TARGET unique Roblox games (placeId + name).
# Sources: explore-api sorts over device/country permutations, merged with the existing file.
import asyncio, json, time
from pathlib import Path

import aiohttp

ROOT = Path(__file__).parent
CATALOG = ROOT / "catalog"
CATALOG.mkdir(exist_ok=True)
GAMES_FILE = CATALOG / "games.json"

BASE = "https://apis.roproxy.com/explore-api/v1/get-sort-content"
SORTS = ["top-playing-now", "top-trending", "up-and-coming", "fun-with-friends", "top-revisited"]
DEVICES = ["computer", "tablet", "phone", "console"]
COUNTRIES = ["all", "us", "ru", "br", "id", "de", "fr", "jp", "kr", "tr", "ph", "mx"]
TARGET = 1200
CONCURRENCY = 24
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0"}


def load_existing():
    if not GAMES_FILE.exists():
        return {}
    try:
        data = json.loads(GAMES_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}
    out = {}
    for g in data.get("games", []):
        pid = g.get("placeId")
        if pid:
            out[str(pid)] = g
    return out


async def fetch_sort(session, sem, sort_id, device, country, games, stats):
    url = f"{BASE}?sortId={sort_id}&device={device}&sessionId=novahub&country={country}"
    for attempt in range(2):
        try:
            async with sem:
                async with session.get(url) as r:
                    if r.status != 200:
                        stats["failed"] += 1
                        await asyncio.sleep(1)
                        continue
                    data = await r.json()
            batch = data.get("games") or []
            stats["ok"] += 1
            for g in batch:
                pid = g.get("rootPlaceId") or g.get("placeId")
                if not pid:
                    continue
                pid = str(pid)
                cur = games.get(pid)
                players = g.get("playerCount", 0) or 0
                if cur is None:
                    games[pid] = {
                        "placeId": pid,
                        "universeId": g.get("universeId"),
                        "name": (g.get("name") or "").strip(),
                        "players": players,
                        "sources": [f"{sort_id}:{device}:{country}"],
                    }
                    stats["new"] += 1
                else:
                    cur["players"] = max(cur["players"], players)
            return
        except Exception:
            await asyncio.sleep(1)
    stats["failed"] += 1


async def main():
    games = load_existing()
    print(f"[start] {len(games)} games already in file")
    stats = {"ok": 0, "failed": 0, "new": 0}
    sem = asyncio.Semaphore(CONCURRENCY)
    t0 = time.time()
    async with aiohttp.ClientSession(headers=UA, timeout=aiohttp.ClientTimeout(total=30)) as session:
        combos = [(s, d, c) for s in SORTS for d in DEVICES for c in COUNTRIES]
        for i in range(0, len(combos), 60):
            chunk = combos[i:i + 60]
            await asyncio.gather(*[fetch_sort(session, sem, s, d, c, games, stats) for s, d, c in chunk])
            print(f"[progress] {i + len(chunk)}/{len(combos)} requests | games {len(games)} | new {stats['new']}")
            if len(games) >= TARGET:
                break

    ordered = sorted(games.values(), key=lambda x: x.get("players", 0), reverse=True)
    payload = {
        "generated": time.time(),
        "count": len(ordered),
        "notes": "placeId + name + playerCount, harvested from explore-api sorts",
        "games": ordered,
    }
    GAMES_FILE.write_text(json.dumps(payload, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\n[done] {len(ordered)} games in {time.time() - t0:.0f}s "
          f"(requests ok {stats['ok']}, failed {stats['failed']}) -> {GAMES_FILE}")


if __name__ == "__main__":
    asyncio.run(main())

