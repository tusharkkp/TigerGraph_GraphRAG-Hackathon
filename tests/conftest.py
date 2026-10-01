"""Shared pytest configuration and fixtures."""

import sys
from pathlib import Path

from dotenv import load_dotenv

# Ensure project root is on sys.path for imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Load environment variables for tests
load_dotenv(PROJECT_ROOT / ".env")
