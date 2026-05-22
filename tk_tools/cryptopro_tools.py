"""Advanced crypto: age, ssh-keys, BIP39, GPG, ECDSA/RSA sign, x509, KDFs, TOTP."""
from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import os
import secrets
import shutil
import struct
import subprocess
import time
import urllib.parse
from pathlib import Path

from _common import lazy_import, tool_main

# ---- age ----

def _check_exe(name, hint):
    path = shutil.which(name)
    if not path:
        print(f"[!] '{name}' not found in PATH. Install: {hint}")
        raise SystemExit(2)
    return path


def cmd_age_encrypt(args):
    exe = _check_exe("age", "https://github.com/FiloSottile/age")
    cmd = [exe]
    if args.recipient:
        for r in args.recipient:
            cmd += ["-r", r]
    elif args.recipients_file:
        cmd += ["-R", args.recipients_file]
    else:
        cmd += ["-p"]
    cmd += ["-o", args.output, args.input]
    return subprocess.call(cmd)


def cmd_age_decrypt(args):
    exe = _check_exe("age", "https://github.com/FiloSottile/age")
    cmd = [exe, "-d"]
    if args.identity:
        cmd += ["-i", args.identity]
    cmd += ["-o", args.output, args.input]
    return subprocess.call(cmd)


# ---- ssh-keygen ----

def cmd_ssh_keygen(args):
    lazy_import("cryptography", "pip install cryptography")
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ed25519, rsa
    if args.algo == "ed25519":
        priv = ed25519.Ed25519PrivateKey.generate()
    else:
        priv = rsa.generate_private_key(public_exponent=65537, key_size=args.bits)
    pub = priv.public_key()
    pem = priv.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.OpenSSH,
        encryption_algorithm=(serialization.BestAvailableEncryption(args.passphrase.encode())
                              if args.passphrase else serialization.NoEncryption()),
    )
    pub_ssh = pub.public_bytes(
        encoding=serialization.Encoding.OpenSSH,
        format=serialization.PublicFormat.OpenSSH,
    )
    out = Path(args.output)
    out.write_bytes(pem)
    try:
        os.chmod(out, 0o600)
    except OSError:
        pass
    Path(str(out) + ".pub").write_bytes(pub_ssh + b" " + (args.comment or "tk").encode() + b"\n")
    print(f"Wrote {out} and {out}.pub")


def cmd_ssh_fingerprint(args):
    data = Path(args.input).read_text(encoding="utf-8").strip().split()
    if len(data) < 2:
        print("Not a valid public key file"); return 1
    keytype, key_b64 = data[0], data[1]
    raw = base64.b64decode(key_b64)
    digest = hashlib.sha256(raw).digest()
    fp = "SHA256:" + base64.b64encode(digest).rstrip(b"=").decode()
    md5 = hashlib.md5(raw).hexdigest()
    md5_fp = ":".join(md5[i:i+2] for i in range(0, len(md5), 2))
    print(f"Type:    {keytype}")
    print(f"SHA256:  {fp}")
    print(f"MD5:     MD5:{md5_fp}")


# ---- BIP39 ----

_BIP39_FALLBACK = None


def _bip39_words():
    global _BIP39_FALLBACK
    try:
        m = lazy_import("mnemonic", "pip install mnemonic")
        return m.Mnemonic("english").wordlist
    except SystemExit:
        raise


