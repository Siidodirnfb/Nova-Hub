# Vesper - split catalog.json into a compact index + one file per game.
# index.json  : {"generated":..,"build":..,"count":..,"games":{"<placeId>":{"name":..,"nk":4,"k":4}}}
# games/<placeId>.json : {"placeId":..,"build":..,"name":..,"noKey":[..],"key":[..]}
import json, shutil, time
from pathlib import Path

ROOT = Path(__file__).parent
CATALOG = ROOT / "catalog"
SRC = CATALOG / "catalog.json"
GAMES_DIR = CATALOG / "games"
INDEX = CATALOG / "index.json"

FIELDS = ("title", "key", "views", "likes", "slug", "rawScript")

# provenance: this string ships inside index.json and inside Vesper.lua.
# A copy that drops it did not come from the original build, and a copy that
# keeps it can be traced back to the commit it was built from.
BUILD_ID = "vesper-2026-11-16"


def trim(items):
    out = []
    for it in items:
        rec = {f: it.get(f) for f in FIELDS if it.get(f) is not None}
        # keep payload small: drop unused metadata
        out.append(rec)
    return out


def main():
    data = json.loads(SRC.read_text(encoding="utf-8"))
    games = data.get("games") or {}
    if GAMES_DIR.exists():
        shutil.rmtree(GAMES_DIR)
    GAMES_DIR.mkdir(parents=True, exist_ok=True)

    index = {"generated": int(time.time()), "build": BUILD_ID, "count": 0, "games": {}}
    written = 0
    for pid, entry in games.items():
        rec = {
            "placeId": pid,
            "build": BUILD_ID,
            "name": entry.get("name") or f"place {pid}",
            "noKey": trim(entry.get("noKey") or []),
            "key": trim(entry.get("key") or []),
        }
        if not rec["noKey"] and not rec["key"]:
            continue
        (GAMES_DIR / f"{pid}.json").write_text(
            json.dumps(rec, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
        )
        index["games"][pid] = {"name": rec["name"], "nk": len(rec["noKey"]), "k": len(rec["key"])}
        written += 1

    index["count"] = written
    INDEX.write_text(json.dumps(index, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    idx_size = INDEX.stat().st_size / 1024
    total = sum((GAMES_DIR / f.name).stat().st_size for f in GAMES_DIR.iterdir()) / 1024 / 1024
    biggest = max(GAMES_DIR.iterdir(), key=lambda f: f.stat().st_size)
    print(f"[done] {written} games")
    print(f"       index.json      {idx_size:>8.1f} KB")
    print(f"       games/          {total:>8.1f} MB total")
    print(f"       largest file    {biggest.name} {biggest.stat().st_size / 1024:.1f} KB")


if __name__ == "__main__":
    main()
