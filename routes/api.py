from flask import Blueprint, jsonify, Response, current_app
import time
from engine.state import global_state
from engine.camera import camera_engine
from database import db

api_bp = Blueprint('api', __name__, url_prefix='/api')

@api_bp.route('/live')
def live_status():
    return jsonify(global_state.get())

@api_bp.route('/stats')
def stats():
    stats_data = db.get_stats()
    return jsonify(stats_data)

@api_bp.route('/events')
def events():
    return jsonify(db.get_recent_events(50))

@api_bp.route('/risk')
def risk():
    state = global_state.get()
    return jsonify({"score": state["risk_score"], "level": state["risk_level"]})

@api_bp.route('/session')
def session_info():
    if camera_engine.session_id:
        return jsonify({"session_id": camera_engine.session_id, "status": "active"})
    return jsonify({"status": "inactive"})

def generate_frames():
    while True:
        frame = camera_engine.get_frame()
        if frame is not None:
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
        else:
            time.sleep(0.1)

@api_bp.route('/video_feed')
def video_feed():
    if not camera_engine.is_running:
        camera_engine.start()
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')
