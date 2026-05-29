import os
import re
import unicodedata
from pathlib import Path
from typing import Dict, Iterable, Optional

MIN_SINGLE_TOKEN_FUZZY_LENGTH = 6
SUPPORTED_AUDIO_EXTENSIONS = frozenset({".m4a"})


def normalize_title(s: str | None) -> str:
    """Normalize human titles/filenames for compatibility comparisons."""
    if not s:
        return ""
    s = unicodedata.normalize("NFKC", s)
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip().lower()


def normalize_core_title(raw_title: str | None) -> str:
    """Remove common bracket decorations before fuzzy matching."""
    title_without_decorations = re.sub(r"\([^)]*\)|\[[^\]]*\]", "", raw_title or "")
    return normalize_title(title_without_decorations)


def _title_tokens_for_fuzzy_match(title: str, title_is_normalized: bool = False) -> set[str]:
    normalized_core_title = title if title_is_normalized else normalize_core_title(title)
    yt_tokens = set(normalized_core_title.split())

    if not yt_tokens:
        normalized_title = title if title_is_normalized else normalize_title(title)
        yt_tokens = set(normalized_title.split())

    if len(yt_tokens) == 1:
        only_token = next(iter(yt_tokens))
        if len(only_token) < MIN_SINGLE_TOKEN_FUZZY_LENGTH:
            return set()

    return yt_tokens


def is_token_match(title: str, existing_norm_name: str, title_is_normalized: bool = False) -> bool:
    yt_tokens = _title_tokens_for_fuzzy_match(title, title_is_normalized=title_is_normalized)
    if not yt_tokens:
        return False
    local_tokens = set(existing_norm_name.split())
    return bool(yt_tokens and yt_tokens.issubset(local_tokens))


def is_existing_file_match(title: str, existing_norm_name: str, title_is_normalized: bool = False) -> bool:
    normalized_title = title if title_is_normalized else normalize_title(title)
    if normalized_title == existing_norm_name:
        return True
    if normalized_title and normalized_title in existing_norm_name:
        # Keep substring matching only for non-generic titles. This preserves useful
        # artist-prefix matches without allowing "Hot!" to match "Mans Not Hot".
        return bool(_title_tokens_for_fuzzy_match(title, title_is_normalized=title_is_normalized))
    return is_token_match(title, existing_norm_name, title_is_normalized=title_is_normalized)


def find_existing_file_match(
    title: str,
    existing_files_map: Dict[str, str],
    title_is_normalized: bool = False,
) -> Optional[str]:
    for existing_norm_name, filename in existing_files_map.items():
        if is_existing_file_match(title, existing_norm_name, title_is_normalized=title_is_normalized):
            return filename
    return None


def get_existing_files(
    folder_path: str | os.PathLike[str],
    audio_extensions: Iterable[str] = SUPPORTED_AUDIO_EXTENSIONS,
) -> Dict[str, str]:
    """Return {normalized_stem: original audio filename} for direct child audio files."""
    folder = Path(folder_path)
    if not folder.exists():
        return {}
    allowed = {ext.lower() for ext in audio_extensions}
    files: Dict[str, str] = {}
    for child in folder.iterdir():
        if child.is_file() and child.suffix.lower() in allowed:
            files[normalize_title(child.stem)] = child.name
    return files
