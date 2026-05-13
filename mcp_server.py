"""MCP (Model Context Protocol) stdio server.

Exposes every tk category/command as an MCP tool so Claude / Cursor / Cline / any
MCP-aware client can call them directly.

Usage from an MCP client config (e.g., Claude Desktop):
    {
      "mcpServers": {
        "tk": {
          "command": "python",
          "args": ["c:/path/to/tools/mcp_server.py"]
        }
      }
    }

Protocol implemented (subset of MCP 2024-11-05):
- initialize
- tools/list
- tools/call
- resources/list   (workspace files)
- resources/read

Speaks JSON-RPC 2.0 over stdio. One JSON object per line.
"""
from __future__ import annotations

import argparse
import argparse as _ap
import contextlib
import importlib
import io
import json
import os
import sys
import threading
import traceback
from pathlib import Path

ROOT = Path(__file__).parent
WORKSPACE = ROOT / "web_workspace"
WORKSPACE.mkdir(exist_ok=True)
sys.path.insert(0, str(ROOT))


def _build_categories() -> dict[str, dict]:
    try:
        import tk
    except Exception:
        return {}
    cats = tk.available_categories() if hasattr(tk, "available_categories") else tk.CATEGORIES
    out = {}
    for key, val in cats.items():
        if isinstance(val, tuple):
            module, label = val[0], val[1] if len(val) > 1 else key
            icon = val[2] if len(val) > 2 else "🔧"
        elif isinstance(val, dict):
            module = val.get("module")
            label = val.get("label", key)
            icon = val.get("icon", "🔧")
        else:
            continue
        out[key] = {"module": module, "label": label, "icon": icon}
    return out


# ----------------------------------------------- argparse → JSON schema

def _argparse_to_json_schema(parser) -> dict:
    """Convert a subparser to JSON Schema for MCP tools/list."""
    props: dict[str, dict] = {}
    required: list[str] = []
    for action in parser._actions:
        if isinstance(action, (_ap._HelpAction, _ap._SubParsersAction)):
            continue
        name = action.dest
        positional = not action.option_strings

        if action.type is int:
            t = "integer"
        elif action.type is float:
            t = "number"
        elif isinstance(action, (_ap._StoreTrueAction, _ap._StoreFalseAction)):
            t = "boolean"
        else:
            t = "string"

        prop: dict = {"description": action.help or ""}
        if isinstance(action.nargs, (str, int)) and action.nargs not in ("?",) and action.nargs != 0:
            prop["type"] = "array"
            prop["items"] = {"type": t}
        else:
            prop["type"] = t
        if action.choices:
            prop["enum"] = list(action.choices)
        if action.default not in (None, _ap.SUPPRESS):
            try:
                json.dumps(action.default)
                prop["default"] = action.default
            except TypeError:
                pass
        if action.option_strings:
            prop["x-flags"] = list(action.option_strings)
        if positional:
            prop["x-positional"] = True
        props[name] = prop
        if positional or getattr(action, "required", False):
            required.append(name)
    return {"type": "object", "properties": props, "required": required}


def _build_argv_from_args(parser, args_dict: dict) -> list[str]:
    """Reverse: turn a JSON args dict into argparse CLI argv."""
    argv: list[str] = []
    # First positionals (in argparse order).
    for action in parser._actions:
        if isinstance(action, (_ap._HelpAction, _ap._SubParsersAction)):
            continue
        if action.option_strings:
            continue
        name = action.dest
        if name not in args_dict:
            continue
        v = args_dict[name]
        if isinstance(v, list):
            argv.extend(str(x) for x in v)
        else:
            argv.append(str(v))
    # Then flags.
    for action in parser._actions:
        if isinstance(action, (_ap._HelpAction, _ap._SubParsersAction)):
            continue
        if not action.option_strings:
            continue
        name = action.dest
        if name not in args_dict:
            continue
        flag = action.option_strings[0]
        v = args_dict[name]
        if isinstance(action, _ap._StoreTrueAction):
            if v:
                argv.append(flag)
        elif isinstance(action, _ap._StoreFalseAction):
            if not v:
                argv.append(flag)
        elif isinstance(v, list):
            argv.append(flag)
            argv.extend(str(x) for x in v)
        else:
            argv.append(flag)
            argv.append(str(v))
    return argv


# ----------------------------------------------- tool registry

def list_tools() -> list[dict]:
    tools = []
    for cat, info in _build_categories().items():
        try:
            mod = importlib.import_module(info["module"])
        except Exception:
            continue
        if not hasattr(mod, "build_parser"):
            continue
        try:
            parser = mod.build_parser()
        except Exception:
            continue
        for action in parser._actions:
            if not isinstance(action, _ap._SubParsersAction):
                continue
            for cmd, sub in action.choices.items():
                tool_name = f"tk__{cat}__{cmd}".replace("-", "_").replace(".", "_")
                tools.append({
                    "name": tool_name,
                    "description": f"[{cat}] {sub.description or sub.prog or cmd}",
                    "inputSchema": _argparse_to_json_schema(sub),
                    "_meta": {"category": cat, "command": cmd},
                })
    return tools


# Build lookup so call_tool() is fast.
_TOOL_INDEX: dict[str, tuple[str, str]] = {}


def _refresh_index():
    _TOOL_INDEX.clear()
    for t in list_tools():
        meta = t["_meta"]
        _TOOL_INDEX[t["name"]] = (meta["category"], meta["command"])


_run_lock = threading.Lock()


