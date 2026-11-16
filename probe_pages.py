import asyncio, json
import aiohttp

API = "https://rscripts.net/api/v2/scripts"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0"}


async def main():
    async with aiohttp.ClientSession(headers=UA, timeout=aiohttp.ClientTimeout(total=40)) as s:
        for page in (1, 2, 5, 20):
            params = {"orderBy": "views", "max": "50", "page": str(page)}
            try:
                async with s.get(API, params=params) as r:
                    if r.status != 200:
                        print(f"page {page}: HTTP {r.status}")
                        continue
                    d = await r.json()
                sc = d.get("scripts", [])
                games = []
                for x in sc:
                    g = x.get("game")
                    if isinstance(g, dict) and g.get("name"):
                        games.append((g["name"], g.get("gameLink", "")))
                print(f"page {page}: {len(sc)} scripts, {len(games)} with game")
                for n, l in games[:5]:
                    print("   ", n[:40], "|", l[:70])
            except Exception as e:
                print(f"page {page}: {type(e).__name__}")

asyncio.run(main())
