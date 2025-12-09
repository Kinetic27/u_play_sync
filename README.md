# UplinkSync 사용 가이드

이 프로젝트는 플레이리스트를 MeTube 서비스와 동기화하여 로컬에 다운로드하는 도구입니다.

## 1. 사전 준비

### 필수 요구 사항
*   **Docker MeTube Container**: 로컬(`http://localhost:8081`) 또는 원격 서버에 MeTube가 실행 중이어야 합니다.
*   **Python 3.11+**: 스크립트 실행을 위한 Python 환경.

### 설치 및 초기화
최초 1회만 설정하면 됩니다.

```bash
# 가상 환경 생성
python3 -m venv venv

# 가상 환경 활성화
source venv/bin/activate

# 의존성 설치
pip install -r requirements.txt
```

## 2. 설정 (`config.yaml`)

`config.yaml` 파일을 생성하여 아래와 같이 설정합니다. 이 파일은 `.gitignore`에 포함되어 있어 개인 설정이 유출되지 않습니다.

```yaml
metube_url: "http://localhost:8081"  # MeTube 서버 주소
playlists:
  - name: "플레이리스트 이름 (로그용)"
    url: "https://xxxxxxx.com/playlist?list=..."  # 플레이리스트 URL
    folder: "/opt/xxxxxx/downloads/playlist_folder"  # 로컬에 이미 다운로드된 확인용 경로
    metube_folder: "playlist_folder"  # MeTube가 다운로드할 폴더명 (MeTube 설정에 따름)
```

## 3. 실행 방법

새로운 곡을 확인하고 다운로드하려면 아래 명령어를 실행하세요.

```bash
cd /home/kinetic27/programming/uplaysync
source venv/bin/activate
python3 sync.py
```

## 4. 작동 원리
1.  플레이리스트의 최신 목록을 가져옵니다.
2.  `folder` 경로에 있는 파일들을 스캔하여 이미 가지고 있는 곡인지 확인합니다.
3.  없는 곡이 있다면 `metube_url`로 다운로드 요청을 보냅니다.
    *   이때 `metube_folder`를 파라미터로 함께 보냅니다.
