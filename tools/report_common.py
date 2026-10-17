"""Word 实验报告排版工具（基于 python-docx）。

把「封面 / 分工页 / 摘要 / 目录域 / 章节标题 / 正文 / 列表 / 代码块 /
插图 / 表格 / 页眉页脚」这些重复劳动封装成 :class:`ReportBuilder`，
生成器 ``make_report.py`` 只负责写内容、给编号，版式由此文件保证一致。

编号约定
--------
* 章：``h1("需求分析与问题建模")`` 自动编号为「第 1 章　需求分析与问题建模」；
* 节：``h2("项目背景")`` 编号为「1.1　项目背景」，``h3`` 继续往下编；
* 图 / 表：每章从 1 重新计数，题注格式为「图 2-1　系统模块划分与数据流」，
  由 :meth:`ReportBuilder.figure` / :meth:`ReportBuilder.table` 自动编号；
* 附录：``h1("附录 B　文件清单", numbered=False, label="B")`` 把编号前缀
  切到 ``B``，于是表格自动编成「表 B-1」。

依赖：仅 python-docx（``pip install python-docx``），不依赖任何 GUI 或网络。
"""

from __future__ import annotations

import os
from datetime import date

from docx import Document
from docx.enum.table import WD_ALIGN_VERTICAL, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

# ----------------------------------------------------------------------
# 配色与字体：集中在这里，换主题只改一处
# ----------------------------------------------------------------------
INK = RGBColor(0x0F, 0x17, 0x2A)      # 正文近黑
SUB = RGBColor(0x47, 0x55, 0x69)      # 次要文字
ACCENT = RGBColor(0x1D, 0x4E, 0xD8)   # 强调蓝
GRAY = RGBColor(0x6B, 0x72, 0x80)     # 页眉页脚 / 注释

BODY_FONT_CN = "宋体"
HEAD_FONT_CN = "黑体"
BODY_FONT_EN = "Times New Roman"
HEAD_FONT_EN = "Arial"
CODE_FONT = "Consolas"

CAPTION_GAP = "\u3000"  # 题注里「图 2-1」和标题之间的全角空格


def _set_run_font(
    run,
    size: float,
    *,
    east: str = BODY_FONT_CN,
    ascii_font: str = BODY_FONT_EN,
    bold: bool = False,
    color: RGBColor | None = None,
) -> None:
    """同时设置西文、中文、字号、加粗、颜色（python-docx 默认只管西文）。"""
    run.font.name = ascii_font
    run.font.size = Pt(size)
    run.font.bold = bold
    rpr = run._element.get_or_add_rPr()
    fonts = rpr.find(qn("w:rFonts"))
    if fonts is None:
        fonts = OxmlElement("w:rFonts")
        rpr.append(fonts)
    fonts.set(qn("w:ascii"), ascii_font)
    fonts.set(qn("w:hAnsi"), ascii_font)
    fonts.set(qn("w:eastAsia"), east)
    if color is not None:
        run.font.color.rgb = color


def _shade(paragraph, fill: str) -> None:
    p_pr = paragraph._p.get_or_add_pPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    p_pr.append(shd)


