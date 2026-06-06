import sys
import os
import cv2
from ultralytics import YOLO

# Add parent directory to path to allow config import
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

class YoloDetector:
    def __init__(self, model_path=config.MODEL_PATH, conf_threshold=config.CONFIDENCE_THRESHOLD):
        """Initializes the YOLOv8 model."""
        self.model_path = model_path
        self.conf_threshold = conf_threshold
        
        # Load the model
        print(f"Loading YOLOv8 model from {self.model_path}...")
        self.model = YOLO(self.model_path)
        print("YOLOv8 model loaded successfully.")

    def _calculate_iou(self, box1, box2):
        """Calculates Intersection over Union (IoU) of two bounding boxes in [left, top, width, height] format."""
        xA = max(box1[0], box2[0])
        yA = max(box1[1], box2[1])
        xB = min(box1[0] + box1[2], box2[0] + box2[2])
        yB = min(box1[1] + box1[3], box2[1] + box2[3])

        interArea = max(0.0, xB - xA) * max(0.0, yB - yA)
        if interArea == 0.0:
            return 0.0

        boxAArea = box1[2] * box1[3]
        boxBArea = box2[2] * box2[3]

        iou = interArea / float(boxAArea + boxBArea - interArea)
        return iou

    def detect(self, frame, imgsz=None):
        """
        Runs object detection on a single frame.
        Returns a list of detections in the format:
        [ ([left, top, width, height], confidence, class_name), ... ]
        """
        if imgsz is None:
            imgsz = config.YOLO_IMGSZ
        results = self.model(frame, verbose=False, imgsz=imgsz)[0]
        detections = []
        
        for box in results.boxes:
            conf = float(box.conf[0])
            if conf < self.conf_threshold:
                continue
                
            class_id = int(box.cls[0])
            if class_id not in config.YOLO_CLASSES:
                continue
                
            class_name = config.YOLO_CLASS_NAMES[class_id]
            
            # Get xyxy coordinates (floats)
            xyxy = box.xyxy[0].tolist()
            x1, y1, x2, y2 = xyxy
            
            # Convert to [left, top, width, height] for Deep SORT
            left = float(x1)
            top = float(y1)
            width = float(x2 - x1)
            height = float(y2 - y1)
            
            detections.append(([left, top, width, height], conf, class_name))
            
        # Class-agnostic / conflicting class NMS filtering to eliminate duplicate overlapping boxes
        VEHICLE_CLASSES = {'car', 'truck', 'bus', 'motorcycle', 'bicycle'}
        detections = sorted(detections, key=lambda x: x[1], reverse=True)
        filtered_detections = []
        
        for det in detections:
            keep = True
            box, conf, class_name = det
            for f_det in filtered_detections:
                f_box, f_conf, f_class_name = f_det
                iou = self._calculate_iou(box, f_box)
                if iou > 0.40:
                    # Suppress if same class
                    if class_name == f_class_name:
                        keep = False
                        break
                    # Suppress if both are vehicle classes (conflicting vehicle detection)
                    if class_name in VEHICLE_CLASSES and f_class_name in VEHICLE_CLASSES:
                        keep = False
                        break
            if keep:
                filtered_detections.append(det)
                
        return filtered_detections

