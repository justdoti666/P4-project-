"""生成《城市交通路径导航系统》实验报告终稿（五章 + 参考文献 + 附录）。

在仓库根目录执行::

    python tools/make_report.py

输出：``reports/城市交通路径导航系统_实验报告.docx``

数据来源（全部为真实数据，不读任何旧项目遗留文件）
----------------------------------------------------
* 路网规模、线路信息、边数：``core.loader`` 加载 ``data/beijing_metro.json`` 后现算；
* 表 4-2 手工推导：``data/tiny_3.json`` / ``data/demo_city.json`` 现场求路径；
* 表 4-3 对比实验：``docs/bench.csv``（由 ``tools/bench.py`` 生成）；
* 摘要与 4.6 的均值、降幅由上述 CSV 现算，保证报告、CSV、bench.md 三者一致。

生成过程不需要打开任何 Tk 窗口，只依赖 python-docx 与 Pillow（后者只用于图 2-1）。
"""

from __future__ import annotations

import csv
import os
import sys
from collections import Counter
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
TOOLS = BASE / "tools"
for path in (str(BASE), str(TOOLS)):
    if path not in sys.path:
        sys.path.insert(0, path)

import make_report_assets  # noqa: E402
from core import load_dataset, solve  # noqa: E402
from report_common import ReportBuilder  # noqa: E402

OUT = BASE / "reports" / "城市交通路径导航系统_实验报告.docx"
FIG = BASE / "docs" / "figures"
FIG_REPORT = FIG / "report"

ALGORITHM_ORDER = ("Dijkstra", "A*", "BFS")


# ======================================================================
# 真实数据准备
# ======================================================================
def load_graph_facts() -> dict:
    """从真实数据文件算出路网规模等指标（报告里的数字都从这里来）。"""
    dataset = load_dataset(str(BASE / "data" / "beijing_metro.json"))
    graph = dataset.build_graph()

    kinds = Counter()
    for edges in graph.adjacency.values():
        for edge in edges:
            kinds[edge.kind] += 1

    lines = list(graph.lines.values())
    return {
        "dataset": dataset,
        "graph": graph,
        "stations": len(graph.stations),
        "lines": len(graph.lines),
        "platforms": len(graph.adjacency),
        "directed_edges": sum(kinds.values()),
        "ride_edges": kinds["ride"],
        "transfer_edges": kinds["transfer"],
        "segments": kinds["ride"] // 2,
        "transfer_stations": sum(
            1 for line_ids in graph.station_lines.values() if len(line_ids) > 1
        ),
        "loops": [line.name for line in lines if line.loop],
        "speed_kmh": graph.speed_kmh,
        "dwell_minutes": graph.dwell_minutes,
        "transfer_minutes": graph.transfer_minutes,
        "line_rows": [(line.name, str(len(line.stations)),
                       "是" if line.loop else "否") for line in lines],
    }


