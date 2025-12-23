# ============================================
#     Lexyo — Main Application (CLEAN PROD 2026)
#     + Cloudflare Turnstile Invisible Support
# ============================================

# -------------------------------------------------
#   EVENTLET PATCH (REQUIRED FOR GUNICORN + RENDER)
# -------------------------------------------------
import eventlet
eventlet.monkey_patch()

import os
from flask import Flask, render_template
from flask_socketio import SocketIO

# -----------------------------------------
#   ENV VARIABLES (.env / Render secrets)
# -----------------------------------------
from dotenv import load_dotenv
load_dotenv()

from py.config import DATA_DIR, TURNSTILE_SITE_KEY
from py.storage import load_channels
from py.cleanup import start_cleanup_task
from py.sockets_public import register_public_handlers
from py.sockets_private import register_private_handlers
from py.logger import log_info, log_error

# =========================================
#   FLASK + SOCKET.IO
# =========================================
app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")

# =========================================
#   ENSURE PERSISTENT DATA DIR EXISTS
# =========================================
# DATA_DIR is now the SINGLE SOURCE OF TRUTH
# (/var/data in prod, ./var/data in dev)
try:
    os.makedirs(DATA_DIR, exist_ok=True)
    log_info("app", f"Persistent DATA_DIR ready at: {DATA_DIR}")
except Exception as e:
    log_error("app", f"Fatal error creating DATA_DIR ({DATA_DIR}): {e}")

# =========================================
#   LOAD CHANNELS AT STARTUP
# =========================================
# Loads channels.json from persistent storage
try:
    load_channels()
    log_info("app", "Channels loaded successfully.")
except Exception as e:
    log_error("app", f"Error loading channels at startup: {e}")

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
#   MAIN ROUTE (Inject TURNSTILE_SITE_KEY)
# =========================================
@app.route("/")
def index():
    try:
        from py.state import rooms
        return render_template(
            "index.html",
            rooms=rooms,
            TURNSTILE_SITE_KEY=TURNSTILE_SITE_KEY,
        )
    except Exception as e:
        log_error("app", f"Error rendering index route: {e}")
        return "Internal server error", 500

# =========================================
#   RUN SERVER (DEV / PROD)
# =========================================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    log_info("app", f"Server starting on port {port}...")
    socketio.run(app, host="0.0.0.0", port=port)
