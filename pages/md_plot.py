from __future__ import annotations

import io
import zipfile
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

from modules.config import PageDefinition
from modules.job_manager import create_job_dir, create_job_id, write_job_manifest
from modules.md_parser import (
    detect_md_file_type,
    parse_decomp_dat,
    parse_mmpbsa_csv,
    parse_mmpbsa_dat,
    parse_xvg,
)
from modules.ui_components import render_download_panel


PLOT_META = {
    "rmsd": ("Fig1_RMSD", "RMSD", "Time ({unit})", "RMSD (nm)"),
    "rmsf": ("Fig2_RMSF", "RMSF", "Residue index", "RMSF (nm)"),
    "gyrate": ("Fig3_Rg", "Radius of gyration", "Time ({unit})", "Rg (nm)"),
    "sasa": ("Fig4_SASA", "SASA", "Time ({unit})", "SASA (nm^2)"),
    "hbond": ("Fig5_Hbond", "Hydrogen bonds", "Time ({unit})", "H-bond count"),
    "mindist": ("Fig_Mindist", "Minimum distance", "Time ({unit})", "Distance (nm)"),
    "contacts": ("Fig_Contacts", "Contacts", "Time ({unit})", "Contacts"),
}


def render_md_plot_page(page: PageDefinition) -> None:
    st.title("MD result plotting")
    st.caption("Upload GROMACS XVG and MMPBSA outputs to generate clean SCI-style figures and summary tables.")

    with st.form("md_plot_form", clear_on_submit=False):
        uploaded_files = st.file_uploader(
            "Upload XVG, MMPBSA, or ZIP files",
            type=["xvg", "csv", "dat", "zip"],
            accept_multiple_files=True,
            help="Supported examples: rmsd.xvg, rmsf.xvg, gyrate.xvg, sasa.xvg, hbond.xvg, FINAL_RESULTS_MMPBSA.csv/dat.",
        )

        st.subheader("Parameters")
        c1, c2, c3 = st.columns(3)
        with c1:
            project_name = st.text_input("Project name", value="MD_project")
            time_unit = st.selectbox("Time unit", ["ps", "ns"], index=1)
            convert_ps_to_ns = st.checkbox("Convert ps to ns", value=True)
        with c2:
            figure_width = st.number_input("Figure width", min_value=2.0, max_value=20.0, value=6.5, step=0.5)
            figure_height = st.number_input("Figure height", min_value=2.0, max_value=20.0, value=4.8, step=0.5)
            dpi = st.number_input("DPI", min_value=72, max_value=1200, value=300, step=50)
        with c3:
            font_size = st.number_input("Font size", min_value=6, max_value=24, value=11, step=1)
            make_summary = st.checkbox("Generate combined figure", value=True)
            export_pdf = st.checkbox("Export PDF", value=True)
            export_clean_csv = st.checkbox("Export cleaned CSV", value=True)

        submitted = st.form_submit_button("Run MD plotting", type="primary")

    if submitted:
        if not uploaded_files:
            st.error("Please upload at least one MD result file.")
            return
        parameters = {
            "project_name": project_name,
            "time_unit": time_unit,
            "convert_ps_to_ns": str(convert_ps_to_ns),
            "figure_width": str(figure_width),
            "figure_height": str(figure_height),
            "dpi": str(dpi),
            "font_size": str(font_size),
            "make_summary": str(make_summary),
            "export_pdf": str(export_pdf),
            "export_clean_csv": str(export_clean_csv),
        }
        try:
            with st.spinner("Parsing MD files and generating figures..."):
                run_result = run_md_plotting(
                    page=page,
                    uploaded_files=uploaded_files,
                    parameters=parameters,
                )
            st.session_state[f"{page.key}_last_result"] = run_result
            st.success(f"Job completed: {run_result['job_id']}")
        except Exception as exc:
            st.error(f"Run failed: {exc}")
            return

    run_result = st.session_state.get(f"{page.key}_last_result")
    if run_result:
        render_md_result(run_result)
        render_download_panel(run_result)


