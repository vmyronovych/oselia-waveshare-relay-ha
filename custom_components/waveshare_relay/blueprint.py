"""Ship the integration's blueprints into the user's HA on startup.

HACS updates only deliver `custom_components/`. The blueprint, though, lives as a separate
copy in `/config/blueprints/automation/vmyronovych/`, so a fix would never reach users
without a manual re-import. We bundle the blueprint inside the package (it ships in the
HACS zip) and copy it onto disk here, so a normal update + restart delivers it.

Overwrite policy is deliberately conservative -- it must never silently lose a user's edits:

  * file missing                       -> create it
  * on disk == bundled                 -> nothing to do
  * no record yet (pre-feature import)  -> adopt it (back up to .bak, then overwrite)
  * on disk == what we last wrote       -> safe to update (user hasn't touched it; .bak first)
  * on disk differs from our last write -> the user edited it; we NEVER overwrite. Instead we
    raise a *fixable* Repairs issue letting them choose "take the new version" or "keep mine".

Per blueprint we remember, in HA's Store:
  * "sha" -- the sha of what we last wrote (so an edit is detectable across restarts), and
  * "ack" -- the bundled sha the user chose "keep mine" against (so we stop nagging for that
    version but still re-notify when a *newer* version ships).
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import logging
from pathlib import Path
import shutil

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.storage import Store

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

#: Blueprints bundled inside this package; layout mirrors the on-disk destination.
BUNDLED_ROOT = Path(__file__).parent / "blueprints"
STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}_blueprints"  # -> .storage/waveshare_relay_blueprints
_BAK_SUFFIX = ".bak"
_ISSUE_PREFIX = "blueprint_user_modified_"


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _issue_id(rel: str, bundled_sha: str) -> str:
    """Version-scoped id: a *new* bundled version raises a fresh issue, so a user who
    dismissed/kept an earlier conflict is still told when a newer version arrives."""
    return f"{_ISSUE_PREFIX}{rel.replace('/', '_')}_{bundled_sha[:12]}"


@dataclass
class Conflict:
    """A user-edited blueprint we won't overwrite; the user must choose what to do."""

    rel: str
    bundled_sha: str
    path: str  # full on-disk path, for the issue/flow text


@dataclass
class SyncResult:
    """Outcome of one disk sync. `state` maps relpath -> {"sha": .., "ack": ..}."""

    state: dict[str, dict]
    dirty: bool = False  # state changed -> persist it
    seen: list[str] = field(default_factory=list)
    created: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    conflicts: list[Conflict] = field(default_factory=list)


def _sync_to_disk(
    bundled_root: Path, dest_root: Path, state: dict[str, dict]
) -> SyncResult:
    """Pure file sync (no `hass`) so it runs in the executor and is unit-testable."""
    result = SyncResult(state={k: dict(v) for k, v in state.items()})
    for src in sorted(bundled_root.rglob("*.yaml")):
        rel = src.relative_to(bundled_root).as_posix()
        dest = dest_root / rel
        result.seen.append(rel)
        bundled_text = src.read_text(encoding="utf-8")
        bundled_sha = _sha(bundled_text)
        rec = result.state.get(rel) or {}
        managed_sha = rec.get("sha")
        ack = rec.get("ack")

        if not dest.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(bundled_text, encoding="utf-8")
            result.state[rel] = {"sha": bundled_sha, "ack": None}
            result.created.append(rel)
            result.dirty = True
            continue

        disk_sha = _sha(dest.read_text(encoding="utf-8"))

        if disk_sha == bundled_sha:  # already current; ensure clean tracking
            if managed_sha != bundled_sha or ack is not None:
                result.state[rel] = {"sha": bundled_sha, "ack": None}
                result.dirty = True
            continue

        if managed_sha is None:
            # Pre-feature / unknown-provenance copy -> adopt (almost always an unmodified
            # official import; the .bak is the safety net).
            shutil.copy2(dest, dest.with_name(dest.name + _BAK_SUFFIX))
            dest.write_text(bundled_text, encoding="utf-8")
            result.state[rel] = {"sha": bundled_sha, "ack": None}
            result.updated.append(rel)
            result.dirty = True
            continue

        if disk_sha == managed_sha:
            # Our own previously-written copy, unedited -> safe to update.
            shutil.copy2(dest, dest.with_name(dest.name + _BAK_SUFFIX))
            dest.write_text(bundled_text, encoding="utf-8")
            result.state[rel] = {"sha": bundled_sha, "ack": None}
            result.updated.append(rel)
            result.dirty = True
            continue

        # User-edited copy (disk != managed): NEVER overwrite automatically.
        if ack == bundled_sha:
            continue  # user already chose "keep mine" for this exact version
        result.conflicts.append(Conflict(rel, bundled_sha, str(dest)))
    return result


