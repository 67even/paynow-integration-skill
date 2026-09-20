#!/usr/bin/env python3
"""Paynow SHA-512 hash helper.

Generate, verify and debug Paynow message hashes from the command line, and prove a
hashing implementation in any language against Paynow's two published fixtures.

    python3 paynow_hash.py selftest
    python3 paynow_hash.py verify   --key <integration-key> --body 'status=Ok&pollurl=...&hash=...'
    python3 paynow_hash.py generate --key <integration-key> --body 'id=1201&reference=INV-1&status=Message'
    python3 paynow_hash.py notification --key <key> --body 'Paynow_Reference=40222&Amount_Paid=26.30&Hash=...'

The API algorithm joins VALUES in arrival order (excluding `hash`), appends the
integration key, and takes an uppercase SHA-512.  Link/button Notification URLs use a
different algorithm that joins KEY+VALUE; that is what `notification` implements.
"""

import argparse
import hashlib
import hmac
import sys
from urllib.parse import unquote_plus

# --- Paynow's two published fixtures -------------------------------------------------

FIXTURE_KEY = "3e9fed89-60e1-4ce5-ab6e-6b1eb2d4f977"

OUTBOUND_BODY = (
    "id=1201&reference=TEST REF&amount=99.99"
    "&additionalinfo=A test ticket transaction"
    "&returnurl=http://www.google.com/search?q=returnurl"
    "&resulturl=http://www.google.com/search?q=resulturl"
    "&status=Message"
)
OUTBOUND_HASH = (
    "2A033FC38798D913D42ECB786B9B19645ADEDBDE788862032F1BD82CF3B92DEF"
    "84F316385D5B40DBB35F1A4FD7D5BFE73835174136463CDD48C9366B0749C689"
)

INBOUND_BODY = (
    "status=Ok"
    "&browserurl=https%3a%2f%2fstaging.paynow.co.zw%2fPayment%2fConfirmPayment%2f9510"
    "&pollurl=https%3a%2f%2fstaging.paynow.co.zw%2fInterface%2fCheckPayment%2f"
    "%3fguid%3dc7ed41da-0159-46da-b428-69549f770413"
    "&paynowreference=9510"
    "&hash=750DD0B0DF374678707BB5AF915AF81C228B9058AD57BB7120569EC68BBB9C2E"
    "FC1B26C6375D2BC562AC909B3CD6B2AF1D42E1A5E479FFAC8F4FB3FDCE71DF4D"
)
INBOUND_HASH = (
    "750DD0B0DF374678707BB5AF915AF81C228B9058AD57BB7120569EC68BBB9C2E"
    "FC1B26C6375D2BC562AC909B3CD6B2AF1D42E1A5E479FFAC8F4FB3FDCE71DF4D"
)


# --- core ----------------------------------------------------------------------------

def parse_body(body, decode=True):
    """Split a Paynow message into ORDERED (key, value) pairs.

    Order is part of the digest, so this deliberately returns a list rather than a dict.
    """
    pairs = []
    for chunk in body.strip().split("&"):
        if not chunk:
            continue
        key, sep, value = chunk.partition("=")
        if decode:
            key, value = unquote_plus(key), unquote_plus(value) if sep else ""
        elif not sep:
            value = ""
        pairs.append((key, value))
    return pairs


def generate(pairs, key):
    """API hash: join VALUES in order, excluding `hash`, append key, SHA-512 uppercase.

    The key is lower-cased first, as both official SDKs do (PHP in its
    constructor, Node inside generateHash). Paynow's published keys are already
    lower-case, so this only shows up on a real upper-cased key.
    """
    concat = "".join(v for k, v in pairs if k.upper() != "HASH")
    return hashlib.sha512((concat + key.lower()).encode("utf-8")).hexdigest().upper()


def generate_notification(pairs, key):
    """Notification-URL hash: join KEY+VALUE in order, excluding `Hash`."""
    concat = "".join(k + v for k, v in pairs if k.upper() != "HASH")
    return hashlib.sha512((concat + key.lower()).encode("utf-8")).hexdigest().upper()


def received_hash(pairs):
    for k, v in pairs:
        if k.upper() == "HASH":
            return v
    return None


# --- commands ------------------------------------------------------------------------

