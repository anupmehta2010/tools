from __future__ import annotations

import argparse
import html
import re
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    Preformatted,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


def _try_register_font(font_name: str, ttf_path: Path) -> bool:
    try:
        if not ttf_path.exists():
            return False
        pdfmetrics.registerFont(TTFont(font_name, str(ttf_path)))
        return True
    except Exception:
        return False


def _register_windows_fonts() -> tuple[str, str, str]:
    """Return (body_font, body_bold_font, mono_font) names that are registered."""

    windows_fonts = Path("C:/Windows/Fonts")

    body_font = "Helvetica"
    body_bold_font = "Helvetica-Bold"
    mono_font = "Courier"

    # Prefer Unicode-capable TrueType fonts (better arrows, ≥, Δ, etc.).
    if _try_register_font("Arial", windows_fonts / "arial.ttf"):
        body_font = "Arial"
    if _try_register_font("Arial-Bold", windows_fonts / "arialbd.ttf"):
        body_bold_font = "Arial-Bold"

    # Monospace for diagrams/code.
    if _try_register_font("Consolas", windows_fonts / "consola.ttf"):
        mono_font = "Consolas"

    return body_font, body_bold_font, mono_font


_LATEX_REPLACEMENTS: list[tuple[str, str]] = [
    (r"\\Delta", "Δ"),
    (r"\\rightarrow", "→"),
    (r"\\leftarrow", "←"),
]


def _sanitize_text_for_pdf(s: str) -> str:
    # Replace emojis/symbols that often don't render in typical TTFs.
    s = s.replace("🔷", "◆")

    # Strip common inline LaTeX wrappers used in the source.
    s = s.replace("\\(", "").replace("\\)", "")
    s = s.replace("\\[", "").replace("\\]", "")

    for pattern, repl in _LATEX_REPLACEMENTS:
        s = re.sub(pattern, repl, s)

    return s


_CODE_SPAN_RE = re.compile(r"`([^`]+)`")
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")


def _md_inline_to_rl(text: str, mono_font: str, bold_font: str) -> str:
    """Convert a small subset of Markdown inline markup to ReportLab Paragraph markup."""

    text = _sanitize_text_for_pdf(text)

    # Handle code spans first.
    def code_repl(m: re.Match[str]) -> str:
        code = html.escape(m.group(1))
        return f'<font face="{mono_font}">{code}</font>'

    text = _CODE_SPAN_RE.sub(code_repl, text)

    # Escape remaining text, but keep already-inserted tags.
    # We escape by splitting on tags.
    parts: list[str] = []
    pos = 0
    for tag_match in re.finditer(r"<[^>]+>", text):
        parts.append(html.escape(text[pos : tag_match.start()]))
        parts.append(text[tag_match.start() : tag_match.end()])
        pos = tag_match.end()
    parts.append(html.escape(text[pos:]))
    text = "".join(parts)

    # Bold markdown.
    def bold_repl(m: re.Match[str]) -> str:
        inner = m.group(1)
        # inner is already escaped
        return f'<font face="{bold_font}"><b>{inner}</b></font>'

    text = _BOLD_RE.sub(bold_repl, text)

    return text


_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_BULLET_RE = re.compile(r"^(\s*)-\s+(.*)$")
_NUMBERED_RE = re.compile(r"^(\s*)(\d+)\.\s+(.*)$")


