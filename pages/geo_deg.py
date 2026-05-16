from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
import streamlit as st

from modules.config import BASE_DIR, PageDefinition
from modules.job_manager import create_job_dir, create_job_id, save_json, write_job_manifest
from modules.ui_components import render_download_panel


R_SCRIPT = BASE_DIR / "scripts" / "02_geo_deg.R"


def render_geo_deg_page(page: PageDefinition) -> None:
    st.title("GEO 差异分析")
    st.caption("上传表达矩阵和分组文件，预留 limma R 脚本接口；无 R 环境时生成框架版 mock DEG 结果。")

    with st.form("geo_deg_form", clear_on_submit=False):
        st.subheader("输入文件")
        left, right = st.columns(2)
        with left:
            expression_file = st.file_uploader(
                "表达矩阵 expression_matrix.csv",
                type=["csv"],
                help="格式：Gene, Sample1, Sample2...",
                key="geo_expression_file",
            )
        with right:
            group_file = st.file_uploader(
                "分组文件 group_info.csv",
                type=["csv"],
                help="格式：sample, group",
                key="geo_group_file",
            )

        st.subheader("项目参数")
        c1, c2, c3 = st.columns(3)
        with c1:
            project_name = st.text_input("项目名称", value="GEO_DEG_project")
            species = st.selectbox("物种", ["Human", "Mouse", "Rat"], index=0)
            gene_col = st.text_input("表达矩阵基因列名", value="Gene")
            sample_col = st.text_input("分组文件样本列名", value="sample")
        with c2:
            group_col = st.text_input("分组文件分组列名", value="group")
            case_group = st.text_input("Case group", value="Model")
            control_group = st.text_input("Control group", value="Control")
            p_col = st.selectbox("显著性列", ["P.Value", "adj.P.Val"], index=0)
        with c3:
            do_log2 = st.checkbox("进行 log2(x+1) 转换", value=False)
            do_normalize = st.checkbox("进行标准化", value=False)
            do_batch = st.checkbox("进行批次校正", value=False, help="第一版仅保存参数。")
            logfc_cutoff = st.number_input("log2FC 阈值", value=0.379, step=0.01, format="%.3f")
            pvalue_cutoff = st.number_input("P value 阈值", value=0.05, step=0.01, format="%.3f")

        submitted = st.form_submit_button("运行 GEO 差异分析", type="primary")

    if submitted:
        if expression_file is None or group_file is None:
            st.error("请同时上传表达矩阵和分组文件。")
            return

        parameters = {
            "project_name": project_name,
            "species": species,
            "gene_col": gene_col,
            "sample_col": sample_col,
            "group_col": group_col,
            "case_group": case_group,
            "control_group": control_group,
            "do_log2": str(do_log2),
            "do_normalize": str(do_normalize),
            "do_batch": str(do_batch),
            "logfc_cutoff": str(logfc_cutoff),
            "pvalue_cutoff": str(pvalue_cutoff),
            "p_col": p_col,
        }

        try:
            with st.spinner("正在验证输入并运行差异分析框架..."):
                run_result = run_geo_deg_analysis(
                    page=page,
                    expression_file=expression_file,
                    group_file=group_file,
                    parameters=parameters,
                )
            st.session_state[f"{page.key}_last_result"] = run_result
            st.success(f"任务已完成：{run_result['job_id']}")
        except Exception as exc:
            st.error(f"运行失败：{exc}")
            return

    run_result = st.session_state.get(f"{page.key}_last_result")
    if run_result:
        render_geo_deg_summary(run_result)
        render_download_panel(run_result)


