from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
RESULTS_DIR = BASE_DIR / "results"
EXAMPLE_DATA_DIR = BASE_DIR / "example_data"

APP_TITLE = "自动化生信分析平台"


@dataclass(frozen=True)
class ParameterSpec:
    name: str
    label: str
    default: str
    help: str = ""


@dataclass(frozen=True)
class PageDefinition:
    key: str
    label: str
    description: str
    accepted_types: list[str] | None = None
    parameters: list[ParameterSpec] = field(default_factory=list)


PAGE_DEFINITIONS = [
    PageDefinition(
        key="home",
        label="首页",
        description="项目入口和任务说明。",
    ),
    PageDefinition(
        key="network_pharmacology",
        label="网络药理学分析",
        description="上传多个单成分靶点表和疾病靶点表，生成 Venn 图与标准化靶点 Excel。",
        accepted_types=["csv", "tsv", "txt", "xlsx"],
        parameters=[
            ParameterSpec("species", "物种", "Homo sapiens", "用于靶点标准化和后续富集分析。"),
            ParameterSpec("component_target_column", "单成分靶点列名", "auto", "填写 auto 时自动识别 Gene、Target、Symbol 等列。"),
            ParameterSpec("disease_target_column", "疾病靶点列名", "auto", "填写 auto 时自动识别 Gene、Target、Symbol 等列。"),
            ParameterSpec("normalize_case", "基因名大小写", "upper", "可选 upper、keep。"),
        ],
    ),
    PageDefinition(
        key="geo_deg",
        label="GEO 差异分析",
        description="上传表达矩阵、分组表或 GEO 相关文件，后续接入 limma/DESeq2 工作流。",
        accepted_types=["csv", "tsv", "txt", "xlsx", "soft", "gz"],
        parameters=[
            ParameterSpec("geo_accession", "GEO 编号", "GSEXXXXX", "例如 GSE55235。"),
            ParameterSpec("case_group", "病例组名称", "case", "需与分组表一致。"),
            ParameterSpec("control_group", "对照组名称", "control", "需与分组表一致。"),
            ParameterSpec("logfc_cutoff", "logFC 阈值", "0.585", "默认约等于 1.5 倍变化。"),
            ParameterSpec("adj_p_cutoff", "校正 P 值阈值", "0.05", "默认使用 adj.P.Val 或等价字段。"),
        ],
    ),
    PageDefinition(
        key="core_targets",
        label="核心靶点筛选",
        description="上传药物靶点、疾病靶点和 DEGs，计算交集并保留来源映射。",
        accepted_types=["csv", "tsv", "txt", "xlsx"],
        parameters=[
            ParameterSpec("gene_id_type", "基因 ID 类型", "Symbol", "建议统一为官方 Gene Symbol。"),
            ParameterSpec("min_sources", "最少来源数", "2", "用于筛选多来源支持的候选靶点。"),
        ],
    ),
    PageDefinition(
        key="enrichment",
        label="富集分析",
        description="上传核心基因列表，后续接入 clusterProfiler 或 g:Profiler。",
        accepted_types=["csv", "tsv", "txt", "xlsx"],
        parameters=[
            ParameterSpec("organism", "物种代码", "hsa", "KEGG 物种代码，例如 hsa/mmu/rno。"),
            ParameterSpec("ontology", "GO 类型", "BP, CC, MF", "可填写 BP、CC、MF 或组合。"),
            ParameterSpec("pvalue_cutoff", "P 值阈值", "0.05", "富集显著性阈值。"),
        ],
    ),
    PageDefinition(
        key="venn_analysis",
        label="Venn 图分析",
        description="上传多个基因或靶点列表，生成 Venn 图和交并集 Excel。",
        accepted_types=["csv", "tsv", "txt", "xlsx"],
        parameters=[
            ParameterSpec("target_column", "靶点列名", "auto", "填写 auto 时自动识别 Gene、Target、Symbol 等列。"),
            ParameterSpec("plot_title", "图标题", "Venn targets", "用于 PNG/PDF/SVG 图标题。"),
            ParameterSpec("normalize_case", "基因名大小写", "upper", "可选 upper、keep。"),
        ],
    ),
    PageDefinition(
        key="md_plotting",
        label="MD 结果绘图",
        description="上传分子动力学结果文件，生成 RMSD/RMSF/Rg 等图形。",
        accepted_types=["csv", "tsv", "txt", "xvg", "dat", "xlsx", "zip"],
        parameters=[
            ParameterSpec("plot_type", "图形类型", "RMSD", "例如 RMSD、RMSF、Rg、H-bonds。"),
            ParameterSpec("time_unit", "时间单位", "ns", "用于坐标轴标注。"),
            ParameterSpec("smooth_window", "平滑窗口", "1", "1 表示不平滑。"),
        ],
    ),
]
