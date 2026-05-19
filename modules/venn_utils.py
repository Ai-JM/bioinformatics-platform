from __future__ import annotations

from collections import Counter, defaultdict
from itertools import combinations
from math import comb
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


def read_input_file(uploaded_file: Any, mode: str, sheet_name: str | int | None = None) -> pd.DataFrame:
    """读取上传文件，自动兼容 CSV、TSV、TXT 和 Excel。"""
    filename = getattr(uploaded_file, "name", str(uploaded_file))
    suffix = Path(filename).suffix.lower()
    if hasattr(uploaded_file, "seek"):
        uploaded_file.seek(0)

    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(uploaded_file, sheet_name=sheet_name or 0)
    if suffix == ".tsv":
        return pd.read_csv(uploaded_file, sep="\t", dtype=str)
    if suffix == ".txt":
        return pd.read_csv(uploaded_file, sep=None, engine="python", dtype=str)
    if suffix == ".csv":
        return pd.read_csv(uploaded_file, dtype=str)
    raise ValueError(f"无法识别的文件格式：{suffix or filename}")


def read_excel_sheet_names(uploaded_file: Any) -> list[str]:
    """读取 Excel sheet 名称，用于页面选择。"""
    if hasattr(uploaded_file, "seek"):
        uploaded_file.seek(0)
    excel = pd.ExcelFile(uploaded_file)
    if hasattr(uploaded_file, "seek"):
        uploaded_file.seek(0)
    return excel.sheet_names


def dataframe_from_text(text: str, *, sep: str | None = None) -> pd.DataFrame:
    """从粘贴文本读取表格，默认自动识别分隔符。"""
    from io import StringIO

    if not text.strip():
        return pd.DataFrame()
    return pd.read_csv(StringIO(text), sep=sep, engine="python", dtype=str)


def manual_rows_to_dataframe(text_sets: list[dict[str, str]]) -> pd.DataFrame:
    """将手动逐组输入转换为 two-column 表。"""
    rows: list[dict[str, str]] = []
    for item in text_sets:
        set_name = str(item.get("name", "")).strip()
        text = str(item.get("text", ""))
        if not set_name or not text.strip():
            continue
        for element in split_elements(text):
            rows.append({"element": element, "set": set_name})
    return pd.DataFrame(rows)


def normalize_sets(
    df: pd.DataFrame,
    input_mode: str,
    uppercase: bool = True,
    strip: bool = True,
    deduplicate: bool = True,
) -> tuple[dict[str, set[str]], pd.DataFrame, dict[str, Any]]:
    """把 two-column、多列或手动表统一为 dict[str, set[str]]。"""
    if df.empty:
        raise ValueError("输入数据为空，请上传文件、粘贴数据或使用示例数据。")

    long_df = _to_long_dataframe(df, input_mode)
    raw_rows = len(long_df)
    null_rows = int(long_df["element"].isna().sum() + long_df["set"].isna().sum())
    long_df = long_df.dropna(subset=["element", "set"]).copy()
    long_df["element"] = long_df["element"].astype(str)
    long_df["set"] = long_df["set"].astype(str)

    if strip:
        long_df["element"] = long_df["element"].str.strip()
        long_df["set"] = long_df["set"].str.strip()
    if uppercase:
        long_df["element"] = long_df["element"].str.upper()

    empty_mask = (long_df["element"] == "") | (long_df["set"] == "")
    empty_rows = int(empty_mask.sum())
    long_df = long_df.loc[~empty_mask, ["element", "set"]].copy()

    duplicate_rows = int(long_df.duplicated(["element", "set"]).sum())
    if deduplicate:
        long_df = long_df.drop_duplicates(["element", "set"])

    sets_dict: dict[str, set[str]] = {
        set_name: set(group["element"].tolist())
        for set_name, group in long_df.groupby("set", sort=False)
    }
    sets_dict = {name: values for name, values in sets_dict.items() if values}
    if len(sets_dict) < 2:
        raise ValueError("至少需要 2 个非空集合才能进行集合关系分析。")

    standardized = long_df.sort_values(["set", "element"]).reset_index(drop=True)
    report = {
        "raw_rows": raw_rows,
        "null_rows": null_rows,
        "empty_rows": empty_rows,
        "duplicate_rows": duplicate_rows,
        "final_rows": len(standardized),
        "set_count": len(sets_dict),
        "unique_element_count": len(set().union(*sets_dict.values())),
        "deduplicate": deduplicate,
    }
    return sets_dict, standardized, report


def compute_set_summary(sets_dict: dict[str, set[str]]) -> pd.DataFrame:
    """统计每个集合的元素数量。"""
    union = set().union(*sets_dict.values()) if sets_dict else set()
    rows = []
    for name, values in sets_dict.items():
        rows.append(
            {
                "set": name,
                "element_count": len(values),
                "unique_element_count": len(values),
                "fraction_of_union": len(values) / len(union) if union else 0,
            }
        )
    return pd.DataFrame(rows)


