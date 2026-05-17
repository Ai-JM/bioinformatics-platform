from __future__ import annotations

from pathlib import Path
from typing import Any

from modules.config import PageDefinition
from modules.job_manager import (
    create_job_dir,
    create_job_id,
    save_json,
    save_uploaded_files,
    write_job_manifest,
)
from modules.target_processing import (
    export_venn_figures,
    load_target_sets,
    target_set_from_text,
    write_target_excel,
)


def run_placeholder_pipeline(
    *,
    page: PageDefinition,
    parameters: dict[str, str],
    uploaded_files: list[Any],
) -> dict[str, str]:
    job_id = create_job_id(page.key)
    job_dir = create_job_dir(job_id)
    input_files = save_uploaded_files(uploaded_files, job_dir)

    manifest_path = write_job_manifest(
        job_dir,
        job_id=job_id,
        module_key=page.key,
        module_label=page.label,
        parameters=parameters,
        input_files=input_files,
    )

    placeholder_result = {
        "job_id": job_id,
        "module": page.label,
        "message": "框架已完成任务初始化。后续可在此处接入 Python、R 脚本或 Docker 容器执行真实分析。",
        "expected_outputs": expected_outputs_for(page.key),
    }
    result_path = job_dir / "outputs" / "placeholder_result.json"
    save_json(placeholder_result, result_path)

    log_path = job_dir / "logs" / "run.log"
    log_path.write_text(
        "\n".join(
            [
                f"job_id={job_id}",
                f"module={page.key}",
                f"inputs={len(input_files)}",
                "status=placeholder_completed",
            ]
        ),
        encoding="utf-8",
    )

    return {
        "job_id": job_id,
        "job_dir": str(job_dir),
        "manifest_path": str(manifest_path),
        "result_path": str(result_path),
        "log_path": str(log_path),
        "artifacts": [
            {"label": "任务参数 JSON", "path": str(manifest_path), "mime": "application/json"},
            {"label": "占位结果 JSON", "path": str(result_path), "mime": "application/json"},
            {"label": "运行日志", "path": str(log_path), "mime": "text/plain"},
        ],
    }


def run_network_pharmacology_pipeline(
    *,
    page: PageDefinition,
    parameters: dict[str, str],
    component_files: list[Any],
    disease_files: list[Any],
) -> dict[str, Any]:
    job_id = create_job_id(page.key)
    job_dir = create_job_dir(job_id)
    component_paths = save_uploaded_group(component_files, job_dir, "component_targets")
    disease_paths = save_uploaded_group(disease_files, job_dir, "disease_targets")
    input_files = component_paths + disease_paths

    manifest_path = write_job_manifest(
        job_dir,
        job_id=job_id,
        module_key=page.key,
        module_label=page.label,
        parameters=parameters,
        input_files=input_files,
    )

    artifacts: list[dict[str, str]] = [
        {"label": "任务参数 JSON", "path": str(manifest_path), "mime": "application/json"}
    ]
    summary: dict[str, Any] = {"job_id": job_id, "groups": {}}

    if component_paths:
        component_sets = load_target_sets(
            component_paths,
            requested_column=parameters.get("component_target_column", "auto"),
            normalize_case=parameters.get("normalize_case", "upper"),
        )
        component_excel = job_dir / "outputs" / "component_targets.xlsx"
        write_target_excel(component_sets, component_excel)
        artifacts.append(
            {
                "label": "单成分靶点 Excel",
                "path": str(component_excel),
                "mime": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            }
        )
        for figure_path in export_venn_figures(
            component_sets,
            job_dir / "outputs" / "component_targets_venn",
            "Component Targets Venn Diagram",
        ):
            artifacts.append(artifact_for_path("单成分靶点 Venn", figure_path))
        summary["groups"]["component_targets"] = summarize_sets(component_sets)

    if disease_paths:
        disease_sets = load_target_sets(
            disease_paths,
            requested_column=parameters.get("disease_target_column", "auto"),
            normalize_case=parameters.get("normalize_case", "upper"),
        )
        disease_excel = job_dir / "outputs" / "disease_targets.xlsx"
        write_target_excel(disease_sets, disease_excel)
        artifacts.append(
            {
                "label": "疾病靶点 Excel",
                "path": str(disease_excel),
                "mime": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            }
        )
        for figure_path in export_venn_figures(
            disease_sets,
            job_dir / "outputs" / "disease_targets_venn",
            "Disease Targets Venn Diagram",
        ):
            artifacts.append(artifact_for_path("疾病靶点 Venn", figure_path))
        summary["groups"]["disease_targets"] = summarize_sets(disease_sets)

    if not component_paths and not disease_paths:
        raise ValueError("请至少上传一组单成分靶点或疾病靶点文件。")

    result_path = job_dir / "outputs" / "network_pharmacology_summary.json"
    save_json(summary, result_path)
    artifacts.append({"label": "结果摘要 JSON", "path": str(result_path), "mime": "application/json"})

    log_path = job_dir / "logs" / "run.log"
    log_path.write_text(
        "\n".join(
            [
                f"job_id={job_id}",
                f"module={page.key}",
                f"component_files={len(component_paths)}",
                f"disease_files={len(disease_paths)}",
                "status=completed",
            ]
        ),
        encoding="utf-8",
    )

    return {
        "job_id": job_id,
        "job_dir": str(job_dir),
        "manifest_path": str(manifest_path),
        "result_path": str(result_path),
        "log_path": str(log_path),
        "artifacts": artifacts,
    }


