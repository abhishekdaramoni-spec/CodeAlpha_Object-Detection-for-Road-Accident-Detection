import os
import sys
import time
import cv2
import sqlite3
from collections import deque
from flask import Flask, render_template, Response, request, redirect, url_for, jsonify, send_file
from werkzeug.utils import secure_filename

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import config
from database.db import (
    init_db, get_db_connection, insert_incident, get_recent_alerts, 
    acknowledge_alert, get_incidents, resolve_incident, get_dashboard_metrics, 
    get_analytics_data, get_incident_by_id
)
from detector.yolo_detector import YoloDetector
from detector.tracker import ObjectTracker
from detector.accident_logic import AccidentDetector
from reports.pdf_generator import generate_incident_pdf

app = Flask(__name__)

# System Configurations
app.config['UPLOAD_FOLDER'] = config.UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024 # 100 MB max video size

# Global App Settings (in-memory settings mapping, loaded from config)
app_settings = {
    'conf_threshold': config.CONFIDENCE_THRESHOLD,
    'max_cosine_distance': config.MAX_COSINE_DISTANCE,
    'sudden_stop_decel': config.SUDDEN_STOP_DECEL,
    'speed_change_threshold': config.SPEED_CHANGE_THRESHOLD,
    'proximity_threshold': config.PROXIMITY_THRESHOLD,
    'fall_aspect_ratio': config.FALL_ASPECT_RATIO,
    'motionless_duration': config.MOTIONLESS_DURATION,
    'audio_alerts': True,
    'auto_resolve_low': False,
    'yolo_imgsz': config.YOLO_IMGSZ,
    'inference_interval': config.INFERENCE_INTERVAL
}

# Global states to track stream source
current_source = None  # Active playing source (webcam index or file path)
target_source = None   # Target source requested by user
streaming_active = False
active_tracks_count = 0

# Session-specific metrics
session_vehicles = set()
session_people = set()
session_incidents = 0
session_alerts = 0

# Track active video writers for pre/post-incident recordings
# Format: { incident_id: { 'writer': cv2.VideoWriter, 'frames_remaining': int } }
active_recorders = {}

def get_current_source_name():
    global current_source
    if current_source == 0:
        return "Web Camera (Default)"
    elif isinstance(current_source, str):
        return os.path.basename(current_source)
    return "Disconnected"

