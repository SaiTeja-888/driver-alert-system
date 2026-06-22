from flask import Blueprint, jsonify

from database import db
from engine.state import global_state


api_bp = Blueprint("api", __name__, url_prefix="/api")


@api_bp.route("/health")
def health():
    return jsonify({"status": "ok", "transport": "websocket", "camera": "browser"})


@api_bp.route("/live")
def live_status():
    return jsonify(global_state.get())


@api_bp.route("/stats")
def stats():
    return jsonify(db.get_stats())


@api_bp.route("/events")
def events():
    return jsonify(db.get_recent_events(50))


@api_bp.route("/risk")
def risk():
    state = global_state.get()
    return jsonify({"score": state["risk_score"], "level": state["risk_level"]})


@api_bp.route("/session")
def session_info():
    state = global_state.get()
    session_id = state.get("session_id")

    if session_id:
        return jsonify({"session_id": session_id, "status": "active"})

    return jsonify({"status": "inactive"})
