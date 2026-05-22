"""Advanced network tools: SSL inspect, headers analyze, JWT verify, HAR view, traceroute, speedtest, DNS, CORS, redirects, cookies."""
from __future__ import annotations

import argparse
import json
import socket
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from http.cookies import SimpleCookie
from pathlib import Path

from _common import human_size, lazy_import, tool_main

UA = "tk/1.0"


def _open(url, method="GET", headers=None, data=None, timeout=30):
    req = urllib.request.Request(url, method=method, data=data)
    req.add_header("User-Agent", UA)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    return urllib.request.urlopen(req, timeout=timeout)


# ---- ssl-info ----

def cmd_ssl_info(args):
    host, _, port = args.target.partition(":")
    port = int(port) if port else 443
    ctx = ssl.create_default_context()
    with socket.create_connection((host, port), timeout=args.timeout) as sock:
        with ctx.wrap_socket(sock, server_hostname=host) as ss:
            cert = ss.getpeercert()
            der = ss.getpeercert(binary_form=True)
            cipher = ss.cipher()
            version = ss.version()
    print(f"Host:        {host}:{port}")
    print(f"TLS:         {version}  cipher={cipher[0]}")
    print("Subject:")
    for rdn in cert.get("subject", []):
        for k, v in rdn:
            print(f"  {k:<24} {v}")
    print("Issuer:")
    for rdn in cert.get("issuer", []):
        for k, v in rdn:
            print(f"  {k:<24} {v}")
    nb = cert.get("notBefore"); na = cert.get("notAfter")
    print(f"Valid from:  {nb}")
    print(f"Valid until: {na}")
    try:
        exp = datetime.strptime(na, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
        delta = exp - datetime.now(timezone.utc)
        print(f"Days remain: {delta.days}")
    except Exception:
        pass
    sans = cert.get("subjectAltName", [])
    if sans:
        print(f"SAN ({len(sans)}):")
        for kind, val in sans:
            print(f"  {kind}: {val}")
    # Try crypto for key/sig details
    try:
        lazy_import("cryptography", "pip install cryptography")
        from cryptography import x509
        from cryptography.hazmat.primitives.asymmetric import ec, rsa
        c = x509.load_der_x509_certificate(der)
        print(f"Signature:   {c.signature_hash_algorithm.name if c.signature_hash_algorithm else '?'} / {c.signature_algorithm_oid._name}")
        pub = c.public_key()
        if isinstance(pub, rsa.RSAPublicKey):
            print(f"Key:         RSA {pub.key_size} bits")
        elif isinstance(pub, ec.EllipticCurvePublicKey):
            print(f"Key:         EC {pub.curve.name}")
        else:
            print(f"Key:         {type(pub).__name__}")
        print(f"Serial:      {c.serial_number:x}")
    except SystemExit:
        pass


# ---- header-analyze ----

SECURITY_HEADERS = {
    "strict-transport-security": "HSTS",
    "content-security-policy":   "CSP",
    "x-frame-options":           "X-Frame-Options",
    "x-content-type-options":    "X-Content-Type-Options",
    "referrer-policy":           "Referrer-Policy",
    "permissions-policy":        "Permissions-Policy",
}


def cmd_header_analyze(args):
    resp = _open(args.url, timeout=args.timeout)
    print(f"Status: {resp.status} {resp.reason}\n")
    hdrs = {k.lower(): v for k, v in resp.getheaders()}
    for k, v in resp.getheaders():
        print(f"{k}: {v}")
    print("\nSecurity audit:")
    score = 0
    each = 100 / len(SECURITY_HEADERS)
    for key, label in SECURITY_HEADERS.items():
        if key in hdrs:
            print(f"  [OK]      {label}: {hdrs[key][:80]}")
            score += each
        else:
            print(f"  [MISSING] {label}")
    print(f"\nScore: {int(round(score))}/100")


# ---- jwt-verify ----

def cmd_jwt_verify(args):
    jwt = lazy_import("jwt", "pip install pyjwt[crypto]")
    key = None
    if args.key_file:
        key = Path(args.key_file).read_bytes()
    elif args.secret:
        key = args.secret
    if key is None:
        print("Provide --secret or --key-file")
        return 1
    algos = [args.algo] if args.algo else ["HS256", "HS384", "HS512",
                                            "RS256", "RS384", "RS512",
                                            "ES256", "ES384"]
    try:
        decoded = jwt.decode(args.token, key, algorithms=algos,
                             options={"verify_aud": False})
        print("Signature: VALID")
        print("Claims:")
        print(json.dumps(decoded, indent=2, default=str))
        return 0
    except Exception as e:
        print(f"Signature: INVALID ({e})")
        try:
            unverified = jwt.decode(args.token, options={"verify_signature": False})
            print("Unverified claims:")
            print(json.dumps(unverified, indent=2, default=str))
        except Exception:
            pass
        return 1


# ---- har-view ----

def cmd_har_view(args):
    data = json.loads(Path(args.input).read_text(encoding="utf-8"))
    entries = data.get("log", {}).get("entries", [])
    print(f"{'METHOD':<7} {'STATUS':<6} {'MS':>7} {'SIZE':>10}  URL")
    print("-" * 100)
    tot_ms = 0; tot_size = 0
    for e in entries:
        req = e.get("request", {})
        resp = e.get("response", {})
        ms = int(e.get("time", 0))
        size = resp.get("bodySize", 0) or 0
        if size < 0: size = 0
        method = req.get("method", "?")
        status = resp.get("status", 0)
        url = req.get("url", "")
        print(f"{method:<7} {status:<6} {ms:>7} {human_size(size):>10}  {url[:60]}")
        tot_ms += ms; tot_size += size
    print(f"\nTotal: {len(entries)} requests, {tot_ms}ms, {human_size(tot_size)}")


# ---- traceroute ----

def cmd_traceroute(args):
    if sys.platform.startswith("win"):
        cmd = ["tracert", "-d" if args.no_resolve else "-h", str(args.max_hops), args.host] if args.no_resolve \
              else ["tracert", "-h", str(args.max_hops), args.host]
    else:
        cmd = ["traceroute", "-m", str(args.max_hops), args.host]
        if args.no_resolve:
            cmd.insert(1, "-n")
    return subprocess.call(cmd)


# ---- speedtest ----

def cmd_speedtest(args):
    url = args.url
    print(f"Download: {url}")
    start = time.time()
    total = 0
    with _open(url, timeout=args.timeout) as r:
        while True:
            chunk = r.read(64 * 1024)
            if not chunk:
                break
            total += len(chunk)
            elapsed = time.time() - start
            if elapsed > 0:
                mbps = (total * 8) / elapsed / 1_000_000
                print(f"\r  {human_size(total):>10}  {mbps:6.2f} Mbps", end="", flush=True)
    elapsed = time.time() - start
    mbps = (total * 8) / elapsed / 1_000_000 if elapsed else 0
    print(f"\nDownloaded {human_size(total)} in {elapsed:.2f}s -> {mbps:.2f} Mbps")


# ---- dns-lookup ----

def cmd_dns_lookup(args):
    dns = lazy_import("dns.resolver", "pip install dnspython")
    types = args.types.split(",") if args.types else ["A", "AAAA", "MX", "TXT", "NS", "CNAME"]
    resolver = dns.resolver.Resolver()
    if args.server:
        resolver.nameservers = [args.server]
    for t in types:
        try:
            ans = resolver.resolve(args.host, t, raise_on_no_answer=False)
            recs = list(ans) if ans.rrset is not None else []
            if not recs:
                print(f"{t:<6}  (no records)")
                continue
            for r in recs:
                print(f"{t:<6}  {r.to_text()}")
        except Exception as e:
            print(f"{t:<6}  ERROR: {e}")


# ---- cors-check ----

def cmd_cors_check(args):
    headers = {
        "Origin": args.origin,
        "Access-Control-Request-Method": args.method,
        "Access-Control-Request-Headers": "content-type",
    }
    try:
        resp = _open(args.url, method="OPTIONS", headers=headers, timeout=args.timeout)
    except urllib.error.HTTPError as e:
        resp = e
    print(f"Status: {resp.status} {resp.reason if hasattr(resp, 'reason') else ''}\n")
    found = False
    for k, v in resp.getheaders():
        if k.lower().startswith("access-control-"):
            print(f"{k}: {v}")
            found = True
    if not found:
        print("(no Access-Control-* headers in response)")


# ---- redirects ----

def cmd_redirects(args):
    url = args.url
    chain = []
    for hop in range(args.max_hops):
        req = urllib.request.Request(url, method="HEAD")
        req.add_header("User-Agent", UA)
        try:
            opener = urllib.request.build_opener(urllib.request.HTTPRedirectHandler)
            # we want manual: use a no-redirect handler
            class NoRedirect(urllib.request.HTTPRedirectHandler):
                def redirect_request(self, req, fp, code, msg, headers, newurl):
                    return None
            opener = urllib.request.build_opener(NoRedirect)
            resp = opener.open(req, timeout=args.timeout)
            status = resp.status
            loc = resp.headers.get("Location")
            chain.append((status, url))
            print(f"  {hop:>2}. {status} {url}")
            if not loc:
                break
            url = urllib.parse.urljoin(url, loc)
        except urllib.error.HTTPError as e:
            status = e.code
            loc = e.headers.get("Location")
            chain.append((status, url))
            print(f"  {hop:>2}. {status} {url}")
            if not loc:
                break
            url = urllib.parse.urljoin(url, loc)
        except Exception as e:
            print(f"  ERROR at hop {hop}: {e}")
            break
    print(f"\nFinal: {url}  ({len(chain)} hops)")


# ---- cookies ----

def cmd_cookies(args):
    resp = _open(args.url, timeout=args.timeout)
    cookies = resp.headers.get_all("Set-Cookie") or []
    if not cookies:
        print("(no Set-Cookie headers)")
        return
    print(f"{'NAME':<24} {'VALUE':<30} {'FLAGS'}")
    print("-" * 100)
    for raw in cookies:
        sc = SimpleCookie()
        try:
            sc.load(raw)
        except Exception:
            print(f"  (parse error) {raw}")
            continue
        for name, morsel in sc.items():
            flags = []
            for attr in ("domain", "path", "expires", "max-age", "secure", "httponly", "samesite"):
                v = morsel.get(attr)
                if v:
                    flags.append(f"{attr}={v}" if v is not True else attr)
            val = morsel.value
            print(f"{name[:24]:<24} {val[:30]:<30} {'; '.join(flags)}")


COMMANDS = {
    "ssl-info":        "TLS certificate details for host[:port]",
    "header-analyze":  "fetch URL and audit security headers (score 0-100)",
    "jwt-verify":      "verify JWT signature with secret or PEM public key",
    "har-view":        "parse HAR file and show summary",
    "traceroute":      "OS traceroute / tracert wrapper",
    "speedtest":       "download throughput test (Cloudflare default)",
    "dns-lookup":      "A/AAAA/MX/TXT/NS/CNAME via dnspython",
    "cors-check":      "send OPTIONS preflight and report CORS headers",
    "redirects":       "follow redirect chain manually",
    "cookies":         "parse Set-Cookie headers from a URL",
}


def build_parser(parser=None):
    parser = parser or argparse.ArgumentParser(prog="netpro_tools", description="Advanced network utilities")
    sub = parser.add_subparsers(dest="cmd")

    p = sub.add_parser("ssl-info", help=COMMANDS["ssl-info"])
    p.add_argument("target", help="host or host:port")
    p.add_argument("--timeout", type=float, default=10)
    p.set_defaults(func=cmd_ssl_info)

    p = sub.add_parser("header-analyze", help=COMMANDS["header-analyze"])
    p.add_argument("url")
    p.add_argument("--timeout", type=int, default=15)
    p.set_defaults(func=cmd_header_analyze)

    p = sub.add_parser("jwt-verify", help=COMMANDS["jwt-verify"])
    p.add_argument("token")
    p.add_argument("--secret")
    p.add_argument("--key-file")
    p.add_argument("--algo")
    p.set_defaults(func=cmd_jwt_verify)

    p = sub.add_parser("har-view", help=COMMANDS["har-view"])
    p.add_argument("input")
    p.set_defaults(func=cmd_har_view)

    p = sub.add_parser("traceroute", help=COMMANDS["traceroute"])
    p.add_argument("host")
    p.add_argument("--max-hops", type=int, default=30)
    p.add_argument("--no-resolve", action="store_true")
    p.set_defaults(func=cmd_traceroute)

    p = sub.add_parser("speedtest", help=COMMANDS["speedtest"])
    p.add_argument("--url", default="https://speed.cloudflare.com/__down?bytes=10000000")
    p.add_argument("--timeout", type=int, default=60)
    p.set_defaults(func=cmd_speedtest)

    p = sub.add_parser("dns-lookup", help=COMMANDS["dns-lookup"])
    p.add_argument("host")
    p.add_argument("--types", help="comma-separated record types")
    p.add_argument("--server", help="DNS server to use")
    p.set_defaults(func=cmd_dns_lookup)

    p = sub.add_parser("cors-check", help=COMMANDS["cors-check"])
    p.add_argument("url")
    p.add_argument("--origin", default="https://example.com")
    p.add_argument("--method", default="GET")
    p.add_argument("--timeout", type=int, default=10)
    p.set_defaults(func=cmd_cors_check)

    p = sub.add_parser("redirects", help=COMMANDS["redirects"])
    p.add_argument("url")
    p.add_argument("--max-hops", type=int, default=10)
    p.add_argument("--timeout", type=int, default=10)
    p.set_defaults(func=cmd_redirects)

    p = sub.add_parser("cookies", help=COMMANDS["cookies"])
    p.add_argument("url")
    p.add_argument("--timeout", type=int, default=10)
    p.set_defaults(func=cmd_cookies)

    return parser


@tool_main("net-pro")
def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 1
    return args.func(args) or 0


if __name__ == "__main__":
    raise SystemExit(main())
