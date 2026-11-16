# Nova Hub - catalog builder v2: games.json -> per-placeId 4 no-key + 4 key scripts
import asyncio, json, re, time, sys
from pathlib import Path

import aiohttp

ROOT = Path(__file__).parent
CATALOG = ROOT / "catalog"
CATALOG.mkdir(exist_ok=True)

API = "https://rscripts.net/api/v2/scripts"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0"}
KEYLESS_TARGET, KEY_TARGET = 4, 4
RETRIES = 2
LIMIT = int(sys.argv[1]) if len(sys.argv) > 1 else 60   # how many games to process

EMOJI = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F\u200d]")


def clean_name(name):
    s = EMOJI.sub(" ", name)
    s = re.sub(r"[\[\](){}|*~<>/\\]+", " ", s)
    s = re.sub(r"\b(UPD|UPDATE|NEW|BETA|CODE)\b\s*\d*", " ", s, flags=re.I)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def qwords(name):
    """candidate search queries for a game name"""
    n = clean_name(name)
    ws = [w for w in re.split(r"[^A-Za-z0-9]+", n) if len(w) > 2]
    cands = [n]
    if len(ws) >= 2:
        cands.append(" ".join(ws[:2]))
    if ws:
        cands.append(ws[0])
    # dedupe, keep order
    out, seen = [], set()
    for c in cands:
        c = c.strip()
        if c and c.lower() not in seen:
            seen.add(c.lower())
            out.append(c)
    return out


async def search(session, sem, query):
    for attempt in range(RETRIES + 1):
        try:
            async with sem:
                async with session.get(API, params={"q": query, "orderBy": "views", "max": "50"}) as r:
                    if r.status != 200:
                        await asyncio.sleep(1.5 + attempt * 2)
                        continue
                    return (await r.json()).get("scripts") or []
        except Exception:
            await asyncio.sleep(1.5 + attempt * 2)
    return []


def matches(script, tokens):
    g = script.get("game")
    gn = (g.get("name") or "").lower() if isinstance(g, dict) else ""
    title = (script.get("title") or "").lower()
    hay = gn + " " + title
    # token list is ordered from most specific to most generic; accept word-level hits
    for t in tokens:
        words = [w for w in re.split(r"[^a-z0-9]+", t.lower()) if len(w) > 2]
        if words and all(w in hay for w in words):
            return True
    return False


async def build_game(session, sem, game):
    place_id, name = game["placeId"], game["name"]
    tokens = qwords(name)
    best = []
    for q in tokens[:3]:
        res = await search(session, sem, q)
        cand = [s for s in res if matches(s, tokens)]
        if len(cand) > len(best):
            best = cand
        if len(best) >= 12:
            break
    seen, entries = set(), []
    for s in best:
        key_id = s.get("_id") or s.get("slug")
        if key_id in seen:
            continue
        seen.add(key_id)
        g = s.get("game")
        gname = g.get("name") if isinstance(g, dict) else None
        gl = g.get("gameLink", "") if isinstance(g, dict) else ""
        m = re.search(r"/games/(\d+)", gl or "")
        entries.append({
            "title": (s.get("title") or "").strip()[:90],
            "gameName": gname or clean_name(name),
            "placeId": m.group(1) if m else None,
            "key": bool(s.get("keySystem", False)),
            "views": s.get("views", 0),
            "likes": s.get("likes", 0),
            "slug": s.get("slug"),
            "rawScript": s.get("rawScript"),
            "lastUpdated": s.get("lastUpdated"),
        })

    def rank(x):
        return (x["likes"] + x["views"] / 10)

    app = lambda pl: pl if pl not in (None, "", place_id) else place_id
    nk = sorted([e for e in entries if not e["key"]], key=rank, reverse=True)
    kk = sorted([e for e in entries if e["key"]], key=rank, reverse=True)
    return {
        "placeId": str(place_id),
        "name": name,
        "players": game.get("players", 0),
        "noKey": [{**e, "placeId": app(e["placeId"])} for e in nk[:KEYLESS_TARGET]],
        "key": [{**e, "placeId": app(e["placeId"])} for e in kk[:KEY_TARGET]],
        "alternatesNoKey": len(nk[KEYLESS_TARGET:]),
        "alternatesKey": len(kk[KEY_TARGET:]),
    }


async def main():
    games = json.loads((CATALOG / "games.json").read_text(encoding="utf-8"))["games"][:LIMIT]
    sem = asyncio.Semaphore(3)
    catalog = {"generated": time.time(), "source": "rscripts.net", "games": {}}
    async with aiohttp.ClientSession(headers=UA, timeout=aiohttp.ClientTimeout(total=45)) as session:
        for i, g in enumerate(games, 1):
            entry = await build_game(session, sem, g)
            catalog["games"][str(g["placeId"])] = entry
            print(f"[{i}/{len(games)}] {g['name'][:38]:38} -> {len(entry['noKey'])} nk / {len(entry['key'])} k")
    out = CATALOG / "catalog.json"
    out.write_text(json.dumps(catalog, indent=1, ensure_ascii=False), encoding="utf-8")
    tn = sum(len(x["noKey"]) for x in catalog["games"].values())
    tk = sum(len(x["key"]) for x in catalog["games"].values())
    print(f"\n[done] {len(catalog['games'])} games, {tn} no-key + {tk} key -> {out}")


if __name__ == "__main__":
    asyncio.run(main())
