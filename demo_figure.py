# -*- coding: utf-8 -*-
"""生成一张示例立体几何图（供答题卡插图演示用）。

运行：python demo_figure.py [输出路径]
默认输出 figs/cube.png
"""

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon

points = {
    "A": (0.0, 0.0),
    "B": (3.2, 0.0),
    "C": (3.2, 2.2),
    "D": (0.0, 2.2),
    "A1": (0.9, 1.5),
    "B1": (4.1, 1.5),
    "C1": (4.1, 3.7),
    "D1": (0.9, 3.7),
}

edges = [
    ("A", "B"), ("B", "C"), ("C", "D"), ("D", "A"),
    ("A1", "B1"), ("B1", "C1"), ("C1", "D1"), ("D1", "A1"),
    ("A", "A1"), ("B", "B1"), ("C", "C1"), ("D", "D1"),
]
hidden = {("D", "A"), ("D", "D1"), ("A", "D"), ("D1", "D")}


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("figs/cube.png")
    out.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(4.2, 3.6), dpi=220)
    # 底面 ABCD 用浅色填充，方便学生想象
    ax.add_patch(Polygon([points[k] for k in ("A", "B", "C", "D")],
                         closed=True, facecolor="0.92", edgecolor="none", zorder=0))

    for a, b in edges:
        if (a, b) in hidden:
            continue
        ax.plot([points[a][0], points[b][0]], [points[a][1], points[b][1]],
                color="black", lw=1.4, zorder=2)

    # 从 A 到 C1 的体对角线（虚线）
    ax.plot([points["A"][0], points["C1"][0]], [points["A"][1], points["C1"][1]],
            color="black", lw=1.0, ls=(0, (4, 2)), zorder=2)

    for name, (x, y) in points.items():
        dx, dy = 0.10, 0.10
        if name in ("B", "C", "B1", "C1"):
            dx = -0.34
        if name in ("C", "D", "C1", "D1"):
            dy = 0.06
        ax.text(x + dx, y + dy, name, fontsize=11, family="serif")

    ax.set_xlim(-0.8, 4.9)
    ax.set_ylim(-0.6, 4.3)
    ax.set_aspect("equal")
    ax.axis("off")
    fig.subplots_adjust(0, 0, 1, 1)
    fig.savefig(out, transparent=True, bbox_inches="tight", pad_inches=0.02)
    print(f"已生成示例插图：{out.resolve()}")


if __name__ == "__main__":
    main()
