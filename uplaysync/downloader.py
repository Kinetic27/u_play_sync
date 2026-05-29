from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


class DownloadCancelled(Exception):
    """Raised internally when a queued download is cancelled."""


@dataclass
class DownloadResult:
    ok: bool
    video_id: str
    title: str | None
    url: str
    filename: str | None = None
    path: str | None = None
    error: str | None = None
    preexisting: bool = False
    cancelled: bool = False


class DirectYtdlpDownloader:
    """Direct yt-dlp audio downloader with MeTube-compatible title output."""

    def __init__(self, youtubedl_cls: Any | None = None):
        self._youtubedl_cls = youtubedl_cls

    def _youtube_dl_cls(self):
        if self._youtubedl_cls is not None:
            return self._youtubedl_cls
        import yt_dlp

        return yt_dlp.YoutubeDL

    def build_options(self, folder: str | Path, cancel_event=None) -> dict[str, Any]:
        folder = Path(folder)
        opts = {
            "format": "bestaudio[ext=m4a]/bestaudio/best",
            "outtmpl": str(folder / "%(title)s.%(ext)s"),
            "noplaylist": True,
            "ignoreerrors": False,
            "overwrites": False,
            "continuedl": True,
            "quiet": False,
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "m4a",
                }
            ],
        }
        if cancel_event is not None:
            def _cancel_hook(_status):
                if cancel_event.is_set():
                    raise DownloadCancelled("download cancelled")
            opts["progress_hooks"] = [_cancel_hook]
        return opts

    def download(self, *, url: str, video_id: str, title: str | None, folder: str | Path, cancel_event=None) -> DownloadResult:
        folder_path = Path(folder)
        folder_path.mkdir(parents=True, exist_ok=True)
        before = {p.name for p in folder_path.iterdir() if p.is_file()}
        if cancel_event is not None and cancel_event.is_set():
            return DownloadResult(False, video_id, title, url, error="download cancelled", cancelled=True)
        opts = self.build_options(folder_path, cancel_event=cancel_event)
        try:
            ydl_cls = self._youtube_dl_cls()
            with ydl_cls(opts) as ydl:
                info = ydl.extract_info(url, download=True)
            final_path = self._find_final_path(info, folder_path, before)
            if final_path is None:
                return DownloadResult(False, video_id, title, url, error="download completed but final file was not found")
            return DownloadResult(
                True,
                video_id,
                title,
                url,
                filename=final_path.name,
                path=str(final_path),
                preexisting=final_path.name in before,
            )
        except DownloadCancelled as exc:
            return DownloadResult(False, video_id, title, url, error=str(exc), cancelled=True)
        except Exception as exc:  # yt-dlp raises many concrete exception types
            return DownloadResult(False, video_id, title, url, error=str(exc))

    def _find_final_path(self, info: dict[str, Any] | None, folder: Path, before: set[str]) -> Path | None:
        if info:
            for requested in info.get("requested_downloads") or []:
                candidate = requested.get("filepath") or requested.get("filename")
                if candidate and Path(candidate).exists():
                    return Path(candidate)
            for key in ("filepath", "_filename", "filename"):
                candidate = info.get(key)
                if candidate and Path(candidate).exists():
                    return Path(candidate)
        after = [p for p in folder.iterdir() if p.is_file() and p.name not in before]
        if after:
            return max(after, key=lambda p: p.stat().st_mtime)
        return None
