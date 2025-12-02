import os
import json

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
            
    @classmethod
    def getFilesWithDiscipline(cls, discipline):
        files = ConfigManager.load().get("files", {})
        return [file for file, disc in files.items() if disc == discipline]