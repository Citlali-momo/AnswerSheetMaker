#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A3 数学答题卡生成器
====================

依据 TikZ 版 A3 答题卡（A3答题卡条形码版.tex）重写，用 matplotlib 直接绘制
矢量 PDF，不需要安装 LaTeX。A3 横向，两页，每页三个 A4 竖排区。

可配置项
--------
* 大标题 / 副标题（例如把「2025年xx考试」换成「2026年yy考试」）
* 选择题：机读涂卡（bubble）或填答案表格（table），1-8 单选、9-11 多选，
  表格里多选格宽度是单选的 2 倍
* 彩色 / 黑白两种配色
* 15-19 每道大题的答题区域右上角可插图（立体几何图），包括续答区域
* 输出 A3 PDF，可直接打印

用法
----
    python answer_sheet.py -c config.json -o out/答题卡.pdf
    python answer_sheet.py --title "2026年某某中学高三模拟考试" --choice-mode table
    python answer_sheet.py --color-mode bw --preview out/preview.png
    python answer_sheet.py --image 15=figs/cube.png --image-width 4.5
    python answer_sheet.py --check            # 布局自检（越界 / 文字重叠）
    python answer_sheet.py --dump-config config.json

依赖：matplotlib、Pillow
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import matplotlib

matplotlib.use("Agg")
matplotlib.rcParams["pdf.fonttype"] = 42          # 嵌入 TrueType 子集，文字清晰可缩放
matplotlib.rcParams["ps.fonttype"] = 42
matplotlib.rcParams["text.parse_math"] = False    # 标题里出现 $ 也按普通字符处理
matplotlib.rcParams["axes.unicode_minus"] = False

import matplotlib.image as mpimg
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.figure import Figure
from matplotlib.font_manager import FontProperties, fontManager
from matplotlib.lines import Line2D
from matplotlib.patches import Circle, PathPatch, Polygon, Rectangle
from matplotlib.path import Path as MplPath

try:
    from PIL import Image
except ImportError:                                # pragma: no cover
    Image = None


# ---------------------------------------------------------------------------
# 版面常量（单位：cm，坐标系与原始 TikZ 一致：原点在绘图区左下角，y 向上）
# ---------------------------------------------------------------------------

CM = 1 / 2.54
PT2CM = 2.54 / 72.0

PAGE_W, PAGE_H = 42.0, 29.7          # A3 横向
LM, BM = 1.4, 0.75                   # 绘图区在页面上的左下角
DRAW_W, DRAW_H = 39.2, 28.25         # 绘图区尺寸
COL_W = 12.9                         # 单个 A4 区宽度
COL_X = (0.0, 13.2, 26.4)            # 三个 A4 区的左边界

# 选择题表格排版参数
TABLE_PAD = 0.12
TABLE_GROUP_H = 0.40
TABLE_HDR_H = 0.48
TABLE_ANS_H = 0.92
TABLE_GAP = 0.18

BUBBLE_HEIGHT = 2.70                 # 机读涂卡区高度
NOTE_LINE_FACTOR = 1.55              # 行距系数

# 字体：西文默认 Times New Roman（新罗马），中文正文宋体、标题黑体。
# 通过 font.family 列表做回退：新罗马没有中文字形，缺的字去后面的字体找。
DEFAULT_LATIN_FONT = "Times New Roman"
DEFAULT_CN_FONT = "SimSun"
DEFAULT_CN_BOLD_FONT = "SimHei"

# 字体名查不到时，用这些文件兜底（主要是防 fontManager 缓存没扫到）
FONT_FILE_FALLBACK = {
    "times new roman": ["C:/Windows/Fonts/times.ttf"],
    "simsun": ["C:/Windows/Fonts/simsun.ttc"],
    "simhei": ["C:/Windows/Fonts/simhei.ttf"],
    "microsoft yahei": ["C:/Windows/Fonts/msyh.ttc"],
    "kaiti": ["C:/Windows/Fonts/simkai.ttf"],
}


def px(x: float) -> float:
    """TikZ 横坐标 -> 页面厘米坐标。"""
    return LM + x


def py(y: float) -> float:
    """TikZ 纵坐标 -> 页面厘米坐标。"""
    return BM + y


def _rrect_path(x: float, y: float, w: float, h: float, r: float) -> MplPath:
    """圆角矩形路径（r 以 cm 为单位）。"""
    r = max(0.0, min(r, w / 2.0, h / 2.0))
    k = 0.5523 * r
    x0, y0, x1, y1 = x, y, x + w, y + h
    verts: List[Tuple[float, float]] = [(x0 + r, y0)]
    codes: List[int] = [MplPath.MOVETO]

    def line(p: Tuple[float, float]) -> None:
        verts.append(p)
        codes.append(MplPath.LINETO)

    def curve(c1: Tuple[float, float], c2: Tuple[float, float], p: Tuple[float, float]) -> None:
        verts.extend([c1, c2, p])
        codes.extend([MplPath.CURVE4, MplPath.CURVE4, MplPath.CURVE4])

    line((x1 - r, y0))
    curve((x1 - r + k, y0), (x1, y0 + r - k), (x1, y0 + r))
    line((x1, y1 - r))
    curve((x1, y1 - r + k), (x1 - r + k, y1), (x1 - r, y1))
    line((x0 + r, y1))
    curve((x0 + r - k, y1), (x0, y1 - r + k), (x0, y1 - r))
    line((x0, y0 + r))
    curve((x0, y0 + r - k), (x0 + r - k, y0), (x0 + r, y0))
    verts.append((x0 + r, y0))
    codes.append(MplPath.CLOSEPOLY)
    return MplPath(verts, codes)


@dataclass
class Region:
    """一块答题区域（左上角 + 宽高）。"""

    x: float
    top: float
    w: float
    h: float

    @property
    def right(self) -> float:
        return self.x + self.w

    @property
    def bottom(self) -> float:
        return self.top - self.h


# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------

DEFAULT_NOTES = [
    "答题前，考生务必用黑色字迹的钢笔或签字笔将姓名和考生号填写在答题卡上。",
    "回答选择题时，选出每小题答案以后，用2B铅笔把答题卡上对应题目的答案标号涂黑。"
    "如需改动，用橡皮擦擦干净后，再选其它答案标号涂黑。回答非选择题时，"
    "将答案写在答题卡上指定区域内，超出答题区域的答案无效。",
    "正确填涂试卷类型，否则答案无效。",
    "答题卡保持卡面整洁，不要折叠和弄破。",
]

