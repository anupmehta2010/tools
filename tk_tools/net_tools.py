"""Network tools: HTTP, download, DNS, ping, port-scan, my-ip, whois, URL check."""
from __future__ import annotations

import argparse
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))
from _common import tool_main


# ---- HTTP ----

def cmd_http(args):
    headers = {}
    for h in args.header or []:
        if ":" in h:
            k, v = h.split(":", 1)
            headers[k.strip()] = v.strip()
    req_body = None
    if args.data:
        req_body = args.data.encode("utf-8")
        headers.setdefault("Content-Type", "application/json" if args.json else "text/plain")
    req = urllib.request.Request(args.url, method=args.method, data=req_body)
    for k, v in headers.items():
        req.add_header(k, v)
    try:
        resp = urllib.request.urlopen(req, timeout=args.timeout)
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code} {e.reason}")
        print(e.read().decode("utf-8", errors="replace"))
        return e.code
    print(f"Status: {resp.status} {resp.reason}")
    if args.show_headers:
        for k, v in resp.getheaders():
            print(f"{k}: {v}")
        print()
    body = resp.read()
    if args.output:
        Path(args.output).write_bytes(body)
        print(f"Wrote {len(body):,} bytes -> {args.output}")
    else:
        print(body.decode("utf-8", errors="replace"))


def cmd_download(args):
    url = args.url
    if args.output:
        out = Path(args.output)
    else:
        name = Path(urllib.parse.urlsplit(url).path).name or "download.bin"
        out = Path(name)

    with urllib.request.urlopen(url, timeout=args.timeout) as resp:
        total = int(resp.headers.get("Content-Length", 0))
        downloaded = 0
        last = time.time()
        with open(out, "wb") as f:
            while True:
                chunk = resp.read(64 * 1024)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)
                now = time.time()
                if now - last > 0.2 or downloaded == total:
                    pct = (downloaded * 100 / total) if total else 0
                    print(f"\r  {downloaded:>12,} bytes ({pct:5.1f}%)", end="", flush=True)
                    last = now
    print(f"\nWrote {out}")


# ---- DNS ----

def cmd_dns(args):
    try:
        ip = socket.gethostbyname(args.host)
        print(f"{args.host} -> {ip}")
    except socket.gaierror as e:
        print(f"Lookup failed: {e}")
        return 1
    if args.all:
        try:
            seen = set()
            for info in socket.getaddrinfo(args.host, None):
                fam, _, _, _, sockaddr = info
                addr = sockaddr[0]
                if addr in seen:
                    continue
                seen.add(addr)
                fam_name = getattr(fam, "name", str(fam))
                print(f"  {fam_name}: {addr}")
        except socket.gaierror:
            pass


def cmd_reverse_dns(args):
    try:
        host, _, _ = socket.gethostbyaddr(args.ip)
        print(host)
    except socket.herror as e:
        print(f"Reverse lookup failed: {e}")
        return 1


# ---- Port scan (TCP) ----

def cmd_port_scan(args):
    host = args.host
    ports: list[int] = []
    for spec in args.ports:
        if "-" in spec:
            a, b = spec.split("-", 1)
            ports.extend(range(int(a), int(b) + 1))
        else:
            ports.append(int(spec))
    open_ports = []
    for port in ports:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(args.timeout)
            try:
                s.connect((host, port))
                open_ports.append(port)
                try:
                    name = socket.getservbyport(port)
                except OSError:
                    name = "?"
                print(f"  {port:>5}/tcp open ({name})")
            except (socket.timeout, ConnectionRefusedError, OSError):
                pass
    print(f"\n{len(open_ports)}/{len(ports)} ports open")


# ---- IP info ----

