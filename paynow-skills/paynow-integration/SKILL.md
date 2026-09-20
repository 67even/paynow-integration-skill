---
name: paynow-integration
description: >
  Build, review, or debug Paynow Zimbabwe payment gateway integrations — in PHP/Laravel,
  Node.js/Express, or any language over raw HTTP. Covers web redirect checkout, Express
  Checkout (EcoCash, OneMoney, InnBucks, O'mari, Zimswitch, card tokens), SHA-512 hashing,
  status-update callbacks, polling, test mode and going live. Use this skill whenever the
  user mentions Paynow or paynow.co.zw, and also whenever they mention EcoCash, OneMoney,
  InnBucks, O'mari or Zimswitch in a payments context, or ask to add a payment gateway,
  checkout flow, mobile-money payment or payment callback to a Zimbabwean app — even if
  they never say "Paynow". Use it too when reviewing or debugging existing payment code
  for hash mismatches, duplicate charges, double-fulfilment, or orders that were paid but
  never fulfilled.
---

# Paynow Zimbabwe Integration

Paynow is a Zimbabwean payment aggregator sitting in front of Visa/Mastercard, Zimswitch,
EcoCash, OneMoney, InnBucks and O'mari. This skill gets an integration right the first
time and keeps money from going missing.

## Start here: which integration style?

| Style | What happens | Use when |
|---|---|---|
| **Web / redirect** | POST the transaction, get a `browserurl`, send the customer's browser there | Card payments, general checkout, you want Paynow to own the payment UI |
| **Express Checkout** | You collect the phone number or card token yourself and POST it. Customer authorises on their handset. **No redirect.** | Mobile money, in-app checkout, recurring card billing |

Both use the same hashing, the same callback and the same status vocabulary. Express
Checkout adds `method`, and for card rails a `merchanttrace`.

If the user hasn't said which, ask — it changes the UI they need to build. Mobile money
means building a "waiting for authorisation" screen; redirect means they build nothing.

## The transport, in one breath

Every merchant→Paynow call is an **HTTP POST** with
`Content-Type: application/x-www-form-urlencoded`. Responses are **not JSON** — they come
back as a URL-encoded query string that you must split and URL-decode yourself:

```
Status=Ok&BrowserUrl=http%3a%2f%2f...&PollUrl=http%3a%2f%2f...&Hash=8614C21D...
```

People lose hours to this. `res.json()` and `json_decode()` return nothing useful.

## The five rules that stop money going missing

These are the failures that actually cost merchants money in production. Everything else
in this skill is detail; this is the part to get right.

### 1. The `returnurl` is cosmetic. Never fulfil from it.

Paynow signals payment two ways: it redirects the customer's browser to your `returnurl`,
and it POSTs a status update server-to-server to your `resulturl`. Only the second is
authoritative. The first is just where the browser lands — the customer can close the tab,
lose signal, or hit that URL by hand. Fulfil from the verified `resulturl` callback or an
explicit poll, and let the return page render whatever state the order is already in.

### 2. `paid()` does not mean paid.

This is the single most expensive mistake in Paynow code, and it is the docs' fault.

A transaction is **fully paid** in three states: `Paid`, `Awaiting Delivery`, and
`Delivered`. `Awaiting Delivery` means Paynow is holding the money in suspense until the
merchant confirms delivery — the customer has paid. Paynow's own documentation makes this
plain without ever saying it outright: the worked example of a **successful** O'mari
payment on the Express Checkout page carries `status=Awaiting+Delivery`.

But the PHP SDK's helper is literally `return $this->status() === 'paid';`, so it returns
**false** for `Awaiting Delivery` and `Delivered`. And the Node SDK has **no `paid()`
method at all** — calling it throws `TypeError`, even though the published quickstart
shows it. Check the status word yourself:

```php
// PHP — status() returns a LOWER-CASED string
$PAID = ['paid', 'awaiting delivery', 'delivered'];
if (in_array($status->status(), $PAID, true)) { /* fulfil */ }
```

```js
// Node — every response member is a property; there is no paid()
const PAID = new Set(["Paid", "Awaiting Delivery", "Delivered"]);
const r = await paynow.pollTransaction(pollUrl);   // must be awaited
if (PAID.has(r.status)) { /* fulfil */ }
```

If you see `paid()` in code you are reviewing, that is a bug report, not a style note.

### 3. Verify the hash on every inbound message — over *every* value, in arrival order.

Every message in both directions carries a SHA-512 `hash`. Verifying it is what stops a
third party POSTing a fake "Paid" to your callback URL, which is public.

The trap: hash **every value in the response, in the order it arrived**, never a fixed
field list. Responses carry undocumented fields — `paynowreference` shows up in initiate
responses but isn't in the documented field table — and they are part of the digest. Code
written against the documented four fields fails on every real transaction.

Use an ordered structure (PHP ordered array, JS `Map`) and read the **raw body**, not a
framework-parsed object, so arrival order survives. See `references/hashing.md`.

### 4. Persist the `pollUrl` before you redirect or show instructions.

The `pollUrl` is your only handle on the transaction afterwards. Write it against the
order inside the same request that created the transaction. If you redirect first and save
second, a crash in between leaves a paying customer and an order you cannot resolve.

For Express Checkout also send a unique `merchanttrace` (≤32 chars) and store it — if the
response never arrives you have no `pollUrl`, and `/interface/trace` is the only way back.

### 5. Make the callback idempotent, and reconcile the amount.

Paynow retries a status update **up to ten times** if your endpoint returns an error, and
legitimately sends the same update more than once as a transaction moves through states.
Guard fulfilment with a unique constraint or a status check, return `200` fast, and queue
the slow work. Compare the callback `amount` against your own stored total before
fulfilling — never trust the posted figure on its own.

## Build order

Working in this order means each step is testable before the next one depends on it:

1. **Credentials** — Integration ID and Key into env/secret storage. The Key is a GUID
   secret: never in client-side code, a URL, a log line, or plaintext in the app database.
2. **Hashing helper + its self-test.** Do this first and prove it against the two known
   fixtures in `references/hashing.md`. Almost every "Paynow doesn't work" report is a
   hashing bug, and a helper you have already proved correct removes that whole class.
3. **Initiate** — build the transaction, verify the response hash, persist `pollUrl`.
4. **Callback handler** — raw body, verify hash, idempotent fulfilment, `200`.
5. **Return page** — read-only, renders current order state.
6. **Polling** — as confirmation after an important callback, and as the backstop for
   mobile money while the customer authorises on their handset.
7. **Test mode** — exercise success, delayed success, cancellation, insufficient balance,
   a duplicate callback and a bad hash before requesting go-live.

## Which reference to read

Read only what the task needs — these are detailed.

| File | Read it when |
|---|---|
| `references/hashing.md` | Writing or debugging any hash. Contains both known-good fixtures and the separate key+value algorithm used by link/button notifications. |
| `references/php-laravel.md` | PHP or Laravel work. SDK surface, the exceptions it throws, full controller/service/config/migration wiring. |
| `references/nodejs-express.md` | Node or Express work. SDK surface and its defects, raw client, raw-body callback route. |
| `references/raw-http.md` | Any other language, or Express Checkout methods the SDKs don't wrap (InnBucks, O'mari, Zimswitch, card tokens). Full endpoint and field tables. |
| `references/testing-and-golive.md` | Test mode, test phone numbers and tokens, the test matrix, go-live steps. |
| `references/troubleshooting.md` | Something is broken. Symptom → cause table; start here rather than re-reading the protocol. |

