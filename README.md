# MEF Subnational Efficiency MCP

Production-grade Local Multi-Agent Analytics Pipeline for auditing Peruvian public budget execution (Fiscal 2025) and digitising the 1964 Ministerio de Hacienda historical archive.

## Architecture

```
Claude Code CLI
     │
     ├── executor_skill.json   ← data engineering worker
     └── evaluator_skill.json  ← QA auditor & UX optimizer
              │
              ▼
     src/mcp_server.py         ← 10 MCP tools (FastMCP)
              │
     datosabiertos.gob.pe      ← CKAN API (snapshots only)
              │
     src/data_pipeline.py      ← DuckDB/Polars local processing
     src/ocr_engine.py         ← PaddleOCR (1964 PDF, 15+ pages)
     src/analytical_engine.py  ← Avance%, Saldo No Devengado
              │
     data/processed/           ← Parquet footprints + OCR JSON
              │
     app.py                    ← 4-tab Streamlit dashboard
```

## Quick Start

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Start the MCP server
```bash
python src/mcp_server.py
```

### 3. Run the Executor Skill
```bash
claude "run executor_skill for period 2025-12"
```

### 4. Run the Evaluator Skill
```bash
claude "run evaluator_skill"
```

### 5. Launch the dashboard
```bash
streamlit run app.py
```

## CLI Period Control

The pipeline is period-driven — never hardcoded:

```bash
claude "run executor_skill for period 2025-12"
claude "execute mef_update for 2025-Q4"
claude "run executor_skill for period 2025-06"
```

## MCP Tools

| Tool | Purpose |
|------|---------|
| `buscar_datasets` | Search portal via CKAN keyword query |
| `obtener_detalle_dataset` | Get resource download URLs by dataset ID |
| `descargar_documento_1964` | Download 1964 historical PDF |
| `listar_entidades_publicas` | List active public organizations |
| `listar_categorias_tematicas` | Map thematic data groups |
| `obtener_ultimas_actualizaciones` | Fetch recently updated datasets |
| `inspeccionar_esquema_csv` | Safe schema snapshot (anti-context-flooding) |
| `consultar_datastore_filtrado` | Remote SQL-like filtered query |
| `procesar_ocr_paginas_1964` | Trigger PaddleOCR on 15+ PDF pages |
| `descargar_y_analizar_estadisticas` | Download + aggregate locally |

## Anti-Context-Flooding Strategy

Raw MEF datasets range from 200MB to 1GB. The pipeline **never** reads these into LLM context. Instead:

1. `inspeccionar_esquema_csv` → snapshot first 10 rows only
2. `data_pipeline.py` runs locally with DuckDB to filter + aggregate
3. Saves a microscopic Parquet file to `data/processed/`
4. Streamlit reads only the Parquet

## Analytical Metrics

- **Avance %** = (Devengado / PIM) × 100
- **Saldo No Devengado** = PIM − Devengado
- **Threshold**: Entities with PIM > S/ 10,000,000 (10M soles)

## Streamlit Dashboard Tabs

| Tab | Content |
|-----|---------|
| 1 — Resumen Ejecutivo | 2025 KPIs + 1964 OCR results (independent, no cross-epoch comparison) |
| 2 — Distribución Territorial | 2025 geospatial charts by department |
| 3 — Hall of Shame | 2025 worst-performing entities (PIM > 10M, lowest execution) |
| 4 — Audit Log & Playground | Evaluator report + live period switcher |

## Git Workflow

```bash
git checkout -b feature/mcp-server-core
git checkout -b feature/data-snapshot-pipeline
git checkout -b feature/historical-1964-paddle-ocr
git checkout -b feature/executor-dashboard-draft
git checkout -b feature/evaluator-qa-refinement
```

Never commit directly to `main`. Always use Pull Requests.
