from __future__ import annotations

import json
import logging
import os
import shutil
import errno
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

SCHEMA_VERSION = 1
STATE_FILE = "sync_state.json"
ID_MAP_FILE = "id_map.json"
DOWNLOAD_HISTORY_FILE = "download_history.json"

logger = logging.getLogger(__name__)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def empty_state() -> dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, "items": {}, "history": []}


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Failed to load JSON from %s: %s", path, exc)
        return default


def _atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")
    try:
        os.replace(tmp, path)
    except OSError as exc:
        if exc.errno != errno.EBUSY:
            raise
        logger.debug("Atomic replace failed for bind-mounted file %s; falling back to in-place write", path)
        try:
            with path.open("w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
                f.write("\n")
        finally:
            tmp.unlink(missing_ok=True)


def backup_existing_files(paths: Iterable[Path], label: str = "sync-state-migration") -> list[Path]:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backups: list[Path] = []
    for path in paths:
        if path.exists():
            backup = path.with_name(f"{path.name}.bak-{label}-{timestamp}")
            shutil.copy2(path, backup)
            backups.append(backup)
    return backups


def load_legacy(id_map_path: Path, history_path: Path) -> tuple[dict[str, str], list[str]]:
    id_map = _load_json(id_map_path, {})
    history = _load_json(history_path, [])
    if not isinstance(id_map, dict):
        id_map = {}
    if not isinstance(history, list):
        history = list(history) if history else []
    return id_map, [str(v) for v in history]


def migrate_legacy_state(id_map_path: Path, history_path: Path) -> dict[str, Any]:
    id_map, history = load_legacy(id_map_path, history_path)
    state = empty_state()
    ordered_ids: list[str] = []
    for vid in history + list(id_map.keys()):
        vid = str(vid)
        if vid and vid not in ordered_ids:
            ordered_ids.append(vid)

    now = utc_now()
    for vid in ordered_ids:
        filename = id_map.get(vid)
        status = "downloaded"
        failure_reason: Optional[str] = None
        if isinstance(filename, str) and filename.startswith("ERROR:"):
            status = "failed"
            failure_reason = filename[len("ERROR:"):].strip() or "unknown error"
        state["items"][vid] = {
            "video_id": vid,
            "title": None,
            "url": f"https://www.youtube.com/watch?v={vid}",
            "playlist_names": [],
            "folder": None,
            "filename": filename if isinstance(filename, str) and status == "downloaded" else None,
            "relative_path": None,
            "status": status,
            "failure_reason": failure_reason,
            "attempt_count": 0,
            "last_attempt_at": None,
            "downloaded_at": now if status == "downloaded" else None,
            "updated_at": now,
        }
    state["history"] = [vid for vid in history if vid in state["items"]]
    return state


def normalize_state(raw_state: Any, source: str | Path = STATE_FILE) -> dict[str, Any]:
    if not isinstance(raw_state, dict):
        logger.warning("Ignoring invalid state from %s: expected object", source)
        return empty_state()

    version = raw_state.get("schema_version", SCHEMA_VERSION)
    if version != SCHEMA_VERSION:
        logger.warning("State %s has unsupported schema_version=%s; using empty state", source, version)
        return empty_state()

    items = raw_state.get("items")
    if not isinstance(items, dict):
        logger.warning("State %s has invalid items; using empty item map", source)
        items = {}

    history = raw_state.get("history")
    if not isinstance(history, list):
        logger.warning("State %s has invalid history; using empty history", source)
        history = []

    normalized = dict(raw_state)
    normalized["schema_version"] = SCHEMA_VERSION
    normalized["items"] = items
    normalized["history"] = [str(video_id) for video_id in history if str(video_id) in items]
    return normalized


def load_state_file(state_path: str | Path = STATE_FILE) -> dict[str, Any]:
    path = Path(state_path)
    return normalize_state(_load_json(path, empty_state()), path)


def load_or_migrate_state(
    state_path: str | Path = STATE_FILE,
    id_map_path: str | Path = ID_MAP_FILE,
    history_path: str | Path = DOWNLOAD_HISTORY_FILE,
    create_backups: bool = True,
    write_migrated: bool = True,
    mirror_legacy: bool = True,
) -> dict[str, Any]:
    state_file = Path(state_path)
    id_file = Path(id_map_path)
    history_file = Path(history_path)
    if state_file.exists():
        return load_state_file(state_file)

    if create_backups:
        backup_existing_files([id_file, history_file, state_file])
    state = migrate_legacy_state(id_file, history_file)
    if write_migrated:
        save_state(state, state_file, id_file, history_file, mirror_legacy=mirror_legacy)
    return state


def save_state(
    state: dict[str, Any],
    state_path: str | Path = STATE_FILE,
    id_map_path: str | Path = ID_MAP_FILE,
    history_path: str | Path = DOWNLOAD_HISTORY_FILE,
    mirror_legacy: bool = True,
) -> None:
    state.setdefault("schema_version", SCHEMA_VERSION)
    state.setdefault("items", {})
    state.setdefault("history", [])
    _atomic_write_json(Path(state_path), state)
    if mirror_legacy:
        write_legacy_mirror(state, Path(id_map_path), Path(history_path))


def write_legacy_mirror(state: dict[str, Any], id_map_path: Path, history_path: Path) -> None:
    id_map: dict[str, str] = {}
    for vid, entry in state.get("items", {}).items():
        status = entry.get("status")
        if status == "failed":
            id_map[vid] = f"ERROR: {entry.get('failure_reason') or 'unknown error'}"
        elif status == "downloaded" and entry.get("filename"):
            id_map[vid] = entry["filename"]
    history = [vid for vid in state.get("history", []) if vid in state.get("items", {})]
    _atomic_write_json(id_map_path, id_map)
    _atomic_write_json(history_path, history)


def add_history(state: dict[str, Any], video_id: str) -> None:
    history = state.setdefault("history", [])
    if video_id in history:
        history.remove(video_id)
    history.append(video_id)


def file_exists_for_entry(entry: dict[str, Any], fallback_folder: str | Path | None = None) -> bool:
    filename = entry.get("filename")
    if not filename:
        return False
    path = Path(filename)
    if path.is_absolute() and path.exists():
        return True

    folder_value = entry.get("folder") or fallback_folder
    folder = Path(folder_value) if folder_value else None
    if folder and (folder / filename).exists():
        return True

    relative_path = entry.get("relative_path")
    if relative_path:
        rel = Path(relative_path)
        if rel.is_absolute() and rel.exists():
            return True
        if folder and (folder.parent / rel).exists():
            return True
    return False


def record_downloaded(
    state: dict[str, Any],
    *,
    video_id: str,
    title: str,
    url: str,
    playlist_name: str | None,
    folder: str,
    filename: str,
) -> dict[str, Any]:
    now = utc_now()
    entry = state.setdefault("items", {}).get(video_id, {})
    playlists = set(entry.get("playlist_names") or [])
    if playlist_name:
        playlists.add(playlist_name)
    attempt_count = int(entry.get("attempt_count") or 0)
    entry.update({
        "video_id": video_id,
        "title": title,
        "url": url,
        "playlist_names": sorted(playlists),
        "folder": folder,
        "filename": filename,
        "relative_path": None,
        "status": "downloaded",
        "failure_reason": None,
        "attempt_count": attempt_count,
        "last_attempt_at": entry.get("last_attempt_at"),
        "downloaded_at": now,
        "updated_at": now,
    })
    state["items"][video_id] = entry
    add_history(state, video_id)
    return entry


def record_attempt(state: dict[str, Any], video_id: str) -> None:
    entry = state.setdefault("items", {}).setdefault(video_id, {"video_id": video_id})
    entry["attempt_count"] = int(entry.get("attempt_count") or 0) + 1
    entry["last_attempt_at"] = utc_now()
    entry["updated_at"] = entry["last_attempt_at"]


def record_failure(
    state: dict[str, Any],
    *,
    video_id: str,
    title: str | None,
    url: str,
    playlist_name: str | None,
    folder: str | None,
    reason: str,
) -> dict[str, Any]:
    now = utc_now()
    entry = state.setdefault("items", {}).get(video_id, {})
    playlists = set(entry.get("playlist_names") or [])
    if playlist_name:
        playlists.add(playlist_name)
    entry.update({
        "video_id": video_id,
        "title": title,
        "url": url,
        "playlist_names": sorted(playlists),
        "folder": folder,
        "filename": entry.get("filename"),
        "relative_path": entry.get("relative_path"),
        "status": "failed",
        "failure_reason": reason,
        "attempt_count": int(entry.get("attempt_count") or 0),
        "last_attempt_at": entry.get("last_attempt_at") or now,
        "downloaded_at": entry.get("downloaded_at"),
        "updated_at": now,
    })
    state["items"][video_id] = entry
    add_history(state, video_id)
    return entry