Copy-ready starting files live in `assets/php-laravel/` and `assets/node-express/`. They
are written to be adapted, not pasted blind — read the surrounding reference first.

## Scripts

```bash
# Prove a hashing implementation, or debug a mismatch against a captured response
python3 scripts/paynow_hash.py selftest
python3 scripts/paynow_hash.py verify --key <integration-key> --body 'status=Ok&pollurl=...&hash=...'
python3 scripts/paynow_hash.py generate --key <integration-key> --body 'id=1201&reference=INV-1&...'

# Audit an existing codebase for the classic money-losing mistakes
python3 scripts/audit_integration.py /path/to/project
```

`audit_integration.py` looks for fulfilment on the return route, `paid()` used as a gate,
missing hash verification, fixed-field-list hashing, and missing idempotency guards. Run
it whenever reviewing someone's existing integration — it finds in seconds what takes a
long read to spot.

## Things that will waste the user's time if you don't warn them

- **Test mode only lets the merchant account pay.** After creating a test transaction,
  only the account that owns the integration can log in and fake payment; anyone else sees
  "merchant is in testing". So in test mode `authemail` must be a merchant login address,
  or the developer locks themselves out of their own test. Make this configurable, not
  hardcoded to the customer's email.
- **The payment method must be ticked in the Paynow dashboard.** Calling `method=ecocash`
  on an integration without EcoCash enabled fails at initiation with an error saying so.
- **`amount` takes no currency symbol** and exactly two decimals: `number_format($n, 2,
  '.', '')` / `Number(n).toFixed(2)`. Locale-formatted floats are rejected.
- **Card tokens are re-issued on every charge.** The status update carries a *new* token —
  overwrite the stored one or recurring billing stops working within months.
- **A trace *error* does not mean the transaction is absent.** Never auto-refund or
  re-charge off one.
- **CSRF middleware will silently eat the callback.** Exempt that route in Laravel/Django/
  Rails before wondering why callbacks never arrive.

## When the user has an existing integration

Run `scripts/audit_integration.py` first, then read `references/troubleshooting.md`. Lead
with what is losing money (rules 1–5 above), not with style. An integration that fulfils
on `returnurl` or gates on `paid()` is shipping bugs right now, and that is worth saying
plainly even if they only asked about something else.