def _cell_shade(cell, fill: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    tc_pr.append(shd)


def _set_cell_margins(table, top=40, bottom=40, left=80, right=80) -> None:
    tbl_pr = table._tbl.tblPr
    mar = OxmlElement("w:tblCellMar")
    for side, value in (("top", top), ("left", left),
                        ("bottom", bottom), ("right", right)):
        node = OxmlElement(f"w:{side}")
        node.set(qn("w:w"), str(value))
        node.set(qn("w:type"), "dxa")
        mar.append(node)
    tbl_pr.append(mar)


def _repeat_header(row) -> None:
    """跨页时重复表格表头。"""
    tr_pr = row._tr.get_or_add_trPr()
    header = OxmlElement("w:tblHeader")
    header.set(qn("w:val"), "true")
    tr_pr.append(header)


def _lock_table_layout(table, widths: list[float]) -> None:
    """固定表格列宽：Word 默认会“自动调整”，导致列宽与设定不一致、表格超出页宽。"""
    tbl = table._tbl
    tbl_pr = tbl.tblPr

    tbl_w = tbl_pr.find(qn("w:tblW"))
    if tbl_w is None:
        tbl_w = OxmlElement("w:tblW")
        tbl_pr.append(tbl_w)
    tbl_w.set(qn("w:type"), "dxa")
    tbl_w.set(qn("w:w"), str(int(round(sum(widths) * 567))))

    layout = OxmlElement("w:tblLayout")
    layout.set(qn("w:type"), "fixed")
    tbl_pr.append(layout)

    grid = tbl.find(qn("w:tblGrid"))
    if grid is not None:
        for grid_col, width in zip(grid.findall(qn("w:gridCol")), widths):
            grid_col.set(qn("w:w"), str(int(round(width * 567))))


def _set_cell_borders(table, color: str = "94A3B8", size: int = 4) -> None:
    """三线表风格：外框与表头下边线加深，其余细灰线。"""
    tbl_pr = table._tbl.tblPr
    borders = OxmlElement("w:tblBorders")
    for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
        node = OxmlElement(f"w:{side}")
        node.set(qn("w:val"), "single")
        node.set(qn("w:sz"), str(size))
        node.set(qn("w:space"), "0")
        node.set(qn("w:color"), color)
        borders.append(node)
    tbl_pr.append(borders)


class ReportBuilder:
    """封装一份课程实践报告的构建过程。

    典型用法::

        report = ReportBuilder(title="城市交通路径导航系统",
                               subtitle="设 计 与 实 现",
                               project="城市交通路径导航系统")
        report.cover()
        report.division_page()          # 分工表
        report.abstract(text, keywords)
        report.toc()
        report.h1("需求分析与问题建模")
        report.h2("项目背景")
        report.p("……")
        report.table("系统功能需求", headers, rows)
        report.figure("docs/figures/x.png", "系统主界面")
        report.save("reports/xxx.docx")
    """

    def __init__(self, title: str, subtitle: str, project: str) -> None:
        self.title = title
        self.subtitle = subtitle
        self.project = project
        self.doc = Document()

        self.chapter = 0             # 章序号（int）
        self.chapter_label = ""      # 图表编号前缀："2" 或 "B"
        self.section = 0
        self.subsection = 0
        self.figure_no = 0
        self.table_no = 0

        self.figures: list[tuple[str, str]] = []   # [(图 2-1, 题注)]
        self.tables: list[tuple[str, str]] = []    # [(表 2-1, 题注)]

        self._setup_page()
        self._setup_styles()

    # ==================================================================
    # 页面、页眉页脚、样式
    # ==================================================================
    def _setup_page(self) -> None:
        section = self.doc.sections[0]
        section.page_width = Cm(21.0)
        section.page_height = Cm(29.7)
        section.top_margin = Cm(2.54)
        section.bottom_margin = Cm(2.54)
        section.left_margin = Cm(2.6)
        section.right_margin = Cm(2.6)
        section.header_distance = Cm(1.4)
        section.footer_distance = Cm(1.4)
        section.different_first_page_header_footer = True

        header = section.header
        header.is_linked_to_previous = False
        para = header.paragraphs[0]
        para.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        run = para.add_run("数据结构课程实践报告 · 城市交通路径导航系统")
        _set_run_font(run, 9, color=GRAY)
        self._add_bottom_border(para)

        footer = section.footer
        footer.is_linked_to_previous = False
        para = footer.paragraphs[0]
        para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        self._add_page_field(para)

    @staticmethod
    def _add_bottom_border(paragraph) -> None:
        p_pr = paragraph._p.get_or_add_pPr()
        borders = OxmlElement("w:pBdr")
        bottom = OxmlElement("w:bottom")
        bottom.set(qn("w:val"), "single")
        bottom.set(qn("w:sz"), "4")
        bottom.set(qn("w:space"), "1")
        bottom.set(qn("w:color"), "CBD5E1")
        borders.append(bottom)
        p_pr.append(borders)

    @staticmethod
    def _add_field(paragraph, instr_text: str, cached_text: str = "") -> None:
        """按 OOXML 规范插入一个复杂域。

        每个 ``w:fldChar`` / ``w:instrText`` 必须各占一个独立的 ``w:r``；
        若把 begin / instrText / separate / 结果 / end 塞进同一个 run，
        Word 打开后会报「域嵌套太深」并拒绝更新目录与页码。
        """

        def _append_run(node) -> None:
            run = paragraph.add_run()
            run._r.append(node)

        begin = OxmlElement("w:fldChar")
        begin.set(qn("w:fldCharType"), "begin")
        _append_run(begin)

        instr = OxmlElement("w:instrText")
        instr.set(qn("xml:space"), "preserve")
        instr.text = instr_text
        _append_run(instr)

        separate = OxmlElement("w:fldChar")
        separate.set(qn("w:fldCharType"), "separate")
        _append_run(separate)

        if cached_text:
            paragraph.add_run(cached_text)

        end = OxmlElement("w:fldChar")
        end.set(qn("w:fldCharType"), "end")
        _append_run(end)

    @staticmethod
    def _add_page_field(paragraph) -> None:
        ReportBuilder._add_field(paragraph, " PAGE ", "1")
        for run in paragraph.runs:
            _set_run_font(run, 9, color=GRAY)

    def _setup_styles(self) -> None:
        normal = self.doc.styles["Normal"]
        normal.font.name = BODY_FONT_EN
        normal.font.size = Pt(12)
        normal.font.color.rgb = INK
        normal.element.rPr.rFonts.set(qn("w:eastAsia"), BODY_FONT_CN)
        fmt = normal.paragraph_format
        fmt.line_spacing = 1.5
        fmt.space_after = Pt(0)
        fmt.space_before = Pt(0)
        fmt.first_line_indent = Cm(0.85)

        for name, size, before, after, align in (
            ("Heading 1", 16, 12, 12, WD_ALIGN_PARAGRAPH.CENTER),
            ("Heading 2", 14, 12, 6, WD_ALIGN_PARAGRAPH.LEFT),
            ("Heading 3", 12, 8, 4, WD_ALIGN_PARAGRAPH.LEFT),
        ):
            style = self.doc.styles[name]
            style.font.name = HEAD_FONT_EN
            style.font.size = Pt(size)
            style.font.bold = True
            style.font.color.rgb = INK
            style.element.rPr.rFonts.set(qn("w:eastAsia"), HEAD_FONT_CN)
            fmt = style.paragraph_format
            fmt.alignment = align
            fmt.space_before = Pt(before)
            fmt.space_after = Pt(after)
            fmt.first_line_indent = Cm(0)
            fmt.line_spacing = 1.3
            fmt.keep_with_next = True
            if name == "Heading 1":
                fmt.page_break_before = True

    # ==================================================================
    # 封面 / 分工页 / 摘要 / 目录
    # ==================================================================
    def cover(self, info: list[tuple[str, str]] | None = None) -> None:
        """封面：课程名 + 大标题 + 副标题 + 信息表（姓名学号留空下划线）。"""
        for _ in range(3):
            self.doc.add_paragraph()
        para = self.doc.add_paragraph()
        para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = para.add_run("数据结构课程实践报告")
        _set_run_font(run, 18, east=HEAD_FONT_CN, ascii_font=HEAD_FONT_EN,
                      bold=True, color=SUB)

        para = self.doc.add_paragraph()
        para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        para.paragraph_format.space_before = Pt(46)
        run = para.add_run(self.title)
        _set_run_font(run, 30, east=HEAD_FONT_CN, ascii_font=HEAD_FONT_EN,
                      bold=True, color=INK)

        para = self.doc.add_paragraph()
        para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = para.add_run(self.subtitle)
        _set_run_font(run, 16, east=HEAD_FONT_CN, ascii_font=HEAD_FONT_EN,
                      bold=True, color=ACCENT)

        para = self.doc.add_paragraph()
        para.paragraph_format.space_before = Pt(24)
        self._add_bottom_border(para)

        rows = info or [
            ("课程名称", "数据结构"),
            ("实践项目", self.project),
            ("选题方向", "选题 A　图与路径规划"),
            ("组　　号", "＿＿＿＿＿＿＿＿"),
            ("姓　　名", "＿＿＿＿＿＿＿＿"),
            ("学　　号", "＿＿＿＿＿＿＿＿"),
            ("班　　级", "＿＿＿＿＿＿＿＿"),
            ("指导教师", "＿＿＿＿＿＿＿＿"),
        ]
        table = self.doc.add_table(rows=0, cols=2)
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        table.autofit = False
        for label, value in rows:
            row = table.add_row()
            row.height = Cm(1.0)
            row.cells[0].width = Cm(4.0)
            row.cells[1].width = Cm(8.6)
            p0 = row.cells[0].paragraphs[0]
            p0.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            p0.paragraph_format.first_line_indent = Cm(0)
            r0 = p0.add_run(label + "：")
            _set_run_font(r0, 12, east=HEAD_FONT_CN, bold=True)
            p1 = row.cells[1].paragraphs[0]
            p1.paragraph_format.first_line_indent = Cm(0)
            r1 = p1.add_run(value)
            _set_run_font(r1, 12)

        for _ in range(3):
            self.doc.add_paragraph()
        para = self.doc.add_paragraph()
        para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = para.add_run(f"{date.today().year} 年 {date.today().month} 月")
        _set_run_font(run, 12, color=SUB)
        self.doc.add_page_break()

    def division_page(self, rows: list[list[str]]) -> None:
        """分工表页：说明 P1~P4 各自负责的文件与内容（姓名一列留空）。"""
        self._plain_heading("项目分工")
        self.p(
            "本项目按「数据层 → 算法层 → 界面层 → 渲染与工程化」四个阶段推进，"
            "每个阶段有明确的交付文件与验收口径，分工如下表所示。",
            indent=True,
        )
        # 分工表不属于正文章节，用不带编号的题注，避免打乱“表 1-1”起的正文编号。
        cap = self.doc.add_paragraph()
        cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
        cap.paragraph_format.first_line_indent = Cm(0)
        cap.paragraph_format.space_before = Pt(8)
        cap.paragraph_format.space_after = Pt(3)
        cap.paragraph_format.keep_with_next = True
        run = cap.add_run("项目分工一览")
        _set_run_font(run, 10.5, color=SUB)
        self._render_table(
            ["阶段", "负责内容", "主要文件", "姓名"],
            rows,
            widths=[2.8, 5.9, 5.6, 1.4],
            font_size=9,
            aligns=["center", "left", "left", "center"],
        )
        self.note(
            "说明：姓名一列由组内填写；P1~P4 的交付物与验收证据分别见"
            "docs/ 目录下的验收说明与报告第 4 章。"
        )
        self.doc.add_page_break()

    def abstract(self, paragraphs: str | list[str], keywords: list[str]) -> None:
        """摘要页：正文 + 关键词。段落之间用空行分隔。"""
        self._plain_heading("摘　要")
        if isinstance(paragraphs, str):
            chunks = [p.strip() for p in paragraphs.strip().split("\n\n") if p.strip()]
        else:
            chunks = [str(p).strip() for p in paragraphs if str(p).strip()]
        for chunk in chunks:
            self.p(chunk, indent=True)

        para = self.doc.add_paragraph()
        para.paragraph_format.first_line_indent = Cm(0)
        para.paragraph_format.space_before = Pt(16)
        run = para.add_run("关键词：")
        _set_run_font(run, 12, bold=True)
        run = para.add_run("；".join(keywords))
        _set_run_font(run, 12)
        self.doc.add_page_break()

    def toc(self) -> None:
        """插入 Word 目录域（打开文档后自动/手动更新即可生成目录）。"""
        self._plain_heading("目　录", center=True)
        para = self.doc.add_paragraph()
        para.paragraph_format.first_line_indent = Cm(0)
        self._add_field(
            para,
            'TOC \\o "1-2" \\h \\z \\u',
            "（打开文档后，在目录处右键选择“更新域”即可生成目录与页码）",
        )
        settings = self.doc.settings.element
        update = OxmlElement("w:updateFields")
        update.set(qn("w:val"), "true")
        settings.append(update)

    def _plain_heading(self, text: str, center: bool = True) -> None:
        para = self.doc.add_paragraph()
        para.alignment = (
            WD_ALIGN_PARAGRAPH.CENTER if center else WD_ALIGN_PARAGRAPH.LEFT
        )
        para.paragraph_format.space_before = Pt(6)
        para.paragraph_format.space_after = Pt(12)
        run = para.add_run(text)
        _set_run_font(run, 16, east=HEAD_FONT_CN, ascii_font=HEAD_FONT_EN,
                      bold=True, color=INK)
        para.paragraph_format.keep_with_next = True

    # ==================================================================
    # 章节标题
    # ==================================================================
    def h1(self, text: str, numbered: bool = True, label: str | None = None) -> None:
        """一级标题。

        * ``numbered=True``：自动编「第 X 章　text」，并重置图表计数；
        * ``numbered=False, label="B"``：不编章号，但图表编号前缀改成 ``B``；
        * ``numbered=False, label=None``：纯标题（参考文献等），不参与图表编号。
        """
        if numbered:
            self.chapter += 1
            self.chapter_label = str(self.chapter)
            title = f"第{self.chapter}章{CAPTION_GAP}{text}"
        else:
            self.chapter_label = label or ""
            title = text
        self.section = 0
        self.subsection = 0
        self.figure_no = 0
        self.table_no = 0
        heading = self.doc.add_heading(title, level=1)
        for run in heading.runs:
            _set_run_font(run, 16, east=HEAD_FONT_CN, ascii_font=HEAD_FONT_EN,
                          bold=True, color=INK)

    def h2(self, text: str) -> None:
        self.section += 1
        self.subsection = 0
        heading = self.doc.add_heading(
            f"{self.chapter_label}.{self.section}{CAPTION_GAP}{text}", level=2
        )
        for run in heading.runs:
            _set_run_font(run, 14, east=HEAD_FONT_CN, ascii_font=HEAD_FONT_EN,
                          bold=True, color=INK)

    def h3(self, text: str) -> None:
        self.subsection += 1
        heading = self.doc.add_heading(
            f"{self.chapter_label}.{self.section}.{self.subsection}{CAPTION_GAP}{text}",
            level=3,
        )
        for run in heading.runs:
            _set_run_font(run, 12, east=HEAD_FONT_CN, ascii_font=HEAD_FONT_EN,
                          bold=True, color=INK)

    # ==================================================================
    # 正文、列表、代码、注释
    # ==================================================================
    def p(
        self,
        text: str,
        *,
        indent: bool = True,
        bold: bool = False,
        size: float = 12,
        align=None,
        space_after: float = 0,
        color: RGBColor | None = None,
    ) -> None:
        para = self.doc.add_paragraph()
        para.paragraph_format.first_line_indent = Cm(0.85) if indent else Cm(0)
        para.paragraph_format.space_after = Pt(space_after)
        if align is not None:
            para.alignment = align
        run = para.add_run(text)
        _set_run_font(run, size, bold=bold, color=color)

    def bullet(self, text: str, level: int = 0) -> None:
        para = self.doc.add_paragraph()
        para.paragraph_format.left_indent = Cm(0.6 + 0.6 * level)
        para.paragraph_format.first_line_indent = Cm(0)
        para.paragraph_format.space_after = Pt(2)
        mark = "•" if level == 0 else "－"
        run = para.add_run(f"{mark} {text}")
        _set_run_font(run, 11.5)

    def code(self, text: str, title: str | None = None) -> None:
        """等宽字体 + 浅灰底的代码块/伪代码块。"""
        if title:
            para = self.doc.add_paragraph()
            para.paragraph_format.first_line_indent = Cm(0)
            para.paragraph_format.space_before = Pt(6)
            para.paragraph_format.keep_with_next = True
            run = para.add_run(title)
            _set_run_font(run, 10, east=HEAD_FONT_CN, bold=True, color=SUB)
        for line in text.rstrip("\n").split("\n"):
            para = self.doc.add_paragraph()
            para.paragraph_format.first_line_indent = Cm(0)
            para.paragraph_format.left_indent = Cm(0.3)
            para.paragraph_format.right_indent = Cm(0.2)
            para.paragraph_format.space_before = Pt(0)
            para.paragraph_format.space_after = Pt(0)
            para.paragraph_format.line_spacing = 1.0
            _shade(para, "F6F8FA")
            run = para.add_run(line if line else " ")
            _set_run_font(run, 8.5, east=BODY_FONT_CN, ascii_font=CODE_FONT)
        spacer = self.doc.add_paragraph()
        spacer.paragraph_format.space_after = Pt(0)
        spacer.paragraph_format.first_line_indent = Cm(0)
        spacer.paragraph_format.line_spacing = 0.6

    def note(self, text: str) -> None:
        para = self.doc.add_paragraph()
        para.paragraph_format.first_line_indent = Cm(0)
        para.paragraph_format.left_indent = Cm(0.3)
        para.paragraph_format.space_after = Pt(4)
        run = para.add_run(text)
        _set_run_font(run, 9.5, color=GRAY)

    def page_break(self) -> None:
        self.doc.add_page_break()

    # ==================================================================
    # 图与表
    # ==================================================================
    def figure(self, path: str, caption: str, width_cm: float = 15.2) -> str:
        """插入插图并自动编号，题注在图下方。

        返回编号标签，例如 ``图 2-1``。
        """
        if not os.path.isfile(path):
            raise FileNotFoundError(f"插图文件不存在：{path}")
        if not self.chapter_label:
            raise RuntimeError("插图必须放在有编号的章/附录里")
        self.figure_no += 1
        label = f"图 {self.chapter_label}-{self.figure_no}"

        para = self.doc.add_paragraph()
        para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        para.paragraph_format.first_line_indent = Cm(0)
        para.paragraph_format.space_before = Pt(6)
        para.paragraph_format.space_after = Pt(3)
        para.paragraph_format.keep_with_next = True
        run = para.add_run()
        run.add_picture(path, width=Cm(width_cm))

        cap = self.doc.add_paragraph()
        cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
        cap.paragraph_format.first_line_indent = Cm(0)
        cap.paragraph_format.space_after = Pt(8)
        run = cap.add_run(f"{label}{CAPTION_GAP}{caption}")
        _set_run_font(run, 10.5, color=SUB)

        self.figures.append((label, caption))
        return label

    def table(
        self,
        caption: str,
        headers: list[str],
        rows: list[list],
        widths: list[float] | None = None,
        font_size: float = 9.5,
        aligns: list[str] | None = None,
    ) -> str:
        """插入表格并自动编号，表题在表上方。

        返回编号标签，例如 ``表 2-1``。
        """
        if not self.chapter_label:
            raise RuntimeError("表格必须放在有编号的章/附录里")
        self.table_no += 1
        label = f"表 {self.chapter_label}-{self.table_no}"

        cap = self.doc.add_paragraph()
        cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
        cap.paragraph_format.first_line_indent = Cm(0)
        cap.paragraph_format.space_before = Pt(8)
        cap.paragraph_format.space_after = Pt(3)
        cap.paragraph_format.keep_with_next = True
        run = cap.add_run(f"{label}{CAPTION_GAP}{caption}")
        _set_run_font(run, 10.5, color=SUB)

        self._render_table(headers, rows, widths, font_size, aligns)
        self.tables.append((label, caption))
        return label

    def _render_table(
        self,
        headers: list[str],
        rows: list[list],
        widths: list[float] | None = None,
        font_size: float = 9.5,
        aligns: list[str] | None = None,
    ) -> None:
        table = self.doc.add_table(rows=1, cols=len(headers))
        table.style = "Table Grid"
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        table.autofit = False
        _set_cell_margins(table)
        if widths is None:
            widths = [15.2 / len(headers)] * len(headers)
        assert len(widths) == len(headers), "列宽数量必须与表头列数一致"
        if sum(widths) > 15.8:
            raise ValueError(f"表格总列宽 {sum(widths):.1f}cm 超过版心 15.8cm：{headers}")
        aligns = aligns or ["center"] * len(headers)
        _lock_table_layout(table, widths)

        header_row = table.rows[0]
        _repeat_header(header_row)
        for idx, text in enumerate(headers):
            cell = header_row.cells[idx]
            cell.width = Cm(widths[idx])
            cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
            _cell_shade(cell, "DBEAFE")
            para = cell.paragraphs[0]
            para.alignment = WD_ALIGN_PARAGRAPH.CENTER
            para.paragraph_format.first_line_indent = Cm(0)
            para.paragraph_format.line_spacing = 1.0
            para.paragraph_format.space_after = Pt(0)
            run = para.add_run(str(text))
            _set_run_font(run, font_size, east=HEAD_FONT_CN, bold=True)

        for row_data in rows:
            row = table.add_row()
            for idx, value in enumerate(row_data):
                cell = row.cells[idx]
                cell.width = Cm(widths[idx])
                cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
                para = cell.paragraphs[0]
                para.alignment = {
                    "center": WD_ALIGN_PARAGRAPH.CENTER,
                    "left": WD_ALIGN_PARAGRAPH.LEFT,
                    "right": WD_ALIGN_PARAGRAPH.RIGHT,
                }[aligns[idx]]
                para.paragraph_format.first_line_indent = Cm(0)
                para.paragraph_format.line_spacing = 1.0
                para.paragraph_format.space_after = Pt(0)
                run = para.add_run(str(value))
                _set_run_font(run, font_size)

        spacer = self.doc.add_paragraph()
        spacer.paragraph_format.first_line_indent = Cm(0)
        spacer.paragraph_format.space_after = Pt(0)
        spacer.paragraph_format.line_spacing = 0.6

    def reference(self, text: str) -> None:
        """参考文献条目：悬挂缩进、小四号。"""
        para = self.doc.add_paragraph()
        para.paragraph_format.left_indent = Cm(0.74)
        para.paragraph_format.first_line_indent = Cm(-0.74)
        para.paragraph_format.space_after = Pt(3)
        run = para.add_run(text)
        _set_run_font(run, 10.5)

    # ==================================================================
    def save(self, path: str) -> str:
        folder = os.path.dirname(os.path.abspath(path))
        if folder:
            os.makedirs(folder, exist_ok=True)
        self.doc.save(path)
        return path
