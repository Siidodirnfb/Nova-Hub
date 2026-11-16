# one-shot proxy test against ipify + ScriptBlox
import asyncio, ssl, json
import aiohttp, aiohttp_socks

PROXIES = ["199.58.185.9:4145", "192.111.139.162:4145", "49.13.22.249:10807"]
TARGETS = ["https://api.ipify.org?format=json",
           "https://scriptblox.com/api/v1/mod/fetch-trending?max=2"]
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE


async def main():
    for p in PROXIES:
        c = aiohttp_socks.ProxyConnector.from_url("socks5://" + p)
        async with aiohttp.ClientSession(connector=c, timeout=aiohttp.ClientTimeout(total=15)) as s:
            for target in TARGETS:
                try:
                    async with s.get(target, ssl=ctx) as r:
                        body = (await r.text())[:250]
                        print(f"{p} -> {target.split('/')[2]} : HTTP {r.status} :: {body}")
                except Exception as e:
                    print(f"{p} -> {target.split('/')[2]} : {type(e).__name__} {e}")

asyncio.run(main())
