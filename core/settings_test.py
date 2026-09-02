"""Test settings.

Identical to ``core.settings`` but with the structured-log file handler forced
off, so ``pytest`` never writes ``logs/app.log`` even after ``cp .env.example
.env`` (which ships ``LOG_JSON_FILE=True``). ``read_env`` in the base module
does not overwrite an already-set variable, so this wins.
"""

import os

os.environ["LOG_JSON_FILE"] = "False"

from core.settings import *  # noqa: E402, F401, F403
