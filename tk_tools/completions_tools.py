"""Shell completion generator for tk.

Emits a self-contained completion script for bash, zsh, PowerShell, or fish.
Discovers categories and subcommands dynamically by importing the tk launcher
and each category module's COMMANDS table, so the completions stay accurate as
new tools are added.

Usage:
    python tk.py completions bash > /etc/bash_completion.d/tk
    python tk.py completions zsh  > ~/.zsh/completions/_tk
    python tk.py completions pwsh > tk-completions.ps1
    python tk.py completions fish > ~/.config/fish/completions/tk.fish

Each subcommand prints to stdout by default; use ``-o FILE`` to write to a file.
"""
from __future__ import annotations

import argparse
import importlib
import sys
import sys as _sys
from pathlib import Path
from pathlib import Path as _Path

_sys.path.insert(0, str(_Path(__file__).resolve().parent.parent))
from _common import tool_main

# Meta verbs handled by tk.py itself (top-level, not in CATEGORIES).
META_COMMANDS = [
    "doctor",
    "history",
    "preset",
    "pipe",
    "plugins",
    "ui",
    "list",
    "version",
    "--json",
    "--help",
    "-h",
]


COMMANDS = {
    "bash": "Emit a bash completion script for tk",
    "zsh":  "Emit a zsh completion script for tk",
    "pwsh": "Emit a PowerShell completion script for tk",
    "fish": "Emit a fish completion script for tk",
}


# ----------------------------------------------------------- discovery

def _discover() -> tuple[list[str], dict[str, list[str]]]:
    """Return (top_level_completions, {category: [subcommands]}).

    top_level_completions = all categories + meta commands.
    Falls back to a static snapshot if tk cannot be imported.
    """
    here = Path(__file__).resolve().parent.parent
    if str(here) not in sys.path:
        sys.path.insert(0, str(here))

    cats_subcmds: dict[str, list[str]] = {}
    categories: list[str] = []

    try:
        tk = importlib.import_module("tk")
        cats = tk.available_categories()
        for key, (mod_name, _desc, _icon) in cats.items():
            categories.append(key)
            try:
                mod = importlib.import_module(mod_name)
                subs = list(getattr(mod, "COMMANDS", {}).keys())
            except Exception:
                subs = []
            cats_subcmds[key] = sorted(subs)
    except Exception as e:
        print(f"# warning: could not import tk ({e}); using static fallback", file=sys.stderr)
        categories = [
            "pdf", "image", "media", "text", "data", "archive", "crypto",
            "net", "fs", "dev", "qr", "oled", "convert",
        ]
        cats_subcmds = {c: [] for c in categories}

    top = sorted(set(categories) | set(META_COMMANDS))
    return top, cats_subcmds


# ----------------------------------------------------------- emit helpers

def _emit(text: str, out: str | None) -> None:
    if out:
        Path(out).write_text(text, encoding="utf-8")
        print(f"Wrote {out}")
    else:
        sys.stdout.write(text)


# ----------------------------------------------------------- bash

def _gen_bash(top: list[str], subs: dict[str, list[str]]) -> str:
    cat_keys = " ".join(k for k in top if not k.startswith("-"))
    flags = " ".join(k for k in top if k.startswith("-"))
    case_lines = []
    for cat, items in sorted(subs.items()):
        if not items:
            continue
        items_s = " ".join(items)
        case_lines.append(f'    {cat})\n      COMPREPLY=( $(compgen -W "{items_s}" -- "$cur") )\n      return 0 ;;')
    cases = "\n".join(case_lines) if case_lines else "    *) ;;"

    return f"""# tk — bash completion (auto-generated)
# Install (system-wide):
#   sudo python tk.py completions bash > /etc/bash_completion.d/tk
# Or for the current shell only:
#   source <(python tk.py completions bash)

_tk_complete() {{
  local cur prev words cword
  COMPREPLY=()
  cur="${{COMP_WORDS[COMP_CWORD]}}"
  prev="${{COMP_WORDS[COMP_CWORD-1]}}"

  # First positional: complete categories + meta verbs + flags
  if [ "$COMP_CWORD" -eq 1 ]; then
    COMPREPLY=( $(compgen -W "{cat_keys} {flags}" -- "$cur") )
    return 0
  fi

  # Second positional: complete the subcommands of the chosen category
  local cat="${{COMP_WORDS[1]}}"
  case "$cat" in
{cases}
    preset)
      COMPREPLY=( $(compgen -W "save list run delete show" -- "$cur") )
      return 0 ;;
    *)
      COMPREPLY=( $(compgen -f -- "$cur") )
      return 0 ;;
  esac
}}
complete -F _tk_complete tk
complete -F _tk_complete tk.py
"""


def cmd_bash(args) -> int:
    top, subs = _discover()
    _emit(_gen_bash(top, subs), args.output)
    return 0


# ----------------------------------------------------------- zsh

def _gen_zsh(top: list[str], subs: dict[str, list[str]]) -> str:
    cat_keys = " ".join(k for k in top if not k.startswith("-"))
    case_lines = []
    for cat, items in sorted(subs.items()):
        if not items:
            continue
        items_s = " ".join(items)
        case_lines.append(f'      {cat}) _values "{cat} command" {items_s} ;;')
    cases = "\n".join(case_lines) if case_lines else "      *) ;;"

    return f"""#compdef tk tk.py
# tk — zsh completion (auto-generated)
# Install:
#   python tk.py completions zsh > ~/.zsh/completions/_tk
# Make sure ~/.zsh/completions is on $fpath, then run: autoload -Uz compinit && compinit

_tk() {{
  local context curcontext="$curcontext" state line
  local -a categories
  categories=({cat_keys})

  _arguments -C \\
    "1:category:->cats" \\
    "*::arg:->args"

  case "$state" in
    cats)
      _values "tk category" $categories
      ;;
    args)
      case "${{line[1]}}" in
{cases}
        preset) _values "preset op" save list run delete show ;;
        *) _files ;;
      esac
      ;;
  esac
}}

_tk "$@"
"""


