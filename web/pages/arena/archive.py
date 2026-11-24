"""A finished room's run directory, copied to a Google Cloud Storage bucket (``WEB5_GCS_BUCKET``).

The server's own disk does not outlive a restart on Cloud Run, so when a room ends (finished, stopped or failed) its
run directory (config.yaml, meta.json, events.jsonl, results.jsonl; the layout tools/monitor reads) is uploaded to
``gs://<bucket>/<WEB5_GCS_PREFIX or "runs">/<run dir name>/``. The events are also in the database (store.py); the
bucket keeps the analysis-ready files. Without ``WEB5_GCS_BUCKET`` nothing is uploaded. Credentials are the
service's own (Application Default Credentials: the Cloud Run service account; locally ``gcloud auth
application-default login``). A failed upload is logged and never breaks the room.
"""

from __future__ import annotations

import logging
import os
import threading
from pathlib import Path

log = logging.getLogger("web5.archive")


def bucket_name() -> str:
    return os.environ.get("WEB5_GCS_BUCKET", "").strip()


def upload_run(run_dir: Path) -> list[str]:
    """Upload every file of *run_dir*; returns the object names written ([] without a bucket)."""
    name = bucket_name()
    if not name:
        return []
    from google.cloud import storage  # optional dependency, only with WEB5_GCS_BUCKET

    prefix = os.environ.get("WEB5_GCS_PREFIX", "runs").strip("/")
    bucket = storage.Client().bucket(name)
    done = []
    for f in sorted(Path(run_dir).iterdir()):
        if f.is_file():
            obj = f"{prefix}/{Path(run_dir).name}/{f.name}"
            bucket.blob(obj).upload_from_filename(str(f))
            done.append(obj)
    log.info("archived %s -> gs://%s/%s/%s/", run_dir, name, prefix, Path(run_dir).name)
    return done


def upload_run_async(run_dir: Path) -> None:
    """``upload_run`` in a background thread; errors are logged."""
    if not bucket_name():
        return

    def go():
        try:
            upload_run(run_dir)
        except Exception:  # noqa: BLE001
            log.exception("archive upload failed for %s", run_dir)

    threading.Thread(target=go, name=f"archive-{Path(run_dir).name}", daemon=True).start()
