# ============================================
#     Lexyo — Cleanup Task (CLEAN PROD)
#     Public rooms ONLY
# ============================================

from py.config import CLEANUP_INTERVAL_SECONDS
from py.rooms import cleanup_rooms
from py.logger import log_info, log_exception

# Set this to True if you want logs *only when something is deleted*
SILENT_CLEANUP = True


def start_cleanup_task(socketio):
    """
    Start the recurring cleanup background task.

    IMPORTANT (MP-02C):
    - This task ONLY cleans PUBLIC rooms.
    - Private messages (MP) are deleted deterministically
      at disconnect time (see sockets_public.py).
    - cleanup_rooms() MUST NOT touch MP rooms.
    """
    log_info("cleanup", "Starting cleanup background task (public rooms only).")

    def _task():
        while True:
            try:
                socketio.sleep(CLEANUP_INTERVAL_SECONDS)

                # cleanup_rooms handles:
                # - TTL for empty public rooms
                # - public orphan files
                # - debounced channel save
                cleanup_rooms(socketio)

                if not SILENT_CLEANUP:
                    log_info("cleanup", "Cleanup cycle executed successfully.")

            except Exception as e:
                log_exception("cleanup", f"Error during cleanup cycle: {e}")

    socketio.start_background_task(_task)
