from flask import Flask, render_template, Response, jsonify, request
import subprocess
import time
import os
import sys
import yaml
from apscheduler.schedulers.background import BackgroundScheduler
import atexit
import json # Added for get_history, was missing in original

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Go up one level to find config.yaml
PROJECT_ROOT = os.path.dirname(BASE_DIR)
CONFIG_FILE_PATH = os.path.join(PROJECT_ROOT, 'config.yaml')
SYNC_SCRIPT_PATH = os.path.join(PROJECT_ROOT, 'sync.py')
STATUS_FILE_PATH = os.path.join(PROJECT_ROOT, 'status.json')

# Global Scheduler
scheduler = BackgroundScheduler()
scheduler.start()
atexit.register(lambda: scheduler.shutdown())

def run_sync_job():
    """Scheduled job to run sync"""
    print("[Scheduler] Starting scheduled sync...")
    # Use subprocess to run sync.py, just like the manual trigger
    # But output goes to standard logs, not SSE stream directly (unless we bridge it)
    try:
        # Record start time
        with open(STATUS_FILE_PATH, 'w') as f:
            json.dump({'last_run': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}, f)
            
        subprocess.run([sys.executable, SYNC_SCRIPT_PATH], check=True)
        print("[Scheduler] Sync job completed.")
    except Exception as e:
        print(f"[Scheduler] Sync job failed: {e}")

def update_scheduler():
    """Update scheduler based on config"""
    try:
        if os.path.exists(CONFIG_FILE_PATH):
            with open(CONFIG_FILE_PATH, 'r') as f:
                config = yaml.safe_load(f)
            
            interval = config.get('schedule_interval', 0)
            
            # Remove existing job
            existing_job = scheduler.get_job('auto_sync')
            if existing_job:
                existing_job.remove()
            
            if interval > 0:
                # interval is in hours
                scheduler.add_job(
                    run_sync_job, 
                    'interval', 
                    hours=interval, 
                    id='auto_sync',
                    replace_existing=True
                )
                print(f"[Scheduler] Auto sync scheduled every {interval} hours.")
            else:
                print("[Scheduler] Auto sync disabled.")
    except Exception as e:
        print(f"[Scheduler] Error updating scheduler: {e}")

# Initialize scheduler on startup
update_scheduler()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/run')
def run_sync():
    """
    sync.py를 실행하고 출력을 SSE로 스트리밍합니다.
    """
    
    def generate():
        yield "data: [시스템] 동기화 프로세스를 시작합니다...\n\n"
        
        try:
            process = subprocess.Popen(
                [sys.executable, "-u", SYNC_SCRIPT_PATH],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
            
            for line in process.stdout:
                yield f"data: {line.strip()}\n\n"
                
            process.wait()
            if process.returncode == 0:
                yield "data: [시스템] 프로세스 종료 (성공)\n\n"
            else:
                yield f"data: [시스템] 프로세스 종료 (오류 코드: {process.returncode})\n\n"
                
        except Exception as e:
            yield f"data: [오류] 실행 중 예외 발생: {str(e)}\n\n"
            
        yield "event: close\ndata: close\n\n"

    return Response(generate(), mimetype='text/event-stream')

@app.route('/api/stop', methods=['POST'])
def stop_sync():
    # In a real scenario, we'd need to track the Popen object globally to kill it.
    # For now, we'll just simulate a stop signal or kill python processes (dangerous).
    # Since we yield 'close' in run_sync, the client disconnects.
    # To truly stop the subprocess, we need a global variable for `process`.
    os.system("pkill -f sync.py") # Simple/Brute-force way for this environment
    return jsonify({'status': 'stopped', 'message': '동기화 작업이 중지 요청되었습니다.'})

@app.route('/api/config', methods=['GET'])
def get_config():
    try:
        config = {}
        if os.path.exists(CONFIG_FILE_PATH):
            with open(CONFIG_FILE_PATH, 'r') as f:
                config = yaml.safe_load(f) or {}
        
        # Merge status info
        if os.path.exists(STATUS_FILE_PATH):
            with open(STATUS_FILE_PATH, 'r') as f:
                status = json.load(f)
                config['last_run'] = status.get('last_run')
                
        return jsonify(config)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/config', methods=['POST'])
def save_config():
    try:
        new_config = request.json
        if not new_config:
            return jsonify({'error': 'No data provided'}), 400
            
        # Basic validation could go here
        
        with open(CONFIG_FILE_PATH, 'w') as f:
            yaml.dump(new_config, f, allow_unicode=True, default_flow_style=False)
        
        # Update scheduler with new config
        update_scheduler()
            
        return jsonify({'status': 'success', 'message': '설정이 저장되었습니다.'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/history', methods=['GET'])
def get_history():
    id_map_path = os.path.join(BASE_DIR, 'id_map.json')
    try:
        if not os.path.exists(id_map_path):
            return jsonify({}) # Return empty object if no history yet
            
        with open(id_map_path, 'r', encoding='utf-8') as f:
            history = json.load(f)
        return jsonify(history)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
