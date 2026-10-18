"""寻路算法（Solver 层）：Dijkstra、A*、分层 BFS 最少换乘。

三种算法共用同一张「站台图」（站点 × 线路），都返回 RouteResult，
因此界面层不需要关心算法细节，只负责把结果画出来。

* Dijkstra：边权 = 乘车/换乘时间（默认）或里程，求总耗时/总里程最短。
* A*      ：在 Dijkstra 基础上加入可采纳启发函数（时间权重用直线距离/最高速度，
             距离权重用直线距离），减少扩展节点，结果仍最优。
* BFS     ：以「换乘次数」为层数扩展，求换乘最少；层内再用整条线路扩展，
             最少换乘次数确定后，在同换乘次数约束下按 ``weight`` 择优。
"""

from __future__ import annotations

import heapq
import itertools
import math
import time
from collections import deque
from dataclasses import dataclass, field

from .graph import Edge, MetroGraph

#: Dijkstra/A* 支持的优化目标：time=最快（默认，兼容旧接口）/ distance=里程最短。
WEIGHTS = ("time", "distance")
_WEIGHT_ALIASES = {
    "time": "time", "duration": "time", "minutes": "time",
    "时间": "time", "最快": "time", "最短时间": "time",
    "distance": "distance", "km": "distance", "length": "distance",
    "距离": "distance", "里程": "distance", "最短距离": "distance",
}


def normalise_weight(weight: str = "time") -> str:
    """把权重名解析成 ``time``（最快，默认）或 ``distance``（里程最短）。

    接受英文与中文别名；未知权重抛 ``ValueError``（与 ``solve`` 的
    “未知算法”保持同一种错误风格，界面层会转成中文提示）。
    """
    text = str(weight or "time").strip().lower()
    if text in _WEIGHT_ALIASES:
        return _WEIGHT_ALIASES[text]
    raise ValueError(
        f"未知权重：{weight!r}，可选：time / distance（也接受 时间/距离 等别名）"
    )


def _edge_cost(edge: Edge, weight: str) -> float:
    """按优化目标取边权：时间（默认）或距离。"""
    return edge.distance if weight == "distance" else edge.time


@dataclass
class Leg:
    """路径中的一段：乘车段（相邻两站）或换乘段（同站换线）。"""

    kind: str                 # "ride" 或 "transfer"
    from_station: str
    to_station: str
    line_id: str              # 乘车段：所乘线路；换乘段：换入线路
    time: float               # 分钟
    distance: float           # km


@dataclass
class RouteResult:
    """一次寻路的完整结果，可直接交给界面显示。"""

    algorithm: str
    found: bool
    start_id: str
    end_id: str
    stations: list[str] = field(default_factory=list)   # 途经站点（去重、按顺序）
    legs: list[Leg] = field(default_factory=list)
    total_time: float = 0.0
    total_distance: float = 0.0
    transfers: int = 0
    expanded: int = 0                                   # 出堆/扩展的站台节点数
    elapsed_ms: float = 0.0
    visited_order: list[str] = field(default_factory=list)  # 供搜索动画使用
    message: str = ""
    weight: str = "time"        # 优化目标：time=最快（默认）/ distance=里程最短

    @property
    def station_count(self) -> int:
        return len(self.stations)