def generate_frames():
    global current_source, target_source, streaming_active, active_tracks_count, active_recorders
    global session_vehicles, session_people, session_incidents, session_alerts
    
    # Reset session metrics for new streaming session
    session_vehicles = set()
    session_people = set()
    session_incidents = 0
    session_alerts = 0
    
    detector = YoloDetector(conf_threshold=app_settings['conf_threshold'])
    tracker = ObjectTracker(max_cosine_distance=app_settings['max_cosine_distance'])
    accident_detector = AccidentDetector()
    
    # Keep rolling buffer of raw frames (10 seconds)
    fps = config.FPS_DEFAULT
    buffer_len = int(config.BUFFER_BEFORE_SEC * fps)
    frame_buffer = deque(maxlen=buffer_len)
    
    # Initialize OpenCV capture
    cap = None
    current_source = target_source
    
    if current_source is not None:
        print(f"Streaming starting for source: {current_source}")
        cap = cv2.VideoCapture(current_source)
        
        # Try to read dimensions and FPS
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 640
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 360
        src_fps = cap.get(cv2.CAP_PROP_FPS)
        if src_fps and 5.0 <= src_fps <= 60.0:
            fps = src_fps
        else:
            fps = config.FPS_DEFAULT
            
        buffer_len = int(config.BUFFER_BEFORE_SEC * fps)
        frame_buffer = deque(maxlen=buffer_len)
            
        streaming_active = True
    else:
        streaming_active = False
        return

    frame_time = 1.0 / fps
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    
    stream_start_time = time.time()
    frame_idx = 0
    
    while streaming_active:
        # Check if source switch was requested
        if target_source != current_source:
            print("Source switch detected. Releasing camera...")
            break
            
        start_t = time.time()
        
        # Determine if the source is a live camera or a static video file
        is_live_camera = (current_source == 0)
        current_wall_time = time.time() - stream_start_time
        
        if is_live_camera:
            target_frame_idx = int(current_wall_time * fps)
            frames_to_skip = target_frame_idx - frame_idx
            
            if frames_to_skip > 0:
                for _ in range(frames_to_skip - 1):
                    cap.grab()
                    frame_idx += 1
                ret, frame = cap.read()
                frame_idx += 1
            else:
                sleep_time = (frame_idx * frame_time) - current_wall_time
                if sleep_time > 0.005:
                    time.sleep(sleep_time)
                ret, frame = cap.read()
                frame_idx += 1
        else:
            # Video file sequential playback - process every frame without skipping
            target_time = frame_idx * frame_time
            sleep_time = target_time - current_wall_time
            if sleep_time > 0.005:
                time.sleep(sleep_time)
            ret, frame = cap.read()
            frame_idx += 1
        
        if not ret:
            # If it's a video file, loop back to the beginning
            if isinstance(current_source, str) and current_source != '0':
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                stream_start_time = time.time()
                frame_idx = 0
                continue
            else:
                break
                
        # Resize frame to standard size to ensure fast inference on standard CPUs
        # Maintains 16:9 ratio, default 640x360
        frame_resized = cv2.resize(frame, (640, 360))
        h_res, w_res = 360, 640
        
        # Append RAW frame to rolling history buffer
        frame_buffer.append(frame_resized.copy())
        
        # Copy frame for drawing HUD annotations
        display_frame = frame_resized.copy()
        
        # 1. & 2. Run object detection & tracking (with interval optimizations)
        run_detection = (config.INFERENCE_INTERVAL <= 1) or (frame_idx % config.INFERENCE_INTERVAL == 0)
        
        if run_detection:
            # Run YOLO object detection with configured imgsz
            detections = detector.detect(frame_resized, imgsz=config.YOLO_IMGSZ)
            # Run Deep SORT tracker updates
            tracker.update(detections, frame_resized)
        else:
            # Detection-free tracking: predict positions for all tracks
            for track in tracker.tracks:
                track.predict()
                
            dt = 1.0 / fps
            for track in tracker.tracks:
                if track.is_confirmed:
                    # Get motion state for this track
                    obj_state = accident_detector.states.get(track.track_id)
                    if obj_state and len(obj_state['velocities']) > 0:
                        vx, vy = obj_state['velocities'][-1]
                        l, t, w, h = track.bbox
                        # Estimate new position using last known velocity
                        l += vx * dt
                        t += vy * dt
                        track.bbox = [l, t, w, h]
            
            # Clean up stale tracks (those exceeding max_age)
            tracker.tracks = [t for t in tracker.tracks if t.time_since_update <= tracker.max_age]
            
        # Format active tracks consistently for both detection and skipped frames
        active_tracks = []
        for track in tracker.tracks:
            # We display the track if it is confirmed AND it has been recently updated
            # (either in this frame, or within the current inference interval)
            if track.is_confirmed and track.time_since_update < config.INFERENCE_INTERVAL:
                l, t, w, h = track.bbox
                ltrb = [l, t, l + w, t + h]
                active_tracks.append({
                    'id': track.track_id,
                    'bbox': [float(ltrb[0]), float(ltrb[1]), float(ltrb[2]), float(ltrb[3])],
                    'class': track.class_name,
                    'confidence': float(track.confidence)
                })
                
        active_tracks_count = len(active_tracks)
        
        # 3. Process kinematics & posture states
        accident_detector.update_states(active_tracks, start_t)
        
        # 4. Draw tracking bounding boxes & kinetic HUD overlays
        for track in active_tracks:
            tid = track['id']
            class_name = track['class']
            bbox = track['bbox'] # [left, top, right, bottom]
            left, top, right, bottom = [int(coord) for coord in bbox]
            
            # Update session-specific track IDs
            if class_name in ['car', 'motorcycle', 'bus', 'truck', 'bicycle']:
                session_vehicles.add(tid)
            elif class_name == 'person':
                session_people.add(tid)
            
            # HUD Colors (BGR) representing Risk Severity
            # Green = Normal (129, 185, 16), Orange = Moderate Risk (11, 158, 245), Red = High Risk Accident (68, 68, 239)
            color = (129, 185, 16) # Default normal green
            
            obj_state = accident_detector.states.get(tid)
            if obj_state:
                risk_lvl = obj_state.get('risk_level', 'Normal')
                if risk_lvl == 'High':
                    color = (68, 68, 239) # Red
                elif risk_lvl == 'Moderate':
                    color = (11, 158, 245) # Orange
                    
            # Draw bounding box
            cv2.rectangle(display_frame, (left, top), (right, bottom), color, 2)
            
            # Draw Label badge
            label_txt = f"{class_name.capitalize()} #{tid}"
            cv2.putText(display_frame, label_txt, (left, max(15, top - 8)), 
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA)
                        
            # B. Draw velocity vector arrow to indicate movement trajectory
            if obj_state and len(obj_state['velocities']) > 0:
                cx = int((left + right) / 2.0)
                cy = int((top + bottom) / 2.0)
                vx, vy = obj_state['velocities'][-1]
                
                # Scale arrow based on speed vector (scaling factor 0.15)
                end_x = int(cx + vx * 0.15)
                end_y = int(cy + vy * 0.15)
                
                # Only draw arrow if speed is noticeable
                if obj_state['speeds'][-1] > 5.0:
                    cv2.arrowedLine(display_frame, (cx, cy), (end_x, end_y), color, 1, tipLength=0.25)
 
        # 5. Run Accident Analysis Engine
        new_incidents = accident_detector.analyze_incidents(start_t)
        
        # 6. Capture Evidence (screenshots & videos) for newly flagged incidents
        for inc in new_incidents:
            # Only process Moderate and High risk incidents with database IDs
            if inc.get('id') is not None:
                incident_id = inc['id']
                risk_lvl = inc['risk_level']
                
                # Update session metrics
                if risk_lvl == 'High':
                    session_incidents += 1
                    session_alerts += 1
                elif risk_lvl == 'Moderate':
                    session_alerts += 1
                
                # Create file paths
                screenshot_filename = f"incident_{incident_id}.jpg"
                video_filename = f"incident_{incident_id}.mp4"
                
                screenshot_path = os.path.join(config.INCIDENT_FOLDER, screenshot_filename)
                video_path = os.path.join(config.INCIDENT_FOLDER, video_filename)
                
                # Save screenshot of visual HUD representation
                cv2.imwrite(screenshot_path, display_frame)
                
                # Update incident records database with screenshot file path
                db_screenshot_rel = f"static/incidents/{screenshot_filename}"
                db_video_rel = f"static/incidents/{video_filename}"
                
                conn = get_db_connection()
                cursor = conn.cursor()
                
                # Initialize video writer for high and moderate risk incidents only
                if risk_lvl in ['High', 'Moderate']:
                    # Open video writer (640x360 size, matching resized frames)
                    writer = cv2.VideoWriter(video_path, fourcc, fps, (640, 360))
                    
                    # Write pre-incident frames from rolling buffer
                    for pre_frame in list(frame_buffer):
                        writer.write(pre_frame)
                        
                    # Queue post-incident recorder state
                    active_recorders[incident_id] = {
                        'writer': writer,
                        'frames_remaining': int(config.BUFFER_AFTER_SEC * fps)
                    }
                    
                    # Link screenshot and video path
                    cursor.execute('''
                        UPDATE incidents 
                        SET screenshot_path = ?, video_path = ? 
                        WHERE id = ?
                    ''', (db_screenshot_rel, db_video_rel, incident_id))
                else:
                    # Low risk logs only save screenshot (no video)
                    cursor.execute('''
                        UPDATE incidents 
                        SET screenshot_path = ? 
                        WHERE id = ?
                    ''', (db_screenshot_rel, incident_id))
                    
                conn.commit()
                conn.close()
                
        # 7. Update continuous active video writers
        for inc_id, recorder in list(active_recorders.items()):
            recorder['writer'].write(frame_resized)
            recorder['frames_remaining'] -= 1
            
            if recorder['frames_remaining'] <= 0:
                recorder['writer'].release()
                print(f"Evidence clip for Incident #{inc_id} saved successfully.")
                del active_recorders[inc_id]

        # Draw system overlay stats HUD onto visual display
        cv2.putText(display_frame, f"Active Tracks: {active_tracks_count}", (10, 25), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1, cv2.LINE_AA)
        cv2.putText(display_frame, f"FPS: {fps:.1f}", (10, 45), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1, cv2.LINE_AA)
        
        # Yield output frame byte stream
        ret_encoded, jpeg = cv2.imencode('.jpg', display_frame)
        if not ret_encoded:
            continue
            
        jpeg_bytes = jpeg.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + jpeg_bytes + b'\r\n')

    # Release resources when broken out
    if cap is not None:
        cap.release()
    streaming_active = False
    print("Video streaming stopped.")

