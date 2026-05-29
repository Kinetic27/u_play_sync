from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Callable, Iterable

from .config import load_config
from .downloader import DirectYtdlpDownloader, DownloadResult
from .lock import AlreadyRunningError, ProcessLock
from .management import record_playlist_snapshot
from .matching import find_existing_file_match, get_existing_files
from .playlist import get_playlist_items
from .state import (
    DOWNLOAD_HISTORY_FILE,
    ID_MAP_FILE,
    STATE_FILE,
    file_exists_for_entry,
    load_or_migrate_state,
    record_attempt,
    record_downloaded,
    record_failure,
    save_state,
)

logger = logging.getLogger(__name__)


def video_url_from_item(item: dict[str, Any]) -> str | None:
    url = item.get("webpage_url") or item.get("url")
    if url and isinstance(url, str) and url.startswith("http"):
        return url
    video_id = item.get("id") or url
    if video_id:
        return f"https://www.youtube.com/watch?v={video_id}"
    return None


def should_queue_item(
    item: dict[str, Any],
    playlist: dict[str, Any],
    state: dict[str, Any],
    existing_files_map: dict[str, str],
    retry_failed: bool = False,
) -> tuple[bool, str, str | None]:
    video_id = item.get("id")
    title = item.get("title")
    folder = playlist.get("folder")
    if not video_id or not title:
        return False, "missing id/title", None

    entry = state.get("items", {}).get(video_id)
    if entry:
        status = entry.get("status")
        if status == "failed" and not retry_failed:
            return False, "previous failure recorded", entry.get("filename")
        if status == "trashed":
            return False, "user trashed", entry.get("filename")
        if file_exists_for_entry(entry, folder):
            return False, "state file exists", entry.get("filename")
        if status == "downloaded" and entry.get("filename"):
            return True, "state file missing", entry.get("filename")

    matched_filename = find_existing_file_match(title, existing_files_map)
    if matched_filename:
        url = video_url_from_item(item) or f"https://www.youtube.com/watch?v={video_id}"
        record_downloaded(
            state,
            video_id=video_id,
            title=title,
            url=url,
            playlist_name=playlist.get("name"),
            folder=folder,
            filename=matched_filename,
        )
        return False, "existing title-compatible file", matched_filename

    return True, "new item", None


def sync_playlists(
    config: dict[str, Any],
    *,
    state_path: str | Path = STATE_FILE,
    id_map_path: str | Path = ID_MAP_FILE,
    history_path: str | Path = DOWNLOAD_HISTORY_FILE,
    playlist_provider: Callable[[str], list[dict[str, Any]]] = get_playlist_items,
    downloader: DirectYtdlpDownloader | None = None,
    retry_failed: bool = False,
    mirror_legacy: bool = True,
) -> dict[str, Any]:
    state = load_or_migrate_state(state_path, id_map_path, history_path, mirror_legacy=mirror_legacy)
    downloader = downloader or DirectYtdlpDownloader()
    summary = {
        "checked": 0,
        "downloaded": 0,
        "skipped": 0,
        "failed": 0,
        "queued": 0,
        "already_synced": 0,
        "existing_matched": 0,
        "previous_failed": 0,
        "trashed": 0,
        "missing_metadata": 0,
        "redownload": 0,
    }

    for playlist_index, playlist in enumerate(config.get("playlists", []) or []):
        name = playlist.get("name") or playlist.get("url") or "playlist"
        folder = playlist.get("folder")
        url = playlist.get("url")
        if not folder or not url:
            logger.warning("Skipping playlist with missing folder/url: %s", name)
            continue

        print(f"\n플레이리스트 처리 중: {name}")
        existing_files_map = get_existing_files(folder)
        items = playlist_provider(url)
        record_playlist_snapshot(state, playlist, items, index=playlist_index)
        print(f"플레이리스트에서 {len(items)}개의 항목을 발견했습니다.")

        for item in items:
            summary["checked"] += 1
            video_id = item.get("id")
            title = item.get("title")
            should_queue, reason, matched = should_queue_item(
                item,
                playlist,
                state,
                existing_files_map,
                retry_failed=retry_failed,
            )
            if not should_queue:
                summary["skipped"] += 1
                if reason == "state file exists":
                    summary["already_synced"] += 1
                elif reason == "existing title-compatible file":
                    summary["existing_matched"] += 1
                elif reason == "previous failure recorded":
                    summary["previous_failed"] += 1
                elif reason == "user trashed":
                    summary["trashed"] += 1
                elif reason == "missing id/title":
                    summary["missing_metadata"] += 1
                continue

            video_url = video_url_from_item(item)
            if not video_id or not title or not video_url:
                summary["skipped"] += 1
                summary["missing_metadata"] += 1
                continue

            summary["queued"] += 1
            if reason == "state file missing":
                summary["redownload"] += 1
                print(f"[재다운로드] {title}")
            else:
                print(f"[다운로드] {title}")
            record_attempt(state, video_id)
            result = downloader.download(url=video_url, video_id=video_id, title=title, folder=folder)
            if result.ok and result.filename:
                record_downloaded(
                    state,
                    video_id=video_id,
                    title=title,
                    url=video_url,
                    playlist_name=name,
                    folder=folder,
                    filename=result.filename,
                )
                if result.preexisting:
                    summary["skipped"] += 1
                    summary["existing_matched"] += 1
                else:
                    summary["downloaded"] += 1
                    print(f"  [완료] {title} -> {result.filename}")
            else:
                record_failure(
                    state,
                    video_id=video_id,
                    title=title,
                    url=video_url,
                    playlist_name=name,
                    folder=folder,
                    reason=result.error or "unknown download failure",
                )
                summary["failed"] += 1
                print(f"  [오류] {title}: {result.error or 'unknown download failure'}")
            save_state(state, state_path, id_map_path, history_path, mirror_legacy=mirror_legacy)

    save_state(state, state_path, id_map_path, history_path, mirror_legacy=mirror_legacy)
    already_done = summary["already_synced"] + summary["existing_matched"]
    print(
        f"\n요약: 확인 {summary['checked']}개, 새 다운로드 {summary['downloaded']}개, "
        f"이미 있음 {already_done}개, 이전 실패 스킵 {summary['previous_failed']}개, "
        f"휴지통 스킵 {summary['trashed']}개, 신규 실패 {summary['failed']}개"
    )
    return {"state": state, "summary": summary}


def main(argv: Iterable[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    config = load_config("config.yaml")
    retry_failed = bool(config.get("retry_failed", False))
    lock_path = os.environ.get("UPLAYSYNC_LOCK_FILE", ".uplaysync.lock")
    try:
        with ProcessLock(lock_path):
            sync_playlists(
                config,
                state_path=os.environ.get("UPLAYSYNC_STATE_FILE", STATE_FILE),
                id_map_path=os.environ.get("UPLAYSYNC_ID_MAP_FILE", ID_MAP_FILE),
                history_path=os.environ.get("UPLAYSYNC_HISTORY_FILE", DOWNLOAD_HISTORY_FILE),
                retry_failed=retry_failed,
            )
    except AlreadyRunningError as exc:
        print(f"[중복 실행 방지] {exc}")
        return 2
    return 0
