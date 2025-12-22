# ============================================
#     Lexyo — Main Application (CLEAN PROD 2026)
#     + Render Ready (eventlet)
#     + Cloudflare Turnstile Invisible Support
#     PATCH 03: Persistent storage bootstrap
# ============================================

import eventlet
eventlet.monkey_patch()

import os
import requests
from flask import Flask, render_template
from flask_socketio import SocketIO

# Load environment variables (.env)
from dotenv import load_dotenv
load_dotenv()

from py.config import (
    DATA_DIR,
    PUBLIC_DIR,
    PRIVATE_DIR,
    CACHE_DIR,
    LOGS_DIR,
    TURNSTILE_SITE_KEY,
)
from py.storage import load_channels
from py.cleanup import start_cleanup_task
from py.sockets_public import register_public_handlers
from py.sockets_private import register_private_handlers
from py.logger import log_info, log_error

# =========================================
#   TURNSTILE (SERVER VERIFY HELPERS)
# =========================================
def verify_turnstile(token: str) -> bool:
    """
    Verify a Turnstile token against Cloudflare siteverify endpoint.
    - One-shot token expected (do not reuse tokens).
    - No remoteip sent (proxy environments like Render/CDN make remote IP unreliable).
    """
    try:
        secret = os.getenv("TURNSTILE_SECRET_KEY", "").strip()
        if not secret:
            log_error("turnstile", "TURNSTILE_SECRET_KEY is missing in environment.")
            return False

        if not token or not isinstance(token, str):
            log_info("turnstile", "Missing or invalid token.")
            return False

        token = token.strip()
        if not token:
            log_info("turnstile", "Empty token after strip.")
            return False

        r = requests.post(
            "https://challenges.cloudflare.com/turnstile/v0/siteverify",
            data={
                "secret": secret,
                "response": token,
            },
            timeout=5,
        )

        try:
            data = r.json()
        except Exception:
            log_error("turnstile", f"Non-JSON response from siteverify: {r.text[:500]}")
            return False

        ok = data.get("success") is True
        if not ok:
            codes = data.get("error-codes")
            log_info("turnstile", f"Verification failed. error-codes={codes}")
        return ok

    except Exception as e:
        log_error("turnstile", f"Verification exception: {e}")
        return False


# =========================================
#   FLASK + SOCKET.IO (EVENTLET)
# =========================================
app = Flask(__name__)
socketio = SocketIO(
    app,
    async_mode="eventlet",
    cors_allowed_origins="*"
)

# Expose helpers for other modules
app.config["VERIFY_TURNSTILE"] = verify_turnstile

# =========================================
#   ENSURE PERSISTENT STORAGE STRUCTURE EXISTS
# =========================================
try:
    for path in (DATA_DIR, PUBLIC_DIR, PRIVATE_DIR, CACHE_DIR, LOGS_DIR):
        os.makedirs(path, exist_ok=True)
    log_info("app", f"Persistent storage ready at: {DATA_DIR}")
except Exception as e:
    log_error("app", f"Error initializing persistent storage: {e}")

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
