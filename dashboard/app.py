import json
import os
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = APP_DIR.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from flask import Flask, Response, jsonify, render_template

try:
    from .event_manager import EVENT_META, get_events, read_event_rows
    from .live_detector import live_driver_monitor
    from .risk_engine import risk_engine
    from .shared_state import DEFAULT_STATE, classify_risk
except ImportError:
    from event_manager import EVENT_META, get_events, read_event_rows
    from live_detector import live_driver_monitor
    from risk_engine import risk_engine
    from shared_state import DEFAULT_STATE, classify_risk


LIVE_STATUS_PATH = APP_DIR / "live_status.json"


app = Flask(__name__)


def _parse_timestamp(value):
    value = str(value or "").strip()

    for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(value, pattern)
        except ValueError:
            pass

    return None


def _yes_no(value):
    if isinstance(value, bool):
        return "YES" if value else "NO"
    text = str(value or "NO").strip().upper()
    return "YES" if text in {"YES", "TRUE", "1", "ON"} else "NO"


def _coerce_live_status(raw):
    status = dict(DEFAULT_STATE)
    status.update(raw or {})

    status["attention_score"] = int(
        max(0, min(100, round(float(status.get("attention_score", 100) or 100))))
    )
    status["risk_score"] = int(status.get("risk_score") or status["attention_score"])
    status["risk"] = str(status.get("risk") or classify_risk(status["risk_score"])).upper()
    status["eye_status"] = str(status.get("eye_status") or "UNKNOWN").upper()
    status["phone_status"] = _yes_no(status.get("phone_status"))
    status["head_pose"] = str(status.get("head_pose") or "CENTER").upper()
    status["head_movement"] = (
        "STABLE" if status["head_pose"] == "CENTER" else "MOVING"
    )
    status["yawning"] = _yes_no(status.get("yawning"))
    status["fps"] = int(float(status.get("fps", 0) or 0))
    status["ear"] = round(float(status.get("ear", 0) or 0), 3)
    status["mar"] = round(float(status.get("mar", 0) or 0), 3)
    status["phone_confidence"] = round(
        float(status.get("phone_confidence", 0) or 0), 3
    )
    status["head_yaw"] = round(float(status.get("head_yaw", 0) or 0), 1)
    status["head_pitch"] = round(float(status.get("head_pitch", 0) or 0), 1)
    status["head_roll"] = round(float(status.get("head_roll", 0) or 0), 1)
    status["active_alerts"] = list(status.get("active_alerts") or [])
    status["last_event"] = status["active_alerts"][0] if status["active_alerts"] else "CLEAR"
    status["camera_status"] = str(status.get("camera_status") or "WAITING").upper()

    return status


def get_live_status(include_risk=True):
    try:
        with LIVE_STATUS_PATH.open("r", encoding="utf-8") as file:
            status = _coerce_live_status(json.load(file))
    except (OSError, json.JSONDecodeError):
        status = _coerce_live_status(DEFAULT_STATE)

    if include_risk:
        stats = get_statistics(include_risk=False)
        risk = risk_engine.calculate_risk(stats=stats, live_status=status)
        status["risk_score"] = risk["score"]
        status["risk"] = risk["level"]

    return status


def _event_counts(rows):
    counter = Counter(row["event"] for row in rows)
    return {
        "drowsiness": counter.get("DROWSINESS", 0),
        "phone_usage": counter.get("PHONE_USAGE", 0),
        "yawning": counter.get("YAWNING", 0),
        "distraction": counter.get("DISTRACTION", 0),
    }


def get_statistics(include_risk=True):
    rows = read_event_rows()
    today = datetime.now().date()
    today_rows = [
        row for row in rows if (_parse_timestamp(row["timestamp"]) or datetime.min).date() == today
    ]
    recent_rows = rows[-20:]
    counts = _event_counts(rows)
    today_counts = _event_counts(today_rows)
    recent_counts = _event_counts(recent_rows)

    hourly_counter = Counter()
    for row in today_rows:
        parsed = _parse_timestamp(row["timestamp"])
        if parsed:
            hourly_counter[parsed.hour] += 1

    hourly_series = [
        {"hour": f"{hour:02d}:00", "count": hourly_counter.get(hour, 0)}
        for hour in range(24)
    ]

    event_mix = [
        {
            "event": event_name,
            "label": EVENT_META[event_name]["label"],
            "count": counts[key],
            "today": today_counts[key],
            "accent": EVENT_META[event_name]["accent"],
        }
        for event_name, key in (
            ("DROWSINESS", "drowsiness"),
            ("PHONE_USAGE", "phone_usage"),
            ("YAWNING", "yawning"),
            ("DISTRACTION", "distraction"),
        )
    ]

    stats = {
        "total_events": len(rows),
        "today_events": len(today_rows),
        "latest_events": list(reversed(rows[-20:])),
        "counts": counts,
        "today_counts": today_counts,
        "recent_counts": recent_counts,
        "event_mix": event_mix,
        "hourly_series": hourly_series,
        "drowsiness": counts["drowsiness"],
        "phone_usage": counts["phone_usage"],
        "yawning": counts["yawning"],
        "distraction": counts["distraction"],
    }

    if include_risk:
        live_status = get_live_status(include_risk=False)
        risk = risk_engine.calculate_risk(stats=stats, live_status=live_status)
        stats["risk"] = risk
        stats["risk_score"] = risk["score"]
        stats["risk_level"] = risk["level"]
    else:
        stats["risk"] = {"score": 100, "level": "LOW"}
        stats["risk_score"] = 100
        stats["risk_level"] = "LOW"

    return stats


def generate_live_frames():
    yield from live_driver_monitor.stream_frames()


@app.route("/")
def dashboard():
    return render_template(
        "index.html",
        stats=get_statistics(),
        live_status=get_live_status(),
        active_page="dashboard",
    )


@app.route("/analytics")
def analytics():
    return render_template(
        "analytics.html",
        stats=get_statistics(),
        live_status=get_live_status(),
        active_page="analytics",
    )


@app.route("/analytics/advanced")
def advanced_analytics():
    return render_template(
        "advanced_analytics.html",
        stats=get_statistics(),
        live_status=get_live_status(),
        active_page="analytics",
    )



@app.route("/reports")
def reports():
    return render_template(
        "reports.html",
        stats=get_statistics(),
        live_status=get_live_status(),
        active_page="reports",
    )


@app.route("/live")
def live():
    live_driver_monitor.start()
    return render_template(
        "live_monitor.html",
        stats=get_statistics(),
        live_status=get_live_status(),
        active_page="live",
    )


@app.route("/video_feed")
def video_feed():
    return Response(
        generate_live_frames(),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )


@app.route("/api/live_status")
def live_status():
    return jsonify(get_live_status())


@app.route("/api/events")
def events():
    return jsonify(get_events())


@app.route("/api/stats")
def stats():
    return jsonify(get_statistics())


@app.route("/api/risk")
def risk():
    stats_data = get_statistics()
    return jsonify(stats_data["risk"])


@app.route("/stop_feed")
def stop_feed():
    live_driver_monitor.stop()
    return jsonify(success=True)
if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"

    print("AI Driver Dashboard started")
    print(f"Dashboard: http://127.0.0.1:{port}")
    print(f"Live Monitor: http://127.0.0.1:{port}/live")

    app.run(
        host="0.0.0.0",
        port=port,
        debug=debug,
        threaded=True,
        use_reloader=False,
    )
