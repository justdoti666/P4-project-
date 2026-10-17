---
name: Bug 报告
about: 自检红了、界面不对、数据加载失败、导出异常……用这个模板报 bug
title: "[bug] 一句话描述问题"
labels: bug
assignees: ""
---

## 问题现象

<!-- 一句话说清发生了什么；有截图直接贴在这里 -->

## 复现命令 / 步骤

```powershell
# 在仓库根目录执行，尽量给出最小可复现命令
python main.py --check
```

1.
2.
3.

## 期望结果

<!-- 按任务书 / README / 自检矩阵，应该是什么样 -->

## 实际结果

<!-- 把关键输出、红项名称、报错堆栈贴在这里（不要只写“报错了”） -->

```text
（粘贴输出）
```

## 环境

| 项 | 值 |
| --- | --- |
| 系统 | Windows 11 / macOS / Linux（哪个发行版） |
| Python | `python --version` 的输出 |
| Pillow | 已装 / 未装，版本 |
| Tk | 可用 / 不可用（`python -c "import tkinter; print(tkinter.TkVersion)"`） |
| 分支 / 提交 | `git branch --show-current`、`git rev-parse --short HEAD` |
| 是否改过代码 | 是 / 否（是的话说明改了哪些文件） |

## 已尝试的排查

- [ ] 重新跑 `python main.py --check --verbose` 看完整堆栈
- [ ] `python selfcheck.py --only <编号> --verbose` 只跑红项
- [ ] 检查 `_smoke/`、`__pycache__/` 是不是旧的（删掉重跑）
- [ ] 对照 `README.md` §9 FAQ / `docs/GitHub协作与上传指南.md` 常见问题
- [ ] 其他：

## 影响范围

- 是否阻塞合并：是 / 否
- 是否影响报告数字 / 截图：是 / 否（说明哪些）
- 建议负责人：@
