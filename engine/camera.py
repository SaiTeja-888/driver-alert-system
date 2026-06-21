import cv2
import time
import threading
from engine.face_analyzer import FaceAnalyzer
from engine.phone_detector import PhoneDetector
from engine.risk import risk_engine
from engine.state import global_state
from database import db
from config import LOG_COOLDOWN

class CameraEngine:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(CameraEngine, cls).__new__(cls)
                cls._instance._init_engine()
            return cls._instance

    def _init_engine(self):
        self.cap = None
        self.analyzer = FaceAnalyzer()
        self.phone_detector = PhoneDetector()
        self.is_running = False
        self.thread = None
        self.current_frame = None
        self.frame_lock = threading.Lock()
        
        self.phone_detected = False
        self.phone_confidence = 0.0
        self.frame_counter = 0
        self.fps = 0.0
        self.previous_time = time.time()
        self.last_event_log = {
            "DROWSINESS": 0.0,
            "PHONE_USAGE": 0.0,
            "YAWNING": 0.0,
            "DISTRACTION": 0.0
        }
        self.session_id = None

    def start(self):
        if self.is_running:
            return
        
        self.cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
        if not self.cap.isOpened():
            self.cap = cv2.VideoCapture(0)
            
        if self.cap.isOpened():
            self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
            self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
            self.cap.set(cv2.CAP_PROP_FPS, 60)
            self.is_running = True
            self.session_id = db.create_session()
            global_state.update(camera_status="LIVE")
            self.thread = threading.Thread(target=self._process_loop, daemon=True)
            self.thread.start()
        else:
            global_state.update(camera_status="OFFLINE")

    def stop(self):
        self.is_running = False
        if self.thread:
            self.thread.join()
        if self.cap:
            self.cap.release()
        global_state.update(camera_status="OFFLINE", eye_status="NO CAMERA", phone_status="NO", head_pose="UNKNOWN")

    def _process_loop(self):
        while self.is_running:
            success, frame = self.cap.read()
            if not success:
                continue

            frame = cv2.flip(frame, 1)
            frame, data = self.analyzer.process_frame(frame)

            self.frame_counter += 1
            if self.frame_counter % 5 == 0:
                frame, self.phone_detected, self.phone_confidence = self.phone_detector.process_frame(frame)

            attention_score = risk_engine.calculate_attention_score(data, self.phone_detected)
            risk_level = risk_engine.get_risk_level(attention_score)

            current_time = time.time()
            self.fps = 0.9 * self.fps + 0.1 * (1 / max(current_time - self.previous_time, 0.0001))
            self.previous_time = current_time

            active_events = []
            if data["eye_status"] == "CLOSED":
                active_events.append("DROWSINESS")
            if self.phone_detected:
                active_events.append("PHONE_USAGE")
            if data["yawning"]:
                active_events.append("YAWNING")
            if data["head_direction"] not in {"CENTER", "UNKNOWN"}:
                active_events.append("DISTRACTION")

            for event in active_events:
                if current_time - self.last_event_log[event] >= LOG_COOLDOWN:
                    db.log_event(self.session_id, event, risk_level)
                    self.last_event_log[event] = current_time

            global_state.update(
                attention_score=attention_score,
                risk_score=attention_score,
                risk_level=risk_level,
                eye_status=data["eye_status"],
                phone_status="YES" if self.phone_detected else "NO",
                head_pose=data["head_direction"],
                head_movement="STABLE" if data["head_direction"] == "CENTER" else "MOVING",
                yawning="YES" if data["yawning"] else "NO",
                fps=int(self.fps),
                ear=data["ear"] or 0.0,
                mar=data["mar"] or 0.0,
                phone_confidence=self.phone_confidence,
                head_yaw=data["head_yaw"],
                head_pitch=data["head_pitch"],
                head_roll=data["head_roll"],
                active_alerts=active_events,
                last_event=active_events[0] if active_events else "CLEAR"
            )

            # Draw minimal overlay
            cv2.putText(frame, f"FPS: {int(self.fps)}", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
            cv2.putText(frame, f"Score: {attention_score}", (20, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0) if attention_score > 60 else (0, 0, 255), 2)

            ok, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            if ok:
                with self.frame_lock:
                    self.current_frame = buffer.tobytes()

            time.sleep(0.01)

    def get_frame(self):
        with self.frame_lock:
            return self.current_frame

camera_engine = CameraEngine()
