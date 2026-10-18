# 城市交通路径导航系统 · P4 渲染与工程化

> 数据结构课程实践（选题 A）｜P4 交付包｜Python 3.10+ / Tkinter
>
> 本包负责：**`CanvasView` 画布组件、自检闸门、导出工具、对比实验与工程化说明**。
> P1 数据层、P2 算法层以只读依赖的形式放在 `core/`，P4 不修改它们。

---

## 0. 一分钟了解

```text
ui/canvas.py          P4 核心：坐标变换 / 缩放拖拽 / 路径高亮 / 动画 / 导出（约 2000 行，含大量中文注释）
ui/window.py          最小可运行窗口（P3 接口替身，只调用画布公开方法）
selfcheck.py          10 项自检矩阵 + “改坏实现会变红”的判别力演示
metro_api.py          可调用接口：Python SDK + CLI（无 Tk、零第三方依赖）
CONTRIBUTING.md       协作规范：分支命名 / 提交信息 / 文件所有权 / PR / 审查 / 合并
.github/              CI 自检闸门、PR/Issue 模板、CODEOWNERS
tools/export_canvas.py 画布导出 PNG/PS + 报告插图一键生成
tools/bench.py        5 对起终点 × 3 算法对比实验 + 图 4-4
tools/record_demo.py  自动驱动真实窗口，录制演示 GIF（有 ffmpeg 时可转 MP4）
tools/serve_api.py    本地 HTTP JSON 服务（REST，跨语言调用）
tools/prepare_github.py 仓库体检 / 待上传清单 / zip 打包 / PR 描述生成
tools/make_report.py  五章报告 docx 生成（终稿见 reports/）
data/                 134 站北京教学路网 + 10 站演示图 + 三站/不连通小图
docs/                 验收说明、GitHub 协作指南、API 说明、报告素材、演示 GIF、bench.csv、插图
reports/              五章实验报告终稿 docx + PDF（目录已更新，可直接提交）
tests/test_api.py     可调用接口回归（34 个 unittest 用例）
```

最短验证命令（在项目根目录执行）：

```powershell
python main.py --check                         # 10 项自检，退出码 0/1
python main.py --smoke _smoke/demo.ps          # 界面冒烟 + 导出画布
python -m unittest discover -s tests -v        # 可调用接口回归（34 用例）
python metro_api.py route --start 苹果园 --end 天通苑北 --json
python tools/export_canvas.py docs/figures/my_route.png --demo
python tools/record_demo.py                    # 自动录制演示 GIF
python tools/prepare_github.py --check         # 仓库体检：协作文件 / CI / 禁止入库项
```

本机实测（Windows 11、Python 3.12.14、Tk 8.6、Pillow 12.3.0）：

| 命令 | 结果 | 用时 |
| --- | --- | --- |
| `python main.py --check` | 10/10 通过，退出码 0 | 约 2.0 s |
| `python selfcheck.py --mutation-demo` | 3 种破坏全部被检查发现 | 约 2 s |
| `python main.py --smoke _smoke/smoke.ps` | 加载→搜索→动画→跳过→导出成功 | 约 3.2 s |
| `python tools/export_canvas.py ...` | 1400×900 PNG 导出成功 | 约 3.0 s |
| `python tools/record_demo.py` | 自动录制 23 帧、1200×789 演示 GIF | 约 20 s |
| `python -m unittest discover -s tests` | 接口 SDK/CLI/HTTP 共 34 个用例全部通过 | 约 2.5 s |
| `python metro_api.py route ... --json` | 返回 JSON：79.575 min / 换乘 1 次 | < 0.5 s |
| `python tools/serve_api.py --port 8765` | 9 个 HTTP 端点 + 404/400/CORS 冒烟通过 | 启动 < 1 s |
| 打开 GUI（含 134 站绘制） | 窗口出现并可交互 | 约 1.6 s |

---

## 1. 5 分钟跑起来（新人实测流程）

### 1.1 环境要求

