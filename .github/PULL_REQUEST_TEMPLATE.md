# Pull Request 模板

> 复制本模板到 PR 描述，逐项填写；不确定的地方先写「待补」，不要直接删掉检查项。
> 更完整的规范见 [CONTRIBUTING.md](../CONTRIBUTING.md)。

## 1. 改动摘要

<!-- 用 1~3 句话说明：改了什么、为什么改、怎么验证 -->

- 一句话摘要：
- 关联 Issue：Closes #
- 分支：`feat/xxx` → `main`
- 提交信息：`feat|fix|docs|test|chore: 中文摘要`

## 2. 自检结果（必须真实跑过）

- [ ] `python main.py --check` → 10 通过 / 0 失败 / 0 跳过（退出码 0）
- [ ] `python selfcheck.py --mutation-demo` → 3 个 `[CAUGHT]`
- [ ] `python tools/prepare_github.py --check` → 退出码 0
- [ ] 截图 / 导出图已人工目检：站名零重叠、路径颜色可辨、没有桌面/标题栏穿帮
- [ ] CI 的「自检闸门」工作流绿（PR 页面底部 status checks 可见）

<details>
<summary>自检输出（可选，粘贴关键几行）</summary>

```text
（把 python main.py --check 的最后几行贴在这里）
```

</details>

## 3. 影响范围（勾选实际改到的部分）

- [ ] `core/` —— 数据层 / 算法层（P1 / P2 负责人必须 review）
- [ ] `ui/canvas.py`、`selfcheck.py` —— P4 渲染与自检
- [ ] `ui/window.py` —— P3 窗口与交互
- [ ] `data/` —— 路网数据
- [ ] `docs/`、`README.md`、`CONTRIBUTING.md` —— 文档
- [ ] `.github/`、`tools/prepare_github.py` —— CI 与协作工具
- [ ] `main.py`、`run.ps1`、`run.bat` —— 公共入口（改前先说一声）

## 4. 审查者须知

<!-- 提醒 reviewers 重点看什么，例如： -->

- 重点看：
- 已知问题 / 暂未处理：
- 需要 reviewer 手动验证的步骤：

### 提交者自查（禁止事项）

- [ ] 没有把 `_smoke/`、`__pycache__/`、`dist/`、`*.zip`、大文件提交进来
- [ ] 没有直接改 `ui/canvas.py` 的私有状态，也没有在画布层写业务逻辑
- [ ] 没有强推 `main`；本 PR 只包含本任务相关的改动
- [ ] 文档里的相对链接都能点开；报告数字与 `docs/bench.csv`、自检输出一致
