"use strict";

/**
 * Express routes for a Paynow integration.
 *
 * The shape that matters: fulfilment happens in exactly one place - the
 * hash-verified callback - and every other route is either starting a payment or
 * reading state that the callback already wrote.
 */

const express = require("express");
const rateLimit = require("express-rate-limit"); // npm i express-rate-limit
const { Paynow } = require("paynow");
const { PaynowHash, isPaid, isTerminal } = require("./paynow-hash");

const app = express();
const hasher = new PaynowHash(process.env.PAYNOW_INTEGRATION_KEY);

app.use(express.json()); // NB: the callback route overrides this — see below

/* ---------- rate limits ----------
 * Three different jobs, so three different ceilings. Getting these backwards
 * is worse than having none: throttle the callback too hard and you drop a real
 * "Paid" notification, which is the exact failure this whole integration is
 * built to avoid.
 *
 * If you run behind a proxy or a CDN, set `app.set("trust proxy", 1)` or every
 * request arrives with the proxy's IP and all your customers share one bucket.
 */

// Starting a payment creates an order and calls Paynow. Unlimited, this is a
// way to run up your own API usage and get your merchant account throttled.
const startPaymentLimit = rateLimit({
  windowMs: 60 * 1000,
  max: 10,
  standardHeaders: true,
  legacyHeaders: false,
  message: { error: "Too many payment attempts. Wait a minute and try again." },
});

// The browser polls this while the customer authorises on their handset, and
// each hit can make an outbound call to Paynow - so it is the easiest route
// here to turn into an amplifier. Generous enough for a 2-3s poll interval.
const statusLimit = rateLimit({
  windowMs: 60 * 1000,
  max: 60,
  standardHeaders: true,
  legacyHeaders: false,
});

// The callback is DELIBERATELY loose. Paynow retries up to ten times per
// transaction and a busy shop can have many in flight at once, all arriving
// from the same handful of Paynow IPs. This ceiling exists to blunt a flood of
// forgeries, not to police Paynow: the hash check below is the real defence,
// and it runs before any database work. Raise it if you process more than a few
// hundred transactions an hour - a 429 here costs you a fulfilled order.
const callbackLimit = rateLimit({
  windowMs: 60 * 1000,
  max: 600,
  standardHeaders: true,
  legacyHeaders: false,
  // A dropped callback is unrecoverable, so say so loudly rather than silently.
  handler: (req, res) => {
    console.error("[paynow] RATE LIMITED a callback - raise callbackLimit.max");
    res.sendStatus(429);
  },
});

function gateway(orderRef) {
  const p = new Paynow(
    process.env.PAYNOW_INTEGRATION_ID,
    process.env.PAYNOW_INTEGRATION_KEY
  );
  p.resultUrl = `${process.env.APP_URL}/paynow/callback`;
  p.returnUrl = `${process.env.APP_URL}/paynow/return?ref=${encodeURIComponent(orderRef)}`;
  return p;
}

/**
 * In test mode only the merchant account that owns the integration can complete a
 * payment - everyone else is told the merchant is in testing. So authemail has to
 * be a merchant login, or you lock yourself out of your own test transactions.
 */
function authEmailFor(customerEmail) {
  return process.env.PAYNOW_TEST_MODE === "true"
    ? process.env.PAYNOW_MERCHANT_EMAIL
    : customerEmail;
}

/* ---------- 1. Start a redirect (web) payment ---------- */
app.post("/checkout/paynow", startPaymentLimit, async (req, res, next) => {
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

    // Persist the poll URL BEFORE responding. It is the only handle on the
    // transaction afterwards.
    await orders.update(order.id, {
      pollUrl: response.pollUrl,
      paymentStatus: "initiated",
    });

    return res.json({ redirectUrl: response.redirectUrl });
  } catch (err) {
    next(err);
  }
});

