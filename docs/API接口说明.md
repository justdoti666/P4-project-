# 可调用接口说明（Python SDK · CLI · HTTP）

> 对应代码：[`metro_api.py`](../metro_api.py)、[`tools/serve_api.py`](../tools/serve_api.py)、
> 测试 [`tests/test_api.py`](../tests/test_api.py)。
> 这一层把 P1/P2 的 `core`（数据 + 三种算法）包装成稳定、JSON 友好、可被其他程序调用的接口，
> **不依赖 Tkinter、不打开窗口、零第三方依赖**。

## 0. 设计约定（先看这节，避免误用）

| 约定 | 说明 |
| --- | --- |
| 分层 | `metro_api → core`（单向）；`status`/文档层不反向依赖 `ui`，所以可以在服务器/脚本里 import |
| 无 GUI | 不 import `tkinter`；可在无显示环境、CI、服务器上跑 |
| 零依赖 | 只用标准库；可选 `Pillow` 只影响画布导出，与本接口无关 |
| JSON 友好 | 返回值全是 `dict/list/str/int/float/bool`，可直接 `json.dumps`，浮点统一保留 6 位小数 |
| 站名/ID 通用 | 先按站 ID 精确匹配，再按站名精确匹配；站名唯一由数据层校验保证 |
| 线程安全 | `MetroNavigator` 建好后只读；HTTP 服务用「一个实例 + 多线程」共享，`solve` 状态全在局部变量 |
| 只读 core | 本接口不修改 `core/` 与数据文件，算法口径与界面完全一致（同一份 `core.solve`） |

## 1. 快速开始

### 1.1 Python（推荐）

```python
from metro_api import connect

nav = connect()                                        # 默认 data/beijing_metro.json
print(nav.info())                                      # 134 站 / 7 线 / 154 站台节点…
print(nav.route("苹果园", "天通苑北")["summary"])        # 站名或站 ID 都行
print(nav.route("S001", "S061", algorithm="A*")["summary"])
print(nav.compare("慈寿寺", "崇文门")["highlights"])     # 三算法差异摘要

# 自己指定数据文件（.json / .txt 都支持）
demo = connect("data/demo_city.json")
```

### 1.2 命令行（给脚本/终端用）

```powershell
python metro_api.py info
python metro_api.py route --start 苹果园 --end 天通苑北
python metro_api.py route --start S001 --end S061 --algorithm A* --json
python metro_api.py compare --start S001 --end S061
python metro_api.py stations --line L1 --query 门
python metro_api.py export --output _smoke/network.json
python metro_api.py serve --port 8765
```

### 1.3 HTTP（跨语言调用）

```powershell
python tools/serve_api.py --port 8765       # 或 python metro_api.py serve --port 8765
```

```powershell
# PowerShell
Invoke-RestMethod "http://127.0.0.1:8765/api/route?start=S001&end=S061"

# curl（中文站名记得 URL 编码）
curl "http://127.0.0.1:8765/api/route?start=%E8%8B%B9%E6%9E%9C%E5%9B%AD&end=%E5%A4%A9%E9%80%9A%E8%8B%91%E5%8C%97"
```

```javascript
// 浏览器控制台 / 前端
const r = await fetch("http://127.0.0.1:8765/api/route?start=S001&end=S061");
const data = await r.json();
console.log(data.summary.time_min, data.summary.transfers);
```

## 2. Python API 参考

### 2.1 入口函数

| 函数 | 说明 |
| --- | --- |
| `connect(data_path=None) -> MetroNavigator` | 加载路网并返回导航会话；最常用入口 |
| `quick_route(start, end, *, algorithm="Dijkstra", data_path=None) -> dict` | 一次性加载 + 求路径（脚本里只查一两条时方便） |
| `resolve_algorithm(name) -> str` | 算法别名解析（`astar`/`bfs`/`最少换乘` → 正式名） |

### 2.2 `MetroNavigator` 方法

| 方法 | 返回 | 说明 |
| --- | --- | --- |
| `info()` | dict | 路网规模、参数、可用算法 |
| `stations(*, line_id=None, query=None)` | list[dict] | 站点列表；可按线路过滤、按站名/ID 模糊搜索 |
| `lines()` | list[dict] | 线路列表（颜色、是否环线、站序） |
| `station(key)` | dict | 单站详情（`is_transfer` 标记换乘站） |
| `resolve_station(key)` | str | 站 ID 或站名 → 站 ID；找不到抛 `StationNotFound` |
| `route(start, end, *, algorithm="Dijkstra")` | dict | 求路径；**无路径不是异常**，返回 `found=false` |
| `compare(start, end)` | dict | 三种算法同跑 + 差异摘要 |
| `export_network(path)` | str | 导出「规模 + 站点 + 线路」JSON，给前端/其他服务用 |
| `city` / `data_path` / `algorithms` | str / str / list | 只读属性 |

