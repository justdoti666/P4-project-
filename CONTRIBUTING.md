# CONTRIBUTING · 团队协作规范

> 适用仓库：`metro-p4`（城市交通路径导航系统 · 数据结构课程实践 选题 A）
> 本文件规定**分支、提交、文件所有权、自检闸门、PR、review、合并、发布**的做法。
> 第一次建仓、保护分支、邀请组员、打 tag 的逐步操作见
> [`docs/GitHub协作与上传指南.md`](docs/GitHub协作与上传指南.md)。

---

## 0. 30 秒速查

```powershell
git switch main
git pull                                   # 同步最新 main
git switch -c feat/p4-canvas               # 开自己的分支（命名见 §2）
# ……改代码……
python main.py --check                     # 必须 10/10 绿
python selfcheck.py --mutation-demo        # 必须 3 个 [CAUGHT]
git add -A
git commit -m "feat: 画布支持 4 倍速回放"
git push -u origin feat/p4-canvas          # 首次推这个分支
# 然后在 GitHub 网页开 PR → 等 CI 绿 + 至少 1 人 review → Squash merge
```

**红线**：不直接 push `main`、不强推、不把 `_smoke/` / `__pycache__/` / `dist/` / 大文件提交进来。

---

## 1. 开始之前

### 1.1 环境

| 项目 | 要求 | 一键检查 |
| --- | --- | --- |
| Python | 3.10+（CI 用 3.12） | `python --version` |
| Tkinter | Python 自带（Windows 安装包默认勾选） | `python -c "import tkinter; print(tkinter.TkVersion)"` |
| Pillow | 仅 PNG/JPG 导出、GIF 录制需要 | `python -c "import PIL; print(PIL.__version__)"` |
| Git | 2.30+ | `git --version` |

```powershell
# 全新克隆（把 URL 换成实际仓库地址）
git clone https://github.com/<账号>/metro-p4.git
cd metro-p4
pip install pillow
python main.py --check          # 第一次就要看到 10/10 绿
```

第一次使用 Git 记得配置身份（只需一次）：

```powershell
git config --global user.name "你的名字"
git config --global user.email "你的邮箱"
# 换行由仓库 .gitattributes 统一为 LF，一般不需要改 core.autocrlf（遇到 CRLF 警告见 §10）
```

### 1.2 先读这三份

1. [`README.md`](README.md) —— 怎么跑、接口、验收、FAQ；
2. [`docs/P4-验收与交接.md`](docs/P4-验收与交接.md) —— 5 条验收逐项证据；
3. 本文件 §3 的文件所有权表 —— **只改自己负责的文件**。

---

## 2. 分支模型与命名

`main` 是唯一长期分支，**受保护**：只能通过 PR 合入，且要求 CI 绿 + 至少 1 人 review。
每个人都从最新 `main` 切自己的分支干活，做完开 PR 合回。

| 分支名 | 用途 | 谁用 |
| --- | --- | --- |
| `feat/p1-data` | P1 数据层：加载、校验、路网数据 | P1 |
| `feat/p2-algo` | P2 算法层：Dijkstra / A* / BFS | P2 |
| `feat/p3-ui` | P3 界面层：窗口、控件、交互状态机 | P3 |
| `feat/p4-canvas` | P4 渲染：画布、动画、导出 | P4 |
| `feat/p4-engineering` | P4 工程化：自检、CI、协作文档、打包 | P4 |
| `docs/<主题>` | 单纯改文档（如 `docs/report-final`） | 任何人 |
| `fix/<主题>` | 修 bug（如 `fix/dpi-blurry-export`） | 任何人 |
| `chore/<主题>` | 杂项（如 `chore/enable-codeowners`） | 任何人 |
| `test/<主题>` | 只改自检/测试 | P4 |

命名规则：全小写、用 `-` 连接、不要中文和空格；一个分支只做一件事。

```powershell
git switch main
git pull
git switch -c feat/p4-canvas
```

---

## 3. 文件所有权

> 原则：**谁负责的模块谁改**。要动别人的文件，先在 Issue 里 @ 对方，得到同意再动。

