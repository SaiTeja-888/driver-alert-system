import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
DATABASE_PATH = PROJECT_ROOT / "data" / "driver_monitor.db"
MODELS_DIR = PROJECT_ROOT
YOLO_MODEL_PATH = MODELS_DIR / "yolo11n.pt"
if not YOLO_MODEL_PATH.exists():
    YOLO_MODEL_PATH = MODELS_DIR / "yolo11m.pt"

LOG_COOLDOWN = int(os.environ.get("LOG_COOLDOWN", "5"))
PHONE_DETECT_INTERVAL = int(os.environ.get("PHONE_DETECT_INTERVAL", "5"))
FPS_TARGET = int(os.environ.get("FPS_TARGET", "30"))
