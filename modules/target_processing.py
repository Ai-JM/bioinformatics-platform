from __future__ import annotations

from dataclasses import dataclass
import matplotlib
matplotlib.use("Agg")

from itertools import combinations
from pathlib import Path
import re

import matplotlib.pyplot as plt
from matplotlib.patches import Circle, Rectangle
import pandas as pd

from modules.plot_style import configure_matplotlib_fonts


configure_matplotlib_fonts()


TARGET_COLUMN_CANDIDATES = [
    "target",
    "targets",
    "gene",
    "genes",
    "symbol",
    "gene_symbol",
    "genesymbol",
    "target_name",
    "protein",
]

IGNORED_TARGET_TOKENS = {
    "score",
    "scores",
    "probability",
    "pvalue",
    "p_value",
    "padj",
    "adj.p.val",
    "source",
    "database",
    "note",
    "notes",
    "extra",
    "extra_note",
}


@dataclass(frozen=True)
class TargetSet:
    name: str
    targets: set[str]


def load_target_sets(
    file_paths: list[str],
    *,
    requested_column: str = "auto",
    normalize_case: str = "upper",
) -> list[TargetSet]:
    target_sets: list[TargetSet] = []
    for file_path in file_paths:
        path = Path(file_path)
        dataframe = read_table(path)
        column = resolve_target_column(dataframe, requested_column)
        targets = clean_targets(dataframe[column], normalize_case=normalize_case)
        target_sets.append(TargetSet(name=path.stem, targets=targets))
    return target_sets


def target_set_from_text(
    name: str,
    text: str,
    *,
    normalize_case: str = "upper",
) -> TargetSet:
    dataframe = pd.DataFrame({"target": parse_targets_from_text(text)})
    targets = clean_targets(dataframe["target"], normalize_case=normalize_case)
    return TargetSet(name=name.strip() or "Set", targets=targets)


def parse_targets_from_text(text: str) -> list[str]:
    targets: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        for token in split_target_cell(stripped):
            cleaned = token.strip().strip('"').strip("'")
            if cleaned:
                targets.append(cleaned)
    return targets


