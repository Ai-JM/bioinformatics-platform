from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import streamlit as st

from modules.config import PAGE_DEFINITIONS, PageDefinition
from modules.pipeline_stubs import run_network_pharmacology_pipeline, run_venn_builder_pipeline


Runner = Callable[..., dict[str, str]]


def render_home_page() -> None:
    st.title("自动化生信分析平台")
    st.caption("Streamlit 第一版框架")

    st.write(
        "本平台第一版已经预留网络药理学、GEO 差异分析、核心靶点筛选、富集分析、"
        "Venn 图分析和 MD 结果绘图模块。每次运行都会生成唯一 job_id，"
        "并将输入、参数、日志和占位结果保存到 results/job_id/。"
    )

    st.subheader("模块")
    for page in PAGE_DEFINITIONS:
        if page.key == "home":
            continue
        st.markdown(f"- **{page.label}**：{page.description}")


def render_network_pharmacology_page(page: PageDefinition) -> None:
    st.title(page.label)
    st.caption("多来源靶点整理、Venn 图导出和 Excel 结果表生成")

    st.markdown(
        "上传多个单成分靶点文件和多个疾病靶点文件。运行后会分别生成 Venn 图 "
        "（PNG、PDF、SVG）和靶点 Excel 表。"
    )

    with st.form(key=f"{page.key}_form", clear_on_submit=False):
        st.subheader("输入数据")
        left, right = st.columns(2)
        with left:
            st.markdown("**单成分靶点数据**")
            component_files = st.file_uploader(
                "上传单成分靶点表",
                type=page.accepted_types,
                accept_multiple_files=True,
                help="每个文件代表一个成分或一个靶点来源。支持 CSV、TSV、TXT、XLSX。",
                key="component_target_files",
            )
        with right:
            st.markdown("**疾病靶点数据**")
            disease_files = st.file_uploader(
                "上传疾病靶点表",
                type=page.accepted_types,
                accept_multiple_files=True,
                help="每个文件代表一个疾病数据库或一个疾病靶点来源。支持 CSV、TSV、TXT、XLSX。",
                key="disease_target_files",
            )

        st.subheader("参数")
        parameter_cols = st.columns(3)
        parameters: dict[str, str] = {}
        for index, parameter in enumerate(page.parameters):
            with parameter_cols[index % 3]:
                parameters[parameter.name] = st.text_input(
                    parameter.label,
                    value=parameter.default,
                    help=parameter.help or None,
                )

        submitted = st.form_submit_button("运行分析", type="primary")

    if submitted:
        try:
            with st.spinner("正在整理靶点并生成 Venn 图..."):
                run_result = run_network_pharmacology_pipeline(
                    page=page,
                    parameters=parameters,
                    component_files=component_files or [],
                    disease_files=disease_files or [],
                )
            st.session_state[f"{page.key}_last_result"] = run_result
            st.success(f"任务已完成：{run_result['job_id']}")
        except Exception as exc:
            st.error(f"运行失败：{exc}")
            return

    render_download_panel(st.session_state.get(f"{page.key}_last_result"))


