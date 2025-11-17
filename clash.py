import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import math
from loader import Table
import requests
from rapidfuzz import fuzz

# ============================
# Load CONFIG
# ============================
try:
    with open("config.json", "r", encoding="utf-8") as f:
        CONFIG = json.load(f)
except Exception:
    CONFIG = {
        "weights": {
            "EST": 5.0,
            "ELE": 10.0,
            "MEC": 8.0,
            "HID": 6.0,
            "ARQ": 4.0,
            "CIV": 6.0,
            "VDI": 5.0,
            "MOD": 3.0
        },
        "files": {}
    }
    with open("config.json", "w", encoding="utf-8") as f:
        json.dump(CONFIG, f, ensure_ascii=False, indent=2)


# =====================================================================
#                          CLASS CLASH REPORT
# =====================================================================

class ClashReport:

    # --------------------------------
    # Load CACHE or create one
    # --------------------------------
    try:
        with open("cache.json", "r", encoding="utf-8", errors="ignore") as f:
            CACHE = json.load(f)
    except Exception:
        CACHE = {}
        with open("cache.json", "w", encoding="utf-8") as f:
            json.dump(CACHE, f, ensure_ascii=False, indent=2)

    DISCIPLINES = CONFIG.get("weights", {}).keys() or ["EST", "ELE", "MEC", "HID", "ARQ", "CIV", "VDI", "MOD"]
    REMOTE_HOST = "http://ec2-54-166-164-195.compute-1.amazonaws.com:5000"

    HAS_OWNER_GUID = False
    HAS_DEFAULT_ID = False
    cache_count = 0

    # =====================================================================
    # Constructor
    # =====================================================================
    def __init__(self, table: Table):
        self.table = table
        self.CACHE = ClashReport.CACHE
        self._has_owner_guid()

    # =====================================================================
    # Detect if DF contains owner GUID
    # =====================================================================
    def _has_owner_guid(self):
        df_cols = set(self.table.df.columns)

        if "Item ID" in df_cols:
            ClashReport.HAS_DEFAULT_ID = True

        if "GVC GUID" in df_cols:
            ClashReport.HAS_OWNER_GUID = True

    # =====================================================================
    # MAIN REPORT GENERATOR
    # C = allow config + weights combination
    # =====================================================================
    def generate_report(self, config=None, weights=None, max_workers=8):

        global CONFIG

        # 1 — config inteiro substitui o CONFIG global
        if config is not None:
            CONFIG = config

        # 2 — weights sobrescrevem apenas o bloco de pesos do config
        if weights is not None:
            if "weights" not in CONFIG:
                CONFIG["weights"] = {}
            CONFIG["weights"].update(weights)

        # --------------------------------
        # Validações básicas
        # --------------------------------
        if not hasattr(self, "table") or not hasattr(self.table, "df"):
            raise AttributeError("Objeto 'self.table.df' não encontrado.")

        if self.table.df.empty:
            return []

        # --------------------------------
        # Process row by row
        # --------------------------------
        report_data = []
        for _, row in self.table.df.iterrows():
            try:
                result = self._process_row(row)
                if result:
                    report_data.append(result)
            except Exception:
                continue

        # --------------------------------
        # Automated SEVERITY calculation
        # --------------------------------
        alpha = 1.5
        min_distance = 0.01

        for item in report_data:
            try:
                d1, d2 = item.get("disciplines", [None, None])
                distance = max(float(item.get("distance") or 0), min_distance)

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

            except Exception:
                continue

        self._save_cache()
        self.report = report_data
        return report_data

    # =====================================================================
    # Process a single row
    # =====================================================================
    def _process_row(self, row):
        id_ = self._parse_clash_name(row.get("Clash Name", "0"))
        distance = self._parse_distance(row)
        source_file = self._parse_source_file(row.get("Path", ""))
        location = self._parse_location(row.get("Clash Point", "x:0,y:0,z:0"))
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
            "guids": items,
            "disciplines": disciplines,
            "itemsInfo": items_info,
            "automatedAnalysis": automated_analysis
        }

    # =====================================================================
    # BUILD ITEMS INFO
    # =====================================================================
    def _build_items_info(self, disciplines, row):

        def classify(idx):
            suffix = f"_{idx}" if idx != 0 else ""
            data = [
                str(disciplines[idx] or ""),
                str(self._parse_category(row, idx)),
                str(self._parse_name(row, idx)),
                str(row.get(f"Path{suffix}", ""))
            ]

            s = ", ".join(data)

            cached = self.search_on_cache(s)
            if cached:
                return cached

            try:
                response = requests.post(
                    f"{self.REMOTE_HOST}/modelitems/model/classify",
                    headers={"Content-Type": "application/json"},
                    json=[s]
                )
                if response.status_code == 200:
                    result = response.json()[0] if response.json() else None
                    self.CACHE[s] = result
                    ClashReport.cache_count += 1
                    if ClashReport.cache_count >= 50:
                        self._save_cache()
                        ClashReport.cache_count = 0
                    return result
            except Exception:
                pass

            return "3E-00-00-00"

        def build_item(discipline, idx):
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

    # =====================================================================
    # Cache search with fuzzy matching
    # =====================================================================
    def search_on_cache(self, string):
        if string in self.CACHE:
            return self.CACHE[string]
        for key in self.CACHE.keys():
            try:
                if fuzz.ratio(key, string) > 50:
                    return self.CACHE[key]
            except Exception:
                continue
        return None

    # =====================================================================
    # Save cache
    # =====================================================================
    def _save_cache(self):
        try:
            with open("cache.json", "w", encoding="utf-8") as f:
                json.dump(self.CACHE, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # =====================================================================
    # Parsers
    # =====================================================================
    def _parse_distance(self, row):
        for name in ["Distance (m)", "Distance (mm)", "Distance"]:
            if name in row and row[name] not in [None, ""]:
                try:
                    return float(row[name])
                except Exception:
                    return 0.0
        return 0.0

    def _parse_clash_name(self, clash_name):
        try:
            return int(str(clash_name).replace("Clash", "").strip())
        except Exception:
            return 0

    def _parse_source_file(self, path):
        try:
            parts = path.split(">")
            return parts[1].strip() if len(parts) > 1 else ""
        except Exception:
            return ""

    def _parse_location(self, raw):
        try:
            parts = raw.split(",")
            x = float(parts[0].replace("x:", "").strip())
            y = float(parts[1].replace("y:", "").strip())
            z = float(parts[2].replace("z:", "").strip())
            return [x, y, z]
        except Exception:
            return [0.0, 0.0, 0.0]

    def _parse_identifier(self, items):
        if self.HAS_OWNER_GUID:
            return "GVC"
        try:
            if all(isinstance(int(str(i).replace("Element ID : ", "")), int) for i in items):
                return "ElementID"
        except Exception:
            pass
        if all(isinstance(i, str) for i in items):
            return "GUID"
        return "Mixed"

    def _parse_items_and_disciplines(self, row):

        def parse_id(value):
            if value is None:
                return ""
            s = str(value).replace("ElementID:", "").strip()
            try:
                return int(s)
            except Exception:
                return s

        id1 = parse_id(row.get("Item ID"))
        id2 = parse_id(row.get("Item ID_1"))

        if self.HAS_OWNER_GUID:
            id1 = row.get("GVC GUID") or row.get("GUID") or id1
            id2 = row.get("GVC GUID_1") or row.get("GUID_1") or id2

        items = [id1, id2]

        d1 = self._extract_discipline(row.get("Path", ""))
        d2 = self._extract_discipline(row.get("Path_1", ""))

        return items, [d1, d2]

    def _extract_discipline(self, path):
        files = {k.lower(): v for k, v in CONFIG.get("files", {}).items()}
        parts = [p.strip().lower() for p in path.split(">")]

        candidates = []
        for file_key in files:
            for p in parts:
                if file_key == p:
                    candidates.append(files[file_key])

        return candidates[-1] if candidates else ""

    def _parse_quadrant(self, row, idx):
        name = "GVC Quadrante"
        return row.get(name if idx == 0 else f"{name}_{idx}", "")

    def _parse_volume(self, row, idx):
        base = "Element Volume"
        return row.get(base if idx == 0 else f"{base}_{idx}", "0")

    def _parse_name(self, row, idx):
        base = "Item Name"
        return row.get(base if idx == 0 else f"{base}_{idx}", "")

    def _parse_category(self, row, idx):
        base = "Element Category"
        return row.get(base if idx == 0 else f"{base}_{idx}", "")

    # =====================================================================
    # Automated analysis stub
    # =====================================================================
    def _build_automated_analysis(self):
        return {
            "first": {"reworkGrade": 0.0},
            "second": {"reworkGrade": 0.0},
            "severity": 0.0,
            "reworkCost": "0R$"
        }

    # =====================================================================
    # Flatten report to DataFrame
    # =====================================================================
    def flatten_report(self):
        if not hasattr(self, "report") or not self.report:
            raise ValueError("Nenhum relatório encontrado.")

        rows = []

        for clash in self.report:
            a = clash.get("automatedAnalysis", {})
            i1 = clash["itemsInfo"]["first"]
            i2 = clash["itemsInfo"]["second"]

            rows.append({
                "id": clash.get("id"),
                "location": "; ".join(map(str, clash.get("location", []))),
                "distance": clash.get("distance"),
                "sourceFile": clash.get("sourceFile"),
                "identifier": clash.get("identifier"),
                "clashType": clash.get("clashType"),

                "severity": a.get("severity"),
                "reworkCost": a.get("reworkCost"),

                "discipline_1": i1.get("discipline"),
                "category_1": i1.get("category"),
                "norma_bim_1": i1.get("norma_bim"),
                "name_1": i1.get("name"),
                "GVC GUID_1": clash.get("guids")[0],
                "volume_1": i1.get("volume"),
                "surface_area_1": i1.get("surface_area"),
                "weight_kg_1": i1.get("weight_kg"),
                "nearby_items_1": ", ".join(map(str, i1.get("nearby_items", []))),
                "quadrants_1": ", ".join(map(str, i1.get("quadrants", []))),
                "reworkGrade_1": a.get("first", {}).get("reworkGrade"),

                "discipline_2": i2.get("discipline"),
                "category_2": i2.get("category"),
                "norma_bim_2": i2.get("norma_bim"),
                "name_2": i2.get("name"),
                "GVC GUID_2": clash.get("guids")[1],
                "volume_2": i2.get("volume"),
                "surface_area_2": i2.get("surface_area"),
                "weight_kg_2": i2.get("weight_kg"),
                "nearby_items_2": ", ".join(map(str, i2.get("nearby_items", []))),
                "quadrants_2": ", ".join(map(str, i2.get("quadrants", []))),
                "reworkGrade_2": a.get("second", {}).get("reworkGrade"),
            })

        return pd.DataFrame(rows)