def run_geo_deg_analysis(
    *,
    page: PageDefinition,
    expression_file: Any,
    group_file: Any,
    parameters: dict[str, str],
) -> dict[str, Any]:
    job_id = create_job_id(page.key)
    job_dir = create_job_dir(job_id)
    input_dir = job_dir / "inputs"
    output_dir = job_dir / "outputs"
    log_path = job_dir / "logs" / "geo_deg.log"

    expr_path = input_dir / "expression_matrix.csv"
    group_path = input_dir / "group_info.csv"
    expr_path.write_bytes(expression_file.getbuffer())
    group_path.write_bytes(group_file.getbuffer())

    expr_df = pd.read_csv(expr_path)
    group_df = pd.read_csv(group_path)
    validation = validate_geo_inputs(expr_df, group_df, parameters)

    manifest_path = write_job_manifest(
        job_dir,
        job_id=job_id,
        module_key=page.key,
        module_label=page.label,
        parameters=parameters,
        input_files=[str(expr_path), str(group_path)],
    )

    r_status = try_run_limma_r(expr_path, group_path, output_dir, log_path, parameters)
    if r_status["used_r"]:
        mode_message = "已调用 scripts/02_geo_deg.R。"
    else:
        mode_message = "当前为框架版本，后续接入真实 limma 脚本。"
        mock_outputs = generate_mock_deg_outputs(
            expr_df=expr_df,
            group_df=group_df,
            output_dir=output_dir,
            parameters=parameters,
        )
        log_path.write_text(
            "\n".join(
                [
                    f"job_id={job_id}",
                    f"mode=python_mock",
                    f"reason={r_status['reason']}",
                    mode_message,
                    *mock_outputs,
                ]
            ),
            encoding="utf-8",
        )

    deg_all_path = output_dir / "DEG_all.csv"
    summary = build_geo_summary(deg_all_path, validation, parameters)
    summary_path = output_dir / "geo_deg_summary.json"
    save_json({"job_id": job_id, "message": mode_message, **summary}, summary_path)

    return {
        "job_id": job_id,
        "job_dir": str(job_dir),
        "manifest_path": str(manifest_path),
        "result_path": str(summary_path),
        "log_path": str(log_path),
        "summary": summary,
        "message": mode_message,
        "artifacts": build_geo_artifacts(job_dir),
    }


def validate_geo_inputs(
    expr_df: pd.DataFrame,
    group_df: pd.DataFrame,
    parameters: dict[str, str],
) -> dict[str, Any]:
    gene_col = parameters["gene_col"]
    sample_col = parameters["sample_col"]
    group_col = parameters["group_col"]
    case_group = parameters["case_group"]
    control_group = parameters["control_group"]

    if gene_col not in expr_df.columns:
        raise ValueError(f"表达矩阵中未找到基因列：{gene_col}")
    if sample_col not in group_df.columns:
        raise ValueError(f"分组文件中未找到样本列：{sample_col}")
    if group_col not in group_df.columns:
        raise ValueError(f"分组文件中未找到分组列：{group_col}")

    sample_names = [col for col in expr_df.columns if col != gene_col]
    group_samples = group_df[sample_col].astype(str).tolist()
    missing_samples = sorted(set(group_samples) - set(sample_names))
    if missing_samples:
        raise ValueError(f"分组文件中的样本不在表达矩阵中：{', '.join(missing_samples[:8])}")

    available_groups = set(group_df[group_col].astype(str))
    if case_group not in available_groups:
        raise ValueError(f"分组文件中未找到 Case group：{case_group}")
    if control_group not in available_groups:
        raise ValueError(f"分组文件中未找到 Control group：{control_group}")

    case_samples = group_df.loc[group_df[group_col].astype(str) == case_group, sample_col].astype(str).tolist()
    control_samples = group_df.loc[group_df[group_col].astype(str) == control_group, sample_col].astype(str).tolist()
    if not case_samples or not control_samples:
        raise ValueError("Case 或 Control 样本数为 0。")

    numeric_expr = expr_df[sample_names].apply(pd.to_numeric, errors="coerce")
    if numeric_expr.isna().all(axis=None):
        raise ValueError("表达矩阵样本列无法转换为数值。")

    return {
        "sample_count": len(group_samples),
        "case_count": len(case_samples),
        "control_count": len(control_samples),
        "gene_count": int(expr_df[gene_col].nunique()),
        "case_samples": case_samples,
        "control_samples": control_samples,
    }


