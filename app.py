from __future__ import annotations

import streamlit as st

from modules.config import APP_TITLE, PAGE_DEFINITIONS
from modules.pipeline_stubs import run_placeholder_pipeline
from modules.ui_components import (
    render_analysis_page,
    render_home_page,
    render_network_pharmacology_page,
)
from modules.page_venn import render_venn_analysis_page
from app_pages.geo_deg import render_geo_deg_page
from app_pages.md_plot import render_md_plot_page


st.set_page_config(
    page_title=APP_TITLE,
    page_icon="🧬",
    layout="wide",
    initial_sidebar_state="expanded",
)


def main() -> None:
    st.sidebar.title(APP_TITLE)
    if "selected_page" not in st.session_state:
        st.session_state.selected_page = PAGE_DEFINITIONS[0].label

    valid_labels = [page.label for page in PAGE_DEFINITIONS]
    if st.session_state.selected_page not in valid_labels:
        st.session_state.selected_page = PAGE_DEFINITIONS[0].label

    st.sidebar.markdown("### 功能导航")
    for page in PAGE_DEFINITIONS:
        is_active = st.session_state.selected_page == page.label
        button_label = f"● {page.label}" if is_active else f"○ {page.label}"
        if st.sidebar.button(
            button_label,
            key=f"nav_{page.key}",
            use_container_width=True,
            type="primary" if is_active else "secondary",
        ):
            st.session_state.selected_page = page.label
            st.rerun()

    selected_page = st.session_state.selected_page
    page_config = next(page for page in PAGE_DEFINITIONS if page.label == selected_page)

    if page_config.key == "home":
        render_home_page()
        return
    if page_config.key == "network_pharmacology":
        render_network_pharmacology_page(page_config)
        return
    if page_config.key == "geo_deg":
        render_geo_deg_page(page_config)
        return
    if page_config.key == "venn_analysis":
        render_venn_analysis_page(page_config)
        return
    if page_config.key == "md_plotting":
        render_md_plot_page(page_config)
        return

    render_analysis_page(
        page=page_config,
        runner=run_placeholder_pipeline,
    )


if __name__ == "__main__":
    main()
