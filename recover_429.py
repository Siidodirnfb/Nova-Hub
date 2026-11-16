# Nova Hub - put back the raw links that were wrongly dropped by HTTP 429
# Uses the verified cache from fill_state.json and the full candidate pool to
# refill empty slots for games that are still short.
import json
from pathlib import Path

from merge_sources import load_candidates, score, dedupe

ROOT = Path(__file__).parent
CATALOG = ROOT / "catalog"
CATALOG_FILE = CATALOG / "catalog.json"
FILL_STATE = CATALOG / "fill_state.json"


def is_full(e):
    return len(e.get("noKey") or []) >= 4 and len(e.get("key") or []) >= 4


def main():
    data = json.loads(CATALOG_FILE.read_text(encoding="utf-8"))
    games = data["games"]
    state = json.loads(FILL_STATE.read_text(encoding="utf-8"))
    cache = {u: tuple(v) for u, v in (state.get("cache") or {}).items()}
    alive = {u for u, (ok, _) in cache.items() if ok}
    print(f"[cache] {len(alive)} urls confirmed alive")

    pool = load_candidates()
    by_url = {}
    for pid, items in pool.items():
        for it in items:
            by_url.setdefault(it["rawScript"], (pid, it))

    added = 0
    fixed_games = 0
    for url in alive:
        hit = by_url.get(url)
        if not hit:
            continue
        pid, cand = hit
        entry = games.get(pid)
        if not entry:
            continue
        bucket = entry.get("key") if cand["key"] else entry.get("noKey")
        if bucket is None:
            continue
        if len(bucket) >= 4:
            continue
        if any(it.get("rawScript") == url for it in bucket):
            continue
        bucket.append(cand)
        added += 1
        if is_full(entry):
            fixed_games += 1

    for pid, entry in games.items():
        entry["noKey"] = sorted(dedupe(entry.get("noKey") or []), key=score, reverse=True)[:4]
        entry["key"] = sorted(dedupe(entry.get("key") or []), key=score, reverse=True)[:4]

    CATALOG_FILE.write_text(json.dumps({
        "generated": data.get("generated"),
        "source": data.get("source"),
        "count": len(games),
        "games": games,
    }, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    full = sum(1 for g in games.values() if is_full(g))
    print(f"[done] added back {added} scripts, {len(games)} games, {full} with 4+4")


if __name__ == "__main__":
    main()