# ----------------------------------------------------------------------
# 结果构造
# ----------------------------------------------------------------------
def _result_from_platforms(
    graph: MetroGraph,
    chain: list[tuple[str, str]],
    algorithm: str,
    start_id: str,
    end_id: str,
    expanded: int,
    elapsed_ms: float,
    visited_order: list[str],
    message: str = "搜索成功",
    weight: str = "time",
) -> RouteResult:
    """把站台节点链转换为「站点序列 + 分段列表 + 统计指标」。"""
    if not chain:
        return RouteResult(
            algorithm=algorithm,
            found=False,
            start_id=start_id,
            end_id=end_id,
            expanded=expanded,
            elapsed_ms=elapsed_ms,
            visited_order=visited_order,
            message="两站之间不存在连通路径",
            weight=weight,
        )

    stations: list[str] = [chain[0][0]]
    legs: list[Leg] = []
    total_time = 0.0
    total_distance = 0.0

    for (s1, l1), (s2, l2) in zip(chain, chain[1:]):
        if s1 == s2 and l1 != l2:
            # 同一站点换到另一条线路
            legs.append(
                Leg("transfer", s1, s2, l2, graph.transfer_minutes, 0.0)
            )
            total_time += graph.transfer_minutes
            continue

        if l1 != l2:
            # 理论上不会出现：不同站点、不同线路
            raise RuntimeError("路径链中出现了非法的跨站换乘")

        # 乘车段：BFS 可能一次跨越多个站，需要补齐中间站
        seq = graph.stations_between(l1, s1, s2)
        for a, b in zip(seq, seq[1:]):
            seg_time, seg_distance = graph.segment(l1, a, b)
            legs.append(Leg("ride", a, b, l1, seg_time, seg_distance))
            total_time += seg_time
            total_distance += seg_distance
            stations.append(b)

    transfers = sum(1 for leg in legs if leg.kind == "transfer")
    return RouteResult(
        algorithm=algorithm,
        found=True,
        start_id=start_id,
        end_id=end_id,
        stations=stations,
        legs=legs,
        total_time=total_time,
        total_distance=total_distance,
        transfers=transfers,
        expanded=expanded,
        elapsed_ms=elapsed_ms,
        visited_order=visited_order,
        message=message,
        weight=weight,
    )


def _chain_from_prev(
    prev: dict[tuple[str, str], tuple[tuple[str, str], str] | None],
    target: tuple[str, str],
) -> list[tuple[str, str]]:
    """沿前驱指针回溯，得到从起点站台到终点站台的站台链。"""
    chain: list[tuple[str, str]] = []
    node: tuple[str, str] | None = target
    while node is not None:
        chain.append(node)
        entry = prev.get(node)
        node = entry[0] if entry else None
    chain.reverse()
    return chain


def _trivial(
    graph: MetroGraph, algorithm: str, start_id: str, end_id: str, elapsed: float,
    weight: str = "time",
) -> RouteResult:
    return RouteResult(
        algorithm=algorithm,
        found=True,
        start_id=start_id,
        end_id=end_id,
        stations=[start_id],
        total_time=0.0,
        total_distance=0.0,
        message="起点与终点相同",
        elapsed_ms=elapsed,
        weight=weight,
    )


# ----------------------------------------------------------------------
# Dijkstra
# ----------------------------------------------------------------------
def dijkstra(
    graph: MetroGraph, start_id: str, end_id: str, weight: str = "time"
) -> RouteResult:
    """基于优先队列（二叉堆）的 Dijkstra。

    ``weight="time"``（默认）求总耗时最短；``weight="distance"`` 求总里程最短。
    换乘边的距离为 0，因此距离权重下换乘不增加里程、只增加时间。
    """
    weight = normalise_weight(weight)
    started = time.perf_counter()
    if start_id == end_id:
        return _trivial(
            graph, "Dijkstra", start_id, end_id,
            (time.perf_counter() - started) * 1000, weight=weight,
        )

    counter = itertools.count()
    heap: list[tuple[float, int, tuple[str, str]]] = []
    dist: dict[tuple[str, str], float] = {}
    prev: dict[tuple[str, str], tuple[tuple[str, str], str] | None] = {}
    visited: set[tuple[str, str]] = set()
    visited_order: list[str] = []

    # 多源起点：起点站的所有站台初始距离均为 0
    for line_id in graph.station_lines[start_id]:
        node = (start_id, line_id)
        dist[node] = 0.0
        prev[node] = None
        heapq.heappush(heap, (0.0, next(counter), node))

    expanded = 0
    target: tuple[str, str] | None = None

    while heap:
        current_dist, _, node = heapq.heappop(heap)
        if node in visited:
            continue
        visited.add(node)
        expanded += 1
        station, _ = node
        if not visited_order or visited_order[-1] != station:
            visited_order.append(station)

        if station == end_id:
            target = node
            break

        for edge in graph.adjacency[node]:
            nxt = (edge.to_station, edge.to_line)
            new_dist = current_dist + _edge_cost(edge, weight)
            if new_dist < dist.get(nxt, math.inf) - 1e-12:
                dist[nxt] = new_dist
                prev[nxt] = (node, edge.kind)
                heapq.heappush(heap, (new_dist, next(counter), nxt))

    elapsed_ms = (time.perf_counter() - started) * 1000
    if target is None:
        return RouteResult(
            algorithm="Dijkstra",
            found=False,
            start_id=start_id,
            end_id=end_id,
            expanded=expanded,
            elapsed_ms=elapsed_ms,
            visited_order=visited_order,
            message="两站之间不存在连通路径",
            weight=weight,
        )
    return _result_from_platforms(
        graph,
        _chain_from_prev(prev, target),
        "Dijkstra",
        start_id,
        end_id,
        expanded,
        elapsed_ms,
        visited_order,
        weight=weight,
    )


