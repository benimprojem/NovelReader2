import json
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
SITES_DIR = ROOT / "sites"


def load_sites():
    index = json.loads((SITES_DIR / "sites.json").read_text(encoding="utf-8"))
    result = []
    for entry in index.get("sites", []):
        if not entry.get("enabled", True):
            continue
        config_path = SITES_DIR / entry["config"]
        config = json.loads(config_path.read_text(encoding="utf-8"))
        config["config_path"] = str(config_path)
        result.append(config)
    return result


def identify_site(url, sites=None):
    host = (urlparse(url).hostname or "").lower()
    for site in sites or load_sites():
        domain = site.get("domain", "").lower()
        if host == domain or host.endswith("." + domain):
            return site
    raise ValueError("Bu adres için etkin bir site yapılandırması bulunamadı.")