def cmd_zsh(args) -> int:
    top, subs = _discover()
    _emit(_gen_zsh(top, subs), args.output)
    return 0


# ----------------------------------------------------------- pwsh

def _gen_pwsh(top: list[str], subs: dict[str, list[str]]) -> str:
    quoted_top = ", ".join(f"'{x}'" for x in top)
    map_entries = []
    for cat, items in sorted(subs.items()):
        if not items:
            continue
        item_list = ", ".join(f"'{x}'" for x in items)
        map_entries.append(f"    '{cat}' = @({item_list})")
    map_entries.append("    'preset' = @('save', 'list', 'run', 'delete', 'show')")
    map_block = "\n".join(map_entries) if map_entries else ""

    return f"""# tk — PowerShell completion (auto-generated)
# Install:
#   python tk.py completions pwsh > $HOME\\Documents\\PowerShell\\tk-completions.ps1
#   Add to your $PROFILE:  . $HOME\\Documents\\PowerShell\\tk-completions.ps1

$global:TkTopLevel = @({quoted_top})
$global:TkSubcommands = @{{
{map_block}
}}

$tkCompleter = {{
    param($wordToComplete, $commandAst, $cursorPosition)

    # Tokenize what the user has typed so far (drop the leading 'tk' / 'tk.py').
    $tokens = @($commandAst.CommandElements | ForEach-Object {{ $_.ToString() }})
    if ($tokens.Count -gt 0) {{ $tokens = $tokens[1..($tokens.Count - 1)] }}

    # First positional -> categories + meta
    if ($tokens.Count -le 1) {{
        return $global:TkTopLevel |
            Where-Object {{ $_ -like "$wordToComplete*" }} |
            ForEach-Object {{ [System.Management.Automation.CompletionResult]::new($_, $_, 'ParameterValue', $_) }}
    }}

    # Second positional -> that category's subcommands
    $cat = $tokens[0]
    if ($global:TkSubcommands.ContainsKey($cat)) {{
        return $global:TkSubcommands[$cat] |
            Where-Object {{ $_ -like "$wordToComplete*" }} |
            ForEach-Object {{ [System.Management.Automation.CompletionResult]::new($_, $_, 'ParameterValue', $_) }}
    }}
    return @()
}}

Register-ArgumentCompleter -CommandName tk, tk.py -Native -ScriptBlock $tkCompleter
"""


def cmd_pwsh(args) -> int:
    top, subs = _discover()
    _emit(_gen_pwsh(top, subs), args.output)
    return 0


# ----------------------------------------------------------- fish

def _gen_fish(top: list[str], subs: dict[str, list[str]]) -> str:
    lines = [
        "# tk — fish completion (auto-generated)",
        "# Install:",
        "#   python tk.py completions fish > ~/.config/fish/completions/tk.fish",
        "",
        "# Disable file completion by default; we re-enable it for unknown positions.",
        "complete -c tk -f",
        "complete -c tk.py -f",
        "",
        "# ---- top-level: categories + meta ----",
    ]
    for tok in top:
        if tok.startswith("--"):
            lines.append(f"complete -c tk    -n '__fish_is_first_arg' -l '{tok.lstrip('-')}'")
        elif tok.startswith("-"):
            continue
        else:
            lines.append(f"complete -c tk    -n '__fish_is_first_arg' -a '{tok}'")
            lines.append(f"complete -c tk.py -n '__fish_is_first_arg' -a '{tok}'")
    lines.append("")
    lines.append("# ---- second-level: per-category subcommands ----")
    for cat, items in sorted(subs.items()):
        if not items:
            continue
        for it in items:
            lines.append(f"complete -c tk    -n '__fish_seen_subcommand_from {cat}' -a '{it}'")
            lines.append(f"complete -c tk.py -n '__fish_seen_subcommand_from {cat}' -a '{it}'")
    # preset ops
    lines.append("complete -c tk    -n '__fish_seen_subcommand_from preset' -a 'save list run delete show'")
    lines.append("complete -c tk.py -n '__fish_seen_subcommand_from preset' -a 'save list run delete show'")
    lines.append("")
    return "\n".join(lines)


def cmd_fish(args) -> int:
    top, subs = _discover()
    _emit(_gen_fish(top, subs), args.output)
    return 0


# ----------------------------------------------------------- parser

def _add_io(p: argparse.ArgumentParser) -> None:
    p.add_argument("-o", "--output", help="Write the script to this file instead of stdout.")


def build_parser(parser: argparse.ArgumentParser | None = None) -> argparse.ArgumentParser:
    parser = parser or argparse.ArgumentParser(
        prog="completions_tools",
        description="Generate shell completion scripts for tk (bash/zsh/pwsh/fish).",
    )
    sub = parser.add_subparsers(dest="cmd")

    p = sub.add_parser("bash", help=COMMANDS["bash"])
    _add_io(p)
    p.set_defaults(func=cmd_bash)

    p = sub.add_parser("zsh", help=COMMANDS["zsh"])
    _add_io(p)
    p.set_defaults(func=cmd_zsh)

    p = sub.add_parser("pwsh", help=COMMANDS["pwsh"])
    _add_io(p)
    p.set_defaults(func=cmd_pwsh)

    p = sub.add_parser("fish", help=COMMANDS["fish"])
    _add_io(p)
    p.set_defaults(func=cmd_fish)

    return parser


@tool_main("completions")
def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 1
    return args.func(args) or 0


if __name__ == "__main__":
    raise SystemExit(main())
