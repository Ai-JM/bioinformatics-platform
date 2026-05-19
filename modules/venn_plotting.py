from __future__ import annotations

from itertools import combinations
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.patches import Circle
import numpy as np
import pandas as pd

from modules.plot_style import configure_matplotlib_fonts
from modules.venn_utils import compute_all_intersections, get_specific_elements


THEMES = {
    "SCI 蓝灰风格": {
        "primary": "#2563eb",
        "secondary": "#64748b",
        "accent": "#14b8a6",
        "palette": ["#60a5fa", "#34d399", "#fbbf24", "#f472b6", "#a78bfa", "#38bdf8", "#94a3b8"],
    },
    "pastel": {
        "primary": "#7dd3fc",
        "secondary": "#c4b5fd",
        "accent": "#f9a8d4",
        "palette": ["#bfdbfe", "#bbf7d0", "#fde68a", "#fecdd3", "#ddd6fe", "#bae6fd", "#fed7aa"],
    },
    "nature": {
        "primary": "#0072B2",
        "secondary": "#009E73",
        "accent": "#D55E00",
        "palette": ["#0072B2", "#009E73", "#E69F00", "#CC79A7", "#56B4E9", "#F0E442", "#D55E00"],
    },
    "jama": {
        "primary": "#374E55",
        "secondary": "#DF8F44",
        "accent": "#00A1D5",
        "palette": ["#374E55", "#DF8F44", "#00A1D5", "#B24745", "#79AF97", "#6A6599", "#80796B"],
    },
}


def style_from_config(style_config: dict[str, Any] | None = None) -> dict[str, Any]:
    config = style_config or {}
    theme_name = config.get("theme", "SCI 蓝灰风格")
    theme = dict(THEMES.get(theme_name, THEMES["SCI 蓝灰风格"]))
    if config.get("custom_color"):
        theme["primary"] = config["custom_color"]
    theme["width"] = float(config.get("width", 8))
    theme["height"] = float(config.get("height", 6))
    theme["dpi"] = int(config.get("dpi", 300))
    theme["font_size"] = int(config.get("font_size", 10))
    theme["label_size"] = int(config.get("label_size", 10))
    return theme


def save_figure(fig: plt.Figure, output_path: Path, formats: list[str]) -> list[Path]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    paths = []
    for suffix in formats:
        path = output_path.with_suffix(f".{suffix}")
        fig.savefig(path, bbox_inches="tight", dpi=300)
        paths.append(path)
    plt.close(fig)
    return paths


def plot_venn_basic(
    sets_dict: dict[str, set[str]],
    output_path: Path,
    style_config: dict[str, Any] | None = None,
) -> tuple[list[Path], str | None]:
    """绘制 2-3 组传统 Venn，更多集合返回友好提示。"""
    style = style_from_config(style_config)
    configure_matplotlib_fonts(style["font_size"])
    n_sets = len(sets_dict)
    if n_sets > 6:
        return [], "集合数量超过 6，传统 Venn 图不适合展示，建议使用 UpSet、Flower 或 Network。"
    if n_sets > 3:
        return plot_flower_summary(sets_dict, output_path, style_config), "4-6 组集合已使用 Flower summary 作为 Venn 概览。"

    names = list(sets_dict)
    fig, ax = plt.subplots(figsize=(style["width"], style["height"]))
    ax.set_axis_off()
    ax.set_aspect("equal", adjustable="box")
    ax.set_title("Venn plot", fontsize=style["font_size"] + 4, fontweight="bold", pad=14)

    try:
        if n_sets == 2:
            from matplotlib_venn import venn2

            venn2([sets_dict[names[0]], sets_dict[names[1]]], set_labels=names, ax=ax)
        elif n_sets == 3:
            from matplotlib_venn import venn3

            venn3([sets_dict[names[0]], sets_dict[names[1]], sets_dict[names[2]]], set_labels=names, ax=ax)
        else:
            return [], "至少需要 2 个集合才能绘制 Venn 图。"
    except Exception:
        _draw_simple_venn(ax, sets_dict, style)

    return save_figure(fig, output_path, ["png", "pdf", "svg"]), None


