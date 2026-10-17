"""城市交通路径导航系统 · 程序入口（P4 工程化）。

常用命令
--------
    python main.py                      # 打开图形界面
    python main.py --check              # 跑 10 项自检，退出码就是闸门
    python main.py --check --verbose    # 自检并打印每一项的细节
    python main.py --smoke _smoke/a.ps  # 界面冒烟 + 自动导出画布
    python main.py --smoke _smoke/a.png
    python main.py --data data/demo_city.json

设计说明
--------
* 所有路径都基于本文件所在目录，不依赖“从哪个目录启动”；
* ``--check`` 不打开窗口（除了最后一项 GUI 冒烟），适合当合并闸门；
* ``--smoke`` 会自动选一对连通站点、搜索、动画、跳过、导出，
  用于验收“界面、动画、导出”三条链路是否完整。
"""

from __future__ import annotations

import argparse
import os
import sys
import traceback

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

DEFAULT_DATA = os.path.join(PROJECT_ROOT, "data", "beijing_metro.json")
DEFAULT_SMOKE = os.path.join(PROJECT_ROOT, "_smoke", "smoke.png")


def enable_high_dpi() -> None:
    """Windows 高分屏下声明 DPI 感知（必须在创建 Tk 窗口之前调用）。

    具体实现放在 ``ui/dpi.py``，自检脚本和导出工具共用同一份，
    避免三处代码各写一遍、以后改漏。
    """
    from ui.dpi import enable_high_dpi as _enable

    _enable()


def run_check(argv: list[str]) -> int:
    """执行自检矩阵；返回 0（全绿）或 1（有红项）。"""
    import selfcheck

    return selfcheck.run_cli(argv)


def run_smoke(data_path: str, export_path: str) -> int:
    """界面冒烟：完整走一遍 加载 -> 搜索 -> 动画 -> 跳过 -> 导出。"""
    enable_high_dpi()
    from ui.window import MetroNavWindow

    window = MetroNavWindow(data_path, silent_load=True)
    try:
        if window.graph is None:
            print("[SMOKE] 数据加载失败，无法继续", file=sys.stderr)
            return 1
        window.update_idletasks()
        window.update()
        info = window.run_smoke(export_path)
        print("[SMOKE] 通过")
        print(f"        起点/终点 : {info['start']} -> {info['end']}")
        print(
            "        统计      : "
            f"{info['metrics']['algorithm']} / "
            f"{info['metrics']['time_min']:.1f} min / "
            f"{info['metrics']['distance_km']:.1f} km / "
            f"换乘 {info['metrics']['transfers']} 次 / "
            f"扩展 {info['metrics']['expanded']}"
        )
        print(
            f"        站名      : 已画 {info['station_labels']} 个，"
            f"省略 {info['hidden_labels']} 个；"
            f"分段标注省略 {info['hidden_segment_labels']} 个"
        )
        print(f"        导出文件  : {info['export']}")
        return 0
    except Exception:
        print("[SMOKE] 失败：", file=sys.stderr)
        traceback.print_exc()
        return 1
    finally:
        try:
            window.destroy()
        except Exception:
            pass


def run_gui(data_path: str | None) -> int:
    enable_high_dpi()
    from ui.window import MetroNavWindow

    window = MetroNavWindow(data_path or DEFAULT_DATA)
    if window.graph is None:
        # 默认数据坏了也要让窗口开着，方便用户点“打开数据…”换一份
        window.status_var.set("默认数据加载失败，请用右上角「打开数据…」选择文件")
    window.mainloop()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="城市交通路径导航系统（数据结构课程实践 · 选题 A）",
    )
    parser.add_argument("--data", default=None,
                        help="路网数据文件（.json 或 .txt），默认 data/beijing_metro.json")
    parser.add_argument("--check", action="store_true",
                        help="运行 10 项自检（退出码 0=全绿，1=有失败）")
    parser.add_argument("--verbose", action="store_true", help="自检时打印每项细节")
    parser.add_argument("--no-gui", action="store_true",
                        help="自检时跳过 GUI 冒烟（无显示环境使用）")
    parser.add_argument("--smoke", nargs="?", const=DEFAULT_SMOKE, default=None,
                        metavar="图片路径",
                        help="界面冒烟并导出画布，默认 _smoke/smoke.png")
    parser.add_argument("--version", action="store_true", help="打印版本信息")
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.version:
        print("城市交通路径导航系统 v1.0（P4 渲染与工程化）")
        print("Python", sys.version.split()[0], "· Tkinter 画布")
        return 0

    if args.check:
        check_args: list[str] = []
        if args.verbose:
            check_args.append("--verbose")
        if args.no_gui:
            check_args.append("--no-gui")
        return run_check(check_args)

    data_path = os.path.abspath(args.data) if args.data else DEFAULT_DATA

    if args.smoke:
        export_path = os.path.abspath(args.smoke)
        os.makedirs(os.path.dirname(export_path), exist_ok=True)
        return run_smoke(data_path, export_path)

    return run_gui(data_path if args.data else None)


if __name__ == "__main__":
    sys.exit(main())
