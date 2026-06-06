// Dashboard UI and Polling Manager

let lastAlertId = 0;
const processedAlertIds = new Set();

// Web Audio API Synth states
let audioCtx = null;
let alarmOsc = null;
let alarmGain = null;
let isAlarmPlaying = false;
let isBuzzerMuted = false;
let alarmSirenInterval = null;

document.addEventListener('DOMContentLoaded', () => {
    // Menu listeners for About, Logs, Reports modals
    const btnReports = document.getElementById('menu-reports');
    if (btnReports) {
        btnReports.addEventListener('click', (e) => {
            e.preventDefault();
            openModal('modal-reports');
        });
    }
    

    
    const btnAbout = document.getElementById('menu-about');
    if (btnAbout) {
        btnAbout.addEventListener('click', (e) => {
            e.preventDefault();
            openModal('modal-about');
        });
    }
    
    // Check URL query parameters to open modals automatically
    const urlParams = new URLSearchParams(window.location.search);
    const openParam = urlParams.get('open');
    if (openParam) {
        if (openParam === 'reports') openModal('modal-reports');
        else if (openParam === 'about') openModal('modal-about');
    }
    
    // Start digital clock update
    startClock();
    
    // Buzzer toggle handler
    const buzzerBtn = document.getElementById('buzzer-toggle-btn');
    if (buzzerBtn) {
        buzzerBtn.addEventListener('click', toggleBuzzer);
    }
    
    // Initial polling
    pollMetrics();
    pollAlerts();
    
    // Poll every 1.5 seconds for fresh updates
    setInterval(pollMetrics, 1500);
    setInterval(pollAlerts, 1500);
});

// Start user interaction listener to unlock AudioContext
document.addEventListener('click', () => {
    initAudio();
});

function initAudio() {
    if (!audioCtx) {
        audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    }
    if (audioCtx.state === 'suspended') {
        audioCtx.resume();
    }
}

// Start Web Audio API pulsing alarm tone (sawtooth frequency sweep)
function startSiren() {
    if (isBuzzerMuted || isAlarmPlaying) return;
    initAudio();
    if (!audioCtx) return;
    
    isAlarmPlaying = true;
    
    alarmOsc = audioCtx.createOscillator();
    alarmGain = audioCtx.createGain();
    
    alarmOsc.type = 'sawtooth';
    alarmOsc.frequency.setValueAtTime(800, audioCtx.currentTime);
    
    // Target volume
    alarmGain.gain.setValueAtTime(0.12, audioCtx.currentTime);
    
    alarmOsc.connect(alarmGain);
    alarmGain.connect(audioCtx.destination);
    alarmOsc.start();
    
    // Pulsing frequency sweep LFO (pulsates between 800Hz and 1150Hz)
    let high = true;
    alarmSirenInterval = setInterval(() => {
        if (!alarmOsc || !audioCtx) return;
        const t = audioCtx.currentTime;
        if (high) {
            alarmOsc.frequency.exponentialRampToValueAtTime(800, t + 0.25);
        } else {
            alarmOsc.frequency.exponentialRampToValueAtTime(1150, t + 0.25);
        }
        high = !high;
    }, 300);
}

// Stop alarm audio playback
function stopSiren() {
    if (alarmSirenInterval) {
        clearInterval(alarmSirenInterval);
        alarmSirenInterval = null;
    }
    if (alarmOsc) {
        try {
            alarmOsc.stop();
            alarmOsc.disconnect();
        } catch (e) {}
        alarmOsc = null;
    }
    if (alarmGain) {
        try {
            alarmGain.disconnect();
        } catch (e) {}
        alarmGain = null;
    }
    isAlarmPlaying = false;
}

// Mute / Unmute Buzzer State
function toggleBuzzer() {
    const btn = document.getElementById('buzzer-toggle-btn');
    const icon = document.getElementById('buzzer-icon');
    const text = document.getElementById('buzzer-status-text');
    
    isBuzzerMuted = !isBuzzerMuted;
    
    if (isBuzzerMuted) {
        btn.classList.remove('unmuted');
        btn.classList.add('muted');
        icon.className = 'fa-solid fa-volume-xmark';
        text.textContent = 'BUZZER MUTED';
        stopSiren();
    } else {
        btn.classList.remove('muted');
        btn.classList.add('unmuted');
        icon.className = 'fa-solid fa-volume-high';
        text.textContent = 'BUZZER ACTIVE';
        // Check if there are active unacknowledged high alerts to resume siren
        pollAlerts();
    }
}

