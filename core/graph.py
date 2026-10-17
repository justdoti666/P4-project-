"""城市交通路网的图结构（Graph 层）。

设计要点
--------
1. 站点（Station）是物理地点；线路（MetroLine）是列车行驶的序列。
2. 搜索时使用「站台节点」= (站点 ID, 线路 ID)。同一站点属于多条线路时，
   不同线路对应不同站台节点，站台之间用「换乘边」连接。这样换乘次数、
   换乘耗时都能被精确建模，而不是把换乘隐藏成一个普通站点。
3. 图的存储采用邻接表：城市路网是稀疏图（E 与 V 同阶），邻接表空间为
   O(V+E)，比邻接矩阵 O(V^2) 更省内存，遍历邻居也更快。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Station:
    """站点：ID、名称、示意坐标（km）。"""

    id: str
    name: str
    x: float
    y: float


@dataclass(frozen=True)
class MetroLine:
    """线路：按列车行驶顺序排列的站点 ID 序列；loop 表示环线。"""

    id: str
    name: str
    color: str
    loop: bool
    stations: tuple[str, ...]


@dataclass(frozen=True)
class Edge:
    """站台节点之间的一条边。

    kind = "ride"     乘车边：同一条线路相邻两站
    kind = "transfer" 换乘边：同一物理站点的两个站台之间
    """

    to_station: str
    to_line: str
    kind: str
    line_id: str
    time: float          # 分钟
    distance: float      # km


@dataclass
class MetroGraph:
    """地铁网络图：负责建图、查询与几何计算，不包含任何寻路算法。"""

    stations: dict[str, Station]
    lines: dict[str, MetroLine]
    speed_kmh: float = 35.0
    dwell_minutes: float = 0.6
    transfer_minutes: float = 4.0

    # 以下字段在 build() 中生成
    station_lines: dict[str, list[str]] = field(default_factory=dict)
    line_stations: dict[str, list[str]] = field(default_factory=dict)
    adjacency: dict[tuple[str, str], list[Edge]] = field(default_factory=dict)
    _line_index: dict[str, dict[str, int]] = field(default_factory=dict)
    _segment_cache: dict[tuple[str, str, str], tuple[float, float]] = field(
        default_factory=dict
    )

    # ------------------------------------------------------------------
    # 建图
    # ------------------------------------------------------------------
    def build(self) -> "MetroGraph":
        """生成站台节点、乘车边、换乘边。"""
        self.station_lines = {sid: [] for sid in self.stations}
        self.line_stations = {}
        self.adjacency = {}
        self._line_index = {}
        self._segment_cache = {}

        # 1) 每条线路的站序、索引
        for line in self.lines.values():
            order = list(line.stations)
            self.line_stations[line.id] = order
            self._line_index[line.id] = {sid: i for i, sid in enumerate(order)}
            for sid in order:
                if sid not in self.stations:
                    raise ValueError(f"线路 {line.id} 引用了不存在的站点 {sid}")
                if line.id not in self.station_lines[sid]:
                    self.station_lines[sid].append(line.id)

        # 2) 创建所有站台节点（即使某站只有一条线也创建）
        for sid, line_ids in self.station_lines.items():
            for lid in line_ids:
                self.adjacency[(sid, lid)] = []

        # 3) 加乘车边（双向）
        for line in self.lines.values():
            order = self.line_stations[line.id]
            pairs = list(zip(order, order[1:]))
            if line.loop and len(order) > 2:
                pairs.append((order[-1], order[0]))
            for a, b in pairs:
                distance = self.distance(a, b)
                time = self.ride_time(distance)
                self.adjacency[(a, line.id)].append(
                    Edge(b, line.id, "ride", line.id, time, distance)
                )
                self.adjacency[(b, line.id)].append(
                    Edge(a, line.id, "ride", line.id, time, distance)
                )

        # 4) 加换乘边（同一站点，任意两条线路之间，双向）
        for sid, line_ids in self.station_lines.items():
            for i in range(len(line_ids)):
                for j in range(len(line_ids)):
                    if i == j:
                        continue
                    self.adjacency[(sid, line_ids[i])].append(
                        Edge(
                            sid,
                            line_ids[j],
                            "transfer",
                            line_ids[j],
                            self.transfer_minutes,
                            0.0,
                        )
                    )
        return self

    # ------------------------------------------------------------------
    # 几何与权重
    # ------------------------------------------------------------------
    def distance(self, a: str, b: str) -> float:
        """两站之间的欧几里得距离（km），用作区间里程。"""
        sa, sb = self.stations[a], self.stations[b]
        return math.hypot(sa.x - sb.x, sa.y - sb.y)

    def ride_time(self, distance: float) -> float:
        """乘车时间 = 行驶时间 + 停站时间。"""
        return distance / self.speed_kmh * 60.0 + self.dwell_minutes

    def heuristic(self, station_id: str, target_id: str) -> float:
        """A* 启发函数 h(n)：当前站到终点的直线距离 / 最高速度（分钟）。

        因为实际乘车时间一定不小于「直线距离 / 最高速度」，且换乘时间为正，
        所以 h(n) 不会高估真实代价（可采纳），A* 仍能得到最优路径。
        """
        return self.distance(station_id, target_id) / self.speed_kmh * 60.0

    def segment(self, line_id: str, a: str, b: str) -> tuple[float, float]:
        """同一条线路上相邻两站 (a,b) 的 (时间, 距离)。"""
        key = (line_id, a, b)
        if key not in self._segment_cache:
            distance = self.distance(a, b)
            self._segment_cache[key] = (self.ride_time(distance), distance)
        return self._segment_cache[key]

    def stations_between(self, line_id: str, a: str, b: str) -> list[str]:
        """在线路 line_id 上，从 a 到 b 依次经过的站点（含首尾）。

        非环线沿线路顺序；环线选择站数较少的方向，避免绕大半圈。
        """
        order = self.line_stations[line_id]
        ia, ib = self._line_index[line_id][a], self._line_index[line_id][b]
        if not self.lines[line_id].loop:
            # 非环线不能绕回起点：反方向时直接取区间后倒序
            if ia <= ib:
                return order[ia : ib + 1]
            return list(reversed(order[ib : ia + 1]))

        # 环线：顺时针、逆时针两条路，选择站数更少的一条
        n = len(order)
        forward_steps = (ib - ia) % n
        backward_steps = (ia - ib) % n
        if forward_steps <= backward_steps:
            return [order[(ia + k) % n] for k in range(forward_steps + 1)]
        return [order[(ia - k) % n] for k in range(backward_steps + 1)]

    def line_color(self, line_id: str) -> str:
        line = self.lines.get(line_id)
        return line.color if line else "#7F8C8D"

    def line_name(self, line_id: str) -> str:
        line = self.lines.get(line_id)
        return line.name if line else line_id

    def station_name(self, station_id: str) -> str:
        station = self.stations.get(station_id)
        return station.name if station else station_id
