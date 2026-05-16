from __future__ import annotations

import re
from pathlib import Path

import pandas as pd


MD_FILE_TYPES = {
    "rmsd": ["rmsd"],
    "rmsf": ["rmsf"],
    "gyrate": ["gyrate", "rg", "radius_gyration"],
    "sasa": ["sasa", "solvent_accessible"],
    "hbond": ["hbond", "hbnum", "hbonds", "hydrogen_bond"],
    "mindist": ["mindist", "minimum_distance"],
    "contacts": ["contact", "contacts"],
    "mmpbsa": ["final_results_mmpbsa", "mmpbsa"],
    "mmpbsa_decomp": ["final_decomp_mmpbsa", "decomp"],
}


def parse_xvg(file_path: str | Path) -> pd.DataFrame:
    """Parse a GROMACS XVG file, skipping comment/metadata rows."""
    path = Path(file_path)
    rows: list[list[float]] = []

    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith(("#", "@")):
                continue
            parts = re.split(r"\s+", line)
            try:
                rows.append([float(item) for item in parts])
            except ValueError:
                continue

    if not rows:
        return pd.DataFrame(columns=["x", "y"])

    max_width = max(len(row) for row in rows)
    padded_rows = [row + [float("nan")] * (max_width - len(row)) for row in rows]
    columns = ["x", "y"] + [f"col_{index}" for index in range(3, max_width + 1)]
    return pd.DataFrame(padded_rows, columns=columns)


def detect_md_file_type(filename: str) -> str:
    """Detect MD result type from the filename."""
    normalized = Path(filename).name.lower()
    for file_type, keywords in MD_FILE_TYPES.items():
        if any(keyword in normalized for keyword in keywords):
            return file_type
    if normalized.endswith(".xvg"):
        return "xvg"
    if normalized.endswith((".csv", ".dat")) and "mmpbsa" in normalized:
        return "mmpbsa"
    return "unknown"


def parse_mmpbsa_csv(file_path: str | Path) -> pd.DataFrame:
    """Parse MMPBSA CSV output into a flat energy table."""
    path = Path(file_path)
    dataframe = pd.read_csv(path, sep=None, engine="python")
    dataframe.columns = [str(column).strip() for column in dataframe.columns]
    return dataframe.dropna(how="all")


def parse_mmpbsa_dat(file_path: str | Path) -> pd.DataFrame:
    """Parse common gmx_MMPBSA FINAL_RESULTS_MMPBSA.dat energy sections."""
    path = Path(file_path)
    records: list[dict[str, object]] = []
    numeric_pattern = re.compile(r"^-?\d+(?:\.\d+)?(?:[Ee][+-]?\d+)?$")

    with path.open("r", encoding="utf-8", errors="ignore") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith(("#", "|", "-")):
                continue
            parts = re.split(r"\s+", line)
            numeric_values: list[float] = []
            while parts and numeric_pattern.match(parts[-1]):
                numeric_values.insert(0, float(parts.pop()))
            if not parts or not numeric_values:
                continue
            record: dict[str, object] = {"term": " ".join(parts), "average": numeric_values[0]}
            for index, value in enumerate(numeric_values[1:], start=2):
                record[f"value_{index}"] = value
            records.append(record)

    return pd.DataFrame(records)


def parse_decomp_dat(file_path: str | Path) -> pd.DataFrame:
    """TODO: Add residue-level decomposition parsing in a later version."""
    return pd.DataFrame(
        {
            "source_file": [Path(file_path).name],
            "status": ["TODO: residue decomposition parser is reserved for v2"],
        }
    )
