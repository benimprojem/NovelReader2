from .scraper import SiteScraper, stable_id, canonical_url
from .library import Library


def download_chapters(site_config, folder_name, chapter_items, progress_callback=None, stop_event=None, limit=None):
    """Download sequentially from the first URL / latest downloaded URL via each page's Next.

    chapter_items is the saved chapter list (not a pre-truncated batch). `limit` is
    the number of *new* chapters to download this run; 0/None means follow Next
    until the site chain ends. The homepage chapter count is informational only.
    """
    scraper = SiteScraper(site_config)
    library = Library()
    metadata = library.get_metadata(folder_name)
    base_url = metadata.get("source_url") or ""
    def is_downloadable_chapter(record):
        # Older library versions may have saved the Chapter 0/info record with
        # the novel homepage as source_url but without the is_info_page flag.
        # Never use that record as the resume point: it has no chapter Next link.
        if record.get("is_info_page") or record.get("chapter_number") == 0:
            return False
        url = canonical_url(record.get("source_url", ""))
        if not url or url == canonical_url(base_url):
            return False
        if url.startswith(("local://", "info://")):
            return False
        return True

    all_records = [x for x in library.get_chapters(folder_name) if is_downloadable_chapter(x)]
    # Include records passed by callers in case a caller's snapshot is newer.
    by_url = {canonical_url(x.get("source_url", "")): x for x in all_records if x.get("source_url")}
    for item in chapter_items or []:
        if not is_downloadable_chapter(item):
            continue
        url = canonical_url(item.get("source_url", ""))
        if url and url not in by_url:
            by_url[url] = item
            all_records.append(item)
    all_records.sort(key=lambda x: int(x.get("source_order", 10**9)))
    downloaded = {canonical_url(x.get("source_url", "")) for x in all_records
                  if x.get("downloaded") and x.get("source_url")}
    ordered_downloaded = [x for x in all_records if x.get("downloaded") and x.get("source_url")]
    errors = []
    new_count = 0
    seen = set()
    total_label = limit if limit and limit > 0 else (metadata.get("site_chapter_count") or "?")

    # Resume from the last successfully downloaded chapter's Next link. If no
    # chapter has been downloaded yet, begin at the user's explicitly supplied URL.
    if ordered_downloaded:
        last = ordered_downloaded[-1]
        current_url = canonical_url(last.get("source_url", ""))
        try:
            current_url = scraper.fetch_next_chapter_url(current_url, base_url)
        except Exception as exc:
            errors.append({"url": last.get("source_url"), "error": f"Kaldığı yerin Next bağlantısı okunamadı: {exc}"})
            return errors
        if not current_url:
            # Older saved scans may already contain the next item. Use that
            # known sequential item as a safe compatibility fallback.
            try:
                idx = next(i for i, x in enumerate(all_records) if canonical_url(x.get("source_url", "")) == canonical_url(last.get("source_url", "")))
                for candidate in all_records[idx + 1:]:
                    candidate_url = canonical_url(candidate.get("source_url", ""))
                    if candidate_url and candidate_url not in downloaded:
                        current_url = candidate_url
                        break
            except StopIteration:
                pass
            if not current_url:
                if (metadata.get("site_chapter_count") or 0) > len(downloaded):
                    errors.append({"url": last.get("source_url"), "error": "Bu bölüm sayfasında Next bağlantısı bulunamadı. Sitedeki toplam bölüm sayısı daha yüksek; indirme tamamlandı kabul edilmedi."})
                return errors
    else:
        current_url = canonical_url(metadata.get("start_chapter_url") or "")
        if not current_url:
            first = next((x for x in all_records if x.get("source_url")), None)
            current_url = canonical_url(first.get("source_url", "")) if first else ""

    if not current_url:
        return [{"url": base_url, "error": "Başlangıç bölüm adresi bulunamadı. İlk bölüm URL'sini girip roman bilgilerini yenileyin."}]

    safety_cap = 5000 if not limit or limit == 0 else max(limit * 5, limit + 30)
    while current_url and current_url not in seen and new_count < (limit if limit and limit > 0 else safety_cap):
        if stop_event and stop_event.is_set():
            break
        seen.add(current_url)
        existing = by_url.get(current_url)
        if current_url in downloaded:
            # This can happen when an older index already contains a chapter
            # after the resume point. Walk through its Next link without counting it.
            try:
                current_url = scraper.fetch_next_chapter_url(current_url, base_url)
            except Exception as exc:
                errors.append({"url": current_url, "error": f"Sonraki bölüm adresi okunamadı: {exc}"})
                break
            continue
        chapter = dict(existing or {})
        if not chapter:
            chapter = {"chapter_id": stable_id(current_url), "title": "", "source_url": current_url,
                       "source_order": max([int(x.get("source_order", -1)) for x in all_records], default=-1) + 1,
                       "downloaded": False}
        chapter["source_url"] = current_url
        try:
            data = scraper.fetch_chapter(current_url, base_url=base_url)
            data["title"] = scraper._clean_chapter_title(data.get("title", ""), metadata.get("title", ""))
            chapter["title"] = scraper._clean_chapter_title(data.get("title") or chapter.get("title", ""), metadata.get("title", ""))
            library.save_chapter(folder_name, chapter, data)
            by_url[current_url] = chapter
            if current_url not in {canonical_url(x.get("source_url", "")) for x in all_records}:
                all_records.append(chapter)
                all_records.sort(key=lambda x: int(x.get("source_order", 10**9)))
            downloaded.add(current_url)
            new_count += 1
            if progress_callback:
                progress_callback(new_count, limit if limit and limit > 0 else total_label, chapter.get("title") or data.get("title", ""), "İndirildi")
            next_url = canonical_url(data.get("next_url", ""))
            if not next_url:
                reported = metadata.get("site_chapter_count")
                if reported and len(downloaded) < int(reported):
                    errors.append({"url": current_url, "error": f"Next bağlantısı bulunamadı. Ana sayfada {reported} bölüm yazıyor; {len(downloaded)} indirilmiş kayıt var. Zincir tamamlandı sayılmadı."})
                break
            if next_url == current_url or next_url in seen:
                errors.append({"url": current_url, "error": "Next bağlantısı aynı bölüme veya daha önce ziyaret edilen bir bölüme dönüyor; döngü güvenlik nedeniyle durduruldu."})
                break
            current_url = next_url
        except Exception as exc:
            errors.append({"url": current_url, "error": str(exc)})
            break
    if current_url in seen and new_count < (limit if limit and limit > 0 else safety_cap) and not errors:
        errors.append({"url": current_url, "error": "Bölüm zinciri daha önce ziyaret edilen bir adrese döndü; indirme durduruldu."})
    return errors
