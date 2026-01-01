import yaml
import os
import requests
import yt_dlp
import json
import re
import time

import logging

# Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)

DOWNLOAD_HISTORY_FILE = "download_history.json"
ID_MAP_FILE = "id_map.json"


CONFIG_FILE = 'config.yaml'

def load_config():
    with open(CONFIG_FILE, 'r') as f:
        return yaml.safe_load(f)

import unicodedata

def normalize_title(s):
    """
    비교를 위해 문자열을 정규화합니다.
    특수문자로 인한 차이(예: '|' vs '｜', '/' vs '_')를 무시하기 위해
    알파벳, 숫자, 한글 등 주요 문자만 남기고 소문자로 변환합니다.
    """
    if not s:
        return ""
    
    # 1. 유니코드 정규화 (NFKC): 'Carrà'(NFD) -> 'Carrà'(NFC), '𝐆'(Bold) -> 'G' 로 통일
    s = unicodedata.normalize('NFKC', s)
    
    # 2. 특수문자 제거
    # \w: 알파벳, 숫자, _, 한글 등
    # 특수문자를 공백으로 치환하여 단어 경계 유지
    s = re.sub(r'[^\w\s]', ' ', s) 
    # 연속된 공백을 하나로
    s = re.sub(r'\s+', ' ', s)
    return s.strip().lower()

