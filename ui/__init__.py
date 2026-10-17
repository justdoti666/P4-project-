"""界面包：P4 画布组件 + P3 窗口的最小可运行版本。

P4 的交付重点是 ``canvas.CanvasView``；这里的 ``window.py`` 只是为了让
``main.py`` 能直接跑起来、让 ``--smoke`` 有地方嵌入画布。真实小组里
这个文件由 P3 负责，P4 只通过下面 6 个方法调用画布，不碰按钮逻辑：

    bind_click / show_path / animate / reset / export / toggle_pause
"""

from .canvas import CanvasView, LabelBox, PathMetrics, ViewTransform

__all__ = ["CanvasView", "LabelBox", "PathMetrics", "ViewTransform"]
