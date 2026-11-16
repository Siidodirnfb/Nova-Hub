# Nova Hub - harvest popular Roblox games (name + placeId) via roproxy mirror
import asyncio, json, time
from pathlib import Path

import aiohttp

ROOT = Path(__file__).parent
OUT = ROOT / "catalog"
OUT.mkdir(exist_ok=True)

BASE = "https://apis.roproxy.com/explore-api/v1"
SORTS = ["top-playing-now", "top-trending", "up-and-coming", "fun-with-friends", "top-revisited"]
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0"}


async def get_sort(session, sort_id):
    url = f"{BASE}/get-sort-content?sortId={sort_id}&device=computer&sessionId=novahub&country=all"
    for attempt in range(3):
        try:
            async with session.get(url) as r:
                if r.status != 200:
                    await asyncio.sleep(2 + attempt * 2)
                    continue
                j = await r.json()
            return j.get("games") or []
        except Exception:
            await asyncio.sleep(2 + attempt * 2)
    return []


async def main():
    games = {}
    async with aiohttp.ClientSession(headers=UA, timeout=aiohttp.ClientTimeout(total=40)) as s:
        for sort_id in SORTS:
            batch = await get_sort(s, sort_id)
            print(f"[{sort_id}] {len(batch)} games")
            for g in batch:
                pid = g.get("rootPlaceId") or g.get("placeId")
                if not pid:
                    continue
                if pid not in games:
                    games[pid] = {
                        "placeId": pid,
                        "universeId": g.get("universeId"),
                        "name": g.get("name", "").strip(),
                        "players": g.get("playerCount", 0),
                        "sources": [sort_id],
                    }
                else:
                    games[pid]["sources"].append(sort_id)
                    games[pid]["players"] = max(games[pid]["players"], g.get("playerCount", 0))
            await asyncio.sleep(1)

    ordered = sorted(games.values(), key=lambda x: x["players"], reverse=True)
    payload = {"generated": time.time(), "count": len(ordered), "games": ordered}
    path = OUT / "games.json"
    path.write_text(json.dumps(payload, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\n[done] {len(ordered)} unique games -> {path}")
    for g in ordered[:10]:
        print(f"   {g['players']:>8} players | {g['placeId']:<18} | {g['name'][:40]}")


if __name__ == "__main__":
    asyncio.run(main())
