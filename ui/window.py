"""最小可运行窗口：把 ``CanvasView`` 嵌进去，验证 P3 的调用约定。

说明
----
任务书把窗口/按钮划给 P3，P4 只负责画布。但课程交付需要一个能直接
``python main.py`` 打开的完整程序，所以这里写了一个**很薄的 P3 替身**：

* 上面是起点/终点/算法选择；
* 中间是 P4 的 ``CanvasView``；
* 右边显示耗时、里程、换乘、扩展节点和途经站点；
* 所有绘画动作都只调用画布的公开方法，没有一行绘图代码。

这样 P3 拿到 ``ui/canvas.py`` 后，只要把这里的按钮换成他的正式实现即可。
"""

from __future__ import annotations

import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from core import DataFormatError, load_dataset, solve
from ui.canvas import (
    ACCENT,
    ANIM,
    BG,
    BORDER,
    CARD,
    END,
    INK,
    SUB,
    CanvasView,
)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DATA = os.path.join(PROJECT_ROOT, "data", "beijing_metro.json")
DEFAULT_DEMO = os.path.join(PROJECT_ROOT, "data", "demo_city.json")

ALGORITHM_CHOICES = [
    ("Dijkstra · 最快", "Dijkstra"),
    ("A* · 启发式最快", "A*"),
    ("BFS · 最少换乘", "BFS"),
]


