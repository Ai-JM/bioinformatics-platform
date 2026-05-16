# 自动化生信分析平台

Streamlit 第一版框架，用于封装网络药理学、GEO 差异分析、药物-疾病-DEGs 交集、GO/KEGG 富集、Venn 图分析和 MD 结果绘图。

## 快速开始

```bash
pip install -r requirements.txt
streamlit run app.py
```

Windows/Codex 环境也可直接运行：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/start_streamlit.ps1
```

## 已完成

- `app.py` Streamlit 入口。
- `scripts/`、`modules/`、`results/`、`example_data/` 项目目录。
- 左侧导航栏包含：首页、网络药理学分析、GEO 差异分析、核心靶点筛选、富集分析、Venn 图分析、MD 结果绘图。
- 每个分析页面包含文件上传、参数输入和运行按钮。
- 每次运行生成唯一 `job_id`。
- 所有结果保存到 `results/<job_id>/`。
- 网络药理学分析支持单成分靶点和疾病靶点多文件输入，导出 PNG/PDF/SVG Venn 图和 Excel 靶点表。
- Venn 图分析支持 2-6 组集合，提供手动粘贴、文件上传、集合命名、交并集 Excel 和 Nature 风格 PNG/PDF/SVG 输出。
- 模块化代码结构，便于后续接入 R 脚本、Python 脚本和 Docker。

## 结果结构

```text
results/
  <job_id>/
    inputs/
    outputs/
    logs/
    job_manifest.json
```

## 模块说明

- `modules/config.py`：页面定义、参数定义、路径配置。
- `modules/job_manager.py`：`job_id` 生成、结果目录创建、上传文件保存、manifest 写入。
- `modules/pipeline_stubs.py`：占位 pipeline runner，后续替换为真实分析流程。
- `modules/ui_components.py`：Streamlit 页面组件。
- `scripts/`：预留 R/Python/Docker 可执行脚本。

## 后续接入建议

1. 将每个分析步骤写成独立 CLI 脚本，例如 `scripts/run_geo_deg.R`。
2. CLI 参数统一包含 `--outdir`，所有输出写入当前 job 的 `outputs/`。
3. Streamlit 只负责收集参数、保存输入、调度脚本和展示结果。
4. Docker 镜像内保持相同目录约定，减少本地和服务器部署差异。
