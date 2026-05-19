from __future__ import annotations

import base64
from pathlib import Path
from typing import Any, Callable

import streamlit as st

from modules.config import BASE_DIR, MODULE_ILLUSTRATIONS, PAGE_DEFINITIONS, PageDefinition
from modules.pipeline_stubs import run_network_pharmacology_pipeline, run_venn_builder_pipeline


Runner = Callable[..., dict[str, str]]

VENN_STYLE_OPTIONS = {
    "auto": "自动选择：按集合数量选择最合适的图型",
    "classic": "标准圆形文氏图：适合 2-3 组集合",
    "overlap": "多圆重叠文氏图：适合 4-7 组集合的重叠展示",
    "flower": "花瓣圆形文氏图：适合 4-7 组集合，突出共同交集",
    "proportional": "成比例面积文氏图：用圆面积体现集合大小",
    "network": "网络 Venn 图：用节点和连线展示集合关系",
    "bar": "文氏图 + 条形图：适合 2 组集合并展示占比",
    "vertical": "垂直圆形文氏图：多组集合纵向叠放展示",
}


def illustration_path(page_key: str) -> Path | None:
    relative_path = MODULE_ILLUSTRATIONS.get(page_key)
    if not relative_path:
        return None
    path = BASE_DIR / relative_path
    return path if path.exists() else None


def render_page_header(page: PageDefinition, subtitle: str | None = None) -> None:
    left, right = st.columns([1.25, 1])
    with left:
        st.title(page.label)
        st.caption(subtitle or page.description)
    with right:
        image_path = illustration_path(page.key)
        if image_path:
            render_svg_image(image_path)


def render_svg_image(path: Path, *, max_width: str = "100%") -> None:
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    st.markdown(
        f'<img src="data:image/svg+xml;base64,{encoded}" style="width:{max_width}; height:auto;" />',
        unsafe_allow_html=True,
    )


def render_home_page() -> None:
    st.title("自动化生信分析平台")
    st.caption("面向网络药理学、GEO 差异分析、靶点筛选、富集分析、Venn 图和 MD 结果绘图的一体化平台。")
    st.markdown(
        "本平台按照任务自动创建独立结果目录，统一保存上传文件、运行参数、日志、表格、图形和报告。"
        "第一版重点完成常用生信流程的网页化入口、文件管理和可视化输出。"
    )

    st.subheader("功能模块")
    module_pages = [page for page in PAGE_DEFINITIONS if page.key != "home"]
    for row_start in range(0, len(module_pages), 3):
        columns = st.columns(3)
        for column, page in zip(columns, module_pages[row_start : row_start + 3]):
            with column:
                image_path = illustration_path(page.key)
                if image_path:
                    render_svg_image(image_path)
                st.markdown(f"#### {page.label}")
                st.write(page.description)
                if st.button("进入模块", key=f"home_open_{page.key}", use_container_width=True):
                    st.session_state.selected_page = page.label
                    st.rerun()


def render_network_pharmacology_page(page: PageDefinition) -> None:
    render_page_header(page, "上传多来源靶点文件，生成标准化靶点表、Venn 图和 Excel 结果。")

    with st.form(key=f"{page.key}_form", clear_on_submit=False):
        st.subheader("输入数据")
        left, right = st.columns(2)
        with left:
            st.markdown("**单成分靶点数据**")
            component_files = st.file_uploader(
                "上传单成分靶点表",
                type=page.accepted_types,
                accept_multiple_files=True,
                help="每个文件代表一个成分或一个靶点来源，支持 CSV、TSV、TXT、XLSX。",
                key="component_target_files",
            )
        with right:
            st.markdown("**疾病靶点数据**")
            disease_files = st.file_uploader(
                "上传疾病靶点表",
                type=page.accepted_types,
                accept_multiple_files=True,
                help="每个文件代表一个疾病数据库或一个疾病靶点来源，支持 CSV、TSV、TXT、XLSX。",
                key="disease_target_files",
            )

        st.subheader("分析参数")
        parameter_cols = st.columns(3)
        parameters: dict[str, str] = {}
        for index, parameter in enumerate(page.parameters):
            with parameter_cols[index % 3]:
                parameters[parameter.name] = st.text_input(
                    parameter.label,
                    value=parameter.default,
                    help=parameter.help or None,
                )

        submitted = st.form_submit_button("运行网络药理学分析", type="primary")

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


def render_venn_style_selector() -> str:
    st.subheader("Venn 图类型")
    gallery_path = BASE_DIR / "assets" / "illustrations" / "venn_style_gallery.svg"
    if gallery_path.exists():
        render_svg_image(gallery_path)
    selected_label = st.selectbox(
        "选择 Venn 图类型",
        options=list(VENN_STYLE_OPTIONS.keys()),
        format_func=lambda key: VENN_STYLE_OPTIONS[key],
        index=0,
        help="不同图型适合不同集合数量。自动选择会按集合数量使用标准文氏图或花瓣文氏图。",
    )
    st.caption(VENN_STYLE_OPTIONS[selected_label])
    return selected_label


def render_venn_builder_page(page: PageDefinition) -> None:
    render_page_header(page, "支持 2-7 组集合，可手动粘贴或上传文件，输出 Venn 图和交并集 Excel。")

    if "venn_set_count" not in st.session_state:
        st.session_state.venn_set_count = 3

    st.session_state.venn_set_count = st.number_input(
        "手动输入集合数量",
        min_value=2,
        max_value=7,
        value=int(st.session_state.venn_set_count),
        step=1,
        help="可手动输入 2-7 个集合，也可以继续上传更多文件补充。",
    )

    with st.form(key=f"{page.key}_form", clear_on_submit=False):
        st.subheader("手动输入集合")
        text_sets: list[dict[str, str]] = []
        for index in range(st.session_state.venn_set_count):
            left, right = st.columns([1, 2])
            default_name = f"集合 {index + 1}"
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
                    placeholder="每行一个基因或靶点，也支持逗号、分号、竖线分隔。",
                )
            text_sets.append({"name": name, "text": text})

        st.subheader("上传文件补充")
        uploaded_files = st.file_uploader(
            "上传集合文件",
            type=page.accepted_types,
            accept_multiple_files=True,
            help="每个文件会作为一个独立集合，文件名会作为集合名。",
        )

        venn_style = render_venn_style_selector()

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
            "venn_style": venn_style,
            "style": VENN_STYLE_OPTIONS.get(venn_style, "Venn diagram"),
        }
        try:
            with st.spinner("正在计算交并集并绘制 Venn 图..."):
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
    render_page_header(page)

    with st.form(key=f"{page.key}_form", clear_on_submit=False):
        uploaded_files = st.file_uploader(
            "上传文件",
            type=page.accepted_types,
            accept_multiple_files=True,
            help="可上传一个或多个输入文件。运行后文件会保存到当前任务的 inputs/ 目录。",
        )

        st.subheader("分析参数")
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
        with st.spinner("正在创建任务并保存输入文件..."):
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
    cols[0].metric("任务编号", run_result["job_id"])
    cols[1].metric("上传文件数", str(len(uploaded_files or [])))
    cols[2].metric("状态", "已完成")

    render_download_panel(run_result)
    st.info("当前模块已完成任务初始化和结果落盘，后续可接入 Python/R 脚本或 Docker 工作流。")


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

    with st.expander("任务文件详情"):
        st.json(run_result)