| 模块 | 文件 / 目录 | Owner | 说明 |
| --- | --- | --- | --- |
| P1 数据层 | `core/loader.py`、`core/graph.py`、`data/` | P1 | 数据格式、加载校验、站点/线路/邻接表 |
| P2 算法层 | `core/algorithms.py` | P2 | Dijkstra / A* / BFS、权重与换乘建模 |
| P3 界面层 | `ui/window.py` | P3 | 窗口、控件、选点/搜索/算法切换 |
| P4 渲染 | `ui/canvas.py`、`ui/dpi.py` | P4 | 坐标变换、绘制、动画、导出、高 DPI |
| P4 自检与工具 | `selfcheck.py`、`tools/` | P4 | 10 项自检、导出/bench/录屏/打包工具 |
| P4 文档 | `README.md`、`CONTRIBUTING.md`、`docs/`、`reports/` | P4（报告统稿人） | 说明、报告、插图、演示 GIF |
| 公共入口 | `main.py`、`run.ps1`、`run.bat`、`requirements.txt` | 全组 | 改动前在群里说一声，PR 要管理员 review |
| CI / 协作配置 | `.github/`、`.gitattributes`、`.editorconfig`、`.gitignore` | 管理员（P4 整理） | 分支保护、CI、模板、CODEOWNERS |
| 只读依赖 | `core/` 对 P4 是只读；`ui/canvas.py` 对 P3 是组件 | —— | P4 不改 P1/P2 的语义，P3 不碰画布私有状态 |

**CODEOWNERS**：`.github/CODEOWNERS` 已按上表写好路径规则，用户名目前是注释占位，
账号确定后按文件里的 3 步替换即可自动拉 reviewer。

---

## 4. 提交信息约定

格式（与 Conventional Commits 一致，摘要用中文）：

```text
<type>: <中文摘要，不超过 50 字>

<可选：为什么改、怎么验证、影响范围>
```

| type | 用于 | 示例 |
| --- | --- | --- |
| `feat` | 新功能 | `feat: 画布支持 1×/2×/4× 动画调速` |
| `fix` | 修 bug | `fix: 修复 125% 缩放下导出截图偏移` |
| `docs` | 只改文档 | `docs: 补充 GitHub 上传与分支保护说明` |
| `test` | 只改自检/测试 | `test: 增加不连通图的第 07 项断言` |
| `chore` | 杂项/配置 | `chore: 启用 CODEOWNERS 与 PR 模板` |
| `refactor` | 不改变行为的重构 | `refactor: 抽出站名排版函数` |
| `perf` | 性能优化 | `perf: 站名宽度缓存，翻页不重复测量` |

规则：

- 一个提交只做一件事；改 10 个无关文件请拆成多个提交；
- 摘要不要写“update”“改了一下”这种看不出内容的话；
- 不要在提交里混入格式化的全文件重排（会让 diff 无法 review）；
- 提交前先 `git status` 看一眼，**不要提交** `_smoke/`、`__pycache__/`、`dist/`、`*.zip`、`~$*.docx`。

---

## 5. 合并前自检闸门（硬性）

在开 PR 之前，在本机仓库根目录**全部跑过**：

```powershell
python main.py --check                     # 必须：10 通过 / 0 失败 / 0 跳过，退出码 0
python selfcheck.py --mutation-demo        # 必须：3 种破坏全部 [CAUGHT]
python tools/prepare_github.py --check     # 必须：退出码 0（仓库体检）
```

没有显示器的环境（远程 Linux / CI）用 `--no-gui`：

```powershell
python main.py --check --no-gui            # 跳过第 10 项 GUI，前 9 项必须全绿
```

> `--no-gui` 的语义以 `selfcheck.py` 实现为准：**只跳过第 10 项**（界面 GUI 冒烟），
> 第 09 项坐标数学照常跑；跳过时结论会写「9 通过 / 0 失败 / 1 跳过」并提示未验证 GUI。

