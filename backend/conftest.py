"""
pytest conftest.py — makes backend/app importable from the tests directory.
"""
import sys
from pathlib import Path

# Add backend/ directory to PYTHONPATH so `from app.xxx import ...` works
sys.path.insert(0, str(Path(__file__).resolve().parent))
