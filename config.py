import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
DATABASE_PATH = PROJECT_ROOT / "data" / "driver_monitor.db"
MODELS_DIR = PROJECT_ROOT
YOLO_MODEL_PATH = MODELS_DIR / "yolo11n.pt"  # Falling back to nano for performance, or keep yolo11m.pt if preferred
if not YOLO_MODEL_PATH.exists():
    YOLO_MODEL_PATH = MODELS_DIR / "yolo11m.pt"

LOG_COOLDOWN = 5  # seconds
FPS_TARGET = 60