| 闸门 | 通过标准 | 失败意味着 |
| --- | --- | --- |
| `python main.py --check` | 10/10，退出码 0 | 数据/算法/边界/性能/界面有回归，**不许合并** |
| `python selfcheck.py --mutation-demo` | 3 个 `[CAUGHT]` | 自检断言失去判别力（改坏也不红），先修自检 |
| `python tools/prepare_github.py --check` | 退出码 0 | 协作文件/CI/禁止入库项有问题 |
| GitHub Actions「自检闸门」 | 绿 | 本机能过 CI 不能过 → 多半是环境差异（见 §10） |

另外：

- 改了界面/画布/导出：附 1~2 张新截图到 PR（用 `python tools/export_canvas.py` 或 `python main.py --smoke _smoke/xx.png`）；
- 改了算法/数据：附 `python tools/bench.py` 复跑后的 `docs/bench.csv` 对比，报告数字要同步；
- **不许**为了让闸门变绿而删除/放宽自检断言；发现断言本身错了，先开 Issue 说明理由，由 P4 修改并补 mutation 用例。

---

## 6. PR 流程

```text
Issue（任务卡）→ 分支 → 提交 → push → 开 PR → CI 绿 → 至少 1 人 review → Squash merge → 删分支 → 同步 main
```

### 6.1 步骤

1. **先有 Issue**：用「任务卡」模板立案（编号、负责人、前置、产出、DoD）；没有 Issue 的改动原则上不接。
2. **切分支**：按 §2 命名，从最新 `main` 切。
3. **小步提交**：按 §4 写提交信息；本地闸门（§5）跑绿才 push。
4. **push 分支**：`git push -u origin feat/xxx`（第一次带 `-u`，以后直接 `git push`）。
5. **开 PR**：GitHub 上点「Compare & pull request」，目标分支选 `main`，
   把 [`.github/PULL_REQUEST_TEMPLATE.md`](.github/PULL_REQUEST_TEMPLATE.md) 的内容填进描述，
   写 `Closes #<Issue 编号>`。
6. **等 CI**：Actions 的「自检闸门」必须绿；红了点进日志看 `[FAIL]` 红项，修完再 push（同一个 PR 会自动重跑）。
7. **找 review**：至少 1 人；改到 `core/`、`ui/window.py` 等他人负责的文件时，**对应 owner 必须 review**。
8. **改 review 意见**：继续在同一个分支提交并 push，PR 会自动更新；不要开新 PR。
9. **Squash merge**：review 通过 + CI 绿后，由 PR 作者或管理员点 **Squash and merge**，
   合并提交信息用 `feat: 摘要 (#PR编号)` 的格式。
10. **收尾**：合并后删除远程分支，本地 `git switch main` + `git pull`，再删本地分支 `git branch -d feat/xxx`。

### 6.2 review 要求

- 至少 1 人 approve；CI 未绿一律不合并；
- reviewer 重点看：**接口是否被破坏**、**自检是否被削弱**、**禁止入库项**、**文档与数字是否一致**；
- 有分歧就在 PR 评论里说清方案，必要时开 Issue 记录决策；不要用“已读不回”当通过；
- 紧急修复也走 PR（可以把 review 人数降为 1，但不能跳过 CI）。

### 6.3 需要谁 review

| 改到 | 必须 review 的人 |
| --- | --- |
| `core/loader.py`、`core/graph.py`、`data/` | P1 |
| `core/algorithms.py` | P2 |
| `ui/window.py` | P3 |
| `ui/canvas.py`、`selfcheck.py`、`tools/` | P4 |
| `main.py`、`.github/`、`CONTRIBUTING.md` | 管理员 + 受影响模块 owner |
| `docs/`、`README.md`、`reports/` | 报告统稿人（P4） |

---

## 7. 冲突处理

1. 开 PR 前先同步：`git switch main` + `git pull`，再 `git switch 你的分支` + `git merge main`（或 `git rebase main`）；
2. 冲突了**不要**慌，也不要把别人代码整段删掉：
   - `git status` 看冲突文件 → 打开手工合并（保留双方意图）；
   - 合完 `git add <文件>`，`git merge --continue`（rebase 时用 `git rebase --continue`）；
