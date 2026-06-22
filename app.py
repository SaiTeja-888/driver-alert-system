import os
import atexit
from flask import Flask

from routes.api import api_bp
from routes.views import views_bp


def create_app():
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static"
    )

    # Register Blueprints
    app.register_blueprint(api_bp)
    app.register_blueprint(views_bp)

    @app.before_request
    def start_camera():
        try:
            from engine.camera import camera_engine

            if not camera_engine.is_running:
                camera_engine.start()

        except Exception as e:
            print(f"Camera startup error: {e}")

    def cleanup():
        try:
            from engine.camera import camera_engine
            camera_engine.stop()
        except Exception:
            pass

    atexit.register(cleanup)

    return app


# Required for Gunicorn
app = create_app()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"

    print("=======================================")
    print("AI Driver Dashboard starting...")
    print(f"URL: http://127.0.0.1:{port}")
    print("=======================================")

    app.run(
        host="0.0.0.0",
        port=port,
        debug=debug,
        use_reloader=False,
        threaded=True,
    )