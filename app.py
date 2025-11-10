from io import StringIO
import json
import streamlit as st
import pandas as pd
from bs4 import BeautifulSoup
import plotly.express as px
import plotly.graph_objects as go
from test_modules import Table, ClashReport
from bcf_exporter import BCFExporter
import tempfile
import base64

class ConfigManager:
    PATH = "config.json"

    @classmethod
    def load(cls):
        try:
            with open(cls.PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"weights": {}}

    @classmethod
    def save(cls, config):
        with open(cls.PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4, ensure_ascii=False)


class ClashAnalyzerApp:
    def __init__(self):
        st.set_page_config(page_title="Analisador de Clash", layout="wide")
        st.title("Analisador de Clash Automático")
        if "CONFIG" not in st.session_state:
            st.session_state.CONFIG = ConfigManager.load()
        self.config = st.session_state.CONFIG

    def sidebar(self):
        st.sidebar.header("Configurações")
        st.sidebar.subheader("Pesos por Disciplina")
        for disc, weight in list(self.config["weights"].items()):
            self.config["weights"][disc] = st.sidebar.number_input(
                disc, min_value=0.0, max_value=10.0, step=0.1, value=float(weight), key=f"weight_{disc}"
            )
        new_disc = st.sidebar.text_input("Nova disciplina")
        new_weight = st.sidebar.number_input("Peso da nova disciplina", min_value=0.0, max_value=10.0, step=0.1, value=1.0)

        if st.sidebar.button("Adicionar disciplina") and new_disc:
            self.config["weights"][new_disc] = new_weight
            ConfigManager.save(self.config)
            st.sidebar.success(f"Disciplina '{new_disc}' adicionada com sucesso!")

        if st.sidebar.button("Salvar Configurações"):
            ConfigManager.save(self.config)
            st.sidebar.success("Configurações salvas com sucesso!")

    def upload_html(self):
        st.markdown("### Envie o arquivo HTML do Clash Report (Navisworks)")
        uploaded_file = st.file_uploader("Escolha o arquivo HTML", type=["html", "htm"])
        if not uploaded_file:
            return None

        soup = BeautifulSoup(StringIO(uploaded_file.getvalue().decode("utf-8")).read(), "lxml")
        table = Table(soup)
        df = table.df

        if df is not None and not df.empty:
            st.success("Arquivo carregado com sucesso!")
            st.dataframe(df, use_container_width=True)
            return table
        st.warning("Nenhuma tabela encontrada no arquivo.")
        return None

    def process_report(self, table):
        report = ClashReport(table)
        data = report.generate_report(weights=self.config.get("weights", {}))
        if not data:
            st.warning("Nenhum dado processado no relatório.")
            return

        df = self.flatten(data)
        st.markdown("### Resultados da Análise")
        report = report.flatten_report()
        st.dataframe(report, use_container_width=True)

        st.markdown("---")
        if st.button("📦 Exportar Relatório BCFZIP"):
            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".bcfzip") as tmp:
                    exporter = BCFExporter(report)
                    exporter.export(output_file=tmp.name)
                    tmp.flush()
                    tmp.seek(0)

                    b64 = base64.b64encode(tmp.read()).decode()
                    href = f'<a href="data:application/zip;base64,{b64}" download="clash_report.bcfzip">⬇️ Clique para baixar o arquivo BCF</a>'
                    st.markdown(href, unsafe_allow_html=True)

                    st.success("Exportação concluída com sucesso!")
            except Exception as e:
                st.error(f"Erro ao exportar BCF: {e}")

        col1, col2 = st.columns(2)
        self.show_combinations(df, col1, col2)
        self.show_map(df)
        self.show_distribution(df)

        with st.expander("Visualizar JSON (10 primeiros)"):
            st.json(data[:10])

    def flatten(self, data):
        def extract_quadrant(item):
            q1 = item.get("itemsInfo", {}).get("first", {}).get("quadrants", [])
            q2 = item.get("itemsInfo", {}).get("second", {}).get("quadrants", [])
            quadrants = [q for q in (q1 + q2) if q]
            return quadrants[0] if quadrants else "Unknown"

        rows = []
        for item in data:
            rows.append({
                "Item ID": item.get("id"),
                "Disciplina 1": (item.get("disciplines") or [None, None])[0],
                "Disciplina 2": (item.get("disciplines") or [None, None])[1],
                "Distância": item.get("distance"),
                "Severity": item.get("automatedAnalysis", {}).get("severity"),
                "Rework Grade 1": item.get("automatedAnalysis", {}).get("first", {}).get("reworkGrade"),
                "Rework Grade 2": item.get("automatedAnalysis", {}).get("second", {}).get("reworkGrade"),
                "Quadrante": extract_quadrant(item),
                "Location X": (item.get("location") or [None, None, None])[0],
                "Location Y": (item.get("location") or [None, None, None])[1],
                "Location Z": (item.get("location") or [None, None, None])[2],
            })
        return pd.DataFrame(rows)

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
        all_discs = pd.unique(pd.concat([df["Disciplina 1"], df["Disciplina 2"]]).fillna("Unknown"))
        combo = pd.DataFrame(0, index=all_discs, columns=all_discs)

        for _, r in df.iterrows():
            d1, d2 = r["Disciplina 1"] or "Unknown", r["Disciplina 2"] or "Unknown"
            combo.at[d1, d2] += 1

        colors = self.generate_colors(all_discs)
        max_val = combo.values.max()
        grid = combo.style.applymap(lambda v: self.color_cells(v, max_val))
        col1.markdown("Combinação de disciplinas (Grid)")
        col1.dataframe(grid, use_container_width=True)

        combo_df = combo.stack().reset_index()
        combo_df.columns = ["Disciplina 1", "Disciplina 2", "Contagem"]
        combo_df = combo_df[combo_df["Contagem"] > 0]
        combo_df["Combinação"] = combo_df["Disciplina 1"] + " × " + combo_df["Disciplina 2"]

        fig = px.bar(
            combo_df, x="Combinação", y="Contagem",
            text="Contagem", color="Contagem",
            color_continuous_scale="RdYlGn_r",
            title="Clashes por Combinação de Disciplinas"
        )
        fig.update_layout(xaxis_tickangle=-45, coloraxis_colorbar=dict(title="Qtd. Clashes"))
        col2.plotly_chart(fig, use_container_width=True)

    def show_map(self, df):
        st.markdown("### 🌐 Mapa dos Clashs")

        map_df = df.dropna(subset=["Location X", "Location Y", "Location Z"])
        if map_df.empty:
            st.info("Sem coordenadas suficientes para plotar (X, Y, Z).")
            return

        tab_quadrante, tab_rework, tab_severity, tab_distance = st.tabs(
            ["Quadrante", "Rework Grade", "Severidade", "Distância"]
        )

        with tab_quadrante:
            self._plot_3d_map(
                map_df,
                color_col="Quadrante",
                title="Mapa 3D dos Clashs por Quadrante"
            )

        with tab_rework:
            map_df["Rework Médio"] = map_df[
                ["Rework Grade 1", "Rework Grade 2"]
            ].mean(axis=1, skipna=True)
            self._plot_3d_map(
                map_df,
                color_col="Rework Médio",
                title="Mapa 3D por Grau Médio de Retrabalho",
                color_scale="RdYlGn_r"
            )

        with tab_severity:
            self._plot_3d_map(
                map_df,
                color_col="Severity",
                title="Mapa 3D por Severidade",
                color_scale="Viridis"
            )

        with tab_distance:
            self._plot_3d_map(
                map_df,
                color_col="Distância",
                title="Mapa 3D por Distância",
                color_scale="RdYlGn_r"
            )


    def _plot_3d_map(self, df, color_col, title, color_scale=None):

        fig = px.scatter_3d(
            df,
            x="Location X",
            y="Location Y",
            z="Location Z",
            color=color_col,
            hover_data=["Item ID", "Disciplina 1", "Disciplina 2", "Severity"],
            title=title,
            opacity=0.75,
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
            fig = px.bar(count, x="Disciplina", y="Contagem", color="Disciplina", color_discrete_map=colors)
            fig.update_layout(title="Distribuição de Disciplinas")
            st.plotly_chart(fig, use_container_width=True)

        with col2:
            quad = df.groupby("Quadrante").agg(Clashes=("Item ID", "count"), Severity=("Severity", "sum")).reset_index()
            fig = go.Figure()
            fig.add_trace(go.Bar(x=quad["Quadrante"], y=quad["Clashes"], name="Clashes"))
            fig.add_trace(go.Line(x=quad["Quadrante"], y=quad["Severity"], name="Severidade", yaxis="y2"))
            fig.update_layout(
                title="Clash por Quadrante e Severidade Acumulada",
                yaxis_title="Clashes",
                yaxis2=dict(overlaying="y", side="right", title="Severidade")
            )
            st.plotly_chart(fig, use_container_width=True)

    def run(self):
        self.sidebar()
        table = self.upload_html()
        if table:
            with st.spinner("Gerando relatório automatizado..."):
                self.process_report(table)


if __name__ == "__main__":
    ClashAnalyzerApp().run()
