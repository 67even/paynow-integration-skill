---
title: "Installing the skill"
nav_order: 2
permalink: /install/
description: "Install the Paynow Integration Skill in Claude Code or on claude.ai: where the files go, how to confirm Claude loaded it, and what to ask once it has."
date: 2026-09-20
last_modified_at: 2026-09-20
seo:
  type: WebPage
image:
  path: /assets/og/install.png
  width: 1200
  height: 630
  alt: "Installing the Paynow Integration Skill in Claude Code or on claude.ai"
---

# Installing the skill

This site is the reference. The **skill** is the thing that makes Claude use it —
install it once and Claude reaches for the right answer on its own, instead of
repeating Paynow's documented advice about `paid()` and quietly losing you orders.

Installing takes about a minute. Everything below is optional after that.

## Contents
{: .no_toc }

- TOC
{:toc}

---

## What you are installing

One folder, `paynow-integration`, containing:

| | |
|:---|:---|
| `SKILL.md` | The decision tree and the five money-safety rules. Always loaded. |
| `references/` | Six deep-dive files. Read only when the task needs them, which is what keeps the cost small. |
| `scripts/` | `paynow_hash.py` and `audit_integration.py` — two tools Claude runs against your code. |
| `assets/` | Copy-ready Laravel and Express starter code, with tests. |

No dependencies, no network calls, no telemetry. It is Markdown and two Python
scripts that use only the standard library.

---

## Claude Code

Clone the repository and copy the skill folder into place.

```bash
git clone https://github.com/67even/paynow-integration-skill.git
cd paynow-integration-skill
```

**For one project** — the skill loads only in that repository:

```bash
mkdir -p /path/to/your/project/.claude/skills
cp -r paynow-skills/paynow-integration /path/to/your/project/.claude/skills/
```

**For every project on your machine:**

```bash
mkdir -p ~/.claude/skills
cp -r paynow-skills/paynow-integration ~/.claude/skills/
```

Either way you should end up with a `SKILL.md` at
`<skills-dir>/paynow-integration/SKILL.md`. Start a new Claude Code session and it
is picked up automatically.

{: .warning }
> Don't install it in both places. A personal skill in `~/.claude/skills/`
> **overrides** a project one with the same name, so an old copy in your home
> directory will silently win over a freshly updated copy in the repo — and you
> will be debugging against documentation you already fixed.

---

## Claude.ai, desktop and mobile

Claude on the web and in the desktop app takes a **ZIP**, uploaded once and
available everywhere you are signed in.

```bash
cd paynow-skills
zip -r paynow-integration.zip paynow-integration -x '*/evals/*' -x '*/.DS_Store'
```

Then in Claude: **Customize → Skills → + → Create skill → Upload a skill**, and
choose that file.

{: .warning }
> Zip the **folder**, not its contents. The archive must contain
> `paynow-integration/SKILL.md`, and the folder name has to match the `name:` in
> `SKILL.md`. A zip of loose files at the top level is rejected, and the error
> does not say why.

---

## Confirm Claude actually loaded it

This is the step people skip, and then conclude the skill does not work.

In Claude Code, run:

```text
/skills
```

`paynow-integration` should be listed, with where it came from — personal,
project, plugin or synced from your account. If it is missing, the folder is in
the wrong place or `SKILL.md` is not directly inside it; check that
`ls ~/.claude/skills/paynow-integration/SKILL.md` finds a file.

On claude.ai, the skill appears under **Customize → Skills** with a toggle. It
has to be switched on.

---

## Use it

You do not invoke the skill by name. It has a `description` that tells Claude
when it is relevant, and Claude decides. Ask for what you want:

```text
Add Paynow checkout to my Laravel app — customers mostly pay by EcoCash.

We need InnBucks payments in our Express API. The SDK doesn't seem to support it?

Customers are paying but a chunk of them never get their orders. Here's the controller.

Why is my Paynow hash always mismatching? I'm following the docs exactly.
```

It also fires when you mention **EcoCash, OneMoney, InnBucks, O'mari or Zimswitch**
in a payments context, or ask for a payment gateway in a Zimbabwean app — even if
you never type the word "Paynow".

**Reviewing an integration you already have?** Point Claude at the code and ask.
It runs [`audit_integration.py`](../troubleshooting/) first, which finds in seconds
what takes a careful read to spot.

---

## Prove the code works before you trust it

The skill ships two hashing fixtures that Paynow publishes, and the helpers are
checked against them:

```bash
cd paynow-skills/paynow-integration
python3 scripts/paynow_hash.py selftest           # expect 4/4
cd assets/node-express && node --test             # expect 6/6
```

If a port of the helper into your own language passes those two fixtures, the
single largest class of Paynow bugs is gone. See
[`hashing.md`](../hashing/) for the algorithm and both fixtures in full.

---

## Updating

The skill is versioned with the repository, so updating is re-copying:

```bash
cd paynow-integration-skill && git pull
rm -rf ~/.claude/skills/paynow-integration
cp -r paynow-skills/paynow-integration ~/.claude/skills/
```

On claude.ai, re-zip and upload again — the new version replaces the old one.

To uninstall, delete the folder, or toggle the skill off in **Customize → Skills**.

---

## You don't actually need Claude

Nothing here is locked behind it. The
[reference pages on this site](../raw-http/) are the complete Paynow interface,
the starter code in `assets/` is ordinary PHP and JavaScript, and both scripts run
on their own:

```bash
# Reproduce a hash, or work out why one mismatches
python3 scripts/paynow_hash.py verify --key <integration-key> --data 'status=Paid&hash=...'

# Scan an existing integration for the mistakes that lose money
python3 scripts/audit_integration.py path/to/your/app
```

`audit_integration.py` exits non-zero when it finds something, so it drops
straight into CI.
