// Polling global state
function fetchLiveStatus() {
    fetch('/api/live')
        .then(response => response.json())
        .then(data => {
            updateDashboard(data);
            updateLiveMonitor(data);
            updateGlobalHeader(data);
        })
        .catch(err => console.error("Error fetching live status:", err));
}

function updateGlobalHeader(data) {
    const riskLevelEl = document.getElementById('global-risk-level');
    const riskBadge = document.getElementById('global-risk-badge');
    const systemDot = document.getElementById('system-dot');
    const systemText = document.getElementById('system-text');
    
    if (riskLevelEl && data.risk_level) {
        riskLevelEl.textContent = data.risk_level;
        riskBadge.className = 'risk-badge';
        
        if (data.risk_level === 'CRITICAL') {
            riskBadge.classList.add('critical');
        } else if (data.risk_level === 'HIGH') {
            riskBadge.classList.add('high');
        }
    }

    if (systemText && data.camera_status) {
        systemText.textContent = `Camera ${data.camera_status}`;
        if (data.camera_status === 'OFFLINE') {
            systemDot.style.backgroundColor = 'red';
            systemDot.style.boxShadow = '0 0 10px red';
        } else {
            systemDot.style.backgroundColor = '#2ed573';
            systemDot.style.boxShadow = '0 0 10px #2ed573';
        }
    }
}

function updateDashboard(data) {
    const el = (id) => document.getElementById(id);
    
    if (el('dash-attention')) el('dash-attention').textContent = data.attention_score;
    if (el('dash-fps')) el('dash-fps').textContent = data.fps;
    if (el('dash-camera-status')) el('dash-camera-status').textContent = data.camera_status;
    if (el('dash-ear')) el('dash-ear').textContent = parseFloat(data.ear).toFixed(2);
    if (el('dash-mar')) el('dash-mar').textContent = parseFloat(data.mar).toFixed(2);
    
    // Update Events
    fetch('/api/events')
        .then(r => r.json())
        .then(events => {
            const list = el('dash-events');
            if (list) {
                list.innerHTML = '';
                events.slice(0, 10).forEach(ev => {
                    list.innerHTML += `
                        <div class="event-item">
                            <strong>${ev.event_type}</strong> - ${new Date(ev.timestamp).toLocaleTimeString()}
                            <div style="font-size: 12px; color: var(--text-secondary); margin-top: 4px;">Severity: ${ev.severity}</div>
                        </div>
                    `;
                });
            }
        });
}

function updateLiveMonitor(data) {
    const el = (id) => document.getElementById(id);
    
    if (el('live-fps')) el('live-fps').textContent = data.fps;
    if (el('live-camera-status')) el('live-camera-status').textContent = data.camera_status;
    if (el('live-attention')) {
        el('live-attention').textContent = data.attention_score;
        el('live-attention').style.color = data.attention_score > 60 ? 'var(--safe)' : 'var(--danger)';
    }
    
    if (el('live-eye-status')) {
        el('live-eye-status').textContent = data.eye_status;
        el('live-eye-status').style.color = data.eye_status === 'CLOSED' ? 'var(--danger)' : 'var(--text-primary)';
    }
    if (el('live-head-pose')) el('live-head-pose').textContent = data.head_pose;
    if (el('live-phone-status')) el('live-phone-status').textContent = data.phone_status;
    if (el('live-yawning')) el('live-yawning').textContent = data.yawning;

    const alertOverlay = el('live-alert-overlay');
    const alertText = el('live-alert-text');
    
    if (alertOverlay && data.active_alerts && data.active_alerts.length > 0) {
        alertText.textContent = data.active_alerts.join(' + ');
        alertOverlay.style.display = 'block';
    } else if (alertOverlay) {
        alertOverlay.style.display = 'none';
    }
}

// Start polling
setInterval(fetchLiveStatus, 1000);
fetchLiveStatus(); // Initial fetch
