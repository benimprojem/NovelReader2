import unittest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from bs4 import BeautifulSoup
from core.scraper import SiteScraper, stable_id
import core.library as library_module
from core.library import Library


class CoreTests(unittest.TestCase):
    def test_stable_id_is_deterministic(self):
        self.assertEqual(stable_id("https://example.com/chapter-a"), stable_id("https://example.com/chapter-a"))
        self.assertNotEqual(stable_id("https://example.com/chapter-a"), stable_id("https://example.com/chapter-b"))

    def test_reported_total(self):
        self.assertEqual(SiteScraper._reported_total("Sci-fi Novels 194 Chapters"), 194)
        self.assertEqual(SiteScraper._reported_total("The novel 318 Chapters. Related novel 2734 Chapters"), 318)
        self.assertEqual(SiteScraper._clean_chapter_title("The First Superhuman: Rebuilding Civilization from the Moon - Chapter 1: Death Of The Earth", "The First Superhuman: Rebuilding Civilization from the Moon"), "Chapter 1: Death Of The Earth")
        self.assertEqual(SiteScraper._reported_total("Chapters: 1,234"), 1234)
        self.assertEqual(SiteScraper._reported_total("Chapter count: 999+"), 1000)
        self.assertEqual(SiteScraper._reported_total("999+"), 1000)
        self.assertIsNone(SiteScraper._reported_total("No chapter count"))

    def test_start_link_prefers_start_reading_button(self):
        config = {"id": "novelbuddy", "name": "NovelBuddy", "domain": "novelbuddy.me",
                  "chapter_discovery": {"start_fallback": "oldest_visible", "newest_first_assumed": True}}
        scraper = SiteScraper(config)
        soup = BeautifulSoup('''<a href="/book/chapter-new">Chapter 104</a>
            <a href="/book/chapter-one">Start Reading</a>''', "html.parser")
        self.assertEqual(scraper._find_start_chapter_url(soup, "https://novelbuddy.me/book",
                         "https://novelbuddy.me/book", config["chapter_discovery"]),
                         "https://novelbuddy.me/book/chapter-one")

    def test_explicit_start_suffix_overrides_homepage_latest_chapter_links(self):
        config = {"id": "freewebnovel", "name": "FreeWebNovel", "domain": "example.com",
                  "chapter_discovery": {"start_url_suffix": "chapter-1", "start_fallback": "oldest_visible"}}
        scraper = SiteScraper(config)
        soup = BeautifulSoup('''<a href="/novel/book/chapter-398">Chapter 398</a>
            <a href="/novel/book/chapter-397">Chapter 397</a><a href="/novel/book/chapter-1">Start Reading</a>''', "html.parser")
        self.assertEqual(scraper._find_start_chapter_url(soup, "https://example.com/novel/book",
                         "https://example.com/novel/book", config["chapter_discovery"]),
                         "https://example.com/novel/book/chapter-1")

    def test_entered_chapter_url_uses_homepage_metadata_and_starts_chain_at_that_url(self):
        config = {
            "id": "freewebnovel", "name": "FreeWebNovel", "domain": "example.com",
            "selectors": {"title": ["h1"], "status": [".status"], "chapter_title": ["h1"]},
            "chapter_discovery": {"strategy": "next_chain", "start_url_suffix": "chapter-1",
                                  "next_link_text_patterns": [r"^next(?:\s+chapter)?$"]},
        }
        scraper = SiteScraper(config)
        pages = {
            "https://example.com/novel/test": '<h1>Test Novel</h1><div class="status">Ongoing</div><p>5 Chapters</p>',
            "https://example.com/novel/test/chapter-1": '<h1>Chapter 1: Start</h1><a href="/novel/test/chapter-2">Next Chapter</a>',
            "https://example.com/novel/test/chapter-2": '<h1>Chapter 2: Continue</h1>',
        }
        with patch.object(scraper, "fetch", side_effect=lambda url: pages[url]) as fetch_mock:
            metadata, chapters = scraper.fetch_novel("https://example.com/novel/test/chapter-1")
        self.assertEqual(metadata["title"], "Test Novel")
        self.assertEqual(metadata["source_url"], "https://example.com/novel/test")
        self.assertEqual(metadata["start_chapter_url"], "https://example.com/novel/test/chapter-1")
        self.assertEqual(metadata["site_chapter_count"], 5)
        self.assertEqual(metadata["publication_status"], "ongoing")
        self.assertEqual([c["source_url"] for c in chapters], ["https://example.com/novel/test/chapter-1"])
        # Metadata scan fetches the homepage only; chapter pages are followed by download.
        self.assertEqual(fetch_mock.call_count, 1)

    def test_publication_status_does_not_infer_completion_from_missing_next(self):
        scraper = SiteScraper({"id": "test", "name": "Test", "domain": "example.com",
                               "selectors": {"status": [".status"]}})
        soup = BeautifulSoup('<div class="status">Ongoing</div>', "html.parser")
        self.assertEqual(scraper._extract_publication_status(soup), ("ongoing", "Ongoing"))
        completed = BeautifulSoup('<div>Status: Completed</div>', "html.parser")
        self.assertEqual(scraper._extract_publication_status(completed)[0], "completed")

    def test_next_chain_skips_self_link_and_finds_real_next_link(self):
        config = {"id": "freewebnovel", "name": "FreeWebNovel", "domain": "example.com",
                  "chapter_discovery": {"next_link_selectors": [".chapter-next a", "a[rel='next']"],
                    "next_link_text_patterns": [r"^next(?:\s+chapter)?$"]}}
        scraper = SiteScraper(config)
        soup = BeautifulSoup("""<div class='chapter-next'><a href='/novel/book/chapter-14'>Next Chapter</a></div>
          <a rel='next' href='/novel/book/chapter-15'><span>Next</span></a>""", "html.parser")
        self.assertEqual(scraper._find_next_chapter_url(soup, "https://example.com/novel/book/chapter-14",
            "https://example.com/novel/book", config["chapter_discovery"]),
            "https://example.com/novel/book/chapter-15")

    def test_chapter_title_strips_novel_name_even_when_prefix_format_varies(self):
        novel = "The First Superhuman: Rebuilding Civilization from the Moon"
        self.assertEqual(SiteScraper._clean_chapter_title(
            novel + " | Chapter 14: Great Construction Era - Free Web Novel", novel),
            "Chapter 14: Great Construction Era")
        self.assertEqual(SiteScraper._clean_chapter_title(
            novel + " Chapter 15: The Seeds Of Godhood", novel),
            "Chapter 15: The Seeds Of Godhood")

    def test_chapter_title_hides_hash_ids_and_novel_only_heading(self):
        novel = "The First Superhuman: Rebuilding Civilization from the Moon"
        self.assertEqual(SiteScraper._clean_chapter_title("a4c9d88201f3b7e0", novel), "")
        self.assertEqual(SiteScraper._clean_chapter_title(novel, novel), "")
        self.assertEqual(SiteScraper._clean_chapter_title(
            "Chapter 40: The New World | The First Superhuman: Rebuilding Civilization from the Moon", novel),
            "Chapter 40: The New World")


    def test_manual_site_chapter_count_persists_in_metadata_and_index(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with patch.object(library_module, "ROOT", root), patch.object(library_module, "DATA_DIR", root / "data"), patch.object(library_module, "NOVELS_DIR", root / "data" / "novels"), patch.object(library_module, "INDEX_FILE", root / "data" / "library.json"):
                library = Library()
                metadata = {"site_id": "test", "site_name": "Test", "novel_id": "n1", "title": "Novel", "site_chapter_count": 120, "source_url": "https://example.com/novel"}
                folder = library.add_or_update_novel(metadata, [])
                library.update_site_chapter_count(folder.name, 99)
                self.assertEqual(library.get_metadata(folder.name)["site_chapter_count"], 99)
                self.assertTrue(library.get_metadata(folder.name)["site_chapter_count_manual"])
                self.assertEqual(library.list_novels()[0]["site_chapter_count"], 99)
                # Refreshing metadata must not erase the user's manual override.
                updated = dict(metadata)
                updated["site_chapter_count"] = 150
                library.add_or_update_novel(updated, [])
                self.assertEqual(library.get_metadata(folder.name)["site_chapter_count"], 99)

    def test_manual_publication_status_persists_in_metadata_and_index(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with patch.object(library_module, "ROOT", root), patch.object(library_module, "DATA_DIR", root / "data"), patch.object(library_module, "NOVELS_DIR", root / "data" / "novels"), patch.object(library_module, "INDEX_FILE", root / "data" / "library.json"):
                library = Library()
                metadata = {"site_id": "test", "site_name": "Test", "novel_id": "n2", "title": "Novel", "site_chapter_count": 120, "source_url": "https://example.com/novel", "publication_status": "unknown"}
                folder = library.add_or_update_novel(metadata, [])
                library.update_manual_publication_status(folder.name, "completed")
                self.assertEqual(library.get_metadata(folder.name)["publication_status"], "completed")
                self.assertTrue(library.get_metadata(folder.name)["publication_status_manual"])
                self.assertEqual(library.list_novels()[0]["publication_status"], "completed")
                # A later scrape must not override the manual status.
                updated = dict(metadata)
                updated["publication_status"] = "ongoing"
                library.add_or_update_novel(updated, [])
                self.assertEqual(library.get_metadata(folder.name)["publication_status"], "completed")
                library.update_manual_publication_status(folder.name, "ongoing")
                self.assertEqual(library.get_metadata(folder.name)["publication_status"], "ongoing")

    def test_library_does_not_recover_a_second_row_for_an_existing_local_file(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with patch.object(library_module, "ROOT", root), patch.object(library_module, "DATA_DIR", root / "data"), patch.object(library_module, "NOVELS_DIR", root / "data" / "novels"), patch.object(library_module, "INDEX_FILE", root / "data" / "library.json"):
                library = Library()
                folder = root / "data" / "novels" / "test_novel"
                (folder / "chapters").mkdir(parents=True)
                (folder / "metadata.json").write_text('{"title":"Test","source_url":"https://example.com/novel"}', encoding="utf-8")
                (folder / "chapters" / "c1.txt").write_text("chapter text", encoding="utf-8")
                (folder / "chapters.json").write_text(json.dumps({"chapters": [
                    {"chapter_id":"c1", "title":"Chapter 1", "source_url":"https://example.com/novel/chapter-1", "downloaded":True, "local_file":"chapters/c1.txt"},
                    {"chapter_id":"c1", "title":"Chapter 1", "source_url":"local://test_novel/c1", "downloaded":True, "local_file":"chapters/c1.txt"}
                ]}), encoding="utf-8")
                chapters = library.get_chapters("test_novel")
                non_info = [x for x in chapters if not x.get("is_info_page") and x.get("chapter_number") != 0]
                self.assertEqual(len(non_info), 1)
                self.assertEqual(non_info[0]["source_url"], "https://example.com/novel/chapter-1")
                self.assertEqual(non_info[0]["local_file"], "chapters/c1.txt")

    def test_numeric_freewebnovel_next_fallback_uses_exact_next_chapter(self):
        scraper = SiteScraper({"id": "freewebnovel", "name": "FreeWebNovel", "domain": "example.com",
                               "chapter_discovery": {"next_link_selectors": [], "next_link_text_patterns": []}})
        soup = BeautifulSoup("""<a href='/novel/book/chapter-18'>Previous</a>
            <a href='/novel/book/chapter-20'>20</a>
            <a href='/novel/book/chapter-19'>Current</a>""", "html.parser")
        self.assertEqual(scraper._find_next_chapter_url(soup, "https://example.com/novel/book/chapter-19",
            "https://example.com/novel/book", {}), "https://example.com/novel/book/chapter-20")

    def test_download_ignores_legacy_homepage_info_record_when_resuming(self):
        from core import downloader as downloader_module
        records = [
            {"chapter_id": "chapter_0_info", "title": "Chapter 0 — Roman Bilgileri",
             "source_url": "https://example.com/novel", "source_order": -1,
             "chapter_number": 0, "downloaded": True},
        ]
        metadata = {"source_url": "https://example.com/novel",
                    "start_chapter_url": "https://example.com/novel/chapter-1",
                    "title": "Test Novel", "site_chapter_count": 5}
        class FakeLibrary:
            def get_metadata(self, folder): return metadata
            def get_chapters(self, folder): return records
            def save_chapter(self, folder, chapter, data):
                chapter["downloaded"] = True
                chapter["resolved_title"] = data["title"]
                records.append(dict(chapter))
        class FakeScraper:
            def __init__(self, config): pass
            def fetch_chapter(self, url, base_url=None):
                n = int(url.rsplit("chapter-", 1)[1])
                return {"title": f"Chapter {n}", "content": "x" * 200,
                        "source_url": url, "next_url": f"https://example.com/novel/chapter-{n+1}" if n < 5 else ""}
            def fetch_next_chapter_url(self, url, base):
                n = int(url.rsplit("chapter-", 1)[1])
                return f"https://example.com/novel/chapter-{n+1}" if n < 5 else ""
            @staticmethod
            def _clean_chapter_title(title, novel): return title
        with patch.object(downloader_module, "Library", FakeLibrary), patch.object(downloader_module, "SiteScraper", FakeScraper):
            errors = downloader_module.download_chapters({"id": "test"}, "novel", records, limit=2)
        self.assertEqual(errors, [])
        downloaded_urls = [r["source_url"] for r in records if r.get("downloaded") and r.get("chapter_number") != 0]
        self.assertEqual(downloaded_urls, ["https://example.com/novel/chapter-1", "https://example.com/novel/chapter-2"])

    def test_download_follows_next_beyond_homepage_discovered_links_and_resumes(self):
        from core import downloader as downloader_module
        records = [
            {"chapter_id": "c1", "title": "Chapter 1", "source_url": "https://example.com/novel/chapter-1",
             "source_order": 0, "downloaded": True}
        ]
        metadata = {"source_url": "https://example.com/novel", "start_chapter_url": "https://example.com/novel/chapter-1",
                    "title": "Test Novel", "site_chapter_count": 5}
        class FakeLibrary:
            def get_metadata(self, folder): return metadata
            def get_chapters(self, folder): return records
            def save_chapter(self, folder, chapter, data):
                chapter["downloaded"] = True
                chapter["resolved_title"] = data["title"]
                existing = next((i for i, r in enumerate(records) if r.get("source_url") == chapter["source_url"]), None)
                if existing is None: records.append(dict(chapter))
                else: records[existing] = dict(chapter)
        class FakeScraper:
            def __init__(self, config): pass
            def fetch_next_chapter_url(self, url, base):
                n = int(url.rsplit("chapter-", 1)[1])
                return f"https://example.com/novel/chapter-{n+1}" if n < 5 else ""
            def fetch_chapter(self, url, base_url=None):
                n = int(url.rsplit("chapter-", 1)[1])
                return {"title": f"Chapter {n}: Title", "content": "x" * 200,
                        "source_url": url, "next_url": f"https://example.com/novel/chapter-{n+1}" if n < 5 else ""}
            @staticmethod
            def _clean_chapter_title(title, novel): return title
        from core.downloader import download_chapters
        with patch.object(downloader_module, "Library", FakeLibrary), patch.object(downloader_module, "SiteScraper", FakeScraper):
            errors = download_chapters({"id": "test"}, "novel", records, limit=2)
        self.assertEqual(errors, [])
        self.assertEqual([r["source_url"] for r in records if r.get("downloaded")], [
            "https://example.com/novel/chapter-1", "https://example.com/novel/chapter-2", "https://example.com/novel/chapter-3"])

    def test_next_chain_crawls_all_pages_in_order(self):
        config = {"id": "test", "name": "Test", "domain": "example.com",
                  "selectors": {"chapter_title": ["h1", "title"]},
                  "chapter_discovery": {"strategy": "next_chain", "start_fallback": "oldest_visible",
                    "newest_first_assumed": True, "start_link_text_patterns": [r"^start reading$"],
                    "next_link_text_patterns": [r"^next(?:\s+chapter)?$"]}}
        scraper = SiteScraper(config)
        home = BeautifulSoup('<h1>Test Novel</h1><a href="/book/chapter-3">Chapter 3</a><a href="/book/chapter-1">Start Reading</a>', "html.parser")
        pages = {
            "https://example.com/book/chapter-1": '<h1>Chapter One</h1><a href="/book/chapter-2">Next Chapter</a>',
            "https://example.com/book/chapter-2": '<h1>Chapter Two</h1><a href="/book/chapter-3">Next</a>',
            "https://example.com/book/chapter-3": '<h1>Chapter Three</h1>'
        }
        with patch.object(scraper, "fetch", side_effect=lambda url: pages[url]):
            items, warning = scraper._crawl_chapter_chain(home, "https://example.com/book", "https://example.com/book", 3, config["chapter_discovery"])
        self.assertEqual([x["source_url"] for x in items], list(pages.keys()))
        self.assertEqual([x["title"] for x in items], ["Chapter One", "Chapter Two", "Chapter Three"])
        self.assertEqual(warning, "")


    def test_paginated_list_collects_chapters_across_index_pages(self):
        config = {"id": "freewebnovel", "name": "FreeWebNovel", "domain": "example.com",
                  "chapter_discovery": {"strategy": "paginated_list", "list_next_selectors": ["a[rel='next']"],
                    "list_next_text_patterns": [r"^next$"]},
                  "selectors": {"title": ["h1"], "chapter_title": ["h1"]}}
        scraper = SiteScraper(config)
        home = BeautifulSoup("<h1>Test Novel</h1><a href='/novel/book/chapter-1'>Chapter 1: First</a>"
            "<a href='/novel/book/chapter-2'>Chapter 2: Second</a><a rel='next' href='?page=2'>Next</a>", "html.parser")
        page2 = "<h1>Test Novel</h1><a href='/novel/book/chapter-3'>Chapter 3: Third</a>"                 "<a href='/novel/book/chapter-4'>Chapter 4: Fourth</a>"
        with patch.object(scraper, "fetch", return_value=page2):
            items, warning = scraper._crawl_chapter_list_pages(home, "https://example.com/novel/book",
                "https://example.com/novel/book", 4, config["chapter_discovery"])
        self.assertEqual([x["title"] for x in items], ["Chapter 1: First", "Chapter 2: Second", "Chapter 3: Third", "Chapter 4: Fourth"])
        self.assertEqual(warning, "")

    def test_fetch_chapter_removes_reader_settings_but_keeps_story_text(self):
        config = {"id": "test", "name": "Test", "domain": "example.com",
                  "selectors": {"chapter_title": ["h1"], "chapter_content": [".novel-tts-content"]}}
        scraper = SiteScraper(config)
        html = """<html><head><title>Chapter 1</title></head><body>
          <div class="novel-tts-content">
            <div class="reader-settings"><select><option>Inter</option><option>Roboto</option></select>
            <button>Çevir</button><div>Türkçe</div></div>
            <p>The old chain trembled in the darkness as he opened his eyes.</p>
            <p>He had waited a million years for this moment to arrive.</p>
          </div></body></html>"""
        with patch.object(scraper, "fetch", return_value=html):
            result = scraper.fetch_chapter("https://example.com/book/chapter-1")
        self.assertIn("The old chain trembled", result["content"])
        self.assertNotIn("Roboto", result["content"])
        self.assertNotIn("Çevir", result["content"])
        self.assertNotIn("Türkçe", result["content"])

    def test_site_specific_cleanup_removes_ads_and_preserves_story(self):
        config = {
            "id": "test", "name": "Test", "domain": "example.com",
            "selectors": {"chapter_title": ["h1"], "chapter_content": [".story"]},
            "content_cleanup": {
                "remove_selectors": [".sponsor-box"],
                "remove_exact_lines": ["Read more on our app"],
                "remove_text_patterns": [r"^Advertisement:.*$"],
            },
        }
        scraper = SiteScraper(config)
        html = """<html><body><h1>Chapter 1</h1><div class="story">
          <p>The traveler crossed the silent valley and watched the sunrise.</p>
          <div class="sponsor-box">Install our app and get rewards</div>
          <p>Advertisement: visit example sponsors now</p>
          <p>Read more on our app</p>
          <p>He continued toward the distant city, carrying the old letter.</p>
        </div></body></html>"""
        with patch.object(scraper, "fetch", return_value=html):
            result = scraper.fetch_chapter("https://example.com/book/chapter-1")
        self.assertIn("The traveler crossed", result["content"])
        self.assertIn("He continued toward the distant city", result["content"])
        self.assertNotIn("Install our app", result["content"])
        self.assertNotIn("Advertisement:", result["content"])
        self.assertNotIn("Read more on our app", result["content"])

    def test_chapter_content_uses_first_specific_selector_not_longest_wrapper(self):
        config = {"id": "test", "name": "Test", "domain": "example.com",
                  "selectors": {"chapter_title": ["h1"], "chapter_content": [".story", "article"]}}
        scraper = SiteScraper(config)
        html = """<html><body><article><div class="settings">Inter Roboto Türkçe</div>
          <div class="story"><p>The old traveler opened the gate and entered the quiet city.</p>
          <p>He carried a map and searched for the lost tower beyond the river.</p></div>
          <div class="footer">Subscribe to updates and recommendations</div></article></body></html>"""
        with patch.object(scraper, "fetch", return_value=html):
            result = scraper.fetch_chapter("https://example.com/book/chapter-1")
        self.assertNotIn("Subscribe to updates", result["content"])
        self.assertIn("The old traveler opened", result["content"])

    def test_library_adds_translatable_chapter_zero_info_page(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with patch.object(library_module, "ROOT", root), patch.object(library_module, "DATA_DIR", root / "data"), patch.object(library_module, "NOVELS_DIR", root / "data" / "novels"), patch.object(library_module, "INDEX_FILE", root / "data" / "library.json"):
                library = Library()
                metadata = {"site_id": "test", "site_name": "Test", "novel_id": "info-novel", "source_url": "https://example.com/novel", "title": "Info Novel", "author": "Writer", "description": "A short summary", "genres": ["Fantasy"], "site_chapter_count": 12}
                folder = library.add_or_update_novel(metadata.copy(), [])
                chapters = library.get_chapters(folder.name)
                self.assertEqual(len(chapters), 1)
                info = chapters[0]
                self.assertTrue(info.get("is_info_page"))
                self.assertEqual(info.get("chapter_number"), 0)
                self.assertTrue(info.get("downloaded"))
                self.assertIn("A short summary", library.read_chapter(folder.name, info))
                library.save_translation(folder.name, info, "Türkçe bilgi özeti")
                refreshed = library.get_chapters(folder.name)[0]
                self.assertTrue(refreshed.get("translated"))
                self.assertEqual(library.read_translation(folder.name, refreshed), "Türkçe bilgi özeti")


    def test_old_library_get_chapters_migrates_chapter_zero_and_saves_resume(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with patch.object(library_module, "ROOT", root), patch.object(library_module, "DATA_DIR", root / "data"), patch.object(library_module, "NOVELS_DIR", root / "data" / "novels"), patch.object(library_module, "INDEX_FILE", root / "data" / "library.json"):
                library = Library()
                folder = root / "data" / "novels" / "test_old"
                folder.mkdir(parents=True)
                (folder / "metadata.json").write_text('{"site_id":"test","novel_id":"old","title":"Old Novel","source_url":"https://example.com/old"}', encoding="utf-8")
                (folder / "chapters.json").write_text('{"chapters":[{"chapter_id":"c1","title":"Chapter 1","source_url":"https://example.com/old/1","downloaded":false}]}', encoding="utf-8")
                chapters = library.get_chapters("test_old")
                self.assertTrue(chapters[0].get("is_info_page"))
                self.assertEqual(chapters[0].get("chapter_number"), 0)
                library.save_reading_progress("test_old", chapters[1])
                metadata = library.get_metadata("test_old")
                self.assertEqual(metadata.get("last_read_chapter_id"), "c1")
                self.assertEqual(metadata.get("last_read_source_url"), "https://example.com/old/1")


    def test_library_recovers_chapter_files_missing_from_chapters_json(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with patch.object(library_module, "ROOT", root), patch.object(library_module, "DATA_DIR", root / "data"), patch.object(library_module, "NOVELS_DIR", root / "data" / "novels"), patch.object(library_module, "INDEX_FILE", root / "data" / "library.json"):
                library = Library()
                folder = root / "data" / "novels" / "legacy_novel"
                (folder / "chapters").mkdir(parents=True)
                (folder / "translated").mkdir(parents=True)
                (folder / "metadata.json").write_text('{"title":"Legacy","source_url":"https://example.com/legacy"}', encoding="utf-8")
                (folder / "chapters.json").write_text('{"chapters":[]}', encoding="utf-8")
                (folder / "chapters" / "legacy_chapter_1.txt").write_text("Original", encoding="utf-8")
                (folder / "translated" / "legacy_chapter_1.txt").write_text("Türkçe", encoding="utf-8")
                chapters = library.get_chapters("legacy_novel")
                self.assertEqual(len(chapters), 2)
                recovered = next(c for c in chapters if c.get("chapter_id") == "legacy_chapter_1")
                self.assertTrue(recovered.get("downloaded"))
                self.assertTrue(recovered.get("translated"))
                self.assertEqual(library.read_translation("legacy_novel", recovered), "Türkçe")

    def test_library_preserves_translation_state_on_refresh(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with patch.object(library_module, "ROOT", root), patch.object(library_module, "DATA_DIR", root / "data"), patch.object(library_module, "NOVELS_DIR", root / "data" / "novels"), patch.object(library_module, "INDEX_FILE", root / "data" / "library.json"):
                library = Library()
                metadata = {"site_id": "test", "site_name": "Test", "novel_id": "novel1", "source_url": "https://example.com/novel", "title": "Test novel", "site_chapter_count": 1}
                chapters = [{"chapter_id": "c1", "title": "Chapter 1", "source_url": "https://example.com/novel/chapter-1", "downloaded": False}]
                folder = library.add_or_update_novel(metadata.copy(), chapters)
                chapter = library.get_chapters(folder.name)[0]
                library.save_chapter(folder.name, chapter, {"content": "source text", "title": "Chapter 1"})
                chapter = library.get_chapters(folder.name)[0]
                library.save_translation(folder.name, chapter, "Türkçe metin")
                refreshed = [{"chapter_id": "c1", "title": "Chapter 1 updated", "source_url": "https://example.com/novel/chapter-1", "downloaded": False}]
                library.add_or_update_novel(metadata.copy(), refreshed)
                saved = library.get_chapters(folder.name)[0]
                self.assertTrue(saved.get("downloaded"))
                self.assertTrue(saved.get("translated"))
                self.assertEqual(library.get_metadata(folder.name).get("translated_chapter_count"), 1)
                self.assertEqual(library.read_translation(folder.name, saved), "Türkçe metin")



    def test_translation_retries_transient_failure_and_saves_success(self):
        import core.translator as translator_module
        class FakeLibrary:
            def read_chapter(self, folder, chapter): return "A sufficiently long source story."
            def get_metadata(self, folder): return {"site_id": "unknown-test-site"}
            def save_translation(self, folder, chapter, text, status="translated"):
                self.saved = (text, status)
            def mark_translation_failure(self, folder, chapter, error): self.failure = error
        fake = FakeLibrary()
        chapter = {"chapter_id": "c1", "source_url": "https://example.com/chapter-1", "downloaded": True, "title": "Chapter 1"}
        with patch.object(translator_module, "Library", return_value=fake), \
             patch.object(translator_module, "translate_text", side_effect=[TimeoutError("timeout"), "Türkçe çeviri"]), \
             patch.object(translator_module.time, "sleep"):
            errors = translator_module.translate_chapters("test", [chapter], fallback_original=True)
        self.assertEqual(errors, [])
        self.assertEqual(fake.saved, ("Türkçe çeviri", "translated"))

    def test_translation_three_failures_saves_marked_original_fallback(self):
        import core.translator as translator_module
        class FakeLibrary:
            def read_chapter(self, folder, chapter): return "Original story text."
            def get_metadata(self, folder): return {"site_id": "unknown-test-site"}
            def save_translation(self, folder, chapter, text, status="translated"):
                self.saved = (text, status)
            def mark_translation_failure(self, folder, chapter, error): self.failure = error
        fake = FakeLibrary()
        chapter = {"chapter_id": "c1", "source_url": "https://example.com/chapter-1", "downloaded": True, "title": "Chapter 1"}
        with patch.object(translator_module, "Library", return_value=fake), \
             patch.object(translator_module, "translate_text", side_effect=TimeoutError("timeout")), \
             patch.object(translator_module.time, "sleep"):
            errors = translator_module.translate_chapters("test", [chapter], fallback_original=True)
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0].get("attempts"), 3)
        self.assertEqual(fake.saved, ("Original story text.", "fallback_original"))

    def test_translation_three_failures_can_be_marked_for_later_retry(self):
        import core.translator as translator_module
        class FakeLibrary:
            def read_chapter(self, folder, chapter): return "Original story text."
            def get_metadata(self, folder): return {"site_id": "unknown-test-site"}
            def save_translation(self, folder, chapter, text, status="translated"): self.saved = (text, status)
            def mark_translation_failure(self, folder, chapter, error): self.failure = error
        fake = FakeLibrary()
        chapter = {"chapter_id": "c1", "source_url": "https://example.com/chapter-1", "downloaded": True, "title": "Chapter 1"}
        with patch.object(translator_module, "Library", return_value=fake), \
             patch.object(translator_module, "translate_text", side_effect=TimeoutError("timeout")), \
             patch.object(translator_module.time, "sleep"):
            errors = translator_module.translate_chapters("test", [chapter], fallback_original=False)
        self.assertEqual(len(errors), 1)
        self.assertIn("timeout", fake.failure)
        self.assertFalse(hasattr(fake, "saved"))

    def test_site_word_filter_removes_literal_phrases_case_insensitively(self):
        from core.word_filters import apply_word_filters
        config = {"content_cleanup": {"remove_phrases": ["Read more at Example.com", "FREE COINS"]}}
        source = "The story begins. READ MORE AT example.com\nA hero sees FREE coins ahead."
        result = apply_word_filters(source, config)
        self.assertNotIn("Read more at", result)
        self.assertNotIn("FREE COINS", result.upper())
        self.assertIn("The story begins.", result)
        self.assertIn("A hero sees ahead.", result)

if __name__ == "__main__":
    unittest.main()
