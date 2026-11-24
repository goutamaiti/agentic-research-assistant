# -*- coding: utf-8 -*-
"""Build the NLP micro-project report PDF in the format of the department template.

Format taken from the template: US Letter, Times New Roman throughout (body 12 pt
justified, chapter titles 17 pt bold centred, section headings 14 pt bold, page numbers
11 pt bottom right), thick-thin triple page border, full-grid tables, centred bold
figure captions, cover page with college header and logo.
"""
import sys
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (BaseDocTemplate, Flowable, Frame, Image, KeepTogether,
                                PageBreak, PageTemplate, Paragraph, Spacer, Table,
                                TableStyle)

FONTS = r"C:\Windows\Fonts"
for name, f in (("TNR", "times.ttf"), ("TNR-B", "timesbd.ttf"),
                ("TNR-I", "timesi.ttf"), ("TNR-BI", "timesbi.ttf")):
    pdfmetrics.registerFont(TTFont(name, f"{FONTS}\\{f}"))
pdfmetrics.registerFontFamily("TNR", normal="TNR", bold="TNR-B", italic="TNR-I", boldItalic="TNR-BI")

BUILD = r"L:\NLP_RB\report_build"
OUT = BUILD + r"\Agentic_RAG_NLP_Micro_Project_Report.pdf"

# ------------------------------------------------------------------ details to fill
STUDENTS = [("Bhoomi Asapur", "2BA23AI011"), ("Rakshit Patil", "2BA23AI036"),
            ("Vaishnavi Bidnoor", "2BA23AI057"), ("Varsha Unki", "2BA23AI058")]
TITLE_LINES = ["\u201cAgentic RAG Framework for Automated Domain-Specific",
               "Knowledge Extraction from a Research Paper\u201d"]

NAVY = colors.Color(0 / 255, 31 / 255, 95 / 255)
BLUE = colors.Color(31 / 255, 70 / 255, 121 / 255)
RED = colors.Color(1, 0, 0)

PAGE_W, PAGE_H = 612, 792
LEFT, WIDTH = 70, 473
TOP_Y = PAGE_H - 54          # top of the text frame
BOTTOM_Y = 76

# ------------------------------------------------------------------ styles
BODY = ParagraphStyle("body", fontName="TNR", fontSize=12, leading=20.6, alignment=TA_JUSTIFY,
                      spaceAfter=14.4)
BODY_TIGHT = ParagraphStyle("bodyt", parent=BODY, spaceAfter=6)
LABEL = ParagraphStyle("label", parent=BODY, spaceAfter=6, keepWithNext=1)
CELL = ParagraphStyle("cell", fontName="TNR", fontSize=12, leading=14, alignment=TA_LEFT)
CELLC = ParagraphStyle("cellc", parent=CELL, alignment=TA_CENTER)
CELLH = ParagraphStyle("cellh", parent=CELL, fontName="TNR-B", alignment=TA_CENTER)
CH = ParagraphStyle("ch", fontName="TNR-B", fontSize=17, leading=22, alignment=TA_CENTER,
                    spaceAfter=16)
CH16 = ParagraphStyle("ch16", parent=CH, fontSize=16)
SEC = ParagraphStyle("sec", fontName="TNR-B", fontSize=14, leading=18, spaceBefore=10,
                     spaceAfter=10, keepWithNext=1)
SUB = ParagraphStyle("sub", fontName="TNR-B", fontSize=12, leading=16, spaceBefore=4,
                     spaceAfter=6, keepWithNext=1)
BUL = ParagraphStyle("bul", parent=BODY, leftIndent=29, bulletIndent=11, spaceAfter=5,
                     bulletFontName="TNR", bulletFontSize=12)
NUM = ParagraphStyle("num", parent=BODY, leftIndent=47, bulletIndent=22, spaceAfter=5,
                     bulletFontName="TNR", bulletFontSize=12)
CAP = ParagraphStyle("cap", fontName="TNR-B", fontSize=12, leading=16, alignment=TA_CENTER,
                     spaceBefore=6, spaceAfter=14)

REC = {}  # heading key -> (page, top y)


class Head(Paragraph):
    """Heading that records where it landed, for the table of contents."""

    def __init__(self, text, style, key=None):
        super().__init__(text, style)
        self.key = key

    def draw(self):
        if self.key:
            _x, y = self.canv.absolutePosition(0, 0)
            REC[self.key] = (self.canv.getPageNumber(), y + self.height)
        super().draw()


def P(text, style=BODY):
    return Paragraph(text, style)


def label_p(text):
    return Paragraph(text, LABEL)


def bullets(items, style=BUL):
    return [Paragraph(t, style, bulletText="\u2022") for t in items]


def numbered(items, start=1):
    return [Paragraph(t, NUM, bulletText=f"{i}.") for i, t in enumerate(items, start)]


def chapter(num, title, key, upper=False):
    label = f"{num}.&nbsp;&nbsp;&nbsp;{title.upper() if upper else title}"
    return [PageBreak(), Head(label, CH, key)]


def section(num, title, key):
    return Head(f"{num} {title}", SEC, key)


def table(rows, widths, header=True, center_cols=(), repeat=1):
    data = []
    for r, row in enumerate(rows):
        out = []
        for c, cell in enumerate(row):
            if r == 0 and header:
                out.append(Paragraph(cell, CELLH))
            else:
                out.append(Paragraph(cell, CELLC if c in center_cols else CELL))
        data.append(out)
    t = Table(data, colWidths=widths, repeatRows=repeat if header else 0)
    t.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.48, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]))
    return [t, Spacer(1, 14)]


# ------------------------------------------------------------------ page decoration
def border(c):
    x0, x1 = 24.5, 588.5
    y0, y1 = 25.0, 769.0          # measured from the top of the page in the template
    for off, w in ((0.35, 0.7), (2.95, 3.0), (5.5, 0.75)):
        c.setLineWidth(w)
        c.rect(x0 + off, PAGE_H - y1 + off, (x1 - x0) - 2 * off, (y1 - y0) - 2 * off)


def decorate(c, doc):
    c.saveState()
    c.setStrokeColor(colors.black)
    border(c)
    if doc.page >= 4:
        c.setFont("TNR", 11)
        c.drawRightString(571, PAGE_H - 737, str(doc.page))
    c.restoreState()


class Absolute(Flowable):
    """Flowable that draws in absolute page coordinates and fills one page."""

    def wrap(self, aw, ah):
        return aw, ah - 1

    def draw(self):
        x, y = self.canv.absolutePosition(0, 0)
        self.canv.saveState()
        self.canv.translate(-x, -y)
        self.paint(self.canv)
        self.canv.restoreState()


def centred(c, text, size, y_top, font="TNR-B", color=colors.black, x=PAGE_W / 2):
    c.setFont(font, size)
    c.setFillColor(color)
    c.drawCentredString(x, PAGE_H - (y_top + size * 0.89), text)


class Cover(Absolute):
    def paint(self, c):
        centred(c, "Shri B.V.V. Sangha\u2019s", 11, 70)
        centred(c, "BASAVESHWAR ENGINEERING COLLEGE, BAGALKOTE", 16, 90)
        centred(c, "[AICTE Approved, Government Aided Institution Affiliated To VTU, Belagavi]", 11, 119)
        c.drawImage(BUILD + r"\logo.png", 261, PAGE_H - 222, 90, 83, mask="auto")
        centred(c, "DEPARTMENT OF ARTIFICIAL INTELLIGENCE & MACHINE", 16, 231)
        centred(c, "LEARNING", 16, 249)
        # mixed-size red line
        a, b = "Micro-Project Report", " On Natural Language Processing (22UAI703E)"
        wa, wb = stringWidth(a, "TNR-B", 14), stringWidth(b, "TNR-B", 11)
        x = (PAGE_W - wa - wb) / 2
        c.setFillColor(RED)
        c.setFont("TNR-B", 14)
        c.drawString(x, PAGE_H - (278 + 14 * 0.89), a)
        c.setFont("TNR-B", 11)
        c.drawString(x + wa, PAGE_H - (278 + 14 * 0.89), b)
        centred(c, TITLE_LINES[0], 19, 304, color=NAVY)
        centred(c, TITLE_LINES[1], 19, 330, color=NAVY)
        centred(c, "Submitted in partial fulfillment of requirement for the award of the degree",
                12, 365, font="TNR-I")
        centred(c, "BACHELOR OF ENGINEERING", 14, 388)
        centred(c, "In", 14, 414)
        centred(c, "ARTIFICIAL INTELLIGENCE & MACHINE LEARNING", 11, 439)
        centred(c, "2026-2027", 14, 460)
        centred(c, "Course Coordinator", 14, 500, color=RED)
        centred(c, "Dr Vishwanath Kagawade", 14, 525)
        centred(c, "Submitted by:", 14, 586, font="TNR-BI")
        for i, (name, usn) in enumerate(STUDENTS):
            y = 623 + i * 17.4
            c.setFont("TNR-B", 12)
            c.setFillColor(BLUE)
            c.drawString(159, PAGE_H - (y + 12 * 0.89), name)
            c.drawString(385, PAGE_H - (y + 12 * 0.89), usn)
        c.setFillColor(colors.black)
        c.setFont("TNR-B", 12)
        c.drawString(159, PAGE_H - (716 + 12 * 0.89), "Date of Submission:")


TOC_ROWS = []   # (level, number, title, key)


