import sys
import os
import math
import time
from collections import deque

# Add parent directory to path to allow config import
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from database.db import insert_incident, insert_detection

class AccidentDetector:
    def __init__(self):
        # Maps track_id to object states
        # Format of state:
        # {
        #   'class': class_name,
        #   'timestamps': deque(maxlen=15),
        #   'centroids': deque(maxlen=15), # (x, y) smoothed
        #   'raw_bboxes': deque(maxlen=15),  # [left, top, right, bottom]
        #   'velocities': deque(maxlen=15), # (vx, vy)
        #   'speeds': deque(maxlen=15),     # float
        #   'accelerations': deque(maxlen=15), # float
        #   'directions': deque(maxlen=15),  # float (degrees)
        #   'aspect_ratios': deque(maxlen=15), # float
        #   'last_seen': float,
        #   'posture': str, # 'standing' or 'fallen'
        #   'posture_change_time': float,
        #   'motionless_start_time': float,
        #   'fall_detected': bool,
        #   'incident_triggered': set() # set of incident types already logged for this object
        # }
        self.states = {}
        
        # Keep track of active alerts to prevent spamming duplicate events
        # key: tuple of (incident_type, vehicle_id, person_id) or similar, value: timestamp
        self.cooldowns = {}
        self.cooldown_period = 15.0 # seconds before logging the exact same event again

    def _calculate_iou(self, boxA, boxB):
        """Calculates Intersection over Union (IoU) of two bounding boxes."""
        xA = max(boxA[0], boxB[0])
        yA = max(boxA[1], boxB[1])
        xB = min(boxA[2], boxB[2])
        yB = min(boxA[3], boxB[3])

        interArea = max(0, xB - xA) * max(0, yB - yA)
        if interArea == 0:
            return 0.0

        boxAArea = (boxA[2] - boxA[0]) * (boxA[3] - boxA[1])
        boxBArea = (boxB[2] - boxB[0]) * (boxB[3] - boxB[1])

        iou = interArea / float(boxAArea + boxBArea - interArea)
        return iou

    def _get_distance(self, p1, p2):
        """Euclidean distance between two coordinates."""
        return math.sqrt((p1[0] - p2[0])**2 + (p1[1] - p2[1])**2)

    def _get_edge_distance(self, box1, box2):
        """Calculates the minimum edge-to-edge distance between two bounding boxes."""
        l1, t1, r1, b1 = box1
        l2, t2, r2, b2 = box2
        
        # Horizontal gap
        if r1 < l2:
            dx = l2 - r1
        elif r2 < l1:
            dx = l1 - r2
        else:
            dx = 0.0
            
        # Vertical gap
        if b1 < t2:
            dy = t2 - b1
        elif b2 < t1:
            dy = t1 - b2
        else:
            dy = 0.0
            
        return max(dx, dy)

    def _is_cooldown_active(self, event_key):
        """Checks if a similar alert was triggered recently."""
        curr_time = time.time()
        if event_key in self.cooldowns:
            if curr_time - self.cooldowns[event_key] < self.cooldown_period:
                return True
        self.cooldowns[event_key] = curr_time
        return False

    def update_states(self, active_tracks, current_time=None):
        """
        Updates internal motion state tracking for all current tracks.
        """
        if current_time is None:
            current_time = time.time()
            
        current_track_ids = set()
        
        for track in active_tracks:
            track_id = track['id']
            class_name = track['class']
            bbox = track['bbox'] # [left, top, right, bottom]
            conf = track['confidence']
            
            # Store confidence in state to conditionally log to DB later
            # (do not store normal stage detections in database)
            
            # Bounding box dimensions & centroid
            left, top, right, bottom = bbox
            width = max(1.0, right - left)
            height = max(1.0, bottom - top)
            centroid = (left + width/2.0, top + height/2.0)
            aspect_ratio = width / height
            
            # Initialize state if not tracked
            if track_id not in self.states:
                self.states[track_id] = {
                    'class': class_name,
                    'timestamps': deque(maxlen=15),
                    'centroids': deque(maxlen=15),
                    'raw_bboxes': deque(maxlen=15),
                    'velocities': deque(maxlen=15),
                    'speeds': deque(maxlen=15),
                    'accelerations': deque(maxlen=15),
                    'directions': deque(maxlen=15),
                    'aspect_ratios': deque(maxlen=15),
                    'last_seen': current_time,
                    'posture': 'standing',
                    'posture_change_time': current_time,
                    'motionless_start_time': None,
                    'fall_detected': False,
                    'incident_triggered': set(),
                    'risk_level': 'Normal'
                }
                
            state = self.states[track_id]
            state['last_seen'] = current_time
            state['confidence'] = conf
            
            # Apply moving average smoothing to centroid to eliminate bbox jitter noise
            if len(state['centroids']) > 0:
                prev_smoothed = state['centroids'][-1]
                # Alpha of 0.6 for smoothing
                smooth_x = prev_smoothed[0] * 0.4 + centroid[0] * 0.6
                smooth_y = prev_smoothed[1] * 0.4 + centroid[1] * 0.6
                state['centroids'].append((smooth_x, smooth_y))
            else:
                state['centroids'].append(centroid)
                
            state['timestamps'].append(current_time)
            state['raw_bboxes'].append(bbox)
            state['aspect_ratios'].append(aspect_ratio)
            
            # Calculate velocity and kinematics
            if len(state['timestamps']) >= 2:
                dt = state['timestamps'][-1] - state['timestamps'][-2]
                if dt > 0:
                    p1 = state['centroids'][-2]
                    p2 = state['centroids'][-1]
                    vx = (p2[0] - p1[0]) / dt
                    vy = (p2[1] - p1[1]) / dt
                    speed = math.sqrt(vx**2 + vy**2)
                    direction = math.atan2(vy, vx) * 180.0 / math.pi
                    
                    state['velocities'].append((vx, vy))
                    state['speeds'].append(speed)
                    state['directions'].append(direction)
                    
                    # Calculate acceleration
                    if len(state['speeds']) >= 2:
                        dv = speed - state['speeds'][-2]
                        accel = dv / dt
                        state['accelerations'].append(accel)
                    else:
                        state['accelerations'].append(0.0)
            else:
                state['velocities'].append((0.0, 0.0))
                state['speeds'].append(0.0)
                state['directions'].append(0.0)
                state['accelerations'].append(0.0)
                
            # Posture identification for pedestrians and two-wheelers (width/height ratio)
            if class_name == 'person':
                # If aspect ratio is larger than threshold, it indicates lying down / fallen posture
                if aspect_ratio >= config.FALL_ASPECT_RATIO:
                    if state['posture'] == 'standing':
                        state['posture'] = 'fallen'
                        state['posture_change_time'] = current_time
                        state['motionless_start_time'] = current_time
                else:
                    if state['posture'] == 'fallen':
                        # Require a short recovery period to confirm standing
                        state['posture'] = 'standing'
                        state['posture_change_time'] = current_time
                        state['motionless_start_time'] = None
                        state['fall_detected'] = False
            elif class_name in ['motorcycle', 'bicycle']:
                # Motorcycle / bicycle rollover aspect ratio check (typically width/height >= 1.3 when fallen)
                if aspect_ratio >= 1.3:
                    if state['posture'] == 'standing':
                        state['posture'] = 'fallen'
                        state['posture_change_time'] = current_time
                        state['motionless_start_time'] = current_time
                else:
                    if state['posture'] == 'fallen':
                        state['posture'] = 'standing'
                        state['posture_change_time'] = current_time
                        state['motionless_start_time'] = None
                        state['fall_detected'] = False
                        
            # Update motionless timer if fallen and speed is low
            if state['posture'] == 'fallen':
                speed = state['speeds'][-1] if len(state['speeds']) > 0 else 0.0
                # Velocity threshold for motionless
                if speed < 4.0: 
                    if state['motionless_start_time'] is None:
                        state['motionless_start_time'] = current_time
                else:
                    # Reset motionless timer if person/object moves significantly
                    state['motionless_start_time'] = None

        # Remove stale tracks that haven't been seen in the last 2 seconds
        stale_ids = []
        for track_id, state in self.states.items():
            if current_time - state['last_seen'] > 2.0:
                stale_ids.append(track_id)
        for tid in stale_ids:
            del self.states[tid]

    def analyze_incidents(self, current_time=None):
        """
        Evaluates current motion states to detect traffic incidents.
        Returns list of newly detected incident dictionaries.
        """
        if current_time is None:
            current_time = time.time()
            
        # Reset risk levels for all tracked objects at the beginning of each frame's analysis.
        # However, if an object was already involved in a high-risk accident (collision, rollover, or fall),
        # keep its risk level as High so its bounding box remains Red.
        for tid, state in self.states.items():
            is_accident = (
                'collision' in state['incident_triggered'] or 
                'rollover' in state['incident_triggered'] or 
                state.get('fall_detected', False)
            )
            if is_accident:
                state['risk_level'] = 'High'
            else:
                state['risk_level'] = 'Normal'
            
        detected_incidents = []
        
        # Gather references to current active vehicles and pedestrians
        vehicles = []
        people = []
        
        for tid, state in self.states.items():
            if state['last_seen'] == current_time:
                if state['class'] in ['car', 'motorcycle', 'bus', 'truck', 'bicycle']:
                    vehicles.append((tid, state))
                elif state['class'] == 'person':
                    people.append((tid, state))
 
        # --- 1. Vehicle-Vehicle Interactions (Collisions & Proximity) ---
        for i in range(len(vehicles)):
            for j in range(i + 1, len(vehicles)):
                id1, v1 = vehicles[i]
                id2, v2 = vehicles[j]
                
                box1 = v1['raw_bboxes'][-1]
                box2 = v2['raw_bboxes'][-1]
                
                iou = self._calculate_iou(box1, box2)
                p1 = v1['centroids'][-1]
                p2 = v2['centroids'][-1]
                dist = self._get_distance(p1, p2)
                edge_dist = self._get_edge_distance(box1, box2)
                
                # Check for proximity or overlap
                if iou > 0.05 or edge_dist < 15.0 or dist < config.PROXIMITY_THRESHOLD * 2.0:
                    v1_recent = list(v1['speeds'])[-5:]
                    v2_recent = list(v2['speeds'])[-5:]
                    v1_avg = sum(v1_recent) / len(v1_recent) if v1_recent else 0.0
                    v2_avg = sum(v2_recent) / len(v2_recent) if v2_recent else 0.0
                    
                    v1_was_moving = len(v1['speeds']) > 3 and any(s > 10.0 for s in list(v1['speeds'])[:-2])
                    v2_was_moving = len(v2['speeds']) > 3 and any(s > 10.0 for s in list(v2['speeds'])[:-2])
                    
                    v1_deceled = (v1['speeds'][-1] < 5.0) or (v1['accelerations'][-1] < -config.SUDDEN_STOP_DECEL * 0.3 if len(v1['accelerations']) > 0 else False)
                    v2_deceled = (v2['speeds'][-1] < 5.0) or (v2['accelerations'][-1] < -config.SUDDEN_STOP_DECEL * 0.3 if len(v2['accelerations']) > 0 else False)
                    
                    # High Risk Accident Criteria:
                    # - Significant overlap (IoU > 0.15) OR touching/extremely close (edge_dist < 15.0px)
                    # - AND at least one was moving and decelerated/stopped, OR both are stationary (touching/crashed site)
                    is_real_collision = False
                    if iou > 0.15 or edge_dist < 15.0:
                        if (v1_was_moving and v1_deceled) or (v2_was_moving and v2_deceled):
                            is_real_collision = True
                        elif v1_avg < 4.0 and v2_avg < 4.0:
                            is_real_collision = True
                        # check trajectory change
                        elif len(v1['directions']) >= 3 and len(v2['directions']) >= 3:
                            v1_dir_change = abs(v1['directions'][-1] - v1['directions'][-3])
                            v2_dir_change = abs(v2['directions'][-1] - v2['directions'][-3])
                            if v1_dir_change > 45.0 or v2_dir_change > 45.0:
                                is_real_collision = True
                                
                    if is_real_collision:
                        event_key = ('vehicle_collision', min(id1, id2), max(id1, id2))
                        if not self._is_cooldown_active(event_key):
                            incident = {
                                'risk_level': 'High',
                                'incident_type': 'Vehicle Collision',
                                'vehicle_id': id1,
                                'person_id': None,
                                'description': f"Collision detected between vehicle #{id1} ({v1['class']}) and vehicle #{id2} ({v2['class']})."
                            }
                            detected_incidents.append(incident)
                            v1['incident_triggered'].add('collision')
                            v2['incident_triggered'].add('collision')
                        v1['risk_level'] = 'High'
                        v2['risk_level'] = 'High'
                    else:
                        # Moderate Risk: Vehicles moving close to each other (potential collision risk but no impact)
                        event_key = ('vehicle_proximity', min(id1, id2), max(id1, id2))
                        if not self._is_cooldown_active(event_key):
                            incident = {
                                'risk_level': 'Moderate',
                                'incident_type': 'Vehicle Proximity Alert',
                                'vehicle_id': id1,
                                'person_id': None,
                                'description': f"Vehicles #{id1} and #{id2} are in close proximity (Distance: {dist:.1f}px, IoU: {iou:.2f})."
                            }
                            detected_incidents.append(incident)
                        if v1['risk_level'] != 'High':
                            v1['risk_level'] = 'Moderate'
                        if v2['risk_level'] != 'High':
                            v2['risk_level'] = 'Moderate'

        # --- 2. Sudden Stops ---
        for tid, state in vehicles:
            if len(state['speeds']) >= 4:
                # Deceleration check: check if average deceleration in last few frames exceeds threshold
                accel = state['accelerations'][-1]
                # Negative acceleration means deceleration
                if accel < -config.SUDDEN_STOP_DECEL:
                    # Make sure it came from a reasonable speed
                    prev_speeds = list(state['speeds'])[-4:-1]
                    if any(s > 25.0 for s in prev_speeds) and state['speeds'][-1] < 5.0:
                        event_key = ('sudden_stop', tid, None)
                        if not self._is_cooldown_active(event_key):
                            incident = {
                                'risk_level': 'Moderate',
                                'incident_type': 'Sudden Stop',
                                'vehicle_id': tid,
                                'person_id': None,
                                'description': f"Vehicle #{tid} ({state['class']}) decelerated and stopped abruptly."
                            }
                            detected_incidents.append(incident)
                            state['incident_triggered'].add('sudden_stop')
                        if state['risk_level'] != 'High':
                            state['risk_level'] = 'Moderate'

        # --- 3. Sudden Trajectory Deviations ---
        for tid, state in vehicles:
            if len(state['directions']) >= 5:
                # Check direction difference between recent steps
                dirs = list(state['directions'])
                speeds = list(state['speeds'])
                
                # Check angle change if vehicle is moving at reasonable speed
                if speeds[-1] > 20.0:
                    d_angle = abs(dirs[-1] - dirs[-3])
                    # Normalize angle diff to [0, 180]
                    if d_angle > 180.0:
                        d_angle = 360.0 - d_angle
                        
                    if d_angle > config.SPEED_CHANGE_THRESHOLD:
                        event_key = ('trajectory_change', tid, None)
                        if not self._is_cooldown_active(event_key):
                            incident = {
                                'risk_level': 'Low',
                                'incident_type': 'Sudden Trajectory Change',
                                'vehicle_id': tid,
                                'person_id': None,
                                'description': f"Vehicle #{tid} ({state['class']}) made an abrupt change in direction of {d_angle:.1f}°."
                            }
                            detected_incidents.append(incident)
                            state['incident_triggered'].add('trajectory_change')

        # --- 4. Vehicle-Pedestrian Close Interactions / Proximity ---
        for pid, pstate in people:
            for vid, vstate in vehicles:
                p_centroid = pstate['centroids'][-1]
                v_centroid = vstate['centroids'][-1]
                dist = self._get_distance(p_centroid, v_centroid)
                
                # Close proximity interaction
                if dist < config.PROXIMITY_THRESHOLD * 2.0:
                    # Calculate rolling average speed to filter out bounding box jitter false alarms on parked cars
                    v_recent = list(vstate['speeds'])[-5:]
                    v_avg_speed = sum(v_recent) / len(v_recent) if v_recent else 0.0
                    
                    # If vehicle is actively moving in proximity of pedestrian
                    if v_avg_speed > 10.0:
                        event_key = ('vehicle_person_interaction', vid, pid)
                        if not self._is_cooldown_active(event_key):
                            incident = {
                                'risk_level': 'Moderate',
                                'incident_type': 'Vehicle-Person Proximity Event',
                                'vehicle_id': vid,
                                'person_id': pid,
                                'description': f"Pedestrian #{pid} in close proximity of moving vehicle #{vid} (Distance: {dist:.1f}px)."
                            }
                            detected_incidents.append(incident)
                            pstate['incident_triggered'].add('vehicle_interaction')
                            vstate['incident_triggered'].add('person_interaction')
                        if pstate['risk_level'] != 'High':
                            pstate['risk_level'] = 'Moderate'
                        if vstate['risk_level'] != 'High':
                            vstate['risk_level'] = 'Moderate'

        # --- 5. Pedestrian Fall / Crash in Vehicle Proximity ---
        for pid, pstate in people:
            # Check proximity to any vehicle that has experienced a collision, sudden stop, trajectory change, or rollover
            near_accident_vehicle = None
            for vid, vstate in vehicles:
                p_cent = pstate['centroids'][-1]
                v_cent = vstate['centroids'][-1]
                dist = self._get_distance(p_cent, v_cent)
                
                # Close proximity
                if dist < config.PROXIMITY_THRESHOLD * 2.5:
                    # Check if this vehicle had a recent incident or is a fallen motorcycle/bicycle
                    had_incident = (
                        'collision' in vstate['incident_triggered'] or
                        'sudden_stop' in vstate['incident_triggered'] or
                        'trajectory_change' in vstate['incident_triggered'] or
                        vstate['posture'] == 'fallen'
                    )
                    if had_incident:
                        near_accident_vehicle = vid
                        break
            
            # If the person has a fallen posture, OR they are close to an accident vehicle (even with normal aspect ratio)
            has_fallen = (pstate['posture'] == 'fallen')
            is_near_crash = (near_accident_vehicle is not None)
            
            if (has_fallen or is_near_crash) and not pstate['fall_detected']:
                pstate['fall_detected'] = True
                
                if near_accident_vehicle is not None:
                    event_key = ('person_fall_accident', near_accident_vehicle, pid)
                    if not self._is_cooldown_active(event_key):
                        incident = {
                            'risk_level': 'High',
                            'incident_type': 'Pedestrian Collision & Fall',
                            'vehicle_id': near_accident_vehicle,
                            'person_id': pid,
                            'description': f"High Risk: Pedestrian #{pid} involved in collision/crash near vehicle #{near_accident_vehicle}."
                        }
                        detected_incidents.append(incident)
                    pstate['risk_level'] = 'High'
                    vstate_obj = self.states.get(near_accident_vehicle)
                    if vstate_obj:
                        vstate_obj['risk_level'] = 'High'
                elif has_fallen:
                    # Fall alone without direct vehicle proximity
                    event_key = ('person_fall_alone', None, pid)
                    if not self._is_cooldown_active(event_key):
                        incident = {
                            'risk_level': 'High',
                            'incident_type': 'Pedestrian Fall',
                            'vehicle_id': None,
                            'person_id': pid,
                            'description': f"Pedestrian #{pid} has fallen/collapsed on the road."
                        }
                        detected_incidents.append(incident)
                    pstate['risk_level'] = 'High'

        # --- 6. Motionless Pedestrian (High Risk Trigger) ---
        for pid, pstate in people:
            if pstate['posture'] == 'fallen':
                m_start = pstate['motionless_start_time']
                if m_start is not None:
                    duration = current_time - m_start
                    if duration >= config.MOTIONLESS_DURATION:
                        # Only trigger if we haven't already flagged this person as motionless
                        if 'motionless' not in pstate['incident_triggered']:
                            pstate['incident_triggered'].add('motionless')
                            
                            event_key = ('motionless_person', None, pid)
                            if not self._is_cooldown_active(event_key):
                                # Check if a vehicle was involved in recent history
                                matched_vehicle = None
                                # Search state keys to find if this person had a collision or vehicle interaction flag
                                if 'vehicle_interaction' in pstate['incident_triggered']:
                                    # Find nearby vehicle
                                    for vid, vstate in vehicles:
                                        if self._get_distance(pstate['centroids'][-1], vstate['centroids'][-1]) < config.PROXIMITY_THRESHOLD * 3.5:
                                            matched_vehicle = vid
                                            break
                                
                                incident = {
                                    'risk_level': 'High',
                                    'incident_type': 'Motionless Pedestrian',
                                    'vehicle_id': matched_vehicle,
                                    'person_id': pid,
                                    'description': f"🚨 High Risk: Pedestrian #{pid} has remained motionless on road surface for {duration:.1f}s after fall."
                                }
                                detected_incidents.append(incident)
                            pstate['risk_level'] = 'High'

        # --- 7. Motorcycle / Bicycle Rollover ---
        for tid, state in vehicles:
            if state['class'] in ['motorcycle', 'bicycle']:
                if state['posture'] == 'fallen' and 'rollover' not in state['incident_triggered']:
                    event_key = ('motorcycle_fall', tid, None)
                    if not self._is_cooldown_active(event_key):
                        incident = {
                            'risk_level': 'High',
                            'incident_type': 'Motorcycle Fall / Rollover',
                            'vehicle_id': tid,
                            'person_id': None,
                            'description': f"High Risk: Motorcycle/Bicycle #{tid} rollover detected."
                        }
                        detected_incidents.append(incident)
                        state['incident_triggered'].add('rollover')
                    state['risk_level'] = 'High'

        # Persist detected incidents to the SQLite database ONLY for Moderate and High Risk
        for inc in detected_incidents:
            if inc['risk_level'] in ['High', 'Moderate']:
                inc_id = insert_incident(
                    risk_level=inc['risk_level'],
                    incident_type=inc['incident_type'],
                    vehicle_id=inc['vehicle_id'],
                    person_id=inc['person_id'],
                    screenshot_path=None,
                    video_path=None
                )
                inc['id'] = inc_id
            else:
                inc['id'] = None
                
        # Log detections to the database ONLY for tracks involved in Moderate or High risk incidents
        # (do not store detections for normal stage traffic)
        for tid, state in self.states.items():
            if state['last_seen'] == current_time:
                if state['risk_level'] in ['High', 'Moderate']:
                    insert_detection(state['class'], tid, state.get('confidence', 0.80))
            
        return detected_incidents
