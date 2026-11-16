# Vesper Hub - catalog hashes
# Recompute the published files and compare with PROVENANCE.md.
import hashlib, json
from pathlib import Path

ROOT = Path(__file__).parent
CATALOG = ROOT / "catalog"

TARGETS = [
    "Vesper.lua",
    "catalog/index.json",
    "catalog/catalog.json",
]


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    rows = []
    for rel in TARGETS:
        p = ROOT / rel
        if not p.exists():
            rows.append((rel, "missing", 0))
            continue
        rows.append((rel, sha256(p), p.stat().st_size))

    games_dir = CATALOG / "games"
    files = sorted(games_dir.glob("*.json"))
    combined = hashlib.sha256()
    total = 0
    for f in files:
        combined.update(f.name.encode())
        combined.update(f.read_bytes())
        total += f.stat().st_size

    print(f"{'file':<26} {'size':>10}  sha256")
    for rel, digest, size in rows:
        print(f"{rel:<26} {size:>10}  {digest}")
    print(f"{'catalog/games/*.json':<26} {total:>10}  {combined.hexdigest()}  ({len(files)} files)")

    index = json.loads((CATALOG / "index.json").read_text(encoding="utf-8"))
    print(f"\nbuild:  {index.get('build')}")
    print(f"games:  {index.get('count')}")


if __name__ == "__main__":
    main()
