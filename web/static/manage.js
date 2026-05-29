document.addEventListener('DOMContentLoaded', () => {
    const summaryEl = document.getElementById('manageSummary');
    const queueEl = document.getElementById('queueList');
    const playlistPanelsEl = document.getElementById('playlistPanels');
    const trashEl = document.getElementById('trashList');
    const statusBadge = document.getElementById('manageStatusBadge');
    const statusText = document.getElementById('manageStatusText');
    const reloadBtn = document.getElementById('reloadManageBtn');

    let refreshTimer = null;
    let currentData = null;

    const statusLabels = {
        downloaded: '완료',
        failed: '실패',
        missing: '파일 없음',
        not_downloaded: '미다운',
        queued: '대기',
        running: '진행 중',
        trashed: '휴지통',
        completed: '완료',
        canceled: '취소됨',
        unknown: '알 수 없음'
    };

    function esc(value) {
        return String(value ?? '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }

    function setStatus(kind, text) {
        statusBadge.className = 'status-badge' + (kind ? ' ' + kind : '');
        statusText.textContent = text;
    }

    async function api(path, options = {}) {
        const res = await fetch(path, {
            ...options,
            headers: {
                'Content-Type': 'application/json',
                ...(options.headers || {})
            }
        });
        const data = await res.json();
        if (!res.ok || data.status === 'error') {
            throw new Error(data.error || data.message || '요청 실패');
        }
        return data;
    }

    async function loadManage() {
        try {
            currentData = await api('/api/manage?t=' + Date.now());
            render(currentData);
            const active = currentData.summary?.queue_active || 0;
            setStatus(active > 0 ? 'running' : '', active > 0 ? `큐 ${active}개 진행/대기` : '대기 중');
        } catch (err) {
            console.error(err);
            setStatus('error', '오류');
            queueEl.innerHTML = `<div class="empty-state">관리 정보를 불러오지 못했습니다: ${esc(err.message)}</div>`;
        }
    }

    function render(data) {
        renderSummary(data.summary || {});
        renderQueue(data.queue || []);
        renderPlaylists(data.playlists || []);
        renderTrash(data.trash || []);
    }

    function renderSummary(summary) {
        const cards = [
            ['플레이리스트', summary.playlists || 0],
            ['스캔 항목', summary.items || 0],
            ['큐 활성', summary.queue_active || 0],
            ['휴지통', summary.trash || 0]
        ];
        summaryEl.innerHTML = cards.map(([label, value]) => `
            <div class="summary-card">
                <div class="summary-value">${esc(value)}</div>
                <div class="summary-label">${esc(label)}</div>
            </div>
        `).join('');
    }

    function renderQueue(queue) {
        if (!queue.length) {
            queueEl.innerHTML = '<div class="empty-state">큐가 비어 있습니다.</div>';
            return;
        }
        queueEl.innerHTML = queue.slice().reverse().map(job => `
            <div class="queue-item">
                <div>
                    <div class="item-title">${esc(job.title || job.video_id)}</div>
                    <div class="item-meta">
                        ${badge(job.status)} ${esc(job.action || '')} · ${esc(job.video_id)}
                        ${job.error ? ` · <span class="error-text">${esc(job.error)}</span>` : ''}
                    </div>
                </div>
                <div class="row-actions">
                    ${['queued', 'running'].includes(job.status) ? `<button class="tiny-button danger" data-cancel-job="${esc(job.id)}">취소/중지</button>` : ''}
                </div>
            </div>
        `).join('');
    }

    function renderPlaylists(playlists) {
        if (!playlists.length) {
            playlistPanelsEl.innerHTML = '<div class="empty-state">설정된 플레이리스트가 없습니다.</div>';
            return;
        }
        playlistPanelsEl.innerHTML = playlists.map(pl => `
            <article class="playlist-panel">
                <div class="playlist-panel-header">
                    <div>
                        <h3>${esc(pl.name)}</h3>
                        <div class="item-meta">${esc(pl.folder || '')}</div>
                        <div class="item-meta">최근 스캔: ${esc(pl.last_scanned_at || '없음')}</div>
                    </div>
                    <button class="tiny-button" data-refresh-playlist="${esc(pl.index)}">수동 갱신</button>
                </div>
                ${renderCounts(pl.counts || {})}
                ${renderItemsTable(pl.items || [])}
            </article>
        `).join('');
    }

    function renderCounts(counts) {
        const entries = Object.entries(counts);
        if (!entries.length) {
            return '<div class="item-meta">아직 스캔된 항목이 없습니다.</div>';
        }
        return `<div class="status-counts">${entries.map(([status, count]) => `
            <span>${badge(status)} ${esc(count)}</span>
        `).join('')}</div>`;
    }

    function renderItemsTable(items) {
        if (!items.length) {
            return '<div class="empty-state compact">스냅샷 없음. 수동 갱신을 눌러 현재 상태를 가져오세요.</div>';
        }
        return `
            <div class="manage-table-wrap">
                <table class="manage-table">
                    <thead>
                        <tr>
                            <th>상태</th>
                            <th>제목</th>
                            <th>파일/오류</th>
                            <th>작업</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${items.map(renderItemRow).join('')}
                    </tbody>
                </table>
            </div>
        `;
    }

    function renderItemRow(item) {
        return `
            <tr>
                <td>${badge(item.status)}</td>
                <td>
                    <div class="item-title">${esc(item.title || item.video_id)}</div>
                    <div class="item-meta">${esc(item.video_id)}</div>
                </td>
                <td>
                    <div>${esc(item.filename || '-')}</div>
                    ${item.failure_reason ? `<div class="error-text">${esc(item.failure_reason)}</div>` : ''}
                </td>
                <td><div class="row-actions">${itemActions(item)}</div></td>
            </tr>
        `;
    }

    function itemActions(item) {
        const id = esc(item.video_id);
        if (item.status === 'queued' || item.status === 'running') {
            return '<span class="muted">큐에서 관리</span>';
        }
        if (item.status === 'downloaded') {
            return `
                <button class="tiny-button" data-enqueue="${id}" data-action="redownload">재다운</button>
                <button class="tiny-button danger" data-trash="${id}">휴지통</button>
            `;
        }
        if (item.status === 'failed') {
            return `<button class="tiny-button" data-enqueue="${id}" data-action="retry_failed">재시도</button>`;
        }
        if (item.status === 'missing') {
            return `<button class="tiny-button" data-enqueue="${id}" data-action="redownload">재다운</button>`;
        }
        if (item.status === 'trashed') {
            return `
                <button class="tiny-button" data-restore="${id}">복원</button>
                <button class="tiny-button" data-enqueue="${id}" data-action="redownload">재다운</button>
            `;
        }
        return `<button class="tiny-button" data-enqueue="${id}" data-action="download">다운로드</button>`;
    }

    function renderTrash(trash) {
        if (!trash.length) {
            trashEl.innerHTML = '<div class="empty-state">휴지통이 비어 있습니다.</div>';
            return;
        }
        trashEl.innerHTML = trash.map(item => `
            <div class="queue-item">
                <div>
                    <div class="item-title">${esc(item.title || item.filename || item.video_id)}</div>
                    <div class="item-meta">${esc(item.filename || '')} · ${esc(item.trashed_at || '')}</div>
                </div>
                <div class="row-actions">
                    <button class="tiny-button" data-restore="${esc(item.video_id)}">복원</button>
                    <button class="tiny-button" data-enqueue="${esc(item.video_id)}" data-action="redownload">재다운</button>
                </div>
            </div>
        `).join('');
    }


    function badge(status) {
        const cls = String(status || 'unknown').replace(/[^a-z0-9_-]/gi, '');
        return `<span class="item-status status-${cls}">${esc(statusLabels[status] || status || '알 수 없음')}</span>`;
    }

    async function mutate(button, fn) {
        const oldText = button.textContent;
        button.disabled = true;
        button.textContent = '처리 중';
        try {
            await fn();
            await loadManage();
        } catch (err) {
            alert(err.message);
        } finally {
            button.disabled = false;
            button.textContent = oldText;
        }
    }

    document.addEventListener('click', (e) => {
        const button = e.target.closest('button');
        if (!button) return;
        if (button.dataset.refreshPlaylist !== undefined) {
            mutate(button, () => api(`/api/manage/playlists/${button.dataset.refreshPlaylist}/refresh`, { method: 'POST' }));
        } else if (button.dataset.enqueue) {
            mutate(button, () => api(`/api/manage/items/${button.dataset.enqueue}/enqueue`, {
                method: 'POST',
                body: JSON.stringify({ action: button.dataset.action || 'download' })
            }));
        } else if (button.dataset.trash) {
            if (!confirm('파일을 휴지통으로 이동할까요? 하드 삭제는 하지 않습니다.')) return;
            mutate(button, () => api(`/api/manage/items/${button.dataset.trash}/trash`, { method: 'POST' }));
        } else if (button.dataset.restore) {
            mutate(button, () => api(`/api/manage/items/${button.dataset.restore}/restore`, { method: 'POST' }));
        } else if (button.dataset.cancelJob) {
            mutate(button, () => api(`/api/manage/queue/${button.dataset.cancelJob}/cancel`, { method: 'POST' }));
        }
    });

    reloadBtn.addEventListener('click', loadManage);
    loadManage();
    refreshTimer = setInterval(loadManage, 3000);
    window.addEventListener('beforeunload', () => clearInterval(refreshTimer));
});
