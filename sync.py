"""Compatibility entrypoint for UPlaySync direct sync."""

from uplaysync.engine import main, sync_playlists, should_queue_item, video_url_from_item
from uplaysync.matching import (
    find_existing_file_match,
    get_existing_files,
    is_existing_file_match,
    is_token_match,
    normalize_core_title,
    normalize_title,
)
from uplaysync.playlist import get_playlist_items


if __name__ == "__main__":
    raise SystemExit(main())
