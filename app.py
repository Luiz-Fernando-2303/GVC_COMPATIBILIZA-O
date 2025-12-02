from io import StringIO
import json
import os
import streamlit as st
import pandas as pd
from bs4 import BeautifulSoup
import plotly.express as px
import plotly.graph_objects as go
from clash import ClashReport
from loader import Table
from configManager import ConfigManager
from sidebar import _render_add_discipline, _render_add_file, _render_file_mapping, _render_import, _render_weights_section
from appComponents import *

class ClashAnalyzerApp:
    def __init__(self):
        st.set_page_config(page_title="Analisador de Clash", layout="wide")
        st.title("Analisador de Clash Automático")
        if "CONFIG" not in st.session_state:
            st.session_state.CONFIG = ConfigManager.load()
        if "force_rerun" not in st.session_state:
            st.session_state.force_rerun = False
        if "use_owner_guid" not in st.session_state:
            st.session_state.use_owner_guid = True
        if "require_reupload" not in st.session_state:
            st.session_state.require_reupload = False
        self.config = st.session_state.CONFIG
        self.USE_OWNER_GUID = st.session_state.use_owner_guid

    def sidebar(self):
        st.sidebar.header("Configurações")

        if not self.config.get("files", {}):
            st.sidebar.warning("Nenhuma disciplina configurada.")

        self.config.setdefault("weights", {})
        self.config.setdefault("files", {})

        st.sidebar.subheader("Pesos por Disciplina")
        _render_weights_section(self)

        st.sidebar.markdown("---")
        st.sidebar.subheader("Gerenciar Disciplinas")
        _render_add_discipline(self)

        st.sidebar.markdown("---")
        st.sidebar.subheader("Mapeamento de Arquivos → Disciplina")
        _render_file_mapping(self)

        st.sidebar.markdown("---")
        st.sidebar.subheader("Adicionar arquivo")
        _render_add_file(self)

        st.sidebar.markdown("---")
        st.sidebar.subheader("Importar configuração via planilha")
        _render_import(self)

        st.sidebar.markdown("---")
        use_owner_guid = st.sidebar.checkbox(
            "Usar GUID do proprietário",
            value=st.session_state.use_owner_guid
        )

        if use_owner_guid != st.session_state.use_owner_guid:
            st.session_state.use_owner_guid = use_owner_guid
            self.USE_OWNER_GUID = use_owner_guid
            if "uploaded_file" in st.session_state:
                del st.session_state["uploaded_file"]
            st.session_state.require_reupload = True
            st.session_state.force_rerun = True
            st.rerun()

        if st.sidebar.button("Salvar Configurações"):
            ConfigManager.save(self.config)
            st.sidebar.success("Configurações salvas.")

        if st.sidebar.button("Atualizar Interface"):
            st.session_state.force_rerun = True

    def process_report(self, table):
        report = ClashReport(table, self.USE_OWNER_GUID)
        data = report.generate_report(
            weights=self.config.get("weights", {}),
            config=self.config
        )
        if not data:
            st.warning("Nenhum dado processado no relatório.")
            st.session_state.force_rerun = True
            ConfigManager.save(self.config)
            return

        df = flatten(self, data)
        st.markdown("### Resultados da Análise")
        report_flat = report.flatten_report()
        st.dataframe(report_flat, use_container_width=True)
        col1, col2 = st.columns(2)
        self.show_combinations(df, col1, col2)
        self.show_bim_combinations(df, col1, col2)
        self.show_map(df)
        self.show_distribution(df)

        data = normalize_clash_data(self, data)

        with st.expander("Visualizar JSON (10 primeiros)"):
            st.download_button(
                label="Download JSON",
                data=json.dumps(data, indent=4, ensure_ascii=False),
                file_name="clash_report.json",
                mime="application/json",
            )
            st.json(data[:10])

    def generate_colors(self, items):
        palette = px.colors.qualitative.Plotly
        return {disc: palette[i % len(palette)] for i, disc in enumerate(items)}

    def color_cells(self, val, max_val):
        if max_val == 0:
            return ""
        ratio = val / max_val
        r, g = int(180 * ratio + 50), int(180 * (1 - ratio) + 50)
        return f"background-color: rgb({r},{g},0); color: black;"

    def show_combinations(self, df, col1, col2):
        all_discs = pd.unique(
            pd.concat([df["Disciplina 1"], df["Disciplina 2"]]).fillna("Unknown")
        )
        combo = pd.DataFrame(0, index=all_discs, columns=all_discs)

        for _, r in df.iterrows():
            d1 = r["Disciplina 1"] or "Unknown"
            d2 = r["Disciplina 2"] or "Unknown"
            if d1 not in combo.index:
                combo.loc[d1] = 0
            if d1 not in combo.columns:
                combo[d1] = 0
            if d2 not in combo.index:
                combo.loc[d2] = 0
            if d2 not in combo.columns:
                combo[d2] = 0
            combo.at[d1, d2] += 1

        max_val = combo.values.max() if combo.size else 0
        grid = combo.style.applymap(lambda v: self.color_cells(v, max_val))
        col1.markdown("Combinação de disciplinas (Grid)")
        col1.dataframe(grid, use_container_width=True)

        combo_df = combo.stack().reset_index()
        combo_df.columns = ["Disciplina 1", "Disciplina 2", "Contagem"]
        combo_df = combo_df[combo_df["Contagem"] > 0]
        combo_df = combo_df.sort_values("Contagem", ascending=False).head(20)
        combo_df["Combinação"] = combo_df["Disciplina 1"] + " × " + combo_df["Disciplina 2"]

        fig = px.bar(
            combo_df, x="Combinação", y="Contagem",
            text="Contagem", color="Contagem",
            color_continuous_scale="RdYlGn_r",
            title="Top 20 Clashes por Combinação de Disciplinas"
        )
        fig.update_layout(xaxis_tickangle=-45)
        col2.plotly_chart(fig, use_container_width=True)

    def show_bim_combinations(self, df, col1, col2):
        bim_list = []
        for val in df["BIM"].dropna():
            parts = val.split(" / ")
            if len(parts) == 2:
                bim_list.extend(parts)
        all_bim = sorted(pd.unique(bim_list))
        combo_bim = pd.DataFrame(0, index=all_bim, columns=all_bim)

        for _, r in df.iterrows():
            parts = (r["BIM"] or "Unknown").split(" / ")
            b1 = parts[0] if len(parts) > 0 else "Unknown"
            b2 = parts[1] if len(parts) > 1 else "Unknown"
            if b1 not in combo_bim.index:
                combo_bim.loc[b1] = 0
                combo_bim[b1] = 0
            if b2 not in combo_bim.columns:
                combo_bim[b2] = 0
                combo_bim.loc[b2] = 0
            combo_bim.at[b1, b2] += 1

        max_val = combo_bim.values.max() if not combo_bim.empty else 0
        grid = combo_bim.style.applymap(lambda v: self.color_cells(v, max_val))
        col1.markdown("Combinação de códigos BIM (Grid)")
        col1.dataframe(grid, use_container_width=True)

        combo_df = combo_bim.stack().reset_index(name="Contagem")
        combo_df.columns = ["BIM 1", "BIM 2", "Contagem"]
        combo_df = combo_df[combo_df["Contagem"] > 0].sort_values("Contagem", ascending=False).head(20)
        combo_df["Combinação"] = combo_df["BIM 1"] + " × " + combo_df["BIM 2"]

        fig = px.bar(
            combo_df, x="Combinação", y="Contagem",
            text="Contagem", color="Contagem",
            color_continuous_scale="RdYlGn_r",
            title="Top 20 Clashes por Combinação de Códigos BIM"
        )
        fig.update_layout(xaxis_tickangle=-45)
        col2.plotly_chart(fig, use_container_width=True)

    def show_map(self, df):
        st.markdown("### 🌐 Mapa dos Clashs")
        map_df = df.dropna(subset=["Location X", "Location Y", "Location Z"])
        if map_df.empty:
            st.info("Sem coordenadas suficientes para plotar (X, Y, Z).")
            return

        tab_quadrante, tab_rework, tab_severity, tab_distance, tab_norm = st.tabs(
            ["Quadrante", "Rework Grade", "Severidade", "Distância", "BIM 3E"]
        )

        with tab_quadrante:
            self._plot_3d_map(
                map_df, color_col="Quadrante",
                title="Mapa 3D dos Clashs por Quadrante"
            )
        with tab_rework:
            map_df["Rework Médio"] = map_df[["Rework Grade 1", "Rework Grade 2"]].mean(axis=1, skipna=True)
            self._plot_3d_map(
                map_df, color_col="Rework Médio",
                title="Mapa 3D por Grau Médio de Retrabalho",
                color_scale="RdYlGn_r"
            )
        with tab_severity:
            self._plot_3d_map(
                map_df, color_col="Severity",
                title="Mapa 3D por Severidade",
                color_scale="Viridis"
            )
        with tab_distance:
            self._plot_3d_map(
                map_df, color_col="Distância",
                title="Mapa 3D por Distância",
                color_scale="RdYlGn_r"
            )
        with tab_norm:
            self._plot_3d_map(
                map_df, color_col="BIM",
                title="Mapa 3D por BIM 3E",
                color_scale="RdYlGn_r"
            )

    def _plot_3d_map(self, df, color_col, title, color_scale=None):
        fig = px.scatter_3d(
            df,
            x="Location X", y="Location Y", z="Location Z",
            color=color_col,
            hover_data=["Item ID", "Disciplina 1", "Disciplina 2", "Severity"],
            title=title, opacity=0.75,
            color_continuous_scale=color_scale or px.colors.qualitative.Bold,
            size_max=8
        )
        fig.update_traces(marker=dict(size=4, line=dict(width=0)))
        fig.update_layout(
            scene=dict(
                xaxis=dict(title="X", backgroundcolor="rgb(15,15,15)", gridcolor="gray", showbackground=True),
                yaxis=dict(title="Y", backgroundcolor="rgb(15,15,15)", gridcolor="gray", showbackground=True),
                zaxis=dict(title="Z", backgroundcolor="rgb(15,15,15)", gridcolor="gray", showbackground=True),
                aspectmode="data"
            ),
            paper_bgcolor="rgb(10,10,10)",
            plot_bgcolor="rgb(10,10,10)",
            font=dict(color="white", size=12),
            title=dict(x=0.05, font=dict(size=18, color="white")),
            margin=dict(l=0, r=0, b=0, t=50),
            height=700,
            showlegend=True,
            legend=dict(bgcolor="rgba(0,0,0,0.5)", bordercolor="gray", font=dict(color="white", size=10))
        )
        fig.update_scenes(camera=dict(eye=dict(x=1.5, y=1.5, z=1.2)))
        st.plotly_chart(fig, use_container_width=True)

    def show_distribution(self, df):
        col1, col2 = st.columns(2)
        colors = self.generate_colors(df["Disciplina 1"].dropna().unique())

        with col1:
            discs = pd.concat([df["Disciplina 1"], df["Disciplina 2"]]).fillna("Unknown")
            count = discs.value_counts().reset_index()
            count.columns = ["Disciplina", "Contagem"]
            fig = px.bar(
                count, x="Disciplina", y="Contagem",
                color="Disciplina", color_discrete_map=colors,
                title="Distribuição de Disciplinas"
            )
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            quad = df.groupby("Quadrante").agg(
                Clashes=("Item ID", "count"),
                Severity=("Severity", "sum")
            ).reset_index()

            fig = go.Figure()
            fig.add_trace(go.Bar(x=quad["Quadrante"], y=quad["Clashes"], name="Clashes"))
            fig.add_trace(go.Scatter(x=quad["Quadrante"], y=quad["Severity"], name="Severidade", yaxis="y2"))

            fig.update_layout(
                title="Clash por Quadrante e Severidade Acumulada",
                yaxis_title="Clashes",
                yaxis2=dict(overlaying="y", side="right", title="Severidade")
            )

            st.plotly_chart(fig, use_container_width=True)

    def run(self):
        self.sidebar()

        upload_key = f"html_upload_{st.session_state.use_owner_guid}"
        table = upload_html(self, key=upload_key)

        if st.session_state.get("require_reupload", False):
            st.warning("O modo de GUID foi alterado. Envie novamente o arquivo HTML para continuar.")
            st.session_state.require_reupload = False
            return

        if table:
            with st.spinner("Gerando relatório automatizado..."):
                self.process_report(table)

        if st.session_state.get("force_rerun", False):
            st.session_state["force_rerun"] = False
            st.rerun()

if __name__ == "__main__":
    ClashAnalyzerApp().run()
