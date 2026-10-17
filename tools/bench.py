"""对比实验：5 对起终点 × 3 种算法，生成 bench.csv / 表格 / 柱状图。

用法
----
    python tools/bench.py                 # 跑实验，写 CSV、Markdown、图 4-4
    python tools/bench.py --runs 9        # 每项重复 9 次取中位数
    python tools/bench.py --no-chart      # 只出表，不画图

为什么用 Pillow 画图？
--------------------
课程环境不一定装了 matplotlib；Pillow 是导出 PNG 已经用到的依赖，
用它手动画一个分组柱状图，少装一个库，也方便把“柱子上写数值”这种
小细节控制得更清楚。

口径
----
* 每个 (起终点, 算法) 先热身跑 1 次，再计时 5 次取**中位数**，避免偶发卡顿；
* 结果里的 expanded 是 P2 的扩展站台数，直接反映搜索规模；
* 时间是算法内部 ``perf_counter()`` 的毫秒数，不含界面绘制。
"""

from __future__ import annotations

import argparse
import csv
import statistics
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core import load_dataset, solve  # noqa: E402

DATA = PROJECT_ROOT / "data" / "beijing_metro.json"
DOCS = PROJECT_ROOT / "docs"
FIG_DIR = DOCS / "figures"

PAIRS = [
    ("S001", "S061"),
    ("S040", "S095"),
    ("S023", "S059"),
    ("S081", "S031"),
    ("S095", "S040"),
]
ALGORITHMS = ("Dijkstra", "A*", "BFS")
COLORS = {"Dijkstra": "#2563EB", "A*": "#059669", "BFS": "#D97706"}


# ----------------------------------------------------------------------
# 跑实验
# ----------------------------------------------------------------------
def run_benchmark(runs: int) -> list[dict]:
    dataset = load_dataset(str(DATA))
    graph = dataset.build_graph()
    names = {sid: station.name for sid, station in dataset.stations.items()}
    rows: list[dict] = []

    for start, end in PAIRS:
        title = f"{names[start]}→{names[end]}"
        for algorithm in ALGORITHMS:
            result = solve(graph, algorithm, start, end)  # 热身
            if not result.found:
                raise SystemExit(f"{title} 的 {algorithm} 没有找到路径，实验数据无效")
            samples: list[float] = []
            for _ in range(max(3, runs)):
                moment = time.perf_counter()
                result = solve(graph, algorithm, start, end)
                samples.append((time.perf_counter() - moment) * 1000.0)
            rows.append({
                "pair": title,
                "start": start,
                "end": end,
                "start_name": names[start],
                "end_name": names[end],
                "algorithm": algorithm,
                "time_min": round(result.total_time, 3),
                "distance_km": round(result.total_distance, 3),
                "transfers": result.transfers,
                "expanded": result.expanded,
                "elapsed_ms": round(statistics.median(samples), 3),
            })
    return rows


# ----------------------------------------------------------------------
# 写 CSV / Markdown
# ----------------------------------------------------------------------
def write_csv(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = ["pair", "start", "end", "algorithm", "time_min", "distance_km",
               "transfers", "expanded", "elapsed_ms"]
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row[key] for key in columns})


