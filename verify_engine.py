import os
import sys
import time
import shutil
import cv2

# Make sure the project directory is in the path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

import config
from database.db import init_db, insert_incident, get_incidents, get_dashboard_metrics, get_db_connection
from detector.accident_logic import AccidentDetector
from reports.pdf_generator import generate_incident_pdf

def test_database():
    print("--- Testing Database Operations ---")
    init_db()
    print("Database initialized.")
    
    # Insert mock incidents
    inc_id1 = insert_incident("Low", "Abrupt Stop", vehicle_id=12)
    inc_id2 = insert_incident("High", "Pedestrian Collision & Fall", vehicle_id=5, person_id=21)
    
    print(f"Inserted mock incidents. IDs: {inc_id1}, {inc_id2}")
    
    # Query incidents
    incidents = get_incidents(limit=5)
    print(f"Total incidents queried: {len(incidents)}")
    assert len(incidents) >= 2, "Failed to query inserted incidents."
    
    # Get dashboard stats
    stats = get_dashboard_metrics()
    print("Dashboard metrics:", stats)
    assert stats['total_incidents'] >= 2, "Incidents count metric mismatch."
    print("Database checks passed successfully.\n")

def test_accident_detection_logic():
    print("--- Testing Accident Detection Logic ---")
    detector = AccidentDetector()
    
    # Scenario 1: Vehicle collision
    print("Simulating Vehicle Collision...")
    # Two vehicles moving closer to each other over multiple frames
    # Coordinates format: [left, top, right, bottom]
    t = time.time()
    for i in range(5):
        t_frame = t + i * 0.05
        # On frame 3 and 4 we simulate them stopping abruptly after impact
        idx1 = i if i < 3 else 3
        idx2 = i if i < 3 else 3
        tracks = [
            {'id': 1, 'class': 'car', 'bbox': [100 + idx1*15, 100, 150 + idx1*15, 150], 'confidence': 0.85},
            {'id': 2, 'class': 'truck', 'bbox': [200 - idx2*15, 100, 260 - idx2*15, 160], 'confidence': 0.90}
        ]
        detector.update_states(tracks, t_frame)
        incidents = detector.analyze_incidents(t_frame)
        collision_inc = [inc for inc in incidents if inc['incident_type'] == 'Vehicle Collision']
        if collision_inc:
            print(f"Collision incident triggered on frame {i}:", collision_inc[0]['description'])
            assert collision_inc[0]['risk_level'] == 'High', "Collision should be high risk."
            break
            
    # Scenario 2: Pedestrian fall
    print("Simulating Pedestrian Fall...")
    detector = AccidentDetector() # reset
    t = time.time()
    # Person aspect ratio (width/height) changes from vertical to horizontal
    for i in range(5):
        t_frame = t + i * 0.05
        # Frame 0-2: aspect ratio width/height = 20/60 = 0.33 (Standing)
        # Frame 3-4: aspect ratio width/height = 65/30 = 2.16 (Lying down)
        w = 20 if i < 3 else 65
        h = 60 if i < 3 else 30
        tracks = [
            {'id': 21, 'class': 'person', 'bbox': [100, 100, 100+w, 100+h], 'confidence': 0.92}
        ]
        detector.update_states(tracks, t_frame)
        incidents = detector.analyze_incidents(t_frame)
        if incidents:
            print(f"Fall incident triggered on frame {i}:", incidents[0]['description'])
            assert incidents[0]['risk_level'] == 'High', "Fallen alone should be high risk."
            break

    # Scenario 3: Motionless pedestrian after fall
    print("Simulating Motionless Pedestrian after Fall...")
    detector = AccidentDetector() # reset
    t = time.time()
    
    # 1. Trigger Fall
    tracks = [{'id': 21, 'class': 'person', 'bbox': [100, 100, 160, 130], 'confidence': 0.92}] # fallen posture ratio 60/30=2.0
    detector.update_states(tracks, t)
    detector.analyze_incidents(t)
    
    # 2. Stay in fallen posture and motionless for MOTIONLESS_DURATION (3 seconds)
    t_after_3s = t + 4.0
    detector.update_states(tracks, t_after_3s)
    incidents = detector.analyze_incidents(t_after_3s)
    if incidents:
        print("Motionless incident triggered:", incidents[0]['description'].encode('ascii', 'ignore').decode('ascii'))
        assert incidents[0]['risk_level'] == 'High', "Motionless pedestrian should be high risk."
    else:
        print("Error: Motionless trigger failed.")
        assert False, "Motionless trigger failed."
        
    print("Accident detection engine checks passed successfully.\n")

def test_pdf_generation():
    print("--- Testing ReportLab PDF Generation ---")
    
    # Make sure we have a mock incident in DB
    init_db()
    inc_id = insert_incident(
        risk_level="High", 
        incident_type="PDF Mock Incident", 
        vehicle_id=12, 
        person_id=21
    )
    
    # Setup dummy screenshot file
    dummy_img_rel = "static/incidents/incident_test.jpg"
    dummy_img_path = os.path.join(config.BASE_DIR, dummy_img_rel)
    
    # Create a small dummy image using OpenCV (white block)
    import numpy as np
    img = np.ones((180, 320, 3), dtype=np.uint8) * 255
    cv2.putText(img, "RADAR AI MOCK CAPTURE", (30, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 1)
    cv2.imwrite(dummy_img_path, img)
    
    # Link screenshot path in database
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE incidents SET screenshot_path = ? WHERE id = ?", (dummy_img_rel, inc_id))
    conn.commit()
    conn.close()
    
    # Run PDF Generation
    pdf_out = os.path.join(config.BASE_DIR, "static", "uploads", f"test_report_{inc_id}.pdf")
    generate_incident_pdf(inc_id, pdf_out)
    
    print(f"Generated PDF file: {pdf_out}")
    assert os.path.exists(pdf_out), "PDF file was not created."
    print("PDF generation checks passed successfully.\n")

if __name__ == '__main__':
    try:
        test_database()
        test_accident_detection_logic()
        test_pdf_generation()
        print("=============================")
        print("ALL ENGINE TESTS PASSED!")
        print("=============================")
    except Exception as e:
        print("\nTEST FAILED WITH ERROR:")
        import traceback
        traceback.print_exc()
        sys.exit(1)
