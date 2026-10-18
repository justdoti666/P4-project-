"""10 项自检矩阵（P4-07）：合并前的“闸门”。

怎么用
------
    python selfcheck.py                # 跑全部 10 项，退出码 0/1
    python selfcheck.py --verbose      # 失败时打印完整堆栈、成功也打印细节
    python selfcheck.py --no-gui       # 没有显示器时跳过第 10 项（界面）
    python selfcheck.py --mutation-demo  # 证明这些断言“改坏实现就会变红”

十项覆盖四类
------------
数据（1-2）    北京 134 站数据完整；10 站演示图可用于站名避让测试。
算法（3-5）    Dijkstra 路径自洽；A* 与 Dijkstra 同优；BFS 换乘不更多。
边界（6-7）    起终点相同；两个不连通分量；真实数据里的独立支线。
性能（8）      134 站全图三算法耗时中位数。
界面（9-10）   坐标变换数学；画布站名零重叠、动画一致、点击命中、导出。

“故意写坏实现能变红”
--------------------
``--mutation-demo`` 会启动 3 个子进程，分别把 y 翻转、Dijkstra 总耗时、
站名排版故意改坏，然后运行对应的检查，要求它们**必须失败**。
这是为了证明断言不是“恒真”的摆设。
"""

from __future__ import annotations

import argparse
import ast
import math
import os
import statistics
import subprocess
import sys
import time
import traceback
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DATA_DIR = PROJECT_ROOT / "data"
BEIJING = DATA_DIR / "beijing_metro.json"
DEMO = DATA_DIR / "demo_city.json"
DISCONNECTED = DATA_DIR / "disconnected_4.json"

from core import (  # noqa: E402  （先设置 sys.path，再导入项目模块）
    astar,
    bfs_min_transfers,
    dijkstra,
    load_dataset,
    solve,
)
from ui.canvas import CanvasView, ViewTransform  # noqa: E402


# ----------------------------------------------------------------------
# 检查注册与结果
# ----------------------------------------------------------------------
@dataclass
class CheckResult:
    number: int
    name: str
    category: str
    status: str          # "PASS" / "FAIL" / "SKIP"
    detail: str
    elapsed_ms: float


class CheckFailure(AssertionError):
    """检查不通过；message 会直接显示给用户。"""


class CheckSkipped(Exception):
    """当前环境跳过（例如无显示环境跳过 GUI 项）。"""


CHECKS: list[tuple[int, str, str, object]] = []


def check(number: int, name: str, category: str):
    """装饰器：把函数登记成第 number 项检查。"""

    def register(func):
        CHECKS.append((number, name, category, func))
        return func

    return register


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise CheckFailure(message)


def _load_graph(filename: Path):
    dataset = load_dataset(str(filename))
    return dataset, dataset.build_graph()


def _adjacent_on_line(graph, line_id: str, a: str, b: str) -> bool:
    """判断 a、b 是否在线路 line_id 上相邻（环线首尾也算）。"""
    line = graph.lines.get(line_id)
    if line is None:
        return False
    order = list(line.stations)
    if a not in order or b not in order:
        return False
    ia, ib = order.index(a), order.index(b)
    if line.loop and len(order) > 2:
        n = len(order)
        return (ia - ib) % n in (1, n - 1)
    return abs(ia - ib) == 1