| 项目 | 要求 | 说明 |
| --- | --- | --- |
| Python | 3.10 及以上 | 用到 `X | None`、`dataclass` 等语法 |
| Tkinter | Python 自带 | Windows 官方安装包默认带 Tcl/Tk；Linux 需 `python3-tk` |
| Pillow | 仅 PNG/JPG 导出和 GIF 录制需要 | `pip install pillow`；只导 PS 可以不装 |
| 中文字体 | 微软雅黑 / 黑体 | 没有时自动回退系统字体，不影响功能 |

```powershell
cd metro-p4
python --version                # 确认 3.10+
pip install pillow              # 只有导出 PNG 才需要
python main.py --check          # 第一道闸门：必须 10/10 绿
python main.py                  # 打开界面
```

> 如果系统没有 `python` 命令，用 `py -3 main.py`，或写本机解释器的绝对路径
> （Windows 常见如 `C:\Python312\python.exe`）。

### 1.2 第一次打开后做什么

1. 顶部选择起点、终点（或者直接点地图上的站点：第一次点设起点，第二次点设终点）；
2. 点「搜索」看静态路径；点「动画」看逐帧动画；
3. 动画中可以「暂停/继续」或「跳过」；
4. 滚轮缩放（0.5×–3×）、按住左键拖拽、双击复位；
5. 「导出图」保存 PNG 或 PS。

### 1.3 不打开界面也能验证

```powershell
python main.py --check --verbose               # 每项都打印细节
python main.py --smoke _smoke/a.png            # 自动选点、搜索、动画、导出
python tools/export_canvas.py _smoke/a.ps      # 只导出画布
python tools/bench.py                          # 生成 docs/bench.csv 和图 4-4
python tools/export_canvas.py --figure-pack    # 生成 docs/figures 整套插图
python tools/record_demo.py                    # 录演示 GIF（窗口会置顶约 15 秒）
```

---

## 2. 目录结构

```text
metro-p4/
├─ main.py                    # 入口：GUI / --check / --smoke / --cli
├─ selfcheck.py               # 10 项自检 + 判别力演示
├─ metro_api.py               # 可调用接口：Python SDK + CLI（无 Tk、零第三方依赖）
├─ CONTRIBUTING.md            # 协作规范：分支/提交/所有权/PR/审查/合并
├─ .github/                   # CI 自检、PR/Issue 模板、CODEOWNERS
├─ .gitattributes             # 换行统一（文本 LF、ps1/bat CRLF、二进制标记）
├─ .editorconfig              # 编辑器风格（UTF-8/LF、py 4 空格、yml/md 2 空格）
├─ ui/
│  ├─ canvas.py               # ★ P4 核心：CanvasView
│  ├─ window.py               # P3 接口替身（最小窗口）
│  └─ dpi.py                  # Windows 高 DPI 适配（截图不偏）
├─ core/                      # P1/P2 只读依赖（不修改）
│  ├─ graph.py                # 站点、线路、邻接表
│  ├─ loader.py               # .json/.txt 加载与校验
│  └─ algorithms.py           # Dijkstra / A* / BFS
├─ tools/
│  ├─ export_canvas.py        # 画布 → PNG/PS
│  ├─ bench.py                # 对比实验 + 图 4-4
│  ├─ record_demo.py          # 自动录演示 GIF / 可选 MP4
│  ├─ serve_api.py            # 本地 HTTP JSON 服务（REST，跨语言调用）
│  ├─ prepare_github.py       # 仓库体检 / manifest / zip 打包 / PR 描述
│  ├─ make_report.py          # 五章报告 docx 生成
│  ├─ check_report.py         # 报告统稿检查（退出码闸门）
│  ├─ make_report_assets.py   # 报告架构图等插图
│  └─ report_common.py        # 报告排版公共函数（被上面脚本复用）
├─ data/
│  ├─ beijing_metro.json/.txt # 134 站 / 7 条线（实测主数据）
│  ├─ demo_city.json          # 10 站 / 3 条线（站名避让自检）
│  ├─ tiny_3.json             # 3 站手工推导
│  └─ disconnected_4.json     # 两个不连通分量
├─ docs/
│  ├─ P4-验收与交接.md        # 5 条验收逐项证据
│  ├─ API接口说明.md          # Python SDK / CLI / HTTP 接口说明（JSON/错误码/FAQ）
│  ├─ GitHub协作与上传指南.md # 建仓 / 保护 main / 邀请组员 / PR / tag / FAQ
│  ├─ P4-报告章节草稿.md      # 4.5–4.7 + 第 5 章素材（终稿已并入 reports/）
│  ├─ P4-报告统稿模板与检查表.md # 五章合并、图表编号、术语统一
│  ├─ P4-报告终稿说明.md      # 报告如何重新生成 / 检查
│  ├─ P4-演示录屏脚本.md      # 2 分钟录屏分镜
│  ├─ P4-演示动画.gif         # 自动录制的真实界面演示
│  ├─ bench.csv / bench.md    # 对比实验原始数据
│  └─ figures/                # 报告插图（report/ 为报告专用插图）
├─ reports/
│  ├─ 城市交通路径导航系统_实验报告.docx  # 五章报告终稿（源文件，可用脚本重新生成）
│  └─ 城市交通路径导航系统_实验报告.pdf   # 终稿 PDF（34 页，目录已更新，可直接提交）
├─ tests/
│  └─ test_api.py             # 可调用接口回归（34 个用例：SDK/CLI/HTTP）
├─ requirements.txt           # Pillow（仅 PNG/GIF 需要）
├─ run.ps1 / run.bat          # 启动脚本
└─ _smoke/                    # 冒烟测试输出（可删，已被 .gitignore 忽略）
```

