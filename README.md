# Nova Hub

Script hub for Roblox on Luna Interface Suite, backed by an automatically generated catalog.

## Current state

| metric | value |
| --- | --- |
| games in catalog | 6754 |
| games with 4 keyless + 4 key | 608 |
| games with 4+ keyless | 1016 |
| games with 4+ key-locked | 923 |
| scripts indexed | 9740 keyless + 8100 key |
| index size | 429 KB |
| per-game file | 0.5-2.4 KB |

## How it works

1. `harvest_index.py` walks every page of the rscripts.net API (`/api/v2/scripts?q=&page=N`, 2707 pages)
   and aggregates scripts by Roblox `placeId`. Resumable via `catalog/index_state.json`.
   Output: `catalog/catalog.json` (keyed by placeId, best 4 keyless + 4 key per game)
   and `catalog/games.json` (flat list).
2. `split_catalog.py` turns the catalog into what the hub actually downloads:
   `catalog/index.json` (placeId -> name + script counts) and `catalog/games/<placeId>.json`.
3. `NovaHub.lua` loads `index.json` (cached for an hour), finds the entry for `game.PlaceId`,
   downloads only that game's file, and renders `No key` / `With key` tabs. The `Catalog` tab
   searches all 6754 games and opens any of them on demand.

## Files

| file | purpose |
| --- | --- |
| `harvest_index.py` | full rscripts index -> catalog.json (main pipeline) |
| `split_catalog.py` | catalog.json -> index.json + games/<placeId>.json |
| `harvest_rscripts_games.py` | keyword-probe game discovery (superseded, kept as a fallback) |
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

```
git init
git remote add origin https://github.com/<you>/nova-hub.git
git add catalog/index.json catalog/games
git commit -m "catalog"
git push -u origin main
```

Then set `CATALOG_BASE` in `NovaHub.lua` to
`https://raw.githubusercontent.com/<you>/nova-hub/main/catalog`.
