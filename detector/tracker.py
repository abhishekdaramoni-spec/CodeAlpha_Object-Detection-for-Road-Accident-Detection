import sys
import os
import numpy as np

# Add parent directory to path to allow config import
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

class Track:
    def __init__(self, track_id, bbox, class_name, confidence, n_init=3):
        self.track_id = track_id
        self.bbox = bbox # [left, top, width, height]
        self.class_name = class_name
        self.confidence = confidence
        self.hits = 1
        self.age = 1
        self.time_since_update = 0
        self.n_init = n_init
        self.is_confirmed = False
        if self.hits >= self.n_init:
            self.is_confirmed = True

    def predict(self):
        self.age += 1
        self.time_since_update += 1

    def update(self, bbox, confidence):
        self.bbox = bbox
        self.confidence = confidence
        self.hits += 1
        self.time_since_update = 0
        if self.hits >= self.n_init:
            self.is_confirmed = True

class ObjectTracker:
    def __init__(self, 
                 max_age=config.MAX_AGE, 
                 n_init=config.N_INIT, 
                 max_cosine_distance=config.MAX_COSINE_DISTANCE):
        """Initializes the tracker using high-performance IoU matching."""
        self.max_age = max_age
        self.n_init = n_init
        self.min_iou = 0.3
        self.next_id = 1
        self.tracks = []

    def _calculate_iou(self, boxA, boxB):
        # box format: [left, top, width, height]
        xA = max(boxA[0], boxB[0])
        yA = max(boxA[1], boxB[1])
        xB = min(boxA[0] + boxA[2], boxB[0] + boxB[2])
        yB = min(boxA[1] + boxA[3], boxB[1] + boxB[3])

        interArea = max(0, xB - xA) * max(0, yB - yA)
        if interArea == 0:
            return 0.0

        boxAArea = boxA[2] * boxA[3]
        boxBArea = boxB[2] * boxB[3]

        iou = interArea / float(boxAArea + boxBArea - interArea)
        return iou

    def update(self, detections, frame=None):
        """
        Updates the tracker with new detections.
        Detections format: [ ([left, top, w, h], confidence, class_name), ... ]
        """
        for track in self.tracks:
            track.predict()

        matched_detections = set()
        matched_tracks = set()

        if self.tracks and detections:
            iou_matrix = np.zeros((len(self.tracks), len(detections)), dtype=np.float32)
            for t_idx, track in enumerate(self.tracks):
                for d_idx, det in enumerate(detections):
                    # Only match same class labels to prevent identity swaps
                    if track.class_name == det[2]:
                        iou_matrix[t_idx, d_idx] = self._calculate_iou(track.bbox, det[0])
                    else:
                        iou_matrix[t_idx, d_idx] = 0.0

            while True:
                max_val = np.max(iou_matrix)
                if max_val < self.min_iou:
                    break
                
                t_idx, d_idx = np.unravel_index(np.argmax(iou_matrix), iou_matrix.shape)
                
                track = self.tracks[t_idx]
                det = detections[d_idx]
                track.update(det[0], det[1])
                
                matched_tracks.add(t_idx)
                matched_detections.add(d_idx)
                
                iou_matrix[t_idx, :] = -1.0
                iou_matrix[:, d_idx] = -1.0

        # Initiate new tracks for unmatched detections
        for d_idx, det in enumerate(detections):
            if d_idx not in matched_detections:
                # Gating: only initiate new tracks if confidence is at least 0.40
                if det[1] >= 0.40:
                    new_track = Track(self.next_id, det[0], det[2], det[1], self.n_init)
                    self.tracks.append(new_track)
                    self.next_id += 1

        # Delete stale tracks
        self.tracks = [t for t in self.tracks if t.time_since_update <= self.max_age]

        # Format output active tracks
        active_tracks = []
        for track in self.tracks:
            # Only return tracks that are confirmed and updated in this frame
            if track.is_confirmed and track.time_since_update == 0:
                l, t, w, h = track.bbox
                ltrb = [l, t, l + w, t + h]
                active_tracks.append({
                    'id': track.track_id,
                    'bbox': [float(ltrb[0]), float(ltrb[1]), float(ltrb[2]), float(ltrb[3])],
                    'class': track.class_name,
                    'confidence': float(track.confidence)
                })

        return active_tracks
