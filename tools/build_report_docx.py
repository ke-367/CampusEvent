"""把 docs/实验报告.md 转换为 docs/实验报告.docx（含图片与表格）。

用法：python tools/build_report_docx.py
"""
from __future__ import annotations

import re
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Cm, Pt, RGBColor

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "docs" / "实验报告.md"
DST = ROOT / "docs" / "实验报告.docx"

BOLD = re.compile(r"\*\*(.+?)\*\*")
INLINE_CODE = re.compile(r"`([^`]+)`")


def add_runs(paragraph, text: str):
    """处理 **粗体** 与 `行内代码`。"""
    text = text.replace("<br>", " ")
    pos = 0
    tokens = []
    for m in BOLD.finditer(text):
        tokens.append(("plain", text[pos:m.start()]))
        tokens.append(("bold", m.group(1)))
        pos = m.end()
    tokens.append(("plain", text[pos:]))
    for kind, chunk in tokens:
        for piece in INLINE_CODE.split(chunk):
            if not piece:
                continue
            run = paragraph.add_run(piece)
            if kind == "bold":
                run.bold = True
            if piece in INLINE_CODE.findall(chunk):
                run.font.name = "Consolas"
                run.font.size = Pt(10)


def main() -> int:
    lines = SRC.read_text(encoding="utf-8").splitlines()
    doc = Document()

    style = doc.styles["Normal"]
    style.font.name = "宋体"
    style.font.size = Pt(10.5)
    style.paragraph_format.line_spacing = 1.15
    style.paragraph_format.space_after = Pt(3)

    for section in doc.sections:
        section.top_margin = Cm(2.0)
        section.bottom_margin = Cm(2.0)
        section.left_margin = Cm(2.2)
        section.right_margin = Cm(2.2)

    for level in range(1, 4):
        hs = doc.styles[f"Heading {level}"]
        hs.font.name = "黑体"
        hs.font.color.rgb = RGBColor(0x1F, 0x2A, 0x44)
        hs.font.size = Pt({1: 18, 2: 15, 3: 12.5}[level])

    table_buf: list[str] = []

    def flush_table():
        nonlocal table_buf
        if not table_buf:
            return
        rows = [
            [c.strip() for c in line.strip().strip("|").split("|")]
            for line in table_buf
            if not re.match(r"^\|[\s:\-|]+\|$", line.strip())
        ]
        table_buf = []
        if not rows:
            return
        cols = max(len(r) for r in rows)
        table = doc.add_table(rows=0, cols=cols)
        table.style = "Table Grid"
        for i, row in enumerate(rows):
            cells = table.add_row().cells
            for j in range(cols):
                text = row[j] if j < len(row) else ""
                cell = cells[j]
                cell.text = ""
                para = cell.paragraphs[0]
                para.paragraph_format.space_after = Pt(2)
                add_runs(para, text)
                for run in para.runs:
                    run.font.size = Pt(8.5)
                    if i == 0:
                        run.bold = True
        doc.add_paragraph()

    in_code = False
    code_buf: list[str] = []

    for raw in lines:
        line = raw.rstrip()

        if line.startswith("```"):
            if in_code:
                para = doc.add_paragraph()
                para.paragraph_format.left_indent = Cm(0.6)
                run = para.add_run("\n".join(code_buf))
                run.font.name = "Consolas"
                run.font.size = Pt(9.5)
                code_buf = []
                in_code = False
            else:
                flush_table()
                in_code = True
            continue
        if in_code:
            code_buf.append(raw)
            continue

        if line.startswith("|"):
            table_buf.append(line)
            continue
        flush_table()

        if not line.strip():
            continue

        if line.startswith("#"):
            level = len(line) - len(line.lstrip("#"))
            text = line[level:].strip()
            if level == 1:
                para = doc.add_paragraph()
                para.alignment = WD_ALIGN_PARAGRAPH.CENTER
                run = para.add_run(text)
                run.font.name = "黑体"
                run.font.size = Pt(20)
                run.bold = True
            else:
                h = doc.add_heading(level=min(level, 3))
                add_runs(h, text)
            continue

        image = re.match(r"!\[(.*?)\]\((.*?)\)", line.strip())
        if image:
            path = (SRC.parent / image.group(2)).resolve()
            if path.exists():
                if path.parent.name == "screenshots":
                    # 截图上下有大量空白，裁掉页眉与空白区，避免报告里出现整页空图
                    from PIL import Image

                    cache = ROOT / "docs" / "_build"
                    cache.mkdir(exist_ok=True)
                    cropped = cache / path.name
                    if not cropped.exists() or cropped.stat().st_mtime < path.stat().st_mtime:
                        with Image.open(path) as im:
                            im.crop((70, 60, 1240, 800)).save(cropped)
                    path = cropped
                doc.add_picture(str(path), width=Cm(13.0))
                doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
            continue

        if line.startswith(("- ", "* ")):
            para = doc.add_paragraph(style="List Bullet")
            add_runs(para, line[2:])
            continue
        if re.match(r"^\d+\.\s", line):
            para = doc.add_paragraph()
            para.paragraph_format.first_line_indent = Cm(0)
            add_runs(para, line.strip())
            continue
        if line.strip() == "---":
            continue

        para = doc.add_paragraph()
        para.paragraph_format.first_line_indent = Cm(0.74)
        add_runs(para, line)

    flush_table()
    doc.save(DST)
    print(f"OK {DST} ({DST.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

