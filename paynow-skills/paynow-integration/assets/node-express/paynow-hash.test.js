"use strict";

/**
 * Paynow's two published fixtures, plus the behaviour that costs money.
 * Run with `node --test`.
 *
 * Write these before anything else: a hashing helper proven against the fixtures
 * removes the largest single class of Paynow bugs, and the Awaiting Delivery case
 * is the one that otherwise only shows up in production.
 */
const test = require("node:test");
const assert = require("node:assert");
const { PaynowHash, isPaid } = require("./paynow-hash");

// Paynow publishes this key in its own hashing examples. Not a secret.
const KEY = "3e9fed89-60e1-4ce5-ab6e-6b1eb2d4f977";

test("outbound fixture", () => {
  const hash = new PaynowHash(KEY).generate({
    id: "1201",
    reference: "TEST REF",
    amount: "99.99",
    additionalinfo: "A test ticket transaction",
    returnurl: "http://www.google.com/search?q=returnurl",
    resulturl: "http://www.google.com/search?q=resulturl",
    status: "Message",
  });

  assert.strictEqual(
    hash,
    "2A033FC38798D913D42ECB786B9B19645ADEDBDE788862032F1BD82CF3B92DEF" +
      "84F316385D5B40DBB35F1A4FD7D5BFE73835174136463CDD48C9366B0749C689"
  );
});

test("inbound fixture verifies", () => {
  const body =
    "status=Ok" +
    "&browserurl=https%3a%2f%2fstaging.paynow.co.zw%2fPayment%2fConfirmPayment%2f9510" +
    "&pollurl=https%3a%2f%2fstaging.paynow.co.zw%2fInterface%2fCheckPayment%2f" +
    "%3fguid%3dc7ed41da-0159-46da-b428-69549f770413" +
    "&paynowreference=9510" +
    "&hash=750DD0B0DF374678707BB5AF915AF81C228B9058AD57BB7120569EC68BBB9C2E" +
    "FC1B26C6375D2BC562AC909B3CD6B2AF1D42E1A5E479FFAC8F4FB3FDCE71DF4D";

  assert.ok(new PaynowHash(KEY).verify(PaynowHash.parseResponse(body)));
});

test("a tampered message is rejected", () => {
  const body = "status=Ok&amount=1.00&hash=DEADBEEF";
  assert.strictEqual(new PaynowHash(KEY).verify(PaynowHash.parseResponse(body)), false);
});

test("parseResponse preserves arrival order", () => {
  const map = PaynowHash.parseResponse("b=2&a=1&1=one&hash=X");
  assert.deepStrictEqual([...map.keys()], ["b", "a", "1", "hash"]);
});

// Both official SDKs lower-case the integration key before hashing. Paynow's
// published keys are already lower-case, so a helper that skips this passes every
// documented fixture and then fails on a real upper-cased key.
test("key case does not change the digest", () => {
  const fields = { id: "1201", reference: "TEST REF", status: "Message" };
  assert.strictEqual(
    new PaynowHash(KEY).generate(fields),
    new PaynowHash(KEY.toUpperCase()).generate(fields)
  );
});

// The one that matters. Awaiting Delivery means the customer HAS paid - Paynow is
// holding funds until delivery is confirmed. Treating it as unpaid strands real
// orders, which is exactly what the docs' `status.paid()` would do if it existed.
test("all three paid states count as paid", () => {
  for (const s of ["Paid", "Awaiting Delivery", "Delivered"]) {
    assert.ok(isPaid(s), `${s} should count as paid`);
  }
  for (const s of ["Created", "Sent", "Cancelled", "Refunded", "Disputed"]) {
    assert.strictEqual(isPaid(s), false, `${s} should not count as paid`);
  }
});
