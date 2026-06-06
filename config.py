import os

# Base directory of the project
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Database Settings
DATABASE_PATH = os.path.join(BASE_DIR, 'database', 'accidents.db')

# Model Settings
MODEL_DIR = os.path.join(BASE_DIR, 'models')
MODEL_PATH = os.path.join(MODEL_DIR, 'yolov8n.pt')

# Directory Paths for Static Assets and Detections
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
INCIDENT_FOLDER = os.path.join(BASE_DIR, 'static', 'incidents')

# Ensure folders exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(INCIDENT_FOLDER, exist_ok=True)
os.makedirs(MODEL_DIR, exist_ok=True)
os.makedirs(os.path.join(BASE_DIR, 'database'), exist_ok=True)

# YOLO Classes of Interest (COCO class indices mapping to interest list)
# 0: person, 1: bicycle, 2: car, 3: motorcycle, 5: bus, 7: truck
YOLO_CLASSES = [0, 1, 2, 3, 5, 7]
YOLO_CLASS_NAMES = {
    0: 'person',
    1: 'bicycle',
    2: 'car',
    3: 'motorcycle',
    5: 'bus',
    7: 'truck'
}

# Detection and Tracking Settings
CONFIDENCE_THRESHOLD = 0.25
IOU_THRESHOLD = 0.45
MAX_COSINE_DISTANCE = 0.3
MAX_AGE = 30
N_INIT = 3

# Accident Detection Parameters
FPS_DEFAULT = 20.0             # Default FPS used if video capture source doesn't provide it
PROXIMITY_THRESHOLD = 45.0    # Distance in pixels below which two bounding boxes are considered 'close'
COLLISION_IOU_THRESHOLD = 0.1  # Bounding box IoU overlap threshold for a collision flag
SUDDEN_STOP_DECEL = 150.0      # Acceleration threshold (pixels/sec^2) for sudden stop
SPEED_CHANGE_THRESHOLD = 40.0 # Velocity magnitude change defining sudden change in trajectory
FALL_ASPECT_RATIO = 1.2        # Bounding box aspect ratio (width/height) to consider a person as fallen
MOTIONLESS_DURATION = 3.0      # Duration in seconds a fallen person must remain motionless to trigger High Risk

# Video Evidence Recording
BUFFER_BEFORE_SEC = 10         # Seconds of video to capture before incident
BUFFER_AFTER_SEC = 10          # Seconds of video to capture after incident

# Performance Settings
YOLO_IMGSZ = 320               # Default input resolution for YOLOv8 model inference
INFERENCE_INTERVAL = 2         # Run YOLO detection every N frames (1 = every frame)

