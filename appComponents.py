import streamlit as st
from io import StringIO
import json
import os
import pandas as pd
from bs4 import BeautifulSoup
import plotly.express as px
import plotly.graph_objects as go
from clash import ClashReport
from loader import Table
from configManager import ConfigManager

def upload_html(self, key="uploader_html"):
    st.markdown("### Envie o arquivo HTML do Clash Report (Navisworks)")

    uploaded_file = st.file_uploader(
        "Escolha o arquivo HTML",
        type=["html", "htm"],
        key=key            # <- agora a key vem da função
    )

    if not uploaded_file:
        return None

    # Tentativa de decodificação
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
        if value <= 33:
            return "baixo"
        elif value <= 66:
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

            severity_val = analysis.get("severity")
            analysis["severity"] =  categorize(self, severity_val)

            first_rg = analysis.get("first", {}).get("reworkGrade")
            second_rg = analysis.get("second", {}).get("reworkGrade")

            if "first" in analysis:
                analysis["first"]["reworkGrade"] = categorize(self, first_rg)
            if "second" in analysis:
                analysis["second"]["reworkGrade"] = categorize(self, second_rg)

        return data
    
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