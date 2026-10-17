#!/usr/bin/env python3
"""GitHub 上传准备工具（P4 工程化）。

一句话：把 ``metro-p4`` 整理成可以直接推上 GitHub 的仓库，并生成交接用的 zip 包。

常用命令
--------
    python tools/prepare_github.py --check      # 仓库体检（不带参数时默认执行）
    python tools/prepare_github.py --stats      # 代码 / 文档 / 图片统计
    python tools/prepare_github.py --manifest   # 生成 dist/manifest.json（路径 / 大小 / SHA-256）
    python tools/prepare_github.py --bundle     # 打包 dist/metro-p4-github-YYYYMMDD.zip
    python tools/prepare_github.py --pr-body    # 生成 dist/PR_BODY.md（PR 描述）
    python tools/prepare_github.py --all        # check + manifest + bundle + pr-body

    # 下面 3 个命令会改仓库或 .git 配置，默认不执行，由仓库管理员在首次上传时手动跑：
    python tools/prepare_github.py --commit -m "feat: 说明"
    python tools/prepare_github.py --remote https://github.com/<账号>/metro-p4.git
    python tools/prepare_github.py --push

输出约定
--------
* 全部中文输出；Windows 控制台 / 重定向到文件都不乱码（强制 UTF-8）；
* 只用 Python 标准库，git 操作全部通过 subprocess 调用本机 git；
* 「待上传文件」= git 已跟踪文件 + 未跟踪但未被 .gitignore 忽略的文件，
  所以**第一次提交之前**（新文件还没 git add）也能正确体检和打包；
* 所有路径基于本文件所在目录的上一级（仓库根），不依赖从哪个目录启动；
* 退出码：0 = 成功 / 体检通过；1 = 失败 / 体检红；2 = 参数用法错误。

体检红绿标准
------------
* 阻塞项（红）：必需文件缺失、禁止入库文件被 git 跟踪、单文件 > 40MB、
  源码里出现本机用户目录绝对路径、CI workflow 结构或闸门命令不对；
* 提醒项（不判红）：报告终稿等由报告组并行产出的文件尚未生成、
  单文件 10MB~40MB、Markdown 相对链接暂时指向尚未生成的文件。
  加 ``--strict`` 可把提醒也当失败（最终上传前建议跑一次）。
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import zipfile
from pathlib import Path

# ----------------------------------------------------------------------
# 常量
# ----------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DIST_DIR = PROJECT_ROOT / "dist"
MANIFEST_PATH = DIST_DIR / "manifest.json"
PR_BODY_PATH = DIST_DIR / "PR_BODY.md"

MAX_FILE_BYTES = 40 * 1024 * 1024          # 单文件上限（GitHub 也会提示，超过就不该入库）
BIG_FILE_WARN_BYTES = 10 * 1024 * 1024     # 大于 10MB 只提醒
VERIFY_TIMEOUT_SECONDS = 300               # 收集自检证据时的超时

# 不进仓库 / 不进 zip 的目录名（任意层级）
EXCLUDED_DIRS = {
    ".git", "dist", "__pycache__", "_smoke", "_verify", ".venv", "venv",
    ".idea", ".vscode", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    ".tox", ".cache", "node_modules",
}
# 不进仓库 / 不进 zip 的后缀
EXCLUDED_SUFFIXES = {
    ".pyc", ".pyo", ".pyd", ".zip", ".7z", ".rar", ".tar", ".gz",
    ".log", ".tmp", ".bak", ".orig", ".rej", ".swp", ".swo",
}
# 不进仓库 / 不进 zip 的具体文件名
EXCLUDED_NAMES = {
    ".DS_Store", "Thumbs.db", "desktop.ini", ".coverage", "coverage.xml",
    ".gitignore.swp",
}
# 会被扫描「本机绝对路径」的文本文件后缀
TEXT_SUFFIXES = {
    ".py", ".ps1", ".bat", ".cmd", ".md", ".txt", ".json", ".yml", ".yaml",
    ".csv", ".html", ".css", ".js", ".toml", ".ini", ".cfg", ".sh",
}
TEXT_FILENAMES = {".gitignore", ".gitattributes", ".editorconfig"}

# 用拼接构造（并把 needle 统一小写），避免本文件自己被下面的绝对路径扫描命中；
# 扫描时对每一行做了 .lower()，这里必须同样是小写，否则永远不会命中。
_LOCAL_PATH_NEEDLES = ("c:" + "\\users" + "\\", "c:" + "/users/")

# 必需文件：缺失 = 阻塞（红）
REQUIRED_FILES = [
    # 根目录：程序入口 + 运行说明 + 协作规范
    "main.py",
    "selfcheck.py",
    "README.md",
    "CONTRIBUTING.md",
    "requirements.txt",
    "run.ps1",
    "run.bat",
    ".gitignore",
    ".gitattributes",
    ".editorconfig",
    # GitHub 协作配置
    ".github/workflows/selfcheck.yml",
    ".github/PULL_REQUEST_TEMPLATE.md",
    ".github/CODEOWNERS",
    ".github/ISSUE_TEMPLATE/task.md",
    ".github/ISSUE_TEMPLATE/bug_report.md",
    # 业务代码（P1/P2/P3/P4）
    "core/__init__.py",
    "core/loader.py",
    "core/graph.py",
    "core/algorithms.py",
    "ui/__init__.py",
    "ui/window.py",
    "ui/canvas.py",
    "ui/dpi.py",
    # 数据
    "data/beijing_metro.json",
    "data/beijing_metro.txt",
    "data/demo_city.json",
    "data/tiny_3.json",
    "data/disconnected_4.json",
    # 文档与素材
    "docs/GitHub协作与上传指南.md",
    "docs/P4-验收与交接.md",
    "docs/P4-报告章节草稿.md",
    "docs/P4-报告统稿模板与检查表.md",
    "docs/P4-演示录屏脚本.md",
    "docs/P4-演示动画.gif",
    "docs/bench.csv",
    "docs/bench.md",
    # 工具
    "tools/prepare_github.py",
    "tools/export_canvas.py",
    "tools/bench.py",
    "tools/record_demo.py",
]

# 报告交付物：由报告组并行产出，缺失只提醒、不判红（最终上传前建议 --strict）
REPORT_FILES = [
    "reports/城市交通路径导航系统_实验报告.docx",
    "docs/P4-报告终稿说明.md",
    "tools/make_report.py",
    "tools/check_report.py",
    "tools/make_report_assets.py",
    "tools/report_common.py",
    "docs/figures/report/fig2-1_arch.png",
]

# 需要检查 Markdown 相对链接的文档
DOC_LINK_FILES = [
    "README.md",
    "CONTRIBUTING.md",
    "docs/GitHub协作与上传指南.md",
]

# .gitignore 必须覆盖的运行产物（做子串匹配）
GITIGNORE_REQUIRED = [
    ("__pycache__", "__pycache__/"),
    ("*.py[cod]", "*.py[cod]"),
    ("_smoke", "_smoke/"),
    ("dist", "dist/"),
    ("_verify", "_verify/"),
    ("*.zip", "*.zip"),
    (".venv", ".venv/"),
    (".pytest_cache", ".pytest_cache/"),
]

# CI workflow 必须包含的关键内容：(出现在文件里的片段, 说明)
WORKFLOW_TOKENS = [
    ("ubuntu-latest", "runs-on: ubuntu-latest"),
    ("actions/checkout@v4", "actions/checkout@v4"),
    ("actions/setup-python@v5", "actions/setup-python@v5"),
    ('python-version: "3.12"', 'python-version: "3.12"'),
    ("pillow", "安装 Pillow（pip install pillow）"),
    ("python main.py --check --no-gui", "自检闸门命令 python main.py --check --no-gui"),
    ("python selfcheck.py --mutation-demo", "判别力演示命令 python selfcheck.py --mutation-demo"),
]

# zip 回读校验时要求一定在包里的文件（报告 docx 另算）
BUNDLE_KEY_FILES = [
    ".github/workflows/selfcheck.yml",
    "CONTRIBUTING.md",
    "tools/prepare_github.py",
    "README.md",
]


class PrepareError(RuntimeError):
    """工具自身无法继续（git 不可用、参数矛盾等）：统一转成可读报错。"""


# ----------------------------------------------------------------------
# 基础工具
# ----------------------------------------------------------------------
def _reconfigure_stdout() -> None:
    """Windows 控制台 / 重定向到文件时都按 UTF-8 输出。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _now_text() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _fmt_bytes(num: int) -> str:
    if num >= 1024 ** 3:
        return f"{num / 1024 ** 3:.2f} GB"
    if num >= 1024 ** 2:
        return f"{num / 1024 ** 2:.2f} MB"
    if num >= 1024:
        return f"{num / 1024:.1f} KB"
    return f"{num} B"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _print_section(title: str) -> None:
    print(f"\n== {title} ==")


