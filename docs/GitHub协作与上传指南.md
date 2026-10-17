# GitHub 协作与上传指南

> 面向：第一次把课程项目传上 GitHub、或第一次带组员用 PR 协作的同学。
> 本指南全部命令在 **Windows PowerShell** 下实测/验证过；等价的纯 git 写法在双栏表里给出。
> 协作规范（分支、提交、所有权、review）见 [`CONTRIBUTING.md`](../CONTRIBUTING.md)；
> 仓库体检/打包工具见 [`tools/prepare_github.py`](../tools/prepare_github.py)。

---

## 0. 先看总览：哪些操作做一次，哪些天天做

| 阶段 | 操作 | 谁做 | 频率 |
| --- | --- | --- | --- |
| 建仓 | GitHub 网页新建仓库 → 本地首次 push | 管理员 | 一次 |
| 配置 | 保护 `main`、邀请组员、填 CODEOWNERS 用户名 | 管理员 | 一次 |
| 日常 | clone → 切分支 → 改 → 自检 → push → 开 PR | 每个组员 | 每人每次任务 |
| 日常 | review → CI 绿 → Squash merge → 删分支 | reviewer + 作者 | 每个 PR |
| 交付 | 打 `v1.0.0` tag、传 Release 资产（zip / 报告 / GIF） | 管理员 | 一次 |

**两个安全网**：

1. `main` 分支保护 + CI：任何人（包括管理员）都不能直接把红代码推进 `main`；
2. 本地自检闸门：`python main.py --check` 10/10 + `python selfcheck.py --mutation-demo` 3 个 `[CAUGHT]`。

---

## 1. 在 GitHub 上创建仓库（一次）

1. 打开 <https://github.com/new>；
2. **Repository name** 填 `metro-p4`；
3. 可见性选 **Private**（课程作业建议私有；老师要求公开再改成 Public）；
4. **不要**勾选 “Add a README file / Add .gitignore / Choose a license”。
   本项目已经有这些文件，勾了会在首次 push 时产生无关提交甚至冲突；
5. 点 **Create repository**，记下页面显示的仓库地址，两种形式任选：

```text
HTTPS：https://github.com/<你的账号>/metro-p4.git
SSH  ：git@github.com:<你的账号>/metro-p4.git
```

> 组员如果只做课程作业、不想配 SSH key，用 HTTPS + 浏览器登录（Windows 会弹
> Git Credential Manager 登录窗）最省事。

---

## 2. 首次上传本地仓库（一次）

前提：本地 `metro-p4` 已经 `git init` 并有提交（本仓库已有 1 个初始提交）。

### 2.1 上传前先体检 + 打包留底

```powershell
cd metro-p4

# 1) 仓库体检：必需文件、禁止入库项、大文件、本机绝对路径、CI 配置
python tools/prepare_github.py --check --strict

# 2) 生成 dist/manifest.json（路径/大小/SHA-256）和离线交付 zip
python tools/prepare_github.py --manifest
python tools/prepare_github.py --bundle
```

`--strict` 模式会把“报告终稿尚未生成”等提醒也算失败——**正式上传前**应该全绿。
`--bundle` 生成的 `dist/metro-p4-github-<YYYYMMDD>.zip` 只含待上传文件，
可以先发给组员/老师，等 GitHub 仓库建好后再 push。

### 2.2 绑定 remote 并 push

| 操作 | PowerShell（在仓库根目录） | 等价 git 命令 |
| --- | --- | --- |
| 确认当前分支是 main | `git branch --show-current` | `git branch --show-current` |
| 添加远程仓库 | `python tools/prepare_github.py --remote https://github.com/<账号>/metro-p4.git` | `git remote add origin https://github.com/<账号>/metro-p4.git` |
| 查看 remote 是否配对 | `python tools/prepare_github.py --remote` | `git remote -v` |
| 首次推送 main | `python tools/prepare_github.py --push` | `git push -u origin main` |
| 推送后核对 | 浏览器打开仓库页，确认 `README.md`、`.github/`、`core/`、`ui/` 都在 | `git log --oneline -1`、`git status` |

> 如果 push 时提示认证失败：Windows 一般会弹窗让你登录 GitHub；
> 也可以在 GitHub → Settings → Developer settings → Personal access tokens 生成
> 一个带 `repo` 权限的 token，把 token 当密码粘贴。**不要把 token 写进任何文件。**
> 远程仓库已有提交（例如网页初始化过）时，先 `git pull --rebase origin main` 再 push。

