import json
import re
import hashlib
import shutil
import threading
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
NOVELS_DIR = DATA_DIR / "novels"
INDEX_FILE = DATA_DIR / "library.json"
_LIBRARY_LOCK = threading.RLock()


def _safe_name(value):
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value).strip(" ._")
    return (value or "novel")[:80]


def _read_json(path, fallback):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return fallback


def _write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


_READER_UI_LINES = {
    "inter", "source sans", "segoe kullanıcı arayüzü", "segoe ui", "roboto",
    "nunito sans", "verdana", "tahoma", "arial", "palatino linotipi",
    "palatino linotype", "bildirim metni", "message text", "times new roman",
    "patrick el", "çevir", "translate", "orijinal (ingilizce)", "original (english)",
    "ispanyolca", "portekizce", "fransızca", "almanca", "italyanca", "rusça",
    "lehçe", "hollandaca", "türkçe", "arapça", "hintçe", "endonezya dili",
    "vietnamca", "filipinli", "tay dili", "japonca", "korece",
    "çince (basitleştirilmiş)", "çince (geleneksel)", "font size", "font family",
    "line height", "önceki", "sonraki", "previous", "next",
}


def _clean_reader_text(text):
    """Hide runs of reader-toolbar strings in legacy files without deleting story words."""
    lines = text.splitlines()
    normalized = [re.sub(r"\s+", " ", line.strip()).casefold().strip(" :：-—") for line in lines]
    remove = set()
    i = 0
    while i < len(lines):
        if normalized[i] not in _READER_UI_LINES:
            i += 1
            continue
        j = i
        while j < len(lines) and (normalized[j] in _READER_UI_LINES or not normalized[j]):
            j += 1
        # Menus show multiple consecutive options. A lone word such as "Türkçe"
        # may be legitimate prose or a translation test and is kept.
        labels = sum(1 for k in range(i, j) if normalized[k] in _READER_UI_LINES)
        if labels >= 3:
            remove.update(range(i, j))
        i = max(j, i + 1)
    cleaned = [line for idx, line in enumerate(lines) if idx not in remove]
    result = "\n".join(cleaned)
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip()


def _info_page_text(metadata):
    genres = metadata.get("genres") or []
    if isinstance(genres, str):
        genres = [genres]
    return "\n".join([
        f"Roman: {metadata.get('title') or 'Bilinmiyor'}",
        f"Site: {metadata.get('site_name') or metadata.get('site_id') or 'Bilinmiyor'}",
        f"Yazar: {metadata.get('author') or 'Bilinmiyor'}",
        f"Türler: {', '.join(str(x) for x in genres) if genres else 'Bilinmiyor'}",
        f"Sitedeki bölüm sayısı: {metadata.get('site_chapter_count', 'Bilinmiyor')}",
        f"Kaynak adresi: {metadata.get('source_url') or ''}",
        f"Kapak adresi: {metadata.get('cover_url') or ''}",
        "", "KONU ÖZETİ", metadata.get('description') or 'Özet bilgisi bulunamadı.'
    ])