def try_run_limma_r(
    expr_path: Path,
    group_path: Path,
    output_dir: Path,
    log_path: Path,
    parameters: dict[str, str],
) -> dict[str, Any]:
    rscript = shutil.which("Rscript")
    if not rscript:
        return {"used_r": False, "reason": "Rscript 不可用"}
    if not R_SCRIPT.exists():
        return {"used_r": False, "reason": "scripts/02_geo_deg.R 不存在"}

    command = [
        rscript,
        str(R_SCRIPT),
        "--expr",
        str(expr_path),
        "--group",
        str(group_path),
        "--gene_col",
        parameters["gene_col"],
        "--sample_col",
        parameters["sample_col"],
        "--group_col",
        parameters["group_col"],
        "--case",
        parameters["case_group"],
        "--control",
        parameters["control_group"],
        "--logfc",
        parameters["logfc_cutoff"],
        "--pvalue",
        parameters["pvalue_cutoff"],
        "--p_col",
        parameters["p_col"],
        "--outdir",
        str(output_dir),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=3600, check=False)
    log_path.write_text(
        " ".join(command)
        + "\n\nSTDOUT:\n"
        + completed.stdout
        + "\n\nSTDERR:\n"
        + completed.stderr,
        encoding="utf-8",
    )
    return {"used_r": completed.returncode == 0, "reason": f"Rscript exit code {completed.returncode}"}


def generate_mock_deg_outputs(
    *,
    expr_df: pd.DataFrame,
    group_df: pd.DataFrame,
    output_dir: Path,
    parameters: dict[str, str],
) -> list[str]:
    gene_col = parameters["gene_col"]
    sample_col = parameters["sample_col"]
    group_col = parameters["group_col"]
    case_group = parameters["case_group"]
    control_group = parameters["control_group"]
    logfc_cutoff = float(parameters["logfc_cutoff"])
    pvalue_cutoff = float(parameters["pvalue_cutoff"])
    p_col = parameters["p_col"]

    case_samples = group_df.loc[group_df[group_col].astype(str) == case_group, sample_col].astype(str).tolist()
    control_samples = group_df.loc[group_df[group_col].astype(str) == control_group, sample_col].astype(str).tolist()
    sample_cols = [col for col in expr_df.columns if col != gene_col]
    numeric_expr = expr_df[[gene_col, *sample_cols]].copy()
    numeric_expr[sample_cols] = numeric_expr[sample_cols].apply(pd.to_numeric, errors="coerce")
    before_expr = numeric_expr.copy()

    if parameters["do_log2"] == "True":
        numeric_expr[sample_cols] = np.log2(numeric_expr[sample_cols].clip(lower=0) + 1)
    if parameters["do_normalize"] == "True":
        numeric_expr[sample_cols] = quantile_normalize(numeric_expr[sample_cols])

    case_mean = numeric_expr[case_samples].mean(axis=1)
    control_mean = numeric_expr[control_samples].mean(axis=1)
    logfc = case_mean - control_mean
    variability = numeric_expr[case_samples + control_samples].std(axis=1).fillna(0) + 1e-6
    score = (logfc.abs() / variability).replace([np.inf, -np.inf], np.nan).fillna(0)
    p_values = np.exp(-score * 2.5).clip(1e-6, 1.0)
    adj_p = benjamini_hochberg(p_values)

    deg_all = pd.DataFrame(
        {
            "Gene": expr_df[gene_col].astype(str),
            "logFC": logfc,
            "AveExpr": numeric_expr[sample_cols].mean(axis=1),
            "P.Value": p_values,
            "adj.P.Val": adj_p,
        }
    ).sort_values(p_col)
    deg_all["change"] = "NotSig"
    deg_all.loc[(deg_all["logFC"] >= logfc_cutoff) & (deg_all[p_col] <= pvalue_cutoff), "change"] = "Up"
    deg_all.loc[(deg_all["logFC"] <= -logfc_cutoff) & (deg_all[p_col] <= pvalue_cutoff), "change"] = "Down"

    deg_sig = deg_all[deg_all["change"].isin(["Up", "Down"])]
    deg_up = deg_all[deg_all["change"] == "Up"]
    deg_down = deg_all[deg_all["change"] == "Down"]

    deg_all.to_csv(output_dir / "DEG_all.csv", index=False)
    deg_sig.to_csv(output_dir / "DEG_sig.csv", index=False)
    deg_up.to_csv(output_dir / "DEG_up.csv", index=False)
    deg_down.to_csv(output_dir / "DEG_down.csv", index=False)

    save_volcano(deg_all, output_dir, logfc_cutoff, pvalue_cutoff, p_col)
    save_heatmap(numeric_expr, deg_all, output_dir, gene_col, sample_cols)
    save_boxplot(before_expr, output_dir / "boxplot_before.png", gene_col, sample_cols, "Expression before processing")
    if parameters["do_log2"] == "True" or parameters["do_normalize"] == "True":
        save_boxplot(numeric_expr, output_dir / "boxplot_after.png", gene_col, sample_cols, "Expression after processing")

    return [
        "outputs/DEG_all.csv",
        "outputs/DEG_sig.csv",
        "outputs/DEG_up.csv",
        "outputs/DEG_down.csv",
        "outputs/volcano.png",
        "outputs/volcano.pdf",
        "outputs/heatmap_top20.png",
        "outputs/heatmap_top20.pdf",
    ]


