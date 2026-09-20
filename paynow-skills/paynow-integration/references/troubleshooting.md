# Troubleshooting

Start here when something is broken. Most Paynow problems are one of about a dozen things,
and the symptom usually points straight at the cause.

## Symptom → cause

| Symptom | Likely cause | Fix |
|---|---|---|
| **Hash mismatch on every response** | Hashing a fixed field list | Hash every value returned, in arrival order. `paynowreference` is in the digest but not in the documented field table. |
| Hash mismatch, intermittent | Field order lost by the parser | Use an ordered array / `Map` parsed from the **raw body**, not `parse_str()` or a framework-parsed object. |
| Hash mismatch on inbound only | Values not URL-decoded before joining | Decode each value first; also replace `+` with a space before `decodeURIComponent`. |
| Hash mismatch on outbound only | Values URL-encoded before joining | Join raw values; encode only when building the request body. |
| Hash mismatch on a button/link notification | Wrong algorithm | Notifications use **key+value**, not values alone. See `hashing.md`. |
| Hash compares as lowercase | Missing `strtoupper()` / `.toUpperCase()` | Output uppercase hex. |
| **`Invalid id.` / init always fails** | Wrong integration ID, or not set live | In PHP this throws `InvalidIntegrationException` rather than returning `success() === false` — catch it. |
| Init fails naming a payment method | Method not ticked on the integration | Enable it in the Paynow dashboard under the integration's Payment Methods. |
| `Invalid amount field` | Currency symbol, thousands separator, or wrong decimals | `number_format($n, 2, '.', '')` / `Number(n).toFixed(2)`. |
| **Callbacks never arrive** | CSRF middleware rejecting the route | Exempt the callback route. Laravel 11+: `validateCsrfTokens(except: [...])`. |
| Callbacks never arrive, no CSRF | `resulturl` not publicly reachable | Localhost and private IPs don't work — tunnel it in development. |
| Callbacks arrive repeatedly | Handler returning a non-2xx | Paynow retries up to ten times on error. Return `200` fast; queue slow work. |
| Callback body is empty | Body parser not set for `x-www-form-urlencoded` | `express.raw` on that route in Express; `php://input` in PHP. |
| **Order paid but never fulfilled** | `paid()` used as the fulfilment gate | PHP `paid()` matches only `Paid`, so `Awaiting Delivery` and `Delivered` fall through. Compare `status()` against the lower-cased three-value set. |
| Order paid but never fulfilled, Node | `status.paid()` threw and the handler swallowed it | There is no `paid()` in the Node SDK. Compare `status.status`. |
| Comparison against status words never matches, PHP | `status()` lower-cases its return | Compare against `['paid','awaiting delivery','delivered']`. |
| **`TypeError: status.paid is not a function`** | Following the published Node quickstart | No `paid()` exists on the response. |
| Node response members all `undefined` | `pollTransaction` not awaited | It returns a promise. `await` it. |
| Node poll result missing `reference`/`amount` | `pollTransaction()` resolves an `InitResponse`, not a `StatusResponse` | Key results off your own stored reference. |
| **Order fulfilled twice** | Non-idempotent callback | Guard with a unique constraint or a fulfilled check before doing work. |
| Fulfilled on an abandoned payment | Fulfilment driven by the `returnurl` hit | The return page is cosmetic. Fulfil only from a verified callback or poll. |
| **PHP constructor won't parse** | The docs snippet omits the comma between the two URLs | Add it. |
| PHP examples fail on 7.x | Promoted properties / named arguments are 8.0+ | Use PHP 8, or rewrite the helper without them. |
| `errors()` prints `Array` | It returns a **string** by default | `errors(false)` gives the array. |
| **"Merchant is in testing" when paying** | `authemail` isn't a merchant login address | In test mode only the merchant account can fake payment. Make `authemail` config-driven. |
| Test payment page won't complete | Same as above | See `testing-and-golive.md`. |
| **Recurring card charge stops working after a few months** | Stored token not refreshed | Every charge re-tokenises; overwrite the stored token from each status update. |
| Token rejected earlier than expected | Token expiry is capped by the card's own expiry | A six-month token on a card expiring sooner dies with the card. |
| **InnBucks deep link does nothing** | Scheme mismatch | Try `schinn.wbpycode://innbucks.co.zw?pymInnCode=` (what the npm package builds) before the documented `com.innbucks.customer://purchase?paymentToken=`. Prefer `response.innbucks_info[0].deep_link_url`. Keep the QR as the primary path. |
| InnBucks QR fails to render | Depending on Google's deprecated Image Charts endpoint | Generate the QR locally — `qrcode` / `endroid/qr-code`. |
| **O'mari transaction dies after a few tries** | Five failed OTP attempts cancels it | Surface the attempt count; re-initiate after cancellation. |
| **Express Checkout response never arrived** | Timeout or crash mid-request; no `pollurl` | That's what `merchanttrace` is for — `POST /interface/trace`. Send and store one on every Express Checkout request. |
| Trace returns an error | Does **not** mean the transaction is absent | Retry. Never auto-refund or re-charge off a trace error. |
| **Duplicate debit on retry** | `merchanttrace` reused or missing on vmc/zimswitch | Unique per *request*, not per order. |

## When nothing above fits

1. Capture the exact request body you sent and the exact response body you got, before any
   parsing. Most theories die on contact with the raw strings.
2. Run `python3 scripts/paynow_hash.py selftest` to confirm the algorithm, then
   `verify --key ... --body '<captured response>'` to see whether the mismatch is in the
   hashing or upstream of it.
3. Run `python3 scripts/audit_integration.py <project>` — it finds the structural mistakes
   that produce intermittent, hard-to-reproduce symptoms.
4. Check the integration in the Paynow dashboard: is it live, are the methods ticked, is
   the Notification URL set when it should be blank?

## Known upstream documentation defects

The developer hub is wrong about its own SDKs in several places. If code disagrees with
`developers.paynow.co.zw` on these, the code in this skill is right:

| Hub says | Reality |
|---|---|
| `paid()` covers the paid states | PHP: `status() === 'paid'` only. Node: no `paid()` at all. |
| `let status = paynow.pollTransaction(url)` | Returns a promise; must be awaited. |
| Initiate response has four fields | Also returns `paynowreference`, which is inside the hash. |
| PHP constructor example | Missing a comma; does not parse. |
| InnBucks scheme `com.innbucks.customer://` | The npm package builds `schinn.wbpycode://`. |
| Link-encoding worked examples | Not reproducible from the documented steps — the published Base64 skips the per-value URL-encode, and the advanced-button example contains a stray space. |
| Shopify listed as a plugin | No self-serve setup — email `sales@paynow.co.zw` before building the store. |
