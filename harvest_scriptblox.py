# Nova Hub - ScriptBlox donor harvester
# Walks /api/script/fetch?page=N (N=1..~500, later pages return 400) and collects
# modern scripts with real placeIds, keyless flag, patch state and popularity.
# Output: catalog/scriptblox.json  (resumable)
import asyncio, json, re, time
from pathlib import Path

import aiohttp

ROOT = Path(__file__).parent
CATALOG = ROOT / "catalog"
CATALOG.mkdir(exist_ok=True)
OUT = CATALOG / "scriptblox.json"
STATE = CATALOG / "scriptblox_state.json"

API = "https://scriptblox.com/api/script/fetch"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0"}
CONCURRENCY = 4
RETRIES = 3
CHUNK = 20
MAX_PAGE = 520

URL_RE = re.compile(r'https?://[^\s"\'\)]+')


def load_state():
    if STATE.exists():
        try:
            return json.loads(STATE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"next_page": 1, "rows": {}}


def save_state(state):
    STATE.write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")


def extract_url(script_field, slug):
    if script_field:
        m = URL_RE.search(script_field)
        if m:
            return m.group(0).rstrip(".,;")
    if slug:
        return f"https://scriptblox.com/raw/{slug}"
    return None


def slim(s):
    g = s.get("game") or {}
    gid = g.get("gameId")
    if not gid or int(gid) <= 0:
        return None
    if s.get("isUniversal"):
        return None
    if s.get("isPatched"):
        return None
    raw = extract_url(s.get("script"), s.get("slug"))
    if not raw:
        return None
    keyless = s.get("keyless")
    if keyless is None:
        keyless = not s.get("key", False)
    return {
        "placeId": str(gid),
        "gameName": (g.get("name") or "").strip() or f"place {gid}",
        "title": (s.get("title") or "").strip()[:90],
        "key": (not keyless),
        "views": s.get("views", 0) or 0,
        "likes": s.get("executes", 0) or 0,
        "slug": s.get("slug"),
        "rawScript": raw,
        "lastUpdated": s.get("lastBump") or s.get("createdAt"),
        "verified": bool(s.get("verified")),
        "source": "scriptblox",
        "id": s.get("_id"),
    }


async def fetch_page(session, sem, page):
    for attempt in range(RETRIES):
        try:
            async with sem:
                async with session.get(API, params={"page": str(page)}) as r:
                    if r.status == 200:
                        return await r.json()
                    if r.status == 400:
                        return {"__stop__": True}
                    await asyncio.sleep(1 + attempt * 2)
        except Exception:
            await asyncio.sleep(1 + attempt * 2)
    return None


async def main():
    state = load_state()
    rows = state["rows"]
    print(f"[start] page {state['next_page']}, {len(rows)} scripts collected")

    sem = asyncio.Semaphore(CONCURRENCY)
    t0 = time.time()
    page = state["next_page"]
    stop = False

    async with aiohttp.ClientSession(headers=UA, timeout=aiohttp.ClientTimeout(total=25)) as session:
        while page <= MAX_PAGE and not stop:
            batch = list(range(page, min(page + CHUNK, MAX_PAGE + 1)))
            results = await asyncio.gather(*[fetch_page(session, sem, p) for p in batch])
            got = 0
            for data in results:
                if not data:
                    continue
                if data.get("__stop__"):
                    stop = True
                    continue
                got += 1
                for s in (data.get("result") or {}).get("scripts") or []:
                    rec = slim(s)
                    if not rec:
                        continue
                    if rec["id"] in rows:
                        continue
                    rows[rec["id"]] = rec
            page += CHUNK
            state["next_page"] = page
            save_state(state)
            print(f"[{min(page - 1, MAX_PAGE)}/{MAX_PAGE}] ok {got}/{len(batch)} | scripts {len(rows)} "
                  f"| {time.time() - t0:.0f}s", flush=True)
            if got == 0:
                print("[stop] no responses in this chunk")
                break

    OUT.write_text(json.dumps({"generated": time.time(), "count": len(rows), "scripts": list(rows.values())},
                              ensure_ascii=False), encoding="utf-8")
    games = len({r["placeId"] for r in rows.values()})
    print(f"\n[done] {len(rows)} scripts across {games} games -> {OUT}")


if __name__ == "__main__":
    asyncio.run(main())
