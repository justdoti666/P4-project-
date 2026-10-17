"""把画布导出成报告插图（P4-06）。

用法
----
    python tools/export_canvas.py _smoke/ui.png
    python tools/export_canvas.py _smoke/ui.ps
    python tools/export_canvas.py docs/figures/demo.png --demo --start S1 --end S8
    python tools/export_canvas.py --figure-pack

支持的参数
----------
--data      路网文件（默认 data/beijing_metro.json）
--demo      快捷使用 data/demo_city.json
--start/--end  站名或站点 ID；不填就自动挑一对连通站点
--algo      Dijkstra / A* / BFS
--zoom      1.0 表示适配窗口；2.0 表示放大两倍
--width/--height  画布尺寸（像素）
--no-path   只画路网，不画路径（适合做总览图）
--figure-pack  一次性生成报告要用的 4 张图 + 1 张 PS

导出原理
--------
PNG 用 Pillow 的 ImageGrab 截取画布区域；PS 用 Tk 自带的 PostScript，
是矢量格式，放大不糊，适合直接插入 Word/LaTeX。导出前会先声明 DPI 感知，
避免 Windows 125%/150% 缩放下截偏。
"""

from __future__ import annotations

import argparse
import os
import sys
import tkinter as tk
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ui.dpi import enable_high_dpi  # noqa: E402

from core import load_dataset, solve  # noqa: E402
from ui.canvas import BG, CanvasView  # noqa: E402

DEFAULT_DATA = PROJECT_ROOT / "data" / "beijing_metro.json"
DEMO_DATA = PROJECT_ROOT / "data" / "demo_city.json"


def find_station(graph, token: str) -> str:
    """按站点 ID、站名精确匹配或站名包含关系找到站点。"""
    token = str(token).strip()
    if token in graph.stations:
        return token
    exact = [sid for sid, station in graph.stations.items() if station.name == token]
    if len(exact) == 1:
        return exact[0]
    fuzzy = [sid for sid, station in graph.stations.items() if token in station.name]
    if len(fuzzy) == 1:
        return fuzzy[0]
    if len(fuzzy) > 1:
        example = "、".join(graph.stations[sid].name for sid in fuzzy[:6])
        raise SystemExit(f"站名“{token}”不唯一，可能是：{example}")
    raise SystemExit(f"找不到站点“{token}”（可以填站点 ID，例如 S001）")


def pick_pair(graph) -> tuple[str, str]:
    """自动挑一对连通的起终点，优先用演示数据里的固定组合。"""
    preferred = [("S001", "S061"), ("S1", "S8"), ("T1", "T3")]
    for start, end in preferred:
        if start in graph.stations and end in graph.stations:
            if solve(graph, "Dijkstra", start, end).found:
                return start, end
    ids = list(graph.stations)
    if len(ids) < 2:
        raise SystemExit("图里至少需要 2 个站点才能画路径")
    first = ids[0]
    for other in ids[1:]:
        if solve(graph, "Dijkstra", first, other).found:
            return first, other
    raise SystemExit("图里没有连通的站点对，无法画路径（可加 --no-path 只画路网）")


def render_one(
    *,
    data_path: Path,
    output: Path,
    width: int = 1400,
    height: int = 900,
    start: str | None = None,
    end: str | None = None,
    algorithm: str = "Dijkstra",
    zoom: float = 1.0,
    no_path: bool = False,
) -> dict:
    """创建一个临时 Tk 窗口，画好后导出，返回统计信息。"""
    dataset = load_dataset(str(data_path))
    graph = dataset.build_graph()

    root = tk.Tk()
    root.title("P4 画布导出")
    # 放在屏幕左上偏一点的位置：既可见，又不会挡住标题栏以外的内容
    root.geometry(f"{width}x{height}+30+30")
    root.configure(bg=BG)

    canvas = CanvasView(root, graph, width=width, height=height)
    canvas.pack(fill="both", expand=True)
    root.update_idletasks()
    root.update()

    metrics = None
    if not no_path:
        start_id = find_station(graph, start) if start else None
        end_id = find_station(graph, end) if end else None
        if not start_id or not end_id:
            start_id, end_id = pick_pair(graph)
        result = solve(graph, algorithm, start_id, end_id)
        metrics = canvas.show_path(result)
        if not result.found:
            print(f"[WARN] {dataset.stations[start_id].name} -> "
                  f"{dataset.stations[end_id].name} 不连通，导出“未找到路径”画面")
    if abs(zoom - 1.0) > 1e-9:
        canvas.set_zoom(zoom)
    canvas._redraw()
    root.update_idletasks()
    root.update()

    # 截图前把窗口提到最前面，避免抓到其它窗口
    root.lift()
    root.attributes("-topmost", True)
    root.update()
    saved = canvas.export(str(output))
    root.attributes("-topmost", False)
    root.update()
    label_count = len(canvas.station_label_boxes)
    hidden_count = len(canvas.hidden_station_labels)
    segment_count = len(canvas.segment_label_boxes)
    hidden_segments = canvas.hidden_segment_labels
    root.destroy()

    return {
        "saved": saved,
        "city": dataset.city,
        "stations": len(graph.stations),
        "lines": len(graph.lines),
        "metrics": metrics,
        "labels": label_count,
        "hidden_labels": hidden_count,
        "segments": segment_count,
        "hidden_segments": hidden_segments,
        "width": width,
        "height": height,
    }


