import os

from flask import Flask
from flask_sock import Sock

from routes.api import api_bp
from routes.views import views_bp
from routes.websocket import register_ws_routes


def create_app():
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )
    app.config["SOCK_SERVER_OPTIONS"] = {"ping_interval": 25}

    app.register_blueprint(api_bp)
    app.register_blueprint(views_bp)

    sock = Sock(app)
    register_ws_routes(sock)

    return app


app = create_app()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"

    print("=======================================")
    print("AI Driver Dashboard starting...")
    print(f"URL: http://127.0.0.1:{port}")
    print("Camera source: browser WebSocket frames")
    print("=======================================")

    app.run(
        host="0.0.0.0",
        port=port,
        debug=debug,
        use_reloader=False,
        threaded=True,
    )