---

## 3. 数据格式

### 3.1 JSON（推荐）

```json
{
  "meta": {
    "city": "演示城市",
    "params": {
      "train_speed_kmh": 35.0,
      "dwell_minutes": 0.6,
      "transfer_minutes": 4.0
    }
  },
  "stations": [
    {"id": "S1", "name": "起点站", "x": 0.0, "y": 0.0}
  ],
  "lines": [
    {
      "id": "L1",
      "name": "1号线",
      "color": "#E11D48",
      "loop": false,
      "stations": ["S1", "S2", "S3"]
    }
  ]
}
```

* `x / y` 是示意坐标，单位 km，**y 轴朝上**（画布会自动翻转）；
* `loop: true` 表示环线，画布会把首尾连起来；
* 线路名包含「接驳」「支线」「摆渡」时自动画成虚线，也可以在代码里显式传 `feeder` 字段；
* 数据文件必须是 UTF-8（`utf-8-sig` 也兼容）。

### 3.2 TXT（便于手工编辑）

```text
CITY 演示城市
PARAM train_speed_kmh=35.0
STATION,S001,苹果园,-13.7,0.2
LINE,L1,1号线,#C0392B,0,S001,S002,S003
```

### 3.3 内置数据

| 文件 | 规模 | 用途 |
| --- | --- | --- |
| `data/beijing_metro.json` | 134 站 / 7 线 | 性能、密集站名、真实感演示 |
| `data/demo_city.json` | 10 站 / 3 线 | 站名避让自检、报告小图 |
| `data/tiny_3.json` | 3 站 / 1 线 | 表 4-2 手工推导 |
| `data/disconnected_4.json` | 4 站 / 2 线 | 「无路径」边界 |

---

## 4. 给 P3 的接口（D1 冻结）

```python
from ui.canvas import CanvasView

view = CanvasView(parent, graph)       # 放进任意 Frame，自动填充
view.bind_click(lambda sid: ...)       # 点击站点回调
view.show_path(result)                 # 静态高亮，返回统计字典
view.animate(result, speed_level=2)    # 1× / 2× / 4× 动画，返回同一份统计
view.reset()                           # 清路径 + 复位缩放/平移
view.export("out.png")                 # 导出 PNG / PS
```