---

## 3. 保护 main 分支（一次，最重要）

目标：`main` 只能通过 PR 合入；PR 必须 CI 绿 + 至少 1 人 review。

**网页操作（GitHub 新版界面）**：

1. 仓库页 → **Settings**（顶部）→ 左侧 **Branches**（或 Rules → Rulesets）；
2. **Add branch protection rule**（经典分支保护）：
   - **Branch name pattern**：`main`
   - ✅ Require a pull request before merging
     - ✅ Require approvals：`1`
     - ✅ Dismiss stale pull request approvals when new commits are pushed
   - ✅ Require status checks to pass before merging
     - ✅ Require branches to be up to date before merging
     - 在搜索框里选 **自检闸门**（第一次 push 之后 CI 跑过一次才会出现；
       状态名类似「Python 3.12 · 10 项自检 + 判别力演示」或「selfcheck」）
   - ✅ Require conversation resolution before merging（可选）
   - ✅ Do not allow bypassing the above settings（勾上后管理员也不能绕过）
   - ❌ 不要勾 “Allow force pushes”，❌ 不要勾 “Allow deletions”
3. 点 **Create** / **Save changes**。

**或者用 Rulesets（新版推荐，等价效果）**：
Settings → Rules → Rulesets → New branch ruleset → Target branches 选 `main` → 勾选
“Require a pull request before merging”“Require status checks to pass”“Block force pushes”，
Bypass list 留空 → Create。

验证：直接在 `main` 上试 `git push` 一个空提交，应该被拒绝（提示 protected branch）；
开一个 PR 能看到 “Review required / Some checks haven't completed” 的提示。

---

## 4. 邀请组员（一次）

1. 仓库页 → **Settings** → **Collaborators**（个人仓库）或 **Manage access**（组织仓库）；
2. **Add people** → 输入组员的 GitHub 用户名或邮箱 → 选 **Write** 权限 → 发送邀请；
3. 组员在邮箱里点接受（或打开 GitHub 通知页接受）后即可 push 分支、开 PR；
4. 组织仓库更推荐建 Team（如 `metro-p4-dev`），把仓库给 Team 开 Write，人员增删只动 Team。

权限建议：

| 角色 | 权限 | 说明 |
| --- | --- | --- |
| 组员（P1–P4） | Write | 可以推分支、开 PR，不能直接改 main（有保护） |
| 管理员/组长 | Admin/Write | 改仓库设置、CODEOWNERS、保护规则、打 tag |
| 老师/助教 | Read | 只读查看 |

**填 CODEOWNERS 用户名**（可选但推荐）：
打开 [`.github/CODEOWNERS`](../.github/CODEOWNERS)，把注释里的 `@p1-data-owner` 等占位换成组员真实
GitHub 用户名，删掉行首 `# `，提交一个 `chore: 启用 CODEOWNERS` 的 PR 合并即可。
写错用户名时 GitHub 会在设置页提示，那一行会被忽略，不影响其他规则。

---

## 5. 组员日常：clone → 分支 → 改 → PR

### 5.1 第一次 clone

| 操作 | PowerShell | 等价 git 命令 |
| --- | --- | --- |
| 克隆仓库 | `git clone https://github.com/<账号>/metro-p4.git` | 同左 |
| 进入目录 | `cd metro-p4` | 同左 |
| 装依赖 | `pip install pillow` | 同左 |
| 跑自检 | `python main.py --check` | 同左 |
| 配身份（只需一次） | `git config --global user.name "你的名字"`<br>`git config --global user.email "你的邮箱"` | 同左 |

### 5.2 开分支改代码

```powershell
# 同步最新 main
git switch main
git pull

# 开自己的分支（命名见 CONTRIBUTING §2）
git switch -c feat/p4-canvas

# ……改代码……

# 合并前闸门（必须全绿）
python main.py --check
python selfcheck.py --mutation-demo

# 提交 → 推送（第一次带 -u）
git add -A
git commit -m "feat: 画布支持 1×/2×/4× 动画调速"
git push -u origin feat/p4-canvas
```

### 5.3 网页开 PR

1. 打开仓库页 → 顶部 **Pull requests** → **New pull request**；
2. `base` 选 `main`，`compare` 选你的分支（push 后页面通常会出现黄色 **Compare & pull request** 按钮）；
3. 标题按 `feat: 摘要` 写；描述把
   [`.github/PULL_REQUEST_TEMPLATE.md`](../.github/PULL_REQUEST_TEMPLATE.md) 的内容填进去，
   写上 `Closes #<Issue 编号>`；