DEFAULTS: Dict[str, Any] = {
    # ---- 文字 ----
    "title": "2026年普通高等学校招生全国统一考试",
    "subtitle": "数学答题卡",
    "footer_template": "数学答题卡第{page}面（共{pages}面）",
    "name_label": "姓名：",
    "student_id_label": "考生号",
    "student_id_digits": 10,
    "barcode_label": "条形码粘贴区",
    "paper_type_title": "试卷类型",
    "paper_types": ["试卷A", "试卷B"],
    "absent_label": "缺考标记",
    "notes": DEFAULT_NOTES,
    "hint_text": "请在各题目的答题区域内作答，超出黑色矩形边框限定区域的答案无效",
    "blank_questions": ["12", "13", "14"],
    "question_labels": {
        "15": "15.（13分）",
        "16": "16.（15分）",
        "17": "17.（15分）",
        "18": "18.（17分）",
        "19": "19.（17分）",
    },
    # ---- 选择题 ----
    "choice_mode": "bubble",          # bubble=机读涂卡, table=填写答案表格
    "single_choice_count": 8,
    "multiple_choice_count": 3,
    # ---- 配色 ----
    "color_mode": "color",            # color=彩色, bw=黑白
    "primary_color": [255, 50, 165],  # 也可写 "#FF32A5" 或 "255,0,0"
    # ---- 版面 ----
    # layout: standard=标准考试版（含注意事项/填涂样例/试卷类型/缺考标记/条形码）
    #         daily   =平时考试版（这五块全省，第一列上移，16 题独占中栏）
    "layout": "standard",
    "continuation_split": {"16": 0.25, "19": 0.5},
    # ---- 插图：键为 15/16/17/18/19（首块区域）或 cont15/cont18/cont19（续答区域）
    #      {"path": "...", "width": 4.6, "height": 3.0, "margin": 0.15,
    #       "align": "top-right"}
    "images": {},
    # ---- 字体 ----
    # 西文（数字 / 字母）优先用 latin，中文字形由 body_cn / bold_cn 回退提供。
    # matplotlib 会把 family 列表当作回退链：一个字体缺的字形去下一个字体找。
    "fonts": {
        "latin": "Times New Roman",
        "body_cn": "SimSun",
        "bold_cn": "SimHei",
    },
}


