"""Entry point. Serves with the Flask dev server in dev, waitress in prod.

Environment (`SUBJECT_TRACKER_ENV`): `dev` (default) | `prod` | `test`.

Dev (localhost):                 python run.py
Dev on the LAN:                  HOST=0.0.0.0 python run.py
Production (waitress):           SUBJECT_TRACKER_ENV=prod SUBJECT_TRACKER_SECRET=... python run.py

Environment variables:
    SUBJECT_TRACKER_ENV     dev | prod | test  (default dev)
    SUBJECT_TRACKER_SECRET  session signing key (REQUIRED in prod)
    HOST                    interface to bind (default 127.0.0.1; 0.0.0.0 to expose)
    PORT                    port to listen on   (default 5000)
    DEBUG                   dev only: 1 enables the reloader/debugger — honoured
                            ONLY on localhost (the Werkzeug debugger runs code).
"""

import os

from tracker import create_app
from tracker.config import DEFAULT_SECRET

app = create_app()


def _is_local(host: str) -> bool:
    return host in ("127.0.0.1", "localhost", "::1")


if __name__ == "__main__":
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "5000"))
    is_prod = app.config.get("ENV") == "prod"

    if not _is_local(host) and app.config.get("SECRET_KEY") == DEFAULT_SECRET:
        print(
            "WARNING: using the default SECRET_KEY while exposed on the network.\n"
            "         Set one with: export SUBJECT_TRACKER_SECRET='<random-string>'\n"
        )

    if is_prod:
        # Production: a real, multi-threaded WSGI server. No debugger, ever.
        from waitress import serve

        print(f"Serving Subject Tracker (production / waitress) on http://{host}:{port}")
        serve(app, host=host, port=port)
    else:
        # Dev: Flask's built-in server. Debugger only on a localhost bind.
        debug = os.environ.get("DEBUG") == "1" and _is_local(host)
        app.run(host=host, port=port, debug=debug)