def run_md_plotting(
    *,
    page: PageDefinition,
    uploaded_files: list[Any],
    parameters: dict[str, str],
) -> dict[str, Any]:
    job_id = create_job_id(page.key)
    job_dir = create_job_dir(job_id)
    input_dir = job_dir / "inputs"
    output_dir = job_dir / "outputs"
    table_dir = output_dir / "md_clean_tables"
    figure_dir = output_dir / "md_figures"
    log_path = job_dir / "logs" / "md_plot.log"
    table_dir.mkdir(parents=True, exist_ok=True)
    figure_dir.mkdir(parents=True, exist_ok=True)

    input_files = save_and_expand_uploads(uploaded_files, input_dir)
    manifest_path = write_job_manifest(
        job_dir,
        job_id=job_id,
        module_key=page.key,
        module_label=page.label,
        parameters=parameters,
        input_files=[str(path) for path in input_files],
    )

    detected: list[dict[str, str]] = []
    xvg_tables: dict[str, pd.DataFrame] = {}
    mmpbsa_tables: list[pd.DataFrame] = []
    decomp_tables: list[pd.DataFrame] = []
    log_lines = [f"job_id={job_id}", f"project_name={parameters['project_name']}"]

    for file_path in input_files:
        file_type = detect_md_file_type(file_path.name)
        detected.append({"file": file_path.name, "type": file_type})
        try:
            if file_path.suffix.lower() == ".xvg":
                dataframe = parse_xvg(file_path)
                if dataframe.empty:
                    log_lines.append(f"skip_empty={file_path.name}")
                    continue
                metric = file_type if file_type in PLOT_META else file_path.stem.lower()
                dataframe = prepare_xvg_table(dataframe, metric, parameters)
                xvg_tables[metric] = dataframe
            elif file_type == "mmpbsa_decomp":
                decomp_tables.append(parse_decomp_dat(file_path))
            elif file_type == "mmpbsa":
                if file_path.suffix.lower() == ".csv":
                    mmpbsa_tables.append(parse_mmpbsa_csv(file_path))
                else:
                    mmpbsa_tables.append(parse_mmpbsa_dat(file_path))
        except Exception as exc:
            log_lines.append(f"parse_failed={file_path.name}: {exc}")

    if not xvg_tables and not mmpbsa_tables and not decomp_tables:
        raise ValueError("No supported MD result table could be parsed.")

    figure_paths: list[Path] = []
    table_paths: list[Path] = []
    if parameters["export_clean_csv"] == "True":
        for metric, dataframe in xvg_tables.items():
            table_path = table_dir / f"{metric}_clean.csv"
            dataframe.to_csv(table_path, index=False)
            table_paths.append(table_path)

    for metric, dataframe in xvg_tables.items():
        figure_paths.extend(save_metric_figure(metric, dataframe, figure_dir, parameters))

    mmpbsa_summary = build_mmpbsa_summary(mmpbsa_tables)
    if not mmpbsa_summary.empty:
        summary_table_path = table_dir / "mmpbsa_clean.csv"
        if parameters["export_clean_csv"] == "True":
            mmpbsa_summary.to_csv(summary_table_path, index=False)
            table_paths.append(summary_table_path)
        figure_paths.extend(save_mmpbsa_figure(mmpbsa_summary, figure_dir, parameters))

    if parameters["make_summary"] == "True" and xvg_tables:
        figure_paths.extend(save_combined_figure(xvg_tables, figure_dir, parameters))

    md_summary = build_md_summary(detected, xvg_tables, mmpbsa_summary, decomp_tables)
    summary_path = output_dir / "md_summary.csv"
    md_summary.to_csv(summary_path, index=False)

    zip_path = output_dir / "md_figures.zip"
    create_zip(zip_path, figure_paths)

    log_lines.extend(
        [
            f"detected_files={len(detected)}",
            f"xvg_metrics={','.join(xvg_tables.keys())}",
            f"mmpbsa_tables={len(mmpbsa_tables)}",
            f"figures={len(figure_paths)}",
            "status=completed",
        ]
    )
    log_path.write_text("\n".join(log_lines), encoding="utf-8")

    artifacts = build_md_artifacts(manifest_path, summary_path, log_path, table_paths, figure_paths, zip_path)
    return {
        "job_id": job_id,
        "job_dir": str(job_dir),
        "manifest_path": str(manifest_path),
        "result_path": str(summary_path),
        "log_path": str(log_path),
        "detected": detected,
        "summary": md_summary.to_dict("records"),
        "mmpbsa_summary": mmpbsa_summary.to_dict("records"),
        "artifacts": artifacts,
    }


