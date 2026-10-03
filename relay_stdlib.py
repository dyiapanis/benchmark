"""SOCKS5 auth relay, stdlib only.

Listens: socks5, NO auth, 127.0.0.1:1080 (what Playwright-Firefox accepts).
Upstream: DataImpulse gw.dataimpulse.com:823, SOCKS5 username/password auth (RFC 1929).

Handshake per connection: read browser's greeting + request (no-auth), dial upstream,
greet with user/pass auth, replay the CONNECT, then splice byte streams.

Published form: upstream credentials are read from the environment at runtime
(DATAIMPULSE_LOGIN / DATAIMPULSE_PASSWORD). The original local script resolved
them from a secret store; nothing is embedded here.
"""
import os
import socket
import struct
import threading

LISTEN = ("127.0.0.1", 1080)
UP_HOST = "gw.dataimpulse.com"
UP_PORT = 823

USER = os.environ["DATAIMPULSE_LOGIN"].encode()
PASS = os.environ["DATAIMPULSE_PASSWORD"].encode()


def recv_exact(sock, n):
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("eof")
        buf += chunk
    return buf


def handle(client: socket.socket):
    try:
        # ── browser side greeting (no auth) ──
        hdr = recv_exact(client, 2)
        ver, nmethods = hdr[0], hdr[1]
        recv_exact(client, nmethods)
        client.sendall(b"\x05\x00")  # no-auth OK

        # ── browser request ──
        req = recv_exact(client, 4)
        if req[1] != 1:  # only CONNECT
            client.sendall(b"\x05\x07\x00\x01" + b"\x00" * 4 + b"\x00" * 2)
            return
        atyp = req[3]
        if atyp == 1:
            addr_bytes = recv_exact(client, 4)
            host = socket.inet_ntoa(addr_bytes)
        elif atyp == 3:
            ln = recv_exact(client, 1)[0]
            addr_bytes = recv_exact(client, ln)
            host = addr_bytes.decode()
        else:
            recv_exact(client, 16)
            host = "unhandled-ipv6"
        port = struct.unpack(">H", recv_exact(client, 2))[0]

        # ── upstream connect + user/pass auth ──
        up = socket.create_connection((UP_HOST, UP_PORT), timeout=20)
        up.sendall(b"\x05\x01\x02")               # offer user/pass auth
        up.recv(2)                                 # \x05\x02
        up.sendall(b"\x01" + bytes([len(USER)]) + USER + bytes([len(PASS)]) + PASS)
        resp = recv_exact(up, 2)
        if resp[1] != 0:
            raise ConnectionError("upstream auth failed")

        # ── upstream CONNECT ──
        if atyp == 3:
            upreq = b"\x05\x01\x00\x03" + bytes([len(addr_bytes)]) + addr_bytes
        else:
            upreq = b"\x05\x01\x00\x01" + addr_bytes
        up.sendall(upreq + struct.pack(">H", port))
        upresp = recv_exact(up, 4)
        if upresp[1] != 0:
            raise ConnectionError(f"upstream connect refused code {upresp[1]}")
        # consume bound addr
        if upresp[3] == 1:
            recv_exact(up, 4 + 2)
        elif upresp[3] == 3:
            ln = recv_exact(up, 1)[0]
            recv_exact(up, ln + 2)
        elif upresp[3] == 4:
            recv_exact(up, 16 + 2)

        # success to browser
        client.sendall(b"\x05\x00\x00\x01" + socket.inet_aton("0.0.0.0") + struct.pack(">H", 0))

        # ── splice ──
        def pipe(a, b):
            try:
                while True:
                    data = a.recv(65536)
                    if not data:
                        break
                    b.sendall(data)
            except OSError:
                pass
            finally:
                try:
                    b.shutdown(socket.SHUT_WR)
                except OSError:
                    pass

        t1 = threading.Thread(target=pipe, args=(client, up), daemon=True)
        t2 = threading.Thread(target=pipe, args=(up, client), daemon=True)
        t1.start(); t2.start(); t1.join(); t2.join()
    except Exception:
        pass  # per-connection failure; browser sees closed conn
    finally:
        try:
            client.close()
        except OSError:
            pass


def main():
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(LISTEN)
    srv.listen(64)
    print(f"relay listening {LISTEN}", flush=True)
    while True:
        c, _ = srv.accept()
        threading.Thread(target=handle, args=(c,), daemon=True).start()


if __name__ == "__main__":
    main()