def get_playlist_items(playlist_url):
    """
    yt-dlp를 사용하여 플레이리스트의 항목을 가져옵니다 (메타데이터만).
    한국어 메타데이터를 우선 요청합니다.
    """
    ydl_opts = {
        'extract_flat': True,
        'quiet': True,
        'ignoreerrors': True,
        'http_headers': {
            'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7'
        }
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

def load_download_history():
    if not os.path.exists(DOWNLOAD_HISTORY_FILE):
        return []
    try:
        with open(DOWNLOAD_HISTORY_FILE, 'r') as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
            return list(data) # Handle case where file was saved as list but read weirdly, or if strictly needed
    except:
        return []

def save_download_history(history_list):
    with open(DOWNLOAD_HISTORY_FILE, 'w') as f:
        json.dump(history_list, f, indent=4, ensure_ascii=False)

def load_id_map():
    if os.path.exists(ID_MAP_FILE):
        try:
            with open(ID_MAP_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_id_map(id_map):
    with open(ID_MAP_FILE, 'w', encoding='utf-8') as f:
        json.dump(id_map, f, ensure_ascii=False, indent=2)

def is_token_match(normalized_yt_title, existing_norm_name):
    """
    토큰 기반 매칭을 수행합니다.
    YouTube 타이틀에서 괄호[...] (...) 안의 내용 제거 후 토큰화
    """
    # YouTube 타이틀에서 괄호[...] (...) 안의 내용 제거 후 토큰화
    title_clean = re.sub(r'\([^)]*\)|\[[^\]]*\]', '', normalized_yt_title)
    normalized_title_clean = normalize_title(title_clean)
    yt_tokens = set(normalized_title_clean.split())
    
    if not yt_tokens:
         yt_tokens = set(normalized_yt_title.split())

    local_tokens = set(existing_norm_name.split())
    
    if len(yt_tokens) > 0 and yt_tokens.issubset(local_tokens):
        return True
    return False

def monitor_downloads(metube_url, expected_items):
    """
    MeTube 히스토리를 모니터링하여 ID를 파일명에 매핑합니다.
    expected_items: [{'id': ..., 'title': ..., 'url': ...}]
    """
    if not expected_items:
        return

    expected_ids = [item['id'] for item in expected_items]
    items_info = {item['id']: item for item in expected_items}

    print(f"\n[모니터링] {len(expected_ids)}개의 항목 완료 대기 중...")
    id_map = load_id_map()
    down_history = load_download_history()
    pending = set(expected_ids)
    
    while pending:
        try:
            resp = requests.get(f"{metube_url}/history", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                done = data.get('done', [])
                queue = data.get('queue', []) + data.get('pending', [])
                
                # Check for finished items
                found = []
                history_changed = False
                
                for item in done:
                    vid = item.get('id')
                    if vid in pending:
                        filename = item.get('filename') # e.g. "Song.m4a"
                        status = item.get('status')
                        
                        if status == 'error' or item.get('msg') == 'error':
                             error_msg = item.get('error') or '알 수 없는 오류'
                             title = items_info[vid].get('title', 'Unknown Title')
                             print(f"  [오류] {title} ({vid}): {error_msg}")
                             
                             # Record failure to prevent infinite retries
                             # Using a special prefix to identify failed items
                             failed_mark = f"ERROR: {error_msg}"
                             
                             if vid in id_map:
                                 del id_map[vid]
                             id_map[vid] = failed_mark
                             
                             # Add to history so user can see it failed
                             if vid in down_history:
                                 down_history.remove(vid)
                             down_history.append(vid)
                             
                             found.append(vid)
                             history_changed = True # Save history to show errors
                             continue

                        if filename:
                            # 경로 제거하고 파일명만 유지
                            # 경로 제거하고 파일명만 유지
                            filename = os.path.basename(filename)
                            
                            # Update Map & Move to End (Recent)
                            if vid in id_map:
                                del id_map[vid]
                            id_map[vid] = filename
                            
                            title = items_info[vid].get('title', vid)
                            print(f"  [완료] {title} -> {filename}")
                            found.append(vid)
                            
                            if vid in down_history:
                                down_history.remove(vid)
                            down_history.append(vid)
                            history_changed = True
                
                for vid in found:
                    pending.remove(vid)
                    
                if found:
                    save_id_map(id_map)
                    
                if history_changed:
                    save_download_history(down_history)
                
                # Check if remaining pending items are actually in queue
                active_ids = {item.get('id') for item in queue}
                
                # Identify lost items (Not in done, Not in queue/pending)
                # They might be failed or cancelled
                lost = [pid for pid in pending if pid not in active_ids]
                for pid in lost:
                    info = items_info.get(pid, {})
                    title = info.get('title', '알 수 없음')
                    url = info.get('url', f"https://youtu.be/{pid}")
                    print(f"  [실종] {title} : {url} (취소/실패됨)")
                    pending.remove(pid)
                
                if not pending:
                    print("[모니터링] 모든 항목 처리 완료.")
                    break
                    
                print(f"  ... {len(pending)}개 남음 (진행 중: {len([p for p in pending if p in active_ids])})")

            
            time.sleep(3)
        except KeyboardInterrupt:
            print("\n[모니터링] 사용자에 의해 중단됨.")
            break
        except Exception as e:
            print(f"[모니터링] 오류: {e}")
            time.sleep(5)


def sync_id_map_from_metube(metube_url):
    """
    MeTube 히스토리에서 전체 기록을 가져와 로컬 id_map을 업데이트합니다.
    이전에 다운로드된 항목들의 매핑 정보를 복구하는 데 도움이 됩니다.
    """

    logging.info("MeTube 히스토리에서 ID 매핑 동기화 중...")
    try:
        logging.info(f"Connecting to MeTube at: {metube_url}/history")
        resp = requests.get(f"{metube_url}/history", timeout=5)
        logging.info(f"MeTube Response Code: {resp.status_code}")
        
        if resp.status_code == 200:
            data = resp.json()
            done = data.get('done', [])
            logging.info(f"Fetched {len(done)} done items from MeTube.")
            
            id_map = load_id_map()
            down_history = load_download_history()
            updated = False
            history_updated = False
            
            for item in done:
                vid = item.get('id')
                filename = item.get('filename')
                if vid and filename:
                    filename = os.path.basename(filename)
                    if vid not in id_map:
                        id_map[vid] = filename
                        updated = True
                        logging.info(f"New history item mapped: {vid} -> {filename}")
                    else:
                        # Existing item: Move to end to mark as 'Recent'
                        del id_map[vid]
                        id_map[vid] = filename
                        updated = True # Force save to persist order change
                    
                    if vid in down_history:
                        down_history.remove(vid)
                    down_history.append(vid)
                    history_updated = True
            
            if updated:
                save_id_map(id_map)
                logging.info(f"히스토리에서 {len(done)}개의 항목으로 id_map 업데이트 완료.")
            else:
                logging.info("ID 매핑이 최신 상태입니다.")
                
            if history_updated:
                save_download_history(down_history)
                logging.info(f"MeTube 기록을 기반으로 다운로드 기록 동기화 완료.")
        else:
            logging.error(f"MeTube responded with error: {resp.text}")
    except Exception as e:
        logging.error(f"id_map 동기화 실패: {e}")

def main():
    # 1. 설정 로드
    config = load_config()
    metube_url = config['metube_url']
    playlists = config['playlists']
    
    # Pre-sync ID map to ensure we have latest filenames
    sync_id_map_from_metube(metube_url)
    
    down_history = load_download_history()
    id_map = load_id_map()
    

    
    total_newly_added = []
    


    for pl in playlists:
        print(f"\n플레이리스트 처리 중: {pl['name']}")
        
        # 2. 로컬 파일 확인
        existing_files_map = get_existing_files(pl['folder']) # {norm_name: real_name}
        existing_filenames = set(existing_files_map.values()) # {real_name}
        
        # 3. 플레이리스트 정보 가져오기
        try:
            items = get_playlist_items(pl['url'])
            print(f"플레이리스트에서 {len(items)}개의 항목을 발견했습니다.")
        except Exception as e:
            print(f"플레이리스트 항목 가져오기 실패: {e}")
            continue

        # 4. 다운로드할 항목 선별
        items_to_download = []
        for item in items:
            vid = item.get('id')
            title = item.get('title')
            
            if not title:
                continue

            # Check download history (Sent previously)
            if vid in down_history:
                 # We sent it before. It should be in our 'total_newly_added' monitoring list (added at start).
                 # So we just skip sending it again.
                 # MeTube might be downloading it.
                 continue
            
            # Check ID Map first (Most accurate)
            if vid in id_map:
                mapped_filename = id_map[vid]
                # Check if mapped filename exists in folder
                if mapped_filename in existing_filenames:
                    # Already exists with mapped name
                    continue
                # If mapped filename is NOT in folder, we MUST download it (User deleted it)
                # Fall through to download
            
            # Check Normalized Title Match (Legacy check)
            # If ID check failed (id not in map), we check title
            normalized_title = normalize_title(title)
            
            if normalized_title in existing_files_map:
                continue
                
            # Check Substring
            if any(normalized_title in f for f in existing_files_map):
                continue

            # Check Token Match
            if any(is_token_match(normalized_title, f) for f in existing_files_map):
                continue
            
            items_to_download.append(item)

        print(f"다운로드할 항목 {len(items_to_download)}개를 식별했습니다.")

        # 5. 다운로드 요청
        added_count = 0
        total_to_download = len(items_to_download)
        current_batch_items = []
        
        for i, item in enumerate(items_to_download, 1):
            vid = item.get('id')
            title = item.get('title')
            print(f"[{i}/{total_to_download}] 다운로드 대기열 추가: {title}")
            
            video_url = item.get('url') or item.get('webpage_url')
            if video_url and not video_url.startswith('http'):
                 video_url = f"https://www.youtube.com/watch?v={video_url}"

            if send_to_metube(metube_url, video_url, pl['metube_folder']):
                added_count += 1
                down_history.add(vid)
                current_batch_items.append({'id': vid, 'title': title, 'url': video_url})
        
        if current_batch_items:
            total_newly_added.extend(current_batch_items)
            save_download_history(down_history)
            
    # 6. Global Monitoring (Monitor all added items across all playlists)
    if total_newly_added:
        monitor_downloads(metube_url, total_newly_added)

if __name__ == "__main__":
    main()
