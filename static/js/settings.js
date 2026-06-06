// Settings Configuration Manager

document.addEventListener('DOMContentLoaded', () => {
    fetchSettings();
});

// Update value labels next to range sliders dynamically
def = function updateValLabel(type, val) {
    document.getElementById(`${type}-val`).textContent = val;
};
window.updateValLabel = updateValLabel;

// Fetch current configurations from API
async function fetchSettings() {
    try {
        const response = await fetch('/api/settings');
        if (!response.ok) return;
        
        const config = await response.json();
        
        // Map data to forms
        document.getElementById('conf-threshold').value = config.conf_threshold;
        updateValLabel('conf', config.conf_threshold);
        
        document.getElementById('cosine-distance').value = config.max_cosine_distance;
        updateValLabel('cosine', config.max_cosine_distance);
        
        document.getElementById('decel-threshold').value = config.sudden_stop_decel;
        updateValLabel('decel', config.sudden_stop_decel + ' px/s²');
        
        document.getElementById('trajectory-threshold').value = config.speed_change_threshold;
        updateValLabel('traj', config.speed_change_threshold + '°');
        
        document.getElementById('proximity-threshold').value = config.proximity_threshold;
        updateValLabel('proximity', config.proximity_threshold + ' px');
        
        document.getElementById('posture-threshold').value = config.fall_aspect_ratio;
        updateValLabel('posture', config.fall_aspect_ratio);
        
        document.getElementById('motionless-threshold').value = config.motionless_duration;
        updateValLabel('motionless', config.motionless_duration + 's');
        
        document.getElementById('yolo-imgsz').value = config.yolo_imgsz;
        document.getElementById('inference-interval').value = config.inference_interval;
        updateValLabel('interval', config.inference_interval + ' frames');
        
        document.getElementById('audio-alerts').checked = config.audio_alerts !== false;
        document.getElementById('auto-reports').checked = config.auto_resolve_low !== false;
        
    } catch (err) {
        console.error('Error fetching settings:', err);
    }
}

// POST form data to API
async function saveSettings(event) {
    event.preventDefault();
    
    const settings = {
        conf_threshold: parseFloat(document.getElementById('conf-threshold').value),
        max_cosine_distance: parseFloat(document.getElementById('cosine-distance').value),
        sudden_stop_decel: parseFloat(document.getElementById('decel-threshold').value),
        speed_change_threshold: parseFloat(document.getElementById('trajectory-threshold').value),
        proximity_threshold: parseFloat(document.getElementById('proximity-threshold').value),
        fall_aspect_ratio: parseFloat(document.getElementById('posture-threshold').value),
        motionless_duration: parseFloat(document.getElementById('motionless-threshold').value),
        audio_alerts: document.getElementById('audio-alerts').checked,
        auto_resolve_low: document.getElementById('auto-reports').checked,
        yolo_imgsz: parseInt(document.getElementById('yolo-imgsz').value),
        inference_interval: parseInt(document.getElementById('inference-interval').value)
    };
    
    try {
        const response = await fetch('/api/settings', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(settings)
        });
        
        if (response.ok) {
            alert('Settings successfully updated and applied to the AI engine.');
            fetchSettings();
        } else {
            alert('Failed to save settings.');
        }
    } catch (err) {
        console.error('Error saving settings:', err);
        alert('Server connection error. Failed to update settings.');
    }
}
