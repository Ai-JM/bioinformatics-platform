from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from modules.config import EXAMPLE_DATA_DIR, PageDefinition
from modules.job_manager import create_job_dir, create_job_id, save_json, write_job_manifest
from modules.ui_components import render_page_header
from modules.venn_plotting import (
    plot_flower_summary,
    plot_pairwise_heatmap,
    plot_upset,
    plot_venn_basic,
    plot_venn_network,
)
from modules.venn_utils import (
    build_membership_records,
    build_report_snippet,
    compute_all_intersections,
    compute_pairwise_similarity,
    compute_set_summary,
    dataframe_from_text,
    estimate_intersection_count,
    get_specific_elements,
    manual_rows_to_dataframe,
    normalize_sets,
    permutation_overlap_test,
    read_excel_sheet_names,
    read_input_file,
    recommend_plot_type,
    split_elements,
)


TWO_COLUMN_EXAMPLE = """element\tset
TP53\tDrug_Targets
AKT1\tDrug_Targets
IL6\tDisease_Targets
TP53\tDisease_Targets
TNF\tDEGs
IL6\tDEGs
VEGFA\tPPI_Hub_Genes
TP53\tPPI_Hub_Genes
MAPK1\tPathway_Related_Genes
AKT1\tPathway_Related_Genes
"""

WIDE_EXAMPLE = """Drug_Targets\tDisease_Targets\tDEGs
TP53\tTP53\tIL6
AKT1\tIL6\tTNF
VEGFA\tTNF\tSTAT3
CASP3\tEGFR\tCXCL8
MAPK1\tMMP9\tJUN
"""


def render_venn_analysis_page(page: PageDefinition) -> None:
    render_page_header(
        page,
        "用于分析基因集、药物靶点、疾病靶点、DEGs 和通路集之间的交集、并集、特异元素与集合相似性。",
    )

    with st.expander("方法说明与图形选择原则", expanded=False):
        st.markdown(
            """
            - 推荐使用 **two-column** 格式：第一列为元素，第二列为集合名称；同一元素属于多个集合时可出现多行。
            - 多列格式中每一列代表一个集合，允许不同列长度不一致。
            - 2-3 个集合优先使用 Venn 图；4-6 个集合可使用 Flower 概览并以 UpSet 为主；7 个以上推荐 UpSet、Flower 或网络图。
            - 输出文件统一保存到 `results/{job_id}/venn/`，文件名使用英文，便于后续 GEO、网络药理学和富集分析联动。
            """
        )

    input_mode, source_df, source_note = render_input_section(page)
    if source_note:
        st.info(source_note)
    if not source_df.empty:
        st.markdown("#### 数据预览")
        st.dataframe(source_df.head(20), use_container_width=True)

    parameters = render_parameter_section(len(source_df.columns) if not source_df.empty else 0)
    run_clicked = st.button("运行集合分析", type="primary", use_container_width=True)

    if run_clicked:
        try:
            result = run_venn_analysis(
                page=page,
                source_df=source_df,
                input_mode=input_mode,
                parameters=parameters,
            )
            st.session_state["venn_analysis_last_result"] = result
            st.success(f"分析完成：{result['job_id']}")
        except Exception as exc:
            st.error(f"运行失败：{exc}")

    render_result_section(st.session_state.get("venn_analysis_last_result"))


