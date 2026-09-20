"use strict";

/**
 * Raw Paynow client for the Express Checkout methods the SDK does not wrap:
 * InnBucks, O'mari, Zimswitch and card tokens.
 *
 * The whole point of building the fields as a Map is that insertion order IS the
 * hash. Anything that reorders them - a plain object with numeric-ish keys, a
 * helper that sorts, a spread that merges - silently breaks every request.
 */

const crypto = require("crypto");
const { PaynowHash } = require("./paynow-hash");

const ENDPOINTS = {
  initiate: "https://www.paynow.co.zw/interface/initiatetransaction",
  remote: "https://www.paynow.co.zw/interface/remotetransaction",
  trace: "https://www.paynow.co.zw/interface/trace",
};

/** Unique per REQUEST, not per order: it is what prevents a duplicate debit on retry. */
const newMerchantTrace = () => crypto.randomUUID().replace(/-/g, "");

class PaynowRawClient {
  constructor(integrationId, integrationKey) {
    this.id = integrationId;
    this.key = integrationKey;
    this.hasher = new PaynowHash(integrationKey);
  }

  /**
   * Express Checkout. Method-specific extras (phone, token) go in `extra` and are
   * appended in the order given.
   */
  async remote({
    reference,
    amount,
    returnUrl,
    resultUrl,
    authEmail,
    method,
    merchantTrace = newMerchantTrace(),
    ...extra
  }) {
    const fields = new Map();
    fields.set("id", this.id);
    fields.set("reference", reference);
    fields.set("amount", Number(amount).toFixed(2)); // two decimals, no symbol
    fields.set("returnurl", returnUrl);
    fields.set("resulturl", resultUrl);
    fields.set("authemail", authEmail); // required for all Express Checkout
    fields.set("method", method); // zimswitch|vmc|ecocash|onemoney|innbucks|omari
    fields.set("merchanttrace", merchantTrace);

    for (const [k, v] of Object.entries(extra)) {
      if (v !== undefined && v !== null) fields.set(k, String(v));
    }

    fields.set("status", "Message");
    fields.set("hash", this.hasher.generate(fields));

    const result = await this.#post(ENDPOINTS.remote, fields);
    return { ...result, merchanttrace: merchantTrace };
  }

  /** Complete an O'mari payment. Five wrong OTPs cancels the transaction for good. */
  async submitOmariOtp(remoteOtpUrl, otp) {
    const fields = new Map();
    fields.set("id", this.id);
    fields.set("otp", otp);
    fields.set("status", "Message");
    fields.set("hash", this.hasher.generate(fields));
    return this.#post(remoteOtpUrl, fields);
  }

  /** Empty POST to the poll URL. */
  async poll(pollUrl) {
    return this.#post(pollUrl, new Map());
  }

  /**
   * Recover a transaction whose response you never received.
   *
   * A trace ERROR does not mean the transaction is absent - retry rather than
   * concluding anything, and never auto-refund or re-charge off one.
   */
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

    // Responses are URL-encoded query strings, never JSON.
    const parsed = PaynowHash.parseResponse(await res.text());

    const lower = {};
    for (const [k, v] of parsed) lower[k.toLowerCase()] = v;

    if (lower.status === "Error") {
      const err = new Error(`Paynow error: ${lower.error ?? "unknown"}`);
      err.paynow = lower;
      throw err;
    }

    // Verify against the ORIGINAL ordered parse, not the lower-cased copy.
    if (!this.hasher.verify(parsed)) {
      throw new Error("Paynow hash verification FAILED - response rejected.");
    }

    return lower;
  }
}

/**
 * InnBucks presentation helper.
 *
 * Two deep-link schemes are in circulation and they disagree: the hub documents
 * `com.innbucks.customer://`, the npm package builds `schinn.wbpycode://`. Offer
 * the SDK's as primary and the documented one as fallback, and keep the QR as the
 * primary path in the UI - it works whichever scheme the installed app registered.
 *
 * Generate the QR locally (`npm install qrcode`). Do not hand an authorization
 * code to a third-party chart API: it lands in someone else's access logs, and
 * the Google endpoint older examples use is deprecated.
 */
function innbucksPresentation(response) {
  const code = response.authorizationcode;
  return {
    code,
    expires: response.authorizationexpires, // "d-MMM-yyyy HH:mm" — show this
    deepLinkPrimary:
      response.innbucks_info?.[0]?.deep_link_url ??
      `schinn.wbpycode://innbucks.co.zw?pymInnCode=${code}`,
    deepLinkFallback: `com.innbucks.customer://purchase?paymentToken=${code}`,
    // const qrDataUri = await require("qrcode").toDataURL(code, { width: 250 });
  };
}

module.exports = { PaynowRawClient, innbucksPresentation, newMerchantTrace, ENDPOINTS };
