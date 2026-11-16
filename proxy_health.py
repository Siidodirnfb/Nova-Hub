# Nova Hub aggregator - proxy health checker v2
# Sweeps free proxy lists (proxifly + proxyscrape) in parallel against ScriptBlox,
# saves live ones to proxies/live.json. Stops early once STOP_AFTER found.
import asyncio, json, time, ssl
from pathlib import Path

import aiohttp
from aiohttp_socks import ProxyConnector

ROOT = Path(__file__).parent
OUT = ROOT / "proxies"
OUT.mkdir(exist_ok=True)

SOURCES = [
    ("https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/all/data.json", "proxifly"),
    ("https://api.proxyscrape.com/v4/free-proxy-list/get?request=display_proxies&proxytype=socks5&country=all", "proxyscrape_s5"),
    ("https://api.proxyscrape.com/v4/free-proxy-list/get?request=display_proxies&proxytype=http&country=all", "proxyscrape_http"),
]

TARGET = "https://scriptblox.com/api/v1/mod/fetch-trending?max=1"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"}
TIMEOUT = aiohttp.ClientTimeout(total=12)
CONCURRENCY = 250
STOP_AFTER = 25

# free proxies MITM TLS with self-signed certs; we only fetch public JSON, so verify off
SSL_CTX = ssl.create_default_context()
SSL_CTX.check_hostname = False
SSL_CTX.verify_mode = ssl.CERT_NONE

stop_event = asyncio.Event()


async def fetch_sources(session):
    proxies = {}
    for url, name in SOURCES:
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as r:
                t = await r.text()
            if name == "proxifly":
                for p in json.loads(t):
                    if p.get("protocol") in ("http", "https", "socks4", "socks5"):
                        scheme = "http" if p["protocol"] in ("http", "https") else p["protocol"]
                        proxies[f"{scheme}://{p['ip']}:{p['port']}"] = name
            else:
                scheme = "socks5" if "socks" in name else "http"
                for line in t.splitlines():
                    line = line.strip()
                    if line and line.count(":") == 1 and not line[0].isalpha():
                        proxies[f"{scheme}://{line}"] = name
            print(f"[source] {name}: ok (pool {len(proxies)})")
        except Exception as e:
            print(f"[source] {name}: FAIL {e}")
    return list(proxies)


async def check(session, sem, url, results):
    if stop_event.is_set():
        return
    async with sem:
        if stop_event.is_set():
            return
        connector = None
        try:
            if url.startswith(("socks4", "socks5")):
                connector = ProxyConnector.from_url(url, ssl=SSL_CTX)
                async with aiohttp.ClientSession(connector=connector, timeout=TIMEOUT) as ps:
                    async with ps.get(TARGET, headers=UA, ssl=SSL_CTX) as r:
                        body = await r.text()
                        ok = r.status == 200 and '"success"' in body
            else:
                async with session.get(TARGET, headers=UA, proxy=url, ssl=SSL_CTX) as r:
                    body = await r.text()
                    ok = r.status == 200 and '"success"' in body
            if ok:
                results.append(url)
                print(f"[LIVE] {url}  ({len(results)}/{STOP_AFTER})")
                if len(results) >= STOP_AFTER:
                    stop_event.set()
            else:
                print(f"[dead {r.status}] {url}")
        except Exception as e:
            print(f"[err] {url} :: {type(e).__name__}")
        finally:
            if connector and not connector.closed:
                await connector.close()


async def main():
    async with aiohttp.ClientSession() as session:
        proxies = await fetch_sources(session)
    print(f"\n[pool] {len(proxies)} proxies, concurrency {CONCURRENCY}\n")
    sem = asyncio.Semaphore(CONCURRENCY)
    results = []
    tasks = [check(session, sem, u, results) for u in proxies]
    t0 = time.time()
    await asyncio.gather(*tasks)
    print(f"\n[done] {len(results)} alive in {time.time()-t0:.0f}s")
    (OUT / "live.json").write_text(json.dumps({"checked": time.time(), "live": results}, indent=1))
    if not results:
        print("[!] none reached ScriptBlox this sweep")


if __name__ == "__main__":
    asyncio.run(main())
