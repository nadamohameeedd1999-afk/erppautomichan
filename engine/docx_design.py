"""
The approved report design (التصميم المعتمد) for Word files the tool hands over:
A4 landscape · RTL · Microsoft Sans Serif · 3-zone header (company | title AR + EN | user + print date) · thick teal line ·
light-teal filter strip · tables with a solid teal header (#0F7C7A, white bold) and thin grey horizontal lines only ·
numbers centered, text right · empty = «—» · amounts 0,000.00 · footer «صفحة X من Y».
"""
from datetime import datetime

import docx
from docx.enum.section import WD_ORIENT
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

TEAL, DARK, GREY, TXT = RGBColor(0x0F, 0x7C, 0x7A), RGBColor(0x0A, 0x56, 0x54), RGBColor(0x6B, 0x7B, 0x7A), RGBColor(0x1C, 0x2B, 0x2A)
RED, GREEN, AMBER, WHITE = RGBColor(0xC6, 0x28, 0x28), RGBColor(0x1E, 0x8E, 0x3E), RGBColor(0xB2, 0x6A, 0x00), RGBColor(0xFF, 0xFF, 0xFF)
WIDTH_CM = 27.1


def money(x):
    try:
        return f"{float(x):,.2f}"
    except (TypeError, ValueError):
        return "—" if x in (None, "") else str(x)