def plot_upset(
    sets_dict: dict[str, set[str]],
    output_path: Path,
    top_n: int = 30,
    min_size: int = 1,
    style_config: dict[str, Any] | None = None,
) -> list[Path]:
    """绘制简化 UpSet 图：交集柱、集合大小柱和成员矩阵。"""
    style = style_from_config(style_config)
    configure_matplotlib_fonts(style["font_size"])
    intersections = compute_all_intersections(sets_dict)
    intersections = intersections[intersections["n_sets"] >= 1].copy()
    intersections = intersections[intersections["count"] >= min_size]
    intersections = intersections.sort_values("count", ascending=False).head(top_n)
    names = list(sets_dict)

    fig = plt.figure(figsize=(max(style["width"], 10.5), max(style["height"], 6.6)))
    grid = fig.add_gridspec(2, 2, width_ratios=[1.55, 4.35], height_ratios=[3, 1.7], hspace=0.08, wspace=0.18)
    ax_set = fig.add_subplot(grid[1, 0])
    ax_bar = fig.add_subplot(grid[0, 1])
    ax_matrix = fig.add_subplot(grid[1, 1], sharex=ax_bar)

    set_counts = [len(sets_dict[name]) for name in names]
    y_positions = np.arange(len(names))
    ax_set.barh(y_positions, set_counts, color=style["secondary"], alpha=0.85)
    ax_set.set_yticks(y_positions)
    ax_set.set_yticklabels(names, fontsize=style["label_size"])
    ax_set.invert_yaxis()
    ax_set.set_xlabel("Set size")
    ax_set.grid(axis="x", alpha=0.2)
    for y_index, count in enumerate(set_counts):
        ax_set.text(count + max(set_counts) * 0.02, y_index, str(count), va="center", fontsize=max(style["font_size"] - 1, 7))

    x_positions = np.arange(len(intersections))
    ax_bar.bar(x_positions, intersections["count"].to_numpy(), color=style["primary"], alpha=0.88)
    ax_bar.set_ylabel("Intersection size")
    ax_bar.set_title("UpSet plot", fontsize=style["font_size"] + 4, fontweight="bold")
    ax_bar.grid(axis="y", alpha=0.2)
    ax_bar.tick_params(axis="x", labelbottom=False)

    membership = []
    for sets_value in intersections["sets"].tolist():
        group = set(str(sets_value).split(";"))
        membership.append([name in group for name in names])

    for x_index, flags in enumerate(membership):
        active_y = []
        for y_index, is_active in enumerate(flags):
            color = style["primary"] if is_active else "#cbd5e1"
            size = 62 if is_active else 28
            ax_matrix.scatter(x_index, y_index, s=size, color=color, zorder=3)
            if is_active:
                active_y.append(y_index)
        if len(active_y) >= 2:
            ax_matrix.plot([x_index, x_index], [min(active_y), max(active_y)], color=style["primary"], linewidth=1.6, zorder=2)

    ax_matrix.set_yticks(y_positions)
    ax_matrix.set_yticklabels([])
    ax_matrix.tick_params(axis="y", length=0)
    ax_matrix.invert_yaxis()
    ax_matrix.set_xlabel("Intersection combinations")
    ax_matrix.set_xlim(-0.6, max(len(intersections) - 0.4, 0.6))
    ax_matrix.grid(axis="y", alpha=0.16)

    return save_figure(fig, output_path, ["png", "pdf"])


def plot_pairwise_heatmap(
    similarity_df: pd.DataFrame,
    output_path: Path,
    metric: str = "jaccard",
    style_config: dict[str, Any] | None = None,
) -> list[Path]:
    """绘制两两相似性热图。"""
    style = style_from_config(style_config)
    configure_matplotlib_fonts(style["font_size"])
    if similarity_df.empty:
        return []

    names = sorted(set(similarity_df["set_a"]) | set(similarity_df["set_b"]))
    matrix = pd.DataFrame(np.eye(len(names)), index=names, columns=names)
    metric_column = metric if metric in similarity_df.columns else "jaccard"
    for _, row in similarity_df.iterrows():
        matrix.loc[row["set_a"], row["set_b"]] = row[metric_column]
        matrix.loc[row["set_b"], row["set_a"]] = row[metric_column]

    fig, ax = plt.subplots(figsize=(max(style["width"], 6), max(style["height"], 5)))
    image = ax.imshow(matrix.to_numpy(), cmap="Blues", vmin=0, vmax=1)
    ax.set_xticks(np.arange(len(names)))
    ax.set_yticks(np.arange(len(names)))
    ax.set_xticklabels(names, rotation=45, ha="right", fontsize=style["label_size"])
    ax.set_yticklabels(names, fontsize=style["label_size"])
    ax.set_title("Pairwise Jaccard similarity", fontsize=style["font_size"] + 4, fontweight="bold")
    for i in range(len(names)):
        for j in range(len(names)):
            ax.text(j, i, f"{matrix.iloc[i, j]:.2f}", ha="center", va="center", fontsize=style["font_size"] - 1)
    fig.colorbar(image, ax=ax, fraction=0.046, pad=0.04)
    return save_figure(fig, output_path, ["png", "pdf"])