def figure_pack(out_dir: Path) -> int:
    """生成报告插图：演示图、北京全图、缩放图、路径特写、PS 矢量图。"""
    out_dir.mkdir(parents=True, exist_ok=True)
    jobs = [
        dict(name="fig_p4_demo_path.png", data=DEMO_DATA, width=1200, height=800,
             start="S1", end="S8", zoom=1.0),
        dict(name="fig_p4_demo_overview.png", data=DEMO_DATA, width=1200, height=800,
             no_path=True),
        dict(name="fig_p4_beijing_path.png", data=DEFAULT_DATA, width=1400, height=900,
             start="S001", end="S061", zoom=1.0),
        dict(name="fig_p4_zoom.png", data=DEFAULT_DATA, width=1200, height=800,
             start="S040", end="S095", zoom=2.0),
        dict(name="fig_p4_canvas.ps", data=DEMO_DATA, width=1000, height=700,
             start="S1", end="S8", zoom=1.0),
    ]
    for job in jobs:
        name = job.pop("name")
        print(f"[FIG] 生成 {name} …")
        info = render_one(
            data_path=job.pop("data"),
            output=out_dir / name,
            width=job.pop("width"),
            height=job.pop("height"),
            start=job.pop("start", None),
            end=job.pop("end", None),
            algorithm=job.pop("algorithm", "Dijkstra"),
            zoom=job.pop("zoom", 1.0),
            no_path=job.pop("no_path", False),
        )
        print(f"      -> {info['saved']}  "
              f"({info['labels']} 个站名，省略 {info['hidden_labels']} 个)")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="导出 CanvasView 画布为 PNG/PS")
    parser.add_argument("output", nargs="?", default=str(PROJECT_ROOT / "_smoke" / "canvas.png"),
                        help="输出文件，.png/.jpg/.ps；默认 _smoke/canvas.png")
    parser.add_argument("--data", default=str(DEFAULT_DATA), help="路网数据文件")
    parser.add_argument("--demo", action="store_true", help="使用 10 站演示数据")
    parser.add_argument("--start", default=None, help="起点站名或 ID")
    parser.add_argument("--end", default=None, help="终点站名或 ID")
    parser.add_argument("--algo", default="Dijkstra", choices=["Dijkstra", "A*", "BFS"])
    parser.add_argument("--zoom", type=float, default=1.0, help="缩放倍率（0.5–3）")
    parser.add_argument("--width", type=int, default=1400)
    parser.add_argument("--height", type=int, default=900)
    parser.add_argument("--no-path", action="store_true", help="只画路网，不搜索路径")
    parser.add_argument("--figure-pack", action="store_true", help="生成 docs/figures 全套插图")
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    enable_high_dpi()
    args = build_parser().parse_args(argv)
    if args.figure_pack:
        return figure_pack(PROJECT_ROOT / "docs" / "figures")

    data_path = Path(args.demo and DEMO_DATA or args.data)
    output = Path(args.output)
    if not output.suffix:
        output = output.with_suffix(".png")
    output.parent.mkdir(parents=True, exist_ok=True)
    info = render_one(
        data_path=data_path,
        output=output,
        width=args.width,
        height=args.height,
        start=args.start,
        end=args.end,
        algorithm=args.algo,
        zoom=args.zoom,
        no_path=args.no_path,
    )
    print(f"已导出：{info['saved']}")
    print(f"  城市：{info['city']}  {info['stations']} 站 / {info['lines']} 线")
    if info["metrics"]:
        print(f"  统计：{info['metrics']}")
    print(f"  站名：画出 {info['labels']} 个，省略 {info['hidden_labels']} 个；"
          f"分段标注省略 {info['hidden_segments']} 个")
    return 0


if __name__ == "__main__":
    sys.exit(main())
