"""Crypto tools: password gen, UUID, file hash, JWT decode, Fernet encrypt/decrypt, random."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import secrets
import string
import sys
import uuid as uuid_mod
from pathlib import Path

from _common import lazy_import


# ---- Password ----

def cmd_password(args):
    chars = ""
    if not args.no_lower:
        chars += string.ascii_lowercase
    if not args.no_upper:
        chars += string.ascii_uppercase
    if not args.no_digits:
        chars += string.digits
    if args.symbols:
        chars += "!@#$%^&*()-_=+[]{}<>?"
    if not chars:
        print("No character classes selected.")
        return 1
    for _ in range(args.count):
        print("".join(secrets.choice(chars) for _ in range(args.length)))


def cmd_passphrase(args):
    """Word-list-style passphrase from a small built-in word list."""
    words = [
        "alpha", "bravo", "charlie", "delta", "echo", "foxtrot", "golf",
        "hotel", "india", "juliet", "kilo", "lima", "mike", "november",
        "oscar", "papa", "quebec", "romeo", "sierra", "tango", "uniform",
        "victor", "whiskey", "xray", "yankee", "zulu", "river", "mountain",
        "forest", "ocean", "valley", "desert", "canyon", "meadow", "harbor",
        "thunder", "shadow", "ember", "frost", "marble", "silver", "copper",
        "amber", "azure", "crimson", "ivory", "jade", "saffron", "violet",
    ]
    out = args.separator.join(secrets.choice(words) for _ in range(args.count))
    if args.suffix_digits:
        out += "".join(secrets.choice(string.digits) for _ in range(args.suffix_digits))
    print(out)


# ---- UUID ----

def cmd_uuid(args):
    if args.version == 1:
        gen = uuid_mod.uuid1
    elif args.version == 4:
        gen = uuid_mod.uuid4
    else:
        print(f"Unsupported version {args.version}")
        return 1
    for _ in range(args.count):
        print(gen())


# ---- Hash ----

def cmd_hash_file(args):
    h = hashlib.new(args.algo)
    with open(args.input, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    print(f"{h.hexdigest()}  {args.input}")


def cmd_verify(args):
    h = hashlib.new(args.algo)
    with open(args.input, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    actual = h.hexdigest()
    expected = args.expected.lower().strip()
    if actual == expected:
        print(f"OK  {args.algo}  {args.input}")
        return 0
    print(f"MISMATCH  expected={expected}  actual={actual}")
    return 1


# ---- JWT ----

def cmd_jwt_decode(args):
    parts = args.token.split(".")
    if len(parts) != 3:
        print("Not a JWT (expected 3 segments).")
        return 1

    def b64url(s: str) -> bytes:
        s += "=" * (-len(s) % 4)
        return base64.urlsafe_b64decode(s)

    try:
        header = json.loads(b64url(parts[0]))
        payload = json.loads(b64url(parts[1]))
    except Exception as e:
        print(f"Decode failed: {e}")
        return 1
    print("Header:")
    print(json.dumps(header, indent=2))
    print("\nPayload:")
    print(json.dumps(payload, indent=2))
    print(f"\nSignature (b64url): {parts[2]}")


# ---- Fernet symmetric encrypt ----

def _fernet_class():
    lazy_import("cryptography", install_hint="pip install cryptography")
    from cryptography.fernet import Fernet
    return Fernet


def cmd_keygen(args):
    Fernet = _fernet_class()
    key = Fernet.generate_key()
    if args.output:
        Path(args.output).write_bytes(key)
        print(f"Wrote key to {args.output}")
    else:
        print(key.decode())


def _resolve_key(args) -> bytes | None:
    if args.key_file:
        return Path(args.key_file).read_bytes().strip()
    if args.key:
        return args.key.encode()
    return None


def cmd_encrypt(args):
    Fernet = _fernet_class()
    key = _resolve_key(args)
    if key is None:
        print("Provide --key or --key-file (use 'keygen' to make one).")
        return 1
    f = Fernet(key)
    Path(args.output).write_bytes(f.encrypt(Path(args.input).read_bytes()))
    print(f"Encrypted -> {args.output}")


def cmd_decrypt(args):
    Fernet = _fernet_class()
    key = _resolve_key(args)
    if key is None:
        print("Provide --key or --key-file.")
        return 1
    f = Fernet(key)
    Path(args.output).write_bytes(f.decrypt(Path(args.input).read_bytes()))
    print(f"Decrypted -> {args.output}")


# ---- Random bytes ----

def cmd_totp(args):
    """Generate a 6-digit TOTP code (RFC 6238) from a base32 secret."""
    import hmac, struct, time
    secret = args.secret.replace(" ", "").upper()
    secret += "=" * (-len(secret) % 8)
    try:
        key = base64.b32decode(secret, casefold=True)
    except Exception as e:
        print(f"Bad base32 secret: {e}"); return 1
    counter = int(time.time() // args.period)
    msg = struct.pack(">Q", counter)
    h = hmac.new(key, msg, getattr(hashlib, args.algo)).digest()
    o = h[-1] & 0x0F
    code = (struct.unpack(">I", h[o:o + 4])[0] & 0x7FFFFFFF) % (10 ** args.digits)
    remaining = args.period - int(time.time() % args.period)
    print(f"{code:0{args.digits}d}   ({remaining}s left)")


def cmd_caesar(args):
    """Caesar cipher (rotate alphabetic chars by N)."""
    n = args.shift % 26
    out = []
    for ch in args.text:
        if "a" <= ch <= "z":
            out.append(chr((ord(ch) - 97 + n) % 26 + 97))
        elif "A" <= ch <= "Z":
            out.append(chr((ord(ch) - 65 + n) % 26 + 65))
        else:
            out.append(ch)
    print("".join(out))


def cmd_rot13_str(args):
    import codecs
    print(codecs.encode(args.text, "rot_13"))


def cmd_otpauth(args):
    """Build an otpauth:// URL (great with `tk qr gen` to make a TOTP QR)."""
    import urllib.parse
    params = {"secret": args.secret.replace(" ", "").upper(),
              "issuer": args.issuer,
              "digits": str(args.digits),
              "period": str(args.period),
              "algorithm": args.algo.upper()}
    label = urllib.parse.quote(f"{args.issuer}:{args.account}")
    qs = urllib.parse.urlencode(params)
    print(f"otpauth://totp/{label}?{qs}")


