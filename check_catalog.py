# Nova Hub - acceptance check for the finished catalog
# Samples random shipped scripts, re-fetches every raw link and reports dead/empty ones.
import asyncio, json, random, sys, time
from pathlib import Path

import aiohttp

ROOT = Path(__file__).parent
CATALOG = ROOT / "catalog" / "catalog.json"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0"}
SAMPLE = int(sys.argv[1]) if len(sys.argv) > 1 else 60
MIN_BODY = 40


async def check(session, sem, item):
    url = item["rawScript"]
    async with sem:
        try:
            async with session.get(url, allow_redirects=True) as r:
                body = await r.content.read(400) if r.status == 200 else b""
                status = r.status
        except Exception as e:
            return item, False, type(e).__name__
    text = body.decode("utf-8", "ignore").strip()
    low = text[:200].lower()
    if status != 200:
        return item, False, f"http {status}"
    if len(text) < MIN_BODY:
        return item, False, f"empty ({len(text)}b)"
    if low.startswith("<!doctype") or low.startswith("<html") or "<head>" in low:
        return item, False, "html"
    return item, True, f"{len(text)}b"


async def main():
    data = json.loads(CATALOG.read_text(encoding="utf-8"))
    games = data["games"]
    rows = []
    for g in games.values():
        for it in (g.get("noKey") or []) + (g.get("key") or []):
            rows.append(it)
    print(f"[catalog] {len(games)} games, {len(rows)} shipped scripts")
    random.seed(7)
    sample = random.sample(rows, min(SAMPLE, len(rows)))

    sem = asyncio.Semaphore(16)
    async with aiohttp.ClientSession(headers=UA, timeout=aiohttp.ClientTimeout(total=25)) as session:
        results = await asyncio.gather(*[check(session, sem, it) for it in sample])

    ok = sum(1 for _, good, _ in results if good)
    print(f"[sample] {ok}/{len(results)} alive ({ok / len(results) * 100:.0f}%)")
    for item, good, why in results:
        if not good:
            print(f"   DEAD {why:>14} | {item.get('source','?'):<10} | {(item.get('title') or '')[:45]}")
    print(f"\n[summary] keyless {sum(1 for g in games.values() for _ in g.get('noKey') or [])}, "
          f"key {sum(1 for g in games.values() for _ in g.get('key') or [])}")


if __name__ == "__main__":
    asyncio.run(main())
