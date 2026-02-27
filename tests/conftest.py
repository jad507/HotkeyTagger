"""pytest configuration: add the project root to sys.path."""

import os
import sys

# Allow tests to import project modules without requiring an installable package.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
