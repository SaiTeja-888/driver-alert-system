class AudioAlertService {
    constructor() {
        this.audioContext = null;
        this.enabled = true;
        this.lastPlayed = { warning: 0, critical: 0 };
        this.cooldowns = { warning: 4500, critical: 8000 };
    }

    async unlock() {
        try {
            const AudioContextClass = window.AudioContext || window.webkitAudioContext;
            if (!AudioContextClass) {
                return;
            }
            if (!this.audioContext) {
                this.audioContext = new AudioContextClass();
            }
            if (this.audioContext.state === 'suspended') {
                await this.audioContext.resume();
            }
        } catch (error) {
            console.warn('Audio unlock failed:', error);
        }
    }

    handle(metrics) {
        if (!this.enabled) {
            return;
        }

        const attention = Number(metrics.attention_score || 100);
        const critical = metrics.risk_level === 'CRITICAL' || attention < 40;
        const warning = Boolean(metrics.phone_detected) ||
            metrics.eye_status === 'CLOSED' ||
            Boolean(metrics.yawning) ||
            (Array.isArray(metrics.active_alerts) && metrics.active_alerts.length > 0);

        if (critical) {
            this.play('critical');
        } else if (warning) {
            this.play('warning');
        }
    }

    play(kind) {
        const now = Date.now();
        if (now - this.lastPlayed[kind] < this.cooldowns[kind]) {
            return;
        }
        this.lastPlayed[kind] = now;
        this.syntheticTone(kind);
    }

    syntheticTone(kind) {
        try {
            const AudioContextClass = window.AudioContext || window.webkitAudioContext;
            if (!AudioContextClass) {
                return;
            }

            const context = this.audioContext || new AudioContextClass();
            this.audioContext = context;

            if (context.state === 'suspended') {
                context.resume().catch(() => {});
            }

            const oscillator = context.createOscillator();
            const gain = context.createGain();
            oscillator.type = kind === 'critical' ? 'sawtooth' : 'sine';
            oscillator.frequency.value = kind === 'critical' ? 880 : 620;
            gain.gain.setValueAtTime(0.001, context.currentTime);
            gain.gain.exponentialRampToValueAtTime(kind === 'critical' ? 0.28 : 0.18, context.currentTime + 0.03);
            gain.gain.exponentialRampToValueAtTime(0.001, context.currentTime + 0.55);
            oscillator.connect(gain);
            gain.connect(context.destination);
            oscillator.start();
            oscillator.stop(context.currentTime + 0.6);
        } catch (error) {
            console.warn('Synthetic tone failed:', error);
        }
    }
}

class BrowserCameraService {
    constructor(video, canvas, options = {}) {
        this.video = video;
        this.canvas = canvas;
        this.context = canvas.getContext('2d', { alpha: false, willReadFrequently: false });
        this.stream = null;
        this.maxWidth = options.maxWidth || 640;
        this.quality = options.quality || 0.62;
        this.isMobile = /Android|iPhone|iPad|iPod|Mobile/i.test(navigator.userAgent);
    }

    async start() {
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            throw new Error('Camera API is not available in this browser.');
        }

        const constraints = {
            video: {
                facingMode: 'user',
                width: { ideal: this.isMobile ? 960 : 1280 },
                height: { ideal: this.isMobile ? 540 : 720 },
                frameRate: { ideal: this.isMobile ? 30 : 60, min: 15 },
            },
            audio: false,
        };

        this.stream = await navigator.mediaDevices.getUserMedia(constraints);
        this.video.srcObject = this.stream;
        this.video.setAttribute('playsinline', 'true');
        await this.video.play();

        if (this.isMobile) {
            this.maxWidth = Math.min(this.maxWidth, 480);
            this.quality = Math.min(this.quality, 0.55);
        }