4. 点 **Create pull request**，等 CI（Actions）跑完。

### 5.4 PR 描述可以用工具生成

```powershell
python tools/prepare_github.py --pr-body
```

会生成 `dist/PR_BODY.md`：里面自动带上「改了哪些文件、自检结果、影响范围、审查要点、
截图链接」，复制到 GitHub PR 描述即可（`dist/` 已被 .gitignore 忽略，不会进仓库）。

---

## 6. review 与合并

### 6.1 reviewer 怎么做

1. 打开 PR → **Files changed** 逐文件看 diff；
2. 有问题在行号旁点 **+** 写评论 → **Start a review** → **Submit review** 选
   **Comment**（提意见）或 **Request changes**（打回）；
3. 没问题选 **Approve**；
4. 重点检查（与 CONTRIBUTING §6 对应）：
   - 有没有破坏 `CanvasView` 公开接口、有没有在画布层写业务逻辑；
   - `selfcheck.py` 的断言有没有被削弱/删除；
   - 有没有混入 `_smoke/`、`__pycache__/`、`dist/`、大文件；
   - 文档里的相对链接、数字是否和 `docs/bench.csv`、自检输出一致。

### 6.2 作者改完怎么办

在同一个分支继续提交并 `git push`，PR 会自动更新；reviewer 的意见在页面上点
**Resolve conversation**，然后重新请求 review。**不要关掉旧 PR 重新开一个。**

### 6.3 合并（CI 绿 + 至少 1 approve 后）

1. PR 页面底部绿色按钮选 **Squash and merge**（不是 Create a merge commit）；
   - 如果组织允许，勾选 “Delete branch” 顺手删远程分支；
2. 合并提交信息用：`feat: 画布支持 4 倍速 (#12)`；
3. 本地收尾：

| 操作 | PowerShell / git 命令 |
| --- | --- |
| 切回 main 并同步 | `git switch main`<br>`git pull` |
| 删除本地已合并分支 | `git branch -d feat/p4-canvas` |

> 用了 Squash merge 后，本地分支与 main 的历史不一致，删掉重建是最简单的方式。

---

## 7. 打 tag 与发布 Release（交付时一次）

```powershell
git switch main
git pull
git tag -a v1.0.0 -m "P4 交付：10 项自检全绿 + 报告终稿 + 演示 GIF"
git push origin v1.0.0
```

然后在网页操作：

1. 仓库页 → 右侧 **Releases** → **Draft a new release**；
2. **Choose a tag** 选刚推的 `v1.0.0`；标题写 `v1.0.0 P4 交付`；
3. 描述里写：本版包含什么、自检结果（10/10、3 CAUGHT）、报告与演示位置；
4. 上传附件：
   - `dist/metro-p4-github-<YYYYMMDD>.zip`（`python tools/prepare_github.py --bundle` 生成）
   - `reports/城市交通路径导航系统_实验报告.docx`（报告组生成）
   - 需要时加 `docs/P4-演示动画.gif`（Release 允许大附件，比塞进 git 更合适）
5. **Publish release**。

> 普通 git push 不能上传 Release 附件；大文件（GIF、docx、zip）优先用 Release 附件
> 或 GitHub 网页上传，不要强行 `git add` 进历史。

---

## 8. 上传 / 更新报告与演示 GIF

| 场景 | 推荐做法 | 命令 |
| --- | --- | --- |
| 报告 docx 小（<10MB）且需要版本历史 | 提交到 `reports/`（已配置为二进制） | `git add reports/城市交通路径导航系统_实验报告.docx` → commit → PR |
| 报告 docx 很大或只想发最终版 | 挂到 Release 附件 | 见 §7 第 4 步 |
| 演示 GIF（本仓库约 3.5MB） | 可以在 `docs/` 里提交；更新时同名覆盖 | `python tools/record_demo.py` 重新生成后按 PR 流程提交 |
| 演示 MP4 | 一般超过 10MB，走 Release 附件 | 按 `docs/P4-演示录屏脚本.md` 录制 |
| 只想给老师看、不公开 | 保持 Private 仓库，把老师加为 Read 权限 | Settings → Collaborators |