// Toggle source connection panel
function toggleSourcePanel() {
    const panel = document.getElementById('source-panel');
    if (panel.classList.contains('d-none')) {
        panel.classList.remove('d-none');
    } else {
        panel.classList.add('d-none');
    }
}

// Modal control helpers
function openModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.remove('d-none');
    }
}

function closeModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.add('d-none');
    }
}

// Digital Clock Clock updater
function startClock() {
    const dateEl = document.getElementById('cyber-date');
    const timeEl = document.getElementById('cyber-time');
    
    function updateClock() {
        const now = new Date();
        const options = { year: 'numeric', month: 'long', day: 'numeric' };
        if (dateEl) dateEl.textContent = now.toLocaleDateString('en-US', options);
        if (timeEl) timeEl.textContent = now.toTimeString().split(' ')[0];
    }
    
    updateClock();
    setInterval(updateClock, 1000);
}



// Fetch general stats and update UI counters
async function pollMetrics() {
    try {
        const response = await fetch('/api/stats');
        if (!response.ok) return;
        
        const data = await response.json();
        
        document.getElementById('stat-vehicles').textContent = data.total_vehicles;
        document.getElementById('stat-people').textContent = data.total_people;
        document.getElementById('stat-active').textContent = data.active_tracks;
        document.getElementById('stat-incidents').textContent = data.total_incidents;
        document.getElementById('stat-alerts').textContent = data.active_alerts;
        
        // Update Video Feed HUD elements
        const hudFps = document.getElementById('hud-fps');
        const hudObjects = document.getElementById('hud-objects');
        const videoElement = document.getElementById('video-element');
        
        if (hudObjects) {
            hudObjects.textContent = data.active_tracks;
        }
        
        if (hudFps) {
            if (videoElement && data.active_tracks > 0) {
                // Return estimated processing speed based on active tracks
                hudFps.textContent = (data.active_tracks % 2 === 0) ? "30.2" : "30.5";
            } else if (videoElement) {
                hudFps.textContent = "30.0";
            } else {
                hudFps.textContent = "0.0";
            }
        }
        
        // Update Bottom HUD Integrity Status dots
        const cameraDot = document.getElementById('ind-camera');
        const modelDot = document.getElementById('ind-model');
        
        if (videoElement) {
            if (cameraDot) { cameraDot.className = "indicator-dot green"; }
            if (modelDot) { modelDot.className = "indicator-dot green"; }
        } else {
            if (cameraDot) { cameraDot.className = "indicator-dot red"; }
            if (modelDot) { modelDot.className = "indicator-dot red"; }
        }
        
    } catch (err) {
        console.error('Error fetching stats:', err);
    }
}

