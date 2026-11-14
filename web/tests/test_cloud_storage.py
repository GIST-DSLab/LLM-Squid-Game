"""The Google Cloud move: a dropped Postgres connection is reopened once, and a finished run dir goes to the bucket."""

from __future__ import annotations

import sys
import types

import pytest

from web.server import archive
from web.server.store import Store


class OperationalError(Exception):
    pass


class FakeConn:
    def __init__(self, log, fail_first=False):
        self.log, self.fail = log, fail_first

    def cursor(self):
        conn = self

        class Cur:
            def execute(self, sql, params=()):
                if conn.fail:
                    conn.fail = False
                    raise OperationalError("server closed the connection unexpectedly")
                conn.log.append(sql)

        return Cur()

    def close(self):
        pass


def test_a_dropped_postgres_connection_is_reopened_once():
    log, opened = [], []

    class Reopening(Store):  # Store with its connection factory swapped for fakes
        @property
        def conn(self):
            if self._conn is None:
                opened.append(1)
                self._conn = FakeConn(log)
            return self._conn

    st = Reopening(dsn="postgresql://x")
    st._conn = FakeConn(log, fail_first=True)  # the first statement meets a dropped connection
    st._exec("SELECT 1")
    assert opened == [1] and log == ["SELECT 1"]


def test_other_errors_are_not_retried():
    st = Store(dsn="postgresql://x")

    class Boom(FakeConn):
        def cursor(self):
            raise ValueError("bad sql")

    st._conn = Boom([])
    with pytest.raises(ValueError):
        st._exec("SELECT 1")


def test_a_run_dir_is_uploaded_to_the_bucket(tmp_path, monkeypatch):
    run = tmp_path / "20261114_120000_ABCDEF"
    run.mkdir()
    for name in ("config.yaml", "meta.json", "events.jsonl", "results.jsonl"):
        (run / name).write_text("x")
    put = {}

    class Blob:
        def __init__(self, name):
            self.name = name

        def upload_from_filename(self, path):
            put[self.name] = path

    class Bucket:
        def blob(self, name):
            return Blob(name)

    class Client:
        def bucket(self, name):
            assert name == "arena-runs"
            return Bucket()

    storage = types.ModuleType("google.cloud.storage")
    storage.Client = Client
    monkeypatch.setitem(sys.modules, "google.cloud.storage", storage)
    monkeypatch.setitem(sys.modules, "google.cloud", types.ModuleType("google.cloud"))
    sys.modules["google.cloud"].storage = storage
    monkeypatch.setenv("WEB5_GCS_BUCKET", "arena-runs")
    out = archive.upload_run(run)
    assert sorted(out) == sorted(f"runs/{run.name}/{n}" for n in ("config.yaml", "meta.json", "events.jsonl", "results.jsonl"))
    assert put[f"runs/{run.name}/events.jsonl"] == str(run / "events.jsonl")


def test_no_bucket_no_upload(tmp_path, monkeypatch):
    monkeypatch.delenv("WEB5_GCS_BUCKET", raising=False)
    assert archive.upload_run(tmp_path) == []
