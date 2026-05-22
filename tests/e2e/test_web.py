"""Playwright web-UI end-to-end tests.

Starts the real stdlib HTTP server with
    python tk.py server --port <ephemeral> --no-browser
(the "server"/"ui"/"web" subcommand routes to server.main; NOT "serve"),
then drives the served web UI (web/index.html + /static/app.js) with a real
Chromium browser via pytest-playwright's `page` fixture.

The whole module is skipped if Playwright is not importable, so the suite stays
green in environments without it (CI's e2e lane runs them where a browser
exists). The server fixture mirrors the proven pattern in tests/test_api.py.

Confirmed stable selectors (from web/index.html):
  - <title>tk — Personal Toolkit</title>
  - #app                    app shell root
  - header.topbar           top bar
  - #search-btn             "Search … commands" button (opens palette)
  - #palette / #palette-input  command palette (Ctrl+K) + its text input
  - aside.sidebar / #categories  category sidebar
  - #form / #form-fields / #run-btn / #output / #output-stdout  run form + output
"""
from __future__ import annotations

import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

pytest.importorskip("playwright")

ROOT = Path(__file__).resolve().parent.parent.parent


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


@pytest.fixture(scope="module")
def web_server():
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
                    proc.kill()
                    pytest.fail(f"server exited early rc={proc.returncode}: {err}")
                time.sleep(0.2)
        else:
            proc.kill()
            pytest.fail("web server did not start in time")
        yield base
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)


def _suppress_first_visit_tour(page):
    """The app shows a first-visit '#tour' modal unless localStorage
    'tk-tour-seen' is '1' (see web/app.js storage.tourSeen). The modal overlays
    the page and intercepts clicks, so we mark it seen before any navigation."""
    page.add_init_script("localStorage.setItem('tk-tour-seen', '1');")


def test_homepage_loads(web_server, page):
    page.goto(web_server)
    page.wait_for_load_state("networkidle")
    assert page.title() != ""
    assert "tk" in page.title().lower()


def test_app_shell_renders(web_server, page):
    _suppress_first_visit_tour(page)
    page.goto(web_server)
    page.wait_for_load_state("networkidle")
    content = page.content().lower()
    assert "tk" in content
    # Real, stable elements confirmed present in web/index.html:
    page.wait_for_selector("#app", timeout=5000)
    page.wait_for_selector("header.topbar", timeout=5000)
    page.wait_for_selector("#search-btn", timeout=5000)
    page.wait_for_selector("aside.sidebar", timeout=5000)


def test_run_command_flow(web_server, page):
    """Full run flow: open the command palette, search for 'calc', select it,
    fill the expression field, run, and assert the output shows '4'.

    Uses only selectors confirmed in web/index.html and app.js:
      #search-btn opens #palette; #palette-input is the search box; pressing
      Enter selects the top result and opens the #form view; calc's positional
      `expression` arg renders as the first <input> inside #form-fields; #run-btn
      executes; the stdout tab text lands in #output-stdout.
    """
    _suppress_first_visit_tour(page)
    page.goto(web_server)
    page.wait_for_load_state("networkidle")

    # Open the command palette and search for calc.
    page.click("#search-btn")
    page.wait_for_selector("#palette:not(.hidden)", timeout=5000)
    palette_input = page.locator("#palette-input")
    palette_input.fill("calc")
    # Wait for the calc result to appear, then select the top result.
    page.wait_for_selector("#palette-results li code", timeout=5000)
    palette_input.press("Enter")

    # The form view should now be visible with the run button.
    page.wait_for_selector("#form:not(.hidden)", timeout=5000)
    page.wait_for_selector("#run-btn", timeout=5000)

    # calc takes a positional `expression` arg -> first input in #form-fields.
    expr_input = page.locator("#form-fields input").first
    expr_input.wait_for(state="visible", timeout=5000)
    expr_input.fill("2+2")

    # Run and wait for the output panel to populate.
    page.click("#run-btn")
    page.wait_for_selector("#output:not(.hidden)", timeout=15000)
    # The result lands in #output-stdout once the run completes.
    page.wait_for_function(
        "document.getElementById('output-stdout')"
        " && document.getElementById('output-stdout').textContent.includes('4')",
        timeout=15000,
    )
    stdout_text = page.locator("#output-stdout").inner_text()
    assert "4" in stdout_text