def plot_flower_summary(
    sets_dict: dict[str, set[str]],
    output_path: Path,
    style_config: dict[str, Any] | None = None,
) -> list[Path]:
    """绘制 Flower summary，中心为共有元素，花瓣为各集合特异元素。"""
    import math

    style = style_from_config(style_config)
    configure_matplotlib_fonts(style["font_size"])
    names = list(sets_dict)
    n_sets = len(names)
    common = set.intersection(*sets_dict.values())
    specific_df = get_specific_elements(sets_dict)
    specific_map = dict(zip(specific_df["set"], specific_df["count"]))
    palette = style["palette"]

    fig, ax = plt.subplots(figsize=(style["width"], style["height"]))
    ax.set_axis_off()
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlim(-4.4, 4.4)
    ax.set_ylim(-4.0, 4.0)
    ax.set_title("Flower summary", fontsize=style["font_size"] + 4, fontweight="bold", pad=12)
    for index, name in enumerate(names):
        angle = 2 * math.pi * index / n_sets
        x = 1.65 * math.cos(angle)
        y = 1.65 * math.sin(angle)
        ax.add_patch(Circle((x, y), 1.65, color=palette[index % len(palette)], alpha=0.34))
        ax.text(x, y, str(specific_map.get(name, 0)), ha="center", va="center", fontsize=style["font_size"] + 2, fontweight="bold")
        ax.text(3.45 * math.cos(angle), 3.05 * math.sin(angle), name, ha="center", va="center", fontsize=style["label_size"])
    ax.add_patch(Circle((0, 0), 0.9, color="#ffffff", alpha=0.95))
    ax.text(0, 0.12, str(len(common)), ha="center", va="center", fontsize=style["font_size"] + 7, fontweight="bold")
    ax.text(0, -0.35, "common", ha="center", va="center", fontsize=style["font_size"])
    return save_figure(fig, output_path, ["png", "pdf", "svg"])


def plot_venn_network(
    sets_dict: dict[str, set[str]],
    output_path: Path,
    style_config: dict[str, Any] | None = None,
    max_elements: int = 120,
) -> Path:
    """输出轻量 HTML 网络图，避免额外 pyvis 依赖。"""
    membership = _top_shared_elements(sets_dict, max_elements=max_elements)
    set_nodes = "".join(
        f'<span class="set-node">{name}<b>{len(values)}</b></span>'
        for name, values in sets_dict.items()
    )
    rows = []
    for element, set_names in membership:
        badges = "".join(f"<span>{name}</span>" for name in set_names)
        rows.append(f"<tr><td>{element}</td><td>{badges}</td><td>{len(set_names)}</td></tr>")
    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>Venn network</title>
<style>
body{{font-family:Arial,'Microsoft YaHei',sans-serif;margin:24px;color:#111827;background:#f8fafc}}
.set-node{{display:inline-flex;flex-direction:column;align-items:center;justify-content:center;width:130px;height:86px;margin:8px;border-radius:22px;background:linear-gradient(135deg,#dbeafe,#ccfbf1);box-shadow:0 10px 24px rgba(15,23,42,.08);font-weight:700}}
.set-node b{{font-size:22px;color:#2563eb;margin-top:8px}}
table{{border-collapse:collapse;width:100%;background:white;border-radius:14px;overflow:hidden}}
th,td{{padding:10px 12px;border-bottom:1px solid #e5e7eb;text-align:left}}
td span{{display:inline-block;padding:4px 8px;margin:2px;border-radius:999px;background:#e0f2fe;color:#075985;font-size:12px}}
</style>
</head>
<body>
<h1>Venn network</h1>
<p>展示共享元素及其所属集合。元素过多时仅显示共享集合数最高的前 {max_elements} 个元素。</p>
<section>{set_nodes}</section>
<h2>Shared elements</h2>
<table><thead><tr><th>Element</th><th>Sets</th><th>n_sets</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
</body>
</html>"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    path = output_path.with_suffix(".html")
    path.write_text(html, encoding="utf-8")
    return path


def _draw_simple_venn(ax: plt.Axes, sets_dict: dict[str, set[str]], style: dict[str, Any]) -> None:
    names = list(sets_dict)
    palette = style["palette"]
    if len(names) == 2:
        centers = [(-0.9, 0), (0.9, 0)]
    else:
        centers = [(-0.8, 0.45), (0.8, 0.45), (0, -0.75)]
    ax.set_xlim(-3.2, 3.2)
    ax.set_ylim(-2.7, 2.7)
    for index, name in enumerate(names):
        ax.add_patch(Circle(centers[index], 1.35, color=palette[index], alpha=0.42))
        ax.text(centers[index][0], centers[index][1] - 1.7, name, ha="center", fontsize=style["label_size"])
        ax.text(centers[index][0], centers[index][1], str(len(sets_dict[name])), ha="center", va="center", fontsize=style["font_size"] + 2)
    common = set.intersection(*(sets_dict[name] for name in names))
    ax.text(0, 0, str(len(common)), ha="center", va="center", fontsize=style["font_size"] + 8, fontweight="bold")


def _top_shared_elements(sets_dict: dict[str, set[str]], max_elements: int) -> list[tuple[str, list[str]]]:
    membership: dict[str, list[str]] = {}
    for set_name, values in sets_dict.items():
        for element in values:
            membership.setdefault(element, []).append(set_name)
    return sorted(membership.items(), key=lambda item: (-len(item[1]), item[0]))[:max_elements]
