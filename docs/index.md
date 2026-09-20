---
title: Home
nav_order: 1
permalink: /
description: >-
  Integrate Paynow Zimbabwe correctly in PHP/Laravel, Node.js/Express or raw
  HTTP. EcoCash, OneMoney, InnBucks. Verified against Paynow's own SDKs.
last_modified_at: 2026-09-20
image:
  path: /assets/og/home.png
  width: 1200
  height: 630
  alt: "Paynow Integration Skill - integrate Paynow Zimbabwe in PHP, Laravel and Node.js"
---

<div class="hero" markdown="0">
  <img class="hero-mark" src="{{ '/assets/images/67even-logo.png' | relative_url }}" alt="67even">
  <p class="hero-tagline">Integrating the Paynow Zimbabwe payment gateway without the bugs that cost merchants money.</p>
  <p class="hero-badges">
    <a href="https://github.com/67even/paynow-integration-skill/stargazers"><img src="https://img.shields.io/github/stars/67even/paynow-integration-skill?style=flat-square&logo=github&label=Stars&color=FF3131&labelColor=0C0E0B" alt="GitHub stars"></a>
    <a href="https://github.com/67even/paynow-integration-skill/actions/workflows/tests.yml"><img src="https://img.shields.io/github/actions/workflow/status/67even/paynow-integration-skill/tests.yml?branch=main&style=flat-square&logo=githubactions&logoColor=white&label=tests&color=FF3131&labelColor=0C0E0B" alt="Tests"></a>
    <a href="https://github.com/67even/paynow-integration-skill/blob/main/LICENSE"><img src="https://img.shields.io/github/license/67even/paynow-integration-skill?style=flat-square&label=License&color=FF3131&labelColor=0C0E0B" alt="MIT licence"></a>
    <a href="https://github.com/67even/paynow-integration-skill"><img src="https://img.shields.io/github/last-commit/67even/paynow-integration-skill?style=flat-square&label=Updated&color=FF3131&labelColor=0C0E0B" alt="Last commit"></a>
  </p>
</div>

<div class="hero-actions" markdown="1">
[View on GitHub](https://github.com/67even/paynow-integration-skill){: .btn .btn-primary }
[Troubleshoot a problem](troubleshooting/){: .btn }
</div>

---

## `paid()` does not mean paid

Paynow's documentation tells you to gate order fulfilment on `paid()`. Follow that
advice and you will lose orders.

A transaction is **fully paid** in three states — `Paid`, `Awaiting Delivery` and
`Delivered`. But the PHP SDK implements its helper as:

```php
public function paid()
{
    return $this->status() === 'paid';
}
```

So `Awaiting Delivery` returns `false`. The money arrives, your callback returns `200`,
Paynow never retries, the dashboard shows the transaction as paid — and your customer
gets nothing. Silently, with no error and no log line.

The Node SDK is worse: it has **no `paid()` method at all**, yet the published
quickstart still shows `if (status.paid())`. That throws `TypeError` at runtime.

{: .warning }
> Paynow's own worked example of a **successful** O'mari payment carries
> `status=Awaiting+Delivery`. The evidence was always there.

Every claim on this site was checked against `paynow/php-sdk` and npm `paynow` v2.2.2
directly, not taken from the documentation.

---

## Where to start

| | |
|:--|:--|
| [**Troubleshooting**](troubleshooting/) | Something is broken right now. Symptom-to-cause table. |
| [**Hashing & signatures**](hashing/) | Hash mismatches, and the two fixtures Paynow publishes. |
| [**PHP & Laravel**](php-laravel/) | SDK surface, the exceptions it throws, complete wiring. |
| [**Node.js & Express**](nodejs-express/) | The SDK's two defects, raw client, callback route. |
| [**HTTP API reference**](raw-http/) | Every endpoint and field — for Python, Go, Java, C#. |
| [**Testing & go-live**](testing/) | Test numbers, card tokens, and the go-live checklist. |

---

## The five rules that stop money going missing

1. **The `returnurl` is cosmetic — never fulfil from it.** Only the server-to-server
   `resulturl` callback is authoritative.
2. **`paid()` does not mean paid.** Check the status word yourself against all three
   paid states.
3. **Verify the hash over *every* value, in arrival order** — never a documented field
   list. Paynow returns fields the docs omit, and they are inside the digest.
4. **Persist the `pollUrl` before you redirect**, and send a unique `merchanttrace` on
   Express Checkout. Otherwise a lost response is unrecoverable.
5. **Make the callback idempotent and reconcile the amount.** Paynow retries up to ten
   times and legitimately sends the same update more than once.

---

## Install the skill

This reference also ships as a skill for Claude, so the guidance applies itself while
you write the integration.

```bash
git clone https://github.com/67even/paynow-integration-skill.git
cp -r paynow-integration-skill/paynow-skills/paynow-integration ~/.claude/skills/
```

It includes two tools that need only Python and no dependencies: one that proves a
hashing implementation against Paynow's published fixtures in any language, and one
that scans an existing codebase for the mistakes above.

```bash
python3 scripts/paynow_hash.py selftest              # 4/4 expected
python3 scripts/audit_integration.py /path/to/project
```

---

## Known upstream documentation defects

Places where the [Paynow Developer Hub](https://developers.paynow.co.zw) is wrong about
its own SDKs, verified against the shipped packages on 20 September 2026.

| The hub says | The shipped SDK does | Severity |
|:--|:--|:--|
| `paid()` covers the paid states | `status() === 'paid'` only | **Critical** |
| `status.paid()` (Node) | No `paid()` exists | **Critical** |
| `let status = paynow.pollTransaction(url)` | Returns a promise; must be awaited | High |
| Link-encoding recipe | Published examples are not reproducible from the documented steps | High |
| InnBucks `com.innbucks.customer://` | npm `paynow` builds `schinn.wbpycode://` | Medium |
| Initiate response has four fields | Also returns `paynowreference`, which is inside the hash | Medium |
| PHP constructor example | Missing a comma — does not parse | Medium |
| Shopify listed as a plugin | No self-serve setup; email `sales@paynow.co.zw` first | Low |

If you re-check these against the hub later and find them disagreeing, the hub is the
stale one — but please
[open an issue](https://github.com/67even/paynow-integration-skill/issues) if the
packages have changed.