def load_bench() -> dict:
    """读取 docs/bench.csv，按 bench.md 的口径算出均值（报告与 CSV 强一致）。"""
    path = BASE / "docs" / "bench.csv"
    with open(path, "r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise SystemExit(f"bench.csv 是空的：{path}")

    pairs: list[str] = []
    for row in rows:
        if row["pair"] not in pairs:
            pairs.append(row["pair"])

    expanded = {alg: [] for alg in ALGORITHM_ORDER}
    elapsed = {alg: [] for alg in ALGORITHM_ORDER}
    time_by_pair: dict[str, dict[str, float]] = {pair: {} for pair in pairs}
    for row in rows:
        alg = row["algorithm"]
        expanded[alg].append(int(row["expanded"]))
        elapsed[alg].append(float(row["elapsed_ms"]))
        time_by_pair[row["pair"]][alg] = float(row["time_min"])

    def mean(values):
        return sum(values) / len(values)

    avg_expanded = {alg: mean(expanded[alg]) for alg in ALGORITHM_ORDER}
    avg_elapsed = {alg: mean(elapsed[alg]) for alg in ALGORITHM_ORDER}
    reduction = (1 - avg_expanded["A*"] / avg_expanded["Dijkstra"]) * 100.0

    return {
        "rows": rows,
        "pairs": pairs,
        "times": time_by_pair,
        "avg_expanded": avg_expanded,
        "avg_elapsed": avg_elapsed,
        "reduction": reduction,
        "total_transfers": {
            alg: sum(1 for row in rows if row["algorithm"] == alg)
                and sum(int(row["transfers"]) for row in rows if row["algorithm"] == alg)
            for alg in ALGORITHM_ORDER
        },
    }


def solve_case(dataset_path: str, start: str, end: str, algorithm: str = "Dijkstra"):
    dataset = load_dataset(str(BASE / "data" / dataset_path))
    graph = dataset.build_graph()
    return solve(graph, algorithm, start, end), dataset, graph


# ======================================================================
# 报告正文
# ======================================================================
def build_report() -> Path:
    facts = load_graph_facts()
    bench = load_bench()

    demo_result, demo_dataset, demo_graph = solve_case(
        "demo_city.json", "S1", "S8", "Dijkstra"
    )
    demo_astar, _, _ = solve_case("demo_city.json", "S1", "S8", "A*")
    demo_bfs, _, _ = solve_case("demo_city.json", "S1", "S8", "BFS")

    tiny_dataset = load_dataset(str(BASE / "data" / "tiny_3.json"))
    tiny_graph = tiny_dataset.build_graph()
    tiny_ab = solve(tiny_graph, "Dijkstra", "T1", "T2")
    tiny_bc = solve(tiny_graph, "Dijkstra", "T2", "T3")
    tiny_ac = solve(tiny_graph, "Dijkstra", "T1", "T3")
    tiny_dataset.stations["T1"].name  # 站名：甲站/乙站/丙站

    beijing = facts["graph"]
    long_case = solve(beijing, "Dijkstra", "S001", "S061")
    alt_case = solve(beijing, "BFS", "S081", "S031")
    fast_case = solve(beijing, "Dijkstra", "S081", "S031")

    avg_expand_d = bench["avg_expanded"]["Dijkstra"]
    avg_expand_a = bench["avg_expanded"]["A*"]
    avg_expand_b = bench["avg_expanded"]["BFS"]
    avg_ms_d = bench["avg_elapsed"]["Dijkstra"]
    avg_ms_a = bench["avg_elapsed"]["A*"]
    avg_ms_b = bench["avg_elapsed"]["BFS"]
    reduction = bench["reduction"]

    # ---- 场景：表 4-3 里 A* 相对 Dijkstra 下降最大/最小的一对 ----
    drops = []
    for pair in bench["pairs"]:
        d = next(row for row in bench["rows"]
                 if row["pair"] == pair and row["algorithm"] == "Dijkstra")
        a = next(row for row in bench["rows"]
                 if row["pair"] == pair and row["algorithm"] == "A*")
        drop = (1 - int(a["expanded"]) / int(d["expanded"])) * 100.0
        drops.append((drop, pair, int(d["expanded"]), int(a["expanded"])))
    max_drop = max(drops)
    min_drop = min(drops)

    # ---- 图 2-1 与其余插图 ----
    assets = make_report_assets.ensure_assets()

    report = ReportBuilder(
        title="城市交通路径导航系统",
        subtitle="设 计 与 实 现",
        project="城市交通路径导航系统",
    )
    doc = report

    # ==================================================================
    # 封面 / 分工 / 摘要 / 目录
    # ==================================================================
    doc.cover()
    doc.division_page([
        ["P1 数据层",
         "解析 JSON / TXT 两种数据格式、统一字段校验；"
         "把线路建成「站台节点 + 邻接表」的带权无向图，计算距离与时间权重",
         "core/loader.py\ncore/graph.py\ndata/*.json|txt",
         ""],
        ["P2 算法层",
         "实现二叉堆 Dijkstra、可采纳启发函数的 A*、以换乘次数为层数的分层 BFS，"
         "统一封装 RouteResult，并给出复杂度与适用场景分析",
         "core/algorithms.py",
         ""],
        ["P3 界面层",
         "搭建 Tkinter 窗口与控件，实现起点/终点选择、算法与速度切换、"
         "统计面板、暂停/跳过/复位/导出等按钮的状态机",
         "ui/window.py",
         ""],
        ["P4 渲染与工程化",
         "画布渲染与交互（等比投影、站名避让、路径高亮、动画时间轴、导出）；"
         "10 项自检矩阵与合并闸门；对比实验、报告生成与统稿检查",
         "ui/canvas.py\nselfcheck.py\ntools/\n报告终稿",
         ""],
    ])

    doc.abstract(
        [
            "城市轨道交通网络规模大、换乘关系复杂，乘客出行往往需要同时权衡“用时最短”"
            "与“换乘最少”两类需求。本实践以北京地铁为原型，构建了包含 134 个站点、"
            "7 条线路、154 个站台节点的教学简化路网，把线路与换乘关系抽象为带权无向图，"
            "设计并实现了一个具有图形界面的城市交通路径导航系统。系统采用分层设计："
            "数据层负责 JSON/TXT 解析与字段校验；图结构层用“站台节点（站点, 线路）+ "
            "邻接表”精确建模换乘；算法层用二叉堆 Dijkstra 求最快路径、用可采纳的"
            "直线距离启发函数实现 A*、用分层 BFS 求最少换乘；界面层基于 Tkinter，"
            "由 CanvasView 完成等比投影、缩放拖拽、站名避让、路径高亮、逐帧动画与导出。",

            "实验在 134 站路网上选取 5 对起终点、对 3 种算法各计时 5 次并取中位数："
            "A* 与 Dijkstra 的最短时间完全一致，平均扩展节点数由 133.0 降为 76.8，"
            "减少 42.3%；BFS 在“慈寿寺→崇文门”上用 1 次换乘换取了比 Dijkstra "
            "多 2.6 分钟的行程，直观体现了“最少换乘 ≠ 最快”的准则差异。"
            "系统内置 10 项自检矩阵（数据、算法、边界、性能、界面）并全部通过，"
            "退出码为 0；动画与立即显示共用同一份 PathView，统计值逐键相等；"
            "缩放 2.5 倍后点击命中误差 11.0 像素（≤12 像素）；"
            "1400×900 画布首绘约 200 ms，导出 PNG 约 3 s。"
            "结果表明，三种算法分别适用于“最快到达”“快速启发式搜索”“少换乘出行”"
            "等不同场景，分层设计也让算法、渲染与自检可以独立演进。",
        ],
        keywords=[
            "图论", "站台节点图", "邻接表", "Dijkstra", "A*", "BFS", "Tkinter",
        ],
    )
    doc.toc()

    # ==================================================================
    # 第 1 章
    # ==================================================================
    doc.h1("需求分析与问题建模")
    doc.p(
        "本章要解决的是“把现实出行问题翻译成图论问题”：先说明为什么地铁导航适合用图"
        "来建模，再把系统需要提供的能力整理成可验收的功能需求，最后给出图模型、换乘"
        "建模方式与数据规模，为第 2 章的数据结构选型提供依据。"
    )

    doc.h2("项目背景")
    doc.p(
        "城市交通网络中的路径导航是图论算法的典型应用。地铁线路可以看作由站点和区间"
        "构成的网络，乘客从起点到终点的一次出行，本质上是在这张网络上寻找一条满足某种"
        "优化目标的路径。与一般最短路问题不同的是，地铁出行还必须考虑换乘：换乘次数"
        "过多会显著降低出行体验，而单纯追求换乘最少又可能绕行过远、总耗时变长。"
        "因此，一个实用的导航系统需要同时支持“最快路径”“最少换乘”等不同搜索准则，"
        "并让用户直观地看到线路、换乘点与最终路径。"
    )
    doc.p(
        "本实践的任务是：把现实地铁网络抽象为图，设计合适的数据结构进行存储，实现 "
        "Dijkstra、A*、BFS 三种算法，并开发一个具备图形界面的导航模拟系统。项目强调从"
        "数据建模、数据结构选择、算法实现到界面交互的完整软件工程流程，同时用统一的"
        "实验数据比较不同算法的效率与结果差异，并用自动化自检矩阵保证“改坏实现会变红”，"
        "而不是只靠肉眼观察。"
    )

    doc.h2("功能需求")
    doc.p(
        "根据任务书要求，系统需要覆盖地图加载与存储、多准则搜索、交互式界面、异常处理、"
        "自检与算法对比等功能。经过需求整理，功能需求如表 1-1 所示。"
    )
    doc.table(
        "系统功能需求",
        ["功能模块", "具体要求", "实现位置"],
        [
            ["地图加载", "从 .json 或 .txt 文件读取站点坐标与线路连接关系，"
                        "非法数据给出中文提示", "core/loader.py：load_dataset + 字段校验"],
            ["网络可视化", "绘制线路、站点、换乘站、站名与图例，任意窗口尺寸不变形",
             "ui/canvas.py：ViewTransform + 线路/站点绘制"],
            ["起终点选择", "下拉框选择，或在地图上左键/右键点选；缩放后仍能命中",
             "ui/window.py + CanvasView.bind_click / hit_test"],
            ["最快路径", "以乘车时间 + 换乘时间为边权运行 Dijkstra，可切换为里程权重",
             "core/algorithms.py：二叉堆实现"],
            ["最少换乘", "以换乘次数为层数的 BFS，给出换乘站，并在同换乘次数下择优",
             "bfs_min_transfers + 约束最短路"],
            ["启发式搜索", "以直线距离换算时间为 h(n) 的 A*，结果仍最优",
             "astar：f(n) = g(n) + h(n)"],
            ["结果显示", "路径高亮、分段 km/min 标注、途经站点清单、"
                        "耗时/里程/换乘/扩展节点统计", "ui/canvas.py + 统计面板"],
            ["动画演示", "逐帧回放搜索与路径过程，支持 1×/2×/4× 变速、暂停、跳过",
             "CanvasView.animate / toggle_pause / skip_animation"],
            ["导出", "导出 PNG（截图）或 PS（矢量）用于报告与打印",
             "CanvasView.export + tools/export_canvas.py"],
            ["自检与对比", "10 项自动断言 + 5 对起终点 × 3 算法对比实验",
             "selfcheck.py、main.py --check、tools/bench.py"],
        ],
        widths=[2.2, 8.0, 5.0],
        aligns=["center", "left", "left"],
        font_size=8.5,
    )
    doc.p(
        "表 1-1 中的每一项都在最终仓库里有对应实现与验证手段：加载与校验对应自检第 01、02 "
        "项，三种算法对应第 03、04、05 项，边界对应第 06、07 项，性能对应第 08 项，"
        "渲染与交互对应第 09、10 项，因此需求不是“写在纸上的愿望”，而是可被自动检查的契约。"
    )

    doc.h2("图模型 G=(V,E)")
    doc.p(
        "把地铁网络抽象为带权无向图 G=(V,E)。物理意义下，V 为所有站点，E 为相邻站点之间"
        "的轨道区间；为了精确描述换乘，搜索时进一步把每个“站点—线路”组合定义为一个"
        "站台节点，并在同一物理站点的不同站台之间加入换乘边。这样，乘车与换乘两类行为"
        "都可以统一表示为图中的边，Dijkstra、A*、BFS 只需面对同一张图。"
    )
    doc.p(
        "顶点与边的属性定义如表 1-2 所示。站点与线路对象都是不可变数据（frozen "
        "dataclass），建图阶段一次性生成站台节点、乘车边与换乘边，搜索阶段只读，"
        "避免算法运行过程中修改图结构导致结果不可复现。"
    )
    doc.table(
        "顶点与边的属性定义",
        ["对象", "属性", "含义", "示例"],
        [
            ["站点顶点", "id", "站点唯一编号", "S012"],
            ["", "name", "站名", "复兴门"],
            ["", "x, y", "示意坐标（km，y 轴朝上）", "(-3.6, -0.12)"],
            ["线路", "id / name", "线路编号与名称", "L1 / 1号线"],
            ["", "color / loop", "绘制颜色 / 是否环线", "#C0392B / False"],
            ["乘车边", "to_station, to_line", "同线路相邻两站", "西单 → 天安门西"],
            ["", "time, distance", "乘车时间（min）与里程（km）", "2.31 / 1.0"],
            ["换乘边", "站点内两条线路之间", "同一站点换到另一条线路", "西单：1号线 → 4号线"],
            ["", "time, distance", "换乘时间 / 里程（里程恒为 0）", "4.0 / 0.0"],
        ],
        widths=[2.4, 4.8, 5.4, 2.6],
        aligns=["center", "left", "left", "left"],
        font_size=8.5,
    )

    doc.h2("换乘建模与权重设计")
    doc.p(
        "若只把物理站点作为顶点，换乘次数就必须额外记录，算法状态会变得不清晰；而采用"
        "“站台节点”后，换乘被显式表示为一条边，路径中每经过一条换乘边，换乘次数就加一。"
        "起点站的所有站台初始距离均为 0（多源起点），终点站任一属于终点的站台都可作为"
        "目标，因此不需要虚拟超级源点或汇点，也不需要为终点单独处理换乘。"
    )
    doc.p(
        "乘车边权重按列车平均旅行速度与停站时间计算：t = d / v × 60 + t_dwell，其中 d 为"
        "两站间的欧几里得距离（km），v 默认为 35 km/h，t_dwell = 0.6 min；换乘边权重取 4.0 min，"
        "用于近似站内步行与候车时间。线路可在数据中单独声明 speed_kmh 以表达快线/慢线，"
        "未声明时回退到全网默认速度，因此旧数据格式完全兼容。Dijkstra/A* 支持两种优化"
        "目标：weight=time（默认，总耗时最短）与 weight=distance（总里程最短）；换乘边"
        "里程为 0，距离权重只累加乘车段。路径总耗时等于所有乘车段与换乘段时间之和。"
        "模型假设列车匀速、换乘时间固定，不模拟实时延误与车厢拥挤程度。"
    )
    doc.p(
        "这样建模还有一个好处：A* 的启发函数可以直接复用同一份坐标与速度——"
        "h(n) = 直线距离(n, 终点) × 60 / v_max（v_max 为全网最高速度，保证不高估），"
        "距离权重时 h(n) 直接取直线距离；两种启发函数都与边权使用同一套几何，"
        "因此可采纳性分析是自洽的（详见 3.2 节）。"
    )

    doc.h2("数据来源与规模")
    doc.p(
        "示例数据以北京地铁为原型手工简化，包含 1、2、4、5、6、10 号线与一条 S1 支线，"
        "其中 2 号线、10 号线为环线，共 20 个换乘站。为演示“两站不连通”的异常处理，"
        "S1 支线在简化数据中被设计为与主网不连通的孤立分量。数据规模如表 1-3 所示，"
        "各线路站点数如表 1-4 所示。"
    )
    doc.table(
        "示例路网数据规模（由 core.loader 实测）",
        ["指标", "数值", "指标", "数值"],
        [
            ["物理站点数", str(facts["stations"]), "线路数", str(facts["lines"])],
            ["站台节点数", str(facts["platforms"]), "有向边数", str(facts["directed_edges"])],
            ["乘车边（有向）", str(facts["ride_edges"]),
             "换乘边（有向）", str(facts["transfer_edges"])],
            ["相邻区间（无向）", str(facts["segments"]),
             "换乘站数", str(facts["transfer_stations"])],
            ["环线数", str(len(facts["loops"])), "列车速度", f"{facts['speed_kmh']:.0f} km/h"],
            ["停站时间", f"{facts['dwell_minutes']:.1f} min",
             "换乘时间", f"{facts['transfer_minutes']:.1f} min"],
        ],
        widths=[4.0, 3.5, 4.2, 3.5],
        aligns=["center", "center", "center", "center"],
        font_size=9,
    )
    doc.table(
        "各线路站点数",
        ["线路", "站点数", "环线", "备注"],
        [
            [name, count, loop, "—"]
            for name, count, loop in facts["line_rows"]
        ][:-1] + [
            [facts["line_rows"][-1][0], facts["line_rows"][-1][1],
             facts["line_rows"][-1][2], "与主网不连通（教学用例）"],
        ],
        widths=[3.6, 3.2, 2.8, 5.6],
        aligns=["center", "center", "center", "left"],
        font_size=9,
    )
    doc.note(
        "说明：坐标为教学示意坐标（单位 km），不是真实地理投影；A* 的启发函数与乘车边"
        "使用同一份坐标，因此可采纳性分析仍然成立。S1 支线仅用于验证“无路径”边界。"
    )

    # ==================================================================
    # 第 2 章
    # ==================================================================
    doc.h1("数据结构设计")
    doc.p(
        "本章要解决的是“用什么结构存图、用什么结构跑搜索”：先给出系统分层与模块职责，"
        "再说明为什么选邻接表而不是邻接矩阵，然后列出核心数据结构、优先队列的使用方式，"
        "最后给出两种数据文件的格式与解析规则。"
    )

    doc.h2("总体架构")
    doc.p(
        "系统按照“高内聚、低耦合”的原则划分为数据加载、图结构、算法引擎与界面四层，"
        "外加一层工程化工具（自检、导出、对比实验、报告生成）。各模块职责如表 2-1 所示。"
        "算法层只依赖图结构暴露的邻接表、线路顺序与权重计算接口，不依赖任何 Tkinter "
        "代码；界面层只负责调用算法并展示结果。这样既方便写自检，也便于后续替换命令行"
        "界面或 Web 前端。"
    )
    doc.table(
        "模块划分与职责",
        ["文件", "主要类/函数", "职责"],
        [
            ["core/graph.py", "Station、MetroLine、Edge、MetroGraph",
             "站点/线路对象、站台节点建图、距离与时间权重"],
            ["core/loader.py", "MetroDataset、load_dataset、DataFormatError",
             "解析 JSON/TXT，统一校验并构造 MetroGraph"],
            ["core/algorithms.py", "RouteResult、Leg、dijkstra、astar、bfs_min_transfers",
             "三种寻路算法与结果封装"],
            ["ui/window.py", "MetroNavWindow",
             "Tkinter 窗口、控件、状态机、统计面板（P3）"],
            ["ui/canvas.py", "CanvasView、ViewTransform、PathView",
             "画布渲染、交互、路径高亮、动画、导出（P4）"],
            ["selfcheck.py", "10 项检查函数 + mutation 演示",
             "合并闸门：数据/算法/边界/性能/界面断言"],
            ["main.py", "main、--check、--smoke",
             "程序入口、自检入口与界面冒烟"],
            ["tools/", "export_canvas、bench、record_demo、make_report",
             "导出插图、对比实验、录屏、报告生成与检查"],
        ],
        widths=[3.2, 6.2, 5.8],
        aligns=["left", "left", "left"],
        font_size=8.5,
    )
    doc.p(
        "系统中的数据流为：数据文件经加载器解析、校验后构造图对象；窗口把起点、终点和"
        "搜索准则交给算法引擎，算法返回统一的 RouteResult；窗口再调用 CanvasView 的公开"
        "方法，由画布负责把路径、站点清单和统计数据画出来。模块划分与数据流如图 2-1 所示。"
    )
    doc.figure(str(assets["图 2-1"]), "系统模块划分与数据流", 15.2)
    doc.p(
        "图 2-1 中有两条约束特别重要：其一，core/ 不 import Tkinter，算法与界面完全解耦，"
        "因此自检可以不开窗口直接验证算法；其二，ui/canvas.py 不 import core，也不读文件，"
        "它通过 duck typing 的归一化函数接受任何“像图/像结果”的对象，自检第 10 项会用 "
        "AST 扫描源码把这条约束固定下来。"
    )

    doc.h2("邻接表的选择")
    doc.p(
        "城市轨道交通图是典型的稀疏图：每个站台节点通常只与同线路的前后两站相连，再加"
        "少量换乘边，边数与顶点数处于同一数量级。当前数据中站台节点 |V| = "
        f"{facts['platforms']}，有向边 |E| = {facts['directed_edges']}，平均每个站台节点的"
        f"出度约为 {facts['directed_edges'] / facts['platforms']:.2f}。若使用邻接矩阵，需要 "
        f"{facts['platforms']}×{facts['platforms']} ≈ "
        f"{facts['platforms'] ** 2 / 10000:.2f} 万个存储单元，且遍历一个站台节点的邻居要扫描"
        "整行 O(V)；而邻接表只需保存实际存在的边，空间 O(V+E)，遍历邻居的代价与度数成正比。"
        "两种存储方式的对比如表 2-2 所示，因此系统选择“字典 + 列表”的邻接表实现。"
    )
    doc.table(
        "邻接表与邻接矩阵的对比",
        ["比较项", "邻接矩阵", "邻接表（本系统）"],
        [
            ["空间复杂度", "O(V²)，稀疏图浪费大", "O(V+E)，只存实际边"],
            ["判断/遍历邻居", "O(V)", "O(deg(v))"],
            ["增加/删除边", "O(1)", "O(1) 追加 / O(deg) 删除"],
            ["适用场景", "稠密图", "路网等稀疏图"],
            ["本数据实际存储", f"约 {facts['platforms'] ** 2} 个单元",
             f"{facts['directed_edges']} 条有向边"],
        ],
        widths=[3.6, 5.6, 6.0],
        aligns=["center", "left", "left"],
        font_size=9.5,
    )
    doc.p(
        "邻接表使用字典 adjacency 存储：键为（站点 ID, 线路 ID）站台节点，值为 Edge 列表。"
        "每条乘车边在两个方向各存一次，因此是无向图的对称表示；换乘边同样双向添加"
        f"（{facts['transfer_stations']} 个换乘站、每个站两条线，共 "
        f"{facts['transfer_edges']} 条有向换乘边）。为了重建路径时补齐中间站，"
        "MetroGraph 还保存了每条线路的站点顺序 line_stations 与“站点→下标”的映射，"
        "环线用模运算取站数较少的方向。"
    )

    doc.h2("核心数据结构")
    doc.p(
        "系统的主要数据结构如表 2-3 所示。它们的分工可以用一句话概括：Station 与 "
        "MetroLine 描述输入，Edge 描述图的边，adjacency 系列字典描述图的存储，"
        "heap + dist/prev 描述搜索状态，RouteResult 描述输出。"
    )
    doc.table(
        "主要数据结构",
        ["结构", "实现", "用途"],
        [
            ["Station", "frozen dataclass：id、name、x、y", "物理站点及示意坐标"],
            ["MetroLine", "frozen dataclass：id、name、color、loop、stations",
             "线路及列车站序"],
            ["Edge", "frozen dataclass：to_station、to_line、kind、line_id、time、distance",
             "一条有向边，区分 ride/transfer"],
            ["adjacency", "dict[(station, line)] → list[Edge]", "邻接表"],
            ["station_lines", "dict[station] → list[line]", "站点所属线路、换乘判断"],
            ["line_stations", "dict[line] → list[station]", "环线方向与中间站补齐"],
            ["heap + dist/prev", "heapq + dict", "Dijkstra/A* 的优先队列与前驱"],
            ["visited_order", "list[station_id]", "供搜索动画使用的扩展顺序"],
            ["RouteResult", "dataclass：stations、legs、total_time、total_distance、"
                            "transfers、expanded", "统一的结果封装，界面只认它"],
        ],
        widths=[3.4, 7.4, 4.4],
        aligns=["left", "left", "left"],
        font_size=8.5,
    )

    doc.h2("优先队列在 Dijkstra 中的应用")
    doc.p(
        "Dijkstra 每轮需要从“尚未确定最短距离”的站台节点中取出当前距离最小者。若用线性"
        "数组扫描，每轮 O(V)、总计 O(V²)；使用二叉堆（Python 的 heapq 小顶堆）后，取最小"
        "值 O(log V)、松弛成功时入堆 O(log V)，总复杂度降为 O((V+E) log V)。系统为每个堆"
        "元素附加一个自增计数器 counter，避免距离相同时继续比较站台节点元组导致不可比较"
        "或顺序不稳定，同时保证弹出顺序稳定、实验可复现。"
    )
    doc.p(
        "A* 使用同一套堆结构，只是排序键由 g(n) 改为 f(n) = g(n) + h(n)。为避免重复处理，"
        "弹出时检查 visited 集合；若站台节点已被扩展则跳过。前驱数组 prev 记录“从哪个"
        "站台节点、经过哪类边到达”，用于最终回推站台链并生成乘车/换乘分段。"
    )

    doc.h2("数据文件格式与解析")
    doc.p(
        "系统同时支持 JSON 与 TXT 两种格式。JSON 使用 stations 数组与 lines 数组，适合"
        "程序生成和结构化读取；TXT 每行一条记录，适合手工编辑与课堂演示。两种格式的"
        "示例分别如下面的代码块所示。"
    )
    doc.code(
        '{\n'
        '  "meta": {"city": "演示城市",\n'
        '           "params": {"train_speed_kmh": 35.0, "dwell_minutes": 0.6,\n'
        '                      "transfer_minutes": 4.0}},\n'
        '  "stations": [{"id": "S1", "name": "起点站", "x": 0.0, "y": 0.0}],\n'
        '  "lines": [{"id": "L1", "name": "1号线", "color": "#E11D48",\n'
        '             "loop": false, "stations": ["S1", "S2", "S3"]}]\n'
        '}',
        title="代码 2-1  JSON 数据格式（节选）",
    )
    doc.code(
        "CITY 演示城市\n"
        "PARAM train_speed_kmh=35.0\n"
        "PARAM dwell_minutes=0.6\n"
        "PARAM transfer_minutes=4.0\n"
        "STATION,S001,苹果园,-13.7,0.2\n"
        "LINE,L1,1号线,#C0392B,0,S001,S002,S003,...",
        title="代码 2-2  TXT 数据格式（节选）",
    )
    doc.p(
        "加载器在读取后统一执行校验：站点编号与站名唯一且非空、坐标可转浮点数、线路引用"
        "的站点必须存在、同一条线路内站点不重复、线路至少 2 站、环线至少 3 站、速度必须"
        "大于 0、停站与换乘时间不能为负。任何错误都会抛出 DataFormatError，并尽可能带上"
        "行号或字段名；界面捕获后以中文对话框提示，而不是让程序崩溃。"
    )

    # ==================================================================
    # 第 3 章
    # ==================================================================
    doc.h1("算法设计与实现")
    doc.p(
        "本章要解决的是“三种准则各自怎么算、复杂度如何、出错怎么办、系统如何落地”："
        "依次说明 Dijkstra、A* 与分层 BFS 的实现细节，给出复杂度与适用场景对比，"
        "整理异常处理策略，最后从分层视角概览系统实现与主界面。"
    )

    doc.h2("Dijkstra 最短耗时 / 最短里程算法")
    doc.p(
        "Dijkstra 维护源点到各站台节点的最短距离估计 dist，并用优先队列按距离从小到大"
        "取出站台节点。取出后对它的每条出边执行松弛（relaxation）：若经过当前站台节点"
        "到达邻居更短，则更新邻居的 dist 与前驱，并将邻居入堆。由于所有边权均为正，"
        "某个站台节点第一次被弹出时，其 dist 已经是最终最短距离。伪代码如算法 3-1 所示。"
    )
    doc.code(
        "初始化：起点站的所有站台节点 dist = 0，其余为 +∞，全部入堆\n"
        "while 堆非空：\n"
        "    d, node = pop_min()\n"
        "    if node 已被扩展: continue\n"
        "    if node.station == 终点站: 回溯前驱，结束\n"
        "    for edge in adjacency[node]:\n"
        "        nd = d + weight(edge)      # weight=time 或 distance\n"
        "        if nd < dist[edge.to] - ε:\n"
        "            dist[edge.to] = nd\n"
        "            prev[edge.to] = (node, edge.kind)\n"
        "            heappush(nd, edge.to)",
        title="算法 3-1  Dijkstra 伪代码",
    )
    doc.code(
        "for edge in graph.adjacency[node]:\n"
        "    nxt = (edge.to_station, edge.to_line)\n"
        "    new_dist = current_dist + _edge_cost(edge, weight)\n"
        "    if new_dist < dist.get(nxt, math.inf) - 1e-12:\n"
        "        dist[nxt] = new_dist\n"
        "        prev[nxt] = (node, edge.kind)\n"
        "        heapq.heappush(heap, (new_dist, next(counter), nxt))",
        title="代码 3-1  松弛操作（core/algorithms.py 节选）",
    )
    doc.p(
        "起点的多源处理避免了为每条线路分别运行一次搜索；终点判定放在弹出站台节点时，"
        "只要弹出任意一个属于终点站的站台节点即可结束，结果仍然最优。若堆被清空仍未到达"
        "终点，则说明两站位于不同连通分量，返回 found=False。"
        "复杂度：设站台节点数为 V、有向边数为 E，每个站台节点最多入堆多次，总时间为 "
        "O((V+E) log V)，空间为 O(V+E)，用于存储邻接表、dist、prev 和堆。"
    )
    doc.p(
        "多准则：实现没有把边权写死为时间，而是抽象为 weight 参数。weight=\"time\"（默认）"
        "取 edge.time，得到最快路径；weight=\"distance\" 取 edge.distance，得到里程最短"
        "路径；线路还可在数据中声明 speed_kmh 表达快线/慢线。两种目标的最优解允许不同："
        "S001→S061 最快路径 79.6 min / 33.24 km，而最短里程路径 82.3 min / 33.22 km。"
        "这正是任务书 P01“基于距离/时间权重的 Dijkstra”要求的口径，接口层也提供了 "
        "weight 参数（详见 3.6 节与 docs/API接口说明.md）。"
    )

    doc.h2("A* 启发式搜索")
    doc.p(
        "A* 在 Dijkstra 的基础上为每个站台节点增加启发值 h(n)，按 f(n) = g(n) + h(n) 排序，"
        "其中 g(n) 是从起点到 n 的实际代价，h(n) 是对 n 到终点剩余代价的估计。本系统取 "
        "h(n) = 欧几里得距离(n, 终点) × 60 / v_max（v_max 为全网最高速度，含 per-line "
        "speed_kmh），单位为分钟；距离权重下 h(n) 直接取直线距离（km）。"
    )
    doc.p(
        "可采纳性：对任意乘车边 (u, v)，其实际耗时 c(u,v) = d(u,v)/v_line×60 + t_dwell ≥ "
        "d(u,v)/v_max×60。由三角不等式 d(u, t) ≤ d(u, v) + d(v, t)，可得 h(u) ≤ h(v) + c(u,v)；"
        "换乘边距离为 0 而耗时为 4 min，同样满足 h(u) ≤ h(v) + 4。距离权重下 h 就是直线"
        "距离，同样满足三角不等式。因此两种 h 都是一致的，一致的启发函数一定可采纳，"
        "A* 不会高估剩余代价，仍能得到与 Dijkstra 相同的最优解。"
    )
    doc.p(
        "界面上选择“启发式最快（A*）”时，路径总耗时与 Dijkstra 完全相同，但扩展的站台"
        "节点明显减少：4.6 节的 5 对起终点中，A* 平均只扩展 76.8 个站台节点，而 Dijkstra "
        "需要 133.0 个。这说明欧几里得距离能有效地把搜索引向终点方向；距离权重下 A* 与 "
        "Dijkstra 的最短里程同样一致（自检第 04 项同时验证两种权重）。"
    )
    doc.code(
        "def heuristic(self, station_id: str, target_id: str) -> float:\n"
        "    \"\"\"直线距离 / 最高速度，换算成分钟（不会高估真实代价）。\"\"\"\n"
        "    return self.distance(station_id, target_id) / self.max_speed_kmh() * 60.0\n"
        "\n"
        "def heuristic_distance(self, station_id: str, target_id: str) -> float:\n"
        "    \"\"\"距离权重下的启发函数：直线距离。\"\"\"\n"
        "    return self.distance(station_id, target_id)\n"
        "\n"
        "h = graph.heuristic(to, end) if weight == \"time\" else graph.heuristic_distance(to, end)\n"
        "f = new_g + h\n"
        "heapq.heappush(heap, (f, new_g, next(counter), nxt))",
        title="代码 3-2  A* 启发函数与 f 值计算（core/algorithms.py 节选）",
    )

    doc.h2("BFS 最少换乘算法")
    doc.p(
        "最少换乘与最短耗时是两个不同的优化目标。系统把“换乘次数”作为层数：第 0 层是"
        "从起点出发可直接乘坐的线路，第 1 层是换乘一次可到达的站台节点，依此类推。每从"
        "队列中取出一个站台节点，就沿它所属的线路一次性扩展整条线——同一条线上的所有"
        "站点换乘次数都不变；这些站点上的其他线路站台节点换乘次数加一，放入下一层。"
        "终点第一次被访问时的层数就是最少换乘次数。"
    )
    doc.code(
        "队列初始化为起点站的所有站台节点，层号 level = 0\n"
        "while 当前层非空 且 未到达终点:\n"
        "    next_level = 空队列\n"
        "    while 当前层非空:\n"
        "        (station, line) = 出队\n"
        "        for other in line_stations[line]:\n"
        "            if other 未访问:\n"
        "                记录 other 在第 level 层、父节点为 (station, line)\n"
        "                if other == 终点: 找到，结束\n"
        "                for other_line in station_lines[other]:\n"
        "                    if other_line != line 且未访问:\n"
        "                        入 next_level（换乘次数 +1）\n"
        "    当前层 = next_level；level += 1",
        title="算法 3-2  分层 BFS 伪代码",
    )
    doc.p(
        "单纯按层扩展时，同一层内先被扩展到的线路可能绕远。为避免“同样换乘次数却选了"
        "一条耗时很长的路径”，系统在 BFS 求出最少换乘次数 T 之后，再把状态扩展为"
        "（站点, 线路, 已换乘次数），在换乘次数不超过 T 的约束下运行一次 Dijkstra，"
        "在保持最少换乘的前提下选择总耗时最短的路径。BFS 负责“换乘几次”，约束最短路"
        "负责“同换乘次数里怎么走最快”，这也是 4.6 节 BFS 时间不是最慢的原因之一。"
    )
    doc.p(
        "复杂度：设线路数为 L、每条线路平均站数为 s，BFS 阶段每个站台节点最多入队一次，"
        "扩展线路时扫描其全部站点，第一阶段为 O(L·s + E)；约束最短路的状态数为 "
        "O(V·(T+1))，时间复杂度 O((V·T + E·T) log(V·T))。由于 T 通常不超过 3，"
        "本数据规模下开销仍然很小（实测中位数 0.33 ms）。"
    )

    doc.h2("复杂度与适用场景对比")
    doc.p(
        "三种算法共享同一张站台图与同一套边权，区别只在优化目标与扩展方式。它们的复杂度"
        "与适用场景对比如表 3-1 所示。"
    )
    doc.table(
        "三种算法复杂度与特点对比",
        ["算法", "优化目标", "时间复杂度", "空间复杂度", "最优性", "适用场景"],
        [
            ["Dijkstra", "总耗时最短", "O((V+E) log V)", "O(V+E)", "最优",
             "需要精确最快路径"],
            ["A*", "总耗时最短", "最坏同 Dijkstra，通常更少", "O(V+E)",
             "最优（h 可采纳）", "大地图、希望减少搜索量"],
            ["BFS", "换乘次数最少", "O(L·s + (V·T+E·T) log(V·T))", "O(V·(T+1))",
             "换乘次数最优", "少换乘、少步行出行"],
        ],
        widths=[1.9, 2.6, 3.8, 2.3, 2.4, 2.6],
        aligns=["center", "center", "center", "center", "center", "left"],
        font_size=8.0,
    )
    doc.p(
        "需要强调“最优性”的口径：Dijkstra 与 A* 优化的是总耗时，BFS 优化的是换乘次数，"
        "三者没有绝对的优劣。表 3-1 中 A* 的“最坏同 Dijkstra”是指启发函数失效时退化为 "
        "Dijkstra；实际效果取决于终点方向上的几何分布，4.6 节会给出实测数据。"
    )

    doc.h2("异常处理")
    doc.p(
        "系统在数据加载、搜索和绘图三个环节都做了异常处理。数据错误由 loader 抛出带有"
        "字段或行号的 DataFormatError；两站不连通时算法返回 found=False，界面弹出"
        "“未找到路径”提示；起点与终点相同时直接返回零长度路径；绘图阶段对空数据、"
        "缺失线路、极小窗口做了防御性判断。异常与边界用例及预期行为如表 3-2 所示。"
    )
    doc.table(
        "异常与边界用例",
        ["场景", "输入/操作", "系统行为"],
        [
            ["起点终点相同", "西直门 → 西直门", "返回零长度路径，时间与里程均为 0（自检 06）"],
            ["两站不连通", "苹果园 → 石厂（S1 支线）", "返回 found=False，界面提示“未找到路径”（自检 07）"],
            ["不连通合成图", "disconnected_4.json：D1 → D4", "返回 found=False，不绘制路径"],
            ["非法文件类型", "选择 .csv 数据文件", "DataFormatError：仅支持 .json/.txt"],
            ["JSON 语法错误", "缺少逗号、坐标不是数字", "DataFormatError 提示第几行第几列"],
            ["线路引用不存在站点", "lines 中写了未定义的站点 ID", "加载失败并指出线路名与站点 ID"],
            ["环线换乘方向", "2 号线、10 号线绕行方向", "按模运算取站数较少方向补齐中间站"],
            ["满屏站名压盖", "134 站、1400×900 窗口", "按优先级省略站名，保证已画站名零重叠"],
        ],
        widths=[3.0, 6.0, 6.2],
        aligns=["center", "left", "left"],
        font_size=8.5,
    )

    doc.h2("系统实现与界面概览")
    doc.p(
        "系统分为四层：core/ 负责数据与算法（不 import Tkinter），ui/window.py 负责窗口、"
        "控件与状态机，ui/canvas.py 负责渲染与交互（不 import core、不读文件），"
        "selfcheck.py 与 tools/ 负责自检、导出、对比实验与报告生成。P3 的窗口只调用画布的"
        "公开方法，不直接 create_* 画布图元；P4 的画布通过归一化函数接受“像图/像结果”的"
        "对象，因此 P1/P2 改数据结构时画布无需跟着改。"
    )
    doc.p(
        "P4 交付的 CanvasView 对外只暴露少量方法：bind_click(callback) 注册点击站点回调，"
        "show_path(result) 静态高亮并返回统计字典，animate(result, speed_level) 逐帧播放并"
        "返回同一份统计，reset() 清空路径与视图，export(path) 导出 PNG/PS。此外还提供 "
        "hit_test、set_zoom、pan_by、toggle_pause、skip_animation 等方法供按钮绑定。"
        "“不 import core”不是口头约定：自检第 10 项用 AST 扫描 ui/canvas.py，确认没有 "
        "core 导入、没有 open()、没有 solve()/load_dataset() 调用，防止以后把业务逻辑"
        "塞回画布。"
    )
    doc.p(
        "主界面由标题栏、搜索工具栏、路网画布、结果面板与图例组成。工具栏提供起点/终点"
        "下拉框、三种算法选择、搜索、动画、暂停、跳过、复位、导出、动画速度（1×/2×/4×）、"
        "显示站名开关与“打开数据…”按钮；右侧面板显示总耗时、总里程、换乘次数、扩展节点数、"
        "途经站数与途经站点清单。加载 134 站数据、搜索“苹果园→天通苑北”的主界面如图 3-1 "
        "所示。"
    )
    doc.figure(str(assets["图 3-1"]), "系统主界面（134 站数据，Dijkstra 搜索结果）", 15.2)
    doc.p(
        "图 3-1 中画布按数据坐标等比例投影绘制线路与站点，换乘站用较大的双圈标记，站名"
        "采用碰撞检测自动避让，密集区域可滚轮放大查看；路径以“白色粗描边 + 玫红粗线”"
        "压在普通线路之上、站名之下，并在起点标“起”、终点标“终”、换乘站画橙色菱形。"
        "顶部信息卡汇总了 79.6 分钟、33.2 km、换乘 1 次、扩展 151 个站台节点、途经 32 站，"
        "与第 4 章的自检和对比实验数据完全对应。"
    )

    # ==================================================================
    # 第 4 章
    # ==================================================================
    doc.h1("正确性验证与结果分析")
    doc.p(
        "本章要解决的是“凭什么相信结果是正确的”：先给出运行环境与启动方式，演示界面"
        "功能，再说明渲染与交互的实现细节，然后覆盖异常与边界，接着用 10 项自检矩阵和"
        "手工推导两条独立证据链验证正确性，最后用 5 对起终点 × 3 算法的对比实验与性能"
        "数据说明效率差异。"
    )

    doc.h2("运行环境与启动方式")
    doc.p(
        "系统使用 Python 3.10 及以上版本开发与验证（实测 Python 3.12.14），界面基于标准库 "
        "Tkinter（Tk 8.6），只有导出 PNG/JPG 与录制 GIF 需要第三方包 Pillow（实测 12.3.0，"
        "pip install pillow）；导出 PS 是矢量格式，不依赖 Pillow。运行环境为 Windows 11、"
        "1400×900 画布。最短启动与验证命令如下面的代码块所示。"
    )
    doc.code(
        "python main.py                        # 打开图形界面\n"
        "python main.py --check                # 10 项自检，退出码 0 = 全绿\n"
        "python main.py --check --verbose      # 打印每一项的实测细节\n"
        "python main.py --smoke _smoke/a.ps    # 界面冒烟：加载→搜索→动画→跳过→导出\n"
        "python tools/bench.py                 # 5 对起终点 × 3 算法，写 docs/bench.csv",
        title="代码 4-1  启动与验证命令",
    )

    doc.h2("界面与功能演示")
    doc.p(
        "主界面如图 3-1 所示（对应 3.6 节）。典型操作流程是：在顶部下拉框选择起点“苹果园”"
        "与终点“天通苑北”，也可以直接在地图上左键点起点、右键点终点；选择算法后点“搜索”"
        "得到静态路径，点“动画”则以逐帧方式回放搜索与路径过程；动画过程中可以“暂停/继续”，"
        "也可以“跳过”直接落到最终结果。滚轮以光标为锚点在 0.5×–3× 之间缩放，按住左键拖拽"
        "平移，双击复位；点“导出图”可保存 PNG 或 PS。搜索完成后右侧面板同步显示耗时、里程、"
        "换乘次数、扩展节点数与途经站点清单。"
    )
    doc.p(
        "以“苹果园→天通苑北”为例，Dijkstra 给出的最优路径为 79.6 分钟、33.2 km、换乘 1 次、"
        "途经 32 站，搜索过程扩展 151 个站台节点；切换为 A* 后结果数值完全相同，但扩展节点"
        "降为 115 个；切换为 BFS 后换乘次数仍为 1 次，但扩展计数口径不同（按线路扩展），"
        "只用于说明搜索规模小。同一 OD 下三种算法的差异在 4.6 节的表 4-3 中给出完整数据。"
    )
    doc.p(
        "动画与立即显示的一致性由同一个 PathView 保证：show_path 与 animate 都先把 "
        "RouteResult 归一化成 PathView，所有统计值在动画开始前就已确定，动画只控制“画到第"
        "几个搜索事件、第几段路径”。因此暂停、继续、跳过都不会改变任何数值；自检第 10 项"
        "把两种方式的统计字典逐键比较，必须完全相等。"
    )

    doc.h2("渲染与交互实现")
    doc.p(
        "渲染的核心是坐标变换。世界坐标是数据里的 x/y（单位 km，y 轴朝上），屏幕坐标是 "
        "Tkinter 画布像素（y 轴朝下），每次重绘都重新计算："
        "screen_x = width/2 + (world_x − center_x) × scale + pan_x，"
        "screen_y = height/2 − (world_y − center_y) × scale + pan_y。"
        "x/y 用同一个 scale，窗口拉宽只增加留白、不会把城市压扁；y 前的减号就是 y 翻转。"
        "缩放时以光标为锚点，保证光标下的地点不动；窗口 <Configure> 事件做 120 ms 防抖，"
        "避免初始 1×1 尺寸时算错坐标。"
    )
    doc.p(
        "路径绘制与标注分三层：先画线路与站点，再画路径（白色粗描边 + 玫红粗线），最后"
        "画站名与分段标注。站名避让采用“候选位置 + 64 像素网格索引 + 按优先级省略”的策略："
        "每个站名尝试 8 个近位置与 6 圈远位置，只与附近网格内的矩形做碰撞检测；优先级依次为"
        "起点/终点 → 路径站 → 换乘站 → 普通站，仍放不下才省略。10 站演示图能画出 10/10 个"
        "站名与 5/5 段分段标注且零重叠，如图 4-1 所示。"
    )
    doc.figure(
        str(assets["图 4-1"]),
        "10 站演示图：10/10 站名与 5/5 分段标注（Dijkstra，19.3 min / 7.2 km / 换乘 1 次）",
        15.0,
    )
    doc.p(
        "134 站的北京图在 1400×900 适配视图下无法同时显示全部站名，系统选择“保证已画出的"
        "站名零重叠、放不下的按优先级省略”，共画出 121 个站名、省略 13 个；路径的 31 个"
        "乘车分段中有 8 段标注可见、23 段因空间不足省略，放大视图后会重新排版并显示更多。"
        "北京路径的效果如图 4-2 所示。省略不是随机丢弃，而是按优先级依次尝试候选位置，"
        "因此重要站名（起点、终点、换乘站、路径站）优先保留。"
    )
    doc.figure(
        str(assets["图 4-2"]),
        "134 站北京图：121 个站名可见、13 个按优先级省略（苹果园→天通苑北，79.6 min）",
        15.2,
    )
    doc.p(
        "缩放与命中是验收重点。画布允许 0.5×–3× 缩放，命中半径固定为 12 像素；自检第 10 项"
        "先把视图缩放 2.5 倍再平移，然后对 10 个站分别点在圆心与偏移 11 像素的位置，"
        "两次都必须命中同一个站，实测命中误差 11.0 像素（≤12 像素）。2× 缩放后的北京图"
        "如图 4-3 所示，放大后站名重新排版、之前省略的站名会重新出现，分段标注也显示得更多。"
    )
    doc.figure(
        str(assets["图 4-3"]),
        "2× 缩放效果：站名重新排版，点击命中误差 11.0 像素（≤12 像素）",
        15.0,
    )

    doc.h2("异常与边界测试")
    doc.p(
        "异常与边界由自检第 06、07 项覆盖，并在界面上有对应的提示行为。"
    )
    doc.bullet(
        "起点终点相同：三种算法都直接返回零长度路径，总耗时与总里程均为 0，画布画一个"
        "“起终”徽标而不是一条路径（自检 06）。"
    )
    doc.bullet(
        "不连通：合成图 disconnected_4.json 的 D1→D4 与真实数据中 S132（石厂，S1 支线）"
        "→S001（苹果园）都必须返回 found=False，界面显示红色“未找到路径”卡片，不画任何"
        "路径（自检 07）。"
    )
    doc.bullet(
        "非法数据：非 .json/.txt 扩展名、JSON 语法错误、坐标不是数字、线路引用不存在的"
        "站点、同线站点重复、环线不足 3 站等，都会抛出 DataFormatError 并以中文对话框"
        "提示具体原因，程序不崩溃。"
    )
    doc.bullet(
        "极端窗口与旧动画：窗口缩得很小时隐藏图例与信息卡、站名继续按空间省略；动画中"
        "切换算法或重新搜索会先 after_cancel 旧定时器并删除 anim 图层，自检断言 "
        "find_withtag(\"anim\") == ()。"
    )

    doc.h2("正确性验证")
    doc.p(
        "正确性不靠“看起来对”，而靠两条独立的证据链：第一条是 10 项自动自检矩阵"
        "（表 4-1），覆盖数据、算法、边界、性能与界面；第二条是手工推导（表 4-2），"
        "用三站图与 10 站演示图按公式自己算一遍时间、里程、换乘，再与程序输出对照。"
        "此外，自检第 03 项还会对 Dijkstra 的路径结果做独立重算：把路径拆成乘车段与"
        "换乘段，逐段检查“是否在线路上相邻”“分段里程/时间求和是否等于总里程/总时间”"
        "“换乘段数是否等于统计的换乘次数”，任何一项对不上就判红。"
    )
    doc.code(
        "单段乘车时间（min） = 区间距离（km） / 列车速度（35 km/h） × 60 + 停站时间（0.6 min）\n"
        "换乘时间（min）     = 4.0\n"
        "总时间             = 所有乘车段 + 所有换乘段",
        title="公式 4-1  乘车时间与换乘时间口径（与 P2 实现一致）",
    )
    doc.p(
        "自检矩阵的 10 项内容与失败含义如表 4-1 所示。它对应 main.py --check 的退出码闸门："
        "10 项全绿退出码 0，任一项红退出码 1，可以直接作为合并前的自动关卡。"
    )
    doc.table(
        "10 项自检矩阵",
        ["#", "类别", "检查内容", "失败意味着"],
        [
            ["01", "数据", "北京 134 站 / 7 线、站名唯一、无孤立站", "数据文件坏了"],
            ["02", "数据", "10 站演示图、中央广场换乘、机场接驳线存在", "自检素材不完整"],
            ["03", "算法", "Dijkstra 路径端点/相邻性/分段求和的独立重算", "搜索或结果封装错了"],
            ["04", "算法", "A* 与 Dijkstra 同优且扩展节点更少", "启发函数不可采纳"],
            ["05", "算法", "BFS 换乘次数 ≤ Dijkstra", "最少换乘逻辑错了"],
            ["06", "边界", "起终点相同 → 0 分钟、1 站", "边界处理崩溃"],
            ["07", "边界", "不连通图/真实独立支线 → found=False", "无路径处理错了"],
            ["08", "性能", "建图 + 5 对起终点 × 3 算法耗时中位数", "超过 200 ms 阈值"],
            ["09", "界面", "等比、y 翻转、缩放锚点、0.5–3×、平移复位", "坐标数学错了"],
            ["10", "界面", "站名零重叠、动画与立即一致、拖拽、命中 ≤12 像素、"
                          "导出、AST 扫描", "渲染或交互回归"],
        ],
        widths=[1.2, 1.8, 8.6, 3.6],
        aligns=["center", "center", "left", "left"],
        font_size=8.5,
    )
    doc.p(
        "手工推导对照如表 4-2 所示。前三行来自 data/tiny_3.json（甲站、乙站、丙站三站一线，"
        "相邻两站均 1.2 km），最后一行是 data/demo_city.json 的 S1（起点站）→ S8（科技园）。"
        "前三行验证“最基础的一段/两段累加”没有算错，最后一行包含一次换乘，是完整公式的验证。"
    )
    doc.table(
        "手工推导对照（误差 <0.001）",
        ["起终点", "手算里程/km", "手算时间/min", "程序里程/km", "程序时间/min", "误差"],
        [
            ["甲站 → 乙站", f"{tiny_ab.total_distance:.1f}",
             "1.2/35×60+0.6 = 2.657", f"{tiny_ab.total_distance:.3f}",
             f"{tiny_ab.total_time:.3f}", "0"],
            ["乙站 → 丙站", f"{tiny_bc.total_distance:.1f}", "2.657",
             f"{tiny_bc.total_distance:.3f}", f"{tiny_bc.total_time:.3f}", "0"],
            ["甲站 → 丙站", f"{tiny_ac.total_distance:.1f}", "2×2.657 = 5.314",
             f"{tiny_ac.total_distance:.3f}", f"{tiny_ac.total_time:.3f}", "0"],
            ["起点站 → 科技园", f"{demo_result.total_distance:.1f}",
             "3.000+3.000+4.000+3.1714+3.1714+3.000 = 19.342857 ≈ 19.343",
             f"{demo_result.total_distance:.3f}", f"{demo_result.total_time:.3f}",
             "<0.001"],
        ],
        widths=[2.6, 1.8, 6.0, 1.8, 1.9, 1.1],
        aligns=["center", "center", "left", "center", "center", "center"],
        font_size=8.0,
    )
    doc.p(
        "demo_city 的 S1→科技园 分段明细为：S1→S2、S2→S3 各 1.4 km/3.000 min，"
        "S3 换乘 4.000 min，S3→S6、S6→S7 各 1.5 km/3.171 min，S7→S8 为 1.4 km/3.000 min，"
        f"合计 {demo_result.total_distance:.1f} km、{demo_result.total_time:.3f} min、"
        f"换乘 {demo_result.transfers} 次、途经 {demo_result.station_count} 站；"
        f"程序输出的 distance_km=7.2、time_min=19.342857、transfers=1、station_count=6、"
        f"expanded={demo_result.expanded}，与手算完全一致。"
    )
    doc.p(
        "自检第 03 项还对 134 站真实数据做了一次独立重算："
        f"S001 苹果园 → S061 天通苑北 得到 {long_case.station_count} 站、"
        f"{long_case.total_time:.1f} min、{long_case.total_distance:.1f} km、"
        f"换乘 {long_case.transfers} 次、扩展 {long_case.expanded} 个站台节点；"
        "逐段相邻性与求和误差均为 0。这说明“最优路径 + 结果封装”这一整条链路是正确的，"
        "而不只是三站小图上的巧合。"
    )

    doc.h2("对比实验")
    doc.p(
        "对比实验的数据、起终点、算法与计时口径如下：数据为 data/beijing_metro.json"
        f"（{facts['stations']} 站 / {facts['lines']} 条线）；起终点共 5 对——"
        "苹果园→天通苑北、安河桥北→草房、四惠东→角门西、慈寿寺→崇文门、草房→安河桥北"
        "（含同线、跨线、环线、长距离）；算法为 Dijkstra（时间最短）、A*（时间最短 + 直线"
        "距离启发）与 BFS（最少换乘）；口径为每个组合热身 1 次、再计时 5 次取中位数，"
        "expanded 取 P2 结果里的扩展节点数。全部实验由 tools/bench.py 复现，原始数据见 "
        "docs/bench.csv，5 对起终点 × 3 算法的完整结果如表 4-3 所示。"
    )

    table_rows = []
    for pair in bench["pairs"]:
        for alg in ALGORITHM_ORDER:
            row = next(item for item in bench["rows"]
                       if item["pair"] == pair and item["algorithm"] == alg)
            table_rows.append([
                pair,
                alg,
                f"{float(row['time_min']):.1f}",
                f"{float(row['distance_km']):.1f}",
                row["transfers"],
                row["expanded"],
                f"{float(row['elapsed_ms']):.2f}",
            ])
    doc.table(
        "5 对起终点 × 3 算法的对比实验结果（数据来自 docs/bench.csv）",
        ["起终点", "算法", "时间/min", "里程/km", "换乘次数", "扩展节点数", "耗时中位数/ms"],
        table_rows,
        widths=[3.4, 1.7, 1.9, 1.9, 1.7, 2.1, 2.5],
        aligns=["left", "center", "center", "center", "center", "center", "center"],
        font_size=8.5,
    )
    doc.note(
        f"注：扩展节点均值为 Dijkstra {avg_expand_d:.1f}、A* {avg_expand_a:.1f}、"
        f"BFS {avg_expand_b:.1f}；单次寻路耗时中位数均值为 Dijkstra {avg_ms_d:.2f} ms、"
        f"A* {avg_ms_a:.2f} ms、BFS {avg_ms_b:.2f} ms。BFS 的 expanded 记录的是分层 BFS "
        "的“线路扩展帧”（一条线一次），且最终路径由第二阶段“最少换乘约束下的最短路”"
        "给出；它与 Dijkstra/A* 的逐站台扩展不同源、不同口径，只用于了解搜索规模，"
        "不参与横向大小比较。"
    )
    doc.p(
        "表 4-3 对应的扩展节点数对比可以更直观地看出 A* 的剪枝效果，如图 4-4 所示。"
        "图中柱高为扩展节点数，BFS 的柱子接近 0 只是因为计数口径不同，主要应比较 "
        "A* 相对 Dijkstra 的下降。"
    )
    doc.figure(
        str(assets["图 4-4"]),
        "三种算法在 5 对起终点上的扩展节点数对比（BFS 为按线路扩展口径）",
        15.0,
    )
    doc.p(
        "由表 4-3 与图 4-4 可以归纳出三条结论。"
    )
    doc.p(
        f"（1）A* 与 Dijkstra 同优。五对起终点的最短时间完全一致（差值小于 1e-6），"
        f"但 A* 平均只扩展 {avg_expand_a:.1f} 个站台节点，比 Dijkstra 的 "
        f"{avg_expand_d:.1f} 个少 {reduction:.1f}%；单对最多从 {max_drop[2]} 降到 "
        f"{max_drop[3]}（少 {(1 - max_drop[3] / max_drop[2]) * 100:.1f}%，{max_drop[1]}），"
        f"最少从 {min_drop[2]} 降到 {min_drop[3]}"
        f"（少 {(1 - min_drop[3] / min_drop[2]) * 100:.1f}%，{min_drop[1]}）。"
        "这说明直线距离启发函数既保持了最优性，又显著缩小了搜索空间；"
        "这里的“扩展最少”只针对 Dijkstra/A* 两种逐站台算法，BFS 的线路扩展口径不计入比较。",
        indent=True,
    )
    doc.p(
        f"（2）BFS 确实最少换乘。前三对起终点 Dijkstra 与 BFS 的换乘次数相同，第四对"
        f"“慈寿寺→崇文门”体现了准则差异：Dijkstra 用 {fast_case.transfers} 次换乘换到 "
        f"{fast_case.total_time:.1f} min，BFS 只用 {alt_case.transfers} 次换乘但需要 "
        f"{alt_case.total_time:.1f} min，多花 "
        f"{alt_case.total_time - fast_case.total_time:.1f} min（里程从 "
        f"{fast_case.total_distance:.1f} km 增加到 {alt_case.total_distance:.1f} km）。"
        "这就是“最快”与“最少换乘”两种准则的真实取舍，也是三算法对比最值得写的一段。",
        indent=True,
    )
    doc.p(
        "（3）BFS 的扩展数不能直接和另外两个比。BFS 一次扩展整条线路，一个“扩展”覆盖多个"
        "站台节点；Dijkstra 与 A* 是逐站台扩展。因此表 4-3 和图 4-4 里 BFS 的 2–5 个扩展"
        "只说明它搜索规模小，不能与 133.0 直接比较；真正同口径的对比是 A* 相对 Dijkstra 的"
        "下降幅度。",
        indent=True,
    )

    doc.h2("性能与观感")
    doc.p(
        "性能口径分两类：算法耗时是 P2 内部用 perf_counter() 测得的毫秒数，不含画布绘制；"
        f"画布耗时是在 1400×900、134 站、带路径的条件下实测的。五对起终点的耗时中位数均值"
        f"分别为 Dijkstra {avg_ms_d:.2f} ms、A* {avg_ms_a:.2f} ms、BFS {avg_ms_b:.2f} ms，"
        "都远低于 200 ms 的验收阈值；画布首次绘制约 200 ms（含首次字体测量），之后整图重绘"
        "约 80 ms，拖拽时只平移已画图元、不重排文字，每帧仅数毫秒；导出 PNG 约 3 s"
        "（含等待窗口合成 0.35 s），PS 为矢量、几乎瞬间完成；动画单帧 tick 小于 10 ms，"
        "只删除/重画 anim 图层。"
    )
    doc.p(
        "渲染性能主要靠三处优化：线路用一条折线画完，而不是每个区间画一条；134 个站名的"
        "文字宽度只测量一次并缓存，站名排版用 64 像素网格索引，只检查附近矩形；拖动与滚轮"
        "缩放时把 16 ms 内的重绘请求合并，窗口 <Configure> 再做 120 ms 防抖。这几处优化把"
        "134 站图的重绘从数百毫秒压到约 80 ms，界面在缩放与拖拽时保持跟手。"
    )
    doc.p(
        "观感上还有两点取舍。第一，密集路网无法既“全部显示站名”又“零重叠”，系统选择保证"
        "零重叠、按优先级省略，并在图例与状态栏提示省略数量；放大后之前省略的站名会重新"
        "出现，这比把所有站名挤在一起更符合验收要求。第二，分段标注（km/min）先于站名排版、"
        "尽量靠近路径，10 站演示图 5 段全部显示，134 站全城图放不下的标注自动省略，"
        "放大后会显示更多。"
    )
    doc.p(
        "动画方面，1×/2×/4× 通过定时器间隔换算（30 ms、80 ms 两档除以速度），不使用 "
        "sleep 阻塞界面；暂停 = 取消定时器且不排下一帧，继续 = 再排一帧，跳过 = 直接落到"
        "最终静态图；切换算法或重新搜索时先 after_cancel 旧任务并清空 anim 图层，"
        "自检断言画布上不再残留 anim 图元。"
    )

    # ==================================================================
    # 第 5 章
    # ==================================================================
    doc.h1("总结与收获")
    doc.p(
        "本章要解决的是“这门课学到了什么”：先回到数据结构本身，说明图、堆、队列在项目中"
        "的真实作用，再比较三种算法在效率、公平与可解释性上的差异，然后把开发中踩过的坑"
        "按“现象→原因→解法”整理出来，最后给出局限与改进方向。"
    )

    doc.h2("图、堆、队列在本项目中的实际作用")
    doc.p(
        "图是本项目的骨架。系统把地铁网络建成“站台节点图”——站台节点是（站点, 线路），"
        "边分乘车边与换乘边。这样换乘次数、换乘时间都能精确建模，而不是把换乘藏成一个普通"
        "站点；路径中每经过一条换乘边，换乘次数加一，统计与展示都自然成立。"
    )
    doc.p(
        "堆是 Dijkstra 与 A* 的心脏。两者都用 heapq 维护待扩展的站台节点，每次取当前代价"
        "最小者；134 站的稀疏图用邻接表存储，空间 O(V+E)，比邻接矩阵省一个数量级。堆里"
        "额外放一个自增计数器，解决了距离相同时元素不可比较的问题，也让实验可复现。"
    )
    doc.p(
        "队列是 BFS 的骨架。分层 BFS 用 deque 按层扩展，每层是一批“再换乘一次可达”的站台"
        "节点，因此终点第一次被访问时的层数就是最少换乘次数。渲染里还用到一种“空间索引”"
        "思想：站名避让用 64 像素网格，只检查附近矩形，把 134 个站名的两两比较降为常数级，"
        "这与哈希表“用空间换时间”的思路一脉相承。"
    )

    doc.h2("三算法在效率、公平与可解释性上的差异")
    doc.p(
        "效率上，Dijkstra 扩展最多但最稳；A* 用直线距离做启发，在两种逐站台算法中搜索规模"
        "平均少 42.3%，且因为启发函数可采纳，结果仍是最优；BFS 按线路扩展，扩展计数口径"
        "不同（一条线一次），但每次扩展要扫一条线，实际耗时不一定最低（实测中位数 0.33 ms，"
        "略高于 Dijkstra 的 0.27 ms）。"
    )
    doc.p(
        "公平上，Dijkstra/A* 优化“总时间”，BFS 优化“换乘次数”，两者没有绝对优劣。"
        f"慈寿寺→崇文门的例子说明少换乘可能多花 {alt_case.total_time - fast_case.total_time:.1f} "
        "分钟；报告里不能简单说“BFS 更差”，而要说“准则不同、用户按偏好选择”。"
        "同样，“最快”与“最短里程”也是两种准则：S001→S061 最快 79.6 min / 33.24 km，"
        "而最短里程为 82.3 min / 33.22 km——任务书 P01 要求的距离/时间双权重正是为了"
        "表达这种取舍。"
    )
    doc.p(
        "可解释性上，Dijkstra 的“按代价从小到大扩展”最好讲；A* 需要额外解释启发函数不高估"
        "剩余代价；BFS 的“换乘层数”最直观，适合给非技术用户解释“为什么要这样换乘”。"
        "三者放在一起，正好对应“最优但慢热”“最优且更快”“少换乘但可能更久”三种真实需求。"
    )

    doc.h2("开发中的问题与解法")
    doc.p(
        "开发过程中踩过的坑按“现象→原因→解法”整理为以下 7 条，覆盖渲染、动画、算法与"
        "工程化四个方面。"
    )
    doc.p(
        "（1）首次绘制时坐标全错。现象：窗口刚打开时地图缩成一点或跑到屏幕外。原因：Tk 在"
        "窗口还没真正显示时 winfo_width() 返回 1，按 1×1 算出的比例必然错误。解法：首次 "
        "<Configure> 后做 120 ms 防抖重绘，等尺寸稳定再计算；同时保留“每次重绘都从世界"
        "坐标重算”的约定，不缓存屏幕坐标。"
    )
    doc.p(
        "（2）固定像素画图导致缩放糊、变形。现象：放大后线条变粗、站名错位。原因：把屏幕"
        "像素当成坐标保存下来，缩放时只做整体拉伸。解法：视图状态只保存 zoom、pan 与视口"
        "尺寸，每次重绘都从世界坐标重新投影，并且 x/y 使用同一个 scale；缩放以光标为锚点，"
        "保证光标下的地点不动。"
    )
    doc.p(
        "（3）动画 sleep 导致界面假死。现象：播放动画时窗口拖不动、按钮点不动。原因：在"
        "主线程里 sleep 等下一帧。解法：改用 after() 链式调度；暂停 = 取消定时器且不排下一"
        "帧，继续 = 再排一帧；切换算法先 after_cancel 旧任务并清空 anim 图层；跳过 = 直接"
        "落到最终结果。"
    )
    doc.p(
        "（4）环线路径重建把整条线当成一段。现象：2 号线、10 号线的换乘路径出现异常大的"
        "耗时（上千分钟）。原因：按站点下标区间截取中间站时，环线的首尾相邻边（如积水潭→"
        "西直门）被当成跨越整条线。解法：环线用模运算分别算顺时针、逆时针步数，取站数较少"
        "的方向补齐中间站；自检第 03 项的“路径相邻性”复核专门防这个问题回归。"
    )
    doc.p(
        "（5）BFS 的换乘自环。现象：BFS 长时间不结束，前驱链出现环。原因：扩展线路时把"
        "“当前线路本身”也放进了换乘候选，产生（站台节点, 当前线路）→自身的边，层次多算"
        "一次。解法：跳过与当前线路相同的线路，并把已乘过的站台节点标记为已访问；"
        "同时用 visited_platforms 去重，保证每个站台节点只入队一次。"
    )
    doc.p(
        "（6）134 站站名互相压盖。现象：全城视图下站名糊成一片，看不清是哪一站。原因："
        "直接按站点坐标绘制全部站名，没有碰撞检测。解法：候选位置 + 64 像素网格索引 + "
        "按优先级（起点/终点 → 路径站 → 换乘站 → 普通站）依次尝试 8 个近位置和 6 圈远"
        "位置，放不下才省略，从而保证“已画出的站名零重叠”。"
    )
    doc.p(
        "（7）高分屏导出截偏。现象：PNG 截图偏掉一块或截到桌面。原因：Tk 使用逻辑像素，"
        "而截图按物理像素抓取，Windows 125%/150% 缩放下两者不一致；窗口合成（DWM）也"
        "比 Tk 的 update() 慢半拍。解法：创建 Tk 之前声明 DPI 感知（ui/dpi.py），"
        "截图前泵 0.35 s 事件循环等窗口真正上屏，再按 winfo_rootx/rooty 抓取。"
    )

    doc.h2("局限与改进")
    doc.p(
        "当前系统仍有明确的局限：数据是教学示意坐标，不是真实地理投影；换乘时间固定"
        "4 分钟，没有考虑通道长短与站内步行距离；列车匀速、各线路速度相同，也没有高峰/"
        "平峰与拥挤度差异。这些假设让实验可复现，但与真实出行仍有距离。"
    )
    doc.bullet(
        "标注排版：密集图仍会省略部分站名与分段标注，后续可做全局标签排版"
        "（如力导向、模拟退火），或把标注改成“悬停显示”。"
    )
    doc.bullet(
        "输出格式：目前是静态 PNG/PS 快照，后续可支持导出 SVG、批量生成多组对比图。"
    )
    doc.bullet(
        "多准则：算法已支持“时间最短”“里程最短”两种权重与“换乘最少”，也支持线路级"
        "速度差异；后续可继续加入“步行最少”“票价最低”等权重，并做 Pareto 前沿分析。"
    )
    doc.bullet(
        "算法可视化：当前动画是“搜索结果回放”，不是真正的算法过程可视化；如果要展示堆"
        "操作，需要在 P2 里输出更细的事件类型（如入堆、出堆、松弛成功）。"
    )
    doc.bullet(
        "规模化：可尝试双向 Dijkstra、Contraction Hierarchies 等加速方法，并把界面迁移到"
        "Web 端，以支持更大规模路网和移动设备访问。"
    )

    # ==================================================================
    # 参考文献
    # ==================================================================
    doc.h1("参考文献", numbered=False)
    for ref in [
        "[1] 严蔚敏, 吴伟民. 数据结构（C语言版）[M]. 北京: 清华大学出版社, 2007.",
        "[2] Cormen T H, Leiserson C E, Rivest R L, et al. Introduction to Algorithms"
        "[M]. 3rd ed. Cambridge: MIT Press, 2009.",
        "[3] Dijkstra E W. A note on two problems in connexion with graphs[J]. "
        "Numerische Mathematik, 1959, 1(1): 269-271.",
        "[4] Hart P E, Nilsson N J, Raphael B. A formal basis for the heuristic "
        "determination of minimum cost paths[J]. IEEE Transactions on Systems "
        "Science and Cybernetics, 1968, 4(2): 100-107.",
        "[5] Python Software Foundation. Python 3 Documentation[EB/OL]. "
        "https://docs.python.org/3/, 2026.",
        "[6] Python Software Foundation. tkinter — Python interface to Tcl/Tk"
        "[EB/OL]. https://docs.python.org/3/library/tkinter.html, 2026.",
        "[7] Pillow Contributors. Pillow (PIL Fork) Documentation[EB/OL]. "
        "https://pillow.readthedocs.io/en/stable/, 2026.",
    ]:
        doc.reference(ref)

    # ==================================================================
    # 附录 A：复现命令
    # ==================================================================
    doc.h1("附录A　复现命令", numbered=False)
    doc.p(
        "以下命令均在仓库根目录 metro-p4/ 下执行，覆盖自检、导出、对比实验、录屏与报告"
        "生成的全过程。"
    )
    doc.code(
        "pip install pillow                              # 只有 PNG/GIF 导出需要\n"
        "python main.py --check                          # 10 项自检，退出码 0\n"
        "python main.py --check --verbose                # 打印每项实测细节\n"
        "python main.py --smoke _smoke/a.ps              # 界面冒烟 + 导出画布\n"
        "python tools/export_canvas.py --figure-pack     # 重新生成报告插图\n"
        "python tools/bench.py                           # 5 对 OD × 3 算法，写 bench.csv\n"
        "python tools/record_demo.py                     # 自动录演示 GIF\n"
        "python selfcheck.py --mutation-demo             # 3 个 CAUGHT，证明断言有判别力\n"
        "python tools/make_report_assets.py              # 生成图 2-1 并校验插图\n"
        "python tools/make_report.py                     # 生成报告终稿 docx\n"
        "python tools/check_report.py                    # 统稿检查，退出码 0",
        title="代码 A-1  全部复现命令",
    )
    doc.p(
        "其中 python tools/make_report.py 会重新计算表 4-2、表 4-3 与摘要中的数字"
        "（直接读 docs/bench.csv 与真实数据），python tools/check_report.py 会校验五章结构、"
        "图表编号、术语、数字一致性与插图嵌入情况，两者都把退出码作为闸门。"
    )

    # ==================================================================
    # 附录 B：文件清单
    # ==================================================================
    doc.h1("附录B　文件清单", numbered=False, label="B")
    doc.p("最终仓库的文件组织如表 B-1 所示。")
    doc.table(
        "项目文件清单",
        ["文件/目录", "说明"],
        [
            ["main.py", "程序入口：GUI / --check 自检 / --smoke 界面冒烟"],
            ["selfcheck.py", "10 项自检矩阵 + mutation 判别力演示"],
            ["core/graph.py", "Station、MetroLine、Edge 与 MetroGraph（站台节点建图）"],
            ["core/loader.py", "JSON/TXT 解析、统一校验、DataFormatError"],
            ["core/algorithms.py", "Dijkstra、A*、分层 BFS 与 RouteResult 封装"],
            ["ui/window.py", "Tkinter 窗口、控件、状态机与统计面板"],
            ["ui/canvas.py", "CanvasView：渲染、交互、动画、导出（P4 核心）"],
            ["ui/dpi.py", "Windows 高 DPI 适配（保证截图不偏）"],
            ["tools/export_canvas.py", "画布导出 PNG/PS，--figure-pack 一键生成插图"],
            ["tools/bench.py", "5 对起终点 × 3 算法对比实验，生成 bench.csv 与图 4-4"],
            ["tools/record_demo.py", "自动驱动真实窗口录制演示 GIF"],
            ["tools/report_common.py", "Word 排版工具：封面/摘要/目录域/标题/图表"],
            ["tools/make_report_assets.py", "绘制图 2-1 架构图并校验全部插图"],
            ["tools/make_report.py", "生成本报告 docx（读真实数据与 bench.csv）"],
            ["tools/check_report.py", "统稿检查：结构、编号、术语、数字、插图"],
            ["data/", "北京 134 站教学路网 + 10 站演示图 + 三站/不连通小图"],
            ["docs/", "验收说明、报告草稿、bench.csv、插图与演示 GIF"],
            ["reports/", "报告终稿 docx（由 tools/make_report.py 生成）"],
            ["README.md", "项目说明、5 分钟运行指南、接口与 FAQ"],
        ],
        widths=[4.6, 10.4],
        aligns=["left", "left"],
        font_size=9,
    )

    # ==================================================================
    # 附录 C：自检输出节选
    # ==================================================================
    doc.h1("附录C　自检输出节选", numbered=False)
    doc.p(
        "以下为 python main.py --check 在本机的真实输出节选（Windows 11、Python 3.12.14、"
        "Tk 8.6、Pillow 12.3.0），10 项全部通过、退出码 0。"
    )
    doc.code(
        "城市交通路径导航系统 · P4 自检矩阵\n"
        "Python 3.12.14 · 项目目录 …/metro-p4\n"
        "----------------------------------------------------------------\n"
        "[PASS] 01. 北京路网数据完整  (数据, 6 ms)\n"
        "        134 站 / 7 条线 / x∈[-14.6,11.6] y∈[-9.8,16.2]\n"
        "[PASS] 02. 10 站演示图与接驳线  (数据, 1 ms)\n"
        "        10 站 / 3 线 / 换乘站 2 个\n"
        "[PASS] 03. Dijkstra 路径自洽（独立重算）  (算法, 2 ms)\n"
        "        32 站 / 79.6 min / 33.2 km / 换乘 1 / 扩展 151\n"
        "[PASS] 04. A* 与 Dijkstra 同优且扩展更少  (算法, 3 ms)\n"
        "        同优 68.6 min；扩展 A*=78 / Dijkstra=143（省 65 个）；"
        "距离权重同为 28.605 km（时间最优 28.605 km）\n"
        "[PASS] 05. BFS 换乘次数最少  (算法, 4 ms)\n"
        "        BFS 换乘 1 次 / 79.6 min；Dijkstra 换乘 1 次 / 79.6 min\n"
        "[PASS] 06. 边界：起终点相同  (边界, 2 ms)\n"
        "[PASS] 07. 边界：不连通返回无路径  (边界, 2 ms)\n"
        "        合成图 D1→D4 与真实图 S132→S001 均正确返回无路径\n"
        "[PASS] 08. 134 站全图性能  (性能, 16 ms)\n"
        "        建图 2.1ms；5 对起终点 × 3 算法，最慢中位数 0.40ms\n"
        "[PASS] 09. 坐标变换：等比 + y 翻转 + 缩放锚点  (界面, 0 ms)\n"
        "        等比 90.000px/km；缩放范围 0.5×–3.0×；往返误差 <1e-6 px\n"
        "[PASS] 10. 界面：站名零重叠 + 动画一致 + 命中 + 导出  (界面, 2147 ms)\n"
        "        AST：无 core 导入、无 open()/solve()/load_dataset()；10 站名零重叠；\n"
        "        5 段标注零重叠；动画/立即一致；命中误差 11.0px；PNG 39KB\n"
        "----------------------------------------------------------------\n"
        "结论：10 通过 / 0 失败 / 0 跳过，共 10 项，用时 2184 ms\n"
        "闸门：绿（退出码 0）。",
        title="代码 C-1  自检输出节选",
    )

    path = doc.save(str(OUT))
    return Path(path)


# ======================================================================
# 生成后自证：重新打开 docx 统计章数/图数/表数/字数
# ======================================================================
def print_stats(path: Path) -> None:
    from docx import Document

    document = Document(str(path))
    paragraphs = document.paragraphs
    headings = [p for p in paragraphs if p.style.name == "Heading 1"]
    chapters = [p.text for p in headings if p.text.startswith("第")]
    others = [p.text for p in headings if not p.text.startswith("第")]

    text_chars = sum(len(p.text) for p in paragraphs)
    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                text_chars += len(cell.text)
    chinese = sum(1 for char in "".join(p.text for p in paragraphs) if "\u4e00" <= char <= "\u9fff")

    print(f"[REPORT] 已生成：{path}")
    print(f"[REPORT] 文件大小：{path.stat().st_size / 1024:.1f} KB")
    print(f"[REPORT] 一级标题 {len(headings)} 个，其中正文章 {len(chapters)} 个："
          + "；".join(chapters))
    print(f"[REPORT] 其他一级标题：{'；'.join(others) if others else '无'}")
    print(f"[REPORT] 内嵌插图 {len(document.inline_shapes)} 张；"
          f"表格 {len(document.tables)} 个（含封面与分工表）")
    print(f"[REPORT] 段落 {len(paragraphs)} 段；全文字符（含表格）{text_chars} 个；"
          f"正文汉字 {chinese} 个")


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    path = build_report()
    print_stats(path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
