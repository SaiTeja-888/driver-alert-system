import os
import atexit
from flask import Flask
from config import PROJECT_ROOT
from routes.api import api_bp
from routes.views import views_bp
from engine.camera import camera_engine

def create_app():
    app = Flask(__name__, template_folder='templates', static_folder='static')
    
    # Register Blueprints
    app.register_blueprint(api_bp)
    app.register_blueprint(views_bp)

    # Start the Camera Engine Thread automatically
    @app.before_request
    def start_camera():
        if not camera_engine.is_running:
            camera_engine.start()

    # Clean up on exit
    def cleanup():
        camera_engine.stop()

    atexit.register(cleanup)

    return app

if __name__ == '__main__':
    port = int(os.environ.get("PORT", "5000"))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"

    print("=======================================")
    print("AI Driver Dashboard starting...")
    print(f"URL: http://127.0.0.1:{port}")
    print("=======================================")

    app = create_app()
    # use_reloader=False is critical to prevent the camera thread from starting twice
    app.run(host="0.0.0.0", port=port, debug=debug, use_reloader=False, threaded=True)
