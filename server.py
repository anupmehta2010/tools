"""Web UI server for the toolkit. Pure stdlib HTTP server.

Endpoints:
    GET  /                                  -> index.html
    GET  /static/*                          -> web/* assets
    GET  /api/categories                    -> list categories + commands (incl. plugins)
    GET  /api/schema/<cat>/<cmd>            -> argparse schema for a command
    POST /api/run                           -> run synchronously, returns full result
    POST /api/run-async                     -> start a background job, returns {id}
    GET  /api/jobs                          -> list known jobs
    GET  /api/jobs/<id>                     -> snapshot of a job
    GET  /api/jobs/<id>/events              -> SSE stream of job events
    DELETE /api/jobs/<id>                   -> cancel a job
    POST /api/batch                         -> run a command across N input files
    GET  /api/files                         -> list workspace
    GET  /api/files/<name>                  -> download
    DELETE /api/files/<name>                -> remove
    POST /api/upload                        -> multipart upload
    POST /api/clear                         -> wipe workspace
    GET  /api/presets                       -> list saved presets
    POST /api/presets                       -> save preset
    DELETE /api/presets/<name>              -> delete preset
    GET  /api/history?limit=N               -> recent runs
    GET  /api/doctor                        -> environment report (JSON)
    GET  /api/themes                        -> bundled theme list
    GET  /api/config                        -> read config
    POST /api/config                        -> write config
    GET  /api/version                       -> version string
"""
from __future__ import annotations

import argparse
import contextlib
import http.server
import importlib
import io
import json
import mimetypes
import os
import queue
import re
import shutil
import socketserver
import sys
import threading
import time
import traceback
import urllib.parse
import uuid
import webbrowser
from pathlib import Path

import argparse as _ap

ROOT = Path(__file__).parent
WEB = ROOT / "web"
WORKSPACE = ROOT / "web_workspace"
WORKSPACE.mkdir(exist_ok=True)

sys.path.insert(0, str(ROOT))

try:
    import tk as _tk
except Exception:
    _tk = None


def _build_categories() -> dict[str, dict]:
    """Pull category list from tk.py (built-in + plugins)."""
    if _tk and hasattr(_tk, "available_categories"):
        cats = _tk.available_categories()
    elif _tk:
        cats = _tk.CATEGORIES
    else:
        cats = {}
    out: dict[str, dict] = {}
    for key, val in cats.items():
        if isinstance(val, tuple) and len(val) >= 3:
            module, label, icon = val[0], val[1], val[2]
        elif isinstance(val, tuple) and len(val) == 2:
            module, label = val
            icon = "🔧"
        elif isinstance(val, dict):
            module = val.get("module")
            label = val.get("label", key)
            icon = val.get("icon", "🔧")
        else:
            continue
        out[key] = {"module": module, "label": label, "icon": icon}
    return out


def get_categories() -> dict[str, dict]:
    return _build_categories()


_run_lock = threading.Lock()


# ============================================================ schema introspection

def _safe_default(v):
    if v is _ap.SUPPRESS:
        return None
    if v is None or isinstance(v, (int, float, str, bool)):
        return v
    if isinstance(v, (list, tuple)):
        return list(v)
    return str(v)


def _safe_nargs(n):
    if n is None or isinstance(n, (int, str)):
        return n
    return str(n)


def _parser_to_schema(parser):
    args = []
    for action in parser._actions:
        if isinstance(action, (_ap._HelpAction, _ap._SubParsersAction)):
            continue
        flags = list(action.option_strings)
        positional = not flags
        if action.type is None:
            type_name = "str"
        else:
            type_name = getattr(action.type, "__name__", str(action.type))
        if isinstance(action, (_ap._StoreTrueAction, _ap._StoreFalseAction)):
            type_name = "bool"
        likely_file = False
        if positional and action.dest in {"input", "inputs", "a", "b", "src", "sources", "file", "files", "path"}:
            likely_file = True
        if not positional and any(f in {"-i", "--input"} for f in flags):
            likely_file = True
        likely_output_file = False
        if positional and action.dest in {"output"}:
            likely_output_file = True
        if not positional and any(f in {"-o", "--output", "-d", "--outdir"} for f in flags):
            likely_output_file = True
        args.append({
            "name": action.dest,
            "flags": flags,
            "required": bool(getattr(action, "required", False)),
            "help": action.help or "",
            "default": _safe_default(action.default),
            "choices": list(action.choices) if action.choices and not isinstance(action.choices, dict) else None,
            "type": type_name,
            "nargs": _safe_nargs(action.nargs),
            "positional": positional,
            "likely_file": likely_file,
            "likely_output_file": likely_output_file,
        })
    return args


