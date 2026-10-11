"""Django settings. Everything local: SQLite in WAL mode, files under var/."""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
VAR_DIR = Path(os.environ.get("SITEMEND_VAR_DIR", BASE_DIR.parent / "var"))
VAR_DIR.mkdir(parents=True, exist_ok=True)

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "local-demo-only-not-a-secret")
DEBUG = os.environ.get("DJANGO_DEBUG", "0") == "1"
ALLOWED_HOSTS = ["127.0.0.1", "localhost", "testserver"]

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "rest_framework",
    "shop",
    "sitemend",
]

MIDDLEWARE = [
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
APPEND_SLASH = False

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": os.environ.get("SITEMEND_DB", str(VAR_DIR / "sitemend.sqlite3")),
        "OPTIONS": {
            # API threads and worker threads write at the same time: WAL lets
            # readers continue, IMMEDIATE takes the write lock up front and the
            # timeout waits for it instead of failing with "database is locked".
            "transaction_mode": "IMMEDIATE",
            "timeout": 30,
            "init_command": "PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;",
        },
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True
TIME_ZONE = "UTC"
TEMPLATES: list[dict] = []

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PARSER_CLASSES": ["rest_framework.parsers.JSONParser"],
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PERMISSION_CLASSES": [],
    "UNAUTHENTICATED_USER": None,
}

# Celery on the filesystem transport. Job state lives in the database, so
# results are ignored and no result backend is configured.
BROKER_DIR = VAR_DIR / "broker"
for sub in ("in", "processed"):
    (BROKER_DIR / sub).mkdir(parents=True, exist_ok=True)
CELERY_BROKER_URL = "filesystem://"
CELERY_BROKER_TRANSPORT_OPTIONS = {
    "data_folder_in": str(BROKER_DIR / "in"),
    "data_folder_out": str(BROKER_DIR / "in"),
    "processed_folder": str(BROKER_DIR / "processed"),
    "store_processed": False,
    "polling_interval": 0.25,
}
CELERY_TASK_IGNORE_RESULT = True
CELERY_TASK_ALWAYS_EAGER = os.environ.get("CELERY_EAGER", "0") == "1"
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_WORKER_HIJACK_ROOT_LOGGER = False
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True

# Where the crawler reaches the origin and edge mounts. Tests swap in an
# in-process WSGI transport instead of a socket.
SITEMEND_SELF_URL = os.environ.get("SITEMEND_SELF_URL", "http://127.0.0.1:14124")
SITEMEND_PUBLIC_DOMAIN = "https://mossgrove-clayworks.example"

# Model and replay settings, read by sitemend.llm.
SITEMEND_MODEL = os.environ.get("SITEMEND_MODEL", "claude-sonnet-5-5")
SITEMEND_MAX_SESSIONS = int(os.environ.get("SITEMEND_MAX_SESSIONS", "3"))
SITEMEND_SESSION_TIMEOUT_S = float(os.environ.get("SITEMEND_SESSION_TIMEOUT_S", "180"))
SITEMEND_FIXTURES_DIR = BASE_DIR / "fixtures" / "replay"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {"httpx": {"level": "WARNING"}},
}