def compute_all_intersections(
    sets_dict: dict[str, set[str]],
    max_combination: int | None = None,
) -> pd.DataFrame:
    """计算所有组合交集，并标记是否为该组合特异交集。"""
    names = list(sets_dict)
    if max_combination is None:
        max_combination = len(names)
    max_combination = min(max_combination, len(names))

    rows = []
    for size in range(1, max_combination + 1):
        for group in combinations(names, size):
            intersection = set.intersection(*(sets_dict[name] for name in group))
            if not intersection:
                continue
            outside = set().union(*(sets_dict[name] for name in names if name not in group)) if size < len(names) else set()
            specific = intersection - outside
            rows.append(
                {
                    "intersection_id": "&".join(group),
                    "sets": ";".join(group),
                    "n_sets": size,
                    "count": len(intersection),
                    "elements": ";".join(sorted(intersection)),
                    "specific_count": len(specific),
                    "specific_elements": ";".join(sorted(specific)),
                    "is_unique_to_combination": len(specific) == len(intersection),
                }
            )
    return pd.DataFrame(rows).sort_values(["n_sets", "count"], ascending=[False, False]).reset_index(drop=True)


def get_specific_elements(sets_dict: dict[str, set[str]]) -> pd.DataFrame:
    """计算每个集合独有元素。"""
    rows = []
    for name, values in sets_dict.items():
        others = set().union(*(items for other, items in sets_dict.items() if other != name))
        specific = values - others
        rows.append({"set": name, "count": len(specific), "elements": ";".join(sorted(specific))})
    return pd.DataFrame(rows)


def compute_union_and_common(sets_dict: dict[str, set[str]]) -> dict[str, Any]:
    """计算并集、所有集合共有元素和各集合独有元素。"""
    union = set().union(*sets_dict.values()) if sets_dict else set()
    common = set.intersection(*sets_dict.values()) if sets_dict else set()
    return {
        "union": union,
        "common": common,
        "specific": {
            name: values - set().union(*(items for other, items in sets_dict.items() if other != name))
            for name, values in sets_dict.items()
        },
    }


def compute_pairwise_similarity(sets_dict: dict[str, set[str]]) -> pd.DataFrame:
    """计算两两集合 Jaccard 和 overlap coefficient。"""
    rows = []
    for set_a, set_b in combinations(sets_dict, 2):
        values_a = sets_dict[set_a]
        values_b = sets_dict[set_b]
        intersection_count = len(values_a & values_b)
        union_count = len(values_a | values_b)
        min_size = min(len(values_a), len(values_b))
        rows.append(
            {
                "set_a": set_a,
                "set_b": set_b,
                "intersection_count": intersection_count,
                "union_count": union_count,
                "jaccard": intersection_count / union_count if union_count else 0,
                "overlap_coefficient": intersection_count / min_size if min_size else 0,
                "set_a_size": len(values_a),
                "set_b_size": len(values_b),
            }
        )
    return pd.DataFrame(rows)


def permutation_overlap_test(
    sets_dict: dict[str, set[str]],
    universe: set[str] | None = None,
    n_perm: int = 1000,
    seed: int = 123,
) -> pd.DataFrame:
    """对两两集合交集做简单随机抽样置换检验。"""
    if universe is None:
        universe = set().union(*sets_dict.values())
    universe_list = np.array(sorted(universe), dtype=object)
    if len(universe_list) == 0:
        return pd.DataFrame()

    rng = np.random.default_rng(seed)
    rows = []
    for set_a, set_b in combinations(sets_dict, 2):
        size_a = min(len(sets_dict[set_a]), len(universe_list))
        size_b = min(len(sets_dict[set_b]), len(universe_list))
        observed = len(sets_dict[set_a] & sets_dict[set_b])
        simulated = np.empty(n_perm, dtype=int)
        for index in range(n_perm):
            sample_a = set(rng.choice(universe_list, size=size_a, replace=False))
            sample_b = set(rng.choice(universe_list, size=size_b, replace=False))
            simulated[index] = len(sample_a & sample_b)
        pvalue = (int((simulated >= observed).sum()) + 1) / (n_perm + 1)
        rows.append(
            {
                "set_a": set_a,
                "set_b": set_b,
                "observed_overlap": observed,
                "expected_overlap_mean": float(simulated.mean()),
                "empirical_pvalue": pvalue,
            }
        )
    result = pd.DataFrame(rows)
    result["FDR_BH"] = _benjamini_hochberg(result["empirical_pvalue"].to_numpy())
    return result


def recommend_plot_type(n_sets: int) -> dict[str, str]:
    """根据集合数量推荐可视化方式。"""
    if n_sets <= 1:
        return {"level": "error", "message": "至少需要 2 个集合。"}
    if n_sets <= 3:
        return {"level": "success", "message": "推荐使用 Venn 图，同时提供 UpSet 图辅助查看交集。"}
    if n_sets <= 6:
        return {"level": "info", "message": "可使用 Venn/Flower 展示概览，建议以 UpSet 图作为主要结果图。"}
    if n_sets <= 10:
        return {"level": "warning", "message": "传统 Venn 图不适合 7 组以上集合，推荐使用 UpSet、Flower 或网络图。"}
    return {"level": "warning", "message": "集合数超过 10，传统 Venn 图可读性较差，推荐 UpSet、Flower、Network 或表格结果。"}