def save_and_expand_uploads(uploaded_files: list[Any], input_dir: Path) -> list[Path]:
    saved_paths: list[Path] = []
    for uploaded_file in uploaded_files:
        destination = input_dir / Path(uploaded_file.name).name
        destination.write_bytes(uploaded_file.getbuffer())
        if destination.suffix.lower() == ".zip":
            extract_dir = input_dir / f"{destination.stem}_extracted"
            extract_dir.mkdir(parents=True, exist_ok=True)
            saved_paths.extend(extract_supported_zip(destination, extract_dir))
        else:
            saved_paths.append(destination)
    return saved_paths


def extract_supported_zip(zip_path: Path, extract_dir: Path) -> list[Path]:
    extracted: list[Path] = []
    allowed_suffixes = {".xvg", ".csv", ".dat"}
    with zipfile.ZipFile(zip_path) as archive:
        for member in archive.infolist():
            member_name = Path(member.filename)
            if member.is_dir() or member_name.suffix.lower() not in allowed_suffixes:
                continue
            safe_name = member_name.name
            if not safe_name:
                continue
            destination = extract_dir / safe_name
            destination.write_bytes(archive.read(member))
            extracted.append(destination)
    return extracted


def prepare_xvg_table(dataframe: pd.DataFrame, metric: str, parameters: dict[str, str]) -> pd.DataFrame:
    output = dataframe.copy()
    output = output.rename(columns={"x": "x", "y": "y"})
    if parameters["convert_ps_to_ns"] == "True" and metric != "rmsf":
        output["x"] = output["x"] / 1000.0
    return output


def save_metric_figure(metric: str, dataframe: pd.DataFrame, figure_dir: Path, parameters: dict[str, str]) -> list[Path]:
    base_name, title, xlabel, ylabel = PLOT_META.get(
        metric,
        (f"Fig_{metric}", metric.upper(), "X", "Y"),
    )
    unit = "ns" if parameters["convert_ps_to_ns"] == "True" and metric != "rmsf" else parameters["time_unit"]
    paths: list[Path] = []
    fig, ax = plt.subplots(figsize=(float(parameters["figure_width"]), float(parameters["figure_height"])))
    apply_sci_style(ax, int(parameters["font_size"]))
    ax.plot(dataframe["x"], dataframe["y"], color="#1f77b4", linewidth=1.4)
    ax.set_title(title, fontsize=int(parameters["font_size"]) + 2)
    ax.set_xlabel(xlabel.format(unit=unit))
    ax.set_ylabel(ylabel)
    fig.tight_layout()
    png_path = figure_dir / f"{base_name}.png"
    fig.savefig(png_path, dpi=int(parameters["dpi"]))
    paths.append(png_path)
    if parameters["export_pdf"] == "True":
        pdf_path = figure_dir / f"{base_name}.pdf"
        fig.savefig(pdf_path)
        paths.append(pdf_path)
    plt.close(fig)
    return paths


