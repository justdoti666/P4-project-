"""可调用接口的自动化测试（Python SDK / CLI / HTTP）。

运行::

    python -m unittest discover -s tests -v

测试原则
--------
* 只用标准库 ``unittest``，不引入 pytest，保证和课程「零第三方依赖」一致；
* 期望值尽量写死（如 S001→S061 = 79.575299 min / 151 扩展），
  这样接口层一旦把 core 的口径包装错就会立刻变红；
* HTTP 测试用 ``port=0`` 让系统分配端口，测试结束关服务，不污染本机端口。
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for path in (str(ROOT), str(ROOT / "tools")):
    if path not in sys.path:
        sys.path.insert(0, path)

import metro_api  # noqa: E402
import serve_api  # noqa: E402
from metro_api import (  # noqa: E402
    AlgorithmNotFound,
    DataError,
    InvalidRequest,
    MetroNavigator,
    StationNotFound,
    connect,
    error_payload,
    http_status_for,
    quick_route,
)

BEIJING = ROOT / "data" / "beijing_metro.json"
DISCONNECTED = ROOT / "data" / "disconnected_4.json"

#: 基准数据（来自 docs/bench.csv，接口层必须原样透出）
PAIR = ("S001", "S061")            # 苹果园 → 天通苑北
PAIR_NAME = ("苹果园", "天通苑北")
EXPECTED_TIME = 79.575299
EXPECTED_DISTANCE = 33.235591
EXPECTED_EXPANDED = 151
EXPECTED_STATIONS = 32


class NavigatorTests(unittest.TestCase):
    """Python SDK：加载、查询、寻路、对比、导出。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.nav = MetroNavigator(BEIJING)

    def test_info_matches_dataset(self) -> None:
        info = self.nav.info()
        self.assertTrue(info["ok"])
        self.assertEqual(info["station_count"], 134)
        self.assertEqual(info["line_count"], 7)
        self.assertEqual(info["platform_count"], 154)
        self.assertEqual(info["transfer_station_count"], 20)
        self.assertEqual(info["loop_line_count"], 2)
        self.assertEqual(info["algorithms"], ["Dijkstra", "A*", "BFS"])
        self.assertAlmostEqual(info["params"]["transfer_minutes"], 4.0)

    def test_connect_and_quick_route(self) -> None:
        nav = connect()  # 默认数据
        self.assertIn("北京", nav.city)
        payload = quick_route(*PAIR)
        self.assertTrue(payload["found"])

    def test_resolve_station_by_id_and_name(self) -> None:
        self.assertEqual(self.nav.resolve_station("S001"), "S001")
        self.assertEqual(self.nav.resolve_station("苹果园"), "S001")
        station = self.nav.station("苹果园")
        self.assertEqual(station["id"], "S001")
        self.assertEqual(station["name"], "苹果园")

    def test_unknown_station_raises(self) -> None:
        with self.assertRaises(StationNotFound):
            self.nav.resolve_station("不存在站")
        with self.assertRaises(StationNotFound):
            self.nav.route("S001", "不存在站")

    def test_stations_and_lines(self) -> None:
        self.assertEqual(len(self.nav.stations()), 134)
        l1_stations = self.nav.stations(line_id="L1")
        self.assertEqual(len(l1_stations), 23)
        found = self.nav.stations(query="苹果")
        self.assertEqual([row["name"] for row in found], ["苹果园"])
        lines = self.nav.lines()
        self.assertEqual(len(lines), 7)
        self.assertEqual(lines[0]["id"], "L1")

    def test_transfer_station_flag(self) -> None:
        transfers = [
            row for row in self.nav.stations() if len(row["line_ids"]) > 1
        ]
        self.assertEqual(len(transfers), 20)
        self.assertTrue(self.nav.station(transfers[0]["id"])["is_transfer"])

    def test_route_known_pair(self) -> None:
        payload = self.nav.route(*PAIR)
        self.assertTrue(payload["ok"])
        self.assertTrue(payload["found"])
        self.assertEqual(payload["algorithm"], "Dijkstra")
        summary = payload["summary"]
        self.assertAlmostEqual(summary["time_min"], EXPECTED_TIME, places=5)
        self.assertAlmostEqual(summary["distance_km"], EXPECTED_DISTANCE, places=5)
        self.assertEqual(summary["transfers"], 1)
        self.assertEqual(summary["expanded"], EXPECTED_EXPANDED)
        self.assertEqual(summary["station_count"], EXPECTED_STATIONS)
        self.assertEqual(len(payload["stations"]), EXPECTED_STATIONS)
        self.assertGreater(summary["wall_ms"], 0.0)

    def test_route_accepts_station_names(self) -> None:
        payload = self.nav.route(*PAIR_NAME, algorithm="A*")
        self.assertTrue(payload["found"])
        self.assertEqual(payload["algorithm"], "A*")
        self.assertEqual(payload["start"]["name"], "苹果园")
        self.assertEqual(payload["end"]["name"], "天通苑北")

    def test_route_legs_sum_to_summary(self) -> None:
        payload = self.nav.route(*PAIR)
        legs = payload["legs"]
        ride_time = sum(leg["time_min"] for leg in legs if leg["kind"] == "ride")
        transfer_time = sum(leg["time_min"] for leg in legs if leg["kind"] == "transfer")
        ride_distance = sum(leg["distance_km"] for leg in legs if leg["kind"] == "ride")
        self.assertAlmostEqual(ride_time + transfer_time, payload["summary"]["time_min"], places=4)
        self.assertAlmostEqual(ride_distance, payload["summary"]["distance_km"], places=4)
        transfers = [leg for leg in legs if leg["kind"] == "transfer"]
        self.assertEqual(len(transfers), payload["summary"]["transfers"])
        # 每一段的起终点必须首尾相接
        for previous, current in zip(legs, legs[1:]):
            self.assertEqual(previous["to"]["id"], current["from"]["id"])

    def test_algorithm_aliases(self) -> None:
        cases = {
            "dijkstra": "Dijkstra",
            "Dijkstra": "Dijkstra",
            "最快": "Dijkstra",
            "a*": "A*",
            "astar": "A*",
            "a星": "A*",
            "bfs": "BFS",
            "最少换乘": "BFS",
        }
        for alias, expected in cases.items():
            with self.subTest(alias=alias):
                payload = self.nav.route(*PAIR, algorithm=alias)
                self.assertEqual(payload["algorithm"], expected)

    def test_unknown_algorithm_raises(self) -> None:
        with self.assertRaises(AlgorithmNotFound):
            self.nav.route(*PAIR, algorithm="floyd")
        with self.assertRaises(InvalidRequest):
            self.nav.route(*PAIR, algorithm="")

    def test_route_weight_distance(self) -> None:
        """M1：distance 权重求最短里程，time 权重求最快，两者允许不同。"""
        fastest = self.nav.route(*PAIR)
        shortest = self.nav.route(*PAIR, weight="distance")
        self.assertEqual(fastest["weight"], "time")
        self.assertEqual(shortest["weight"], "distance")
        self.assertLessEqual(
            shortest["summary"]["distance_km"], fastest["summary"]["distance_km"]
        )
        self.assertGreaterEqual(
            shortest["summary"]["time_min"], fastest["summary"]["time_min"]
        )
        alias = self.nav.route(*PAIR, weight="最短距离")
        self.assertEqual(alias["weight"], "distance")
        # 换乘边距离为 0：距离权重下里程不会比时间最优路径更长
        self.assertTrue(shortest["found"])

    def test_invalid_weight_raises(self) -> None:
        with self.assertRaises(InvalidRequest):
            self.nav.route(*PAIR, weight="toll")

    def test_compare_weight_distance(self) -> None:
        payload = self.nav.compare(*PAIR, weight="distance")
        self.assertEqual(payload["weight"], "distance")
        for name in ("Dijkstra", "A*", "BFS"):
            self.assertEqual(payload["algorithms"][name]["weight"], "distance")
        d = payload["algorithms"]["Dijkstra"]["summary"]["distance_km"]
        a = payload["algorithms"]["A*"]["summary"]["distance_km"]
        self.assertAlmostEqual(d, a, places=6)

    def test_same_station_route(self) -> None:
        payload = self.nav.route("S001", "S001")
        self.assertTrue(payload["found"])
        self.assertAlmostEqual(payload["summary"]["time_min"], 0.0)
        self.assertEqual(payload["summary"]["transfers"], 0)
        self.assertEqual(payload["summary"]["station_count"], 1)

    def test_no_path_returns_found_false(self) -> None:
        nav = MetroNavigator(DISCONNECTED)
        payload = nav.route("D1", "D4")
        self.assertTrue(payload["ok"])
        self.assertFalse(payload["found"])
        self.assertEqual(payload["stations"], [])
        self.assertEqual(payload["legs"], [])

    def test_compare_highlights(self) -> None:
        payload = self.nav.compare(*PAIR)
        self.assertEqual(set(payload["algorithms"]), {"Dijkstra", "A*", "BFS"})
        highlights = payload["highlights"]
        self.assertTrue(highlights["dijkstra_astar_same_time"])
        expected_reduction = (1 - 115 / 151) * 100.0
        self.assertAlmostEqual(
            highlights["astar_expanded_reduction_pct"], expected_reduction, places=2
        )
        self.assertEqual(highlights["transfers_diff_bfs_vs_dijkstra"], 0)

    def test_compare_transfer_tradeoff(self) -> None:
        """慈寿寺→崇文门：BFS 少 1 次换乘，但多花约 2.6 分钟。"""
        payload = self.nav.compare("慈寿寺", "崇文门")
        dijkstra = payload["algorithms"]["Dijkstra"]
        bfs = payload["algorithms"]["BFS"]
        self.assertEqual(dijkstra["summary"]["transfers"], 2)
        self.assertEqual(bfs["summary"]["transfers"], 1)
        self.assertAlmostEqual(
            bfs["summary"]["time_min"] - dijkstra["summary"]["time_min"], 2.646, places=2
        )
        self.assertEqual(payload["highlights"]["transfers_diff_bfs_vs_dijkstra"], -1)

    def test_network_export_is_json(self) -> None:
        # 写到仓库的 _smoke/（已被 .gitignore 忽略），避免沙箱对系统临时目录的限制
        smoke_dir = ROOT / "_smoke"
        smoke_dir.mkdir(exist_ok=True)
        target = smoke_dir / "api_network_test.json"
        try:
            saved = self.nav.export_network(target)
            payload = json.loads(Path(saved).read_text(encoding="utf-8"))
            self.assertTrue(payload["ok"])
            self.assertEqual(len(payload["stations"]), 134)
            self.assertEqual(len(payload["lines"]), 7)
        finally:
            target.unlink(missing_ok=True)

    def test_result_is_json_serializable(self) -> None:
        text = json.dumps(self.nav.route(*PAIR), ensure_ascii=False)
        self.assertIn("苹果园", text)
        json.dumps(self.nav.compare(*PAIR), ensure_ascii=False)

    def test_error_mapping(self) -> None:
        exc = StationNotFound("找不到站点")
        self.assertEqual(exc.code, "STATION_NOT_FOUND")
        self.assertEqual(http_status_for(exc), 404)
        payload = error_payload(exc)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "STATION_NOT_FOUND")
        self.assertEqual(error_payload(RuntimeError("boom"))["error"]["code"], "INTERNAL_ERROR")
        self.assertEqual(http_status_for(RuntimeError("boom")), 500)

    def test_missing_data_file(self) -> None:
        with self.assertRaises(DataError):
            MetroNavigator(ROOT / "data" / "no_such_file.json")


