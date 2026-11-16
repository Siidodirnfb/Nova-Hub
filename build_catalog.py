# Nova Hub - catalog builder (phase 1: rscripts.net, works without proxy)
# Fetches top scripts per game, splits into noKey / keySystem, writes catalog JSON.
import asyncio, json, time, re, html
from pathlib import Path

import aiohttp

ROOT = Path(__file__).parent
CATALOG = ROOT / "catalog"
CATALOG.mkdir(exist_ok=True)

API = "https://rscripts.net/api/v2/scripts"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0"}
KEYLESS_TARGET = 4
KEY_TARGET = 4
RETRIES = 2
PAGE_DELAY = 0.6

SEED_GAMES = [
    # (display name, [search keywords / aliases]) вЂ” rscripts search is full-text
    ("Blox Fruits", ["blox fruit"]),
    ("Steal a Brainrot", ["brainrot"]),
    ("Adopt Me", ["adopt me"]),
    ("Brookhaven", ["brookhaven"]),
    ("Arsenal", ["arsenal"]),
    ("Murder Mystery 2", ["murder mystery"]),
    ("Blade Ball", ["blade ball"]),
    ("Toilet Tower Defense", ["toilet tower"]),
    ("Doors", ["doors"]),
    ("Tower of Hell", ["tower of hell"]),
    ("Jailbreak", ["jailbreak"]),
    ("Da Hood", ["da hood"]),
    ("Anime Vanguards", ["anime vanguards"]),
    ("Grow a Garden", ["grow a garden"]),
    ("Dress to Impress", ["dress to impress"]),
    ("Basketball Legends", ["basketball legends"]),
    ("Bee Swarm Simulator", ["bee swarm"]),
    ("Fisch", ["fisch"]),
    ("Jujutsu Shenanigans", ["jujutsu"]),
    ("The Strongest Battlegrounds", ["strongest battlegrounds"]),
    ("Solo Leveling", ["solo leveling"]),
    ("Rivals", ["rivals"]),
    ("Volleyball Legends", ["volleyball legends"]),
    ("99 Nights in the Forest", ["99 nights"]),
]


def clean(s):
    if not isinstance(s, str):
        return ""
    s = html.unescape(re.sub(r"<[^>]+>", " ", s))
    return re.sub(r"\s+", " ", s).strip()


def parse_game(g):
    """game can be dict with gameLink (placeId inside) or plain string."""
    if isinstance(g, dict):
        name = clean(g.get("name") or g.get("title") or "")
        link = g.get("gameLink", "") or ""
        m = re.search(r"/games/(\d+)", link)
        return name, (m.group(1) if m else None)
    return clean(g), None


async def fetch_search(session, sem, game_name, aliases):
    """Search by each alias keyword; keep entries whose title mentions an alias."""
    entries, seen = [], set()
    for alias in aliases:
        for attempt in range(RETRIES + 1):
            try:
                async with sem:
                    params = {"q": alias, "orderBy": "views", "max": "50", "page": "1"}
                    async with session.get(API, params=params) as r:
                        if r.status == 429:
                            await asyncio.sleep(3 + attempt * 3)
                            continue
                        if r.status != 200:
                            print(f"[warn] {alias}: HTTP {r.status}")
                            scripts = []
                        else:
                            scripts = (await r.json()).get("scripts") or []
                break
            except Exception as e:
                if attempt == RETRIES:
                    print(f"[err] {alias}: {type(e).__name__}")
                    scripts = []
                    break
                await asyncio.sleep(2)
        for s in scripts:
            title = clean(s.get("title", "")).lower()
            desc = clean(s.get("description", "")).lower() if isinstance(s.get("description"), str) else ""
            gname, place_id = parse_game(s.get("game", {}))
            if not any(a in title or a in (gname or "").lower() for a in aliases):
                continue
            key_id = s.get("_id") or s.get("slug")
            if key_id in seen:
                continue
            seen.add(key_id)
            entries.append({
                "title": clean(s.get("title", "")),
                "game": gname or game_name,
                "placeId": place_id,
                "key": bool(s.get("keySystem", False)),
                "views": s.get("views", 0),
                "likes": s.get("likes", 0),
                "slug": s.get("slug"),
                "rawScript": s.get("rawScript"),
                "lastUpdated": s.get("lastUpdated"),
            })
    return entries


def rank(scripts):
    return sorted(scripts, key=lambda s: (s["likes"] + s["views"] / 10), reverse=True)


def pick(entries):
    nokey = rank([e for e in entries if not e["key"]])
    key = rank([e for e in entries if e["key"]])
    return {
        "noKey": nokey[:KEYLESS_TARGET],
        "noKeyAlternates": nokey[KEYLESS_TARGET:][:3],
        "key": key[:KEY_TARGET],
        "keyAlternates": key[KEY_TARGET:][:3],
    }


async def main():
    sem = asyncio.Semaphore(3)
    timeout = aiohttp.ClientTimeout(total=40)
    catalog = {"generated": time.time(), "source": "rscripts.net", "games": {}}
    async with aiohttp.ClientSession(timeout=timeout, headers=UA) as session:
        results = await asyncio.gather(*[fetch_search(session, sem, name, aliases) for name, aliases in SEED_GAMES])
    for (game, _), entries in zip(SEED_GAMES, results):
        if not entries:
            catalog["games"][game] = {"noKey": [], "key": []}
            print(f"[empty] {game}")
            continue
        sel = pick(entries)
        catalog["games"][game] = sel
        n, k = len(sel["noKey"]), len(sel["key"])
        print(f"[ok] {game}: {n} no-key, {k} key (of {len(entries)} matched)")
    out = CATALOG / "catalog.json"
    out.write_text(json.dumps(catalog, indent=1, ensure_ascii=False), encoding="utf-8")
    tn = sum(len(g.get("noKey", [])) for g in catalog["games"].values())
    tk = sum(len(g.get("key", [])) for g in catalog["games"].values())
    print(f"\n[done] {len(catalog['games'])} games, {tn} no-key + {tk} key -> {out}")


if __name__ == "__main__":
    asyncio.run(main())