# ----------------------------------------------------------------------
# A*
# ----------------------------------------------------------------------
def astar(
    graph: MetroGraph, start_id: str, end_id: str, weight: str = "time"
) -> RouteResult:
    """A*：f(n) = g(n) + h(n)。

    ``weight="time"``（默认）时 h 为“直线距离 / 全网最高速度”，单位分钟；
    ``weight="distance"`` 时 h 直接取直线距离（km）。两种 h 都不会高估真实
    代价，因此 A* 结果与同权重的 Dijkstra 一致，但扩展更少。
    """
    weight = normalise_weight(weight)
    started = time.perf_counter()
    if start_id == end_id:
        return _trivial(
            graph, "A*", start_id, end_id,
            (time.perf_counter() - started) * 1000, weight=weight,
        )

    counter = itertools.count()
    heap: list[tuple[float, float, int, tuple[str, str]]] = []
    g_score: dict[tuple[str, str], float] = {}
    prev: dict[tuple[str, str], tuple[tuple[str, str], str] | None] = {}
    visited: set[tuple[str, str]] = set()
    visited_order: list[str] = []
    closed_expanded = 0

    for line_id in graph.station_lines[start_id]:
        node = (start_id, line_id)
        g_score[node] = 0.0
        prev[node] = None
        if weight == "distance":
            h = graph.heuristic_distance(start_id, end_id)
        else:
            h = graph.heuristic(start_id, end_id)
        heapq.heappush(heap, (h, 0.0, next(counter), node))

    target: tuple[str, str] | None = None

    while heap:
        _, current_g, _, node = heapq.heappop(heap)
        if node in visited:
            continue
        visited.add(node)
        closed_expanded += 1
        station, _ = node
        if not visited_order or visited_order[-1] != station:
            visited_order.append(station)

        if station == end_id:
            target = node
            break

        for edge in graph.adjacency[node]:
            nxt = (edge.to_station, edge.to_line)
            new_g = current_g + _edge_cost(edge, weight)
            if new_g < g_score.get(nxt, math.inf) - 1e-12:
                g_score[nxt] = new_g
                prev[nxt] = (node, edge.kind)
                if weight == "distance":
                    h = graph.heuristic_distance(edge.to_station, end_id)
                else:
                    h = graph.heuristic(edge.to_station, end_id)
                f = new_g + h
                heapq.heappush(heap, (f, new_g, next(counter), nxt))

    elapsed_ms = (time.perf_counter() - started) * 1000
    if target is None:
        return RouteResult(
            algorithm="A*",
            found=False,
            start_id=start_id,
            end_id=end_id,
            expanded=closed_expanded,
            elapsed_ms=elapsed_ms,
            visited_order=visited_order,
            message="两站之间不存在连通路径",
            weight=weight,
        )
    return _result_from_platforms(
        graph,
        _chain_from_prev(prev, target),
        "A*",
        start_id,
        end_id,
        closed_expanded,
        elapsed_ms,
        visited_order,
        weight=weight,
    )