/* ---------- 2. Start a mobile money payment ---------- */
app.post("/checkout/paynow/mobile", startPaymentLimit, async (req, res, next) => {
  try {
    const { phone, method } = req.body; // 'ecocash' | 'onemoney'
    const order = await orders.create(req.body);
    const paynow = gateway(order.reference);

    const payment = paynow.createPayment(order.reference, authEmailFor(order.email));
    for (const item of order.items) {
      payment.add(item.name, Number((item.price * item.qty).toFixed(2)));
    }

    const response = await paynow.sendMobile(payment, phone, method);

    if (!response.success) {
      // Insufficient balance fails HERE. A user cancellation initiates fine and
      // only fails later via the status update — handle both.
      return res.status(402).json({ error: response.error });
    }

    await orders.update(order.id, {
      pollUrl: response.pollUrl,
      paymentStatus: "awaiting_authorisation",
    });

    return res.json({
      reference: order.reference,
      instructions: response.instructions, // render verbatim
    });
  } catch (err) {
    next(err);
  }
});

/* ---------- 3. Status update callback (resultUrl) ---------- */
/**
 * express.raw on THIS route only. The hash depends on field order; a parsed object
 * usually preserves insertion order in V8, but "usually" is a poor foundation for
 * payment verification. express.json() stays on for everything else.
 */
app.post("/paynow/callback", callbackLimit, express.raw({ type: "*/*" }), async (req, res) => {
  const fields = PaynowHash.parseResponse(req.body.toString("utf8"));

  if (!hasher.verify(fields)) {
    // This URL is public by definition. Anyone who finds it can POST a fake
    // "Paid" — the hash is the only thing standing in the way.
    console.warn("[paynow] REJECTED callback: bad hash");
    return res.sendStatus(400);
  }

  const f = {};
  for (const [k, v] of fields) f[k.toLowerCase()] = v;

  const order = await orders.findByReference(f.reference);
  if (!order) {
    console.warn("[paynow] unknown reference", f.reference);
    return res.sendStatus(200); // 200, not 404: a non-2xx triggers ten retries
  }

  if (isPaid(f.status)) {
    if (order.fulfilled) return res.sendStatus(200); // idempotent

    if (Math.abs(Number(f.amount) - Number(order.total)) > 0.001) {
      console.error("[paynow] AMOUNT MISMATCH", f.reference, f.amount, order.total);
      await orders.flagForReview(order.id);
      return res.sendStatus(200);
    }

    await orders.markPaid(order.id, f.paynowreference, f.status);
    await queue.add("fulfil-order", { orderId: order.id }); // slow work off the request
  } else if (isTerminal(f.status)) {
    await orders.markTerminal(order.id, f.status);
  } else {
    await orders.touchStatus(order.id, f.status); // Created / Sent
  }

  return res.sendStatus(200);
});

/* ---------- 4. Browser return URL — cosmetic only ---------- */
/**
 * The customer's browser lands here, which proves nothing: they may have
 * abandoned the payment, or typed the URL. Render current state, fulfil nothing.
 */
app.get("/paynow/return", async (req, res) => {
  const order = await orders.findByReference(req.query.ref);
  if (!order) return res.status(404).send("Unknown order");
  res.render("checkout/thanks", { order });
});

/* ---------- 5. Front-end status endpoint ---------- */
/**
 * The browser polls this, never Paynow directly: exposing the poll URL leaks a
 * transaction handle into the page and invites tampering.
 */
app.get("/paynow/status/:ref", statusLimit, async (req, res) => {
  const order = await orders.findByReference(req.params.ref);
  if (!order) return res.sendStatus(404);

  if (!order.fulfilled && order.pollUrl) {
    const paynow = gateway(order.reference);

    // Must be awaited, and there is no .paid() on the result — the published
    // quickstart is wrong on both counts.
    const r = await paynow.pollTransaction(order.pollUrl);

    if (isPaid(r.status) && !order.fulfilled) {
      await orders.markPaid(order.id, null, r.status);
      await queue.add("fulfil-order", { orderId: order.id });
    }
  }

  const fresh = await orders.findByReference(req.params.ref);
  res.json({ status: fresh.paymentStatus, paid: fresh.fulfilled });
});

module.exports = app;
