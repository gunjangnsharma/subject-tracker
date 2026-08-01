"""WSGI entry point for external production servers (gunicorn, uWSGI, waitress).

The environment is resolved from SUBJECT_TRACKER_ENV (set it to `prod`), and the
app refuses to start in prod with the default SECRET_KEY.

    SUBJECT_TRACKER_ENV=prod SUBJECT_TRACKER_SECRET=... \
        waitress-serve --listen=127.0.0.1:5000 wsgi:app

    SUBJECT_TRACKER_ENV=prod SUBJECT_TRACKER_SECRET=... \
        gunicorn --bind 127.0.0.1:5000 wsgi:app        # Linux
"""

from tracker import create_app

app = create_app()
