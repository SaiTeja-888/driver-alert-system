import cv2
from ultralytics import YOLO
from config import YOLO_MODEL_PATH
import torch

# Fix for PyTorch 2.6+ weights_only=True default issue with Ultralytics
# Monkeypatching torch.load to use weights_only=False as YOLO models need it
_original_torch_load = torch.load
def _safe_torch_load(*args, **kwargs):
    if 'weights_only' not in kwargs:
        kwargs['weights_only'] = False
    return _original_torch_load(*args, **kwargs)
torch.load = _safe_torch_load

class PhoneDetector:
    def __init__(self, confidence=0.12, iou=0.5):
        print(f"Loading YOLO phone detection model from {YOLO_MODEL_PATH}...")
        self.model = YOLO(str(YOLO_MODEL_PATH))
        self.confidence = confidence
        self.iou = iou

    def process_frame(self, frame):
        phone_detected = False
        phone_confidence = 0.0

        results = self.model(frame, conf=self.confidence, iou=self.iou, verbose=False)

        for result in results:
            if result.boxes is None:
                continue

            for box in result.boxes:
                cls = int(box.cls[0])
                conf = float(box.conf[0])
                class_name = str(self.model.names[cls]).lower()

                if class_name != "cell phone" or conf < self.confidence:
                    continue

                phone_detected = True
                phone_confidence = max(phone_confidence, conf)

                x1, y1, x2, y2 = map(int, box.xyxy[0])
                cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 70, 255), 3)

                label = f"PHONE {conf:.2f}"
                (text_width, text_height), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
                cv2.rectangle(frame, (x1, max(0, y1 - text_height - 12)), (x1 + text_width + 14, y1), (0, 70, 255), -1)
                cv2.putText(frame, label, (x1 + 7, max(20, y1 - 7)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

        return frame, phone_detected, phone_confidence
