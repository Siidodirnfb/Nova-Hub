# Compare published files with the hashes recorded in PROVENANCE.md.
import hashlib
import re
import urllib.request
from pathlib import Path

BASE = "https://raw.githubusercontent.com/Siidodirnfb/Vesper-Hub/main/"
prov = Path("PROVENANCE.md").read_text(encoding="utf-8")

rows = re.findall(r"\| `([^`]+)`[^|]*\|[^|]*\| `([0-9a-f]{64})` \|", prov)


def sha(b):
    return hashlib.sha256(b).hexdigest()


ok = 0
for rel, digest in rows:
    if "*" in rel:
        continue
    try:
        body = urllib.request.urlopen(BASE + rel, timeout=60).read()
    except Exception as exc:
        print(f"{rel:<22} ERR {exc}")
        continue
    match = sha(body) == digest
    ok += match
    print(f"{rel:<22} {len(body):>9}  {sha(body)[:16]}  match={match}")

print(f"\n{ok}/{len(rows)} files match")