更新报告/截图后记得同步 `README.md` §11 文档索引和报告里的图号；报告重新生成命令：

```powershell
python tools/make_report.py          # 生成 reports/城市交通路径导航系统_实验报告.docx
python tools/check_report.py         # 统稿检查，退出码 0 才算过
```

---

## 9. CI（GitHub Actions）怎么工作

工作流文件：[`.github/workflows/selfcheck.yml`](../.github/workflows/selfcheck.yml)

| 项 | 内容 |
| --- | --- |
| 触发 | push 到 `main`、向 `main` 开/更新 PR |
| 环境 | `ubuntu-latest` + Python 3.12 + Pillow + Tk 运行库 + xvfb 虚拟显示 |
| 步骤 1 | `python main.py --check --no-gui`（无显示环境，跳过第 10 项 GUI，失败会显示 `[FAIL]` 红项） |
| 步骤 2 | `xvfb-run -a python selfcheck.py --mutation-demo`（在虚拟显示下跑真实 Tk 窗口，必须 3 个 `[CAUGHT]`） |
| 失败时 | PR 页面底部 checks 变红；点 **Details** 看日志里 `[FAIL]` 与 detail，修完 push 会自动重跑 |

本地模拟 CI（不想装 xvfb 时用 `--no-gui`）：

```powershell
python main.py --check --no-gui
python selfcheck.py --mutation-demo
```

> 说明：CI 里第 10 项 GUI 检查依赖 runner 的 Tk/Pillow 截图能力，因此额外装了
> `python3-tk + xvfb`；如果某次 CI 日志显示第 10 项环境报错，请在本地 Windows 上补跑
> `python main.py --check`（10/10）并把截图贴进 PR，同时开 Issue 记录。

---

## 10. 常见问题（FAQ）

### Q1：Git 提示 `LF will be replaced by CRLF` / 行尾混乱

仓库已用 [`.gitattributes`](../.gitattributes) 统一：文本文件入库为 LF，Windows 的
`.ps1/.bat` 保持 CRLF。**不要去改全局 `core.autocrlf`**。如果已经出现全文件换行 diff：

```powershell
git add --renormalize .
git status
```

### Q2：push 被拒绝：`protected branch` / `required status check`

这是分支保护在起作用（正常现象）。把改动放到 `feat/xxx` 分支 → 开 PR → CI 绿 + review 后
Squash merge；不要尝试绕过保护。

### Q3：`remote: Support for password authentication was removed`

GitHub 不再接受账号密码。Windows 上用 Git Credential Manager 浏览器登录，或生成
Personal Access Token（Settings → Developer settings → Tokens）作为密码。
token 只存在凭据管理器里，**不要写进脚本或提交到仓库**。

### Q4：大文件推不上去（>100MB 或警告 >50MB）

不要提交。把文件从暂存区拿掉（`git restore --staged <文件>`），改用 Release 附件或 Git LFS。
已经提交进历史的大文件需要 `git filter-repo` 清理（属于高风险操作，先找管理员）。

### Q5：合并冲突怎么解

```powershell
git switch main
git pull
git switch feat/xxx
git merge main          # 冲突文件会标出来
# 手工编辑冲突文件 -> git add <文件> -> git merge --continue
python main.py --check  # 解决后重新跑闸门
git push
```

冲突发生在别人负责的文件（见 CONTRIBUTING §3）时，拉对方一起看再合并。

### Q6：`python main.py --check` 红了

1. `python main.py --check --verbose` 看完整堆栈；
2. 先只跑红项：`python selfcheck.py --only <编号> --verbose`；
3. 常见原因：数据文件被改坏（01/02）、算法口径变了（03–05）、性能超阈值（08）、
   Tk/显示环境问题（09/10，可先 `--no-gui` 确认前 9 项）；
4. 修好前不要开 PR；**不要删断言来“过闸”**。

### Q7：`ModuleNotFoundError: No module named 'PIL'`

只影响 PNG/JPG 导出和 GIF 录制：`pip install pillow`。
PS 导出和画布本身只需要标准库 + Tk。

### Q8：`No module named 'tkinter'` / CI 上 Tk 不可用

- Windows：重新运行 Python 安装包，勾选 “tcl/tk and IDLE”；
- Ubuntu/Debian：`sudo apt install python3-tk`；
- macOS：用 python.org 安装包一般自带；
- 远程无显示器：`python main.py --check --no-gui` 先验证前 9 项。

