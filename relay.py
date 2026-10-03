"""DataImpulse SOCKS5 relay via pproxy library API.

Local socks5 (no auth) on 127.0.0.1:1080 -> upstream socks5://user:pass@gw.dataimpulse.com:823.
Playwright-Firefox can't do socks5-with-auth; this bridges it.

Published form: the upstream proxy endpoint + credentials are read from the
environment at runtime (UPSTREAM_URI). The original local script resolved
them from a secret store; nothing is embedded here.
"""
import asyncio
import os

import pproxy


async def main():
    endpoint = os.environ["UPSTREAM_URI"]  # e.g. socks5://user:pass@gw.dataimpulse.com:823
    print("upstream:", endpoint.split("@")[1], flush=True)
    remote, jump = pproxy.server.proxy_by_uri(endpoint, None)
    server = pproxy.Server(socks5="socks5://127.0.0.1:1080")
    srv, _ = await server.start_server(remote=remote)
    print("relay listening on 127.0.0.1:1080", flush=True)
    async with srv:
        await srv.serve_forever()


asyncio.run(main())