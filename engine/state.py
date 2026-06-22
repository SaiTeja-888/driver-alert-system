from threading import Lock
from datetime import datetime

class StateManager:
    def __init__(self):
        self.lock = Lock()
        self.state = {
            "attention_score": 100,
            "risk_score": 0,
            "risk_level": "LOW",
            "eye_status": "OPEN",
            "phone_status": "NO",
            "phone_detected": False,
            "head_pose": "CENTER",
            "head_movement": "STABLE",
            "yawning": "NO",
            "fps": 0,
            "ear": 0.0,
            "mar": 0.0,
            "phone_confidence": 0.0,
            "head_yaw": 0.0,
            "head_pitch": 0.0,
            "head_roll": 0.0,
            "active_alerts": [],
            "last_event": "CLEAR",
            "camera_status": "WAITING",
            "connection_status": "DISCONNECTED",
            "session_id": None,
            "last_updated": datetime.now().isoformat(timespec="seconds"),
        }

    def update(self, **kwargs):
        with self.lock:
            self.state.update(kwargs)
            self.state["last_updated"] = datetime.now().isoformat(timespec="seconds")

    def get(self):
        with self.lock:
            return dict(self.state)

global_state = StateManager()
