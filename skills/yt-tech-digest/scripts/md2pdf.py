# -*- coding: utf-8 -*-
"""Markdown -> PDF (кириллица, таблицы). reportlab Platypus, шрифт Arial из C:\\Windows\\Fonts."""
import re, sys, os
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
                                PageBreak, KeepTogether)

F = r"C:\Windows\Fonts"
pdfmetrics.registerFont(TTFont("Ar", os.path.join(F, "arial.ttf")))
pdfmetrics.registerFont(TTFont("ArB", os.path.join(F, "arialbd.ttf")))
pdfmetrics.registerFont(TTFont("ArI", os.path.join(F, "ariali.ttf")))
pdfmetrics.registerFont(TTFont("Mono", os.path.join(F, "consola.ttf")))
pdfmetrics.registerFontFamily("Ar", normal="Ar", bold="ArB", italic="ArI")

ACC = colors.HexColor("#C8102E")   # акцент
INK = colors.HexColor("#1a1a1a")
MUT = colors.HexColor("#666666")
HDRBG = colors.HexColor("#F2F2F2")

S = getSampleStyleSheet()
def st(name, **kw):
    base = dict(fontName="Ar", textColor=INK, leading=13, fontSize=9.2, alignment=TA_LEFT)
    base.update(kw)
    return ParagraphStyle(name, **base)

P      = st("P", spaceAfter=4)
LI     = st("LI", leftIndent=10, bulletIndent=2, spaceAfter=2)
H1     = st("H1", fontName="ArB", fontSize=19, leading=23, textColor=ACC, spaceBefore=6, spaceAfter=8)
H2     = st("H2", fontName="ArB", fontSize=13.5, leading=17, textColor=ACC, spaceBefore=11, spaceAfter=5)
H3     = st("H3", fontName="ArB", fontSize=11, leading=14, spaceBefore=8, spaceAfter=3)
CODE   = st("CODE", fontName="Mono", fontSize=7.8, leading=10, backColor=colors.HexColor("#F6F6F6"),
            borderPadding=4, leftIndent=4, spaceAfter=5)
QUOTE  = st("QUOTE", fontName="ArI", textColor=MUT, leftIndent=8, spaceAfter=5)
TDS    = st("TD", fontSize=7.6, leading=9.6)
THS    = st("TH", fontName="ArB", fontSize=7.6, leading=9.6)

def inline(t):
    """markdown inline -> reportlab intra-paragraph markup"""
    t = (t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
    t = re.sub(r"`([^`]+)`", r'<font face="Mono" size="8">\1</font>', t)
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"(?<![\w*])\*([^*\n]+?)\*(?![\w*])", r"<i>\1</i>", t)
    t = re.sub(r"(?<!\w)_([^_\n]+?)_(?!\w)", r"<i>\1</i>", t)
    t = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<link href="\2"><font color="#0645AD">\1</font></link>', t)
    t = re.sub(r"~~(.+?)~~", r"<strike>\1</strike>", t)
    return t

def split_row(line):
    line = line.strip()
    if line.startswith("|"): line = line[1:]
    if line.endswith("|"): line = line[:-1]
    return [c.strip() for c in re.split(r"(?<!\\)\|", line)]