class Toc(Absolute):
    def paint(self, c):
        centred(c, "TABLE OF CONTENTS", 16, 65)
        c.setFillColor(colors.black)
        c.setFont("TNR-B", 16)
        top = 93
        for label, x in (("Chapter", 52), ("Title", 172), ("P.No", 443)):
            c.drawString(x, PAGE_H - (top + 16 * 0.89), label)
        keys = [r[3] for r in TOC_ROWS]
        last = REC.get("_last", (0, 0))[0]
        chapters = [i for i, r in enumerate(TOC_ROWS) if r[0] == 0]
        y = 115
        for i, (level, num, title, key) in enumerate(TOC_ROWS):
            start = REC.get(key, (0, 0))[0]
            if level == 0:
                later = [j for j in chapters if j > i]
                nxt = TOC_ROWS[later[0]][3] if later else None
            else:
                nxt = keys[i + 1] if i + 1 < len(keys) else None
            if nxt and nxt in REC:
                npage, ny = REC[nxt]
                end = start if npage == start else (npage - 1 if ny > 700 else npage)
            else:
                end = last
            end = max(end, start)
            rng = f"{start}-{end}" if end > start else f"{start}"
            font = "TNR-B" if level == 0 else "TNR"
            c.setFont(font, 12)
            c.drawString(52 if level == 0 else 137, PAGE_H - (y + 12 * 0.89), num)
            c.setFont("TNR", 12)
            c.drawString(171, PAGE_H - (y + 12 * 0.89), title)
            c.setFont(font, 12)
            c.drawString(483, PAGE_H - (y + 12 * 0.89), rng)
            y += 18.6


# ------------------------------------------------------------------ diagrams
LIGHT = colors.Color(0.78, 0.88, 0.96)
DARK = colors.Color(0.08, 0.22, 0.45)
GREEN = colors.Color(0.1, 0.6, 0.25)
PURPLE = colors.Color(0.45, 0.2, 0.7)
REDL = colors.Color(0.85, 0.15, 0.15)


def box(c, x, y, w, h, text, size=7.2, fill=LIGHT, shape="rect", bold=True):
    c.setFillColor(fill)
    c.setStrokeColor(DARK)
    c.setLineWidth(0.8)
    if shape == "round":
        c.roundRect(x, y, w, h, h / 2, fill=1, stroke=1)
    elif shape == "para":
        p = c.beginPath()
        p.moveTo(x + 8, y)
        p.lineTo(x + w, y)
        p.lineTo(x + w - 8, y + h)
        p.lineTo(x, y + h)
        p.close()
        c.drawPath(p, fill=1, stroke=1)
    elif shape == "diamond":
        p = c.beginPath()
        p.moveTo(x + w / 2, y + h)
        p.lineTo(x + w, y + h / 2)
        p.lineTo(x + w / 2, y)
        p.lineTo(x, y + h / 2)
        p.close()
        c.drawPath(p, fill=1, stroke=1)
    else:
        c.roundRect(x, y, w, h, 2, fill=1, stroke=1)
    c.setFillColor(DARK)
    c.setFont("TNR-B" if bold else "TNR", size)
    lines = text.split("\n")
    ty = y + h / 2 + (len(lines) - 1) * size * 0.55 - size * 0.3
    for ln in lines:
        c.drawCentredString(x + w / 2, ty, ln)
        ty -= size * 1.1


def arrow(c, x1, y1, x2, y2, color=DARK, width=0.8):
    import math
    c.setStrokeColor(color)
    c.setFillColor(color)
    c.setLineWidth(width)
    c.line(x1, y1, x2, y2)
    ang = math.atan2(y2 - y1, x2 - x1)
    s = 3.6
    p = c.beginPath()
    p.moveTo(x2, y2)
    p.lineTo(x2 - s * math.cos(ang - 0.4), y2 - s * math.sin(ang - 0.4))
    p.lineTo(x2 - s * math.cos(ang + 0.4), y2 - s * math.sin(ang + 0.4))
    p.close()
    c.drawPath(p, fill=1, stroke=0)


class FlowChart(Flowable):
    H = 508

    def wrap(self, aw, ah):
        return WIDTH, self.H

    def draw(self):
        c = self.canv
        W, H = WIDTH, self.H
        c.setFillColor(DARK)
        c.setFont("TNR-B", 12)
        c.drawCentredString(W / 2, H - 14, "PROPOSED MODEL OF THE SYSTEM")
        c.setStrokeColor(colors.Color(0.7, 0.75, 0.85))
        c.line(0, H - 22, W, H - 22)
        cx, bw, bh, pitch = W / 2, 250, 19, 26.5
        y = H - 22 - 10 - bh
        chain = [
            ("START", "round"),
            ("UPLOAD RESEARCH PAPER (PDF, UP TO 30 MB)", "para"),
            ("VALIDATE FILE (TYPE, SIZE, PAGE COUNT)", "rect"),
            ("EXTRACT PAGE TEXT (PyMuPDF; TESSERACT OCR FOR SCANNED PAGES)", "rect"),
            ("DETECT SECTIONS, METADATA AND PRINTED PAGE NUMBERS", "rect"),
            ("SPLIT TEXT INTO SECTION-AWARE CHUNKS (220 TOKENS, 40 OVERLAP)", "rect"),
        ]
        prev = None
        for text, shape in chain:
            sz = 6.6 if len(text) > 48 else 7.2
            ww = max(bw, stringWidth(text, "TNR-B", sz) + 24)
            box(c, cx - ww / 2, y, ww, bh, text, shape=shape, size=sz)
            if prev is not None:
                arrow(c, cx, prev, cx, y + bh)
            prev = y
            y -= pitch
        # two parallel index branches
        bw2 = 180
        lx, rx = cx - 105, cx + 105
        box(c, lx - bw2 / 2, y - 6, bw2, bh + 12, "EMBED CHUNKS (SENTENCE TRANSFORMERS)\nSTORE VECTORS IN CHROMADB", size=6.6)
        box(c, rx - 70, y - 6, 140, bh + 12, "BUILD BM25 KEYWORD\nINDEX FROM CHUNKS", size=6.6)
        arrow(c, cx, prev, lx, y + bh + 6)
        arrow(c, cx, prev, rx, y + bh + 6)
        join_y = y - 6
        y -= pitch + 14
        box(c, cx - 70, y, 140, bh, "PAPER INDEXED", shape="round")
        arrow(c, lx, join_y, cx - 30, y + bh)
        arrow(c, rx, join_y, cx + 30, y + bh)
        prev = y
        y -= pitch
        for text, shape in [
            ("EXTRACT KNOWLEDGE: 3 PARALLEL GEMINI CALLS, A QUOTE FOR EVERY CLAIM", "rect"),
            ("LOCATE EACH QUOTE IN THE STORED TEXT (EXACT / NORMALISED / NOT FOUND)", "rect"),
            ("VERIFY CLAIMS (CODE RULES + LLM JUDGEMENT), STORE ANALYSIS IN SQLITE", "rect"),
            ("USER ASKS A QUESTION ABOUT THE PAPER", "para"),
            ("HYBRID RETRIEVAL: SEMANTIC + BM25 MERGED WITH RRF", "rect"),
            ("GENERATE ANSWER FROM RETRIEVED PASSAGES WITH CITATIONS (GEMINI)", "rect"),
        ]:
            sz = 6.4 if len(text) > 56 else 7.2
            ww = max(bw, stringWidth(text, "TNR-B", sz) + 24)
            box(c, cx - ww / 2, y, ww, bh, text, shape=shape, size=sz)
            arrow(c, cx, prev, cx, y + bh)
            prev = y
            y -= pitch
        # decision
        dh = 30
        y -= 4
        box(c, cx - 62, y - 4, 124, dh, "VALID CITATION?", shape="diamond", size=7)
        arrow(c, cx, prev, cx, y - 4 + dh)
        dy = y - 4 + dh / 2
        box(c, 6, y - 6, 150, 26, "SHOW ANSWER WITH\nPAGE REFERENCES", size=6.6)
        box(c, W - 156, y - 6, 150, 26, "SHOW \u201cINSUFFICIENT\nEVIDENCE\u201d NOTICE", size=6.6)
        arrow(c, cx - 62, dy, 156, dy)
        arrow(c, cx + 62, dy, W - 156, dy)
        c.setFillColor(DARK)
        c.setFont("TNR-B", 6.4)
        c.drawCentredString((156 + cx - 62) / 2, dy + 3, "YES")
        c.drawCentredString((cx + 62 + W - 156) / 2, dy + 3, "NO")
        yy = y - 6 - 18
        box(c, cx - bw / 2, yy - 6, bw, bh, "SAVE QUESTION AND ANSWER IN CONVERSATION HISTORY", size=6.6)
        arrow(c, 81, y - 6, cx - 60, yy - 6 + bh)
        arrow(c, W - 81, y - 6, cx + 60, yy - 6 + bh)
        box(c, cx - 35, yy - 6 - pitch, 70, bh, "END", shape="round")
        arrow(c, cx, yy - 6, cx, yy - 6 - pitch + bh)