def save_mmpbsa_figure(dataframe: pd.DataFrame, figure_dir: Path, parameters: dict[str, str]) -> list[Path]:
    term_col, value_col = pick_mmpbsa_columns(dataframe)
    plot_df = dataframe[[term_col, value_col]].dropna().copy()
    plot_df[value_col] = pd.to_numeric(plot_df[value_col], errors="coerce")
    plot_df = plot_df.dropna(subset=[value_col]).tail(12)
    if plot_df.empty:
        return []

    fig, ax = plt.subplots(figsize=(float(parameters["figure_width"]), float(parameters["figure_height"])))
    apply_sci_style(ax, int(parameters["font_size"]))
    colors = ["#3b82f6" if value >= 0 else "#ef4444" for value in plot_df[value_col]]
    ax.barh(plot_df[term_col].astype(str), plot_df[value_col], color=colors, alpha=0.86)
    ax.axvline(0, color="#111827", linewidth=0.8)
    ax.set_title("MMPBSA binding energy", fontsize=int(parameters["font_size"]) + 2)
    ax.set_xlabel(value_col)
    fig.tight_layout()
    png_path = figure_dir / "Fig6_MMPBSA.png"
    paths = [png_path]
    fig.savefig(png_path, dpi=int(parameters["dpi"]))
    if parameters["export_pdf"] == "True":
        pdf_path = figure_dir / "Fig6_MMPBSA.pdf"
        fig.savefig(pdf_path)
        paths.append(pdf_path)
    plt.close(fig)
    return paths


def save_combined_figure(
    xvg_tables: dict[str, pd.DataFrame],
    figure_dir: Path,
    parameters: dict[str, str],
) -> list[Path]:
    metrics = [metric for metric in ["rmsd", "rmsf", "gyrate", "sasa", "hbond", "mindist", "contacts"] if metric in xvg_tables]
    if not metrics:
        return []
    rows = (len(metrics) + 1) // 2
    fig, axes = plt.subplots(rows, 2, figsize=(float(parameters["figure_width"]) * 1.55, 3.4 * rows))
    axes_list = list(axes.flat) if hasattr(axes, "flat") else [axes]
    for ax, metric in zip(axes_list, metrics):
        _, title, xlabel, ylabel = PLOT_META.get(metric, (metric, metric.upper(), "X", "Y"))
        unit = "ns" if parameters["convert_ps_to_ns"] == "True" and metric != "rmsf" else parameters["time_unit"]
        apply_sci_style(ax, int(parameters["font_size"]))
        table = xvg_tables[metric]
        ax.plot(table["x"], table["y"], color="#1f77b4", linewidth=1.2)
        ax.set_title(title)
        ax.set_xlabel(xlabel.format(unit=unit))
        ax.set_ylabel(ylabel)
    for ax in axes_list[len(metrics) :]:
        ax.axis("off")
    fig.tight_layout()
    png_path = figure_dir / "Fig_MD_summary.png"
    paths = [png_path]
    fig.savefig(png_path, dpi=int(parameters["dpi"]))
    if parameters["export_pdf"] == "True":
        pdf_path = figure_dir / "Fig_MD_summary.pdf"
        fig.savefig(pdf_path)
        paths.append(pdf_path)
    plt.close(fig)
    return paths


def apply_sci_style(ax: plt.Axes, font_size: int) -> None:
    plt.rcParams.update({"font.size": font_size, "font.family": "Arial"})
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(True, color="#e5e7eb", linewidth=0.6, alpha=0.8)
    ax.tick_params(direction="out", length=3, width=0.8)


def build_mmpbsa_summary(tables: list[pd.DataFrame]) -> pd.DataFrame:
    if not tables:
        return pd.DataFrame()
    normalized: list[pd.DataFrame] = []
    for table in tables:
        if table.empty:
            continue
        copy = table.copy()
        copy.columns = [str(column).strip() for column in copy.columns]
        normalized.append(copy)
    if not normalized:
        return pd.DataFrame()
    return pd.concat(normalized, ignore_index=True, sort=False).dropna(how="all")


def pick_mmpbsa_columns(dataframe: pd.DataFrame) -> tuple[str, str]:
    columns = list(dataframe.columns)
    term_col = "term" if "term" in columns else columns[0]
    candidates = [column for column in columns if str(column).lower() in {"average", "delta total", "binding", "total"}]
    if candidates:
        value_col = candidates[0]
    else:
        numeric_cols = [column for column in columns if pd.to_numeric(dataframe[column], errors="coerce").notna().any()]
        value_col = numeric_cols[0] if numeric_cols else columns[-1]
    return term_col, value_col


