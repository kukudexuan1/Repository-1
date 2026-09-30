"""Markdown 设计文档转 docx。

只处理渲染器实际产出的 Markdown 子集（标题、段落、无序/有序列表、表格、
引用、代码块），不追求通用 Markdown 兼容——文档是我们自己生成的，格式可控。
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_UL = re.compile(r"^\s*[-*]\s+(.*)$")
_OL = re.compile(r"^\s*\d+\.\s+(.*)$")
_QUOTE = re.compile(r"^>\s?(.*)$")
_TABLE_SEP = re.compile(r"^\|[\s:|-]+\|$")
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_CODE = re.compile(r"`([^`]+)`")


class DocxUnavailable(RuntimeError):
    pass


def markdown_to_docx(markdown: str, path: Path) -> Path:
    try:
        from docx import Document
        from docx.shared import Pt
    except ImportError as exc:  # pragma: no cover
        raise DocxUnavailable(
            "缺少 python-docx 依赖，无法导出 docx。请先 pip install python-docx"
        ) from exc

    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = "宋体"
    style.font.size = Pt(10.5)

    lines = markdown.splitlines()
    idx = 0
    in_code = False
    code_buffer: list[str] = []

    while idx < len(lines):
        line = lines[idx]

        if line.strip().startswith("```"):
            if in_code:
                _add_code_block(doc, code_buffer)
                code_buffer = []
            in_code = not in_code
            idx += 1
            continue
        if in_code:
            code_buffer.append(line)
            idx += 1
            continue

        if not line.strip():
            idx += 1
            continue

        if line.strip() == "---":
            doc.add_paragraph()
            idx += 1
            continue

        heading = _HEADING.match(line)
        if heading:
            level = min(len(heading.group(1)), 4)
            doc.add_heading(_plain(heading.group(2)), level=level)
            idx += 1
            continue

        if line.lstrip().startswith("|"):
            idx = _add_table(doc, lines, idx)
            continue

        quote = _QUOTE.match(line)
        if quote:
            para = doc.add_paragraph(_plain(quote.group(1)))
            para.style = doc.styles["Intense Quote"] if "Intense Quote" in [
                s.name for s in doc.styles
            ] else para.style
            idx += 1
            continue

        ul = _UL.match(line)
        if ul:
            doc.add_paragraph(_plain(ul.group(1)), style="List Bullet")
            idx += 1
            continue

        ol = _OL.match(line)
        if ol:
            doc.add_paragraph(_plain(ol.group(1)), style="List Number")
            idx += 1
            continue

        doc.add_paragraph(_plain(line))
        idx += 1

    if code_buffer:
        _add_code_block(doc, code_buffer)

    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(path))
    return path


def _add_table(doc, lines: list[str], start: int) -> int:
    rows: list[list[str]] = []
    idx = start
    while idx < len(lines) and lines[idx].lstrip().startswith("|"):
        raw = lines[idx].strip()
        if _TABLE_SEP.match(raw):
            idx += 1
            continue
        cells = [c.strip() for c in raw.strip("|").split("|")]
        rows.append(cells)
        idx += 1

    if not rows:
        return idx

    width = max(len(r) for r in rows)
    table = doc.add_table(rows=0, cols=width)
    table.style = "Table Grid"
    for r_idx, row in enumerate(rows):
        cells = table.add_row().cells
        for c_idx in range(width):
            text = _plain(row[c_idx]) if c_idx < len(row) else ""
            cells[c_idx].text = text
            if r_idx == 0:
                for paragraph in cells[c_idx].paragraphs:
                    for run in paragraph.runs:
                        run.bold = True
    return idx


def _add_code_block(doc, buffer: list[str]) -> None:
    from docx.shared import Pt

    para = doc.add_paragraph()
    run = para.add_run("\n".join(buffer))
    run.font.name = "Consolas"
    run.font.size = Pt(9)


def _plain(text: str) -> str:
    text = _BOLD.sub(r"\1", text)
    text = _CODE.sub(r"\1", text)
    return text.strip()