class BlockDiagram(Flowable):
    H = 360

    def wrap(self, aw, ah):
        return WIDTH, self.H

    def draw(self):
        c = self.canv
        W, H = WIDTH, self.H
        c.setFillColor(colors.Color(0.95, 0.97, 1.0))
        c.setStrokeColor(colors.Color(0.8, 0.85, 0.93))
        c.rect(0, 0, W, H, fill=1, stroke=1)
        c.setFillColor(DARK)
        c.setFont("TNR-B", 11.5)
        c.drawCentredString(W / 2, H - 20, "BLOCK DIAGRAM OF THE AGENTIC RAG RESEARCH ASSISTANT")
        # ---- user column
        ux, uw = 10, 92
        c.setFillColor(colors.white)
        c.setStrokeColor(DARK)
        c.roundRect(ux, 68, uw, 246, 4, fill=1, stroke=1)
        c.setFillColor(LIGHT)
        c.rect(ux, 294, uw, 20, fill=1, stroke=1)
        c.setFillColor(DARK)
        c.setFont("TNR-B", 8)
        c.drawCentredString(ux + uw / 2, 300, "USER")
        c.setFillColor(DARK)
        c.circle(ux + uw / 2, 270, 7, fill=1, stroke=0)
        c.roundRect(ux + uw / 2 - 12, 247, 24, 15, 5, fill=1, stroke=0)
        c.setFont("TNR", 6.8)
        for i, t in enumerate(["\u2022 Upload a paper (PDF)", "\u2022 Watch the progress", "\u2022 Read claims, quotes",
                               "   and page numbers", "\u2022 Filter by status", "\u2022 Ask questions",
                               "\u2022 Download PDF / JSON", "   report"]):
            c.drawString(ux + 5, 232 - i * 12, t)
        # ---- web application
        wx, ww = 128, 206
        c.setFillColor(colors.white)
        c.roundRect(wx, 46, ww, 276, 4, fill=1, stroke=1)
        c.setFillColor(LIGHT)
        c.rect(wx, 292, ww, 30, fill=1, stroke=1)
        c.setFillColor(DARK)
        c.setFont("TNR-B", 8)
        c.drawCentredString(wx + ww / 2, 309, "WEB APPLICATION")
        c.setFont("TNR", 6.8)
        c.drawCentredString(wx + ww / 2, 298, "React interface + FastAPI backend + LangGraph workflow")
        stages = ["1  Upload validation", "2  Text extraction and OCR", "3  Sections and metadata",
                  "4  Chunking and indexing", "5  Knowledge extraction (Gemini)",
                  "6  Evidence verification (Gemini)", "7  Research assistant (cited answers)"]
        sy = 266
        for i, t in enumerate(stages):
            box(c, wx + 10, sy, ww - 20, 24, t, size=7.4, fill=colors.Color(0.86, 0.93, 0.98) if i < 4 else colors.Color(1, 0.93, 0.8))
            sy -= 31
        # ---- data storage
        dx, dw = 362, 100
        c.setFillColor(colors.white)
        c.roundRect(dx, 150, dw, 172, 4, fill=1, stroke=1)
        c.setFillColor(LIGHT)
        c.rect(dx, 302, dw, 20, fill=1, stroke=1)
        c.setFillColor(DARK)
        c.setFont("TNR-B", 8)
        c.drawCentredString(dx + dw / 2, 308, "DATA STORAGE")
        store = [("SQLITE", "papers, pages, chunks,\nclaims, chat history"),
                 ("CHROMADB", "one vector collection\nper paper"),
                 ("BM25 INDEX", "keyword index built\nfrom stored chunks"),
                 ]
        yy = 262
        for name, desc in store:
            c.setFillColor(colors.Color(0.9, 0.95, 0.99))
            c.roundRect(dx + 6, yy - 6, dw - 12, 40, 3, fill=1, stroke=1)
            c.setFillColor(DARK)
            c.setFont("TNR-B", 7.2)
            c.drawCentredString(dx + dw / 2, yy + 24, name)
            c.setFont("TNR", 6.4)
            for k, ln in enumerate(desc.split("\n")):
                c.drawCentredString(dx + dw / 2, yy + 12 - k * 8, ln)
            yy -= 50
        # files
        c.setFillColor(colors.Color(0.9, 0.95, 0.99))
        c.roundRect(dx, 98, dw, 40, 3, fill=1, stroke=1)
        c.setFillColor(DARK)
        c.setFont("TNR-B", 7.2)
        c.drawCentredString(dx + dw / 2, 124, "FILE STORAGE")
        c.setFont("TNR", 6.4)
        c.drawCentredString(dx + dw / 2, 112, "uploaded PDFs and")
        c.drawCentredString(dx + dw / 2, 104, "generated reports")
        # gemini
        c.setFillColor(colors.Color(1, 0.93, 0.8))
        c.roundRect(dx, 46, dw, 40, 3, fill=1, stroke=1)
        c.setFillColor(DARK)
        c.setFont("TNR-B", 7.2)
        c.drawCentredString(dx + dw / 2, 72, "GEMINI API")
        c.setFont("TNR", 6.4)
        c.drawCentredString(dx + dw / 2, 60, "structured JSON answers")
        c.drawCentredString(dx + dw / 2, 52, "(external service)")
        # arrows
        arrow(c, ux + uw, 200, wx, 200, GREEN, 1.2)
        arrow(c, wx, 150, ux + uw, 150, GREEN, 1.2)
        arrow(c, wx + ww, 238, dx, 238, PURPLE, 1.2)
        arrow(c, dx, 188, wx + ww, 188, PURPLE, 1.2)
        arrow(c, wx + ww, 72, dx, 72, REDL, 1.2)
        arrow(c, dx, 58, wx + ww, 58, REDL, 1.2)
        c.setFont("TNR", 6)
        c.setFillColor(DARK)
        c.drawCentredString((ux + uw + wx) / 2, 212, "Uploads,")
        c.drawCentredString((ux + uw + wx) / 2, 205, "questions")
        c.drawCentredString((ux + uw + wx) / 2, 140, "Answers,")
        c.drawCentredString((ux + uw + wx) / 2, 133, "results")
        # legend
        c.setFillColor(colors.white)
        c.setStrokeColor(DARK)
        c.setLineWidth(0.8)
        c.rect(10, 8, 452, 28, fill=1, stroke=1)
        c.setFillColor(DARK)
        c.setFont("TNR-B", 7)
        c.drawString(16, 25, "LEGEND")
        arrow(c, 62, 27, 92, 27, GREEN, 1.2)
        c.setFont("TNR", 6.8)
        c.drawString(97, 25, "User interaction")
        arrow(c, 176, 27, 206, 27, PURPLE, 1.2)
        c.drawString(211, 25, "Storage reads and writes")
        arrow(c, 316, 27, 346, 27, REDL, 1.2)
        c.drawString(351, 25, "LLM requests and replies")
        c.setFillColor(DARK)
        c.setFont("TNR", 6.2)
        c.drawString(16, 13, "Stages 5 to 7 (highlighted) are the only parts that call the LLM; stages 1 to 4 run locally.")


DESC = ParagraphStyle("desc", fontName="TNR", fontSize=11.5, leading=14.5, alignment=TA_JUSTIFY,
                      spaceAfter=12)
CAP_D = ParagraphStyle("capd", parent=CAP, spaceAfter=2)
REPO = "https://github.com/goutamaiti/agentic-research-assistant"