| 方法 | 作用 | 返回值 |
| --- | --- | --- |
| `bind_click(callback)` | 注册点击站点回调 | `None` |
| `show_path(result)` | 静态高亮路径 | `{algorithm, found, distance_km, time_min, transfers, expanded, station_count}` |
| `animate(result, speed_level)` | 逐帧动画 | 同上（与 `show_path` 完全一致） |
| `toggle_pause()` | 暂停/继续 | 当前是否暂停 |
| `skip_animation()` | 跳过动画 | `None` |
| `reset()` | 清路径与视图 | `None` |
| `reset_view()` | 只复位缩放平移 | `None` |
| `export(path)` | 导出 `.png/.jpg/.ps` | 实际保存路径 |
| `get_metrics()` | 当前统计 | 字典（无路径时为空） |
| `hit_test(x, y)` | 屏幕坐标命中站点 | 站点 ID 或 `None` |
| `set_graph(graph)` | 换一份图 | `None` |
| `set_show_labels(bool)` | 显示/隐藏站名 | `None` |
| `on_animation_end(callback)` | 动画结束回调 | `None` |

### 坐标与绘制约定

```text
screen_x = width / 2  + (world_x - center_x) * scale + pan_x
screen_y = height / 2 - (world_y - center_y) * scale + pan_y
```

* 每次重绘都从世界坐标重新算屏幕坐标，所以窗口拉伸**不会变形**；
* x/y 用同一个 `scale`（等比），窗口拉宽只增加留白；
* `y` 前面的减号就是 y 翻转；
* 滚轮以光标为中心缩放，`zoom ∈ [0.5, 3.0]`；
* 窗口 `<Configure>` 做 120ms 防抖，避免初始 1×1 时算错；
* 拖动时只平移已画好的图元（`canvas.move`），不重排站名，所以 134 站也不卡。

### 画布不做业务

`ui/canvas.py` **没有** import `core`，也**没有** `open()` / `solve()`。
自检第 10 项用 AST 扫描源码验证这一点：P3 可以放心把它当纯组件，
换算法、换数据都不用改画布。

---

## 5. 自检闸门（P4-07）

```powershell
python main.py --check              # 10 项，退出码 0/1
python selfcheck.py --verbose       # 打印细节
python selfcheck.py --no-gui        # 无显示环境跳过第 10 项
python selfcheck.py --mutation-demo # 证明断言不是恒真
```

| # | 类别 | 检查内容 | 失败意味着 |
| --- | --- | --- | --- |
| 01 | 数据 | 北京 134 站/7 线、站名唯一、无孤立站 | 数据文件坏了 |
| 02 | 数据 | 10 站演示图、S3 换乘、接驳线存在 | 自检素材不完整 |
| 03 | 算法 | Dijkstra 路径端点/相邻性/分段求和独立重算 | 搜索或结果封装错了 |
| 04 | 算法 | A* 与 Dijkstra 同优且扩展节点更少 | 启发函数不可采纳 |
| 05 | 算法 | BFS 换乘次数 ≤ Dijkstra | 最少换乘逻辑错了 |
| 06 | 边界 | 起终点相同 → 0 分钟、1 站 | 边界处理崩溃 |
| 07 | 边界 | 不连通图/真实独立支线 → `found=False` | 无路径处理错了 |
| 08 | 性能 | 建图 + 5 对起终点 × 3 算法中位数 | 超过 200ms 阈值 |
| 09 | 界面 | 等比、y 翻转、缩放锚点、0.5–3×、平移复位 | 坐标数学错了 |
| 10 | 界面 | 10 站/北京站名零重叠、动画一致、拖拽、命中 ≤12px、导出、AST 扫描 | 渲染或交互回归 |

实测输出（节选）：

```text
[PASS] 10. 界面：站名零重叠 + 动画一致 + 命中 + 导出  (界面, 1658 ms)
        AST：无 core 导入、无 open()/solve()/load_dataset()；10 站名零重叠；
        5 段标注零重叠；动画/立即一致；北京 117 站名零重叠（省略 17 个）；
        命中误差 11.0px；PNG 39KB
结论：10 通过 / 0 失败 / 0 跳过，共 10 项，用时 1643 ms
闸门：绿（退出码 0）。
```