def render_input_section(page: PageDefinition) -> tuple[str, pd.DataFrame, str]:
    st.markdown("### 1. 数据输入")
    input_choice = st.radio(
        "选择输入方式",
        ["two-column 模式（推荐）", "多列模式", "手动粘贴模式"],
        horizontal=True,
    )

    if input_choice == "two-column 模式（推荐）":
        source = st.radio("数据来源", ["上传文件", "粘贴数据", "使用示例数据"], horizontal=True, key="venn_two_source")
        if source == "上传文件":
            uploaded = st.file_uploader("上传 two-column 文件", type=page.accepted_types, key="venn_two_file")
            return "two_column", read_uploaded_dataframe(uploaded, "two_column", "venn_two_sheet"), ""
        if source == "粘贴数据":
            text = st.text_area("粘贴 two-column 表格", value=TWO_COLUMN_EXAMPLE, height=180, key="venn_two_text")
            return "two_column", dataframe_from_text(text, sep=None), ""
        path = EXAMPLE_DATA_DIR / "venn_gene_sets_two_column.tsv"
        return "two_column", pd.read_csv(path, sep="\t", dtype=str), f"已载入示例数据：{path.name}"

    if input_choice == "多列模式":
        source = st.radio("数据来源", ["上传文件", "粘贴数据", "使用示例数据"], horizontal=True, key="venn_wide_source")
        if source == "上传文件":
            uploaded = st.file_uploader("上传多列集合文件", type=page.accepted_types, key="venn_wide_file")
            return "wide", read_uploaded_dataframe(uploaded, "wide", "venn_wide_sheet"), ""
        if source == "粘贴数据":
            text = st.text_area("粘贴多列表格", value=WIDE_EXAMPLE, height=180, key="venn_wide_text")
            return "wide", dataframe_from_text(text, sep=None), ""
        path = EXAMPLE_DATA_DIR / "venn_gene_sets_wide.xlsx"
        return "wide", pd.read_excel(path), f"已载入示例数据：{path.name}"

    if input_choice == "手动粘贴模式":
        set_count = st.number_input("手动输入集合数量", min_value=2, max_value=6, value=3, step=1)
        text_sets: list[dict[str, str]] = []
        for index in range(int(set_count)):
            left, right = st.columns([1, 2])
            with left:
                name = st.text_input(f"集合 {index + 1} 名称", value=f"集合_{index + 1}", key=f"manual_set_name_{index}")
            with right:
                text = st.text_area(
                    f"集合 {index + 1} 元素",
                    value="",
                    placeholder="每行一个元素，也支持逗号、分号和竖线分隔。",
                    height=110,
                    key=f"manual_set_text_{index}",
                )
            text_sets.append({"name": name, "text": text})
        return "manual", manual_rows_to_dataframe(text_sets), ""

    return "two_column", pd.DataFrame(), ""


def render_parameter_section(column_count: int) -> dict[str, Any]:
    st.markdown("### 2. 参数设置")
    left, middle, right = st.columns(3)
    with left:
        uppercase = st.checkbox("gene symbol 自动转大写", value=True)
        deduplicate = st.checkbox("去除重复元素", value=True)
        strip_space = st.checkbox("去除前后空格", value=True)
        min_intersection_size = st.number_input("最少显示交集元素数", min_value=1, value=1, step=1)
    with middle:
        top_n = st.number_input("UpSet 显示 top N 交集", min_value=5, max_value=100, value=30, step=5)
        compute_similarity = st.checkbox("计算 pairwise Jaccard similarity", value=True)
        run_permutation = st.checkbox("进行随机抽样/置换检验", value=False)
        n_perm = st.number_input("置换次数", min_value=100, max_value=10000, value=1000, step=100)
        seed = st.number_input("随机种子", min_value=1, value=123, step=1)
    with right:
        max_combination_size = st.number_input("最大交集组合阶数", min_value=2, max_value=15, value=6, step=1)
        width = st.number_input("图片宽度", min_value=4.0, max_value=20.0, value=8.0, step=0.5)
        height = st.number_input("图片高度", min_value=3.0, max_value=16.0, value=6.0, step=0.5)
        dpi = st.number_input("DPI", min_value=100, max_value=600, value=300, step=50)
        font_size = st.number_input("字体大小", min_value=6, max_value=24, value=10, step=1)
        label_size = st.number_input("标签大小", min_value=6, max_value=24, value=10, step=1)
        theme = st.selectbox("颜色主题", ["SCI 蓝灰风格", "pastel", "nature", "jama", "custom"])
        custom_color = st.color_picker("自定义主色", "#2563eb") if theme == "custom" else ""

    universe_file = st.file_uploader("背景基因集 universe（可选）", type=["csv", "tsv", "txt", "xlsx"], key="venn_universe")
    return {
        "uppercase": uppercase,
        "deduplicate": deduplicate,
        "strip_space": strip_space,
        "min_intersection_size": int(min_intersection_size),
        "top_n": int(top_n),
        "compute_similarity": compute_similarity,
        "run_permutation": run_permutation,
        "n_perm": int(n_perm),
        "seed": int(seed),
        "max_combination_size": int(max_combination_size),
        "universe_file": universe_file,
        "style_config": {
            "width": float(width),
            "height": float(height),
            "dpi": int(dpi),
            "font_size": int(font_size),
            "label_size": int(label_size),
            "theme": theme,
            "custom_color": custom_color,
        },
    }


