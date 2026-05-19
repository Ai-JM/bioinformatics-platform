# 自动化生信分析平台

这是一个 Streamlit 生信分析平台，逐步接入网络药理学、GEO 差异分析、核心靶点筛选、GO/KEGG 富集、集合分析 / Venn图和 MD 结果绘图。

## 快速开始

```bash
pip install -r requirements.txt
streamlit run app.py
```

Windows/Codex 环境也可以运行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start_streamlit.ps1 -Port 8502
```

## 结果结构

每次运行都会生成唯一 `job_id`，结果保存到：

```text
results/
  <job_id>/
    inputs/
    outputs/
    logs/
    job_manifest.json
```

集合分析 / Venn图模块会额外写入：

```text
results/<job_id>/venn/
  input_standardized_two_column.tsv
  set_summary.csv
  all_intersections.csv
  specific_elements.csv
  intersection_element_details.csv
  pairwise_similarity.csv
  permutation_test.csv
  Venn_plot.png/pdf/svg
  UpSet_plot.png/pdf
  Jaccard_heatmap.png/pdf
  Flower_summary.png
  Venn_network.html
  report_snippet.md
```

## 集合分析 / Venn图模块

页面入口：左侧导航栏选择 **集合分析 / Venn图**。

该模块用于分析多个基因集、药物靶点集、疾病靶点集、DEGs 或富集通路集之间的关系，包含：

- 统一输入格式：two-column、多列和手动粘贴。
- 集合统计：每个集合元素数、并集、共有元素和特异元素。
- 全部交集表：支持查询任意交集组合对应的元素列表。
- 集合相似性：Jaccard index 和 overlap coefficient。
- 可选置换检验：输出 empirical p value 和 FDR_BH。
- 论文图导出：Venn、UpSet、Jaccard heatmap、Flower summary、HTML 网络图。
- 自动生成 `report_snippet.md`，可作为论文方法和结果描述初稿。

### 推荐输入格式

推荐使用 two-column 格式，第一列为元素，第二列为集合名称：

```text
element    set
TP53       Drug_Targets
AKT1       Drug_Targets
TP53       Disease_Targets
IL6        DEGs
```

同一个元素属于多个集合时，在 two-column 表中出现多行即可。

### 示例数据

项目内置两个示例文件：

- `example_data/venn_gene_sets_two_column.tsv`
- `example_data/venn_gene_sets_wide.xlsx`

在页面中选择“使用示例数据”后可以直接运行分析。

### 图形选择原则

- 2-3 个集合：优先使用 Venn 图，同时输出 UpSet。
- 4-6 个集合：可使用 Flower 或 Venn 概览，推荐以 UpSet 作为主要图。
- 7-10 个集合：传统 Venn 可读性较差，推荐 UpSet、Flower 或网络图。
- 10 个以上集合：不推荐传统 Venn，建议使用 UpSet、Flower、Network 或结果表格。

## 模块结构

- `app.py`：Streamlit 入口和导航。
- `modules/config.py`：页面配置、参数配置和路径配置。
- `modules/job_manager.py`：任务目录、上传文件、manifest 和日志管理。
- `modules/page_venn.py`：集合分析 / Venn图页面逻辑。
- `modules/venn_utils.py`：集合清洗、交并集、相似性和置换检验。
- `modules/venn_plotting.py`：Venn、UpSet、热图、Flower 和网络图绘制。
- `modules/pipeline_stubs.py`：其他模块的占位 runner。
- `app_pages/`：GEO 差异分析和 MD 结果绘图页面。
- `scripts/`：后续可接入 R/Python/Docker CLI 脚本。

## 后续接入建议

1. 将每个分析步骤封装成独立 CLI 脚本，并统一提供 `--outdir`。
2. Streamlit 页面只负责收集参数、保存输入、调度脚本和展示结果。
3. GEO 差异分析可输出 `DEGs.csv`，集合分析模块可将其作为一个集合继续分析。
4. 网络药理学模块可输出 `Drug_Targets`、`Disease_Targets`，集合分析模块可自动生成候选靶点交集。
5. 富集分析模块后续可接收集合分析得到的交集基因列表。