def _print_status(level: str, text: str) -> None:
    """level: OK / FAIL / WARN / INFO。"""
    print(f"  [{level:<4}] {text}")


def _git(*args: str, timeout: int = 120) -> subprocess.CompletedProcess:
    """调用本机 git；统一 UTF-8、关闭路径转义（中文文件名保持原样）。"""
    command = ["git", "-c", "core.quotepath=false", *args]
    try:
        return subprocess.run(
            command,
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise PrepareError("找不到 git 命令，请先安装 Git 并加入 PATH。") from exc
    except subprocess.TimeoutExpired as exc:
        raise PrepareError(f"git 命令超时：{' '.join(args)}") from exc


def _git_output(*args: str) -> str:
    proc = _git(*args)
    if proc.returncode != 0:
        return ""
    return proc.stdout


def _git_paths(*args: str) -> list[str]:
    """git ls-files 一类命令的 NUL 分隔输出 -> 路径列表（中文文件名不受转义影响）。"""
    proc = _git(*args, "-z")
    if proc.returncode != 0:
        raise PrepareError(f"git {' '.join(args)} 执行失败：{proc.stderr.strip()}")
    return [item for item in proc.stdout.split("\0") if item.strip()]


def _normalize_rel(rel: str) -> str:
    return rel.replace("\\", "/").strip("/")


def _is_excluded(rel_posix: str) -> bool:
    parts = rel_posix.split("/")
    if any(part in EXCLUDED_DIRS for part in parts[:-1]):
        return True
    # DSH 工具（office 渲染预览）的 .dsh-office-xxxx / .dsh-xxxx 缓存目录
    if any(part.startswith(".dsh-") for part in parts[:-1]):
        return True
    name = parts[-1]
    if name in EXCLUDED_NAMES:
        return True
    if (name.startswith("~$") or name.startswith("._") or name.startswith("_tmp")
            or name.startswith(".dsh-")):
        return True
    if rel_posix.startswith("reports/") and name.startswith("_"):
        return True  # 报告预览/渲染的临时文件（如 reports/_preview.pdf）
    if Path(name).suffix.lower() in EXCLUDED_SUFFIXES:
        return True
    return False


def _repo_info() -> dict:
    """当前 git 仓库信息；不是 git 仓库时返回 is_repo=False。"""
    info = {"is_repo": False, "branch": "-", "head": "-", "remote": ""}
    proc = _git("rev-parse", "--is-inside-work-tree")
    if proc.returncode != 0 or proc.stdout.strip() != "true":
        return info
    info["is_repo"] = True
    info["branch"] = _git_output("rev-parse", "--abbrev-ref", "HEAD").strip() or "-"
    info["head"] = _git_output("rev-parse", "--short", "HEAD").strip() or "（尚无提交）"
    info["remote"] = _git_output("remote", "get-url", "origin").strip()
    return info


def _collect_upload() -> dict:
    """收集「待上传文件」。

    返回 ``{"files": [...], "tracked": [...], "untracked": [...], "missing": [...]}``，
    其中 files 是过滤后的仓库相对路径（posix 风格，已排序），
    tracked / untracked 是过滤前的原始 git 清单（用于打印说明）。
    """
    tracked = [_normalize_rel(item) for item in _git_paths("ls-files", "--cached") if item.strip()]
    untracked = [
        _normalize_rel(item)
        for item in _git_paths("ls-files", "--others", "--exclude-standard")
        if item.strip()
    ]
    files: list[str] = []
    missing: list[str] = []
    seen: set[str] = set()
    for rel in tracked + untracked:
        if not rel or rel in seen or _is_excluded(rel):
            continue
        seen.add(rel)
        if (PROJECT_ROOT / rel).is_file():
            files.append(rel)
        else:
            missing.append(rel)
    files.sort()
    return {
        "files": files,
        "tracked": [rel for rel in tracked if rel and not _is_excluded(rel)],
        "untracked": [rel for rel in untracked if rel and not _is_excluded(rel)],
        "missing": missing,
    }


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


# ----------------------------------------------------------------------
# 仓库体检（--check，默认命令）
# ----------------------------------------------------------------------
def _check_required_files(problems: list[str], reminders: list[str]) -> None:
    _print_section("1. 必需文件（缺失 = 阻塞）")
    present = 0
    for rel in REQUIRED_FILES:
        if (PROJECT_ROOT / rel).is_file():
            present += 1
            _print_status("OK", rel)
        else:
            problems.append(f"缺少必需文件：{rel}")
            _print_status("FAIL", f"缺少：{rel}")
    print(f"  ---- 必需文件 {present}/{len(REQUIRED_FILES)} 存在")

    _print_section("2. 报告交付物（报告组并行产出；缺失只提醒）")
    present = 0
    for rel in REPORT_FILES:
        if (PROJECT_ROOT / rel).is_file():
            present += 1
            _print_status("OK", rel)
        else:
            reminders.append(f"报告交付物尚未生成：{rel}")
            _print_status("WARN", f"尚未生成：{rel}")
    print(f"  ---- 报告交付物 {present}/{len(REPORT_FILES)} 存在")


def _check_forbidden_tracked(problems: list[str]) -> None:
    _print_section("3. 禁止入库项（是否被 git 跟踪）")
    tracked = [_normalize_rel(item) for item in _git_paths("ls-files", "--cached") if item.strip()]
    bad: list[tuple[str, str]] = []
    for rel in tracked:
        if any(part in EXCLUDED_DIRS for part in rel.split("/")[:-1]):
            bad.append((rel, "位于不应入库的目录"))
        elif rel.endswith(tuple(EXCLUDED_SUFFIXES)):
            bad.append((rel, "不应入库的文件后缀"))
        elif Path(rel).name in EXCLUDED_NAMES:
            bad.append((rel, "不应入库的系统/临时文件"))
        elif Path(rel).name.startswith("~$"):
            bad.append((rel, "Office 临时锁文件"))
    if bad:
        for rel, reason in bad:
            problems.append(f"禁止入库的文件被 git 跟踪：{rel}（{reason}）")
            _print_status("FAIL", f"{rel}（{reason}）")
    else:
        _print_status("OK", f"已跟踪文件 {len(tracked)} 个，未发现 "
                            "__pycache__ / _smoke / dist / .venv / *.pyc / *.zip")
    # 顺带提示：_smoke 等目录里若还有未跟踪文件，不影响上传，但打包会被排除
    smoke = PROJECT_ROOT / "_smoke"
    if smoke.is_dir():
        count = sum(1 for _ in smoke.rglob("*") if _.is_file())
        if count:
            _print_status("INFO", f"_smoke/ 有 {count} 个冒烟测试产物，上传时自动排除")


def _check_large_files(collection: dict, problems: list[str], reminders: list[str]) -> None:
    _print_section("4. 大文件（单文件 > 40MB = 阻塞；> 10MB 提醒）")
    files = collection["files"]
    total = 0
    big_problems = 0
    biggest: list[tuple[str, int]] = []
    for rel in files:
        size = (PROJECT_ROOT / rel).stat().st_size
        total += size
        biggest.append((rel, size))
        if size > MAX_FILE_BYTES:
            big_problems += 1
            problems.append(f"文件超过 40MB：{rel}（{_fmt_bytes(size)}）")
            _print_status("FAIL", f"{rel} 有 {_fmt_bytes(size)}，超过 40MB 上限")
        elif size > BIG_FILE_WARN_BYTES:
            reminders.append(f"文件较大（10~40MB）：{rel}（{_fmt_bytes(size)}）")
            _print_status("WARN", f"{rel} 有 {_fmt_bytes(size)}，建议走 Release 附件或 Git LFS")
    biggest.sort(key=lambda item: item[1], reverse=True)
    for rel, size in biggest[:5]:
        _print_status("INFO", f"最大文件之一：{rel}  {_fmt_bytes(size)}")
    _print_status("OK" if big_problems == 0 else "INFO",
                  f"待上传 {len(files)} 个文件，合计 {_fmt_bytes(total)}")


def _scan_local_absolute_paths(collection: dict, problems: list[str]) -> None:
    _print_section("5. 本机绝对路径扫描（源码/文档里不应写死 C 盘用户目录）")
    scanned = 0
    hits = 0
    for rel in collection["files"]:
        path = PROJECT_ROOT / rel
        if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in TEXT_FILENAMES:
            continue
        if path.stat().st_size > 2 * 1024 * 1024:
            continue
        scanned += 1
        try:
            text = _read_text(path)
        except OSError:
            continue
        for line_no, line in enumerate(text.splitlines(), start=1):
            lower = line.lower()
            if any(needle in lower for needle in _LOCAL_PATH_NEEDLES):
                hits += 1
                problems.append(f"发现本机绝对路径：{rel}:{line_no}")
                _print_status("FAIL", f"{rel}:{line_no}  {line.strip()[:100]}")
    if not hits:
        _print_status("OK", f"扫描 {scanned} 个文本文件，未发现本机用户目录绝对路径")


def _check_gitignore(problems: list[str]) -> None:
    _print_section("6. .gitignore 覆盖运行产物")
    path = PROJECT_ROOT / ".gitignore"
    if not path.is_file():
        problems.append(".gitignore 不存在")
        _print_status("FAIL", ".gitignore 不存在")
        return
    text = _read_text(path).lower()
    for token, label in GITIGNORE_REQUIRED:
        if token.lower() in text:
            _print_status("OK", label)
        else:
            problems.append(f".gitignore 没有覆盖：{label}")
            _print_status("FAIL", f"缺少：{label}")


def _collect_markdown_links() -> list[tuple[str, int, str]]:
    """(文档路径, 行号, 链接目标) 列表；只收相对链接。"""
    links: list[tuple[str, int, str]] = []
    pattern = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
    for rel in DOC_LINK_FILES:
        path = PROJECT_ROOT / rel
        if not path.is_file():
            continue
        for line_no, line in enumerate(_read_text(path).splitlines(), start=1):
            for match in pattern.finditer(line):
                target = match.group(1).strip()
                if not target or target.startswith(("#", "http://", "https://", "mailto:", "/")):
                    continue
                links.append((rel, line_no, target))
    return links


def _check_markdown_links(reminders: list[str]) -> None:
    _print_section("7. 文档内链（README / CONTRIBUTING / GitHub 指南）")
    links = _collect_markdown_links()
    broken = 0
    for doc, line_no, target in links:
        plain = target.split("#", 1)[0]
        if not plain:
            continue
        plain = plain.replace("%20", " ")
        resolved = (PROJECT_ROOT / doc).parent / plain
        if not resolved.exists():
            broken += 1
            reminders.append(f"文档内链指向尚不存在的文件：{doc}:{line_no} -> {target}")
            _print_status("WARN", f"{doc}:{line_no} -> {target}（暂不存在）")
    if not broken:
        _print_status("OK", f"共 {len(links)} 个相对链接，全部指向真实文件/目录")


def _check_workflow(problems: list[str]) -> None:
    _print_section("8. CI workflow（.github/workflows/*.yml）")
    workflow_dir = PROJECT_ROOT / ".github" / "workflows"
    workflows = sorted(workflow_dir.glob("*.yml")) + sorted(workflow_dir.glob("*.yaml"))
    if not workflows:
        problems.append("没有找到 .github/workflows/*.yml")
        _print_status("FAIL", "没有找到 workflow 文件")
        return

    for path in workflows:
        rel = path.relative_to(PROJECT_ROOT).as_posix()
        text = _read_text(path)
        errors: list[str] = []

        # (1) YAML 基础结构：不允许 tab；顶层键 name / on / jobs 必须存在
        if "\t" in text:
            errors.append("包含制表符（YAML 缩进不能用 tab）")
        lines = text.splitlines()
        top_keys: list[str] = []
        for line in lines:
            if not line or line.startswith(("#", " ", "-")):
                continue
            if ":" not in line:
                continue
            top_keys.append(line.split(":", 1)[0].strip().strip("'\""))
        for need in ("name", "on", "jobs"):
            if need not in top_keys:
                errors.append(f"缺少顶层键 {need}:")
        if not re.search(r"(?m)^\s{0,2}push:\s*$", text):
            errors.append("缺少 push 触发（on: push: branches: [main]）")
        if not re.search(r"(?m)^\s{0,2}pull_request:\s*$", text):
            errors.append("缺少 pull_request 触发")
        # 触发条件：push / pull_request 到 main（允许写成 "- main" 或 "[main]" 两种风格）
        inline_branches = re.search(r"(?m)^\s*branches:\s*\[[^\]]*\bmain\b[^\]]*\]", text)
        list_branches = re.search(r"(?m)^\s+-\s+main\s*$", text)
        if not (inline_branches or list_branches):
            errors.append("缺少 branches 里的 main")
        if not re.search(r"(?m)^\s{2,6}runs-on:\s*\S+", text):
            errors.append("缺少 runs-on")
        if not re.search(r"(?m)^\s{2,6}steps:\s*$", text):
            errors.append("缺少 steps:")
        if len(re.findall(r"(?m)^\s+uses:\s*\S+", text)) < 2:
            errors.append("uses: 动作少于 2 个")

        # (2) 环境与闸门命令
        for token, label in WORKFLOW_TOKENS:
            if token not in text:
                errors.append(f"缺少 {label}")

        if errors:
            for message in errors:
                problems.append(f"CI 配置有问题（{rel}）：{message}")
                _print_status("FAIL", f"{rel}：{message}")
        else:
            _print_status("OK", f"{rel}：YAML 结构 / push+PR 触发 main / 环境 / 闸门命令 全部通过")
            _print_status("INFO", "YAML 校验方式：无 tab + 顶层键 name/on/jobs + "
                                  "runs-on/steps + 触发分支 + 关键命令片段")


def run_check(strict: bool = False) -> int:
    """仓库体检；返回 0（可上传）或 1（有阻塞问题）。"""
    info = _repo_info()
    print("=" * 82)
    print("GitHub 上传准备工具 · 仓库体检")
    print(f"项目目录：{PROJECT_ROOT}")
    if info["is_repo"]:
        remote = info["remote"] or "未配置 origin"
        print(f"git 状态：{info['branch']} @ {info['head']} · {remote}")
    else:
        print("git 状态：当前目录不是 git 仓库")
    print("=" * 82)

    problems: list[str] = []
    reminders: list[str] = []
    try:
        collection = _collect_upload()
    except PrepareError as exc:
        print(f"\n[错误] {exc}")
        return 1

    _check_required_files(problems, reminders)
    _check_forbidden_tracked(problems)
    _check_large_files(collection, problems, reminders)
    _scan_local_absolute_paths(collection, problems)
    _check_gitignore(problems)
    _check_markdown_links(reminders)
    _check_workflow(problems)

    print("\n" + "-" * 82)
    print(f"待上传文件：git 跟踪 {len(collection['tracked'])} 个 + "
          f"未跟踪未忽略 {len(collection['untracked'])} 个 "
          f"= 打包候选 {len(collection['files'])} 个")
    if collection["missing"]:
        print(f"[提醒] git 清单里有 {len(collection['missing'])} 个文件在磁盘上不存在：")
        for rel in collection["missing"][:10]:
            print(f"        - {rel}")

    print(f"阻塞问题：{len(problems)} 个")
    for item in problems:
        print(f"  - {item}")
    print(f"提醒项：{len(reminders)} 个")
    for item in reminders[:20]:
        print(f"  - {item}")
    if len(reminders) > 20:
        print(f"  …… 另有 {len(reminders) - 20} 条，略")

    if problems:
        print("结论：仓库暂时不能上传（请先修复上面的阻塞问题），退出码 1。")
        return 1
    if strict and reminders:
        print("结论：--strict 模式下提醒也算失败（提醒 " + str(len(reminders)) + " 个），退出码 1。")
        return 1
    print(f"结论：仓库可上传（阻塞 0 个，提醒 {len(reminders)} 个），退出码 0。")
    return 0


# ----------------------------------------------------------------------
# 待上传清单 / manifest（--manifest）
# ----------------------------------------------------------------------
def _build_manifest() -> dict:
    collection = _collect_upload()
    entries = []
    total = 0
    for rel in collection["files"]:
        path = PROJECT_ROOT / rel
        size = path.stat().st_size
        total += size
        entries.append({"path": rel, "size": size, "sha256": _sha256_file(path)})
    return {
        "generated_at": _now_text(),
        "repo": PROJECT_ROOT.name,
        "git_branch": _repo_info()["branch"],
        "git_head": _repo_info()["head"],
        "file_count": len(entries),
        "total_bytes": total,
        "git_tracked": len(collection["tracked"]),
        "git_untracked": len(collection["untracked"]),
        "files": entries,
    }


def run_manifest() -> int:
    print("=" * 82)
    print("待上传文件清单 → dist/manifest.json")
    print("=" * 82)
    manifest = _build_manifest()
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"  [OK  ] 清单写入：{MANIFEST_PATH}")
    print(f"  [INFO] 待上传文件：{manifest['file_count']} 个，"
          f"合计 {_fmt_bytes(manifest['total_bytes'])}（{manifest['total_bytes']} 字节）")
    print(f"  [INFO] git 跟踪 {manifest['git_tracked']} 个 + "
          f"未跟踪未忽略 {manifest['git_untracked']} 个")
    print(f"  [INFO] 每个文件都记录了 SHA-256，可直接比对 zip 包内容是否被改动")
    return 0