def run_venn_analysis(
    *,
    page: PageDefinition,
    source_df: pd.DataFrame,
    input_mode: str,
    parameters: dict[str, Any],
) -> dict[str, Any]:
    sets_dict, standardized_df, cleaning_report = normalize_sets(
        source_df,
        input_mode,
        uppercase=parameters["uppercase"],
        strip=parameters["strip_space"],
        deduplicate=parameters["deduplicate"],
    )
    if len(sets_dict) > 15:
        estimated = estimate_intersection_count(len(sets_dict), parameters["max_combination_size"])
        if estimated > 50000:
            raise ValueError("集合数量较多且组合数过大，请降低最大交集组合阶数后再运行。")

    job_id = create_job_id("venn_analysis")
    job_dir = create_job_dir(job_id)
    venn_dir = job_dir / "venn"
    venn_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = write_job_manifest(
        job_dir,
        job_id=job_id,
        module_key=page.key,
        module_label=page.label,
        parameters={key: str(value) for key, value in parameters.items() if key != "universe_file"},
        input_files=[],
    )

    standardized_path = venn_dir / "input_standardized_two_column.tsv"
    set_summary_path = venn_dir / "set_summary.csv"
    intersections_path = venn_dir / "all_intersections.csv"
    specific_path = venn_dir / "specific_elements.csv"
    membership_path = venn_dir / "intersection_element_details.csv"
    similarity_path = venn_dir / "pairwise_similarity.csv"
    permutation_path = venn_dir / "permutation_test.csv"
    report_path = venn_dir / "report_snippet.md"

    standardized_df.to_csv(standardized_path, sep="\t", index=False)
    set_summary_df = compute_set_summary(sets_dict)
    intersections_df = compute_all_intersections(sets_dict, max_combination=parameters["max_combination_size"])
    intersections_df = intersections_df[intersections_df["count"] >= parameters["min_intersection_size"]]
    specific_df = get_specific_elements(sets_dict)
    membership_df = build_membership_records(sets_dict)
    similarity_df = compute_pairwise_similarity(sets_dict) if parameters["compute_similarity"] else pd.DataFrame()

    set_summary_df.to_csv(set_summary_path, index=False)
    intersections_df.to_csv(intersections_path, index=False)
    specific_df.to_csv(specific_path, index=False)
    membership_df.to_csv(membership_path, index=False)
    similarity_df.to_csv(similarity_path, index=False)

    if parameters["run_permutation"]:
        universe = read_universe(parameters["universe_file"])
        permutation_df = permutation_overlap_test(
            sets_dict,
            universe=universe,
            n_perm=parameters["n_perm"],
            seed=parameters["seed"],
        )
        permutation_df.to_csv(permutation_path, index=False)
    else:
        permutation_df = pd.DataFrame()

    venn_paths, venn_message = plot_venn_basic(sets_dict, venn_dir / "Venn_plot", parameters["style_config"])
    upset_paths = plot_upset(
        sets_dict,
        venn_dir / "UpSet_plot",
        top_n=parameters["top_n"],
        min_size=parameters["min_intersection_size"],
        style_config=parameters["style_config"],
    )
    heatmap_paths = plot_pairwise_heatmap(similarity_df, venn_dir / "Jaccard_heatmap", style_config=parameters["style_config"])
    flower_paths = plot_flower_summary(sets_dict, venn_dir / "Flower_summary", parameters["style_config"])
    network_path = plot_venn_network(sets_dict, venn_dir / "Venn_network", parameters["style_config"])

    if {"Drug_Targets", "Disease_Targets", "DEGs"}.issubset(sets_dict):
        candidate = sorted(sets_dict["Drug_Targets"] & sets_dict["Disease_Targets"] & sets_dict["DEGs"])
        pd.DataFrame({"candidate_target": candidate}).to_csv(venn_dir / "candidate_targets.csv", index=False)

    report_text = build_report_snippet(sets_dict, intersections_df, similarity_df)
    report_path.write_text(report_text, encoding="utf-8")
    save_json({"cleaning_report": cleaning_report, "recommendation": recommend_plot_type(len(sets_dict))}, venn_dir / "analysis_summary.json")
    (job_dir / "logs" / "venn_analysis.log").write_text(f"job_id={job_id}\nsets={len(sets_dict)}\nstatus=completed\n", encoding="utf-8")

    artifacts = [
        artifact("标准化 two-column 表", standardized_path, "text/tab-separated-values"),
        artifact("集合统计表", set_summary_path, "text/csv"),
        artifact("全部交集表", intersections_path, "text/csv"),
        artifact("集合特异元素", specific_path, "text/csv"),
        artifact("元素所属集合明细", membership_path, "text/csv"),
        artifact("Jaccard 相似性表", similarity_path, "text/csv"),
        artifact("论文方法结果片段", report_path, "text/markdown"),
        artifact("网络图 HTML", network_path, "text/html"),
        artifact("任务参数 JSON", manifest_path, "application/json"),
    ]
    if parameters["run_permutation"]:
        artifacts.append(artifact("置换检验结果", permutation_path, "text/csv"))
    for path in [*venn_paths, *upset_paths, *heatmap_paths, *flower_paths]:
        artifacts.append(artifact(path.name, path, mime_for_path(path)))

    return {
        "job_id": job_id,
        "job_dir": str(job_dir),
        "venn_dir": str(venn_dir),
        "sets_dict": {name: sorted(values) for name, values in sets_dict.items()},
        "cleaning_report": cleaning_report,
        "recommendation": recommend_plot_type(len(sets_dict)),
        "venn_message": venn_message,
        "tables": {
            "set_summary": str(set_summary_path),
            "all_intersections": str(intersections_path),
            "specific_elements": str(specific_path),
            "pairwise_similarity": str(similarity_path),
            "permutation_test": str(permutation_path) if parameters["run_permutation"] else "",
            "membership": str(membership_path),
        },
        "figures": {
            "venn": [str(path) for path in venn_paths],
            "upset": [str(path) for path in upset_paths],
            "heatmap": [str(path) for path in heatmap_paths],
            "flower": [str(path) for path in flower_paths],
            "network": str(network_path),
        },
        "report_path": str(report_path),
        "artifacts": artifacts,
    }