class HttpApiTests(unittest.TestCase):
    """HTTP JSON 服务：启动、各端点、错误码、CORS。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.nav = MetroNavigator(BEIJING)
        cls.server = serve_api.create_server(cls.nav, "127.0.0.1", 0, quiet=True)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(
            target=cls.server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True
        )
        cls.thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    # ------------------------------------------------------------------
    def request(
        self,
        path: str,
        *,
        method: str = "GET",
        payload: dict | None = None,
    ) -> tuple[int, dict, dict]:
        url = f"http://127.0.0.1:{self.port}{path}"
        data = None
        headers = {}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                raw = response.read().decode("utf-8")
                return (
                    response.status,
                    json.loads(raw) if raw else {},
                    dict(response.headers),
                )
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8")
            return (
                exc.code,
                json.loads(raw) if raw else {},
                dict(exc.headers),
            )

    def test_health(self) -> None:
        status, payload, headers = self.request("/api/health")
        self.assertEqual(status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["status"], "up")
        self.assertIn("application/json", headers["Content-Type"])

    def test_root_lists_endpoints(self) -> None:
        status, payload, _ = self.request("/")
        self.assertEqual(status, 200)
        paths = {row["path"] for row in payload["endpoints"]}
        self.assertIn("/api/route", paths)
        self.assertIn("/api/compare", paths)

    def test_route_by_id(self) -> None:
        status, payload, _ = self.request(f"/api/route?start={PAIR[0]}&end={PAIR[1]}")
        self.assertEqual(status, 200)
        self.assertTrue(payload["found"])
        self.assertAlmostEqual(
            payload["summary"]["time_min"], EXPECTED_TIME, places=5
        )

    def test_route_by_chinese_name(self) -> None:
        start = urllib.parse.quote(PAIR_NAME[0])
        end = urllib.parse.quote(PAIR_NAME[1])
        status, payload, _ = self.request(f"/api/route?start={start}&end={end}")
        self.assertEqual(status, 200)
        self.assertTrue(payload["found"])

    def test_post_route(self) -> None:
        status, payload, _ = self.request(
            "/api/route",
            method="POST",
            payload={"start": "S001", "end": "S061", "algorithm": "bfs"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["algorithm"], "BFS")

    def test_compare_endpoint(self) -> None:
        status, payload, _ = self.request(
            f"/api/compare?start={PAIR[0]}&end={PAIR[1]}"
        )
        self.assertEqual(status, 200)
        self.assertEqual(set(payload["algorithms"]), {"Dijkstra", "A*", "BFS"})

    def test_route_weight_distance(self) -> None:
        status, payload, _ = self.request(
            f"/api/route?start={PAIR[0]}&end={PAIR[1]}&weight=distance"
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["weight"], "distance")
        self.assertLessEqual(payload["summary"]["distance_km"], EXPECTED_DISTANCE)

    def test_post_route_weight(self) -> None:
        status, payload, _ = self.request(
            "/api/route",
            method="POST",
            payload={"start": "S001", "end": "S061", "weight": "distance"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["weight"], "distance")

    def test_invalid_weight_is_400(self) -> None:
        status, payload, _ = self.request(
            f"/api/route?start={PAIR[0]}&end={PAIR[1]}&weight=toll"
        )
        self.assertEqual(status, 400)
        self.assertEqual(payload["error"]["code"], "INVALID_REQUEST")

    def test_unknown_station_is_404(self) -> None:
        status, payload, _ = self.request("/api/route?start=NOPE&end=S061")
        self.assertEqual(status, 404)
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["error"]["code"], "STATION_NOT_FOUND")

    def test_unknown_algorithm_is_400(self) -> None:
        status, payload, _ = self.request(
            f"/api/route?start={PAIR[0]}&end={PAIR[1]}&algorithm=floyd"
        )
        self.assertEqual(status, 400)
        self.assertEqual(payload["error"]["code"], "ALGORITHM_NOT_FOUND")

    def test_unknown_endpoint_is_404(self) -> None:
        status, payload, _ = self.request("/api/nope")
        self.assertEqual(status, 404)
        self.assertEqual(payload["error"]["code"], "NOT_FOUND")

    def test_stations_filter_and_search(self) -> None:
        status, payload, _ = self.request("/api/stations?line=L1")
        self.assertEqual(status, 200)
        self.assertEqual(payload["count"], 23)
        status, payload, _ = self.request("/api/station?q=" + urllib.parse.quote("苹果园"))
        self.assertEqual(status, 200)
        self.assertEqual(payload["station"]["id"], "S001")

    def test_options_and_cors(self) -> None:
        status, _, headers = self.request("/api/health", method="OPTIONS")
        self.assertEqual(status, 204)
        self.assertEqual(headers["Access-Control-Allow-Origin"], "*")

    def test_unsupported_method_is_405_json(self) -> None:
        """PUT/DELETE 等不支持的方法也要返回统一 JSON，而不是默认 501 HTML。"""
        status, payload, headers = self.request("/api/route", method="PUT")
        self.assertEqual(status, 405)
        self.assertEqual(payload["error"]["code"], "METHOD_NOT_ALLOWED")
        self.assertEqual(headers["Allow"], "GET, POST, OPTIONS")


class CliTests(unittest.TestCase):
    """命令行：route / info / 错误退出码。"""

    def run_cli(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(ROOT / "metro_api.py"), *args],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=60,
        )

    def test_route_json(self) -> None:
        proc = self.run_cli("route", "--start", "S001", "--end", "S061", "--json")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertTrue(payload["found"])
        self.assertAlmostEqual(payload["summary"]["time_min"], EXPECTED_TIME, places=5)

    def test_route_weight_distance_json(self) -> None:
        proc = self.run_cli(
            "route", "--start", "S001", "--end", "S061",
            "--weight", "distance", "--json",
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        payload = json.loads(proc.stdout)
        self.assertEqual(payload["weight"], "distance")
        self.assertLessEqual(payload["summary"]["distance_km"], EXPECTED_DISTANCE)

    def test_info_json(self) -> None:
        proc = self.run_cli("info", "--json")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["station_count"], 134)

    def test_unknown_station_exit_code(self) -> None:
        proc = self.run_cli("route", "--start", "NOPE", "--end", "S061")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("STATION_NOT_FOUND", proc.stderr)

    def test_version(self) -> None:
        proc = self.run_cli("--version")
        self.assertEqual(proc.returncode, 0)
        self.assertIn("metro_api", proc.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
