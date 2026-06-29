---
name: blueprint-release-rollout
description: >-
  Attach the right end-user rollout note whenever a PR or GitHub Release for this
  repo changes a file under blueprints/**. From the auto-install build (v0.2.1+) the
  blueprint ships inside the integration and updates itself on restart, so the note is
  short; a legacy manual re-import fallback is kept for users still on <= v0.1.x. Use
  when asked to "open a PR" / "cut a release" / "write release notes" / "draft the PR
  body" and the diff touches blueprints/**, or when reminding a user what to do after
  an update that changed a blueprint.
---

# Blueprint release rollout

**As of the auto-install build (v0.2.1+), the blueprint is bundled inside the integration
and written to `/config/blueprints/automation/vmyronovych/` on startup** (see
`custom_components/waveshare_relay/blueprint.py`). So a normal **HACS update + restart
delivers blueprint fixes automatically** — there is no manual re-import in the common case.

**Lead with the consumer, then go technical.** Every PR body and release note must be
ordered **non-technical first**: open with a plain-language description of *the problem this
release solves for the user* and the outcome they get (no jargon, no file names), then the
how-to-apply link — and only **after** that, a separate `## Technical details` section
(summary of changes, verification) for engineers. The bilingual rollout blocks below are the
consumer-first part and go at the **top**; the technical detail goes underneath.

What the consumer-first rollout note must convey now:

- **The problem and the outcome in plain words** — what was wrong / what gets better, framed
  for a homeowner or installer, not a developer.
- **Update the integration in HACS and restart HA. That's it** — the new blueprint installs
  itself on restart; automations keep their inputs and need no changes.
- **User edits are safe.** The installer uses a smart overwrite: it only replaces a copy the
  user hasn't touched (backing the old one up to `*.bak` first). If the user edited their
  blueprint, it is **left alone** and a **Repairs issue** appears instead — never clobbered.
- **To customize and still get updates:** copy the blueprint to your own name/path and build
  automations from that copy (a private path is never overwritten).

## Legacy fallback (users still on ≤ v0.1.x, before auto-install)

Those builds don't auto-install, so the blueprint is a **separate imported copy** and a fix
is **not active until they re-import** — and the UI's **"Re-import" button re-fetches the old
pinned `source_url`**, so it pulls the pre-fix file (the bug PR #2 hit). For that audience the
note must say: **Import Blueprint using the NEW tag's URL and confirm Overwrite** — never
"just re-import". These manual steps now live in **`UPGRADING.md`** (§4), which every
release note links to — they are not repeated inline.

What's safe to state either way: automations reference the blueprint by **path** and store
their **own inputs** in `automations.yaml`, so overwriting the template never touches them.
Never recommend delete + re-add (HA blocks deleting an in-use blueprint).

## Required layout (do not drop any of these)

The rollout section the user receives **must**:

1. Come **first**, at the top of the PR body / release notes (before any technical
   section). It is the consumer-facing part.
2. Be **two root-level collapsible `<details>` blocks, one per language, Ukrainian first**
   (`<details open>`) and English second (`<details>`). GitHub-Flavored Markdown has no
   tabs; `<details>` is the native equivalent. There is **no** shared summary outside the
   blocks — a reader opens one block and has everything in their language.
3. Contain, in each block: (a) the release's **plain-language problem + outcome** in that
   language (what gets better for the user, no jargon), then (b) a **link to the
   `UPGRADING.md` upgrade guide** for how to apply. The how-to-apply *steps* are not repeated
   in the note — they live in the canonical `UPGRADING.md` (which also holds the ≤ v0.1.x
   manual-import fallback). **Every release note and PR body must carry this link.**
4. Be followed by a `## Technical details` section (summary of changes + verification) for
   engineers — never above the consumer blocks.

`rollout-snippet.md` encodes this; fill only `<SUMMARY_UA>` / `<SUMMARY_EN>` with the
per-release issue text in each language. If you edit the snippet, preserve the layout and
the upgrade-guide link.

## What to do

When the diff (PR) or the release contents (since the previous tag) touch `blueprints/**`:

1. Confirm it: `git diff --name-only <base>..<head> -- 'blueprints/**'` (PR) or
   `git diff --name-only <prev_tag>..<new_tag> -- 'blueprints/**'` (release).
2. **Resync the bundled copy** so the shipped blueprint matches the canonical one (the CI
   `blueprints in sync` check enforces this):
   ```sh
   cp blueprints/automation/vmyronovych/oselia_button_to_relay.yaml \
      custom_components/waveshare_relay/blueprints/automation/vmyronovych/oselia_button_to_relay.yaml
   ```
3. Take the canonical text from [`rollout-snippet.md`](rollout-snippet.md) and fill only
   `<SUMMARY_UA>` / `<SUMMARY_EN>` (the issue/fix summary in each language). Paste it
   **whole** — it already is the two `<details>` blocks plus the `UPGRADING.md` link.
   - **PR body:** paste the filled snippet as its own section.
   - **Release notes:** paste it into the body (`gh release create --generate-notes` won't
     add it — append it yourself, or `gh release edit vX.Y.Z --notes-file …`).
4. If the release changes *how updates work* (not just this fix), update **`UPGRADING.md`**
   too — it is the single source of the apply steps every release links to.
5. Sanity-check (if you have container access): after restart the file at
   `/config/blueprints/automation/vmyronovych/oselia_button_to_relay.yaml` matches the
   shipped one, and `.storage/waveshare_relay_blueprints` recorded its sha.

## Keep it consistent

`rollout-snippet.md` is the single source of the user-facing wording — edit it there, not
inline, so PR bodies and release notes never drift. This mirrors the human-facing
`RELEASING.md` / `ROLLOUT.md` docs in the repo root.
