"""Ship the integration's blueprints into the user's HA on startup.

HACS updates only deliver `custom_components/`. The blueprint, though, lives as a separate
copy in `/config/blueprints/automation/vmyronovych/`, so a fix would never reach users
without a manual re-import. We bundle the blueprint inside the package (it ships in the
HACS zip) and copy it onto disk here, so a normal update + restart delivers it.

Overwrite policy is deliberately conservative -- it must never silently lose a user's edits:

  * file missing                      -> create it
  * on disk == bundled                -> nothing to do
  * on disk == what we last wrote      -> safe to update (the user hasn't touched it);
    (or no record yet)                   back the old file up to `<name>.bak` first
  * on disk differs from our last write -> the user edited it; skip and raise a Repairs
                                           issue rather than clobber their work

We remember the sha of what we last wrote (per blueprint) in HA's Store so "the user
hasn't touched it" is decidable across restarts.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import logging
from pathlib import Path
import shutil

from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.storage import Store

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

#: Blueprints bundled inside this package; layout mirrors the on-disk destination so the
#: copy is a plain tree walk and extends to any future blueprints.
BUNDLED_ROOT = Path(__file__).parent / "blueprints"
STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}_blueprints"  # -> .storage/waveshare_relay_blueprints
_BAK_SUFFIX = ".bak"


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class SyncResult:
    """Outcome of one disk sync. `state` maps blueprint relpath -> sha we last wrote."""

    state: dict[str, str]
    dirty: bool = False  # state changed -> persist it
    seen: list[str] = field(default_factory=list)
    created: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)  # user-edited; left untouched


def _sync_to_disk(
    bundled_root: Path, dest_root: Path, state: dict[str, str]
) -> SyncResult:
    """Pure file sync (no `hass`) so it runs in the executor and is unit-testable."""
    result = SyncResult(state=dict(state))
    for src in sorted(bundled_root.rglob("*.yaml")):
        rel = src.relative_to(bundled_root).as_posix()
        dest = dest_root / rel
        result.seen.append(rel)
        bundled_text = src.read_text(encoding="utf-8")
        bundled_sha = _sha(bundled_text)

        if not dest.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(bundled_text, encoding="utf-8")
            result.state[rel] = bundled_sha
            result.created.append(rel)
            result.dirty = True
            continue

        disk_sha = _sha(dest.read_text(encoding="utf-8"))
        if disk_sha == bundled_sha:
            if state.get(rel) != bundled_sha:  # already current; just start tracking it
                result.state[rel] = bundled_sha
                result.dirty = True
            continue

        last_sha = state.get(rel)
        if last_sha is None or disk_sha == last_sha:
            # Unedited since our last write -- or a pre-feature copy of unknown provenance,
            # which we adopt (it's almost always an unmodified official import, and the
            # .bak is the safety net). Either way, update it.
            shutil.copy2(dest, dest.with_name(dest.name + _BAK_SUFFIX))
            dest.write_text(bundled_text, encoding="utf-8")
            result.state[rel] = bundled_sha
            result.updated.append(rel)
            result.dirty = True
        else:
            # On disk matches neither the bundle nor our last write -> the user edited it.
            result.skipped.append(rel)
    return result


def _issue_id(rel: str) -> str:
    return f"blueprint_user_modified_{rel.replace('/', '_')}"


async def async_install_bundled_blueprints(hass: HomeAssistant) -> None:
    """Write/refresh the bundled blueprints into `/config/blueprints` (best effort)."""
    store: Store[dict[str, str]] = Store(hass, STORAGE_VERSION, STORAGE_KEY)
    saved = await store.async_load()
    state = dict(saved) if saved else {}
    dest_root = Path(hass.config.path("blueprints"))

    try:
        result = await hass.async_add_executor_job(
            _sync_to_disk, BUNDLED_ROOT, dest_root, state
        )
    except Exception:  # noqa: BLE001 - never block integration setup on a file error
        _LOGGER.exception("Waveshare: could not install bundled blueprints")
        return

    if result.dirty:
        await store.async_save(result.state)
    for rel in result.created:
        _LOGGER.info("Waveshare: installed blueprint %s", rel)
    for rel in result.updated:
        _LOGGER.info("Waveshare: updated blueprint %s (previous saved as %s%s)",
                     rel, rel, _BAK_SUFFIX)

    # Raise a Repairs issue for each user-edited blueprint we left alone; clear it for any
    # blueprint that's now in sync again.
    for rel in result.seen:
        if rel in result.skipped:
            ir.async_create_issue(
                hass,
                DOMAIN,
                _issue_id(rel),
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key="blueprint_user_modified",
                translation_placeholders={"path": str(dest_root / rel)},
            )
        else:
            ir.async_delete_issue(hass, DOMAIN, _issue_id(rel))

    # If an in-use blueprint actually changed, reload automations so the new template takes
    # effect without a full restart. A freshly created blueprint has no automations yet.
    if result.updated and "automation" in hass.config.components:
        hass.async_create_task(
            hass.services.async_call("automation", "reload", blocking=False)
        )
