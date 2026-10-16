"""Compatibility entry point: render speech-based groups, never opener groups."""
import runpy
from pathlib import Path

runpy.run_path(str(Path(__file__).with_name('build_semantic_transfers.py')), run_name='__main__')
