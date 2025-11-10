import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import math
from loader import Table
import requests
from rapidfuzz import fuzz

with open("config.json", "r") as f:
    CONFIG = json.load(f)

class ClashReport:
    try:
        with open("cache.json", "r") as f:
            CACHE = json.load(f)
    except FileNotFoundError:
        with open("cache.json", "w") as f:
            json.dump({}, f)
        CACHE = {}

    DISCIPLINES = CONFIG.get("weights", {}).keys() or ["EST", "ELE", "MEC", "HID", "ARQ", "CIV", "VDI", "MOD"]
    REMOTE_HOST = "http://ec2-54-166-164-195.compute-1.amazonaws.com:5000"
    cache_count = 0

    def __init__(self, table: Table):
        self.table = table
        self.CACHE = ClashReport.CACHE

    def generate_report(self, weights=None, max_workers=8):
        report_data = []
        if weights:
            CONFIG["weights"] = weights
        if not hasattr(self, "table") or not hasattr(self.table, "df"):
            raise AttributeError("Objeto 'self.table.df' não encontrado ou inválido.")
        if self.table.df.empty:
            return []

        for _, row in self.table.df.iterrows():
            result = self._process_row(row)
            if result:
                report_data.append(result)

        alpha = 1.5
        min_distance = 0.01

        for item in report_data:
            try:
                d1, d2 = item.get("disciplines", [None, None])
                distance = max(item.get("distance", 0.0), min_distance)
                if not d1 or not d2:
                    continue
                w1 = CONFIG["weights"].get(d1, 1)
                w2 = CONFIG["weights"].get(d2, 1)
                severity = 100 * (math.sqrt(w1 * w2) / 10) * math.exp(-alpha * distance)
                severity = min(max(severity, 0), 100)
                rework_first = severity * (w1 / (w1 + w2))
                rework_second = severity * (w2 / (w1 + w2))
                item.setdefault("automatedAnalysis", {})
                item["automatedAnalysis"].setdefault("first", {})
                item["automatedAnalysis"].setdefault("second", {})
                item["automatedAnalysis"]["first"]["reworkGrade"] = round(rework_first, 2)
                item["automatedAnalysis"]["second"]["reworkGrade"] = round(rework_second, 2)
                item["automatedAnalysis"]["severity"] = round(severity, 2)
            except Exception as e:
                print(f"[ERRO] Falha ao calcular métricas do item: {e}")

        self._save_cache()
        self.report = report_data
        return report_data

    def _process_row(self, row):
        id_ = self._parse_clash_name(row["Clash Name"])
        distance = self._parse_distance(row)
        source_file = self._parse_source_file(row["Path"])
        location = self._parse_location(row["Clash Point"])
        items, disciplines = self._parse_items_and_disciplines(row)
        identifier = self._parse_identifier(items)
        items_info = self._build_items_info(disciplines, row)
        automated_analysis = self._build_automated_analysis()
        return {
            "id": id_,
            "distance": distance,
            "sourceFile": source_file,
            "location": location,
            "identifier": identifier,
            "clashType": "Hard",
            "items": items,
            "disciplines": disciplines,
            "itemsInfo": items_info,
            "automatedAnalysis": automated_analysis
        }

    def _build_items_info(self, disciplines, row):
        def classify(idx: int):
            suffix = f"_{idx}" if idx != 0 else ""
            data = [
                str(disciplines[idx] or ""),
                str(self._parse_category(row, idx) or ""),
                str(self._parse_name(row, idx) or ""),
                str(row.get(f"Path{suffix}", "") or "")
            ]
            single_string = ", ".join(data)
            result = self.search_on_cache(single_string)
            if result:
                return result
            
            try:
                response = requests.post(
                    f"{self.REMOTE_HOST}/modelitems/model/classify",
                    headers={"Content-Type": "application/json"},
                    json=[single_string]
                )
                if response.status_code == 200:
                    result = response.json()[0] if response.json() else None
                    self.CACHE[single_string] = result
                    ClashReport.cache_count += 1
                    if ClashReport.cache_count >= 50:
                        self._save_cache()
                        ClashReport.cache_count = 0
                    return result
                else:
                    return "3E-00-00-00"
            except Exception as e:
                print(f"[WARN] Falha na requisição: {e}")
                return "3E-00-00-00"

        def build_item(discipline, idx: int = 0):
            return {
                "discipline": discipline,
                "category": self._parse_category(row, idx),
                "norma_bim": classify(idx),
                "name": self._parse_name(row, idx),
                "volume": self._parse_volume(row, idx),
                "surface_area": "",
                "weight_kg": "",
                "nearby_items": [],
                "quadrants": [self._parse_quadrant(row, idx)]
            }

        return {
            "first": build_item(disciplines[0], 0),
            "second": build_item(disciplines[1], 1)
        }
    
    def search_on_cache(self, string):
        if self.CACHE.get(string, None):
                return self.CACHE[string]
        
        # fuzz
        for key in self.CACHE.keys():
            if fuzz.ratio(key, string) > 80:
                return self.CACHE[key]

        print(f"[INFO] Cache miss: {string[:100]}...")
        return None

    def _save_cache(self):
        try:
            with open("cache.json", "w") as f:
                json.dump(self.CACHE, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[WARN] Falha ao salvar cache: {e}")

    def _parse_distance(self, row):
        return float(row["Distance"])

    def _parse_clash_name(self, clash_name):
        return int(clash_name.strip("Clash"))

    def _parse_source_file(self, path):
        return path.split(">")[1].strip()

    def _parse_location(self, location_raw):
        x_str, y_str, z_str = [s.strip() for s in location_raw.split(",")]
        x = float(x_str.replace("x:", ""))
        y = float(y_str.replace("y:", ""))
        z = float(z_str.replace("z:", ""))
        return [x, y, z]

    def _parse_identifier(self, items):
        if all(isinstance(item, int) for item in items):
            return "ElementID"
        if all(isinstance(item, str) for item in items):
            return "GUID"
        return "Mixed"

    def _parse_items_and_disciplines(self, row):
        def parse_id(value):
            value = value.replace(" ", "").strip().replace("ElementID:", "").strip()
            try:
                return int(value)
            except ValueError:
                return value

        id_1 = parse_id(row["Item ID"])
        id_2 = parse_id(row["Item ID_1"])
        items = [id_1, id_2]
        discipline_1 = self._extract_discipline(row["Path"])
        discipline_2 = self._extract_discipline(row["Path_1"])
        disciplines = [discipline_1, discipline_2]
        return items, disciplines

    def _extract_discipline(self, path):
        self.DISCIPLINES = sorted(self.DISCIPLINES, key=len)
        for discipline in self.DISCIPLINES:
            for pathItem in path.split(">"):
                if discipline in pathItem or pathItem == discipline:
                    return discipline
            
        return None

    def _parse_quadrant(self, row, idx: int):
        return row["GVC Quadrante"] if idx == 0 else row.get(f"GVC Quadrante_{idx}", "")

    def _parse_volume(self, row, idx: int):
        return row["Element Volume"] if idx == 0 else row.get(f"Element Volume_{idx}", 0)

    def _parse_name(self, row, idx: int):
        return row["Item Name"] if idx == 0 else row.get(f"Item Name_{idx}", "")

    def _parse_category(self, row, idx: int):
        return row["Element Category"] if idx == 0 else row.get(f"Element Category_{idx}", "")

    def _build_automated_analysis(self):
        return {"first": {"reworkGrade": 0.0}, "second": {"reworkGrade": 0.0}, "severity": 0.0, "reworkCost": "0R$"}

    def flatten_report(self):
        if not hasattr(self, "report") or not self.report:
            raise ValueError("Nenhum relatório encontrado. Execute generate_report() primeiro.")
        flattened_rows = []
        for clash in self.report:
            first_item = clash.get("itemsInfo", {}).get("first", {})
            second_item = clash.get("itemsInfo", {}).get("second", {})
            analysis_info = clash.get("automatedAnalysis", {})
            flattened_rows.append({
                "id": clash.get("id"),
                "distance": clash.get("distance"),
                "sourceFile": clash.get("sourceFile"),
                "identifier": clash.get("identifier"),
                "clashType": clash.get("clashType"),
                "severity": analysis_info.get("severity"),
                "reworkCost": analysis_info.get("reworkCost", ""),
                "discipline_1": first_item.get("discipline"),
                "category_1": first_item.get("category"),
                "norma_bim_1": first_item.get("norma_bim"),
                "name_1": first_item.get("name"),
                "volume_1": first_item.get("volume"),
                "surface_area_1": first_item.get("surface_area"),
                "weight_kg_1": first_item.get("weight_kg"),
                "nearby_items_1": ", ".join(map(str, first_item.get("nearby_items", []))),
                "quadrants_1": ", ".join(map(str, first_item.get("quadrants", []))),
                "reworkGrade_1": analysis_info.get("first", {}).get("reworkGrade"),
                "discipline_2": second_item.get("discipline"),
                "category_2": second_item.get("category"),
                "norma_bim_2": second_item.get("norma_bim"),
                "name_2": second_item.get("name"),
                "volume_2": second_item.get("volume"),
                "surface_area_2": second_item.get("surface_area"),
                "weight_kg_2": second_item.get("weight_kg"),
                "nearby_items_2": ", ".join(map(str, second_item.get("nearby_items", []))),
                "quadrants_2": ", ".join(map(str, second_item.get("quadrants", []))),
                "reworkGrade_2": analysis_info.get("second", {}).get("reworkGrade")
            })
        return pd.DataFrame(flattened_rows)
