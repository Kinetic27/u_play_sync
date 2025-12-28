document.addEventListener('DOMContentLoaded', () => {
    const runBtn = document.getElementById('runBtn');
    const stopBtn = document.getElementById('stopBtn');
    const logContainer = document.getElementById('logContainer');
    const statusBadge = document.getElementById('statusBadge');
    const statusText = document.getElementById('statusText');

    let eventSource = null;

    runBtn.addEventListener('click', () => {
        startSync();
    });

    stopBtn.addEventListener('click', () => {
        fetch('/api/stop', { method: 'POST' })
            .then(res => res.json())
            .then(data => {
                addLog('error', `[시스템] ${data.message}`);
                stopSync(true); // Treat as error/cancelled state
            })
            .catch(err => console.error(err));
    });

    function startSync() {
        if (eventSource) {
            eventSource.close();
        }

        // UI Reset
        runBtn.style.display = 'none';
        stopBtn.style.display = 'inline-block';
        
        statusBadge.className = 'status-badge running';
        statusText.textContent = '동기화 중';
        logContainer.innerHTML = '';
        addLog('system', '[시스템] 서버에 동기화 요청을 전송했습니다...');

        // EventSource Connection
        eventSource = new EventSource('/api/run');

        eventSource.onmessage = function(event) {
            // Close signal from server
            if (event.data === 'close' || event.data.includes('[시스템] 프로세스 종료')) {
                // Remove error handler so check doesn't fire when we close
                eventSource.onerror = null;
                stopSync();
                return;
            }
            addLog('normal', event.data);
        };

        eventSource.onerror = function() {
            // Only fire if connection died unexpectedly
            addLog('error', '[오류] 서버와의 연결이 끊어졌습니다.');
            stopSync(true);
        };
    }

    function stopSync(isError = false) {
        if (eventSource) {
            eventSource.close();
            eventSource = null;
        }

        runBtn.style.display = 'inline-block';
        stopBtn.style.display = 'none';
        runBtn.disabled = false;
        runBtn.innerHTML = '<i class="fa-solid fa-bolt"></i> 동기화 시작';
        
        if (isError) {
            statusBadge.className = 'status-badge error';
            statusText.textContent = '중지됨';
        } else {
            statusBadge.className = 'status-badge';
            statusText.textContent = '대기 중';
            addLog('system', '[시스템] 작업이 완료되었습니다.');
        }
    }

    function addLog(type, message) {
        const line = document.createElement('div');
        line.className = `log-line ${type}`;

        // Simple highlighting based on content
        if (message.includes('다운로드 대기열 추가')) {
            line.classList.add('highlight');
        } else if (message.includes('[오류]')) {
            line.classList.add('error');
        } else if (message.includes('[완료]')) {
            line.classList.add('success');
        }

        // Linkify URLs
        const escapedMessage = message.replace(/&/g, '&amp;')
                                      .replace(/</g, '&lt;')
                                      .replace(/>/g, '&gt;')
                                      .replace(/"/g, '&quot;')
                                      .replace(/'/g, '&#039;');
                                      
        const linkedMessage = escapedMessage.replace(
            /(https?:\/\/[^\s)]+)/g, 
            '<a href="$1" target="_blank" style="color: #4facfe; text-decoration: underline;">$1</a>'
        );

        line.innerHTML = linkedMessage;
        
        logContainer.appendChild(line);
        
        // Auto scroll to bottom
        logContainer.scrollTop = logContainer.scrollHeight;
    }
});
