"""Keep legacy sibling imports working when the repository tests are packages."""

import sys
from pathlib import Path

TEST_DIR = str(Path(__file__).resolve().parent)
if TEST_DIR not in sys.path:
    sys.path.insert(0, TEST_DIR)
