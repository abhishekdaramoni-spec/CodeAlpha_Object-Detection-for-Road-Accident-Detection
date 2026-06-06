# RADAR AI: Road Accident Detection and Emergency Alert System

RADAR AI is a complete, production-ready traffic monitoring, accident detection, and emergency alert system. It combines state-of-the-art computer vision models (Ultralytics YOLOv8 Nano) with advanced multi-object tracking (Deep SORT) and a custom physics-based kinematics analysis engine to identify road accidents (collisions, sudden stops, pedestrian falls, motionless victims) in real time. 

The system features a professional dark-themed responsive dashboard displaying a live annotated video stream (webcam or file uploads), emergency buzzer alarms, evidence capture (screenshots and 20-second video clips), analytics graphs, configuration settings sliders, and automated PDF report downloads.

---

## 🌟 Key Features

1. **Dual Video Source Stream**: Supports processing from a real-time web camera feed or uploaded traffic camera footage (.mp4, .avi).
2. **AI-Powered Object Tracking HUD**: Uses YOLOv8 Nano to detect vehicles (cars, buses, trucks, motorcycles, bicycles) and pedestrians, and tracks them using Deep SORT. The stream displays bounding boxes, track IDs, and overlays a real-time **Velocity Vector Arrow** for each active object.
3. **Kinematics & posturing Engine**:
   - **Vehicle Collisions**: Flags vehicle centroid overlays and bounding box intersections (IoU).
   - **Sudden Stops & Trajectory Swerves**: Calculates velocity changes and acceleration vectors to identify dangerous braking ($a < -150 \text{ px/s}^2$) or sharp trajectory shifts.
   - **Pedestrian Falls**: Monitors aspect ratio ($W/H \ge 1.2$) to identify collapsing/fallen pedestrians.
   - **Motionless Victims**: Tracks duration of post-fall immobility and escalates warning flags to **HIGH RISK** if stationary for over 3 seconds.
4. **Rolling Evidence Recording Buffer**: Keeps a rolling 10-second queue of video frames. Upon incident detection, it writes the 10 seconds of pre-incident footage and captures 10 seconds of post-incident frames to write a trimmed `mp4` file and a screenshot to disk.
5. **Interactive Dashboard**:
   - **Metrics Grid**: Real-time track counts, historical detection numbers, and active alarms.
   - **Buzzer Notification**: Audio warning siren triggered upon Moderate/High risk accidents.
   - **Live Logs Sidebar**: Clean logs panel to acknowledge active triggers.
6. **Analytics Trends**: Visualization of hourly traffic load, class distribution (pie chart), risk levels, and date ranges.
7. **Report Compilation**: Creates and downloads ReportLab PDF documents with metadata tables and embedded screenshot evidence.

---

## 📂 Project Structure

```text
road_accident_detection/
├── app.py                      # Flask Server (streaming & API endpoints)
├── config.py                   # System thresholds & folder paths configuration
├── requirements.txt            # Package dependencies list
├── verify_engine.py            # Unit & verification test suite
├── models/
│   └── yolov8n.pt              # YOLOv8 weights (auto-downloaded on first run)
├── database/
│   ├── db.py                   # SQLite tables creation & analytics queries
│   └── accidents.db            # SQLite database file
├── detector/
│   ├── yolo_detector.py        # YOLOv8 inference wrapper
│   ├── tracker.py              # Deep SORT tracker integration (CPU optimized)
│   └── accident_logic.py       # Accident kinematics analysis
├── reports/
│   └── pdf_generator.py        # ReportLab PDF design and compile helper
├── static/
│   ├── css/
│   │   └── style.css           # Premium Dark Mode stylesheet
│   ├── js/
│   │   ├── dashboard.js        # Websocket/AJAX live screen poller
│   │   ├── incidents.js        # Log search, resolution, and modal viewer
│   │   ├── analytics.js        # Chart.js graphing scripts
│   │   └── settings.js         # Settings synchronization
│   ├── uploads/                # Video uploads and reports storage
│   └── incidents/              # Screenshot and video clip evidence folder
└── templates/
    ├── dashboard.html          # Camera feed & live monitoring dashboard
    ├── incidents.html          # Incident search & investigation log
    ├── analytics.html          # Traffic volume analytics charts
    └── settings.html           # Sensor sensitivity slider adjustments
```

---

## 🛠️ Installation & Setup

### Prerequisites
- Python 3.10+ (tested on Windows 10/11)
- C++ build tools (required by some tracking dependencies like `lap` if not pre-built, although `deep-sort-realtime` handles this gracefully)

### Step 1: Clone and Navigate
```bash
cd road_accident_detection
```

### Step 2: Install Dependencies
Install packages listed in `requirements.txt`:
```bash
pip install -r requirements.txt
```

### Step 3: Run Engine Verifications (Recommended)
Before running the server, verify the core subsystems (SQLite transactions, kinematics simulator, fall posturing, motionless timer, and ReportLab PDF compilation):
```bash
python verify_engine.py
```
*(All tests should return `ALL ENGINE TESTS PASSED!`)*

### Step 4: Run Flask Server
Run the Flask server:
```bash
python app.py
```
Open a browser and navigate to: `http://localhost:5000`

---

## ⚙️ Physics and Threshold Explanations

1. **Velocity and Acceleration**:
   - Centroids are calculated as the geometric center of the tracking bounding box: $C = (x_{mid}, y_{mid})$.
   - Centroid coordinates are smoothed using a rolling exponential filter to eliminate pixel jitter.
   - Velocity is computed as: $\vec{V} = (\frac{\Delta x}{\Delta t}, \frac{\Delta y}{\Delta t})$ pixels per second.
   - Deceleration is computed as change in speed magnitude: $a = \frac{\Delta ||V||}{\Delta t}$. If $a < -\text{SUDDEN\_STOP\_DECEL}$, it triggers a **Sudden Stop** (Low Risk).
2. **Pedestrian Fall Check**:
   - Height ($H$) and Width ($W$) of the bounding box are extracted.
   - Aspect ratio is evaluated: $AR = \frac{W}{H}$.
   - If a pedestrian's aspect ratio rises above $1.2$ ($AR \ge 1.2$), they are flagged as having fallen (horizontal posture).
3. **Motionless Check**:
   - When a person falls, their speed is checked.
   - If speed remains below $4.0 \text{ px/s}$ for a continuous period of $\ge 3.0 \text{ seconds}$, a **Motionless Pedestrian** alert (High Risk) is dispatched.

---

## 🎓 Internship & Showcase Guide

- **GitHub/LinkedIn Placement**: Capture a short GIF or video demonstrating a file upload showing bounding boxes and tracking IDs. Highlight the velocity vectors and the glowing alert popup.
- **System Footprint**: The model weights (`yolov8n.pt`) are 6.2 MB. SQLite is a zero-configuration database. There are no heavy server components, making the total project deployment footprint under **25 MB**, easily fitting the 500 MB budget.
- **Real-Time Framerates**: To maintain 20-30 FPS on CPU laptops, the Flask app automatically resizes incoming frames to `640x360` before running YOLO, avoiding bottlenecks.

---

## 📝 License
This project is released under the MIT License.