class MetroNavWindow(tk.Tk):
    """主窗口（P3 接口的最小实现）。"""

    def __init__(self, data_path: str | None = None, *, silent_load: bool = False) -> None:
        super().__init__()
        self.title("城市交通路径导航系统 · P4 渲染与工程化")
        self.geometry("1440x900+40+30")
        self.minsize(1120, 760)
        self.configure(bg=BG)

        # ---- 运行状态 ----
        self.dataset = None
        self.graph = None
        self.canvas: CanvasView | None = None
        self.result = None
        self._station_name_to_id: dict[str, str] = {}
        self._station_id_to_name: dict[str, str] = {}
        self._click_phase = 0

        # ---- 字体 ----
        family = "Microsoft YaHei UI"
        self.font_title = (family, 16, "bold")
        self.font_sub = (family, 9)
        self.font_body = (family, 10)
        self.font_bold = (family, 10, "bold")
        self.font_small = (family, 9)
        self.font_stat = (family, 15, "bold")

        self._build_ui()
        self._bind_shortcuts()
        if data_path:
            self.load_file(data_path, silent=silent_load)

    # ==================================================================
    # 界面布局
    # ==================================================================
    def _build_ui(self) -> None:
        # ---- 顶部标题 ----
        header = tk.Frame(self, bg="#0B1220", height=84)
        header.pack(fill="x")
        header.pack_propagate(False)
        left = tk.Frame(header, bg="#0B1220")
        left.pack(side="left", padx=22, pady=9)
        tk.Label(left, text="城市交通路径导航系统", bg="#0B1220", fg="#F8FAFC",
                 font=self.font_title).pack(anchor="w")
        tk.Label(left, text="P4 渲染与工程化 · 画布组件 / 自检闸门",
                 bg="#0B1220", fg="#94A3B8", font=self.font_sub).pack(anchor="w")
        tk.Label(header, text="数据结构课程实践 · 选题 A", bg="#1E3A8A",
                 fg="#DBEAFE", font=self.font_small, padx=12, pady=5).pack(
                     side="right", padx=22)

        # ---- 工具栏（两行，避免窄窗口把右侧按钮挤出屏幕）----
        toolbar = tk.Frame(self, bg=CARD)
        toolbar.pack(fill="x", padx=14, pady=(10, 0))
        row1 = tk.Frame(toolbar, bg=CARD)
        row1.pack(fill="x")
        row2 = tk.Frame(toolbar, bg=CARD)
        row2.pack(fill="x")

        def label(parent, text, pad=(14, 4), pady=8):
            tk.Label(parent, text=text, bg=CARD, fg=SUB,
                     font=self.font_small).pack(side="left", padx=pad, pady=pady)

        label(row1, "起点")
        self.start_var = tk.StringVar()
        self.start_box = ttk.Combobox(row1, textvariable=self.start_var,
                                      width=13, state="readonly", font=self.font_body)
        self.start_box.pack(side="left", pady=8)

        tk.Button(row1, text="⇄", command=self.swap_endpoints, bg=CARD, fg=SUB,
                  relief="flat", font=(family_or_default(), 12, "bold"), bd=0,
                  cursor="hand2", width=2).pack(side="left", padx=2)

        label(row1, "终点", (8, 4))
        self.end_var = tk.StringVar()
        self.end_box = ttk.Combobox(row1, textvariable=self.end_var,
                                    width=13, state="readonly", font=self.font_body)
        self.end_box.pack(side="left", pady=8)

        label(row1, "算法", (18, 4))
        self.algo_var = tk.StringVar(value=ALGORITHM_CHOICES[0][0])
        self.algo_box = ttk.Combobox(row1, textvariable=self.algo_var, width=15,
                                     state="readonly", font=self.font_body,
                                     values=[name for name, _ in ALGORITHM_CHOICES])
        self.algo_box.pack(side="left", pady=8)

        self.search_btn = self._button(row1, "搜索", self.run_search, ACCENT, "#FFFFFF")
        self.search_btn.pack(side="left", padx=(18, 4), pady=7)
        self.anim_btn = self._button(row1, "动画", self.run_animation, ANIM, "#FFFFFF")
        self.anim_btn.pack(side="left", padx=4, pady=7)

        tk.Frame(toolbar, bg=BORDER, height=1).pack(fill="x")
        self.pause_btn = self._button(row2, "暂停", self.toggle_pause, CARD, INK)
        self.pause_btn.pack(side="left", padx=(14, 4), pady=6)
        self.skip_btn = self._button(row2, "跳过", self.skip_animation, CARD, SUB)
        self.skip_btn.pack(side="left", padx=4, pady=6)
        self.reset_btn = self._button(row2, "复位", self.reset, CARD, SUB)
        self.reset_btn.pack(side="left", padx=4, pady=6)
        self.export_btn = self._button(row2, "导出图", self.export_dialog, CARD, SUB)
        self.export_btn.pack(side="left", padx=4, pady=6)

        tk.Label(row2, text="动画速度", bg=CARD, fg=SUB,
                 font=self.font_small).pack(side="left", padx=(12, 4), pady=6)
        self.speed_var = tk.StringVar(value="2×")
        self.speed_box = ttk.Combobox(row2, textvariable=self.speed_var, width=4,
                                      state="readonly", font=self.font_small,
                                      values=["1×", "2×", "4×"])
        self.speed_box.pack(side="left", pady=6)

        self.labels_var = tk.BooleanVar(value=True)
        tk.Checkbutton(row2, text="显示站名", variable=self.labels_var,
                       command=self.toggle_labels, bg=CARD, fg=SUB,
                       font=self.font_small, activebackground=CARD).pack(
                           side="left", padx=(14, 6), pady=6)

        self.file_btn = self._button(row2, "打开数据…", self.open_file_dialog, CARD, SUB)
        self.file_btn.pack(side="right", padx=14, pady=6)
        self.data_label = tk.Label(
            row2, text="数据：data/beijing_metro.json", bg=CARD, fg="#94A3B8",
            font=self.font_small,
        )
        self.data_label.pack(side="right", padx=10)

        # ---- 主体：左画布 + 右信息栏 ----
        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=14, pady=12)

        self.canvas_card = tk.Frame(body, bg=CARD, highlightbackground=BORDER,
                                    highlightthickness=1)
        self.canvas_card.pack(side="left", fill="both", expand=True)
        self.canvas_host = tk.Frame(self.canvas_card, bg=BG)
        self.canvas_host.pack(fill="both", expand=True, padx=1, pady=1)
        self.canvas_hint = tk.Label(
            self.canvas_host,
            text="正在加载路网，请稍候…",
            bg=BG, fg=SUB, font=(family_or_default(), 11),
        )
        self.canvas_hint.place(relx=0.5, rely=0.5, anchor="center")

        sidebar = tk.Frame(body, bg=CARD, width=326, highlightbackground=BORDER,
                           highlightthickness=1)
        sidebar.pack(side="right", fill="y", padx=(12, 0))
        sidebar.pack_propagate(False)
        self._build_sidebar(sidebar)

        # ---- 状态栏 ----
        self.status_var = tk.StringVar(value="准备就绪")
        status = tk.Frame(self, bg="#0B1220", height=28)
        status.pack(fill="x")
        status.pack_propagate(False)
        tk.Label(status, textvariable=self.status_var, bg="#0B1220", fg="#CBD5E1",
                 font=self.font_small).pack(side="left", padx=14)
        tk.Label(status, text="滚轮缩放 0.5×–3× · 拖拽平移 · 双击复位 · 点击站点选起终点",
                 bg="#0B1220", fg="#64748B", font=self.font_small).pack(
                     side="right", padx=14)

    def _build_sidebar(self, parent: tk.Frame) -> None:
        head = tk.Frame(parent, bg=CARD)
        head.pack(fill="x", padx=16, pady=(16, 4))
        tk.Label(head, text="搜索结果", bg=CARD, fg=INK,
                 font=self.font_bold).pack(side="left")
        self.algo_badge = tk.Label(head, text="等待搜索", bg="#EFF6FF", fg=ACCENT,
                                   font=self.font_small, padx=8, pady=2)
        self.algo_badge.pack(side="right")

        stats = tk.Frame(parent, bg=CARD)
        stats.pack(fill="x", padx=16, pady=8)
        self.stat_vars: dict[str, tk.StringVar] = {}
        items = [
            ("time", "总耗时", "—"),
            ("distance", "总里程", "—"),
            ("transfers", "换乘次数", "—"),
            ("expanded", "扩展节点", "—"),
            ("stations", "途经站数", "—"),
        ]
        for i, (key, title, default) in enumerate(items):
            cell = tk.Frame(stats, bg="#F8FAFC", highlightbackground=BORDER,
                            highlightthickness=1)
            cell.grid(row=i // 2, column=i % 2, sticky="nsew",
                      padx=(0 if i % 2 == 0 else 6, 0), pady=(0, 6))
            tk.Label(cell, text=title, bg="#F8FAFC", fg=SUB,
                     font=self.font_small).pack(anchor="w", padx=10, pady=(6, 0))
            var = tk.StringVar(value=default)
            self.stat_vars[key] = var
            tk.Label(cell, textvariable=var, bg="#F8FAFC", fg=INK,
                     font=self.font_stat).pack(anchor="w", padx=10, pady=(0, 6))
        stats.grid_columnconfigure(0, weight=1)
        stats.grid_columnconfigure(1, weight=1)

        note = tk.Label(
            parent,
            text="动画与“立即显示”使用同一份 Result，数值完全一致。",
            bg="#ECFDF5", fg="#047857", font=self.font_small,
            wraplength=292, justify="left", padx=10, pady=8,
        )
        note.pack(fill="x", padx=16, pady=(0, 10))

        route_head = tk.Frame(parent, bg=CARD)
        route_head.pack(fill="x", padx=16)
        tk.Label(route_head, text="途经站点", bg=CARD, fg=INK,
                 font=self.font_bold).pack(side="left")
        self.route_count = tk.Label(route_head, text="", bg=CARD, fg=SUB,
                                    font=self.font_small)
        self.route_count.pack(side="right")

        list_frame = tk.Frame(parent, bg=CARD)
        list_frame.pack(fill="both", expand=True, padx=16, pady=(6, 16))
        scrollbar = tk.Scrollbar(list_frame)
        scrollbar.pack(side="right", fill="y")
        self.route_list = tk.Listbox(
            list_frame, bg="#F8FAFC", fg="#334155", font=self.font_small,
            relief="flat", highlightthickness=0, yscrollcommand=scrollbar.set,
            activestyle="none",
        )
        self.route_list.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=self.route_list.yview)

    def _button(self, parent, text, command, bg, fg):
        return tk.Button(
            parent, text=text, command=command, bg=bg, fg=fg,
            activebackground=bg, activeforeground=fg,
            relief="flat", font=self.font_small, bd=0,
            padx=12, pady=6, cursor="hand2",
        )

    def _bind_shortcuts(self) -> None:
        self.bind("<Control-o>", lambda _e: self.open_file_dialog())
        self.bind("<F5>", lambda _e: self.run_search())
        self.bind("<space>", lambda _e: self.toggle_pause())

    # ==================================================================
    # 数据加载
    # ==================================================================
    def load_file(self, path: str, *, silent: bool = False) -> bool:
        """加载路网并创建画布；失败时在状态栏/对话框给出中文原因。"""
        try:
            dataset = load_dataset(path)
            graph = dataset.build_graph()
        except (DataFormatError, ValueError, OSError) as exc:
            self.status_var.set(f"加载失败：{exc}")
            if not silent:
                messagebox.showerror("加载失败", str(exc), parent=self)
            return False

        self.dataset = dataset
        self.graph = graph
        self._station_name_to_id = {s.name: s.id for s in dataset.stations.values()}
        self._station_id_to_name = {s.id: s.name for s in dataset.stations.values()}

        # 重建画布（P3 的正式版本也会在换数据时这样做）
        if self.canvas is not None:
            self.canvas.destroy()
        self.canvas_hint.place_forget()
        # 请求尺寸比窗口小一点，让 pack 把剩余空间分配给它；
        # 否则 700px 的请求高度会把底部状态栏挤出窗口。
        self.canvas = CanvasView(self.canvas_host, graph, width=900, height=560)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind_click(self.on_station_click)
        self.canvas.on_animation_end(self.on_animation_end)

        self._fill_combos()
        self.result = None
        self._clear_stats()
        self.algo_badge.config(text="等待搜索", bg="#EFF6FF", fg=ACCENT)
        self.data_label.config(text=f"数据：{os.path.basename(path)}")
        self.status_var.set(
            f"已加载 {dataset.city}：{len(dataset.stations)} 站 / "
            f"{len(dataset.lines)} 条线路"
        )
        self.update_idletasks()
        self.canvas.after(150, self.canvas._redraw)
        return True

    def _fill_combos(self) -> None:
        names = [s.name for s in self.dataset.stations.values()]
        self.start_box.config(values=names)
        self.end_box.config(values=names)
        self.start_var.set("")
        self.end_var.set("")
        self._click_phase = 0

    def open_file_dialog(self) -> None:
        path = filedialog.askopenfilename(
            parent=self, title="选择路网数据",
            initialdir=os.path.join(PROJECT_ROOT, "data"),
            filetypes=[("路网数据", "*.json *.txt"), ("所有文件", "*.*")],
        )
        if path:
            self.load_file(path)

    # ==================================================================
    # 搜索与展示
    # ==================================================================
    def _resolve_station(self, text: str) -> str | None:
        if not text:
            return None
        return self._station_name_to_id.get(text, text if text in self._station_id_to_name else None)

    def _algorithm_key(self) -> str:
        for name, key in ALGORITHM_CHOICES:
            if name == self.algo_var.get():
                return key
        return "Dijkstra"

    def _speed_level(self) -> int:
        """把界面上的“2×”翻译成 CanvasView 的 speed_level。"""
        try:
            return int(self.speed_var.get().replace("×", "").strip())
        except ValueError:
            return 2

    def run_search(self, animate: bool = False) -> dict | None:
        """执行一次搜索并交给画布显示；返回统计字典。"""
        if self.graph is None or self.canvas is None:
            self.status_var.set("还没有加载路网数据")
            return None
        start = self._resolve_station(self.start_var.get())
        end = self._resolve_station(self.end_var.get())
        if not start or not end:
            self.status_var.set("请先选择起点和终点（也可以直接点击地图上的站点）")
            return None
        if start == end:
            self.status_var.set("起点和终点相同：结果为 0 分钟，可用于边界演示")

        try:
            result = solve(self.graph, self._algorithm_key(), start, end)
        except ValueError as exc:
            self.status_var.set(f"搜索失败：{exc}")
            return None
        self.result = result

        if animate:
            metrics = self.canvas.animate(result, speed_level=self._speed_level())
            self.pause_btn.config(text="暂停")
            self.status_var.set(
                f"搜索动画播放中（{self._speed_level()}×）…空格暂停 / S 跳过"
            )
        else:
            metrics = self.canvas.show_path(result)
            self.status_var.set(self._summary_text(result))
        self._update_stats(result)
        return metrics

    def run_animation(self) -> None:
        self.run_search(animate=True)

    def _summary_text(self, result) -> str:
        if not result.found:
            return f"未找到路径：{result.message or '两站不连通'}"
        return (
            f"{result.algorithm} 搜索完成：{result.total_time:.1f} 分钟 · "
            f"{result.total_distance:.1f} km · 换乘 {result.transfers} 次 · "
            f"扩展 {result.expanded} 个站台"
        )

    def on_station_click(self, station_id: str) -> None:
        """点击站点：第一次设起点，第二次设终点，第三次重新开始。"""
        name = self._station_id_to_name.get(station_id, station_id)
        if self._click_phase == 0 or self._click_phase >= 2:
            self.start_var.set(name)
            self.end_var.set("")
            self._click_phase = 1
            self.status_var.set(f"起点：{name}，再点一个站点作为终点")
        else:
            if name == self.start_var.get():
                self.status_var.set("终点不能和起点相同，请点另一个站点")
                return
            self.end_var.set(name)
            self._click_phase = 2
            self.status_var.set(f"终点：{name}，点「搜索」或「动画」查看结果")

    def toggle_pause(self) -> None:
        if self.canvas is None:
            return
        paused = self.canvas.toggle_pause()
        self.pause_btn.config(text="继续" if paused else "暂停")
        self.status_var.set("动画已暂停" if paused else "动画继续播放")

    def skip_animation(self) -> None:
        if self.canvas is not None and self.canvas.is_animating:
            self.canvas.skip_animation()
            self.pause_btn.config(text="暂停")
            self.status_var.set("已跳过动画，直接显示最终结果")

    def on_animation_end(self) -> None:
        self.pause_btn.config(text="暂停")
        if self.result is not None:
            self.status_var.set(self._summary_text(self.result))

    def reset(self) -> None:
        if self.canvas is not None:
            self.canvas.reset()
        self.result = None
        self._click_phase = 0
        self._clear_stats()
        self.algo_badge.config(text="等待搜索", bg="#EFF6FF", fg=ACCENT)
        self.status_var.set("已复位：路径、缩放、平移全部清除")
        self.pause_btn.config(text="暂停")

    def toggle_labels(self) -> None:
        if self.canvas is not None:
            self.canvas.set_show_labels(bool(self.labels_var.get()))

    def swap_endpoints(self) -> None:
        start, end = self.start_var.get(), self.end_var.get()
        self.start_var.set(end)
        self.end_var.set(start)
        if start and end:
            self.run_search()

    def _clear_stats(self) -> None:
        for var in self.stat_vars.values():
            var.set("—")
        self.route_list.delete(0, "end")
        self.route_count.config(text="")

    def _update_stats(self, result) -> None:
        if not result.found:
            self._clear_stats()
            self.algo_badge.config(text="未找到路径", bg="#FEF2F2", fg=END)
            return
        self.stat_vars["time"].set(f"{result.total_time:.1f} min")
        self.stat_vars["distance"].set(f"{result.total_distance:.1f} km")
        self.stat_vars["transfers"].set(str(result.transfers))
        self.stat_vars["expanded"].set(str(result.expanded))
        self.stat_vars["stations"].set(str(len(result.stations)))
        self.algo_badge.config(
            text=result.algorithm + ("" if result.found else " · 无路径"),
            bg="#EFF6FF", fg=ACCENT,
        )

        self.route_list.delete(0, "end")
        line_names = {line.id: line.name for line in self.dataset.lines.values()}
        transfer_ids = {leg.from_station for leg in result.legs if leg.kind == "transfer"}
        for index, sid in enumerate(result.stations):
            name = self._station_id_to_name.get(sid, sid)
            suffix = "  ⇄ 换乘" if sid in transfer_ids else ""
            self.route_list.insert("end", f"{index + 1:>2}. {name}{suffix}")
        self.route_count.config(text=f"共 {len(result.stations)} 站")
        if line_names:
            used = []
            for leg in result.legs:
                if leg.kind == "ride" and leg.line_id not in used:
                    used.append(leg.line_id)
            if used:
                self.route_list.insert("end", "")
                self.route_list.insert(
                    "end", "乘坐线路：" + " → ".join(line_names.get(lid, lid) for lid in used)
                )

    # ==================================================================
    # 导出
    # ==================================================================
    def export_dialog(self) -> None:
        if self.canvas is None:
            return
        path = filedialog.asksaveasfilename(
            parent=self, title="导出当前画布",
            defaultextension=".png",
            initialfile="metro_canvas.png",
            initialdir=os.path.join(PROJECT_ROOT, "_smoke"),
            filetypes=[("PNG 图片", "*.png"), ("PostScript 矢量图", "*.ps")],
        )
        if not path:
            return
        try:
            saved = self.canvas.export(path)
        except Exception as exc:  # 导出失败要把原因告诉用户
            self.status_var.set(f"导出失败：{exc}")
            messagebox.showerror("导出失败", str(exc), parent=self)
            return
        self.status_var.set(f"已导出：{saved}")

    # ==================================================================
    # 自动化冒烟：main.py --smoke 调用
    # ==================================================================
    def _pick_connected_pair(self) -> tuple[str, str] | None:
        """挑一对连通的起终点：优先用演示数据里的固定对，否则自动试。"""
        stations = list(self.graph.stations)
        preferred = [("S001", "S061"), ("S1", "S8"), ("T1", "T3")]
        for start, end in preferred:
            if start in self.graph.stations and end in self.graph.stations:
                result = solve(self.graph, "Dijkstra", start, end)
                if result.found:
                    return start, end
        if len(stations) < 2:
            return None
        first = stations[0]
        for other in stations[1:]:
            if solve(self.graph, "Dijkstra", first, other).found:
                return first, other
        return None

    def run_smoke(self, export_path: str) -> dict:
        """自动完成：选起终点 -> 搜索 -> 动画 -> 跳过 -> 导出。"""
        if self.graph is None:
            raise RuntimeError("冒烟测试需要先成功加载数据")
        pair = self._pick_connected_pair()
        if pair is None:
            raise RuntimeError("图中找不到连通的两个站点，无法冒烟")
        start, end = pair
        self.update_idletasks()
        self.update()

        self.start_var.set(self._station_id_to_name.get(start, start))
        self.end_var.set(self._station_id_to_name.get(end, end))
        static_metrics = self.run_search(animate=False)
        if not static_metrics or not static_metrics.get("found"):
            raise RuntimeError("静态搜索失败，冒烟不通过")
        self.update()

        anim_metrics = self.run_search(animate=True)
        if anim_metrics != static_metrics:
            raise RuntimeError(
                f"动画与立即结果不一致：{anim_metrics} != {static_metrics}"
            )
        self.update()
        if not self.canvas.is_animating:
            raise RuntimeError("动画没有启动")
        self.canvas.skip_animation()
        self.update()
        if self.canvas.is_animating:
            raise RuntimeError("跳过动画后仍在播放")
        if self.canvas.get_metrics() != static_metrics:
            raise RuntimeError("动画结束后统计值发生变化")

        # 导出前把窗口提到最前面，避免截图被其它窗口遮挡
        self.lift()
        self.attributes("-topmost", True)
        self.update()
        saved = self.canvas.export(export_path)
        self.attributes("-topmost", False)
        self.update()

        return {
            "start": start,
            "end": end,
            "metrics": static_metrics,
            "station_labels": len(self.canvas.station_label_boxes),
            "hidden_labels": len(self.canvas.hidden_station_labels),
            "hidden_segment_labels": self.canvas.hidden_segment_labels,
            "export": saved,
        }


def family_or_default() -> str:
    """返回一个存在的中文字体名，避免在某些精简 Tk 环境里字体缺失。"""
    try:
        import tkinter.font as tkfont
        families = set(tkfont.families())
    except Exception:
        return "TkDefaultFont"
    for name in ("Microsoft YaHei UI", "Microsoft YaHei", "SimHei"):
        if name in families:
            return name
    return "TkDefaultFont"