> 说明：上面的 117/17 是自检内部画布尺寸下的统计；报告图 4-2 用 1400×900 导出，
> 口径为 121 个站名、省略 13 个。两者只是画布尺寸不同，不是数据差异。

### 判别力：把实现改坏会发生什么

`--mutation-demo` 会启动 3 个子进程，分别做以下破坏：

1. 去掉 `ViewTransform.to_screen` 的 y 翻转 → 第 09 项必须红；
2. 给 Dijkstra 的 `total_time` 加 1 分钟 → 第 03 项必须红；
3. 把 10 个站名叠在同一位置 → 第 10 项必须红。

实测：

```text
[CAUGHT] 第 09 项：把 y 翻转去掉              -> 退出码 1
[CAUGHT] 第 03 项：给 Dijkstra 总耗时加 1 分钟 -> 退出码 1
[CAUGHT] 第 10 项：把 10 个站名叠在同一位置    -> 退出码 1
结果：3 种破坏全部被检查发现，说明断言有判别力（不是恒真）。
```

---

## 6. 验收对照（任务书 5 条）

| 验收项 | 证据 | 结果 |
| --- | --- | --- |
| 1. 任意窗口尺寸不变形、不裁切、站名不重叠 | 在 1070×700、1200×800、1400×900 三种尺寸导出；10 站图零省略，北京图按空间自动省略并保证已画站名零重叠 | 通过 |
| 2. 滚轮 0.5–3×、拖拽、悬停、缩放后命中 ≤12px | 自检第 09/10 项；11.0px 偏移仍命中 | 通过 |
| 3. 动画逐帧、调速、暂停/跳过、动画=立即 | 自检第 10 项比较 `PathMetrics`；演示 5 段标注全部显示 | 通过 |
| 4. `python main.py --check` 10 组断言、退出码闸门、改坏变红 | 10/10 绿；mutation 3/3 红 | 通过 |
| 5. 新人 5 分钟跑起来 | 见 §1 与 §8 实测记录 | 通过 |

更细的逐项证据与截图见 [`docs/P4-验收与交接.md`](docs/P4-验收与交接.md)。

---

## 7. 对比实验与报告素材

```powershell
python tools/bench.py                 # 写 docs/bench.csv、docs/bench.md、图 4-4
python tools/export_canvas.py --figure-pack
python tools/record_demo.py           # 录 docs/P4-演示动画.gif
```

* 5 对起终点：苹果园→天通苑北、安河桥北→草房、四惠东→角门西、慈寿寺→崇文门、草房→安河桥北；
* 每项热身 1 次，再计时 5 次取中位数；
* 结果：A* 平均扩展 76.8 个节点，Dijkstra 133.0 个，耗时都在 0.4ms 以内；
* BFS 在「慈寿寺→崇文门」用 1 次换乘换到 2.6 分钟绕行，体现“最少换乘 ≠ 最快”；
* BFS 的 `expanded` 是“按线路扩展”的计数，和 Dijkstra/A* 的逐站台计数口径不同，
  报告里只把它作为“搜索规模很小”的旁证，不直接和 133 比大小。

图表与数据：

* [`docs/bench.csv`](docs/bench.csv)、[`docs/bench.md`](docs/bench.md)
* [`docs/figures/fig4-4_expanded.png`](docs/figures/fig4-4_expanded.png)
* [`docs/figures/fig_p4_beijing_path.png`](docs/figures/fig_p4_beijing_path.png)
* [`docs/figures/fig_p4_demo_path.png`](docs/figures/fig_p4_demo_path.png)
* [`docs/figures/fig_p4_zoom.png`](docs/figures/fig_p4_zoom.png)
* [`docs/figures/fig3-1_ui.png`](docs/figures/fig3-1_ui.png) —— 第 3 章主界面截图
* [`docs/figures/fig_p4_canvas.ps`](docs/figures/fig_p4_canvas.ps)

