import cv2
import mediapipe as mp
import numpy as np
from scipy.spatial import distance

LEFT_EYE = [33, 160, 158, 133, 153, 144]
RIGHT_EYE = [362, 385, 387, 263, 373, 380]
MOUTH = [61, 13, 14, 291]
HEAD_POSE_POINTS = [1, 152, 33, 263, 61, 291]

class FaceAnalyzer:
    def __init__(self):
        self.mp_face_mesh = mp.solutions.face_mesh
        self.face_mesh = self.mp_face_mesh.FaceMesh(
            static_image_mode=False,
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.6,
            min_tracking_confidence=0.6,
        )
        self.closed_frames = 0
        self.yawn_frames = 0
        self.head_off_center_frames = 0

    @staticmethod
    def calculate_ear(eye):
        v1 = distance.euclidean(eye[1], eye[5])
        v2 = distance.euclidean(eye[2], eye[4])
        h = distance.euclidean(eye[0], eye[3])
        return (v1 + v2) / (2 * h) if h else 0.0

    @staticmethod
    def calculate_mar(mouth):
        h = distance.euclidean(mouth[0], mouth[3])
        v = distance.euclidean(mouth[1], mouth[2])
        return v / h if h else 0.0

    @staticmethod
    def _landmark_point(landmarks, index, width, height):
        lm = landmarks.landmark[index]
        return int(lm.x * width), int(lm.y * height)

    def _estimate_head_pose(self, landmarks, width, height):
        image_points = np.array(
            [self._landmark_point(landmarks, index, width, height) for index in HEAD_POSE_POINTS],
            dtype=np.float64,
        )

        model_points = np.array([
            (0.0, 0.0, 0.0),
            (0.0, -63.6, -12.5),
            (-43.3, 32.7, -26.0),
            (43.3, 32.7, -26.0),
            (-28.9, -28.9, -24.1),
            (28.9, -28.9, -24.1),
        ], dtype=np.float64)

        focal_length = width
        center = (width / 2, height / 2)
        camera_matrix = np.array([
            [focal_length, 0, center[0]],
            [0, focal_length, center[1]],
            [0, 0, 1],
        ], dtype=np.float64)
        dist_coeffs = np.zeros((4, 1))

        success, rotation_vector, translation_vector = cv2.solvePnP(
            model_points, image_points, camera_matrix, dist_coeffs, flags=cv2.SOLVEPNP_ITERATIVE
        )

        if not success:
            return "CENTER", {"yaw": 0.0, "pitch": 0.0, "roll": 0.0}

        rotation_matrix, _ = cv2.Rodrigues(rotation_vector)
        projection_matrix = np.hstack((rotation_matrix, translation_vector))
        _, _, _, _, _, _, euler_angles = cv2.decomposeProjectionMatrix(projection_matrix)

        pitch = float(euler_angles[0][0])
        yaw = float(euler_angles[1][0])
        roll = float(euler_angles[2][0])

        # Adjust thresholds for better calibration
        # pitch < -20 is usually a real "look down" for drivers
        # pitch > 20 is usually "look up"
        direction = "CENTER"
        if yaw < -20:
            direction = "LEFT"
        elif yaw > 20:
            direction = "RIGHT"
        elif pitch < -18: 
            direction = "DOWN"
        elif pitch > 18:
            direction = "UP"

        if direction == "CENTER":
            self.head_off_center_frames = 0
        else:
            self.head_off_center_frames += 1

        if self.head_off_center_frames < 3:
            direction = "CENTER"

        return direction, {"yaw": yaw, "pitch": pitch, "roll": roll}

    def process_frame(self, frame):
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self.face_mesh.process(rgb)

        data = {
            "ear": None,
            "mar": None,
            "eye_status": "OPEN",
            "head_direction": "CENTER",
            "head_yaw": 0.0,
            "head_pitch": 0.0,
            "head_roll": 0.0,
            "yawning": False,
            "face_detected": False,
        }

        if not results.multi_face_landmarks:
            self.closed_frames = 0
            self.yawn_frames = 0
            self.head_off_center_frames = 0
            data["eye_status"] = "NO FACE"
            data["head_direction"] = "UNKNOWN"
            return frame, data

        landmarks = results.multi_face_landmarks[0]
        height, width, _ = frame.shape
        data["face_detected"] = True

        left_eye = [self._landmark_point(landmarks, index, width, height) for index in LEFT_EYE]
        right_eye = [self._landmark_point(landmarks, index, width, height) for index in RIGHT_EYE]
        mouth = [self._landmark_point(landmarks, index, width, height) for index in MOUTH]

        ear = (self.calculate_ear(left_eye) + self.calculate_ear(right_eye)) / 2
        mar = self.calculate_mar(mouth)

        data["ear"] = ear
        data["mar"] = mar

        self.closed_frames = self.closed_frames + 1 if ear < 0.20 else 0
        self.yawn_frames = self.yawn_frames + 1 if mar > 0.60 else 0

        if self.closed_frames > 15:
            data["eye_status"] = "CLOSED"

        if self.yawn_frames > 5:
            data["yawning"] = True

        direction, angles = self._estimate_head_pose(landmarks, width, height)
        data["head_direction"] = direction
        data["head_yaw"] = angles["yaw"]
        data["head_pitch"] = angles["pitch"]
        data["head_roll"] = angles["roll"]

        # Removed visual dots for cleaner UI as requested
        # Head direction text remains for context on the HUD
        return frame, data