def get_command_schema(category, command):
    cats = get_categories()
    info = cats.get(category)
    if not info:
        return None
    try:
        mod = importlib.import_module(info["module"])
    except Exception:
        return None
    if not hasattr(mod, "build_parser"):
        return None
    parser = mod.build_parser()
    for action in parser._actions:
        if isinstance(action, _ap._SubParsersAction):
            sub = action.choices.get(command)
            if sub:
                return _parser_to_schema(sub)
    return None


def list_commands(category):
    cats = get_categories()
    info = cats.get(category)
    if not info:
        return []
    try:
        mod = importlib.import_module(info["module"])
    except Exception as e:
        return [{"error": str(e)}]
    cmds = getattr(mod, "COMMANDS", {})
    return [{"name": k, "help": v if isinstance(v, str) else (v[1] if len(v) > 1 else "")} for k, v in cmds.items()]


# ============================================================ sync tool runner

def run_tool(category, command, args_list):
    cats = get_categories()
    info = cats.get(category)
    if not info:
        return {"rc": 1, "stdout": "", "stderr": "unknown category", "new_files": [], "new_dirs": []}
    try:
        mod = importlib.import_module(info["module"])
    except Exception as e:
        return {"rc": 1, "stdout": "", "stderr": f"Could not import {info['module']}: {e}", "new_files": [], "new_dirs": []}

    with _run_lock:
        before = {p.name for p in WORKSPACE.iterdir() if p.is_file()}
        before_dirs = {p.name for p in WORKSPACE.iterdir() if p.is_dir()}
        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()
        cwd_before = os.getcwd()
        rc = 0
        try:
            os.chdir(WORKSPACE)
            with contextlib.redirect_stdout(stdout_buf), contextlib.redirect_stderr(stderr_buf):
                try:
                    rc = mod.main([command] + list(args_list)) or 0
                except SystemExit as e:
                    rc = e.code if isinstance(e.code, int) else 1
                except Exception as e:
                    stderr_buf.write(f"Error: {e}\n")
                    stderr_buf.write(traceback.format_exc())
                    rc = 1
        finally:
            os.chdir(cwd_before)
        after = {p.name for p in WORKSPACE.iterdir() if p.is_file()}
        after_dirs = {p.name for p in WORKSPACE.iterdir() if p.is_dir()}
        new_files = sorted(after - before)
        new_dirs = sorted(after_dirs - before_dirs)

    return {
        "rc": rc,
        "stdout": stdout_buf.getvalue(),
        "stderr": stderr_buf.getvalue(),
        "new_files": new_files,
        "new_dirs": new_dirs,
    }


# ============================================================ async jobs (SSE)

class Job:
    def __init__(self, category: str, command: str, args: list[str]):
        self.id = uuid.uuid4().hex[:12]
        self.category = category
        self.command = command
        self.args = args
        self.state = "queued"  # queued | running | done | error | cancelled
        self.rc: int | None = None
        self.stdout = ""
        self.stderr = ""
        self.new_files: list[str] = []
        self.new_dirs: list[str] = []
        self.started_at: float | None = None
        self.finished_at: float | None = None
        self.events: queue.Queue = queue.Queue()  # SSE event stream
        self._cancel = threading.Event()

    def snapshot(self) -> dict:
        return {
            "id": self.id,
            "category": self.category,
            "command": self.command,
            "args": self.args,
            "state": self.state,
            "rc": self.rc,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "new_files": self.new_files,
            "new_dirs": self.new_dirs,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }


_jobs: dict[str, Job] = {}
_jobs_lock = threading.Lock()


def _job_emit(job: Job, kind: str, data):
    job.events.put({"event": kind, "data": data})


