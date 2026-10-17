"""What the engine needs under Pyodide that the Worker does not ship, installed before ``squid5`` is imported.

- ``httpx``: imported at the top of squid5/core/providers.py and web/server/engine.py for the host's model calls.
  The Worker makes its model calls with ``js.fetch`` (ollama_fetch.py), so only the names the engine touches at
  import or in an ``except`` tuple are needed: a stand-in module whose calls raise.
- ``numpy``: imported by squid5/e52_game.py for ``report()`` (``np.mean``) only; a session never calls it. A stand-in
  with ``mean`` keeps the bundle and the cold start small (the real package adds megabytes to the snapshot).
- threads: ``Session._calls`` runs a batch of model calls in a ``ThreadPoolExecutor``; Pyodide cannot start a thread.
  ``InlineExecutor`` runs each job at once, in order, and keeps its exception, so every call of a batch is made (and
  every missing reply registered, see replay.py) before the first exception is raised by ``result()``. It is swapped
  in only while a replay runs (``inline_executor()``), so a CPython process that also runs the experiment keeps its
  threads.

Each stand-in is installed only when the real module cannot be imported, so the same code runs under CPython with
the real packages (the tests in web/cloudflare/tests use them).
"""

from __future__ import annotations

import contextlib
import sys
import types


def _stub_httpx() -> None:
    try:
        import httpx  # noqa: F401
        return
    except ImportError:
        pass
    m = types.ModuleType("httpx")

    class HTTPError(Exception):
        pass

    class HTTPStatusError(HTTPError):
        pass

    def _no(*_a, **_k):
        raise HTTPError("httpx is not available in the Worker; model calls go through ollama_fetch.py")

    m.HTTPError, m.HTTPStatusError, m.TimeoutException = HTTPError, HTTPStatusError, HTTPError
    m.post = m.get = m.stream = m.request = _no
    sys.modules["httpx"] = m


def _stub_numpy() -> None:
    try:
        import numpy  # noqa: F401
        return
    except ImportError:
        pass
    m = types.ModuleType("numpy")
    m.mean = lambda xs: sum(xs) / len(xs)
    sys.modules["numpy"] = m


class _Done:
    def __init__(self, fn, a, k):
        self._value, self._error = None, None
        try:
            self._value = fn(*a, **k)
        except BaseException as err:  # noqa: BLE001 - kept like a Future keeps it; replay.Suspend is a BaseException
            self._error = err

    def result(self, timeout=None):
        if self._error is not None:
            raise self._error
        return self._value


class InlineExecutor:
    """``ThreadPoolExecutor`` without threads: ``submit`` runs the job now."""

    def __init__(self, max_workers=None, *a, **k):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def submit(self, fn, *a, **k):
        return _Done(fn, a, k)

    def shutdown(self, wait=True, **k):
        pass


def install() -> None:
    """Call once before importing ``squid5`` or ``web.server``."""
    _stub_httpx()
    _stub_numpy()


@contextlib.contextmanager
def inline_executor():
    """``Session._calls`` without threads for the duration (it looks ``ThreadPoolExecutor`` up at call time)."""
    from squid5 import e52_game

    before = e52_game.ThreadPoolExecutor
    e52_game.ThreadPoolExecutor = InlineExecutor
    try:
        yield
    finally:
        e52_game.ThreadPoolExecutor = before