# ----------------------------------------------------------------------
# 分层 BFS：最少换乘
# ----------------------------------------------------------------------
def _fastest_within_transfers(
    graph: MetroGraph, start_id: str, end_id: str, max_transfers: int,
    weight: str = "time",
) -> RouteResult | None:
    """在“换乘次数不超过 max_transfers”的约束下，按 ``weight`` 择优。

    这是对分层 BFS 的补充：BFS 只保证换乘次数最少，同一层里可能存在
    绕远路的方案。这里把状态扩展为 (站点, 线路, 已换乘次数)，再跑一次
    Dijkstra，从而在“最少换乘”的前提下按耗时（默认）或里程择优。

    状态数最多为 |站台| × (max_transfers+1)，本数据规模下开销很小。
    """
    counter = itertools.count()
    heap: list[tuple[float, int, int, tuple[str, str, int]]] = []
    dist: dict[tuple[str, str, int], float] = {}
    prev: dict[
        tuple[str, str, int], tuple[tuple[str, str, int], str] | None
    ] = {}
    visited: set[tuple[str, str, int]] = set()
    visited_order: list[str] = []

    for line_id in graph.station_lines[start_id]:
        state = (start_id, line_id, 0)
        dist[state] = 0.0
        prev[state] = None
        heapq.heappush(heap, (0.0, 0, next(counter), state))

    target: tuple[str, str, int] | None = None
    while heap:
        current_dist, transfers, _, state = heapq.heappop(heap)
        if state in visited:
            continue
        visited.add(state)
        station, line_id, _ = state
        if not visited_order or visited_order[-1] != station:
            visited_order.append(station)
        if station == end_id:
            target = state
            break
        for edge in graph.adjacency[(station, line_id)]:
            next_transfers = transfers + (1 if edge.kind == "transfer" else 0)
            if next_transfers > max_transfers:
                continue
            nxt = (edge.to_station, edge.to_line, next_transfers)
            new_dist = current_dist + _edge_cost(edge, weight)
            if new_dist < dist.get(nxt, math.inf) - 1e-12:
                dist[nxt] = new_dist
                prev[nxt] = (state, edge.kind)
                heapq.heappush(heap, (new_dist, next_transfers, next(counter), nxt))

    if target is None:
        return None
    chain: list[tuple[str, str]] = []
    node: tuple[str, str, int] | None = target
    while node is not None:
        chain.append((node[0], node[1]))
        entry = prev.get(node)
        node = entry[0] if entry else None
    chain.reverse()
    return _result_from_platforms(
        graph, chain, "BFS", start_id, end_id, 0, 0.0, visited_order,
        message="搜索成功（最少换乘，同换乘次数下按权重择优）",
        weight=weight,
    )