def cmd_random(args):
    if args.format == "hex":
        print(secrets.token_hex(args.bytes))
    elif args.format == "b64":
        print(secrets.token_urlsafe(args.bytes))
    elif args.format == "raw":
        sys.stdout.buffer.write(secrets.token_bytes(args.bytes))


COMMANDS = {
    "password":   "generate strong random passwords",
    "passphrase": "generate word-list passphrase",
    "uuid":       "generate UUIDs (v1 or v4)",
    "hash":       "hash a file (md5/sha*/blake2*)",
    "verify":     "verify a file against an expected hash",
    "jwt":        "decode a JWT (no signature verification)",
    "keygen":     "generate a Fernet symmetric key",
    "encrypt":    "encrypt a file with Fernet",
    "decrypt":    "decrypt a file with Fernet",
    "random":     "cryptographic random bytes (hex/b64/raw)",
    "totp":       "compute current TOTP 6-digit code from base32 secret",
    "caesar":     "Caesar cipher shift",
    "rot13":      "ROT13 transform of a string",
    "otpauth":    "build otpauth:// URL (pair with `qr gen` to make a TOTP QR)",
}


def build_parser(parser=None):
    parser = parser or argparse.ArgumentParser(prog="crypto_tools", description="Crypto utilities")
    sub = parser.add_subparsers(dest="cmd")

    p = sub.add_parser("password", help=COMMANDS["password"])
    p.add_argument("--length", type=int, default=16)
    p.add_argument("--count", type=int, default=1)
    p.add_argument("--no-lower", action="store_true")
    p.add_argument("--no-upper", action="store_true")
    p.add_argument("--no-digits", action="store_true")
    p.add_argument("--symbols", action="store_true")
    p.set_defaults(func=cmd_password)

    p = sub.add_parser("passphrase", help=COMMANDS["passphrase"])
    p.add_argument("--count", type=int, default=4)
    p.add_argument("--separator", default="-")
    p.add_argument("--suffix-digits", type=int, default=0)
    p.set_defaults(func=cmd_passphrase)

    p = sub.add_parser("uuid", help=COMMANDS["uuid"])
    p.add_argument("--version", type=int, default=4, choices=[1, 4])
    p.add_argument("--count", type=int, default=1)
    p.set_defaults(func=cmd_uuid)

    p = sub.add_parser("hash", help=COMMANDS["hash"])
    p.add_argument("input")
    p.add_argument("--algo", default="sha256",
                   choices=["md5", "sha1", "sha224", "sha256", "sha384", "sha512", "blake2b", "blake2s"])
    p.set_defaults(func=cmd_hash_file)

    p = sub.add_parser("verify", help=COMMANDS["verify"])
    p.add_argument("input")
    p.add_argument("expected")
    p.add_argument("--algo", default="sha256")
    p.set_defaults(func=cmd_verify)

    p = sub.add_parser("jwt", help=COMMANDS["jwt"])
    p.add_argument("token")
    p.set_defaults(func=cmd_jwt_decode)

    p = sub.add_parser("keygen", help=COMMANDS["keygen"])
    p.add_argument("-o", "--output")
    p.set_defaults(func=cmd_keygen)

    p = sub.add_parser("encrypt", help=COMMANDS["encrypt"])
    p.add_argument("input"); p.add_argument("output")
    p.add_argument("--key"); p.add_argument("--key-file")
    p.set_defaults(func=cmd_encrypt)

    p = sub.add_parser("decrypt", help=COMMANDS["decrypt"])
    p.add_argument("input"); p.add_argument("output")
    p.add_argument("--key"); p.add_argument("--key-file")
    p.set_defaults(func=cmd_decrypt)

    p = sub.add_parser("random", help=COMMANDS["random"])
    p.add_argument("--bytes", type=int, default=16)
    p.add_argument("--format", choices=["hex", "b64", "raw"], default="hex")
    p.set_defaults(func=cmd_random)

    p = sub.add_parser("totp", help=COMMANDS["totp"])
    p.add_argument("secret", help="base32 secret")
    p.add_argument("--digits", type=int, default=6)
    p.add_argument("--period", type=int, default=30)
    p.add_argument("--algo", choices=["sha1", "sha256", "sha512"], default="sha1")
    p.set_defaults(func=cmd_totp)

    p = sub.add_parser("caesar", help=COMMANDS["caesar"])
    p.add_argument("text")
    p.add_argument("--shift", type=int, default=3)
    p.set_defaults(func=cmd_caesar)

    p = sub.add_parser("rot13", help=COMMANDS["rot13"])
    p.add_argument("text")
    p.set_defaults(func=cmd_rot13_str)

    p = sub.add_parser("otpauth", help=COMMANDS["otpauth"])
    p.add_argument("secret")
    p.add_argument("--account", default="user")
    p.add_argument("--issuer", default="tk")
    p.add_argument("--digits", type=int, default=6)
    p.add_argument("--period", type=int, default=30)
    p.add_argument("--algo", choices=["sha1", "sha256", "sha512"], default="sha1")
    p.set_defaults(func=cmd_otpauth)

    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 1
    return args.func(args) or 0


if __name__ == "__main__":
    raise SystemExit(main())
