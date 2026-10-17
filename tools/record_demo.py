"""自动录制 P4 演示 GIF（可选 MP4）。

为什么需要它
------------
任务书 P4-09 要求一条 2 分钟演示视频。人工录屏当然最自然，但调试阶段经常
需要“改完立刻看效果”。这个脚本把真实窗口驱动一遍：

    加载 134 站 → 搜索 → 动画（可暂停/继续/跳过）→ 缩放/平移/悬停 → 收尾

每一步都截真实窗口画面，拼成动画 GIF。机器上装了 ffmpeg 时，加 `--mp4` 还能
顺手转成 mp4；没有 ffmpeg 也能交付 GIF（浏览器/PPT 都能直接放）。

用法
----
    python tools/record_demo.py
    python tools/record_demo.py --out docs/P4-演示动画.gif
    python tools/record_demo.py --mp4 docs/P4-演示录屏.mp4
    python tools/record_demo.py --data data/demo_city.json --fast

注意
----
* 需要图形界面（Windows 桌面）；无显示器环境会失败；
* 录制时窗口会置顶十几秒，请不要在这段时间操作鼠标键盘；
* 字幕条是脚本画上去的，不依赖系统录屏软件。
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
import types
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ui.dpi import enable_high_dpi  # noqa: E402

enable_high_dpi()  # 必须在创建 Tk 窗口之前调用，否则截图会偏

import tkinter as tk  # noqa: E402
from PIL import Image, ImageDraw, ImageFont, ImageGrab  # noqa: E402

from core import load_dataset, solve  # noqa: E402
from ui.window import MetroNavWindow  # noqa: E402

DEFAULT_DATA = PROJECT_ROOT / "data" / "beijing_metro.json"
DEFAULT_GIF = PROJECT_ROOT / "docs" / "P4-演示动画.gif"
SMOKE_DIR = PROJECT_ROOT / "_smoke"


# ----------------------------------------------------------------------
# 截图与字幕
# ----------------------------------------------------------------------
def load_font(size: int, bold: bool = False):
    """加载中文字体；找不到就退回 Pillow 默认字体（可能出现方框）。"""
    candidates = [
        ("C:/Windows/Fonts/msyhbd.ttc" if bold else "C:/Windows/Fonts/msyh.ttc", 0),
        ("C:/Windows/Fonts/simhei.ttf", 0),
        ("C:/Windows/Fonts/simsun.ttc", 0),
    ]
    for path, index in candidates:
        try:
            return ImageFont.truetype(path, size=size, index=index)
        except OSError:
            continue
    return ImageFont.load_default()


def grab_window(window: tk.Misc, caption: str, target_width: int) -> Image.Image:
    """截取整个窗口，并在底部加一条深色字幕。"""
    window.update_idletasks()
    window.update()
    x, y = window.winfo_rootx(), window.winfo_rooty()
    width, height = window.winfo_width(), window.winfo_height()
    image = ImageGrab.grab(bbox=(x, y, x + width, y + height), all_screens=True)
    image = image.convert("RGB")

    if target_width and image.width != target_width:
        scale = target_width / image.width
        image = image.resize(
            (target_width, max(1, int(round(image.height * scale)))),
            Image.Resampling.LANCZOS,
        )

    bar_h = max(36, int(image.height * 0.052))
    output = Image.new("RGB", (image.width, image.height + bar_h), "#0B1220")
    output.paste(image, (0, 0))
    draw = ImageDraw.Draw(output)
    draw.rectangle((0, image.height, image.width, image.height + bar_h), fill="#0B1220")
    draw.rectangle((0, image.height, 5, image.height + bar_h), fill="#2563EB")
    draw.text(
        (16, image.height + bar_h / 2), caption,
        fill="#F8FAFC", font=load_font(max(14, int(bar_h * 0.45))), anchor="lm",
    )
    return output


class Recorder:
    """收集帧和每帧的停留时间。"""

    def __init__(self, window: tk.Misc, target_width: int) -> None:
        self.window = window
        self.target_width = target_width
        self.frames: list[Image.Image] = []
        self.durations: list[int] = []

    def shot(self, caption: str, duration_ms: int = 220) -> None:
        frame = grab_window(self.window, caption, self.target_width)
        # 缩放后各帧尺寸必须完全一致，否则 GIF 会报错
        if self.frames and frame.size != self.frames[0].size:
            frame = frame.resize(self.frames[0].size, Image.Resampling.LANCZOS)
        self.frames.append(frame)
        self.durations.append(max(40, int(duration_ms)))

    def pump(self, seconds: float, caption: str, every: float = 0.16,
             duration_ms: int = 150) -> None:
        """在 seconds 秒内持续泵 Tk 事件，并每隔 every 秒截一帧。"""
        deadline = time.perf_counter() + seconds
        next_shot = 0.0
        while time.perf_counter() < deadline:
            self.window.update()
            now = time.perf_counter()
            if now >= next_shot:
                self.shot(caption, duration_ms)
                next_shot = now + every
            time.sleep(0.015)


# ----------------------------------------------------------------------
# 挑选演示起终点
# ----------------------------------------------------------------------
def pick_pair(dataset) -> tuple[str, str]:
    """优先用演示数据里的固定对，否则找一对连通且换乘≥1 的站。"""
    graph = dataset.build_graph()
    preferred = [("S001", "S061"), ("S1", "S8")]
    for start, end in preferred:
        if start in graph.stations and end in graph.stations:
            result = solve(graph, "Dijkstra", start, end)
            if result.found:
                return start, end
    ids = list(graph.stations)
    first = ids[0]
    for other in ids[1:]:
        result = solve(graph, "Dijkstra", first, other)
        if result.found:
            return first, other
    return ids[0], ids[-1]


def station_name(dataset, sid: str) -> str:
    station = dataset.stations.get(sid)
    return station.name if station else sid


# ----------------------------------------------------------------------
# 主流程
# ----------------------------------------------------------------------
def record(data_path: Path, target_width: int,
           fast: bool) -> tuple[list[Image.Image], list[int]]:
    dataset = load_dataset(str(data_path))
    window = MetroNavWindow(str(data_path), silent_load=True)
    window.geometry("1440x900+20+20")
    window.update_idletasks()
    window.update()

    # 等窗口真正合成到屏幕上，避免第一帧截到桌面
    deadline = time.perf_counter() + 0.8
    while time.perf_counter() < deadline:
        window.update()
        time.sleep(0.02)
    window.lift()
    window.attributes("-topmost", True)
    window.update()

    recorder = Recorder(window, target_width)
    start, end = pick_pair(dataset)
    start_name, end_name = station_name(dataset, start), station_name(dataset, end)

    try:
        recorder.shot(
            f"城市交通路径导航系统 · {len(dataset.stations)} 站 / {len(dataset.lines)} 条线路",
            900,
        )
        recorder.pump(0.5 if fast else 1.0, "P4 渲染与工程化：画布 / 自检 / 导出", 0.5, 500)

        # 1) 搜索
        window.start_var.set(start_name)
        window.end_var.set(end_name)
        window.speed_var.set("1×")
        window.run_search()
        window.update()
        recorder.pump(0.6 if fast else 1.2,
                      f"Dijkstra：{start_name} → {end_name}", 0.5, 700)

        result = window.result
        if result is not None and result.found:
            # 2) 动画（1×），中途暂停再继续，最后跳过
            window.run_search(animate=True)
            recorder.pump(1.1 if fast else 1.8,
                          "搜索动画：逐帧点亮扩展节点", 0.16, 130)
            window.toggle_pause()
            recorder.pump(0.35 if fast else 0.8, "动画已暂停（数值不变）", 0.35, 500)
            window.toggle_pause()
            recorder.pump(0.5 if fast else 1.0, "继续播放", 0.18, 150)
            window.skip_animation()
            recorder.pump(0.5 if fast else 1.0, "跳过动画：直接显示最终路径", 0.5, 600)

            # 3) 缩放 / 平移 / 悬停
            window.canvas.set_zoom(2.0)
            window.update()
            recorder.pump(0.5 if fast else 1.0,
                          "滚轮缩放 2×：以光标为锚点，站名重新避让", 0.5, 550)
            window.canvas.pan_by(-160, 70)
            window.update()
            recorder.pump(0.5 if fast else 0.9, "拖拽平移：地图跟手，图例不动", 0.5, 500)
            window.canvas.reset_view()
            window.update()

            # 模拟鼠标悬停到路径上的一个中间站
            path_stations = result.stations
            hover_sid = path_stations[len(path_stations) // 2]
            station = dataset.stations[hover_sid]
            sx, sy = window.canvas.world_to_screen(station.x, station.y)
            window.canvas._on_motion(types.SimpleNamespace(x=int(sx), y=int(sy)))
            window.canvas._update_hover()
            window.update()
            recorder.pump(0.5 if fast else 1.0,
                          f"悬停高亮：{station.name}（{len(dataset.stations)} 站中任意站点可点）",
                          0.35, 550)

        recorder.shot("自检 10/10 · README 5 分钟可复现 · 导出 PNG/PS", 1000)
    finally:
        window.attributes("-topmost", False)
        window.destroy()
    return recorder.frames, recorder.durations


# ----------------------------------------------------------------------
# 保存
# ----------------------------------------------------------------------
def save_gif(frames: list[Image.Image], durations: list[int],
             path: Path) -> tuple[Path, int]:
    path.parent.mkdir(parents=True, exist_ok=True)
    # 注意：不要开 optimize，也不要用 disposal=2。
    # Pillow 在“只写变化区域 + 透明帧”时，某些播放器会把没重画的区域显示成黑色，
    # 这里宁可文件大一点，也保证每一帧都是完整画面。
    frames[0].save(
        path,
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=0,
        optimize=False,
        disposal=1,
    )
    # GIF 编码器可能合并完全相同的相邻帧，读回来报告“实际帧数”更诚实
    with Image.open(path) as check:
        actual_frames = getattr(check, "n_frames", len(frames))
    return path, actual_frames


def save_mp4(frames: list[Image.Image], path: Path) -> bool:
    """有 ffmpeg 才转 mp4；返回是否成功。"""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        print("[VIDEO] 没有找到 ffmpeg，跳过 MP4；GIF 已生成。")
        print("        装好 ffmpeg 后重新运行：python tools/record_demo.py --mp4 输出.mp4")
        return False

    frame_dir = SMOKE_DIR / "demo_frames"
    if frame_dir.exists():
        shutil.rmtree(frame_dir)
    frame_dir.mkdir(parents=True, exist_ok=True)
    for index, frame in enumerate(frames):
        frame.save(frame_dir / f"frame_{index:04d}.png")
    path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        ffmpeg, "-y", "-framerate", "8",
        "-i", str(frame_dir / "frame_%04d.png"),
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
        str(path),
    ]
    print("[VIDEO] 正在编码 MP4 …")
    process = subprocess.run(command, capture_output=True, text=True)
    if process.returncode != 0:
        print("[VIDEO] ffmpeg 编码失败：")
        print((process.stderr or "")[-800:])
        return False
    shutil.rmtree(frame_dir, ignore_errors=True)
    print(f"[VIDEO] MP4 已生成：{path}")
    return True


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="自动录制 P4 演示 GIF/MP4")
    parser.add_argument("--data", default=str(DEFAULT_DATA), help="路网数据文件")
    parser.add_argument("--out", default=str(DEFAULT_GIF), help="输出 GIF 路径")
    parser.add_argument("--mp4", default=None, help="同时尝试输出 MP4（需 ffmpeg）")
    parser.add_argument("--width", type=int, default=1200, help="GIF 宽度，默认 1200")
    parser.add_argument("--fast", action="store_true", help="快录模式，停留时间更短")
    parser.add_argument("--keep-frames", action="store_true",
                        help="把原始帧另存到 _smoke/demo_frames 便于检查")
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    args = build_parser().parse_args(argv)
    data_path = Path(args.data)
    if not data_path.is_absolute():
        data_path = PROJECT_ROOT / data_path
    if not data_path.is_file():
        print(f"[ERROR] 找不到数据文件：{data_path}", file=sys.stderr)
        return 1

    print("[VIDEO] 开始录制（窗口会置顶约 15 秒）…")
    frames, durations = record(data_path, args.width, args.fast)
    if args.keep_frames:
        raw_dir = SMOKE_DIR / "demo_frames"
        if raw_dir.exists():
            shutil.rmtree(raw_dir)
        raw_dir.mkdir(parents=True, exist_ok=True)
        for index, frame in enumerate(frames):
            frame.save(raw_dir / f"raw_{index:03d}.png")
        print(f"[VIDEO] 原始帧已保存：{raw_dir}")
    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = PROJECT_ROOT / out_path
    _, actual_frames = save_gif(frames, durations, out_path)
    size_mb = out_path.stat().st_size / 1024 / 1024
    print(f"[VIDEO] GIF 已生成：{out_path}（{actual_frames} 帧，{size_mb:.1f} MB）")

    if args.mp4:
        mp4_path = Path(args.mp4)
        if not mp4_path.is_absolute():
            mp4_path = PROJECT_ROOT / mp4_path
        save_mp4(frames, mp4_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