def read_table(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(path)
    if suffix == ".txt":
        return read_raw_target_list(path)
    try:
        if suffix == ".tsv":
            return pd.read_csv(path, sep="\t", encoding="utf-8-sig", on_bad_lines="skip")
        return pd.read_csv(path, encoding="utf-8-sig", on_bad_lines="skip")
    except Exception:
        return read_raw_target_list(path)


def read_raw_target_list(path: Path) -> pd.DataFrame:
    text = read_text_with_fallback(path)
    targets: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        for token in split_target_cell(stripped):
            cleaned = token.strip().strip('"').strip("'")
            if cleaned:
                targets.append(cleaned)
    if not targets:
        raise ValueError(f"无法从文件中读取靶点：{path.name}")
    return pd.DataFrame({"target": targets})


def read_text_with_fallback(path: Path) -> str:
    for encoding in ["utf-8-sig", "utf-8", "gbk", "latin1"]:
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(errors="ignore")


def resolve_target_column(dataframe: pd.DataFrame, requested_column: str) -> str:
    if dataframe.empty:
        raise ValueError("输入文件为空。")

    if requested_column and requested_column.lower() != "auto":
        if requested_column not in dataframe.columns:
            raise ValueError(f"未找到指定列：{requested_column}")
        return requested_column

    normalized_columns = {str(column).strip().lower(): column for column in dataframe.columns}
    for candidate in TARGET_COLUMN_CANDIDATES:
        if candidate in normalized_columns:
            return normalized_columns[candidate]
    return dataframe.columns[0]


def clean_targets(series: pd.Series, *, normalize_case: str) -> set[str]:
    targets: set[str] = set()
    for value in series.dropna():
        text = str(value).strip()
        if not text:
            continue
        for token in split_target_cell(text):
            cleaned = token.strip()
            if should_skip_target_token(cleaned):
                continue
            if normalize_case.lower() == "upper":
                cleaned = cleaned.upper()
            targets.add(cleaned)
    return targets


def should_skip_target_token(token: str) -> bool:
    normalized = token.strip().lower()
    if not normalized:
        return True
    if normalized in TARGET_COLUMN_CANDIDATES or normalized in IGNORED_TARGET_TOKENS:
        return True
    return bool(re.fullmatch(r"[-+]?\d+(\.\d+)?([eE][-+]?\d+)?", normalized))


def split_target_cell(text: str) -> list[str]:
    separators = [";", ",", "|", "/", "\n", "\t"]
    values = [text]
    for separator in separators:
        next_values: list[str] = []
        for value in values:
            next_values.extend(value.split(separator))
        values = next_values
    return values


def write_target_excel(target_sets: list[TargetSet], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    summary = pd.DataFrame(
        [{"dataset": item.name, "target_count": len(item.targets)} for item in target_sets]
    )
    union_targets = sorted(set().union(*(item.targets for item in target_sets))) if target_sets else []
    union_columns = build_union_columns(target_sets, union_targets)

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        union_columns.to_excel(writer, sheet_name="union_by_column", index=False)
        summary.to_excel(writer, sheet_name="summary", index=False)
        for item in target_sets:
            pd.DataFrame({"target": sorted(item.targets)}).to_excel(
                writer,
                sheet_name=safe_sheet_name(item.name),
                index=False,
            )
        write_intersections(writer, target_sets)


def build_union_columns(target_sets: list[TargetSet], union_targets: list[str]) -> pd.DataFrame:
    columns: dict[str, pd.Series] = {
        "union_targets": pd.Series(union_targets, dtype="object"),
    }
    for item in target_sets:
        columns[item.name] = pd.Series(sorted(item.targets), dtype="object")
    return pd.DataFrame(columns)


def write_intersections(writer: pd.ExcelWriter, target_sets: list[TargetSet]) -> None:
    rows = []
    for size in range(2, len(target_sets) + 1):
        for group in combinations(target_sets, size):
            intersection = set.intersection(*(item.targets for item in group))
            rows.append(
                {
                    "datasets": " ∩ ".join(item.name for item in group),
                    "count": len(intersection),
                    "targets": ";".join(sorted(intersection)),
                }
            )
    pd.DataFrame(rows).to_excel(writer, sheet_name="intersections", index=False)


def safe_sheet_name(name: str) -> str:
    invalid_chars = '[]:*?/\\'
    cleaned = "".join("_" if char in invalid_chars else char for char in name)
    return cleaned[:31] or "targets"


def export_venn_figures(
    target_sets: list[TargetSet],
    output_prefix: Path,
    title: str,
    style: str = "auto",
) -> list[Path]:
    output_prefix.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(7.8, 5.6))
    ax.set_axis_off()
    ax.set_aspect("equal", adjustable="box")
    ax.set_title(title, fontsize=16, fontweight="bold", pad=18)

    selected_style = resolve_venn_style(style, len(target_sets))
    if selected_style == "bar":
        draw_venn_bar(ax, target_sets)
    elif selected_style == "vertical":
        draw_vertical_venn(ax, target_sets)
    elif selected_style == "proportional":
        draw_proportional_venn(ax, target_sets)
    elif selected_style == "overlap":
        draw_overlap_venn(ax, target_sets)
    elif selected_style == "network":
        draw_network_venn(ax, target_sets)
    elif selected_style == "flower":
        draw_flower_venn(ax, target_sets)
    elif len(target_sets) == 2:
        draw_two_set_venn(ax, target_sets)
    elif len(target_sets) == 3:
        draw_three_set_venn(ax, target_sets)
    elif 4 <= len(target_sets) <= 7:
        draw_flower_venn(ax, target_sets)
    else:
        draw_set_overview(ax, target_sets)

    paths: list[Path] = []
    for suffix in ["png", "pdf", "svg"]:
        path = output_prefix.with_suffix(f".{suffix}")
        fig.savefig(path, bbox_inches="tight", dpi=300)
        paths.append(path)
    plt.close(fig)
    return paths


def resolve_venn_style(style: str, set_count: int) -> str:
    style = (style or "auto").lower()
    if style == "auto":
        return "flower" if set_count >= 4 else "classic"
    if style == "classic" and set_count >= 4:
        return "flower"
    return style


def draw_two_set_venn(ax: plt.Axes, target_sets: list[TargetSet]) -> None:
    left, right = target_sets
    both = left.targets & right.targets
    left_only = left.targets - right.targets
    right_only = right.targets - left.targets

    ax.set_xlim(0, 10)
    ax.set_ylim(0, 7)
    ax.add_patch(Circle((4, 3.5), 2.1, color="#60a5fa", alpha=0.45))
    ax.add_patch(Circle((6, 3.5), 2.1, color="#34d399", alpha=0.45))
    ax.text(3.1, 3.5, str(len(left_only)), ha="center", va="center", fontsize=18, fontweight="bold")
    ax.text(5.0, 3.5, str(len(both)), ha="center", va="center", fontsize=18, fontweight="bold")
    ax.text(6.9, 3.5, str(len(right_only)), ha="center", va="center", fontsize=18, fontweight="bold")
    ax.text(3.2, 1.0, left.name, ha="center", fontsize=10)
    ax.text(6.8, 1.0, right.name, ha="center", fontsize=10)


def draw_three_set_venn(ax: plt.Axes, target_sets: list[TargetSet]) -> None:
    a, b, c = target_sets
    only_a = a.targets - b.targets - c.targets
    only_b = b.targets - a.targets - c.targets
    only_c = c.targets - a.targets - b.targets
    ab = (a.targets & b.targets) - c.targets
    ac = (a.targets & c.targets) - b.targets
    bc = (b.targets & c.targets) - a.targets
    abc = a.targets & b.targets & c.targets

    ax.set_xlim(0, 10)
    ax.set_ylim(0, 8)
    ax.add_patch(Circle((4.2, 4.5), 2.2, color="#60a5fa", alpha=0.42))
    ax.add_patch(Circle((5.8, 4.5), 2.2, color="#34d399", alpha=0.42))
    ax.add_patch(Circle((5.0, 2.9), 2.2, color="#fbbf24", alpha=0.42))
    ax.text(3.3, 5.1, str(len(only_a)), ha="center", va="center", fontsize=15, fontweight="bold")
    ax.text(6.7, 5.1, str(len(only_b)), ha="center", va="center", fontsize=15, fontweight="bold")
    ax.text(5.0, 1.8, str(len(only_c)), ha="center", va="center", fontsize=15, fontweight="bold")
    ax.text(5.0, 5.2, str(len(ab)), ha="center", va="center", fontsize=15, fontweight="bold")
    ax.text(4.1, 3.3, str(len(ac)), ha="center", va="center", fontsize=15, fontweight="bold")
    ax.text(5.9, 3.3, str(len(bc)), ha="center", va="center", fontsize=15, fontweight="bold")
    ax.text(5.0, 4.0, str(len(abc)), ha="center", va="center", fontsize=17, fontweight="bold")
    ax.text(2.9, 6.9, a.name, ha="center", fontsize=10)
    ax.text(7.1, 6.9, b.name, ha="center", fontsize=10)
    ax.text(5.0, 0.3, c.name, ha="center", fontsize=10)


def draw_flower_venn(ax: plt.Axes, target_sets: list[TargetSet]) -> None:
    import math

    all_intersection = set.intersection(*(item.targets for item in target_sets))
    union_targets = set.union(*(item.targets for item in target_sets))
    n_sets = len(target_sets)
    ax.set_xlim(-4.5, 4.5)
    ax.set_ylim(-4.2, 4.2)
    colors = ["#60a5fa", "#34d399", "#fbbf24", "#f472b6", "#a78bfa", "#fb7185", "#14b8a6"]

    for index, item in enumerate(target_sets):
        angle = 2 * math.pi * index / n_sets
        x = 1.65 * math.cos(angle)
        y = 1.65 * math.sin(angle)
        petal_only = item.targets - all_intersection
        ax.add_patch(Circle((x, y), 1.8, color=colors[index], alpha=0.34, linewidth=1.2))
        ax.text(
            x,
            y,
            str(len(petal_only)),
            ha="center",
            va="center",
            fontsize=12,
            fontweight="bold",
        )
        label_x = 3.4 * math.cos(angle)
        label_y = 3.2 * math.sin(angle)
        ax.text(label_x, label_y, item.name, ha="center", va="center", fontsize=8)

    ax.add_patch(Circle((0, 0), 1.0, color="#ffffff", alpha=0.94, linewidth=1.0))
    ax.text(
        0,
        0.1,
        str(len(all_intersection)),
        ha="center",
        va="center",
        fontsize=17,
        fontweight="bold",
    )
    ax.text(0, -0.45, "all sets", ha="center", va="center", fontsize=8)
    ax.text(
        0,
        -3.85,
        f"Union = {len(union_targets)} targets",
        ha="center",
        va="center",
        fontsize=9,
    )


def draw_overlap_venn(ax: plt.Axes, target_sets: list[TargetSet]) -> None:
    import math

    if not target_sets:
        return
    n_sets = len(target_sets)
    ax.set_xlim(-4.8, 4.8)
    ax.set_ylim(-4.1, 4.1)
    colors = ["#ef4444", "#2563eb", "#22c55e", "#f59e0b", "#a855f7", "#14b8a6", "#64748b"]
    all_intersection = set.intersection(*(item.targets for item in target_sets))
    union_targets = set.union(*(item.targets for item in target_sets))
    layout_radius = 1.45 if n_sets <= 5 else 1.65
    circle_radius = 1.95 if n_sets <= 5 else 1.82

    for index, item in enumerate(target_sets):
        angle = 2 * math.pi * index / max(n_sets, 1)
        x = layout_radius * math.cos(angle)
        y = layout_radius * math.sin(angle)
        ax.add_patch(
            Circle((x, y), circle_radius, color=colors[index % len(colors)], alpha=0.32)
        )
        ax.text(3.65 * math.cos(angle), 3.15 * math.sin(angle), item.name, ha="center", va="center", fontsize=9)
        ax.text(
            2.25 * math.cos(angle),
            1.95 * math.sin(angle),
            str(len(item.targets - all_intersection)),
            ha="center",
            va="center",
            fontsize=10,
        )

    ax.text(0, 0, str(len(all_intersection)), ha="center", va="center", fontsize=18, fontweight="bold")
    ax.text(0, -3.25, f"Union = {len(union_targets)}", ha="center", fontsize=10)


def draw_proportional_venn(ax: plt.Axes, target_sets: list[TargetSet]) -> None:
    import math

    if len(target_sets) < 2:
        draw_set_overview(ax, target_sets)
        return
    selected = target_sets[:3]
    max_size = max(len(item.targets) for item in selected) or 1
    colors = ["#fca5a5", "#93c5fd", "#5eead4"]
    centers = [(-1.4, 0.45), (1.4, 0.45), (0, -0.95)]
    ax.set_xlim(-4.2, 4.2)
    ax.set_ylim(-3.2, 3.4)
    for index, item in enumerate(selected):
        radius = 0.75 + 1.25 * math.sqrt(len(item.targets) / max_size)
        ax.add_patch(Circle(centers[index], radius, color=colors[index], alpha=0.46))
        ax.text(centers[index][0], centers[index][1] + radius + 0.28, item.name, ha="center", fontsize=10)
        ax.text(centers[index][0], centers[index][1], str(len(item.targets)), ha="center", va="center", fontsize=12)
    intersection = set.intersection(*(item.targets for item in selected))
    ax.text(0, 0.1, str(len(intersection)), ha="center", va="center", fontsize=17, fontweight="bold")


def draw_venn_bar(ax: plt.Axes, target_sets: list[TargetSet]) -> None:
    if len(target_sets) < 2:
        draw_set_overview(ax, target_sets)
        return
    left, right = target_sets[:2]
    both = left.targets & right.targets
    left_only = left.targets - right.targets
    right_only = right.targets - left.targets
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 8)
    ax.add_patch(Circle((4, 5.1), 1.35, color="#c4b5fd", alpha=0.62))
    ax.add_patch(Circle((5.5, 5.1), 1.35, color="#fecaca", alpha=0.62))
    ax.text(3.45, 5.1, str(len(left_only)), ha="center", va="center", fontsize=12)
    ax.text(4.75, 5.1, str(len(both)), ha="center", va="center", fontsize=12, fontweight="bold")
    ax.text(6.05, 5.1, str(len(right_only)), ha="center", va="center", fontsize=12)
    total = max(len(left.targets | right.targets), 1)
    left_width = 4.2 * len(left.targets) / total
    right_width = 4.2 * len(right.targets) / total
    ax.add_patch(Rectangle((2.9, 2.1), left_width, 0.25, color="#c4b5fd", alpha=0.72))
    ax.add_patch(Rectangle((2.9 + left_width, 1.68), right_width, 0.25, color="#fecaca", alpha=0.72))
    ax.text(2.8, 1.2, left.name, ha="right", fontsize=9)
    ax.text(7.5, 1.2, right.name, ha="left", fontsize=9)


