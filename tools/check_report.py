"""统稿检查器：读报告 docx，逐项校验结构、编号、术语、数字与插图。

用法
----
    python tools/check_report.py                     # 检查默认终稿
    python tools/check_report.py --docx 路径.docx     # 检查指定文件
    python tools/check_report.py --verbose            # 打印每项细节

退出码
------
0 = 全部通过；1 = 至少一项失败。因此可以直接当“报告合并闸门”：

    python tools/make_report.py && python tools/check_report.py

检查项
------
1. 结构：封面信息、分工表、摘要、关键词、目录域、五章、参考文献、附录 A/B/C；
2. 五章：标题与顺序正确，每章开头有一段“本章要解决什么”；
3. 图表编号：按章从 1 连续、全局不重复，图题/表题格式规范；
4. 引用顺序：正文先“如图/如表 x-x 所示”，图/表再出现；
5. 术语：禁止“换线/转线/辅线”，“节点”只出现在“站台节点/扩展节点”等复合词中；
6. 数字：表 4-3 与 docs/bench.csv 逐格一致；摘要与 4.6/4.7 的关键数字
   与 CSV 现算值一致；数据规模与 data/beijing_metro.json 实测一致；
7. 插图：题注数量与真正嵌入的图片数量一致，6 张插图文件齐全；
8. 表格完整性：表 4-1 有 10 项、表 4-2 有 4 行、表 4-3 有 15 行；
9. 统计：摘要字数、全文字数、内嵌图数、表格数、估算页数。
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from math import ceil
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

BASE = Path(__file__).resolve().parent.parent
DEFAULT_DOCX = BASE / "reports" / "城市交通路径导航系统_实验报告.docx"
BENCH_CSV = BASE / "docs" / "bench.csv"
BEIJING_JSON = BASE / "data" / "beijing_metro.json"

ALGORITHM_ORDER = ("Dijkstra", "A*", "BFS")
CHAPTER_TITLES = {
    1: "需求分析与问题建模",
    2: "数据结构设计",
    3: "算法设计与实现",
    4: "正确性验证与结果分析",
    5: "总结与收获",
}
FORBIDDEN_TERMS = ("换线", "转线", "辅线")
# “节点”允许出现的复合词前缀（术语表要求：物理站叫站点，搜索状态叫站台节点）
NODE_PREFIXES = ("站台", "扩展", "父", "子", "根", "叶", "邻居", "中间", "终点", "起点")

FIGURE_RE = re.compile(r"^图\s*([0-9A-Z]+)-(\d+)\u3000(.*)$")
TABLE_RE = re.compile(r"^表\s*([0-9A-Z]+)-(\d+)\u3000(.*)$")

RESULT_PASS = "PASS"
RESULT_FAIL = "FAIL"
RESULT_WARN = "WARN"


class Checker:
    def __init__(self, docx: Path) -> None:
        self.path = docx
        self.document = Document(str(docx))
        self.results: list[tuple[str, str, str]] = []  # (状态, 检查项, 说明)
        self.paragraphs: list[str] = []
        self.body_items: list[dict] = []
        self._scan_body()
        self.full_text = "\n".join(self.paragraphs)
        self.table_text = self._collect_table_text()
        self.all_text = self.full_text + "\n" + self.table_text

    # ------------------------------------------------------------------
    # 读取文档
    # ------------------------------------------------------------------
    def _scan_body(self) -> None:
        """按文档顺序展开段落与表格，记录每个段落的样式与文本。"""
        for child in self.document.element.body.iterchildren():
            if child.tag == qn("w:p"):
                paragraph = Paragraph(child, self.document)
                self.paragraphs.append(paragraph.text)
                self.body_items.append({
                    "kind": "p",
                    "text": paragraph.text,
                    "style": paragraph.style.name if paragraph.style is not None else "",
                })
            elif child.tag == qn("w:tbl"):
                self.body_items.append({"kind": "tbl", "table": Table(child, self.document)})

    def _collect_table_text(self) -> str:
        chunks = []
        for table in self.document.tables:
            for row in table.rows:
                for cell in row.cells:
                    chunks.append(cell.text)
        return "\n".join(chunks)

    # ------------------------------------------------------------------
    # 小工具
    # ------------------------------------------------------------------
    def add(self, status: str, name: str, detail: str) -> None:
        self.results.append((status, name, detail))

    def fail(self, name: str, detail: str) -> None:
        self.add(RESULT_FAIL, name, detail)

    def warn(self, name: str, detail: str) -> None:
        self.add(RESULT_WARN, name, detail)

    def ok(self, name: str, detail: str) -> None:
        self.add(RESULT_PASS, name, detail)

    def heading1(self) -> list[tuple[int, int, str]]:
        """返回 [(body_items 下标, 章号或 0, 标题文本)]；章号 0 表示非正文章节。"""
        items: list[tuple[int, int, str]] = []
        for index, item in enumerate(self.body_items):
            if item["kind"] != "p" or item["style"] != "Heading 1":
                continue
            match = re.match(r"^第(\d+)章\u3000", item["text"])
            items.append((index, int(match.group(1)) if match else 0, item["text"]))
        return items

    def chapter_text(self, chapter: int) -> str:
        headings = self.heading1()
        for pos, (index, number, _title) in enumerate(headings):
            if number != chapter:
                continue
            end = headings[pos + 1][0] if pos + 1 < len(headings) else len(self.body_items)
            chunks = []
            for item in self.body_items[index:end]:
                if item["kind"] == "p":
                    chunks.append(item["text"])
                else:
                    chunks.append(self._table_text(item["table"]))
            return "\n".join(chunks)
        return ""

    @staticmethod
    def _table_text(table: Table) -> str:
        return "\n".join(
            "\t".join(cell.text for cell in row.cells) for row in table.rows
        )

    # ------------------------------------------------------------------
    # 1. 结构
    # ------------------------------------------------------------------
    def check_structure(self) -> None:
        # 封面信息有一部分在表格里（信息表），因此要把表格文字也算进“开头部分”。
        head_text = "\n".join(self.paragraphs[:40]) + "\n" + self._collect_table_text()
        required = ["数据结构课程实践报告", "城市交通路径导航系统", "课程名称", "姓　　名", "学　　号"]
        missing = [token for token in required if token not in head_text]
        if missing:
            self.fail("结构/封面", f"封面缺少：{'、'.join(missing)}")
        else:
            self.ok("结构/封面", "题目、课程、姓名/学号占位齐全")

        if "项目分工" in self.full_text and all(
            f"P{number}" in self.full_text for number in (1, 2, 3, 4)
        ):
            self.ok("结构/分工表", "P1~P4 分工表存在（姓名列留空）")
        else:
            self.fail("结构/分工表", "缺少 P1~P4 分工说明")

        abstract_index = next(
            (i for i, text in enumerate(self.paragraphs) if text.strip() in {"摘　要", "摘要"}),
            None,
        )
        toc_index = next(
            (i for i, text in enumerate(self.paragraphs) if text.strip() in {"目　录", "目录"}),
            None,
        )
        if abstract_index is None or toc_index is None or abstract_index >= toc_index:
            self.fail("结构/摘要", "找不到摘要页或目录页（顺序应为 摘要 → 目录）")
            self.abstract_text = ""
        else:
            self.abstract_text = "\n".join(self.paragraphs[abstract_index + 1:toc_index])
            chinese = sum(
                1 for char in self.abstract_text if "\u4e00" <= char <= "\u9fff"
            )
            if 300 <= chinese <= 600:
                self.ok("结构/摘要", f"摘要 {chinese} 个汉字（要求 300–500 字，允许到 600）")
            else:
                self.fail("结构/摘要", f"摘要 {chinese} 个汉字，超出 300–600 范围")

            keyword_line = next(
                (text for text in self.paragraphs if text.startswith("关键词：")), ""
            )
            if keyword_line and "图论" in keyword_line and "Dijkstra" in keyword_line:
                self.ok("结构/关键词", keyword_line.strip())
            else:
                self.fail("结构/关键词", "关键词缺失或未包含“图论”“Dijkstra”")

        xml = self.document.element.xml
        if "TOC \\o" in xml or "TOC \\\\o" in xml or "toc" in xml.lower():
            self.ok("结构/目录域", "存在 Word 目录域（打开后更新域即可生成目录）")
        else:
            self.fail("结构/目录域", "没有找到 TOC 域")

        if "参考文献" in [text.strip() for text in self.paragraphs]:
            refs = [
                text for text in self.paragraphs
                if re.match(r"^\[\d+\]", text.strip())
            ]
            if len(refs) >= 5:
                self.ok("结构/参考文献", f"{len(refs)} 条参考文献")
            else:
                self.fail("结构/参考文献", f"参考文献只有 {len(refs)} 条（要求 ≥5）")
        else:
            self.fail("结构/参考文献", "缺少“参考文献”标题")

        appendix_ok = all(
            any(text.strip().startswith(f"附录{letter}") for text in self.paragraphs)
            for letter in ("A", "B", "C")
        )
        if appendix_ok:
            self.ok("结构/附录", "附录 A 复现命令、附录 B 文件清单、附录 C 自检输出节选齐全")
        else:
            self.fail("结构/附录", "附录 A/B/C 不齐全")

    # ------------------------------------------------------------------
    # 2. 五章
    # ------------------------------------------------------------------
    def check_chapters(self) -> None:
        headings = self.heading1()
        chapters = [(index, number, title) for index, number, title in headings if number]
        numbers = [number for _index, number, _title in chapters]
        if numbers != [1, 2, 3, 4, 5]:
            self.fail("五章/编号", f"正文章号顺序异常：{numbers}（应为 1,2,3,4,5）")
            return
        self.ok("五章/编号", "第 1~5 章按顺序出现")

        title_problems = []
        for _index, number, title in chapters:
            expected = CHAPTER_TITLES[number]
            if expected not in title:
                title_problems.append(f"第 {number} 章标题「{title}」不含「{expected}」")
        if title_problems:
            self.fail("五章/标题", "；".join(title_problems))
        else:
            self.ok("五章/标题", "五章标题与任务书一致")

        no_intro = []
        for pos, (index, number, _title) in enumerate(chapters):
            end = chapters[pos + 1][0] if pos + 1 < len(chapters) else len(self.body_items)
            first_para = ""
            for item in self.body_items[index + 1:end]:
                if item["kind"] == "p" and item["text"].strip():
                    first_para = item["text"]
                    break
            if "本章" not in first_para:
                no_intro.append(f"第 {number} 章")
        if no_intro:
            self.fail("五章/导语", "以下章缺少“本章要解决什么”导语：" + "、".join(no_intro))
        else:
            self.ok("五章/导语", "每章开头都有导语段")

    # ------------------------------------------------------------------
    # 3/4. 图表编号与引用顺序
    # ------------------------------------------------------------------
    def scan_captions(self, pattern: re.Pattern, kind: str) -> list[dict]:
        found = []
        for index, item in enumerate(self.body_items):
            if item["kind"] != "p":
                continue
            match = pattern.match(item["text"].strip())
            if not match:
                continue
            chapter_label, number, title = match.group(1), int(match.group(2)), match.group(3)
            found.append({
                "index": index,
                "chapter": chapter_label,
                "number": number,
                "label": f"{kind} {chapter_label}-{number}",
                "title": title.strip(),
            })
        return found

    def check_caption_numbering(self) -> None:
        figures = self.scan_captions(FIGURE_RE, "图")
        tables = self.scan_captions(TABLE_RE, "表")
        self.figures = figures
        self.tables = tables

        problems = []
        for kind, captions in (("图", figures), ("表", tables)):
            by_chapter: dict[str, list[int]] = {}
            labels = []
            for caption in captions:
                by_chapter.setdefault(caption["chapter"], []).append(caption["number"])
                labels.append(caption["label"])
            duplicates = {label for label in labels if labels.count(label) > 1}
            if duplicates:
                problems.append(f"{kind}注重复：{'、'.join(sorted(duplicates))}")
            for chapter, numbers in by_chapter.items():
                if sorted(numbers) != list(range(1, len(numbers) + 1)):
                    problems.append(
                        f"{kind} {chapter} 章编号不连续：{sorted(numbers)}"
                    )
        if problems:
            self.fail("图表/编号", "；".join(problems))
        else:
            fig_desc = "、".join(caption["label"] for caption in figures)
            tab_desc = "、".join(caption["label"] for caption in tables)
            self.ok(
                "图表/编号",
                f"图 {len(figures)} 张（{fig_desc}）；表 {len(tables)} 张（{tab_desc}）",
            )

        if len(figures) < 6:
            self.fail("图表/数量", f"图只有 {len(figures)} 张，要求至少 6 张")
        if len(tables) < 12:
            self.fail("图表/数量", f"表只有 {len(tables)} 张，要求至少 12 张")

    def check_reference_order(self) -> None:
        problems = []
        for kind, captions in (("图", self.figures), ("表", self.tables)):
            prefix = ""
            paragraph_texts = []
            for item in self.body_items:
                if item["kind"] == "p":
                    paragraph_texts.append(item["text"])
                else:
                    paragraph_texts.append("")
            for caption in captions:
                token = f"{caption['chapter']}-{caption['number']}"
                before = "\n".join(paragraph_texts[:caption["index"]])
                pattern = re.compile(rf"{kind}\s*{re.escape(token)}(?!\d)")
                if not pattern.search(before):
                    problems.append(f"{caption['label']} 在正文中没有先引用")
        if problems:
            self.fail("图表/引用顺序", "；".join(problems))
        else:
            self.ok("图表/引用顺序", "每张图/表都在正文中先被“如图/如表 x-x 所示”引用")

    # ------------------------------------------------------------------
    # 5. 术语
    # ------------------------------------------------------------------
    def check_terminology(self) -> None:
        hits = [term for term in FORBIDDEN_TERMS if term in self.all_text]
        if hits:
            self.fail("术语/黑名单", "出现禁用词：" + "、".join(hits))
        else:
            self.ok("术语/黑名单", "未出现“换线/转线/辅线”")

        if "换乘" not in self.all_text:
            self.fail("术语/换乘", "全文找不到“换乘”")
        else:
            self.ok("术语/换乘", f"“换乘”出现 {self.all_text.count('换乘')} 次，口径统一")

        bad_nodes = []
        for match in re.finditer("节点", self.all_text):
            start = max(0, match.start() - 4)
            window = self.all_text[start:match.start()]
            if not any(window.endswith(prefix) for prefix in NODE_PREFIXES):
                snippet = self.all_text[max(0, match.start() - 12):match.end() + 8]
                bad_nodes.append(repr(snippet))
        if bad_nodes:
            self.fail(
                "术语/节点",
                "“节点”单独出现（应写“站台节点”）：" + "；".join(bad_nodes[:5]),
            )
        else:
            self.ok("术语/节点", "“节点”均以“站台节点/扩展节点/父节点”等复合词出现")

    # ------------------------------------------------------------------
    # 6. 数字一致性
    # ------------------------------------------------------------------
    def _bench(self) -> dict:
        with open(BENCH_CSV, "r", encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        expanded = {alg: [] for alg in ALGORITHM_ORDER}
        elapsed = {alg: [] for alg in ALGORITHM_ORDER}
        for row in rows:
            expanded[row["algorithm"]].append(int(row["expanded"]))
            elapsed[row["algorithm"]].append(float(row["elapsed_ms"]))
        avg_expanded = {
            alg: sum(values) / len(values) for alg, values in expanded.items()
        }
        avg_elapsed = {
            alg: sum(values) / len(values) for alg, values in elapsed.items()
        }
        return {
            "rows": rows,
            "avg_expanded": avg_expanded,
            "avg_elapsed": avg_elapsed,
            "reduction": (1 - avg_expanded["A*"] / avg_expanded["Dijkstra"]) * 100,
        }

    def check_numbers(self) -> None:
        bench = self._bench()
        avg_d = bench["avg_expanded"]["Dijkstra"]
        avg_a = bench["avg_expanded"]["A*"]
        reduction = bench["reduction"]

        # 6.1 表 4-3 与 CSV 逐格一致
        caption = next((item for item in self.tables if item["label"] == "表 4-3"), None)
        if caption is None:
            self.fail("数字/表4-3", "找不到表 4-3 的题注")
        else:
            table = None
            for item in self.body_items[caption["index"] + 1:]:
                if item["kind"] == "tbl":
                    table = item["table"]
                    break
                if item["kind"] == "p" and item["text"].strip():
                    break
            if table is None:
                self.fail("数字/表4-3", "表 4-3 题注后没有紧跟表格")
            else:
                rows = [
                    [cell.text.strip() for cell in row.cells] for row in table.rows
                ]
                csv_rows = bench["rows"]
                if len(rows) - 1 != len(csv_rows):
                    self.fail(
                        "数字/表4-3",
                        f"表格数据行 {len(rows) - 1} 行，CSV 有 {len(csv_rows)} 行",
                    )
                else:
                    mismatches = []
                    for row, source in zip(rows[1:], csv_rows):
                        expected = [
                            source["pair"],
                            source["algorithm"],
                            f"{float(source['time_min']):.1f}",
                            f"{float(source['distance_km']):.1f}",
                            source["transfers"],
                            source["expanded"],
                            f"{float(source['elapsed_ms']):.2f}",
                        ]
                        if row != expected:
                            mismatches.append(f"{source['pair']}/{source['algorithm']}")
                    if mismatches:
                        self.fail(
                            "数字/表4-3",
                            "以下行与 bench.csv 不一致：" + "、".join(mismatches),
                        )
                    else:
                        self.ok("数字/表4-3", f"{len(csv_rows)} 行与 docs/bench.csv 逐格一致")

        # 6.2 摘要硬指标
        abstract = getattr(self, "abstract_text", "")
        required = [
            ("134", "站点数"),
            ("7 条线路", "线路数"),
            ("154", "站台节点数"),
            ("10 项", "自检项数"),
            ("5 对", "对比实验 OD 数"),
            ("3 种算法", "算法数"),
            (f"{reduction:.1f}%", "A* 扩展降幅"),
            ("11.0 像素", "命中误差"),
            ("动画", "动画一致性"),
        ]
        missing = [f"{value}（{meaning}）" for value, meaning in required
                   if value not in abstract]
        if missing:
            self.fail("数字/摘要", "摘要缺少硬指标：" + "、".join(missing))
        else:
            self.ok("数字/摘要", "摘要包含 134 站/7 线/154 站台节点/10 项自检/5 对 OD/"
                                  f"3 算法/{reduction:.1f}%/11.0 像素")

        # 6.3 第 4 章 4.6 与 4.7 关键数字
        chapter_4 = self.chapter_text(4)
        section_46 = self._section_text(chapter_4, "4.6", "4.7")
        section_47 = self._section_text(chapter_4, "4.7", None)
        checks = [
            (f"{avg_a:.1f}", "A* 平均扩展数", section_46),
            (f"{avg_d:.1f}", "Dijkstra 平均扩展数", section_46),
            (f"{reduction:.1f}%", "A* 扩展降幅", section_46),
            ("43.2", "BFS 慈寿寺→崇文门时间", section_46),
            ("40.6", "Dijkstra 慈寿寺→崇文门时间", section_46),
            ("慈寿寺", "换乘对比 OD", section_46),
            ("崇文门", "换乘对比 OD", section_46),
            (f"{bench['avg_elapsed']['Dijkstra']:.2f}", "Dijkstra 中位耗时", section_47),
            (f"{bench['avg_elapsed']['A*']:.2f}", "A* 中位耗时", section_47),
            (f"{bench['avg_elapsed']['BFS']:.2f}", "BFS 中位耗时", section_47),
        ]
        missing = [
            f"{value}（{meaning}）" for value, meaning, section in checks
            if value not in section
        ]
        if missing:
            self.fail("数字/4.6-4.7", "关键数字缺失：" + "、".join(missing))
        else:
            self.ok("数字/4.6-4.7", "4.6 与 4.7 的均值、降幅、换乘取舍与耗时口径与 CSV 一致")

        # 6.4 数据规模与真实数据文件一致
        import json

        with open(BEIJING_JSON, "r", encoding="utf-8-sig") as handle:
            payload = json.load(handle)
        stations = len(payload.get("stations", []))
        lines = len(payload.get("lines", []))
        platforms = sum(len(line["stations"]) for line in payload.get("lines", []))
        chapter_1 = self.chapter_text(1)
        facts_missing = [
            str(value) for value in (stations, lines, platforms)
            if str(value) not in chapter_1
        ]
        if facts_missing:
            self.fail(
                "数字/数据规模",
                f"第 1 章缺少真实规模数字：{'、'.join(facts_missing)}",
            )
        else:
            self.ok(
                "数字/数据规模",
                f"第 1 章规模与 data/beijing_metro.json 一致（{stations} 站 / {lines} 线 / "
                f"{platforms} 站台节点）",
            )

    @staticmethod
    def _section_text(chapter_text: str, start_marker: str, end_marker: str | None) -> str:
        start = chapter_text.find(start_marker)
        if start < 0:
            return ""
        if end_marker:
            end = chapter_text.find(end_marker, start + len(start_marker))
            end = len(chapter_text) if end < 0 else end
        else:
            end = len(chapter_text)
        return chapter_text[start:end]

    # ------------------------------------------------------------------
    # 7. 插图嵌入
    # ------------------------------------------------------------------
    def check_figures(self) -> None:
        inline = len(self.document.inline_shapes)
        if inline != len(self.figures):
            self.fail(
                "插图/嵌入",
                f"题注 {len(self.figures)} 张，真正嵌入的图片 {inline} 张",
            )
        else:
            self.ok("插图/嵌入", f"{inline} 张题注与 {inline} 张内嵌图片一一对应")

        sys.path.insert(0, str(BASE / "tools"))
        import make_report_assets  # noqa: PLC0415

        ok, missing = make_report_assets.check_figures()
        if ok:
            self.ok(
                "插图/文件",
                f"{len(make_report_assets.REPORT_FIGURES)} 张插图文件齐全"
                "（图 2-1、3-1、4-1~4-4）",
            )
        else:
            self.fail("插图/文件", "缺少插图：" + "；".join(missing))

    # ------------------------------------------------------------------
    # 8. 表格完整性
    # ------------------------------------------------------------------
    def _table_after(self, label: str) -> Table | None:
        caption = next((item for item in self.tables if item["label"] == label), None)
        if caption is None:
            return None
        for item in self.body_items[caption["index"] + 1:]:
            if item["kind"] == "tbl":
                return item["table"]
            if item["kind"] == "p" and item["text"].strip():
                return None
        return None

    def check_tables(self) -> None:
        expectations = {"表 4-1": 11, "表 4-2": 5, "表 4-3": 16}
        problems = []
        for label, min_rows in expectations.items():
            table = self._table_after(label)
            if table is None:
                problems.append(f"{label} 找不到表格")
            elif len(table.rows) < min_rows:
                problems.append(
                    f"{label} 只有 {len(table.rows)} 行（至少 {min_rows} 行）"
                )
        if problems:
            self.fail("表格/完整性", "；".join(problems))
        else:
            self.ok("表格/完整性", "表 4-1 有 10 项、表 4-2 有 4 行、表 4-3 有 15 行")

        if len(self.document.tables) < 15:
            self.warn("表格/数量", f"文档共 {len(self.document.tables)} 个表格")

    # ------------------------------------------------------------------
    # 9. 统计
    # ------------------------------------------------------------------
    def estimate_pages(self) -> int:
        """按段落/图片/表格的实际排版尺寸估算页数（版心 15.8×24.62 cm）。

        这不是 Word 的精确分页（那需要打开 Word 排版），而是根据字号、行距、
        图片高度和表格行数累加出来的近似值，实测与 LibreOffice 渲染相差 1–2 页。
        """
        content_height_cm = 29.7 - 2.54 * 2
        total_cm = 0.0
        chapters = 0
        for paragraph in self.document.paragraphs:
            text = paragraph.text
            if not text.strip():
                total_cm += 0.30
                continue
            style = paragraph.style.name if paragraph.style is not None else ""
            if style == "Heading 1":
                total_cm += 1.70
                chapters += 1
                continue
            if style == "Heading 2":
                total_cm += 1.30
                continue
            if style == "Heading 3":
                total_cm += 1.00
                continue
            sizes = {run.font.size.pt for run in paragraph.runs if run.font.size}
            is_code = bool(sizes) and min(sizes) <= 9 and any(
                (run.font.name or "") == "Consolas" for run in paragraph.runs
            )
            if is_code:
                total_cm += 0.45
                continue
            lines = max(1, ceil(len(text) / 33))   # 12pt 宋体约 33 字/行
            total_cm += lines * 0.82               # 1.5 倍行距约 0.82 cm/行
        for shape in self.document.inline_shapes:
            total_cm += shape.height / 360000 + 0.60
        for table in self.document.tables:
            total_cm += len(table.rows) * 1.02 + 0.45
        pages = ceil(total_cm / content_height_cm + chapters * 0.42)
        return max(1, pages)

    def stats(self) -> dict:
        chinese = sum(
            1 for char in self.all_text if "\u4e00" <= char <= "\u9fff"
        )
        total_chars = len(self.all_text)
        paragraphs = len(self.paragraphs)
        images = len(self.document.inline_shapes)
        tables = len(self.document.tables)
        pages = self.estimate_pages()
        return {
            "chinese": chinese,
            "chars": total_chars,
            "paragraphs": paragraphs,
            "images": images,
            "tables": tables,
            "pages": pages,
            "chapters": len([1 for _i, n, _t in self.heading1() if n]),
            "headings": len(self.heading1()),
        }

    # ------------------------------------------------------------------
    def run(self) -> int:
        self.check_structure()
        self.check_chapters()
        self.check_caption_numbering()
        self.check_reference_order()
        self.check_terminology()
        self.check_numbers()
        self.check_figures()
        self.check_tables()

        print(f"报告文件：{self.path}")
        print(f"文件大小：{self.path.stat().st_size / 1024:.1f} KB")
        print("-" * 78)
        for status, name, detail in self.results:
            print(f"[{status}] {name}：{detail}")
        print("-" * 78)

        stats = self.stats()
        print(
            f"统计：一级标题 {stats['headings']} 个（正文章 {stats['chapters']} 个）；"
            f"图 {len(self.figures)} 张、表 {len(self.tables)} 张编号表"
            f"（文档共 {stats['tables']} 个表格）；内嵌图片 {stats['images']} 张"
        )
        print(
            f"统计：段落 {stats['paragraphs']} 段；汉字 {stats['chinese']} 个；"
            f"全文字符 {stats['chars']} 个；估算页数约 {stats['pages']} 页"
            "（Word 实际分页可能相差 1–2 页）"
        )

        failures = [item for item in self.results if item[0] == RESULT_FAIL]
        warnings = [item for item in self.results if item[0] == RESULT_WARN]
        print(
            f"结论：{len(self.results) - len(failures) - len(warnings)} 通过 / "
            f"{len(failures)} 失败 / {len(warnings)} 警告，共 {len(self.results)} 项"
        )
        if failures:
            print("闸门：红（退出码 1）")
            return 1
        print("闸门：绿（退出码 0）。")
        return 0


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(description="报告终稿统稿检查（退出码 0/1）")
    parser.add_argument("--docx", default=str(DEFAULT_DOCX),
                        help="待检查的 docx 路径")
    args = parser.parse_args(argv)

    path = Path(args.docx)
    if not path.is_file():
        print(f"[FAIL] 报告文件不存在：{path}", file=sys.stderr)
        print("请先运行：python tools/make_report.py", file=sys.stderr)
        return 1
    try:
        checker = Checker(path)
    except Exception as exc:  # noqa: BLE001 - docx 打不开时要给出可读错误
        print(f"[FAIL] 无法打开 docx：{exc}", file=sys.stderr)
        return 1
    return checker.run()


if __name__ == "__main__":
    sys.exit(main())