def cmd_my_ip(args):
    print(f"Hostname:  {socket.gethostname()}")
    try:
        local_ip = socket.gethostbyname(socket.gethostname())
        print(f"Local IP:  {local_ip}")
    except socket.gaierror:
        pass
    # All local interface IPs
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None):
            fam, _, _, _, addr = info
            print(f"  iface:   {addr[0]}")
    except socket.gaierror:
        pass
    try:
        with urllib.request.urlopen("https://api.ipify.org", timeout=5) as r:
            print(f"Public IP: {r.read().decode()}")
    except Exception as e:
        print(f"Could not fetch public IP: {e}")


# ---- Ping (OS) ----

def cmd_ping(args):
    if sys.platform.startswith("win"):
        cmd = ["ping", "-n", str(args.count), args.host]
    else:
        cmd = ["ping", "-c", str(args.count), args.host]
    return subprocess.call(cmd)


# ---- WHOIS ----

def cmd_whois(args):
    server = args.server
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(args.timeout)
        s.connect((server, 43))
        s.sendall((args.query + "\r\n").encode())
        chunks = []
        while True:
            data = s.recv(4096)
            if not data:
                break
            chunks.append(data)
    print(b"".join(chunks).decode("utf-8", errors="replace"))


# ---- URL check ----

def cmd_check(args):
    start = time.time()
    try:
        resp = urllib.request.urlopen(args.url, timeout=args.timeout)
        elapsed = (time.time() - start) * 1000
        print(f"OK    {resp.status}  {elapsed:>6.0f} ms  {args.url}")
        return 0
    except Exception as e:
        elapsed = (time.time() - start) * 1000
        print(f"FAIL       {elapsed:>6.0f} ms  {args.url}  ({e})")
        return 1


# ---- Headers only (HEAD via custom request) ----

def cmd_ssl_info(args):
    """Show TLS certificate info for host:port."""
    import ssl, socket as _sk
    host = args.host
    port = args.port
    ctx = ssl.create_default_context()
    with _sk.create_connection((host, port), timeout=args.timeout) as sock:
        with ctx.wrap_socket(sock, server_hostname=host) as ss:
            cert = ss.getpeercert()
    print(f"Subject:")
    for rdn in cert.get("subject", []):
        for k, v in rdn:
            print(f"  {k:<24} {v}")
    print(f"\nIssuer:")
    for rdn in cert.get("issuer", []):
        for k, v in rdn:
            print(f"  {k:<24} {v}")
    print(f"\nValidity: {cert.get('notBefore')}  ->  {cert.get('notAfter')}")
    sans = cert.get("subjectAltName", [])
    if sans:
        print(f"\nSubjectAltName ({len(sans)}):")
        for kind, val in sans[:20]:
            print(f"  {kind}: {val}")


def cmd_url_parse(args):
    p = urllib.parse.urlsplit(args.url)
    print(f"Scheme:    {p.scheme}")
    print(f"Hostname:  {p.hostname}")
    print(f"Port:      {p.port}")
    print(f"Path:      {p.path}")
    print(f"Query:     {p.query}")
    print(f"Fragment:  {p.fragment}")
    if p.username:
        print(f"User:      {p.username}")
    qs = urllib.parse.parse_qsl(p.query, keep_blank_values=True)
    if qs:
        print("\nQuery params:")
        for k, v in qs:
            print(f"  {k:<20} {v}")


def cmd_url_build(args):
    """Build a URL from parts and query parameters."""
    qs = []
    for kv in args.params or []:
        if "=" in kv:
            k, v = kv.split("=", 1)
            qs.append((k, v))
    query = urllib.parse.urlencode(qs)
    parts = urllib.parse.urlsplit(args.base)
    new = parts._replace(query=query, path=args.path or parts.path)
    print(urllib.parse.urlunsplit(new))


def cmd_headers(args):
    req = urllib.request.Request(args.url, method="HEAD")
    try:
        with urllib.request.urlopen(req, timeout=args.timeout) as resp:
            print(f"Status: {resp.status} {resp.reason}")
            for k, v in resp.getheaders():
                print(f"{k}: {v}")
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code} {e.reason}")
        return e.code


