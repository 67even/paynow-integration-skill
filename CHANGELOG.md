# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- Documentation site at <https://67even.github.io/paynow-integration-skill/>,
  built with [just-the-docs](https://github.com/just-the-docs/just-the-docs) on a
  67even dark theme whose palette is derived from the logo (`#FF3131` on
  `#0C0E0B`). Full-text search, a stars badge, and `SoftwareSourceCode`
  structured data.
- `tools/check_docs_site.py` — validates the Jekyll configuration without a Ruby
  toolchain, and runs in CI. GitHub Pages does not fail loudly on a bad config;
  this catches a missing default layout, a `_layouts/` override shadowing the
  theme, a `color_scheme` with no matching `_sass` file, a page missing front
  matter, and a referenced logo or favicon that was never committed.

### Changed

- `tools/check_links.py` now also checks raw HTML `src` and `href` attributes,
  skipping targets that contain Liquid. The README's Paynow button and the docs
  hero images were previously unchecked.
- The README links to the documentation site.

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
