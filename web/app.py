from flask import Flask, render_template, Response, jsonify, request
import subprocess
import os
import sys
import yaml
from apscheduler.schedulers.background import BackgroundScheduler
import atexit
import json
import datetime
import threading

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from uplaysync.config import merge_config_preserving_unknown, strip_legacy_metube_fields  # noqa: E402
from uplaysync.state import (  # noqa: E402
    DOWNLOAD_HISTORY_FILE,
    ID_MAP_FILE,
    STATE_FILE,
    load_state_file,
    save_state,
)

CONFIG_FILE_PATH = os.path.join(PROJECT_ROOT, 'config.yaml')
SYNC_SCRIPT_PATH = os.path.join(PROJECT_ROOT, 'sync.py')
STATUS_FILE_PATH = os.path.join(PROJECT_ROOT, 'status.json')
STATE_FILE_PATH = os.environ.get('UPLAYSYNC_STATE_FILE', os.path.join(PROJECT_ROOT, STATE_FILE))
ID_MAP_PATH = os.environ.get('UPLAYSYNC_ID_MAP_FILE', os.path.join(PROJECT_ROOT, ID_MAP_FILE))
HISTORY_PATH = os.environ.get('UPLAYSYNC_HISTORY_FILE', os.path.join(PROJECT_ROOT, DOWNLOAD_HISTORY_FILE))

# Global Scheduler / process state
scheduler = BackgroundScheduler()
scheduler.start()
atexit.register(lambda: scheduler.shutdown())
current_process = None
sync_process_lock = threading.Lock()


def run_sync_job():
    """Scheduled job to run sync."""
    global current_process
    if not sync_process_lock.acquire(blocking=False):
        print("[Scheduler] Sync skipped because another sync is already running.")
        return
    print("[Scheduler] Starting scheduled sync...")
    try:
        with open(STATUS_FILE_PATH, 'w', encoding='utf-8') as f:
            json.dump({'last_run': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}, f)
        current_process = subprocess.Popen([sys.executable, SYNC_SCRIPT_PATH], cwd=PROJECT_ROOT)
        current_process.wait()
        if current_process.returncode != 0:
            raise subprocess.CalledProcessError(current_process.returncode, [sys.executable, SYNC_SCRIPT_PATH])
        print("[Scheduler] Sync job completed.")
    except Exception as e:
        print(f"[Scheduler] Sync job failed: {e}")
    finally:
        current_process = None
        sync_process_lock.release()


def update_scheduler():
    """Update scheduler based on config."""
    try:
        if os.path.exists(CONFIG_FILE_PATH):
            with open(CONFIG_FILE_PATH, 'r', encoding='utf-8') as f:
                config = strip_legacy_metube_fields(yaml.safe_load(f) or {})

            interval = int(config.get('schedule_interval', 0))
            print(f"[Scheduler] Configured interval: {interval} hours (Type: {type(interval)})")

            existing_job = scheduler.get_job('auto_sync')
            if existing_job:
                existing_job.remove()
                print("[Scheduler] Removed existing auto_sync job.")

            if interval > 0:
                scheduler.add_job(
                    run_sync_job,
                    'interval',
                    hours=interval,
                    id='auto_sync',
                    replace_existing=True,
                    max_instances=1,
                    coalesce=True,
                )
                print(f"[Scheduler] Auto sync scheduled every {interval} hours.")
                job = scheduler.get_job('auto_sync')
                if job:
                    print(f"[Scheduler] Next run at: {job.next_run_time}")
            else:
                print("[Scheduler] Auto sync disabled (interval is 0).")
    except Exception as e:
        print(f"[Scheduler] Error updating scheduler: {e}")
        import traceback
        traceback.print_exc()


# Initialize scheduler on startup
update_scheduler()


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/run')
def run_sync():
    """Run sync.py and stream output as SSE."""
    if not sync_process_lock.acquire(blocking=False):
        return jsonify({'status': 'already_running', 'message': '이미 동기화 작업이 실행 중입니다.'}), 409

    def generate():
        global current_process
        yield "data: [시스템] 동기화 프로세스를 시작합니다...\n\n"
        try:
            current_process = subprocess.Popen(
                [sys.executable, "-u", SYNC_SCRIPT_PATH],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                cwd=PROJECT_ROOT,
            )

            for line in current_process.stdout:
                yield f"data: {line.strip()}\n\n"

            current_process.wait()
            if current_process.returncode == 0:
                yield "data: [시스템] 프로세스 종료 (성공)\n\n"
            else:
                yield f"data: [시스템] 프로세스 종료 (오류 코드: {current_process.returncode})\n\n"
        except Exception as e:
            yield f"data: [오류] 실행 중 예외 발생: {str(e)}\n\n"
        finally:
            current_process = None
            sync_process_lock.release()

        yield "event: close\ndata: close\n\n"

    return Response(generate(), mimetype='text/event-stream')


