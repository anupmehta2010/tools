"""Smoke tests: every module imports cleanly, every parser builds, basic CLI flows work.

Run:
    pip install pytest
    pytest -q
"""
from __future__ import annotations

import importlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


CORE_MODULES = [
    "_common", "convert_tools", "archive_tools", "crypto_tools", "data_tools",
    "dev_tools", "fs_tools", "image_tools", "media_tools", "net_tools",
    "oled_tools", "pdf_tools", "qr_tools", "text_tools",
]

ADVANCED_MODULES = [
    "ai_tools", "audiopro_tools", "code_tools", "cryptopro_tools", "db_tools",
    "doc_tools", "embedded_tools", "finance_tools", "forensic_tools", "gen_tools",
    "geo_tools", "imagepro_tools", "ml_tools", "netpro_tools", "pdfpro_tools",
    "steg_tools", "threed_tools", "time_tools", "videopro_tools", "watch_tools",
    "recipes_tools", "bundle_tools", "completions_tools",
]


def test_core_imports():
    for m in CORE_MODULES:
        importlib.import_module(m)


def test_advanced_imports():
    for m in ADVANCED_MODULES:
        importlib.import_module(m)


def test_tk_imports():
    import tk
    assert tk.__version__
    cats = tk.available_categories()
    assert len(cats) >= 36, f"expected ≥36 categories, got {len(cats)}"


def test_recipe_scaffold_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    sys.modules.pop("_common", None)
    import _common
    importlib.reload(_common)
    rec = {"name": "smoke-r", "steps": [{"id": "n1", "tool": "dev:calc", "argv": ["2+2"]}]}
    _common.recipe_save("smoke-r", rec)
    loaded = _common.recipe_load("smoke-r")
    assert loaded["name"] == "smoke-r"
    assert len(_common.recipe_list()) == 1
    _common.recipe_delete("smoke-r")


def test_bundle_info_runs():
    r = subprocess.run(
        [sys.executable, str(ROOT / "tk.py"), "bundle", "info"],
        capture_output=True, text=True, timeout=60,
    )
    assert r.returncode == 0, r.stderr
    assert "Bundle contents" in r.stdout


def test_server_imports():
    import server
    assert server.get_categories()


def test_mcp_imports():
    import mcp_server
    tools = mcp_server.list_tools()
    assert len(tools) > 100, f"expected ≥100 MCP tools, got {len(tools)}"
    sample = tools[0]
    assert sample["name"].startswith("tk__")
    assert sample["inputSchema"]["type"] == "object"


def test_every_module_builds_parser():
    """Every tool module exposes COMMANDS + build_parser + main."""
    for m in CORE_MODULES + ADVANCED_MODULES:
        mod = importlib.import_module(m)
        if not hasattr(mod, "build_parser"):
            continue
        parser = mod.build_parser()
        assert parser is not None
        assert hasattr(mod, "COMMANDS"), f"{m} missing COMMANDS"
        assert hasattr(mod, "main"), f"{m} missing main"


def test_text_hash_smoke(tmp_path):
    """text hash subcommand actually runs."""
    f = tmp_path / "hi.txt"
    f.write_text("hello world", encoding="utf-8")
    r = subprocess.run(
        [sys.executable, str(ROOT / "tk.py"), "text", "hash", "--algo", "sha256", "-i", str(f)],
        capture_output=True, text=True, timeout=30,
    )
    assert r.returncode == 0, r.stderr
    assert "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9" in r.stdout


def test_dev_calc_smoke():
    r = subprocess.run(
        [sys.executable, str(ROOT / "tk.py"), "dev", "calc", "2 + 2 * 5"],
        capture_output=True, text=True, timeout=30,
    )
    assert r.returncode == 0, r.stderr
    assert "12" in r.stdout


def test_doctor_runs():
    r = subprocess.run(
        [sys.executable, str(ROOT / "tk.py"), "doctor"],
        capture_output=True, text=True, timeout=30,
    )
    assert r.returncode == 0, r.stderr
    assert "Python:" in r.stdout


def test_list_json():
    r = subprocess.run(
        [sys.executable, str(ROOT / "tk.py"), "--json", "list"],
        capture_output=True, text=True, timeout=60,
    )
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert "categories" in data
    assert len(data["categories"]) >= 32


def test_embedded_crc16():
    """CRC-16/CCITT-FALSE check value."""
    r = subprocess.run(
        [sys.executable, str(ROOT / "tk.py"), "embedded", "crc16", "--hex", "313233343536373839"],
        capture_output=True, text=True, timeout=30,
    )
    assert r.returncode == 0, r.stderr
    assert "0x29b1" in r.stdout.lower()


def test_preset_roundtrip(tmp_path, monkeypatch):
    """Save a preset, list it, load it, delete it."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    # Force a fresh _common reload so it picks up new HOME.
    sys.modules.pop("_common", None)
    import _common
    importlib.reload(_common)
    _common.preset_save("smoke", "text", "hash", ["--algo", "sha256"])
    items = _common.preset_list()
    names = [p["name"] for p in items]
    assert "smoke" in names
    loaded = _common.preset_load("smoke")
    assert loaded["category"] == "text" and loaded["command"] == "hash"
    assert _common.preset_delete("smoke")
