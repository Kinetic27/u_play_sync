from flask import Flask, render_template, Response, jsonify
import subprocess
import time
import os
import sys

app = Flask(__name__)

# UplinkSync 루트 디렉토리 (config.yaml 등이 있는 곳)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SYNC_SCRIPT = os.path.join(BASE_DIR, '..', 'sync.py')

@app.route('/')
def index():
    return render_template('index.html')

current_process = None

@app.route('/api/run')
def run_sync():
    """
    sync.py를 실행하고 출력을 SSE로 스트리밍합니다.
    """
    global current_process
    
    def generate():
        global current_process
        # 버퍼링 없이 출력하기 위해 -u 옵션 사용
        process = subprocess.Popen(
            [sys.executable, '-u', SYNC_SCRIPT],
            cwd=os.path.join(BASE_DIR, '..'), # 상위 디렉토리에서 실행
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )
        current_process = process
        
        yield "data: [시스템] 동기화 프로세스를 시작합니다...\n\n"
        
        try:
            for line in iter(process.stdout.readline, ''):
                if line:
                    # SSE 포맷에 맞춰 전송 (data: 메시지\n\n)
                    yield f"data: {line.strip()}\n\n"
            
            process.wait()
            yield f"data: [시스템] 프로세스 종료 (Exit Code: {process.returncode})\n\n"
            yield "event: close\ndata: close\n\n"
            
        except Exception as e:
            yield f"data: [오류] 실행 중 에러 발생: {str(e)}\n\n"
            yield "event: close\ndata: close\n\n"
        finally:
            current_process = None

    return Response(generate(), mimetype='text/event-stream')

@app.route('/api/stop', methods=['POST'])
def stop_sync():
    global current_process
    if current_process:
        current_process.terminate()
        try:
            current_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            current_process.kill()
        current_process = None
        return jsonify({"status": "stopped", "message": "프로세스가 강제로 중지되었습니다."})
    return jsonify({"status": "no_process", "message": "실행 중인 프로세스가 없습니다."})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