### Q9：Actions 一直不跑 / 权限不足

- Settings → Actions → General → 确认 “Allow all actions”；
- PR 来自 fork 时，首次需要维护者点 **Approve and run workflows**；
- 组织仓库可能限制 Actions 权限，找管理员开。

### Q10：CODEOWNERS 不生效 / 用户名写错

GitHub 只按**合并进默认分支的 CODEOWNERS**生效；用户名必须是真实账号（带 `@`）。
写错的行会被忽略，可在仓库 Settings → Code and automation → Code owners 页面看提示。
也可以不启用 CODEOWNERS，改为手动在 PR 里 @ 对应 owner（见 CONTRIBUTING §6.3）。

### Q11：中文乱码

源码/JSON 都是 UTF-8；PowerShell 里可先 `chcp 65001`，或设
`$env:PYTHONIOENCODING="utf-8"`。Git 提交信息用中文没问题，但建议避免生僻 emoji。

### Q12：想撤销一次提交 / 回退

- 只撤销最近一次提交但保留改动：`git reset --soft HEAD~1`；
- 已经 push 到自己的分支：`git revert <hash>`（生成反向提交，最安全）；
- **不要**对 `main` 用 `reset --hard` + 强推。

---

## 11. 命令速查（PowerShell / git 双栏）

| 作用 | PowerShell 常用写法 | 等价 git 写法 |
| --- | --- | --- |
| 查看分支 / 状态 | `git branch --show-current`<br>`git status --short` | 同左 |
| 同步 main | `git switch main`<br>`git pull` | `git fetch origin` + `git merge --ff-only origin/main` |
| 新建并切分支 | `git switch -c feat/p4-canvas` | `git checkout -b feat/p4-canvas` |
| 查看改了什么 | `git diff`<br>`git diff --stat` | 同左 |
| 暂存 + 提交 | `git add -A`<br>`git commit -m "feat: 摘要"` | `git commit -am "feat: 摘要"`（不处理新文件） |
| 推分支 | `git push -u origin feat/p4-canvas` | `git push --set-upstream origin feat/p4-canvas` |
| 看远程地址 | `python tools/prepare_github.py --remote` | `git remote -v` |
| 加远程仓库 | `python tools/prepare_github.py --remote <URL>` | `git remote add origin <URL>` |
| 首次推送 main | `python tools/prepare_github.py --push` | `git push -u origin main` |
| 打 tag | `git tag -a v1.0.0 -m "说明"` | 同左 |
| 推 tag | `git push origin v1.0.0` | `git push --tags`（会推所有 tag） |
| 合并 main 进分支 | `git fetch origin`<br>`git merge origin/main` | `git pull origin main` |
| 删本地分支 | `git branch -d feat/p4-canvas` | `git branch -D`（未合并时强删） |
| 仓库体检 | `python tools/prepare_github.py --check --strict` | —— |
| 生成交付 zip | `python tools/prepare_github.py --bundle` | —— |
| 生成 PR 描述 | `python tools/prepare_github.py --pr-body` | —— |
| 一键（体检+清单+zip+PR 描述） | `python tools/prepare_github.py --all` | —— |

> 提示：PowerShell 里路径含空格要加引号；`;` 可以一行连写多条命令（如
> `cd metro-p4; python main.py --check`）。cmd 用户请把 `;` 换成 `&&` 或分行写。

---

## 12. 一页纸清单（打印出来贴显示器）

**管理员（一次性）**

- [ ] GitHub 新建 private 仓库 `metro-p4`（不勾 README/gitignore）
- [ ] `prepare_github.py --check --strict` → `--remote <URL>` → `--push`
- [ ] 保护 `main`：Require PR + 1 approval + 自检闸门 status check
- [ ] 邀请组员（Write 权限），必要时填 CODEOWNERS 用户名
- [ ] 交付时：打 `v1.0.0` tag → Release 上传 zip + 报告 + GIF

**每个组员（每个任务）**

- [ ] `git switch main && git pull` → `git switch -c feat/xxx`
- [ ] 只改自己负责的文件（CONTRIBUTING §3）
- [ ] `python main.py --check`（10/10）→ `python selfcheck.py --mutation-demo`（3 CAUGHT）
- [ ] 提交信息 `type: 中文摘要` → push 分支 → 开 PR（模板填全）
- [ ] 等 CI 绿 + 至少 1 人 approve → Squash merge → 删分支 → 同步 main