### 2.3 `route()` 返回结构

```json
{
  "ok": true,
  "algorithm": "Dijkstra",
  "found": true,
  "start": {"id": "S001", "name": "苹果园"},
  "end": {"id": "S061", "name": "天通苑北"},
  "summary": {
    "time_min": 79.575299,
    "distance_km": 33.235591,
    "transfers": 1,
    "expanded": 151,
    "station_count": 32,
    "elapsed_ms": 0.293,
    "wall_ms": 0.301
  },
  "stations": [{"id": "S001", "name": "苹果园", "line_ids": ["L1"]}],
  "legs": [
    {
      "kind": "ride",
      "from": {"id": "S001", "name": "苹果园"},
      "to": {"id": "S002", "name": "古城"},
      "line_id": "L1",
      "line_name": "1号线",
      "time_min": 2.314286,
      "distance_km": 1.0
    }
  ],
  "message": "搜索成功"
}
```

字段口径：

* `summary.time_min` = 乘车时间 + 换乘时间；`distance_km` 只累加乘车段；
* `expanded` 为扩展站台节点数（BFS 按线路口径，与 Dijkstra/A* 不同，不要横比，见报告 4.6）；
* `elapsed_ms` 由 P2 内部计时，`wall_ms` 为接口层整体计时，两者相差调度噪声；
* `legs[].kind` = `ride`（乘车）或 `transfer`（换乘）；每段首尾相接，可直接画路径。

### 2.4 `compare()` 额外返回 `highlights`

```json
{
  "dijkstra_astar_same_time": true,
  "astar_expanded_reduction_pct": 23.84106,
  "transfers_diff_bfs_vs_dijkstra": 0,
  "time_diff_bfs_vs_dijkstra_min": 0.0
}
```

`transfers_diff_bfs_vs_dijkstra < 0` 表示 BFS 少换乘（如慈寿寺→崇文门为 -1、多花约 2.6 分钟），
适合直接写进实验报告的对比分析。

## 3. CLI 参考

```
python metro_api.py <子命令> [选项]
python main.py --cli <子命令> [选项]        # 等价入口（转发给 metro_api）
```

| 子命令 | 用途 | 关键参数 |
| --- | --- | --- |
| `info` | 路网规模 | `--json` |
| `stations` | 站点列表/搜索 | `--line L1`、`--query 门`、`--json` |
| `lines` | 线路列表 | `--json` |
| `route` | 求路径 | `--start`、`--end`、`--algorithm`、`--json` |
| `compare` | 三算法对比 | `--start`、`--end`、`--json` |
| `export` | 导出路网 JSON | `--output` |
| `serve` | 起 HTTP 服务 | `--host`、`--port`、`--quiet` |

全局选项：`--data <文件>` 指定路网（各子命令也接受自己的 `--data`）；`--version`。

退出码：`0` 成功（`found=false` 也算请求成功）；`1` 可预期错误（站点/算法/数据）；
`2` 参数错误（argparse）；`130` Ctrl+C。

## 4. HTTP API 参考

启动后默认监听 **127.0.0.1:8765**（仅本机可访问；需要局域网给同学看时用 `--host 0.0.0.0`，
并注意这是无鉴权的本地服务）。

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/` | 服务信息 + 端点表 |
| GET | `/api/health` | 健康检查 |
| GET | `/api/info` | 路网规模与参数 |
| GET | `/api/stations?line=L1&query=门` | 站点列表/搜索 |
| GET | `/api/lines` | 线路列表 |
| GET | `/api/station?q=苹果园` | 单站详情（也接受 `?id=`/`?name=`） |
| GET | `/api/route?start=..&end=..&algorithm=Dijkstra` | 寻路 |
| POST | `/api/route` | 寻路，JSON body `{"start":..,"end":..,"algorithm":..}` |
| GET | `/api/compare?start=..&end=..` | 三算法对比 |
| OPTIONS | 任意 | CORS 预检（`Access-Control-Allow-Origin: *`） |

约定：

* 响应统一 `Content-Type: application/json; charset=utf-8`，并带 `X-API-Version`；
* 不支持的方法（PUT/DELETE/PATCH）返回 **405 JSON**（`METHOD_NOT_ALLOWED`，带 `Allow` 头），
  不会出现框架默认的 501 HTML；
* 错误统一 `{"ok": false, "error": {"code": ..., "message": ...}}`；
* 请求体上限 1 MB；POST 时 query 参数可作为兜底（JSON body 优先）；
* 该服务面向本地演示/联调，**没有鉴权与 TLS**，不要直接暴露到公网。

### 错误码

| `error.code` | HTTP | 触发场景 |
| --- | --- | --- |
| `INVALID_REQUEST` | 400 | 缺参数、参数为空、JSON 非法、请求体过大 |
| `ALGORITHM_NOT_FOUND` | 400 | 算法名不认识 |
| `STATION_NOT_FOUND` | 404 | 起点/终点查不到 |
| `DATA_ERROR` | 422 | 数据文件缺失或格式错误（启动时） |
| `NOT_FOUND` | 404 | 端点不存在 |
| `METHOD_NOT_ALLOWED` | 405 | 使用了不支持的 HTTP 方法（仅 GET/POST/OPTIONS） |
| `INTERNAL_ERROR` | 500 | 未预期异常（BUG，请附日志提 Issue） |

## 5. 错误与异常（Python 侧）

```python
from metro_api import (
    MetroAPIError,      # 基类
    InvalidRequest,     # 400
    DataError,          # 422
    StationNotFound,    # 404
    AlgorithmNotFound,  # 400
)

