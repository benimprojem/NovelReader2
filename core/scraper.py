import copy
import hashlib
import re
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse, urldefrag

import requests
from bs4 import BeautifulSoup
from .word_filters import apply_word_filters

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0 Safari/537.36"


def canonical_url(url):
    url, _fragment = urldefrag(url.strip())
    return url.rstrip("/") if urlparse(url).path not in ("", "/") else url


def stable_id(value, length=16):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]


class SiteScraper:
    def __init__(self, site_config, timeout=25):
        self.config = site_config
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "en-US,en;q=0.9"})

    def fetch(self, url):
        response = self.session.get(url, timeout=self.timeout)
        response.raise_for_status()
        if not response.encoding or response.encoding.lower() == "iso-8859-1":
            response.encoding = response.apparent_encoding or "utf-8"
        return response.text

    @staticmethod
    def _node_value(node):
        if node is None:
            return ""
        if node.name == "meta":
            return (node.get("content") or "").strip()
        if node.name == "img":
            return (node.get("src") or node.get("data-src") or node.get("data-original") or "").strip()
        return " ".join(node.stripped_strings).strip()

    def _first_value(self, soup, key, base_url=""):
        for selector in self.config.get("selectors", {}).get(key, []):
            try:
                node = soup.select_one(selector)
            except Exception:
                continue
            value = self._node_value(node)
            if value:
                if key == "cover":
                    return urljoin(base_url, value)
                return value
        return ""

    def _all_values(self, soup, key):
        values = []
        for selector in self.config.get("selectors", {}).get(key, []):
            try:
                nodes = soup.select(selector)
            except Exception:
                continue
            for node in nodes:
                value = self._node_value(node)
                if value and value not in values:
                    values.append(value)
        return values

    def _novel_base(self, url):
        p = urlparse(canonical_url(url))
        path = p.path.rstrip("/")
        # FreeWebNovel chapter pages use /novel/<slug>/chapter-...
        path = re.sub(r"/chapter-[^/]+$", "", path, flags=re.I)
        # NovelBuddy chapter pages may use arbitrary chapter slugs. Callers should
        # normally supply the novel home URL, so do not guess on arbitrary slugs.
        return f"{p.scheme}://{p.netloc}{path}".rstrip("/")

    def fetch_novel(self, url):
        # The user may enter the first chapter URL directly. Derive the novel
        # homepage for metadata, but use the supplied chapter URL as the chain start.
        entered_url = canonical_url(url)
        base_url = self._novel_base(entered_url)
        is_chapter_entry = base_url != entered_url
        metadata_url = base_url if is_chapter_entry else entered_url
        html = self.fetch(metadata_url)
        soup = BeautifulSoup(html, "html.parser")
        title = self._first_value(soup, "title", metadata_url)
        if title:
            title = re.sub(r"\s*[|–-]\s*(NovelBuddy|Free Web Novel|FreeWebNovel).*?$", "", title, flags=re.I).strip()
        if not title:
            title = urlparse(metadata_url).path.rstrip("/").split("/")[-1].replace("-", " ").title()
        description = self._first_value(soup, "description", metadata_url)
        author = self._first_value(soup, "author", metadata_url)
        cover = self._first_value(soup, "cover", metadata_url)
        genres = self._all_values(soup, "genres")
        publication_status, publication_status_text = self._extract_publication_status(soup)
        # Prefer a count from the page's first/main novel listing. The whole page
        # may contain recommendation cards for unrelated novels with larger counts.
        body_text = soup.get_text(" ", strip=True)
        total = self._reported_total(body_text)
        discovery = self.config.get("chapter_discovery", {})
        strategy = discovery.get("strategy", "same_novel_path")
        discovery_warning = ""
        if strategy == "next_chain":
            # Metadata scan must not crawl chapters or infer the site's total from
            # how many Next links happened to parse. Read the total from the novel
            # homepage and save only a starting URL; the downloader follows Next
            # one page at a time, respecting the user's requested batch size.
            start_url = entered_url if is_chapter_entry else self._find_start_chapter_url(
                soup, metadata_url, base_url, discovery
            )
            if start_url:
                slug = urlparse(start_url).path.rstrip("/").split("/")[-1]
                number = re.search(r"chapter-(\d+)", slug, flags=re.I)
                start_title = f"Chapter {number.group(1)}" if number else "İlk bölüm"
                chapter_items = [{
                    "chapter_id": stable_id(start_url), "title": start_title,
                    "source_url": start_url, "source_order": 0, "downloaded": False
                }]
            else:
                chapter_items = self._extract_chapter_links(soup, metadata_url, base_url)
                discovery_warning = "İlk bölüm URL'si bulunamadı; ilk bölüm adresini doğrudan girmeniz önerilir."
        elif strategy == "paginated_list":
            chapter_items, discovery_warning = self._crawl_chapter_list_pages(soup, metadata_url, base_url, total, discovery)
        else:
            chapter_items = self._extract_chapter_links(soup, metadata_url, base_url)
        # Keep chapter titles concise: sites sometimes prepend the novel title to every chapter.
        for item in chapter_items:
            item["title"] = self._clean_chapter_title(item.get("title", ""), title)
        if total is None:
            total = len(chapter_items)
        metadata = {
            "site_id": self.config["id"],
            "site_name": self.config["name"],
            "novel_id": stable_id(self.config["id"] + "|" + base_url),
            "source_url": base_url,
            "source_page_url": metadata_url,
            "start_chapter_url": entered_url if is_chapter_entry else "",
            "title": title,
            "publication_status": publication_status,
            "publication_status_text": publication_status_text,
            "cover_url": cover,
            "description": description,
            "author": author,
            "genres": genres,
            "site_chapter_count": total,
            "discovered_chapter_count": len(chapter_items),
            "chapter_discovery_warning": discovery_warning,
            "downloaded_chapter_count": 0,
            "metadata_updated_at": datetime.now(timezone.utc).isoformat(),
            "metadata_record": True
        }
        return metadata, chapter_items

    def _extract_publication_status(self, soup):
        """Read the novel's declared status; absence of Next is not status evidence."""
        known = {
            "completed": "completed", "complete": "completed", "finished": "completed",
            "ongoing": "ongoing", "continuing": "ongoing", "in progress": "ongoing",
            "hiatus": "hiatus", "on hiatus": "hiatus",
            "dropped": "dropped", "cancelled": "dropped", "canceled": "dropped",
        }
        selectors = self.config.get("selectors", {}).get("status", [])
        candidates = []
        for selector in selectors:
            try:
                node = soup.select_one(selector)
            except Exception:
                node = None
            value = self._node_value(node)
            if value:
                candidates.append(value)
        text = soup.get_text(" ", strip=True)
        # Site status labels usually look like "Status: Ongoing" or "Novel Status Completed".
        match = re.search(
            r"(?:novel\s+)?status\s*[:：]?\s*(completed|complete|finished|ongoing|continuing|in progress|hiatus|on hiatus|dropped|cancelled|canceled)\b",
            text, flags=re.I,
        )
        if match:
            candidates.insert(0, match.group(1))
        for candidate in candidates:
            normalized = re.sub(r"\s+", " ", candidate).strip().casefold()
            if normalized in known:
                return known[normalized], candidate
            # A status element may include a label and value, e.g. "Status Ongoing".
            for raw, canonical in known.items():
                if re.search(rf"\b{re.escape(raw)}\b", normalized, flags=re.I):
                    return canonical, candidate
        return "unknown", candidates[0] if candidates else ""

    @staticmethod
    def _clean_chapter_title(chapter_title, novel_title=""):
        """Return a user-facing chapter title, not the novel/site page template."""
        original = re.sub(r"\s+", " ", str(chapter_title or "")).strip()
        title = re.sub(r"\s*[|–—:-]\s*(?:NovelBuddy|Free\s*Web\s*Novel|FreeWebNovel).*?$", "", original, flags=re.I).strip()
        novel = re.sub(r"\s+", " ", str(novel_title or "")).strip()
        if novel:
            # Remove exact novel-name occurrences at either end, with common
            # separators, even when a site places the novel name before the chapter.
            title = re.sub(rf"^{re.escape(novel)}\s*(?:[:|–—-]\s*)?", "", title, flags=re.I).strip()
            title = re.sub(rf"\s*(?:[:|–—-]\s*)?{re.escape(novel)}\s*$", "", title, flags=re.I).strip()
            # Some title templates wrap the chapter label between novel-name pieces.
            title = re.sub(rf"{re.escape(novel)}", "", title, flags=re.I).strip(" :|–—-	")
        # Discard SEO prefixes before a recognizable chapter number.
        chapter_match = re.search(r"\b(?:chapter|ch\.?|book)\s*#?\d+\s*(?::|[-|–—])?\s*.*$", title, flags=re.I)
        if chapter_match:
            title = chapter_match.group(0).strip()
        title = re.sub(r"^[:|–—-]+\s*|\s*[:|–—-]+$", "", title).strip()
        # If the page heading was only the novel title, infer a human-readable label
        # from the URL rather than exposing the SHA/MD5-like internal ID.
        if not title or (novel and title.casefold() == novel.casefold()):
            return ""
        if re.fullmatch(r"[a-f0-9]{12,64}", title, flags=re.I):
            return ""
        return title

    def _find_next_list_page_url(self, soup, page_url, base_url, discovery):
        """Find the next chapter-index page, not the next chapter-reading URL."""
        base = urlparse(base_url)
        allowed_suffixes = [re.compile(x, re.I) for x in discovery.get("list_page_path_patterns", [r"/page/\d+/?$", r"/list/\d+/?$"])]

        def is_list_page(candidate):
            parsed = urlparse(candidate)
            if parsed.netloc.lower() != base.netloc.lower():
                return False
            base_path = base.path.rstrip("/")
            path = parsed.path.rstrip("/")
            if path == base_path:
                return candidate != page_url
            if path.startswith(base_path + "/") and any(p.search(path) for p in allowed_suffixes):
                return True
            return False

        selectors = discovery.get("list_next_selectors", [
            ".pagination a[rel='next']", ".pagination a.next", "a[rel='next']", ".page-nav a.next"
        ])
        for selector in selectors:
            try:
                node = soup.select_one(selector)
            except Exception:
                node = None
            if node:
                href = node.get("href") or (node.find("a", href=True).get("href") if node.find("a", href=True) else "")
                if href:
                    candidate = canonical_url(urljoin(page_url, href))
                    if is_list_page(candidate):
                        return candidate

        patterns = [re.compile(x, re.I) for x in discovery.get("list_next_text_patterns", [r"^next$", r"^next page$", r"^›$", r"^older$", r"^older posts$"])]
        for anchor in soup.find_all("a", href=True):
            label = " ".join(anchor.stripped_strings).strip()
            attrs = " ".join(str(anchor.get(k, "")) for k in ("aria-label", "title", "class", "id"))
            if not any(p.search(label) or p.search(attrs) for p in patterns):
                continue
            candidate = canonical_url(urljoin(page_url, anchor["href"]))
            if is_list_page(candidate):
                return candidate
        return ""

    def _crawl_chapter_list_pages(self, home_soup, home_url, base_url, reported_total, discovery):
        """Collect chapter links from every paginated index page."""
        current_url = home_url
        current_soup = home_soup
        seen_pages = set()
        by_url = {}
        warning = ""
        # Page-count hint only; the hard cap protects against malformed loops.
        max_pages = min(max(((reported_total or 0) // 10) + 20, 100), 5000)
        while current_url and current_url not in seen_pages and len(seen_pages) < max_pages:
            seen_pages.add(current_url)
            for item in self._extract_chapter_links(current_soup, current_url, base_url):
                if item["source_url"] not in by_url:
                    item["source_order"] = len(by_url)
                    by_url[item["source_url"]] = item
            next_url = self._find_next_list_page_url(current_soup, current_url, base_url, discovery)
            if not next_url or next_url in seen_pages:
                break
            try:
                current_soup = BeautifulSoup(self.fetch(next_url), "html.parser")
                current_url = next_url
            except Exception as exc:
                warning = f"Bölüm listesi sayfaları taranırken durdu ({len(by_url)} bölüm bulundu): {exc}"
                break
        if len(seen_pages) >= max_pages:
            warning = f"Bölüm listesi taraması güvenlik sınırına ({max_pages} sayfa) ulaştı."
        elif reported_total and len(by_url) < reported_total and not warning:
            warning = (f"Sitede {reported_total} bölüm bildiriliyor, liste sayfalarından {len(by_url)} bağlantı bulundu. "
                       "Sayfalama bağlantısı veya site seçicileri kontrol edilmeli.")
        return list(by_url.values()), warning

    def _find_start_chapter_url(self, soup, page_url, base_url, discovery):
        """Choose a real chapter start link, never assume the homepage list is complete."""
        # An explicit start suffix is authoritative. This is important on sites
        # whose novel homepage lists newest chapters first: discovery must begin
        # at chapter 1, then follow the Next link found on each reading page.
        explicit_suffix = discovery.get("start_url_suffix")
        if explicit_suffix:
            return canonical_url(urljoin(base_url.rstrip("/") + "/", explicit_suffix.lstrip("/")))

        patterns = [re.compile(x, re.I) for x in discovery.get("start_link_text_patterns", [
            r"^start reading$", r"^read first$", r"^first chapter$", r"^begin reading$", r"^read from beginning$"
        ])]
        candidates = []
        for anchor in soup.find_all("a", href=True):
            href = canonical_url(urljoin(page_url, anchor.get("href", "")))
            if not self._is_novel_chapter_url(href, base_url):
                continue
            label = " ".join(anchor.stripped_strings).strip()
            label = label or anchor.get("aria-label", "") or anchor.get("title", "")
            if any(p.search(label.strip()) for p in patterns):
                return href
            candidates.append(href)

        # If the site exposes only a reverse-ordered partial list, the oldest visible
        # link is a last resort. Following Next from that page can discover the full chain.
        if candidates and discovery.get("start_fallback", "oldest_visible") == "oldest_visible":
            unique = list(dict.fromkeys(candidates))
            if discovery.get("newest_first_assumed", False):
                return unique[-1]
            return unique[0]
        return ""

    @staticmethod
    def _is_novel_chapter_url(url, base_url):
        parsed = urlparse(url)
        base = urlparse(base_url)
        path = parsed.path.rstrip("/")
        base_path = base.path.rstrip("/")
        return parsed.netloc.lower() == base.netloc.lower() and path.startswith(base_path + "/") and path != base_path

    def _find_next_chapter_url(self, soup, page_url, base_url, discovery):
        """Find a genuine next reading page; ignore disabled/self-referential controls."""
        current = canonical_url(page_url)

        def usable(href):
            if not href:
                return ""
            candidate = canonical_url(urljoin(page_url, href))
            if candidate == current or not self._is_novel_chapter_url(candidate, base_url):
                return ""
            return candidate

        # Site-specific selectors first. A number of reader themes render a
        # disabled/self-link before the real Next link, so never return it blindly.
        for selector in discovery.get("next_link_selectors", []):
            try:
                nodes = soup.select(selector)
            except Exception:
                nodes = []
            for node in nodes:
                href = node.get("href")
                if not href:
                    child = node.find("a", href=True)
                    href = child.get("href") if child else ""
                candidate = usable(href)
                if candidate:
                    return candidate

        anchors = soup.find_all("a", href=True)
        # rel=next is the strongest semantic signal.
        for anchor in anchors:
            rel = anchor.get("rel", [])
            if isinstance(rel, str):
                rel = rel.split()
            if any(str(x).lower() == "next" for x in rel):
                candidate = usable(anchor.get("href"))
                if candidate:
                    return candidate

        patterns = [re.compile(x, re.I) for x in discovery.get("next_link_text_patterns", [
            r"^next(?:\s+chapter)?$", r"^next chapter\b", r"^next\s*›?$", r"^older chapter$"
        ])]
        for anchor in anchors:
            label = " ".join(anchor.stripped_strings).strip()
            attrs = " ".join(str(anchor.get(k, "")) for k in ("aria-label", "title", "class", "id"))
            # Test visible text independently from attributes; combining them made
            # anchored patterns fail for icon-only anchors with a class='next'.
            if not (any(p.search(label) for p in patterns) or
                    re.search(r"(?:^|\s)(?:next|next-chapter|chapter-next)(?:\s|$)", attrs, flags=re.I)):
                continue
            candidate = usable(anchor.get("href"))
            if candidate:
                return candidate

        # Last-resort semantic fallback: some sites use an icon-only link without
        # rel/title/text. First inspect navigation-related controls.
        for anchor in anchors:
            attrs = " ".join(str(anchor.get(k, "")) for k in ("class", "id", "aria-label", "title", "rel"))
            if not re.search(r"(?:next|chapter-nav|chapter-control|pagination|next_chap|nextchap)", attrs, flags=re.I):
                continue
            candidate = usable(anchor.get("href"))
            if candidate:
                return candidate

        # Numeric FreeWebNovel URLs often have a perfectly usable Chapter N+1
        # link even when the theme's button has no useful label/class. Do not use
        # this for arbitrary slugs: only accept the exact next numeric chapter.
        current_match = re.search(r"/chapter-(\d+)(?:\.html)?/?$", urlparse(current).path, flags=re.I)
        if current_match:
            wanted = int(current_match.group(1)) + 1
            for anchor in anchors:
                candidate = usable(anchor.get("href"))
                if not candidate:
                    continue
                candidate_match = re.search(r"/chapter-(\d+)(?:\.html)?/?$", urlparse(candidate).path, flags=re.I)
                if candidate_match and int(candidate_match.group(1)) == wanted:
                    return candidate
        return ""

    def fetch_next_chapter_url(self, chapter_url, base_url):
        """Fetch a chapter page and resolve its next link using the site's rules."""
        html = self.fetch(chapter_url)
        soup = BeautifulSoup(html, "html.parser")
        return self._find_next_chapter_url(
            soup, chapter_url, base_url, self.config.get("chapter_discovery", {})
        )

    def _crawl_chapter_chain(self, home_soup, home_url, base_url, reported_total, discovery, start_url=""):
        # An explicitly entered chapter URL takes precedence over homepage heuristics.
        start_url = canonical_url(start_url) if start_url else self._find_start_chapter_url(home_soup, home_url, base_url, discovery)
        if not start_url:
            fallback = self._extract_chapter_links(home_soup, home_url, base_url)
            warning = "İlk bölüm bağlantısı bulunamadı; yalnızca ana sayfada görünen bağlantılar alındı. Next seçicisini kontrol edin."
            return fallback, warning

        items = []
        seen = set()
        current_url = start_url
        # The reported total is a hint, not a stopping condition: sites can have
        # stale totals or hidden bonus chapters. The hard cap prevents runaway loops.
        max_pages = min(max((reported_total or 0) + 20, 250), 5000)
        warning = ""
        while current_url and current_url not in seen and len(items) < max_pages:
            seen.add(current_url)
            try:
                page_html = self.fetch(current_url)
            except Exception as exc:
                warning = f"Bölüm bağlantılarını tararken durdu ({len(items)} bulundu): {exc}"
                break
            chapter_soup = BeautifulSoup(page_html, "html.parser")
            title = self._first_value(chapter_soup, "chapter_title", current_url)
            if title:
                title = re.sub(r"\s*[|–-]\s*(NovelBuddy|Free Web Novel|FreeWebNovel).*?$", "", title, flags=re.I).strip()
            if not title:
                title = chapter_soup.title.get_text(" ", strip=True) if chapter_soup.title else current_url
            items.append({
                "chapter_id": stable_id(current_url),
                "title": title,
                "source_url": current_url,
                "source_order": len(items),
                "downloaded": False
            })
            next_url = self._find_next_chapter_url(chapter_soup, current_url, base_url, discovery)
            if not next_url or next_url in seen:
                break
            current_url = next_url
        if len(items) >= max_pages:
            warning = f"Tarama güvenlik sınırına ({max_pages} bölüm) ulaştı."
        elif reported_total and len(items) < reported_total:
            warning = f"Sitede {reported_total} bölüm bildiriliyor, Next zincirinden {len(items)} bağlantı bulundu. Next bağlantısı veya site sayfalaması kontrol edilmeli."
        return items, warning

    def _extract_chapter_links(self, soup, page_url, base_url):
        items = []
        seen = set()
        base_path = urlparse(base_url).path.rstrip("/")
        host = urlparse(base_url).netloc.lower()
        for anchor in soup.find_all("a", href=True):
            href = canonical_url(urljoin(page_url, anchor["href"]))
            parsed = urlparse(href)
            if parsed.netloc.lower() != host:
                continue
            path = parsed.path.rstrip("/")
            if not path or path == base_path or not path.startswith(base_path + "/"):
                continue
            tail = path[len(base_path) + 1:].strip("/")
            if not tail or any(x in ("/" + tail.lower() + "/") for x in ["/genre/", "/genres/", "/author/", "/tag/"]):
                continue
            if href in seen:
                continue
            title = " ".join(anchor.stripped_strings).strip()
            if not title:
                title = anchor.get("title", "").strip()
            if not title or len(title) > 220:
                continue
            low = title.lower()
            if low in {"next", "previous", "prev", "first", "last", "read first", "chapter list", "add to library", "start reading"}:
                continue
            seen.add(href)
            items.append({
                "chapter_id": stable_id(href),
                "title": title,
                "source_url": href,
                "source_order": len(items),
                "downloaded": False
            })
        return items

    @staticmethod
    def _reported_total(text):
        # 999+ is a lower bound (at least 1000), not an exact count of 999.
        plus_patterns = [r"\b999\s*\+\s*chapters?\b", r"\bchapters?\s*[:：]?\s*999\s*\+", r"\b999\s*\+"]
        for pattern in plus_patterns:
            if re.search(pattern, text, flags=re.I):
                return 1000
        patterns = [r"\b(\d[\d,]*)\s+Chapters?\b", r"\bChapters?\s*[:：]?\s*(\d[\d,]*)\b"]
        for pattern in patterns:
            matches = re.findall(pattern, text, flags=re.I)
            if matches:
                # The first count belongs to the primary page content in normal
                # novel pages; later matches often belong to recommended novels.
                try:
                    return int(matches[0].replace(",", ""))
                except ValueError:
                    pass
        return None

    def _clean_reader_content(self, node):
        """Extract story text, applying generic and per-site cleanup before saving."""
        clone = copy.deepcopy(node)
        cleanup = self.config.get("content_cleanup", {})
        # Remove common UI areas and controls before collecting text. Class/id
        # matching is intentionally broad because reader sites use many themes.
        junk_selectors = [
            "script", "style", "noscript", "nav", "header", "footer", "aside",
            "button", "select", "option", "input", "textarea", "form", "label",
            "iframe", "svg", "canvas", "[role='navigation']", "[role='toolbar']",
            "[aria-label*='setting' i]", "[aria-label*='font' i]",
            "[class*='setting' i]", "[id*='setting' i]",
            "[class*='toolbar' i]", "[id*='toolbar' i]",
            "[class*='font' i]", "[id*='font' i]",
            "[class*='translate' i]", "[id*='translate' i]",
            "[class*='language' i]", "[id*='language' i]",
            "[class*='dropdown' i]", "[id*='dropdown' i]",
            ".ads", ".advertisement", ".share", ".social", ".pagination",
            ".chapter-nav", ".reader-options", ".reading-options",
        ]
        # Site-specific selectors are applied during download, before plain text is made.
        junk_selectors.extend(cleanup.get("remove_selectors", []))
        for selector in junk_selectors:
            try:
                for junk in clone.select(selector):
                    junk.decompose()
            except Exception:
                pass

        ui_labels = {
            "inter", "source sans", "segoe kullanıcı arayüzü", "segoe ui", "roboto",
            "nunito sans", "verdana", "tahoma", "arial", "palatino linotipi",
            "palatino linotype", "bildirim metni", "message text", "times new roman",
            "patrick el", "çevir", "translate", "orijinal (ingilizce)", "original (english)",
            "ispanyolca", "portekizce", "fransızca", "almanca", "italyanca", "rusça",
            "lehçe", "hollandaca", "türkçe", "arapça", "hintçe", "endonezya dili",
            "vietnamca", "filipinli", "tay dili", "japonca", "korece",
            "çince (basitleştirilmiş)", "çince (geleneksel)", "previous", "next",
            "önceki", "sonraki", "font size", "font family", "line height",
        }
        lines = []
        for raw in clone.stripped_strings:
            line = re.sub(r"\s+", " ", raw).strip()
            if not line:
                continue
            normalized = line.casefold().strip(" :：-—")
            if normalized in ui_labels:
                continue
            # Settings menus sometimes concatenate their choices into one line.
            # Skip a line only when it is mostly UI labels, not normal prose.
            tokens = [x.strip(" :：-—") for x in re.split(r"[\n|]", line)]
            if len(tokens) >= 4 and sum(t.casefold() in ui_labels for t in tokens) / len(tokens) > 0.5:
                continue
            lines.append(line)
        # Adjacent duplicate strings are common when both a wrapper and a child
        # repeat a heading. Preserve the text order but collapse immediate repeats.
        compact = []
        for line in lines:
            if not compact or compact[-1] != line:
                compact.append(line)
        text = "\n\n".join(compact).strip()
        # Site-specific patterns remove recurring ad slogans / injected lines.
        # Patterns should target known boilerplate, not general story vocabulary.
        for pattern in cleanup.get("remove_text_patterns", []):
            try:
                text = re.sub(pattern, "", text, flags=re.I | re.M)
            except re.error:
                continue
        exact_lines = {str(x).strip().casefold() for x in cleanup.get("remove_exact_lines", []) if str(x).strip()}
        if exact_lines:
            text = "\n".join(line for line in text.splitlines() if line.strip().casefold().strip(" :：-—") not in exact_lines)
        text = apply_word_filters(text, self.config)
        text = re.sub(r"[ \t]+\n", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def fetch_chapter(self, chapter_url, base_url=None):
        html = self.fetch(chapter_url)
        soup = BeautifulSoup(html, "html.parser")
        base_url = base_url or self._novel_base(chapter_url)
        next_url = self._find_next_chapter_url(
            soup, chapter_url, base_url, self.config.get("chapter_discovery", {})
        )
        title = self._first_value(soup, "chapter_title", chapter_url)
        if title:
            title = re.sub(r"\s*[|–-]\s*(NovelBuddy|Free Web Novel|FreeWebNovel).*?$", "", title, flags=re.I).strip()
        content = ""
        # Selectors are ordered from the most specific content container to broader
        # fallbacks. Use the first plausible match instead of the longest wrapper,
        # which can accidentally include the entire page's menus and advertisements.
        for selector in self.config.get("selectors", {}).get("chapter_content", []):
            try:
                nodes = soup.select(selector)
            except Exception:
                nodes = []
            for node in nodes:
                candidate = self._clean_reader_content(node)
                if len(candidate) >= 120:
                    content = candidate
                    break
                if len(candidate) > len(content):
                    content = candidate
            if len(content) >= 120:
                break

        # Fallback: rank plausible content containers by readable paragraph text,
        # while excluding containers that are clearly page chrome or controls.
        if len(content) < 120:
            for node in soup.find_all(["article", "main", "div", "section"]):
                marker = " ".join([str(node.get("id", "")), " ".join(node.get("class", []))]).casefold()
                if any(word in marker for word in ("setting", "toolbar", "header", "footer", "sidebar", "menu", "comment", "related", "recommend")):
                    continue
                paragraphs = node.find_all("p", recursive=True)
                if paragraphs:
                    candidate = self._clean_reader_content(node)
                    if len(candidate) > len(content):
                        content = candidate
        if not title:
            title = soup.title.get_text(" ", strip=True) if soup.title else chapter_url
        if not content.strip():
            raise ValueError("Bölüm metni bulunamadı. Site yapılandırmasındaki chapter_content seçicileri güncellenmeli.")
        # Avoid repeating the page/chapter heading as the first paragraph.
        content_lines = content.splitlines()
        while content_lines and content_lines[0].strip().casefold() == title.strip().casefold():
            content_lines.pop(0)
        content = "\n".join(content_lines).strip()
        if len(content) < 40:
            raise ValueError("Sayfadan gerçek bölüm metni çıkarılamadı; yalnızca menü/ayar metni bulunmuş olabilir.")
        return {"title": title, "source_url": chapter_url, "content": content,
                "next_url": next_url, "downloaded_at": datetime.now(timezone.utc).isoformat()}