# ----------------------------------------------------------------------
# 打包（--bundle）
# ----------------------------------------------------------------------
def _bundle_zip_path() -> Path:
    stamp = datetime.date.today().strftime("%Y%m%d")
    return DIST_DIR / f"metro-p4-github-{stamp}.zip"


def run_bundle() -> int:
    print("=" * 82)
    print("打包 GitHub 交付 zip（只含待上传文件）")
    print("=" * 82)
    collection = _collect_upload()
    files = collection["files"]
    if not files:
        print("  [FAIL] 没有可打包的文件（git 清单为空？）")
        return 1

    DIST_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = _bundle_zip_path()
    if zip_path.exists():
        zip_path.unlink()

    expected: dict[str, str] = {}
    print(f"  [..  ] 正在打包 {len(files)} 个文件……")
    started = time.perf_counter()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED,
                         compresslevel=6) as archive:
        for rel in files:
            path = PROJECT_ROOT / rel
            archive.write(path, arcname=rel)
            expected[rel] = _sha256_file(path)
    elapsed = (time.perf_counter() - started) * 1000
    size = zip_path.stat().st_size

    # ---- 回读 zip 自校验：条目数、SHA-256、必需文件、禁止项 ----
    problems: list[str] = []
    warnings: list[str] = []
    with zipfile.ZipFile(zip_path, "r") as archive:
        names = archive.namelist()
        bad_sha: list[str] = []
        for name in names:
            actual = hashlib.sha256(archive.read(name)).hexdigest()
            if expected.get(name) != actual:
                bad_sha.append(name)
        corrupt = archive.testzip()
    if len(names) != len(expected):
        problems.append(f"zip 条目数 {len(names)} 与待上传文件数 {len(expected)} 不一致")
    if bad_sha:
        problems.append(f"zip 内有 {len(bad_sha)} 个文件 SHA-256 与源文件不一致")
    if corrupt:
        problems.append(f"zip 内文件损坏：{corrupt}")

    missing_keys = [rel for rel in BUNDLE_KEY_FILES if rel not in names]
    if missing_keys:
        problems.append(f"zip 缺少必需文件：{', '.join(missing_keys)}")
    report_rel = "reports/城市交通路径导航系统_实验报告.docx"
    if (PROJECT_ROOT / report_rel).is_file():
        if report_rel not in names:
            problems.append(f"zip 缺少报告终稿：{report_rel}")
    else:
        warnings.append(f"报告终稿尚未生成，zip 暂不包含 {report_rel}")

    forbidden_hits = [
        name for name in names
        if "__pycache__" in name or "_smoke/" in name or ".git/" in name
        or name.startswith("dist/") or "_verify/" in name
        or name.endswith((".pyc", ".pyo", ".zip"))
        or Path(name).is_absolute() or ".." in Path(name).parts
    ]
    if forbidden_hits:
        problems.append(f"zip 内混入 {len(forbidden_hits)} 个不应上传的文件："
                        f"{', '.join(forbidden_hits[:5])}")

    print(f"  [OK  ] 生成：{zip_path}")
    print(f"  [INFO] 大小：{_fmt_bytes(size)}（{size} 字节），条目 {len(names)} 个，"
          f"打包耗时 {elapsed:.0f} ms")
    print(f"  [INFO] 已跟踪文件 {len(collection['tracked'])} 个 + "
          f"未跟踪新文件 {len(collection['untracked'])} 个都打进了包里")
    if problems:
        for message in problems:
            print(f"  [FAIL] {message}")
        print("  [FAIL] 回读校验未通过，退出码 1。")
        return 1
    for message in warnings:
        print(f"  [WARN] {message}")
    print(f"  [OK  ] 回读校验通过：{len(names)} 个条目、SHA-256 全部一致、"
          f"未包含 .git / dist / __pycache__ / _smoke")
    print(f"  [OK  ] 必需文件已包含：{', '.join(BUNDLE_KEY_FILES)}")
    print("  [INFO] 用法：把 zip 解压到空目录（或直接发给组员/老师），"
          "解压后的目录结构就是仓库根。")
    return 0


