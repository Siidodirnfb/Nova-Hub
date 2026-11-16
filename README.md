# Nova Hub

Script hub for Roblox on Luna Interface Suite, backed by an automatically generated catalog.

## Current state

| metric | value |
| --- | --- |
| games in catalog | 7096 |
| shipped scripts | 9441 keyless + 10164 key |
| games with 4 keyless + 4 key | 774 |
| games with 4+ keyless | 935 |
| games with 4+ key-locked | 1070 |
| index size | 451 KB |
| per-game file | 0.3-1.8 KB |
| sampled raw links alive | 80/80 |

Sources: rscripts.net (full index, 2707 pages, ~43k scripts) and scriptblox.com
(500 pages + per-game search). Every raw link in the catalog was fetched and
verified; empty stubs, 404s and HTML error pages are rejected automatically
(`catalog/rejected_urls.json` keeps the count, not the junk).

## How it works

1. `harvest_index.py` walks every page of the rscripts.net API (`/api/v2/scripts?q=&page=N`, 2707 pages)
   and aggregates scripts by Roblox `placeId`. Resumable via `catalog/index_state.json`.
2. `harvest_scriptblox.py` walks scriptblox.com `/api/script/fetch?page=N` (pages 1-500; later pages
   return HTTP 400) and keeps modern scripts with a real `game.gameId`. Output: `catalog/scriptblox.json`.
3. `merge_sources.py` merges both pools, ranks scripts, and verifies every raw link
   (status 200, real body, not an HTML page). Checkpoints to `catalog/merge_partial.json`.
4. `fill_gaps.py` searches ScriptBlox by game name for games still short of 4+4 and keeps only
   results whose `game.gameId` matches that exact placeId.
5. `recover_429.py` puts back links that were dropped purely because of rate limiting.
6. `split_catalog.py` turns the catalog into what the hub actually downloads:
   `catalog/index.json` (placeId -> name + script counts) and `catalog/games/<placeId>.json`.
7. `NovaHub.lua` loads `index.json` (cached for an hour), finds the entry for `game.PlaceId`,
   downloads only that game's file, and renders `No key` / `With key` tabs. The `Catalog` tab
   searches all 7096 games and opens any of them on demand.

## Coverage reality

Only 774 of the 7096 games have four keyless *and* four key-locked scripts, because that is all
the sources publish. Every other game shows as many scripts as exist (1-3 in a category).
Nothing is padded with unrelated scripts.

## Files

| file | purpose |
| --- | --- |
| `harvest_index.py` | full rscripts index -> catalog pool |
| `harvest_scriptblox.py` | ScriptBlox donor pool |
| `merge_sources.py` | merge + rank + verify raw links |
| `fill_gaps.py` | targeted per-game search for missing slots |
| `recover_429.py` | re-add links dropped by rate limiting |
| `split_catalog.py` | catalog.json -> index.json + games/<placeId>.json |
| `check_catalog.py` | samples shipped scripts and re-checks raw links |
| `find_donors.py` | GitHub donor scanner (mostly SEO spam, kept for reference) |
| `harvest_rscripts_games.py` | keyword-probe game discovery (superseded) |
| `harvest_games2.py` | explore-api game harvest via roproxy (superseded) |
| `build_catalog2.py` | per-game search builder (superseded) |
| `NovaHub.lua` | the hub |
| `proxy_health.py` | free proxy sweeper (unused) |
| `show_catalog.py` | prints a readable slice of the catalog |

## Running

```
pip install aiohttp
python harvest_index.py     # ~6 min, 2707 requests
python split_catalog.py
```

## Notes

- The rscripts API only paginates when `q` is empty. With `orderBy` set, `page` returns HTTP 500.
- `keySystem` is the keyless/key-locked flag.
- `game.placeId` inside each script record is the authoritative game id.
- Scripts run as `loadstring(game:HttpGet(rawScript, true))()`.
- `CATALOG_BASE` inside `NovaHub.lua` must point at the published raw catalog before the hub works for players.

## Publishing

The catalog lives at `https://github.com/Siidodirnfb/Nova-Hub` and the hub reads it from
`https://raw.githubusercontent.com/Siidodirnfb/Nova-Hub/main/catalog`.

To refresh after rebuilding:

```
python harvest_index.py
python harvest_scriptblox.py
python merge_sources.py
python fill_gaps.py
python recover_429.py
python split_catalog.py
python check_catalog.py 80

git add -A
git commit -m "catalog refresh"
git push
```

Players load the hub with:

```lua
loadstring(game:HttpGet("https://raw.githubusercontent.com/Siidodirnfb/Nova-Hub/main/NovaHub.lua"))()
```

