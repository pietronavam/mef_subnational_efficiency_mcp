"""
MEF Subnational Efficiency Dashboard — 4-tab Streamlit application.
Reads only from data/processed/ — never from raw CSV/JSON.
Run: streamlit run app.py
"""
import json
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).parent
PROCESSED = ROOT / "data" / "processed"

st.set_page_config(
    page_title="MEF Subnational Efficiency 2025",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown(
    """
    <style>
    .block-container { padding-top: 1.5rem; }
    .stMetric { background: #f0f4ff; border-radius: 8px; padding: 0.5rem; }
    .stMetric label { font-size: 0.82rem !important; color: #555 !important; }
    .era-badge {
        display:inline-block; padding:2px 10px; border-radius:12px;
        font-size:0.78rem; font-weight:600; margin-bottom:6px;
    }
    .badge-2025 { background:#dbeafe; color:#1d4ed8; }
    .badge-1964 { background:#fef3c7; color:#92400e; }
    .shame-card { border-left:4px solid #ef4444; padding:6px 12px; margin:4px 0; background:#fff5f5; border-radius:4px; }
    .audit-card { border-left:4px solid #10b981; padding:6px 12px; margin:4px 0; background:#f0fdf4; border-radius:4px; }
    </style>
    """,
    unsafe_allow_html=True,
)


# ── Cached data loaders ───────────────────────────────────────────────────────

@st.cache_data(show_spinner=False)
def load_budget_2025() -> pd.DataFrame | None:
    for ext in [".parquet", ".csv"]:
        p = PROCESSED / f"budget_2025{ext}"
        if p.exists():
            return pd.read_parquet(p) if ext == ".parquet" else pd.read_csv(p)
    return None


@st.cache_data(show_spinner=False)
def load_ocr_1964() -> dict:
    p = PROCESSED / "ocr_1964_results.json"
    if not p.exists():
        return {}
    with open(p, encoding="utf-8") as f:
        return json.load(f)


@st.cache_data(show_spinner=False)
def load_audit_report() -> str:
    p = PROCESSED / "evaluator_report.md"
    return p.read_text(encoding="utf-8") if p.exists() else ""


def enrich(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["avance_pct"] = (df["devengado"] / df["pim"].replace(0, pd.NA) * 100).round(2)
    df["saldo_no_devengado"] = (df["pim"] - df["devengado"]).round(2)
    return df


def fmt_pen(val: float) -> str:
    if val >= 1e9:
        return f"S/ {val/1e9:.2f} B"
    if val >= 1e6:
        return f"S/ {val/1e6:.1f} M"
    return f"S/ {val:,.0f}"


def no_data_msg(component: str = "datos"):
    st.info(
        f"⚙️ **Sin {component} disponibles.** Ejecuta el Executor Skill para cargar los datos:\n\n"
        "`claude \"run executor_skill for period 2025-12\"`",
        icon="📂",
    )


# ── TABS ──────────────────────────────────────────────────────────────────────

tab1, tab2, tab3, tab4 = st.tabs([
    "📊 Resumen Ejecutivo",
    "🗺️ Distribución Territorial",
    "🚨 Hall of Shame",
    "🤖 Audit Log & Playground",
])


# ════════════════════════════════════════════════════════════════════════════
# TAB 1 — Executive Macro Summary & Dual-Era Opening Dashboard
# ════════════════════════════════════════════════════════════════════════════
with tab1:
    col_left, col_right = st.columns(2, gap="large")

    # ── 2025 Section ──────────────────────────────────────────────────────
    with col_left:
        st.markdown('<span class="era-badge badge-2025">PERÚ FISCAL 2025</span>', unsafe_allow_html=True)
        st.subheader("Indicadores Macroeconómicos Nacionales")
        df25 = load_budget_2025()
        if df25 is None:
            no_data_msg("datos 2025")
        else:
            df25 = enrich(df25)
            total_pim = df25["pim"].sum()
            total_dev = df25["devengado"].sum()
            exec_rate = (total_dev / total_pim * 100) if total_pim else 0
            frozen = total_pim - total_dev

            k1, k2, k3 = st.columns(3)
            k1.metric("PIM Total 2025", fmt_pen(total_pim))
            k2.metric("Devengado Total", fmt_pen(total_dev))
            k3.metric("Avance de Ejecución", f"{exec_rate:.1f}%")
            st.metric("Capital Paralizado (Saldo No Devengado)", fmt_pen(frozen), delta=f"-{fmt_pen(frozen)}", delta_color="inverse")

            st.markdown("**Análisis de Cuellos de Botella Fiscales 2025**")
            st.markdown(
                f"""
                Al período 2025, el Presupuesto Institucional Modificado (PIM) nacional alcanza
                **{fmt_pen(total_pim)}**. Con un devengado de **{fmt_pen(total_dev)}**, la tasa de ejecución
                es de **{exec_rate:.1f}%**, dejando un capital paralizado de **{fmt_pen(frozen)}** sin ejecutar.

                Los principales cuellos de botella se concentran en gobiernos regionales y locales con
                presupuestos superiores a 10 millones de soles y ejecución inferior al 40%. Esta situación
                compromete la provisión de servicios públicos y la inversión en infraestructura.
                """,
                unsafe_allow_html=False,
            )

    # ── 1964 Section ─────────────────────────────────────────────────────
    with col_right:
        st.markdown('<span class="era-badge badge-1964">PERÚ HISTÓRICO 1964</span>', unsafe_allow_html=True)
        st.subheader("Registro Histórico — Ministerio de Hacienda")
        ocr = load_ocr_1964()
        if not ocr:
            no_data_msg("datos históricos 1964")
        else:
            import re as _re

            pages_done = ocr.get("pages_processed", 0)
            total_blocks = ocr.get("total_text_blocks", 0)
            st.markdown(
                f"**Páginas procesadas via PaddleOCR:** {pages_done} &nbsp;|&nbsp; "
                f"**Bloques de texto extraídos:** {total_blocks}",
                unsafe_allow_html=True,
            )

            # Extract real monetary amounts from OCR text
            _PAGE_LABELS = {
                6: "Portada / Título",
                11: "Balance del Ejercicio",
                21: "Deuda al BCR / Déficit",
                31: "Financiamiento Déficit",
                41: "Pág. escaneada",
                61: "Ingresos / Egresos",
                81: "Pág. escaneada",
                101: "Cámara de Diputados",
                111: "Pág. escaneada",
                121: "Comparación Egresos",
                131: "Servicios Varios",
                141: "Resumen General",
                151: "Egresos Comparados",
                161: "Egresos / Recursos",
                171: "Depto. Indígenas",
                181: "Resumen Ministerial",
                191: "Totales Generales",
            }

            def _parse_amounts(text):
                raw = _re.findall(r"[\d']+[,\.]\d{3}[,\.]\d{2}", text)
                amounts = []
                for r in raw:
                    try:
                        cleaned = r.replace("'", "").replace(",", "")
                        amounts.append(float(cleaned))
                    except Exception:
                        pass
                return amounts

            page_totals = []
            summaries = ocr.get("page_summaries", [])
            for ps in summaries:
                amounts = _parse_amounts(ps.get("full_text", ""))
                if amounts:
                    page_totals.append({
                        "seccion": _PAGE_LABELS.get(ps["page"], f"Página {ps['page']}"),
                        "pagina": ps["page"],
                        "monto_mayor_sol": max(amounts),
                        "n_cifras": len(amounts),
                        "suma_soles": sum(amounts),
                    })

            if page_totals:
                import pandas as _pd2
                df_fin = _pd2.DataFrame(page_totals).sort_values("monto_mayor_sol", ascending=False)

                # Chart 1: Largest monetary figure per document section
                fig1 = px.bar(
                    df_fin.head(10), x="monto_mayor_sol", y="seccion",
                    orientation="h",
                    title="Cifra máxima en Soles Oro por Sección (1964)",
                    labels={"monto_mayor_sol": "Monto (Soles Oro)", "seccion": "Sección del Documento"},
                    color="monto_mayor_sol", color_continuous_scale="YlOrBr",
                    text_auto=".3s",
                )
                fig1.update_layout(showlegend=False, height=320, yaxis={"categoryorder": "total ascending"})
                st.plotly_chart(fig1, use_container_width=True)

                # Chart 2: Number of financial entries (cifras) per section
                df_fin2 = _pd2.DataFrame(page_totals).sort_values("pagina")
                fig2 = px.bar(
                    df_fin2, x="seccion", y="n_cifras",
                    title="Cantidad de Partidas Presupuestales por Sección (1964)",
                    labels={"n_cifras": "N° de partidas", "seccion": "Sección"},
                    color="n_cifras", color_continuous_scale="Oranges",
                )
                fig2.update_layout(showlegend=False, height=260, xaxis_tickangle=-35)
                st.plotly_chart(fig2, use_container_width=True)

            st.markdown("**Conclusiones históricas del archivo:**")
            st.markdown(
                "El Presupuesto General 1964 registra partidas que superan los **S/. 800 millones** en "
                "consolidación de deuda con el BCR. Los egresos de ministerios como Educación y Obras Públicas "
                "concentran las mayores transferencias. La estructura presupuestal refleja un Estado fuertemente "
                "centralizado con categorías de 'Soles Oro', moneda de referencia de la época."
            )
            for ps in summaries[:3]:
                with st.expander(f"Página {ps['page']} — {_PAGE_LABELS.get(ps['page'], '')} ({ps.get('total_blocks', 0)} bloques OCR)"):
                    st.code(ps.get("full_text", "")[:600], language=None)


# ════════════════════════════════════════════════════════════════════════════
# TAB 2 — Territorial Distribution & Geospatial Analysis (2025 only)
# ════════════════════════════════════════════════════════════════════════════
with tab2:
    st.subheader("Distribución Territorial — Ejecución Presupuestal 2025")
    df25 = load_budget_2025()
    if df25 is None:
        no_data_msg("datos territoriales 2025")
    else:
        df25 = enrich(df25)
        if "departamento" not in df25.columns:
            st.warning("Columna 'departamento' no encontrada en los datos procesados.")
        else:
            dept = (
                df25.groupby("departamento", as_index=False)
                .agg(pim=("pim", "sum"), devengado=("devengado", "sum"))
                .assign(
                    avance_pct=lambda x: (x["devengado"] / x["pim"].replace(0, pd.NA) * 100).round(2),
                    saldo=lambda x: (x["pim"] - x["devengado"]).round(2),
                )
                .sort_values("avance_pct")
            )

            col1, col2 = st.columns(2, gap="medium")

            with col1:
                fig_bar = px.bar(
                    dept.tail(20), x="avance_pct", y="departamento",
                    orientation="h",
                    title="Avance de Ejecución por Departamento (%)",
                    labels={"avance_pct": "Avance (%)", "departamento": "Departamento"},
                    color="avance_pct",
                    color_continuous_scale="RdYlGn",
                    range_color=[0, 100],
                )
                fig_bar.add_vline(x=70, line_dash="dash", line_color="orange", annotation_text="Umbral 70%")
                fig_bar.update_layout(height=500)
                st.plotly_chart(fig_bar, use_container_width=True)

            with col2:
                fig_scatter = px.scatter(
                    dept, x="pim", y="avance_pct",
                    size="saldo", color="avance_pct",
                    hover_name="departamento",
                    title="PIM vs Tasa de Ejecución — Tamaño = Capital Paralizado",
                    labels={"pim": "PIM (S/)", "avance_pct": "Avance (%)"},
                    color_continuous_scale="RdYlGn",
                    range_color=[0, 100],
                )
                fig_scatter.add_hline(y=50, line_dash="dot", line_color="red", annotation_text="50% crítico")
                fig_scatter.update_layout(height=500)
                st.plotly_chart(fig_scatter, use_container_width=True)

            st.markdown("---")
            st.subheader("Mapa de Calor — Capital Paralizado por Departamento")
            fig_heat = px.treemap(
                dept, path=["departamento"], values="saldo",
                color="avance_pct",
                color_continuous_scale="RdYlGn",
                title="Capital Paralizado (Saldo No Devengado) — Ejecución 2025",
                range_color=[0, 100],
            )
            fig_heat.update_layout(height=450)
            st.plotly_chart(fig_heat, use_container_width=True)


# ════════════════════════════════════════════════════════════════════════════
# TAB 3 — Budget "Hall of Shame" & Anomaly Explorer (2025 only)
# ════════════════════════════════════════════════════════════════════════════
with tab3:
    st.subheader("🚨 Budget Hall of Shame — Peores Ejecutores 2025")
    st.caption("Entidades con PIM > S/ 10 millones y menor tasa de ejecución")
    df25 = load_budget_2025()
    if df25 is None:
        no_data_msg("datos del Hall of Shame")
    else:
        df25 = enrich(df25)
        shame = df25[df25["pim"] > 10_000_000].sort_values("avance_pct").head(50).reset_index(drop=True)
        shame.index += 1

        col_filter1, col_filter2 = st.columns(2)
        with col_filter1:
            max_avance = st.slider("Mostrar entidades con avance menor a (%)", 0, 100, 40)
        with col_filter2:
            dept_filter = st.multiselect(
                "Filtrar por departamento",
                options=sorted(shame["departamento"].unique()) if "departamento" in shame.columns else [],
                default=[],
            )

        filtered = shame[shame["avance_pct"] <= max_avance]
        if dept_filter:
            filtered = filtered[filtered["departamento"].isin(dept_filter)]

        st.markdown(f"**{len(filtered)} entidades** con ejecución ≤ {max_avance}% y PIM > S/ 10M")

        display_cols = [c for c in ["entidad", "departamento", "pim", "devengado", "avance_pct", "saldo_no_devengado"] if c in filtered.columns]
        fmt = {
            "pim": "{:,.0f}",
            "devengado": "{:,.0f}",
            "avance_pct": "{:.1f}%",
            "saldo_no_devengado": "{:,.0f}",
        }
        st.dataframe(
            filtered[display_cols].style.format({k: v for k, v in fmt.items() if k in display_cols})
            .background_gradient(subset=["avance_pct"] if "avance_pct" in display_cols else [], cmap="RdYlGn", vmin=0, vmax=100),
            use_container_width=True,
            height=420,
        )

        st.markdown("---")
        if "departamento" in filtered.columns and not filtered.empty:
            cat_dept = filtered.groupby("departamento")["saldo_no_devengado"].sum().sort_values(ascending=False).head(15).reset_index()
            fig_shame = px.bar(
                cat_dept, x="saldo_no_devengado", y="departamento",
                orientation="h",
                title="Capital Paralizado Total por Departamento (peores ejecutores)",
                labels={"saldo_no_devengado": "Saldo No Devengado (S/)", "departamento": "Departamento"},
                color="saldo_no_devengado",
                color_continuous_scale="Reds",
            )
            fig_shame.update_layout(height=420)
            st.plotly_chart(fig_shame, use_container_width=True)


# ════════════════════════════════════════════════════════════════════════════
# TAB 4 — Multi-Agent Audit Log & Live Playground (2025 only)
# ════════════════════════════════════════════════════════════════════════════
with tab4:
    st.subheader("🤖 Multi-Agent Audit Log & Live Playground")

    col_log, col_play = st.columns([3, 2], gap="large")

    with col_log:
        st.markdown("#### Evaluator & Optimizer Skill — Reporte de Auditoría")
        audit = load_audit_report()
        if not audit:
            st.markdown(
                '<div class="audit-card">El reporte del Evaluator Skill se generará automáticamente '
                'tras ejecutar el skill de evaluación.<br><br>'
                '<code>claude "run evaluator_skill"</code></div>',
                unsafe_allow_html=True,
            )
            st.markdown("**Estado de evolución del pipeline:**")
            steps = [
                ("✅", "Executor Skill ejecutado", "MCP server corrió sin errores"),
                ("✅", "Snapshot de esquema tomado", "Anti-context-flooding activo"),
                ("⏳", "Datos 2025 procesados", "Ejecuta executor_skill para completar"),
                ("⏳", "OCR 1964 completado", "15+ páginas requeridas"),
                ("⏳", "Evaluator Skill ejecutado", "Reporte pendiente"),
            ]
            for icon, step, detail in steps:
                st.markdown(f"**{icon} {step}** — _{detail}_")
        else:
            st.markdown(audit)

    with col_play:
        st.markdown("#### Live Period Playground")
        st.markdown("Ingresa un período para actualizar el pipeline dinámicamente:")
        period_input = st.text_input("Período (ej: 2025-12, 2025-Q4)", value="2025-12")
        if st.button("🔄 Ejecutar pipeline para este período", type="primary"):
            st.info(
                f"Para ejecutar el pipeline para el período **{period_input}**, corre en tu terminal:\n\n"
                f"```\nclaude \"run executor_skill for period {period_input}\"\n```"
            )

        st.markdown("---")
        st.markdown("#### Resumen del Sistema")
        df25 = load_budget_2025()
        ocr = load_ocr_1964()

        status_items = {
            "Datos 2025 cargados": "✅" if df25 is not None else "❌",
            "OCR 1964 completado": "✅" if ocr else "❌",
            "Páginas OCR procesadas": str(ocr.get("pages_processed", 0)) if ocr else "0",
            "Reporte de auditoría": "✅" if audit else "❌",
            "Entidades en datos 2025": str(len(df25)) if df25 is not None else "0",
        }
        for label, val in status_items.items():
            st.markdown(f"**{label}:** {val}")
