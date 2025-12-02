import streamlit as st
from configManager import ConfigManager
import pandas as pd

def _render_weights_section(self):
    weights = dict(self.config["weights"])
    if not weights:
        st.sidebar.info("Nenhum peso registrado.")

    for disc in sorted(weights.keys()):
        try:
            new_val = st.sidebar.number_input(
                disc,
                min_value=0.0,
                max_value=10.0,
                step=0.1,
                value=float(weights[disc]),
                key=f"weight_{disc}"
            )
            if float(new_val) != weights[disc]:
                self.config["weights"][disc] = float(new_val)
                ConfigManager.save(self.config)
                st.sidebar.success(f"Peso atualizado: {disc}")
        except:
            st.sidebar.error(f"Erro ao processar peso de {disc}")

def _render_add_discipline(self):
    new_disc = st.sidebar.text_input("Nova disciplina", key="input_new_disc")
    new_weight = st.sidebar.number_input(
        "Peso da nova disciplina",
        0.0, 10.0, 1.0, 0.1,
        key="input_new_weight"
    )

    if st.sidebar.button("Adicionar disciplina"):
        if not new_disc.strip():
            st.sidebar.error("Nome inválido.")
            return

        if new_disc in self.config["weights"]:
            st.sidebar.warning("Disciplina já existe.")
            return

        self.config["weights"][new_disc] = float(new_weight)
        self.config["files"][new_disc] = new_disc
        ConfigManager.save(self.config)
        st.sidebar.success("Disciplina adicionada.")

def _render_file_mapping(self):
    files = dict(self.config["files"])
    if not files:
        st.sidebar.info("Nenhum arquivo configurado.")

    for fname in sorted(list(files.keys())):
        cols = st.sidebar.columns([4, 4, 1])

        with cols[0]:
            new_name = st.text_input(
                "Arquivo",
                value=fname,
                key=f"file_name_{fname}"
            )
            if new_name != fname and new_name.strip():
                self.config["files"][new_name] = self.config["files"].pop(fname)
                ConfigManager.save(self.config)
                st.sidebar.success("Arquivo renomeado.")

        with cols[1]:
            current_disc = self.config["files"].get(fname, "")
            new_disc = st.text_input(
                "Disciplina",
                value=current_disc,
                key=f"file_disc_{fname}"
            )
            if new_disc != current_disc:
                self.config["files"][fname] = new_disc
                if new_disc not in self.config["weights"]:
                    self.config["weights"][new_disc] = 1.0
                ConfigManager.save(self.config)
                st.sidebar.success("Disciplina atualizada.")

        with cols[2]:
            if st.button("🗑️", key=f"btn_remove_{fname}"):
                try:
                    disc = self.config["files"][fname]
                    files_with_disc = ConfigManager.getFilesWithDiscipline(disc)

                    if len(files_with_disc) > 1:
                        del self.config["files"][fname]
                    else:
                        if disc in self.config["weights"]:
                            del self.config["weights"][disc]
                        del self.config["files"][fname]

                    ConfigManager.save(self.config)
                    st.sidebar.success("Removido.")
                except:
                    st.sidebar.error("Erro ao remover.")

def _render_add_file(self):
    new_file = st.sidebar.text_input("Novo arquivo (nome.nwd)", key="input_new_file")
    new_file_disc = st.sidebar.text_input("Disciplina do novo arquivo", key="input_new_file_disc")

    if st.sidebar.button("Adicionar arquivo"):
        if not new_file.strip():
            st.sidebar.error("Nome de arquivo inválido.")
            return

        if new_file in self.config["files"]:
            st.sidebar.warning("Arquivo já existe.")
            return

        self.config["files"][new_file] = new_file_disc
        if new_file_disc not in self.config["weights"]:
            self.config["weights"][new_file_disc] = 1.0
        ConfigManager.save(self.config)
        st.sidebar.success("Arquivo adicionado.")

def _render_import(self):
    config_file = st.sidebar.file_uploader(
        "Importar CSV ou Excel (arquivo / disciplina)",
        type=["csv", "xlsx"],
        key="uploader_config"
    )

    if config_file is None:
        return

    try:
        df = pd.read_csv(config_file) if config_file.name.endswith(".csv") else pd.read_excel(config_file)
        df.columns = [col.replace("\t", "").replace(" ", "_") for col in df.columns]

        for _, row in df.iterrows():
            file_name = str(row.iloc[0]).strip()
            disc_name = str(row.iloc[1]).strip()

            if file_name:
                self.config["files"][file_name] = disc_name
                if disc_name and disc_name not in self.config["weights"]:
                    self.config["weights"][disc_name] = 1.0

        ConfigManager.save(self.config)
        st.sidebar.success("Configurações importadas.")
    except Exception as e:
        st.sidebar.error(f"Erro ao importar: {e}")