def _looks_like_md_table_row(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("|") and stripped.count("|") >= 2


def _split_md_table_row(line: str) -> list[str]:
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    return [cell.strip() for cell in stripped.split("|")]


def _is_md_table_separator_row(cells: list[str]) -> bool:
    # Example: |---|---:|:---:| etc.
    if not cells:
        return False
    return all(re.fullmatch(r":?-{3,}:?", c.strip()) is not None for c in cells)


def _md_table_alignments_from_separator(cells: list[str]) -> list[str]:
    aligns: list[str] = []
    for c in cells:
        cs = c.strip()
        if cs.startswith(":") and cs.endswith(":"):
            aligns.append("CENTER")
        elif cs.endswith(":"):
            aligns.append("RIGHT")
        else:
            aligns.append("LEFT")
    return aligns


def _plain_len_for_table_width(s: str) -> int:
    # Roughly estimate column width needs by stripping common markdown markup.
    s = _sanitize_text_for_pdf(s)
    s = re.sub(r"`([^`]+)`", r"\1", s)
    s = re.sub(r"\*\*(.+?)\*\*", r"\1", s)
    s = s.replace("\t", " ")
    return len(s.strip())


def build_pdf(md_path: Path, pdf_path: Path) -> None:
    body_font, body_bold_font, mono_font = _register_windows_fonts()

    lines = md_path.read_text(encoding="utf-8").splitlines()

    doc_title = "Autonomous Safari Navigation System Build Guide"
    for raw in lines:
        hm = _HEADING_RE.match(raw.strip("\n"))
        if hm and len(hm.group(1)) == 1:
            doc_title = _sanitize_text_for_pdf(hm.group(2).strip())
            break

    styles = getSampleStyleSheet()

    style_body = ParagraphStyle(
        "Body",
        parent=styles["BodyText"],
        fontName=body_font,
        fontSize=10.5,
        leading=14,
        spaceAfter=6,
    )

    style_h1 = ParagraphStyle(
        "H1",
        parent=styles["Heading1"],
        fontName=body_bold_font,
        fontSize=18,
        leading=22,
        spaceBefore=6,
        spaceAfter=10,
    )
    style_h2 = ParagraphStyle(
        "H2",
        parent=styles["Heading2"],
        fontName=body_bold_font,
        fontSize=14,
        leading=18,
        spaceBefore=10,
        spaceAfter=8,
    )
    style_h3 = ParagraphStyle(
        "H3",
        parent=styles["Heading3"],
        fontName=body_bold_font,
        fontSize=12.5,
        leading=16,
        spaceBefore=8,
        spaceAfter=6,
    )
    style_h4 = ParagraphStyle(
        "H4",
        parent=styles["Heading4"],
        fontName=body_bold_font,
        fontSize=11.5,
        leading=15,
        spaceBefore=6,
        spaceAfter=4,
    )

    style_code = ParagraphStyle(
        "Code",
        parent=styles["Code"],
        fontName=mono_font,
        fontSize=9,
        leading=11,
        spaceBefore=6,
        spaceAfter=6,
    )

    style_table_cell = ParagraphStyle(
        "TableCell",
        parent=style_body,
        fontSize=9.2,
        leading=11,
        spaceBefore=0,
        spaceAfter=0,
        wordWrap="CJK",
    )
    style_table_header = ParagraphStyle(
        "TableHeader",
        parent=style_table_cell,
        fontName=body_bold_font,
    )

    def on_page(canvas, doc):
        canvas.saveState()
        canvas.setFont(body_font, 9)
        canvas.drawRightString(doc.pagesize[0] - 1.5 * cm, 1.2 * cm, str(doc.page))
        canvas.restoreState()

    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=A4,
        leftMargin=2.0 * cm,
        rightMargin=2.0 * cm,
        topMargin=2.0 * cm,
        bottomMargin=2.0 * cm,
        title=doc_title,
        author="",
    )

    flow = []

    in_code = False
    code_lines: list[str] = []
    para_lines: list[str] = []

    def flush_paragraph() -> None:
        nonlocal para_lines
        if not para_lines:
            return
        text = " ".join(line.strip() for line in para_lines).strip()
        para_lines = []
        if not text:
            return
        rl = _md_inline_to_rl(text, mono_font=mono_font, bold_font=body_bold_font)
        flow.append(Paragraph(rl, style_body))

    def flush_code() -> None:
        nonlocal code_lines
        if not code_lines:
            return
        code = "\n".join(code_lines).rstrip("\n")
        code_lines = []
        code = _sanitize_text_for_pdf(code)
        flow.append(Preformatted(code, style_code))

    i = 0
    while i < len(lines):
        line = lines[i].rstrip("\n")

        if line.strip().startswith("```"):
            flush_paragraph()
            if in_code:
                flush_code()
                in_code = False
            else:
                in_code = True
                code_lines = []
            i += 1
            continue

        if in_code:
            code_lines.append(line)
            i += 1
            continue

        # Tables (Markdown pipe tables)
        if _looks_like_md_table_row(line):
            flush_paragraph()

            table_lines: list[str] = []
            while i < len(lines) and _looks_like_md_table_row(lines[i]):
                table_lines.append(lines[i].rstrip("\n"))
                i += 1

            rows = [_split_md_table_row(tl) for tl in table_lines]
            if not rows:
                continue

            # Normalize row widths
            col_count = max(len(r) for r in rows)
            rows = [r + [""] * (col_count - len(r)) for r in rows]

            header_row_count = 0
            col_aligns: list[str] = ["LEFT"] * col_count
            if len(rows) >= 2 and _is_md_table_separator_row(rows[1]):
                header_row_count = 1
                col_aligns = _md_table_alignments_from_separator(rows[1])
                col_aligns = col_aligns + ["LEFT"] * (col_count - len(col_aligns))
                rows = [rows[0]] + rows[2:]

            # Column widths (rough heuristic based on max cell length)
            max_lens = [0] * col_count
            for r in rows:
                for c in range(col_count):
                    max_lens[c] = max(max_lens[c], _plain_len_for_table_width(r[c]))
            weights = [min(60, max(6, ml)) for ml in max_lens]
            weight_sum = sum(weights) or 1
            col_widths = [doc.width * (w / weight_sum) for w in weights]

            table_data: list[list[Paragraph]] = []
            for ridx, r in enumerate(rows):
                is_header = header_row_count == 1 and ridx == 0
                cell_style = style_table_header if is_header else style_table_cell
                rendered_row: list[Paragraph] = []
                for cell in r:
                    cell_rl = _md_inline_to_rl(cell, mono_font=mono_font, bold_font=body_bold_font)
                    rendered_row.append(Paragraph(cell_rl, cell_style))
                table_data.append(rendered_row)

            t = Table(table_data, colWidths=col_widths, repeatRows=header_row_count)
            ts = TableStyle(
                [
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ]
            )
            if header_row_count == 1:
                ts.add("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey)
            for col, align in enumerate(col_aligns[:col_count]):
                ts.add("ALIGN", (col, 0), (col, -1), align)
            t.setStyle(ts)
            flow.append(t)
            flow.append(Spacer(1, 8))
            continue

        # Page breaks (optional): honor explicit marker.
        if line.strip() == "\\pagebreak":
            flush_paragraph()
            flow.append(PageBreak())
            i += 1
            continue

        # Horizontal rule
        if line.strip() in {"---", "***"}:
            flush_paragraph()
            flow.append(Spacer(1, 10))
            i += 1
            continue

        # Headings
        hm = _HEADING_RE.match(line)
        if hm:
            flush_paragraph()
            hashes = hm.group(1)
            title = hm.group(2).strip()
            title_rl = _md_inline_to_rl(title, mono_font=mono_font, bold_font=body_bold_font)
            level = len(hashes)
            if level == 1:
                flow.append(Paragraph(title_rl, style_h1))
            elif level == 2:
                flow.append(Paragraph(title_rl, style_h2))
            elif level == 3:
                flow.append(Paragraph(title_rl, style_h3))
            else:
                flow.append(Paragraph(title_rl, style_h4))
            i += 1
            continue

        # Bullets
        bm = _BULLET_RE.match(line)
        if bm:
            flush_paragraph()
            indent_spaces = len(bm.group(1).replace("\t", "    "))
            item = bm.group(2).strip()
            item_rl = _md_inline_to_rl(item, mono_font=mono_font, bold_font=body_bold_font)
            left_indent = 12 + min(36, indent_spaces * 2)
            bullet_style = ParagraphStyle(
                "Bullet",
                parent=style_body,
                leftIndent=left_indent,
                firstLineIndent=-10,
            )
            flow.append(Paragraph(item_rl, bullet_style, bulletText="•"))
            i += 1
            continue

        nm = _NUMBERED_RE.match(line)
        if nm:
            flush_paragraph()
            indent_spaces = len(nm.group(1).replace("\t", "    "))
            num = nm.group(2)
            item = nm.group(3).strip()
            item_rl = _md_inline_to_rl(item, mono_font=mono_font, bold_font=body_bold_font)
            left_indent = 12 + min(36, indent_spaces * 2)
            num_style = ParagraphStyle(
                "Numbered",
                parent=style_body,
                leftIndent=left_indent,
                firstLineIndent=-18,
            )
            flow.append(Paragraph(item_rl, num_style, bulletText=f"{num}."))
            i += 1
            continue

        if not line.strip():
            flush_paragraph()
            i += 1
            continue

        para_lines.append(line)

        i += 1

    flush_paragraph()
    if in_code:
        flush_code()

    doc.build(flow, onFirstPage=on_page, onLaterPages=on_page)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate PDF from build guide markdown.")
    parser.add_argument(
        "--md",
        default=str(Path("docs") / "Autonomous_Safari_Navigation_System_Build_Guide.md"),
        help="Path to the Markdown source file.",
    )
    parser.add_argument(
        "--pdf",
        default=str(Path("docs") / "Autonomous_Safari_Navigation_System_Build_Guide.pdf"),
        help="Output PDF path.",
    )
    args = parser.parse_args()

    md_path = Path(args.md)
    pdf_path = Path(args.pdf)

    if not md_path.exists():
        raise SystemExit(f"Markdown file not found: {md_path}")

    pdf_path.parent.mkdir(parents=True, exist_ok=True)

    build_pdf(md_path=md_path, pdf_path=pdf_path)
    print(f"Wrote: {pdf_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