def quantile_normalize(dataframe: pd.DataFrame) -> pd.DataFrame:
    ranked_mean = dataframe.stack().groupby(dataframe.rank(method="first").stack().astype(int)).mean()
    normalized = dataframe.rank(method="min").stack().astype(int).map(ranked_mean).unstack()
    return normalized[dataframe.columns]


def benjamini_hochberg(p_values: np.ndarray) -> np.ndarray:
    p_values = np.asarray(p_values, dtype=float)
    order = np.argsort(p_values)
    ranked = p_values[order]
    n = len(p_values)
    adjusted = ranked * n / np.arange(1, n + 1)
    adjusted = np.minimum.accumulate(adjusted[::-1])[::-1]
    output = np.empty_like(adjusted)
    output[order] = np.clip(adjusted, 0, 1)
    return output


def save_volcano(
    deg_all: pd.DataFrame,
    output_dir: Path,
    logfc_cutoff: float,
    pvalue_cutoff: float,
    p_col: str,
) -> None:
    fig, ax = plt.subplots(figsize=(6.5, 5))
    colors = deg_all["change"].map({"Up": "#dc2626", "Down": "#2563eb", "NotSig": "#9ca3af"})
    y_values = -np.log10(deg_all[p_col].clip(lower=1e-300))
    ax.scatter(deg_all["logFC"], y_values, c=colors, s=14, alpha=0.78, linewidths=0)
    ax.axvline(logfc_cutoff, color="#6b7280", linestyle="--", linewidth=0.8)
    ax.axvline(-logfc_cutoff, color="#6b7280", linestyle="--", linewidth=0.8)
    ax.axhline(-np.log10(pvalue_cutoff), color="#6b7280", linestyle="--", linewidth=0.8)
    ax.set_xlabel("log2 Fold Change")
    ax.set_ylabel(f"-log10({p_col})")
    ax.set_title("Volcano plot")
    fig.tight_layout()
    fig.savefig(output_dir / "volcano.png", dpi=300)
    fig.savefig(output_dir / "volcano.pdf")
    plt.close(fig)


def save_heatmap(
    expr_df: pd.DataFrame,
    deg_all: pd.DataFrame,
    output_dir: Path,
    gene_col: str,
    sample_cols: list[str],
) -> None:
    top_genes = deg_all.head(20)["Gene"].astype(str).tolist()
    heatmap_df = expr_df.loc[expr_df[gene_col].astype(str).isin(top_genes), [gene_col, *sample_cols]].copy()
    if heatmap_df.empty:
        heatmap_df = expr_df[[gene_col, *sample_cols]].head(20).copy()
    heatmap_df = heatmap_df.drop_duplicates(subset=[gene_col]).set_index(gene_col)
    zscore = heatmap_df.sub(heatmap_df.mean(axis=1), axis=0).div(heatmap_df.std(axis=1).replace(0, 1), axis=0)
    fig, ax = plt.subplots(figsize=(8, max(4, 0.22 * len(zscore))))
    sns.heatmap(zscore, cmap="RdBu_r", center=0, ax=ax, cbar_kws={"label": "Row z-score"})
    ax.set_title("Top 20 DEG heatmap")
    ax.set_xlabel("")
    ax.set_ylabel("")
    fig.tight_layout()
    fig.savefig(output_dir / "heatmap_top20.png", dpi=300)
    fig.savefig(output_dir / "heatmap_top20.pdf")
    plt.close(fig)


