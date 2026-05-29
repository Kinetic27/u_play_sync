from typing import Any


def get_playlist_items(playlist_url: str) -> list[dict[str, Any]]:
    """Fetch playlist metadata only."""
    import yt_dlp

    ydl_opts = {
        "extract_flat": True,
        "quiet": True,
        "ignoreerrors": True,
        "http_headers": {
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        },
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        result = ydl.extract_info(playlist_url, download=False)
        if result and "entries" in result:
            return [entry for entry in result["entries"] if entry]
        return []