def run_venn_pipeline(
    *,
    page: PageDefinition,
    parameters: dict[str, str],
    uploaded_files: list[Any],
) -> dict[str, Any]:
    job_id = create_job_id(page.key)
    job_dir = create_job_dir(job_id)
    input_files = save_uploaded_files(uploaded_files, job_dir)
    manifest_path = write_job_manifest(
        job_dir,
        job_id=job_id,
        module_key=page.key,
        module_label=page.label,
        parameters=parameters,
        input_files=input_files,
    )
    if not input_files:
        raise ValueError("请至少上传 2 个靶点列表文件。")

    target_sets = load_target_sets(
        input_files,
        requested_column=parameters.get("target_column", "auto"),
        normalize_case=parameters.get("normalize_case", "upper"),
    )
    excel_path = job_dir / "outputs" / "venn_targets.xlsx"
    write_target_excel(target_sets, excel_path)
    figure_paths = export_venn_figures(
        target_sets,
        job_dir / "outputs" / "venn_targets",
        parameters.get("plot_title", "Venn targets"),
    )
    result_path = job_dir / "outputs" / "venn_summary.json"
    save_json({"job_id": job_id, "sets": summarize_sets(target_sets)}, result_path)
    log_path = job_dir / "logs" / "run.log"
    log_path.write_text(f"job_id={job_id}\nmodule={page.key}\nstatus=completed", encoding="utf-8")

    artifacts = [
        {"label": "任务参数 JSON", "path": str(manifest_path), "mime": "application/json"},
        {
            "label": "靶点交并集 Excel",
            "path": str(excel_path),
            "mime": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        },
        {"label": "结果摘要 JSON", "path": str(result_path), "mime": "application/json"},
    ]
    artifacts.extend(artifact_for_path("Venn 图", path) for path in figure_paths)

    return {
        "job_id": job_id,
        "job_dir": str(job_dir),
        "manifest_path": str(manifest_path),
        "result_path": str(result_path),
        "log_path": str(log_path),
        "artifacts": artifacts,
    }