def build(md, story, avail):
    lines = md.split("\n")
    i, n = 0, len(lines)
    while i < n:
        ln = lines[i]
        s = ln.strip()

        if not s:
            i += 1; continue

        # fenced code
        if s.startswith("```"):
            i += 1; buf = []
            while i < n and not lines[i].strip().startswith("```"):
                buf.append(lines[i]); i += 1
            i += 1
            txt = "\n".join(buf).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
            story.append(Paragraph(txt.replace("\n", "<br/>"), CODE)); continue

        # table
        if s.startswith("|") and i + 1 < n and re.match(r"^\s*\|[\s:|-]+\|\s*$", lines[i+1]):
            head = split_row(s); i += 2
            rows = []
            while i < n and lines[i].strip().startswith("|"):
                rows.append(split_row(lines[i])); i += 1
            ncol = max(len(head), max((len(r) for r in rows), default=0))
            head += [""] * (ncol - len(head))
            data = [[Paragraph(inline(c), THS) for c in head]]
            for r in rows:
                r += [""] * (ncol - len(r))
                data.append([Paragraph(inline(c), TDS) for c in r])
            w = avail / ncol
            t = Table(data, colWidths=[w]*ncol, repeatRows=1, hAlign="LEFT")
            t.setStyle(TableStyle([
                ("BACKGROUND", (0,0), (-1,0), HDRBG),
                ("GRID", (0,0), (-1,-1), 0.4, colors.HexColor("#CCCCCC")),
                ("LINEBELOW", (0,0), (-1,0), 0.9, ACC),
                ("VALIGN", (0,0), (-1,-1), "TOP"),
                ("LEFTPADDING", (0,0), (-1,-1), 3), ("RIGHTPADDING", (0,0), (-1,-1), 3),
                ("TOPPADDING", (0,0), (-1,-1), 3), ("BOTTOMPADDING", (0,0), (-1,-1), 3),
                ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#FAFAFA")]),
            ]))
            story.append(Spacer(1, 3)); story.append(t); story.append(Spacer(1, 7)); continue

        # hr
        if re.match(r"^(-{3,}|\*{3,}|_{3,})$", s):
            story.append(Spacer(1, 4))
            story.append(Table([[""]], colWidths=[avail], rowHeights=[0.6],
                               style=[("BACKGROUND", (0,0), (-1,-1), colors.HexColor("#DDDDDD"))]))
            story.append(Spacer(1, 6)); i += 1; continue

        # headings
        m = re.match(r"^(#{1,6})\s+(.*)$", s)
        if m:
            lvl, txt = len(m.group(1)), inline(m.group(2))
            sty = H1 if lvl == 1 else (H2 if lvl == 2 else H3)
            story.append(Paragraph(txt, sty)); i += 1; continue

        # quote
        if s.startswith(">"):
            buf = []
            while i < n and lines[i].strip().startswith(">"):
                buf.append(re.sub(r"^\s*>\s?", "", lines[i])); i += 1
            story.append(Paragraph(inline(" ".join(buf)), QUOTE)); continue

        # lists
        m = re.match(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$", ln)
        if m:
            indent = len(m.group(1)) // 2
            ordered = bool(re.match(r"\d", m.group(2)))
            bullet = m.group(2) if ordered else "•"
            sty = ParagraphStyle("li%d" % indent, parent=LI, leftIndent=10 + indent*12,
                                 bulletIndent=2 + indent*12)
            story.append(Paragraph(inline(m.group(3)), sty, bulletText=bullet)); i += 1; continue

        # paragraph
        buf = []
        while i < n and lines[i].strip() and not re.match(r"^\s*(#{1,6}\s|\||>|```|[-*+]\s|\d+[.)]\s)", lines[i]) \
              and not re.match(r"^(-{3,}|\*{3,}|_{3,})$", lines[i].strip()):
            buf.append(lines[i].strip()); i += 1
        if buf:
            story.append(Paragraph(inline(" ".join(buf)), P))
        else:
            i += 1

def footer(canv, doc):
    canv.saveState()
    canv.setFont("Ar", 7.5); canv.setFillColor(MUT)
    canv.drawString(15*mm, 10*mm, "Golden Sample PCs · 9950X3D direct-die / ROG Crosshair X870E Extreme")
    canv.drawRightString(A4[0]-15*mm, 10*mm, "стр. %d" % doc.page)
    canv.setStrokeColor(colors.HexColor("#DDDDDD")); canv.setLineWidth(0.4)
    canv.line(15*mm, 13*mm, A4[0]-15*mm, 13*mm)
    canv.restoreState()

def main(out, files):
    doc = SimpleDocTemplate(out, pagesize=A4,
                            leftMargin=15*mm, rightMargin=15*mm, topMargin=14*mm, bottomMargin=16*mm,
                            title="9950X3D / X870E Extreme — разгон, профили, пошаговка",
                            author="Golden Sample PCs")
    avail = A4[0] - 30*mm
    story = []
    for k, f in enumerate(files):
        if k: story.append(PageBreak())
        build(open(f, encoding="utf-8").read(), story, avail)
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    print("OK ->", out, os.path.getsize(out), "bytes")

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:])
