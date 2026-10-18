"""本地 HTTP JSON 服务：把 :mod:`metro_api` 的接口以 REST 形式暴露。

为什么用标准库
--------------
课程项目要求零第三方依赖；``http.server`` 的 ``ThreadingHTTPServer`` 足够
支撑本地/局域网调用（前端 fetch、requests、curl 都能用），也方便同学在
答辩现场用浏览器直接看结果。

启动::

    python tools/serve_api.py                      # 127.0.0.1:8765
    python tools/serve_api.py --port 9000 --quiet
    python metro_api.py serve --port 8765          # 等价入口

接口一览::

    GET  /                      服务信息（端点表）
    GET  /api/health            健康检查
    GET  /api/info              路网规模与参数
    GET  /api/stations          站点列表（?line=L1&query=苹果）
    GET  /api/lines             线路列表
    GET  /api/station?q=苹果园   单个站点详情
    GET  /api/route?start=..&end=..&algorithm=Dijkstra
    POST /api/route             JSON body: {"start": .., "end": .., "algorithm": ..}
    GET  /api/compare?start=..&end=..   三种算法对比
    OPTIONS *                   CORS 预检

所有响应都是 UTF-8 JSON；可预期错误返回 ``{"ok": false, "error": {...}}``，
HTTP 状态码见 :mod:`metro_api` 顶部错误码表。
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from metro_api import (  # noqa: E402
    InvalidRequest,
    MetroAPIError,
    MetroNavigator,
    __version__,
    connect,
    error_payload,
    http_status_for,
)

#: 请求体上限（1 MB）：本地服务不需要传大文件，防止误发大请求。
MAX_BODY_BYTES = 1_000_000

#: 端点表：既用于 ``GET /`` 的自描述，也用于启动横幅。
ENDPOINTS: list[tuple[str, str, str]] = [
    ("GET", "/", "服务信息"),
    ("GET", "/api/health", "健康检查"),
    ("GET", "/api/info", "路网规模与参数"),
    ("GET", "/api/stations", "站点列表（?line=&query=）"),
    ("GET", "/api/lines", "线路列表"),
    ("GET", "/api/station", "站点详情（?q=站名或ID）"),
    ("GET", "/api/route", "寻路（?start=&end=&algorithm=）"),
    ("POST", "/api/route", "寻路（JSON body）"),
    ("GET", "/api/compare", "三算法对比（?start=&end=）"),
]


def _json_bytes(payload: object) -> bytes:
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


class ApiHandler(BaseHTTPRequestHandler):
    """每个请求一个实例；共享数据放在 ``self.server.nav``（只读）。"""

    server_version = f"MetroAPI/{__version__}"
    protocol_version = "HTTP/1.1"

    # ------------------------------------------------------------------
    # 基础设施
    # ------------------------------------------------------------------
    def log_message(self, fmt: str, *args: object) -> None:  # noqa: A003
        if getattr(self.server, "quiet", False):
            return
        sys.stderr.write(f"[{self.log_date_time_string()}] {fmt % args}\n")

    def _cors_headers(self) -> dict[str, str]:
        return {
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type",
            "X-Content-Type-Options": "nosniff",
        }

    def _send(self, status: int, payload: object, headers: dict[str, str] | None = None) -> None:
        body = _json_bytes(payload)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-API-Version", __version__)
        for key, value in self._cors_headers().items():
            self.send_header(key, value)
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _read_json_body(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError as exc:
            raise InvalidRequest("Content-Length 不是合法数字") from exc
        if length <= 0:
            raise InvalidRequest("空请求体：POST /api/route 需要 JSON")
        if length > MAX_BODY_BYTES:
            raise InvalidRequest(f"请求体过大（>{MAX_BODY_BYTES} 字节）")
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except UnicodeDecodeError as exc:
            raise InvalidRequest("请求体不是合法 UTF-8") from exc
        except json.JSONDecodeError as exc:
            raise InvalidRequest(f"JSON 解析失败：{exc.msg}（第 {exc.lineno} 行）") from exc
        if not isinstance(payload, dict):
            raise InvalidRequest("请求体必须是 JSON 对象，例如 {\"start\": ..., \"end\": ...}")
        return payload

    def _dispatch(self, handler) -> None:  # noqa: ANN001
        try:
            handler()
        except MetroAPIError as exc:
            self._send(http_status_for(exc), exc.to_dict())
        except Exception as exc:  # pragma: no cover - 兜底，避免服务被一个请求打挂
            traceback.print_exc()
            self._send(500, error_payload(exc))

    # ------------------------------------------------------------------
    # HTTP 方法
    # ------------------------------------------------------------------
    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        for key, value in self._cors_headers().items():
            self.send_header(key, value)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_HEAD(self) -> None:  # noqa: N802
        self.do_GET()

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        query = {key: values[-1] for key, values in parse_qs(parsed.query).items()}
        self._dispatch(lambda: self._handle_get(parsed.path, query))

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        self._dispatch(lambda: self._handle_post(parsed.path, parsed.query))

    # ------------------------------------------------------------------
    # 路由
    # ------------------------------------------------------------------
    @property
    def nav(self) -> MetroNavigator:
        return self.server.nav  # type: ignore[attr-defined]

    def _handle_get(self, path: str, query: dict[str, str]) -> None:
        nav = self.nav
        if path == "/":
            self._send(
                200,
                {
                    "ok": True,
                    "name": "城市交通路径导航系统 · HTTP API",
                    "version": __version__,
                    "city": nav.city,
                    "endpoints": [
                        {"method": method, "path": route, "description": desc}
                        for method, route, desc in ENDPOINTS
                    ],
                    "docs": "docs/API接口说明.md",
                },
            )
        elif path == "/api/health":
            self._send(200, {"ok": True, "status": "up", "version": __version__})
        elif path == "/api/info":
            self._send(200, nav.info())
        elif path == "/api/stations":
            rows = nav.stations(line_id=query.get("line"), query=query.get("query"))
            self._send(200, {"ok": True, "count": len(rows), "stations": rows})
        elif path == "/api/lines":
            rows = nav.lines()
            self._send(200, {"ok": True, "count": len(rows), "lines": rows})
        elif path == "/api/station":
            key = query.get("q") or query.get("id") or query.get("name")
            self._send(200, {"ok": True, "station": nav.station(key)})
        elif path == "/api/route":
            self._send(
                200,
                nav.route(
                    query.get("start"),
                    query.get("end"),
                    algorithm=query.get("algorithm") or "Dijkstra",
                ),
            )
        elif path == "/api/compare":
            self._send(200, nav.compare(query.get("start"), query.get("end")))
        else:
            self._send(
                404,
                {
                    "ok": False,
                    "error": {
                        "code": "NOT_FOUND",
                        "message": f"没有这个端点：{path}",
                        "hint": "GET / 可查看全部端点",
                    },
                },
            )

    def _handle_post(self, path: str, raw_query: str) -> None:
        if path != "/api/route":
            self._send(
                404,
                {
                    "ok": False,
                    "error": {
                        "code": "NOT_FOUND",
                        "message": f"没有这个端点：{path}",
                        "hint": "POST 目前只支持 /api/route",
                    },
                },
            )
            return
        # 允许把参数放在 query 里作为兜底，JSON body 优先
        query = {key: values[-1] for key, values in parse_qs(raw_query).items()}
        body = self._read_json_body()
        start = body.get("start", query.get("start"))
        end = body.get("end", query.get("end"))
        algorithm = body.get("algorithm", query.get("algorithm") or "Dijkstra")
        self._send(200, self.nav.route(start, end, algorithm=algorithm))


class _ThreadingServer(ThreadingHTTPServer):
    """带 ``nav`` 与 ``quiet`` 属性的线程化服务器；便于测试里注入。"""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, handler_class, *, nav: MetroNavigator, quiet: bool = False):  # noqa: ANN001
        super().__init__(address, handler_class)
        self.nav = nav
        self.quiet = quiet


def create_server(
    nav: MetroNavigator,
    host: str = "127.0.0.1",
    port: int = 8765,
    *,
    quiet: bool = False,
) -> _ThreadingServer:
    """创建（但不启动）服务；``port=0`` 时由系统分配空闲端口，适合测试。"""
    return _ThreadingServer((host, port), ApiHandler, nav=nav, quiet=quiet)


def serve(
    nav: MetroNavigator,
    host: str = "127.0.0.1",
    port: int = 8765,
    *,
    quiet: bool = False,
) -> int:
    """启动 HTTP 服务并阻塞到 Ctrl+C。返回进程退出码。"""
    server = create_server(nav, host, port, quiet=quiet)
    actual_host, actual_port = server.server_address[:2]
    if not quiet:
        print("城市交通路径导航系统 · HTTP API")
        print(f"  监听  http://{actual_host}:{actual_port}")
        print(f"  路网  {nav.city}（{nav.data_path}）")
        print("  端点：")
        for method, route, desc in ENDPOINTS:
            print(f"    {method:<6} {route:<46} {desc}")
        print("\n  示例：")
        print(f'    curl "http://127.0.0.1:{actual_port}/api/route?start=S001&end=S061"')
        print(f'    curl "http://127.0.0.1:{actual_port}/api/compare?start=苹果园&end=天通苑北"')
        print("\n  Ctrl+C 停止服务。\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止 HTTP 服务。", file=sys.stderr)
    finally:
        server.shutdown()
        server.server_close()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="serve_api.py",
        description="城市交通路径导航系统 · 本地 HTTP JSON 服务（零第三方依赖）",
    )
    parser.add_argument("--data", default=None,
                        help="路网数据（.json/.txt），默认 data/beijing_metro.json")
    parser.add_argument("--host", default="127.0.0.1",
                        help="监听地址（默认 127.0.0.1，仅本机可访问）")
    parser.add_argument("--port", type=int, default=8765, help="监听端口（默认 8765）")
    parser.add_argument("--quiet", action="store_true", help="不打印启动横幅与访问日志")
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    args = build_parser().parse_args(argv)
    try:
        nav = connect(args.data)
    except MetroAPIError as exc:
        print(f"错误[{exc.code}]：{exc.message}", file=sys.stderr)
        return 1
    return serve(nav, host=args.host, port=args.port, quiet=args.quiet)


if __name__ == "__main__":
    sys.exit(main())