# ----------------------------------------------------------------------
# 统计（--stats）
# ----------------------------------------------------------------------
def _count_lines(path: Path) -> int:
    try:
        return len(_read_text(path).splitlines())
    except OSError:
        return 0


def run_stats() -> int:
    print("=" * 82)
    print("仓库统计（代码 / 文档 / 图片 / 报告）")
    print("=" * 82)
    collection = _collect_upload()
    files = collection["files"]

    py_files = [rel for rel in files if rel.endswith(".py")]
    py_lines = {rel: _count_lines(PROJECT_ROOT / rel) for rel in py_files}
    total_py_lines = sum(py_lines.values())
    md_files = [rel for rel in files if rel.endswith(".md")]
    md_lines = sum(_count_lines(PROJECT_ROOT / rel) for rel in md_files)
    image_files = [rel for rel in files
                   if Path(rel).suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".ps"}]
    json_files = [rel for rel in files if rel.endswith(".json")]
    total_bytes = sum((PROJECT_ROOT / rel).stat().st_size for rel in files)
    info = _repo_info()

    print(f"  [INFO] 待上传文件：{len(files)} 个，合计 {_fmt_bytes(total_bytes)}")
    print(f"  [INFO] git：{info['branch']} @ {info['head']}；"
          f"已跟踪 {len(collection['tracked'])} 个，未跟踪 {len(collection['untracked'])} 个")
    print(f"\n  Python：{len(py_files)} 个文件，共 {total_py_lines} 行")
    ranking = sorted(py_lines.items(), key=lambda item: item[1], reverse=True)
    for rank, (rel, lines) in enumerate(ranking[:10], start=1):
        print(f"    {rank:>2}. {rel:<32} {lines:>5} 行")

    print(f"\n  文档：{len(md_files)} 个 Markdown，共 {md_lines} 行")
    print(f"  图片：{len(image_files)} 个（PNG / GIF / PS），"
          f"合计 {_fmt_bytes(sum((PROJECT_ROOT / rel).stat().st_size for rel in image_files))}")
    print(f"  数据：{len(json_files)} 个 JSON + "
          f"{len([rel for rel in files if rel.endswith('.txt')])} 个 TXT")

    report_rel = "reports/城市交通路径导航系统_实验报告.docx"
    if (PROJECT_ROOT / report_rel).is_file():
        size = (PROJECT_ROOT / report_rel).stat().st_size
        print(f"  报告：{report_rel}（{_fmt_bytes(size)}）")
    else:
        print(f"  报告：{report_rel} 尚未生成（报告组并行产出中）")

    # 自检闸门是否可跑
    registered: set[str] = set()
    selfcheck_path = PROJECT_ROOT / "selfcheck.py"
    if selfcheck_path.is_file():
        registered = set(re.findall(r"@check\(\s*(\d+)\s*,", _read_text(selfcheck_path)))
    tk_ok = True
    try:
        import tkinter  # noqa: F401
        tk_version = f"Tk {tkinter.TkVersion}"
    except Exception as exc:  # pragma: no cover - 取决于本机环境
        tk_ok = False
        tk_version = f"不可用（{type(exc).__name__}: {exc}）"
    pillow_ok = True
    try:
        from PIL import Image  # noqa: F401
        pillow_version = "Pillow 可用"
    except Exception:  # pragma: no cover
        pillow_ok = False
        pillow_version = "Pillow 未安装（PNG 导出/GIF 录制会跳过）"
    print(f"\n  自检闸门：{len(registered)} 项检查已注册；环境 {tk_version}、{pillow_version}")
    if len(registered) == 10 and tk_ok:
        print("            可运行 `python main.py --check` 完整验证 10 项（GUI 可用）")
    elif len(registered) == 10:
        print("            只能运行 `python main.py --check --no-gui`（前 9 项，GUI 不可用）")
    else:
        print("  [WARN] 自检项不是 10 项，请检查 selfcheck.py 的 @check 注册")
    print("\n  提示：--stats 只统计，不改文件；需要上传请用 --bundle / --all。")
    return 0


