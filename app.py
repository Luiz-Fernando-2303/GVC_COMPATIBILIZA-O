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

class ConfigManager:
    PATH = "config.json"
    DEFAULT = {
        "weights": {
            "ARQ": 4.0,
        },
        "files": {
            "190-0000.nwc": "ARQ",
        }
    }

    @classmethod
    def load(cls):
        if not os.path.exists(cls.PATH):
            cls.save(cls.DEFAULT)
            return dict(cls.DEFAULT)
        try:
            with open(cls.PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            if "weights" not in data or "files" not in data:
                cls.save(cls.DEFAULT)
                return dict(cls.DEFAULT)
            return data
        except Exception:
            cls.save(cls.DEFAULT)
            return dict(cls.DEFAULT)

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
        if "force_rerun" not in st.session_state:
            st.session_state.force_rerun = False
        self.config = st.session_state.CONFIG

    def read_csv_safely(self, file):
        encodings = ["cp1252", "latin-1", "iso-8859-1", "utf-8"]
        seps = [",", ";", "\t"]
        for enc in encodings:
            for sep in seps:
                try:
                    file.seek(0)
                    return pd.read_csv(file, encoding=enc, sep=sep)
                except Exception:
                    pass
        raise ValueError("Não foi possível detectar o encoding/sep do CSV.")

    def sidebar(self):
        st.sidebar.header("Configurações")

        # ---------------------------
        # PESOS POR DISCIPLINA
        # ---------------------------
        st.sidebar.subheader("Pesos por Disciplina")
        self.config.setdefault("weights", {})
        weights = dict(self.config["weights"])

        for disc in list(weights.keys()):
            new_val = st.sidebar.number_input(
                disc, min_value=0.0, max_value=10.0, step=0.1,
                value=float(weights[disc]), key=f"weight_{disc}"
            )
            if float(new_val) != weights[disc]:
                self.config["weights"][disc] = float(new_val)
                ConfigManager.save(self.config)
                st.session_state.force_rerun = True

        st.sidebar.markdown("---")

        # ---------------------------
        # ADICIONAR NOVA DISCIPLINA
        # ---------------------------
        st.sidebar.subheader("Gerenciar Disciplinas")

        new_disc = st.sidebar.text_input("Nova disciplina", key="input_new_disc")
        new_weight = st.sidebar.number_input(
            "Peso da nova disciplina", 0.0, 10.0, 1.0, 0.1, key="input_new_weight"
        )

        if st.sidebar.button("Adicionar disciplina", key="btn_add_disc"):
            if new_disc.strip():
                self.config["weights"][new_disc] = float(new_weight)
                ConfigManager.save(self.config)
                st.session_state.force_rerun = True

        st.sidebar.markdown("---")

        # ---------------------------
        # MAPEAMENTO ARQUIVOS → DISCIPLINAS (somente campos texto)
        # ---------------------------
        st.sidebar.subheader("Mapeamento de Arquivos → Disciplina")

        self.config.setdefault("files", {})
        files = dict(self.config["files"])

        if not files:
            st.sidebar.info("Nenhum arquivo configurado.")

        for fname in list(files.keys()):
            cols = st.sidebar.columns([3, 3, 1])

            # Nome do arquivo editável
            with cols[0]:
                new_name = st.text_input(
                    "Arquivo",
                    value=fname,
                    key=f"file_name_{fname}"
                )

                if new_name != fname and new_name.strip():
                    self.config["files"][new_name] = self.config["files"].pop(fname)
                    ConfigManager.save(self.config)
                    st.session_state.force_rerun = True

            # Disciplina também editável
            with cols[1]:
                current_disc = self.config["files"].get(fname, "")
                new_disc = st.text_input(
                    "Disciplina",
                    value=current_disc,
                    key=f"file_disc_{fname}"
                )

                if new_disc != current_disc:
                    self.config["files"][fname] = new_disc
                    ConfigManager.save(self.config)
                    st.session_state.force_rerun = True

            # Botão remover
            with cols[2]:
                if st.button("🗑️", key=f"btn_remove_{fname}"):
                    del self.config["files"][fname]
                    ConfigManager.save(self.config)
                    st.session_state.force_rerun = True

        st.sidebar.markdown("---")

        # ---------------------------
        # ADICIONAR NOVO ARQUIVO (somente texto)
        # ---------------------------
        st.sidebar.subheader("Adicionar arquivo")

        new_file = st.sidebar.text_input("Novo arquivo (nome.ext)", key="input_new_file")

        new_file_disc = st.sidebar.text_input(
            "Disciplina do novo arquivo", key="input_new_file_disc"
        )

        if st.sidebar.button("Adicionar arquivo", key="btn_add_file"):
            if new_file.strip():
                self.config["files"][new_file] = new_file_disc
                ConfigManager.save(self.config)
                st.session_state.force_rerun = True

        st.sidebar.markdown("---")

        # ---------------------------
        # IMPORTAR PLANILHA
        # ---------------------------
        st.sidebar.subheader("Importar configuração via planilha")

        config_file = st.sidebar.file_uploader(
            "Importar CSV ou Excel (arquivo / disciplina)",
            type=["csv", "xlsx"],
            key="uploader_config"
        )

        if config_file is not None:
            try:
                if config_file.name.endswith(".csv"):
                    df = self.read_csv_safely(config_file)
                    df.columns = [col.replace("\t", "").replace(" ", "_") for col in df.columns]
                else:
                    df = pd.read_excel(config_file)

                for _, row in df.iterrows():
                    self.config["files"][str(row["arquivo"])] = str(row["disciplina"])

                ConfigManager.save(self.config)
                st.sidebar.success("Configurações importadas.")
                st.session_state.force_rerun = True

            except Exception as e:
                st.sidebar.error(f"Erro ao importar: {e}")

        st.sidebar.markdown("---")

        # ---------------------------
        # SALVAR CONFIGURAÇÕES
        # ---------------------------
        if st.sidebar.button("Salvar Configurações", key="btn_save_config"):
            ConfigManager.save(self.config)
            st.session_state.force_rerun = True

    def upload_html(self):
        st.markdown("### Envie o arquivo HTML do Clash Report (Navisworks)")
        uploaded_file = st.file_uploader(
            "Escolha o arquivo HTML", type=["html", "htm"], key="uploader_html"
        )
        if not uploaded_file:
            return None
        try:
            content = uploaded_file.getvalue().decode("utf-8")
        except Exception:
            try:
                content = uploaded_file.getvalue().decode("latin-1")
            except Exception:
                st.error("Erro ao decodificar o arquivo.")
                return None
        soup = BeautifulSoup(StringIO(content).read(), "lxml")
        table = Table(soup)
        df = table.df
        if df is not None and not df.empty:
            st.success("Arquivo carregado com sucesso!")
            st.dataframe(df, use_container_width=True)
            return table
        st.warning("Nenhuma tabela encontrada no arquivo.")
        return None
    
    def categorize(self, value):
        if value is None or value == "":
            return ""
        if value < 10:
            return "baixo"
        elif value < 20:
            return "medio"
        else:
            return "alto"


    def normalize_clash_data(self, data):
        """
        Normaliza os valores de severity e reworkGrade em 'alto', 'medio' e 'baixo'.
        Modifica o dicionário data diretamente.
        """
        for item in data:
            analysis = item.get("automatedAnalysis", {})

            # Normaliza severity
            severity_val = analysis.get("severity")
            analysis["severity"] =  self.categorize(severity_val)

            # Normaliza reworkGrade dos dois lados
            first_rg = analysis.get("first", {}).get("reworkGrade")
            second_rg = analysis.get("second", {}).get("reworkGrade")

            if "first" in analysis:
                analysis["first"]["reworkGrade"] = self.categorize(first_rg)
            if "second" in analysis:
                analysis["second"]["reworkGrade"] = self.categorize(second_rg)

        return data

    def process_report(self, table):
        report = ClashReport(table)
        data = report.generate_report(
            weights=self.config.get("weights", {}),
            config=self.config
        )
        if not data:
            st.warning("Nenhum dado processado no relatório.")
            st.session_state.force_rerun = True
            ConfigManager.save(self.config)
            return

        df = self.flatten(data)
        st.markdown("### Resultados da Análise")
        report_flat = report.flatten_report()
        st.dataframe(report_flat, use_container_width=True)
        col1, col2 = st.columns(2)
        self.show_combinations(df, col1, col2)
        self.show_bim_combinations(df, col1, col2)
        self.show_map(df)
        self.show_distribution(df)

        data = self.normalize_clash_data(data)

        with st.expander("Visualizar JSON (10 primeiros)"):
            st.download_button(
                label="Download JSON",
                data=json.dumps(data, indent=4, ensure_ascii=False),
                file_name="clash_report.json",
                mime="application/json",
            )
            st.json(data[:10])

    def flatten(self, data):
        def extract_quadrant(item):
            q1 = item.get("itemsInfo", {}).get("first", {}).get("quadrants", [])
            q2 = item.get("itemsInfo", {}).get("second", {}).get("quadrants", [])
            quadrants = [q for q in (q1 + q2) if q]
            return quadrants[0] if quadrants else "Unknown"

        rows = []
        for item in data:
            bim_normas = (
                item.get("itemsInfo", {}).get("first", {}).get("norma_bim", "Unknown") +
                " / " +
                item.get("itemsInfo", {}).get("second", {}).get("norma_bim", "Unknown")
            )
            rows.append({
                "Item ID": item.get("id"),
                "Disciplina 1": (item.get("disciplines") or [None, None])[0],
                "Disciplina 2": (item.get("disciplines") or [None, None])[1],
                "Distância": item.get("distance"),
                "Severity": item.get("automatedAnalysis", {}).get("severity"),
                "Rework Grade 1": item.get("automatedAnalysis", {}).get("first", {}).get("reworkGrade"),
                "Rework Grade 2": item.get("automatedAnalysis", {}).get("second", {}).get("reworkGrade"),
                "Quadrante": extract_quadrant(item),
                "BIM": bim_normas,
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
        table = self.upload_html()
        if table:
            with st.spinner("Gerando relatório automatizado..."):
                self.process_report(table)
        if st.session_state.get("force_rerun", False):
            st.session_state["force_rerun"] = False
            st.rerun()

if __name__ == "__main__":
    ClashAnalyzerApp().run()
