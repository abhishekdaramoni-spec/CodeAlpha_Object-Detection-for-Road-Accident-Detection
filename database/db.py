import sqlite3
import os
from datetime import datetime
import sys

# Add parent directory to sys.path to allow imports from config
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

def get_db_connection():
    """Establishes a connection to the SQLite database."""
    conn = sqlite3.connect(config.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initializes the database by creating tables if they do not exist."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Create Incidents Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS incidents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            risk_level TEXT NOT NULL,
            incident_type TEXT NOT NULL,
            vehicle_id INTEGER,
            person_id INTEGER,
            screenshot_path TEXT,
            video_path TEXT,
            resolved INTEGER DEFAULT 0
        )
    ''')
    
    # 2. Create Detections Table (captures count and classes detected in incidents or general traffic logging)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS detections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            class_label TEXT NOT NULL,
            track_id INTEGER NOT NULL,
            confidence REAL NOT NULL
        )
    ''')
    
    # 3. Create Alerts Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            incident_id INTEGER,
            message TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            acknowledged INTEGER DEFAULT 0,
            FOREIGN KEY (incident_id) REFERENCES incidents (id)
        )
    ''')
    
    conn.commit()
    conn.close()

def insert_incident(risk_level, incident_type, vehicle_id=None, person_id=None, screenshot_path=None, video_path=None):
    """Inserts a new accident/incident record, preventing duplicates in short windows."""
    conn = get_db_connection()
    cursor = conn.cursor()
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    # 1. Prevent duplicate alerts for similar tracks in a 12-second window
    cursor.execute('''
        SELECT timestamp, vehicle_id, person_id FROM incidents 
        WHERE incident_type = ? 
        ORDER BY id DESC LIMIT 1
    ''', (incident_type,))
    row = cursor.fetchone()
    
    if row:
        try:
            last_time = datetime.strptime(row['timestamp'], '%Y-%m-%d %H:%M:%S')
            if (datetime.now() - last_time).total_seconds() < 12.0:
                # If they involve the same IDs or both are None
                same_vehicle = (vehicle_id is not None and row['vehicle_id'] == vehicle_id)
                same_person = (person_id is not None and row['person_id'] == person_id)
                both_null = (vehicle_id is None and person_id is None and row['vehicle_id'] is None and row['person_id'] is None)
                if same_vehicle or same_person or both_null:
                    conn.close()
                    return None
        except Exception:
            pass

    # 2. Insert if not a duplicate
    cursor.execute('''
        INSERT INTO incidents (timestamp, risk_level, incident_type, vehicle_id, person_id, screenshot_path, video_path, resolved)
        VALUES (?, ?, ?, ?, ?, ?, ?, 0)
    ''', (timestamp, risk_level, incident_type, vehicle_id, person_id, screenshot_path, video_path))
    
    incident_id = cursor.lastrowid
    
    # If it is high-risk or moderate, also automatically create an alert
    if risk_level in ['High', 'Moderate']:
        if risk_level == 'High':
            msg = f"🚨 High Risk Accident: {incident_type} detected."
        else:
            msg = f"⚠️ Moderate Risk: {incident_type} detected."
            
        if vehicle_id:
            msg += f" Vehicle ID: #{vehicle_id}."
        if person_id:
            msg += f" Person ID: #{person_id}."
        
        cursor.execute('''
            INSERT INTO alerts (incident_id, message, timestamp, acknowledged)
            VALUES (?, ?, ?, 0)
        ''', (incident_id, msg, timestamp))
        
    conn.commit()
    conn.close()
    return incident_id

# In-memory cache to avoid querying the DB for detections on every frame
_detections_cache = {}

def insert_detection(class_label, track_id, confidence):
    """Logs an object detection, limiting updates to once per 15 seconds per track."""
    global _detections_cache
    now = datetime.now()
    cache_key = (class_label, track_id)
    
    # 1. Check in-memory cache first to avoid any DB connection or query overhead
    if cache_key in _detections_cache:
        last_time = _detections_cache[cache_key]
        if (now - last_time).total_seconds() < 15.0:
            return
            
    conn = get_db_connection()
    cursor = conn.cursor()
    timestamp = now.strftime('%Y-%m-%d %H:%M:%S')
    
    # 2. Query DB if cache is cold
    cursor.execute('''
        SELECT timestamp FROM detections 
        WHERE class_label = ? AND track_id = ? 
        ORDER BY id DESC LIMIT 1
    ''', (class_label, track_id))
    row = cursor.fetchone()
    
    should_insert = True
    if row:
        try:
            last_time_db = datetime.strptime(row['timestamp'], '%Y-%m-%d %H:%M:%S')
            if (now - last_time_db).total_seconds() < 15.0:
                should_insert = False
                _detections_cache[cache_key] = last_time_db
        except Exception:
            pass
            
    if should_insert:
        cursor.execute('''
            INSERT INTO detections (timestamp, class_label, track_id, confidence)
            VALUES (?, ?, ?, ?)
        ''', (timestamp, class_label, track_id, confidence))
        conn.commit()
        _detections_cache[cache_key] = now
        
    conn.close()

def get_recent_alerts(limit=5, unacknowledged_only=False):
    """Retrieves list of latest emergency alerts."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    query = '''
        SELECT a.id, a.message, a.timestamp, a.acknowledged, a.incident_id, i.risk_level, i.screenshot_path
        FROM alerts a
        LEFT JOIN incidents i ON a.incident_id = i.id
    '''
    
    if unacknowledged_only:
        query += ' WHERE a.acknowledged = 0'
        
    query += ' ORDER BY a.timestamp DESC LIMIT ?'
    
    cursor.execute(query, (limit,))
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows

def acknowledge_alert(alert_id):
    """Marks an alert as acknowledged."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE alerts SET acknowledged = 1 WHERE id = ?', (alert_id,))
    conn.commit()
    conn.close()

def resolve_incident(incident_id):
    """Marks an incident as resolved."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE incidents SET resolved = 1 WHERE id = ?', (incident_id,))
    # Also acknowledge linked alerts
    cursor.execute('UPDATE alerts SET acknowledged = 1 WHERE incident_id = ?', (incident_id,))
    conn.commit()
    conn.close()

def get_incidents(resolved=None, limit=50):
    """Retrieves list of incidents, optionally filtered by resolution status."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    query = 'SELECT * FROM incidents'
    params = []
    
    if resolved is not None:
        query += ' WHERE resolved = ?'
        params.append(1 if resolved else 0)
        
    query += ' ORDER BY timestamp DESC LIMIT ?'
    params.append(limit)
    
    cursor.execute(query, params)
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows

def get_incident_by_id(incident_id):
    """Retrieves a single incident by ID."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM incidents WHERE id = ?', (incident_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def get_dashboard_metrics():
    """Calculates metrics for dashboard display."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Total vehicles detected (unique track_ids for vehicle classes)
    cursor.execute('''
        SELECT COUNT(DISTINCT track_id) FROM detections 
        WHERE class_label IN ('car', 'motorcycle', 'bus', 'truck', 'bicycle')
    ''')
    total_vehicles = cursor.fetchone()[0] or 0
    
    # 2. Total people detected (unique track_ids for 'person' class)
    cursor.execute("SELECT COUNT(DISTINCT track_id) FROM detections WHERE class_label = 'person'")
    total_people = cursor.fetchone()[0] or 0
    
    # 3. Suspected accidents (only HIGH risk incidents in DB)
    cursor.execute("SELECT COUNT(id) FROM incidents WHERE risk_level = 'High'")
    total_incidents = cursor.fetchone()[0] or 0
    
    # 4. Emergency Alerts (unacknowledged alerts)
    cursor.execute("SELECT COUNT(id) FROM alerts WHERE acknowledged = 0")
    active_alerts = cursor.fetchone()[0] or 0
    
    conn.close()
    return {
        'total_vehicles': total_vehicles,
        'total_people': total_people,
        'total_incidents': total_incidents,
        'active_alerts': active_alerts
    }

def get_analytics_data():
    """Generates counts grouped by category for Chart.js rendering."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Traffic hourly distribution (past 24 hrs)
    cursor.execute('''
        SELECT strftime('%H', timestamp) as hour, COUNT(id) as count 
        FROM detections 
        WHERE timestamp >= datetime('now', '-24 hours')
        GROUP BY hour
        ORDER BY hour ASC
    ''')
    hourly_traffic = {row['hour']: row['count'] for row in cursor.fetchall()}
    
    # Fill in empty hours if missing
    hourly_data = []
    for h in range(24):
        hour_str = f"{h:02d}"
        hourly_data.append({
            'label': f"{hour_str}:00",
            'count': hourly_traffic.get(hour_str, 0)
        })
        
    # 2. Vehicle distribution (by class)
    cursor.execute('''
        SELECT class_label, COUNT(DISTINCT track_id) as count 
        FROM detections 
        WHERE class_label IN ('car', 'motorcycle', 'bus', 'truck', 'bicycle')
        GROUP BY class_label
    ''')
    vehicle_distribution = {row['class_label']: row['count'] for row in cursor.fetchall()}
    
    # 3. Incident frequency by risk level
    cursor.execute('''
        SELECT risk_level, COUNT(id) as count 
        FROM incidents 
        GROUP BY risk_level
    ''')
    risk_distribution = {row['risk_level']: row['count'] for row in cursor.fetchall()}
    
    # 4. Incident details list for analytics charts
    cursor.execute('''
        SELECT strftime('%m-%d', timestamp) as date, COUNT(id) as count
        FROM incidents
        GROUP BY date
        ORDER BY date ASC
        LIMIT 10
    ''')
    incident_dates = [row['date'] for row in cursor.fetchall()]
    cursor.execute('''
        SELECT strftime('%m-%d', timestamp) as date, COUNT(id) as count
        FROM incidents
        GROUP BY date
        ORDER BY date ASC
        LIMIT 10
    ''')
    incident_counts = [row['count'] for row in cursor.fetchall()]
    
    conn.close()
    
    return {
        'hourly_traffic': hourly_data,
        'vehicle_distribution': vehicle_distribution,
        'risk_distribution': risk_distribution,
        'incidents_by_date': {
            'labels': incident_dates,
            'counts': incident_counts
        }
    }

# Run database setup if script is run directly
if __name__ == '__main__':
    init_db()
    print("Database initialized successfully at:", config.DATABASE_PATH)