def cmd_generate(args, hasher=generate):
    pairs = parse_body(args.body, decode=not args.no_decode)
    digest = hasher(pairs, args.key)
    if args.verbose:
        concat = "".join(v for k, v in pairs if k.upper() != "HASH")
        print("fields joined (%d, hash excluded):" % len([p for p in pairs if p[0].upper() != "HASH"]))
        for k, v in pairs:
            marker = "  [skipped]" if k.upper() == "HASH" else ""
            print("  %-24s %s%s" % (k, v, marker))
        print("\nconcatenated:\n%s\n" % concat)
    print(digest)
    return 0


def cmd_verify(args, hasher=generate):
    pairs = parse_body(args.body, decode=not args.no_decode)
    got = received_hash(pairs)
    if got is None:
        print("FAIL: message contains no `hash` field", file=sys.stderr)
        return 2

    expected = hasher(pairs, args.key)
    ok = hmac.compare_digest(expected, got.upper())

    print("expected: %s" % expected)
    print("received: %s" % got.upper())
    print("MATCH" if ok else "MISMATCH")

    if not ok:
        print("\nThings to check, in the order they usually go wrong:", file=sys.stderr)
        print("  1. Are all returned values included? Paynow sends fields the docs omit", file=sys.stderr)
        print("     (paynowreference is a common one) and they are inside the digest.", file=sys.stderr)
        print("  2. Is field order exactly as it arrived? Parse the raw body, not a", file=sys.stderr)
        print("     framework-parsed object.", file=sys.stderr)
        print("  3. Are inbound values URL-decoded before joining? Try --no-decode to", file=sys.stderr)
        print("     see whether the body was already decoded.", file=sys.stderr)
        print("  4. Is this a link/button Notification POST? Those use key+value -", file=sys.stderr)
        print("     rerun with the `notification` subcommand.", file=sys.stderr)
        print("  5. Is the integration key the one for THIS integration?", file=sys.stderr)
    return 0 if ok else 1


def cmd_selftest(_args):
    failures = 0

    out = generate(parse_body(OUTBOUND_BODY), FIXTURE_KEY)
    ok = out == OUTBOUND_HASH
    failures += not ok
    print("%s  outbound fixture (generate)" % ("PASS" if ok else "FAIL"))
    if not ok:
        print("      expected %s\n      got      %s" % (OUTBOUND_HASH, out))

    inb = generate(parse_body(INBOUND_BODY), FIXTURE_KEY)
    ok = inb == INBOUND_HASH
    failures += not ok
    print("%s  inbound fixture (verify)" % ("PASS" if ok else "FAIL"))
    if not ok:
        print("      expected %s\n      got      %s" % (INBOUND_HASH, inb))

    # Both official SDKs lower-case the key before hashing; a helper that skips
    # this passes every published fixture and fails on a real upper-cased key.
    up = generate(parse_body(OUTBOUND_BODY), FIXTURE_KEY.upper())
    ok = up == OUTBOUND_HASH
    failures += not ok
    print("%s  upper-cased key gives the same digest" % ("PASS" if ok else "FAIL"))

    # A hash must not validate under a different key.
    bad = generate(parse_body(INBOUND_BODY), FIXTURE_KEY.replace("3e9", "3e8"))
    ok = bad != INBOUND_HASH
    failures += not ok
    print("%s  wrong key is rejected" % ("PASS" if ok else "FAIL"))

    print("\n%d/4 passed" % (4 - failures))
    if not failures:
        print("\nPort these two fixtures into the project's own test suite. A hashing"
              "\nhelper proven against them removes the largest single class of Paynow bugs.")
    return 1 if failures else 0


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    def add_common(sp):
        sp.add_argument("--key", required=True, help="Paynow integration key (GUID)")
        sp.add_argument("--body", required=True, help="the raw message, e.g. 'a=1&b=2&hash=...'")
        sp.add_argument("--no-decode", action="store_true",
                        help="treat values as already URL-decoded")
        sp.add_argument("-v", "--verbose", action="store_true", help="show the joined string")

    add_common(sub.add_parser("generate", help="compute an API hash"))
    add_common(sub.add_parser("verify", help="verify an API hash"))
    add_common(sub.add_parser("notification", help="verify a link/button Notification POST hash"))
    sub.add_parser("selftest", help="check the algorithm against Paynow's published fixtures")

    args = p.parse_args()
    if args.cmd == "generate":
        return cmd_generate(args)
    if args.cmd == "verify":
        return cmd_verify(args)
    if args.cmd == "notification":
        return cmd_verify(args, hasher=generate_notification)
    return cmd_selftest(args)


if __name__ == "__main__":
    sys.exit(main())
