"""Stable paths shared by tests; never import a pytest conftest module."""
from pathlib import Path

LAYOUTS = Path(__file__).parent / "fixtures" / "layouts"
