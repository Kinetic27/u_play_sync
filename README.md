# UPlaySync 사용 가이드

이 문서는 플레이리스트를 미디어 서버를 통해 로컬 디렉토리와 동기화하는 `sync.py` 스크립트의 사용법을 설명합니다.

## 사전 요구 사항

1.  **서버 실행**: 미디어 서버 컨테이너가 `http://localhost:8081`에서 실행 중이어야 합니다.
2.  **가상 환경**: 프로젝트 디렉토리 내에 Python 가상 환경이 설정되어 있어야 합니다.

## 동기화 실행 방법

터미널에서 다음 명령어를 실행하여 동기화를 시작합니다:

```bash
cd /home/kinetic27/programming/uplaysync
source venv/bin/activate
python3 sync.py
```

## 작동 방식

1.  `config.yaml`에 정의된 플레이리스트 목록을 불러옵니다.
2.  각 플레이리스트에 대해:
    *   원격지에서 최신 곡 목록을 가져옵니다.
    *   로컬 폴더를 스캔하여 이미 다운로드된 곡을 확인합니다.
    *   **누락된 곡**이 있다면 서버 API를 통해 다운로드를 요청합니다.
3.  **큐 모니터링 & 파일명 매핑 (New)**:
    *   스크립트가 서버의 다운로드 대기열을 실시간으로 감시합니다.
    *   다운로드가 완료되면 최종 파일명을 추적하여 내부 데이터베이스(`id_map.json`)에 저장합니다.
    *   이 매핑 정보를 통해 다음 실행 시 파일명이 달라도(예: "Mr. Hong" vs "미스터 홍") 중복 다운로드를 방지합니다.
    *   서버에서 에러가 발생한 항목은 자동으로 감지하고 처리합니다.

## 설정 변경

`config.yaml` 파일을 수정하여 플레이리스트를 추가하거나 경로를 변경할 수 있습니다.

```yaml
metube_url: "http://localhost:8081" # 미디어 서버 주소
playlists:
  - name: "플레이리스트 이름"
    url: "https://example.com/playlist?list=..."
    folder: "/로컬/저장/경로"
    metube_folder: "서버내/저장/경로"
```

## 문제 해결

*   **`ModuleNotFoundError`**: `source venv/bin/activate`를 실행했는지 확인하세요.
*   **서버 연결 오류**: 서버가 실행 중인지, `config.yaml`의 주소가 올바른지 확인하세요.