---

## 8. 新人 5 分钟实测记录

日期：2026-10-17 ｜ 机器：Windows 11 ｜ Python 3.12.14 ｜ 依赖已就绪

| 步骤 | 操作 | 实测 |
| --- | --- | --- |
| 1 | 打开 README，确认环境要求 | 约 40 s |
| 2 | `pip install pillow`（若未装） | 约 25 s |
| 3 | `python main.py --check` | 2.0 s，10/10 绿 |
| 4 | `python main.py` 打开界面 | 1.6 s |
| 5 | 选「苹果园→天通苑北」，点搜索 | 结果 79.6 min / 33.2 km / 换乘 1 次 |
| 6 | 点「动画」→ 暂停 → 跳过 | 数值不变，画面正确 |
| 7 | `python tools/export_canvas.py _smoke/a.png` | 3.0 s，PNG 可打开 |

合计约 **1 分钟**（不含阅读时间）；即使第一次遇到 Pillow 未装、路径写错等小问题，
按 §9 FAQ 排查也在 5 分钟内。README 里的命令全部实际执行过。

---

## 9. 常见问题（FAQ）

**Q1：`ModuleNotFoundError: No module named 'PIL'`**
只影响 PNG/JPG 导出：`pip install pillow`。PS 导出和画布本身不需要 Pillow。

**Q2：`No module named 'tkinter'`**
Linux：`sudo apt install python3-tk`；Windows：重新运行 Python 安装包，勾选
“tcl/tk and IDLE”；macOS 用 python.org 安装包一般自带。

**Q3：导出的 PNG 截到了桌面/标题栏，画布偏了**
这是 Windows 125%/150% 缩放下的 DPI 问题。项目里的导出工具和自检都先调用
`ui/dpi.py::enable_high_dpi()`；**自己在别的程序里嵌画布导出时也要在创建 Tk 前调用它**。
另外 `CanvasView.export()` 会等窗口合成 0.35s，避免刚建窗就截图截到桌面。

**Q4：北京图有些站名没显示**
134 站在 1400×900 的适配视图里必然挤。策略是：先保证**已画出的站名零重叠**，
放不下的自动省略并在图例/状态栏提示；放大到 1.5×–3× 会逐步出现。
10 站演示图则 100% 显示（自检第 10 项）。

**Q5：路径每段 km/min 标注只显示了一部分**
一张全城图里 30 多段路径的标注总长度远超路线本身，强行全画必然互相压盖。
标注按“靠近路径优先”排，放不下才省略；放大后会显示更多。10 站演示图 5 段全部显示。

**Q6：PS 打不开/预览不了**
Tk 导出的其实是 EPS（`%!PS-Adobe-3.0 EPSF-3.0`）。Windows 资源管理器不预览 EPS，
用 Inkscape / Ghostscript / Adobe Illustrator 打开，或在 Word 里“插入图片”试一试；
报告正文更推荐 PNG。

**Q7：`--check` 退出码 1**
看红项名称和 detail；`--verbose` 打印堆栈。常见原因是数据文件被改坏、
或运行环境没有 Tk（第 10 项失败，可先 `--no-gui` 验证前 9 项）。

**Q8：动画中切换算法，旧动画会残留吗？**
不会。`animate()` 先 `after_cancel` 旧任务、删 `anim` 图层；`show_path()` 也会取消动画。
自检第 10 项专门验证了 `find_withtag("anim") == ()`。

**Q9：中文控制台乱码**
源码和 JSON 都是 UTF-8；Windows 控制台可先 `chcp 65001`，或设置
`$env:PYTHONIOENCODING="utf-8"`。Tk 界面不受控制台编码影响。

---

## 10. 分工边界与已知限制