def _run_job(job: Job):
    job.state = "running"
    job.started_at = time.time()
    _job_emit(job, "state", {"state": "running"})

    cats = get_categories()
    info = cats.get(job.category)
    if not info:
        job.state = "error"
        job.rc = 1
        job.stderr = "unknown category"
        job.finished_at = time.time()
        _job_emit(job, "done", job.snapshot())
        return

    try:
        mod = importlib.import_module(info["module"])
    except Exception as e:
        job.state = "error"
        job.rc = 1
        job.stderr = f"Could not import {info['module']}: {e}"
        job.finished_at = time.time()
        _job_emit(job, "done", job.snapshot())
        return

    class _StreamSink(io.StringIO):
        def __init__(self, kind: str):
            super().__init__()
            self.kind = kind
            self._lock = threading.Lock()
        def write(self, s):
            if not s:
                return 0
            with self._lock:
                n = super().write(s)
            _job_emit(job, self.kind, s)
            return n

    out_sink = _StreamSink("stdout")
    err_sink = _StreamSink("stderr")
    before = {p.name for p in WORKSPACE.iterdir() if p.is_file()}
    before_dirs = {p.name for p in WORKSPACE.iterdir() if p.is_dir()}
    cwd_before = os.getcwd()
    rc = 0
    try:
        os.chdir(WORKSPACE)
        with contextlib.redirect_stdout(out_sink), contextlib.redirect_stderr(err_sink):
            try:
                rc = mod.main([job.command] + list(job.args)) or 0
            except SystemExit as e:
                rc = e.code if isinstance(e.code, int) else 1
            except Exception as e:
                err_sink.write(f"Error: {e}\n")
                err_sink.write(traceback.format_exc())
                rc = 1
    finally:
        os.chdir(cwd_before)

    job.stdout = out_sink.getvalue()
    job.stderr = err_sink.getvalue()
    job.rc = rc
    after = {p.name for p in WORKSPACE.iterdir() if p.is_file()}
    after_dirs = {p.name for p in WORKSPACE.iterdir() if p.is_dir()}
    job.new_files = sorted(after - before)
    job.new_dirs = sorted(after_dirs - before_dirs)
    job.state = "done" if rc == 0 else "error"
    job.finished_at = time.time()
    _job_emit(job, "done", job.snapshot())


def start_async_job(category: str, command: str, args: list[str]) -> Job:
    job = Job(category, command, args)
    with _jobs_lock:
        _jobs[job.id] = job
        # Trim old jobs (>50).
        if len(_jobs) > 50:
            for old_id in sorted(_jobs, key=lambda i: _jobs[i].started_at or 0)[: len(_jobs) - 50]:
                _jobs.pop(old_id, None)
    threading.Thread(target=_run_job, args=(job,), daemon=True).start()
    return job


# -- Recipe (pipeline) job: runs a recipe and emits per-node SSE events ----------

def start_recipe_job(recipe: dict, variables: dict) -> Job:
    job = Job("recipes", "run", [recipe.get("name", "_inline")])
    job.state = "queued"
    with _jobs_lock:
        _jobs[job.id] = job

    def _run():
        job.state = "running"
        job.started_at = time.time()
        _job_emit(job, "state", {"state": "running"})

        def emit(kind, payload):
            _job_emit(job, kind, payload)

        try:
            import recipes_tools
            result = recipes_tools.run_recipe(recipe, variables, emit_event=emit)
            job.rc = 0 if result.get("ok") else 1
            job.stdout = json.dumps(result, default=str)
            job.state = "done" if result.get("ok") else "error"
        except Exception as e:
            job.rc = 1
            job.stderr = f"{e}\n{traceback.format_exc()}"
            job.state = "error"
        job.finished_at = time.time()
        _job_emit(job, "done", job.snapshot())

    threading.Thread(target=_run, daemon=True).start()
    return job


# -- AI assistant: proxy chat to ollama with a tool-aware system prompt ----------

