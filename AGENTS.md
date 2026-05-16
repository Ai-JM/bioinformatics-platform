# AGENTS.md

## 项目目标

构建一个 Streamlit 自动化生信分析平台，逐步接入网络药理学、GEO 差异分析、核心靶点筛选、GO/KEGG 富集、Venn 图分析和 MD 结果绘图。

## 开发约定

- 保持 `app.py` 轻量，只负责应用入口和导航。
- 页面配置、参数配置集中放在 `modules/config.py`。
- 任务创建、文件保存、manifest 和日志写入放在 `modules/job_manager.py`。
- 真实分析逻辑通过 `modules/pipeline_stubs.py` 中的 runner 接入或替换。
- R/Python 分析脚本放在 `scripts/`，应提供清晰 CLI 参数。
- 所有运行结果必须写入 `results/<job_id>/`，不要写入全局临时目录。
- 上传文件保存到 `results/<job_id>/inputs/`。
- 表格、图形、报告保存到 `results/<job_id>/outputs/`。
- 运行日志保存到 `results/<job_id>/logs/`。

## 后续集成 R 脚本

推荐脚本接口：

```bash
Rscript scripts/run_geo_deg.R \
  --expression results/<job_id>/inputs/expression.csv \
  --metadata results/<job_id>/inputs/metadata.csv \
  --case_group case \
  --control_group control \
  --outdir results/<job_id>/outputs
```

## Docker 约定

- 容器内工作目录建议为 `/workspace`。
- 将项目目录挂载到 `/workspace`。
- 容器内脚本只写入调用方传入的 `--outdir`。
- 不在脚本中硬编码 Windows 或本机绝对路径。
