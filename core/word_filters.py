"""Site-specific literal phrase filters shared by download and translation."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITES_DIR = ROOT / "sites"


def apply_word_filters(text, site_config):
    cleanup = (site_config or {}).get("content_cleanup", {})
    phrases = cleanup.get("remove_phrases", [])
    result = text or ""
    # Literal, case-insensitive substring replacement; user phrases are not regex.
    for phrase in phrases:
        phrase = str(phrase).strip()
        if phrase:
            result = re.sub(re.escape(phrase), "", result, flags=re.IGNORECASE)
    result = re.sub(r"[ \t]{2,}", " ", result)
    result = re.sub(r" *\n *", "\n", result)
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip()


def get_site_config(site_id):
    index_path = SITES_DIR / "sites.json"
    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
        for entry in index.get("sites", []):
            if entry.get("id") == site_id:
                path = SITES_DIR / entry["config"]
                return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return {"id": site_id, "content_cleanup": {"remove_phrases": []}}