def draw_vertical_venn(ax: plt.Axes, target_sets: list[TargetSet]) -> None:
    selected = target_sets[: min(7, len(target_sets))]
    colors = ["#a3e635", "#60a5fa", "#f472b6", "#facc15", "#34d399", "#a78bfa", "#fb7185"]
    ax.set_xlim(-4.2, 4.2)
    ax.set_ylim(-4.0, 4.0)
    for index, item in enumerate(selected):
        y = 2.1 - index * 0.7
        x = -0.35 if index % 2 == 0 else 0.35
        ax.add_patch(Circle((x, y), 1.45, color=colors[index], alpha=0.42))
        ax.text(-3.8, y, item.name, va="center", fontsize=9)
        ax.text(0, y, str(len(item.targets)), ha="center", va="center", fontsize=12, fontweight="bold")
    if selected:
        intersection = set.intersection(*(item.targets for item in selected))
        ax.text(0, -3.45, f"Intersection = {len(intersection)}", ha="center", fontsize=10)


def draw_network_venn(ax: plt.Axes, target_sets: list[TargetSet]) -> None:
    import math

    if not target_sets:
        return
    n_sets = len(target_sets)
    ax.set_xlim(-4.4, 4.4)
    ax.set_ylim(-3.5, 3.5)
    all_intersection = set.intersection(*(item.targets for item in target_sets))
    ax.add_patch(Circle((0, 0), 0.48, color="#ef4444", alpha=0.88))
    ax.text(0, 0, str(len(all_intersection)), ha="center", va="center", fontsize=11, color="white", fontweight="bold")
    colors = ["#60a5fa", "#34d399", "#f59e0b", "#a78bfa", "#fb7185", "#14b8a6"]
    for index, item in enumerate(target_sets):
        angle = 2 * math.pi * index / n_sets
        x = 2.75 * math.cos(angle)
        y = 2.15 * math.sin(angle)
        ax.plot([0, x], [0, y], color="#94a3b8", linewidth=1.4)
        ax.add_patch(Circle((x, y), 0.55, color=colors[index % len(colors)], alpha=0.88))
        ax.text(x, y, str(len(item.targets)), ha="center", va="center", fontsize=10, color="white", fontweight="bold")
        ax.text(3.65 * math.cos(angle), 2.85 * math.sin(angle), item.name, ha="center", va="center", fontsize=9)


def draw_set_overview(ax: plt.Axes, target_sets: list[TargetSet]) -> None:
    ax.text(
        0.5,
        0.92,
        "Set count is outside the standard 2-3 Venn layout; Excel intersection tables were exported.",
        ha="center",
        va="center",
        transform=ax.transAxes,
        fontsize=11,
    )
    names = [item.name for item in target_sets]
    counts = [len(item.targets) for item in target_sets]
    ax.barh(range(len(names)), counts, color="#60a5fa")
    ax.set_axis_on()
    ax.set_yticks(range(len(names)))
    ax.set_yticklabels(names)
    ax.set_xlabel("Targets")
    ax.invert_yaxis()
