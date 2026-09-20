# Test mode, test credentials & going live

Every new integration starts in test mode. You can create, pay and cancel transactions
without moving money and without any bank or wallet access.

## Contents

- [Getting credentials](#getting-credentials)
- [The merchant-account rule](#the-merchant-account-rule)
- [Completing a redirect test payment](#completing-a-redirect-test-payment)
- [Test credentials](#test-credentials)
- [The test matrix worth automating](#the-test-matrix-worth-automating)
- [Going live](#going-live)

## Getting credentials

An account can have many integrations; each gets its own ID and Key.

1. Register at `https://www.paynow.co.zw/Customer/Register`, validate the email.
2. Configure the bank account to be settled into.
3. **Other Ways To Get Paid** → `https://www.paynow.co.zw/Home/Receive`
4. **Create/Manage Shopping Carts** → **Create Advanced Integration**
5. Fill in:
   - **Name** — how you'll identify it.
   - **Absorb fees** — merchant or customer carries Paynow's fee. This decides whether
     `Transaction_Amount` and `Amount_Paid` differ on button notifications.
   - **Email** — where transaction updates go.
   - **Notification URL** — *leave blank* when sending a per-transaction `resulturl`,
     which is what both SDKs do. Only set it for link/button integrations.
   - **Payment Methods** — tick every method you intend to call. Calling `method=ecocash`
     on an integration without EcoCash ticked fails at initiation.
6. Save.

The **Integration ID** then appears in *Integration Keys*. The **Key is never displayed**
— click **Email Key To Company Address** to receive it.

```bash
# .env — never commit
PAYNOW_INTEGRATION_ID=1201
PAYNOW_INTEGRATION_KEY=3e9fed89-60e1-4ce5-ab6e-6b1eb2d4f977
PAYNOW_RESULT_URL=https://example.com/payments/paynow/callback
PAYNOW_RETURN_URL=https://example.com/payments/paynow/return
PAYNOW_TEST_MODE=true
PAYNOW_MERCHANT_EMAIL=merchant-login@example.com
```

## The merchant-account rule

This is the number one cause of "it won't let me pay".

> After creating a test transaction, **only the merchant account that owns the
> integration** can log in and fake a payment. Anyone else sees a message saying the
> merchant is in testing and cannot proceed.

So in test mode `authemail` must be a **login address of the merchant account**, or the
developer locks themselves out of their own test. The same applies to Express Checkout.
Make it switchable rather than hardcoding the customer's email:

```php
$authEmail = config('services.paynow.test_mode')
    ? config('services.paynow.merchant_email')
    : $order->customer_email;
```

```js
const authEmail = process.env.PAYNOW_TEST_MODE === "true"
  ? process.env.PAYNOW_MERCHANT_EMAIL
  : customer.email;
```

Build this in from the start. Retrofitting it means every test transaction up to that
point was unusable.

## Completing a redirect test payment

On the Paynow payment page choose **[TESTING: Faked Success]** → **[Make Payment]**.
Paynow then responds exactly as for a real payment, including the `resulturl` status
update — so this is a genuine end-to-end test of the callback, not a stub.

## Test credentials

### Mobile money (`ecocash`, `onemoney`) — pass as `phone`

| Scenario | Number | Behaviour |
|---|---|---|
| Success | `0771111111` | `SUCCESS` status update **5s** after initiation |
| Delayed success | `0772222222` | `SUCCESS` status update **30s** after initiation |
| User cancelled | `0773333333` | `FAILED` status update **30s** after initiation |
| Insufficient balance | `0774444444` | Fails **immediately during initiation** |

The distinction matters for your error handling: `0774444444` fails at the *initiate*
step, caught by `success` / `success()`. `0773333333` initiates fine and only fails later
via the status update. A checkout that handles one but not the other looks fine in testing
and strands customers in production.

### Visa/Mastercard (`method=vmc`) — pass as `token`

```
{11111111-1111-1111-1111-111111111111}  success
{22222222-2222-2222-2222-222222222222}  pending
{33333333-3333-3333-3333-333333333333}  cancelled
{44444444-4444-4444-4444-444444444444}  insufficient balance
```

### Zimswitch (`method=zimswitch`) — pass as `token`

```
11111111111111111111111111111111  success
22222222222222222222222222222222  pending
33333333333333333333333333333333  cancelled
44444444444444444444444444444444  insufficient balance
```

Both token sets follow the mobile-money timings: success at 5s, pending→success at 30s,
cancelled→failed at 30s, insufficient balance immediately at initiation.

## The test matrix worth automating

| Case | Trigger | Expected |
|---|---|---|
| Init rejected | Bad amount, or a method not enabled on the integration | `Status=Error`, `error` populated, nothing persisted |
| Hash mismatch on response | Flip one character of the key in a unit test | Request aborted, no redirect, alert raised |
| Mobile success | `0771111111` | Poll flips to paid ~5s |
| Mobile delayed | `0772222222` | Still pending at 10s, paid by ~35s |
| Mobile cancelled | `0773333333` | Terminal failure ~30s, order not fulfilled |
| Mobile no funds | `0774444444` | Init fails immediately |
| Duplicate callback | Replay the same POST twice | Order fulfilled exactly once |
| Callback before return | Replay callback, then hit the return URL | No double-fulfilment; return page shows correct state |
| Unknown reference | POST a callback for a nonexistent ref | Logged, ignored, `200` returned |
| `Awaiting Delivery` | Craft a callback with that status | **Order fulfilled** — this is the one `paid()` breaks |
| Amount mismatch | Craft a callback with a short amount | Flagged for review, not fulfilled |

The last two are worth writing even when nothing else is: they catch the two failure modes
that lose real money and neither shows up in ordinary happy-path testing.

## Going live

1. Exercise every path in the matrix above.
2. **Integration Keys** → **[Request to be Set Live]**. Paynow support verifies at least
   one successful test transaction before flipping you live.
3. **[Generate New Key]** at the same time, so development keys and any ex-developer's
   copy stop working.
4. Confirm the production checklist:
   - Key in secret storage, never in client code, URLs, logs, or plaintext in the DB
   - Hash verified on every inbound message, timing-safe, over every value in arrival order
   - Initiation hash verified *before* redirecting
   - `resulturl` and `returnurl` on HTTPS
   - `additionalinfo` carries nothing confidential — the customer sees it
   - `reference` unique per transaction; `amount` two decimals, no symbol
   - Callback amount reconciled against your own record
   - `pollUrl` persisted before redirect; `merchanttrace` sent and stored for Express Checkout
   - Callback idempotent, returns `200` fast, slow work queued
   - All three paid states treated as paid, checked in your own code
   - Fulfilment never driven by the `returnurl` hit
   - Logging redacts hash and key
   - Alerts on hash-verification failures — they mean a bug or an attack
   - Reconciliation job polls anything still pending after N minutes
   - Mobile money has a hard timeout (~3–5 min) before being marked abandoned
