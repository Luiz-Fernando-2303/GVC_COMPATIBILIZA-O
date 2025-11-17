from bs4 import BeautifulSoup
from clash import ClashReport
from loader import Table
# from bcf_exporter import BCFExporter
    
if __name__ == "__main__":
    import streamlit.web.cli as stcli
    import sys
    sys.argv = ["streamlit", "run", "app.py", "--server.maxUploadSize=1024", "--logger.level=debug"]
    sys.exit(stcli.main())