def _validate_path(graph, result, label: str) -> str:
    """独立重算一条路径：端点、相邻性、分段求和、换乘计数。"""
    _assert(result.found, f"{label}：结果 found=False")
    _assert(bool(result.stations), f"{label}：路径为空")
    _assert(result.stations[0] == result.start_id, f"{label}：起点不符")
    _assert(result.stations[-1] == result.end_id, f"{label}：终点不符")

    total_time = 0.0
    total_distance = 0.0
    transfers = 0
    for leg in result.legs:
        if leg.kind == "transfer":
            _assert(leg.from_station == leg.to_station, f"{label}：换乘段跨站")
            transfers += 1
        else:
            _assert(
                _adjacent_on_line(graph, leg.line_id, leg.from_station, leg.to_station),
                f"{label}：乘车段 {leg.from_station}->{leg.to_station} 不在线路 "
                f"{leg.line_id} 上相邻",
            )
        total_time += leg.time
        total_distance += leg.distance

    _assert(abs(total_time - result.total_time) < 1e-6,
            f"{label}：总时间 {result.total_time} 与分段和 {total_time} 不一致")
    _assert(abs(total_distance - result.total_distance) < 1e-6,
            f"{label}：总里程与分段和不一致")
    _assert(transfers == result.transfers,
            f"{label}：换乘次数 {result.transfers} 与换乘段数 {transfers} 不一致")
    _assert(result.expanded > 0, f"{label}：扩展节点数应大于 0")
    return (f"{len(result.stations)} 站 / {result.total_time:.1f} min / "
            f"{result.total_distance:.1f} km / 换乘 {result.transfers} / "
            f"扩展 {result.expanded}")


# ----------------------------------------------------------------------
# 1-2 数据
# ----------------------------------------------------------------------
@check(1, "北京路网数据完整", "数据")
def check_data_beijing() -> str:
    dataset, graph = _load_graph(BEIJING)
    _assert(len(dataset.stations) >= 100,
            f"站点数只有 {len(dataset.stations)}，演示数据应 ≥100")
    _assert(len(dataset.lines) >= 5, "线路数太少")
    names = [station.name for station in dataset.stations.values()]
    _assert(len(names) == len(set(names)), "站名有重复（加载器应已拦截）")
    xs = [station.x for station in dataset.stations.values()]
    ys = [station.y for station in dataset.stations.values()]
    _assert(max(xs) - min(xs) > 10, "x 方向跨度太小，不像真实路网")
    _assert(max(ys) - min(ys) > 10, "y 方向跨度太小")
    _assert(all(graph.station_lines[sid] for sid in graph.stations),
            "存在不属于任何线路的孤立站点")
    return (f"{len(dataset.stations)} 站 / {len(dataset.lines)} 条线 / "
            f"x∈[{min(xs):.1f},{max(xs):.1f}] y∈[{min(ys):.1f},{max(ys):.1f}]")


@check(2, "10 站演示图与接驳线", "数据")
def check_demo_dataset() -> str:
    dataset, graph = _load_graph(DEMO)
    _assert(len(dataset.stations) == 10, "演示图应正好 10 站")
    _assert(len(dataset.lines) == 3, "演示图应有 3 条线")
    _assert(graph.station_lines.get("S3") == ["L1", "L2"],
            "S3 中央广场应为 L1/L2 换乘站")
    feeder = [line for line in dataset.lines.values() if "接驳" in line.name]
    _assert(len(feeder) == 1, "应有一条名称含“接驳”的接驳线（用于虚线）")
    _assert(len({(s.x, s.y) for s in dataset.stations.values()}) == 10,
            "演示图坐标不应重合")
    return f"10 站 / 3 线 / 换乘站 {sum(1 for s in graph.station_lines.values() if len(s) > 1)} 个"


# ----------------------------------------------------------------------
# 3-5 算法
# ----------------------------------------------------------------------
@check(3, "Dijkstra 路径自洽（独立重算）", "算法")
def check_dijkstra() -> str:
    _, graph = _load_graph(BEIJING)
    result = solve(graph, "Dijkstra", "S001", "S061")
    detail = _validate_path(graph, result, "Dijkstra")
    _assert(result.algorithm == "Dijkstra", "结果里的算法名不对")
    return detail