# --- Flask Routes ---

@app.route('/')
def index():
    return redirect(url_for('dashboard'))

@app.route('/dashboard')
def dashboard():
    return render_template(
        'dashboard.html', 
        streaming_active=(target_source is not None), 
        current_source_name=get_current_source_name()
    )

@app.route('/incidents')
def incidents_page():
    return render_template('incidents.html')

@app.route('/analytics')
def analytics_page():
    return render_template('analytics.html')

@app.route('/settings')
def settings_page():
    return render_template('settings.html')

@app.route('/video_feed')
def video_feed():
    """Route serving multipart camera frame streams."""
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/set_source_webcam')
def set_source_webcam():
    """Switches input stream source to local webcam."""
    global target_source
    target_source = 0
    # Wait short delay for existing loop to cycle out
    time.sleep(0.5)
    return redirect(url_for('dashboard'))

@app.route('/upload_video', methods=['POST'])
def upload_video():
    """Saves uploaded video file and initiates stream thread."""
    global target_source
    if 'video_file' not in request.files:
        return redirect(url_for('dashboard'))
        
    file = request.files['video_file']
    if file.filename == '':
        return redirect(url_for('dashboard'))
        
    if file:
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        target_source = filepath
        # Delay to allow streaming generators to switch safely
        time.sleep(0.5)
        
    return redirect(url_for('dashboard'))

