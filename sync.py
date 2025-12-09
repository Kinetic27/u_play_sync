import yaml
import os
import requests
import yt_dlp
import json

CONFIG_FILE = 'config.yaml'

def load_config():
    with open(CONFIG_FILE, 'r') as f:
        return yaml.safe_load(f)

def get_playlist_items(playlist_url):
    """
    yt-dlp를 사용하여 플레이리스트의 항목을 가져옵니다 (메타데이터만).
    """
    ydl_opts = {
        'extract_flat': True,
        'quiet': True,
        'ignoreerrors': True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        result = ydl.extract_info(playlist_url, download=False)
        if 'entries' in result:
            return result['entries']
        return []

def get_existing_files(folder_path):
    """
    로컬 폴더에 있는 파일들의 기본 이름(확장자 제외)을 반환합니다.
    """
    if not os.path.exists(folder_path):
        return set()
    
    files = set()
    for f in os.listdir(folder_path):
        # m4a 파일만 대상으로 하거나, 모든 파일을 대상으로 할 수 있습니다.
        # 여기서는 파일명 매칭을 위해 확장자를 제거한 이름을 사용합니다.
        name, _ = os.path.splitext(f)
        files.add(name)
    return files

def send_to_metube(metube_url, video_url, folder_name):
    """
    MeTube API에 다운로드를 요청합니다.
    """
    add_url = f"{metube_url}/add"
    payload = {
        "url": video_url,
        "quality": "best",
        "format": "m4a",
        "folder": folder_name
    }
    
    try:
        response = requests.post(add_url, json=payload)
        response.raise_for_status()
        return True
    except requests.exceptions.RequestException as e:
        print(f"Error sending to MeTube: {e}")
        return False

def main():
    config = load_config()
    metube_url = config['metube_url']

    for playlist in config['playlists']:
        print(f"Processing playlist: {playlist['name']}...")
        
        # 1. 플레이리스트 목록 가져오기
        print("Fetching playlist items...")
        items = get_playlist_items(playlist['url'])
        print(f"Found {len(items)} items in playlist.")

        # 2. 로컬 파일 목록 가져오기
        local_folder = playlist['folder']
        existing_files = get_existing_files(local_folder)
        print(f"Found {len(existing_files)} existing files in {local_folder}.")

        # 3. 비교 및 다운로드 요청
        added_count = 0
        for item in items:
            title = item.get('title')
            # yt-dlp might not resolve the full title in flat playlist mode sometimes, 
            # but usually it does. The 'title' here is what we expect the filename to be.
            # Warning: Special characters might be handled differently by filesystem/metube.
            
            # Simple check: if title is vaguely in existing files
            # This is a weak point. existing files might have sanitized names.
            # But let's try direct matching first as user requested.
            
            if title in existing_files:
                continue

            # Check if file exists with sanitize logic roughly
            # (Metube uses yt-dlp sanitization, so we rely on that)
            # For now, if exact match fails, we assume it's new. 
            # This might cause dupes if titles are slightly different (e.g. chars).
            
            # A safer check might be to see if we can find the title substring in existing files?
            # Or just proceed. User warned about dupes.

            print(f"Queueing download: {title}")
            video_url = item.get('url') or item.get('webpage_url')
            # flat extraction gives 'url' usually as ID, need full URL? 
            # yt-dlp flat extract 'url' is usually the video ID or partial. 
            # Let's construct full URL to be safe if it looks like ID.
            if video_url and not video_url.startswith('http'):
                 video_url = f"https://www.youtube.com/watch?v={video_url}"

            if send_to_metube(metube_url, video_url, playlist['metube_folder']):
                added_count += 1
        
        print(f"Finished processing {playlist['name']}. Added {added_count} new items.\n")

if __name__ == "__main__":
    main()