def build_md_summary(
    detected: list[dict[str, str]],
    xvg_tables: dict[str, pd.DataFrame],
    mmpbsa_summary: pd.DataFrame,
    decomp_tables: list[pd.DataFrame],
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for metric, dataframe in xvg_tables.items():
        rows.append(
            {
                "type": metric,
                "file_count": sum(1 for item in detected if item["type"] == metric),
                "n_points": len(dataframe),
                "x_min": dataframe["x"].min(),
                "x_max": dataframe["x"].max(),
                "y_mean": dataframe["y"].mean(),
                "y_sd": dataframe["y"].std(),
            }
        )
    if not mmpbsa_summary.empty:
        rows.append(
            {
                "type": "mmpbsa",
                "file_count": sum(1 for item in detected if item["type"] == "mmpbsa"),
                "n_points": len(mmpbsa_summary),
                "x_min": None,
                "x_max": None,
                "y_mean": None,
                "y_sd": None,
            }
        )
    if decomp_tables:
        rows.append(
            {
                "type": "mmpbsa_decomp",
                "file_count": len(decomp_tables),
                "n_points": 0,
                "x_min": None,
                "x_max": None,
                "y_mean": None,
                "y_sd": None,
            }
        )
    return pd.DataFrame(rows)


def create_zip(zip_path: Path, paths: list[Path]) -> None:
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in paths:
            if path.exists():
                archive.write(path, arcname=path.name)


def build_md_artifacts(
    manifest_path: Path,
    summary_path: Path,
    log_path: Path,
    table_paths: list[Path],
    figure_paths: list[Path],
    zip_path: Path,
) -> list[dict[str, str]]:
    artifacts = [
        {"label": "Job manifest JSON", "path": str(manifest_path), "mime": "application/json"},
        {"label": "MD summary CSV", "path": str(summary_path), "mime": "text/csv"},
        {"label": "MD plot log", "path": str(log_path), "mime": "text/plain"},
    ]
    artifacts.extend({"label": f"Clean table {path.name}", "path": str(path), "mime": "text/csv"} for path in table_paths)
    for path in figure_paths:
        mime = "application/pdf" if path.suffix.lower() == ".pdf" else "image/png"
        artifacts.append({"label": f"MD figure {path.name}", "path": str(path), "mime": mime})
    artifacts.append({"label": "All MD figures ZIP", "path": str(zip_path), "mime": "application/zip"})
    return artifacts


def render_md_result(run_result: dict[str, Any]) -> None:
    st.subheader("Detected MD file types")
    st.dataframe(pd.DataFrame(run_result.get("detected", [])), use_container_width=True)

    summary = pd.DataFrame(run_result.get("summary", []))
    if not summary.empty:
        st.subheader("MD summary")
        st.dataframe(summary, use_container_width=True)

    figure_dir = Path(run_result["job_dir"]) / "outputs" / "md_figures"
    image_paths = sorted(figure_dir.glob("*.png"))
    if image_paths:
        st.subheader("Figures")
        for left, right in batched(image_paths, 2):
            cols = st.columns(2)
            with cols[0]:
                st.image(str(left), caption=left.stem, use_column_width=True)
            if right is not None:
                with cols[1]:
                    st.image(str(right), caption=right.stem, use_column_width=True)

    mmpbsa_summary = pd.DataFrame(run_result.get("mmpbsa_summary", []))
    if not mmpbsa_summary.empty:
        st.subheader("MMPBSA binding energy table")
        st.dataframe(mmpbsa_summary, use_container_width=True)


def batched(paths: list[Path], size: int) -> list[tuple[Path, Path | None]]:
    output: list[tuple[Path, Path | None]] = []
    for index in range(0, len(paths), size):
        first = paths[index]
        second = paths[index + 1] if index + 1 < len(paths) else None
        output.append((first, second))
    return output
