"""Windows 高分屏适配（一个小工具）。

为什么需要它
------------
Windows 在 125% / 150% 缩放时，Tk 拿到的是“逻辑像素”，而 Pillow 的
``ImageGrab`` 抓屏拿到的是“物理像素”。如果进程没有声明 DPI 感知，
导出 PNG 时用 Tk 的坐标去截屏，就会截偏（甚至截到桌面和标题栏）。

这个函数在**创建任何 Tk 窗口之前**调用一次即可。其它系统直接跳过。
"""

from __future__ import annotations

import sys

__all__ = ["enable_high_dpi"]


def enable_high_dpi() -> None:
    """声明进程为 DPI 感知，让 Tk 坐标与截图像素对齐。"""
    if sys.platform != "win32":
        return
    try:
        import ctypes

        # 1 = PROCESS_SYSTEM_DPI_AWARE；Win8.1 及以上可用
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
        return
    except Exception:
        pass
    try:
        import ctypes

        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        # 极老的系统或受限环境：不影响程序运行，只是截图可能偏
        pass
