# 评审整改差异包（06e182a → b641db7）

> 用途：把「外部评审整改」的差异单独打包，方便 P2/同事**只审阅差异**，或在旧版本上应用补丁。
> 完整代码、报告与测试已在 `main` 的 `b641db7`；本目录只是差异副本，不替代仓库。

## 内容

| 文件 | 说明 |
| --- | --- |
| `评审整改-b641db7.patch` | 文本补丁（24 个文本文件；SHA-256 `6fbc6f884d8e080dea0b790122477385c497d519276f7a7e87631956d1ce1d32`；`git diff` 生成，UTF-8） |
| `diffstat.txt` | `git diff --stat 06e182a..b641db7` 的完整统计（共 26 个文件，+948/−152） |
| `binary-files.json` | 两个报告二进制文件的大小/SHA-256；文本补丁不含二进制 |
| `README.md` | 本说明 |

基线 `06e182a` 是上一版（可调用接口 + 报告 34 页）；整改版 `b641db7` 包含：
P2 兼容（`sid`/`events`）、双权重与线路速度、BFS 口径修正、bench 默认输出、L1–L5 小项、
报告重新生成（PDF 35 页）、unittest 35→55。

## 如何审阅

```powershell
git fetch origin
git diff --stat 06e182a..b641db7                 # 先看规模
git diff 06e182a..b641db7 -- core ui tests      # 重点看代码
git show b641db7 --stat
```

## 如何应用补丁（在旧版本上）

```powershell
git switch -c review-fixes 06e182a
git apply docs/review-fixes/评审整改-b641db7.patch
# 补丁已用 git apply --check 在 06e182a 上验证可干净应用（24 个文本文件）
# 两个报告二进制文件不在补丁里，二选一：
git checkout b641db7 -- "reports/城市交通路径导航系统_实验报告.docx" "reports/城市交通路径导航系统_实验报告.pdf"

python -m unittest discover -s tests -v        # 55/55
python main.py --check --no-gui                # 9 PASS + 1 SKIP
python tools/check_report.py                   # 22/22
python tools/prepare_github.py --check --strict
```

## 校验

- 补丁 SHA-256：`6fbc6f884d8e080dea0b790122477385c497d519276f7a7e87631956d1ce1d32`
- 应用后文本文件变更应为 24 个；再按 `binary-files.json` 校验两个报告文件的 SHA-256。
- 整改逐项说明见 [`../评审整改记录-2026-10-18.md`](../评审整改记录-2026-10-18.md)。