COMMANDS = {
    "http":      "send HTTP request and print response",
    "download":  "download a file with progress",
    "dns":       "DNS lookup (host -> IP)",
    "rdns":      "reverse DNS (IP -> host)",
    "ping":      "ping a host (uses OS ping)",
    "port-scan": "scan TCP ports on a host",
    "my-ip":     "show local and public IP",
    "whois":     "WHOIS lookup",
    "check":     "check URL reachability with timing",
    "headers":   "fetch only response headers (HEAD)",
    "ssl-info":  "show TLS certificate info for host",
    "url-parse": "decompose URL into parts (and query params)",
    "url-build": "compose URL from base + query params",
}


def build_parser(parser=None):
    parser = parser or argparse.ArgumentParser(prog="net_tools", description="Network utilities")
    sub = parser.add_subparsers(dest="cmd")

    p = sub.add_parser("http", help=COMMANDS["http"])
    p.add_argument("url")
    p.add_argument("-X", "--method", default="GET")
    p.add_argument("-H", "--header", action="append")
    p.add_argument("-d", "--data")
    p.add_argument("--json", action="store_true")
    p.add_argument("-o", "--output")
    p.add_argument("--show-headers", action="store_true")
    p.add_argument("--timeout", type=int, default=30)
    p.set_defaults(func=cmd_http)

    p = sub.add_parser("download", help=COMMANDS["download"])
    p.add_argument("url"); p.add_argument("-o", "--output")
    p.add_argument("--timeout", type=int, default=60)
    p.set_defaults(func=cmd_download)

    p = sub.add_parser("dns", help=COMMANDS["dns"])
    p.add_argument("host")
    p.add_argument("--all", action="store_true")
    p.set_defaults(func=cmd_dns)

    p = sub.add_parser("rdns", help=COMMANDS["rdns"])
    p.add_argument("ip")
    p.set_defaults(func=cmd_reverse_dns)

    p = sub.add_parser("ping", help=COMMANDS["ping"])
    p.add_argument("host")
    p.add_argument("--count", type=int, default=4)
    p.set_defaults(func=cmd_ping)

    p = sub.add_parser("port-scan", help=COMMANDS["port-scan"])
    p.add_argument("host")
    p.add_argument("ports", nargs="+", help="e.g. 22 80 443 1000-1100")
    p.add_argument("--timeout", type=float, default=0.5)
    p.set_defaults(func=cmd_port_scan)

    p = sub.add_parser("my-ip", help=COMMANDS["my-ip"])
    p.set_defaults(func=cmd_my_ip)

    p = sub.add_parser("whois", help=COMMANDS["whois"])
    p.add_argument("query")
    p.add_argument("--server", default="whois.iana.org")
    p.add_argument("--timeout", type=float, default=10)
    p.set_defaults(func=cmd_whois)

    p = sub.add_parser("check", help=COMMANDS["check"])
    p.add_argument("url")
    p.add_argument("--timeout", type=int, default=10)
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("headers", help=COMMANDS["headers"])
    p.add_argument("url")
    p.add_argument("--timeout", type=int, default=10)
    p.set_defaults(func=cmd_headers)

    p = sub.add_parser("ssl-info", help=COMMANDS["ssl-info"])
    p.add_argument("host")
    p.add_argument("--port", type=int, default=443)
    p.add_argument("--timeout", type=float, default=10)
    p.set_defaults(func=cmd_ssl_info)

    p = sub.add_parser("url-parse", help=COMMANDS["url-parse"])
    p.add_argument("url")
    p.set_defaults(func=cmd_url_parse)

    p = sub.add_parser("url-build", help=COMMANDS["url-build"])
    p.add_argument("base")
    p.add_argument("--path")
    p.add_argument("--params", nargs="+", help="key=value pairs")
    p.set_defaults(func=cmd_url_build)

    return parser


@tool_main("net")
def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 1
    return args.func(args) or 0


if __name__ == "__main__":
    raise SystemExit(main())