        return this.stream;
    }

    stop() {
        if (!this.stream) {
            return;
        }
        this.stream.getTracks().forEach((track) => track.stop());
        this.stream = null;
    }

    async captureBase64() {
        if (!this.video.videoWidth || !this.video.videoHeight) {
            return null;
        }

        const scale = Math.min(1, this.maxWidth / this.video.videoWidth);
        const width = Math.max(320, Math.round(this.video.videoWidth * scale));
        const height = Math.round(this.video.videoHeight * scale);

        if (this.canvas.width !== width || this.canvas.height !== height) {
            this.canvas.width = width;
            this.canvas.height = height;
        }

        this.context.drawImage(this.video, 0, 0, width, height);

        const blob = await new Promise((resolve) => {
            this.canvas.toBlob(resolve, 'image/jpeg', this.quality);
        });

        if (!blob) {
            return null;
        }

        const dataUrl = await new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onloadend = () => resolve(reader.result);
            reader.onerror = reject;
            reader.readAsDataURL(blob);
        });

        return {
            frame: String(dataUrl).split(',')[1],
            width,
            height,
            bytes: blob.size,
        };
    }
}

class DriverMonitorDashboard {
    constructor() {
        this.root = document.querySelector('[data-monitor-root]');
        this.dashboardRoot = document.querySelector('[data-dashboard-root]');
        this.video = document.getElementById('camera-preview');
        this.canvas = document.getElementById('capture-canvas');
        this.startButton = document.getElementById('start-monitor');
        this.camera = this.video && this.canvas ? new BrowserCameraService(this.video, this.canvas) : null;
        this.audio = new AudioAlertService();
        this.ws = null;
        this.running = false;
        this.encoding = false;
        this.pendingFrames = 0;
        this.maxPendingFrames = 3;
        this.targetFps = this.camera?.isMobile ? 20 : 30;
        this.lastSentAt = 0;
        this.sentFrames = 0;
        this.sentFps = 0;
        this.sentFpsWindowStart = performance.now();
        this.reconnectTimer = null;
        this.pollTimer = null;
        this.paused = false;
        this.elements = this.mapElements();
    }

    init() {
        if (this.root && this.camera) {
            this.setConnectionStatus('DISCONNECTED');
            this.startButton.addEventListener('click', () => this.start());
            window.addEventListener('beforeunload', () => this.shutdown());
            document.addEventListener('visibilitychange', () => {
                if (document.hidden && this.running) {
                    this.pauseCapture();
                } else if (!document.hidden && this.running) {
                    this.resumeCapture();
                }
            });
            return;
        }

        if (this.dashboardRoot) {
            this.startDashboardPolling();
        }
    }

    mapElements() {
        const ids = [
            'connection-status',
            'metric-connection',
            'global-risk-level',
            'global-risk-badge',
            'system-dot',
            'system-text',
            'live-fps',
            'client-fps',
            'live-attention',
            'metric-attention',
            'metric-risk-score',
            'metric-risk-level',
            'live-risk-level',
            'live-phone-status',
            'live-eye-status',
            'live-head-pose',
            'live-yawning',
            'metric-phone-confidence',
            'metric-ear',
            'metric-mar',
            'metric-yaw',
            'metric-pitch',
            'metric-roll',
            'metric-processing',
            'metric-dropped',
            'live-alert-overlay',
            'live-alert-text',
            'risk-readout',
            'dash-attention',
            'dash-total-events',
            'dash-camera-status',
            'dash-fps',
            'dash-ear',
            'dash-mar',
        ];

        return ids.reduce((acc, id) => {
            acc[id] = document.getElementById(id);
            return acc;
        }, {});
    }

    async start() {
        try {
            this.startButton.disabled = true;
            this.startButton.querySelector('span').textContent = 'Starting';
            await this.audio.unlock();
            await this.camera.start();
            this.running = true;
            this.startButton.classList.add('hidden');
            this.connect();
            requestAnimationFrame((time) => this.captureLoop(time));
        } catch (error) {
            console.error(error);
            this.startButton.disabled = false;
            this.startButton.querySelector('span').textContent = 'Start Monitoring';
            const blocked = error.name === 'NotAllowedError' || error.name === 'PermissionDeniedError';
            this.setConnectionStatus(blocked ? 'CAMERA BLOCKED' : 'CAMERA ERROR');
            this.showAlert(['CAMERA_PERMISSION_REQUIRED'], 'HIGH');
        }
    }

