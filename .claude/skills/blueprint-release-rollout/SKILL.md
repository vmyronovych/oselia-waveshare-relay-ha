---
name: blueprint-release-rollout
description: >-
  Attach the right end-user rollout note whenever a PR or GitHub Release for this
  repo changes a file under blueprints/**. From the auto-install build (v0.2.0+) the
  blueprint ships inside the integration and updates itself on restart, so the note is
  short; a legacy manual re-import fallback is kept for users still on <= v0.1.x. Use
  when asked to "open a PR" / "cut a release" / "write release notes" / "draft the PR
  body" and the diff touches blueprints/**, or when reminding a user what to do after
  an update that changed a blueprint.
---

# Blueprint release rollout

**As of the auto-install build (v0.2.0+), the blueprint is bundled inside the integration
and written to `/config/blueprints/automation/vmyronovych/` on startup** (see
`custom_components/waveshare_relay/blueprint.py`). So a normal **HACS update + restart
delivers blueprint fixes automatically** — there is no manual re-import in the common case.

What the rollout note must convey now:

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
"just re-import". This lives as a collapsed fallback inside the snippet; keep it.

What's safe to state either way: automations reference the blueprint by **path** and store
their **own inputs** in `automations.yaml`, so overwriting the template never touches them.
Never recommend delete + re-add (HA blocks deleting an in-use blueprint).

## Required layout (do not drop any of these)

The rollout section the user receives **must**:

1. Be **two root-level collapsible `<details>` blocks, one per language, Ukrainian first**
   (`<details open>`) and English second (`<details>`). GitHub-Flavored Markdown has no
   tabs; `<details>` is the native equivalent. There is **no** shared summary outside the
   blocks — a reader opens one block and has everything in their language.
2. Make **each block fully self-contained**, in this order: (a) the release's **issue/fix
   summary** in that language, (b) the **auto-delivery apply steps** (update + restart) in
   that language, (c) a nested collapsed **legacy manual-import fallback** for ≤ v0.1.x.

`rollout-snippet.md` encodes all of this (steps + fallback are canonical; fill `<SUMMARY_UA>`
/ `<SUMMARY_EN>` with the per-release issue text in each language). If you edit the snippet,
preserve the layout.

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
3. Take the canonical text from [`rollout-snippet.md`](rollout-snippet.md) and fill its
   placeholders: `<NEW_TAG>`, the blueprint sub-path `<BP_SUBPATH>`, and `<SUMMARY_UA>` /
   `<SUMMARY_EN>` (the issue/fix summary in each language). Paste it **whole** — it already
   is the two self-contained `<details>` blocks. Keep the placeholders identical between
   the two languages.
   - **PR body:** paste the filled snippet as its own section.
   - **Release notes:** paste it into the body (`gh release create --generate-notes` won't
     add it — append it yourself, or `gh release edit vX.Y.Z --notes-file …`).
4. Use the **tag** URL in the legacy fallback (immutable). For the PR body you may point at
   `main` or the branch.
5. Sanity-check (if you have container access): after restart the file at
   `/config/blueprints/automation/vmyronovych/oselia_button_to_relay.yaml` matches the
   shipped one, and `.storage/waveshare_relay_blueprints` recorded its sha.

## Keep it consistent

`rollout-snippet.md` is the single source of the user-facing wording — edit it there, not
inline, so PR bodies and release notes never drift. This mirrors the human-facing
`RELEASING.md` / `ROLLOUT.md` docs in the repo root.
