"""core 包：P1 数据层 + P2 算法层的只读依赖。

P4（渲染与工程化）不修改这里的任何逻辑，只是**调用**它们：

* ``core.loader``  —— 读取 .json/.txt 路网文件，做格式校验；
* ``core.graph``   —— 站点、线路、邻接表、距离与时间等基础数据；
* ``core.algorithms`` —— Dijkstra / A* / BFS 三种寻路算法。

这样分层的好处是：画布只要拿到一个“图对象”和一份“结果对象”就能工作，
不会把算法或文件读写塞进界面代码里。
"""

from .algorithms import (
    ALGORITHMS,
    Leg,
    RouteResult,
    astar,
    bfs_min_transfers,
    compare_algorithms,
    dijkstra,
    solve,
)
from .graph import Edge, MetroGraph, MetroLine, Station
from .loader import DataFormatError, MetroDataset, load_dataset

__all__ = [
    "ALGORITHMS",
    "DataFormatError",
    "Edge",
    "Leg",
    "MetroDataset",
    "MetroGraph",
    "MetroLine",
    "RouteResult",
    "Station",
    "astar",
    "bfs_min_transfers",
    "compare_algorithms",
    "dijkstra",
    "load_dataset",
    "solve",
]
