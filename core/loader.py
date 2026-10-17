"""路网数据加载与校验（Loader 层）。

支持两种文件格式：
* JSON：结构清晰，适合程序读写（stations 数组 + lines 数组）。
* TXT ：一行一条记录，适合手工编辑，便于展示“从文本文件加载数据”。

加载完成后统一转换为 Station / MetroLine 对象，再交给 MetroGraph 建图。
任何格式错误都会抛出 DataFormatError，并在界面中以对话框形式提示。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

from .graph import MetroGraph, MetroLine, Station


class DataFormatError(Exception):
    """数据文件格式错误，message 为面向用户的中文说明。"""


@dataclass
class MetroDataset:
    """一份完整的路网数据。"""

    city: str
    stations: dict[str, Station]
    lines: dict[str, MetroLine]
    speed_kmh: float = 35.0
    dwell_minutes: float = 0.6
    transfer_minutes: float = 4.0
    source_path: str = ""
    extra: dict = field(default_factory=dict)

    def build_graph(self) -> MetroGraph:
        graph = MetroGraph(
            stations=dict(self.stations),
            lines=dict(self.lines),
            speed_kmh=self.speed_kmh,
            dwell_minutes=self.dwell_minutes,
            transfer_minutes=self.transfer_minutes,
        )
        return graph.build()


# ----------------------------------------------------------------------
# 对外入口
# ----------------------------------------------------------------------
def load_dataset(path: str) -> MetroDataset:
    """根据扩展名选择解析器并完成校验。"""
    if not os.path.isfile(path):
        raise DataFormatError(f"找不到数据文件：\n{path}")
    ext = os.path.splitext(path)[1].lower()
    if ext == ".json":
        dataset = _load_json(path)
    elif ext == ".txt":
        dataset = _load_txt(path)
    else:
        raise DataFormatError(
            f"不支持的文件类型：{ext}\n请选择 .json 或 .txt 格式的路网数据文件。"
        )
    dataset.source_path = path
    _validate(dataset)
    return dataset


# ----------------------------------------------------------------------
# JSON 解析
# ----------------------------------------------------------------------
def _load_json(path: str) -> MetroDataset:
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            payload = json.load(f)
    except json.JSONDecodeError as exc:
        raise DataFormatError(
            f"JSON 语法错误（第 {exc.lineno} 行第 {exc.colno} 列）：{exc.msg}"
        ) from exc
    except OSError as exc:
        raise DataFormatError(f"无法读取文件：{exc}") from exc

    if not isinstance(payload, dict):
        raise DataFormatError("JSON 根节点必须是对象（包含 stations 与 lines）。")

    meta = payload.get("meta") or {}
    params = meta.get("params") or {}

    stations: dict[str, Station] = {}
    for item in payload.get("stations", []):
        try:
            station = Station(
                id=str(item["id"]).strip(),
                name=str(item["name"]).strip(),
                x=float(item["x"]),
                y=float(item["y"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise DataFormatError(
                f"站点记录不完整或坐标不是数字：{item}"
            ) from exc
        stations[station.id] = station

    lines: dict[str, MetroLine] = {}
    for item in payload.get("lines", []):
        try:
            line = MetroLine(
                id=str(item["id"]).strip(),
                name=str(item["name"]).strip(),
                color=str(item.get("color", "#7F8C8D")),
                loop=bool(item.get("loop", False)),
                stations=tuple(str(s).strip() for s in item["stations"]),
            )
        except (KeyError, TypeError) as exc:
            raise DataFormatError(f"线路记录不完整：{item}") from exc
        lines[line.id] = line

    return MetroDataset(
        city=str(meta.get("city", os.path.basename(path))),
        stations=stations,
        lines=lines,
        speed_kmh=float(params.get("train_speed_kmh", 35.0)),
        dwell_minutes=float(params.get("dwell_minutes", 0.6)),
        transfer_minutes=float(params.get("transfer_minutes", 4.0)),
        extra=meta,
    )


# ----------------------------------------------------------------------
# TXT 解析
# ----------------------------------------------------------------------
def _load_txt(path: str) -> MetroDataset:
    """解析自定义的逗号分隔文本格式。

    示例：
        CITY 北京市（教学简化路网）
        PARAM train_speed_kmh=35.0
        STATION,S001,苹果园,-13.7,0.2
        LINE,L1,1号线,#C0392B,0,S001,S002,S003
    """
    stations: dict[str, Station] = {}
    lines: dict[str, MetroLine] = {}
    params: dict[str, float] = {}
    city = os.path.splitext(os.path.basename(path))[0]

    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            raw_lines = f.readlines()
    except OSError as exc:
        raise DataFormatError(f"无法读取文件：{exc}") from exc

    for line_no, raw in enumerate(raw_lines, 1):
        text = raw.strip()
        if not text or text.startswith("#"):
            continue
        upper = text.upper()
        if upper.startswith("CITY "):
            city = text[5:].strip()
            continue
        if upper.startswith("PARAM "):
            body = text[6:].strip()
            if "=" not in body:
                raise DataFormatError(f"第 {line_no} 行 PARAM 缺少 '='：{text}")
            key, value = body.split("=", 1)
            try:
                params[key.strip()] = float(value)
            except ValueError as exc:
                raise DataFormatError(
                    f"第 {line_no} 行参数值不是数字：{value}"
                ) from exc
            continue

        parts = [p.strip() for p in text.split(",")]
        keyword = parts[0].upper()
        if keyword == "STATION":
            if len(parts) != 5:
                raise DataFormatError(
                    f"第 {line_no} 行 STATION 应有 5 个字段，实际 {len(parts)} 个。"
                )
            try:
                station = Station(parts[1], parts[2], float(parts[3]), float(parts[4]))
            except ValueError as exc:
                raise DataFormatError(
                    f"第 {line_no} 行站点坐标不是数字：{text}"
                ) from exc
            stations[station.id] = station
        elif keyword == "LINE":
            if len(parts) < 7:
                raise DataFormatError(
                    f"第 {line_no} 行 LINE 字段数不足（至少需要 2 个站点）：{text}"
                )
            line = MetroLine(
                id=parts[1],
                name=parts[2],
                color=parts[3] if parts[3].startswith("#") else f"#{parts[3]}",
                loop=parts[4] == "1",
                stations=tuple(parts[5:]),
            )
            lines[line.id] = line
        else:
            raise DataFormatError(f"第 {line_no} 行无法识别的记录：{parts[0]}")

    return MetroDataset(
        city=city,
        stations=stations,
        lines=lines,
        speed_kmh=params.get("train_speed_kmh", 35.0),
        dwell_minutes=params.get("dwell_minutes", 0.6),
        transfer_minutes=params.get("transfer_minutes", 4.0),
        extra={"params": params},
    )


# ----------------------------------------------------------------------
# 统一校验
# ----------------------------------------------------------------------
def _validate(dataset: MetroDataset) -> None:
    if len(dataset.stations) < 2:
        raise DataFormatError("数据文件至少需要 2 个站点。")
    if not dataset.lines:
        raise DataFormatError("数据文件至少需要 1 条线路。")

    names: dict[str, str] = {}
    for sid, station in dataset.stations.items():
        if not sid or not station.name:
            raise DataFormatError("站点 ID 和站名不能为空。")
        if station.name in names:
            raise DataFormatError(
                f"站名重复：{station.name}（{names[station.name]} 与 {sid}）"
            )
        names[station.name] = sid

    for lid, line in dataset.lines.items():
        if not lid or not line.name:
            raise DataFormatError("线路 ID 和线路名不能为空。")
        if len(line.stations) < 2:
            raise DataFormatError(f"线路 {line.name} 至少需要 2 个站点。")
        if line.loop and len(line.stations) < 3:
            raise DataFormatError(f"环线 {line.name} 至少需要 3 个站点。")
        seen: set[str] = set()
        for sid in line.stations:
            if sid not in dataset.stations:
                raise DataFormatError(
                    f"线路 {line.name} 引用了不存在的站点 ID：{sid}"
                )
            if sid in seen:
                raise DataFormatError(
                    f"线路 {line.name} 中站点重复：{dataset.stations[sid].name}"
                )
            seen.add(sid)

    if dataset.speed_kmh <= 0:
        raise DataFormatError("列车速度 train_speed_kmh 必须大于 0。")
    if dataset.dwell_minutes < 0 or dataset.transfer_minutes < 0:
        raise DataFormatError("停站时间与换乘时间不能为负数。")