def build_membership_records(sets_dict: dict[str, set[str]]) -> pd.DataFrame:
    """生成每个元素属于哪些集合的索引表。"""
    membership: defaultdict[str, list[str]] = defaultdict(list)
    for set_name, elements in sets_dict.items():
        for element in elements:
            membership[element].append(set_name)
    return pd.DataFrame(
        [
            {"element": element, "sets": ";".join(sorted(set_names)), "n_sets": len(set_names)}
            for element, set_names in sorted(membership.items())
        ]
    )


def build_report_snippet(
    sets_dict: dict[str, set[str]],
    intersections_df: pd.DataFrame,
    similarity_df: pd.DataFrame,
) -> str:
    """生成可直接放入论文草稿的方法和结果描述。"""
    union_common = compute_union_and_common(sets_dict)
    set_count = len(sets_dict)
    union_count = len(union_common["union"])
    common_count = len(union_common["common"])
    top_intersection = intersections_df[intersections_df["n_sets"] >= 2].head(1)
    if not top_intersection.empty:
        top_sets = str(top_intersection.iloc[0]["sets"]).replace(";", "、")
        top_count = int(top_intersection.iloc[0]["count"])
    else:
        top_sets = "主要集合"
        top_count = 0

    if not similarity_df.empty:
        best = similarity_df.sort_values("jaccard", ascending=False).iloc[0]
        best_pair = f"{best['set_a']} 与 {best['set_b']}"
        best_jaccard = f"{best['jaccard']:.3f}"
    else:
        best_pair = "集合间"
        best_jaccard = "NA"

    method = (
        "## 方法\n\n"
        "为分析不同来源基因集之间的重叠关系，本研究构建集合分析模块，对药物靶点、疾病相关靶点、"
        "差异表达基因或其他生物学元素进行交集、并集、特异元素和集合相似性分析。输入数据统一转换为 "
        "two-column 格式，并去除空值及重复元素。对于 2-6 个集合，采用 Venn 或 Flower 图展示集合重叠关系；"
        "对于更多集合，采用 UpSet 图展示主要交集组合。集合间相似性采用 Jaccard index 和 overlap coefficient 进行评估。\n"
    )
    result = (
        "\n## 结果\n\n"
        f"共纳入 {set_count} 个集合，去重后包含 {union_count} 个唯一元素。所有集合共有元素为 {common_count} 个。"
        f"{top_sets} 的交集包含 {top_count} 个候选元素。Pairwise Jaccard 分析显示，{best_pair} 的相似性最高，"
        f"Jaccard index 为 {best_jaccard}。"
    )
    return method + result + "\n"


def split_elements(text: str) -> list[str]:
    """按换行、逗号、分号和竖线拆分元素。"""
    values = [text]
    for separator in ["\n", ",", ";", "|", "\t"]:
        next_values: list[str] = []
        for value in values:
            next_values.extend(value.split(separator))
        values = next_values
    return [value.strip() for value in values if value.strip()]


def estimate_intersection_count(n_sets: int, max_combination: int) -> int:
    """估算组合数量，用于大数据保护。"""
    return sum(comb(n_sets, size) for size in range(1, min(n_sets, max_combination) + 1))


def _to_long_dataframe(df: pd.DataFrame, input_mode: str) -> pd.DataFrame:
    if input_mode == "two_column":
        if df.shape[1] < 2:
            raise ValueError("two-column 格式至少需要两列：element 和 set。")
        working = df.iloc[:, :2].copy()
        working.columns = ["element", "set"]
        return working

    if input_mode == "wide":
        rows = []
        for column in df.columns:
            for value in df[column].dropna().tolist():
                rows.append({"element": value, "set": str(column)})
        return pd.DataFrame(rows)

    if input_mode == "manual":
        if {"element", "set"}.issubset(df.columns):
            return df[["element", "set"]].copy()
        raise ValueError("手动输入数据需要包含 element 和 set 两列。")

    raise ValueError(f"未知输入模式：{input_mode}")


def _benjamini_hochberg(pvalues: np.ndarray) -> np.ndarray:
    pvalues = np.asarray(pvalues, dtype=float)
    n_tests = len(pvalues)
    if n_tests == 0:
        return pvalues
    order = np.argsort(pvalues)
    ranked = pvalues[order]
    adjusted = ranked * n_tests / (np.arange(n_tests) + 1)
    adjusted = np.minimum.accumulate(adjusted[::-1])[::-1]
    output = np.empty_like(adjusted)
    output[order] = np.minimum(adjusted, 1.0)
    return output