def render_result_section(result: dict[str, Any] | None) -> None:
    if not result:
        return

    st.markdown("### 3. 分析结果")
    report = result["cleaning_report"]
    cols = st.columns(4)
    cols[0].metric("集合数量", report["set_count"])
    cols[1].metric("唯一元素", report["unique_element_count"])
    cols[2].metric("清理后记录", report["final_rows"])
    cols[3].metric("重复记录", report["duplicate_rows"])

    recommendation = result["recommendation"]
    if recommendation["level"] == "success":
        st.success(recommendation["message"])
    elif recommendation["level"] == "warning":
        st.warning(recommendation["message"])
    else:
        st.info(recommendation["message"])
    if result.get("venn_message"):
        st.info(result["venn_message"])

    st.markdown("#### 图形展示")
    fig_cols = st.columns(2)
    show_image_from_paths(fig_cols[0], "UpSet 图", result["figures"]["upset"])
    show_image_from_paths(fig_cols[1], "Jaccard 热图", result["figures"]["heatmap"])
    fig_cols2 = st.columns(2)
    show_image_from_paths(fig_cols2[0], "Venn / Flower 图", result["figures"]["venn"] or result["figures"]["flower"])
    show_image_from_paths(fig_cols2[1], "Flower summary", result["figures"]["flower"])

    st.markdown("#### 交集元素查询")
    intersections_df = pd.read_csv(result["tables"]["all_intersections"])
    query_df = intersections_df[intersections_df["n_sets"] >= 2].copy()
    if query_df.empty:
        st.info("暂无 2 个及以上集合的交集。")
    else:
        options = query_df["intersection_id"].tolist()
        selected = st.selectbox("选择交集组合", options)
        row = query_df[query_df["intersection_id"] == selected].iloc[0]
        elements = [item for item in str(row["elements"]).split(";") if item]
        st.write(f"元素数量：{len(elements)}")
        st.dataframe(pd.DataFrame({"element": elements}), use_container_width=True)
        st.download_button(
            "下载当前交集元素 TXT",
            data="\n".join(elements).encode("utf-8"),
            file_name=f"{selected.replace('&', '_')}_elements.txt",
            mime="text/plain",
        )

    membership_df = pd.read_csv(result["tables"]["membership"])
    search = st.text_input("搜索某个元素属于哪些集合", placeholder="例如 TP53")
    if search:
        hit = membership_df[membership_df["element"].str.upper() == search.strip().upper()]
        st.dataframe(hit, use_container_width=True)

    st.markdown("#### 结果表格")
    table_tabs = st.tabs(["集合统计", "全部交集", "特异元素", "Jaccard 相似性", "置换检验"])
    table_paths = [
        result["tables"]["set_summary"],
        result["tables"]["all_intersections"],
        result["tables"]["specific_elements"],
        result["tables"]["pairwise_similarity"],
        result["tables"]["permutation_test"],
    ]
    for tab, path in zip(table_tabs, table_paths):
        with tab:
            if path and Path(path).exists():
                st.dataframe(pd.read_csv(path), use_container_width=True)
            else:
                st.info("未启用或暂无结果。")

    st.markdown("#### 下载区")
    for item in result["artifacts"]:
        path = Path(item["path"])
        if path.exists():
            st.download_button(
                item["label"],
                data=path.read_bytes(),
                file_name=path.name,
                mime=item["mime"],
                use_container_width=True,
                key=f"download_{result['job_id']}_{path.name}_{item['label']}",
            )

    with st.expander("任务文件详情"):
        st.json({key: value for key, value in result.items() if key != "sets_dict"})


