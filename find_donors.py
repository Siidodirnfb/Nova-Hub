# Nova Hub - find real GitHub donor repos that actually contain .lua scripts
# 1. search repos across several queries
# 2. shallow-clone candidates
# 3. count .lua/.txt script files, keep the ones that look like script collections
import json, os, re, shutil, subprocess, time
from pathlib import Path

ROOT = Path(__file__).parent
DONORS = ROOT / "donors"
DONORS.mkdir(exist_ok=True)
REPORT = ROOT / "donors_report.json"
UA = "nova-hub"

QUERIES = [
    "roblox script hub lua",
    "roblox scripts collection",
    "topic:roblox-scripts",
    "topic:roblox-script",
    "topic:roblox-exploits",
    "luau script hub",
    "roblox executor scripts",
    "roblox autofarm scripts",
]

# obvious SEO spam: repos whose only content is a landing page
SPAM_WORDS = ("alternative", "vault", "prime", "reforged", "compendium", "core", "2026")
MAX_REPOS = 26


def gh(path):
    out = subprocess.run(
        ["curl", "-s", "-H", f"User-Agent: {UA}", "-H", "Accept: application/vnd.github+json",
         f"https://api.github.com{path}"],
        capture_output=True, text=True, timeout=60,
    )
    try:
        return json.loads(out.stdout)
    except Exception:
        return {}


def search():
    repos = {}
    for q in QUERIES:
        data = gh(f"/search/repositories?q={q.replace(' ', '+')}&sort=stars&order=desc&per_page=30")
        items = data.get("items") or []
        print(f"[search] {q}: {data.get('total_count', '?')} total, {len(items)} items")
        for it in items:
            name = it["full_name"]
            if name in repos:
                continue
            desc = (it.get("description") or "").lower()
            # skip landing-page spam
            if it["size"] < 40:
                continue
            if sum(w in name.lower() for w in SPAM_WORDS) and it["size"] < 1500:
                continue
            repos[name] = {
                "full_name": name,
                "stars": it.get("stargazers_count", 0),
                "size": it.get("size", 0),
                "pushed": it.get("pushed_at"),
                "default_branch": it.get("default_branch", "main"),
                "description": (it.get("description") or "")[:120],
            }
        time.sleep(6)
    return repos


def clone(name, branch):
    dest = DONORS / name.replace("/", "__")
    if dest.exists():
        return dest
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    try:
        subprocess.run(
            ["git", "clone", "--depth", "1", "--quiet", "--branch", branch,
             f"https://github.com/{name}.git", str(dest)],
            capture_output=True, timeout=180, env=env,
        )
    except Exception as e:
        print(f"   clone error {name}: {type(e).__name__}")
    return dest if dest.exists() else None


def profile(dest):
    lua, txt, other = [], [], 0
    for p in dest.rglob("*"):
        if not p.is_file():
            continue
        rel = str(p.relative_to(dest))
        if ".git/" in rel or rel.startswith(".git"):
            continue
        ext = p.suffix.lower()
        size = p.stat().st_size
        if ext in (".lua", ".luau"):
            lua.append((rel, size))
        elif ext == ".txt" and size > 200:
            txt.append((rel, size))
        else:
            other += 1
    return lua, txt, other


def main():
    repos = search()
    print(f"\n[search] {len(repos)} unique candidate repos")

    ranked = sorted(repos.values(), key=lambda r: r["stars"], reverse=True)[:MAX_REPOS]
    report = []
    for r in ranked:
        name = r["full_name"]
        print(f"[clone] {name} ({r['stars']}*, {r['size']} KB)")
        dest = clone(name, r["default_branch"])
        if not dest:
            print("   failed")
            continue
        lua, txt, other = profile(dest)
        r["lua"] = len(lua)
        r["txt"] = len(txt)
        r["lua_bytes"] = sum(s for _, s in lua)
        r["samples"] = [f for f, _ in lua][:8]
        r["txtSamples"] = [f for f, _ in txt][:4]
        report.append(r)
        print(f"   {len(lua)} .lua, {len(txt)} .txt, {other} other")
        for f, _ in lua[:4]:
            print(f"      {f}")

    report.sort(key=lambda r: (r["lua"], r["stars"]), reverse=True)
    REPORT.write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
    good = [r for r in report if r["lua"] >= 10]
    print(f"\n[done] {len(good)} repos with 10+ .lua files -> {REPORT}")
    for r in good[:15]:
        print(f"   {r['lua']:>4} lua | {r['stars']:>5}* | {r['full_name']}")


if __name__ == "__main__":
    main()