async def _async_load_state(hass: HomeAssistant) -> tuple[Store, dict[str, dict]]:
    """Load the Store, migrating the legacy flat `{rel: sha}` shape to `{rel: {...}}`."""
    store: Store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
    saved = await store.async_load()
    state: dict[str, dict] = {}
    for rel, val in (saved or {}).items():
        if isinstance(val, str):  # legacy: {rel: "<sha>"}
            state[rel] = {"sha": val, "ack": None}
        elif isinstance(val, dict):
            state[rel] = {"sha": val.get("sha"), "ack": val.get("ack")}
    return store, state


async def async_install_bundled_blueprints(hass: HomeAssistant) -> None:
    """Write/refresh the bundled blueprints into `/config/blueprints` (best effort)."""
    store, state = await _async_load_state(hass)
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

    _reconcile_issues(hass, result.conflicts)

    # If an in-use blueprint actually changed, reload automations so the new template
    # takes effect without a full restart. A freshly created blueprint has no automations.
    if result.updated and "automation" in hass.config.components:
        hass.async_create_task(
            hass.services.async_call("automation", "reload", blocking=False)
        )


@callback
def _reconcile_issues(hass: HomeAssistant, conflicts: list[Conflict]) -> None:
    """Raise a fixable issue per current conflict; clear any of ours that no longer apply."""
    active: dict[str, Conflict] = {
        _issue_id(c.rel, c.bundled_sha): c for c in conflicts
    }
    registry = ir.async_get(hass)
    for domain, issue_id in list(registry.issues):
        if domain == DOMAIN and issue_id.startswith(_ISSUE_PREFIX) and issue_id not in active:
            ir.async_delete_issue(hass, DOMAIN, issue_id)
    for issue_id, conflict in active.items():
        ir.async_create_issue(
            hass,
            DOMAIN,
            issue_id,
            is_fixable=True,
            severity=ir.IssueSeverity.WARNING,
            translation_key="blueprint_user_modified",
            data={
                "rel": conflict.rel,
                "bundled_sha": conflict.bundled_sha,
                "path": conflict.path,
            },
        )


# --- repair actions (called from repairs.py) -------------------------------------------


async def async_take_new_version(hass: HomeAssistant, rel: str) -> None:
    """Repair: replace the user's edited copy with the bundled one (backed up to .bak)."""
    store, state = await _async_load_state(hass)
    dest_root = Path(hass.config.path("blueprints"))

    def _write() -> str:
        src = BUNDLED_ROOT / rel
        dest = dest_root / rel
        text = src.read_text(encoding="utf-8")
        if dest.exists():
            shutil.copy2(dest, dest.with_name(dest.name + _BAK_SUFFIX))
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")
        return _sha(text)

    sha = await hass.async_add_executor_job(_write)
    state[rel] = {"sha": sha, "ack": None}
    await store.async_save(state)
    if "automation" in hass.config.components:
        await hass.services.async_call("automation", "reload", blocking=False)


async def async_keep_user_version(hass: HomeAssistant, rel: str) -> None:
    """Repair: keep the user's edited copy; stop flagging *this* bundled version.

    We only record the acknowledged bundled sha -- never the user's content as our
    `sha` -- so the edit stays detectable and is never auto-overwritten later.
    """
    store, state = await _async_load_state(hass)

    def _bundled_sha() -> str:
        return _sha((BUNDLED_ROOT / rel).read_text(encoding="utf-8"))

    bundled_sha = await hass.async_add_executor_job(_bundled_sha)
    rec = state.get(rel) or {"sha": None, "ack": None}
    rec["ack"] = bundled_sha
    state[rel] = rec
    await store.async_save(state)
