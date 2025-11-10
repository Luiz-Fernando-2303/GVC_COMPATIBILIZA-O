import pandas as pd
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor

class Table:
    def __init__(self, soup: BeautifulSoup, max_workers: int = 8):
        self.soup = soup
        self.max_workers = max_workers
        self.df = self.to_df()

    def to_df(self):
        table = self.soup.find("table", class_=lambda x: x and "mainTable" in x)
        if table is None:
            return None

        header_rows = table.find_all("tr", class_="headerRow")
        if len(header_rows) < 2:
            return None

        header_cells = header_rows[1].find_all("td")
        headers = [
            " ".join(th.get_text(separator=" ", strip=True).split())
            for th in header_cells
        ]

        seen = {}
        new_headers = []
        for h in headers:
            if h in seen:
                seen[h] += 1
                new_headers.append(f"{h}_{seen[h]}")
            else:
                seen[h] = 0
                new_headers.append(h)

        def process_tr(tr):
            try:
                return [
                    " ".join(td.get_text(separator=" ", strip=True).split())
                    for td in tr.find_all("td")
                ]
            except Exception:
                return None

        content_rows = table.find_all("tr", class_="contentRow")
        if not content_rows:
            return None

        data = []
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            results = list(executor.map(process_tr, content_rows))

        data = [r for r in results if r]

        return pd.DataFrame(data, columns=new_headers) if data else None