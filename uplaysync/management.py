from __future__ import annotations

import hashlib
import uuid
from pathlib import Path
from typing import Any, Iterable

from .playlist import get_playlist_items
from .state import add_history, file_exists_for_entry, utc_now

QUEUE_ACTIVE_STATUSES = {"queued", "running"}
TRASH_DIR_NAME = ".uplaysync-trash"


def playlist_key(playlist: dict[str, Any], index: int | None = None) -> str:
    seed = playlist.get("url") or playlist.get("name") or str(index or 0)
    digest = hashlib.sha1(str(seed).encode("utf-8")).hexdigest()[:12]
    return f"pl-{digest}"


def ensure_management_sections(state: dict[str, Any]) -> None:
    state.setdefault("playlist_snapshots", {})
    state.setdefault("queue", [])
    state.setdefault("queue_history", [])


def compact_queue(state: dict[str, Any], *, keep_finished: int = 100) -> None:
    ensure_management_sections(state)
    active: list[dict[str, Any]] = []
    finished: list[dict[str, Any]] = []
    for job in state.get("queue", []) or []:
        if job.get("status") in QUEUE_ACTIVE_STATUSES:
            active.append(job)
        else:
            finished.append(job)
    if len(finished) > keep_finished:
        archive = state.setdefault("queue_history", [])
        archive.extend(finished[:-keep_finished])
        finished = finished[-keep_finished:]
        state["queue_history"] = archive[-500:]
    state["queue"] = active + finished


def video_url_from_snapshot_item(item: dict[str, Any]) -> str | None:
    url = item.get("webpage_url") or item.get("url")
    if isinstance(url, str) and url.startswith("http"):
        return url
    video_id = item.get("id") or item.get("video_id") or url
    if video_id:
        return f"https://www.youtube.com/watch?v={video_id}"
    return None


def normalize_playlist_item(item: dict[str, Any], playlist: dict[str, Any]) -> dict[str, Any] | None:
    video_id = item.get("id") or item.get("video_id")
    title = item.get("title")
    if not video_id or not title:
        return None
    url = video_url_from_snapshot_item(item)
    if not url:
        return None
    return {
        "video_id": str(video_id),
        "title": title,
        "url": url,
        "playlist_name": playlist.get("name") or playlist.get("url") or "playlist",
        "folder": playlist.get("folder"),
    }


def record_playlist_snapshot(
    state: dict[str, Any],
    playlist: dict[str, Any],
    items: Iterable[dict[str, Any]],
    *,
    index: int | None = None,
) -> dict[str, Any]:
    ensure_management_sections(state)
    key = playlist_key(playlist, index)
    normalized = [item for item in (normalize_playlist_item(raw, playlist) for raw in items) if item]
    snapshot = {
        "key": key,
        "index": index,
        "name": playlist.get("name") or playlist.get("url") or "playlist",
        "url": playlist.get("url"),
        "folder": playlist.get("folder"),
        "last_scanned_at": utc_now(),
        "count": len(normalized),
        "items": normalized,
    }
    state["playlist_snapshots"][key] = snapshot
    return snapshot


def refresh_playlist_snapshot(
    state: dict[str, Any],
    config: dict[str, Any],
    playlist_index: int,
    *,
    playlist_provider=get_playlist_items,
) -> dict[str, Any]:
    playlists = config.get("playlists", []) or []
    if playlist_index < 0 or playlist_index >= len(playlists):
        raise IndexError("playlist index out of range")
    playlist = playlists[playlist_index]
    url = playlist.get("url")
    if not url:
        raise ValueError("playlist url is required")
    items = playlist_provider(url)
    return record_playlist_snapshot(state, playlist, items, index=playlist_index)


def _entry_file_path(entry: dict[str, Any]) -> Path | None:
    filename = entry.get("filename")
    folder = entry.get("folder")
    if not filename:
        return None
    path = Path(filename)
    if path.is_absolute():
        return path
    if folder:
        return Path(folder) / filename
    return None


def _unique_trash_path(source: Path, video_id: str) -> Path:
    trash_dir = source.parent / TRASH_DIR_NAME
    trash_dir.mkdir(parents=True, exist_ok=True)
    timestamp = utc_now().replace(":", "").replace("+", "Z")
    base = f"{video_id}--{timestamp}--{source.name}"
    candidate = trash_dir / base
    counter = 1
    while candidate.exists():
        candidate = trash_dir / f"{video_id}--{timestamp}--{counter}--{source.name}"
        counter += 1
    return candidate


