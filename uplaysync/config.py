from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG_FILE = "config.yaml"
LEGACY_METUBE_TOP_LEVEL_KEYS = {"metube_url"}
LEGACY_METUBE_PLAYLIST_KEYS = {"metube_folder"}


def strip_legacy_metube_fields(config: dict[str, Any]) -> dict[str, Any]:
    """Remove obsolete MeTube routing fields from user-facing config."""
    cleaned = dict(config or {})
    for key in LEGACY_METUBE_TOP_LEVEL_KEYS:
        cleaned.pop(key, None)

    playlists = []
    for playlist in cleaned.get("playlists", []) or []:
        if not isinstance(playlist, dict):
            continue
        cleaned_playlist = dict(playlist)
        for key in LEGACY_METUBE_PLAYLIST_KEYS:
            cleaned_playlist.pop(key, None)
        playlists.append(cleaned_playlist)
    cleaned["playlists"] = playlists
    return cleaned


def load_config(path: str | Path = DEFAULT_CONFIG_FILE) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as f:
        return strip_legacy_metube_fields(yaml.safe_load(f) or {})


def save_config(config: dict[str, Any], path: str | Path = DEFAULT_CONFIG_FILE) -> None:
    with Path(path).open("w", encoding="utf-8") as f:
        yaml.dump(config, f, allow_unicode=True, default_flow_style=False)


def merge_config_preserving_unknown(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = dict(existing or {})
    merged.update(incoming or {})
    return strip_legacy_metube_fields(merged)