try:
    nav.route("不存在的站", "S061")
except StationNotFound as exc:
    print(exc.code, exc.http_status, exc.message)   # STATION_NOT_FOUND 404 …
except MetroAPIError as exc:
    print(exc.to_dict())                            # 直接给前端/日志用
```

`error_payload(exc)` / `http_status_for(exc)` 可把任意异常转成统一 JSON 与状态码（HTTP 服务内部也用它们）。

## 6. 测试与 CI

```powershell
python -m unittest discover -s tests -v     # 34 个用例，约 2.5 s
```

覆盖：数据加载与规模、站名/ID 解析、已知 OD 的期望值（79.575299 min / 151 扩展）、
算法别名、分段求和与首尾相接、同站/无路径边界、三算法对比与换乘取舍、
JSON 可序列化、错误码映射、HTTP 全部端点与 404/400/CORS、CLI 退出码。

CI（[`.github/workflows/selfcheck.yml`](../.github/workflows/selfcheck.yml)）在 10 项自检之外，
会把 `unittest` 作为独立一步执行；接口回归与渲染回归互不阻塞。

## 7. 性能与口径

* 134 站规模下单次寻路约 0.2–0.4 ms（算法内部计时），HTTP 整体含 json 约 1–3 ms；
* 每次请求都重新求解，不缓存结果（保证与界面/自检口径一致，避免缓存掩盖回归）；
* 浮点统一 6 位小数；`time_min`/`distance_km` 在 1e-6 内可复现；
* BFS 的 `expanded` 与 Dijkstra/A* 口径不同，对比时请用 `compare()` 的 `highlights`。

## 8. 常见问题（FAQ）

**Q1：中文站名在 curl 里报错/查不到？**
URL 里中文必须百分号编码（浏览器/`Invoke-RestMethod`/`requests` 会自动处理；curl 手写需要）。

**Q2：端口被占用怎么办？**
`--port 0` 让系统分配（会打印实际端口），或换一个端口；HTTP 服务默认只绑定 127.0.0.1。

**Q3：能不能不装 Pillow 用这个接口？**
可以。接口只依赖标准库；Pillow 只服务画布 PNG/GIF 导出。

**Q4：能不能直接嵌进 Django/Flask/FastAPI？**
可以，`MetroNavigator` 是普通 Python 类，进程内建一个实例全局复用即可；
本项目刻意不引入 Web 框架，是为了守住「零第三方依赖」的课程约束。

**Q5：接口会随算法/数据改动而变吗？**
`route()`/`compare()` 的字段与错误码视为 v1 稳定契约；新增字段属于兼容变更，
删除/改名会 bump `metro_api.__version__` 并在 PR 描述里注明。

**Q6：多线程安全吗？**
`MetroNavigator` 建好后只读，可被多线程共享；HTTP 服务用 `ThreadingHTTPServer`，
每个请求独立求解，无共享可变状态。

## 9. 版本与变更记录

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| 1.0.0 | 2026-10-18 | 首版：Python SDK（`connect`/`MetroNavigator`）、CLI 7 个子命令、HTTP 9 个端点、34 个 unittest、本说明 |

## 附：与任务书的对应关系

| 任务书要求 | 本接口的落实 |
| --- | --- |
| P4 渲染与工程化「给全班可复用的组件」 | `CanvasView` 之外再提供**无界面调用层**，P3 之外的脚本/前端也能用 |
| 质量门「新功能有新断言」 | `tests/test_api.py` 34 个用例；CI 独立执行 |
| 质量门「UI 改动附截图」 | 本接口不改 UI；HTTP 服务用浏览器/curl 可直接演示 |
| 零第三方依赖 | 仅标准库；`http.server` 提供 REST |
