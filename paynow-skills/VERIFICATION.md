# Verification record — 20 September 2026

Everything in this folder was verified by execution, not by inspection. This file records
what was actually run, so the next person does not have to take it on trust.

## Defect found and fixed during verification

**The hash helpers did not lower-case the integration key.** Both official SDKs do:
`paynow/php-sdk` in its constructor (`$this->integrationKey = strtolower($key)`) and again
in `initiateTransaction()`, and npm `paynow` inside `generateHash()`
(`string += integrationKey.toLowerCase()`).

Every integration key Paynow publishes is already lower-case, so the helpers reproduced
all the documented fixtures correctly and would have failed the first time a merchant's
key arrived upper-cased — with a hash mismatch that looks exactly like a wrong key.

Fixed in `PaynowHash.php`, `paynow-hash.js`, `paynow_hash.py`, `references/hashing.md`,
and in `PAYNOW.md` §6.1/§6.4/§6.5/§7.4, with a regression test added in all three
languages (`test_key_case_does_not_change_the_digest` / `"key case does not change the
digest"` / the `selftest` third case).

Two smaller fixes: the auditor was flagging its own detection patterns when it scanned a
directory containing itself (now skips its own file), and `references/raw-http.md` carried
the InnBucks expiry format without a source.

## What was executed

| # | Check | Result |
|---|---|---|
| 1 | `php -l` on all 8 PHP assets (PHP 8.4) | 8/8 parse |
| 2 | PHP hash helper run against both published fixtures + 11 edge cases (tampering, wrong key, missing hash, lower-cased received hash, a value containing a space, a literal `+`, the notification key+value algorithm) | 13/13 |
| 3 | PHP helper vs the real `paynow/php-sdk` `Hash::make` over 6 hand-written + 1000 random field sets | 1006 agree, 0 disagree |
| 4 | `node --check` on all 4 JS assets; `node --test` | 4/4 parse, 6/6 tests |
| 5 | JS helper vs the real npm `paynow` `generateHash` over 5 + 1000 random field sets, plus a cross-language check that JS and PHP produce the same digest | 1005 agree, 0 disagree |
| 6 | `paynow_hash.py selftest` | 4/4 |
| 7 | `paynow_hash.py` CLI: verify a real fixture, non-zero exit on a bad hash | correct |
| 8 | Auditor precision: clean run on the good PHP assets, the good Node assets, and the skill directory itself | 0 findings each |
| 9 | Auditor recall: a deliberately broken PHP controller and a deliberately broken Express route | 4 and 5 findings, all correct |
| 10 | 37 structural checks — frontmatter, every referenced path exists, every in-file markdown anchor resolves, fixture constants identical across files, no stray digests, paid-state sets consistent, endpoint URLs consistent, no `paid()` gate or `parse_str` in shipped code, `evals.json` well-formed | all clean |
| 11 | Packaged `.skill` zip integrity and `SKILL.md` byte-identical to source | OK |

## Claims checked against primary sources

- **`authorizationexpires` format** — previously unevidenced. Confirmed from the live
  Express Checkout page: *"in the format `d-MMM-yyyy HH:mm`"*. Paynow specifies **no
  timezone**, so the reference now says to parse the documented format but not to expire
  codes client-side on a guessed offset.
- **All three paid states** — Paynow's own worked example of a *successful* O'mari payment
  carries `status=Awaiting+Delivery`, which is the cleanest available evidence that
  `paid()` gating loses real orders. Now quoted in `SKILL.md`.
- **InnBucks deep link** — the hub documents `com.innbucks.customer://`, the npm package
  builds `schinn.wbpycode://`. Still contradictory upstream; the skill ships the SDK's as
  primary and the documented one as fallback, and says why.

## Benchmark, re-graded

The first assertion set was too easy — several assertions passed on a comment, or on the
mere absence of a bad pattern. Tightened from 23 to 34 assertions and the six existing runs
were re-graded against the stricter bar.

| | With skill | Without |
|---|---|---|
| Assertions passed | **34/34** | 24/34 (71%) |
| Mean wall-clock | 377s | 468s |
| Mean tokens | 143,215 | 121,370 |

**Correction:** the first benchmark reported the skill using ~6k *fewer* tokens. That was
wrong — the aggregator had not found the run directories and fell back to bad data. The
skill costs about **21.8k more tokens** per task, which is what reading reference files
should cost. It is 91s faster in wall clock, because it reads a known answer rather than
inferring one.

## What this does not prove

No request has ever been sent to Paynow from this code. Everything above is offline:
algorithm agreement with the official SDKs, structural correctness, and the behaviour of
the tooling. Before going live, run the test matrix in
`paynow-integration/references/testing-and-golive.md` against a real integration in test
mode — in particular the `Awaiting Delivery` callback and the duplicate-callback case,
which are the two that catch what offline testing cannot.
