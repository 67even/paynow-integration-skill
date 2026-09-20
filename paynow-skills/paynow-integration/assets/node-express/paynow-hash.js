"use strict";

const crypto = require("crypto");

/**
 * SHA-512 hashing for Paynow messages.
 *
 * Two things make Paynow hashes fail in practice, and both are handled here:
 * field ORDER (the digest depends on it, so a Map is used rather than a plain
 * object) and COMPLETENESS (Paynow returns fields the docs don't list -
 * paynowreference is a common one - and they are part of the digest, so never
 * hash a fixed list).
 *
 * Proven against Paynow's two published fixtures - see paynow-hash.test.js.
 */
class PaynowHash {
  constructor(integrationKey) {
    if (!integrationKey) {
      throw new Error("PaynowHash requires an integration key");
    }
    // Lower-cased to match both official SDKs: the PHP SDK does it in its
    // constructor, the Node SDK inside generateHash(). Paynow's published keys
    // are lower-case, so skipping this works in every example and then fails on
    // a real upper-cased key.
    this.integrationKey = String(integrationKey).toLowerCase();
  }

  /** API hash: join VALUES in order, excluding `hash`. */
  generate(values) {
    const entries = values instanceof Map ? [...values] : Object.entries(values);
    const concat =
      entries
        .filter(([k]) => k.toUpperCase() !== "HASH")
        .map(([, v]) => String(v))
        .join("") + this.integrationKey;

    return crypto.createHash("sha512").update(concat, "utf8").digest("hex").toUpperCase();
  }

  /** values: already URL-decoded fields of an inbound message, in arrival order. */
  verify(values) {
    const entries = values instanceof Map ? [...values] : Object.entries(values);
    const found = entries.find(([k]) => k.toUpperCase() === "HASH");
    if (!found) return false;

    const expected = Buffer.from(this.generate(values));
    const actual = Buffer.from(String(found[1]).toUpperCase());

    // Length check first: timingSafeEqual throws on a length mismatch.
    return expected.length === actual.length && crypto.timingSafeEqual(expected, actual);
  }

  /**
   * Parse "a=1&b=2" into an ORDERED Map of decoded values.
   *
   * A Map rather than an object because it preserves insertion order for every
   * key shape - plain objects reorder numeric-looking keys, and the digest
   * depends on order.
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

  /**
   * Verify a Links & Buttons Notification URL POST.
   * Different algorithm on purpose: key+value, not values alone.
   */
  static verifyNotification(body, integrationKey) {
    let concat = "";
    let received = null;

    for (const [key, value] of Object.entries(body)) {
      if (key.toLowerCase() === "hash") {
        received = String(value);
        continue;
      }
      concat += key + String(value);
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
}

/**
 * All three mean the customer's money has arrived. Awaiting Delivery is held in
 * suspense until the merchant confirms delivery; Delivered is inside the 24-hour
 * confirmation window.
 *
 * The published Node quickstart shows `status.paid()` - that method does not
 * exist in the package and calling it throws. This set is the replacement.
 */
const PAID = new Set(["Paid", "Awaiting Delivery", "Delivered"]);
const TERMINAL = new Set(["Cancelled", "Refunded", "Disputed"]);

const isPaid = (status) => PAID.has(String(status));
const isTerminal = (status) => TERMINAL.has(String(status));

module.exports = { PaynowHash, PAID, TERMINAL, isPaid, isTerminal };
