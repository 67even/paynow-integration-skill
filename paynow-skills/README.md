# paynow-skills

The Claude skill itself lives in [`paynow-integration/`](paynow-integration/) — that
folder is what you copy into your skills directory.

For installation, supported languages, usage and benchmarks, see the
[main README](../README.md). This file is the map of what's in here.

## Layout

```
paynow-integration/          ← install this folder
├── SKILL.md                 Decision tree + the five money-safety rules
├── references/              Loaded on demand, only when the task needs them
│   ├── hashing.md                   SHA-512 algorithm, both published fixtures, pitfalls
│   ├── php-laravel.md               SDK surface, the exceptions it throws, Laravel wiring
│   ├── nodejs-express.md            SDK surface and its defects, raw client, callback route
│   ├── raw-http.md                  Endpoints and field tables for any language
│   ├── testing-and-golive.md        Test credentials, the test matrix, go-live checklist
│   └── troubleshooting.md           Symptom → cause table
├── scripts/
│   ├── paynow_hash.py               Generate / verify / debug hashes; self-tests the algorithm
│   └── audit_integration.py         Scan a codebase for the money-losing mistakes
├── assets/
│   ├── php-laravel/                 Hash helper, gateway service, controller, routes,
│   │                                config, migration, PHPUnit tests, env template
│   └── node-express/                Hash helper, raw Express Checkout client, Express
│                                    routes, node:test suite, env template
└── evals/evals.json         Test prompts and assertions used to verify the skill
```

`VERIFICATION.md` in this folder records what was executed to verify all of it, the
defect that verification found, and what the checks do **not** prove.

## Quick check that it works

```bash
python3 paynow-integration/scripts/paynow_hash.py selftest          # 4/4 expected
cd paynow-integration/assets/node-express && node --test            # 6/6 expected
```

Both exercise the two hashing fixtures Paynow publishes. A port of the helper into any
other language that passes those has eliminated the largest single class of Paynow bugs.

## How the skill is structured, and why

`SKILL.md` stays under 200 lines because it is loaded into context every time the skill
triggers. It carries only the decision tree and the five rules that decide whether an
integration loses money.

Everything else is a reference file loaded on demand. A question about test phone
numbers should not drag in the hashing algorithm, and a hash mismatch should not drag in
the go-live checklist. The `SKILL.md` table says which file answers which kind of
question.

The starter code in `assets/` is written to be adapted rather than pasted. It carries
comments explaining *why* each guard is there, because a guard whose purpose is not
understood is a guard that gets removed in the next refactor.