@app.route('/stop_feed')
def stop_feed():
    """Stops the active video capture."""
    global target_source, streaming_active
    target_source = None
    streaming_active = False
    return redirect(url_for('dashboard'))

# --- API Endpoints ---

@app.route('/api/stats')
def api_stats():
    global streaming_active, active_tracks_count, session_vehicles, session_people, session_incidents, session_alerts
    if not streaming_active:
        return jsonify({
            'total_vehicles': 0,
            'total_people': 0,
            'total_incidents': 0,
            'active_alerts': 0,
            'active_tracks': 0
        })
    
    return jsonify({
        'total_vehicles': len(session_vehicles),
        'total_people': len(session_people),
        'total_incidents': session_incidents,
        'active_alerts': session_alerts,
        'active_tracks': active_tracks_count
    })

@app.route('/api/alerts')
def api_alerts():
    global streaming_active
    if not streaming_active:
        return jsonify([])
    # Only pull unacknowledged alerts for live sidebar alerts logs
    alerts = get_recent_alerts(limit=8, unacknowledged_only=True)
    return jsonify(alerts)

@app.route('/api/alerts/acknowledge/<int:alert_id>', methods=['POST'])
def api_ack_alert(alert_id):
    acknowledge_alert(alert_id)
    return jsonify({'success': True})

@app.route('/api/incidents_history')
def api_incidents_history():
    history = get_incidents(resolved=None, limit=100)
    return jsonify(history)

@app.route('/api/incidents/resolve/<int:incident_id>', methods=['POST'])
def api_resolve_incident(incident_id):
    resolve_incident(incident_id)
    return jsonify({'success': True})

@app.route('/api/incidents/clear', methods=['POST'])
def api_clear_history():
    try:
        # Clear database tables
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM detections")
        cursor.execute("DELETE FROM incidents")
        cursor.execute("DELETE FROM alerts")
        conn.commit()
        conn.close()
        
        # Delete screenshot/video evidence files in static/incidents
        incident_folder = config.INCIDENT_FOLDER
        if os.path.exists(incident_folder):
            for filename in os.listdir(incident_folder):
                file_path = os.path.join(incident_folder, filename)
                try:
                    if os.path.isfile(file_path) or os.path.islink(file_path):
                        os.unlink(file_path)
                except Exception as e:
                    print(f"Failed to delete {file_path}. Reason: {e}")
                    
        # Reset the in-memory cache for detections
        from database.db import _detections_cache
        _detections_cache.clear()
        
        # Reset active session metrics
        session_vehicles.clear()
        session_people.clear()
        global session_incidents, session_alerts
        session_incidents = 0
        session_alerts = 0
        
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/analytics_stats')
def api_analytics_stats():
    stats = get_analytics_data()
    return jsonify(stats)

@app.route('/api/settings', methods=['GET', 'POST'])
def api_settings_endpoint():
    global app_settings
    if request.method == 'GET':
        return jsonify(app_settings)
    else:
        new_settings = request.json
        # Merge changes
        for k, v in new_settings.items():
            if k in app_settings:
                app_settings[k] = v
        
        # Apply configurations to dynamic thresholds
        config.CONFIDENCE_THRESHOLD = app_settings['conf_threshold']
        config.MAX_COSINE_DISTANCE = app_settings['max_cosine_distance']
        config.SUDDEN_STOP_DECEL = app_settings['sudden_stop_decel']
        config.SPEED_CHANGE_THRESHOLD = app_settings['speed_change_threshold']
        config.PROXIMITY_THRESHOLD = app_settings['proximity_threshold']
        config.FALL_ASPECT_RATIO = app_settings['fall_aspect_ratio']
        config.MOTIONLESS_DURATION = app_settings['motionless_duration']
        config.YOLO_IMGSZ = int(app_settings['yolo_imgsz'])
        config.INFERENCE_INTERVAL = int(app_settings['inference_interval'])
        
        return jsonify({'success': True})

@app.route('/api/report/<int:incident_id>')
def api_generate_report(incident_id):
    """Generates PDF report and starts attachment download."""
    filename = f"accident_report_{incident_id}.pdf"
    output_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    
    try:
        generate_incident_pdf(incident_id, output_path)
        return send_file(output_path, as_attachment=True, download_name=filename)
    except Exception as e:
        return jsonify({'error': str(e)}), 404

# Main runner
if __name__ == '__main__':
    # Force initialize database schema
    init_db()
    
    # Run server locally on port 5000
    app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)