def figure(path, caption, width=440, ratio=None, desc=None):
    from PIL import Image as PILImage
    w, h = PILImage.open(path).size
    img = Image(path, width=width, height=width * h / w)
    img.hAlign = "CENTER"
    box_t = Table([[img]], colWidths=[width + 4])
    box_t.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.6, colors.Color(0.5, 0.5, 0.5)),
                               ("LEFTPADDING", (0, 0), (-1, -1), 1), ("RIGHTPADDING", (0, 0), (-1, -1), 1),
                               ("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 1)]))
    if desc:
        return KeepTogether([box_t, P(caption, CAP_D), P(desc, DESC)])
    return KeepTogether([box_t, P(caption, CAP)])


# ------------------------------------------------------------------ source code appendix
pdfmetrics.registerFont(TTFont("MONO", f"{FONTS}\\consola.ttf"))
pdfmetrics.registerFont(TTFont("MONO-B", f"{FONTS}\\consolab.ttf"))
ROOT = r"L:\NLP_RB"
CODE_FONT, CODE_LEAD = 7.0, 8.4
CODE_COLS = int(WIDTH // (CODE_FONT * 0.55)) - 1
CODE = ParagraphStyle("code", fontName="MONO", fontSize=CODE_FONT, leading=CODE_LEAD)
CODE_H = ParagraphStyle("codeh", fontName="MONO-B", fontSize=9, leading=11, spaceBefore=8, spaceAfter=3,
                        keepWithNext=1)
CODE_SKIP = ("backend/alembic/versions/", "backend/alembic/README")


def code_files():
    """(path, line count) of tracked source files, in a stable order."""
    import subprocess
    out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True)
    names = [f for f in out.stdout.decode("utf-8").split("\0") if f]
    keep = []
    for f in names:
        if f.startswith(CODE_SKIP) or f.startswith(("backend/tests/", "backend/scripts/")):
            continue
        ok = (f.startswith(("backend/app/", "frontend/src/")) and f.endswith((".py", ".js", ".jsx", ".css"))) \
            or f in ("backend/alembic/env.py", "Dockerfile", "run.bat", "run.sh", "share.bat")
        if not ok or f.endswith("__init__.py"):
            continue
        with open(f"{ROOT}\\{f}", encoding="utf-8", errors="replace") as fh:
            n = len(fh.read().splitlines())
        if n:
            keep.append((f, n))
    order = {"backend": 0, "frontend": 1}
    keep.sort(key=lambda t: (order.get(t[0].split("/")[0], 2), t[0]))
    return keep


def code_index_table(rows):
    cs = ParagraphStyle("ci", fontName="MONO", fontSize=8, leading=10)
    csh = ParagraphStyle("cih", fontName="TNR-B", fontSize=11, leading=13, alignment=TA_CENTER)
    data = [[Paragraph(r[0], csh if i == 0 else cs), Paragraph(r[1], csh if i == 0 else
            ParagraphStyle("cn", parent=cs, alignment=TA_CENTER))] for i, r in enumerate(rows)]
    t = Table(data, colWidths=[400, 73], repeatRows=1)
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.48, colors.black), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                           ("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))
    return [Spacer(1, 4), t]


def wrap_line(s):
    s = s.expandtabs(4).rstrip()
    if len(s) <= CODE_COLS:
        return [s]
    indent = len(s) - len(s.lstrip())
    out, first = [], True
    while len(s) > CODE_COLS:
        out.append(s[:CODE_COLS])
        s = " " * (indent + 4) + s[CODE_COLS:]
    out.append(s)
    return out


def code_story():
    from reportlab.platypus import Preformatted
    S = [PageBreak(), Head("<a name=\"code_start\"/>Source Code Listing", CH16, "code")]
    for path, _n in code_files():
        with open(f"{ROOT}\\{path}", encoding="utf-8", errors="replace") as fh:
            lines = [w for l in fh.read().splitlines() for w in wrap_line(l)]
        S += [Paragraph(path, CODE_H), Preformatted("\n".join(lines), CODE)]
    return S


# ------------------------------------------------------------------ content
def build_story():
    S = []
    TOC_ROWS.clear()

    def reg(level, num, title, key):
        TOC_ROWS.append((level, num, title, key))

    # ---------------- cover, abstract, TOC
    S += [Cover(), PageBreak()]
    S += [Spacer(1, 4), Paragraph("ABSTRACT", ParagraphStyle("abs", parent=CH16, spaceAfter=14))]
    S += [
        P("The Agentic RAG Framework for Automated Domain-Specific Knowledge Extraction is a web-based "
          "research assistant that reads one academic paper in PDF form and converts it into structured, "
          "evidence-backed knowledge. The system combines Natural Language Processing (NLP), "
          "Retrieval-Augmented Generation (RAG) and a Large Language Model (LLM) agent workflow to extract "
          "the research problem, objectives, methodology, algorithms, datasets, experimental setup, results, "
          "limitations, contributions and terminology, and it links every extracted claim to a word-for-word "
          "quotation and a printed page number in the paper."),
        P("Ordinary LLM summaries can sound fluent while inventing details or giving no source. The proposed "
          "system addresses this by requiring a quotation for every claim, checking by program code that the "
          "quotation really exists in the stored paper text, and then verifying each claim against its "
          "quotation. Every claim receives one of five statuses: verified, partially supported, unsupported, "
          "contradicted or not verifiable. A claim is never marked verified by default, and system "
          "interpretations are labelled separately from the authors\u2019 own statements."),
        P("Text is extracted with PyMuPDF, and scanned pages are read with Tesseract OCR. The text is split into "
          "section-aware chunks, embedded with Sentence Transformers and stored in ChromaDB, while a BM25 keyword "
          "index runs alongside it. Hybrid retrieval merges both rankings with Reciprocal Rank Fusion. The "
          "seven-stage analysis is orchestrated with LangGraph, and Google Gemini 3.8 Flash produces schema-"
          "constrained JSON. A research assistant answers questions about the paper with page citations, or states "
          "clearly that the paper does not contain enough evidence. The application uses React, Vite and Tailwind "
          "CSS for the frontend, and Python, FastAPI and SQLite for the backend."),
        P("On the test paper \u201cAttention Is All You Need\u201d (15 pages), a complete analysis takes about two "
          "minutes and produced 113 claims, of which 78 were verified against the paper\u2019s own text. "
          "A total of 343 automated backend tests and 5 frontend tests pass. The main objective is to give "
          "researchers and students a trustworthy way to read a paper quickly while being able to check every "
          "statement against its source."),
        P("<b>Source code:</b> <a href=\"%s\" color=\"#1F4679\"><u>%s</u></a>" % (REPO, REPO)),
    ]
    S += [PageBreak(), Toc(), PageBreak()]

    # ---------------- 1 Introduction
    reg(0, "1", "Introduction", "c1")
    S += [Head("1.&nbsp;&nbsp;&nbsp;INTRODUCTION", CH, "c1")]
    reg(1, "1.1", "Overview", "s1.1")
    S += [section("1.1", "Overview", "s1.1")]
    S += [
        P("The Agentic RAG Framework is a web-based application that helps a reader understand a single research "
          "paper quickly and check what is said about it. The user uploads one academic paper as a PDF. The system "
          "reads it, organises it into sections, extracts structured knowledge and presents it in a form in which "
          "every statement can be traced back to the paper."),
        P("Reading research papers is slow, and summaries produced by language models are risky because they can "
          "contain details that are not in the paper at all. This project treats the paper as the only source of "
          "truth. The language model is asked to quote the passage that supports each claim, program code checks "
          "that the quotation exists in the paper text, and a verification step records how well the quotation "
          "supports the claim."),
        P("The system is agentic because the analysis is not a single prompt. It is a workflow of separate steps "
          "with their own tools, state and failure handling: validation, text extraction, section detection, "
          "indexing, knowledge extraction, verification and finalisation. A separate research assistant answers "
          "free-form questions using the same retrieval index."),
        P("The project is developed with React, Vite and Tailwind CSS for the frontend, Python and FastAPI for "
          "the backend, PyMuPDF and Tesseract for document processing, Sentence Transformers, ChromaDB and BM25 "
          "for retrieval, LangGraph for orchestration, SQLite for storage and Google Gemini for language "
          "understanding."),
    ]
    reg(1, "1.2", "Scope", "s1.2")
    S += [section("1.2", "Scope", "s1.2")]
    S += [
        P("The scope of the project is a single-paper analysis and question-answering tool. A user can upload one "
          "PDF of up to 30 MB, follow the progress of the analysis stage by stage, read the extracted knowledge "
          "organised in fourteen categories, inspect the quotation behind every claim, filter claims by "
          "verification status, ask questions about the paper and download the result as a PDF or JSON report."),
        P("The extracted categories are the research problem, objectives, motivation, background, methodology, "
          "algorithms and models, datasets, experimental setup, results, limitations, future scope, research "
          "contributions, a step-by-step methodology breakdown and technical terminology, together with paper "
          "metadata such as title, authors, year and venue."),
        P("The project deliberately does not compare several papers, understand figures and tables as images, or "
          "judge whether a paper\u2019s scientific conclusions are correct. These topics are listed as future "
          "work. Because the work was carried out as a micro project, the scope was reduced and recorded formally "
          "in the project context document, so that the delivered system is smaller but fully tested."),
    ]
    reg(1, "1.3", "Need for the Project", "s1.3")
    S += [section("1.3", "Need for the Project", "s1.3")]
    S += [
        P("Students, researchers and reviewers read many papers, and each one takes time. Skimming an abstract is "
          "quick but incomplete, and reading every page to find the dataset, the hyperparameters or the "
          "limitations is slow. General-purpose chatbots can answer questions about a paper, but they do not "
          "show where an answer comes from, and they may state details that the paper never contains."),
        P("The need is therefore not only for faster reading but for trustworthy reading. A reader should be able "
          "to see a claim, see the exact quotation behind it, see the page it came from and see whether an "
          "automatic check agrees. Where the paper does not say something, the system should say so instead of "
          "guessing."),
        P("The Agentic RAG Framework meets this need by combining retrieval, structured extraction and "
          "verification in one tool. It reduces the time to understand a paper while keeping the reader in "
          "control of what to believe."),
    ]
    reg(1, "1.4", "Features of the System", "s1.4")
    S += [section("1.4", "Features of the System", "s1.4")]
    S += bullets([
        "<b>PDF processing:</b> text extraction with page numbers, automatic OCR for scanned pages, section and "
        "metadata detection.",
        "<b>Hybrid retrieval:</b> semantic search and BM25 keyword search merged with Reciprocal Rank Fusion.",
        "<b>Structured extraction:</b> fourteen knowledge categories produced as schema-checked JSON, with a "
        "quotation for every claim.",
        "<b>Evidence linking:</b> every quotation is located in the stored paper text; a quotation that cannot "
        "be found receives no page reference.",
        "<b>Claim verification:</b> five statuses shown as text and a symbol, never by colour alone.",
        "<b>Origin labels:</b> author-claimed, directly extracted, system-inferred and system-explanation "
        "statements are kept apart.",
        "<b>Cited question answering:</b> answers with page citations, or an explicit insufficient-evidence reply.",
        "<b>Reports and sharing:</b> PDF and JSON reports, one-click launchers and an optional access password.",
    ])
    reg(1, "1.5", "Benefits of the System", "s1.5")
    S += [section("1.5", "Benefits of the System", "s1.5")]
    S += [
        P("The main benefit is saved time: a structured overview of a fifteen-page paper is ready in about two "
          "minutes. The second benefit is trust, because each claim carries its quotation, page and verification "
          "status, so a reader can confirm it in seconds. The third is honesty about gaps: values that are not "
          "present, such as a missing DOI, are shown as \u201cnot found in the paper\u201d rather than invented."),
        P("The system also runs on an ordinary laptop. Embeddings, indexes and the database are local, and only "
          "the selected passages are sent to the language model service. A friend or a guide can run the whole "
          "project with a single click, which makes it easy to demonstrate and to evaluate."),
    ]

    # ---------------- 2 Problem Statement
    reg(0, "2", "Problem Statement", "c2")
    S += chapter("2", "Problem Statement", "c2")
    reg(1, "2.1", "Problem Definition", "s2.1")
    S += [section("2.1", "Problem Definition / Aim of the Project", "s2.1")]
    S += [
        P("Finding what a research paper actually says about its problem, method, data and results usually means "
          "reading it from beginning to end. Automatic summaries are faster, but they are not tied to the "
          "source text, so the reader cannot tell which sentences are supported by the paper and which were "
          "invented by the model. The core problem is the lack of a tool that extracts knowledge from a paper "
          "quickly <i>and</i> proves each statement against the paper itself."),
        P("The aim of the project is to build a single-paper research assistant that extracts structured knowledge "
          "with a verbatim quotation and page number for every claim, verifies each claim automatically, labels "
          "the origin of each statement, and answers questions only from the paper."),
    ]
    reg(1, "2.2", "Challenges", "s2.2")
    S += [section("2.2", "Challenges", "s2.2")]
    ch = [
        ("Reliable text from PDFs:", "Papers have two-column layouts, headers, footers, vertical margin text and "
         "sometimes only scanned images. Page numbers printed on the page often differ from the PDF page index."),
        ("Grounding and hallucination:", "A language model may produce a plausible claim with a quotation that "
         "does not exist, or a quotation that does not support the claim."),
        ("Finding the right passages:", "Keyword search misses paraphrases, while meaning-based search can miss "
         "exact terms, numbers and acronyms."),
        ("Reliable structured output:", "During development the model omitted optional JSON fields, truncated "
         "long answers and sometimes hit quota limits, so the extraction had to be designed to tolerate this."),
        ("Trustworthy verification:", "The verifier must be strict enough to catch unsupported claims and must "
         "never mark a claim as verified when evidence is missing."),
    ]
    for i, (lab, txt) in enumerate(ch, 1):
        S += [Paragraph(f"{i}.&nbsp;<b>{lab}</b>", LABEL)] + bullets([txt])
    reg(1, "2.3", "Limitations", "s2.3")
    S += [section("2.3", "Limitations", "s2.3")]
    lim = [
        ("Internet connection:", "Language-model calls to Google Gemini need an internet connection and an API key."),
        ("Paper quality and format:", "Heavily formatted tables, equations and figures are read as plain text only, "
         "and OCR quality on poor scans has not been measured."),
        ("Verification accuracy:", "The verifier is itself an LLM and can be wrong; its verdicts can differ between "
         "runs, so every status is a reading aid and not a final judgement."),
        ("Evaluation size:", "Quantitative results come from one paper and draft labels and must be extended."),
    ]
    for i, (lab, txt) in enumerate(lim, 1):
        S += [Paragraph(f"{i}.&nbsp;<b>{lab}</b>", LABEL)] + bullets([txt])
    reg(1, "2.4", "Applications", "s2.4")
    S += [section("2.4", "Applications", "s2.4")]
    app = [
        ("Students:", "Quickly understand the method, data and results of a paper before reading it in detail."),
        ("Researchers and literature reviews:", "Collect the problem, method and limitations of many papers one "
         "by one with quotations ready to cite."),
        ("Guides and reviewers:", "Check what a paper really claims and where, using the evidence view."),
        ("Technical reading:", "Extract requirements and parameters from standards, reports and manuals."),
    ]
    for i, (lab, txt) in enumerate(app, 1):
        S += [Paragraph(f"{i}.&nbsp;<b>{lab}</b>", LABEL)] + bullets([txt])

    # ---------------- 3 SRS
    reg(0, "3", "Software Requirement Specification", "c3")
    S += [PageBreak(), Head("3.&nbsp;&nbsp;&nbsp;Software Requirement Specification", CH, "c3")]
    reg(1, "3.1", "User Requirements", "s3.1")
    S += [section("3.1", "User Requirements", "s3.1")]
    S += bullets(["<b>Functional:</b> the system must let a user upload a research paper, analyse it "
                  "automatically, inspect the evidence behind each claim and ask questions about the paper."])
    S += numbered([
        "<b>Paper upload:</b> the user can upload one PDF and see its processing progress.",
        "<b>Structured analysis:</b> metadata and fourteen knowledge categories are shown with page references.",
        "<b>Evidence inspection:</b> each claim shows its quotation, page, origin and verification status.",
        "<b>Question answering:</b> answers cite pages; unanswerable questions get an explicit notice.",
        "<b>Export:</b> the analysis can be downloaded as a PDF or JSON report.",
    ])
    S += bullets(["<b>Non-Functional:</b> the system should be trustworthy, easy to use and quick enough "
                  "for interactive study."])
    S += numbered([
        "<b>Trustworthiness:</b> no statement is shown as verified without evidence in the paper.",
        "<b>Usability:</b> a simple interface with four pages and plain-language messages.",
        "<b>Accessibility:</b> statuses use text and symbols, keyboard focus is visible, and layouts work on phones.",
        "<b>Performance:</b> a typical paper is analysed within a few minutes.",
    ])
    reg(1, "3.2", "System Requirements", "s3.2")
    S += [section("3.2", "System Requirements", "s3.2")]
    S += bullets(["<b>Functional:</b> the system must integrate document processing, retrieval, an LLM "
                  "service, verification logic and persistent storage."])
    S += numbered([
        "<b>Document processing:</b> PDF parsing with page labels, OCR fallback, section detection and chunking.",
        "<b>Retrieval:</b> embeddings in ChromaDB, BM25 keyword search and Reciprocal Rank Fusion.",
        "<b>LLM integration:</b> schema-constrained JSON output from Google Gemini, with retry and quota handling.",
        "<b>Background processing:</b> analysis runs in a background job with stage-by-stage status and recovery "
        "after a restart.",
        "<b>Persistence:</b> SQLite with versioned migrations for documents, pages, chunks, analyses and chats.",
    ])
    S += bullets(["<b>Non-Functional:</b> the architecture must be reliable, modular, secure and easy "
                  "to install."])
    S += numbered([
        "<b>Reliability:</b> the LLM stages are non-fatal, so a paper is still indexed if the service is unavailable.",
        "<b>Maintainability:</b> separate modules with typed schemas and an automated test suite.",
        "<b>Security:</b> API keys stay in a local .env file; text from papers is sanitised before prompts; an "
        "optional access password protects public sharing.",
        "<b>Data integrity:</b> stable claim and evidence identifiers and foreign-key constraints.",
        "<b>Portability:</b> one-click launchers for Windows and macOS/Linux and a Docker image.",
    ])

    # ---------------- 4 System Design
    reg(0, "4", "System Design", "c4")
    S += [PageBreak(), Head("4.&nbsp;&nbsp;&nbsp;System Design", CH, "c4")]
    reg(1, "4.1", "Methodology", "s4.1")
    S += [section("4.1", "Methodology", "s4.1")]
    S += [P("The project was developed in small, tested steps. Each step produced working code, automated "
            "tests and an entry in the development log before the next step began.")]
    meth = [
        ("Document processing:", "Pages are parsed with PyMuPDF, scanned pages are read with Tesseract OCR, "
         "headings are detected from font size and numbering, and the text is cut into section-aware chunks."),
        ("Retrieval and indexing:", "Chunks are embedded with the multi-qa-mpnet-base-cos-v1 model and stored "
         "in ChromaDB, with a BM25 index built from the same chunks."),
        ("LLM integration:", "Gemini is called through a small service layer that enforces a JSON schema, "
         "retries safely and stops quickly when the quota is exhausted."),
        ("Agentic workflow:", "LangGraph connects seven stages and routes a failed processing stage to the end "
         "of the graph, while the two LLM stages are allowed to fail without losing the indexed paper."),
        ("Verification:", "Quotations are located in the text by code, and an LLM judges whether each "
         "quotation supports its claim; a number that does not appear in the quotation lowers the status."),
        ("Assistant and interface:", "A research assistant answers with validated citations, and a four-page "
         "React interface presents the analysis, evidence and chat."),
        ("Evaluation:", "Automated tests, a real end-to-end run and small retrieval and verification "
         "evaluations measure the system honestly, including where it does not do better."),
    ]
    S += numbered([f"<b>{a}</b> {b}" for a, b in meth])
    reg(1, "4.2", "Proposed Model", "s4.2")
    S += [PageBreak(), section("4.2", "Proposed Model", "s4.2")]
    S += [P("Figure 4.2.1 shows the complete flow of the proposed system, from uploading a paper to saving a "
            "cited answer. The left part indexes the paper, the middle part extracts and verifies knowledge, and "
            "the lower part answers user questions."), Spacer(1, 2), FlowChart(),
          P("Figure 4.2.1: proposed model of the system", CAP)]
    reg(1, "4.3", "Data Flow Design", "s4.3")
    S += [PageBreak(), section("4.3", "Data Flow Design", "s4.3")]
    S += [P("The data moves through the system in the following order:", BODY_TIGHT)]
    S += numbered([
        "<b>User interaction:</b> the browser uploads the PDF to the FastAPI backend and polls the status endpoint.",
        "<b>Document processing flow:</b> the file is validated, stored, and its text, sections and metadata are "
        "extracted and saved in SQLite.",
        "<b>Indexing flow:</b> chunks are embedded into ChromaDB, and the same chunks feed the BM25 keyword search.",
        "<b>Extraction flow:</b> three parallel Gemini calls receive only the retrieved passages and return JSON "
        "claims with quotations.",
        "<b>Verification flow:</b> each quotation is located in the stored text and each claim receives a status.",
        "<b>Question answering flow:</b> a question is retrieved against, answered with citations and saved with "
        "its conversation.",
    ])
    S += [Spacer(1, 6), BlockDiagram(), P("Fig 4.3.1 Block Diagram", CAP)]

    # ---------------- 5 Implementation
    reg(0, "5", "System Development / Implementation", "c5")
    S += [PageBreak(), Head("5.&nbsp;&nbsp;&nbsp;System Development / Implementation", CH, "c5")]
    reg(1, "5.1", "Development Environment", "s5.1")
    S += [section("5.1", "Development Environment", "s5.1")]
    S += [label_p("<b>Development Setup:</b>")]
    S += bullets([
        "<b>Operating System:</b> Windows 11, used for development, execution and testing.",
        "<b>Python environment:</b> Python 3.12 with a project-specific virtual environment (.venv).",
        "<b>Dependencies:</b> exact versions are listed in requirements.txt and installed with pip; the frontend "
        "uses npm.",
        "<b>Configuration:</b> the Gemini API key and optional settings are read from backend/.env, which is "
        "never committed to the repository.",
        "<b>Application server:</b> Uvicorn serves FastAPI and the built React interface on one address.",
    ])
    S += [label_p("<b>Tools and Libraries Used:</b>")]
    S += table([
        ["Tool / Library", "Purpose in the Project"],
        ["Python 3.12", "Main programming language for the backend."],
        ["FastAPI, Uvicorn", "REST endpoints, validation and the ASGI server."],
        ["React, Vite, Tailwind CSS", "Browser interface, build tool and base styles."],
        ["PyMuPDF, pdfplumber", "Extract page text, positions and page labels from PDFs."],
        ["Tesseract (pytesseract)", "OCR for pages without a text layer."],
        ["Sentence Transformers", "Embed chunks and questions (multi-qa-mpnet-base-cos-v1)."],
        ["ChromaDB", "Local vector store, one collection per paper."],
        ["rank-bm25", "Keyword ranking over the stored chunks."],
        ["LangGraph", "Seven-stage analysis workflow with shared state."],
        ["Google Gemini (google-genai)", "Structured extraction, verification and answers."],
        ["SQLAlchemy, Alembic, SQLite", "Database access and versioned schema migrations."],
        ["ReportLab", "PDF report generation."],
        ["pytest, Vitest, ruff", "Automated tests and code checks."],
    ], [150, 323])
    S += [label_p("<b>Hardware and Connectivity:</b>")]
    S += bullets([
        "A standard Windows, macOS or Linux laptop with Python 3.12 or newer; no GPU is required.",
        "Internet connectivity for the Gemini service and for the first download of the embedding model "
        "(about 420 MB).",
    ])
    reg(1, "5.2", "Frontend Development", "s5.2")
    S += [section("5.2", "Frontend Development", "s5.2")]
    S += [P("The frontend is a React application built with Vite. It has four pages reached by hash routing, "
            "and it talks only to same-origin /api paths, so no backend address or secret is stored in the "
            "browser bundle.", BODY)]
    S += [label_p("<b>Main Interface Components:</b>")]
    S += bullets([
        "<b>Upload page:</b> uploads a PDF, lists papers with their status, shows stage-by-stage progress and "
        "the backend health.",
        "<b>Analysis page:</b> metadata, fourteen categories with a status symbol, a verification bar and report "
        "download buttons.",
        "<b>Evidence page:</b> every claim beside its quotation with a connecting line coloured and shaped by "
        "its status, and filters by status.",
        "<b>Assistant page:</b> a chat with page citations, an insufficient-evidence notice and conversation "
        "history.",
        "<b>Design:</b> the paper\u2019s words are shown on white sheets in a serif face and the system\u2019s own "
        "text in a sans-serif face, so a reader always knows who is speaking.",
    ])
    S += [PageBreak(),
          figure(BUILD + r"\fig_upload.jpg", "Figure 5.2.1: upload page with the list of analysed papers",
                 desc="The home page, where a PDF is chosen to start an analysis. It lists every analysed paper "
                      "with its status and shows stage-by-stage progress and the backend health."),
          figure(BUILD + r"\fig_analysis.jpg", "Figure 5.2.2: analysis page with metadata and the verification bar",
                 desc="Shows the paper’s title, authors and year, the extracted categories and a bar counting "
                      "claims by verification status. Buttons on this page download the PDF or JSON report."),
          PageBreak(),
          figure(BUILD + r"\fig_evidence.jpg", "Figure 5.2.3: evidence page filtered to the unsupported claim",
                 desc="Each claim sits beside its exact quotation and page number, joined by a line whose colour "
                      "shows its status. Here the list is filtered to the single unsupported claim."),
          figure(BUILD + r"\fig_assistant.jpg", "Figure 5.2.4: assistant answering with a page citation and "
                 "declining an unanswerable question",
                 desc="The assistant answers questions with page citations taken from retrieved passages. When the "
                      "paper does not contain the answer, it says so instead of guessing.")]
    reg(1, "5.3", "Backend Development", "s5.3")
    S += [PageBreak(), section("5.3", "Backend Development", "s5.3")]
    S += [P("The backend is divided into API routers, services, agents, document-processing modules and "
            "retrieval modules. Routers validate requests and return structured errors, services run the "
            "workflow in a background job, and agents wrap the LLM calls.")]
    S += [label_p("<b>5.3.1 Modular Route and Service Architecture:</b>")]
    S += table([
        ["Module", "Responsibility"],
        ["pdf_parser.py", "Extracts text per page with positions, merges lines, detects page labels."],
        ["ocr.py", "Runs Tesseract on pages with no usable text layer."],
        ["section_detector.py", "Finds headings from font size and numbering."],
        ["metadata.py", "Reads title, authors and year from the front matter."],
        ["chunker.py", "Splits sections into 220-token chunks with 40-token overlap."],
        ["vector_store.py", "Stores and searches embeddings in ChromaDB."],
        ["keyword_search.py", "BM25 ranking over stored chunks."],
        ["hybrid_search.py", "Merges semantic and BM25 rankings with RRF."],
        ["llm_service.py", "Gemini and OpenRouter transports, retries, quota handling."],
        ["extraction_agent.py", "Three parallel extraction tasks, claim and evidence assembly."],
        ["evidence_linker.py", "Locates each quotation in the stored text."],
        ["verification_agent.py", "Rule checks and batched LLM verdicts per claim."],
        ["research_assistant.py", "Cited answers and insufficient-evidence replies."],
        ["analysis_graph.py", "LangGraph workflow of seven stages."],
        ["report_service.py", "Writes PDF and JSON reports."],
    ], [150, 323])
    S += [label_p("<b>5.3.2 Document Processing and NLP Pipeline:</b>")]
    S += [
        P("The parser reads each page with PyMuPDF, joins text pieces that share a baseline, drops vertical "
          "margin text and records both the PDF page index and the page number printed on the page. A page with "
          "fewer than 40 extractable characters is treated as scanned and rendered at 300 DPI for Tesseract."),
        P("Headings are identified from font size and numbering patterns, so each passage knows its section. "
          "Title, authors and year are first read deterministically from the front page; the language model "
          "only fills gaps and must quote its source. Chunks are measured in word pieces of the embedding "
          "model, so that no chunk is cut off by the model\u2019s input limit. References are stored but not "
          "indexed."),
        label_p("<b>Key Processing Parameters:</b>"),
    ]
    S += table([
        ["Parameter", "Value", "Reason"],
        ["Chunk target / overlap / maximum", "220 / 40 / 256 tokens", "Embedding model was trained on inputs near 250 word pieces."],
        ["OCR trigger", "fewer than 40 characters", "Detects pages that are images only."],
        ["OCR resolution", "300 DPI", "Standard resolution for Tesseract."],
        ["Candidates per search", "8 semantic + 8 BM25", "Small, focused candidate lists."],
        ["RRF constant k", "60", "Standard value from the RRF paper."],
        ["Passages per question", "6", "Enough context without noise."],
        ["Extraction passage budget", "8,000 tokens per task", "Keeps prompts focused."],
        ["LLM temperature / reasoning", "0.1 / low", "Quotation extraction needs little reasoning and is faster."],
    ], [150, 115, 208])
    S += [label_p("<b>5.3.3 Hybrid Retrieval and Gemini Answer Generation:</b>")]
    S += [
        P("Each query runs two searches over the stored chunks. Semantic search finds passages with similar "
          "meaning, and BM25 finds passages with the same words, numbers and acronyms. The two ranked lists are "
          "combined with Reciprocal Rank Fusion: the score of a passage is the sum of 1/(60 + rank) over the two "
          "lists. Because only ranks are used, the two different score scales never need to be calibrated."),
        P("For extraction, the retrieved passages are sent to Gemini together with a JSON schema in which every "
          "field is required, because the model otherwise leaves optional fields out. Text from the paper is "
          "sanitised so that instructions hidden inside a paper cannot change the task. For questions, the six "
          "best passages and the last four messages are sent, and the answer must cite passage identifiers. "
          "The code removes unknown identifiers, and an answer left with no valid citation is replaced by an "
          "insufficient-evidence reply."),
    ]
    S += [label_p("<b>5.3.4 Agentic Workflow and Evidence Verification:</b>")]
    S += [
        P("The LangGraph workflow has seven stages: upload validation, document extraction, section "
          "identification, retrieval indexing, knowledge extraction, evidence verification and finalisation. A "
          "failure in the first four stages ends the run and records which stage failed. The two LLM stages are "
          "non-fatal, so a paper remains indexed and searchable even when the language model is unavailable."),
        P("Verification starts with code. A claim without evidence is not verifiable, a quotation that cannot be "
          "found in the paper makes the claim unsupported, and deterministic metadata whose value appears in its "
          "quotation is verified without a model call. All other claims are judged by Gemini in batches of "
          "twenty. If a number in the claim does not appear in its quotation, the result is capped at partially "
          "supported. Without a language model, claims stay pending."),
    ]
    S += [label_p("<b>5.3.5 Database and Report Generation:</b>")]
    S += [
        P("SQLite stores documents, pages, sections, chunks, processing runs, extractions, conversations and "
          "messages, and Alembic migrations create the schema automatically at start-up. ChromaDB keeps one "
          "cosine-similarity collection per paper. Reports are written with ReportLab (PDF) or as JSON and are "
          "downloaded through a random identifier."),
    ]

    # ---------------- 6 Testing
    reg(0, "6", "System Testing / Experiment and Results", "c6")
    S += [PageBreak(), Head("6.&nbsp;&nbsp;&nbsp;System Testing / Experiments and Results", CH, "c6")]
    reg(1, "6.1", "Testing Approach", "s6.1")
    S += [section("6.1", "Testing Approach", "s6.1")]
    S += bullets([
        "<b>Module testing:</b> parsing, OCR fallback, chunking, retrieval, evidence matching and verification "
        "rules are tested with synthetic PDFs and fake LLM and embedding components, so tests are free and offline.",
        "<b>API testing:</b> upload, status, analysis, evidence, chat and report endpoints are tested through "
        "FastAPI\u2019s test client, including error responses.",
        "<b>Workflow testing:</b> the LangGraph graph is tested for normal runs, failed stages and a missing LLM.",
        "<b>Regression testing:</b> independent reviews found problems that were each fixed and given a regression "
        "test.",
        "<b>End-to-end testing:</b> complete analyses of a real paper with the live Gemini service, plus small "
        "retrieval and verification evaluations.",
    ])
    reg(1, "6.2", "Test Cases and Results", "s6.2")
    S += [section("6.2", "Test Cases and Results", "s6.2")]
    S += [P("The following table lists representative test cases together with the observed result and status "
            "of each test.", BODY_TIGHT)]
    S += table([
        ["Test Case ID", "Test Scenario", "Expected / Observed Result", "Result"],
        ["TC-01", "Start application", "Migrations run and /api/health reports database, vector store and LLM.", "PASS"],
        ["TC-02", "Upload a valid PDF", "File is stored with its hash and page count and analysis can start.", "PASS"],
        ["TC-03", "Upload a non-PDF or oversized file", "Rejected with a structured error message.", "PASS"],
        ["TC-04", "Parse a PDF with printed page numbers", "Text, positions and page labels are extracted.", "PASS"],
        ["TC-05", "Scanned page", "Tesseract OCR reads the page; real OCR check done.", "PASS"],
        ["TC-06", "Chunk a paper", "Chunks respect section boundaries and the 256-token cap.", "PASS"],
        ["TC-07", "Hybrid retrieval", "Semantic and BM25 results are merged by RRF.", "PASS"],
        ["TC-08", "Analyse a real 15-page paper", "Status analyzed in about two minutes with fourteen categories.", "PASS"],
        ["TC-09", "Planted fabricated quotation", "Claim is marked unsupported and receives no page.", "PASS"],
        ["TC-10", "Number missing from the quotation", "Status is capped at partially supported.", "PASS"],
        ["TC-11", "LLM unavailable or quota used up", "Paper is still indexed; claims stay pending, none verified.", "PASS"],
        ["TC-12", "Ask an answerable question", "Answer: Adam optimizer with its parameters, cited to page 7.", "PASS"],
        ["TC-13", "Ask an unanswerable question", "Insufficient-evidence notice; nothing is invented.", "PASS"],
        ["TC-14", "Prompt injection inside paper text", "The planted instruction is not followed.", "PASS"],
        ["TC-15", "Download PDF and JSON reports", "Report files are generated and downloaded by random ID.", "PASS"],
        ["TC-16", "Access password enabled", "API without password returns 401; with password returns 200.", "PASS"],
        ["TC-17", "One-click launch on a fresh copy", "Packages install, interface builds and the app starts.", "PASS"],
    ], [52, 128, 233, 60], center_cols=(0, 3))
    G = [label_p("<b>Automated Test Suite Results:</b>")]
    G += [P("The complete backend suite was run on 23 November 2026: 343 tests passed and 2 optional "
            "integration tests that need the real embedding model were skipped. The 5 frontend tests also passed.",
            BODY_TIGHT)]
    G += table([
        ["Test Area", "Tests", "Status"],
        ["Configuration, database, migrations and health", "25", "PASS"],
        ["Document upload API", "25", "PASS"],
        ["PDF parsing, OCR, sections and metadata", "47", "PASS"],
        ["Chunking, keyword and vector search", "27", "PASS"],
        ["LLM service and providers", "56", "PASS"],
        ["Evidence records and schemas", "77", "PASS"],
        ["Extraction and verification agents", "21", "PASS"],
        ["Analysis workflow and analysis API", "17", "PASS"],
        ["Assistant and reports", "5", "PASS"],
        ["Review regression tests", "40", "PASS"],
        ["Access password", "3", "PASS"],
        ["<b>Total</b>", "<b>343</b>", "<b>PASS</b>"],
    ], [300, 80, 93], center_cols=(1, 2))
    S += G
    G = [label_p("<b>End-to-End Results on a Real Paper:</b>")]
    G += [P("The paper \u201cAttention Is All You Need\u201d (arXiv 1706.03762, 15 pages, 26 detected sections, 61 "
            "chunks) was analysed twice with Gemini 3.8 Flash. The quotation check is stable between runs, "
            "while the verdicts of the language-model verifier vary.", BODY_TIGHT)]
    G += table([
        ["Measure", "Run 1 (5 Nov 2026)", "Run 2 (23 Nov 2026)"],
        ["Total analysis time", "125 s", "about 2 minutes"],
        ["Extraction stage (3 parallel calls)", "49 s", "49 s (tasks 32, 49 and 48 s)"],
        ["Claims extracted", "120", "113"],
        ["Evidence records", "158", "137"],
        ["Quotations found exactly in the paper", "157", "136"],
        ["Quotations not found", "1", "1"],
        ["Verified", "80", "78"],
        ["Partially supported", "22", "33"],
        ["Unsupported", "17", "1"],
        ["Not verifiable", "1", "1"],
    ], [200, 130, 143], center_cols=(1, 2))
    S += [KeepTogether(G)]
    G = [label_p("<b>Retrieval and Verification Evaluation:</b>")]
    G += [P("Retrieval was compared on 12 queries about this paper (top 5 results, draft relevance labels). "
            "Hybrid retrieval equalled semantic search on the first relevant rank (MRR) but did not improve "
            "recall on this small set.", BODY_TIGHT)]
    G += table([
        ["Retriever", "Precision@5", "Recall@5", "MRR"],
        ["Semantic", "0.417", "0.900", "0.861"],
        ["BM25", "0.350", "0.692", "0.662"],
        ["Hybrid (RRF)", "0.383", "0.775", "0.861"],
    ], [170, 101, 101, 101], center_cols=(1, 2, 3))
    S += [KeepTogether(G)]
    S += [P("The verifier was also tested on 12 labelled claim and quotation pairs: accuracy 1.00, false "
            "acceptance 0 of 5 and false rejection 0 of 7. False acceptance, marking a wrong claim as verified, "
            "is the most important error for this project.")]
    S += [label_p("<b>Observed Application Output:</b>")]
    S += [
        P("The assistant answered \u201cWhat optimizer was used to train the model?\u201d with the Adam optimizer "
          "and its parameters, cited to page 7 under the section Optimizer. It answered \u201cHow many patients "
          "were enrolled in the clinical trial?\u201d with an insufficient-evidence notice, because the paper "
          "contains no clinical trial. The evidence page flagged the claim describing multi-head attention in "
          "detail as unsupported, because its quotation on page 5 states only that the model attends to "
          "information from different representation subspaces."),
        label_p("<b>Limitations and Further Testing:</b>"),
        P("The evaluation labels were drafted during development and need a person\u2019s review. Only one "
          "paper was evaluated, so retrieval and verification results are preliminary. Further testing should "
          "use two to four more papers from different fields, measure OCR quality on real scans and repeat the "
          "verification several times to measure how much the language-model verdicts vary."),
    ]
    # steps
    reg(1, "", "Steps to run the Project", "steps")
    S += [PageBreak(), Head("Steps to run the project:", ParagraphStyle("st", parent=SEC, fontSize=16, leading=20, spaceBefore=0), "steps")]
    S += [P("<b>Prerequisites:</b> make sure the following are available on your system.", BODY_TIGHT)]
    S += bullets([
        "Python 3.12 or newer, with \u201cAdd python.exe to PATH\u201d ticked on Windows.",
        "Node.js (LTS), needed once to build the web interface.",
        "A Google Gemini API key from Google AI Studio.",
        "Optional: Tesseract OCR for scanned PDFs, and a modern web browser.",
    ], ParagraphStyle("bt", parent=BUL, spaceAfter=2, leading=15))
    steps = [
        ("Step 1: Get the project", "Clone https://github.com/goutamaiti/agentic-research-assistant or download the "
         "ZIP, and keep the folder at a short path such as C:\\Projects\\agentic-research-assistant."),
        ("Step 2: Start with one click", "On Windows double-click run.bat; on macOS or Linux run ./run.sh. The first "
         "run creates the Python environment, installs packages (5 to 10 minutes) and builds the interface."),
        ("Step 3: Enter the API key", "Paste the Gemini API key when asked. It is stored only in backend\\.env and is "
         "never committed."),
        ("Step 4: Open the application", "The browser opens http://127.0.0.1:8000 automatically."),
        ("Step 5: Upload and analyse", "Upload a PDF and wait about two minutes while the stages are shown."),
        ("Step 6: Read, check and ask", "Use the Analysis, Evidence and Assistant pages, and download the PDF or JSON "
         "report."),
        ("Step 7: Inspect the API", "Open http://127.0.0.1:8000/docs to try the endpoints."),
        ("Step 8: Run the tests", "In backend run: .venv\\Scripts\\python -m pytest. In frontend run: npm test."),
        ("Optional: Share with a friend", "Set ACCESS_PASSWORD in backend\\.env and run share.bat to get a temporary "
         "public Cloudflare link."),
    ]
    tight = ParagraphStyle("tt", parent=BODY, leading=14, spaceAfter=3, alignment=TA_LEFT)
    h14 = ParagraphStyle("h14", fontName="TNR-B", fontSize=14, leading=16, spaceBefore=4, spaceAfter=2, keepWithNext=1)
    for h, t in steps:
        S += [Paragraph(h, h14), Paragraph(t, tight)]
    S += [Paragraph("Project Execution Flow", ParagraphStyle("pef", parent=h14, fontSize=16, spaceBefore=6))]
    flow = ["Run run.bat (installs, builds and starts the backend on http://127.0.0.1:8000)",
            "Open the browser and enter the API key on the first run",
            "Upload a research paper and wait for the analysis",
            "Inspect claims, evidence and the assistant, and download the report"]
    for i, f in enumerate(flow):
        S += [Paragraph(f, tight)]
        if i < len(flow) - 1:
            S += [Paragraph("\u2193", ParagraphStyle("ar", parent=tight, spaceAfter=0, leading=13))]

    # step-by-step user guide
    reg(1, "", "Step-by-step Guide to use the Tool", "guide")
    S += [PageBreak(), Head("Step-by-step guide to use the tool:", ParagraphStyle(
        "gd", parent=SEC, fontSize=16, leading=20, spaceBefore=0), "guide")]
    G = ParagraphStyle("g", parent=BODY, leading=15.5, spaceAfter=3, alignment=TA_LEFT)
    GH = ParagraphStyle("gh", fontName="TNR-B", fontSize=13, leading=16, spaceBefore=6, spaceAfter=2,
                        keepWithNext=1)
    guide = [
        ("1. Open the application",
         "After run.bat finishes, the browser opens http://127.0.0.1:8000. A small status badge at the top "
         "shows whether the backend is running. If a password screen appears, enter the password you were given."),
        ("2. Upload a paper",
         "On the Upload page choose a research paper in PDF form (up to 30 MB; scanned PDFs are read with OCR) "
         "and press the analyse button."),
        ("3. Watch the progress",
         "The seven stages are listed with their status: upload validation, document extraction, section "
         "identification, retrieval indexing, knowledge extraction, evidence verification and finalisation. "
         "A fifteen-page paper takes about two minutes. The page may be left and reopened later."),
        ("4. Open the analysis",
         "When the paper shows as complete, press Open analysis. The page gives the title, authors and year, "
         "the extracted categories (problem, methods, datasets, results, limitations and so on) and a bar "
         "showing how many claims are verified, partially supported or unsupported."),
        ("5. Check the evidence",
         "Press Check evidence. Every claim is shown beside its exact quotation and printed page number. Use "
         "the filter to show only one status, for example unsupported claims, and read the quotation to decide "
         "whether the claim is correct."),
        ("6. Ask questions",
         "Press Ask questions and type a question about the paper. The answer carries page citations. If the "
         "paper does not contain the answer, the assistant says that there is not enough evidence."),
        ("7. Download the report",
         "From the analysis page download the PDF or JSON report to keep or share the result."),
        ("8. Analyse another paper",
         "Return to All papers to open an earlier paper or upload a new one. Analyse again re-runs the "
         "analysis for a paper already uploaded."),
    ]
    for h, t in guide:
        S += [Paragraph(h, GH), Paragraph(t, G)]
    S += [Paragraph("Note: a Gemini API key is required, and answers are only as good as the paper’s text, "
                    "so read the quotation before trusting a claim.",
                    ParagraphStyle("gn", parent=G, fontName="TNR-I", spaceBefore=6))]

    # ---------------- 7 Conclusion
    reg(0, "7", "Conclusion", "c7")
    S += [PageBreak(), Head("7.&nbsp;&nbsp;&nbsp;Conclusion", CH, "c7")]
    S += [
        P("The Agentic RAG Framework for Automated Domain-Specific Knowledge Extraction shows that a language "
          "model can be used for reading research papers without asking the reader to trust it blindly. By "
          "requiring a quotation for every claim, locating that quotation in the stored text with code, and "
          "verifying each claim separately, the system turns an unreliable summary into a list of statements that "
          "can each be checked in seconds."),
        P("The project combines document processing, hybrid retrieval, a LangGraph workflow, structured LLM output, "
          "verification and a cited question-answering assistant in a single application that runs on a laptop and "
          "starts with one click. A complete analysis of a fifteen-page paper takes about two minutes, 343 "
          "automated backend tests and 5 frontend tests pass, and the system answers honestly when the paper does "
          "not contain the answer."),
        P("The work also showed where care is needed: the language model must be forced to return every field, "
          "quota limits must fail fast, and verdicts from a language-model verifier vary between runs. Future work "
          "includes evaluating more papers with human-reviewed labels, adding a reranking model, understanding "
          "tables and figures, comparing several papers and deploying the application online."),
    ]

    # ---------------- 8 References
    reg(0, "8", "References", "c8")
    S += [PageBreak(), Head("References", CH16, "c8")]
    refs = [
        "Lewis, P., Perez, E., Piktus, A., Petroni, F., Karpukhin, V., et al., \"Retrieval-Augmented Generation "
        "for Knowledge-Intensive NLP Tasks\", Advances in Neural Information Processing Systems (NeurIPS), 2020.",
        "Reimers, N., &amp; Gurevych, I., \"Sentence-BERT: Sentence Embeddings using Siamese BERT-Networks\", "
        "Proceedings of EMNLP-IJCNLP, 2019.",
        "Robertson, S., &amp; Zaragoza, H., \"The Probabilistic Relevance Framework: BM25 and Beyond\", Foundations "
        "and Trends in Information Retrieval, 2009.",
        "Cormack, G. V., Clarke, C. L. A., &amp; B\u00fcttcher, S., \"Reciprocal Rank Fusion Outperforms Condorcet "
        "and Individual Rank Learning Methods\", Proceedings of ACM SIGIR, 2009.",
        "Ji, Z., Lee, N., Frieske, R., Yu, T., et al., \"Survey of Hallucination in Natural Language "
        "Generation\", ACM Computing Surveys, 2023.",
        "Vaswani, A., Shazeer, N., Parmar, N., Uszkoreit, J., et al., \"Attention Is All You Need\", Advances in "
        "Neural Information Processing Systems (NeurIPS), 2017 (test paper used in this project).",
        "Smith, R., \"An Overview of the Tesseract OCR Engine\", Proceedings of the International Conference on "
        "Document Analysis and Recognition (ICDAR), 2007.",
        "LangGraph documentation, LangChain, https://langchain-ai.github.io/langgraph/",
        "Chroma documentation, https://docs.trychroma.com/",
        "FastAPI documentation, https://fastapi.tiangolo.com/",
    ]
    S += bullets(refs, ParagraphStyle("ref", parent=BUL, spaceAfter=3, leading=20.6))

    # ---------------- Appendix A: source code
    reg(0, "A", "Appendix: Source Code", "app")
    S += [PageBreak(), Head("Appendix A: Source Code", CH16, "app")]
    files = code_files()
    total = sum(n for _p, n in files)
    S += [P("The complete source code of the application is listed in this appendix, starting on page %s. "
            "The same listing is also supplied as a separate PDF file, and the project is published on GitHub."
            % REC.get("code", (0, 0))[0]),
          P("<b>GitHub repository:</b> <a href=\"%s\" color=\"#1F4679\"><u>%s</u></a>" % (REPO, REPO)),
          P("<b>Source code listing:</b> <a href=\"#code_start\" color=\"#1F4679\"><u>Open the code, page %s</u></a>"
            % REC.get("code", (0, 0))[0]),
          P("The listing has %d files and %s lines of code." % (len(files), format(total, ","))),
          ]
    rows = [["File", "Lines"]] + [[p.replace("/", "/​"), str(n)] for p, n in files]
    S += code_index_table(rows)
    S += code_story()
    return S


class Doc(BaseDocTemplate):
    pass


def make(path):
    doc = Doc(path, pagesize=(PAGE_W, PAGE_H), leftMargin=LEFT, rightMargin=PAGE_W - LEFT - WIDTH,
              topMargin=54, bottomMargin=BOTTOM_Y, title="Agentic RAG Framework - NLP Micro-Project Report",
              author="Micro-Project Team")
    frame = Frame(LEFT, BOTTOM_Y, WIDTH, TOP_Y - BOTTOM_Y, leftPadding=0, rightPadding=0, topPadding=0,
                  bottomPadding=0, id="f")
    doc.addPageTemplates([PageTemplate(id="p", frames=[frame], onPage=decorate)])
    doc.build(build_story())
    REC["_last"] = (doc.page, 0)


CODE_OUT = BUILD + r"\Agentic_RAG_Source_Code.pdf"


def make_code(path):
    def deco(c, doc):
        c.saveState()
        c.setFont("TNR", 10)
        c.drawRightString(PAGE_W - 50, 30, str(doc.page))
        c.restoreState()
    doc = BaseDocTemplate(path, pagesize=(PAGE_W, PAGE_H), title="Agentic RAG - Source Code",
                          author="Micro-Project Team")
    frame = Frame(LEFT, 50, WIDTH, PAGE_H - 50 - 54, leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates([PageTemplate(id="c", frames=[frame], onPage=deco)])
    story = code_story()[1:]
    story[0] = Paragraph("Agentic RAG Framework - Source Code (%s)" % REPO, CH16)
    doc.build(story)


if __name__ == "__main__":
    make(BUILD + r"\_pass1.pdf")      # first pass collects heading pages
    make(OUT)                         # second pass prints the real table of contents
    make_code(CODE_OUT)
    print("pages:", REC["_last"][0])
    for k, v in REC.items():
        if k != "_last":
            print(k, v[0], round(v[1]))
