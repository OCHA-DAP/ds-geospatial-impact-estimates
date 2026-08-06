#!/usr/bin/env python3
"""Encrypt a rendered HTML document for publication behind a passphrase gate.

The repository and the Pages site are both public, so a JavaScript password prompt in front of
plaintext HTML protects nothing — the content ships to the browser before the prompt appears,
and it is readable straight off github.com. What is committed here is ciphertext instead:
useless without the passphrase, which is never stored in the repo.

Run this locally after re-rendering an artefact. It never runs in CI; the deploy workflow only
uploads files. That is why depending on ``cryptography`` is free — AES-GCM is not in the
standard library, but PBKDF2 (``hashlib``) and gzip are.

    uv run --with cryptography python scripts/encrypt_page.py \\
      --in  exploratory/paper/satellite_damage_evaluation_v2.html \\
      --out pages/slides/damage-evaluation/content.enc

The passphrase comes from ``$GIE_PAGE_PASS`` if set, otherwise an interactive prompt (entered
twice, because a mistyped passphrase produces a file nobody can ever open). There is no default
and no fallback: if neither is available, this fails.

Output layout — see pages/assets/decrypt.js, which reads it:

    offset  bytes  field
    0       8      magic b"GIEENC01"
    8       16     PBKDF2 salt
    24      12     AES-GCM nonce
    36      4      PBKDF2 iteration count, uint32 big-endian
    40      ...    AES-GCM ciphertext with its 16-byte tag appended

The iteration count travels in the header rather than being hardcoded in both this script and
the JavaScript, so it can be raised later without invalidating already-published files.
"""

from __future__ import annotations

import argparse
import getpass
import gzip
import hashlib
import os
import sys
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

MAGIC = b"GIEENC01"
SALT_BYTES = 16
NONCE_BYTES = 12
KEY_BYTES = 32
HEADER_BYTES = len(MAGIC) + SALT_BYTES + NONCE_BYTES + 4

# OWASP's 2023 floor for PBKDF2-SHA256. Costs the reader well under a second in-browser.
DEFAULT_ITERATIONS = 600_000
MIN_ITERATIONS = 100_000


class EncryptError(Exception):
    """Something the caller must fix. The message says which of the three it is."""


def derive_key(passphrase: str, salt: bytes, iterations: int) -> bytes:
    """PBKDF2-SHA256, matching WebCrypto's deriveBits with the same parameters."""
    return hashlib.pbkdf2_hmac("sha256", passphrase.encode("utf-8"), salt, iterations, KEY_BYTES)


def read_passphrase() -> str:
    """From the environment, or prompted twice. Never defaulted."""
    from_env = os.environ.get("GIE_PAGE_PASS")
    if from_env is not None:
        if not from_env:
            raise EncryptError("GIE_PAGE_PASS is set but empty; unset it to be prompted instead")
        return from_env

    if not sys.stdin.isatty():
        raise EncryptError(
            "no passphrase: set GIE_PAGE_PASS, or run interactively to be prompted"
        )

    first = getpass.getpass("Passphrase: ")
    if not first:
        raise EncryptError("empty passphrase")
    # A typo here yields a file that nobody — including you — can ever open, and the damage
    # is only discovered by a reader much later. Confirm it now.
    if first != getpass.getpass("Confirm passphrase: "):
        raise EncryptError("passphrases do not match")
    return first


def encrypt(plaintext: bytes, passphrase: str, iterations: int) -> bytes:
    """gzip, then AES-GCM. Returns the complete file contents."""
    compressed = gzip.compress(plaintext, 9)
    salt = os.urandom(SALT_BYTES)
    nonce = os.urandom(NONCE_BYTES)
    key = derive_key(passphrase, salt, iterations)
    sealed = AESGCM(key).encrypt(nonce, compressed, None)
    return MAGIC + salt + nonce + iterations.to_bytes(4, "big") + sealed


def decrypt(blob: bytes, passphrase: str) -> bytes:
    """Inverse of :func:`encrypt`, used to self-check what we are about to commit."""
    if blob[: len(MAGIC)] != MAGIC:
        raise EncryptError(f"not a {MAGIC.decode()} file")
    salt = blob[8:24]
    nonce = blob[24:36]
    iterations = int.from_bytes(blob[36:40], "big")
    key = derive_key(passphrase, salt, iterations)
    return gzip.decompress(AESGCM(key).decrypt(nonce, blob[HEADER_BYTES:], None))


def reject_legacy_gate(plaintext: bytes, src: Path) -> None:
    """Refuse to publish a document that still carries the superseded client-side gate.

    ``exploratory/paper/password.html`` was a cosmetic gate: a synchronous ``window.prompt``
    hardcoded to one password, which wipes the body and shows "Access denied" on a mismatch.
    Encrypting a document that contains it produces a page nobody can read — this gate decrypts
    correctly, and then the document's own gate denies the reader, who has no way to know why.
    It also blocks headless browsers, because an undismissed dialog stalls the renderer.

    Detected on the old gate's sessionStorage key, which is specific to it.
    """
    if b"gie-auth" not in plaintext:
        return
    raise EncryptError(
        f"{src} still contains the superseded client-side password gate (password.html).\n"
        "  Encrypted, it would decrypt fine and then deny every reader with 'Access denied'.\n"
        "  Fix: remove `include-in-header: password.html` from the .qmd and re-render.\n"
        "  This gate replaces it; two gates on one document is never what you want."
    )


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Encrypt a rendered HTML page for the passphrase-gated Pages site."
    )
    ap.add_argument("--in", dest="src", required=True, type=Path, help="rendered .html to encrypt")
    ap.add_argument("--out", dest="dst", required=True, type=Path, help="ciphertext to write")
    ap.add_argument(
        "--iterations", type=int, default=DEFAULT_ITERATIONS,
        help=f"PBKDF2 iterations (default {DEFAULT_ITERATIONS:,})",
    )
    args = ap.parse_args()

    try:
        if not args.src.is_file():
            raise EncryptError(f"input not found: {args.src}")
        # Not created for you: a mistyped --out would otherwise quietly produce an orphan
        # directory that never gets published and is never noticed.
        if not args.dst.parent.is_dir():
            raise EncryptError(f"output directory does not exist: {args.dst.parent}")
        if args.iterations < MIN_ITERATIONS:
            raise EncryptError(f"--iterations below the {MIN_ITERATIONS:,} floor")

        passphrase = read_passphrase()
        plaintext = args.src.read_bytes()
        reject_legacy_gate(plaintext, args.src)
        blob = encrypt(plaintext, passphrase, args.iterations)

        # Round-trip before writing. Catches a format or parameter bug here, rather than
        # leaving a reader staring at an unopenable page.
        if decrypt(blob, passphrase) != plaintext:
            raise EncryptError("self-check failed: round-trip did not reproduce the input")

        args.dst.write_bytes(blob)
    except EncryptError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(
        f"{args.src} -> {args.dst}\n"
        f"  {len(plaintext) / 1e6:.2f} MB plaintext -> {len(blob) / 1e6:.2f} MB ciphertext"
        f"  ({args.iterations:,} PBKDF2 iterations, round-trip verified)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