def render_venn_builder_page(page: PageDefinition) -> None:
    st.title(page.label)
    st.caption("多集合交并集分析与 Nature 风格 Venn 图导出")
    st.markdown(
        "支持 2-6 组集合。每组可以直接粘贴基因/靶点列表，也可以上传 CSV、TSV、TXT、XLSX 文件。"
        "输出包含 PNG、PDF、SVG 和按列排列的交并集 Excel。"
    )

    if "venn_set_count" not in st.session_state:
        st.session_state.venn_set_count = 3

    control_cols = st.columns([1, 1, 3])
    with control_cols[0]:
        if st.button("添加集合", use_container_width=True) and st.session_state.venn_set_count < 6:
            st.session_state.venn_set_count += 1
            st.rerun()
    with control_cols[1]:
        if st.button("删除集合", use_container_width=True) and st.session_state.venn_set_count > 2:
            st.session_state.venn_set_count -= 1
            st.rerun()

    with st.form(key=f"{page.key}_form", clear_on_submit=False):
        st.subheader("手动输入集合")
        text_sets: list[dict[str, str]] = []
        for index in range(st.session_state.venn_set_count):
            left, right = st.columns([1, 2])
            default_name = f"Set {index + 1}"
            with left:
                name = st.text_input(
                    f"集合 {index + 1} 名称",
                    value=st.session_state.get(f"venn_name_{index}", default_name),
                    key=f"venn_name_{index}",
                )
            with right:
                text = st.text_area(
                    f"集合 {index + 1} 内容",
                    value=st.session_state.get(f"venn_text_{index}", ""),
                    key=f"venn_text_{index}",
                    height=110,
                    placeholder="每行一个基因，也支持逗号、分号、竖线分隔",
                )
            text_sets.append({"name": name, "text": text})

        st.subheader("上传文件补充")
        uploaded_files = st.file_uploader(
            "上传集合文件",
            type=page.accepted_types,
            accept_multiple_files=True,
            help="每个文件会作为一个独立集合。文件名会作为集合名。",
        )

        st.subheader("图形与解析参数")
        param_cols = st.columns(3)
        with param_cols[0]:
            plot_title = st.text_input("图标题", value="Venn analysis")
        with param_cols[1]:
            target_column = st.text_input("文件靶点列名", value="auto")
        with param_cols[2]:
            normalize_case = st.selectbox("基因名大小写", ["upper", "keep"], index=0)

        submitted = st.form_submit_button("生成 Venn 图", type="primary")

    if submitted:
        parameters = {
            "plot_title": plot_title,
            "target_column": target_column,
            "normalize_case": normalize_case,
            "style": "Nature-style clean Venn",
        }
        try:
            with st.spinner("正在计算交并集并绘制 Nature 风格 Venn 图..."):
                run_result = run_venn_builder_pipeline(
                    page=page,
                    parameters=parameters,
                    text_sets=text_sets,
                    uploaded_files=uploaded_files or [],
                )
            st.session_state[f"{page.key}_last_result"] = run_result
            st.success(f"任务已完成：{run_result['job_id']}")
        except Exception as exc:
            st.error(f"运行失败：{exc}")
            return

    render_download_panel(st.session_state.get(f"{page.key}_last_result"))


def render_analysis_page(page: PageDefinition, runner: Runner) -> None:
    st.title(page.label)
    st.caption(page.description)

    with st.form(key=f"{page.key}_form", clear_on_submit=False):
        uploaded_files = st.file_uploader(
            "上传文件",
            type=page.accepted_types,
            accept_multiple_files=True,
            help="可上传一个或多个输入文件。运行后文件会保存到当前 job 的 inputs/ 目录。",
        )

        st.subheader("参数")
        parameters: dict[str, str] = {}
        parameter_cols = st.columns(3) if page.parameters else []
        for index, parameter in enumerate(page.parameters):
            with parameter_cols[index % 3]:
                parameters[parameter.name] = st.text_input(
                    parameter.label,
                    value=parameter.default,
                    help=parameter.help or None,
                )

        submitted = st.form_submit_button("运行分析", type="primary")

    if not submitted:
        render_download_panel(st.session_state.get(f"{page.key}_last_result"))
        return

    try:
        with st.spinner("正在创建任务并保存输入..."):
            run_result = runner(
                page=page,
                parameters=parameters,
                uploaded_files=uploaded_files or [],
            )
        st.session_state[f"{page.key}_last_result"] = run_result
    except Exception as exc:
        st.error(f"运行失败：{exc}")
        return

    st.success(f"任务已创建：{run_result['job_id']}")
    st.write("结果目录：", run_result["job_dir"])

    cols = st.columns(3)
    cols[0].metric("job_id", run_result["job_id"])
    cols[1].metric("上传文件数", str(len(uploaded_files or [])))
    cols[2].metric("状态", "placeholder_completed")

    render_download_panel(run_result)

    if page.key not in {"venn_analysis"}:
        st.info("当前版本完成任务初始化和结果落盘。下一步可将 runner 替换为 R 脚本、Python 脚本或 Docker 调用。")


def render_download_panel(run_result: dict[str, Any] | None) -> None:
    if not run_result:
        return

    artifacts = run_result.get("artifacts", [])
    if not artifacts:
        return

    st.subheader("结果下载")
    for index, artifact in enumerate(artifacts):
        path = Path(artifact["path"])
        if not path.exists():
            st.warning(f"文件不存在：{path}")
            continue
        st.download_button(
            artifact["label"],
            data=path.read_bytes(),
            file_name=path.name,
            mime=artifact.get("mime", "application/octet-stream"),
            key=f"download_{run_result['job_id']}_{index}",
            use_container_width=True,
        )

    with st.expander("任务文件"):
        st.json(run_result)
