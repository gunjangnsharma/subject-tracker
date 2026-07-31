"""Development / LAN entry point.

Run locally (default, localhost only):
    python run.py

Expose on your local network so other devices can reach it:
    HOST=0.0.0.0 python run.py
then open http://<this-machine-ip>:5000 from the other device.

Environment variables:
    HOST   interface to bind (default 127.0.0.1; use 0.0.0.0 for LAN access)
    PORT   port to listen on   (default 5000)
    DEBUG  set to 1 to enable the reloader/debugger — ONLY honoured on localhost,
           because the Werkzeug debugger allows code execution and must never be
           reachable from the network.
"""

import os

from tracker import create_app

app = create_app()


def _is_local(host: str) -> bool:
    return host in ("127.0.0.1", "localhost", "::1")


if __name__ == "__main__":
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "5000"))
    # Debugger is only allowed when bound to localhost — never on a LAN bind.
    debug = os.environ.get("DEBUG") == "1" and _is_local(host)

    if not _is_local(host) and app.config.get("SECRET_KEY") == "dev-secret-change-me":
        print(
            "WARNING: using the default SECRET_KEY while exposed on the network.\n"
            "         Set one with: export SUBJECT_TRACKER_SECRET='<random-string>'\n"
        )

    app.run(host=host, port=port, debug=debug)
