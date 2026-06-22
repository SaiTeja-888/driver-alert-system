import json
from typing import Any, Dict

try:
    from simple_websocket.errors import ConnectionClosed
except Exception:  # pragma: no cover - import depends on installed websocket backend
    ConnectionClosed = RuntimeError


MAX_FRAME_CHARS = 2_500_000


def register_ws_routes(sock):
    @sock.route("/ws")
    def monitor_socket(ws):
        from engine.camera import BrowserFrameProcessor

        processor = BrowserFrameProcessor()

        try:
            ws.send(json.dumps(processor.get_latest_result()))

            while True:
                raw_message = ws.receive()
                if raw_message is None:
                    break

                message = _parse_message(raw_message)
                frame = message.get("frame")

                if not isinstance(frame, str):
                    ws.send(json.dumps({"type": "error", "message": "Missing frame"}))
                    continue

                if len(frame) > MAX_FRAME_CHARS:
                    ws.send(json.dumps({"type": "error", "message": "Frame too large"}))
                    continue

                ack = processor.submit_frame(frame, metadata=message)
                response = processor.get_latest_result()
                response.update(
                    accepted=ack["accepted"],
                    frames_received=ack.get("frames_received", response.get("frames_received", 0)),
                    frames_dropped=ack.get("frames_dropped", response.get("frames_dropped", 0)),
                )
                ws.send(json.dumps(response))

        except ConnectionClosed:
            pass
        except Exception as exc:
            try:
                ws.send(json.dumps({"type": "error", "message": str(exc)}))
            except Exception:
                pass
        finally:
            processor.close()


def _parse_message(raw_message: Any) -> Dict[str, Any]:
    if isinstance(raw_message, bytes):
        raw_message = raw_message.decode("utf-8")

    if not isinstance(raw_message, str):
        return {}

    try:
        parsed = json.loads(raw_message)
    except json.JSONDecodeError:
        return {}

    return parsed if isinstance(parsed, dict) else {}
