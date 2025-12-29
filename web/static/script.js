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

    // Modal Elements
    const configBtn = document.getElementById('configBtn');
    const configModal = document.getElementById('configModal');
    const closeModals = document.querySelectorAll('.close-modal');
    const saveConfigBtn = document.getElementById('saveConfigBtn');
    const addPlaylistBtn = document.getElementById('addPlaylistBtn');
    const playlistContainer = document.getElementById('playlistContainer');
    const metubeUrlInput = document.getElementById('metubeUrl');
    const scheduleIntervalInput = document.getElementById('scheduleInterval');
    const playlistItemTemplate = document.getElementById('playlistItemTemplate');
    
    // History Elements
    const historyBtn = document.getElementById('historyBtn');
    const historyModal = document.getElementById('historyModal');
    const historyTableBody = document.getElementById('historyTableBody');
    const historySearch = document.getElementById('historySearch');

    let currentConfig = {};
    let fullHistory = []; // Store full history for searching

    // --- Modal Logic ---
    function openModal(modal) {
        modal.style.display = 'block';
    }

    function closeModal(modal) {
        modal.style.display = 'none';
    }

    configBtn.addEventListener('click', () => {
        openModal(configModal);
        fetchConfig();
    });
    
    historyBtn.addEventListener('click', () => {
        openModal(historyModal);
        fetchHistory();
    });

    closeModals.forEach(btn => {
        btn.addEventListener('click', (e) => {
            closeModal(e.target.closest('.modal'));
        });
    });

    window.addEventListener('click', (e) => {
        if (e.target.classList.contains('modal')) {
            closeModal(e.target);
        }
    });

    // --- History Logic ---
    function fetchHistory() {
        fetch('/api/history')
            .then(res => res.json())
            .then(data => {
                // Convert object {id: filename} to array [{id, filename}] and reverse to show latest first
                fullHistory = Object.entries(data).map(([id, filename]) => ({ id, filename })).reverse();
                renderHistory(fullHistory);
            })
            .catch(err => console.error('Error fetching history:', err));
    }

    function renderHistory(items) {
        historyTableBody.innerHTML = '';
        if (items.length === 0) {
            historyTableBody.innerHTML = '<tr><td colspan="2" style="text-align:center; padding: 2rem; color: #888;">기록이 없습니다.</td></tr>';
            return;
        }

        items.forEach(item => {
            const row = document.createElement('tr');
            row.innerHTML = `
                <td><span class="id-badge">${item.id}</span></td>
                <td>${item.filename}</td>
            `;
            historyTableBody.appendChild(row);
        });
    }

    historySearch.addEventListener('input', (e) => {
        const searchTerm = e.target.value.toLowerCase();
        const filtered = fullHistory.filter(item => 
            item.id.toLowerCase().includes(searchTerm) || 
            item.filename.toLowerCase().includes(searchTerm)
        );
        renderHistory(filtered);
    });

    // --- Config Logic ---
    const decreaseBtn = document.getElementById('decreaseInterval');
    const increaseBtn = document.getElementById('increaseInterval');

    decreaseBtn.addEventListener('click', () => {
        let val = parseInt(scheduleIntervalInput.value) || 0;
        if (val > 0) {
            scheduleIntervalInput.value = val - 1;
        }
    });

    increaseBtn.addEventListener('click', () => {
        let val = parseInt(scheduleIntervalInput.value) || 0;
        scheduleIntervalInput.value = val + 1;
    });



    // Validate number input for scheduleInterval (since we changed it to type="text")
    scheduleIntervalInput.addEventListener('input', (e) => {
        e.target.value = e.target.value.replace(/[^0-9]/g, '');
    });

    addPlaylistBtn.addEventListener('click', () => addPlaylistItem());
    saveConfigBtn.addEventListener('click', saveConfig);


    function fetchConfig() {
        fetch('/api/config')
            .then(res => res.json())
            .then(data => {
                currentConfig = data;
                metubeUrlInput.value = data.metube_url || '';
                scheduleIntervalInput.value = data.schedule_interval || 0;
                
                const lastRunDisplay = document.getElementById('lastRunDisplay');
                if (data.last_run) {
                    lastRunDisplay.innerHTML = `<i class="fa-solid fa-check-circle" style="color: var(--primary-color);"></i> 최근 실행: ${data.last_run}`;
                } else {
                    lastRunDisplay.innerHTML = '<i class="fa-solid fa-clock"></i> 최근 실행: 기록 없음';
                }

                renderPlaylists(data.playlists || []);
            })
            .catch(err => alert('설정을 불러오는 중 오류가 발생했습니다: ' + err));
    }

    function renderPlaylists(playlists) {
        playlistContainer.innerHTML = '';
        playlists.forEach(pl => addPlaylistItem(pl));
    }

    function addPlaylistItem(pl = {}) {
        const clone = playlistItemTemplate.content.cloneNode(true);
        const itemDiv = clone.querySelector('.playlist-item');
        
        itemDiv.querySelector('.pl-name').value = pl.name || '';
        itemDiv.querySelector('.pl-url').value = pl.url || '';
        itemDiv.querySelector('.pl-folder').value = pl.folder || '';
        itemDiv.querySelector('.pl-metube').value = pl.metube_folder || '';
        
        itemDiv.querySelector('.delete-btn').addEventListener('click', () => {
            itemDiv.remove();
        });

        playlistContainer.appendChild(itemDiv);
    }

    function saveConfig() {
        const newPlaylists = [];
        const items = playlistContainer.querySelectorAll('.playlist-item');
        
        items.forEach(item => {
            const name = item.querySelector('.pl-name').value.trim();
            const url = item.querySelector('.pl-url').value.trim();
            const folder = item.querySelector('.pl-folder').value.trim();
            const metube_folder = item.querySelector('.pl-metube').value.trim();
            
            if (name && url && folder) {
                newPlaylists.push({
                    name, 
                    url, 
                    folder,
                    metube_folder: metube_folder || undefined
                });
            }
        });

        const newConfig = {
            metube_url: metubeUrlInput.value.trim(),
            schedule_interval: parseInt(scheduleIntervalInput.value) || 0,
            playlists: newPlaylists
        };

        fetch('/api/config', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(newConfig)
        })
        .then(res => res.json())
        .then(data => {
            if (data.status === 'success') {
                alert('설정이 저장되었습니다.');
                configModal.style.display = 'none';
            } else {
                alert('저장 실패: ' + data.error);
            }
        })
        .catch(err => alert('저장 중 오류 발생: ' + err));
    }
});
