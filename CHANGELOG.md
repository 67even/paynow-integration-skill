# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [1.0.0] — 2026-09-20

First release.

### Added

- `paynow-integration` skill: `SKILL.md`, six reference files, two executable
  scripts, and copy-ready PHP/Laravel and Node/Express starter code.
- `scripts/paynow_hash.py` — generate, verify and debug Paynow hashes from the
  command line; self-tests against both published fixtures.
- `scripts/audit_integration.py` — scan a codebase for the integration mistakes
  that lose money.
- `PAYNOW.md` — full corrected API reference, including Appendix E documenting
  where the official developer hub is wrong about its own SDKs.
- Test suites in three languages, all passing: PHPUnit (5 cases), `node --test`
  (6 cases), Python `selftest` (4 cases).

### Fixed

- **Hash helpers did not lower-case the integration key.** Both official SDKs do
  (`paynow/php-sdk` in its constructor and in `initiateTransaction()`, npm
  `paynow` inside `generateHash()`). Every key Paynow publishes is already
  lower-case, so the helpers passed all documented fixtures and would have failed
  on a real upper-cased key. Regression tests added in all three languages.
- `audit_integration.py` reported its own detection patterns as findings when
  scanning a directory containing itself.
- `references/raw-http.md` carried the InnBucks `authorizationexpires` format
  without a source. Confirmed as `d-MMM-yyyy HH:mm` against the live docs, with a
  note that Paynow specifies no timezone.

### Verified

- PHP helper agrees with `paynow/php-sdk` `Hash::make` on 1,006 inputs.
- Node helper agrees with npm `paynow` `generateHash` on 1,005 inputs.
- PHP and Node helpers produce identical digests for the same input.
- Auditor: 0 findings on the shipped assets, 4 and 5 findings on deliberately
  broken PHP and Express fixtures.

See [`paynow-skills/VERIFICATION.md`](paynow-skills/VERIFICATION.md) for the full record.
