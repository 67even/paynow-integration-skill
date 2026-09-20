<h1 align="center">Paynow Integration Skill</h1>

<p align="center">
  <strong>A Claude skill for integrating the Paynow Zimbabwe payment gateway — without the bugs that cost merchants money.</strong>
</p>

<p align="center">
  <a href="#installation"><img alt="Claude Skill" src="https://img.shields.io/badge/Claude-Skill-D97757"></a>
  <a href="LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/License-MIT-blue.svg"></a>
  <img alt="PHP 8.0+" src="https://img.shields.io/badge/PHP-8.0%2B-777BB4?logo=php&logoColor=white">
  <img alt="Node 18+" src="https://img.shields.io/badge/Node.js-18%2B-339933?logo=node.js&logoColor=white">
  <img alt="Python 3.8+" src="https://img.shields.io/badge/Python-3.8%2B-3776AB?logo=python&logoColor=white">
  <a href="https://github.com/67even/paynow-integration-skill/actions/workflows/tests.yml"><img alt="tests" src="https://github.com/67even/paynow-integration-skill/actions/workflows/tests.yml/badge.svg"></a>
</p>

---

## Why this exists

Paynow's official documentation tells you to gate order fulfilment on the SDK's
`paid()` helper.

Follow that advice and you will lose orders. A Paynow transaction is **fully paid**
in three states — `Paid`, `Awaiting Delivery` and `Delivered` — but the PHP SDK
implements the helper as:

```php
public function paid()
{
    return $this->status() === 'paid';
}
```

So `Awaiting Delivery` returns `false`. The money arrives, the callback returns `200`,
Paynow never retries, the dashboard shows the transaction as paid — and your customer
gets nothing. Silently, with no error and no log line.

The Node SDK is worse: it has **no `paid()` method at all**, yet the published
quickstart still shows `if (status.paid())`. That throws `TypeError` at runtime.

This skill exists because integrating Paynow correctly requires knowing several things
the documentation does not tell you, and a few things it tells you wrongly. Every claim
here was checked against `paynow/php-sdk` and npm `paynow` v2.2.2 directly, not taken
from the docs.

> Paynow's own worked example of a **successful** O'mari payment carries
> `status=Awaiting+Delivery`. The evidence was always there.

---

## Table of contents

