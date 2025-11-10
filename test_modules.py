from bs4 import BeautifulSoup
from clash import ClashReport
from loader import Table
# from bcf_exporter import BCFExporter
    
if __name__ == "__main__":

    with open("Example.html", "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f, "lxml")
        table = Table(soup)
        report = ClashReport(table)
        # exporter = BCFExporter(report)
        # exporter.export()