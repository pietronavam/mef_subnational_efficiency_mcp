"""
Local MCP Server — exposes 10 tools for querying datosabiertos.gob.pe
and triggering local OCR/analytics tasks.
Run with: python src/mcp_server.py
"""
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import urllib3
import requests

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
_GET = lambda url, **kw: requests.get(url, verify=False, **kw)

from mcp.server.fastmcp import FastMCP

ROOT = Path(__file__).parent.parent
PORTAL = "https://www.datosabiertos.gob.pe"
RAW_PDFS = ROOT / "data" / "raw_pdfs"
SNAPSHOTS = ROOT / "data" / "snapshots"
PROCESSED = ROOT / "data" / "processed"

mcp = FastMCP("MEF Subnational Efficiency")


# ── 1. buscar_datasets ──────────────────────────────────────────────────────

@mcp.tool()
def buscar_datasets(query: str, rows: int = 10) -> dict:
    """Search datasets on the portal using a keyword string via CKAN API.
    Falls back to package_list keyword filter when package_search is unavailable."""
    # Primary: package_search (requires Solr backend)
    url = f"{PORTAL}/api/3/action/package_search"
    try:
        r = _GET(url, params={"q": query, "rows": rows}, timeout=30)
        if r.status_code == 200:
            data = r.json()
            if data.get("success"):
                results = data["result"]["results"]
                return {
                    "total": data["result"]["count"],
                    "datasets": [
                        {
                            "id": d["id"],
                            "name": d["name"],
                            "title": d.get("title", ""),
                            "organization": (d.get("organization") or {}).get("title", ""),
                            "resources": [
                                {
                                    "id": res["id"],
                                    "name": res.get("name", ""),
                                    "format": res.get("format", ""),
                                    "url": res.get("url", ""),
                                }
                                for res in d.get("resources", [])[:5]
                            ],
                        }
                        for d in results
                    ],
                }
    except Exception:
        pass

    # Fallback: package_list + keyword filter (works even without Solr)
    list_url = f"{PORTAL}/api/3/action/package_list"
    r2 = _GET(list_url, params={"limit": 1000}, timeout=30)
    r2.raise_for_status()
    data2 = r2.json()
    if not data2.get("success"):
        return {"error": "Both package_search and package_list failed"}
    keywords = [k.lower() for k in query.split()]
    matches = [
        name for name in data2["result"]
        if any(kw in name.lower() for kw in keywords)
    ][:rows]
    return {
        "total": len(matches),
        "note": "package_search unavailable (Solr offline); results from package_list keyword filter",
        "datasets": [{"id": name, "name": name, "title": name.replace("-", " ").title(), "organization": "", "resources": []} for name in matches],
    }


# ── 2. obtener_detalle_dataset ───────────────────────────────────────────────

@mcp.tool()
def obtener_detalle_dataset(dataset_id: str) -> dict:
    """Extract direct download URLs for all resources of a dataset by ID.
    Falls back to current_package_list_with_resources scan when package_show is unavailable."""
    url = f"{PORTAL}/api/3/action/package_show"
    try:
        r = _GET(url, params={"id": dataset_id}, timeout=30)
        if r.status_code == 200:
            data = r.json()
            if data.get("success"):
                pkg = data["result"]
                return {
                    "id": pkg["id"],
                    "title": pkg.get("title", ""),
                    "notes": pkg.get("notes", "")[:500],
                    "resources": [
                        {
                            "id": res["id"],
                            "name": res.get("name", ""),
                            "format": res.get("format", ""),
                            "url": res.get("url", ""),
                            "size": res.get("size"),
                            "last_modified": res.get("last_modified", ""),
                        }
                        for res in pkg.get("resources", [])
                    ],
                }
    except Exception:
        pass

    # Fallback: scan current_package_list_with_resources for a name match
    list_url = f"{PORTAL}/api/3/action/current_package_list_with_resources"
    r2 = _GET(list_url, params={"limit": 200}, timeout=60)
    r2.raise_for_status()
    data2 = r2.json()
    for pkg in data2.get("result", []):
        if pkg.get("id") == dataset_id or pkg.get("name") == dataset_id:
            return {
                "id": pkg.get("id", dataset_id),
                "title": pkg.get("title", ""),
                "notes": pkg.get("notes", "")[:500],
                "resources": [
                    {
                        "id": res.get("id", ""),
                        "name": res.get("name", ""),
                        "format": res.get("format", ""),
                        "url": res.get("url", ""),
                        "size": res.get("size"),
                        "last_modified": res.get("last_modified", ""),
                    }
                    for res in pkg.get("resources", [])
                ],
            }
    return {"error": f"Dataset '{dataset_id}' not found via package_show or package_list scan"}


