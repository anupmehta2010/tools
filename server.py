"""Web UI server for the toolkit. Pure stdlib HTTP server (no Flask/FastAPI required).

Run:
    python server.py             # http://127.0.0.1:8765/
    python server.py --port 9000
    python server.py --host 0.0.0.0 --no-browser

Or via the launcher:
    python tk.py ui
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
import re
import socketserver
import sys
import threading
import traceback
import urllib.parse
import webbrowser
from pathlib import Path

import argparse as _ap

ROOT = Path(__file__).parent
WEB = ROOT / "web"
WORKSPACE = ROOT / "web_workspace"
WORKSPACE.mkdir(exist_ok=True)

sys.path.insert(0, str(ROOT))


CATEGORIES = {
    "pdf":     {"module": "pdf_tools",     "label": "PDF",                "icon": "📄"},
    "image":   {"module": "image_tools",   "label": "Image",              "icon": "🖼️"},
    "media":   {"module": "media_tools",   "label": "Audio / Video",      "icon": "🎬"},
    "text":    {"module": "text_tools",    "label": "Text & Encoding",    "icon": "✍️"},
    "data":    {"module": "data_tools",    "label": "Data Conversion",    "icon": "📊"},
    "archive": {"module": "archive_tools", "label": "Archives",           "icon": "📦"},
    "crypto":  {"module": "crypto_tools",  "label": "Crypto & Security",  "icon": "🔐"},
    "net":     {"module": "net_tools",     "label": "Network",            "icon": "🌐"},
    "fs":      {"module": "fs_tools",      "label": "Filesystem",         "icon": "📁"},
    "dev":     {"module": "dev_tools",     "label": "Dev Utilities",      "icon": "⚙️"},
    "qr":      {"module": "qr_tools",      "label": "QR Codes",           "icon": "📱"},
    "oled":    {"module": "oled_tools",    "label": "OLED & Embedded",    "icon": "💡"},
    "convert": {"module": "convert_tools", "label": "Universal Convert",   "icon": "🔄"},
}

_run_lock = threading.Lock()


# ------------------------------- Schema introspection ----------------------------

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
        if positional and action.dest in {"input", "inputs", "a", "b", "src", "sources"}:
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
    info = CATEGORIES.get(category)
    if not info:
        return None
    try:
        mod = importlib.import_module(info["module"])
    except Exception:
        return None
    parser = mod.build_parser()
    for action in parser._actions:
        if isinstance(action, _ap._SubParsersAction):
            sub = action.choices.get(command)
            if sub:
                return _parser_to_schema(sub)
    return None


def list_commands(category):
    info = CATEGORIES.get(category)
    if not info:
        return []
    try:
        mod = importlib.import_module(info["module"])
    except Exception as e:
        return [{"error": str(e)}]
    cmds = getattr(mod, "COMMANDS", {})
    return [{"name": k, "help": v} for k, v in cmds.items()]


# --------------------------------- Tool runner -----------------------------------

def run_tool(category, command, args_list):
    info = CATEGORIES.get(category)
    if not info:
        return {"rc": 1, "stdout": "", "stderr": "unknown category", "new_files": []}
    try:
        mod = importlib.import_module(info["module"])
    except Exception as e:
        return {"rc": 1, "stdout": "", "stderr": f"Could not import {info['module']}: {e}", "new_files": []}

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


def list_workspace_files():
    files = []
    for p in sorted(WORKSPACE.iterdir(), key=lambda x: x.name.lower()):
        if p.is_file():
            files.append({"name": p.name, "size": p.stat().st_size, "kind": "file"})
        elif p.is_dir():
            count = sum(1 for _ in p.rglob("*") if _.is_file())
            files.append({"name": p.name, "size": count, "kind": "dir"})
    return files


# --------------------------------- Multipart -------------------------------------

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


# --------------------------------- HTTP handler ----------------------------------

class APIHandler(http.server.BaseHTTPRequestHandler):
    server_version = "tk/1.0"

    def log_message(self, fmt, *args):
        pass  # silent

    def _send_json(self, data, status=200):
        body = json.dumps(data, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
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
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        url = urllib.parse.urlsplit(self.path)
        path = url.path

        if path == "/" or path == "/index.html":
            self._send_file(WEB / "index.html")
            return
        if path.startswith("/static/"):
            rel = path[len("/static/"):]
            self._send_file(WEB / rel)
            return
        if path == "/api/categories":
            cats = []
            for key, info in CATEGORIES.items():
                cats.append({
                    "key": key,
                    "label": info["label"],
                    "icon": info["icon"],
                    "module": info["module"],
                    "commands": list_commands(key),
                })
            self._send_json({"categories": cats})
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

        # Try static fallback under web/
        candidate = WEB / path.lstrip("/")
        if candidate.exists() and candidate.is_file():
            self._send_file(candidate)
            return
        self.send_error(404)

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
                import shutil
                shutil.rmtree(target)
                self._send_json({"ok": True})
            else:
                self.send_error(404)
            return
        if path == "/api/clear":
            import shutil
            for p in WORKSPACE.iterdir():
                if p.is_file():
                    p.unlink()
                elif p.is_dir():
                    shutil.rmtree(p, ignore_errors=True)
            self._send_json({"ok": True})
            return
        self.send_error(404)

    def do_POST(self):
        url = urllib.parse.urlsplit(self.path)
        path = url.path
        try:
            length = int(self.headers.get("Content-Length", 0))
        except ValueError:
            length = 0
        body = self.rfile.read(length) if length else b""

        if path == "/api/run":
            try:
                req = json.loads(body.decode("utf-8") or "{}")
            except Exception as e:
                self._send_json({"error": f"bad JSON: {e}"}, 400)
                return
            cat = req.get("category")
            cmd = req.get("command")
            args = req.get("args", [])
            if cat not in CATEGORIES:
                self._send_json({"error": "unknown category"}, 400)
                return
            if not isinstance(args, list):
                self._send_json({"error": "args must be a list"}, 400)
                return
            args = [str(a) for a in args]
            result = run_tool(cat, cmd, args)
            self._send_json(result)
            return

        if path == "/api/upload":
            ctype = self.headers.get("Content-Type", "")
            if "multipart/form-data" not in ctype:
                self._send_json({"error": "expected multipart/form-data"}, 400)
                return
            m = re.search(r"boundary=([^;]+)", ctype)
            if not m:
                self._send_json({"error": "no boundary"}, 400)
                return
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
            import shutil
            for p in WORKSPACE.iterdir():
                if p.is_file():
                    p.unlink()
                elif p.is_dir():
                    shutil.rmtree(p, ignore_errors=True)
            self._send_json({"ok": True})
            return

        self.send_error(404)


class ThreadedServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def serve(host="127.0.0.1", port=8765, open_browser=True):
    server = ThreadedServer((host, port), APIHandler)
    url = f"http://{host}:{port}/"
    print()
    print(f"  tk web UI running at  {url}")
    print(f"  Workspace dir:        {WORKSPACE}")
    print(f"  Press Ctrl+C to stop.")
    print()
    if open_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Stopped.")
        server.shutdown()


def main(argv=None):
    parser = argparse.ArgumentParser(prog="server", description="Web UI for the tk toolkit")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true", help="don't auto-open the browser")
    args = parser.parse_args(argv)
    serve(args.host, args.port, open_browser=not args.no_browser)


if __name__ == "__main__":
    main()