# ----------------------------------------------------------------------
# 自检证据（给 --pr-body 用）
# ----------------------------------------------------------------------
def _last_line_with(text: str, keyword: str) -> str:
    found = ""
    for line in text.splitlines():
        if keyword in line:
            found = line.strip()
    return found


def _run_command_detailed(argv: list[str], timeout: int = VERIFY_TIMEOUT_SECONDS):
    """运行子进程并返回 (returncode, stdout, stderr)；超时返回 (-1, ...)。"""
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        proc = subprocess.run(
            [sys.executable, *argv],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=env,
        )
        return proc.returncode, proc.stdout or "", proc.stderr or ""
    except subprocess.TimeoutExpired:
        return -1, "", f"命令超时（{timeout}s）"


def _probe_selfcheck() -> dict:
    """实际跑一遍自检闸门，把结论写进 PR 描述（跑不动时降级为 --no-gui）。"""
    result = {
        "check": {"ok": False, "command": "python main.py --check",
                  "summary": "未运行", "detail": ""},
        "mutation": {"ok": False, "command": "python selfcheck.py --mutation-demo",
                     "summary": "未运行", "detail": ""},
    }
    print("  [..  ] 运行 python main.py --check 收集自检证据（约数秒）……")
    for argv in (["main.py", "--check"], ["main.py", "--check", "--no-gui"]):
        code, stdout, stderr = _run_command_detailed(argv)
        summary = _last_line_with(stdout, "结论：")
        if not summary:
            summary = f"退出码 {code}" + (f"；{stderr.strip().splitlines()[-1][:120]}"
                                          if stderr.strip() else "")
        result["check"] = {
            "ok": code == 0,
            "command": "python " + " ".join(argv),
            "summary": summary,
            "detail": stdout[-4000:],
        }
        if code == 0:
            break
    print(f"  [{'OK  ' if result['check']['ok'] else 'WARN'}] "
          f"{result['check']['command']}：{result['check']['summary']}")

    print("  [..  ] 运行 python selfcheck.py --mutation-demo 收集判别力证据……")
    code, stdout, stderr = _run_command_detailed(["selfcheck.py", "--mutation-demo"])
    caught = stdout.count("[CAUGHT]")
    missed = stdout.count("[MISSED]")
    summary = f"{caught} 个 [CAUGHT] / {missed} 个 [MISSED]"
    if code != 0 and caught == 0:
        summary = f"退出码 {code}" + (f"；{stderr.strip().splitlines()[-1][:120]}"
                                      if stderr.strip() else "")
    result["mutation"] = {
        "ok": code == 0 and caught >= 3,
        "command": "python selfcheck.py --mutation-demo",
        "summary": summary,
        "detail": stdout[-4000:],
    }
    print(f"  [{'OK  ' if result['mutation']['ok'] else 'WARN'}] "
          f"{result['mutation']['summary']}")
    return result