def deep_merge(base: Dict[str, Any], override: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    out = dict(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def parse_color(value: Any) -> Tuple[int, int, int]:
    """接受 [255,50,165] / "255,50,165" / "#FF32A5" / "FF32A5"。"""
    if isinstance(value, (list, tuple)) and len(value) == 3:
        return tuple(int(v) for v in value)  # type: ignore[return-value]
    s = str(value).strip().lstrip("#")
    if "," in s:
        parts = [int(p) for p in s.split(",")][:3]
        if len(parts) != 3:
            raise ValueError(f"颜色格式不对：{value!r}")
        return tuple(parts)  # type: ignore[return-value]
    if len(s) == 6:
        return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
    raise ValueError(f"颜色格式不对：{value!r}")


class Config:
    """把 JSON 配置整理成程序使用的样子。"""

    def __init__(self, data: Optional[Dict[str, Any]] = None, base_dir: Optional[Path] = None):
        d = deep_merge(DEFAULTS, data or {})
        self.data = d
        self.base_dir = Path(base_dir or Path.cwd())

        self.title = str(d["title"])
        self.subtitle = str(d["subtitle"])
        self.footer_template = str(d["footer_template"])
        self.name_label = str(d["name_label"])
        self.student_id_label = str(d["student_id_label"])
        self.student_id_digits = int(d["student_id_digits"])
        self.barcode_label = str(d["barcode_label"])
        self.paper_type_title = str(d["paper_type_title"])
        self.paper_types = [str(t) for t in d["paper_types"]]
        self.absent_label = str(d["absent_label"])
        self.notes = [str(t) for t in d["notes"]]
        self.hint_text = str(d["hint_text"])
        self.blank_questions = [str(x) for x in d["blank_questions"]]

        self.choice_mode = str(d["choice_mode"]).lower()
        if self.choice_mode not in ("bubble", "table"):
            raise ValueError("choice_mode 只能是 bubble 或 table")
        self.single_choice_count = int(d["single_choice_count"])
        self.multiple_choice_count = int(d["multiple_choice_count"])

        self.color_mode = str(d["color_mode"]).lower()
        if self.color_mode not in ("color", "bw"):
            raise ValueError("color_mode 只能是 color 或 bw")
        self.primary_color = parse_color(d["primary_color"])

        self.question_labels = {str(k): str(v) for k, v in d["question_labels"].items()}
        self.layout = str(d.get("layout") or "standard").lower()
        if self.layout not in ("standard", "daily"):
            raise ValueError("layout 只能是 standard 或 daily")
        self.continuation_split = {str(k): float(v) for k, v in d["continuation_split"].items()}
        self.images = {str(k): dict(v) for k, v in (d["images"] or {}).items()}

        fonts = d.get("fonts") or {}
        # 新写法：latin=西文字体名，body_cn/bold_cn=中文字体名
        self.font_latin = str(fonts.get("latin") or DEFAULT_LATIN_FONT)
        self.font_body_cn = str(fonts.get("body_cn") or fonts.get("body") or DEFAULT_CN_FONT)
        self.font_bold_cn = str(fonts.get("bold_cn") or fonts.get("bold") or DEFAULT_CN_BOLD_FONT)
        # 兼容旧写法：直接给字体文件路径
        legacy = fonts.get("legacy_files")
        self.font_legacy = dict(legacy) if isinstance(legacy, dict) else {}

    # -- 小工具 ---------------------------------------------------------
    def label(self, q: str, default: str = "") -> str:
        return self.question_labels.get(q, default or f"{q}.")

    def split(self, q: str, default: float) -> float:
        return float(self.continuation_split.get(q, default))

    @property
    def is_daily(self) -> bool:
        """平时考试版：省掉注意事项等五块，第一列上移，16 题独占中栏。"""
        return self.layout == "daily"

    @property
    def header_bottom(self) -> float:
        """头部内容的下沿：平时版只到考生号框，标准版到注意事项框。"""
        return 23.675 if self.is_daily else (23.20 - 4.40)

    def rgb(self) -> Tuple[float, float, float]:
        if self.color_mode == "bw":
            return (0.0, 0.0, 0.0)
        return tuple(v / 255.0 for v in self.primary_color)  # type: ignore[return-value]

    def resolve(self, p: str) -> Path:
        q = Path(p)
        return q if q.is_absolute() else (self.base_dir / q)


# ---------------------------------------------------------------------------
# 绘制
# ---------------------------------------------------------------------------

NO_LINE_START = "，。、；：？！）】》”’%，．"


class Sheet:
    """一页 A3 答题卡。"""

    def __init__(self, cfg: Config, page_no: int, total_pages: int = 2):
        self.cfg = cfg
        self.page_no = page_no
        self.total_pages = total_pages

        self.primary = cfg.rgb()
        self.black = (0.0, 0.0, 0.0)
        self.gray = (0.35, 0.35, 0.35)

        self.fig = Figure(figsize=(PAGE_W * CM, PAGE_H * CM), dpi=200)
        self.fig.patch.set_facecolor("white")
        self.canvas = FigureCanvasAgg(self.fig)
        self.ax = self.fig.add_axes([0.0, 0.0, 1.0, 1.0])
        self.ax.set_xlim(0, PAGE_W)
        self.ax.set_ylim(0, PAGE_H)
        self.ax.set_aspect("equal")
        self.ax.axis("off")

        self._font_cache: Dict[Tuple[bool, float], FontProperties] = {}
        self._measure_cache: Dict[Tuple[str, float, bool], float] = {}
        self.containers: List[Tuple[str, float, float, float, float]] = []

        self.font_families = {
            False: self._font_chain(cfg.font_latin, cfg.font_body_cn),
            True: self._font_chain(cfg.font_latin, cfg.font_bold_cn),
        }
        self.font_files = {
            False: self._font_file(cfg.font_body_cn),
            True: self._font_file(cfg.font_bold_cn),
        }
        if self.font_families[False] is None and self.font_files[False] is None:
            raise FileNotFoundError(
                "找不到可用的中文字体，请在配置的 fonts 里指定字体名或路径")

    # -- 基础设施 -------------------------------------------------------
    @staticmethod
    def _font_available(name: str) -> bool:
        target = str(name).strip().lower()
        if not target:
            return False
        return any(str(f.name).lower() == target
                   for f in fontManager.ttflist)

    @staticmethod
    def _font_file(name: str) -> Optional[str]:
        for path in FONT_FILE_FALLBACK.get(str(name).strip().lower(), []):
            if Path(path).exists():
                return path
        return None

    @classmethod
    def _font_chain(cls, latin: str, chinese: str) -> Optional[List[str]]:
        """西文在前、中文在后的回退链；名字都查不到时返回 None。"""
        chain = [n for n in (latin, chinese) if cls._font_available(n)]
        return chain or None

    def font(self, bold: bool, size: float) -> FontProperties:
        key = (bool(bold), round(float(size), 2))
        fp = self._font_cache.get(key)
        if fp is None:
            chain = self.font_families[bool(bold)]
            if chain:
                # family 列表即回退链：数字/字母命中 Times，中文落到宋体或黑体
                fp = FontProperties(family=chain, size=size,
                                    weight="bold" if bold else "normal")
            else:
                fp = FontProperties(fname=self.font_files[bool(bold)], size=size)
            self._font_cache[key] = fp
        return fp

    def text(self, x: float, y: float, s: Any, size: float = 11, bold: bool = False,
             color: Optional[Tuple[float, float, float]] = None, ha: str = "center",
             va: str = "center", zorder: int = 6, absolute: bool = False):
        if s is None or str(s) == "":
            return None
        X = x if absolute else px(x)
        Y = y if absolute else py(y)
        t = self.ax.text(
            X, Y, str(s),
            fontproperties=self.font(bold, size),
            color=self.black if color is None else color,
            ha=ha, va=va, zorder=zorder,
        )
        return t

    def line(self, pts: Sequence[Tuple[float, float]], color=None, lw: float = 0.8,
             ls: Any = "-", zorder: int = 3) -> None:
        xs = [px(p[0]) for p in pts]
        ys = [py(p[1]) for p in pts]
        self.ax.add_line(
            Line2D(xs, ys, color=self.black if color is None else color,
                   linewidth=lw, linestyle=ls, solid_capstyle="butt",
                   dash_capstyle="butt", zorder=zorder)
        )

    def rect(self, x: float, y: float, w: float, h: float, color=None, lw: float = 0.8,
             ls: Any = "-", fill: Optional[Any] = None, zorder: int = 2) -> None:
        self.ax.add_patch(
            Rectangle((px(x), py(y)), w, h,
                      facecolor=(fill if fill is not None else "none"),
                      edgecolor=(self.black if color is None else color),
                      linewidth=lw, linestyle=ls, zorder=zorder,
                      joinstyle="miter")
        )

    def rrect(self, x: float, y: float, w: float, h: float, r: float = 0.353,
              color=None, lw: float = 1.0, zorder: int = 2) -> None:
        path = _rrect_path(px(x), py(y), w, h, r)
        self.ax.add_patch(
            PathPatch(path, facecolor="none",
                      edgecolor=(self.black if color is None else color),
                      linewidth=lw, zorder=zorder, capstyle="round")
        )

    def container(self, name: str, x: float, y: float, w: float, h: float) -> None:
        """登记一个边框区域（左下角 + 宽高，单位 cm），供自检判断文字是否超框。"""
        self.containers.append((name, px(x), py(y), w, h))

    # -- 文字测量与折行 -------------------------------------------------
    def measure(self, s: str, size: float, bold: bool = False) -> float:
        key = (s, float(size), bool(bold))
        if key in self._measure_cache:
            return self._measure_cache[key]
        t = self.ax.text(0, 0, s, fontproperties=self.font(bold, size))
        bb = t.get_window_extent(renderer=self.canvas.get_renderer())
        t.remove()
        w = bb.width * 72.0 / self.fig.dpi * PT2CM
        self._measure_cache[key] = w
        return w

    def wrap(self, text: str, size: float, max_w: float, bold: bool = False) -> List[str]:
        """按实际字宽折行（中文按字断行，避免标点出现在行首）。"""
        return self.wrap_hanging(text, size, max_w, max_w, 0.0, bold)

    def wrap_hanging(self, text: str, size: float, max_w: float, first_w: float,
                     indent: float, bold: bool = False) -> List[str]:
        """首行宽度可与续行不同（续行左侧留 indent 缩进）。"""
        lines: List[str] = []
        cur = ""
        limit = first_w
        for ch in text:
            if cur and self.measure(cur + ch, size, bold) > limit:
                if ch in NO_LINE_START and len(cur) > 1:
                    lines.append(cur + ch)
                    cur = ""
                    limit = max_w - indent
                    continue
                lines.append(cur)
                cur = "" if ch == " " else ch
                limit = max_w - indent
            else:
                cur += ch
        if cur:
            lines.append(cur)
        return lines or [""]

    # -- 页脚 / 定位码 --------------------------------------------------
    def draw_registration_marks(self) -> None:
        mw, mh = 1.0, 0.6
        xs = [LM - 0.7, LM + 12.5, LM + 25.7]
        for x in xs:
            self.ax.add_patch(Rectangle((x, BM), mw, mh, facecolor="black",
                                        edgecolor="none", zorder=1))
            self.ax.add_patch(Rectangle((x, BM + DRAW_H - mh), mw, mh,
                                        facecolor="black", edgecolor="none", zorder=1))
        xr = PAGE_W - 0.7 - mw
        self.ax.add_patch(Rectangle((xr, BM), mw, mh, facecolor="black",
                                    edgecolor="none", zorder=1))
        self.ax.add_patch(Rectangle((xr, BM + DRAW_H - mh), mw, mh, facecolor="black",
                                    edgecolor="none", zorder=1))

    def draw_footer(self) -> None:
        txt = self.cfg.footer_template.format(page=self.page_no, pages=self.total_pages)
        self.text(PAGE_W / 2, 0.42, txt, 10.5, bold=True, color=self.primary, absolute=True)

    # -- 页头 -----------------------------------------------------------
    def _fit_size(self, s: str, bold: bool, sizes: Sequence[float], max_w: float) -> float:
        for size in sizes:
            if self.measure(s, size, bold) <= max_w:
                return float(size)
        return float(sizes[-1])

    def draw_titles(self) -> None:
        """主标题 / 副标题：过长时自动缩小字号，再不行就拆成两行。"""
        cfg = self.cfg
        cx = COL_W / 2.0
        max_w = 12.40

        title = cfg.title
        size = self._fit_size(title, True, [16, 15.5, 15, 14.5, 14, 13.5, 13,
                                            12.5, 12, 11.5, 11, 10.5], max_w)
        if self.measure(title, size, True) <= max_w:
            self.text(cx, 27.30, title, size, bold=True, color=self.primary)
        else:
            best = None
            for k in range(1, len(title)):
                a, b = title[:k], title[k:]
                w = max(self.measure(a, 12, True), self.measure(b, 12, True))
                if best is None or w < best[0]:
                    best = (w, a, b)
            _, a, b = best
            lsize = self._fit_size(a if self.measure(a, 12, True) >= self.measure(b, 12, True) else b,
                                   True, [13, 12.5, 12, 11.5, 11, 10.5, 10, 9.5, 9], max_w)
            self.text(cx, 27.55, a, lsize, bold=True, color=self.primary)
            self.text(cx, 27.10, b, lsize, bold=True, color=self.primary)

        ssize = self._fit_size(cfg.subtitle, True,
                              [22, 21, 20, 19, 18, 17, 16, 15, 14, 13], max_w)
        self.text(cx, 26.30, cfg.subtitle, ssize, bold=True)

    def draw_header(self) -> None:
        cfg = self.cfg
        c = self.primary

        self.draw_titles()

        # 姓名
        self.text(0.02, 25.00, cfg.name_label, 11, ha="left")
        self.line([(1.32, 24.72), (7.80, 24.72)], color=c, lw=0.9)

        # 考生号
        self.text(0.00, 24.00, cfg.student_id_label, 11, ha="left")
        for i in range(cfg.student_id_digits):
            self.rect(1.50 + i * 0.65, 23.675, 0.65, 0.65, color=c, lw=0.7)

        # 条形码粘贴区（平时考试版不要）
        if not cfg.is_daily:
            bx, bt, bw, bh = 8.35, 25.50, 4.55, 1.825
            self.rect(bx, bt - bh, bw, bh, color=c, lw=0.9, ls=(0, (4, 2)))
            self.text(bx + bw / 2, bt - bh / 2, cfg.barcode_label, 10.5, bold=True, color=c)
            self.container("条形码区", bx, bt - bh, bw, bh)

        # 顶边 15 个黑色定位码
        for i in range(15):
            self.ax.add_patch(Rectangle((px(0.55 + i * 0.8), py(27.85)), 0.5, 0.25,
                                        facecolor="black", edgecolor="none", zorder=2))

        # 注意事项、填涂样例、试卷类型、缺考标记：平时考试版一并省略
        if cfg.is_daily:
            return

        self.draw_notes_box()
        self.draw_sample_box()
        self.draw_paper_type_box()
        self.draw_absent_box()

    def draw_notes_box(self) -> None:
        cfg = self.cfg
        x, top, w, h = 0.0, 23.20, 8.00, 4.40
        self.rect(x, top - h, w, h, color=self.primary, lw=0.8)
        self.container("注意事项框", x, top - h, w, h)

        text_w = w - 0.28
        start_y = 23.05
        max_h = h - 0.25

        chosen = None
        for size in (8.0, 7.8, 7.6, 7.4, 7.2, 7.0, 6.8, 6.6, 6.4, 6.2):
            lines, lh = self._layout_notes(size, text_w)
            if lh * (len(lines) + 1) <= max_h:
                chosen = (size, lines, lh)
                break
        if chosen is None:
            size = 6.2
            lines, lh = self._layout_notes(size, text_w)
            chosen = (size, lines, lh)

        size, lines, lh = chosen
        self.text(x + 0.12, start_y, "注意事项：", size, bold=True, ha="left", va="top")
        y = start_y - lh
        for dx, s in lines:
            self.text(x + 0.12 + dx, y, s, size, ha="left", va="top")
            y -= lh

    def _layout_notes(self, size: float, width: float) -> Tuple[List[Tuple[float, str]], float]:
        em = size * PT2CM
        lh = em * NOTE_LINE_FACTOR
        out: List[Tuple[float, str]] = []
        for i, item in enumerate(self.cfg.notes, 1):
            prefix = f"{i}．"
            pw = self.measure(prefix, size)
            lines = self.wrap_hanging(item, size, width, width - pw, 1.5 * em)
            out.append((0.0, prefix + lines[0]))
            for ln in lines[1:]:
                out.append((1.5 * em, ln))
        return out, lh

    def draw_sample_box(self) -> None:
        x, top, w, h = 8.35, 23.20, 4.55, 2.00
        c = self.primary
        self.rect(x, top - h, w, h, color=c, lw=0.8)
        self.container("填涂样例框", x, top - h, w, h)
        self.text(x + 0.10, top - 0.12, "填涂样例", 9, bold=True, ha="left", va="top")
        self.text(x + 0.10, top - 0.72, "正确填涂", 8.5, ha="left")
        self.text(x + 0.10, top - 1.30, "错误填涂", 8.5, ha="left")

        # 正确填涂
        self.rect(x + 1.75, top - 0.92, 0.50, 0.25, fill="black", color="black", lw=0.0)

        # 四种错误填涂
        mtop = top - 1.42
        mh = 0.25
        for i in range(4):
            self.rect(x + 1.75 + i * 0.75, mtop, 0.50, mh, color=c, lw=0.7)

        # 1) 斜涂
        b0 = x + 1.75
        self.ax.add_patch(Polygon(
            [(px(b0 + 0.04), py(mtop + 0.06)), (px(b0 + 0.30), py(mtop + 0.20)),
             (px(b0 + 0.46), py(mtop + 0.19)), (px(b0 + 0.20), py(mtop + 0.04))],
            closed=True, facecolor="black", edgecolor="none", zorder=4))
        # 2) 横线
        self.rect(b0 + 0.75 + 0.02, mtop + 0.09, 0.46, 0.075, fill="black",
                  color="black", lw=0.0, zorder=4)
        # 3) 打叉
        b2 = b0 + 1.50
        self.line([(b2 + 0.06, mtop + 0.05), (b2 + 0.44, mtop + 0.20)],
                  color=self.black, lw=1.0, zorder=4)
        self.line([(b2 + 0.06, mtop + 0.20), (b2 + 0.44, mtop + 0.05)],
                  color=self.black, lw=1.0, zorder=4)
        # 4) 画圈
        b3 = b0 + 2.25 + 0.25
        cy = py(mtop + 0.125)
        self.ax.add_patch(Circle((px(b3), cy), 0.10, facecolor="black",
                                 edgecolor="none", zorder=4))
        self.ax.add_patch(Circle((px(b3), cy), 0.05, facecolor="white",
                                 edgecolor="none", zorder=5))

    def draw_paper_type_box(self) -> None:
        cfg = self.cfg
        x, top, w, h = 8.35, 20.80, 2.50, 2.00
        c = self.primary
        self.rect(x, top - h, w, h, color=c, lw=0.8)
        self.container("试卷类型框", x, top - h, w, h)
        self.text(x + 0.10, top - 0.12, cfg.paper_type_title, 9, bold=True,
                  ha="left", va="top")
        for i, name in enumerate(cfg.paper_types[:2]):
            yy = top - 0.78 - i * 0.52
            self.text(x + 0.18, yy, name, 9, ha="left")
            self.rect(x + 1.55, yy - 0.115, 0.50, 0.23, color=c, lw=0.7)

    def draw_absent_box(self) -> None:
        cfg = self.cfg
        x, top, w, h = 11.20, 20.80, 1.70, 2.00
        c = self.primary
        self.rect(x, top - h, w, h, color=c, lw=0.8)
        self.container("缺考标记框", x, top - h, w, h)
        self.text(x + 0.10, top - 0.12, cfg.absent_label, 8.5, bold=True,
                  ha="left", va="top")
        self.rect(x + 0.55, top - 1.05, 0.50, 0.25, color=c, lw=0.7)

    # -- 通用块 ---------------------------------------------------------
    def answer_frame(self, x: float, top: float, bottom: float,
                     hint_bottom: bool = True, hint_top: bool = False) -> None:
        h = top - bottom
        self.rrect(x, bottom, COL_W, h, 0.353, color=self.primary, lw=1.0)
        self.container("答题区外框", x, bottom, COL_W, h)
        if hint_bottom:
            self.text(x + COL_W / 2, bottom + 0.30, self.cfg.hint_text, 8, color=self.primary)
        if hint_top:
            self.text(x + COL_W / 2, top - 0.30, self.cfg.hint_text, 8, color=self.primary)

    def inner_box(self, col_x: float) -> None:
        self.rect(col_x + 0.20, 1.20, 12.50, 25.60, color="black", lw=0.9)
        self.container("答题框", col_x + 0.20, 1.20, 12.50, 25.60)

    def section_box(self, x: float, top: float, w: float, h: float, heading: str) -> None:
        self.rect(x, top - h, w, h, color="black", lw=0.9)
        self.container(heading, x, top - h, w, h)
        self.text(x + 0.10, top + 0.55, heading, 10, bold=True, ha="left", va="top")

    def cont_label(self, q: str) -> str:
        return f"（续{q}题）"

    # -- 选择题 ---------------------------------------------------------
    def choice_height(self) -> float:
        if self.cfg.choice_mode == "bubble":
            return BUBBLE_HEIGHT
        blocks = 0
        if self.cfg.single_choice_count > 0:
            blocks += 1
        if self.cfg.multiple_choice_count > 0:
            blocks += 1
        if blocks == 0:
            return BUBBLE_HEIGHT
        return (2 * TABLE_PAD + blocks * (TABLE_GROUP_H + TABLE_HDR_H + TABLE_ANS_H)
                + (blocks - 1) * TABLE_GAP)

    def choice_heading(self) -> str:
        s, m = self.cfg.single_choice_count, self.cfg.multiple_choice_count
        if s and m:
            return f"一、选择题（1—{s} 单选，{s + 1}—{s + m} 多选）"
        if m:
            return f"一、选择题（1—{m} 多选）"
        return "一、选择题"

    def draw_choice(self, top: float, height: float) -> None:
        if self.cfg.choice_mode == "bubble":
            self._draw_bubbles(top, height)
        else:
            self._draw_choice_table(top, height)

    def _bracket(self, x: float, y: float, side: int) -> None:
        half = 0.125
        y0 = y + 0.125
        y1 = y0 - 0.25
        if side < 0:
            pts = [(x - half, y0), (x - 2 * half, y0), (x - 2 * half, y1), (x - half, y1)]
        else:
            pts = [(x + half, y0), (x + 2 * half, y0), (x + 2 * half, y1), (x + half, y1)]
        self.line(pts, color=self.primary, lw=0.7)

    def _draw_bubbles(self, top: float, height: float) -> None:
        total = self.cfg.single_choice_count + self.cfg.multiple_choice_count
        per_col = 4
        step_y = 0.55
        col_d = 4.05
        start_y = top - 0.53

        for i in range(total):
            col, row = divmod(i, per_col)
            x = 0.70 + col * col_d
            y = start_y - row * step_y
            self.text(x, y, str(i + 1), 10)
            for k, letter in enumerate("ABCD"):
                lx = x + 0.70 + k * 0.75
                self.text(lx, y, letter, 8.5, color=self.primary)
                self._bracket(lx, y, -1)
                self._bracket(lx, y, +1)

        # 左侧黑色定位码
        for row in range(per_col):
            y_top = start_y - row * step_y + 0.125
            self.ax.add_patch(Rectangle((px(-0.70), py(y_top - 0.25)), 0.50, 0.25,
                                        facecolor="black", edgecolor="none", zorder=2))

    def _draw_choice_table(self, top: float, height: float) -> None:
        cfg = self.cfg
        single, multi = cfg.single_choice_count, cfg.multiple_choice_count
        box_l, box_r = 0.20, 12.70
        pad = 0.15
        x0 = box_l + pad
        total_w = (box_r - pad) - x0
        lwcol = 1.35
        ws = (total_w - lwcol) / max(single, 1)
        wm = 2.0 * ws

        y = top - TABLE_PAD
        if single > 0:
            y = self._table_block(x0, y, lwcol, ws, 1, single, "单项选择题", box_r)
            y -= TABLE_GAP
        if multi > 0:
            note = f"{single + 1}—{single + multi} 为多项选择题，请填写全部正确选项"
            self._table_block(x0, y, lwcol, wm, single + 1, single + multi,
                              "多项选择题", box_r, note)

    def _table_block(self, x: float, y_top: float, lwcol: float, cw: float,
                     first: int, last: int, label: str, box_right: float,
                     note: Optional[str] = None) -> float:
        n = last - first + 1
        if n <= 0:
            return y_top
        y = y_top
        self.text(x, y, label, 8, color=self.gray, ha="left", va="top")
        y -= TABLE_GROUP_H

        hdr, ans = TABLE_HDR_H, TABLE_ANS_H
        tw = lwcol + n * cw
        bottom = y - hdr - ans

        self.rect(x, bottom, tw, hdr + ans, color="black", lw=0.9)
        self.line([(x, y - hdr), (x + tw, y - hdr)], color="black", lw=0.7)
        for i in range(n + 1):
            xx = x + lwcol + i * cw
            self.line([(xx, bottom), (xx, y)], color="black", lw=0.7)

        self.text(x + lwcol / 2, y - hdr / 2, "题号", 9)
        self.text(x + lwcol / 2, bottom + ans / 2, "答案", 9)
        for i in range(n):
            self.text(x + lwcol + (i + 0.5) * cw, y - hdr / 2, str(first + i), 10)

        if note:
            nx = x + tw + 0.12
            avail = box_right - nx - 0.05
            if avail > 0.8:
                size = 7.5
                lines = self.wrap(note, size, avail)
                lh = size * PT2CM * 1.5
                yy = bottom + ans / 2 + lh * (len(lines) - 1) / 2
                for ln in lines:
                    self.text(nx, yy, ln, size, color=self.gray, ha="left")
                    yy -= lh

        return bottom

    # -- 填空题 ---------------------------------------------------------
    def draw_blanks(self, top: float) -> None:
        d = 4.05
        for i, num in enumerate(self.cfg.blank_questions[:3]):
            x = 0.70 + i * d + 0.10
            self.text(x, top - 0.80, f"{num}.", 10)
            self.line([(x + 0.40, top - 1.00), (x + 0.40 + 3.05, top - 1.00)],
                      color=self.primary, lw=0.8)

    # -- 插图 -----------------------------------------------------------
    def maybe_image(self, key: str, region: Region) -> None:
        spec = self.cfg.images.get(key)
        if not spec:
            return
        raw = spec.get("path") or spec.get("file")
        if not raw:
            return
        path = self.cfg.resolve(str(raw))
        if not path.exists():
            print(f"[警告] 找不到图片：{path}")
            return
        if Image is None:
            print("[警告] 未安装 Pillow，跳过插图")
            return

        with Image.open(path) as im:
            iw, ih = im.size
        if not iw or not ih:
            print(f"[警告] 图片尺寸异常：{path}")
            return

        margin = float(spec.get("margin", 0.15))
        sw, sh = spec.get("width"), spec.get("height")

        if sw and sh:
            w, h = float(sw), float(sh)
        elif sw:
            w = float(sw)
            h = w * ih / iw
        elif sh:
            h = float(sh)
            w = h * iw / ih
        else:
            w = min(4.80, region.w * 0.40)
            h = w * ih / iw

        maxw = max(0.5, region.w - 2 * margin)
        maxh = max(0.5, region.h - 2 * margin)
        k = min(1.0, maxw / w if w > 0 else 1.0, maxh / h if h > 0 else 1.0)
        w, h = w * k, h * k

        align = str(spec.get("align", "top-right"))
        if align == "top-left":
            x0 = region.x + margin
        else:
            x0 = region.right - margin - w
        y1 = region.top - margin
        y0 = y1 - h

        try:
            arr = mpimg.imread(str(path))
        except Exception as exc:                  # pragma: no cover
            print(f"[警告] 读取图片失败：{path}（{exc}）")
            return

        self.ax.imshow(arr, extent=(px(x0), px(x0 + w), py(y0), py(y1)),
                       origin="upper", zorder=2.5, interpolation="antialiased")
        self.ax.set_xlim(0, PAGE_W)
        self.ax.set_ylim(0, PAGE_H)
        self.ax.set_aspect("equal")

    # -- 页面 -----------------------------------------------------------
    def page1_layout(self) -> Dict[str, float]:
        """第一页第一列的纵向排布。

        标准版从注意事项下沿 18.40 起；平时版头部只剩考生号，从 22.88 起，
        选择题、填空题、15 题因此整体上移 4.48cm，15 题答题区也更高。
        """
        col_top = self.cfg.header_bottom - 0.40
        ch = self.choice_height()
        choice_top = col_top - 0.70
        blank_top = choice_top - ch - 0.70
        essay_top = blank_top - 1.40 - 0.70
        return {
            "col_top": col_top,
            "choice_top": choice_top,
            "choice_h": ch,
            "blank_top": blank_top,
            "essay_top": essay_top,
            "essay_h": essay_top - 1.20,
        }

    def draw_page1(self) -> None:
        cfg = self.cfg
        self.draw_registration_marks()
        self.draw_footer()
        self.draw_header()

        L = self.page1_layout()

        # ---- 第一列 ----
        self.answer_frame(0.0, L["col_top"], 0.6, hint_bottom=True)
        self.section_box(0.20, L["choice_top"], 12.50, L["choice_h"], self.choice_heading())
        self.draw_choice(L["choice_top"], L["choice_h"])

        self.section_box(0.20, L["blank_top"], 12.50, 1.40, "二、填空题")
        self.draw_blanks(L["blank_top"])

        self.section_box(0.20, L["essay_top"], 12.50, L["essay_h"], "三、解答题")
        r15 = Region(0.20, L["essay_top"], 12.50, L["essay_h"])
        self.text(1.50, L["essay_top"] - 0.50, cfg.label("15"), 11)
        self.maybe_image("15", r15)

        # ---- 第二列：标准版「续15题 + 16题」上下分栏；平时版 16 题独占整栏 ----
        self.answer_frame(13.2, 27.4, 0.6, hint_bottom=True, hint_top=True)
        self.inner_box(13.2)
        box_top, box_h = 26.80, 25.60

        if cfg.is_daily:
            self.text(14.70, box_top - 0.50, cfg.label("16"), 11)
            self.maybe_image("16", Region(13.40, box_top, 12.50, box_h))
        else:
            split = cfg.split("16", 0.25)
            div_y = box_top - box_h * split
            self.line([(13.40, div_y), (25.90, div_y)], color="black", lw=0.8)
            self.text(14.70, box_top - 0.50, self.cont_label("15"), 11,
                      bold=True, color=self.primary)
            self.text(14.70, div_y - 0.50, cfg.label("16"), 11)
            self.maybe_image("cont15", Region(13.40, box_top, 12.50, box_h * split))
            self.maybe_image("16", Region(13.40, div_y, 12.50, box_h * (1 - split)))

        # ---- 第三列 ----
        self.answer_frame(26.4, 27.4, 0.6, hint_bottom=True, hint_top=True)
        self.inner_box(26.4)
        self.text(27.90, 26.30, cfg.label("17"), 11)
        self.maybe_image("17", Region(26.60, 26.80, 12.50, 25.60))

    def draw_page2(self) -> None:
        cfg = self.cfg
        self.draw_registration_marks()
        self.draw_footer()

        # ---- 第一列 ----
        self.answer_frame(0.0, 27.4, 0.6, hint_bottom=True)
        self.inner_box(0.0)
        self.text(1.50, 26.30, cfg.label("18"), 11)
        self.maybe_image("18", Region(0.20, 26.80, 12.50, 25.60))

        # ---- 第二列 ----
        self.answer_frame(13.2, 27.4, 0.6, hint_bottom=True, hint_top=True)
        self.inner_box(13.2)
        box_top, box_h = 26.80, 25.60
        split = cfg.split("19", 0.5)
        div_y = box_top - box_h * split
        self.line([(13.40, div_y), (25.90, div_y)], color="black", lw=0.8)
        self.text(14.70, box_top - 0.50, self.cont_label("18"), 11,
                  bold=True, color=self.primary)
        self.text(14.70, div_y - 0.50, cfg.label("19"), 11)
        self.maybe_image("cont18", Region(13.40, box_top, 12.50, box_h * split))
        self.maybe_image("19", Region(13.40, div_y, 12.50, box_h * (1 - split)))

        # ---- 第三列 ----
        self.answer_frame(26.4, 27.4, 0.6, hint_bottom=True, hint_top=True)
        self.inner_box(26.4)
        self.text(27.90, 26.30, self.cont_label("19"), 11,
                  bold=True, color=self.primary)
        self.maybe_image("cont19", Region(26.60, 26.80, 12.50, 25.60))


# ---------------------------------------------------------------------------
# 构建 / 导出 / 自检
# ---------------------------------------------------------------------------

def build(cfg: Config) -> List[Sheet]:
    sheets: List[Sheet] = []
    for pno in (1, 2):
        sh = Sheet(cfg, pno, total_pages=2)
        if pno == 1:
            sh.draw_page1()
        else:
            sh.draw_page2()
        sheets.append(sh)
    return sheets


def save_pdf(sheets: Sequence[Sheet], cfg: Config, out_path: Path) -> Path:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with PdfPages(str(out_path)) as pdf:
        for sh in sheets:
            pdf.savefig(sh.fig, facecolor="white")
        info = pdf.infodict()
        info["Title"] = f"{cfg.title} {cfg.subtitle}"
        info["Subject"] = cfg.subtitle
        info["Creator"] = "Cyrene AnswerSheetMaker"
        info["Author"] = ""
    return out_path


def save_previews(sheets: Sequence[Sheet], path: Path, dpi: int = 150) -> List[Path]:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    outs: List[Path] = []
    for i, sh in enumerate(sheets, 1):
        p = path if len(sheets) == 1 else path.with_name(f"{path.stem}-{i}{path.suffix}")
        sh.fig.savefig(str(p), dpi=dpi, facecolor="white")
        outs.append(p)
    return outs


def sheet_report(sh: Sheet) -> List[str]:
    """检查文字是否越界、超框或互相重叠。"""
    sh.canvas.draw()
    renderer = sh.canvas.get_renderer()
    inv = sh.ax.transData.inverted()
    boxes: List[Tuple[str, float, float, float, float]] = []
    for t in sh.ax.texts:
        s = t.get_text()
        if not s.strip():
            continue
        bb = t.get_window_extent(renderer=renderer)
        (x0, y0), (x1, y1) = inv.transform([[bb.x0, bb.y0], [bb.x1, bb.y1]])
        boxes.append((s, min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)))

    issues: List[str] = []
    for s, x0, y0, x1, y1 in boxes:
        if x0 < -0.02 or y0 < -0.02 or x1 > PAGE_W + 0.02 or y1 > PAGE_H + 0.02:
            issues.append(f"[越界] {s!r} -> ({x0:.2f},{y0:.2f})-({x1:.2f},{y1:.2f})")

    # 超框检查：取包含文字中心的最小边框
    tol = 0.04
    for s, x0, y0, x1, y1 in boxes:
        cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
        best = None
        for name, bx, by, bw, bh in sh.containers:
            if bx <= cx <= bx + bw and by <= cy <= by + bh:
                if best is None or bw * bh < best[0]:
                    best = (bw * bh, name, bx, by, bw, bh)
        if best is None:
            continue
        _, name, bx, by, bw, bh = best
        if x0 < bx - tol or y0 < by - tol or x1 > bx + bw + tol or y1 > by + bh + tol:
            issues.append(
                f"[超框] {s!r} 超出「{name}」 文字 ({x0:.2f},{y0:.2f})-({x1:.2f},{y1:.2f})"
                f" / 框 ({bx:.2f},{by:.2f})-({bx + bw:.2f},{by + bh:.2f})"
            )

    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            a, b = boxes[i], boxes[j]
            ox = min(a[3], b[3]) - max(a[1], b[1])
            oy = min(a[4], b[4]) - max(a[2], b[2])
            if ox > 0.04 and oy > 0.04:
                issues.append(
                    f"[重叠] {a[0]!r} × {b[0]!r}（{ox:.2f}×{oy:.2f} cm）"
                )
    return issues


# ---------------------------------------------------------------------------
# 命令行
# ---------------------------------------------------------------------------

def _load_json(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="A3 数学答题卡生成器：可改标题、可插图、可切换涂卡/填表、彩色/黑白，输出 PDF。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("-c", "--config", help="配置文件（JSON）")
    ap.add_argument("-o", "--out", help="输出 PDF 路径（默认 out/答题卡.pdf）")
    ap.add_argument("--title", help="大标题，例如：2026年某某中学高三模拟考试")
    ap.add_argument("--subtitle", help="副标题，例如：数学答题卡")
    ap.add_argument("--layout", choices=["standard", "daily"],
                    help="standard=标准考试版（含注意事项/条形码等），daily=平时考试版（省掉这五块）")
    ap.add_argument("--choice-mode", choices=["bubble", "table"],
                    help="bubble=机读涂卡，table=填写答案表格")
    ap.add_argument("--color-mode", choices=["color", "bw"], help="彩色 / 黑白")
    ap.add_argument("--primary-color", help='主色，如 "255,0,0" 或 "#FF32A5"')
    ap.add_argument("--image", action="append", default=[], metavar="KEY=PATH",
                    help="插图，键为 15/16/17/18/19 或 cont15/cont18/cont19，可重复")
    ap.add_argument("--image-width", type=float, help="插图宽度（cm），配合 --image 使用")
    ap.add_argument("--preview", help="同时输出 PNG 预览（按页生成）")
    ap.add_argument("--dpi", type=int, default=150, help="预览图 DPI，默认 150")
    ap.add_argument("--check", action="store_true", help="生成后检查文字越界与重叠")
    ap.add_argument("--dump-config", help="把当前配置写成 JSON 文件后退出")
    args = ap.parse_args(argv)

    # ---- 读配置 ----
    data: Dict[str, Any] = {}
    base_dir = Path.cwd()
    if args.config:
        cfg_path = Path(args.config)
        if not cfg_path.exists():
            print(f"[错误] 配置文件不存在：{cfg_path}")
            return 2
        data = _load_json(cfg_path)
        base_dir = cfg_path.resolve().parent
    elif Path("config.json").exists():
        data = _load_json(Path("config.json"))
        base_dir = Path("config.json").resolve().parent

    data = json.loads(json.dumps(data, ensure_ascii=False))  # 深拷贝

    # ---- 命令行覆盖 ----
    if args.title:
        data["title"] = args.title
    if args.subtitle:
        data["subtitle"] = args.subtitle
    if args.layout:
        data["layout"] = args.layout
    if args.choice_mode:
        data["choice_mode"] = args.choice_mode
    if args.color_mode:
        data["color_mode"] = args.color_mode
    if args.primary_color:
        data["primary_color"] = parse_color(args.primary_color)

    if args.image:
        images = dict(data.get("images") or {})
        for item in args.image:
            if "=" not in item:
                print(f"[错误] --image 需要 KEY=PATH 形式，收到：{item}")
                return 2
            key, p = item.split("=", 1)
            spec = dict(images.get(key.strip(), {}))
            spec["path"] = p.strip()
            if args.image_width:
                spec["width"] = args.image_width
            images[key.strip()] = spec
        data["images"] = images

    cfg = Config(data, base_dir)

    if args.dump_config:
        target = Path(args.dump_config)
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "w", encoding="utf-8") as f:
            json.dump(deep_merge(DEFAULTS, data), f, ensure_ascii=False, indent=2)
        print(f"配置模板已写入：{target.resolve()}")
        return 0

    # ---- 生成 ----
    if cfg.choice_mode == "bubble":
        total = cfg.single_choice_count + cfg.multiple_choice_count
        if total > 12:
            print(f"[提示] 选择题共 {total} 题，超过 12 题时涂卡区可能放不下，建议改用 --choice-mode table")

    sheets = build(cfg)

    out_path = Path(args.out) if args.out else Path("out") / "答题卡.pdf"
    save_pdf(sheets, cfg, out_path)
    print(f"已生成 PDF：{out_path.resolve()}")

    if args.preview:
        for p in save_previews(sheets, Path(args.preview), dpi=args.dpi):
            print(f"已生成预览：{p.resolve()}")

    if args.check:
        bad = 0
        for sh in sheets:
            issues = sheet_report(sh)
            if issues:
                bad += len(issues)
                print(f"--- 第 {sh.page_no} 页 ---")
                for it in issues:
                    print("   " + it)
        print("布局自检通过：没有越界或文字重叠" if bad == 0 else f"布局自检发现 {bad} 处问题")

    return 0


if __name__ == "__main__":
    sys.exit(main())
