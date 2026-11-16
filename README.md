# Vesper

A Roblox script hub on the Luna Interface Suite. It indexes 7096 games and shows the scripts published for the game you are sitting in, split into keyless and key-locked. If the game is not indexed, the Catalog tab searches everything and opens any game's scripts anyway.

```lua
loadstring(game:HttpGet("https://raw.githubusercontent.com/Siidodirnfb/Vesper-Hub/main/Vesper.lua"))()
```

## What it holds

| | |
| --- | --- |
| games | 7096 |
| scripts | 19 605 (9441 keyless, 10 164 key-locked) |
| games with 4 keyless and 4 key-locked | 774 |
| catalog size | 451 KB index, 0.3-1.8 KB per game |
| sources | rscripts.net, scriptblox.com |

The hub downloads the index once and caches it for an hour, then pulls only the file for the game in front of you. Nothing else is fetched until you press a script.

## The scripts are checked

Every link in the catalog was fetched during the build. 19 457 links were tested one by one and 786 were thrown out: 404s, empty stubs of 10 to 29 bytes, HTML error pages, patched entries. What shipped is the alive remainder, best four of each kind per game.

What "checked" means here, exactly:

- the link answers with HTTP 200;
- the body is a real script, not an HTML page and not a stub;
- the keyless or key-locked flag comes from the source API, not from guessing the title;
- universal scripts and entries marked patched are excluded.

What it does not mean: that every script still works in every executor today. Third-party authors break their own scripts without telling anyone. Re-check the current catalog at any time with:

```
python check_catalog.py 200
```

## If you are in Russia

The hub itself, its catalog and rscripts.net are reachable without a VPN, checked from a Russian network.

Some scripts are not. They call hosts that Russian ISPs block, most often `api.luarmor.net`, gateway and key-service APIs. The symptom is a button that does nothing, or a notification saying the script did not run. The catalog is fine in that case, the script's own host is not. Turn on a VPN and press the same button again.

## Trust

The hub is ~200 lines of readable Lua. It only sends HTTP GET requests, has no `HttpPost`, no webhook, no clipboard access, and writes nothing except its own cache folder. Full host list, the exact grep commands and the reasoning are in [TRUST.md](TRUST.md).

Scripts themselves are third-party code. They can do what any Roblox script can do in your client, which is why every button shows the script's title and views instead of an "OP" label.

## License and copies

[LICENSE](LICENSE) allows reading, forking and modifying, and requires one thing: keep the credit and the build id. Selling it behind a key gate, or rebranding the catalog as your own, is outside the license.

Two markers make a copy visible:

- `BUILD` in `Vesper.lua` and `build` in `catalog/index.json` carry the same id;
- [PROVENANCE.md](PROVENANCE.md) lists the sha256 of every published file, regenerated on each rebuild, and `python verify.py` recomputes them.

A copy that keeps the id can be traced to the commit it came from. A copy that strips it is, by that act, an unlicensed fork. Neither stops anyone. Both make the difference between the original and a reupload a matter of record instead of a matter of opinion.

## How it is built

1. `harvest_index.py` walks every page of the rscripts.net API (`/api/v2/scripts?q=&page=N`, 2707 pages) and groups scripts by Roblox `placeId`.
2. `harvest_scriptblox.py` walks scriptblox.com `/api/script/fetch?page=N` (pages 1-500, later pages return HTTP 400) and keeps entries with a real `game.gameId`.
3. `merge_sources.py` merges both pools, ranks them, and verifies every raw link. Checkpoints to `catalog/merge_partial.json`.
4. `fill_gaps.py` searches ScriptBlox by game name for games still short, and keeps only results whose `game.gameId` matches that exact placeId.
5. `recover_429.py` puts back links that were dropped only because of rate limiting.
6. `split_catalog.py` splits the result into `catalog/index.json` and one `catalog/games/<placeId>.json` per game.

Ranking is `views + likes * 12 + executes * 2 + verified bonus + recency bonus`. Recency decays over about two years, so a script from 2019 does not outrank a working one from this month just because it has old views.

## Files

| file | purpose |
| --- | --- |
| `Vesper.lua` | the hub |
| `harvest_index.py` | full rscripts index |
| `harvest_scriptblox.py` | ScriptBlox pool |
| `merge_sources.py` | merge, rank, verify links |
| `fill_gaps.py` | targeted search for missing slots |
| `recover_429.py` | re-add links dropped by rate limiting |
| `split_catalog.py` | catalog -> index + per-game files |
| `check_catalog.py` | re-check a sample of shipped links |
| `verify.py` | recompute published hashes |
| `provenance.py` | regenerate PROVENANCE.md |
| `find_donors.py` | GitHub donor scanner (mostly SEO spam, kept for reference) |
| `harvest_rscripts_games.py`, `harvest_games2.py`, `build_catalog2.py` | earlier approaches, superseded |
| `proxy_health.py` | free proxy sweeper, unused |

## Rebuilding

```
pip install aiohttp
python harvest_index.py        # ~6 min, 2707 requests
python harvest_scriptblox.py   # ~6 min, 500 requests
python merge_sources.py        # ~35 min, checks every link
python fill_gaps.py
python recover_429.py
python split_catalog.py
python provenance.py
python check_catalog.py 200

git add -A && git commit -m "catalog refresh" && git push
```

Two habits keep the pipeline honest. The API only paginates when `q` is empty; with `orderBy` set, `page` returns HTTP 500. And `game.placeId` inside a script record is the only id trusted for matching a script to a game.
