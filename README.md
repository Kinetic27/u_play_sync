# UPlaySync 사용 가이드

UPlaySync는 YouTube playlist를 로컬/Jellyfin용 오디오 폴더와 동기화하는 도구입니다. 현재 자동 동기화 경로는 MeTube `/add`/`/history`에 의존하지 않고 `yt-dlp`를 직접 사용합니다. MeTube 앱은 별도 수동 다운로드 도구로 계속 사용할 수 있습니다.

## 핵심 정책

- 기존 `.m4a` 파일명은 대량 변경하지 않습니다.
- 새 다운로드 파일명은 MeTube 기본 출력과 호환되는 제목 기반 형식(`%(title)s.%(ext)s`)을 유지합니다.
- 중복/삭제/실패 판단은 `sync_state.json`의 video id 기반 상태를 우선 사용합니다.
- `id_map.json`과 `download_history.json`은 첫 실행 시 `sync_state.json`으로 마이그레이션되며, 호환성을 위해 mirror로 계속 기록됩니다.

## 사전 요구 사항

1. Python 3.11+ 또는 Docker 환경
2. `ffmpeg` 설치: `yt-dlp` 오디오 후처리에 필요합니다.
3. Python dependencies:

```bash
pip install -r requirements.txt Flask
```

## 동기화 실행 방법

```bash
cd /home/kinetic27/programming/uplaysync
python3 sync.py
```

Docker/compose 사용 시 state directory가 `/app/state`에 mount되고 `UPLAYSYNC_STATE_FILE=/app/state/sync_state.json`로 보존됩니다.

```bash
mkdir -p state
docker compose up --build
```

웹 UI는 기본적으로 `http://localhost:5000`에서 실행됩니다.

관리 페이지는 `http://localhost:5000/manage`에서 확인할 수 있습니다. 이 페이지는 마지막 플레이리스트 스냅샷 기준 상태, 다운로드 큐, 휴지통 복원/재다운로드 작업을 제공합니다. 하드 삭제는 하지 않고 같은 폴더의 `.uplaysync-trash`로 이동합니다.

## 작동 방식

1. `config.yaml`의 playlist 목록을 읽습니다.
2. `yt-dlp`로 playlist metadata를 가져옵니다.
3. 각 playlist folder의 기존 파일을 title-compatible 방식으로 인덱싱합니다.
4. `sync_state.json`의 video id 상태와 실제 파일 존재 여부를 확인합니다.
5. 이미 받은 파일은 건너뜁니다.
6. state에는 있지만 실제 파일이 삭제된 항목은 다시 다운로드 대상으로 봅니다.
7. 새 항목은 `yt-dlp`로 직접 m4a 오디오를 다운로드합니다.
8. 성공/실패 상태를 `sync_state.json`에 기록하고 legacy `id_map.json`/`download_history.json`도 mirror합니다.

## 설정

기존 설정은 그대로 유지됩니다.

```yaml
metube_url: "http://localhost:8081" # legacy/manual compatibility; direct backend does not require it
playlists:
  - name: "플레이리스트 이름"
    url: "https://example.com/playlist?list=..."
    folder: "/로컬/저장/경로"
    metube_folder: "서버내/저장/경로" # legacy/manual compatibility
schedule_interval: 8
retry_failed: false
```

`retry_failed: false`가 기본입니다. 실패/비공개/차단 항목은 무한 재시도하지 않고 상태에 남깁니다.

## 상태 파일

- `sync_state.json`: canonical state (local default). 관리 페이지의 플레이리스트 스냅샷, 다운로드 큐, 휴지통 메타데이터도 이 파일 안에 저장됩니다.
- `id_map.json`: legacy mirror
- `download_history.json`: legacy mirror

첫 migration 전에는 `*.bak-sync-state-migration-YYYYMMDD-HHMMSS` 백업을 생성합니다.

## 테스트

```bash
python -m unittest discover -s tests
python -m py_compile sync.py web/app.py $(find uplaysync -name '*.py' -print)
```

테스트는 임시 폴더와 mock downloader를 사용하며 live media 폴더에 쓰지 않습니다.

## 주의

- MeTube 앱 자체는 제거하지 않습니다.
- 기존 Jellyfin media 파일을 대량 rename/delete하지 않습니다.
- live media 경로에서 실험하지 말고 staging 폴더로 smoke test를 먼저 수행하세요.
