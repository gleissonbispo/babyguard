"""
Shared test configuration and fixtures for BabyGuard tests.

All test files can import server modules directly because this conftest
adds the server/ directory to sys.path before any test runs.
"""
import sys
from pathlib import Path

# Make server modules importable without relative imports
sys.path.insert(0, str(Path(__file__).parent.parent / "server"))