* **P1/P2**：`core/` 是只读依赖，P4 没有改算法和数据格式；
* **P3**：`ui/window.py` 只是最小替身，正式按钮逻辑由 P3 接到 `CanvasView` 的公开方法上；
* **P4 自己的文件**：`ui/canvas.py`、`selfcheck.py`、`tools/export_canvas.py`、`tools/bench.py`、`tools/record_demo.py`、`README.md`、`docs/`；
* **接口层（P4 扩展）**：`metro_api.py` / `tools/serve_api.py` 是不打开窗口的调用层，只读 `core`，不参与 UI 分工；
* 限制 1：密集路网会自动省略部分站名/分段标注（放大恢复），这是为了保证“不重叠”；
* 限制 2：PNG 导出依赖可见窗口（截图方案），PS 是矢量、不受影响；
* 限制 3：BFS 的 `expanded` 计数口径与 Dijkstra/A* 不同，对比实验已在图注中说明；
* 限制 4：坐标是教学示意数据，不是真实地理投影。

---

## 11. 文档索引

### 11.1 协作与工程化

* [`CONTRIBUTING.md`](CONTRIBUTING.md) —— 分支命名、提交信息、文件所有权、自检闸门、PR/review/合并规范
* [`docs/GitHub协作与上传指南.md`](docs/GitHub协作与上传指南.md) —— 建仓、首次 push、保护 main、邀请组员、tag/Release、FAQ
* [`.github/workflows/selfcheck.yml`](.github/workflows/selfcheck.yml) —— GitHub Actions 自检闸门
* [`tools/prepare_github.py`](tools/prepare_github.py) —— 仓库体检 / manifest / zip 打包 / PR 描述生成

### 11.2 验收与报告

* [`docs/P4-验收与交接.md`](docs/P4-验收与交接.md) —— 5 条验收逐项证据、接口交接、限制
* [`reports/城市交通路径导航系统_实验报告.docx`](reports/城市交通路径导航系统_实验报告.docx) —— **五章实验报告终稿源文件**（`python tools/make_report.py` 可重新生成）
* [`reports/城市交通路径导航系统_实验报告.pdf`](reports/城市交通路径导航系统_实验报告.pdf) —— **终稿 PDF**（34 页，目录页码已更新，可直接提交；docx 为可再生成源）
* [`docs/P4-报告终稿说明.md`](docs/P4-报告终稿说明.md) —— 报告如何重新生成 / 检查、本版改动清单
* [`tools/make_report.py`](tools/make_report.py) —— 报告生成器（`python tools/make_report.py`）
* [`tools/check_report.py`](tools/check_report.py) —— 报告统稿检查器（退出码 0/1）
* [`docs/P4-报告章节草稿.md`](docs/P4-报告章节草稿.md) —— 第 4.5–4.7 节 + 第 5 章素材（已并入终稿）
* [`docs/P4-报告统稿模板与检查表.md`](docs/P4-报告统稿模板与检查表.md) —— 五章合并、图表编号、术语检查

### 11.3 演示与实验数据

* [`docs/P4-演示录屏脚本.md`](docs/P4-演示录屏脚本.md) —— 2 分钟录屏分镜与旁白
* [`docs/P4-演示动画.gif`](docs/P4-演示动画.gif) —— 自动录制的真实界面演示（23 帧）
* [`docs/bench.md`](docs/bench.md) / [`docs/bench.csv`](docs/bench.csv) —— 对比实验原始表与数据
* [`docs/figures/`](docs/figures/) —— 报告插图（`report/` 下为报告专用插图）

### 11.4 可调用接口

* [`docs/API接口说明.md`](docs/API接口说明.md) —— Python SDK / CLI / HTTP 三套调用的完整说明
* [`metro_api.py`](metro_api.py) —— `connect()` / `MetroNavigator` / 命令行入口
* [`tools/serve_api.py`](tools/serve_api.py) —— 本地 HTTP JSON 服务（零第三方依赖）
* [`tests/test_api.py`](tests/test_api.py) —— 34 个接口回归用例

---

## 12. GitHub 协作与上传

### 12.1 CI 徽章（占位，首次 push 后生效）

仓库建好后，把下面 URL 里的 `YOUR-GITHUB-NAME` 换成实际 GitHub 用户名/组织名，徽章会自动显示最新一次 CI 结果：