def cmd_bip39_gen(args):
    if args.words not in (12, 15, 18, 21, 24):
        print("--words must be 12/15/18/21/24"); return 1
    strength_bits = {12: 128, 15: 160, 18: 192, 21: 224, 24: 256}[args.words]
    entropy = secrets.token_bytes(strength_bits // 8)
    wordlist = _bip39_words()
    # checksum
    cs_len = strength_bits // 32
    h = hashlib.sha256(entropy).digest()
    bits = "".join(f"{b:08b}" for b in entropy)
    bits += "".join(f"{b:08b}" for b in h)[:cs_len]
    words = []
    for i in range(0, len(bits), 11):
        idx = int(bits[i:i+11], 2)
        words.append(wordlist[idx])
    print(" ".join(words))


def cmd_bip39_verify(args):
    wordlist = _bip39_words()
    words = args.phrase.strip().split()
    if len(words) not in (12, 15, 18, 21, 24):
        print(f"Invalid word count: {len(words)}"); return 1
    try:
        indices = [wordlist.index(w) for w in words]
    except ValueError as e:
        print(f"Unknown word: {e}"); return 1
    bits = "".join(f"{i:011b}" for i in indices)
    ent_bits = len(bits) * 32 // 33
    ent = bits[:ent_bits]; cs = bits[ent_bits:]
    ent_bytes = int(ent, 2).to_bytes(ent_bits // 8, "big")
    expected = "".join(f"{b:08b}" for b in hashlib.sha256(ent_bytes).digest())[:len(cs)]
    if cs == expected:
        print("VALID checksum")
        return 0
    print("INVALID checksum")
    return 1


# ---- GPG ----

def cmd_gpg_encrypt(args):
    exe = _check_exe("gpg", "https://gnupg.org")
    cmd = [exe, "--output", args.output]
    if args.recipient:
        cmd += ["--encrypt"]
        for r in args.recipient:
            cmd += ["--recipient", r]
    else:
        cmd += ["--symmetric"]
    if args.armor:
        cmd += ["--armor"]
    cmd += [args.input]
    return subprocess.call(cmd)


def cmd_gpg_decrypt(args):
    exe = _check_exe("gpg", "https://gnupg.org")
    return subprocess.call([exe, "--output", args.output, "--decrypt", args.input])


# ---- ECDSA P-256 ----

def cmd_ecdsa_sign(args):
    lazy_import("cryptography", "pip install cryptography")
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    key = serialization.load_pem_private_key(Path(args.key).read_bytes(), password=None)
    data = Path(args.input).read_bytes()
    sig = key.sign(data, ec.ECDSA(hashes.SHA256()))
    Path(args.output).write_bytes(sig)
    print(f"Wrote signature -> {args.output} ({len(sig)} bytes)")


def cmd_ecdsa_verify(args):
    lazy_import("cryptography", "pip install cryptography")
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    pub = serialization.load_pem_public_key(Path(args.key).read_bytes())
    data = Path(args.input).read_bytes()
    sig = Path(args.signature).read_bytes()
    try:
        pub.verify(sig, data, ec.ECDSA(hashes.SHA256()))
        print("VALID"); return 0
    except InvalidSignature:
        print("INVALID"); return 1


# ---- RSA PKCS#1 v1.5 ----

def cmd_rsa_sign(args):
    lazy_import("cryptography", "pip install cryptography")
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    key = serialization.load_pem_private_key(Path(args.key).read_bytes(), password=None)
    data = Path(args.input).read_bytes()
    sig = key.sign(data, padding.PKCS1v15(), hashes.SHA256())
    Path(args.output).write_bytes(sig)
    print(f"Wrote signature -> {args.output} ({len(sig)} bytes)")


def cmd_rsa_verify(args):
    lazy_import("cryptography", "pip install cryptography")
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    pub = serialization.load_pem_public_key(Path(args.key).read_bytes())
    data = Path(args.input).read_bytes()
    sig = Path(args.signature).read_bytes()
    try:
        pub.verify(sig, data, padding.PKCS1v15(), hashes.SHA256())
        print("VALID"); return 0
    except InvalidSignature:
        print("INVALID"); return 1


# ---- x509-info ----

def cmd_x509_info(args):
    lazy_import("cryptography", "pip install cryptography")
    from cryptography import x509
    from cryptography.hazmat.primitives.asymmetric import ec, rsa
    data = Path(args.input).read_bytes()
    cert = x509.load_pem_x509_certificate(data) if b"BEGIN CERT" in data else x509.load_der_x509_certificate(data)
    print(f"Subject:    {cert.subject.rfc4514_string()}")
    print(f"Issuer:     {cert.issuer.rfc4514_string()}")
    print(f"Serial:     {cert.serial_number:x}")
    print(f"Version:    {cert.version.name}")
    print(f"Not Before: {cert.not_valid_before_utc}")
    print(f"Not After:  {cert.not_valid_after_utc}")
    sig_alg = cert.signature_hash_algorithm.name if cert.signature_hash_algorithm else "?"
    print(f"Sig Alg:    {sig_alg}")
    pub = cert.public_key()
    if isinstance(pub, rsa.RSAPublicKey):
        print(f"Key:        RSA {pub.key_size} bits")
    elif isinstance(pub, ec.EllipticCurvePublicKey):
        print(f"Key:        EC {pub.curve.name}")
    else:
        print(f"Key:        {type(pub).__name__}")
    for ext in cert.extensions:
        print(f"Ext:        {ext.oid._name}  critical={ext.critical}")


# ---- KDFs ----

def cmd_pbkdf2(args):
    salt = (args.salt.encode() if args.salt else secrets.token_bytes(16))
    dk = hashlib.pbkdf2_hmac(args.algo, args.password.encode(), salt, args.iterations, dklen=args.length)
    print(f"salt (hex):       {salt.hex()}")
    print(f"iterations:       {args.iterations}")
    print(f"algo:             {args.algo}")
    print(f"derived (hex):    {dk.hex()}")
    print(f"derived (b64):    {base64.b64encode(dk).decode()}")


def cmd_argon2(args):
    lazy_import("argon2", "pip install argon2-cffi")
    from argon2 import PasswordHasher
    ph = PasswordHasher(time_cost=args.time_cost, memory_cost=args.memory_cost, parallelism=args.parallelism)
    print(ph.hash(args.password))


# ---- TOTP ----

def cmd_totp(args):
    secret = args.secret.replace(" ", "").upper()
    secret += "=" * (-len(secret) % 8)
    key = base64.b32decode(secret, casefold=True)
    counter = int(time.time() // args.period)
    h = hmac.new(key, struct.pack(">Q", counter), getattr(hashlib, args.algo)).digest()
    o = h[-1] & 0x0F
    code = (struct.unpack(">I", h[o:o+4])[0] & 0x7FFFFFFF) % (10 ** args.digits)
    remaining = args.period - int(time.time() % args.period)
    print(f"{code:0{args.digits}d}   ({remaining}s left)")


def cmd_totp_uri(args):
    params = {
        "secret": args.secret.replace(" ", "").upper(),
        "issuer": args.issuer,
        "digits": str(args.digits),
        "period": str(args.period),
        "algorithm": args.algo.upper(),
    }
    label = urllib.parse.quote(f"{args.issuer}:{args.account}")
    print(f"otpauth://totp/{label}?{urllib.parse.urlencode(params)}")


COMMANDS = {
    "age-encrypt":     "encrypt file with `age` (passphrase or recipient)",
    "age-decrypt":     "decrypt `age` file",
    "ssh-keygen":      "generate ed25519 or RSA SSH keypair",
    "ssh-fingerprint": "SHA256/MD5 fingerprint of OpenSSH public key",
    "bip39-gen":       "generate BIP39 mnemonic (12/15/18/21/24 words)",
    "bip39-verify":    "verify BIP39 phrase checksum",
    "gpg-encrypt":     "GPG encrypt (symmetric or recipient)",
    "gpg-decrypt":     "GPG decrypt",
    "ecdsa-sign":      "ECDSA P-256 sign (PEM private key)",
    "ecdsa-verify":    "ECDSA P-256 verify",
    "rsa-sign":        "RSA PKCS#1 v1.5 sign",
    "rsa-verify":      "RSA PKCS#1 v1.5 verify",
    "x509-info":       "dump X.509 certificate details",
    "pbkdf2":          "PBKDF2 key derivation",
    "argon2":          "Argon2 password hashing",
    "totp":            "current TOTP code from base32 secret",
    "totp-uri":        "build otpauth:// URI",
}


def build_parser(parser=None):
    parser = parser or argparse.ArgumentParser(prog="cryptopro_tools", description="Advanced crypto utilities")
    sub = parser.add_subparsers(dest="cmd")

    p = sub.add_parser("age-encrypt", help=COMMANDS["age-encrypt"])
    p.add_argument("input"); p.add_argument("output")
    p.add_argument("-r", "--recipient", action="append")
    p.add_argument("-R", "--recipients-file")
    p.set_defaults(func=cmd_age_encrypt)

    p = sub.add_parser("age-decrypt", help=COMMANDS["age-decrypt"])
    p.add_argument("input"); p.add_argument("output")
    p.add_argument("-i", "--identity")
    p.set_defaults(func=cmd_age_decrypt)

    p = sub.add_parser("ssh-keygen", help=COMMANDS["ssh-keygen"])
    p.add_argument("output")
    p.add_argument("--algo", choices=["ed25519", "rsa"], default="ed25519")
    p.add_argument("--bits", type=int, default=3072)
    p.add_argument("--passphrase", default="")
    p.add_argument("--comment", default="tk")
    p.set_defaults(func=cmd_ssh_keygen)

    p = sub.add_parser("ssh-fingerprint", help=COMMANDS["ssh-fingerprint"])
    p.add_argument("input")
    p.set_defaults(func=cmd_ssh_fingerprint)

    p = sub.add_parser("bip39-gen", help=COMMANDS["bip39-gen"])
    p.add_argument("--words", type=int, default=12)
    p.set_defaults(func=cmd_bip39_gen)

    p = sub.add_parser("bip39-verify", help=COMMANDS["bip39-verify"])
    p.add_argument("phrase")
    p.set_defaults(func=cmd_bip39_verify)

    p = sub.add_parser("gpg-encrypt", help=COMMANDS["gpg-encrypt"])
    p.add_argument("input"); p.add_argument("output")
    p.add_argument("-r", "--recipient", action="append")
    p.add_argument("--armor", action="store_true")
    p.set_defaults(func=cmd_gpg_encrypt)

    p = sub.add_parser("gpg-decrypt", help=COMMANDS["gpg-decrypt"])
    p.add_argument("input"); p.add_argument("output")
    p.set_defaults(func=cmd_gpg_decrypt)

    p = sub.add_parser("ecdsa-sign", help=COMMANDS["ecdsa-sign"])
    p.add_argument("input"); p.add_argument("output"); p.add_argument("--key", required=True)
    p.set_defaults(func=cmd_ecdsa_sign)

    p = sub.add_parser("ecdsa-verify", help=COMMANDS["ecdsa-verify"])
    p.add_argument("input"); p.add_argument("signature"); p.add_argument("--key", required=True)
    p.set_defaults(func=cmd_ecdsa_verify)

    p = sub.add_parser("rsa-sign", help=COMMANDS["rsa-sign"])
    p.add_argument("input"); p.add_argument("output"); p.add_argument("--key", required=True)
    p.set_defaults(func=cmd_rsa_sign)

    p = sub.add_parser("rsa-verify", help=COMMANDS["rsa-verify"])
    p.add_argument("input"); p.add_argument("signature"); p.add_argument("--key", required=True)
    p.set_defaults(func=cmd_rsa_verify)

    p = sub.add_parser("x509-info", help=COMMANDS["x509-info"])
    p.add_argument("input")
    p.set_defaults(func=cmd_x509_info)

    p = sub.add_parser("pbkdf2", help=COMMANDS["pbkdf2"])
    p.add_argument("password")
    p.add_argument("--salt")
    p.add_argument("--iterations", type=int, default=200_000)
    p.add_argument("--length", type=int, default=32)
    p.add_argument("--algo", default="sha256")
    p.set_defaults(func=cmd_pbkdf2)

    p = sub.add_parser("argon2", help=COMMANDS["argon2"])
    p.add_argument("password")
    p.add_argument("--time-cost", type=int, default=3)
    p.add_argument("--memory-cost", type=int, default=65536)
    p.add_argument("--parallelism", type=int, default=4)
    p.set_defaults(func=cmd_argon2)

    p = sub.add_parser("totp", help=COMMANDS["totp"])
    p.add_argument("secret")
    p.add_argument("--digits", type=int, default=6)
    p.add_argument("--period", type=int, default=30)
    p.add_argument("--algo", choices=["sha1", "sha256", "sha512"], default="sha1")
    p.set_defaults(func=cmd_totp)

    p = sub.add_parser("totp-uri", help=COMMANDS["totp-uri"])
    p.add_argument("secret")
    p.add_argument("--account", default="user")
    p.add_argument("--issuer", default="tk")
    p.add_argument("--digits", type=int, default=6)
    p.add_argument("--period", type=int, default=30)
    p.add_argument("--algo", choices=["sha1", "sha256", "sha512"], default="sha1")
    p.set_defaults(func=cmd_totp_uri)

    return parser


@tool_main("crypto-pro")
def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 1
    return args.func(args) or 0


if __name__ == "__main__":
    raise SystemExit(main())
