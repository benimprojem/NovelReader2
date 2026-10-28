"""Optional Google Translate worker. Stores translated text separately from source chapters."""
import re
import time
from .library import Library, NOVELS_DIR
from .word_filters import apply_word_filters, get_site_config

def _split_text(text, max_chars=3500):
    paragraphs = text.splitlines(keepends=True)
    chunks, current = [], ""
    for paragraph in paragraphs:
        if len(paragraph) > max_chars:
            if current:
                chunks.append(current); current = ""
            pieces = re.split(r"(?<=[.!?])\s+", paragraph)
            for piece in pieces:
                if len(piece) > max_chars:
                    for start in range(0, len(piece), max_chars):
                        chunks.append(piece[start:start+max_chars])
                elif chunks and len(chunks[-1]) + len(piece) + 1 <= max_chars and not chunks[-1].endswith("\n"):
                    chunks[-1] += " " + piece
                else:
                    chunks.append(piece)
            continue
        if current and len(current) + len(paragraph) > max_chars:
            chunks.append(current); current = paragraph
        else:
            current += paragraph
    if current:
        chunks.append(current)
    return [x for x in chunks if x]

def translate_text(text, source="auto", target="tr"):
    try:
        from googletrans import Translator
    except ImportError as exc:
        raise RuntimeError("Çeviri için googletrans paketi kurulu değil. requirements.txt dosyasını yeniden kurun.") from exc
    translator = Translator()
    translated = []
    chunks = _split_text(text)
    for chunk in chunks:
        result = translator.translate(chunk, src=source, dest=target)
        translated.append(result.text)
    return "".join(translated)

def translate_chapters(folder_name, chapters, progress_callback=None, stop_event=None,
                      retry_failed=False, fallback_original=True):
    """Translate selected chapters, retrying transient failures up to three total attempts.

    retry_failed=True is reserved for the explicit "Eksik Bölümleri Çevir" action.
    fallback_original stores source text as a clearly marked readable fallback after
    all three attempts fail; it is not counted as a successful translation.
    """
    library = Library()
    errors = []
    total = len(chapters)
    for index, chapter in enumerate(chapters, 1):
        if stop_event and stop_event.is_set():
            break
        status = chapter.get("translation_status", "translated" if chapter.get("translated") else "")
        if chapter.get("translated") and not (retry_failed and status == "fallback_original"):
            if progress_callback: progress_callback(index, total, chapter.get("title", ""), "Zaten çevrildi")
            continue
        if not chapter.get("downloaded"):
            if progress_callback: progress_callback(index, total, chapter.get("title", ""), "Önce indirilmesi gerekiyor")
            continue
        try:
            source_text = library.read_chapter(folder_name, chapter)
            metadata = library.get_metadata(folder_name)
            site_config = get_site_config(metadata.get("site_id", ""))
            filtered_source = apply_word_filters(source_text, site_config)
            if filtered_source != source_text and chapter.get("local_file"):
                source_path = NOVELS_DIR / folder_name / chapter["local_file"]
                source_path.write_text(filtered_source, encoding="utf-8")
            last_error = None
            for attempt in range(1, 4):
                if stop_event and stop_event.is_set():
                    break
                try:
                    translated_text = translate_text(filtered_source)
                    translated_text = apply_word_filters(translated_text, site_config)
                    library.save_translation(folder_name, chapter, translated_text, status="translated")
                    last_error = None
                    if progress_callback:
                        progress_callback(index, total, chapter.get("title", ""), "Çevrildi" if attempt == 1 else f"Çevrildi ({attempt}. deneme)")
                    break
                except Exception as exc:
                    last_error = exc
                    if progress_callback:
                        progress_callback(index, total, chapter.get("title", ""), f"Hata — {attempt}/3: {exc}")
                    if attempt < 3 and not (stop_event and stop_event.is_set()):
                        # Backoff is interruptible so Stop remains responsive.
                        delay = 2 if attempt == 1 else 5
                        for _ in range(delay * 10):
                            if stop_event and stop_event.is_set():
                                break
                            time.sleep(0.1)
            if stop_event and stop_event.is_set():
                break
            if last_error is not None:
                errors.append({"url": chapter.get("source_url"), "error": str(last_error), "attempts": 3})
                if fallback_original:
                    library.save_translation(folder_name, chapter, filtered_source, status="fallback_original")
                    if progress_callback:
                        progress_callback(index, total, chapter.get("title", ""), "3 deneme başarısız — orijinal yedek kaydedildi; eksik listesinde")
                else:
                    library.mark_translation_failure(folder_name, chapter, str(last_error))
                    if progress_callback:
                        progress_callback(index, total, chapter.get("title", ""), "3 deneme başarısız — eksik olarak işaretlendi")
        except Exception as exc:
            errors.append({"url": chapter.get("source_url"), "error": str(exc)})
            library.mark_translation_failure(folder_name, chapter, str(exc))
            if progress_callback: progress_callback(index, total, chapter.get("title", ""), f"Hata: {exc}")
    return errors
