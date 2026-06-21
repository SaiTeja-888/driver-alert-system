# AI Driver Monitoring and Alert System - Enterprise Refactor

## Architecture Migration Plan

The previous architecture suffered from severe camera access conflicts because both `main.py` and the Flask application in `dashboard/app.py` attempted to initialize `cv2.VideoCapture(0)`. In addition, logging was done using basic CSV files, and there was no clean separation of concerns.

### New Single-Process Architecture
We have transitioned to a **Single-Process, Multi-Threaded Architecture**:
1. **`app.py` (Entry Point):** Initializes the Flask application and automatically spawns a background thread for the `CameraEngine`.
2. **`engine/camera.py` (CameraEngine):** A singleton class that safely acquires the camera feed once, processes frames with AI models, and broadcasts the live feed securely via MJPEG.
3. **`engine/face_analyzer.py` & `engine/phone_detector.py`:** Retained the robust MediaPipe Face Mesh and YOLOv8 logic but cleaned up for integration into the `CameraEngine`.
4. **`engine/state.py`:** Implements a thread-safe global state dictionary. The background camera thread writes telemetry here, and Flask reads from it instantly without blocking.
5. **`database.py`:** Replaced CSV with a robust SQLite schema tracking `drivers`, `sessions`, `events`, `alerts`, and `reports`.
6. **Frontend:** Introduced a modern Dark Theme with Glassmorphism, real-time Chart.js analytics, and MJPEG streaming without the previous `live.jpg` refresh hack.

## Setup Instructions

1. Ensure you have Python 3.10+ installed.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Ensure the YOLO model `yolo11m.pt` (or `yolo11n.pt`) is present in the root directory.
4. Run the application:
   ```bash
   python app.py
   ```
5. Open your browser and navigate to `http://127.0.0.1:5000`

## Legacy Cleanup
The old `main.py`, `dashboard/` directory, and `utils/` directory can now be safely removed. All logic has been successfully migrated to the root directory, `engine/`, `routes/`, `templates/`, and `static/`.
