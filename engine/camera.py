import base64
import queue
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

import cv2
import numpy as np

from config import LOG_COOLDOWN, PHONE_DETECT_INTERVAL
from database import db
from engine.face_analyzer import FaceAnalyzer
from engine.phone_detector import PhoneDetector
from engine.risk import risk_engine
from engine.state import global_state


@dataclass
class FrameJob:
    frame_base64: str
    client_timestamp: Optional[float] = None
    width: Optional[int] = None
    height: Optional[int] = None


_phone_detector: Optional[PhoneDetector] = None
_phone_detector_init_lock = threading.Lock()
_phone_detector_inference_lock = threading.Lock()


def get_phone_detector() -> PhoneDetector:
    global _phone_detector

    if _phone_detector is None:
        with _phone_detector_init_lock:
            if _phone_detector is None:
                _phone_detector = PhoneDetector()

    return _phone_detector


class BrowserFrameProcessor:
    """Processes camera frames supplied by a browser WebSocket session."""

    def __init__(self, phone_interval: int = PHONE_DETECT_INTERVAL):
        self.face_analyzer = FaceAnalyzer()
        self.phone_interval = max(1, phone_interval)
        self.frame_queue: queue.Queue[FrameJob] = queue.Queue(maxsize=1)
        self.stop_event = threading.Event()
        self.worker = threading.Thread(target=self._worker_loop, daemon=True)
        self.latest_result_lock = threading.Lock()
        self.latest_result: Optional[Dict[str, Any]] = None

        self.session_id = self._create_session()
        self.frames_received = 0
        self.frames_processed = 0
        self.frames_dropped = 0
        self.last_phone_detected = False
        self.last_phone_confidence = 0.0
        self.processing_fps = 0.0
        self.previous_processed_at = time.perf_counter()
        self.last_event_log = {
            "DROWSINESS": 0.0,
            "PHONE_USAGE": 0.0,
            "YAWNING": 0.0,
            "DISTRACTION": 0.0,
        }

        global_state.update(
            camera_status="WAITING",
            connection_status="CONNECTED",
            session_id=self.session_id,
            active_alerts=[],
            last_event="CLEAR",
        )
        self.worker.start()

    @staticmethod
    def _create_session() -> Optional[int]:
        try:
            return db.create_session()
        except Exception as exc:
            print(f"Unable to create monitoring session: {exc}")
            return None

    def close(self) -> None:
        self.stop_event.set()
        if self.worker.is_alive():
            self.worker.join(timeout=2)

        global_state.update(
            camera_status="OFFLINE",
            connection_status="DISCONNECTED",
            active_alerts=[],
            last_event="CLEAR",
        )

    def submit_frame(self, frame_base64: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if not frame_base64:
            return {"accepted": False, "reason": "empty frame"}

        metadata = metadata or {}
        job = FrameJob(
            frame_base64=frame_base64,
            client_timestamp=self._coerce_float(metadata.get("timestamp")),
            width=self._coerce_int(metadata.get("width")),
            height=self._coerce_int(metadata.get("height")),
        )

        self.frames_received += 1

        try:
            self.frame_queue.put_nowait(job)
        except queue.Full:
            try:
                self.frame_queue.get_nowait()
                self.frames_dropped += 1
            except queue.Empty:
                pass
            self.frame_queue.put_nowait(job)

        return {
            "accepted": True,
            "frames_received": self.frames_received,
            "frames_dropped": self.frames_dropped,
        }

    def get_latest_result(self) -> Dict[str, Any]:
        with self.latest_result_lock:
            if self.latest_result is not None:
                return dict(self.latest_result)

        return {
            "type": "status",
            "session_id": self.session_id,
            "connection_status": "CONNECTED",
            "camera_status": "WAITING",
            "attention_score": 100,
            "risk_score": 0,
            "risk_level": "LOW",
            "alert_level": "LOW",
            "phone_detected": False,
            "phone_status": "NO",
            "yawning": False,
            "yawning_status": "NO",
            "eye_status": "OPEN",
            "head_pose": "CENTER",
            "fps": 0,
            "active_alerts": [],
            "frames_received": self.frames_received,
            "frames_processed": self.frames_processed,
            "frames_dropped": self.frames_dropped,
        }

    @staticmethod
    def _coerce_float(value: Any) -> Optional[float]:
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _coerce_int(value: Any) -> Optional[int]:
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    def _worker_loop(self) -> None:
        while not self.stop_event.is_set():
            try:
                job = self.frame_queue.get(timeout=0.25)
            except queue.Empty:
                continue

            started_at = time.perf_counter()
            result = self._process_job(job, started_at)

            with self.latest_result_lock:
                self.latest_result = result

            self._publish_state(result)
            self.frame_queue.task_done()

    def _process_job(self, job: FrameJob, started_at: float) -> Dict[str, Any]:
        frame = self._decode_frame(job.frame_base64)
        if frame is None:
            return {
                **self.get_latest_result(),
                "type": "error",
                "message": "Invalid JPEG frame",
                "connection_status": "CONNECTED",
                "camera_status": "FRAME_ERROR",
            }

        self.frames_processed += 1

        _, face_data = self.face_analyzer.process_frame(frame)

        if self.frames_processed % self.phone_interval == 0:
            try:
                with _phone_detector_inference_lock:
                    _, self.last_phone_detected, self.last_phone_confidence = get_phone_detector().process_frame(
                        frame,
                        annotate=False,
                    )
            except Exception as exc:
                print(f"Phone detection error: {exc}")
                self.last_phone_detected = False
                self.last_phone_confidence = 0.0

        attention_score = int(risk_engine.calculate_attention_score(face_data, self.last_phone_detected))
        risk_score = int(100 - attention_score)
        risk_level = risk_engine.get_risk_level(attention_score)
        active_alerts = self._active_alerts(face_data, self.last_phone_detected)

        now = time.time()
        self._log_events(active_alerts, risk_level, now)
        self._update_fps()

        processing_ms = round((time.perf_counter() - started_at) * 1000, 1)
        latency_ms = None
        if job.client_timestamp:
            latency_ms = max(0, round(time.time() * 1000 - job.client_timestamp, 1))

        return {
            "type": "metrics",
            "session_id": self.session_id,
            "attention_score": attention_score,
            "risk_score": risk_score,
            "risk_level": risk_level,
            "alert_level": risk_level,
            "phone_detected": bool(self.last_phone_detected),
            "phone_status": "YES" if self.last_phone_detected else "NO",
            "phone_confidence": round(float(self.last_phone_confidence), 3),
            "yawning": bool(face_data["yawning"]),
            "yawning_status": "YES" if face_data["yawning"] else "NO",
            "eye_status": face_data["eye_status"],
            "head_pose": face_data["head_direction"],
            "head_movement": "STABLE" if face_data["head_direction"] == "CENTER" else "MOVING",
            "head_yaw": round(float(face_data["head_yaw"]), 2),
            "head_pitch": round(float(face_data["head_pitch"]), 2),
            "head_roll": round(float(face_data["head_roll"]), 2),
            "ear": round(float(face_data["ear"] or 0.0), 3),
            "mar": round(float(face_data["mar"] or 0.0), 3),
            "face_detected": bool(face_data["face_detected"]),
            "active_alerts": active_alerts,
            "last_event": active_alerts[0] if active_alerts else "CLEAR",
            "fps": int(round(self.processing_fps)),
            "processing_ms": processing_ms,
            "latency_ms": latency_ms,
            "frames_received": self.frames_received,
            "frames_processed": self.frames_processed,
            "frames_dropped": self.frames_dropped,
            "queue_depth": self.frame_queue.qsize(),
            "connection_status": "CONNECTED",
            "camera_status": "LIVE",
            "frame_width": job.width,
            "frame_height": job.height,
        }

    @staticmethod
    def _decode_frame(frame_base64: str) -> Optional[np.ndarray]:
        try:
            if "," in frame_base64:
                frame_base64 = frame_base64.split(",", 1)[1]

            frame_bytes = base64.b64decode(frame_base64, validate=False)
            frame_array = np.frombuffer(frame_bytes, dtype=np.uint8)
            return cv2.imdecode(frame_array, cv2.IMREAD_COLOR)
        except Exception as exc:
            print(f"Frame decode error: {exc}")
            return None

    @staticmethod
    def _active_alerts(face_data: Dict[str, Any], phone_detected: bool) -> list[str]:
        alerts = []

        if face_data["eye_status"] == "CLOSED":
            alerts.append("DROWSINESS")
        if phone_detected:
            alerts.append("PHONE_USAGE")
        if face_data["yawning"]:
            alerts.append("YAWNING")
        if face_data["head_direction"] not in {"CENTER", "UNKNOWN"}:
            alerts.append("DISTRACTION")
        if face_data["eye_status"] == "NO FACE":
            alerts.append("DISTRACTION")

        return alerts

    def _log_events(self, active_alerts: list[str], risk_level: str, now: float) -> None:
        if self.session_id is None:
            return

        for event_type in active_alerts:
            if now - self.last_event_log.get(event_type, 0.0) < LOG_COOLDOWN:
                continue

            try:
                db.log_event(self.session_id, event_type, risk_level)
                self.last_event_log[event_type] = now
            except Exception as exc:
                print(f"Unable to log {event_type}: {exc}")

    def _update_fps(self) -> None:
        now = time.perf_counter()
        delta = max(now - self.previous_processed_at, 0.0001)
        instant_fps = 1.0 / delta
        self.processing_fps = instant_fps if self.processing_fps == 0 else (0.85 * self.processing_fps + 0.15 * instant_fps)
        self.previous_processed_at = now

    @staticmethod
    def _publish_state(result: Dict[str, Any]) -> None:
        global_state.update(
            attention_score=result["attention_score"],
            risk_score=result["risk_score"],
            risk_level=result["risk_level"],
            eye_status=result["eye_status"],
            phone_status=result["phone_status"],
            phone_detected=result["phone_detected"],
            head_pose=result["head_pose"],
            head_movement=result["head_movement"],
            yawning=result["yawning_status"],
            fps=result["fps"],
            ear=result["ear"],
            mar=result["mar"],
            phone_confidence=result["phone_confidence"],
            head_yaw=result["head_yaw"],
            head_pitch=result["head_pitch"],
            head_roll=result["head_roll"],
            active_alerts=result["active_alerts"],
            last_event=result["last_event"],
            camera_status=result["camera_status"],
            connection_status=result["connection_status"],
            session_id=result["session_id"],
        )