@check(4, "A* 与 Dijkstra 同优且扩展更少", "算法")
def check_astar() -> str:
    _, graph = _load_graph(BEIJING)
    d = solve(graph, "Dijkstra", "S040", "S095")
    a = solve(graph, "A*", "S040", "S095")
    _validate_path(graph, d, "Dijkstra")
    _validate_path(graph, a, "A*")
    _assert(abs(d.total_time - a.total_time) < 1e-6,
            f"A* 耗时 {a.total_time} 与 Dijkstra {d.total_time} 不同（启发函数不可采纳？）")
    _assert(abs(d.total_distance - a.total_distance) < 1e-6, "A* 与 Dijkstra 里程不同")
    _assert(a.expanded <= d.expanded,
            f"A* 扩展 {a.expanded} 个节点，反而多于 Dijkstra 的 {d.expanded} 个")
    # 多准则口径（任务书 P01“基于距离/时间权重的 Dijkstra”）：
    # 距离权重下 Dijkstra / A* 必须得到同一最短里程，且“最快”与“最短里程”
    # 是两种不同准则——时间最优的路不一定是里程最短的路。
    dd = solve(graph, "Dijkstra", "S040", "S095", weight="distance")
    ad = solve(graph, "A*", "S040", "S095", weight="distance")
    _validate_path(graph, dd, "Dijkstra(distance)")
    _validate_path(graph, ad, "A*(distance)")
    _assert(dd.weight == "distance" and ad.weight == "distance", "结果里的权重标记不对")
    _assert(abs(dd.total_distance - ad.total_distance) < 1e-6,
            "距离权重下 A* 与 Dijkstra 的最短里程不一致")
    _assert(dd.total_distance <= d.total_distance + 1e-9,
            f"距离权重路径 {dd.total_distance} km 反而长于时间权重路径 {d.total_distance} km")
    _assert(d.total_time <= dd.total_time + 1e-9,
            f"时间权重路径 {d.total_time} min 反而慢于距离权重路径 {dd.total_time} min")
    return (f"同优 {d.total_time:.1f} min；扩展 A*={a.expanded} / "
            f"Dijkstra={d.expanded}（省 {d.expanded - a.expanded} 个）；"
            f"距离权重同为 {dd.total_distance:.3f} km"
            f"（时间最优 {d.total_distance:.3f} km）")


@check(5, "BFS 换乘次数最少", "算法")
def check_bfs() -> str:
    _, graph = _load_graph(BEIJING)
    d = solve(graph, "Dijkstra", "S001", "S061")
    b = solve(graph, "BFS", "S001", "S061")
    _validate_path(graph, b, "BFS")
    _assert(b.transfers <= d.transfers,
            f"BFS 换乘 {b.transfers} 次，多于 Dijkstra 的 {d.transfers} 次")
    return (f"BFS 换乘 {b.transfers} 次 / {b.total_time:.1f} min；"
            f"Dijkstra 换乘 {d.transfers} 次 / {d.total_time:.1f} min")


# ----------------------------------------------------------------------
# 6-7 边界
# ----------------------------------------------------------------------
@check(6, "边界：起终点相同", "边界")
def check_same_station() -> str:
    _, graph = _load_graph(BEIJING)
    details = []
    for algorithm in ("Dijkstra", "A*", "BFS"):
        result = solve(graph, algorithm, "S001", "S001")
        _assert(result.found, f"{algorithm} 起终点相同应视为找到路径")
        _assert(result.stations == ["S001"], f"{algorithm} 同站结果应只有一个站点")
        _assert(abs(result.total_time) < 1e-9, f"{algorithm} 同站耗时应为 0")
        _assert(result.transfers == 0, f"{algorithm} 同站不应有换乘")
        details.append(f"{algorithm}=0 min")
    return "；".join(details)


@check(7, "边界：不连通返回无路径", "边界")
def check_no_path() -> str:
    _, graph = _load_graph(DISCONNECTED)
    result = solve(graph, "Dijkstra", "D1", "D4")
    _assert(not result.found, "D1 与 D4 属于两个连通分量，应返回 found=False")
    _assert(bool(result.message), "无路径结果应带中文说明")

    # 真实北京数据里的 S1 支线也是独立分量，顺便验证一次
    _, beijing = _load_graph(BEIJING)
    real = solve(beijing, "Dijkstra", "S132", "S001")
    _assert(not real.found, "北京 S1 支线（S132）与主线不连通，应返回 found=False")
    return "合成图 D1→D4 与真实图 S132→S001 均正确返回无路径"


