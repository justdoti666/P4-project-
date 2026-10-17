"""生成报告终稿的插图资产（Pillow 绘制，不依赖 GUI）。

职责
----
1. 绘制 **图 2-1「系统模块划分与数据流」**，输出到
   ``docs/figures/report/fig2-1_arch.png``；
2. 校验报告要用的其余插图是否齐全（缺哪张就报哪张，不静默跳过）。

用法
----
    python tools/make_report_assets.py            # 生成图 2-1 并校验全部插图
    python tools/make_report_assets.py --check    # 只校验，不重新画图
    python tools/make_report_assets.py --force    # 强制重画图 2-1

说明：图内的中文用系统自带「微软雅黑」，因此这里固定使用 Windows 字体路径；
找不到字体时直接报错，避免生成一张“方块字”图混进报告。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FIG_DIR = PROJECT_ROOT / "docs" / "figures"
REPORT_FIG_DIR = FIG_DIR / "report"
ARCH_FIG = REPORT_FIG_DIR / "fig2-1_arch.png"

FONT_CANDIDATES = [
    Path(r"C:\Windows\Fonts\msyh.ttc"),      # 微软雅黑
    Path(r"C:\Windows\Fonts\msyhbd.ttc"),    # 微软雅黑 Bold
    Path(r"C:\Windows\Fonts\simhei.ttf"),    # 黑体
]
FONT_BOLD_CANDIDATES = [
    Path(r"C:\Windows\Fonts\msyhbd.ttc"),
    Path(r"C:\Windows\Fonts\simhei.ttf"),
]

# 报告里要引用/嵌入的全部插图：编号 -> (路径, 用途说明)
REPORT_FIGURES = {
    "图 2-1": (REPORT_FIG_DIR / "fig2-1_arch.png", "系统模块划分与数据流（本脚本绘制）"),
    "图 3-1": (FIG_DIR / "fig3-1_ui.png", "主界面截图（真实窗口导出）"),
    "图 4-1": (FIG_DIR / "fig_p4_demo_path.png", "10 站演示路径（10/10 站名、5/5 分段标注）"),
    "图 4-2": (FIG_DIR / "fig_p4_beijing_path.png", "134 站北京路径（密集站名按优先级省略）"),
    "图 4-3": (FIG_DIR / "fig_p4_zoom.png", "2× 缩放效果（命中误差 11.0 像素）"),
    "图 4-4": (FIG_DIR / "fig4-4_expanded.png", "三种算法扩展节点数对比（tools/bench.py 生成）"),
}

# 配色：与报告正文、ui/canvas.py 的蓝紫灰体系保持一致
COLOR_BG = "#FFFFFF"
COLOR_SUB = "#475569"
COLOR_LINE = "#64748B"
COLOR_NOTE_BG = "#F8FAFC"
COLOR_NOTE_BORDER = "#E2E8F0"

THEMES = {
    "data": ("#ECFDF5", "#059669", "#065F46"),
    "core": ("#EFF6FF", "#2563EB", "#1E3A8A"),
    "ui": ("#F5F3FF", "#7C3AED", "#5B21B6"),
    "tools": ("#FFF7ED", "#D97706", "#9A3412"),
}

CANVAS_SIZE = (1400, 1090)

# 版式常量（左列核心层、右列界面层、底部说明条）
LEFT_X1, LEFT_X2 = 50, 700
RIGHT_X1, RIGHT_X2 = 760, 1210
BOX_TITLE_SIZE = 34
BOX_LINE_SIZE = 26
NOTE_SIZE = 23


# ----------------------------------------------------------------------
# 字体与绘图小工具
# ----------------------------------------------------------------------
def _first_existing(paths: list[Path]) -> Path:
    for path in paths:
        if path.is_file():
            return path
    raise FileNotFoundError(
        "找不到中文字体，请确认系统里有微软雅黑/黑体："
        + "、".join(str(p) for p in paths)
    )


_FONT_REGULAR = _first_existing(FONT_CANDIDATES)
_FONT_BOLD = _first_existing(FONT_BOLD_CANDIDATES)
_FONT_CACHE: dict[tuple[int, bool], ImageFont.FreeTypeFont] = {}


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    key = (int(size), bool(bold))
    if key not in _FONT_CACHE:
        path = _FONT_BOLD if bold else _FONT_REGULAR
        _FONT_CACHE[key] = ImageFont.truetype(str(path), int(size))
    return _FONT_CACHE[key]


def text_width(draw: ImageDraw.ImageDraw, text: str, size: int, bold: bool = False) -> float:
    return draw.textlength(text, font=font(size, bold))


def fit_size(
    draw: ImageDraw.ImageDraw,
    text: str,
    preferred: int,
    max_width: float,
    minimum: int = 20,
    bold: bool = False,
) -> int:
    """在 [minimum, preferred] 里找一个能塞进 max_width 的字号。

    宁可缩小说明文字，也不让文字压出卡片边框——报告里的图要能看清。
    """
    size = preferred
    while size > minimum and text_width(draw, text, size, bold) > max_width:
        size -= 1
    if text_width(draw, text, size, bold) > max_width:
        raise ValueError(f"文字过长，最小字号也放不下：{text!r}")
    return size


def dashed_line(draw, points, color, width=4, dash=12, gap=8):
    for (x1, y1), (x2, y2) in zip(points, points[1:]):
        length = max(abs(x2 - x1), abs(y2 - y1))
        if length <= 0:
            continue
        dx, dy = (x2 - x1) / length, (y2 - y1) / length
        pos = 0.0
        while pos < length:
            end = min(pos + dash, length)
            draw.line(
                (x1 + dx * pos, y1 + dy * pos, x1 + dx * end, y1 + dy * end),
                fill=color,
                width=width,
            )
            pos = end + gap


def arrow(draw, points, color=COLOR_LINE, width=4, dashed=False, head=16):
    """折线箭头：最后一段的终点画三角箭头。"""
    if dashed:
        dashed_line(draw, points, color, width=width)
    else:
        draw.line(points, fill=color, width=width, joint="curve")
    (x1, y1), (x2, y2) = points[-2], points[-1]
    if abs(x2 - x1) >= abs(y2 - y1):
        direction = 1 if x2 > x1 else -1
        triangle = [
            (x2, y2),
            (x2 - direction * head, y2 - head * 0.55),
            (x2 - direction * head, y2 + head * 0.55),
        ]
    else:
        direction = 1 if y2 > y1 else -1
        triangle = [
            (x2, y2),
            (x2 - head * 0.55, y2 - direction * head),
            (x2 + head * 0.55, y2 - direction * head),
        ]
    draw.polygon(triangle, fill=color)


def arrow_label(draw, cx, cy, text, size=24):
    """箭头旁边的白底标签，避免压在箭头上看不清。"""
    fnt = font(size)
    box = draw.textbbox((0, 0), text, font=fnt)
    w, h = box[2] - box[0], box[3] - box[1]
    draw.rounded_rectangle(
        (cx - w / 2 - 8, cy - h / 2 - 5, cx + w / 2 + 8, cy + h / 2 + 5),
        radius=8,
        fill=COLOR_BG,
    )
    draw.text((cx, cy), text, font=fnt, fill=COLOR_SUB, anchor="mm")


def module_box(draw, xy, title, lines, theme: str):
    """一个模块卡片：标题 + 若干行说明；左侧竖条与描边表示所属层。"""
    fill, border, title_color = THEMES[theme]
    x1, y1, x2, y2 = xy
    draw.rounded_rectangle(xy, radius=18, fill=fill, outline=border, width=3)
    draw.rounded_rectangle((x1 + 4, y1 + 14, x1 + 13, y2 - 14), radius=4, fill=border)

    title_size = fit_size(
        draw, title, BOX_TITLE_SIZE, (x2 - x1) - 60, minimum=26, bold=True
    )
    draw.text((x1 + 30, y1 + 18), title, font=font(title_size, True), fill=title_color)

    line_size = min(
        fit_size(draw, line, BOX_LINE_SIZE, (x2 - x1) - 60, minimum=21)
        for line in lines
    )
    y = y1 + 18 + title_size + 18
    for line in lines:
        draw.text((x1 + 32, y), line, font=font(line_size), fill=COLOR_SUB)
        y += line_size + 12


# ----------------------------------------------------------------------
# 图 2-1：系统模块划分与数据流
# ----------------------------------------------------------------------
def draw_architecture(output: Path) -> Path:
    """绘制图 2-1：数据文件 → loader → graph → algorithms → window → canvas。"""
    width, height = CANVAS_SIZE
    image = Image.new("RGB", (width, height), COLOR_BG)
    draw = ImageDraw.Draw(image)

    # ---- 左列：数据层与核心层（自上而下单向数据流）----
    data_box = (LEFT_X1, 60, LEFT_X2, 220)
    loader_box = (LEFT_X1, 270, LEFT_X2, 430)
    graph_box = (LEFT_X1, 480, LEFT_X2, 640)
    algo_box = (LEFT_X1, 690, LEFT_X2, 880)

    module_box(
        draw, data_box, "数据文件（data/）",
        [
            "beijing_metro.json / .txt：134 站 / 7 条线",
            "demo_city · tiny_3 · disconnected_4",
        ],
        "data",
    )
    module_box(
        draw, loader_box, "core/loader.py",
        [
            "load_dataset() 解析 JSON / TXT",
            "字段校验 → DataFormatError 中文提示",
        ],
        "core",
    )
    module_box(
        draw, graph_box, "core/graph.py",
        [
            "MetroGraph：站台节点（站点, 线路）",
            "邻接表 + 乘车边 / 换乘边 + 权重",
        ],
        "core",
    )
    module_box(
        draw, algo_box, "core/algorithms.py",
        [
            "dijkstra / astar / bfs_min_transfers",
            "统一返回 RouteResult（站点链 + 分段 + 统计）",
            "结果交给 ui/window.py，界面不碰算法细节",
        ],
        "core",
    )

    arrow(draw, [(375, 220), (375, 270)])
    arrow_label(draw, 375, 245, "解析 / 校验")
    arrow(draw, [(375, 430), (375, 480)])
    arrow_label(draw, 375, 455, "建图")
    arrow(draw, [(375, 640), (375, 690)])
    arrow_label(draw, 375, 665, "solve()")

    # ---- 右列：界面层（窗口 → 画布）----
    window_box = (RIGHT_X1, 60, RIGHT_X2, 260)
    canvas_box = (RIGHT_X1, 330, RIGHT_X2, 620)
    tools_box = (RIGHT_X1, 660, RIGHT_X2, 870)

    module_box(
        draw, window_box, "ui/window.py（P3）",
        [
            "起点 / 终点下拉框 · 地图点选",
            "算法与速度切换 · 统计面板",
            "暂停 / 跳过 / 复位 / 导出按钮",
        ],
        "ui",
    )
    module_box(
        draw, canvas_box, "ui/canvas.py（P4）",
        [
            "CanvasView：渲染与交互组件",
            "世界→屏幕：等比缩放 + y 翻转",
            "站名避让 · 路径高亮 · 分段标注",
            "动画：1× / 2× / 4×、暂停、跳过",
            "导出 PNG（截图）/ PS（矢量）",
        ],
        "ui",
    )
    module_box(
        draw, tools_box, "tools/selfcheck.py（P4）",
        [
            "10 项自检矩阵 · 合并闸门",
            "任一失败 → 退出码 1",
            "AST 扫描 canvas 不 import core",
        ],
        "tools",
    )

    # algorithms → window：走两列之间的走廊（结果回流）
    arrow(draw, [(700, 785), (730, 785), (730, 160), (760, 160)])
    # window → canvas：窗口只调画布公开方法
    arrow(draw, [(985, 260), (985, 330)])
    arrow_label(draw, 985, 295, "公开方法")
    # selfcheck → 核心层：逐层复核（虚线，表示“旁挂闸门”）
    arrow(
        draw,
        [(985, 870), (985, 930), (375, 930), (375, 885)],
        color=THEMES["tools"][1],
        dashed=True,
    )
    arrow_label(draw, 690, 930, "逐层复核数据 / 算法 / 几何", size=22)

    # ---- 底部说明条：图例 + 分层约定 ----
    draw.rounded_rectangle(
        (LEFT_X1, 950, 1350, 1080), radius=14,
        fill=COLOR_NOTE_BG, outline=COLOR_NOTE_BORDER, width=2,
    )
    legend = [
        ("data", "数据文件"),
        ("core", "core/ 核心层"),
        ("ui", "ui/ 界面层"),
        ("tools", "tools/ 工程化"),
    ]
    x = 90
    for theme, label in legend:
        _fill, border, _title = THEMES[theme]
        draw.rounded_rectangle((x, 966, x + 24, 992), radius=6,
                               fill=border, outline=border)
        draw.text((x + 34, 979), label, font=font(24), fill=COLOR_SUB, anchor="lm")
        x += 34 + int(text_width(draw, label, 24)) + 54

    note_lines = [
        "分层约定：core/ 不 import Tkinter；ui/canvas.py 不 import core（自检第 10 项用 AST 扫描验证）。",
        "show_path 与 animate 共用同一份 PathView，因此“动画”与“立即显示”的统计数值完全一致。",
    ]
    note_size = min(
        fit_size(draw, line, NOTE_SIZE, 1250, minimum=19) for line in note_lines
    )
    for index, line in enumerate(note_lines):
        draw.text((LEFT_X1 + 24, 1012 + index * 32), line,
                  font=font(note_size), fill=COLOR_SUB)

    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, optimize=True)
    return output


# ----------------------------------------------------------------------
# 插图清单校验
# ----------------------------------------------------------------------
def check_figures(figures: dict | None = None) -> tuple[bool, list[str]]:
    """校验报告插图是否齐全，返回 (是否齐全, 缺少项说明列表)。"""
    missing: list[str] = []
    for label, (path, _purpose) in (figures or REPORT_FIGURES).items():
        if not path.is_file():
            missing.append(f"{label} → {path.relative_to(PROJECT_ROOT)}")
        elif path.stat().st_size < 1024:
            missing.append(
                f"{label} → {path.relative_to(PROJECT_ROOT)}（文件过小，疑似损坏）"
            )
    return (not missing), missing


def ensure_assets(force: bool = False) -> dict:
    """生成图 2-1（不存在或 force 时）并校验全部插图，返回 编号→路径 字典。"""
    if force or not ARCH_FIG.is_file():
        draw_architecture(ARCH_FIG)
        print(f"[ASSET] 已生成图 2-1：{ARCH_FIG.relative_to(PROJECT_ROOT)}")
    ok, missing = check_figures()
    if not ok:
        raise FileNotFoundError("报告插图缺失：\n  " + "\n  ".join(missing))
    return {label: path for label, (path, _purpose) in REPORT_FIGURES.items()}


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(description="生成/校验报告插图资产（图 2-1 等）")
    parser.add_argument("--check", action="store_true", help="只校验，不重新画图")
    parser.add_argument("--force", action="store_true", help="强制重画图 2-1")
    args = parser.parse_args(argv)

    if not args.check:
        draw_architecture(ARCH_FIG)
        print(f"[ASSET] 已生成：{ARCH_FIG.relative_to(PROJECT_ROOT)}")

    ok, missing = check_figures()
    print("[ASSET] 报告插图清单：")
    for label, (path, purpose) in REPORT_FIGURES.items():
        mark = "OK  " if path.is_file() else "缺失"
        print(f"  [{mark}] {label}  {path.relative_to(PROJECT_ROOT)}  —— {purpose}")
    if not ok:
        print("[ASSET] 缺少插图：\n  " + "\n  ".join(missing), file=sys.stderr)
        return 1
    print(f"[ASSET] 共 {len(REPORT_FIGURES)} 张插图齐全。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