def bfs_min_transfers(
    graph: MetroGraph, start_id: str, end_id: str, weight: str = "time"
) -> RouteResult:
    """以换乘次数为层数的 BFS，并在最少换乘约束下按 ``weight`` 择优。

    第 k 层保存「恰好换乘 k 次可达」的站台。每弹出一个站台，就沿它所属的
    线路一次扩展整条线（同一条线上的所有站点换乘次数都不变），再把这些站点
    上的其他线路站台放入下一层（换乘 +1）。因此终点第一次被访问时的层数
    就是最少换乘次数。

    BFS 只负责确定“最少换乘几次”；同一换乘次数下可能有多条路线，
    随后在换乘次数不超过该值的约束下按 ``weight``（默认耗时，可改为里程）
    再做一次最短路搜索，避免选中绕远路的方案。

    ``expanded`` 记录的是分层 BFS 的“线路扩展帧”（一条线一次），与
    Dijkstra/A* 的逐站台扩展**不是同一计数口径**，报告中已单列说明。
    """
    weight = normalise_weight(weight)
    started = time.perf_counter()
    if start_id == end_id:
        return _trivial(
            graph, "BFS", start_id, end_id,
            (time.perf_counter() - started) * 1000, weight=weight,
        )

    start_platforms = [(start_id, lid) for lid in graph.station_lines[start_id]]
    parent: dict[
        tuple[str, str], tuple[tuple[str, str], str] | None
    ] = {node: None for node in start_platforms}
    visited_platforms = set(start_platforms)
    visited_stations = {start_id: 0}
    visited_order = [start_id]

    current = deque(start_platforms)
    next_level: deque[tuple[str, str]] = deque()
    level = 0
    target: tuple[str, str] | None = None
    expanded = 0

    while current and target is None:
        next_level = deque()
        while current and target is None:
            station_id, line_id = current.popleft()
            expanded += 1

            # 沿当前线路乘坐，可直达该线路上的所有站点（换乘次数不变）
            for other in graph.line_stations[line_id]:
                # 已访问过的站点：它的换乘站台在更早的层已经入队，无需重复处理
                if other in visited_stations:
                    continue

                visited_stations[other] = level
                visited_order.append(other)
                parent[(other, line_id)] = ((station_id, line_id), "ride")
                # 该乘车方向上的站台已经处理过，标记后避免被当成换乘节点重复入队
                visited_platforms.add((other, line_id))

                if other == end_id:
                    target = (other, line_id)
                    break

                # 该站点上其他线路的站台，需要多一次换乘，放到下一层
                for other_line in graph.station_lines[other]:
                    if other_line == line_id:
                        continue
                    node = (other, other_line)
                    if node not in visited_platforms:
                        visited_platforms.add(node)
                        parent[node] = ((other, line_id), "transfer")
                        next_level.append(node)
        current = next_level
        level += 1

    elapsed_ms = (time.perf_counter() - started) * 1000
    if target is None:
        return RouteResult(
            algorithm="BFS",
            found=False,
            start_id=start_id,
            end_id=end_id,
            expanded=expanded,
            elapsed_ms=elapsed_ms,
            visited_order=visited_order,
            message="两站之间不存在连通路径",
            weight=weight,
        )

    # 第二阶段：在“不超过最少换乘次数”的约束下按 weight 择优
    min_transfers = level - 1
    optimized = _fastest_within_transfers(
        graph, start_id, end_id, min_transfers, weight=weight
    )
    if optimized is not None and optimized.found:
        # expanded 仍是分层 BFS 的线路扩展帧（口径见 docstring / 报告注脚）；
        # 动画改用第二阶段（决定最终路径）的搜索顺序，保证“搜索波”与高亮
        # 路径同源；旧数据/无记录时退回分层 BFS 的层序。
        optimized.expanded = expanded
        optimized.elapsed_ms = (time.perf_counter() - started) * 1000
        optimized.visited_order = optimized.visited_order or visited_order
        optimized.transfers = min_transfers
        optimized.weight = weight
        return optimized

    # 理论上不会走到这里；保留 BFS 原始路径作为兜底
    chain = _chain_from_prev(parent, target)
    result = _result_from_platforms(
        graph,
        chain,
        "BFS",
        start_id,
        end_id,
        expanded,
        (time.perf_counter() - started) * 1000,
        visited_order,
        message="搜索成功（按换乘次数最少）",
        weight=weight,
    )
    result.transfers = min_transfers
    return result


# ----------------------------------------------------------------------
# 统一入口与对比
# ----------------------------------------------------------------------
ALGORITHMS = {
    "Dijkstra": dijkstra,
    "A*": astar,
    "BFS": bfs_min_transfers,
}


def solve(
    graph: MetroGraph, algorithm: str, start_id: str, end_id: str,
    weight: str = "time",
) -> RouteResult:
    """按名称调用算法，供界面层/接口层使用。

    ``weight``：``time``（默认，最快）或 ``distance``（里程最短），
    也接受“时间/距离/最快/最短距离”等中文别名。
    """
    try:
        func = ALGORITHMS[algorithm]
    except KeyError as exc:
        raise ValueError(f"未知算法：{algorithm}") from exc
    if start_id not in graph.stations or end_id not in graph.stations:
        raise ValueError("起点或终点不在当前路网中")
    weight = normalise_weight(weight)
    return func(graph, start_id, end_id, weight=weight)


def compare_algorithms(
    graph: MetroGraph, start_id: str, end_id: str, weight: str = "time"
) -> dict[str, RouteResult]:
    """依次运行三种算法，返回对比结果（默认按最快口径）。"""
    return {
        name: solve(graph, name, start_id, end_id, weight=weight)
        for name in ("Dijkstra", "A*", "BFS")
    }
