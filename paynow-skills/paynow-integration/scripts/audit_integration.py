#!/usr/bin/env python3
"""Audit an existing Paynow integration for the mistakes that lose money.

    python3 audit_integration.py /path/to/project
    python3 audit_integration.py /path/to/project --json

These are pattern checks, not a type system: they are tuned to catch the handful of
errors that show up again and again in real Paynow code, and they will occasionally
misfire on unusual structures.  Read each finding before acting on it.  A clean run is
not a guarantee of correctness - it means none of the known traps are visibly present.

Exit code is 1 if anything CRITICAL or HIGH was found, otherwise 0.
"""

import argparse
import json
import os
import re
import sys

SKIP_DIRS = {".git", "node_modules", "vendor", "dist", "build", ".next", "__pycache__",
             ".venv", "venv", "storage", "bootstrap/cache", ".idea", ".vscode"}
CODE_EXT = {".php", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".py", ".rb", ".go",
            ".java", ".cs", ".vue", ".blade.php", ".env", ".yml", ".yaml"}

# Field names Paynow returns; three or more concatenated together suggests a
# hard-coded field list rather than hashing whatever actually arrived.
RESPONSE_FIELDS = ["status", "browserurl", "pollurl", "reference", "amount",
                   "paynowreference", "instructions", "error"]


COMMENT = re.compile(r"^\s*(?://|\*|/\*|#|<!--)")

TESTISH = re.compile(r"(?:^|/)(?:tests?|spec|specs|__tests__|fixtures?|examples?|docs?)/"
                     r"|(?:Test|Spec|Example)\.(?:php|js|ts|py)$|_test\.(?:py|go|js)$", re.I)

# Paynow publishes this key in its own hashing examples. Finding it in source means
# someone copied the docs, not that a live secret leaked.
PUBLIC_FIXTURE_KEY = "3e9fed89-60e1-4ce5-ab6e-6b1eb2d4f977"

# A file that only names the callback route (a route table, a config block) is not the
# thing that verifies the hash. Only flag files that actually read a request body.
READS_BODY = re.compile(r"php://input|->getContent\(|\$_POST|request\.body|req\.body"
                        r"|request\.get_data|readBody|rawBody|processStatusUpdate", re.I)


RETURN_HANDLER = re.compile(
    r"(?:function|def|fun|public function)\s+\w*(?:return|thank|complete|success)\w*\s*\("
    r"|(?:get|post|router\.get|app\.get|Route::get)\s*\(\s*['\"][^'\"]*"
    r"(?:return|thanks|complete|success)[^'\"]*['\"]",
    re.I)

BLOCK_END = re.compile(r"^\s*(?:public |private |protected |static |async )*"
                       r"(?:function|def|fun)\s+\w+|^\s*(?:app|router|Route)[.:]", re.I)


def return_handler_blocks(lines, max_len=45):
    """Yield (start_line_no, block_text) for handlers that look like returnurl targets.

    Scoped to the handler rather than the whole file because in a typical controller the
    checkout, callback and return actions all live together, and a file-level check would
    either miss the problem or flag the callback by mistake.
    """
    blocks = []
    for i, ln in enumerate(lines):
        if not RETURN_HANDLER.search(ln):
            continue
        body = []
        for j in range(i + 1, min(i + 1 + max_len, len(lines))):
            if BLOCK_END.match(lines[j]):
                break
            body.append(lines[j])
        blocks.append((i + 2, "\n".join(body)))
    return blocks


class Finding:
    def __init__(self, severity, code, path, line, snippet, why, fix):
        self.severity, self.code = severity, code
        self.path, self.line, self.snippet = path, line, snippet.strip()[:160]
        self.why, self.fix = why, fix

    def as_dict(self):
        return {"severity": self.severity, "code": self.code, "file": self.path,
                "line": self.line, "snippet": self.snippet, "why": self.why, "fix": self.fix}


def walk(root):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for fn in filenames:
            if any(fn.endswith(e) for e in CODE_EXT) or fn == ".env":
                yield os.path.join(dirpath, fn)