    connect() {
        if (!this.running) {
            return;
        }

        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws`;

        this.setConnectionStatus('CONNECTING');
        this.ws = new WebSocket(wsUrl);

        this.ws.addEventListener('open', () => {
            this.pendingFrames = 0;
            this.setConnectionStatus('CONNECTED');
        });

        this.ws.addEventListener('message', (event) => {
            this.pendingFrames = Math.max(0, this.pendingFrames - 1);
            try {
                const metrics = JSON.parse(event.data);
                if (metrics.type !== 'error') {
                    this.update(metrics);
                    this.audio.handle(metrics);
                    this.adapt(metrics);
                } else {
                    console.warn(metrics.message);
                }
            } catch (error) {
                console.warn('Invalid metrics payload:', error);
            }
        });

        this.ws.addEventListener('close', () => this.scheduleReconnect());
        this.ws.addEventListener('error', () => this.scheduleReconnect());
    }

    scheduleReconnect() {
        if (!this.running || this.reconnectTimer) {
            return;
        }
        this.setConnectionStatus('RECONNECTING');
        this.reconnectTimer = window.setTimeout(() => {
            this.reconnectTimer = null;
            this.connect();
        }, 1200);
    }

    captureLoop(now) {
        if (!this.running || this.paused) {
            if (this.running) {
                requestAnimationFrame((time) => this.captureLoop(time));
            }
            return;
        }

        const minInterval = 1000 / this.targetFps;
        const socketReady = this.ws && this.ws.readyState === WebSocket.OPEN;
        const canSend = socketReady &&
            !this.encoding &&
            this.pendingFrames < this.maxPendingFrames &&
            this.ws.bufferedAmount < 1_000_000 &&
            now - this.lastSentAt >= minInterval;

        if (canSend) {
            this.sendFrame(now);
        }

        requestAnimationFrame((time) => this.captureLoop(time));
    }

    async sendFrame(now) {
        this.encoding = true;
        this.lastSentAt = now;

        try {
            const capture = await this.camera.captureBase64();
            if (!capture || !this.ws || this.ws.readyState !== WebSocket.OPEN) {
                return;
            }

            this.ws.send(JSON.stringify({
                frame: capture.frame,
                timestamp: Date.now(),
                width: capture.width,
                height: capture.height,
                bytes: capture.bytes,
                target_fps: this.targetFps,
            }));
            this.pendingFrames += 1;
            this.recordClientFps();
        } catch (error) {
            console.warn('Frame capture failed:', error);
        } finally {
            this.encoding = false;
        }
    }

    recordClientFps() {
        this.sentFrames += 1;
        const now = performance.now();
        const elapsed = now - this.sentFpsWindowStart;
        if (elapsed >= 1000) {
            this.sentFps = Math.round((this.sentFrames * 1000) / elapsed);
            this.sentFrames = 0;
            this.sentFpsWindowStart = now;
            this.setText('client-fps', this.sentFps);
        }
    }

    adapt(metrics) {
        const serverFps = Number(metrics.fps || 0);
        const latency = Number(metrics.latency_ms || 0);
        const dropped = Number(metrics.frames_dropped || 0);
        const minFps = this.camera?.isMobile ? 10 : 12;

        if ((serverFps > 0 && serverFps < 18) || latency > 450 || dropped > 20) {
            this.targetFps = Math.max(minFps, this.targetFps - 4);
            this.camera.quality = Math.max(0.48, this.camera.quality - 0.04);
        } else if (serverFps >= this.targetFps - 4 && latency < 220) {
            const maxFps = this.camera?.isMobile ? 24 : 60;
            this.targetFps = Math.min(maxFps, this.targetFps + 2);
            this.camera.quality = Math.min(0.72, this.camera.quality + 0.02);
        }
    }

    update(data) {
        this.setConnectionStatus(data.connection_status || 'CONNECTED');
        this.setText('live-fps', data.fps ?? 0);
        this.setText('live-attention', data.attention_score ?? 100);
        this.setText('metric-attention', data.attention_score ?? 100);
        this.setText('metric-risk-score', data.risk_score ?? 0);
        this.setText('metric-risk-level', data.risk_level || 'LOW');
        this.setText('live-risk-level', data.risk_level || 'LOW');
        this.setText('global-risk-level', data.risk_level || 'LOW');
        this.setText('live-phone-status', data.phone_status || 'NO');
        this.setText('live-eye-status', data.eye_status || 'OPEN');
        this.setText('live-head-pose', data.head_pose || 'CENTER');
        this.setText('live-yawning', data.yawning_status || (data.yawning ? 'YES' : 'NO'));
        this.setText('metric-phone-confidence', Number(data.phone_confidence || 0).toFixed(2));
        this.setText('metric-ear', Number(data.ear || 0).toFixed(2));
        this.setText('metric-mar', Number(data.mar || 0).toFixed(2));
        this.setText('metric-yaw', Number(data.head_yaw || 0).toFixed(1));
        this.setText('metric-pitch', Number(data.head_pitch || 0).toFixed(1));
        this.setText('metric-roll', Number(data.head_roll || 0).toFixed(1));
        this.setText('metric-processing', `${Number(data.processing_ms || 0).toFixed(0)} ms`);
        this.setText('metric-dropped', data.frames_dropped ?? 0);

        this.setText('dash-attention', data.attention_score ?? 100);
        this.setText('dash-camera-status', data.camera_status || 'WAITING');
        this.setText('dash-fps', data.fps ?? 0);
        this.setText('dash-ear', Number(data.ear || 0).toFixed(2));
        this.setText('dash-mar', Number(data.mar || 0).toFixed(2));

        this.applyRisk(data.risk_level || 'LOW');
        this.showAlert(data.active_alerts || [], data.risk_level || 'LOW');
    }

    setConnectionStatus(status) {
        this.setText('connection-status', status);
        this.setText('metric-connection', status);
        this.setText('system-text', status === 'CONNECTED' ? 'Browser Camera Live' : status);

        const dot = this.elements['system-dot'];
        if (dot) {
            const ok = status === 'CONNECTED';
            dot.style.backgroundColor = ok ? 'var(--safe)' : 'var(--warning)';
            dot.style.boxShadow = ok ? '0 0 16px var(--safe)' : '0 0 16px var(--warning)';
        }
    }

    applyRisk(level) {
        const normalized = String(level).toLowerCase();
        document.body.dataset.risk = normalized;

        ['global-risk-badge', 'risk-readout'].forEach((id) => {
            const el = this.elements[id];
            if (!el) {
                return;
            }
            el.classList.remove('low', 'medium', 'high', 'critical');
            el.classList.add(normalized);
        });
    }

    showAlert(alerts, level) {
        const overlay = this.elements['live-alert-overlay'];
        const text = this.elements['live-alert-text'];
        if (!overlay || !text) {
            return;
        }

        if (alerts.length > 0) {
            overlay.classList.add('active');
            overlay.classList.toggle('critical', level === 'CRITICAL');
            text.textContent = alerts.join(' + ');
        } else {
            overlay.classList.remove('active', 'critical');
            text.textContent = 'CLEAR';
        }
    }

    setText(id, value) {
        const element = this.elements[id];
        if (element) {
            element.textContent = value;
        }
    }

    startDashboardPolling() {
        const refresh = () => {
            Promise.all([
                fetch('/api/live').then((response) => response.json()),
                fetch('/api/stats').then((response) => response.json()),
                fetch('/api/events').then((response) => response.json()),
            ])
                .then(([live, stats, events]) => {
                    this.update(live);
                    const totalEvents = Object.values(stats || {}).reduce((sum, value) => sum + Number(value || 0), 0);
                    this.setText('dash-total-events', totalEvents);
                    this.renderEvents(events);
                })
                .catch((error) => console.warn('Dashboard refresh failed:', error));
        };

        refresh();
        this.pollTimer = window.setInterval(refresh, 2000);
    }

    renderEvents(events) {
        const eventsList = document.getElementById('dash-events');
        if (!eventsList || !Array.isArray(events)) {
            return;
        }

        eventsList.innerHTML = '';
        events.slice(0, 10).forEach((event) => {
            const row = document.createElement('div');
            row.className = 'event-item';
            row.innerHTML = `<strong>${event.event_type}</strong><span>${new Date(event.timestamp).toLocaleTimeString()}</span>`;
            eventsList.appendChild(row);
        });
    }

    pauseCapture() {
        this.paused = true;
    }

    resumeCapture() {
        this.paused = false;
    }

    shutdown() {
        this.running = false;
        this.paused = false;

        if (this.reconnectTimer) {
            window.clearTimeout(this.reconnectTimer);
            this.reconnectTimer = null;
        }

        if (this.pollTimer) {
            window.clearInterval(this.pollTimer);
            this.pollTimer = null;
        }

        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }

        if (this.camera) {
            this.camera.stop();
        }
    }
}

document.addEventListener('DOMContentLoaded', () => {
    const dashboard = new DriverMonitorDashboard();
    dashboard.init();
});
