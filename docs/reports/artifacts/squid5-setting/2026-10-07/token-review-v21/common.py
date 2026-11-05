"""v21 shared settings for the token review pipeline (runs root, models, append-safe raw reads).

Raw run files may still be growing (a model's games still running), so every script reads the same byte prefix that
build.py recorded in data.json (cut at the last full line) and checks its sha256, instead of the whole file."""
import hashlib
from pathlib import Path

ROOT = Path.home() / 'squid5-runs/e52_v21'  # v21 runs; folders whose name starts with '_' (e.g. _stopped/) are ignored
MODELS = {  # model id -> (label, colour); a model with 0 finished games is skipped in every plot and table
    'gpt-6-sol': ('Sol', '#e3ad49'),
    'gpt-6-luna': ('Luna', '#48ba9c'),
    'glm-5.3-flash': ('GLM', '#6aa7e8'),  # blue: '#5bb98c' would sit next to Luna's teal
}


def read_prefix(path, size=None):
    """Bytes of `path` up to `size`, or (size None) up to the last complete line."""
    content = Path(path).read_bytes()
    if size is None:
        return content[:content.rfind(b'\n') + 1]
    assert len(content) >= size, f'{path} shrank; rebuild from build.py'
    return content[:size]


def sha(content):
    return hashlib.sha256(content).hexdigest()


def checked(record):
    """Raw bytes for a data.json input record, verified against its recorded prefix hash."""
    content = read_prefix(record['path'], record['size'])
    assert sha(content) == record['sha256'], f'{record["path"]} changed (not just appended); rebuild from build.py'
    return content


def active(models_with_games):
    """MODELS keys (in display order) that have at least one finished game."""
    present = set(models_with_games)  # may be a generator: materialise once
    return [m for m in MODELS if m in present]