# ----------------------------------------------------------------------
# 8 性能
# ----------------------------------------------------------------------
@check(8, "134 站全图性能", "性能")
def check_performance() -> str:
    start = time.perf_counter()
    _, graph = _load_graph(BEIJING)
    build_ms = (time.perf_counter() - start) * 1000.0

    pairs = [
        ("S001", "S061"),
        ("S040", "S095"),
        ("S023", "S059"),
        ("S081", "S031"),
        ("S095", "S040"),
    ]
    worst_median = 0.0
    worst_label = ""
    samples: list[str] = []
    for start_id, end_id in pairs:
        for algorithm in ("Dijkstra", "A*", "BFS"):
            times = []
            for _ in range(3):
                moment = time.perf_counter()
                result = solve(graph, algorithm, start_id, end_id)
                times.append((time.perf_counter() - moment) * 1000.0)
                _assert(result.found, f"{algorithm} {start_id}->{end_id} 应连通")
            median = statistics.median(times)
            if median > worst_median:
                worst_median = median
                worst_label = f"{algorithm} {start_id}->{end_id}"
        samples.append(f"{start_id}->{end_id}")
    _assert(build_ms < 500, f"建图耗时 {build_ms:.1f}ms 超过 500ms")
    _assert(worst_median < 200,
            f"最慢算法中位数 {worst_median:.1f}ms（{worst_label}）超过 200ms 阈值")
    return (f"建图 {build_ms:.1f}ms；{len(pairs)} 对起终点 × 3 算法，"
            f"最慢中位数 {worst_median:.2f}ms（{worst_label}）")


# ----------------------------------------------------------------------
# 9 坐标数学（不需要 GUI）
# ----------------------------------------------------------------------
@check(9, "坐标变换：等比 + y 翻转 + 缩放锚点", "界面")
def check_transform() -> str:
    transform = ViewTransform((0.0, 0.0, 10.0, 6.0), 1000, 700, 50)

    # 1) y 翻转：世界 y 越大，屏幕 y 越小（越靠上）
    _, y_bottom = transform.to_screen(0, 0)
    _, y_top = transform.to_screen(0, 6)
    _assert(y_top < y_bottom, "y 轴没有翻转")

    # 2) 等比：同样 1 公里，水平和垂直方向的像素长度相同
    p0 = transform.to_screen(0, 0)
    px = transform.to_screen(1, 0)
    py = transform.to_screen(0, 1)
    dx = math.dist(p0, px)
    dy = math.dist(p0, py)
    _assert(abs(dx - dy) < 1e-9, f"x/y 缩放不同比：{dx:.6f} vs {dy:.6f}")

    # 3) 往返：屏幕 -> 世界 -> 屏幕 误差应接近 0
    for sx, sy in ((0, 0), (123.4, 456.7), (999, 699), (500, 350)):
        wx, wy = transform.to_world(sx, sy)
        bx, by = transform.to_screen(wx, wy)
        _assert(abs(sx - bx) < 1e-6 and abs(sy - by) < 1e-6, "坐标往返误差过大")

    # 4) 以光标为锚点缩放：光标下的世界坐标不变
    anchor = (321.0, 234.0)
    before = transform.to_world(*anchor)
    old_scale = transform.scale
    _assert(transform.zoom_at(anchor[0], anchor[1], 1.5), "zoom_at 应改变缩放")
    after = transform.to_world(*anchor)
    _assert(abs(before[0] - after[0]) < 1e-6 and abs(before[1] - after[1]) < 1e-6,
            "缩放后光标下的世界坐标漂移了")
    _assert(abs(transform.scale / old_scale - 1.5) < 1e-9, "缩放倍率不是 1.5")

    # 5) 缩放范围限制 0.5x ~ 3x
    for _ in range(30):
        transform.zoom_at(500, 350, 2.0)
    _assert(transform.zoom <= ViewTransform.MAX_ZOOM + 1e-9, "放大超过 3 倍上限")
    for _ in range(60):
        transform.zoom_at(500, 350, 0.5)
    _assert(transform.zoom >= ViewTransform.MIN_ZOOM - 1e-9, "缩小低于 0.5 倍下限")

    # 6) 平移与复位
    transform.reset()
    base = transform.to_screen(5, 3)
    transform.pan_by(37, -21)
    moved = transform.to_screen(5, 3)
    _assert(abs(moved[0] - base[0] - 37) < 1e-6, "pan_x 未生效")
    _assert(abs(moved[1] - base[1] + 21) < 1e-6, "pan_y 未生效")
    transform.reset()
    _assert(transform.zoom == 1.0 and transform.pan_x == 0 and transform.pan_y == 0,
            "复位没有清空缩放/平移")

    return (f"等比 {dx:.3f}px/km；缩放范围 {ViewTransform.MIN_ZOOM}×–"
            f"{ViewTransform.MAX_ZOOM}×；往返误差 <1e-6 px")