# ── 3. descargar_documento_1964 ──────────────────────────────────────────────

@mcp.tool()
def descargar_documento_1964(pdf_url: str, filename: str = "hacienda_1964.pdf") -> dict:
    """
    Download the 1964 Ministerio de Hacienda PDF into data/raw_pdfs/.
    Pass the direct PDF URL (obtained from the historical archive portal).
    """
    RAW_PDFS.mkdir(parents=True, exist_ok=True)
    dest = RAW_PDFS / filename
    if dest.exists():
        return {"status": "already_exists", "path": str(dest), "size_mb": round(dest.stat().st_size / 1e6, 2)}
    r = _GET(pdf_url, stream=True, timeout=120)
    r.raise_for_status()
    with open(dest, "wb") as f:
        for chunk in r.iter_content(chunk_size=8192):
            f.write(chunk)
    return {"status": "downloaded", "path": str(dest), "size_mb": round(dest.stat().st_size / 1e6, 2)}


# ── 4. listar_entidades_publicas ─────────────────────────────────────────────

@mcp.tool()
def listar_entidades_publicas(limit: int = 30) -> dict:
    """Fetch a list of active public organizations registered on the portal."""
    url = f"{PORTAL}/api/3/action/organization_list"
    r = _GET(url, params={"all_fields": True, "limit": limit}, timeout=30)
    r.raise_for_status()
    data = r.json()
    if not data.get("success"):
        return {"error": "Failed to list organizations"}
    orgs = data["result"]
    return {
        "count": len(orgs),
        "organizations": [
            {"id": o.get("id"), "name": o.get("name"), "title": o.get("title"), "package_count": o.get("package_count", 0)}
            for o in orgs[:limit]
        ],
    }


# ── 5. listar_categorias_tematicas ───────────────────────────────────────────

@mcp.tool()
def listar_categorias_tematicas() -> dict:
    """Map high-level data groups (topic categories) available on the portal."""
    url = f"{PORTAL}/api/3/action/group_list"
    r = _GET(url, params={"all_fields": True}, timeout=30)
    r.raise_for_status()
    data = r.json()
    if not data.get("success"):
        return {"error": "Failed to list groups"}
    groups = data["result"]
    return {
        "count": len(groups),
        "categories": [
            {"id": g.get("id"), "name": g.get("name"), "title": g.get("title"), "package_count": g.get("package_count", 0)}
            for g in groups
        ],
    }


# ── 6. obtener_ultimas_actualizaciones ───────────────────────────────────────

@mcp.tool()
def obtener_ultimas_actualizaciones(limit: int = 10) -> dict:
    """Return the most recently updated datasets on the portal."""
    url = f"{PORTAL}/api/3/action/package_search"
    r = _GET(url, params={"sort": "metadata_modified desc", "rows": limit}, timeout=30)
    r.raise_for_status()
    data = r.json()
    if not data.get("success"):
        return {"error": "Failed to fetch updates"}
    results = data["result"]["results"]
    return {
        "updates": [
            {
                "name": d.get("name"),
                "title": d.get("title"),
                "modified": d.get("metadata_modified"),
                "organization": (d.get("organization") or {}).get("title", ""),
            }
            for d in results
        ]
    }


# ── 7. inspeccionar_esquema_csv ──────────────────────────────────────────────

