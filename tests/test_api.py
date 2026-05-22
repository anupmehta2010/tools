"""Contract tests for the stdlib HTTP server in server.py.

Starts `python tk.py serve --port <ephemeral> --no-browser` in a subprocess,
polls until it answers, then exercises the real /api/ endpoints.

Real interface (discovered from server.py):
  Start:    python tk.py server --port <p> --no-browser  (-> server.main)
            (tk.py routes "ui"/"web"/"server" to server.main; NOT "serve")
            flags: --host (default 127.0.0.1), --port (default 8765),
                   --no-browser (suppress webbrowser.open)
  GET  /api/categories         -> {"categories": [{key,label,icon,module,commands:[...]}]}
  GET  /api/schema/<cat>/<cmd> -> {"args": [...]}  (404 {"error":...} if not found)
  POST /api/run  body {"category","command","args":[...]}
                 -> {"rc","stdout","stderr","new_files","new_dirs"}
                 -> 400 {"error":"unknown category"} for a bad category
  GET  /api/doctor             -> {"python","platform","modules","binaries"}
  GET  /api/themes             -> {"themes":[...]}
  GET  /api/presets            -> {"presets":[...]}
  GET  /api/history?limit=N    -> {"runs":[...]}
"""
from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def _get(base: str, path: str):
    with urllib.request.urlopen(base + path, timeout=10) as r:
        return r.status, json.loads(r.read().decode("utf-8"))


def _post(base: str, path: str, payload: dict):
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        base + path,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status, json.loads(r.read().decode("utf-8"))


@pytest.fixture(scope="module")
def server():
    port = _free_port()
    proc = subprocess.Popen(
        [sys.executable, str(ROOT / "tk.py"), "server",
         "--port", str(port), "--no-browser"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(50):
            try:
                urllib.request.urlopen(base + "/api/categories", timeout=1)
                break
            except (urllib.error.URLError, OSError):
                if proc.poll() is not None:
                    out, err = proc.communicate()
                    pytest.fail(f"server exited early rc={proc.returncode}: {err}")
                time.sleep(0.2)
        else:
            proc.kill()
            pytest.fail("server did not start in time")
        yield base
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)


def test_categories(server):
    status, data = _get(server, "/api/categories")
    assert status == 200
    assert "categories" in data
    cats = data["categories"]
    assert isinstance(cats, list) and cats
    keys = {c["key"] for c in cats}
    assert "dev" in keys


def test_schema(server):
    status, data = _get(server, "/api/schema/dev/calc")
    assert status == 200
    assert "args" in data
    assert isinstance(data["args"], list)


def test_run(server):
    status, data = _post(server, "/api/run", {
        "category": "dev",
        "command": "calc",
        "args": ["2+2"],
    })
    assert status == 200
    assert data["rc"] == 0
    assert "4" in (data.get("stdout", "") + data.get("stderr", ""))


def test_doctor(server):
    status, data = _get(server, "/api/doctor")
    assert status == 200
    assert "python" in data
    assert "modules" in data


def test_run_unknown_category(server):
    """Malformed POST: unknown category -> 400 HTTPError with JSON error,
    OR a 200 with an error/nonzero rc in the body."""
    try:
        status, data = _post(server, "/api/run", {
            "category": "nope_not_a_category",
            "command": "whatever",
            "args": [],
        })
    except urllib.error.HTTPError as e:
        assert e.code >= 400
        body = json.loads(e.read().decode("utf-8"))
        assert "error" in body
        return
    # Fallback: if it returned 200, it must signal failure in the body.
    assert data.get("error") or data.get("rc", 0) != 0


def test_themes(server):
    status, data = _get(server, "/api/themes")
    assert status == 200
    assert isinstance(data.get("themes"), list)


def test_presets(server):
    status, data = _get(server, "/api/presets")
    assert status == 200
    assert "presets" in data


def test_history(server):
    status, data = _get(server, "/api/history?limit=5")
    assert status == 200
    assert "runs" in data