# ----------------------------------------------------------------------
# 10 GUI 冒烟（站名 / 动画 / 命中 / 导出 / 无业务逻辑）
# ----------------------------------------------------------------------
def _assert_no_overlap(boxes, label: str) -> None:
    """两两检查矩形是否重叠。"""
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            _assert(not boxes[i].overlaps(boxes[j], pad=1.0),
                    f"{label}重叠：{boxes[i].text!r} 与 {boxes[j].text!r}")


def _scan_canvas_source() -> str:
    """用 AST 检查画布没有偷读文件、没有调用求解器。"""
    source = (PROJECT_ROOT / "ui" / "canvas.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.append(node.module or "")
    bad_imports = [
        name for name in imported
        if name == "core" or name.startswith("core.")
        or name in {"algorithms", "loader", "graph"}
    ]
    _assert(not bad_imports, f"canvas.py 不应导入业务层：{bad_imports}")
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            _assert(node.func.id not in {"open", "solve", "load_dataset"},
                    f"canvas.py 不应调用 {node.func.id}()")
    return "AST：无 core 导入、无 open()/solve()/load_dataset()"


@check(10, "界面：站名零重叠 + 动画一致 + 命中 + 导出", "界面")
def check_gui() -> str:
    import tkinter as tk

    _assert_no_business_logic = _scan_canvas_source()
    _, graph = _load_graph(DEMO)
    result = solve(graph, "Dijkstra", "S1", "S8")
    _assert(result.found, "演示图 S1→S8 应连通")

    root = tk.Tk()
    root.title("P4 selfcheck")
    root.geometry("1260x860+40+40")
    try:
        canvas = CanvasView(root, graph)
        canvas.pack(fill="both", expand=True)
        root.update_idletasks()
        root.update()

        # ---- 静态路径：站名/分段标注零重叠 ----
        metrics_static = canvas.show_path(result)
        canvas._redraw()
        root.update()

        station_boxes = list(canvas.station_label_boxes.values())
        _assert(len(station_boxes) == 10,
                f"10 站演示图应画出 10 个站名，实际 {len(station_boxes)}")
        _assert(not canvas.hidden_station_labels,
                f"演示图不应省略站名，实际省略 {canvas.hidden_station_labels}")
        _assert_no_overlap(station_boxes, "站名")

        ride_legs = [leg for leg in result.legs if leg.kind == "ride"]
        _assert(len(canvas.segment_label_boxes) == len(ride_legs),
                f"应画出 {len(ride_legs)} 个分段标注，实际 "
                f"{len(canvas.segment_label_boxes)}（省略 {canvas.hidden_segment_labels}）")
        _assert(canvas.hidden_segment_labels == 0, "演示图不应省略分段标注")
        for segment in canvas.segment_label_boxes:
            for station in station_boxes:
                _assert(not segment.overlaps(station, pad=1.0),
                        f"分段标注压住站名：{segment.text!r} / {station.text!r}")

        # ---- 动画：数值与立即显示完全一致 ----
        metrics_anim = canvas.animate(result, speed_level=4)
        _assert(metrics_anim == metrics_static,
                f"动画统计 {metrics_anim} 与立即显示 {metrics_static} 不一致")
        root.update()
        _assert(canvas.is_animating, "调用 animate 后应处于动画状态")
        canvas.skip_animation()
        root.update()
        _assert(not canvas.is_animating, "skip 后动画应停止")
        _assert(canvas.get_metrics() == metrics_static, "动画结束后统计值变化")

        # ---- 切换算法时旧动画不能残留 ----
        canvas.animate(result, speed_level=4)
        root.update()
        canvas.show_path(result)
        root.update()
        _assert(not canvas.is_animating, "show_path 应取消旧动画")
        _assert(not canvas.find_withtag("anim"), "旧动画帧没有被清理")

        # ---- 缩放/平移后点击命中 ----
        canvas.reset()
        canvas.set_zoom(2.5)
        canvas.pan_by(-30, 20)
        canvas._redraw()
        root.update()
        max_hit_error = 0.0
        offset = 7.8  # 斜向偏移约 11.03px，仍在 12px 命中半径内
        for sid, station in graph.stations.items():
            sx, sy = canvas.world_to_screen(station.x, station.y)
            # 1) 正好点在站点圆心上，必须命中
            hit = canvas.hit_test(sx, sy)
            _assert(hit == sid, f"缩放后点击 {sid} 命中到了 {hit}")
            # 2) 偏 11px 还能命中，说明验收要求的 ≤12px 容差确实生效
            hit_near = canvas.hit_test(sx + offset, sy + offset)
            _assert(hit_near == sid,
                    f"点击偏 11px 后 {sid} 命中到了 {hit_near}")
            max_hit_error = max(max_hit_error, math.hypot(offset, offset))
        _assert(max_hit_error <= 12.0, "点击命中误差超过 12px")

        # ---- 拖拽：只平移地图层，图例等固定控件不跟着跑 ----
        import types

        canvas.reset()
        canvas.show_path(result)
        canvas._redraw()
        root.update()
        before = canvas.station_screen("S1")
        legend_before = canvas._legend_rect
        press = types.SimpleNamespace(x=500, y=400)
        drag = types.SimpleNamespace(x=540, y=420)
        release = types.SimpleNamespace(x=540, y=420)
        canvas._on_press(press)
        canvas._on_drag(drag)
        after = canvas.station_screen("S1")
        _assert(before is not None and after is not None, "拖拽前/后取不到站点屏幕坐标")
        _assert(abs((after[0] - before[0]) - 40) < 1e-6,
                f"拖拽 40px 后 x 位移是 {after[0] - before[0]:.2f}")
        _assert(abs((after[1] - before[1]) - 20) < 1e-6,
                f"拖拽 20px 后 y 位移是 {after[1] - before[1]:.2f}")
        _assert(canvas._legend_rect == legend_before, "拖拽时图例不应跟着移动")
        canvas._on_release(release)
        root.update()

        # ---- 导出 PNG ----
        canvas.reset()
        canvas.show_path(result)
        canvas._redraw()
        root.update()
        root.lift()
        root.attributes("-topmost", True)
        root.update()
        out_path = PROJECT_ROOT / "_smoke" / "selfcheck_canvas.png"
        saved = canvas.export(str(out_path))
        root.attributes("-topmost", False)
        _assert(os.path.isfile(saved), f"导出文件不存在：{saved}")
        _assert(os.path.getsize(saved) > 8_000,
                f"导出 PNG 只有 {os.path.getsize(saved)} 字节，可能没截到画布")

        # ---- 真实 134 站密集图：站名仍然不能互相压盖 ----
        _, beijing_graph = _load_graph(BEIJING)
        canvas.set_graph(beijing_graph)
        dense_result = solve(beijing_graph, "Dijkstra", "S001", "S061")
        canvas.show_path(dense_result)
        canvas._redraw()
        root.update()
        dense_stations = list(canvas.station_label_boxes.values())
        _assert(len(dense_stations) >= 100,
                f"北京图只画出 {len(dense_stations)} 个站名，避让策略过于保守")
        _assert_no_overlap(dense_stations, "北京站名")
        for segment in canvas.segment_label_boxes:
            for station in dense_stations:
                _assert(not segment.overlaps(station, pad=1.0),
                        f"北京图分段标注压住站名：{segment.text!r} / {station.text!r}")

        return (f"{_assert_no_business_logic}；10 站名零重叠；"
                f"{len(ride_legs)} 段标注零重叠；动画/立即一致；"
                f"北京 {len(dense_stations)} 站名零重叠（省略 "
                f"{len(canvas.hidden_station_labels)} 个）；"
                f"命中误差 {max_hit_error:.1f}px；PNG {os.path.getsize(saved) // 1024}KB")
    finally:
        try:
            root.destroy()
        except tk.TclError:
            pass


# ----------------------------------------------------------------------
# 运行器
# ----------------------------------------------------------------------
def _apply_mutation(name: str) -> None:
    """把某个实现故意改坏，用来验证检查确实能变红。"""
    if name == "yflip":
        from ui.canvas import ViewTransform

        def broken_to_screen(self, x, y):
            # 故意不减 y：y 轴不翻转
            scale = self.scale
            return (
                self.width / 2.0 + (x - self.center_x) * scale + self.pan_x,
                self.height / 2.0 + (y - self.center_y) * scale + self.pan_y,
            )

        ViewTransform.to_screen = broken_to_screen

    elif name == "dijkstra_cost":
        from core import algorithms

        original = algorithms.ALGORITHMS["Dijkstra"]

        def broken_dijkstra(*args, **kwargs):
            result = original(*args, **kwargs)
            result.total_time += 1.0  # 故意改坏总耗时
            return result

        algorithms.ALGORITHMS["Dijkstra"] = broken_dijkstra

    elif name == "labels":
        from ui import canvas as canvas_module

        def broken_layout(self, font_size, path):
            # 故意把前 10 个站名全放在同一个位置
            placed = []
            for sid, station in list(self.draw_graph.stations.items())[:10]:
                placed.append(
                    canvas_module._PlacedLabel(
                        station.name, (10.0, 10.0, 90.0, 24.0), sid,
                        font_size, False, "#000000", False,
                    )
                )
            return placed, []

        CanvasView._layout_station_labels = broken_layout

    else:
        raise ValueError(f"未知的 mutation：{name}")


def _run_one(number: int, name: str, category: str, func, verbose: bool,
             no_gui: bool) -> CheckResult:
    start = time.perf_counter()
    if no_gui and number == 10:
        return CheckResult(number, name, category, "SKIP",
                           "使用 --no-gui，跳过界面项", (time.perf_counter() - start) * 1000)
    try:
        detail = func()
        status = "PASS"
    except CheckSkipped as exc:
        detail = str(exc)
        status = "SKIP"
    except Exception as exc:
        detail = f"{type(exc).__name__}: {exc}"
        if verbose:
            traceback.print_exc()
        status = "FAIL"
    return CheckResult(number, name, category, status, str(detail),
                       (time.perf_counter() - start) * 1000)


def run_checks(only: list[int] | None = None, verbose: bool = False,
               no_gui: bool = False) -> int:
    selected = [item for item in CHECKS if only is None or item[0] in only]
    if not selected:
        print("没有匹配的检查项。")
        return 2

    print("=" * 78)
    print("城市交通路径导航系统 · P4 自检矩阵")
    print(f"Python {sys.version.split()[0]} · 项目目录 {PROJECT_ROOT}")
    print("=" * 78)

    results: list[CheckResult] = []
    started = time.perf_counter()
    for number, name, category, func in selected:
        result = _run_one(number, name, category, func, verbose, no_gui)
        results.append(result)
        mark = {"PASS": "PASS", "FAIL": "FAIL", "SKIP": "SKIP"}[result.status]
        print(f"[{mark}] {number:02d}. {name}  ({category}, {result.elapsed_ms:.0f} ms)")
        if result.detail and (verbose or result.status != "PASS"):
            for line in result.detail.splitlines():
                print(f"        {line}")

    elapsed = (time.perf_counter() - started) * 1000
    passed = sum(1 for r in results if r.status == "PASS")
    failed = sum(1 for r in results if r.status == "FAIL")
    skipped = sum(1 for r in results if r.status == "SKIP")
    print("-" * 78)
    print(f"结论：{passed} 通过 / {failed} 失败 / {skipped} 跳过，"
          f"共 {len(results)} 项，用时 {elapsed:.0f} ms")
    if failed:
        print("闸门：红（退出码 1）。请修好失败项再合并。")
        return 1
    if skipped:
        print("闸门：绿（有跳过项；本次未验证 GUI）。")
    else:
        print("闸门：绿（退出码 0）。")
    return 0


# ----------------------------------------------------------------------
# 判别力演示：改坏实现 -> 检查必须变红
# ----------------------------------------------------------------------
MUTATIONS = [
    ("yflip", 9, "把 y 翻转去掉"),
    ("dijkstra_cost", 3, "给 Dijkstra 总耗时加 1 分钟"),
    ("labels", 10, "把 10 个站名叠在同一位置"),
]


def run_mutation_demo() -> int:
    print("=" * 78)
    print("判别力演示：故意改坏实现，对应的自检必须失败（变红）")
    print("=" * 78)
    all_caught = True
    for name, number, description in MUTATIONS:
        command = [
            sys.executable, str(Path(__file__).resolve()),
            "--only", str(number), "--mutate", name,
        ]
        env = dict(os.environ)
        env["PYTHONIOENCODING"] = "utf-8"
        process = subprocess.run(
            command, capture_output=True, text=True,
            encoding="utf-8", errors="replace", env=env, timeout=180,
            cwd=str(PROJECT_ROOT),
        )
        caught = process.returncode == 1
        all_caught = all_caught and caught
        mark = "CAUGHT" if caught else "MISSED"
        print(f"[{mark}] 第 {number:02d} 项：{description} -> "
              f"退出码 {process.returncode}")
        if not caught:
            tail = (process.stdout or "")[-600:]
            print(tail)
            print((process.stderr or "")[-600:])
    print("-" * 78)
    if all_caught:
        print("结果：3 种破坏全部被检查发现，说明断言有判别力（不是恒真）。")
        return 0
    print("结果：有破坏没有被发现，自检不可信！")
    return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="P4 自检矩阵")
    parser.add_argument("--verbose", action="store_true", help="打印每项细节/失败堆栈")
    parser.add_argument("--no-gui", action="store_true", help="跳过 GUI 项（无显示环境）")
    parser.add_argument("--only", default="", help="只跑指定编号，例如 3 或 3,9,10")
    parser.add_argument("--mutation-demo", action="store_true",
                        help="演示“改坏实现会变红”")
    parser.add_argument("--mutate", default="", help=argparse.SUPPRESS)
    return parser


def run_cli(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    # GUI 检查要截图导出，必须先声明 DPI 感知，否则 125%/150% 缩放下会截偏
    from ui.dpi import enable_high_dpi

    enable_high_dpi()
    args = build_parser().parse_args(argv)
    if args.mutation_demo:
        return run_mutation_demo()
    if args.mutate:
        _apply_mutation(args.mutate)
    only = None
    if args.only:
        try:
            only = [int(part) for part in args.only.replace("，", ",").split(",") if part.strip()]
        except ValueError:
            print("--only 需要逗号分隔的数字，例如 3,9,10")
            return 2
    return run_checks(only=only, verbose=args.verbose, no_gui=args.no_gui)


def main() -> int:
    return run_cli(sys.argv[1:])


if __name__ == "__main__":
    sys.exit(main())