def save_boxplot(expr_df: pd.DataFrame, output_path: Path, gene_col: str, sample_cols: list[str], title: str) -> None:
    long_df = expr_df[sample_cols].melt(var_name="sample", value_name="expression")
    fig, ax = plt.subplots(figsize=(max(6, 0.45 * len(sample_cols)), 4))
    sns.boxplot(data=long_df, x="sample", y="expression", ax=ax, color="#93c5fd")
    ax.set_title(title)
    ax.tick_params(axis="x", rotation=45)
    fig.tight_layout()
    fig.savefig(output_path, dpi=300)
    plt.close(fig)


def build_geo_summary(
    deg_all_path: Path,
    validation: dict[str, Any],
    parameters: dict[str, str],
) -> dict[str, Any]:
    deg_all = pd.read_csv(deg_all_path)
    deg_sig = deg_all[deg_all["change"].isin(["Up", "Down"])]
    return {
        "sample_count": validation["sample_count"],
        "control_count": validation["control_count"],
        "case_count": validation["case_count"],
        "case_group": parameters["case_group"],
        "control_group": parameters["control_group"],
        "gene_count": validation["gene_count"],
        "deg_total": int(len(deg_sig)),
        "deg_up": int((deg_all["change"] == "Up").sum()),
        "deg_down": int((deg_all["change"] == "Down").sum()),
    }


def render_geo_deg_summary(run_result: dict[str, Any]) -> None:
    summary = run_result["summary"]
    st.info(run_result["message"])
    metric_cols = st.columns(4)
    metric_cols[0].metric("样本数量", summary["sample_count"])
    metric_cols[1].metric(f"{summary['control_group']} 数量", summary["control_count"])
    metric_cols[2].metric(f"{summary['case_group']} 数量", summary["case_count"])
    metric_cols[3].metric("基因数量", summary["gene_count"])
    metric_cols = st.columns(3)
    metric_cols[0].metric("DEG 总数", summary["deg_total"])
    metric_cols[1].metric("上调基因数", summary["deg_up"])
    metric_cols[2].metric("下调基因数", summary["deg_down"])

    output_dir = Path(run_result["job_dir"]) / "outputs"
    left, right = st.columns(2)
    with left:
        volcano = output_dir / "volcano.png"
        if volcano.exists():
            st.image(str(volcano), caption="火山图", use_column_width=True)
    with right:
        heatmap = output_dir / "heatmap_top20.png"
        if heatmap.exists():
            st.image(str(heatmap), caption="Top 20 DEG 热图", use_column_width=True)

    deg_all = output_dir / "DEG_all.csv"
    if deg_all.exists():
        st.subheader("DEG 表格预览")
        st.dataframe(pd.read_csv(deg_all).head(30), use_container_width=True)


def build_geo_artifacts(job_dir: Path) -> list[dict[str, str]]:
    output_dir = job_dir / "outputs"
    log_dir = job_dir / "logs"
    candidates = [
        ("任务参数 JSON", job_dir / "job_manifest.json", "application/json"),
        ("DEG 全量 CSV", output_dir / "DEG_all.csv", "text/csv"),
        ("DEG 显著 CSV", output_dir / "DEG_sig.csv", "text/csv"),
        ("DEG 上调 CSV", output_dir / "DEG_up.csv", "text/csv"),
        ("DEG 下调 CSV", output_dir / "DEG_down.csv", "text/csv"),
        ("火山图 PNG", output_dir / "volcano.png", "image/png"),
        ("火山图 PDF", output_dir / "volcano.pdf", "application/pdf"),
        ("热图 PNG", output_dir / "heatmap_top20.png", "image/png"),
        ("热图 PDF", output_dir / "heatmap_top20.pdf", "application/pdf"),
        ("处理前箱线图 PNG", output_dir / "boxplot_before.png", "image/png"),
        ("处理后箱线图 PNG", output_dir / "boxplot_after.png", "image/png"),
        ("运行日志", log_dir / "geo_deg.log", "text/plain"),
    ]
    return [
        {"label": label, "path": str(path), "mime": mime}
        for label, path, mime in candidates
        if path.exists()
    ]