# ----------------------------------------------------------------------
# PR 描述（--pr-body）
# ----------------------------------------------------------------------
_STATUS_LABELS = {
    "A": "新增", "??": "新增", "M": "修改", "D": "删除",
    "R": "重命名", "C": "复制", "T": "类型变更", "U": "冲突",
}


def _collect_changes() -> tuple[str, list[tuple[str, str]]]:
    """返回 (变更来源说明, [(状态字母, 路径)])。"""
    proc = _git("status", "--porcelain", "-z", "--untracked-files=all")
    changes: list[tuple[str, str]] = []
    if proc.returncode == 0 and proc.stdout:
        items = proc.stdout.split("\0")
        index = 0
        while index < len(items):
            entry = items[index]
            index += 1
            if not entry or len(entry) < 4:
                continue
            status = entry[:2]
            path = _normalize_rel(entry[3:])
            if status[0] in "RC":
                index += 1  # 跳过被重命名/复制的旧路径
            changes.append((status, path))
        if changes:
            return f"工作区未提交改动（{len(changes)} 个文件）", changes

    # 工作区干净：用最近一次提交的文件清单
    name_status = _git_output("show", "--name-status", "--format=", "HEAD")
    for line in name_status.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        status, path = parts[0].strip(), _normalize_rel(parts[-1])
        changes.append((status, path))
    info = _repo_info()
    source = (f"最近一次提交 {info['head']}（工作区干净，共 {len(changes)} 个文件）"
              if changes else "没有检测到改动")
    return source, changes


def _impact_items(changes: list[tuple[str, str]]) -> list[tuple[bool, str]]:
    paths = [path for _, path in changes]
    has = lambda prefix: any(path == prefix or path.startswith(prefix + "/") for path in paths)  # noqa: E731
    return [
        (has("core"), "core/（P1 数据层 / P2 算法层）"),
        (has("ui/canvas.py") or has("selfcheck.py"), "ui/canvas.py / selfcheck.py（P4 渲染与自检）"),
        (has("ui") and not has("ui/canvas.py"), "ui/（P3 窗口与交互）"),
        (has("data"), "data/（路网数据）"),
        (has("docs") or has("README.md") or has("CONTRIBUTING.md"),
         "docs/ · README.md · CONTRIBUTING.md（文档）"),
        (has(".github"), ".github/（CI 与协作模板）"),
        (has("main.py") or has("run."), "main.py / run.ps1 / run.bat（公共入口）"),
        (has("tools"), "tools/（工具与打包脚本）"),
    ]


def _review_points(changes: list[tuple[str, str]]) -> list[str]:
    paths = [path for _, path in changes]
    has = lambda prefix: any(path == prefix or path.startswith(prefix + "/") for path in paths)  # noqa: E731
    points: list[str] = []
    if has("core"):
        points.append("`core/` 改动：请 P1/P2 负责人确认数据格式与算法口径，"
                      "并附 `python tools/bench.py` 复跑后的数据。")
    if has("ui/canvas.py"):
        points.append("`ui/canvas.py` 改动：确认没有 import `core`、没有 `open()`/`solve()`"
                      "（自检第 10 项会用 AST 扫描），也没有绕过 `CanvasView` 公开接口。")
    if has("ui/window.py"):
        points.append("`ui/window.py` 改动：只调用 `CanvasView` 公开方法，"
                      "不要直接改 `draw_graph` / `_transform` 等私有状态。")
    if has("selfcheck.py"):
        points.append("`selfcheck.py` 改动：新增断言必须能被 `--mutation-demo` 证明有判别力"
                      "（把实现改坏后必须变红）。")
    if has("main.py") or has("run."):
        points.append("`main.py` / 启动脚本是公共入口：GUI、`--check`、`--smoke` 三条路径都要手动跑。")
    if has("docs") or has("README.md") or has("CONTRIBUTING.md"):
        points.append("文档改动：检查相对链接、命令与代码一致；报告数字必须与 `docs/bench.csv`、"
                      "自检输出一致。")
    if has(".github") or has("tools/prepare_github.py"):
        points.append("CI / 工具改动：检查 YAML 缩进与 `on:` 触发分支，命令要和本地一致；"
                      "本地先跑 `python tools/prepare_github.py --check`。")
    if not points:
        points.append("常规改动：按 `CONTRIBUTING.md` 的自检闸门跑一遍，附自检输出截图。")
    points.append("合并前确认：GitHub Actions「自检闸门」绿、至少 1 人 review、"
                  "没有把 `_smoke/`、`__pycache__/`、大文件提交进来。")
    return points


