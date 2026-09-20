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
- Open Graph cards for every page (`tools/build_og_images.py`), rendered at
  1200×630 with headless Chromium from the 67even palette, so a shared link
  shows a card instead of a bare URL. Wired through `jekyll-seo-tag`, which
  turns them into `og:image` and a `summary_large_image` Twitter card.
- Structured data Google still surfaces: `BreadcrumbList` on every page and
  `TechArticle` on each reference page, plus `Organization` and
  `SoftwareSourceCode` for entity matching. Deliberately no `FAQPage` or
  `HowTo` — Google retired both, so that markup would render nothing.
- `robots` directives with `max-image-preview:large` and `max-snippet:-1`,
  which `jekyll-seo-tag` does not emit, and an explicit `docs/robots.txt`.
- `last_modified_at` on every page, published as `<lastmod>` in the sitemap and
  as `dateModified` in the structured data. The date only moves when the page
  content actually changes, so `build_docs.py --check` stays green.
- `tools/check_structured_data.py` and `tools/check_meta_tags.py`, both run
  against the *rendered* site by a new CI job that builds it with Jekyll.
  Structured data fails silently — a stray comma out of Liquid and Google drops
  the block with nothing visibly wrong — so checking the template is not enough.
- An **Installing the skill** page on the documentation site, second in the
  sidebar. The repository shipped a skill that the site never explained how to
  install: where the files go for Claude Code and for claude.ai, how to confirm
  Claude actually loaded it with `/skills`, what to ask once it has, and how to
  update or remove it.

### Fixed

- **`PAYNOW.md` contradicted itself in four places, each one telling the reader to
  do exactly what the rest of the repository classifies as a CRITICAL or HIGH
  mistake.** §1 said to parse responses with `parse_str()` / `querystring.parse()`
  and then URL-decode — §6.4, `hashing.md` and the auditor all forbid it, and it
  double-decodes. §3.8 said payment is "confirmed by `paid()` on a poll", six lines
  under the row explaining that `paid()` is false for `Awaiting Delivery`. The §9.3
  Node troubleshooting table prescribed `express.urlencoded` on the callback route,
  where §10.4 and every shipped file use `express.raw`. The §10.2 callback recipe
  polled a URL taken from the request body, which the project's own evals mark as
  a failure.
- The Laravel starter stored a locally generated `merchant_trace` that was never
  sent to Paynow — the PHP SDK's `sendMobile()` has no `merchanttrace` parameter.
  It looked like a recovery handle while `/interface/trace` would answer
  `NotFound`. The column is now left null on the SDK path, and the reference, the
  migration comment and the go-live checklist say why and what to do instead.
- `docs/install.md` documented `paynow_hash.py verify --data`; the flag is
  `--body`, so the command a new user copies first exited 2. The same page said
  the auditor "exits non-zero when it finds something" — it exits 1 only on
  CRITICAL or HIGH, so a CI built on that sentence would pass MEDIUM findings its
  author expected to block.
- `docs/index.md`'s quick-start `cd`-ed nowhere, so its own next command could not
  find the scripts.
- `references/php-laravel.md` listed four controller actions; there are five, and
  it named `return` rather than `returnFromPaynow`, dropping the mobile-money
  action entirely.
- The README called Appendix E "the nine places the official hub is wrong" — row 8
  records a hub statement that is **true**, and the README's own summary table
  lists eight.
- The README's repository tree omitted `NOTICE`, `docs/`, `tools/`, `assets/` and
  `.github/` — roughly half the repository — and nothing explained that `docs/` is
  generated. `.gitignore` pointed at `scripts/package_skill.py`, which has never
  existed.
- `VERIFICATION.md` presented every check as reproducible. Three needed the real
  `paynow/php-sdk` and npm `paynow` installed plus fixtures that were never
  committed; it now says which rows re-run from a clean clone and which do not.

- Every page was rendering without an `<h1>`. `build_docs.py` stripped the source
  heading on the assumption that just-the-docs renders `page.title` as one — its
  default layout emits `{{ content }}` and nothing else, so the pages simply had
  none. The heading is now restated from the page title, so the `<h1>`, the
  `<title>` and the sidebar label all agree. `check_meta_tags.py` fails the build
  if a page ever has zero or more than one.
- The README described installing the packaged bundle by attaching a `.skill`
  file and clicking "Save skill". It is a ZIP, uploaded through
  **Customize → Skills**.

- Google Search Console verification on the entry page. The token sits in
  `docs/_config.yml`; `check_meta_tags.py` fails the build if the tag ever goes
  missing, because Google re-checks it and quietly un-verifies the property.

### Security

- Rate limiting on the Express example routes (`express-rate-limit`). Starting a
  payment creates an order and calls Paynow, and the status route can call
  Paynow on every hit, so leaving either unlimited hands a stranger a way to run
  up your API usage. The callback's ceiling is deliberately far looser — Paynow
  retries up to ten times per transaction and a `429` there costs a fulfilled
  order, so the hash check remains the real defence on that route.
- `audit_integration.py` matched `chart.googleapis.com` as a bare substring, so
  a look-alike host such as `chart.googleapis.com.evil.test` would have matched
  it. The host is now anchored at both ends.
- `tests.yml` declares `permissions: contents: read`. Without it every job ran
  with whatever the repository default grants, which is usually far more.

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
