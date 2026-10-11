"""Settings for pytest: replay mode, eager Celery and a scratch data folder."""

import os
import tempfile

os.environ["SITEMEND_VAR_DIR"] = tempfile.mkdtemp(prefix="sitemend-test-")
os.environ["CELERY_EAGER"] = "1"
# Jobs always run on replay in tests; tests/test_live.py calls the live provider directly.
os.environ["DEMO_REPLAY"] = "1"

from .settings import *  # noqa: E402,F403
