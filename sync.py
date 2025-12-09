import yaml
import os
import requests
import yt_dlp
import json
import re

CONFIG_FILE = 'config.yaml'

def load_config():
    with open(CONFIG_FILE, 'r') as f:
        return yaml.safe_load(f)

def normalize_title(s):
    """
    비교를 위해 문자열을 정규화합니다.
    특수문자로 인한 차이(예: '|' vs '｜', '/' vs '_')를 무시하기 위해
    알파벳, 숫자, 한글 등 주요 문자만 남기고 소문자로 변환합니다.
    """
    if not s:
        return ""
    # 유니코드 정규화는 생략하고, 간단히 특수문자 제거 방식을 사용
    # \w: 알파벳, 숫자, _, 한글 등
    # 특수문자를 공백으로 치환하여 단어 경계 유지
    s = re.sub(r'[^\w\s]', ' ', s) 
    # 연속된 공백을 하나로
    s = re.sub(r'\s+', ' ', s)
    return s.strip().lower()

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
    로컬 폴더에 있는 파일들을 정규화된 이름으로 매핑하여 반환합니다.
    반환값: {normalized_name: original_filename}
    """
    if not os.path.exists(folder_path):
        return {}
    
    files = {}
    for f in os.listdir(folder_path):
        # m4a 파일만 대상으로 하거나, 모든 파일을 대상으로 할 수 있습니다.
        name, _ = os.path.splitext(f)
        norm_name = normalize_title(name)
        files[norm_name] = f
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
        existing_files_map = get_existing_files(local_folder)
        print(f"Found {len(existing_files_map)} existing files in {local_folder}.")

        # 3. 비교 및 다운로드 요청
        added_count = 0
        total_items = len(items)
        for i, item in enumerate(items, 1):
            title = item.get('title')
            if not title:
                continue

            normalized_title = normalize_title(title)
            
            if normalized_title in existing_files_map:
                continue
            
            # 디버깅: 왜 매칭이 안 되었는지 확인할 수 있도록 로그를 남길 수도 있음
            # print(f"DEBUG: No match for '{title}' (Normalized: '{normalized_title}')")

            print(f"[{i}/{total_items}] Queueing download: {title}")
            video_url = item.get('url') or item.get('webpage_url')
            if video_url and not video_url.startswith('http'):
                 video_url = f"https://www.youtube.com/watch?v={video_url}"

            if send_to_metube(metube_url, video_url, playlist['metube_folder']):
                added_count += 1
        
        print(f"Finished processing {playlist['name']}. Added {added_count} new items.\n")

if __name__ == "__main__":
    main()