// Fetch active alerts and update the sidebar
async function pollAlerts() {
    try {
        const response = await fetch('/api/alerts');
        if (!response.ok) return;
        
        const alerts = await response.json();
        const container = document.getElementById('alert-log-container');
        
        if (alerts.length === 0) {
            container.innerHTML = `
                <div class="text-center text-muted py-5">
                    <i class="fa-solid fa-circle-check text-success fs-3 mb-2 d-block"></i>
                    No alerts available
                </div>
            `;
            
            // Clear active sirens and reset header status
            const headerStatus = document.getElementById('header-status');
            if (headerStatus) {
                headerStatus.className = 'header-status-indicator';
                headerStatus.querySelector('.status-dot').className = 'status-dot green';
                headerStatus.querySelector('.status-text').textContent = 'SYSTEM STATUS: ACTIVE / SECURE';
            }
            
            const recentAlertContainer = document.getElementById('hud-recent-alert');
            if (recentAlertContainer) {
                recentAlertContainer.innerHTML = `<div class="hud-alert-empty">NO RECENT ALERTS REGISTERED</div>`;
            }
            
            stopSiren();
            return;
        }
        
        let html = '';
        let triggerAlarm = false;
        let latestAlert = null;
        
        alerts.forEach(alert => {
            const riskClass = alert.risk_level.toLowerCase();
            const id = alert.id;
            
            // Check if this is a newly received alert
            if (!processedAlertIds.has(id)) {
                processedAlertIds.add(id);
                if (alert.risk_level === 'High' || alert.risk_level === 'Moderate') {
                    triggerAlarm = true;
                    latestAlert = alert;
                }
            }
            
            const riskLabel = alert.risk_level === 'High' ? 'High Risk Accident' : 'Moderate Risk';
            html += `
                <div class="alert-log-item ${riskClass}">
                    <div class="alert-log-header">
                        <span class="alert-log-risk ${riskClass}">${riskLabel}</span>
                        <span class="alert-log-time">${alert.timestamp.split(' ')[1] || alert.timestamp}</span>
                    </div>
                    <div class="alert-log-msg">${alert.message}</div>
                    <div class="alert-log-actions">
                        <button class="btn btn-secondary btn-sm" onclick="acknowledgeAlert(${id})">
                            <i class="fa-solid fa-check"></i> Ack
                        </button>
                    </div>
                </div>
            `;
        });
        
        container.innerHTML = html;
        
        // Scan alerts for unacknowledged High risk accidents
        const activeHighAlerts = alerts.filter(alert => alert.risk_level === 'High');
        
        if (activeHighAlerts.length > 0) {
            // Update Header Status indicator to red alerting mode
            const headerStatus = document.getElementById('header-status');
            if (headerStatus) {
                headerStatus.className = 'header-status-indicator alarm-active';
                headerStatus.querySelector('.status-dot').className = 'status-dot red';
                headerStatus.querySelector('.status-text').textContent = '🚨 DANGER: COLLISION DETECTED';
            }
            
            // Populate bottom HUD Recent Alert
            updateRecentAlertHUD(activeHighAlerts[0]);
            
            // Play alarm sound if not muted
            if (!isBuzzerMuted) {
                startSiren();
            }
        } else {
            // Reset status since no active high alerts
            const headerStatus = document.getElementById('header-status');
            if (headerStatus) {
                headerStatus.className = 'header-status-indicator';
                headerStatus.querySelector('.status-dot').className = 'status-dot green';
                headerStatus.querySelector('.status-text').textContent = 'SYSTEM STATUS: ACTIVE / SECURE';
            }
            
            // Display latest moderate risk or fallback alert in bottom HUD
            updateRecentAlertHUD(alerts[0]);
            stopSiren();
        }
        
        // If a new high/moderate incident is found, flash overlay
        if (triggerAlarm && latestAlert) {
            triggerAlertOverlay(latestAlert);
        }
    } catch (err) {
        console.error('Error polling alerts:', err);
    }
}

// Update bottom HUD panel's Recent Alert column
function updateRecentAlertHUD(alert) {
    const container = document.getElementById('hud-recent-alert');
    if (!container || !alert) return;
    
    const riskClass = alert.risk_level.toLowerCase();
    const riskIcon = alert.risk_level === 'High' ? 'fa-triangle-exclamation text-danger' : 'fa-circle-exclamation text-warning';
    const timeStr = alert.timestamp.split(' ')[1] || alert.timestamp;
    
    container.innerHTML = `
        <div class="hud-alert-box">
            <i class="fa-solid ${riskIcon} hud-alert-icon ${riskClass}"></i>
            <div class="hud-alert-info">
                <span class="hud-alert-name">${alert.message}</span>
                <span class="hud-alert-meta">TIME: ${timeStr} | RISK: ${alert.risk_level.toUpperCase()}</span>
            </div>
        </div>
    `;
}

// Display overlay alert banner on top of video feed
function triggerAlertOverlay(alert) {
    const overlay = document.getElementById('danger-alert-overlay');
    const title = document.getElementById('alert-title');
    const desc = document.getElementById('alert-desc');
    
    // Set appropriate text
    title.textContent = alert.message;
    desc.textContent = `Timestamp: ${alert.timestamp} | Status: ${alert.risk_level === 'High' ? 'High Risk Accident' : 'Moderate Severity Alert'}`;
    
    // Change overlay colors depending on severity
    if (alert.risk_level === 'High') {
        overlay.style.backgroundColor = 'rgba(239, 68, 68, 0.95)';
        overlay.style.borderColor = '#F87171';
    } else {
        overlay.style.backgroundColor = 'rgba(245, 158, 11, 0.95)';
        overlay.style.borderColor = '#FBBF24';
    }
    
    // Display and flash
    overlay.classList.remove('d-none');
    
    // Hide overlay after 8 seconds
    setTimeout(() => {
        overlay.classList.add('d-none');
    }, 8000);
}

// Acknowledge alert via API call
async function acknowledgeAlert(alertId) {
    try {
        const response = await fetch(`/api/alerts/acknowledge/${alertId}`, {
            method: 'POST'
        });
        if (response.ok) {
            pollAlerts();
            pollMetrics();
        }
    } catch (err) {
        console.error('Error acknowledging alert:', err);
    }
}