def call_tool(name: str, args: dict) -> dict:
    if not _TOOL_INDEX:
        _refresh_index()
    if name not in _TOOL_INDEX:
        return {"isError": True, "content": [{"type": "text", "text": f"unknown tool: {name}"}]}
    cat, cmd = _TOOL_INDEX[name]
    cats = _build_categories()
    info = cats.get(cat)
    if not info:
        return {"isError": True, "content": [{"type": "text", "text": f"category {cat} not found"}]}
    try:
        mod = importlib.import_module(info["module"])
    except Exception as e:
        return {"isError": True, "content": [{"type": "text", "text": f"import {info['module']}: {e}"}]}

    # Build CLI argv from json args.
    parser = mod.build_parser()
    sub_parser = None
    for action in parser._actions:
        if isinstance(action, _ap._SubParsersAction):
            sub_parser = action.choices.get(cmd)
            break
    if sub_parser is None:
        return {"isError": True, "content": [{"type": "text", "text": f"sub-command {cmd} not found"}]}

    argv = [cmd] + _build_argv_from_args(sub_parser, args or {})

    with _run_lock:
        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()
        before = {p.name for p in WORKSPACE.iterdir() if p.is_file()}
        cwd_before = os.getcwd()
        rc = 0
        try:
            os.chdir(WORKSPACE)
            with contextlib.redirect_stdout(stdout_buf), contextlib.redirect_stderr(stderr_buf):
                try:
                    rc = mod.main(argv) or 0
                except SystemExit as e:
                    rc = e.code if isinstance(e.code, int) else 1
                except Exception as e:
                    stderr_buf.write(f"Error: {e}\n")
                    stderr_buf.write(traceback.format_exc())
                    rc = 1
        finally:
            os.chdir(cwd_before)
        after = {p.name for p in WORKSPACE.iterdir() if p.is_file()}
        new_files = sorted(after - before)

    content = []
    if stdout_buf.getvalue():
        content.append({"type": "text", "text": stdout_buf.getvalue()})
    if stderr_buf.getvalue():
        content.append({"type": "text", "text": "STDERR:\n" + stderr_buf.getvalue()})
    if new_files:
        content.append({"type": "text", "text": "Created files:\n" + "\n".join(f"- {f}" for f in new_files)})
    if not content:
        content = [{"type": "text", "text": f"(no output; exit code {rc})"}]
    return {"isError": rc != 0, "content": content, "_meta": {"rc": rc, "new_files": new_files}}


# ----------------------------------------------- resources (workspace files)

def list_resources() -> list[dict]:
    out = []
    for p in sorted(WORKSPACE.iterdir()):
        if not p.is_file():
            continue
        out.append({
            "uri": f"workspace://{p.name}",
            "name": p.name,
            "mimeType": _guess_mime(p),
            "description": f"workspace file, {p.stat().st_size} bytes",
        })
    return out


def read_resource(uri: str) -> dict:
    if not uri.startswith("workspace://"):
        return {"contents": [{"uri": uri, "text": "not a workspace URI"}]}
    name = uri[len("workspace://"):]
    target = WORKSPACE / name
    if not target.is_file():
        return {"contents": [{"uri": uri, "text": "not found"}]}
    mime = _guess_mime(target)
    if mime.startswith("text/") or mime in ("application/json", "application/xml"):
        return {"contents": [{"uri": uri, "mimeType": mime, "text": target.read_text(encoding="utf-8", errors="replace")}]}
    import base64
    return {"contents": [{"uri": uri, "mimeType": mime, "blob": base64.b64encode(target.read_bytes()).decode("ascii")}]}


def _guess_mime(p: Path) -> str:
    import mimetypes
    m, _ = mimetypes.guess_type(str(p))
    return m or "application/octet-stream"


# ----------------------------------------------- JSON-RPC plumbing

def _result(rid, data):
    return {"jsonrpc": "2.0", "id": rid, "result": data}


def _error(rid, code, message, data=None):
    err = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return {"jsonrpc": "2.0", "id": rid, "error": err}


def handle(msg: dict) -> dict | None:
    method = msg.get("method")
    rid = msg.get("id")
    params = msg.get("params") or {}

    if method == "initialize":
        try:
            import tk
            ver = getattr(tk, "__version__", "0.0.0")
        except Exception:
            ver = "0.0.0"
        return _result(rid, {
            "protocolVersion": "2024-11-05",
            "serverInfo": {"name": "tk", "version": ver},
            "capabilities": {
                "tools": {"listChanged": False},
                "resources": {"listChanged": False, "subscribe": False},
            },
        })

    if method == "notifications/initialized":
        return None  # no response for notifications

    if method == "tools/list":
        tools = []
        for t in list_tools():
            tools.append({"name": t["name"], "description": t["description"], "inputSchema": t["inputSchema"]})
        _refresh_index()
        return _result(rid, {"tools": tools})

    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        return _result(rid, call_tool(name, args))

    if method == "resources/list":
        return _result(rid, {"resources": list_resources()})

    if method == "resources/read":
        uri = params.get("uri", "")
        return _result(rid, read_resource(uri))

    if method == "ping":
        return _result(rid, {})

    return _error(rid, -32601, f"method not found: {method}")


def serve_stdio():
    """Read one JSON message per line from stdin, write JSON to stdout."""
    for raw in sys.stdin:
        line = raw.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError as e:
            sys.stderr.write(f"[mcp] bad JSON: {e}\n")
            continue
        try:
            resp = handle(msg)
        except Exception as e:
            resp = _error(msg.get("id"), -32603, str(e))
        if resp is not None:
            sys.stdout.write(json.dumps(resp, default=str) + "\n")
            sys.stdout.flush()


def main(argv=None):
    p = argparse.ArgumentParser(prog="mcp_server", description="tk MCP stdio server")
    p.add_argument("--list-tools", action="store_true", help="print tool registry as JSON and exit")
    args = p.parse_args(argv)
    if args.list_tools:
        print(json.dumps(list_tools(), indent=2, default=str))
        return 0
    serve_stdio()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