[![自检闸门](https://github.com/YOUR-GITHUB-NAME/metro-p4/actions/workflows/selfcheck.yml/badge.svg)](https://github.com/YOUR-GITHUB-NAME/metro-p4/actions/workflows/selfcheck.yml)

CI 配置见 [`.github/workflows/selfcheck.yml`](.github/workflows/selfcheck.yml)，
在 `ubuntu-latest + Python 3.12` 上跑两道闸门：

* `python main.py --check --no-gui` —— 无显示环境跳过第 10 项 GUI，前 9 项必须全绿；
* `xvfb-run -a python selfcheck.py --mutation-demo` —— 虚拟显示下跑真实 Tk 窗口，必须 3 个 `[CAUGHT]`；
* `python -m unittest discover -s tests -v` —— 可调用接口（SDK/CLI/HTTP）34 个用例。

push / PR 到 `main` 自动触发；失败时 Actions 日志里能直接看到 `[FAIL]` 红项与 detail。

### 12.2 `prepare_github.py` 常用命令

```powershell
python tools/prepare_github.py --check      # 仓库体检（默认命令）：必需文件 / 禁止入库 / 大文件 / 本机路径 / CI
python tools/prepare_github.py --stats      # 代码行数排行、文档/图片统计、自检是否可跑
python tools/prepare_github.py --manifest   # dist/manifest.json：待上传文件路径/大小/SHA-256
python tools/prepare_github.py --bundle     # dist/metro-p4-github-<日期>.zip（含未提交新文件，回读校验）
python tools/prepare_github.py --pr-body    # dist/PR_BODY.md：改动摘要 / 自检结果 / 审查要点 / 截图链接
python tools/prepare_github.py --all        # check + manifest + bundle + pr-body
```

首次上传（管理员执行一次；会改 remote 的命令默认不自动跑）：

```powershell
python tools/prepare_github.py --check --strict
python tools/prepare_github.py --remote https://github.com/YOUR-GITHUB-NAME/metro-p4.git
python tools/prepare_github.py --push
```

### 12.3 最小协作流程

```text
Issue（任务卡）→ 分支 feat/p1-data 等 → 本地自检
  → push → 开 PR（模板自动带出）→ CI 绿 → 至少 1 人 review → Squash merge
```

* 分支命名、提交信息、文件所有权、合并前闸门：[`CONTRIBUTING.md`](CONTRIBUTING.md)
* 建仓、保护 `main`、邀请组员、打 `v1.0.0` tag、常见问题：[`docs/GitHub协作与上传指南.md`](docs/GitHub协作与上传指南.md)
* 装好 remote 后，`python tools/prepare_github.py --pr-body` 可以直接生成 PR 描述。

---

## 13. 可调用接口（给同学 / 外部程序用）

除了 `CanvasView`（界面组件），项目还提供一层**不打开窗口**的调用接口，
适合批处理、脚本化演示、前端联调；与界面共用同一份 `core.solve`，数值口径完全一致。

```python
from metro_api import connect

nav = connect()                                        # 默认 134 站北京路网
print(nav.route("苹果园", "天通苑北")["summary"])        # 79.575 min / 33.236 km / 换乘 1
print(nav.compare("慈寿寺", "崇文门")["highlights"])     # 三算法差异摘要
```

```powershell
python metro_api.py route --start S001 --end S061 --json
python metro_api.py compare --start S001 --end S061
python main.py --cli info                              # 等价入口
python tools/serve_api.py --port 8765                  # HTTP：GET /api/route?start=..&end=..
python -m unittest discover -s tests -v                # 34 个接口回归用例
```

* 完整文档（方法 / JSON 结构 / 端点 / 错误码 / FAQ）：[`docs/API接口说明.md`](docs/API接口说明.md)
* 设计约束：不依赖 Tkinter、零第三方依赖、只读 `core`、JSON 友好、可多线程共享；
* 安全提示：HTTP 服务默认只绑定 `127.0.0.1`，没有鉴权/TLS，不要直接暴露到公网。

