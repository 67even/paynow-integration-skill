---
title: "Paynow Zimbabwe integration: PHP, Laravel, Node.js"
description: >-
  Integrate Paynow Zimbabwe correctly in PHP/Laravel, Node.js/Express or raw
  HTTP. EcoCash, OneMoney, InnBucks. Verified against Paynow's own SDKs.
permalink: /
lede: "Paynow's documentation tells you to gate order fulfilment on paid(). Follow that advice and you will lose orders."
---

A Paynow transaction is **fully paid** in three states — `Paid`, `Awaiting Delivery`
and `Delivered`. But the PHP SDK implements its helper as:

```php
public function paid()
{
    return $this->status() === 'paid';
}
```

So `Awaiting Delivery` returns `false`. The money arrives, your callback returns
`200`, Paynow never retries, the dashboard shows the transaction as paid — and your
customer gets nothing. Silently, with no error and no log line.

The Node SDK is worse: it has **no `paid()` method at all**, yet the published
quickstart still shows `if (status.paid())`. That throws `TypeError` at runtime.

> Paynow's own worked example of a **successful** O'mari payment carries
> `status=Awaiting+Delivery`. The evidence was always there.

This site documents what it actually takes to integrate Paynow correctly. Every
claim was checked against `paynow/php-sdk` and npm `paynow` v2.2.2 directly, not
taken from the documentation.

## Start here

| | |
|---|---|
| [**Troubleshooting**](troubleshooting/) | Something is broken right now. Symptom-to-cause table — start here rather than re-reading the protocol. |
| [**Hashing**](hashing/) | Hash mismatches, and the two fixtures Paynow publishes. Almost every "Paynow isn't working" report is a hashing bug. |
| [**PHP / Laravel**](php-laravel/) | SDK surface, the exceptions it throws instead of returning failures, and complete controller/service/routes/migration wiring. |
| [**Node.js / Express**](nodejs-express/) | The SDK's two defects, a raw client for InnBucks and O'mari, and a callback route that preserves field order. |
| [**HTTP API**](raw-http/) | Every endpoint, request field and status value — for Python, Go, Ruby, Java, C# or anything else that speaks HTTP. |
| [**Test mode & go-live**](testing/) | Test phone numbers and card tokens, the merchant-account rule that blocks your own test payments, and the go-live checklist. |

## The five rules that stop money going missing

These are the failures that actually cost merchants money in production.

1. **The `returnurl` is cosmetic — never fulfil from it.** Only the server-to-server
   `resulturl` callback is authoritative. A customer can close the tab, lose signal,
   cancel and still be returned, or type the URL by hand.
2. **`paid()` does not mean paid.** Check the status word yourself against all three
   paid states.
3. **Verify the hash over *every* value, in arrival order** — never a documented field
   list. Paynow returns fields the docs omit, and they are inside the digest.
4. **Persist the `pollUrl` before you redirect**, and send a unique `merchanttrace` on
   Express Checkout. Otherwise a lost response is unrecoverable.
5. **Make the callback idempotent and reconcile the amount.** Paynow retries up to ten
   times and legitimately sends the same update more than once.

## Install the skill

The reference on this site also ships as a skill for Claude, so the guidance applies
itself while you write the integration.

```bash
git clone https://github.com/67even/paynow-integration-skill.git
cp -r paynow-integration-skill/paynow-skills/paynow-integration ~/.claude/skills/
```

It comes with two tools that need only Python and no dependencies: one that proves a
hashing implementation against Paynow's published fixtures in any language, and one
that scans an existing codebase for the mistakes above.

[**View the repository on GitHub →**](https://github.com/67even/paynow-integration-skill)

## Known upstream documentation defects

Places where the [Paynow Developer Hub](https://developers.paynow.co.zw) is wrong
about its own SDKs, verified against the shipped packages on 20 September 2026.

| The hub says | The shipped SDK does | Severity |
|---|---|---|
| `paid()` covers the paid states | `status() === 'paid'` only | **Critical** |
| `status.paid()` (Node) | No `paid()` exists | **Critical** |
| `let status = paynow.pollTransaction(url)` | Returns a promise; must be awaited | High |
| Link-encoding recipe | Published example links are not reproducible from the documented steps | High |
| InnBucks `com.innbucks.customer://` | npm `paynow` builds `schinn.wbpycode://` | Medium |
| Initiate response has four fields | Also returns `paynowreference`, which is inside the hash | Medium |
| PHP constructor example | Missing a comma — does not parse | Medium |
| Shopify listed as a plugin | No self-serve setup; email `sales@paynow.co.zw` first | Low |

If you re-check this against the hub later and find these disagreeing, the hub is the
stale one — but please
[open an issue](https://github.com/67even/paynow-integration-skill/issues) if the
packages have changed.
