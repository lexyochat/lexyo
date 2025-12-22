# ============================================
#     Lexyo — Main Application (CLEAN PROD 2026)
#     + Render Ready (eventlet)
#     + Cloudflare Turnstile Invisible Support
# ============================================

import eventlet
eventlet.monkey_patch()

import os
from flask import Flask, render_template
from flask_socketio import SocketIO

# Load environment variables (.env)
from dotenv import load_dotenv
load_dotenv()

from py.config import DATA_DIR, TURNSTILE_SITE_KEY
from py.storage import load_channels
from py.cleanup import start_cleanup_task
from py.sockets_public import register_public_handlers
from py.sockets_private import register_private_handlers
from py.logger import log_info, log_error

# =========================================
#   FLASK + SOCKET.IO (EVENTLET)
# =========================================
app = Flask(__name__)
socketio = SocketIO(
    app,
    async_mode="eventlet",
    cors_allowed_origins="*"
)

# =========================================
#   ENSURE DATA DIR EXISTS
# =========================================
try:
    os.makedirs(DATA_DIR, exist_ok=True)
    log_info("app", f"DATA_DIR verified/created at: {DATA_DIR}")
except Exception as e:
    log_error("app", f"Error creating DATA_DIR: {e}")

# =========================================
#   LOAD CHANNELS AT STARTUP
# =========================================
try:
    load_channels()
    log_info("app", "Channels loaded successfully.")
except Exception as e:
    log_error("app", f"Error loading channels: {e}")

# =========================================
#   START CLEANUP BACKGROUND TASK
# =========================================
try:
    start_cleanup_task(socketio)
    log_info("app", "Cleanup background task started.")
except Exception as e:
    log_error("app", f"Error starting cleanup task: {e}")

# =========================================
#   REGISTER ALL SOCKET.IO HANDLERS
# =========================================
try:
    register_public_handlers(socketio)
    register_private_handlers(socketio)
    log_info("app", "Socket handlers registered successfully.")
except Exception as e:
    log_error("app", f"Error registering socket handlers: {e}")

# =========================================
#   MAIN ROUTE
# =========================================
@app.route("/")
def index():
    try:
        from py.state import rooms
        return render_template(
            "index.html",
            rooms=rooms,
            TURNSTILE_SITE_KEY=TURNSTILE_SITE_KEY
        )
    except Exception as e:
        log_error("app", f"Error rendering index route: {e}")
        return "Internal server error", 500

# =========================================
#   RUN SERVER (Render compatible)
# =========================================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    log_info("app", f"Server starting on port {port}...")
    socketio.run(app, host="0.0.0.0", port=port)