def _screenshot_links() -> list[str]:
    candidates = [
        ("docs/figures/fig3-1_ui.png", "主界面截图（图 3-1）"),
        ("docs/figures/fig_p4_demo_path.png", "10 站演示路径（图 4-1）"),
        ("docs/figures/fig_p4_beijing_path.png", "134 站北京路径（图 4-2）"),
        ("docs/figures/fig_p4_zoom.png", "缩放后命中（图 4-3）"),
        ("docs/figures/fig4-4_expanded.png", "扩展节点数对比（图 4-4）"),
        ("docs/P4-演示动画.gif", "自动录制的界面演示 GIF"),
    ]
    lines = []
    for rel, label in candidates:
        if (PROJECT_ROOT / rel).is_file():
            lines.append(f"- [{label}]({rel})")
    lines.append("- 自检输出截图：请在 PowerShell 里跑 `python main.py --check` 后截图，"
                 "直接粘贴到 PR 评论（图片会自动上传到 GitHub）。")
    return lines


def run_pr_body(no_verify: bool = False) -> int:
    print("=" * 82)
    print("生成 PR 描述 → dist/PR_BODY.md")
    print("=" * 82)
    info = _repo_info()
    source, changes = _collect_changes()
    evidence = {"check": None, "mutation": None}
    if no_verify:
        print("  [INFO] --no-verify：不运行自检，PR 里的自检结果留作勾选模板")
    else:
        evidence = _probe_selfcheck()

    if evidence["check"]:
        mark = "[x]" if evidence["check"]["ok"] else "[ ]"
        check_line = (f"- {mark} `{evidence['check']['command']}` → "
                      f"{evidence['check']['summary']}")
        if not evidence["check"]["ok"]:
            check_line += "（生成时该项未通过，请修复后再提交 PR）"
    else:
        check_line = ("- [ ] `python main.py --check` → 应为 10 通过 / 0 失败 / 0 跳过"
                      "（`--no-verify` 生成，未运行）")

    if evidence["mutation"]:
        mark = "[x]" if evidence["mutation"]["ok"] else "[ ]"
        mutation_line = (f"- {mark} `{evidence['mutation']['command']}` → "
                         f"{evidence['mutation']['summary']}")
        if not evidence["mutation"]["ok"]:
            mutation_line += "（生成时未通过，请修复后再提交 PR）"
    else:
        mutation_line = ("- [ ] `python selfcheck.py --mutation-demo` → 应为 3 个 `[CAUGHT]`"
                         "（`--no-verify` 生成，未运行）")

    # 受影响文件表
    file_rows = []
    for status, path in changes[:80]:
        label = _STATUS_LABELS.get(status, status.strip() or "变更")
        file_rows.append(f"| {label} | `{path}` |")
    if len(changes) > 80:
        file_rows.append(f"| …… | 另有 {len(changes) - 80} 个文件，见 `git status` |")

    impact_lines = []
    for affected, label in _impact_items(changes):
        impact_lines.append(f"- {'[x]' if affected else '[ ]'} {label}")
    review_lines = [f"{index}. {text}" for index, text in enumerate(_review_points(changes), start=1)]

    title_hint = "feat: <一句话说明这个 PR 做了什么>"
    body = f"""# {title_hint}

> 本文件由 `python tools/prepare_github.py --pr-body` 于 {_now_text()} 自动生成。
> 提交 PR 时把**整段内容**粘进 GitHub 的 PR 描述，再按需补充截图和 Issue 编号。

## 1. 改动摘要

<!-- 用 1~3 句话说明：改了什么、为什么改、怎么验证 -->
- 变更来源：{source}
- 分支：`{info['branch']}` ｜ 提交：`{info['head']}`
- 一句话摘要：<在这里补一句>

## 2. 关联 Issue

Closes #<Issue 编号>

## 3. 自检结果（生成时实际运行，可重新跑）

{check_line}
{mutation_line}
- [ ] `python tools/prepare_github.py --check` 通过（仓库体检）
- [ ] 截图 / 导出图已人工目检：站名零重叠、路径颜色可辨、没有桌面穿帮
- [ ] GitHub Actions「自检闸门」通过（PR 页面底部可见）

## 4. 涉及文件（{len(changes)} 个）

| 状态 | 文件 |
| --- | --- |
{chr(10).join(file_rows) if file_rows else '| - | 无文件变更 |'}

## 5. 影响范围

{chr(10).join(impact_lines)}

## 6. 审查要点

{chr(10).join(review_lines)}

## 7. 截图与证据

{chr(10).join(_screenshot_links())}

## 8. 合并方式

- 合并方式：**Squash merge**（保持 main 线性、一个 PR 一个提交）
- 合并后删除源分支；本地 `git switch main` + `git pull` 同步
- 详细规范见 [`CONTRIBUTING.md`](CONTRIBUTING.md)
"""
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    PR_BODY_PATH.write_text(body, encoding="utf-8")
    print(f"  [OK  ] 已写入：{PR_BODY_PATH}")
    print(f"  [INFO] 变更来源：{source}")
    print(f"  [INFO] 涉及文件：{len(changes)} 个；审查要点 {len(review_lines)} 条")
    print("  [INFO] 使用方法：复制 dist/PR_BODY.md 内容到 GitHub PR 描述，"
          "补上 Issue 编号和一句话摘要即可。")
    return 0


# ----------------------------------------------------------------------
# git 操作（--commit / --remote / --push）：默认不执行，需管理员手动跑
# ----------------------------------------------------------------------
def run_commit(message: str) -> int:
    print("=" * 82)
    print("提交本地改动（先体检，再 git add -A + git commit，不 push）")
    print("=" * 82)
    if not message.strip():
        print("  [FAIL] --commit 必须配合 -m \"提交信息\" 使用，例如：")
        print("         python tools/prepare_github.py --commit -m \"feat: 完成 GitHub 协作包\"")
        return 2
    code = run_check()
    if code != 0:
        print("\n  [FAIL] 仓库体检未通过，已中止提交（先修红项再提交）。")
        return 1

    print("\n  [..  ] git add -A")
    proc = _git("add", "-A")
    if proc.returncode != 0:
        print(f"  [FAIL] git add 失败：{proc.stderr.strip()}")
        return 1
    staged = _git("diff", "--cached", "--name-only")
    if staged.returncode == 0 and not staged.stdout.strip():
        print("  [INFO] 没有需要提交的改动（工作区已干净）。")
        return 0
    print("  [..  ] git commit -m ...")
    proc = _git("commit", "-m", message)
    if proc.returncode != 0:
        print(f"  [FAIL] git commit 失败：{proc.stderr.strip() or proc.stdout.strip()}")
        return 1
    head = _git_output("rev-parse", "--short", "HEAD").strip()
    print(f"  [OK  ] 已提交：{head}  {message}")
    print("  [INFO] 尚未 push；确认后运行：python tools/prepare_github.py --push")
    return 0