class Report:
    def __init__(self, company, title_ar, title_en, user=""):
        self.d = docx.Document()
        sec = self.d.sections[0]
        sec.orientation = WD_ORIENT.LANDSCAPE
        sec.page_width, sec.page_height = Cm(29.7), Cm(21.0)
        sec.left_margin = sec.right_margin = Cm(1.3)
        sec.top_margin = sec.bottom_margin = Cm(1.2)
        st = self.d.styles["Normal"]
        st.font.name = "Microsoft Sans Serif"
        st.font.size = Pt(9)
        st.element.rPr.rFonts.set(qn("w:cs"), "Microsoft Sans Serif")
        st.paragraph_format.space_after = Pt(2)
        self._header(company, title_ar, title_en, user)
        self._footer()

    # ---- low level
    @staticmethod
    def rtl(p):
        p._p.get_or_add_pPr().append(OxmlElement("w:bidi"))
        return p

    @staticmethod
    def run(p, text, size=9, bold=False, color=TXT):
        r = p.add_run(str(text))
        r.font.size, r.font.bold, r.font.color.rgb = Pt(size), bold, color
        rPr = r._r.get_or_add_rPr()
        rPr.append(OxmlElement("w:rtl"))
        cs = OxmlElement("w:szCs")
        cs.set(qn("w:val"), str(int(size * 2)))
        rPr.append(cs)
        if bold:
            rPr.append(OxmlElement("w:bCs"))
        return r

    @staticmethod
    def shade(cell, hexcolor):
        s = OxmlElement("w:shd")
        s.set(qn("w:val"), "clear")
        s.set(qn("w:color"), "auto")
        s.set(qn("w:fill"), hexcolor)
        cell._tc.get_or_add_tcPr().append(s)

    @staticmethod
    def borders(table, inside_h="D5E2E1"):
        tblPr = table._tbl.tblPr
        b = OxmlElement("w:tblBorders")
        for edge in ("top", "left", "bottom", "right", "insideV"):
            e = OxmlElement(f"w:{edge}")
            e.set(qn("w:val"), "nil")
            b.append(e)
        e = OxmlElement("w:insideH")
        e.set(qn("w:val"), "single" if inside_h else "nil")
        e.set(qn("w:sz"), "4")
        e.set(qn("w:color"), inside_h or "auto")
        b.append(e)
        tblPr.append(b)
        tblPr.append(OxmlElement("w:bidiVisual"))

    def para(self, text="", size=9, bold=False, color=TXT, align=WD_ALIGN_PARAGRAPH.RIGHT, space_before=0):
        p = self.rtl(self.d.add_paragraph())
        p.alignment = align
        if space_before:
            p.paragraph_format.space_before = Pt(space_before)
        if text:
            self.run(p, text, size, bold, color)
        return p

    # ---- blocks
    def _header(self, company, ar, en, user):
        h = self.d.add_table(rows=1, cols=3)
        self.borders(h, None)
        h.autofit = False
        h.alignment = WD_TABLE_ALIGNMENT.CENTER
        for i, w in enumerate((7.5, 12.1, 7.5)):
            h.columns[i].width = Cm(w)
            h.rows[0].cells[i].width = Cm(w)
        c0, c1, c2 = h.rows[0].cells
        p = self.rtl(c0.paragraphs[0])
        self.run(p, company, 12, True, DARK)
        p = self.rtl(c1.paragraphs[0])
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        self.run(p, ar, 16, True)
        p = self.rtl(c1.add_paragraph())
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        self.run(p, en, 11, False, TEAL)
        p = self.rtl(c2.paragraphs[0])
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        self.run(p, "المستخدم: ", 9, False, GREY)
        self.run(p, user or "—", 9, True)
        p = self.rtl(c2.add_paragraph())
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        self.run(p, "تاريخ الطباعة: ", 9, False, GREY)
        self.run(p, datetime.now().strftime("%Y-%m-%d %H:%M"), 9, True)
        p = self.d.add_paragraph()
        pb = OxmlElement("w:pBdr")
        bt = OxmlElement("w:bottom")
        for k, v in (("val", "single"), ("sz", "18"), ("color", "0F7C7A")):
            bt.set(qn(f"w:{k}"), v)
        pb.append(bt)
        p._p.get_or_add_pPr().append(pb)

    def strip(self, pairs):
        """light-teal box: label (grey) + value (bold) …"""
        t = self.d.add_table(rows=1, cols=1)
        self.borders(t, None)
        self.shade(t.rows[0].cells[0], "E7F3F2")
        p = self.rtl(t.rows[0].cells[0].paragraphs[0])
        for i, (lbl, val) in enumerate(pairs):
            if i:
                self.run(p, "    ·    ", 9, False, GREY)
            self.run(p, f"{lbl}: ", 9, False, GREY)
            self.run(p, val if val not in (None, "") else "—", 9, True)
        self.d.add_paragraph()

    def table(self, cols, rows, center=(), colors=None, bold_cols=(), size=8.5):
        """cols = [(title, width weight)], rows = [[values]] ; colors(row_index, col_index, value) -> RGBColor | None"""
        t = self.d.add_table(rows=1, cols=len(cols))
        self.borders(t)
        t.autofit = False
        tot = sum(w for _, w in cols)
        for i, (lbl, w) in enumerate(cols):
            t.columns[i].width = Cm(WIDTH_CM * w / tot)
            c = t.rows[0].cells[i]
            c.width = Cm(WIDTH_CM * w / tot)
            self.shade(c, "0F7C7A")
            p = self.rtl(c.paragraphs[0])
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            self.run(p, lbl, 9, True, WHITE)
        t.rows[0]._tr.get_or_add_trPr().append(OxmlElement("w:tblHeader"))
        for ri, row in enumerate(rows):
            cells = t.add_row().cells
            for i, v in enumerate(row):
                cells[i].width = Cm(WIDTH_CM * cols[i][1] / tot)
                v = "—" if v in (None, "") else str(v)
                p = self.rtl(cells[i].paragraphs[0])
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER if i in center else WD_ALIGN_PARAGRAPH.RIGHT
                col = colors(ri, i, v) if colors else None
                self.run(p, v, size, i in bold_cols or col is not None, col or TXT)
        self.d.add_paragraph()
        return t

    def page_break(self):
        self.d.add_page_break()

    def _footer(self):
        sec = self.d.sections[0]
        fp = self.rtl(sec.footer.paragraphs[0])
        fp.alignment = WD_ALIGN_PARAGRAPH.CENTER

        def field(code):
            for kind, val in (("begin", None), ("instr", code), ("end", None)):
                r = fp.add_run()
                if kind == "instr":
                    it = OxmlElement("w:instrText")
                    it.set(qn("xml:space"), "preserve")
                    it.text = val
                    r._r.append(it)
                else:
                    e = OxmlElement("w:fldChar")
                    e.set(qn("w:fldCharType"), kind)
                    r._r.append(e)
        self.run(fp, "صفحة ", 9, False, GREY)
        field("PAGE")
        self.run(fp, " من ", 9, False, GREY)
        field("NUMPAGES")

    def save(self, path):
        self.d.save(str(path))
        return str(path)