- [What you get](#what-you-get)
- [Supported languages and frameworks](#supported-languages-and-frameworks)
- [Installation](#installation)
- [Usage](#usage)
- [The two tools](#the-two-tools)
- [What the skill is opinionated about](#what-the-skill-is-opinionated-about)
- [Repository structure](#repository-structure)
- [Verification](#verification)
- [Does it actually help?](#does-it-actually-help)
- [Known upstream documentation defects](#known-upstream-documentation-defects)
- [Contributing](#contributing)
- [Author](#author)
- [License](#license)

---

## What you get

| | |
|---|---|
| **A skill Claude loads on demand** | `SKILL.md` carries the decision tree and five money-safety rules. Six reference files load only when the task needs them, so nothing is wasted on a question about hashing when you asked about test mode. |
| **Copy-ready starter code** | A Laravel service, controller, routes, migration and PHPUnit tests; an Express route set, raw Express Checkout client and `node --test` suite. Written to be adapted, not pasted blind. |
| **Two executable tools** | Prove a hashing implementation in any language against Paynow's published fixtures, and scan an existing codebase for the mistakes that lose money. |
| **A corrected API reference** | [`PAYNOW.md`](PAYNOW.md) — the full protocol, with an appendix documenting the nine places the official hub is wrong about its own SDKs. |

---

## Supported languages and frameworks

### First class — full starter code and dedicated reference

| Stack | Minimum | What ships | Reference |
|---|---|---|---|
| **PHP / Laravel** | PHP **8.0+**<br>Laravel 10 or 11 | Hash helper, gateway service, controller (checkout / mobile / callback / return / status), routes, migration, PHPUnit tests, `.env` template | [`php-laravel.md`](paynow-skills/paynow-integration/references/php-laravel.md) |
| **Node.js / Express** | Node **18+**<br>Express 4 or 5 | Hash helper, raw Express Checkout client, full Express route set, `node --test` suite, `.env` template | [`nodejs-express.md`](paynow-skills/paynow-integration/references/nodejs-express.md) |

> **Why PHP 8.0+:** the shipped code uses constructor property promotion, named
> arguments and union types in `catch`. The `paynow/php-sdk` package itself supports
> PHP 5.6+, so you can back-port the helper if you must.
>
> **Why Node 18+:** the raw client uses built-in `fetch` and `AbortSignal.timeout`,
> and the test suite uses `node --test`. Swap in `axios` and any test runner to go
> lower.

### Any other language — full protocol reference

[`raw-http.md`](paynow-skills/paynow-integration/references/raw-http.md) documents
every endpoint, field table, status word and error path, so the skill still helps in
**Python, Go, Ruby, Java, C#, Elixir, Rust** or anything else that speaks HTTP.

Paynow publishes five official SDKs — PHP, Node.JS, **C#/.NET, Python and Java**. The
last three are not covered in depth here; check the hub's quickstart for your language
before hand-rolling.

### Tooling

The two scripts in `scripts/` need **Python 3.8+** and nothing else — standard library
only, no `pip install`. They are development tools, not runtime dependencies: you never
ship Python to integrate Paynow.

---

## Installation

### Option 1 — Claude Code / Cowork (recommended)

Clone the repo and copy the skill into your skills directory:

```bash
git clone https://github.com/67even/paynow-integration-skill.git
cd paynow-integration-skill

# Claude Code (project-scoped)
mkdir -p .claude/skills
cp -r paynow-skills/paynow-integration .claude/skills/

# or user-scoped, available in every project
mkdir -p ~/.claude/skills
cp -r paynow-skills/paynow-integration ~/.claude/skills/
```

Claude picks the skill up automatically the next time it starts.

### Option 2 — packaged `.skill` bundle

Build a distributable bundle and install it through the Claude UI:

```bash
zip -r paynow-integration.skill paynow-integration \
  -x '*/evals/*' -x '*/.DS_Store' \
  && echo "built paynow-integration.skill"
```

Run that from inside `paynow-skills/`. Attach the resulting file in Claude and click
**Save skill**.

### Option 3 — reference only, no skill

You do not need Claude to get value from this repo. Read [`PAYNOW.md`](PAYNOW.md),
lift the starter code from `paynow-skills/paynow-integration/assets/`, and run the two
scripts against your own project.

### Verify the install

```bash
cd paynow-skills/paynow-integration
python3 scripts/paynow_hash.py selftest          # expect 4/4
cd assets/node-express && node --test            # expect 6/6
```

Both check the same two hashing fixtures Paynow publishes. If a port of the helper into
your own language passes those, the single largest class of Paynow bugs is gone.

---

## Usage

Once installed, the skill triggers on its own. You do not invoke it by name.

**It fires on prompts like these:**

```text
Add Paynow checkout to my Laravel app — customers mostly pay by EcoCash.

We need InnBucks payments in our Express API. The SDK doesn't seem to support it?

Customers are paying but a chunk of them never get their orders. Here's the controller.

Why is my Paynow hash always mismatching? I'm following the docs exactly.

How do I test EcoCash payments without spending real money?
```

It also fires when you mention **EcoCash, OneMoney, InnBucks, O'mari or Zimswitch** in
a payments context, or ask for a payment gateway in a Zimbabwean app — even if you
never type the word "Paynow".

**Reviewing an existing integration?** Point Claude at the code and ask. It will run
the auditor first, which finds in seconds what takes a long read to spot.

---

## The two tools

### `paynow_hash.py` — prove and debug your hashing

Almost every "Paynow isn't working" report is a hashing bug. Build the helper first,
prove it, and that whole class of failure disappears.

```bash
# Check the algorithm against Paynow's two published fixtures
python3 scripts/paynow_hash.py selftest

# Debug a real mismatch against a captured response
python3 scripts/paynow_hash.py verify \
  --key 3e9fed89-... \
  --body 'status=Ok&pollurl=...&hash=750DD0B0...'

# Compute an outbound hash, showing the joined string
python3 scripts/paynow_hash.py generate --key 3e9fed89-... --body 'id=1201&...' -v

# Link/button Notification URLs use a DIFFERENT algorithm (key+value)
python3 scripts/paynow_hash.py notification --key ... --body 'Paynow_Reference=40222&...'
```

On a mismatch it prints the five things that actually go wrong, in the order they
usually go wrong. Exit code is `1` on mismatch, so it drops straight into CI.

### `audit_integration.py` — find the money-losing mistakes

```bash
python3 scripts/audit_integration.py /path/to/your/project
python3 scripts/audit_integration.py /path/to/project --json   # for CI
```

Detects, with severity and a fix for each: fulfilment on the return route, `paid()`
used as a gate, unverified callbacks, hashing a fixed field list, `parse_str` on a
Paynow response, missing idempotency guards, a hard-coded integration key, missing
`merchanttrace`, parsed-body hashing, third-party QR services, and the InnBucks
deep-link scheme mismatch.

Exit code is `1` if anything **CRITICAL** or **HIGH** is found. A clean run is not a
proof of correctness — it means none of the known traps are visibly present.

---

## What the skill is opinionated about

Five things, because these are what actually cost merchants money.

<details>
<summary><strong>1. The <code>returnurl</code> is cosmetic — never fulfil from it</strong></summary>

<br>

Paynow signals payment twice: it redirects the browser to your `returnurl`, and it
POSTs a status update server-to-server to your `resulturl`. Only the second is
authoritative. The first is just where the browser lands — the customer can close the
tab, lose signal, cancel and still be returned, or type the URL by hand.

Fulfil from the hash-verified callback or an explicit poll. Let the return page render
whatever state the order is already in.

</details>

<details>
<summary><strong>2. <code>paid()</code> does not mean paid</strong></summary>

<br>

PHP's matches only the literal `Paid`. Node has no `paid()` at all. Check the status
word yourself:

```php
$PAID = ['paid', 'awaiting delivery', 'delivered'];   // status() is LOWER-CASED
if (in_array($status->status(), $PAID, true)) { /* fulfil */ }
```

```js
const PAID = new Set(["Paid", "Awaiting Delivery", "Delivered"]);
const r = await paynow.pollTransaction(pollUrl);      // must be awaited
if (PAID.has(r.status)) { /* fulfil */ }
```

</details>

<details>
<summary><strong>3. Verify the hash over <em>every</em> value, in arrival order</strong></summary>

<br>

Your callback URL is public by definition — the hash is the only thing stopping a
stranger POSTing a fake `Paid`.

The trap: hash **every field that arrived**, never a documented field list. Paynow
returns fields the docs omit — `paynowreference` appears in initiate responses but not
in the response table — and they are inside the digest. Read the **raw body**, not a
framework-parsed object, so arrival order survives.

And lower-case the integration key before appending it. Both official SDKs do; every
key Paynow publishes is already lower-case, so skipping it passes every documented
example and fails on a real upper-cased key.

</details>

<details>
<summary><strong>4. Persist the <code>pollUrl</code> before you redirect</strong></summary>

<br>

It is your only handle on the transaction afterwards. Save it in the same request that
created the transaction — a crash between redirect and save leaves a paying customer
and an order you cannot resolve.

For Express Checkout also send a unique `merchanttrace` (≤32 chars) and store it. If
the response never arrives you have no `pollUrl`, and `/interface/trace` is the only
way back.

</details>

<details>
<summary><strong>5. Make the callback idempotent, and reconcile the amount</strong></summary>

<br>

Paynow retries a status update **up to ten times** if your endpoint errors, and
legitimately sends the same update more than once as a transaction moves through
states. Guard fulfilment with an atomic conditional update, a unique constraint or a
row lock. Return `200` fast — including for unknown references, since a `4xx` just
triggers the retries — and queue the slow work.

</details>

---

## Repository structure

```
.
├── README.md                    ← you are here
├── CHANGELOG.md
├── LICENSE
├── PAYNOW.md                    Full corrected Paynow API reference (~110 KB)
└── paynow-skills/
    ├── README.md                Skill-folder guide
    ├── VERIFICATION.md          What was executed to verify this, and what it proves
    └── paynow-integration/      ← the skill; this folder is what you install
        ├── SKILL.md             Decision tree + the five money-safety rules
        ├── references/
        │   ├── hashing.md               Algorithm, both published fixtures, pitfalls
        │   ├── php-laravel.md           SDK surface, exceptions, Laravel wiring
        │   ├── nodejs-express.md        SDK surface and its defects, raw client
        │   ├── raw-http.md              Endpoints and field tables for any language
        │   ├── testing-and-golive.md    Test credentials, test matrix, go-live
        │   └── troubleshooting.md       Symptom → cause table
        ├── scripts/
        │   ├── paynow_hash.py           Generate / verify / debug hashes
        │   └── audit_integration.py     Scan a codebase for money-losing mistakes
        ├── assets/
        │   ├── php-laravel/             Laravel starter set + PHPUnit tests
        │   └── node-express/            Express starter set + node:test suite
        └── evals/evals.json             Test prompts and assertions
```

---

## Verification

Everything here was verified by **execution**, not inspection.

| Check | Result |
|---|---|
| PHP helper vs the real `paynow/php-sdk` `Hash::make`, 1,006 inputs | **1006 agree, 0 disagree** |
| Node helper vs the real npm `paynow` `generateHash`, 1,005 inputs | **1005 agree, 0 disagree** |
| PHP and Node helpers produce identical digests for the same input | ✅ |
| Both published fixtures, plus tampering / wrong key / spaces / literal `+` / the separate notification algorithm | **13/13** |
| `php -l` on all 8 PHP assets (PHP 8.4) · `node --check` on all 4 JS assets | **8/8 · 4/4** |
| PHPUnit **5** · `node --test` **6** · Python `selftest` **4** | **15/15 passing** |
| Auditor precision — the shipped assets and the skill directory itself | **0 findings** |
| Auditor recall — deliberately broken PHP and Express fixtures | **4 and 5 findings** |
| 37 structural checks (paths, anchors, fixture constants, endpoint consistency) | **all clean** |

Full record: [`paynow-skills/VERIFICATION.md`](paynow-skills/VERIFICATION.md).

> **What this does not prove.** No request has ever been sent to Paynow from this code.
> Everything above is offline. Before going live, run the test matrix in
> [`testing-and-golive.md`](paynow-skills/paynow-integration/references/testing-and-golive.md)
> against a real integration in test mode — especially the `Awaiting Delivery` callback
> and the duplicate-callback case, which are exactly what offline testing cannot catch.

---

## Does it actually help?

Three realistic tasks were run twice — once with the skill, once without — and graded
against 34 objective assertions by an independent agent.

| | With skill | Without |
|---|---:|---:|
| Assertions passed | **34 / 34** | 24 / 34 (71%) |
| Mean wall-clock | **377 s** | 468 s |
| Mean tokens | 143,215 | **121,370** |

The skill costs about **22k more tokens** — the price of reading reference files — and
saves about **91 seconds**, because it reads a known answer instead of inferring one.

Every failure without the skill loses money or leaks: fulfilling in the return route
(free goods), polling a URL taken from the request body, `400` on an unknown reference
(ten Paynow retries), no `merchanttrace` (a lost response is unrecoverable), and an
invented expiry format that hard-expires live payment codes.

The debugging task is the clearest signal. Without the skill, the model invented a
confident bug that was not in the file — *"the result and return URLs are swapped in the
constructor"* — made it the headline finding with *"Verify this first"*, and hedged the
real cause into a sixth item. Correct code in the output does not rescue a wrong
diagnosis: the user acts on the diagnosis.

---

## Known upstream documentation defects

Places where the [Paynow Developer Hub](https://developers.paynow.co.zw) is wrong about
its own SDKs, verified against the shipped packages on 20 September 2026. If you
re-check this repo against the hub later and find these disagreeing, **the hub is the
stale one.**

| The hub says | The shipped SDK does | Severity |
|---|---|---|
| `paid()` covers the paid states | `status() === 'paid'` only — false for `Awaiting Delivery` and `Delivered` | **Critical** |
| `status.paid()` (Node) | No `paid()` exists; `pollTransaction()` even resolves an `InitResponse` | **Critical** |
| `let status = paynow.pollTransaction(url)` | Returns a promise; must be awaited | High |
| Link-encoding recipe | The published example links are not reproducible from the documented steps | High |
| InnBucks `com.innbucks.customer://` | npm `paynow` builds `schinn.wbpycode://` | Medium |
| Initiate response has four fields | Also returns `paynowreference`, which is inside the hash | Medium |
| PHP constructor example | Missing a comma — does not parse | Medium |
| Shopify listed as a plugin | No self-serve setup; email `sales@paynow.co.zw` first | Low |

Full detail in [`PAYNOW.md`](PAYNOW.md) Appendix E.

---

## Contributing

Issues and pull requests welcome — especially from anyone running Paynow in production.

**Particularly valuable:**

- Confirmation of the **InnBucks deep-link scheme** on a real handset. The hub and the
  npm package disagree and neither has been observed working here.
- The **timezone** of `authorizationexpires`. The format is documented as
  `d-MMM-yyyy HH:mm`; the timezone is not documented at all.
- Any behaviour that differs from what is written here. Please include the raw request
  and response bodies, with the hash and integration key redacted.

**Before opening a PR:**

```bash
cd paynow-skills/paynow-integration
python3 scripts/paynow_hash.py selftest                  # 4/4
python3 scripts/audit_integration.py assets/php-laravel  # 0 findings
python3 scripts/audit_integration.py assets/node-express # 0 findings
cd assets/node-express && node --test                    # 6/6
```

Never commit a real integration key. `.gitignore` covers `.env` and `*.key`, but the
check that matters is the one you do before `git add`.

---

## Author

Written and maintained by **[John Mugabe](https://github.com/johnmugabe)** ([@johnmugabe](https://github.com/johnmugabe)).

Every correction in this repository came from reading Paynow's own SDK source
against its published documentation and recording where the two disagree.

---

## License

[MIT](LICENSE) © 2026 John Mugabe.

Independent and community-maintained. Not affiliated with, endorsed by, or supported by
Paynow Zimbabwe. Paynow is a trademark of its respective owner.

---

<p align="center">
  <sub>Built for the Zimbabwean developers who kept losing orders to a helper called <code>paid()</code>.</sub>
</p>