3. 冲突集中在别人负责的文件时，**拉对方一起看**，不要单方面决定；
4. 合并后**重新跑一遍 §5 的闸门**，再 push 到自己的分支；
5. 禁止 `git push --force` 到 `main`；自己的分支需要强推时用 `--force-with-lease`，并在 PR 里说明。

---

## 8. 禁止事项（红线）

- ❌ 直接 push `main`、强推 `main`、删除别人的分支；
- ❌ 提交 `_smoke/`、`__pycache__/`、`dist/`、`*.zip`、`.venv/`、`~$*.docx`、>40MB 文件；
- ❌ 源码/文档里写本机绝对路径（例如 C 盘用户目录），请用仓库相对路径；`prepare_github.py --check` 会扫描；
- ❌ 改 `ui/canvas.py` 的私有状态（`draw_graph`、`_transform`、`station_label_boxes` 等），或在画布里写业务逻辑（import `core`、读文件、调求解器）；
- ❌ 删除、注释、放宽 `selfcheck.py` 的断言来“过闸”；
- ❌ 把报告终稿里的数字改成与 `docs/bench.csv`、自检输出不一致；
- ❌ 提交来源不明的第三方代码/字体/图片（需要时先确认许可并在报告里注明）。

---

## 9. 发布与打 tag（管理员 / 交接人）

正式交付时打一个版本标签，并把打包好的 zip 和报告挂到 GitHub Release：

```powershell
git switch main
git pull
git tag -a v1.0.0 -m "P4 交付：10 项自检全绿 + 报告终稿 + 演示 GIF"
git push origin v1.0.0
python tools/prepare_github.py --all       # 生成 dist/metro-p4-github-<日期>.zip 和 dist/PR_BODY.md
```

然后在 GitHub 仓库页 → Releases → Draft a new release → 选 `v1.0.0` →
上传 `dist/metro-p4-github-<日期>.zip` 和 `reports/城市交通路径导航系统_实验报告.docx` → Publish。
详见 [`docs/GitHub协作与上传指南.md`](docs/GitHub协作与上传指南.md) §7。

---

## 10. 常见问题

| 问题 | 处理 |
| --- | --- |
| `--check` 出现红项 | `python main.py --check --verbose` 看堆栈；先只跑红项 `python selfcheck.py --only <编号> --verbose` |
| CI 红但本机绿 | 多半是环境差异：CI 无显示器（用 `--no-gui`）、没装 Pillow、Tk 不可用；看 CI 日志里的 `[FAIL]` 与 Tk/Pillow 检查步骤 |
| `ModuleNotFoundError: No module named 'PIL'` | `pip install pillow`（只影响 PNG/JPG 导出和 GIF 录制） |
| `No module named 'tkinter'` | Linux `sudo apt install python3-tk`；Windows 重装 Python 时勾选 tcl/tk |
| 中文乱码 | `chcp 65001` 或 `$env:PYTHONIOENCODING="utf-8"`；源码/JSON 都是 UTF-8 |
| 换行符 CRLF 警告 | 不要改 `core.autocrlf` 全局配置，仓库用 `.gitattributes` 统一为 LF |
| 大文件推不上去 | 不允许入库；用 GitHub Release 附件或 Git LFS，先删掉再提交 |
| push 被拒（protected branch） | 正常现象：main 只能走 PR；把你的提交放到分支上重新开 PR |

---

## 11. 常用命令卡

```powershell
# 同步与分支
git switch main ; git pull
git switch -c feat/xxx
git status --short
git diff --stat

# 自检闸门
python main.py --check
python selfcheck.py --mutation-demo
python tools/prepare_github.py --check

# 提交与推送
git add -A
git commit -m "feat: 中文摘要"
git push -u origin feat/xxx

# 合并 main 进分支（解决冲突用）
git fetch origin
git merge origin/main

# 本地看效果
python main.py
python main.py --smoke _smoke/a.png
python tools/export_canvas.py _smoke/a.ps --demo
```