def read_uploaded_dataframe(uploaded: Any, input_mode: str, sheet_key: str) -> pd.DataFrame:
    if uploaded is None:
        return pd.DataFrame()
    if Path(uploaded.name).suffix.lower() in {".xlsx", ".xls"}:
        sheets = read_excel_sheet_names(uploaded)
        sheet_name = st.selectbox("选择 Excel sheet", sheets, key=sheet_key)
        return read_input_file(uploaded, input_mode, sheet_name=sheet_name)
    return read_input_file(uploaded, input_mode)


def read_universe(uploaded: Any) -> set[str] | None:
    if uploaded is None:
        return None
    df = read_input_file(uploaded, "wide", sheet_name=0)
    if df.empty:
        return None
    values: set[str] = set()
    for value in df.iloc[:, 0].dropna().astype(str):
        values.update(split_elements(value))
    return {value.upper() for value in values if value}


def show_image_from_paths(container: Any, title: str, paths: list[str]) -> None:
    with container:
        st.markdown(f"**{title}**")
        png_paths = [path for path in paths if str(path).lower().endswith(".png")]
        if png_paths and Path(png_paths[0]).exists():
            st.image(str(png_paths[0]), use_container_width=True)
        else:
            st.info("暂无图片。")


def artifact(label: str, path: Path, mime: str) -> dict[str, str]:
    return {"label": label, "path": str(path), "mime": mime}


def mime_for_path(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".png":
        return "image/png"
    if suffix == ".pdf":
        return "application/pdf"
    if suffix == ".svg":
        return "image/svg+xml"
    return "application/octet-stream"
