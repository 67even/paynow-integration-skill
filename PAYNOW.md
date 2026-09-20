# Paynow Payment Gateway — Integration Reference (PHP & Node.js)

> A working reference for Claude (and humans) when writing code that integrates the
> **Paynow Zimbabwe** payment gateway into a PHP or Node.js project.
>
> Source of truth: <https://developers.paynow.co.zw>
> Compiled: 2026-09-20 · Revised: 2026-09-20 after a full re-verification against the hub
> and the shipped SDK packages. **See [Appendix E](#appendix-e--known-upstream-defects)
> for the places where the official docs are wrong about their own SDKs.**

---

## Table of Contents

1. [Concepts & Mental Model](#1-concepts--mental-model)
2. [Getting Your Integration ID & Key](#2-getting-your-integration-id--key)
3. [PHP SDK](#3-php-sdk)
4. [Node.js SDK](#4-nodejs-sdk)
5. [API Reference (raw HTTP)](#5-api-reference-raw-http)
6. [Hashing: Generate & Validate](#6-hashing-generate--validate)
7. [Links & Buttons](#7-links--buttons)
8. [Test Mode](#8-test-mode)
9. [Production Checklist & Gotchas](#9-production-checklist--gotchas)
10. [Copy-Paste Recipes](#10-copy-paste-recipes)

---

## 1. Concepts & Mental Model

Paynow is a Zimbabwean payment aggregator. It sits between your application and the
underlying rails (Visa/Mastercard, Zimswitch, EcoCash, OneMoney, InnBucks, O'mari).

### The two integration styles

| Style | What happens | Use when |
|---|---|---|
| **Web / Redirect** | You POST transaction details to Paynow, get back a `browserurl`, and redirect the customer's browser there to pay. | Card payments, general checkout, anything where you want Paynow to own the payment UI. |
| **Express Checkout (Remote)** | You collect the payment detail (phone number or card token) yourself and POST it. The customer authorises on their handset (USSD/OTP) — **no redirect**. | Mobile money, recurring card billing, in-app checkout. |

### The transport

Everything is **HTTP POST with `Content-Type: application/x-www-form-urlencoded`**.
Responses are **not JSON** — they come back as a URL-encoded query string:

```
Status=Ok&BrowserUrl=http%3a%2f%2f...&PollUrl=http%3a%2f%2f...&Hash=8614C21D...
```

You must `parse_str()` / `querystring.parse()` these, then **URL-decode each value**.

### The lifecycle

```
┌────────────┐
│ Your app   │
└─────┬──────┘
      │ 1. POST /interface/initiatetransaction  (id, reference, amount, urls, hash)
      ▼
┌────────────┐
│  Paynow    │  2. Replies: Status=Ok & BrowserUrl & PollUrl & Hash
└─────┬──────┘
      │ 3. You VALIDATE THE HASH, save PollUrl, redirect customer to BrowserUrl
      ▼
┌────────────┐
│  Customer  │  4. Pays (card / EcoCash / etc.)
└─────┬──────┘
      │
      ├──► 5a. Paynow POSTs a Status Update to your **resulturl**  (server-to-server, authoritative)
      │
      └──► 5b. Customer's browser is redirected to your **returnurl** (cosmetic only)
      
      6. You validate the hash on the status update, and optionally POST to PollUrl to confirm.
```

**Critical rule:** the `returnurl` redirect is *cosmetic*. Never fulfil an order based on it.
Only the `resulturl` callback (verified by hash) or an explicit poll is authoritative.

### The three security primitives

1. **Integration ID** — public-ish identifier of your integration (not your account).
2. **Integration Key** — a GUID secret. Never expose it in client-side code, URLs, or logs.
3. **Hash** — SHA-512 (uppercase hex) of concatenated field values + integration key.
   Every message in **both directions** carries one, and every message must be verified.

---

## 2. Getting Your Integration ID & Key

Each integration gets its own ID and Key. An account can have many integrations.

1. Register at <https://www.paynow.co.zw/Customer/Register> and complete email validation.
2. Log in and configure the bank account you want to be settled into.
3. Go to **Other Ways To Get Paid** → <https://www.paynow.co.zw/Home/Receive>
4. Click **Create/Manage Shopping Carts** → **Create Advanced Integration**.
5. Fill in:
   - **Name** — how you'll identify the integration.
   - **Absorb fees** — whether the merchant or customer carries Paynow's fee.
   - **Email** — where transaction updates go.
   - **Notification URL** — *leave blank* if you'll send a per-transaction `resulturl`
     (which is what both SDKs do). Only set it for link/button integrations.
   - **Note** — internal only, not shown to customers.
   - **Payment Methods** — tick every method you intend to use.
     ⚠️ If you later call `method=ecocash` but EcoCash isn't ticked, the request errors out.
6. **Save.**

The **Integration ID** is then visible in the *Integration Keys* section.
The **Integration Key is never displayed** — click **Email Key To Company Address** to receive it.

> **Going live:** click **Request to be Set Live**. Paynow support verifies you've done at
> least one successful test transaction. Also click **Generate New Key** when moving from
> dev to production, so old/test keys and ex-developers lose access.

### Storing credentials

```bash
# .env  — never commit this
PAYNOW_INTEGRATION_ID=1201
PAYNOW_INTEGRATION_KEY=3e9fed89-60e1-4ce5-ab6e-6b1eb2d4f977
PAYNOW_RESULT_URL=https://example.com/payments/paynow/callback
PAYNOW_RETURN_URL=https://example.com/payments/paynow/return
```

---

## 3. PHP SDK

### 3.1 Prerequisites

- The SDK itself supports PHP **5.6+**.
- ⚠️ **The reference implementations in §6.4 and §10.1 of this document require PHP 8.0+**
  (constructor property promotion, named arguments). Use PHP 8.x.
- The **cURL** extension enabled

### 3.2 Installation

```bash
composer require paynow/php-sdk
```

```php
<?php
require_once __DIR__ . '/vendor/autoload.php';
```

Without Composer, download the library and include its bundled autoloader:

```php
<?php
require_once 'path/to/library/autoloader.php';
```

### 3.3 Instantiating the client

```php
<?php
use Paynow\Payments\Paynow;

$paynow = new Paynow(
    getenv('PAYNOW_INTEGRATION_ID'),
    getenv('PAYNOW_INTEGRATION_KEY'),
    'https://example.com/paynow/return?ref=INV-35',   // returnurl  (browser lands here)
    'https://example.com/paynow/callback'             // resulturl  (server callback)
);
```

> ⚠️ **Gotcha:** the snippet published on the Paynow docs site is missing a comma after the
> return URL argument — it will not parse. Always put a comma between the two URLs.

URLs can also be set after construction, which is useful when you need to embed the
order reference into the return URL:

```php
$paynow->setReturnUrl('https://example.com/paynow/return?ref=' . urlencode($orderRef));
$paynow->setResultUrl('https://example.com/paynow/callback');
```

### 3.4 Creating a payment (cart)

```php
// createPayment(<your unique reference>, <customer email>)
$payment = $paynow->createPayment('INV-35', 'customer@example.com');

// add(<item name>, <price>)
$payment->add('Bananas', 2.50);
$payment->add('Apples',  3.40);
```

- The **reference must be unique per transaction** on your side (invoice no., order id, UUID).
- If the email matches a registered Paynow account the customer is prompted to log in;
  otherwise they're logged in anonymously.
- The total sent to Paynow is the sum of the added items.

### 3.5 Web (redirect) transaction

```php
use Paynow\Payments\InvalidIntegrationException;
use Paynow\Payments\HashMismatchException;
use Paynow\Http\ConnectionException;

try {
    $response = $paynow->send($payment);
} catch (InvalidIntegrationException $e) {
    // Wrong integration id, or the integration is not live yet.
    error_log('[paynow] invalid integration id');
    throw $e;
} catch (HashMismatchException $e) {
    // The SDK verified the response hash and it FAILED. Do not redirect.
    error_log('[paynow] RESPONSE HASH MISMATCH - possible tampering');
    throw $e;
} catch (ConnectionException $e) {
    // Transport/network failure - safe to retry.
    error_log('[paynow] connection failed: ' . $e->getMessage());
    throw $e;
}

if ($response->success()) {
    $redirectUrl = $response->redirectUrl();  // send the browser here
    $pollUrl     = $response->pollUrl();      // PERSIST THIS

    // Save $pollUrl against the order before redirecting.
    $orderRepo->attachPollUrl($orderRef, $pollUrl);

    header('Location: ' . $redirectUrl);
    exit;
}

// Failed to initiate. NOTE: errors() returns a STRING by default; errors(false) gives the array.
error_log('Paynow init failed: ' . $response->errors());
```

> ⚠️ **`send()` throws rather than returning a failed response** for the most common
> conditions of all — a wrong or not-yet-live integration ID, a failed hash, a network
> error, an empty cart. `success()` is only reached when nothing was thrown, so a bare
> `if ($response->success())` with no `try` will 500 on a misconfigured key.
> See [§3.10](#310-exceptions-the-php-sdk-throws).

### 3.6 Mobile money (Express Checkout) transaction

Only `ecocash` and `onemoney` are supported by the SDK helper. There is **no redirect** —
the customer gets a USSD prompt on their handset.

```php
$payment = $paynow->createPayment('INV-36', 'customer@example.com');
$payment->add('Sadza and Beans', 1.25);

try {
    $response = $paynow->sendMobile($payment, '0771111111', 'ecocash');
} catch (\Paynow\Payments\InvalidIntegrationException
       | \Paynow\Payments\HashMismatchException
       | \Paynow\Http\ConnectionException $e) {
    error_log('[paynow] ' . get_class($e) . ': ' . $e->getMessage());   // see §3.10
    throw $e;
}

if ($response->success()) {
    $pollUrl      = $response->pollUrl();       // PERSIST THIS
    $instructions = $response->instructions();  // SHOW THIS TO THE USER
} else {
    // e.g. "Insufficient balance" - $response->errors() returns a string
}
```

`instructions()` returns human-readable guidance ("Dial *151*200# …") that you should
render on screen while you poll.

### 3.7 Checking transaction status (polling)

```php
$status = $paynow->pollTransaction($pollUrl);

// ⚠️ Do NOT use $status->paid() - see the warning below.
// status() returns a LOWER-CASED string, so compare against lower-cased words.
$PAID = ['paid', 'awaiting delivery', 'delivered'];

if (in_array($status->status(), $PAID, true)) {
    // Funds confirmed — fulfil the order (idempotently!)
} else {
    // Still pending, cancelled, or failed
}
```

> ### ⚠️ `paid()` does not mean "paid"
>
> The PHP SDK implements it as `return $this->status() === 'paid';`, so it is **`false`
> for `Awaiting Delivery` and `Delivered`** — both of which are fully paid states.
> Using `paid()` as your fulfilment gate silently drops orders on any integration that
> uses the delivery-confirmation flow: the money arrives, the customer gets nothing.
>
> Note also that `status()` **lower-cases** its return value, so comparing it against the
> capitalised status words from §5.6 will never match.

### 3.8 Response object cheat-sheet (PHP)

| Method | Available on | Returns |
|---|---|---|
| `success()` | init response | `bool` — was the *initiation* accepted |
| `redirectUrl()` | web init | `string` — Paynow URL to redirect the browser to |
| `pollUrl()` | web + mobile init | `string` — URL to poll for status |
| `instructions()` | mobile init | `string` — payment instructions for the customer |
| `errors()` | init response | `string` — space-joined error details. Pass `errors(false)` for the array. |
| `paid()` | poll/status | ⚠️ `bool` — **true only for the literal status `Paid`.** Does **not** cover `Awaiting Delivery` / `Delivered`. Never use it as a fulfilment gate. |
| `status()` | poll/status | `string` — Paynow status word, **lower-cased by the SDK** (`awaiting delivery`, not `Awaiting Delivery`) |
| `amount()` | poll/status | the transaction amount |
| `reference()` | poll/status | your merchant reference |
| `paynowReference()` | poll/status | Paynow's own reference |

> `success()` only means *"Paynow accepted the request"*. It does **not** mean the customer paid.
> Payment is only confirmed by `paid()` on a poll, or by a hash-verified status update.

### 3.9 Complete PHP example

```php
<?php
require_once __DIR__ . '/vendor/autoload.php';

use Paynow\Payments\Paynow;

$paynow = new Paynow(
    getenv('PAYNOW_INTEGRATION_ID'),
    getenv('PAYNOW_INTEGRATION_KEY'),
    'https://example.com/paynow/return?gateway=paynow',
    'https://example.com/paynow/callback'
);

$payment = $paynow->createPayment('INV-35', 'customer@example.com');
$payment->add('Sadza and Beans', 1.25);

try {
    $response = $paynow->send($payment);
} catch (Throwable $e) {           // see §3.10 for the specific exception types
    error_log('[paynow] ' . get_class($e) . ': ' . $e->getMessage());
    http_response_code(502);
    exit('Could not start payment.');
}

if (! $response->success()) {
    http_response_code(502);
    exit('Could not start payment.');
}

$pollUrl = $response->pollUrl();
// persist $pollUrl keyed by 'INV-35' here...

header('Location: ' . $response->redirectUrl());
exit;
```

### 3.10 Exceptions the PHP SDK throws

`send()`, `sendMobile()` and `pollTransaction()` **throw** instead of returning a failed
response for the conditions below. `success()` is only reached when nothing was thrown.

| Exception | Namespace | Raised when |
|---|---|---|
| `InvalidIntegrationException` | `Paynow\Payments` | Paynow replied `Invalid id.` — wrong integration ID, or not set live. |
| `HashMismatchException` | `Paynow\Payments` | The response hash failed verification. **Never continue.** |
| `ConnectionException` | `Paynow\Http` | Transport/network failure. Safe to retry. |
| `EmptyCartException` | `Paynow\Payments` | `send()` called with no items added. |
| `EmptyTransactionReferenceException` | `Paynow\Payments` | `createPayment()` called with an empty reference. |
| `InvalidUrlException` | `Paynow\Payments` | `returnurl` / `resulturl` is not a valid URL. |

Note that `InvalidIntegrationException` in particular is **not** surfaced through
`success() === false` — the single most common misconfiguration bypasses your error
branch entirely unless you catch it.

> **Useful consequence:** because the SDK raises `HashMismatchException` itself, the §9.1
> checklist item *"hash verified on every inbound message"* is already satisfied on
> `send()`, `sendMobile()` and `pollTransaction()`. Only the `resulturl` callback (§10.2)
> needs hand-rolled verification.

### 3.11 `processStatusUpdate()` — the SDK's callback helper

The SDK ships a helper for the `resulturl` callback that reads `$_POST`, verifies the
hash, and returns a `StatusResponse`:

```php
try {
    $status = $paynow->processStatusUpdate();   // reads $_POST, verifies the hash
} catch (\Paynow\Payments\HashMismatchException $e) {
    error_log('[paynow] REJECTED callback: bad hash');
    http_response_code(400);
    exit;
}

$PAID = ['paid', 'awaiting delivery', 'delivered'];   // status() is lower-cased
if (in_array($status->status(), $PAID, true)) {
    // fulfil, idempotently
}

http_response_code(200);
```

> **Why §10.2 hand-rolls this instead:** the hash depends on the *order* Paynow sent the
> fields in. `$_POST` is a PHP-parsed array; reading the raw body with `php://input`
> preserves arrival order with no assumptions. Use `processStatusUpdate()` when you want
> brevity, the §10.2 pattern when you want the ordering guarantee.

---

## 4. Node.js SDK

### 4.1 Prerequisites

- Node.js (the library declares support from very old versions; use an LTS release)
- npm or yarn

### 4.2 Installation

```bash
npm install --save paynow
# or
yarn add paynow
```

### 4.3 Instantiating the client

```js
const { Paynow } = require("paynow");
// ESM:  import { Paynow } from "paynow";

const paynow = new Paynow(
  process.env.PAYNOW_INTEGRATION_ID,
  process.env.PAYNOW_INTEGRATION_KEY
);

// URLs are plain properties, set them any time before send()
paynow.resultUrl = "https://example.com/paynow/callback";
paynow.returnUrl = "https://example.com/paynow/return?merchantReference=INV-35";
```

- **`resultUrl`** — server-to-server POST target for status updates.
- **`returnUrl`** — where the browser lands afterwards. If you omit it you must rely
  entirely on polling to learn the outcome.

### 4.4 Creating a payment (cart)

```js
// Web transactions: email is optional
const payment = paynow.createPayment("INV-35");

// Mobile transactions: email is REQUIRED
const mobilePayment = paynow.createPayment("INV-37", "customer@example.com");

payment.add("Bananas", 2.5);
payment.add("Apples", 3.4);
```

Passing an email lets Paynow attempt to auto-login the customer if that address is
attached to a Paynow account.

> **TypeScript:** the shipped typings declare `createPayment(reference: string,
> authEmail: string)` — `authEmail` is **not** optional in the type, so the email-less
> web form above is a compile error even though it works fine at runtime. Pass
> `undefined as unknown as string`, or widen the signature in your own declaration file.

### 4.5 Web (redirect) transaction

```js
const response = await paynow.send(payment);   // returns Promise<InitResponse>

if (response.success) {
  const link    = response.redirectUrl;  // redirect the browser here
  const pollUrl = response.pollUrl;      // PERSIST THIS
  // await orders.attachPollUrl("INV-35", pollUrl);
} else {
  console.error(response.error);
}
```

Promise style, if you prefer:

```js
paynow.send(payment).then((response) => {
  if (response.success) {
    const link = response.redirectUrl;
  }
});
```

### 4.6 Mobile money (Express Checkout) transaction

> Currently: **EcoCash works with Econet numbers, OneMoney with NetOne numbers.**

```js
const payment = paynow.createPayment("INV-37", "customer@example.com");
payment.add("Bananas", 2.5);
payment.add("Apples", 1.0);

paynow
  .sendMobile(payment, "0777000000", "ecocash")
  .then((response) => {
    if (response.success) {
      const instructions = response.instructions; // show to the customer
      const pollUrl      = response.pollUrl;      // persist
      console.log(instructions);
    } else {
      console.log(response.error);
    }
  })
  .catch((ex) => {
    console.error("Paynow request failed", ex);
  });
```

### 4.7 Polling for status

```js
const PAID = new Set(["Paid", "Awaiting Delivery", "Delivered"]);

const r = await paynow.pollTransaction(pollUrl);

if (PAID.has(r.status)) {
  // fulfil the order
} else {
  console.log("Not paid yet:", r.status);
}
```

> ### ⚠️ Two separate defects in the published Node example
>
> The docs show `let status = paynow.pollTransaction(pollUrl); if (status.paid()) {...}`.
> **Both halves are wrong.**
>
> 1. **It must be awaited.** `pollTransaction` performs network I/O and returns a
>    promise. Without `await`, `status` is a `Promise` and every member is undefined.
> 2. **There is no `paid()` method.** The shipped `StatusResponse` exposes `reference`,
>    `amount`, `paynowReference`, `pollUrl`, `status` and `error` as plain **properties**
>    — `paid` appears nowhere in the package. Calling it throws
>    `TypeError: status.paid is not a function`. Compare `r.status` against the paid
>    status words yourself, as above.
>
> Note too that `pollTransaction()` resolves an **`InitResponse`**, not a
> `StatusResponse` — internally it returns `this.parse(response.data)`. `status`,
> `pollUrl` and `error` are populated; `reference`, `amount` and `paynowReference` are
> **not**. Key poll results off your own stored reference, never off the response.

### 4.8 Response object cheat-sheet (Node.js)

These are **properties**, not methods (unlike PHP) — *all* of them, with no exceptions:

| Member | Type | Notes |
|---|---|---|
| `response.success` | `boolean` | initiation accepted |
| `response.redirectUrl` | `string` | web transactions only |
| `response.pollUrl` | `string` | both web and mobile |
| `response.instructions` | `string` | mobile transactions only |
| `response.error` | `string` | present when `success === false` |
| `status.status` | `string` | raw Paynow status word — compare against the §5.6 values |

> ⚠️ **There is no `status.paid()`.** The published docs show one; the package does not
> ship one, and calling it throws. Use
> `["Paid", "Awaiting Delivery", "Delivered"].includes(status.status)`.

### 4.9 Complete Node.js example

```js
const { Paynow } = require("paynow");

const paynow = new Paynow(
  process.env.PAYNOW_INTEGRATION_ID,
  process.env.PAYNOW_INTEGRATION_KEY
);

paynow.resultUrl = "https://example.com/paynow/callback";
paynow.returnUrl = "https://example.com/paynow/return?merchantReference=INV-35";

const payment = paynow.createPayment("INV-35");
payment.add("Bananas", 2.5);
payment.add("Apples", 3.4);

paynow.send(payment).then((response) => {
  if (response.success) {
    const link    = response.redirectUrl;
    const pollUrl = response.pollUrl;   // save this (recommended)
  }
});
```

---

## 5. API Reference (raw HTTP)

Use this when no SDK exists for your stack, when you need Express Checkout methods the
SDKs don't wrap (InnBucks, O'mari, Zimswitch, card tokens), or when debugging.

> Paynow publishes **five** official SDKs: PHP, Node.JS, C#/.NET, Python and Java. This
> document covers PHP and Node.js in depth — if you are on .NET, Python or Java, check
> the hub's quickstart for your language before hand-rolling against raw HTTP.

### 5.0 Transport rules

- All merchant→Paynow calls are **HTTP POST**.
- Body must be **URL-encoded**, header `Content-Type: application/x-www-form-urlencoded`.
  Example: `id=123&reference=ABC123&amount=1.23&...`
- Responses are URL-encoded key/value strings, **not JSON**.
- Security material (hashes, integration keys) must **never** appear in client-visible
  pages or URLs. Store the integration key encrypted or outside the main app database.

### 5.1 Endpoints

| Purpose | Method | URL |
|---|---|---|
| Initiate web transaction | POST | `https://www.paynow.co.zw/interface/initiatetransaction` |
| Initiate Express Checkout / mobile money | POST | `https://www.paynow.co.zw/interface/remotetransaction` |
| Initiate passenger (air) ticket transaction | POST | `https://www.paynow.co.zw/interface/initiatetickettransaction` |
| Poll transaction status | POST (empty body) | the `pollurl` returned to you |
| Trace by merchant reference | POST | `https://www.paynow.co.zw/interface/trace` |
| Submit O'mari OTP | POST | the `remoteotpurl` returned to you |

### 5.2 Initiate a transaction

`POST https://www.paynow.co.zw/interface/initiatetransaction`

**Request fields**

| Field | Type | Req. | Description |
|---|---|:--:|---|
| `id` | Integer | ✅ | Your Integration ID. |
| `reference` | String | ✅ | Your unique transaction reference. |
| `amount` | Decimal | ✅ | Final amount, two decimal places, **no currency symbol**. |
| `additionalinfo` | String | ➖ | Extra text shown to the customer on Paynow. Never put confidential data here. |
| `returnurl` | String | ✅ | Where the browser is sent after processing. Include enough info to identify the transaction. |
| `resulturl` | String | ✅ | Where Paynow POSTs status updates. Include enough info to identify the transaction. |
| `authemail` | String | ➖ | Auto-logs the customer in (anonymously, or prompts login if registered). **Required for Express Checkout.** |
| `authphone` | String | ➖ | Pre-fills the customer's mobile number for the session. |
| `authname` | String | ➖ | Pre-fills the customer's name for the session. |
| `tokenize` | Boolean | ➖ | If `true` and the customer pays by Visa/Mastercard/Zimswitch, a reusable card token is returned in the status update. Requires approval — contact `support@paynow.co.zw`. |
| `merchanttrace` | String | ➖ | Unique per merchant, ≤ 32 chars. Lets you trace a transaction after a timeout/network error. |
| `status` | String | ✅ | Literal `Message` at this stage. |
| `hash` | String | ✅ | See [§6](#6-hashing-generate--validate). |

> The **Req.** column is this document's reading, not Paynow's schema — the official
> table has no required/optional column and only flags certain fields as "(optional)" in
> prose. Treat ➖ as "documented as optional", not as a guarantee.

**Success response**

| Field | Description |
|---|---|
| `status` | `Ok` |
| `browserurl` | Redirect the customer's browser here. |
| `pollurl` | Poll here for current status. |
| `hash` | Verify before doing anything else. |

> ⚠️ **The response carries fields beyond these four.** `paynowreference` is commonly
> present — the §6.3 worked example is an initiate response containing it — and it **is**
> part of the digest. Never hash a fixed field list: **hash every value in the response,
> in arrival order.** The helpers in §6.4/§6.5 already do this; the table above simply
> doesn't say so, which is how implementations end up with phantom hash mismatches.

```
Status=Ok&BrowserUrl=http%3a%2f%2fwww.paynow.co.zw%3a7106%2fPayment%2fConfirmPayment%2f1169&PollUrl=http%3a%2f%2fwww.paynow.co.zw%3a7106%2fInterface%2fCheckPayment%2f%3fguid%3d3cb27f4b-b3ef-4d1f-9178-5e5e62a43995&Hash=8614C21D...
```

> ⚠️ **Verify the hash before redirecting the customer to `browserurl`.**

**Error response**

| Field | Description |
|---|---|
| `status` | `Error` |
| `error` | Failure detail |

```
Status=Error&Error=Invalid+amount+field
```

### 5.3 Initiate a mobile money transaction

`POST https://www.paynow.co.zw/interface/remotetransaction`

Same fields as §5.2, **plus**:

| Field | Type | Description |
|---|---|---|
| `phone` | String | Mobile wallet subscriber number to debit. |
| `method` | String | `ecocash` or `onemoney`. |

A USSD session is pushed to the subscriber's handset asking for their wallet PIN to
authorise (or cancel) the transaction.

> The Integration ID must have EcoCash and/or OneMoney enabled in the Paynow setup area,
> otherwise initiation fails with an error describing exactly that.

### 5.4 Express Checkout transactions

`POST https://www.paynow.co.zw/interface/remotetransaction`

Express Checkout captures the payment method inside your own application and completes
payment **without redirecting** the customer to Paynow.

Supported methods: **Visa/Mastercard (tokenised)**, **Zimswitch (tokenised)**,
**EcoCash**, **OneMoney**, **InnBucks**, **O'mari**.

Fields in addition to §5.2:

| Field | Required for | Description |
|---|---|---|
| `method` | all | One of `zimswitch`, `vmc`, `ecocash`, `onemoney`, `innbucks`, `omari`. |
| `phone` | mobile money | Wallet subscriber number to debit. |
| `token` | vmc / zimswitch | Token returned by a previous tokenised transaction; enables recurring billing with no cardholder input. |
| `merchanttrace` | vmc / zimswitch | **Unique per request** — prevents duplicate debits on timeout/network interruption. |

Remember `authemail` is required for Express Checkout.

#### InnBucks

The response carries two extra values:

- `authorizationcode` — display to the customer.
- `authorizationexpires` — expiry, format `d-MMM-yyyy HH:mm`. Display to the customer.

Render the authorization code as a QR code for the InnBucks app to scan, and offer a
deep link.

##### ⚠️ Two conflicting deep-link schemes

The developer hub and the shipped `paynow` npm package disagree about the URI scheme.
**Use the SDK's scheme as primary** — it is what the current package actually builds —
and fall back to the documented scheme if the primary fails to open the app:

```
# PRIMARY  — paynow npm v2.2.2, src/constants.ts (INNBUCKS_DEEPLINK_PREFIX)
schinn.wbpycode://innbucks.co.zw?pymInnCode=<authorizationcode>

# FALLBACK — developers.paynow.co.zw, Express Checkout page
com.innbucks.customer://purchase?paymentToken=<authorizationcode>
```

Better still, on the Node SDK read the link Paynow itself returns rather than building
either string by hand:

```js
const deepLink = response.innbucks_info?.[0]?.deep_link_url;
```

> This conflict is unresolved upstream — confirm the current scheme with
> `support@paynow.co.zw` before shipping. Keep the **QR code as the primary path** in
> your UI either way: it works regardless of which URI scheme the installed app
> registers, and costs the customer one scan instead of a dead link.

#### O'mari

Initiating an O'mari payment sends an OTP by SMS to the customer's MSISDN. The response
carries:

- `otpreference` — display to the customer.
- `remoteotpurl` — where you POST the OTP once the customer enters it.

**Completing the O'mari transaction:** `POST <remoteotpurl>` with:

| Field | Description |
|---|---|
| `id` | Integration ID |
| `otp` | OTP the customer received by SMS |
| `status` | `Message` |
| `hash` | Generated as in §6 |

```
id=12345&otp=012345&status=Message&hash=8614C21D...
```

- Success → a normal Status Update payload (§5.6).
- Failure → `status=Error&error=Invalid+OTP`
- After **5 failed OTP attempts** the transaction is cancelled and must be re-initiated.

#### Card tokens (continued)

Token transactions are automatically **re-tokenised** during payment, and the *new* token
is returned in the status update callback. Always overwrite your stored token with the
newest one after each successful charge, otherwise it will eventually stop working.

Tokens are valid for **up to six months** from issue, but never beyond the underlying
card's own expiry. For example, a token issued on 3 March 2019 for a card expiring end of
April 2019 has a token expiry of **30 April 2019**, not 3 September 2019.

> Tokenisation is a permissioned feature. Apply via `support@paynow.co.zw`.

---

### 5.5 Initiate a passenger (air) ticket transaction

`POST https://www.paynow.co.zw/interface/initiatetickettransaction`

Used by airlines/travel agents so that airline-specific data travels with the payment
(needed for card scheme airline addendum data and fraud scoring).

| Field | Type | Description |
|---|---|---|
| `id` | Integer | Integration ID. |
| `reference` | String | Your unique transaction reference. |
| `amount` | Decimal | Final amount **in USD**, two decimal places, no currency symbol. |
| `primaryticketnumber` | String | Ticket / reservation number. |
| `passengerfirstname` | String | Passenger first name. |
| `passengerlastname` | String | Passenger last name. |
| `passengerid` | String | Passenger identifier — e.g. frequent flyer number. |
| `passengerstatus` | String | Your own classification, e.g. `standard`, `gold`, `platinum`. |
| `passengertype` | String | Fare classification — see table below. |
| `firstdeparturelocationcode` | String | IATA code of the departure airport, e.g. `JNB`. |
| `firstarrivallocationcode` | String | IATA code of the arrival airport. |
| `pnrnumber` | String | PNR (Passenger Name Record) identifier in the reservation system. |
| `officeiatanumber` | String | Issuing office IATA number. |
| `ordernumber` | String | Order number. |
| `placeofissue` | String | Ticket office location. |
| `departuredate` | Numeric | `yyyymmdd` of the initial leg. |
| `departuretime` | String | `HH:mm "GMT"zzz`, e.g. `19:55 GMT+02:00`. |
| `arrivaldate` | Numeric | `yyyymmdd` of the final leg. |
| `arrivaltime` | String | `HH:mm "GMT"zzz`, e.g. `23:10 GMT+02:00`. |
| `journeytype` | String | `one way` or `round trip`. |
| `completeroute` | String | Legs concatenated: `ORIG1-DEST1[:ORIG2-DEST2…]`, e.g. `CPT-JNB:JNB-NBO`. |
| `additionalinfo` | String (optional) | Extra text shown to the customer. No confidential data. |
| `returnurl` | String | Browser return URL. |
| `resulturl` | String | Server callback URL. |
| `authemail` | String (optional) | Auto-login email. |
| `status` | String | `Message`. |
| `hash` | String | See §6. |

**Passenger types**

| Code | Meaning |
|---|---|
| `ADT` | Adult |
| `CNN` | Child |
| `INF` | Infant |
| `YTH` | Youth |
| `STU` | Student |
| `SCR` | Senior Citizen |
| `MIL` | Military |

Status updates behave exactly as in §5.6. Ticket transactions also return the payment
instrument detail fields.

---

### 5.6 Status Update (the `resulturl` callback)

Whenever a transaction's status changes, Paynow sends an **HTTP POST to your `resulturl`**.

**Core fields**

| Field | Type | Description |
|---|---|---|
| `reference` | String | Your merchant reference. |
| `amount` | Decimal | Final amount, two decimal places. |
| `paynowreference` | String | Paynow's own reference for the transaction. |
| `pollurl` | String | URL to poll for the current status. |
| `status` | String | One of the status words below. |
| `hash` | String | Verify this — see §6. |

**Tokenisation fields** (only if your merchant account is permitted to tokenise):

| Field | Description |
|---|---|
| `token` | Reusable payment instrument token for recurring payments. |
| `tokenexpiry` | Token expiry, format `D-MMM-YYYY`, e.g. `31-Dec-2027`. |

**Payment instrument fields** (only if enabled for your account, or on ticket transactions).
All are returned **only for successful payments**:

| Field | Description |
|---|---|
| `paymentchannel` | Channel name, e.g. `Visa`, `Mastercard`, `Ecocash`. |
| `paymentinstrument` | Masked card number, wallet MSISDN, etc. |
| `paymentinstrumentname` | Cardholder name. |
| `paymentinstrumentnationality` | `Domestic` or `Foreign`. |
| `paymentchannelreference` | Approval transaction code. |
| `paymentchanneleci` | Electronic Commerce Indicator. |
| `paymentfraudscore` | Fraud score. |
| `paymentfrauddecision` | `Issue`, `Request Manual Review`, or `Reject`. |

**Example payload**

```
reference=ABC123&paynowreference=123456&amount=1.00&status=Awaiting+Delivery&pollurl=https%3A%2F%2Fwww.paynow.co.zw%2FInterface%2FCheckPayment%2F%3Fguid%3D9f24be04-f4a6-4dff-8ab5-455263ba7b6b&hash=785659BF...
```

#### Status values

**Paid / settling states**

| Status | Meaning |
|---|---|
| `Paid` | Paid successfully; funds reach you at the next settlement. |
| `Awaiting Delivery` | Paid successfully, but held in suspense until you confirm delivery of goods. |
| `Delivered` | Delivery acknowledged; funds still in suspense during the 24-hour confirmation window. |

**Other states** (sent if they change, or returned when you poll)

| Status | Meaning |
|---|---|
| `Created` | Created in Paynow, not yet paid. |
| `Sent` | Created and passed to an upstream system; customer referred but hasn't paid. |
| `Cancelled` | Cancelled — cannot be resumed, must be recreated. |
| `Disputed` | Disputed by the customer; funds held pending resolution. |
| `Refunded` | Funds returned to the customer. |

> **Treat `Paid`, `Awaiting Delivery` and `Delivered` as "money is good".**
>
> ⚠️ **You must do this yourself — the SDK `paid()` helpers do NOT.** The PHP SDK's
> `paid()` is `return $this->status() === 'paid';`, so it is false for `Awaiting
> Delivery` and `Delivered`. The Node SDK has no `paid()` at all. Compare the status word
> against the three-value set in your own code — see
> [§3.7](#37-checking-transaction-status-polling) and [§4.7](#47-polling-for-status).

#### Retry behaviour

You aren't required to reply with anything specific, **but** if your endpoint returns an
HTTP error status code Paynow retries the status update **up to ten times** before giving
up. So:

- Return `200 OK` quickly (do heavy work asynchronously).
- Make your handler **idempotent** — the same update can legitimately arrive many times.

> ⚠️ **On every status update, validate the hash.** And when you receive an important
> update (e.g. "paid"), it is recommended you additionally poll Paynow to confirm the
> status matches.

---

### 5.7 Polling for a status update

Poll by making an **empty HTTP POST** to the `pollurl` you were given at initiation or in
a status update. The reply has the same shape as a status update message (§5.6).

```
reference=ABC123&paynowreference=123456&amount=1.00&status=Awaiting+Delivery&pollurl=https%3A%2F%2F...&hash=785659BF...
```

Paynow asks that you poll only in these two scenarios:

1. You received an important status update and want to confirm it.
2. You are about to delete old/unpaid transactions and want to confirm status first.

In practice you will also need to poll while waiting on a mobile-money USSD
authorisation. Do it on a **sensible backoff** (see §10.5), not in a tight loop.

---

### 5.8 Trace (recovering from a timeout)

If you sent an Express Checkout request and never got the response — network interruption,
timeout, crash — you have no `pollurl`. That's what `merchanttrace` is for: supply a
unique value (≤ 32 chars, unique per merchant) with every Express Checkout request, then
you can look the transaction up afterwards.

`POST https://www.paynow.co.zw/interface/trace`

| Field | Description |
|---|---|
| `id` | Integration ID. |
| `merchanttrace` | The exact value you sent when initiating. |
| `status` | `Message`. |
| `hash` | See §6. |

**Outcomes**

- **Found** → a standard Status Update message showing current status.
- **Not found** →
```
  status=NotFound&hash=2D72F08C...
```
- **Error** →
```
  status=Error&error=Trace+failed
```
  ⚠️ A trace *error* does **not** mean the transaction doesn't exist. Retry before
  assuming the payment never happened — never auto-refund or re-charge off a trace error.

---

## 6. Hashing: Generate & Validate

Every message to and from Paynow carries a `hash`, and **every message must be verified**.

### 6.1 The algorithm

1. Concatenate the **values** of every field in the message, in order, **excluding** the
   `hash` field itself. Use the **raw** values:
   - From a result string → **URL-decode first**.
   - From a form POST → your framework has already decoded them.
   - When *generating* an outbound hash → use the raw values, do **not** URL-encode them
     before joining (you URL-encode only when building the request body).
2. Append your **Integration Key**, **lower-cased**, to the end of the string.
3. UTF-8 encode the string. (In PHP this is usually already the case.)
4. **SHA-512** the string and output as **UPPERCASE hexadecimal**.

> ⚠️ **Lower-case the integration key.** Both official SDKs do it — `paynow/php-sdk`
> in its constructor (`$this->integrationKey = strtolower($key)`) and again in
> `initiateTransaction()`, and npm `paynow` inside `generateHash()`
> (`string += integrationKey.toLowerCase()`). Every key Paynow publishes is already
> lower-case, which is precisely why this is easy to miss: skip it and your helper
> reproduces all the documented fixtures, then fails the day a merchant's key arrives
> upper-cased. Verified against both packages, 20 Sep 2026.

### 6.2 Worked example — outbound

Integration key: `3e9fed89-60e1-4ce5-ab6e-6b1eb2d4f977`

Message:

```
id=1201
reference=TEST REF
amount=99.99
additionalinfo=A test ticket transaction
returnurl=http://www.google.com/search?q=returnurl
resulturl=http://www.google.com/search?q=resulturl
status=Message
```

Step 1 — join the values:

```
1201TEST REF99.99A test ticket transactionhttp://www.google.com/search?q=returnurlhttp://www.google.com/search?q=resulturlMessage
```

Step 2 — append the integration key:

```
1201TEST REF99.99A test ticket transactionhttp://www.google.com/search?q=returnurlhttp://www.google.com/search?q=resulturlMessage3e9fed89-60e1-4ce5-ab6e-6b1eb2d4f977
```

Step 3 — SHA-512, uppercase hex:

```
2A033FC38798D913D42ECB786B9B19645ADEDBDE788862032F1BD82CF3B92DEF84F316385D5B40DBB35F1A4FD7D5BFE73835174136463CDD48C9366B0749C689
```

Step 4 — append `hash=2A033FC3…` to your outbound message.

Use this exact fixture as a **unit test** for your hashing helper.

### 6.3 Worked example — inbound validation

Given this response:

```
status=Ok&browserurl=https%3a%2f%2fstaging.paynow.co.zw%2fPayment%2fConfirmPayment%2f9510&pollurl=https%3a%2f%2fstaging.paynow.co.zw%2fInterface%2fCheckPayment%2f%3fguid%3dc7ed41da-0159-46da-b428-69549f770413&paynowreference=9510&hash=750DD0B0DF374678707BB5AF915AF81C228B9058AD57BB7120569EC68BBB9C2EFC1B26C6375D2BC562AC909B3CD6B2AF1D42E1A5E479FFAC8F4FB3FDCE71DF4D
```

1. Split on `&` into key/value pairs.
2. Split each pair on the first `=`.
3. Join every value **except** `hash`, **URL-decoding each one first**:

```
Okhttps://staging.paynow.co.zw/Payment/ConfirmPayment/9510https://staging.paynow.co.zw/Interface/CheckPayment/?guid=c7ed41da-0159-46da-b428-69549f7704139510
```

4. Append the integration key.
5. SHA-512 → uppercase hex:

```
750DD0B0DF374678707BB5AF915AF81C228B9058AD57BB7120569EC68BBB9C2EFC1B26C6375D2BC562AC909B3CD6B2AF1D42E1A5E479FFAC8F4FB3FDCE71DF4D
```

6. Compare with the `hash` in the message. Match → authentic. Mismatch → **reject**.

### 6.4 PHP implementation

```php
<?php

final class PaynowHash
{
    public function __construct(private string $integrationKey)
    {
        $this->integrationKey = strtolower($integrationKey);   // as both SDKs do
    }

    /**
     * Build the uppercase SHA-512 hash for a set of fields.
     * $values must already be in the correct order, with 'hash' absent or ignored.
     */
    public function generate(array $values): string
    {
        $concat = '';
        foreach ($values as $key => $value) {
            if (strtoupper((string) $key) === 'HASH') {
                continue;
            }
            $concat .= $value;
        }
        $concat .= $this->integrationKey;

        return strtoupper(hash('sha512', $concat));
    }

    /**
     * Verify an inbound message. $values should be the already-URL-decoded
     * key => value pairs, in the order they arrived.
     */
    public function verify(array $values): bool
    {
        $received = null;
        foreach ($values as $key => $value) {
            if (strtoupper((string) $key) === 'HASH') {
                $received = $value;
            }
        }
        if ($received === null) {
            return false;
        }

        // Timing-safe comparison
        return hash_equals($this->generate($values), strtoupper($received));
    }

    /**
     * Parse a Paynow response body ("a=1&b=2") into an ORDERED, URL-decoded array.
     * Do NOT use parse_str() — it mangles keys and loses ordering guarantees.
     */
    public static function parseResponse(string $body): array
    {
        $out = [];
        foreach (explode('&', trim($body)) as $pair) {
            if ($pair === '') {
                continue;
            }
            $parts = explode('=', $pair, 2);
            $key   = urldecode($parts[0]);
            $out[$key] = isset($parts[1]) ? urldecode($parts[1]) : '';
        }
        return $out;
    }
}
```

**Self-test:**

```php
$h = new PaynowHash('3e9fed89-60e1-4ce5-ab6e-6b1eb2d4f977');

$fields = [
    'id'             => '1201',
    'reference'      => 'TEST REF',
    'amount'         => '99.99',
    'additionalinfo' => 'A test ticket transaction',
    'returnurl'      => 'http://www.google.com/search?q=returnurl',
    'resulturl'      => 'http://www.google.com/search?q=resulturl',
    'status'         => 'Message',
];

assert($h->generate($fields) === '2A033FC38798D913D42ECB786B9B19645ADEDBDE788862032F1BD82CF3B92DEF84F316385D5B40DBB35F1A4FD7D5BFE73835174136463CDD48C9366B0749C689');
```

### 6.5 Node.js implementation

```js
const crypto = require("crypto");

class PaynowHash {
  constructor(integrationKey) {
    this.integrationKey = String(integrationKey).toLowerCase();   // as both SDKs do
  }

  /** values: ordered object or Map, 'hash' excluded/ignored */
  generate(values) {
    const entries = values instanceof Map ? [...values] : Object.entries(values);
    const concat =
      entries
        .filter(([k]) => k.toUpperCase() !== "HASH")
        .map(([, v]) => String(v))
        .join("") + this.integrationKey;

    return crypto.createHash("sha512").update(concat, "utf8").digest("hex").toUpperCase();
  }

  /** values must be the already URL-decoded, in-order fields of an inbound message */
  verify(values) {
    const entries = values instanceof Map ? [...values] : Object.entries(values);
    const found = entries.find(([k]) => k.toUpperCase() === "HASH");
    if (!found) return false;

    const expected = Buffer.from(this.generate(values));
    const actual = Buffer.from(String(found[1]).toUpperCase());
    return expected.length === actual.length && crypto.timingSafeEqual(expected, actual);
  }

  /**
   * Parse "a=1&b=2" into an ORDERED Map of decoded values.
   * Using a Map preserves insertion order for all key shapes.
   */
  static parseResponse(body) {
    const map = new Map();
    for (const pair of String(body).trim().split("&")) {
      if (!pair) continue;
      const i = pair.indexOf("=");
      const k = decodeURIComponent((i === -1 ? pair : pair.slice(0, i)).replace(/\+/g, " "));
      const v = i === -1 ? "" : decodeURIComponent(pair.slice(i + 1).replace(/\+/g, " "));
      map.set(k, v);
    }
    return map;
  }
}

module.exports = { PaynowHash };
```

**Self-test:**

```js
const h = new PaynowHash("3e9fed89-60e1-4ce5-ab6e-6b1eb2d4f977");
const hash = h.generate({
  id: "1201",
  reference: "TEST REF",
  amount: "99.99",
  additionalinfo: "A test ticket transaction",
  returnurl: "http://www.google.com/search?q=returnurl",
  resulturl: "http://www.google.com/search?q=resulturl",
  status: "Message",
});
console.assert(
  hash ===
    "2A033FC38798D913D42ECB786B9B19645ADEDBDE788862032F1BD82CF3B92DEF84F316385D5B40DBB35F1A4FD7D5BFE73835174136463CDD48C9366B0749C689"
);
```

### 6.6 Hashing pitfalls

| Pitfall | Fix |
|---|---|
| Hashing **encoded** values on outbound messages | Join raw values; encode only when building the body. |
| Forgetting to **decode** inbound values before hashing | URL-decode each value first. |
| Field **order** changed by your HTTP client or `parse_str()` | Use an ordered structure (PHP ordered array, JS `Map`) and preserve arrival order. |
| Lowercase hex output | `strtoupper()` / `.toUpperCase()`. |
| `+` in a query string not decoded to a space | Replace `+` with space before `decodeURIComponent` (the Node helper above does this). |
| Including `hash` itself in the concatenation | Always exclude it. |
| Comparing hashes with `==` / `===` | Use `hash_equals` / `crypto.timingSafeEqual`. |
| Integration key hashed in the case it arrived | Lower-case it first — both SDKs do. Invisible on Paynow's own lower-case example keys. |

---

## 7. Links & Buttons

These are **no-code / low-code** integrations: you build a URL, put it behind a button or
email it. They need no server-side API calls. Their weakness is that the customer can
potentially tamper with the values, so **always verify the amount and reference after
payment**. If you need values the customer genuinely cannot change, use the API/SDK
integration in §3–§5 instead.

### 7.1 URL-safe Base64 encoding

Base64 output contains `+`, `=` and `/`, which are unsafe inside a URL. Paynow's link
formats therefore use **Base64-encode, then URL-encode**.

Order of operations, precisely:

1. URL-encode **each individual argument value**.
2. Join them into `key=value&key=value…`.
3. **Base64-encode** the whole argument string.
4. **URL-encode** the Base64 string.
5. Append as `?q=<result>`.

> ### ⚠️ Paynow's own worked examples do not follow this recipe
>
> The steps above match Paynow's canonical C# `GenerateLink`, and the helpers below
> implement them faithfully. But the literal example links published in §7.2 and §7.3
> were **not** generated this way, so you cannot reproduce them with this code:
>
> - The §7.2 Base64 decodes to `search=company@gmail.com&amount=12.50&reference=ABC123&l=1`
>   — the `@` is **not** encoded, so step 1 was skipped.
> - The §7.3 Base64 decodes to `id=1046&amount=75.50&f1=Red&f2= Pay+when%3F+Paynow%21&f3=32&l=1`
>   — note the **stray leading space** in `f2`, which is absent from the argument string
>   printed directly above it in the docs.
>
> Treat the published strings as illustrative only. Generate your links with the code
> below, and **test one against a live Paynow account** before shipping.

**PHP**

```php
function paynowEncodeArgs(array $args): string
{
    // http_build_query URL-encodes each value for us
    $query  = http_build_query($args, '', '&', PHP_QUERY_RFC1738);
    return urlencode(base64_encode($query));
}

function paynowSimpleLink(
    string $merchantEmail,
    float $amount,
    string $reference,
    bool $locked = true,
    ?string $customerEmail = null
): string {
    $q = paynowEncodeArgs([
        'search'    => $merchantEmail,
        'amount'    => number_format($amount, 2, '.', ''),
        'reference' => $reference,
        'l'         => $locked ? 1 : 0,
    ]);

    return sprintf(
        'https://www.paynow.co.zw/payment/link/%s?q=%s',
        rawurlencode($customerEmail ?? ''),
        $q
    );
}
```

**Node.js**

```js
function paynowEncodeArgs(args) {
  const query = new URLSearchParams(args).toString(); // encodes each value
  return encodeURIComponent(Buffer.from(query, "utf8").toString("base64"));
}

function paynowSimpleLink({ merchantEmail, amount, reference, locked = true, customerEmail = "" }) {
  const q = paynowEncodeArgs({
    search: merchantEmail,
    amount: Number(amount).toFixed(2),
    reference,
    l: locked ? 1 : 0,
  });
  return `https://www.paynow.co.zw/payment/link/${encodeURIComponent(customerEmail)}?q=${q}`;
}
```

> **Note on the path segment:** `rawurlencode()` / `encodeURIComponent()` renders
> `customer@gmail.com` as `customer%40gmail.com`, whereas Paynow's examples put the raw
> address in the path. Both resolve; drop the encode on that segment only if you want
> links that match the published form byte-for-byte.

Paynow also points at free online tools if you just need a one-off link:
Base64 <http://www.freeformatter.com/base64-encoder.html> ·
URL encode <http://www.freeformatter.com/url-encoder.html>

### 7.2 Simple Payment Request Button

Lets you email or embed a request for money from anyone with an email address, and get
notified when they pay.

**URL format**

```
https://www.paynow.co.zw/payment/link/{customer-email}?q={arguments}
```

`{customer-email}` is **optional**. If supplied, Paynow anonymously logs that address in
(or shows a login page if the address already has a Paynow account).

**Arguments** (joined with `&`, then Base64 + URL encoded)

| Name | Key | Type | Description | Default | Example |
|---|---|---|---|---|---|
| Merchant Email | `search` | Text | Paynow email of the merchant receiving payment | n/a | `company@gmail.com` |
| Payment Amount | `amount` | Numeric | Amount the customer pays | `0.00` | `23.65` |
| Payment Reference | `reference` | Text | Your payment reference | *(blank)* | `INV-12345` |
| Locked | `l` | `1` or `0` | Whether amount and reference are read-only for the customer | `0` | `1` |

If `l` is omitted or `0`, the customer can edit the amount and reference — useful for
donations or open-ended amounts.

**Worked example**

| Item | Value |
|---|---|
| Merchant e-mail | `company@gmail.com` |
| Amount | `12.50` |
| Reference | `ABC123` |
| Locked | `1` |

URL-encode each value → `company%40gmail.com`, `12.50`, `ABC123`, `1`

Join:

```
search=company%40gmail.com&amount=12.50&reference=ABC123&l=1
```

Base64 — **as published by Paynow.** Note this decodes to an *un*-encoded `@`
(`search=company@gmail.com&...`), so it is not what the §7.1 recipe produces:

```
c2VhcmNoPWNvbXBhbnlAZ21haWwuY29tJmFtb3VudD0xMi41MCZyZWZlcmVuY2U9QUJDMTIzJmw9MQ==
```

Following §7.1 exactly, you would instead get:

```
c2VhcmNoPWNvbXBhbnklNDBnbWFpbC5jb20mYW1vdW50PTEyLjUwJnJlZmVyZW5jZT1BQkMxMjMmbD0x
```

URL-encode:

```
c2VhcmNoPWNvbXBhbnlAZ21haWwuY29tJmFtb3VudD0xMi41MCZyZWZlcmVuY2U9QUJDMTIzJmw9MQ%3D%3D
```

Final link:

```
https://www.paynow.co.zw/payment/link/customer@gmail.com?q=c2VhcmNoPWNvbXBhbnlAZ21haWwuY29tJmFtb3VudD0xMi41MCZyZWZlcmVuY2U9QUJDMTIzJmw9MQ%3D%3D
```

### 7.3 Advanced Payment Request Button

Lets the customer supply extra details (colour, size, quantity, a caption…). Requires you
to first create a **Custom Button Template** in the merchant's Paynow account and note its
**Integration ID**.

**URL format**

```
https://www.paynow.co.zw/payment/billpaymentlink/{customer-email}?q={arguments}
```

**Arguments**

| Name | Key | Type | Description | Default | Example |
|---|---|---|---|---|---|
| ID | `id` | Numeric | Integration ID of the custom button template | n/a | `1046` |
| Payment Amount | `amount` | Numeric | Amount (unit price if "Use Quantity" is ticked) | `0.00` | `25.00` |
| Quantity | `quantity` | Numeric | Quantity — ignored unless "Use Quantity" is ticked | `1.00` | `2.36` |
| Locked | `l` | `1` or `0` | Whether the input fields are read-only | `0` | `1` |
| Extra fields | `f1`, `f2`, `f3`… | Text | Your template's extra fields, **in the order they appear in the template** | *(blank)* | see below |

**Worked example** — a template (ID `1046`) with three extra fields: Item Colour (select),
Caption (text), Size (text+numeric).

| Item | Value |
|---|---|
| Amount | `75.50` |
| `f1` | `Red` |
| `f2` | `Pay when? Paynow!` |
| `f3` | `32` |
| Locked | `1` |

Arguments:

```
id=1046&amount=75.50&f1=Red&f2=Pay+when%3F+Paynow%21&f3=32&l=1
```

Base64 + URL encode, then — **as published by Paynow**:

```
https://www.paynow.co.zw/payment/billpaymentlink/customer@gmail.com?q=aWQ9MTA0NiZhbW91bnQ9NzUuNTAmZjE9UmVkJmYyPSBQYXkrd2hlbiUzRitQYXlub3clMjEmZjM9MzImbD0x
```

> ⚠️ That Base64 decodes to
> `id=1046&amount=75.50&f1=Red&f2= Pay+when%3F+Paynow%21&f3=32&l=1` — with a **stray
> space** before `Pay` that does not appear in the argument string above it. Paynow's
> published example is malformed; build your own with the §7.1 helpers.

### 7.4 Notification, Success & Cancel URLs (continued)

| URL | What happens |
|---|---|
| **Notification URL** | Paynow sends a **form POST** carrying transaction data (server-to-server). |
| **Success URL** | The customer's browser is redirected here on success — **no extra data is passed**. |
| **Cancel URL** | The customer's browser is redirected here on cancellation — **no extra data is passed**. |

Because success/cancel carry no data, **all of your business logic must hang off the
Notification URL POST**, exactly as `resulturl` works in the API integration.

#### POST data sent to the Notification URL

| Field | Type | Description | Example |
|---|---|---|---|
| `Paynow_Reference` | Text | Paynow's transaction reference | `40222` |
| `Customer_Name` | Text | Customer name | `John Smith` |
| `Customer_Email` | Text | Customer email | `customer@gmail.com` |
| `Customer_Phone` | Text | Customer phone | `0733123456` |
| `Transaction_Amount` | Numeric | The transaction amount | `25.00` |
| `Amount_Paid` | Numeric | Amount actually debited from the customer | `26.30` |
| `Hash` | Text | SHA-512 hash of the posted data | `81D4957A0EB1…` |
| *(extra fields)* | Text | Any extra fields defined on your custom button template | see below |

> Note `Transaction_Amount` and `Amount_Paid` can differ — the debit includes fees when
> the customer (rather than the merchant) absorbs them. **Reconcile against
> `Transaction_Amount`.**

Extra template fields are posted with their own key and value. **Spaces in field names
become underscores**:

| Field | Value |
|---|---|
| `Item_Colour` | `Red` |
| `Caption` | `Pay when? Pay now!` |
| `Size` | `32` |

#### ⚠️ Verifying this hash is DIFFERENT from the API hash

For notification-URL posts you concatenate **key + value**, not just values:

1. Concatenate **the key plus the value**, with no space or separator, **in the same order
   they appear in the post**, **excluding the `Hash` field itself**.
2. Append the **Integration Key** (found by clicking *edit* on the template in Paynow).
3. UTF-8 encode the string.
4. SHA-512 → **uppercase hexadecimal**.

> **Interpretation note:** Paynow's wording is only *"concatenate the key plus the value
> with no space or separator in the same order they appear in the post"* — it never says
> to skip `Hash`. Excluding it is the working interpretation, and matches the API-hash
> convention; the code below does so.

If the result doesn't match the posted `Hash`, **do not accept the notification** — the
data may have been spoofed by a third party.

**PHP**

```php
<?php
/**
 * Verify a Paynow Custom Button Template notification POST.
 * $post must preserve the original field order (PHP's $_POST does).
 */
function verifyPaynowNotification(array $post, string $integrationKey): bool
{
    $concat   = '';
    $received = null;

    foreach ($post as $key => $value) {
        if (strcasecmp($key, 'Hash') === 0) {
            $received = $value;
            continue;               // Hash itself is not part of the digest
        }
        $concat .= $key . $value;   // NOTE: key + value, unlike the API hash
    }

    if ($received === null) {
        return false;
    }

    $expected = strtoupper(hash('sha512', $concat . strtolower($integrationKey)));

    return hash_equals($expected, strtoupper($received));
}
```

**Node.js (Express, `express.urlencoded`)**

```js
const crypto = require("crypto");

function verifyPaynowNotification(body, integrationKey) {
  let concat = "";
  let received = null;

  for (const [key, value] of Object.entries(body)) {
    if (key.toLowerCase() === "hash") {
      received = String(value);
      continue;
    }
    concat += key + String(value); // key + value
  }
  if (received === null) return false;

  const expected = crypto
    .createHash("sha512")
    .update(concat + String(integrationKey).toLowerCase(), "utf8")
    .digest("hex")
    .toUpperCase();

  const a = Buffer.from(expected);
  const b = Buffer.from(received.toUpperCase());
  return a.length === b.length && crypto.timingSafeEqual(a, b);
}
```

### 7.5 Artwork and buttons

Paynow publishes official branding assets so your checkout visually associates with the
Paynow brand:

- Formats: **`.AI`** (Adobe Illustrator) and **`.SVG`** (Scalable Vector Graphics).
- Use the SVGs directly in responsive web apps so they stay crisp at any resolution.
- **Badges:** dark-background and light-background variants.
- **Buttons:** *Add To Cart*, *Buy Now*, *Donate*, *Order*, *Buy Now*, *Pay Now*.

Download from <https://developers.paynow.co.zw/docs/paynow/artwork/>.

```html
<!-- Example usage -->
<a href="<?= htmlspecialchars($redirectUrl, ENT_QUOTES) ?>">
  <img src="/assets/paynow/paynow-buy-now.svg" alt="Pay with Paynow" height="44">
</a>
```

---

## 8. Test Mode

**Every new integration starts in test mode.** You can create, pay and cancel
transactions to exercise every branch of your code. No money moves, and you don't need
access to Visa/Mastercard/Vpayments/EcoCash/TeleCash/OneMoney to run a test.

### 8.1 The merchant-account rule (the #1 cause of "it won't let me pay")

> ⚠️ After creating a test transaction, **only the merchant account that created the
> integration can log in and fake a payment.** Any other user sees a message saying the
> merchant is in testing and cannot proceed.

Consequences for your code:

- If you send `authemail`, it **must** be a login email address of the merchant account
  being tested — otherwise you'll be locked out of completing your own test.
- The same applies to Express Checkout: the `authemail` supplied in test mode must match a
  merchant-account login email.

A practical pattern:

```php
$testing   = getenv('PAYNOW_TEST_MODE') === 'true';
$authEmail = $testing ? getenv('PAYNOW_MERCHANT_EMAIL') : $customer->email;

$payment = $paynow->createPayment($orderRef, $authEmail);
```

```js
const testing = process.env.PAYNOW_TEST_MODE === "true";
const authEmail = testing ? process.env.PAYNOW_MERCHANT_EMAIL : customer.email;
const payment = paynow.createPayment(orderRef, authEmail);
```

### 8.2 Completing a redirect (web) test payment

On the Paynow payment page, choose **[TESTING: Faked Success]** and click
**[Make Payment]**. Paynow then responds to your site exactly as if a real payment had
been made — including the `resulturl` status update.

### 8.3 Express Checkout — Mobile money (EcoCash, OneMoney) test numbers

Four pre-configured MSISDNs simulate the main outcomes. Use them as the `phone` value.

| Scenario | Number | Behaviour |
|---|---|---|
| **SUCCESS** | `0771111111` | `SUCCESS` status update **5 seconds** after initiation. |
| **DELAYED SUCCESS** | `0772222222` | `SUCCESS` status update **30 seconds** after initiation — simulates a slow user. |
| **USER CANCELLED** | `0773333333` | `FAILED` status update **30 seconds** after initiation. |
| **INSUFFICIENT BALANCE** | `0774444444` | Fails **immediately during initiation**, returning an "Insufficient balance" error. |

Note the distinction: `0774444444` fails at the *initiate* step (your
`success` / `success()` check catches it), while `0773333333` initiates fine and only
fails later via the status update. **Test both paths.**

### 8.4 Express Checkout — Visa/Mastercard (`method=vmc`) test tokens

Pass as `token=…` to `/interface/remotetransaction`, along with the other required fields.

| Scenario | Token |
|---|---|
| **SUCCESS** | `{11111111-1111-1111-1111-111111111111}` |
| **PENDING** | `{22222222-2222-2222-2222-222222222222}` |
| **CANCELLED** | `{33333333-3333-3333-3333-333333333333}` |
| **INSUFFICIENT BALANCE** | `{44444444-4444-4444-4444-444444444444}` |

Timings match the mobile-money table: success at 5s, pending→success at 30s,
cancelled→failed at 30s, insufficient balance fails immediately at initiation.

### 8.5 Express Checkout — Zimswitch (`method=zimswitch`) test tokens

| Scenario | Token |
|---|---|
| **SUCCESS** | `11111111111111111111111111111111` |
| **PENDING** | `22222222222222222222222222222222` |
| **CANCELLED** | `33333333333333333333333333333333` |
| **INSUFFICIENT BALANCE** | `44444444444444444444444444444444` |

Same behaviours and timings as above.

### 8.6 Going live

1. Exercise every path: success, delayed success, cancellation, insufficient balance,
   duplicate status updates, bad hash.
2. Go back to the **Integration Keys** section and click **[Request to be Set Live]**.
3. Paynow support verifies you have completed **at least one successful test
   transaction**, then flips you live.
4. Click **[Generate New Key]** at the same time so the development key is invalidated.
5. Once live, your selected payment methods start accepting real money.

### 8.7 Test matrix worth automating

| Case | How to trigger | Expected |
|---|---|---|
| Init rejected | Bad amount / wrong method for integration | `Status=Error`, `error` populated, nothing persisted |
| Hash mismatch on response | Flip one character of the key in a unit test | Request aborted, no redirect, alert raised |
| Mobile success | `0771111111` | Poll flips to paid ~5s |
| Mobile delayed | `0772222222` | Poll still pending at 10s, paid by ~35s |
| Mobile cancelled | `0773333333` | Terminal failure at ~30s, order not fulfilled |
| Mobile no funds | `0774444444` | Init fails immediately with "Insufficient balance" |
| Duplicate callback | Replay the same POST twice | Order fulfilled exactly once |
| Callback before redirect | Replay callback, then hit return URL | No double-fulfilment, return page shows correct state |
| Unknown reference in callback | Post a callback for a nonexistent ref | Logged and ignored, `200` returned |

---

## 9. Production Checklist & Gotchas

### 9.1 Security

- [ ] Integration Key lives in environment/secret storage — **never** in client-side code,
      URLs, query strings, logs, or the main site database in plaintext.
- [ ] Hash verified on **every** inbound message (init response, status update, poll
      result, trace result, notification POST). *(The PHP SDK already does this for you
      on `send()`, `sendMobile()` and `pollTransaction()` — see §3.10 — leaving only the
      `resulturl` callback to hand-roll.)*
- [ ] Hash computed over **every value in the response, in arrival order** — never a
      fixed field list. Responses carry undocumented fields such as `paynowreference`
      that are part of the digest.
- [ ] Hash comparison is **timing-safe** (`hash_equals` / `crypto.timingSafeEqual`).
- [ ] Initiation response hash verified **before** redirecting the customer to
      `browserurl`.
- [ ] `resulturl` and `returnurl` served over **HTTPS**.
- [ ] `additionalinfo` contains **no confidential data** — it is displayed to the customer.
- [ ] A new key generated when moving dev → production.

### 9.2 Correctness

- [ ] `reference` is unique per transaction.
- [ ] `amount` formatted to exactly two decimals, no currency symbol, no thousands
      separator (`number_format($n, 2, '.', '')` / `Number(n).toFixed(2)`).
- [ ] Amount in the callback **reconciled against your own record** — never trust the
      posted amount blindly, and never fulfil if it's short.
- [ ] `pollUrl` persisted against the order **before** redirecting or showing instructions.
- [ ] Callback handler is **idempotent** (unique constraint or status guard).
- [ ] Callback returns `200` fast; slow work is queued.
- [ ] `Paid`, `Awaiting Delivery` and `Delivered` all treated as money-received,
      **checked in your own code** — not delegated to `paid()` (PHP's matches only
      `Paid`; Node has none).
- [ ] Order fulfilment is driven by the callback/poll, **never** by the `returnurl` hit.
- [ ] `merchanttrace` supplied and stored for every Express Checkout request.
- [ ] Integration configured in Paynow with every payment method you call.

### 9.3 Language-specific gotchas

**PHP**

| Gotcha | Fix |
|---|---|
| Docs snippet omits the comma between `returnurl` and `resulturl` | Add the comma. |
| cURL extension missing | Enable `ext-curl`; the SDK requires it. |
| `parse_str()` mangles keys containing dots/spaces and can reorder | Use a manual splitter that preserves order (see §6.4). |
| Floats formatted with locale separators | Always `number_format($n, 2, '.', '')`. |
| Framework middleware (CSRF) blocking the callback route | Exempt the Paynow callback route from CSRF. |
| `send()` throwing instead of returning `success() === false` | Wrap every SDK call in `try/catch` — see §3.10. |
| Using `$status->paid()` as the fulfilment gate | It matches only `Paid`. Compare `status()` against the lower-cased paid set. |
| `errors()` treated as an array | It returns a space-joined **string** by default; `errors(false)` gives the array. |
| Examples here failing to parse on PHP 7.x | §6.4 and §10.1 use PHP 8.0+ syntax (promoted properties, named arguments). |

**Node.js**

| Gotcha | Fix |
|---|---|
| `pollTransaction` used synchronously as in the docs | `await` it. |
| Calling `status.paid()` as the docs show | It does not exist — `TypeError`. Compare `status.status` against `Paid` / `Awaiting Delivery` / `Delivered`. |
| Response members are **properties** (`response.success`), not methods | Don't call any of them. |
| `pollTransaction()` resolves an `InitResponse`, so `reference` / `amount` come back undefined | Key poll results off your own stored reference. |
| Body parser not configured for form posts | `app.use(express.urlencoded({ extended: false }))` on the callback route. |
| Unhandled promise rejection on network failure | Always `.catch(…)` / wrap in `try/catch`. |
| `returnUrl`/`resultUrl` set **after** `send()` | Set them before. |
| `+` not decoded to space when hand-parsing responses | Replace `+` before `decodeURIComponent`. |

### 9.4 Operational

- [ ] Log every request/response **with the hash and key redacted**.
- [ ] Alert on hash-verification failures — they indicate either a bug or an attack.
- [ ] Poll with backoff, and give a mobile-money transaction a hard timeout
      (≈ 3–5 minutes) before marking it abandoned.
- [ ] Keep a reconciliation job that polls any order still pending after N minutes.
- [ ] Handle the trace-error case without auto-refunding or re-charging.
- [ ] Never delete an unpaid transaction without polling Paynow first.

---

## 10. Copy-Paste Recipes

### 10.1 Raw PHP API client (no SDK)

```php
<?php

final class PaynowClient
{
    private const INITIATE = 'https://www.paynow.co.zw/interface/initiatetransaction';
    private const REMOTE   = 'https://www.paynow.co.zw/interface/remotetransaction';
    private const TRACE    = 'https://www.paynow.co.zw/interface/trace';

    private PaynowHash $hasher;

    public function __construct(
        private string $integrationId,
        private string $integrationKey,
    ) {
        $this->hasher = new PaynowHash($integrationKey);
    }

    /** Web/redirect transaction. Returns ['browserurl' => ..., 'pollurl' => ...] */
    public function initiate(
        string $reference,
        float $amount,
        string $returnUrl,
        string $resultUrl,
        ?string $authEmail = null,
        ?string $additionalInfo = null,
    ): array {
        // ORDER MATTERS for the hash
        $fields = ['id' => $this->integrationId, 'reference' => $reference,
                   'amount' => number_format($amount, 2, '.', '')];

        if ($additionalInfo !== null) $fields['additionalinfo'] = $additionalInfo;
        $fields['returnurl'] = $returnUrl;
        $fields['resulturl'] = $resultUrl;
        if ($authEmail !== null)      $fields['authemail'] = $authEmail;
        $fields['status'] = 'Message';
        $fields['hash']   = $this->hasher->generate($fields);

        return $this->post(self::INITIATE, $fields);
    }

    /** Express Checkout (mobile money / innbucks / omari / vmc / zimswitch). */
    public function remote(
        string $reference,
        float $amount,
        string $returnUrl,
        string $resultUrl,
        string $authEmail,
        string $method,
        string $merchantTrace,
        ?string $phone = null,
        ?string $token = null,
    ): array {
        $fields = ['id' => $this->integrationId, 'reference' => $reference,
                   'amount' => number_format($amount, 2, '.', ''),
                   'returnurl' => $returnUrl, 'resulturl' => $resultUrl,
                   'authemail' => $authEmail, 'method' => $method,
                   'merchanttrace' => $merchantTrace];

        if ($phone !== null) $fields['phone'] = $phone;
        if ($token !== null) $fields['token'] = $token;

        $fields['status'] = 'Message';
        $fields['hash']   = $this->hasher->generate($fields);

        return $this->post(self::REMOTE, $fields);
    }

    /** Empty POST to the poll URL. */
    public function poll(string $pollUrl): array
    {
        return $this->post($pollUrl, []);
    }

    /** Recover a transaction whose response you never received. */
    public function trace(string $merchantTrace): array
    {
        $fields = ['id' => $this->integrationId, 'merchanttrace' => $merchantTrace,
                   'status' => 'Message'];
        $fields['hash'] = $this->hasher->generate($fields);

        return $this->post(self::TRACE, $fields);
    }

    /** @return array<string,string> lower-cased keys, values already decoded */
    private function post(string $url, array $fields): array
    {
        $ch = curl_init($url);
        curl_setopt_array($ch, [
            CURLOPT_POST           => true,
            CURLOPT_POSTFIELDS     => http_build_query($fields, '', '&', PHP_QUERY_RFC1738),
            CURLOPT_HTTPHEADER     => ['Content-Type: application/x-www-form-urlencoded'],
            CURLOPT_RETURNTRANSFER => true,
            CURLOPT_TIMEOUT        => 30,
            CURLOPT_SSL_VERIFYPEER => true,
        ]);

        $body = curl_exec($ch);
        if ($body === false) {
            $err = curl_error($ch);
            curl_close($ch);
            throw new RuntimeException("Paynow request failed: {$err}");
        }
        curl_close($ch);

        $parsed = PaynowHash::parseResponse($body);

        // Normalise keys for lookup, but hash against the ORIGINAL ordered array.
        $lower = [];
        foreach ($parsed as $k => $v) {
            $lower[strtolower($k)] = $v;
        }

        if (($lower['status'] ?? '') === 'Error') {
            throw new RuntimeException('Paynow error: ' . ($lower['error'] ?? 'unknown'));
        }

        // NotFound responses from trace are hashed too
        if (! $this->hasher->verify($parsed)) {
            throw new RuntimeException('Paynow hash verification FAILED — response rejected.');
        }

        return $lower;
    }
}
```

**Usage**

```php
$client = new PaynowClient(getenv('PAYNOW_INTEGRATION_ID'), getenv('PAYNOW_INTEGRATION_KEY'));

$res = $client->initiate(
    reference: 'INV-35',
    amount: 12.50,
    returnUrl: 'https://example.com/paynow/return?ref=INV-35',
    resultUrl: 'https://example.com/paynow/callback',
    authEmail: 'customer@example.com',
);

$orderRepo->attachPollUrl('INV-35', $res['pollurl']);
header('Location: ' . $res['browserurl']);
```

### 10.2 PHP callback (`resulturl`) handler — idempotent

```php
<?php
require __DIR__ . '/vendor/autoload.php';

$key    = getenv('PAYNOW_INTEGRATION_KEY');
$hasher = new PaynowHash($key);

// Read the RAW body so field order is preserved exactly as Paynow sent it.
$raw    = file_get_contents('php://input');
$fields = PaynowHash::parseResponse($raw);

if (! $hasher->verify($fields)) {
    error_log('[paynow] REJECTED callback: bad hash');
    http_response_code(400);
    exit;
}

$lower = array_change_key_case($fields, CASE_LOWER);

$reference = $lower['reference']       ?? null;
$status    = $lower['status']          ?? '';
$amount    = (float) ($lower['amount'] ?? 0);
$pnRef     = $lower['paynowreference'] ?? null;

$order = $orderRepo->findByReference($reference);
if (! $order) {
    error_log("[paynow] unknown reference {$reference}");
    http_response_code(200);   // 200 so Paynow stops retrying
    exit;
}

$PAID = ['Paid', 'Awaiting Delivery', 'Delivered'];

if (in_array($status, $PAID, true)) {
    if ($order->isFulfilled()) {
        http_response_code(200);   // idempotent: already done
        exit;
    }
    if (abs($amount - $order->expectedAmount) > 0.001) {
        error_log("[paynow] AMOUNT MISMATCH ref={$reference} got={$amount} want={$order->expectedAmount}");
        $orderRepo->flagForReview($order->id);
        http_response_code(200);
        exit;
    }

    // Confirm by polling before releasing goods (recommended by Paynow)
    $confirm = (new PaynowClient(getenv('PAYNOW_INTEGRATION_ID'), $key))->poll($lower['pollurl']);
    if (! in_array($confirm['status'] ?? '', $PAID, true)) {
        error_log("[paynow] callback said paid but poll said {$confirm['status']}");
        http_response_code(200);
        exit;
    }

    $orderRepo->markPaid($order->id, $pnRef, $status);
    $queue->push(new FulfilOrderJob($order->id));

} elseif (in_array($status, ['Cancelled', 'Refunded', 'Disputed'], true)) {
    $orderRepo->markTerminal($order->id, $status);
} else {
    $orderRepo->touchStatus($order->id, $status);   // Created / Sent
}

http_response_code(200);
```

### 10.3 Laravel controller

```php
<?php

namespace App\Http\Controllers;

use Illuminate\Http\Request;
use Paynow\Payments\Paynow;

class PaynowController extends Controller
{
    private function gateway(string $orderRef): Paynow
    {
        return new Paynow(
            config('services.paynow.id'),
            config('services.paynow.key'),
            route('paynow.return', ['ref' => $orderRef]),
            route('paynow.callback'),
        );
    }

    /** POST /checkout/paynow */
    public function checkout(Request $request)
    {
        $order  = $request->user()->currentOrder();
        $paynow = $this->gateway($order->reference);

        $authEmail = config('services.paynow.test_mode')
            ? config('services.paynow.merchant_email')   // must be the merchant login in test mode
            : $order->customer_email;

        $payment = $paynow->createPayment($order->reference, $authEmail);
        foreach ($order->items as $item) {
            $payment->add($item->name, round($item->price * $item->qty, 2));
        }

        try {
            $response = $paynow->send($payment);
        } catch (\Throwable $e) {
            // InvalidIntegration / HashMismatch / Connection / EmptyCart — see §3.10
            report($e);
            return back()->withErrors('Could not start the payment. Please try again.');
        }

        if (! $response->success()) {
            report(new \RuntimeException('Paynow init failed: ' . $response->errors()));
            return back()->withErrors('Could not start the payment. Please try again.');
        }

        $order->update([
            'poll_url'       => $response->pollUrl(),
            'payment_status' => 'initiated',
        ]);

        return redirect()->away($response->redirectUrl());
    }

    /** POST /paynow/callback  — exempt from CSRF in bootstrap/app.php or VerifyCsrfToken */
    public function callback(Request $request)
    {
        $fields = \PaynowHash::parseResponse($request->getContent());

        if (! (new \PaynowHash(config('services.paynow.key')))->verify($fields)) {
            logger()->warning('Paynow callback rejected: bad hash');
            return response('', 400);
        }

        $f     = array_change_key_case($fields, CASE_LOWER);
        $order = \App\Models\Order::where('reference', $f['reference'] ?? '')->first();

        if ($order && ! $order->isPaid()
            && in_array($f['status'] ?? '', ['Paid', 'Awaiting Delivery', 'Delivered'], true)
            && abs((float) $f['amount'] - (float) $order->total) < 0.001) {

            $order->markPaid($f['paynowreference'] ?? null);
            \App\Jobs\FulfilOrder::dispatch($order);
        }

        return response('', 200);
    }

    /** GET /paynow/return — cosmetic only */
    public function return(Request $request)
    {
        $order = \App\Models\Order::where('reference', $request->query('ref'))->firstOrFail();
        return view('checkout.thanks', ['order' => $order->fresh()]);
    }
}
```

`config/services.php`:

```php
'paynow' => [
    'id'             => env('PAYNOW_INTEGRATION_ID'),
    'key'            => env('PAYNOW_INTEGRATION_KEY'),
    'test_mode'      => env('PAYNOW_TEST_MODE', true),
    'merchant_email' => env('PAYNOW_MERCHANT_EMAIL'),
],
```

### 10.4 Express.js end-to-end app (continued)

```js
const express = require("express");
const { Paynow } = require("paynow");
const { PaynowHash } = require("./paynow-hash");

const app = express();
const hasher = new PaynowHash(process.env.PAYNOW_INTEGRATION_KEY);
const PAID = new Set(["Paid", "Awaiting Delivery", "Delivered"]);
const TERMINAL = new Set(["Cancelled", "Refunded", "Disputed"]);

function gateway(orderRef) {
  const p = new Paynow(
    process.env.PAYNOW_INTEGRATION_ID,
    process.env.PAYNOW_INTEGRATION_KEY
  );
  p.resultUrl = `${process.env.APP_URL}/paynow/callback`;
  p.returnUrl = `${process.env.APP_URL}/paynow/return?ref=${encodeURIComponent(orderRef)}`;
  return p;
}

function authEmailFor(customerEmail) {
  // In test mode Paynow only lets the MERCHANT account fake a payment.
  return process.env.PAYNOW_TEST_MODE === "true"
    ? process.env.PAYNOW_MERCHANT_EMAIL
    : customerEmail;
}

app.use(express.json());

/* ---------- 1. Start a redirect (web) payment ---------- */
app.post("/checkout/paynow", async (req, res, next) => {
  try {
    const order = await orders.create(req.body);
    const paynow = gateway(order.reference);

    const payment = paynow.createPayment(order.reference, authEmailFor(order.email));
    for (const item of order.items) {
      payment.add(item.name, Number((item.price * item.qty).toFixed(2)));
    }

    const response = await paynow.send(payment);

    if (!response.success) {
      console.error("[paynow] init failed:", response.error);
      return res.status(502).json({ error: "Could not start payment." });
    }

    await orders.update(order.id, {
      pollUrl: response.pollUrl,
      paymentStatus: "initiated",
    });

    return res.json({ redirectUrl: response.redirectUrl });
  } catch (err) {
    next(err);
  }
});

/* ---------- 2. Start a mobile money (Express Checkout) payment ---------- */
app.post("/checkout/paynow/mobile", async (req, res, next) => {
  try {
    const { phone, method } = req.body; // method: 'ecocash' | 'onemoney'
    const order = await orders.create(req.body);
    const paynow = gateway(order.reference);

    // email is REQUIRED for mobile payments
    const payment = paynow.createPayment(order.reference, authEmailFor(order.email));
    for (const item of order.items) {
      payment.add(item.name, Number((item.price * item.qty).toFixed(2)));
    }

    const response = await paynow.sendMobile(payment, phone, method);

    if (!response.success) {
      // e.g. "Insufficient balance" (test number 0774444444)
      return res.status(402).json({ error: response.error });
    }

    await orders.update(order.id, {
      pollUrl: response.pollUrl,
      paymentStatus: "awaiting_authorisation",
    });

    return res.json({
      reference: order.reference,
      instructions: response.instructions, // show this to the customer
    });
  } catch (err) {
    next(err);
  }
});

/* ---------- 3. Status update callback (resultUrl) ---------- */
// IMPORTANT: capture the RAW body so field order survives for hashing.
app.post(
  "/paynow/callback",
  express.raw({ type: "*/*" }),
  async (req, res) => {
    const raw = req.body.toString("utf8");
    const fields = PaynowHash.parseResponse(raw);

    if (!hasher.verify(fields)) {
      console.warn("[paynow] REJECTED callback: bad hash");
      return res.sendStatus(400);
    }

    // Normalise keys for lookup
    const f = {};
    for (const [k, v] of fields) f[k.toLowerCase()] = v;

    const order = await orders.findByReference(f.reference);
    if (!order) {
      console.warn("[paynow] unknown reference", f.reference);
      return res.sendStatus(200); // 200 so Paynow stops retrying
    }

    if (PAID.has(f.status)) {
      if (order.fulfilled) return res.sendStatus(200); // idempotent

      if (Math.abs(Number(f.amount) - Number(order.total)) > 0.001) {
        console.error("[paynow] AMOUNT MISMATCH", f.reference, f.amount, order.total);
        await orders.flagForReview(order.id);
        return res.sendStatus(200);
      }

      await orders.markPaid(order.id, f.paynowreference, f.status);
      await queue.add("fulfil-order", { orderId: order.id });
    } else if (TERMINAL.has(f.status)) {
      await orders.markTerminal(order.id, f.status);
    } else {
      await orders.touchStatus(order.id, f.status); // Created / Sent
    }

    return res.sendStatus(200);
  }
);

/* ---------- 4. Browser return URL (cosmetic only) ---------- */
app.get("/paynow/return", async (req, res) => {
  const order = await orders.findByReference(req.query.ref);
  if (!order) return res.status(404).send("Unknown order");
  // Never fulfil here — just render current state.
  res.render("checkout/thanks", { order });
});

/* ---------- 5. Front-end status endpoint for polling UI ---------- */
app.get("/paynow/status/:ref", async (req, res) => {
  const order = await orders.findByReference(req.params.ref);
  if (!order) return res.sendStatus(404);

  if (!order.fulfilled && order.pollUrl) {
    const paynow = gateway(order.reference);
    // NB: the resolved object has NO paid() method - compare the status word.
    const r = await paynow.pollTransaction(order.pollUrl);
    if (PAID.has(r.status) && !order.fulfilled) {
      await orders.markPaid(order.id, null, r.status);
      await queue.add("fulfil-order", { orderId: order.id });
    }
  }

  const fresh = await orders.findByReference(req.params.ref);
  res.json({ status: fresh.paymentStatus, paid: fresh.fulfilled });
});

app.listen(3000);
```

> **Why `express.raw` on the callback route only?** The hash depends on field *order*.
> `express.urlencoded` produces a plain object, and while V8 usually preserves insertion
> order for string keys, capturing the raw body removes all doubt. Keep `express.json()`
> for your normal routes.

### 10.5 Polling with backoff

Mobile money needs a poll loop while the customer authorises on their handset.
Test number `0772222222` resolves at ~30 s, so your loop must survive at least that long.

**Node.js**

```js
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/**
 * Poll until terminal or timeout.
 * Schedule: 3s, 3s, 5s, 5s, 8s, 8s, 13s, 13s, 20s, 20s, then 20s... (cap 20s)
 */
async function awaitPayment(paynow, pollUrl, { timeoutMs = 300_000 } = {}) {
  const PAID = new Set(["Paid", "Awaiting Delivery", "Delivered"]);
  const TERMINAL = new Set(["Cancelled", "Refunded", "Disputed"]);

  const deadline = Date.now() + timeoutMs;
  let delay = 3000;

  while (Date.now() < deadline) {
    await sleep(delay);
    delay = Math.min(Math.round(delay * 1.35), 20_000);

    let status;
    try {
      status = await paynow.pollTransaction(pollUrl);
    } catch (err) {
      console.warn("[paynow] poll failed, retrying:", err.message);
      continue; // transient network error — keep going
    }

    if (PAID.has(status.status)) return { outcome: "paid", status: status.status };
    if (TERMINAL.has(status.status)) return { outcome: "failed", status: status.status };
    // 'Created' / 'Sent' → keep waiting
  }

  return { outcome: "timeout", status: null };
}
```

**PHP (queue worker / CLI)**

```php
<?php
function awaitPayment(PaynowClient $client, string $pollUrl, int $timeoutSeconds = 300): array
{
    $paid     = ['Paid', 'Awaiting Delivery', 'Delivered'];
    $terminal = ['Cancelled', 'Refunded', 'Disputed'];

    $deadline = time() + $timeoutSeconds;
    $delay    = 3;

    while (time() < $deadline) {
        sleep($delay);
        $delay = min((int) ceil($delay * 1.35), 20);

        try {
            $result = $client->poll($pollUrl);
        } catch (Throwable $e) {
            error_log('[paynow] poll failed: ' . $e->getMessage());
            continue;
        }

        $status = $result['status'] ?? '';
        if (in_array($status, $paid, true))     return ['outcome' => 'paid',   'status' => $status];
        if (in_array($status, $terminal, true)) return ['outcome' => 'failed', 'status' => $status];
    }

    return ['outcome' => 'timeout', 'status' => null];
}
```

> Prefer **callback-driven** fulfilment and use polling as confirmation/backstop.
> A long-running poll loop inside an HTTP request will time out; run it in a worker.

### 10.6 Front-end pattern for mobile money

```js
// 1. Kick off the payment
const res = await fetch("/checkout/paynow/mobile", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ phone: "0771111111", method: "ecocash", ...cart }),
});

if (!res.ok) {
  showError((await res.json()).error);   // e.g. "Insufficient balance"
  return;
}

const { reference, instructions } = await res.json();

// 2. Show the Paynow-supplied instructions verbatim
instructionsEl.textContent = instructions;

// 3. Poll YOUR OWN endpoint (never Paynow directly from the browser —
//    that would expose the poll URL and invite tampering)
const started = Date.now();
const timer = setInterval(async () => {
  const s = await (await fetch(`/paynow/status/${reference}`)).json();

  if (s.paid) {
    clearInterval(timer);
    window.location = `/orders/${reference}/complete`;
  } else if (Date.now() - started > 300_000) {
    clearInterval(timer);
    showError("Payment timed out. If you were debited, contact support.");
  }
}, 4000);
```

### 10.7 Raw Node.js client (for methods the SDK doesn't wrap)

Use this for **InnBucks**, **O'mari**, **Zimswitch** and **card-token** Express Checkout.

```js
const crypto = require("crypto");
const { PaynowHash } = require("./paynow-hash");

const ENDPOINTS = {
  initiate: "https://www.paynow.co.zw/interface/initiatetransaction",
  remote: "https://www.paynow.co.zw/interface/remotetransaction",
  trace: "https://www.paynow.co.zw/interface/trace",
};

class PaynowRawClient {
  constructor(integrationId, integrationKey) {
    this.id = integrationId;
    this.key = integrationKey;
    this.hasher = new PaynowHash(integrationKey);
  }

  /** Express Checkout — pass method-specific extras in `extra`. */
  async remote({ reference, amount, returnUrl, resultUrl, authEmail, method, merchantTrace, ...extra }) {
    // Insertion order defines the hash — build deliberately.
    const fields = new Map();
    fields.set("id", this.id);
    fields.set("reference", reference);
    fields.set("amount", Number(amount).toFixed(2));
    fields.set("returnurl", returnUrl);
    fields.set("resulturl", resultUrl);
    fields.set("authemail", authEmail);            // REQUIRED for express checkout
    fields.set("method", method);                  // zimswitch|vmc|ecocash|onemoney|innbucks|omari
    fields.set("merchanttrace", merchantTrace);    // REQUIRED for vmc/zimswitch
    for (const [k, v] of Object.entries(extra)) {
      if (v !== undefined && v !== null) fields.set(k, String(v)); // phone, token, ...
    }
    fields.set("status", "Message");
    fields.set("hash", this.hasher.generate(fields));

    return this.#post(ENDPOINTS.remote, fields);
  }

  /** Complete an O'mari payment with the OTP the customer received by SMS. */
  async submitOmariOtp(remoteOtpUrl, otp) {
    const fields = new Map();
    fields.set("id", this.id);
    fields.set("otp", otp);
    fields.set("status", "Message");
    fields.set("hash", this.hasher.generate(fields));
    return this.#post(remoteOtpUrl, fields);
  }

  async poll(pollUrl) {
    return this.#post(pollUrl, new Map());
  }

  async trace(merchantTrace) {
    const fields = new Map();
    fields.set("id", this.id);
    fields.set("merchanttrace", merchantTrace);
    fields.set("status", "Message");
    fields.set("hash", this.hasher.generate(fields));
    return this.#post(ENDPOINTS.trace, fields);
  }

  async #post(url, fields) {
    const body = new URLSearchParams();
    for (const [k, v] of fields) body.append(k, v);

    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: body.toString(),
      signal: AbortSignal.timeout(30_000),
    });

    const text = await res.text();
    const parsed = PaynowHash.parseResponse(text);

    const lower = {};
    for (const [k, v] of parsed) lower[k.toLowerCase()] = v;

    if (lower.status === "Error") {
      const err = new Error(`Paynow error: ${lower.error ?? "unknown"}`);
      err.paynow = lower;
      throw err;
    }
    if (!this.hasher.verify(parsed)) {
      throw new Error("Paynow hash verification FAILED — response rejected.");
    }
    return lower;
  }
}

module.exports = { PaynowRawClient };
```

**InnBucks usage**

```js
const r = await client.remote({
  reference: "INV-40", amount: 12.5,
  returnUrl, resultUrl, authEmail: "customer@example.com",
  method: "innbucks", merchantTrace: crypto.randomUUID().replace(/-/g, ""),
});

// Show BOTH to the customer:
//   r.authorizationcode      e.g. "AB12CD"
//   r.authorizationexpires   e.g. "20-Sep-2026 14:35"

// Deep link - PRIMARY is the scheme the paynow npm package builds (v2.2.2);
// the developer hub documents a different one. Offer the fallback if the
// primary fails to open the app on the customer's handset. See §5.4.
const deepLinkPrimary  = `schinn.wbpycode://innbucks.co.zw?pymInnCode=${r.authorizationcode}`;
const deepLinkFallback = `com.innbucks.customer://purchase?paymentToken=${r.authorizationcode}`;

// QR - generate LOCALLY. Do not hand the authorization code to a third-party
// chart API: it lands in someone else's access logs, and Google's Image Charts
// endpoint is deprecated with no availability guarantee.
//   npm install qrcode          (PHP: composer require endroid/qr-code)
const QRCode = require("qrcode");
const qrDataUri = await QRCode.toDataURL(r.authorizationcode, { width: 250 });
// render as: <img src="${qrDataUri}" alt="Scan with InnBucks">
```

**O'mari usage**

```js
const r = await client.remote({
  reference: "INV-41", amount: 12.5,
  returnUrl, resultUrl, authEmail: "customer@example.com",
  method: "omari", phone: "0712345678",
  merchantTrace: crypto.randomUUID().replace(/-/g, ""),
});

// Show r.otpreference to the customer, collect the SMS OTP, then:
const done = await client.submitOmariOtp(r.remoteotpurl, userEnteredOtp);
// done.status === "Paid" / "Awaiting Delivery" ... or throws with "Invalid OTP"
// After 5 wrong attempts the transaction is cancelled — start a new one.
```

**Recurring card charge with a stored token**

```js
const r = await client.remote({
  reference: "SUB-2026-09", amount: 9.99,
  returnUrl, resultUrl, authEmail: customer.email,
  method: "vmc",
  token: customer.paynowCardToken,
  merchantTrace: crypto.randomUUID().replace(/-/g, ""), // unique per attempt
});
// The status update will carry a NEW token — overwrite the stored one.
```

---

## Appendix A — Official Plugins & Extensions (no code required)

If the project is a WordPress/e-commerce site, prefer an official plugin over hand-rolled
code. The three WordPress plugins below need only your **Integration ID** and
**Integration Key**. Shopify does **not** — see below.

### WooCommerce

**Prerequisites:** WordPress, WooCommerce, Integration ID & Key.

1. Install the *Paynow for WooCommerce* plugin like any other WordPress plugin:
   **Dashboard → Plugins → Add New → Upload Plugin**.
2. Go to **Plugins** and activate it.
3. Go to **WooCommerce → Settings → Checkout**; Paynow appears as a checkout option.
   Open its settings page.
4. Tick the checkbox to enable the gateway, then enter your Integration ID into
   **Merchant ID** and your Integration Key into **Merchant Key**.
5. **Save Changes**, then run a test checkout from the site front end.

### Gravity Forms

**Prerequisites:** WordPress, Gravity Forms, Integration ID & Key.

1. Install and activate the *Paynow for Gravity Forms* plugin.
2. Go to **Forms → Settings → Paynow** tab.
3. Enter your Integration ID into **Merchant ID** and Integration Key into **Merchant Key**.
4. **Update Settings**, then build your form with the required **Pricing Fields** and
   configure the **Paynow Feed** settings.

### Easy Digital Downloads

**Prerequisites:** WordPress, Easy Digital Downloads, Integration ID & Key.

1. Install and activate the *Paynow for Easy Digital Downloads* plugin.
2. Go to **Downloads → Settings → Payment Gateways**.
3. Tick **Paynow Gateway** to enable it.
4. Scroll to **Paynow Gateway Settings** and enter your Integration ID into
   **Merchant api ID** and Integration Key into **Merchant API Key**.
5. **Save Changes**, then run a test checkout from the site front end.

### Shopify — not self-serve

⚠️ Shopify is listed under *Plugins & Extensions*, but there is **no published ID/Key
configuration flow**. The hub's entire Shopify page reads:

> *"If you would like to integrate Shopify with Paynow please contact us before setting
> up your store. Send us an email at sales@paynow.co.zw."*

So: **email `sales@paynow.co.zw` before you build the store**, not after.

### Developed by the community

The hub keeps these in a separate *Developed by the Community* section: **Magento**,
**CampTix** and **Spring Boot**. They are **not maintained by Paynow** — read the source
before putting one in front of real money.

---

## Appendix B — Quick Reference Card

### Endpoints

```
POST https://www.paynow.co.zw/interface/initiatetransaction        # web / redirect
POST https://www.paynow.co.zw/interface/remotetransaction          # express checkout
POST https://www.paynow.co.zw/interface/initiatetickettransaction  # airline tickets
POST https://www.paynow.co.zw/interface/trace                      # recover by merchanttrace
POST <pollurl>                                                      # empty body
POST <remoteotpurl>                                                 # O'mari OTP
```

Content type is always `application/x-www-form-urlencoded`. Responses are query strings.

### Express Checkout methods

```
zimswitch | vmc | ecocash | onemoney | innbucks | omari
```

### Statuses

```
MONEY GOOD : Paid · Awaiting Delivery · Delivered   (check all three YOURSELF)
IN FLIGHT  : Created · Sent
TERMINAL   : Cancelled · Disputed · Refunded
TRACE ONLY : NotFound
ERRORS     : Error (+ error=<reason>)
```

### Hash algorithm

```
API messages          : join VALUES (in order, excl. hash) + integrationKey → SHA512 → UPPER HEX
Button notifications  : join KEY+VALUE (in order, excl. Hash) + integrationKey → SHA512 → UPPER HEX
Inbound               : URL-decode every value before joining
Outbound              : use raw values; URL-encode only when building the body
Integration key       : LOWER-CASE it before appending (both SDKs do)
```

### Test credentials

```
Mobile money phone numbers
  0771111111  success (5s)      0772222222  delayed success (30s)
  0773333333  cancelled (30s)   0774444444  insufficient balance (immediate)

vmc tokens
  {11111111-1111-1111-1111-111111111111}  success
  {22222222-2222-2222-2222-222222222222}  pending
  {33333333-3333-3333-3333-333333333333}  cancelled
  {44444444-4444-4444-4444-444444444444}  insufficient balance

zimswitch tokens
  11111111111111111111111111111111  success
  22222222222222222222222222222222  pending
  33333333333333333333333333333333  cancelled
  44444444444444444444444444444444  insufficient balance

Hash test vector (key 3e9fed89-60e1-4ce5-ab6e-6b1eb2d4f977)
  → 2A033FC38798D913D42ECB786B9B19645ADEDBDE788862032F1BD82CF3B92DEF
    84F316385D5B40DBB35F1A4FD7D5BFE73835174136463CDD48C9366B0749C689
```

### Link formats

```
Simple button   : https://www.paynow.co.zw/payment/link/{email}?q={b64+urlenc args}
                  args: search, amount, reference, l
Advanced button : https://www.paynow.co.zw/payment/billpaymentlink/{email}?q={b64+urlenc args}
                  args: id, amount, quantity, l, f1, f2, f3...
```

### SDK API surface

| | PHP | Node.js |
|---|---|---|
| Install | `composer require paynow/php-sdk` | `npm install --save paynow` |
| Construct | `new Paynow($id, $key, $returnUrl, $resultUrl)` | `new Paynow(id, key)` |
| Set URLs | `setReturnUrl()` / `setResultUrl()` | `paynow.returnUrl =` / `paynow.resultUrl =` |
| New cart | `$paynow->createPayment($ref, $email)` | `paynow.createPayment(ref, email?)` |
| Add item | `$payment->add($name, $price)` | `payment.add(name, price)` |
| Send web | `$paynow->send($payment)` | `await paynow.send(payment)` |
| Send mobile | `$paynow->sendMobile($p, $phone, $method)` | `await paynow.sendMobile(p, phone, method)` |
| Poll | `$paynow->pollTransaction($pollUrl)` | `await paynow.pollTransaction(pollUrl)` |
| Success? | `$response->success()` *(method)* | `response.success` *(property)* |
| Redirect | `$response->redirectUrl()` | `response.redirectUrl` |
| Poll URL | `$response->pollUrl()` | `response.pollUrl` |
| Instructions | `$response->instructions()` | `response.instructions` |
| Paid? | ⚠️ **not** `paid()` (matches only `Paid`) — use `in_array($status->status(), ['paid','awaiting delivery','delivered'], true)` | ⚠️ **no `paid()` exists** — use `["Paid","Awaiting Delivery","Delivered"].includes(status.status)` |

---

## Appendix C — Rules Claude Should Always Apply

When generating Paynow integration code, apply these without being asked:

1. **Never** place the integration key in client-side code, a URL, a query string, or a log line.
2. **Always** verify the hash on every inbound message before acting on it, using a
   timing-safe comparison.
3. **Always** verify the initiation-response hash *before* redirecting the customer.
4. **Never** fulfil an order from the `returnurl` hit — only from a verified `resulturl`
   callback or an explicit poll.
5. **Always** persist the `pollUrl` before redirecting or displaying mobile instructions.
6. **Always** make the callback handler idempotent and return `200` quickly (Paynow retries
   up to 10 times on error responses).
7. **Always** reconcile the callback `amount` against your own stored total before fulfilling.
8. **Always** treat `Paid`, `Awaiting Delivery` and `Delivered` as payment received —
      and **never** delegate that check to `paid()`. PHP's `paid()` matches only `Paid`;
      Node has no `paid()` at all.
9. **Always** send a unique `merchanttrace` on Express Checkout requests and store it.
10. **Always** format amounts to exactly two decimals with a `.` separator and no symbol.
11. **Always** preserve field order when building or verifying hashes (ordered array / `Map`).
12. In test mode, **always** set `authemail` to the merchant account's own login address.
13. **Always** put a comma between the return and result URL arguments in the PHP
      constructor (the published example omits it).
14. In Node, **always** `await pollTransaction()`; **every** response member is a
      property and there is **no `paid()` method**, whatever the published docs show.
15. **Never** expose the poll URL to the browser; proxy status checks through your own endpoint.
16. **Never** auto-refund or re-charge on a trace *error* — a trace error does not prove the
      transaction is absent.
17. Remember that button/link integrations let a determined customer alter amount and
      reference even when `l=1`; verify values after payment, or use the API integration.
18. Notification-URL hashes use **key+value** concatenation, unlike API hashes which use
      **values only**.
19. **Always** hash every value in a response, in arrival order — never a fixed field
      list. Responses carry undocumented fields (`paynowreference`) that are in the digest.
19a. **Always** lower-case the integration key before appending it to the hash string,
      as both official SDKs do. Paynow's own example keys are lower-case, so omitting
      this passes every published fixture and fails on an upper-cased production key.
20. **Always** wrap PHP SDK calls in `try/catch` — `send()`, `sendMobile()` and
      `pollTransaction()` throw rather than returning a failed response (§3.10).
21. **Never** send a payment code, token or reference to a third-party service to render
      a QR code. Generate QR codes locally.

---

## Appendix D — Source Index

All content verified against the Paynow Developer Hub on **20 September 2026**.

| Topic | URL |
|---|---|
| Getting Started | `/docs/paynow/quickstart/` |
| Generating Integration Keys | `/docs/paynow/integration_generation/` |
| Test Mode | `/docs/paynow/test_mode/` |
| Artwork and Buttons | `/docs/paynow/artwork/` |
| PHP Quickstart | `/docs/paynow/php_quickstart/` |
| Node.JS Quickstart | `/docs/paynow/nodejs_quickstart/` |
| System Layout | `/docs/paynow/paynow_api/` |
| Initiate a transaction | `/docs/paynow/initiate_transaction/` |
| Initiate a mobile money transaction | `/docs/paynow/initiate_mobile_transaction/` — ⚠️ **orphaned**: still resolves, but no longer linked from the API Reference sidebar. Express Checkout is now the canonical page for mobile money. |
| Express Checkout Transactions | `/docs/paynow/express_checkout_transactions/` |
| Initiate a Passenger Ticket Transaction | `/docs/paynow/initiate_ticket_transaction/` |
| Complete a Transaction | `/docs/paynow/complete_transaction/` |
| Status Update | `/docs/paynow/status_update/` |
| Polling for a Status Update | `/docs/paynow/polling_status/` |
| Generating Hash | `/docs/paynow/generating_hash/` |
| Validating Hash | `/docs/paynow/validating_hash/` |
| Simple Payment Request Button | `/docs/paynow/simple_paynow_request_button/` |
| Advanced Payment Request Button | `/docs/paynow/advanced_paynow_request_button/` |
| Notification, Success & Cancel URLs | `/docs/paynow/notification_success_cancel_urls/` |
| URL Safe Base 64 Encoding | `/docs/paynow/url_safe_base64_encoding/` |
| WooCommerce | `/docs/paynow/woocommerce/` |
| Gravity Forms | `/docs/paynow/gravity_forms/` |
| Easy Digital Downloads | `/docs/paynow/easy_digital_downloads/` |
| Shopify | `/docs/paynow/shopify/` |
| Camptix *(community)* | `/docs/paynow/camptix_nigelrodgers/` |
| Magento *(community)* | `/docs/paynow/magento_prizeless/` |
| Spring Boot *(community)* | `/docs/paynow/springboot_bmukorera_tzifudzi/` |

Also on the hub but not covered in depth here: the **C#/.NET**, **Python** and **Java**
quickstarts.

**Corroborating sources** — read directly from the packages, not via the hub, and the
basis for every finding in Appendix E:

- `github.com/paynow/Paynow-PHP-SDK` (Composer `paynow/php-sdk`)
- `github.com/paynow/Paynow-Nodejs-SDK` (npm `paynow` **v2.2.2**)

Base: `https://developers.paynow.co.zw`
Support / feature applications (tokenisation, payment-instrument detail): `support@paynow.co.zw`
Shopify setup (mandatory, before building the store): `sales@paynow.co.zw`

---

## Appendix E — Known Upstream Defects

Places where **the Paynow Developer Hub is wrong about its own SDKs**, verified against
the shipped packages on 20 September 2026.

If you later re-verify this document against the hub and find these corrections
disagreeing with it, **the hub is the stale one** — do not revert them without re-reading
the package source.

| # | Where | The hub says | The shipped SDK does | Severity |
|---|---|---|---|---|
| 1 | PHP status checks | `paid()` covers the paid states | `return $this->status() === 'paid';` — false for `Awaiting Delivery` and `Delivered` | **Critical** — unfulfilled paid orders |
| 2 | Node quickstart | `status.paid()` | No `paid()` on `StatusResponse`; `pollTransaction()` even resolves an `InitResponse` | **Critical** — `TypeError` at runtime |
| 3 | Node quickstart | `let status = paynow.pollTransaction(url)` | Returns a promise; must be awaited | High |
| 4 | URL Safe Base 64 Encoding | Recipe: URL-encode each value → Base64 → URL-encode | Published example links skip step 1; the advanced-button example has a stray space in `f2`. Neither is reproducible. | High |
| 5 | Express Checkout (InnBucks) | `com.innbucks.customer://purchase?paymentToken=` | `schinn.wbpycode://innbucks.co.zw?pymInnCode=` (`INNBUCKS_DEEPLINK_PREFIX`) | Medium — open with `support@paynow.co.zw` |
| 6 | Initiate a transaction | Success response has four fields | Also returns `paynowreference`, which is inside the hash | Medium — phantom hash mismatches |
| 7 | PHP quickstart | Constructor example | Missing comma between `returnurl` and `resulturl` — does not parse | Medium |
| 8 | PHP quickstart | PHP 5.6+ | True of the SDK; §6.4 and §10.1 here need 8.0+ | Low |
| 9 | Shopify | Listed as a plugin | No self-serve setup — email `sales@paynow.co.zw` first | Low |

### Re-verified and found correct

Recorded so the next review doesn't redo the work:

- **Both SHA-512 fixtures** (§6.2 outbound, §6.3 inbound) recomputed byte-for-byte,
  including the URL-decoded values and the trailing join artefact in §6.3.
- All **six endpoint URLs** (§5.1, Appendix B), cross-checked against both SDKs' constants.
- Field tables for **§5.2–§5.8**: initiate, mobile money, Express Checkout (incl. the
  InnBucks / O'mari / token rules), passenger ticket (all 24 fields + 7 passenger types),
  status update (incl. tokenisation and payment-instrument blocks), polling, trace.
- The full **status vocabulary** and its grouping, plus `NotFound` for trace.
- The **ten-retry** rule and the recommendation to poll after an important update.
- The **token expiry** rule, including the 3 Mar 2019 / 30 Apr 2019 worked example.
- All **test-mode material**: the merchant-account-only rule, `[TESTING: Faked Success]`,
  the four MSISDNs with their 5s/30s/30s/immediate timings, and both the `vmc` GUID and
  `zimswitch` 32-character token sets.
- The **Links & Buttons** argument tables, the Notification-URL POST field list (incl.
  `Transaction_Amount` vs `Amount_Paid`), and the artwork formats and button variants.
- **Plugin install steps** for WooCommerce, Gravity Forms and Easy Digital Downloads,
  including the exact field labels.