@mcp.tool()
def inspeccionar_esquema_csv(resource_url: str, sample_rows: int = 10) -> dict:
    """
    Stream the first N rows of a CSV resource to capture headers and types
    without downloading the full file. Saves snapshot to data/snapshots/.
    """
    import io
    import pandas as pd

    SNAPSHOTS.mkdir(parents=True, exist_ok=True)
    r = _GET(resource_url, stream=True, timeout=60)
    r.raise_for_status()

    lines: list[bytes] = []
    for i, line in enumerate(r.iter_lines()):
        lines.append(line)
        if i >= sample_rows + 1:
            break

    raw = b"\n".join(lines)
    try:
        df = pd.read_csv(io.BytesIO(raw), nrows=sample_rows, encoding="latin1", on_bad_lines="skip")
    except Exception:
        df = pd.read_csv(io.BytesIO(raw), nrows=sample_rows, on_bad_lines="skip")

    snap_name = "snapshot_" + resource_url.split("/")[-1][:40] + ".csv"
    snap_path = SNAPSHOTS / snap_name
    df.to_csv(snap_path, index=False)

    return {
        "columns": list(df.columns),
        "dtypes": {col: str(dt) for col, dt in df.dtypes.items()},
        "sample_rows": df.head(5).to_dict(orient="records"),
        "snapshot_saved": str(snap_path),
    }


# ── 8. consultar_datastore_filtrado ─────────────────────────────────────────

@mcp.tool()
def consultar_datastore_filtrado(
    resource_id: str,
    filters: dict[str, Any] | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict:
    """
    Perform a filtered query on the CKAN Datastore API.
    filters example: {"anio": "2025", "nivel_gobierno": "GR"}
    """
    url = f"{PORTAL}/api/3/action/datastore_search"
    params: dict[str, Any] = {"resource_id": resource_id, "limit": limit, "offset": offset}
    if filters:
        params["filters"] = json.dumps(filters)
    r = _GET(url, params=params, timeout=60)
    r.raise_for_status()
    data = r.json()
    if not data.get("success"):
        return {"error": "Datastore query failed", "raw": data}
    result = data["result"]
    return {
        "total": result.get("total"),
        "fields": result.get("fields", []),
        "records": result.get("records", []),
    }


# ── 9. procesar_ocr_paginas_1964 ─────────────────────────────────────────────

@mcp.tool()
def procesar_ocr_paginas_1964(
    pdf_path: str = "",
    page_numbers: list[int] | None = None,
) -> dict:
    """
    Trigger local PaddleOCR routines over selected pages of the 1964 PDF.
    Defaults to the file in data/raw_pdfs/hacienda_1964.pdf and pages 1-15.
    """
    if not pdf_path:
        pdf_path = str(RAW_PDFS / "hacienda_1964.pdf")
    if page_numbers is None:
        page_numbers = list(range(1, 16))

    result = subprocess.run(
        [sys.executable, str(ROOT / "src" / "ocr_engine.py"), pdf_path, json.dumps(page_numbers)],
        capture_output=True,
        text=True,
        timeout=600,
    )
    if result.returncode != 0:
        return {"error": result.stderr[:2000]}
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"raw_output": result.stdout[:3000]}


# ── 10. descargar_y_analizar_estadisticas ────────────────────────────────────

@mcp.tool()
def descargar_y_analizar_estadisticas(
    resource_url: str,
    group_by: str = "departamento",
    metric_col: str = "monto_devengado",
    period: str = "2025",
) -> dict:
    """
    Download a resource, run light local aggregations via DuckDB,
    and return descriptive summaries without flooding the context window.
    """
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "src" / "data_pipeline.py"),
            resource_url,
            group_by,
            metric_col,
            period,
        ],
        capture_output=True,
        text=True,
        timeout=600,
    )
    if result.returncode != 0:
        return {"error": result.stderr[:2000]}
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"raw_output": result.stdout[:3000]}


if __name__ == "__main__":
    mcp.run()
