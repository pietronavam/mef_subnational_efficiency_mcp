"""
Anti-context-flooding data pipeline.
Downloads, filters, and aggregates MEF budget data locally.
Saves microscopic Parquet footprints to data/processed/.

Usage (standalone — called by MCP tool descargar_y_analizar_estadisticas):
    python src/data_pipeline.py <resource_url> <group_by> <metric_col> <period>
"""
import io
import json
import sys
from pathlib import Path

import duckdb
import pandas as pd
import requests

ROOT = Path(__file__).parent.parent
PROCESSED = ROOT / "data" / "processed"
SNAPSHOTS = ROOT / "data" / "snapshots"
MIN_PIM_SOLES = 10_000_000


# ── Schema snapshot (safe — only first N rows) ───────────────────────────────

def snapshot_schema(url: str, n: int = 10) -> pd.DataFrame:
    r = requests.get(url, stream=True, timeout=60)
    r.raise_for_status()
    lines: list[bytes] = []
    for i, line in enumerate(r.iter_lines()):
        lines.append(line)
        if i >= n + 2:
            break
    raw = b"\n".join(lines)
    try:
        df = pd.read_csv(io.BytesIO(raw), nrows=n, encoding="latin1", on_bad_lines="skip")
    except Exception:
        df = pd.read_csv(io.BytesIO(raw), nrows=n, on_bad_lines="skip")
    return df


# ── Column normalisation ─────────────────────────────────────────────────────

_COL_MAP = {
    "año": "anio", "año_eje": "anio",
    "sec_func": "categoria",
    "pliego": "entidad", "nombre_pliego": "entidad",
    "departamento": "departamento", "nom_departamento": "departamento",
    "pia": "pia", "pim": "pim",
    "devengado": "devengado", "monto_devengado": "devengado",
    "girado": "girado",
}

def normalise_columns(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = [c.lower().strip() for c in df.columns]
    return df.rename(columns={k: v for k, v in _COL_MAP.items() if k in df.columns})


# ── Full download + filter pipeline ─────────────────────────────────────────

def download_and_process(
    resource_url: str,
    period: str = "2025",
    output_filename: str = "budget_2025.parquet",
) -> dict:
    PROCESSED.mkdir(parents=True, exist_ok=True)
    out_path = PROCESSED / output_filename

    r = requests.get(resource_url, stream=True, timeout=300)
    r.raise_for_status()

    raw_bytes = r.content
    try:
        df = pd.read_csv(io.BytesIO(raw_bytes), encoding="latin1", low_memory=False, on_bad_lines="skip")
    except Exception:
        df = pd.read_csv(io.BytesIO(raw_bytes), low_memory=False, on_bad_lines="skip")

    df = normalise_columns(df)

    if "anio" in df.columns:
        df = df[df["anio"].astype(str).str.startswith(period[:4])]

    for col in ["pim", "devengado", "pia"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col].astype(str).str.replace(",", ""), errors="coerce").fillna(0.0)

    df = df[df.get("pim", pd.Series([0] * len(df))) > 0] if "pim" in df.columns else df

    if "entidad" not in df.columns:
        df["entidad"] = "Sin nombre"
    if "departamento" not in df.columns:
        df["departamento"] = "Sin departamento"

    required = [c for c in ["entidad", "departamento", "pim", "devengado"] if c in df.columns]
    df_save = df[required].copy()
    df_save.to_parquet(out_path, index=False)

    return {
        "rows_saved": len(df_save),
        "columns": list(df_save.columns),
        "output_file": str(out_path),
        "period": period,
    }


# ── DuckDB aggregation ────────────────────────────────────────────────────────

def aggregate_with_duckdb(
    parquet_path: str,
    group_by: str = "departamento",
    metric_col: str = "devengado",
) -> dict:
    con = duckdb.connect()
    q = f"""
        SELECT
            {group_by},
            COUNT(*) AS num_entities,
            SUM(pim) AS total_pim,
            SUM({metric_col}) AS total_devengado,
            ROUND(SUM({metric_col}) / NULLIF(SUM(pim), 0) * 100, 2) AS avance_pct,
            SUM(pim - {metric_col}) AS saldo_no_devengado
        FROM read_parquet('{parquet_path}')
        GROUP BY {group_by}
        ORDER BY avance_pct ASC
    """
    result = con.execute(q).fetchdf()
    return {
        "group_by": group_by,
        "rows": len(result),
        "summary": result.to_dict(orient="records"),
    }


# ── Standalone entry point (called by MCP tool) ──────────────────────────────

def run(resource_url: str, group_by: str, metric_col: str, period: str) -> dict:
    dl = download_and_process(resource_url, period)
    if "error" in dl:
        return dl
    agg = aggregate_with_duckdb(dl["output_file"], group_by, metric_col)
    return {**dl, "aggregation": agg}


if __name__ == "__main__":
    if len(sys.argv) < 5:
        print(json.dumps({"error": "Usage: data_pipeline.py <url> <group_by> <metric_col> <period>"}))
        sys.exit(1)
    url, group_by, metric_col, period = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
    result = run(url, group_by, metric_col, period)
    print(json.dumps(result, default=str))
