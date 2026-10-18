"""城市交通路径导航系统 · 可调用接口（Python SDK + 命令行）。

这个模块把 P1/P2 的 ``core``（数据 + 三种算法）包装成**稳定、JSON 友好、可被
其他程序调用**的接口，不依赖 Tkinter、不打开窗口、不需要第三方库。

给谁用
------
* 同组同学：P3 的窗口之外，如果还要做批处理、对比实验、脚本化演示，
  直接 ``from metro_api import connect`` 即可；
* 其他课程/项目：不想要 GUI、只要「给起终点，返回路径与统计」的能力；
* 其他语言：`python tools/serve_api.py` 起一个本地 HTTP JSON 服务，
  用 curl / requests / 前端 fetch 都能调（见 ``docs/API接口说明.md``）。

快速上手
--------
::

    from metro_api import connect

    nav = connect()                                  # 默认 data/beijing_metro.json
    print(nav.info())                                # 规模统计
    print(nav.route("苹果园", "天通苑北")["summary"])  # 用站名或站 ID 都行
    print(nav.compare("S001", "S061")["highlights"])

命令行::

    python metro_api.py info
    python metro_api.py route --start 苹果园 --end 天通苑北 --json
    python metro_api.py compare --start S001 --end S061
    python metro_api.py serve --port 8765

接口约定
--------
1. **站名或站 ID 都可以**：先按 ID 精确匹配，再按站名精确匹配；
2. **返回纯 Python 对象**（dict / list / str / int / float / bool），
   可直接 ``json.dumps``，不含 dataclass、不含浮点 NaN；
3. **错误分类型**：调用方可以 ``except StationNotFound`` 之类精确处理，
   CLI 与 HTTP 会把它转成对应的错误码（见下表）；
4. **不修改 core**：本模块只读 ``MetroDataset`` / ``MetroGraph`` / ``RouteResult``，
   算法口径与界面完全一致（同一份 ``core.solve``）。

错误码（HTTP 的 ``error.code`` / CLI 的 ``--json`` 输出）
--------------------------------------------------------
==================  ======  ==================================================
code                HTTP    含义
==================  ======  ==================================================
INVALID_REQUEST     400     参数缺失/类型不对（如没给 start）
DATA_ERROR          422     数据文件找不到或格式错误
STATION_NOT_FOUND   404     起点/终点查不到
ALGORITHM_NOT_FOUND 400     算法名不认识（可用 Dijkstra / A* / BFS 及别名）
NOT_FOUND           404     HTTP 端点不存在（仅 HTTP 层）
METHOD_NOT_ALLOWED  405     HTTP 方法不支持，只接受 GET/POST/OPTIONS（仅 HTTP 层）
INTERNAL_ERROR      500     未预期异常（属于 bug，请附日志提 Issue）
==================  ======  ==================================================
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Iterable

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core import (  # noqa: E402  （必须在 sys.path 调整之后导入）
    ALGORITHMS,
    WEIGHTS,
    DataFormatError,
    MetroDataset,
    RouteResult,
    load_dataset,
    normalise_weight,
    solve,
)

__version__ = "1.1.0"

DEFAULT_DATA = PROJECT_ROOT / "data" / "beijing_metro.json"
ALGORITHM_NAMES = ("Dijkstra", "A*", "BFS")

#: 算法别名：大小写/中英文/常见缩写都接受，统一映射到 P2 的三个正式名称。
ALGORITHM_ALIASES = {
    "dijkstra": "Dijkstra",
    "dij": "Dijkstra",
    "time": "Dijkstra",
    "fastest": "Dijkstra",
    "最快": "Dijkstra",
    "最短时间": "Dijkstra",
    "a*": "A*",
    "astar": "A*",
    "a-star": "A*",
    "a星": "A*",
    "bfs": "BFS",
    "least_transfers": "BFS",
    "min_transfers": "BFS",
    "最少换乘": "BFS",
    "换乘最少": "BFS",
}

#: 浮点统一保留 6 位小数，保证 JSON 输出可复现、不出现 79.57529999999 这类噪声。
_FLOAT_DIGITS = 6


# ======================================================================
# 异常：调用方可以按类型捕获，CLI/HTTP 会转成错误码
# ======================================================================
class MetroAPIError(Exception):
    """本模块所有可预期错误的基类。"""

    code = "API_ERROR"
    http_status = 400

    def __init__(self, message: str, *, detail: Any = None) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail

    def to_dict(self) -> dict:
        payload: dict[str, Any] = {
            "ok": False,
            "error": {"code": self.code, "message": self.message},
        }
        if self.detail is not None:
            payload["error"]["detail"] = self.detail
        return payload


class InvalidRequest(MetroAPIError):
    """参数缺失或类型不对。"""

    code = "INVALID_REQUEST"
    http_status = 400


class DataError(MetroAPIError):
    """数据文件不存在或格式错误。"""

    code = "DATA_ERROR"
    http_status = 422


class StationNotFound(MetroAPIError):
    """起点/终点无法按 ID 或站名找到。"""

    code = "STATION_NOT_FOUND"
    http_status = 404


class AlgorithmNotFound(MetroAPIError):
    """算法名不在支持列表中。"""

    code = "ALGORITHM_NOT_FOUND"
    http_status = 400


def _round(value: float) -> float:
    """统一浮点精度（6 位小数）。"""
    return round(float(value), _FLOAT_DIGITS)


def _require_text(value: Any, field: str) -> str:
    """校验必填文本参数，并去掉首尾空白。"""
    if value is None:
        raise InvalidRequest(f"缺少参数：{field}")
    text = str(value).strip()
    if not text:
        raise InvalidRequest(f"参数不能为空：{field}")
    return text


def resolve_algorithm(name: Any) -> str:
    """把算法别名解析成 ``Dijkstra`` / ``A*`` / ``BFS``。"""
    text = _require_text(name, "algorithm")
    if text in ALGORITHM_NAMES:
        return text
    key = text.lower()
    if key in ALGORITHM_ALIASES:
        return ALGORITHM_ALIASES[key]
    # 中文别名不能用 lower() 的语义，但 dict 里已含原样键，再查一次兜底
    if text in ALGORITHM_ALIASES:
        return ALGORITHM_ALIASES[text]
    raise AlgorithmNotFound(
        f"未知算法：{text!r}，可用：{'、'.join(ALGORITHM_NAMES)}"
        "（也接受 astar / bfs / 最少换乘 等别名）",
        detail=list(ALGORITHM_NAMES),
    )


def resolve_weight(name: Any = "time") -> str:
    """把权重别名解析成 ``time``（最快，默认）或 ``distance``（里程最短）。

    失败时抛 :class:`InvalidRequest`（对应 HTTP 400 / CLI 退出码 1），
    与未知算法保持同一种错误处理风格。
    """
    try:
        return normalise_weight(name)
    except ValueError as exc:
        raise InvalidRequest(str(exc)) from exc


# ======================================================================
# 核心：MetroNavigator
# ======================================================================
class MetroNavigator:
    """一个已加载路网的导航会话；线程内只读，可被多个请求复用。

    典型用法::

        nav = MetroNavigator()                    # 默认北京教学路网
        nav = MetroNavigator("data/demo_city.json")
        nav = MetroNavigator(dataset=my_dataset)  # 已有 MetroDataset 时

    实例创建后不再修改图结构，因此同一实例可以被 HTTP 服务的多个线程共享
    （``solve`` 内部所有状态都是局部变量）。
    """

    def __init__(
        self,
        data_path: str | os.PathLike[str] | None = None,
        *,
        dataset: MetroDataset | None = None,
    ) -> None:
        if dataset is None:
            path = Path(data_path) if data_path is not None else DEFAULT_DATA
            path = path.expanduser()
            if not path.is_absolute():
                path = (Path.cwd() / path).resolve()
            try:
                dataset = load_dataset(str(path))
            except DataFormatError as exc:
                raise DataError(str(exc)) from exc
        self.dataset: MetroDataset = dataset
        self.graph = dataset.build_graph()

        # 站名 → ID（loader 已保证站名唯一）；ID → 站名走 graph.station_name
        self._name_to_id: dict[str, str] = {
            st.name: sid for sid, st in dataset.stations.items()
        }

    # ------------------------------------------------------------------
    # 元信息
    # ------------------------------------------------------------------
    @property
    def city(self) -> str:
        return self.dataset.city

    @property
    def data_path(self) -> str:
        return self.dataset.source_path

    @property
    def algorithms(self) -> list[str]:
        return list(ALGORITHM_NAMES)

    def info(self) -> dict:
        """路网规模与参数，等价于「这个接口能提供什么」的一览表。"""
        graph = self.graph
        ride_edges = sum(
            1
            for edges in graph.adjacency.values()
            for edge in edges
            if edge.kind == "ride"
        )
        transfer_edges = sum(
            1
            for edges in graph.adjacency.values()
            for edge in edges
            if edge.kind == "transfer"
        )
        transfer_stations = sum(
            1 for line_ids in graph.station_lines.values() if len(line_ids) > 1
        )
        return {
            "ok": True,
            "api_version": __version__,
            "city": self.city,
            "data_path": self.data_path,
            "station_count": len(self.dataset.stations),
            "line_count": len(self.dataset.lines),
            "platform_count": len(graph.adjacency),
            "ride_edge_count": ride_edges,
            "transfer_edge_count": transfer_edges,
            "transfer_station_count": transfer_stations,
            "loop_line_count": sum(1 for line in self.dataset.lines.values() if line.loop),
            "params": {
                "train_speed_kmh": graph.speed_kmh,
                "dwell_minutes": graph.dwell_minutes,
                "transfer_minutes": graph.transfer_minutes,
            },
            "algorithms": self.algorithms,
        }

    def stations(self, *, line_id: str | None = None, query: str | None = None) -> list[dict]:
        """站点列表：可按线路过滤、按站名/ID 模糊搜索。"""
        line_filter = _require_text(line_id, "line") if line_id else None
        if line_filter is not None and line_filter not in self.dataset.lines:
            raise InvalidRequest(f"线路不存在：{line_filter}")
        needle = str(query).strip().lower() if query else ""
        result: list[dict] = []
        for sid, station in self.dataset.stations.items():
            line_ids = self.graph.station_lines.get(sid, [])
            if line_filter is not None and line_filter not in line_ids:
                continue
            if needle and needle not in sid.lower() and needle not in station.name.lower():
                continue
            result.append(
                {
                    "id": sid,
                    "name": station.name,
                    "x": _round(station.x),
                    "y": _round(station.y),
                    "line_ids": list(line_ids),
                    "line_names": [self.graph.line_name(lid) for lid in line_ids],
                }
            )
        return result

    def lines(self) -> list[dict]:
        """线路列表：颜色、是否环线、站序。"""
        return [
            {
                "id": line.id,
                "name": line.name,
                "color": line.color,
                "loop": bool(line.loop),
                "station_count": len(line.stations),
                "stations": list(line.stations),
            }
            for line in self.dataset.lines.values()
        ]

    # ------------------------------------------------------------------
    # 站点解析
    # ------------------------------------------------------------------
    def resolve_station(self, key: Any) -> str:
        """把「站 ID 或站名」解析成站 ID；找不到时抛 :class:`StationNotFound`。"""
        text = _require_text(key, "station")
        if text in self.dataset.stations:
            return text
        if text in self._name_to_id:
            return self._name_to_id[text]
        raise StationNotFound(
            f"找不到站点：{text!r}（可用站 ID 或站名，先调用 stations() 查看）"
        )

    def station(self, key: Any) -> dict:
        """单个站点的详情（ID / 站名 / 坐标 / 所属线路）。"""
        sid = self.resolve_station(key)
        station = self.dataset.stations[sid]
        line_ids = self.graph.station_lines.get(sid, [])
        return {
            "id": sid,
            "name": station.name,
            "x": _round(station.x),
            "y": _round(station.y),
            "line_ids": list(line_ids),
            "line_names": [self.graph.line_name(lid) for lid in line_ids],
            "is_transfer": len(line_ids) > 1,
        }

    # ------------------------------------------------------------------
    # 寻路
    # ------------------------------------------------------------------
    def route(
        self,
        start: Any,
        end: Any,
        *,
        algorithm: str = "Dijkstra",
        weight: str = "time",
    ) -> dict:
        """求一条路径，返回可直接 JSON 化的结果字典。

        参数
        ----
        start / end : 站 ID 或站名（如 ``"S001"`` / ``"苹果园"``）；
        algorithm   : ``Dijkstra``（默认，最快）、``A*``、``BFS``（最少换乘），
                      也接受 ``astar`` / ``bfs`` / ``最少换乘`` 等别名；
        weight      : 优化目标，``time``（默认，最快）或 ``distance``（里程最短），
                      也接受 ``距离`` / ``最短距离`` 等中文别名；BFS 用它做
                      “最少换乘”前提下的同层择优。

        返回
        ----
        dict：``ok``、``algorithm``、``weight``、``found``、``start``/``end``、
        ``summary``、``stations``、``legs``、``message``。无路径时
        ``found=False``、列表为空，不抛异常。
        """
        start_id = self.resolve_station(start)
        end_id = self.resolve_station(end)
        algorithm = resolve_algorithm(algorithm)
        weight = resolve_weight(weight)

        started = time.perf_counter()
        result = solve(self.graph, algorithm, start_id, end_id, weight=weight)
        wall_ms = (time.perf_counter() - started) * 1000.0
        return self._result_to_dict(result, wall_ms)

    def compare(self, start: Any, end: Any, *, weight: str = "time") -> dict:
        """同一对起终点跑三种算法，并给出差异摘要（答辩/报告常用）。

        ``weight`` 默认为 ``time``（最快）；传 ``distance`` 可比较“最短里程”口径。
        """
        start_id = self.resolve_station(start)
        end_id = self.resolve_station(end)
        weight = resolve_weight(weight)

        routes: dict[str, dict] = {}
        for name in ALGORITHM_NAMES:
            routes[name] = self.route(start_id, end_id, algorithm=name, weight=weight)

        dijkstra = routes["Dijkstra"]
        astar = routes["A*"]
        bfs = routes["BFS"]
        highlights: dict[str, Any] = {
            "dijkstra_astar_same_time": None,
            "astar_expanded_reduction_pct": None,
            "transfers_diff_bfs_vs_dijkstra": None,
            "time_diff_bfs_vs_dijkstra_min": None,
        }
        if dijkstra["found"] and astar["found"]:
            highlights["dijkstra_astar_same_time"] = (
                abs(dijkstra["summary"]["time_min"] - astar["summary"]["time_min"]) < 1e-6
            )
            d_exp = dijkstra["summary"]["expanded"]
            if d_exp:
                highlights["astar_expanded_reduction_pct"] = _round(
                    (1 - astar["summary"]["expanded"] / d_exp) * 100.0
                )
        if dijkstra["found"] and bfs["found"]:
            highlights["transfers_diff_bfs_vs_dijkstra"] = (
                bfs["summary"]["transfers"] - dijkstra["summary"]["transfers"]
            )
            highlights["time_diff_bfs_vs_dijkstra_min"] = _round(
                bfs["summary"]["time_min"] - dijkstra["summary"]["time_min"]
            )
        return {
            "ok": True,
            "start": self._station_ref(start_id),
            "end": self._station_ref(end_id),
            "weight": weight,
            "algorithms": routes,
            "highlights": highlights,
        }

    def export_network(self, path: str | os.PathLike[str]) -> str:
        """把路网元信息 + 站点 + 线路导出为 UTF-8 JSON（给前端/其他服务用）。"""
        target = Path(path).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "ok": True,
            "info": self.info(),
            "stations": self.stations(),
            "lines": self.lines(),
        }
        target.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return str(target)

    # ------------------------------------------------------------------
    # 内部：结果序列化
    # ------------------------------------------------------------------
    def _station_ref(self, sid: str) -> dict:
        return {"id": sid, "name": self.graph.station_name(sid)}

    def _result_to_dict(self, result: RouteResult, wall_ms: float) -> dict:
        payload: dict[str, Any] = {
            "ok": True,
            "algorithm": result.algorithm,
            "weight": result.weight,
            "found": bool(result.found),
            "start": self._station_ref(result.start_id),
            "end": self._station_ref(result.end_id),
            "summary": {
                "time_min": _round(result.total_time),
                "distance_km": _round(result.total_distance),
                "transfers": int(result.transfers),
                "expanded": int(result.expanded),
                "station_count": int(result.station_count),
                "elapsed_ms": _round(result.elapsed_ms),
                "wall_ms": _round(wall_ms),
            },
            "stations": [
                {
                    **self._station_ref(sid),
                    "line_ids": list(self.graph.station_lines.get(sid, [])),
                }
                for sid in result.stations
            ],
            "legs": [
                {
                    "kind": leg.kind,
                    "from": self._station_ref(leg.from_station),
                    "to": self._station_ref(leg.to_station),
                    "line_id": leg.line_id,
                    "line_name": self.graph.line_name(leg.line_id),
                    "time_min": _round(leg.time),
                    "distance_km": _round(leg.distance),
                }
                for leg in result.legs
            ],
            "message": result.message,
        }
        return payload


# ======================================================================
# 模块级便捷函数：一行代码完成常见操作
# ======================================================================
def connect(data_path: str | os.PathLike[str] | None = None) -> MetroNavigator:
    """加载路网并返回 :class:`MetroNavigator`；最常用的入口。"""
    return MetroNavigator(data_path)


def quick_route(
    start: Any,
    end: Any,
    *,
    algorithm: str = "Dijkstra",
    weight: str = "time",
    data_path: str | os.PathLike[str] | None = None,
) -> dict:
    """一次性加载 + 求路径（适合脚本里只查一两条的场景）。"""
    return connect(data_path).route(
        start, end, algorithm=algorithm, weight=weight
    )


def error_payload(exc: BaseException) -> dict:
    """把异常转成统一的错误 JSON；HTTP 服务与 CLI 共用。"""
    if isinstance(exc, MetroAPIError):
        return exc.to_dict()
    return {
        "ok": False,
        "error": {"code": "INTERNAL_ERROR", "message": f"{type(exc).__name__}: {exc}"},
    }


def http_status_for(exc: BaseException) -> int:
    """异常对应的 HTTP 状态码。"""
    if isinstance(exc, MetroAPIError):
        return exc.http_status
    return 500


# ======================================================================
# 命令行
# ======================================================================
def _print_json(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _format_route(payload: dict) -> str:
    """把 route()/compare() 的结果排版成人类可读的中文文本。"""
    if not payload.get("found", True):
        return (
            f"未找到路径：{payload['start']['name']} → {payload['end']['name']}"
            f"（{payload.get('message') or '两站不连通'}）"
        )
    summary = payload["summary"]
    weight_label = "最快" if payload.get("weight", "time") == "time" else "最短里程"
    lines = [
        f"{payload['algorithm']}（{weight_label}）："
        f"{payload['start']['name']} → {payload['end']['name']}",
        f"  {summary['time_min']:.3f} 分钟 · {summary['distance_km']:.3f} km · "
        f"换乘 {summary['transfers']} 次 · {summary['station_count']} 站 · "
        f"扩展 {summary['expanded']} 个站台 · 算法 {summary['elapsed_ms']:.3f} ms",
        "  途经：" + " → ".join(st["name"] for st in payload["stations"]),
    ]
    for leg in payload["legs"]:
        if leg["kind"] == "transfer":
            lines.append(
                f"    ↺ {leg['from']['name']} 换乘 {leg['line_name']}"
                f"（{leg['time_min']:.3f} min）"
            )
        else:
            lines.append(
                f"    {leg['from']['name']} → {leg['to']['name']}"
                f"（{leg['line_name']}，{leg['distance_km']:.3f} km / {leg['time_min']:.3f} min）"
            )
    return "\n".join(lines)


def _cmd_info(nav: MetroNavigator, args: argparse.Namespace) -> int:
    payload = nav.info()
    if args.json:
        _print_json(payload)
        return 0
    print(f"路网：{payload['city']}（{os.path.basename(payload['data_path'])}）")
    print(
        f"  {payload['station_count']} 站 · {payload['line_count']} 线 · "
        f"{payload['platform_count']} 个站台节点 · "
        f"{payload['transfer_station_count']} 个换乘站 · "
        f"{payload['loop_line_count']} 条环线"
    )
    print(f"  算法：{' / '.join(payload['algorithms'])}")
    return 0


def _cmd_stations(nav: MetroNavigator, args: argparse.Namespace) -> int:
    rows = nav.stations(line_id=args.line, query=args.query)
    if args.json:
        _print_json({"ok": True, "count": len(rows), "stations": rows})
        return 0
    print(f"共 {len(rows)} 个站点：")
    for row in rows:
        print(f"  {row['id']:<6} {row['name']:<8} {'/'.join(row['line_names'])}")
    return 0


def _cmd_lines(nav: MetroNavigator, args: argparse.Namespace) -> int:
    rows = nav.lines()
    if args.json:
        _print_json({"ok": True, "count": len(rows), "lines": rows})
        return 0
    print(f"共 {len(rows)} 条线路：")
    for row in rows:
        tag = "（环线）" if row["loop"] else ""
        print(f"  {row['id']:<4} {row['name']:<6}{tag}  {row['station_count']} 站")
    return 0


def _cmd_route(nav: MetroNavigator, args: argparse.Namespace) -> int:
    payload = nav.route(
        args.start, args.end, algorithm=args.algorithm, weight=args.weight
    )
    if args.json:
        _print_json(payload)
    else:
        print(_format_route(payload))
    return 0


def _cmd_compare(nav: MetroNavigator, args: argparse.Namespace) -> int:
    payload = nav.compare(args.start, args.end, weight=args.weight)
    if args.json:
        _print_json(payload)
        return 0
    for name in ALGORITHM_NAMES:
        print(_format_route(payload["algorithms"][name]))
        print()
    print("差异摘要：")
    for key, value in payload["highlights"].items():
        print(f"  {key} = {value}")
    return 0


def _cmd_export(nav: MetroNavigator, args: argparse.Namespace) -> int:
    saved = nav.export_network(args.output)
    if args.json:
        _print_json({"ok": True, "output": saved})
    else:
        print(f"已导出路网 JSON：{saved}")
    return 0


def _cmd_serve(nav: MetroNavigator, args: argparse.Namespace) -> int:
    sys.path.insert(0, str(PROJECT_ROOT / "tools"))
    import serve_api  # noqa: PLC0415  （按需导入，普通 SDK 使用不需要 HTTP）

    return serve_api.serve(nav, host=args.host, port=args.port, quiet=args.quiet)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="metro_api.py",
        description="城市交通路径导航系统 · 可调用接口（Python SDK / CLI / HTTP）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例：\n"
            "  python metro_api.py info\n"
            "  python metro_api.py route --start 苹果园 --end 天通苑北 --json\n"
            "  python metro_api.py compare --start S001 --end S061\n"
            "  python metro_api.py serve --port 8765\n"
        ),
    )
    parser.add_argument("--data", default=None,
                        help="路网数据（.json/.txt），默认 data/beijing_metro.json")
    parser.add_argument("--version", action="store_true", help="打印版本信息")

    sub = parser.add_subparsers(dest="command", metavar="子命令")

    def _add_data_option(p: argparse.ArgumentParser) -> None:
        p.add_argument("--data", default=None, dest="sub_data",
                       help="该子命令使用的数据文件（覆盖全局 --data）")

    info = sub.add_parser("info", help="路网规模与参数")
    _add_data_option(info)
    info.add_argument("--json", action="store_true", help="输出 JSON")

    stations = sub.add_parser("stations", help="站点列表 / 搜索")
    _add_data_option(stations)
    stations.add_argument("--line", default=None, help="只看某条线路，如 L1")
    stations.add_argument("--query", default=None, help="按站名或 ID 模糊搜索")
    stations.add_argument("--json", action="store_true", help="输出 JSON")

    lines = sub.add_parser("lines", help="线路列表")
    _add_data_option(lines)
    lines.add_argument("--json", action="store_true", help="输出 JSON")

    route = sub.add_parser("route", help="求一条路径")
    _add_data_option(route)
    route.add_argument("--start", required=True, help="起点：站 ID 或站名")
    route.add_argument("--end", required=True, help="终点：站 ID 或站名")
    route.add_argument("--algorithm", default="Dijkstra",
                       help="Dijkstra（默认）/ A* / BFS，支持别名")
    route.add_argument("--weight", default="time",
                       help="优化目标：time=最快（默认）/ distance=最短里程")
    route.add_argument("--json", action="store_true", help="输出 JSON")

    compare = sub.add_parser("compare", help="三种算法对比")
    _add_data_option(compare)
    compare.add_argument("--start", required=True)
    compare.add_argument("--end", required=True)
    compare.add_argument("--weight", default="time",
                         help="优化目标：time=最快（默认）/ distance=最短里程")
    compare.add_argument("--json", action="store_true", help="输出 JSON")

    export = sub.add_parser("export", help="导出路网 JSON（站点 + 线路 + 规模）")
    _add_data_option(export)
    export.add_argument("--output", required=True, help="输出 .json 路径")
    export.add_argument("--json", action="store_true", help="输出 JSON")

    serve = sub.add_parser("serve", help="启动本地 HTTP JSON 服务")
    _add_data_option(serve)
    serve.add_argument("--host", default="127.0.0.1", help="监听地址（默认仅本机）")
    serve.add_argument("--port", type=int, default=8765, help="监听端口（默认 8765）")
    serve.add_argument("--quiet", action="store_true", help="不打印启动横幅")
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    """CLI 入口；返回进程退出码（0 成功，1 可预期错误，2 参数错误）。"""
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    args_list = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    args = parser.parse_args(args_list)

    if args.version:
        print(f"metro_api {__version__} · 城市交通路径导航系统可调用接口")
        return 0
    if not args.command:
        parser.print_help()
        return 0

    data_path = getattr(args, "sub_data", None) or args.data
    try:
        nav = connect(data_path)
    except MetroAPIError as exc:
        if getattr(args, "json", False):
            _print_json(exc.to_dict())
        else:
            print(f"错误[{exc.code}]：{exc.message}", file=sys.stderr)
        return 1

    handlers = {
        "info": _cmd_info,
        "stations": _cmd_stations,
        "lines": _cmd_lines,
        "route": _cmd_route,
        "compare": _cmd_compare,
        "export": _cmd_export,
        "serve": _cmd_serve,
    }
    try:
        return handlers[args.command](nav, args)
    except MetroAPIError as exc:
        if getattr(args, "json", False):
            _print_json(exc.to_dict())
        else:
            print(f"错误[{exc.code}]：{exc.message}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\n已停止。", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