def run_remote(url: str | None) -> int:
    print("=" * 82)
    print("配置 GitHub remote（origin）")
    print("=" * 82)
    proc = _git("remote", "get-url", "origin")
    existing = proc.stdout.strip() if proc.returncode == 0 else ""
    if url is None or not url.strip():
        remotes = _git_output("remote", "-v").strip()
        if remotes:
            print("  [INFO] 当前 remote：")
            for line in remotes.splitlines():
                print(f"         {line}")
        else:
            print("  [INFO] 当前还没有配置 remote。")
            print("  [INFO] 用法：python tools/prepare_github.py "
                  "--remote https://github.com/<账号>/metro-p4.git")
        return 0

    url = url.strip()
    if existing:
        print(f"  [INFO] 已存在 origin：{existing}")
        print("  [INFO] 保留现有配置，未做修改。")
        print("  [INFO] 如需换地址，请手动执行：git remote set-url origin " + url)
        return 0
    print(f"  [..  ] 添加 origin -> {url}")
    proc = _git("remote", "add", "origin", url)
    if proc.returncode != 0:
        print(f"  [FAIL] 添加 remote 失败：{proc.stderr.strip()}")
        return 1
    print("  [OK  ] origin 已添加。下一步：")
    print("         1) python tools/prepare_github.py --check --strict")
    print("         2) python tools/prepare_github.py --push")
    return 0


def run_push() -> int:
    print("=" * 82)
    print("推送到 GitHub（git push -u origin main）")
    print("=" * 82)
    proc = _git("remote", "get-url", "origin")
    if proc.returncode != 0:
        print("  [FAIL] 还没有配置 origin remote，请先运行：")
        print("         python tools/prepare_github.py --remote https://github.com/<账号>/metro-p4.git")
        return 1
    url = proc.stdout.strip()
    print(f"  [INFO] origin：{url}")
    print("  [..  ] git push -u origin main ……")
    proc = _git("push", "-u", "origin", "main", timeout=300)
    if proc.returncode == 0:
        print("  [OK  ] 推送成功。打开仓库页面确认文件齐全，"
              "再按 docs/GitHub协作与上传指南.md 保护 main 分支。")
        return 0
    detail = (proc.stderr or proc.stdout).strip()
    print("  [FAIL] 推送失败。常见原因：")
    print("         1) 还没登录 GitHub / 凭据过期：Windows 会弹窗登录，"
          "或用 Personal Access Token 作为密码；")
    print("         2) 仓库地址写错或没有写权限（请管理员邀请你为 Write 权限）；")
    print("         3) 远程已有提交、本地又改过历史：先 git pull --rebase origin main；")
    print("         4) 网络被墙 / 代理配置问题。")
    if detail:
        print("  ---- git 原始输出 ----")
        for line in detail.splitlines()[-12:]:
            print(f"         {line}")
    return 1


# ----------------------------------------------------------------------
# 命令行入口
# ----------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="prepare_github.py",
        description="metro-p4 GitHub 上传准备：仓库体检、manifest、zip 打包、PR 描述。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例：\n"
            "  python tools/prepare_github.py --check\n"
            "  python tools/prepare_github.py --all\n"
            "  python tools/prepare_github.py --bundle\n"
            "  python tools/prepare_github.py --commit -m \"feat: GitHub 协作包\"\n"
        ),
    )
    parser.add_argument("--check", action="store_true",
                        help="仓库体检（默认命令）：必需文件 / 禁止入库 / 大文件 / 绝对路径 / CI")
    parser.add_argument("--strict", action="store_true",
                        help="配合 --check：把提醒项也算失败（最终上传前建议使用）")
    parser.add_argument("--manifest", action="store_true",
                        help="生成 dist/manifest.json（路径 / 大小 / SHA-256）")
    parser.add_argument("--bundle", action="store_true",
                        help="生成 dist/metro-p4-github-YYYYMMDD.zip 并回读校验")
    parser.add_argument("--stats", action="store_true",
                        help="打印 Python 行数排行、文档数、图片数、自检可运行性")
    parser.add_argument("--commit", action="store_true",
                        help="先体检，再 git add -A + git commit -m（不 push）")
    parser.add_argument("-m", "--message", default="",
                        help="--commit 的提交信息，例如 \"feat: 完成 P4 协作包\"")
    parser.add_argument("--remote", nargs="?", const="", default=None, metavar="URL",
                        help="没有 origin 时添加 origin；不给 URL 则只打印当前 remote")
    parser.add_argument("--push", action="store_true",
                        help="git push -u origin main（默认不执行，需管理员手动跑）")
    parser.add_argument("--pr-body", action="store_true",
                        help="生成 dist/PR_BODY.md（含实际自检结果、涉及文件、审查要点）")
    parser.add_argument("--no-verify", action="store_true",
                        help="配合 --pr-body：不跑自检，生成待勾选模板（更快）")
    parser.add_argument("--all", action="store_true",
                        help="check + manifest + bundle + pr-body")
    parser.add_argument("--version", action="store_true", help="打印版本")
    return parser


def _resolve_actions(args: argparse.Namespace) -> list[str]:
    if args.all:
        return ["check", "manifest", "bundle", "pr_body"]
    actions: list[str] = []
    if args.check:
        actions.append("check")
    if args.stats:
        actions.append("stats")
    if args.manifest:
        actions.append("manifest")
    if args.bundle:
        actions.append("bundle")
    if args.pr_body:
        actions.append("pr_body")
    if args.commit:
        actions.append("commit")
    if args.remote is not None:
        actions.append("remote")
    if args.push:
        actions.append("push")
    if not actions:
        actions = ["check"]
    return actions


def main(argv: list[str] | None = None) -> int:
    _reconfigure_stdout()
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.version:
        print("prepare_github.py v1.0（metro-p4 P4 工程化）")
        print(f"仓库：{PROJECT_ROOT}")
        return 0

    actions = _resolve_actions(args)
    codes: list[int] = []
    failures = 0
    started = time.perf_counter()
    for action in actions:
        try:
            if action == "check":
                code = run_check(strict=args.strict)
            elif action == "stats":
                code = run_stats()
            elif action == "manifest":
                code = run_manifest()
            elif action == "bundle":
                code = run_bundle()
            elif action == "pr_body":
                code = run_pr_body(no_verify=args.no_verify)
            elif action == "commit":
                code = run_commit(args.message)
            elif action == "remote":
                code = run_remote(args.remote)
            elif action == "push":
                code = run_push()
            else:  # pragma: no cover - 不会发生
                print(f"[错误] 未知动作：{action}")
                code = 1
        except PrepareError as exc:
            print(f"\n[错误] {exc}")
            code = 1
        codes.append(code)
        if code != 0:
            failures += 1
            # 体检不过就别继续打包了：避免把红仓库打成交付包
            if action == "check" and len(actions) > 1:
                print("\n[中止] 仓库体检未通过，后续打包 / 生成步骤已跳过。")
                break
        print()

    elapsed = (time.perf_counter() - started) * 1000
    if len(actions) > 1 or failures:
        print(f"本次执行动作：{', '.join(actions)}；失败 {failures} 个；"
              f"总用时 {elapsed:.0f} ms")
    if failures and all(code in (0, 2) for code in codes):
        return 2  # 纯参数用法错误
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