@app.route('/api/stop', methods=['POST'])
def stop_sync():
    global current_process
    if current_process and current_process.poll() is None:
        current_process.terminate()
        try:
            current_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            current_process.kill()
            current_process.wait(timeout=5)
        return jsonify({'status': 'stopped', 'message': '동기화 작업이 중지되었습니다.'})
    return jsonify({'status': 'idle', 'message': '실행 중인 동기화 작업이 없습니다.'})


@app.route('/api/config', methods=['GET'])
def get_config():
    try:
        config = {}
        if os.path.exists(CONFIG_FILE_PATH):
            with open(CONFIG_FILE_PATH, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f) or {}

        if os.path.exists(STATUS_FILE_PATH):
            try:
                with open(STATUS_FILE_PATH, 'r', encoding='utf-8') as f:
                    content = f.read().strip()
                    if content:
                        status = json.loads(content)
                        config['last_run'] = status.get('last_run')
            except Exception as e:
                print(f"[API] Warning: Failed to parse status.json: {e}")

        job = scheduler.get_job('auto_sync')
        if job and job.next_run_time:
            config['next_run'] = job.next_run_time.strftime('%Y-%m-%d %H:%M:%S')
        else:
            config['next_run'] = None

        return jsonify(config)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/config', methods=['POST'])
def save_config():
    try:
        new_config = request.json
        print(f"[API] Received config save request: {new_config}")

        if not new_config:
            return jsonify({'error': 'No data provided'}), 400

        existing = {}
        if os.path.exists(CONFIG_FILE_PATH):
            with open(CONFIG_FILE_PATH, 'r', encoding='utf-8') as f:
                existing = yaml.safe_load(f) or {}
        merged = merge_config_preserving_unknown(existing, new_config)

        with open(CONFIG_FILE_PATH, 'w', encoding='utf-8') as f:
            yaml.dump(merged, f, allow_unicode=True, default_flow_style=False)

        update_scheduler()
        return jsonify({'status': 'success', 'message': '설정이 저장되었습니다.'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def _history_from_state():
    state = load_state_file(STATE_FILE_PATH)
    items = state.get('items', {})
    result = []
    for vid in reversed(state.get('history', [])):
        entry = items.get(vid, {})
        result.append({
            'id': vid,
            'filename': entry.get('filename') or f"ID: {vid}",
            'status': entry.get('status') or 'unknown',
            'failure_reason': entry.get('failure_reason'),
        })
    return result


def _history_from_legacy():
    id_map = {}
    if os.path.exists(ID_MAP_PATH):
        with open(ID_MAP_PATH, 'r', encoding='utf-8') as f:
            id_map = json.load(f)
    history_ids = []
    if os.path.exists(HISTORY_PATH):
        with open(HISTORY_PATH, 'r', encoding='utf-8') as f:
            history_ids = json.load(f)
    return [
        {
            'id': vid,
            'filename': id_map.get(vid, f"ID: {vid}"),
            'status': 'failed' if str(id_map.get(vid, '')).startswith('ERROR:') else 'downloaded',
            'failure_reason': str(id_map.get(vid, ''))[len('ERROR:'):].strip()
            if str(id_map.get(vid, '')).startswith('ERROR:') else None,
        }
        for vid in reversed(history_ids)
    ]


@app.route('/api/history', methods=['GET'])
def get_history():
    try:
        if os.path.exists(STATE_FILE_PATH):
            state_history = _history_from_state()
            if state_history or not os.path.exists(HISTORY_PATH):
                return jsonify(state_history)
        return jsonify(_history_from_legacy())
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/history', methods=['DELETE'])
def clear_history():
    try:
        if os.path.exists(STATE_FILE_PATH):
            sync_state = load_state_file(STATE_FILE_PATH)
            sync_state['history'] = []
            save_state(sync_state, STATE_FILE_PATH, ID_MAP_PATH, HISTORY_PATH)
        else:
            with open(HISTORY_PATH, 'w', encoding='utf-8') as f:
                json.dump([], f)
        return jsonify({'status': 'success', 'message': '기록이 삭제되었습니다.'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
