"""
Core metrics and data-grouping module for 2025 MEF budget analysis.
Reads only pre-processed files from data/processed/ — never raw CSVs.
"""
from pathlib import Path
import pandas as pd

PROCESSED = Path(__file__).parent.parent / "data" / "processed"
MIN_PIM = 10_000_000  # 10 million PEN


def load_processed_data(filename: str = "budget_2025.parquet") -> pd.DataFrame | None:
    path = PROCESSED / filename
    if not path.exists():
        csv_path = path.with_suffix(".csv")
        if csv_path.exists():
            return pd.read_csv(csv_path)
        return None
    return pd.read_parquet(path)


def calc_execution_rate(df: pd.DataFrame) -> pd.DataFrame:
    """Avance % = (Devengado / PIM) * 100, safe against zero PIM."""
    df = df.copy()
    df["avance_pct"] = (df["devengado"] / df["pim"].replace(0, pd.NA)) * 100
    return df


def calc_frozen_capital(df: pd.DataFrame) -> pd.DataFrame:
    """Saldo No Devengado = PIM - Devengado."""
    df = df.copy()
    df["saldo_no_devengado"] = df["pim"] - df["devengado"]
    return df


def enrich(df: pd.DataFrame) -> pd.DataFrame:
    df = calc_execution_rate(df)
    df = calc_frozen_capital(df)
    return df


def get_national_kpis(df: pd.DataFrame) -> dict:
    total_pim = df["pim"].sum()
    total_dev = df["devengado"].sum()
    return {
        "total_pim": round(total_pim, 2),
        "total_devengado": round(total_dev, 2),
        "national_execution_rate": round((total_dev / total_pim * 100) if total_pim else 0, 2),
        "frozen_capital": round(total_pim - total_dev, 2),
        "num_entities": len(df),
    }


def get_worst_performers(df: pd.DataFrame, n: int = 20) -> pd.DataFrame:
    """Entities with PIM > 10M PEN sorted by lowest execution rate."""
    df = enrich(df)
    mask = df["pim"] > MIN_PIM
    return (
        df[mask]
        .sort_values("avance_pct", ascending=True)
        .head(n)[["entidad", "departamento", "pim", "devengado", "avance_pct", "saldo_no_devengado"]]
        .reset_index(drop=True)
    )


def get_department_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregated execution metrics grouped by department."""
    df = enrich(df)
    grp = (
        df.groupby("departamento", as_index=False)
        .agg(
            pim=("pim", "sum"),
            devengado=("devengado", "sum"),
            num_entities=("entidad", "count"),
        )
    )
    grp["avance_pct"] = (grp["devengado"] / grp["pim"].replace(0, pd.NA) * 100).round(2)
    grp["saldo_no_devengado"] = (grp["pim"] - grp["devengado"]).round(2)
    return grp.sort_values("avance_pct", ascending=True).reset_index(drop=True)


def get_category_breakdown(df: pd.DataFrame) -> pd.DataFrame:
    """Spending breakdown by category/function where available."""
    col = next((c for c in df.columns if "categoria" in c.lower() or "funcion" in c.lower()), None)
    if col is None:
        return pd.DataFrame()
    df = enrich(df)
    return (
        df.groupby(col, as_index=False)
        .agg(pim=("pim", "sum"), devengado=("devengado", "sum"))
        .assign(avance_pct=lambda x: (x["devengado"] / x["pim"].replace(0, pd.NA) * 100).round(2))
        .sort_values("saldo_no_devengado" if "saldo_no_devengado" in df.columns else "pim", ascending=False)
        .reset_index(drop=True)
    )


def load_ocr_historical() -> dict:
    """Load the 1964 OCR results from processed files."""
    path = PROCESSED / "ocr_1964_results.json"
    if not path.exists():
        return {}
    import json
    with open(path, encoding="utf-8") as f:
        return json.load(f)