def run_venn_builder_pipeline(
    *,
    page: PageDefinition,
    parameters: dict[str, str],
    text_sets: list[dict[str, str]],
    uploaded_files: list[Any],
) -> dict[str, Any]:
    job_id = create_job_id(page.key)
    job_dir = create_job_dir(job_id)
    input_files = save_uploaded_files(uploaded_files, job_dir)
    manifest_path = write_job_manifest(
        job_dir,
        job_id=job_id,
        module_key=page.key,
        module_label=page.label,
        parameters={**parameters, "manual_set_count": str(len(text_sets))},
        input_files=input_files,
    )

    normalize_case = parameters.get("normalize_case", "upper")
    manual_sets = [
        target_set_from_text(item["name"], item["text"], normalize_case=normalize_case)
        for item in text_sets
        if item.get("text", "").strip()
    ]
    file_sets = load_target_sets(
        input_files,
        requested_column=parameters.get("target_column", "auto"),
        normalize_case=normalize_case,
    )
    target_sets = [item for item in manual_sets + file_sets if item.targets]

    if len(target_sets) < 2:
        raise ValueError("请至少提供 2 组非空集合。")
    if len(target_sets) > 6:
        raise ValueError("当前 Venn 图模块最多支持 6 组集合。")

    text_source_path = job_dir / "inputs" / "manual_sets.txt"
    text_source_path.write_text(format_manual_sets(text_sets), encoding="utf-8")

    excel_path = job_dir / "outputs" / "venn_union_intersections.xlsx"
    write_target_excel(target_sets, excel_path)
    figure_paths = export_venn_figures(
        target_sets,
        job_dir / "outputs" / "nature_style_venn",
        parameters.get("plot_title", "Venn analysis"),
    )

    summary = {
        "job_id": job_id,
        "plot_style": "Nature-style clean Venn/flower Venn",
        "set_count": len(target_sets),
        "sets": summarize_sets(target_sets),
        "outputs": [str(path) for path in [excel_path, *figure_paths]],
    }
    result_path = job_dir / "outputs" / "venn_summary.json"
    save_json(summary, result_path)

    log_path = job_dir / "logs" / "run.log"
    log_path.write_text(
        "\n".join(
            [
                f"job_id={job_id}",
                f"module={page.key}",
                f"sets={len(target_sets)}",
                "status=completed",
            ]
        ),
        encoding="utf-8",
    )

    artifacts = [
        {"label": "任务参数 JSON", "path": str(manifest_path), "mime": "application/json"},
        {
            "label": "交并集 Excel",
            "path": str(excel_path),
            "mime": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        },
        {"label": "结果摘要 JSON", "path": str(result_path), "mime": "application/json"},
        {"label": "手动输入 TXT", "path": str(text_source_path), "mime": "text/plain"},
    ]
    artifacts.extend(artifact_for_path("Nature Venn", path) for path in figure_paths)

    return {
        "job_id": job_id,
        "job_dir": str(job_dir),
        "manifest_path": str(manifest_path),
        "result_path": str(result_path),
        "log_path": str(log_path),
        "artifacts": artifacts,
    }


def expected_outputs_for(module_key: str) -> list[str]:
    outputs_by_module = {
        "network_pharmacology": [
            "component_targets.xlsx",
            "component_targets_venn.png",
            "component_targets_venn.pdf",
            "component_targets_venn.svg",
            "disease_targets.xlsx",
            "disease_targets_venn.png",
            "disease_targets_venn.pdf",
            "disease_targets_venn.svg",
        ],
        "geo_deg": ["deg_results.csv", "volcano_plot.pdf", "heatmap.pdf"],
        "core_targets": ["intersection_targets.csv", "target_source_matrix.csv"],
        "enrichment": ["go_results.csv", "kegg_results.csv", "enrichment_plots.pdf"],
        "venn_analysis": ["venn_targets.xlsx", "venn_targets.png", "venn_targets.pdf", "venn_targets.svg"],
        "md_plotting": ["md_summary.csv", "md_plot.pdf"],
    }
    return outputs_by_module.get(module_key, [])


def build_command_preview(script_path: Path, parameters: dict[str, str], job_dir: Path) -> list[str]:
    command = ["Rscript" if script_path.suffix.lower() == ".r" else "python", str(script_path)]
    for key, value in parameters.items():
        command.extend([f"--{key}", value])
    command.extend(["--outdir", str(job_dir / "outputs")])
    return command


def save_uploaded_group(uploaded_files: list[Any], job_dir: Path, group_name: str) -> list[str]:
    saved_paths: list[str] = []
    input_dir = job_dir / "inputs" / group_name
    input_dir.mkdir(parents=True, exist_ok=True)
    for uploaded_file in uploaded_files:
        destination = input_dir / uploaded_file.name
        destination.write_bytes(uploaded_file.getbuffer())
        saved_paths.append(str(destination))
    return saved_paths


def summarize_sets(target_sets: list[Any]) -> list[dict[str, Any]]:
    return [{"name": item.name, "target_count": len(item.targets)} for item in target_sets]


def artifact_for_path(label_prefix: str, path: Path) -> dict[str, str]:
    suffix = path.suffix.lower()
    mime_by_suffix = {
        ".png": "image/png",
        ".pdf": "application/pdf",
        ".svg": "image/svg+xml",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        ".json": "application/json",
        ".log": "text/plain",
        ".txt": "text/plain",
    }
    return {
        "label": f"{label_prefix} {suffix.lstrip('.').upper()}",
        "path": str(path),
        "mime": mime_by_suffix.get(suffix, "application/octet-stream"),
    }


def format_manual_sets(text_sets: list[dict[str, str]]) -> str:
    blocks = []
    for item in text_sets:
        if item.get("text", "").strip():
            blocks.append(f"> {item.get('name', 'Set')}\n{item['text'].strip()}")
    return "\n\n".join(blocks)