def _ai_chat(req: dict) -> dict:
    """POST {messages: [{role, content}]} → forward to ollama /api/chat."""
    from _common import load_config
    cfg = load_config()
    host = req.get("host") or cfg.get("ollama_host", "http://localhost:11434")
    model = req.get("model") or cfg.get("ollama_model", "llama3.2")
    user_msgs = req.get("messages", [])

    # System prompt: enumerate available tools so model can suggest [[run cat:cmd args]].
    cats_summary = []
    for cat, info in list(get_categories().items())[:40]:
        cmds = list_commands(cat)
        names = ", ".join(c["name"] for c in cmds if "name" in c)[:200]
        cats_summary.append(f"- {cat}: {names}")
    system = (
        "You are an assistant inside the tk personal toolkit. Reply concisely. "
        "When a user request maps to an available tool, suggest it inline with "
        "the format [[run cat:cmd arg1=val1 arg2=val2]] so the UI can offer a Run button. "
        "Available categories and commands:\n" + "\n".join(cats_summary)
    )
    messages = [{"role": "system", "content": system}] + user_msgs

    body = json.dumps({"model": model, "messages": messages, "stream": False}).encode("utf-8")
    import urllib.request
    try:
        rq = urllib.request.Request(
            host.rstrip("/") + "/api/chat",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(rq, timeout=60) as r:
            data = json.loads(r.read().decode("utf-8"))
        # Ollama: {"message": {"role": "assistant", "content": "..."}}
        content = (data.get("message") or {}).get("content", "")
        return {"role": "assistant", "content": content, "model": model}
    except Exception as e:
        return {
            "role": "assistant",
            "content": (
                f"(AI backend not reachable: {e})\n\nTo enable: install ollama "
                f"from https://ollama.com and run `ollama pull {model}`."
            ),
            "error": str(e),
        }


# ============================================================ workspace helpers

def list_workspace_files():
    files = []
    for p in sorted(WORKSPACE.iterdir(), key=lambda x: x.name.lower()):
        if p.is_file():
            files.append({"name": p.name, "size": p.stat().st_size, "kind": "file", "mtime": p.stat().st_mtime})
        elif p.is_dir():
            count = sum(1 for _ in p.rglob("*") if _.is_file())
            files.append({"name": p.name, "size": count, "kind": "dir", "mtime": p.stat().st_mtime})
    return files


def parse_multipart(body: bytes, boundary: str):
    boundary_bytes = ("--" + boundary).encode()
    parts = body.split(boundary_bytes)
    files_out = {}
    fields = {}
    for part in parts[1:-1]:
        if part.startswith(b"\r\n"):
            part = part[2:]
        if part.endswith(b"\r\n"):
            part = part[:-2]
        if not part:
            continue
        sep = part.find(b"\r\n\r\n")
        if sep == -1:
            continue
        headers = part[:sep].decode("utf-8", errors="ignore")
        content = part[sep + 4:]
        m = re.search(r'name="([^"]+)"(?:; filename="([^"]*)")?', headers)
        if not m:
            continue
        name = m.group(1)
        filename = m.group(2)
        if filename:
            files_out.setdefault(name, []).append((filename, content))
        else:
            fields[name] = content.decode("utf-8", errors="replace")
    return fields, files_out


def safe_target(name: str) -> Path:
    safe = Path(name).name
    safe = re.sub(r"[^\w.\-]+", "_", safe) or "file"
    target = WORKSPACE / safe
    if target.exists():
        stem = target.stem
        suffix = target.suffix
        i = 1
        while target.exists():
            target = WORKSPACE / f"{stem}_{i}{suffix}"
            i += 1
    return target


# ============================================================ themes (bundled)

THEMES = [
    {"id": "dark",      "name": "Dark"},
    {"id": "light",     "name": "Light"},
    {"id": "oled",      "name": "OLED Black"},
    {"id": "dracula",   "name": "Dracula"},
    {"id": "catppuccin","name": "Catppuccin"},
    {"id": "solarized", "name": "Solarized"},
    {"id": "nord",      "name": "Nord"},
    {"id": "gruvbox",   "name": "Gruvbox"},
    {"id": "system",    "name": "Match system"},
]


# ============================================================ HTTP handler

class APIHandler(http.server.BaseHTTPRequestHandler):
    server_version = "tk/0.2"

    def log_message(self, fmt, *args):
        pass

    # ---------- response helpers ----------
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _send_json(self, data, status=200):
        body = json.dumps(data, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path, download_name: str | None = None):
        if not path.exists() or not path.is_file():
            self.send_error(404)
            return
        ctype, _ = mimetypes.guess_type(str(path))
        ctype = ctype or "application/octet-stream"
        try:
            data = path.read_bytes()
        except OSError:
            self.send_error(500)
            return
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        if download_name:
            self.send_header("Content-Disposition", f'attachment; filename="{download_name}"')
        self._cors()
        self.end_headers()
        self.wfile.write(data)

    # ---------- OPTIONS ----------
    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    # ---------- GET ----------
    def do_GET(self):
        url = urllib.parse.urlsplit(self.path)
        path = url.path
        qs = urllib.parse.parse_qs(url.query)

        if path in ("/", "/index.html"):
            self._send_file(WEB / "index.html")
            return
        if path.startswith("/static/"):
            self._send_file(WEB / path[len("/static/"):])
            return

        if path == "/api/version":
            self._send_json({"version": getattr(_tk, "__version__", "0.0.0")})
            return

        if path == "/api/openapi.json":
            self._send_json(self._openapi_spec())
            return

        if path == "/api/themes":
            self._send_json({"themes": THEMES})
            return

        if path == "/api/categories":
            cats_out = []
            for key, info in get_categories().items():
                cats_out.append({
                    "key": key,
                    "label": info["label"],
                    "icon": info["icon"],
                    "module": info["module"],
                    "commands": list_commands(key),
                })
            self._send_json({"categories": cats_out})
            return

        if path.startswith("/api/schema/"):
            rest = path[len("/api/schema/"):].split("/")
            if len(rest) == 2:
                schema = get_command_schema(rest[0], rest[1])
                if schema is None:
                    self._send_json({"error": "command not found"}, 404)
                else:
                    self._send_json({"args": schema})
                return
            self._send_json({"error": "bad request"}, 400)
            return

        if path == "/api/files":
            self._send_json({"files": list_workspace_files()})
            return

        if path.startswith("/api/files/"):
            name = urllib.parse.unquote(path[len("/api/files/"):])
            if ".." in name or name.startswith("/") or name.startswith("\\"):
                self.send_error(400)
                return
            target = WORKSPACE / name
            if target.is_file():
                self._send_file(target, download_name=Path(name).name)
                return
            self.send_error(404)
            return

        if path == "/api/jobs":
            with _jobs_lock:
                snap = [j.snapshot() for j in _jobs.values()]
            self._send_json({"jobs": snap})
            return

        if path.startswith("/api/jobs/") and path.endswith("/events"):
            jid = path[len("/api/jobs/"):-len("/events")]
            job = _jobs.get(jid)
            if not job:
                self.send_error(404)
                return
            self._stream_job_events(job)
            return

        if path.startswith("/api/jobs/"):
            jid = path[len("/api/jobs/"):]
            job = _jobs.get(jid)
            if not job:
                self._send_json({"error": "job not found"}, 404)
                return
            self._send_json(job.snapshot())
            return

        if path == "/api/presets":
            from _common import preset_list
            self._send_json({"presets": preset_list()})
            return

        if path == "/api/recipes":
            from _common import recipe_list
            self._send_json({"recipes": recipe_list()})
            return

        if path.startswith("/api/recipes/"):
            from _common import recipe_load
            name = urllib.parse.unquote(path[len("/api/recipes/"):])
            r = recipe_load(name)
            if not r:
                self._send_json({"error": "not found"}, 404)
            else:
                self._send_json(r)
            return

        if path == "/api/hooks":
            from _common import hook_list
            self._send_json({"hooks": hook_list()})
            return

        if path == "/api/history":
            from _common import recent_runs
            try:
                limit = int(qs.get("limit", ["50"])[0])
            except ValueError:
                limit = 50
            self._send_json({"runs": recent_runs(limit)})
            return

        if path == "/api/doctor":
            self._send_json(self._doctor_report())
            return

        if path == "/api/config":
            from _common import load_config
            self._send_json({"config": load_config()})
            return

        # Static fallback under web/
        candidate = WEB / path.lstrip("/")
        if candidate.exists() and candidate.is_file():
            self._send_file(candidate)
            return
        self.send_error(404)

    def _stream_job_events(self, job: Job):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self._cors()
        self.end_headers()
        # Initial state snapshot.
        try:
            self._sse_send("snapshot", job.snapshot())
            # Drain pending events until job done.
            while True:
                try:
                    evt = job.events.get(timeout=15.0)
                except queue.Empty:
                    self._sse_send("ping", {"t": time.time()})
                    if job.state in ("done", "error", "cancelled") and job.events.empty():
                        break
                    continue
                self._sse_send(evt["event"], evt["data"])
                if evt["event"] == "done":
                    break
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _sse_send(self, kind: str, data):
        try:
            payload = data if isinstance(data, str) else json.dumps(data, default=str)
            chunk = f"event: {kind}\ndata: {payload}\n\n".encode("utf-8")
            self.wfile.write(chunk)
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            raise

    def _openapi_spec(self):
        """Auto-generate OpenAPI 3.1 spec for every category/command."""
        paths = {
            "/api/categories": {"get": {"summary": "List categories + commands", "responses": {"200": {"description": "ok"}}}},
            "/api/files":      {"get": {"summary": "List workspace files", "responses": {"200": {"description": "ok"}}}},
            "/api/jobs":       {"get": {"summary": "List jobs", "responses": {"200": {"description": "ok"}}}},
            "/api/history":    {"get": {"summary": "Recent runs", "responses": {"200": {"description": "ok"}}}},
            "/api/doctor":     {"get": {"summary": "Environment report", "responses": {"200": {"description": "ok"}}}},
            "/api/themes":     {"get": {"summary": "Theme list", "responses": {"200": {"description": "ok"}}}},
            "/api/presets":    {
                "get":  {"summary": "List presets", "responses": {"200": {"description": "ok"}}},
                "post": {"summary": "Save preset", "responses": {"200": {"description": "ok"}}},
            },
            "/api/run":        {"post": {"summary": "Run tool synchronously", "responses": {"200": {"description": "ok"}}}},
            "/api/run-async":  {"post": {"summary": "Start a background job",  "responses": {"200": {"description": "ok"}}}},
            "/api/batch":      {"post": {"summary": "Run a tool over many files", "responses": {"200": {"description": "ok"}}}},
            "/api/upload":     {"post": {"summary": "Upload files (multipart)", "responses": {"200": {"description": "ok"}}}},
        }
        # Per-tool endpoints (synthetic) for discoverability:
        for cat, info in get_categories().items():
            for c in list_commands(cat):
                if "error" in c:
                    continue
                cmd = c["name"]
                schema = get_command_schema(cat, cmd) or []
                path = f"/api/run#{cat}.{cmd}"
                props = {}
                for a in schema:
                    t = {"int": "integer", "float": "number", "bool": "boolean"}.get(a["type"], "string")
                    props[a["name"]] = {"type": t, "description": a["help"]}
                paths[path] = {
                    "post": {
                        "summary": f"{cat} {cmd} — {c['help']}",
                        "tags": [cat],
                        "requestBody": {"content": {"application/json": {"schema": {"type": "object", "properties": props}}}},
                        "responses": {"200": {"description": "tool output"}},
                    }
                }
        return {
            "openapi": "3.1.0",
            "info": {
                "title": "tk Toolkit API",
                "version": getattr(_tk, "__version__", "0.0.0"),
                "description": "Auto-generated from every category + command.",
            },
            "servers": [{"url": "/"}],
            "paths": paths,
        }

    def _doctor_report(self):
        from _common import have_module, have_binary
        mods = [
            "pypdf", "PIL", "reportlab", "markdown", "openpyxl", "yaml", "tomli",
            "cryptography", "requests", "dns", "jwt", "qrcode", "pyzbar", "librosa",
            "rembg", "cv2", "onnxruntime", "sentence_transformers", "faster_whisper",
            "serial", "croniter", "dateutil", "camelot", "ocrmypdf", "pytesseract",
            "mnemonic", "argon2", "piexif", "mutagen",
        ]
        bins = ["ffmpeg", "ffprobe", "pandoc", "tesseract", "gpg", "age", "qpdf"]
        return {
            "python":   sys.version.split()[0],
            "platform": sys.platform,
            "modules":  {m: have_module(m) for m in mods},
            "binaries": {b: have_binary(b) for b in bins},
        }

    # ---------- DELETE ----------
    def do_DELETE(self):
        url = urllib.parse.urlsplit(self.path)
        path = url.path
        if path.startswith("/api/files/"):
            name = urllib.parse.unquote(path[len("/api/files/"):])
            if ".." in name:
                self.send_error(400)
                return
            target = WORKSPACE / name
            if target.is_file():
                target.unlink()
                self._send_json({"ok": True})
            elif target.is_dir():
                shutil.rmtree(target)
                self._send_json({"ok": True})
            else:
                self.send_error(404)
            return
        if path == "/api/clear":
            for p in WORKSPACE.iterdir():
                if p.is_file():
                    p.unlink()
                elif p.is_dir():
                    shutil.rmtree(p, ignore_errors=True)
            self._send_json({"ok": True})
            return
        if path.startswith("/api/jobs/"):
            jid = path[len("/api/jobs/"):]
            job = _jobs.pop(jid, None)
            if job:
                self._send_json({"ok": True})
            else:
                self._send_json({"error": "not found"}, 404)
            return
        if path.startswith("/api/presets/"):
            from _common import preset_delete
            name = urllib.parse.unquote(path[len("/api/presets/"):])
            ok = preset_delete(name)
            self._send_json({"ok": ok})
            return
        if path.startswith("/api/recipes/"):
            from _common import recipe_delete
            name = urllib.parse.unquote(path[len("/api/recipes/"):])
            ok = recipe_delete(name)
            self._send_json({"ok": ok})
            return
        if path.startswith("/api/hooks/"):
            from _common import hook_delete
            name = urllib.parse.unquote(path[len("/api/hooks/"):])
            ok = hook_delete(name)
            self._send_json({"ok": ok})
            return
        self.send_error(404)

    # ---------- POST ----------
    def do_POST(self):
        url = urllib.parse.urlsplit(self.path)
        path = url.path
        try:
            length = int(self.headers.get("Content-Length", 0))
        except ValueError:
            length = 0
        body = self.rfile.read(length) if length else b""

        if path == "/api/run":
            req = self._json(body)
            if req is None:
                return
            cat = req.get("category"); cmd = req.get("command"); args = req.get("args", [])
            if cat not in get_categories():
                self._send_json({"error": "unknown category"}, 400); return
            if not isinstance(args, list):
                self._send_json({"error": "args must be a list"}, 400); return
            self._send_json(run_tool(cat, cmd, [str(a) for a in args]))
            return

        if path == "/api/run-async":
            req = self._json(body)
            if req is None:
                return
            cat = req.get("category"); cmd = req.get("command"); args = req.get("args", [])
            if cat not in get_categories():
                self._send_json({"error": "unknown category"}, 400); return
            if not isinstance(args, list):
                self._send_json({"error": "args must be a list"}, 400); return
            job = start_async_job(cat, cmd, [str(a) for a in args])
            self._send_json({"id": job.id, "state": job.state})
            return

        if path == "/api/batch":
            # Run a command across many input files. Body:
            # {category, command, args, file_arg: "input", files: ["a.png", "b.png"]}
            req = self._json(body)
            if req is None:
                return
            cat = req.get("category"); cmd = req.get("command")
            base_args = req.get("args", []) or []
            file_arg = req.get("file_arg", "input")
            files = req.get("files", [])
            results = []
            for fname in files:
                # Find the placeholder in args.
                this_args = []
                substituted = False
                for a in base_args:
                    if a == "{file}" or a == f"${file_arg}":
                        this_args.append(fname)
                        substituted = True
                    else:
                        this_args.append(a)
                if not substituted:
                    this_args = [fname] + list(base_args)
                results.append({"file": fname, "result": run_tool(cat, cmd, [str(a) for a in this_args])})
            self._send_json({"results": results})
            return

        if path == "/api/upload":
            ctype = self.headers.get("Content-Type", "")
            if "multipart/form-data" not in ctype:
                self._send_json({"error": "expected multipart/form-data"}, 400); return
            m = re.search(r"boundary=([^;]+)", ctype)
            if not m:
                self._send_json({"error": "no boundary"}, 400); return
            boundary = m.group(1).strip().strip('"')
            _, files = parse_multipart(body, boundary)
            saved = []
            for _, file_list in files.items():
                for filename, content in file_list:
                    target = safe_target(filename)
                    target.write_bytes(content)
                    saved.append({"name": target.name, "size": len(content)})
            self._send_json({"files": saved})
            return

        if path == "/api/clear":
            for p in WORKSPACE.iterdir():
                if p.is_file():
                    p.unlink()
                elif p.is_dir():
                    shutil.rmtree(p, ignore_errors=True)
            self._send_json({"ok": True})
            return

        if path == "/api/presets":
            from _common import preset_save
            req = self._json(body)
            if req is None:
                return
            try:
                p = preset_save(req["name"], req["category"], req["command"], req.get("args", []))
                self._send_json({"ok": True, "path": str(p)})
            except KeyError as e:
                self._send_json({"error": f"missing field: {e}"}, 400)
            return

        if path == "/api/recipes":
            from _common import recipe_save
            req = self._json(body)
            if req is None:
                return
            try:
                p = recipe_save(req["name"], req.get("recipe", req))
                self._send_json({"ok": True, "path": str(p)})
            except KeyError as e:
                self._send_json({"error": f"missing field: {e}"}, 400)
            return

        if path == "/api/recipes/run":
            req = self._json(body)
            if req is None:
                return
            from _common import recipe_load
            if "recipe" in req:
                recipe = req["recipe"]
            elif "name" in req:
                recipe = recipe_load(req["name"])
                if not recipe:
                    self._send_json({"error": "recipe not found"}, 404); return
            else:
                self._send_json({"error": "need 'recipe' or 'name'"}, 400); return
            variables = req.get("vars", {}) or {}
            job = start_recipe_job(recipe, variables)
            self._send_json({"id": job.id, "state": job.state})
            return

        if path == "/api/hooks":
            from _common import hook_save
            req = self._json(body)
            if req is None:
                return
            try:
                hook = hook_save(req["name"], req["recipe"], req.get("token"))
                self._send_json({"ok": True, "hook": hook})
            except KeyError as e:
                self._send_json({"error": f"missing field: {e}"}, 400)
            return

        if path.startswith("/api/hook/"):
            # Webhook trigger: POST /api/hook/<token>  body = {vars: {...}}
            from _common import hook_by_token, recipe_load
            token = urllib.parse.unquote(path[len("/api/hook/"):])
            hook = hook_by_token(token)
            if not hook:
                self._send_json({"error": "unknown token"}, 404); return
            recipe = recipe_load(hook["recipe"])
            if not recipe:
                self._send_json({"error": f"recipe '{hook['recipe']}' missing"}, 500); return
            req = self._json(body) or {}
            variables = req.get("vars", {}) or {}
            job = start_recipe_job(recipe, variables)
            self._send_json({"ok": True, "job_id": job.id, "recipe": hook["recipe"]})
            return

        if path == "/api/ai/chat":
            req = self._json(body)
            if req is None:
                return
            self._send_json(_ai_chat(req))
            return

        if path == "/api/config":
            from _common import save_config, load_config
            req = self._json(body)
            if req is None:
                return
            cfg = load_config(); cfg.update(req or {}); save_config(cfg)
            self._send_json({"ok": True, "config": cfg})
            return

        self.send_error(404)

    def _json(self, body: bytes):
        try:
            return json.loads(body.decode("utf-8") or "{}")
        except Exception as e:
            self._send_json({"error": f"bad JSON: {e}"}, 400)
            return None


class ThreadedServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def serve(host="127.0.0.1", port=8765, open_browser=True):
    server = ThreadedServer((host, port), APIHandler)
    url = f"http://{host}:{port}/"
    print()
    print(f"  tk web UI running at  {url}")
    print(f"  Workspace dir:        {WORKSPACE}")
    print(f"  Categories loaded:    {len(get_categories())}")
    print("  Press Ctrl+C to stop.")
    print()
    if open_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Stopped.")
        server.shutdown()


def main(argv=None):
    from _common import load_config
    cfg = load_config()
    parser = argparse.ArgumentParser(prog="server", description="Web UI for the tk toolkit")
    parser.add_argument("--host", default=cfg.get("server_host", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=cfg.get("server_port", 8765))
    parser.add_argument("--no-browser", action="store_true", help="don't auto-open the browser")
    args = parser.parse_args(argv)
    serve(args.host, args.port, open_browser=not args.no_browser)


if __name__ == "__main__":
    main()