def read(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""


def rel(root, path):
    return os.path.relpath(path, root)


def audit(root):
    findings = []
    paynow_files = []

    self_path = os.path.realpath(__file__)

    for path in walk(root):
        # Skip this script. It necessarily contains every pattern it looks for, so
        # scanning a directory that holds it would otherwise report its own rules
        # as findings.
        if os.path.realpath(path) == self_path:
            continue
        text = read(path)
        if not text:
            continue
        low = text.lower()
        touches_paynow = "paynow" in low
        if touches_paynow:
            paynow_files.append((path, text, low))

        lines = text.splitlines()

        # --- CRITICAL: paid() used as a gate -------------------------------------
        if touches_paynow:
            for i, ln in enumerate(lines, 1):
                if COMMENT.match(ln):
                    continue
                if re.search(r"(?:->|\.)paid\s*\(\s*\)", ln):
                    findings.append(Finding(
                        "CRITICAL", "paid-helper", rel(root, path), i, ln,
                        "The PHP SDK's paid() is `status() === 'paid'`, so it is false for "
                        "Awaiting Delivery and Delivered - both fully paid. The Node SDK has "
                        "no paid() at all and this throws TypeError.",
                        "Compare the status word yourself against "
                        "['paid','awaiting delivery','delivered'] (PHP status() is lower-cased) "
                        "or [\"Paid\",\"Awaiting Delivery\",\"Delivered\"] (Node)."))

        # --- CRITICAL: hard-coded integration key --------------------------------
        testish = bool(TESTISH.search(rel(root, path)))
        for i, ln in enumerate(lines, 1):
            if re.search(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", ln, re.I):
                if PUBLIC_FIXTURE_KEY in ln.lower() or testish or path.endswith(".env"):
                    continue
                ctx = " ".join(lines[max(0, i - 3):i + 2]).lower()
                if "paynow" in ctx and "key" in ctx:
                    findings.append(Finding(
                        "CRITICAL", "hardcoded-key", rel(root, path), i, ln,
                        "The integration key is the only thing standing between a stranger and "
                        "a forged 'Paid' callback. In source it reaches version control, logs "
                        "and anyone who has ever had repo access.",
                        "Move it to environment/secret storage and rotate the exposed key via "
                        "Generate New Key in the Paynow dashboard."))

        # --- HIGH: fixed field list in a hash ------------------------------------
        if touches_paynow or "sha512" in low:
            for i, ln in enumerate(lines, 1):
                if COMMENT.match(ln):
                    continue
                hits = [f for f in RESPONSE_FIELDS if re.search(r"['\"\[]%s['\"\]]" % f, ln)]
                if len(hits) >= 3 and re.search(r"\.\s*|\+|\bjoin\b|\bconcat\b", ln):
                    findings.append(Finding(
                        "HIGH", "fixed-field-hash", rel(root, path), i, ln,
                        "Paynow returns fields the docs don't list - paynowreference is in "
                        "initiate responses and inside the digest. Hashing a fixed list fails "
                        "on every real transaction and looks like a wrong key.",
                        "Iterate over every field that actually arrived, in arrival order, "
                        "skipping only `hash`."))

        # --- HIGH: parse_str on a Paynow response --------------------------------
        if touches_paynow and "parse_str" in low:
            for i, ln in enumerate(lines, 1):
                if "parse_str" in ln and not COMMENT.match(ln):
                    findings.append(Finding(
                        "HIGH", "parse-str", rel(root, path), i, ln,
                        "parse_str() mangles keys containing dots or spaces and gives no "
                        "ordering guarantee, and the hash depends on field order.",
                        "Split the raw body manually into an ordered array - see "
                        "references/hashing.md."))

        # --- MEDIUM: deprecated Google chart QR ----------------------------------
        for i, ln in enumerate(lines, 1):
            if "chart.googleapis.com" in ln:
                findings.append(Finding(
                    "MEDIUM", "third-party-qr", rel(root, path), i, ln,
                    "This sends the payment authorization code to a third party on every "
                    "checkout, and Google's Image Charts endpoint is deprecated with no "
                    "availability guarantee.",
                    "Generate the QR locally - `qrcode` (npm) or `endroid/qr-code` (composer)."))

        # --- MEDIUM: InnBucks deep link without a fallback -----------------------
        if "com.innbucks.customer" in low and "schinn.wbpycode" not in low:
            i = next((n for n, l in enumerate(lines, 1) if "com.innbucks.customer" in l), 1)
            findings.append(Finding(
                "MEDIUM", "innbucks-scheme", rel(root, path), i, lines[i - 1],
                "The documented scheme and the one the paynow npm package builds disagree. "
                "Shipping only the documented one risks a dead link on the customer's handset.",
                "Prefer response.innbucks_info[0].deep_link_url, or offer "
                "schinn.wbpycode://innbucks.co.zw?pymInnCode= as primary with this as "
                "fallback. Keep the QR as the primary path in the UI."))

    # --- whole-file checks on the callback/return handlers ------------------------
    for path, text, low in paynow_files:
        lines = text.splitlines()
        is_callback = bool(re.search(r"resulturl|result_url|/callback|statusupdate|status_update"
                                     r"|processStatusUpdate", low)) and bool(READS_BODY.search(text))
        verifies = bool(re.search(r"sha512|hash_equals|timingsafeequal|verifyhash|->verify\("
                                  r"|\.verify\(|processstatusupdate", low))

        if is_callback and not verifies:
            i = next((n for n, l in enumerate(lines, 1)
                      if re.search(r"resulturl|/callback|status_update|statusupdate", l, re.I)), 1)
            findings.append(Finding(
                "CRITICAL", "unverified-callback", rel(root, path), i, lines[i - 1],
                "This handler appears to accept Paynow status updates without verifying the "
                "hash. The callback URL is public by definition - anyone who finds it can POST "
                "a fake 'Paid' and take goods for free.",
                "Verify the SHA-512 hash over every value in arrival order, timing-safe, "
                "before touching the order. See references/hashing.md."))

        if is_callback and verifies and not re.search(
                r"fulfilled|isfulfilled|is_paid|ispaid|already|idempot|unique|firstorcreate"
                r"|->wherenull|status\s*!==?\s*['\"]paid", low):
            i = next((n for n, l in enumerate(lines, 1)
                      if re.search(r"resulturl|/callback|status_update", l, re.I)), 1)
            findings.append(Finding(
                "HIGH", "non-idempotent-callback", rel(root, path), i, lines[i - 1],
                "Paynow retries a status update up to ten times on error and legitimately "
                "sends the same update more than once. Without a guard the order is fulfilled "
                "repeatedly.",
                "Check a fulfilled flag (or rely on a unique constraint) before doing work, "
                "and return 200 quickly."))

        for line_no, blk in return_handler_blocks(lines):
            hit = re.search(r"markpaid|mark_paid|fulfil|fulfill|::dispatch|->dispatch"
                            r"|queue|deliverorder|grantaccess|activatesubscription", blk, re.I)
            if not hit:
                continue
            off = blk[:hit.start()].count("\n")
            findings.append(Finding(
                "CRITICAL", "fulfil-on-return", rel(root, path), line_no + off,
                lines[min(line_no + off - 1, len(lines) - 1)],
                "The returnurl is where the customer's browser lands - it is cosmetic. "
                "Fulfilling from it means anyone who opens that URL gets the goods, and a "
                "customer who closes the tab after paying gets nothing.",
                "Fulfil only from the hash-verified resulturl callback or an explicit poll. "
                "The return page should render whatever state the order is already in."))

        if re.search(r"redirecturl", low) and "pollurl" not in low:
            i = next((n for n, l in enumerate(lines, 1) if re.search(r"redirecturl", l, re.I)), 1)
            findings.append(Finding(
                "HIGH", "pollurl-not-persisted", rel(root, path), i, lines[i - 1],
                "The pollUrl is the only handle on the transaction after initiation. Redirecting "
                "without storing it leaves a paying customer and an order you cannot resolve.",
                "Persist pollUrl against the order in the same request that created the "
                "transaction, before redirecting."))

        if re.search(r"express\.urlencoded", low) and is_callback:
            i = next((n for n, l in enumerate(lines, 1) if "express.urlencoded" in l.lower()), 1)
            findings.append(Finding(
                "MEDIUM", "parsed-body-hash", rel(root, path), i, lines[i - 1],
                "The hash depends on field order. A parsed object usually preserves insertion "
                "order in V8, but 'usually' is a poor foundation for payment verification.",
                "Use express.raw({ type: '*/*' }) on the callback route only and parse the raw "
                "body yourself."))

        if re.search(r"method\s*[=:>]+\s*['\"](?:vmc|zimswitch)['\"]", low) \
                and "merchanttrace" not in low:
            i = next((n for n, l in enumerate(lines, 1)
                      if re.search(r"vmc|zimswitch", l, re.I)), 1)
            findings.append(Finding(
                "MEDIUM", "no-merchanttrace", rel(root, path), i, lines[i - 1],
                "Without a merchanttrace, an Express Checkout request whose response is lost to "
                "a timeout cannot be recovered - there is no pollUrl and no way to trace it. On "
                "card rails it is also what prevents a duplicate debit on retry.",
                "Send a unique merchanttrace (<=32 chars) with every Express Checkout request "
                "and store it against the order."))

    order = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
    findings.sort(key=lambda f: (order.get(f.severity, 9), f.path, f.line))
    return findings, len(paynow_files)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path", help="project root to audit")
    ap.add_argument("--json", action="store_true", help="emit JSON instead of a report")
    args = ap.parse_args()

    root = os.path.abspath(args.path)
    if not os.path.isdir(root):
        print("not a directory: %s" % root, file=sys.stderr)
        return 2

    findings, n_files = audit(root)

    if args.json:
        print(json.dumps({"root": root, "paynow_files": n_files,
                          "findings": [f.as_dict() for f in findings]}, indent=2))
    else:
        print("Paynow integration audit - %s" % root)
        print("%d file(s) reference Paynow; %d finding(s)\n" % (n_files, len(findings)))
        if n_files == 0:
            print("No files mention Paynow. Is this the right directory?")
        elif not findings:
            print("None of the known traps are visibly present.")
            print("This is not a proof of correctness - confirm by hand that fulfilment is")
            print("driven only by the verified callback, and that all three paid states")
            print("(Paid / Awaiting Delivery / Delivered) are treated as paid.")
        else:
            current = None
            for f in findings:
                if f.severity != current:
                    current = f.severity
                    print("=" * 72)
                    print(current)
                    print("=" * 72)
                print("\n  %s:%d  [%s]" % (f.path, f.line, f.code))
                print("    > %s" % f.snippet)
                print("    why: %s" % f.why)
                print("    fix: %s" % f.fix)
            print()

    return 1 if any(f.severity in ("CRITICAL", "HIGH") for f in findings) else 0


if __name__ == "__main__":
    sys.exit(main())
