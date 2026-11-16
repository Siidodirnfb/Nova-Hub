# Nova Hub - harvest games that actually have scripts, from rscripts.net
# Strategy: probe many keyword queries, collect game dicts (name + gameLink placeId),
# then merge into catalog/games.json. These games are guaranteed to have at least one script.
import asyncio, json, re, time
from pathlib import Path

import aiohttp

ROOT = Path(__file__).parent
CATALOG = ROOT / "catalog"
CATALOG.mkdir(exist_ok=True)
GAMES_FILE = CATALOG / "games.json"

API = "https://rscripts.net/api/v2/scripts"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0"}
CONCURRENCY = 3

# Popular game names + genre words. rscripts search matches titles AND game names,
# so generic genre words surface a lot of distinct games in one shot.
SEEDS = [
    # top games
    "blox fruits", "adopt me", "brookhaven", "pet simulator", "murder mystery", "jailbreak",
    "arsenal", "piggy", "doors", "fisch", "bloxburg", "da hood", "anime adventures",
    "all star tower defense", "tower defense", "king legacy", "grand piece", "a one piece game",
    "fruit battlegrounds", "combat warriors", "slap battles", "blade ball", "bedwars",
    "steal a brainrot", "grow a garden", "plants vs brainrots", "dress to impress",
    "99 nights in the forest", "rivals", "dead rails", "sols rng", "sol's rng",
    "jujutsu shenanigans", "jujutsu infinite", "the strongest battlegrounds", "hero battlegrounds",
    "basketball zero", "blue lock rivals", "volleyball legends", "nfl universe football",
    "universal tower defense", "toilet tower defense", "tower blitz", "obby",
    "saber showdown", "booga booga", "islands", "skyblock", "hypixel",
    # genres
    "simulator", "tycoon", "clicker", "idle", "rng", "battlegrounds", "fighting",
    "horror", "survival", "zombie", "racing", "parkour", "roleplay", "rpg",
    "mining", "fishing", "farming", "pets", "trading", "pvp", "sword", "gun",
    "anime", "naruto", "dragon ball", "one piece", "demon slayer", "jujutsu kaisen",
    "solo leveling", "attack on titan", "hunter x hunter", "bleach", "fairy tail",
    "squid game", "among us", "backrooms", "scary", "escape", "prison",
    "restaurant", "cafe", "bakery", "city", "school", "hospital", "airport",
    "car", "plane", "train", "boat", "spider", "superhero", "battle royale",
    "lucky blocks", "snowball", "sword fighting", "boxing", "wrestling",
    "football", "soccer", "basketball", "golf", "tennis", "skateboard",
    "ninja", "pirate", "knight", "dragon", "monster", "giant", "kaiju",
    "incremental", "rebirth", "grind", "afk", "auto", "farm", "egg",
    "brainrot", "steal", "grow", "build", "craft", "sandbox", "obby tower",
    "difficulty chart", "jtoh", "parkour reborn", "speed run",
]

EMOJI = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F\u200d]")


def clean_name(name):
    s = EMOJI.sub(" ", name or "")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def load_games():
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


async def probe(session, sem, query, stats):
    for attempt in range(3):
        try:
            async with sem:
                async with session.get(API, params={"q": query, "orderBy": "views", "max": "50"}) as r:
                    if r.status != 200:
                        await asyncio.sleep(1 + attempt * 2)
                        continue
                    data = await r.json()
            stats["ok"] += 1
            return data.get("scripts") or []
        except Exception:
            await asyncio.sleep(1 + attempt * 2)
    stats["failed"] += 1
    return []


async def main():
    games = load_games()
    before = len(games)
    stats = {"ok": 0, "failed": 0}
    sem = asyncio.Semaphore(CONCURRENCY)
    t0 = time.time()
    new = 0

    async with aiohttp.ClientSession(headers=UA, timeout=aiohttp.ClientTimeout(total=40)) as session:
        for i, q in enumerate(SEEDS, 1):
            script_list = await probe(session, sem, q, stats)
            for s in script_list:
                g = s.get("game")
                if not isinstance(g, dict):
                    continue
                link = g.get("gameLink") or ""
                m = re.search(r"/games/(\d+)", link)
                if not m:
                    continue
                pid = m.group(1)
                if pid in games:
                    continue
                games[pid] = {
                    "placeId": pid,
                    "universeId": None,
                    "name": clean_name(g.get("name")) or f"place {pid}",
                    "players": s.get("views", 0),
                    "sources": [f"rscripts:{q}"],
                    "hasScripts": True,
                }
                new += 1
            if i % 10 == 0:
                print(f"[{i}/{len(SEEDS)}] games {len(games)} (+{new}) ok {stats['ok']} failed {stats['failed']}")

    ordered = sorted(games.values(), key=lambda x: x.get("players", 0), reverse=True)
    payload = {
        "generated": time.time(),
        "count": len(ordered),
        "notes": "placeId + name; explore-api sorts + rscripts game index",
        "games": ordered,
    }
    GAMES_FILE.write_text(json.dumps(payload, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\n[done] {len(ordered)} games ({before} -> {len(ordered)}, +{new} from rscripts) "
          f"in {time.time() - t0:.0f}s -> {GAMES_FILE}")


if __name__ == "__main__":
    asyncio.run(main())
