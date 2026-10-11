"""Settings for pytest: replay mode, eager Celery and a scratch data folder."""

import atexit
import os
import shutil
import tempfile

_scratch = tempfile.mkdtemp(prefix="sitemend-test-")
atexit.register(shutil.rmtree, _scratch, ignore_errors=True)
os.environ["SITEMEND_VAR_DIR"] = _scratch
os.environ["CELERY_EAGER"] = "1"
# Jobs always run on replay in tests; tests/test_live.py calls the live provider directly.
os.environ["DEMO_REPLAY"] = "1"

from .settings import *  # noqa: E402,F403