class Library:
    def __init__(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        NOVELS_DIR.mkdir(parents=True, exist_ok=True)
        if not INDEX_FILE.exists():
            _write_json(INDEX_FILE, {"version": 1, "novels": []})

    def list_novels(self):
        return _read_json(INDEX_FILE, {"version": 1, "novels": []}).get("novels", [])

    def novel_dir(self, metadata):
        folder = f"{_safe_name(metadata.get('site_id','site'))}_{metadata.get('novel_id','unknown')}"
        return NOVELS_DIR / folder

    def add_or_update_novel(self, metadata, chapters):
        with _LIBRARY_LOCK:
            folder = self.novel_dir(metadata)
            folder.mkdir(parents=True, exist_ok=True)
            old_metadata = _read_json(folder / "metadata.json", {})
            if old_metadata.get("site_chapter_count_manual"):
                metadata["site_chapter_count"] = old_metadata.get("site_chapter_count", metadata.get("site_chapter_count"))
                metadata["site_chapter_count_manual"] = True
            if old_metadata.get("publication_status_manual"):
                metadata["publication_status"] = old_metadata.get("publication_status", metadata.get("publication_status", "ongoing"))
                metadata["publication_status_manual"] = True
                metadata["publication_status_text"] = old_metadata.get("publication_status_text", metadata.get("publication_status_text", ""))
            old_chapters = _read_json(folder / "chapters.json", {"chapters": []}).get("chapters", [])
            old_by_url = {x.get("source_url"): x for x in old_chapters if x.get("source_url")}
            info_text = _info_page_text(metadata)
            info_path = folder / "info.txt"
            old_info_text = info_path.read_text(encoding="utf-8") if info_path.exists() else None
            old_info = next((x for x in old_chapters if x.get("is_info_page")), {})
            info_chapter = {
                "chapter_id": "chapter_0_info",
                "chapter_number": 0,
                "title": "Chapter 0 — Roman Bilgileri",
                "resolved_title": "Chapter 0 — Roman Bilgileri",
                "source_url": metadata.get("source_url") or metadata.get("source_page_url") or "info://" + str(metadata.get("novel_id", "novel")),
                "is_info_page": True,
                "downloaded": True,
                "local_file": "info.txt",
            }
            # Preserve the info-page translation only if the source metadata did not change.
            if old_info and old_info_text == info_text:
                for key in ("translated", "translated_file", "translated_at", "translation_status", "translation_error", "translation_attempted_at"):
                    if key in old_info:
                        info_chapter[key] = old_info[key]
            elif old_info and old_info.get("translated_file"):
                try:
                    (folder / old_info["translated_file"]).unlink(missing_ok=True)
                except OSError:
                    pass
            info_path.write_text(info_text, encoding="utf-8")

            merged = [info_chapter]
            for item in chapters:
                old = old_by_url.get(item.get("source_url"), {})
                merged.append({**item, **{k: old[k] for k in ("downloaded", "downloaded_at", "local_file", "resolved_title", "translated", "translated_file", "translated_at", "translation_status", "translation_error", "translation_attempted_at") if k in old}})
            present = {x.get("source_url") for x in merged}
            merged.extend(x for x in old_chapters if not x.get("is_info_page") and x.get("source_url") not in present)
            _write_json(folder / "chapters.json", {"chapters": merged, "updated_at": datetime.now(timezone.utc).isoformat()})
            metadata["downloaded_chapter_count"] = sum(1 for x in merged if x.get("downloaded"))
            metadata["translated_chapter_count"] = sum(1 for x in merged if x.get("translated") and x.get("translation_status", "translated") == "translated")
            _write_json(folder / "metadata.json", metadata)
            index = _read_json(INDEX_FILE, {"version": 1, "novels": []})
            summary = {k: metadata.get(k) for k in ("site_id", "site_name", "novel_id", "source_url", "title", "cover_url", "author", "genres", "site_chapter_count", "publication_status", "publication_status_text", "downloaded_chapter_count", "translated_chapter_count")}
            summary["folder"] = folder.name
            entries = [x for x in index.get("novels", []) if not (x.get("site_id") == metadata.get("site_id") and x.get("novel_id") == metadata.get("novel_id"))]
            entries.append(summary)
            index["novels"] = entries
            _write_json(INDEX_FILE, index)
            return folder

    def delete_novel(self, folder_name):
        with _LIBRARY_LOCK:
            """Delete one library entry and its local files, restricted to NOVELS_DIR."""
            folder = (NOVELS_DIR / folder_name).resolve()
            root = NOVELS_DIR.resolve()
            if folder == root or root not in folder.parents:
                raise ValueError("Geçersiz roman klasörü; güvenlik nedeniyle silinmedi.")
            if folder.exists():
                shutil.rmtree(folder)
            index = _read_json(INDEX_FILE, {"version": 1, "novels": []})
            index["novels"] = [item for item in index.get("novels", []) if item.get("folder") != folder.name]
            _write_json(INDEX_FILE, index)


    def get_metadata(self, folder_name):
        return _read_json(NOVELS_DIR / folder_name / "metadata.json", {})

    def update_site_chapter_count(self, folder_name, count):
        """Manually override the site's reported chapter total without touching chapter files."""
        count = int(count)
        if count < 0:
            raise ValueError("Toplam bölüm sayısı negatif olamaz.")
        with _LIBRARY_LOCK:
            folder = NOVELS_DIR / folder_name
            metadata_path = folder / "metadata.json"
            metadata = _read_json(metadata_path, {})
            if not metadata:
                raise FileNotFoundError(f"Roman bilgileri bulunamadı: {folder_name}")
            metadata["site_chapter_count"] = count
            metadata["site_chapter_count_manual"] = True
            _write_json(metadata_path, metadata)
            index = _read_json(INDEX_FILE, {"version": 1, "novels": []})
            for item in index.get("novels", []):
                if item.get("folder") == folder_name:
                    item["site_chapter_count"] = count
                    item["site_chapter_count_manual"] = True
            _write_json(INDEX_FILE, index)
            return metadata

    def update_manual_publication_status(self, folder_name, status):
        """Persist a user's completed/ongoing choice and keep it across metadata refreshes."""
        if status not in ("completed", "ongoing"):
            raise ValueError("Yayın durumu 'completed' veya 'ongoing' olmalı.")
        with _LIBRARY_LOCK:
            folder = NOVELS_DIR / folder_name
            metadata_path = folder / "metadata.json"
            metadata = _read_json(metadata_path, {})
            if not metadata:
                raise FileNotFoundError(f"Roman bilgileri bulunamadı: {folder_name}")
            metadata["publication_status"] = status
            metadata["publication_status_manual"] = True
            metadata["publication_status_text"] = "Completed (manual)" if status == "completed" else "Ongoing (manual)"
            _write_json(metadata_path, metadata)
            index = _read_json(INDEX_FILE, {"version": 1, "novels": []})
            for item in index.get("novels", []):
                if item.get("folder") == folder_name:
                    item["publication_status"] = status
                    item["publication_status_manual"] = True
                    item["publication_status_text"] = metadata["publication_status_text"]
            _write_json(INDEX_FILE, index)
            return metadata

    def get_chapters(self, folder_name):
        """Load chapter records, migrate older formats, and recover local chapter files."""
        folder = NOVELS_DIR / folder_name
        chapters_path = folder / "chapters.json"
        raw = _read_json(chapters_path, {"chapters": []})
        if isinstance(raw, list):
            chapters = [x for x in raw if isinstance(x, dict)]
        elif isinstance(raw, dict):
            records = raw.get("chapters", raw.get("items", raw.get("sections", [])))
            chapters = [x for x in records if isinstance(x, dict)] if isinstance(records, list) else []
        else:
            chapters = []
        if not folder.exists():
            return chapters

        # Some older builds wrote chapter text before the matching record. Recover
        # only genuinely orphaned files. Checking chapter IDs alone is insufficient:
        # legacy records may use a different ID while already pointing at this file,
        # which made every saved chapter appear twice (one URL record + one local:// row).
        known_ids = {str(x.get("chapter_id") or "") for x in chapters}
        known_local_names = {
            Path(str(x.get("local_file") or "")).name
            for x in chapters if x.get("local_file")
        }
        # Also recognize IDs generated from the canonical source URL in older builds.
        # If the record lost its local_file field, reconnect it to the matching saved file.
        source_dir = folder / "chapters"
        for record in chapters:
            source = str(record.get("source_url") or "")
            if source and not source.startswith(("local://", "info://")):
                generated_id = hashlib.sha256(source.encode("utf-8")).hexdigest()[:16]
                known_ids.add(generated_id)
                generated_file = source_dir / f"{generated_id}.txt"
                if not record.get("local_file") and generated_file.is_file():
                    record["local_file"] = f"chapters/{generated_file.name}"
                    record["downloaded"] = True
                    known_local_names.add(generated_file.name)
        source_dir = folder / "chapters"
        if source_dir.is_dir():
            for file_path in sorted(source_dir.glob("*.txt")):
                chapter_id = file_path.stem
                if chapter_id in known_ids or file_path.name in known_local_names:
                    continue
                translated_path = folder / "translated" / file_path.name
                chapters.append({
                    "chapter_id": chapter_id,
                    "chapter_number": len(chapters) + 1,
                    "title": f"Bölüm {len(chapters) + 1}",
                    "resolved_title": f"Bölüm {len(chapters) + 1}",
                    "source_url": "local://" + folder_name + "/" + chapter_id,
                    "downloaded": True,
                    "local_file": f"chapters/{file_path.name}",
                    "translated": translated_path.exists(),
                    "translated_file": f"translated/{file_path.name}" if translated_path.exists() else None,
                })
                known_ids.add(chapter_id)
                known_local_names.add(file_path.name)

        # Merge duplicate legacy rows by stable ID or local file. Prefer the record
        # with a real web URL, while retaining downloaded/translation state from both.
        deduped = []
        key_to_index = {}
        for chapter in chapters:
            if not isinstance(chapter, dict):
                continue
            source = str(chapter.get("source_url") or "")
            local_file = str(chapter.get("local_file") or "")
            chapter_id = str(chapter.get("chapter_id") or "")
            keys = [f"id:{chapter_id}" if chapter_id else ""]
            if local_file:
                keys.append(f"file:{local_file}")
            if source and not source.startswith(("local://", "info://")):
                keys.append(f"url:{source.rstrip('/')}" )
            match_index = next((key_to_index[k] for k in keys if k and k in key_to_index), None)
            if match_index is None:
                idx = len(deduped)
                deduped.append(dict(chapter))
                for key in keys:
                    if key:
                        key_to_index[key] = idx
                continue
            old = deduped[match_index]
            # Real source URLs always win over synthetic local:// URLs.
            old_source = str(old.get("source_url") or "")
            if old_source.startswith(("local://", "info://")) and source and not source.startswith(("local://", "info://")):
                merged = {**old, **chapter}
            else:
                merged = {**chapter, **old}
            for flag in ("downloaded", "translated"):
                merged[flag] = bool(old.get(flag) or chapter.get(flag))
            for field in ("local_file", "translated_file", "downloaded_at", "translated_at", "translation_status", "translation_error"):
                if not merged.get(field):
                    merged[field] = old.get(field) or chapter.get(field)
            deduped[match_index] = merged
            for key in keys:
                if key:
                    key_to_index[key] = match_index
        chapters = deduped

        metadata = self.get_metadata(folder_name)
        has_info = any(x.get("is_info_page") or x.get("chapter_number") == 0 for x in chapters)
        if not has_info:
            info_path = folder / "info.txt"
            if not info_path.exists():
                info_path.write_text(_info_page_text(metadata), encoding="utf-8")
            info_chapter = {
                "chapter_id": "chapter_0_info",
                "chapter_number": 0,
                "title": "Chapter 0 — Roman Bilgileri",
                "resolved_title": "Chapter 0 — Roman Bilgileri",
                "source_url": metadata.get("source_url") or "info://" + folder_name,
                "is_info_page": True,
                "downloaded": True,
                "local_file": "info.txt",
            }
            chapters.insert(0, info_chapter)

        # Restore translation flags from actual files if an older metadata write lost the flag.
        for chapter in chapters:
            translated_file = chapter.get("translated_file")
            if translated_file and (folder / translated_file).is_file():
                chapter["translated"] = True
            elif chapter.get("chapter_id"):
                candidate = folder / "translated" / f"{chapter['chapter_id']}.txt"
                if candidate.is_file():
                    chapter["translated"] = True
                    chapter["translated_file"] = f"translated/{candidate.name}"

        with _LIBRARY_LOCK:
            # Persist migrations/deduplication and repair stale summary counts.
            if not isinstance(raw, dict) or raw.get("chapters") != chapters:
                _write_json(chapters_path, {"chapters": chapters, "updated_at": datetime.now(timezone.utc).isoformat()})
            metadata["downloaded_chapter_count"] = sum(1 for x in chapters if x.get("downloaded"))
            metadata["translated_chapter_count"] = sum(
                1 for x in chapters
                if x.get("translated") and x.get("translation_status", "translated") == "translated"
            )
            _write_json(folder / "metadata.json", metadata)
            index = _read_json(INDEX_FILE, {"version": 1, "novels": []})
            for item in index.get("novels", []):
                if item.get("folder") == folder_name:
                    item["downloaded_chapter_count"] = metadata["downloaded_chapter_count"]
                    item["translated_chapter_count"] = metadata["translated_chapter_count"]
            _write_json(INDEX_FILE, index)
        return chapters

    def save_reading_progress(self, folder_name, chapter):
        """Persist the last chapter opened so double-click can resume reading."""
        with _LIBRARY_LOCK:
            metadata = self.get_metadata(folder_name)
            metadata["last_read_chapter_id"] = chapter.get("chapter_id")
            metadata["last_read_source_url"] = chapter.get("source_url")
            metadata["last_read_title"] = chapter.get("resolved_title") or chapter.get("title")
            metadata["last_read_at"] = datetime.now(timezone.utc).isoformat()
            _write_json(NOVELS_DIR / folder_name / "metadata.json", metadata)

    def save_chapter(self, folder_name, chapter, chapter_data):
        with _LIBRARY_LOCK:
            folder = NOVELS_DIR / folder_name
            chapter_dir = folder / "chapters"
            chapter_dir.mkdir(parents=True, exist_ok=True)
            chapter_id = chapter.get("chapter_id") or "chapter"
            local_file = f"chapters/{chapter_id}.txt"
            (folder / local_file).write_text(chapter_data["content"], encoding="utf-8")
            chapter["downloaded"] = True
            chapter["downloaded_at"] = chapter_data.get("downloaded_at")
            chapter["local_file"] = local_file
            chapter["resolved_title"] = chapter_data.get("title", chapter.get("title", ""))
            all_chapters = self.get_chapters(folder_name)
            replaced = False
            for i, item in enumerate(all_chapters):
                if item.get("source_url") == chapter.get("source_url"):
                    all_chapters[i] = {**item, **chapter}
                    replaced = True
                    break
            if not replaced:
                # A sequential Next crawl may discover chapters beyond the links
                # found on the homepage. Persist them immediately and in order.
                if "source_order" not in chapter:
                    existing_orders = [int(x.get("source_order", -1)) for x in all_chapters
                                       if not x.get("is_info_page")]
                    chapter["source_order"] = max(existing_orders, default=-1) + 1
                all_chapters.append(chapter)
            _write_json(folder / "chapters.json", {"chapters": all_chapters, "updated_at": datetime.now(timezone.utc).isoformat()})
            metadata = self.get_metadata(folder_name)
            metadata["downloaded_chapter_count"] = sum(1 for x in all_chapters if x.get("downloaded"))
            metadata["translated_chapter_count"] = sum(1 for x in all_chapters if x.get("translated") and x.get("translation_status", "translated") == "translated")
            _write_json(folder / "metadata.json", metadata)
            index = _read_json(INDEX_FILE, {"version": 1, "novels": []})
            for item in index.get("novels", []):
                if item.get("folder") == folder_name:
                    item["downloaded_chapter_count"] = metadata["downloaded_chapter_count"]
                    item["translated_chapter_count"] = metadata["translated_chapter_count"]
            _write_json(INDEX_FILE, index)
            return folder / local_file



    def save_translation(self, folder_name, chapter, translated_text, status="translated"):
        """Save translation text and distinguish real translations from fallback copies."""
        with _LIBRARY_LOCK:
            folder = NOVELS_DIR / folder_name
            translated_dir = folder / "translated"
            translated_dir.mkdir(parents=True, exist_ok=True)
            chapter_id = chapter.get("chapter_id") or "chapter"
            local_file = f"translated/{chapter_id}.txt"
            (folder / local_file).write_text(translated_text, encoding="utf-8")
            all_chapters = self.get_chapters(folder_name)
            for i, item in enumerate(all_chapters):
                if item.get("source_url") == chapter.get("source_url"):
                    # Keep fallback text readable in the Reader, but do not count it
                    # as a successful translation. The dedicated retry action can find it.
                    item["translated"] = status in ("translated", "fallback_original")
                    item["translation_status"] = status
                    item["translated_file"] = local_file
                    item["translated_at"] = datetime.now(timezone.utc).isoformat()
                    all_chapters[i] = item
                    break
            _write_json(folder / "chapters.json", {"chapters": all_chapters, "updated_at": datetime.now(timezone.utc).isoformat()})
            metadata = self.get_metadata(folder_name)
            metadata["translated_chapter_count"] = sum(1 for x in all_chapters if x.get("translated") and x.get("translation_status", "translated") == "translated")
            metadata["downloaded_chapter_count"] = sum(1 for x in all_chapters if x.get("downloaded"))
            _write_json(folder / "metadata.json", metadata)
            index = _read_json(INDEX_FILE, {"version": 1, "novels": []})
            for item in index.get("novels", []):
                if item.get("folder") == folder_name:
                    item["translated_chapter_count"] = metadata["translated_chapter_count"]
                    item["downloaded_chapter_count"] = metadata["downloaded_chapter_count"]
            _write_json(INDEX_FILE, index)
            return folder / local_file


    def mark_translation_failure(self, folder_name, chapter, error=""):
        """Persist a failed translation attempt without advancing the success count."""
        with _LIBRARY_LOCK:
            folder = NOVELS_DIR / folder_name
            all_chapters = self.get_chapters(folder_name)
            for item in all_chapters:
                if item.get("source_url") == chapter.get("source_url"):
                    item["translated"] = False
                    item["translation_status"] = "failed"
                    item["translation_error"] = str(error)[:1000]
                    item["translation_attempted_at"] = datetime.now(timezone.utc).isoformat()
                    break
            _write_json(folder / "chapters.json", {"chapters": all_chapters, "updated_at": datetime.now(timezone.utc).isoformat()})
            metadata = self.get_metadata(folder_name)
            metadata["translated_chapter_count"] = sum(1 for x in all_chapters if x.get("translated") and x.get("translation_status", "translated") == "translated")
            metadata["downloaded_chapter_count"] = sum(1 for x in all_chapters if x.get("downloaded"))
            _write_json(folder / "metadata.json", metadata)
            index = _read_json(INDEX_FILE, {"version": 1, "novels": []})
            for item in index.get("novels", []):
                if item.get("folder") == folder_name:
                    item["translated_chapter_count"] = metadata["translated_chapter_count"]
                    item["downloaded_chapter_count"] = metadata["downloaded_chapter_count"]
            _write_json(INDEX_FILE, index)

    def read_translation(self, folder_name, chapter):
        local_file = chapter.get("translated_file")
        if not local_file and chapter.get("chapter_id"):
            candidate = NOVELS_DIR / folder_name / "translated" / f"{chapter['chapter_id']}.txt"
            if candidate.is_file():
                local_file = f"translated/{candidate.name}"
        if not local_file:
            return "Bu bölüm henüz çevrilmedi."
        try:
            return _clean_reader_text((NOVELS_DIR / folder_name / local_file).read_text(encoding="utf-8"))
        except OSError:
            return "Çeviri dosyası bulunamadı. Çeviriyi yeniden çalıştırın."

    def read_chapter(self, folder_name, chapter):
        local_file = chapter.get("local_file")
        if not local_file:
            return "Bu bölüm henüz indirilmedi."
        path = NOVELS_DIR / folder_name / local_file
        try:
            return _clean_reader_text(path.read_text(encoding="utf-8"))
        except OSError:
            return "Bölüm dosyası bulunamadı. İndirme işlemini yeniden çalıştırın."