def move_entry_to_trash(
    state: dict[str, Any],
    video_id: str,
    *,
    reason: str = "user-trash",
) -> dict[str, Any]:
    items = state.setdefault("items", {})
    entry = items.get(video_id)
    if not entry:
        raise KeyError(f"unknown item: {video_id}")
    source = _entry_file_path(entry)
    if not source or not source.exists():
        raise FileNotFoundError(f"downloaded file not found for {video_id}")
    destination = _unique_trash_path(source, video_id)
    source.rename(destination)
    now = utc_now()
    entry.update({
        "status": "trashed",
        "trash_path": str(destination),
        "trashed_at": now,
        "trash_reason": reason,
        "updated_at": now,
    })
    items[video_id] = entry
    add_history(state, video_id)
    return entry


def restore_trashed_entry(state: dict[str, Any], video_id: str) -> dict[str, Any]:
    items = state.setdefault("items", {})
    entry = items.get(video_id)
    if not entry:
        raise KeyError(f"unknown item: {video_id}")
    if entry.get("status") != "trashed":
        raise ValueError(f"item is not trashed: {video_id}")
    trash_path_value = entry.get("trash_path")
    if not trash_path_value:
        raise FileNotFoundError(f"trash path missing for {video_id}")
    trash_path = Path(trash_path_value)
    if not trash_path.exists():
        raise FileNotFoundError(f"trash file not found for {video_id}")
    target = _entry_file_path(entry)
    if not target:
        raise ValueError(f"original path is unknown for {video_id}")
    if target.exists():
        raise FileExistsError(f"target already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    trash_path.rename(target)
    now = utc_now()
    entry.update({
        "status": "downloaded",
        "failure_reason": None,
        "trash_path": None,
        "restored_at": now,
        "updated_at": now,
    })
    items[video_id] = entry
    add_history(state, video_id)
    return entry


def _active_queue_job_for_video(state: dict[str, Any], video_id: str) -> dict[str, Any] | None:
    for job in state.get("queue", []) or []:
        if job.get("video_id") == video_id and job.get("status") in QUEUE_ACTIVE_STATUSES:
            return job
    return None


def _snapshot_context_for_video(state: dict[str, Any], video_id: str) -> dict[str, Any] | None:
    for snapshot in (state.get("playlist_snapshots", {}) or {}).values():
        for item in snapshot.get("items", []) or []:
            if item.get("video_id") == video_id:
                return dict(item)
    return None


def item_context_for_video(state: dict[str, Any], video_id: str) -> dict[str, Any] | None:
    context = _snapshot_context_for_video(state, video_id)
    entry = state.get("items", {}).get(video_id)
    if context:
        if entry:
            context.setdefault("title", entry.get("title"))
            context.setdefault("url", entry.get("url"))
            context.setdefault("folder", entry.get("folder"))
        return context
    if entry:
        return {
            "video_id": video_id,
            "title": entry.get("title") or entry.get("filename") or video_id,
            "url": entry.get("url") or f"https://www.youtube.com/watch?v={video_id}",
            "playlist_name": (entry.get("playlist_names") or [None])[0],
            "folder": entry.get("folder"),
        }
    return None


def enqueue_item(
    state: dict[str, Any],
    video_id: str,
    *,
    action: str = "download",
) -> tuple[dict[str, Any], bool]:
    ensure_management_sections(state)
    if action not in {"download", "redownload", "retry_failed"}:
        raise ValueError(f"unsupported queue action: {action}")
    existing = _active_queue_job_for_video(state, video_id)
    if existing:
        return existing, False
    context = item_context_for_video(state, video_id)
    if not context:
        raise KeyError(f"unknown item: {video_id}")
    if not context.get("url") or not context.get("folder"):
        raise ValueError(f"item lacks url or folder: {video_id}")
    now = utc_now()
    job = {
        "id": str(uuid.uuid4()),
        "video_id": video_id,
        "title": context.get("title") or video_id,
        "url": context.get("url"),
        "playlist_name": context.get("playlist_name"),
        "folder": context.get("folder"),
        "action": action,
        "status": "queued",
        "created_at": now,
        "started_at": None,
        "finished_at": None,
        "error": None,
        "cancel_requested": False,
    }
    state["queue"].append(job)
    return job, True


def cancel_queue_job(state: dict[str, Any], job_id: str) -> dict[str, Any]:
    ensure_management_sections(state)
    for job in state.get("queue", []) or []:
        if job.get("id") != job_id:
            continue
        if job.get("status") == "queued":
            now = utc_now()
            job.update({"status": "canceled", "finished_at": now, "cancel_requested": True})
        elif job.get("status") == "running":
            job["cancel_requested"] = True
        return job
    raise KeyError(f"unknown queue job: {job_id}")


def reset_interrupted_jobs(state: dict[str, Any]) -> int:
    ensure_management_sections(state)
    count = 0
    for job in state.get("queue", []) or []:
        if job.get("status") == "running":
            job.update({
                "status": "queued",
                "started_at": None,
                "error": "resumed after app restart",
                "cancel_requested": False,
            })
            count += 1
    return count


def next_queued_job(state: dict[str, Any]) -> dict[str, Any] | None:
    ensure_management_sections(state)
    for job in state.get("queue", []) or []:
        if job.get("status") == "queued":
            return job
    return None


def status_for_item(state: dict[str, Any], item: dict[str, Any]) -> tuple[str, dict[str, Any] | None]:
    video_id = item.get("video_id")
    active_job = _active_queue_job_for_video(state, video_id) if video_id else None
    if active_job:
        return active_job.get("status") or "queued", active_job
    entry = state.get("items", {}).get(video_id) if video_id else None
    if not entry:
        return "not_downloaded", None
    status = entry.get("status") or "unknown"
    if status == "downloaded" and not file_exists_for_entry(entry, item.get("folder")):
        return "missing", entry
    return status, entry


def build_management_view(config: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    ensure_management_sections(state)
    playlists_out = []
    seen_video_ids: set[str] = set()
    for index, playlist in enumerate(config.get("playlists", []) or []):
        key = playlist_key(playlist, index)
        snapshot = (state.get("playlist_snapshots", {}) or {}).get(key, {})
        items_out = []
        counts: dict[str, int] = {}
        for item in snapshot.get("items", []) or []:
            status, source = status_for_item(state, item)
            counts[status] = counts.get(status, 0) + 1
            video_id = item.get("video_id")
            if video_id:
                seen_video_ids.add(video_id)
            entry = source if isinstance(source, dict) and source.get("video_id") == video_id else state.get("items", {}).get(video_id, {})
            items_out.append({
                **item,
                "status": status,
                "filename": entry.get("filename"),
                "failure_reason": entry.get("failure_reason"),
                "attempt_count": entry.get("attempt_count"),
                "updated_at": entry.get("updated_at"),
                "downloaded_at": entry.get("downloaded_at"),
                "trash_path": entry.get("trash_path"),
            })
        playlists_out.append({
            "index": index,
            "key": key,
            "name": playlist.get("name") or playlist.get("url") or f"playlist {index + 1}",
            "url": playlist.get("url"),
            "folder": playlist.get("folder"),
            "last_scanned_at": snapshot.get("last_scanned_at"),
            "count": len(items_out),
            "counts": counts,
            "items": items_out,
        })

    orphan_items = []
    for video_id, entry in sorted((state.get("items", {}) or {}).items()):
        if video_id in seen_video_ids:
            continue
        status = entry.get("status") or "unknown"
        if status == "downloaded" and not file_exists_for_entry(entry):
            status = "missing"
        orphan_items.append({
            "video_id": video_id,
            "title": entry.get("title") or entry.get("filename") or video_id,
            "url": entry.get("url"),
            "playlist_name": ", ".join(entry.get("playlist_names") or []),
            "folder": entry.get("folder"),
            "status": status,
            "filename": entry.get("filename"),
            "failure_reason": entry.get("failure_reason"),
            "attempt_count": entry.get("attempt_count"),
            "updated_at": entry.get("updated_at"),
            "downloaded_at": entry.get("downloaded_at"),
            "trash_path": entry.get("trash_path"),
        })

    queue = list(state.get("queue", []) or [])
    trash = [
        {"video_id": vid, **entry}
        for vid, entry in (state.get("items", {}) or {}).items()
        if entry.get("status") == "trashed"
    ]
    return {
        "playlists": playlists_out,
        "orphan_items": orphan_items,
        "queue": queue,
        "trash": trash,
        "summary": {
            "playlists": len(playlists_out),
            "items": sum(p["count"] for p in playlists_out),
            "queue_active": sum(1 for job in queue if job.get("status") in QUEUE_ACTIVE_STATUSES),
            "trash": len(trash),
            "orphan_items": len(orphan_items),
        },
    }