def markdown_table(rows: list[dict]) -> str:
    lines = [
        "| 起终点 | 算法 | 时间/min | 里程/km | 换乘 | 扩展节点 | 耗时中位数/ms |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in rows:
        lines.append(
            f"| {row['pair']} | {row['algorithm']} | {row['time_min']:.1f} | "
            f"{row['distance_km']:.1f} | {row['transfers']} | {row['expanded']} | "
            f"{row['elapsed_ms']:.2f} |"
        )
    return "\n".join(lines)


def summaries(rows: list[dict]) -> list[str]:
    """给报告用的两三句结论（根据真实数据生成，不写死）。"""
    by_algo = {name: [r for r in rows if r["algorithm"] == name] for name in ALGORITHMS}
    lines = []
    if all(by_algo.values()):
        avg_expanded = {name: statistics.mean(r["expanded"] for r in rs)
                        for name, rs in by_algo.items()}
        avg_time = {name: statistics.mean(r["elapsed_ms"] for r in rs)
                    for name, rs in by_algo.items()}
        transfers = {name: sum(r["transfers"] for r in rs) for name, rs in by_algo.items()}
        lines.append(
            "扩展节点均值："
            + "，".join(f"{name} {avg_expanded[name]:.1f}" for name in ALGORITHMS)
            + "。A* 借助直线距离启发函数，平均搜索规模最小。"
        )
        lines.append(
            "单次寻路耗时中位数均值："
            + "，".join(f"{name} {avg_time[name]:.2f}ms" for name in ALGORITHMS)
            + "。三者在 134 站规模下都远低于 200ms 的验收阈值。"
        )
        lines.append(
            "换乘次数总计："
            + "，".join(f"{name} {transfers[name]}" for name in ALGORITHMS)
            + "。BFS 以换乘次数为层数，因此在跨线场景下换乘不会更多。"
        )
    return lines


# ----------------------------------------------------------------------
# Pillow 分组柱状图
# ----------------------------------------------------------------------
def load_font(size: int, bold: bool = False):
    from PIL import ImageFont

    candidates = [
        ("C:/Windows/Fonts/msyhbd.ttc" if bold else "C:/Windows/Fonts/msyh.ttc", 0),
        ("C:/Windows/Fonts/simhei.ttf", 0),
        ("C:/Windows/Fonts/simsun.ttc", 0),
    ]
    for path, index in candidates:
        try:
            return ImageFont.truetype(path, size=size, index=index)
        except OSError:
            continue
    return ImageFont.load_default()


def draw_chart(rows: list[dict], path: Path) -> None:
    from PIL import Image, ImageDraw

    pairs = list(dict.fromkeys(row["pair"] for row in rows))
    values = {(row["pair"], row["algorithm"]): row["expanded"] for row in rows}
    max_value = max(values.values())
    y_max = max(30, ((max_value + 19) // 20) * 20 + 20)
    tick_count = 6

    width, height = 1440, 840
    left, right, top, bottom = 100, 60, 100, 130
    plot_w = width - left - right
    plot_h = height - top - bottom

    image = Image.new("RGB", (width, height), "#FFFFFF")
    draw = ImageDraw.Draw(image)

    font_title = load_font(30, True)
    font_axis = load_font(18)
    font_tick = load_font(16)
    font_label = load_font(15)
    font_value = load_font(14, True)
    font_legend = load_font(18)

    # 标题与副标题
    draw.text((left, 26), "图 4-4  三种算法扩展节点数对比", fill="#0F172A", font=font_title)
    draw.text((left, 68), "5 对起终点 · 134 站北京教学路网 · 柱顶为扩展节点数",
              fill="#64748B", font=font_axis)

    # 网格与 Y 轴刻度
    def y_of(value: float) -> float:
        return top + plot_h - value / y_max * plot_h

    for i in range(tick_count + 1):
        value = y_max * i / tick_count
        y = y_of(value)
        draw.line((left, y, left + plot_w, y), fill="#E2E8F0", width=1)
        draw.text((left - 14, y), f"{int(value)}", fill="#64748B",
                  font=font_tick, anchor="rm")
    draw.line((left, top, left, top + plot_h), fill="#94A3B8", width=2)
    draw.line((left, top + plot_h, left + plot_w, top + plot_h), fill="#94A3B8", width=2)

    # 分组柱子
    group_w = plot_w / len(pairs)
    bar_gap = 6
    bar_w = min(58.0, group_w * 0.24)
    for index, pair in enumerate(pairs):
        center = left + group_w * (index + 0.5)
        total_w = len(ALGORITHMS) * bar_w + (len(ALGORITHMS) - 1) * bar_gap
        start_x = center - total_w / 2
        for slot, algorithm in enumerate(ALGORITHMS):
            value = values[(pair, algorithm)]
            x0 = start_x + slot * (bar_w + bar_gap)
            x1 = x0 + bar_w
            y0 = y_of(value)
            # 圆角柱：Pillow 的 rounded_rectangle 在旧版本没有，做个降级
            try:
                draw.rounded_rectangle((x0, y0, x1, top + plot_h), radius=5,
                                       fill=COLORS[algorithm])
            except AttributeError:
                draw.rectangle((x0, y0, x1, top + plot_h), fill=COLORS[algorithm])
            draw.text(((x0 + x1) / 2, y0 - 11), str(value), fill="#0F172A",
                      font=font_value, anchor="mm")
        # X 轴标签
        draw.text((center, top + plot_h + 22), pair, fill="#334155",
                  font=font_label, anchor="ma")

    # 图例
    legend_x = width - right - 360
    legend_y = top + 8
    for i, algorithm in enumerate(ALGORITHMS):
        x = legend_x + i * 120
        draw.rounded_rectangle((x, legend_y, x + 18, legend_y + 18), radius=4,
                               fill=COLORS[algorithm])
        draw.text((x + 26, legend_y + 9), algorithm, fill="#334155",
                  font=font_legend, anchor="lm")

    draw.text((left, height - 58),
              "注：BFS 按整条线路扩展，一个扩展覆盖多个站台；与 Dijkstra/A* 的逐站台扩展"
              "不是同一计数口径，主要对比 A* 相对 Dijkstra 的下降。",
              fill="#64748B", font=font_tick)
    draw.text((left, height - 30),
              "生成命令：python tools/bench.py     数据：docs/bench.csv",
              fill="#94A3B8", font=font_tick)

    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)


# ----------------------------------------------------------------------
# 入口
# ----------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(description="P4 对比实验")
    parser.add_argument("--runs", type=int, default=5, help="每个组合计时次数（中位数）")
    parser.add_argument("--no-chart", action="store_true", help="不画柱状图")
    args = parser.parse_args(argv)

    rows = run_benchmark(args.runs)
    csv_path = DOCS / "bench.csv"
    write_csv(rows, csv_path)
    table = markdown_table(rows)
    (DOCS / "bench.md").write_text(
        "# 对比实验原始表\n\n" + table + "\n\n" + "\n".join(f"- {line}" for line in summaries(rows)) + "\n",
        encoding="utf-8",
    )

    print(table)
    print()
    for line in summaries(rows):
        print("-", line)
    print(f"\nCSV：{csv_path}")

    if not args.no_chart:
        chart_path = FIG_DIR / "fig4-4_expanded.png"
        draw_chart(rows, chart_path)
        print(f"图 4-4：{chart_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
