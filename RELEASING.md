# Releasing (GitHub → HACS)

This integration updates via **HACS** — it polls this repo's GitHub Releases and offers a
one-click update (then HA restarts).

## Versioning

- Releases use plain **`v*`** semver tags (e.g. `v0.2.0`).
- The **tag is the single source of version truth**: the `release` workflow stamps it into
  `custom_components/waveshare_relay/manifest.json`, so the committed manifest version is
  just a dev default and can't drift from what ships.
- `hacs.json` sets `zip_release` + `filename: waveshare_relay.zip`, so HACS installs the
  workflow's built asset (not the repo tree).

## Cut a release

1. Land your changes on `main` (the `Validate` workflow — hassfest + HACS action — runs on
   every PR).
2. Create a GitHub Release on a new `v*` tag — UI, or:
   ```sh
   gh release create v0.2.0 --generate-notes --title "v0.2.0"
   ```
3. The **`release` workflow** (`.github/workflows/release.yml`) fires on *release
   published*: it gates on `py_compile`, stamps the tag version into `manifest.json`, zips
   the component, and attaches **`waveshare_relay.zip`** to the release.

HACS reads the version from the manifest inside that zip, so what installs matches the tag.

## If the release changes a blueprint (`blueprints/**`)

The blueprint is **bundled inside the integration** and auto-installs on startup, so a
HACS update + restart delivers blueprint fixes **automatically** — no manual re-import.
The smart-overwrite keeps any user edits (and raises a Repairs issue instead of clobbering
them); see `custom_components/waveshare_relay/blueprint.py`.

Two things to do when a blueprint changes:

1. **Keep the bundled copy in sync with the canonical one.** The repo-root file
   `blueprints/automation/vmyronovych/oselia_button_to_relay.yaml` is the human-edited
   source; the shipped copy under `custom_components/waveshare_relay/blueprints/…` must
   match it. Resync and commit:
   ```sh
   cp blueprints/automation/vmyronovych/oselia_button_to_relay.yaml \
      custom_components/waveshare_relay/blueprints/automation/vmyronovych/oselia_button_to_relay.yaml
   ```
   The `blueprints in sync` check in `validate.yml` fails the build if they drift.
2. **Release notes** need only a one-line *"the blueprint updates automatically on restart"*.
   The canonical wording lives in the `blueprint-release-rollout` skill
   (`.claude/skills/blueprint-release-rollout/rollout-snippet.md`) — it ships the
   auto-delivery note plus a legacy manual-import fallback for users still on a
   pre-auto-install build (≤ v0.1.x).

## Distribution

- **Now:** users add this repo as a HACS *custom repository* (category: Integration).
- **Later:** PRs to [`hacs/default`](https://github.com/hacs/default) (HACS store, no manual
  URL) and [`home-assistant/brands`](https://github.com/home-assistant/brands) for the icon
  (assets in [`brands/`](brands/)).

## Notes

- **Beta channel:** mark a release as a *prerelease* (e.g. `v0.3.0-rc1`); HACS only offers
  prereleases to users who opt into betas for the repository.
