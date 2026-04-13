from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import mimetypes
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from urllib.parse import parse_qs, urljoin, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup
from bs4.element import NavigableString, Tag


WORKSPACE = Path(__file__).resolve().parents[1]
CSV_PATH = WORKSPACE / "rance_world_note_page_urls.csv"
OUTPUT_ROOT = WORKSPACE / "rance-world-note"
MIRROR_ROOT = OUTPUT_ROOT / "_mirror"
PAGE_ROOT = MIRROR_ROOT / "pages"
STYLE_PATH = OUTPUT_ROOT / "assets" / "site.css"
LIST_JS_PATH = OUTPUT_ROOT / "assets" / "list.js"
MANIFEST_PATH = MIRROR_ROOT / "manifest.json"
VERCEL_ROUTES_PATH = WORKSPACE / "vercel-routes.json"
HOME_FILE = MIRROR_ROOT / "home.html"
LIST_FILE = MIRROR_ROOT / "list.html"

SOURCE_ORIGIN = "https://seesaawiki.jp"
SOURCE_SITE = "rance-world-note"
SOURCE_SITE_PREFIX = f"/{SOURCE_SITE}"
TIMEOUT = 30
RETRIES = 4
BACKOFF_BASE = 1.2
DEFAULT_WORKERS = 4
USER_AGENT = "Mozilla/5.0 (compatible; RanceWikiLocalMirror/1.0)"

URL_ATTRS = ("src", "data-src", "data-original", "poster")
UNWANTED_TAGS = {"script", "style", "noscript", "form", "input", "button", "textarea", "select", "option"}
FILE_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".svg",
    ".bmp",
    ".ico",
    ".pdf",
    ".txt",
    ".zip",
    ".7z",
    ".rar",
    ".mp3",
    ".mp4",
    ".wav",
    ".ogg",
}
CONTENT_TYPE_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/svg+xml": ".svg",
    "image/x-icon": ".ico",
    "application/pdf": ".pdf",
    "text/plain": ".txt",
    "audio/mpeg": ".mp3",
    "video/mp4": ".mp4",
}
DECODE_CANDIDATES = ("euc_jis_2004", "euc_jp", "euc_jisx0213", "cp932", "shift_jis", "utf-8")
STYLE_URL_RE = re.compile(r"url\((['\"]?)(.+?)\1\)")

STYLE_CSS = """\
:root {
  color-scheme: light;
  --bg: #eef1f5;
  --panel: #ffffff;
  --panel-border: #d8dde6;
  --ink: #1d2430;
  --muted: #5b6574;
  --accent: #1859b8;
  --accent-soft: #e7f0ff;
  --danger: #b84a4a;
  --shadow: 0 18px 50px rgba(17, 29, 51, 0.08);
  --radius: 16px;
}

* {
  box-sizing: border-box;
}

html {
  scroll-behavior: smooth;
}

body {
  margin: 0;
  background:
    radial-gradient(circle at top right, rgba(24, 89, 184, 0.08), transparent 28%),
    linear-gradient(180deg, #f7f9fc 0%, var(--bg) 100%);
  color: var(--ink);
  font-family: "Yu Gothic UI", "Hiragino Kaku Gothic ProN", Meiryo, sans-serif;
  line-height: 1.75;
}

a {
  color: var(--accent);
  text-decoration: none;
}

a:hover {
  text-decoration: underline;
}

img {
  max-width: 100%;
  height: auto;
}

iframe {
  max-width: 100%;
  border: 0;
}

.site-shell {
  width: min(1180px, calc(100vw - 32px));
  margin: 0 auto;
  padding: 24px 0 48px;
}

.site-header {
  position: sticky;
  top: 0;
  z-index: 20;
  backdrop-filter: blur(14px);
  background: rgba(247, 249, 252, 0.82);
  border-bottom: 1px solid rgba(216, 221, 230, 0.9);
}

.site-header-inner {
  width: min(1180px, calc(100vw - 32px));
  margin: 0 auto;
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  align-items: center;
  justify-content: space-between;
  padding: 14px 0;
}

.site-brand {
  display: flex;
  gap: 12px;
  align-items: center;
}

.site-brand-mark {
  width: 12px;
  height: 12px;
  border-radius: 999px;
  background: linear-gradient(135deg, #f4b400, #1859b8);
  box-shadow: 0 0 0 6px rgba(24, 89, 184, 0.08);
}

.site-brand-text strong,
.site-brand-text span {
  display: block;
}

.site-brand-text strong {
  font-size: 0.98rem;
  letter-spacing: 0.02em;
}

.site-brand-text span {
  color: var(--muted);
  font-size: 0.86rem;
}

.site-nav {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.site-nav a {
  padding: 8px 12px;
  border-radius: 999px;
  background: #fff;
  border: 1px solid var(--panel-border);
  box-shadow: 0 4px 12px rgba(20, 33, 55, 0.04);
}

.page-card,
.overview-card {
  background: var(--panel);
  border: 1px solid var(--panel-border);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
}

.page-card {
  padding: 28px;
}

.overview-card {
  padding: 24px;
}

.page-head {
  margin-bottom: 28px;
}

.page-title {
  margin: 0 0 8px;
  font-size: clamp(1.6rem, 2vw + 1rem, 2.4rem);
  line-height: 1.2;
}

.page-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 10px 16px;
  color: var(--muted);
  font-size: 0.92rem;
}

.page-meta span {
  display: inline-flex;
  gap: 6px;
  align-items: center;
}

.page-content {
  min-width: 0;
}

.page-content > .user-area {
  display: grid;
  gap: 18px;
}

.page-content .wiki-section-1,
.page-content .wiki-section-2,
.page-content .wiki-section-3 {
  background: #fbfcfe;
  border: 1px solid #e3e8f0;
  border-radius: 14px;
  overflow: hidden;
}

.page-content .title-1,
.page-content .title-2,
.page-content .title-3 {
  padding: 14px 18px;
  background: linear-gradient(180deg, #f3f7ff 0%, #ebf1fb 100%);
  border-bottom: 1px solid #e3e8f0;
}

.page-content .title-1 h3,
.page-content .title-2 h4,
.page-content .title-3 h5 {
  margin: 0;
  line-height: 1.45;
}

.page-content .wiki-section-body-1,
.page-content .wiki-section-body-2,
.page-content .wiki-section-body-3 {
  padding: 18px;
}

.page-content .toc,
.page-content .wiki-catalog {
  background: var(--accent-soft);
  border: 1px solid #cbdcfb;
  border-radius: 12px;
}

.page-content .wiki-catalog-inner {
  padding: 14px 18px;
}

.page-content ul,
.page-content ol {
  padding-left: 1.5em;
}

.page-content table {
  width: 100%;
  border-collapse: collapse;
  margin: 10px 0 0;
  background: #fff;
}

.page-content th,
.page-content td {
  border: 1px solid #d6dde7;
  padding: 8px 10px;
  vertical-align: top;
}

.page-content th {
  background: #f4f7fb;
}

.page-content blockquote {
  margin: 16px 0;
  padding: 12px 16px;
  border-left: 4px solid #cbd6e6;
  background: #f7f9fc;
}

.page-content hr {
  border: 0;
  border-top: 1px solid #d8dde6;
  margin: 24px 0;
}

.page-content .footer-footnote {
  margin-top: 24px;
  padding: 16px 18px;
  background: #fafbfc;
  border: 1px solid #e3e8f0;
  border-radius: 14px;
}

.page-content .toggle-display {
  display: block !important;
}

.missing-link {
  color: var(--danger);
  text-decoration: underline dotted;
}

.overview-grid {
  display: grid;
  gap: 20px;
}

.overview-card h1,
.overview-card h2 {
  margin-top: 0;
}

.overview-actions {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  margin-top: 16px;
}

.overview-actions a {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 168px;
  padding: 12px 16px;
  border-radius: 999px;
  border: 1px solid var(--panel-border);
  background: #fff;
}

.overview-actions a.primary {
  color: #fff;
  border-color: transparent;
  background: linear-gradient(135deg, #1859b8, #0f7c83);
}

.page-list-tools {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
  margin: 18px 0 14px;
}

.page-list-tools input {
  flex: 1 1 320px;
  min-width: 220px;
  padding: 12px 14px;
  border-radius: 12px;
  border: 1px solid #cfd7e4;
  background: #fff;
  font: inherit;
}

.page-list-tools .result-count {
  color: var(--muted);
  font-size: 0.92rem;
}

.page-list {
  width: 100%;
  border-collapse: collapse;
  background: #fff;
}

.page-list th,
.page-list td {
  border-bottom: 1px solid #e8edf5;
  padding: 10px 12px;
  text-align: left;
}

.page-list tbody tr:hover {
  background: #f7faff;
}

.page-list .num {
  width: 90px;
  color: var(--muted);
}

.page-list .updated {
  white-space: nowrap;
  color: var(--muted);
  font-size: 0.9rem;
}

.site-footer {
  width: min(1180px, calc(100vw - 32px));
  margin: 0 auto;
  padding: 0 0 36px;
  color: var(--muted);
  font-size: 0.9rem;
}

@media (max-width: 860px) {
  .page-card,
  .overview-card {
    padding: 18px;
    border-radius: 14px;
  }

  .page-content .wiki-section-body-1,
  .page-content .wiki-section-body-2,
  .page-content .wiki-section-body-3 {
    padding: 14px;
  }

  .page-content table {
    display: block;
    overflow-x: auto;
    white-space: nowrap;
  }
}
"""

LIST_JS = """\
(() => {
  const input = document.querySelector('[data-page-filter]');
  const count = document.querySelector('[data-result-count]');
  const rows = Array.from(document.querySelectorAll('[data-page-row]'));
  if (!input || !count || rows.length === 0) {
    return;
  }

  const update = () => {
    const keyword = input.value.trim().toLowerCase();
    let visible = 0;
    for (const row of rows) {
      const haystack = row.dataset.search || '';
      const show = keyword === '' || haystack.includes(keyword);
      row.hidden = !show;
      if (show) {
        visible += 1;
      }
    }
    count.textContent = `${visible} / ${rows.length} 件表示`;
  };

  input.addEventListener('input', update);
  update();
})();
"""


@dataclass(frozen=True)
class PageRecord:
    no: int
    source_url: str
    source_path: str


@dataclass
class PageMeta:
    no: int
    title: str
    source_url: str
    route_path: str
    file: str
    updated_text: str


_thread_local = threading.local()
_asset_cache: dict[str, str] = {}
_asset_cache_lock = threading.Lock()


def get_session() -> requests.Session:
    session = getattr(_thread_local, "session", None)
    if session is None:
        session = requests.Session()
        session.headers.update({"User-Agent": USER_AGENT})
        _thread_local.session = session
    return session


def request(url: str, *, stream: bool = False) -> requests.Response:
    last_error: Exception | None = None
    for attempt in range(1, RETRIES + 1):
        try:
            response = get_session().get(url, timeout=TIMEOUT, stream=stream)
            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            last_error = exc
            if attempt == RETRIES:
                break
            time.sleep(BACKOFF_BASE * attempt)
    assert last_error is not None
    raise last_error


def decode_bytes(data: bytes) -> str:
    for encoding in DECODE_CANDIDATES:
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("euc_jp", errors="replace")


def normalize_url(url: str, base_url: str) -> str:
    absolute = urljoin(base_url, url)
    parts = urlsplit(absolute)
    return urlunsplit((parts.scheme or "https", parts.netloc, parts.path, parts.query, parts.fragment))


def normalize_source_page_url(url: str) -> str:
    absolute = normalize_url(url, SOURCE_ORIGIN)
    parts = urlsplit(absolute)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def source_path_to_route(path: str) -> str:
    if path == SOURCE_SITE_PREFIX or path == SOURCE_SITE_PREFIX + "/":
        return f"{SOURCE_SITE_PREFIX}/"
    if path == f"{SOURCE_SITE_PREFIX}/l" or path == f"{SOURCE_SITE_PREFIX}/l/":
        return f"{SOURCE_SITE_PREFIX}/l/"
    if path.startswith(f"{SOURCE_SITE_PREFIX}/d/"):
        return path.rstrip("/") + "/"
    return path


def is_source_page_link(url: str) -> bool:
    parts = urlsplit(url)
    return parts.netloc == "seesaawiki.jp" and parts.path.startswith(f"{SOURCE_SITE_PREFIX}/d/")


def is_source_root_or_list(url: str) -> bool:
    parts = urlsplit(url)
    return parts.netloc == "seesaawiki.jp" and parts.path in {
        SOURCE_SITE_PREFIX,
        SOURCE_SITE_PREFIX + "/",
        f"{SOURCE_SITE_PREFIX}/l",
        f"{SOURCE_SITE_PREFIX}/l/",
    }


def is_source_edit_link(url: str) -> bool:
    parts = urlsplit(url)
    return parts.netloc == "seesaawiki.jp" and parts.path.startswith(f"{SOURCE_SITE_PREFIX}/e/")


def is_missing_page_link(url: str) -> bool:
    parts = urlsplit(url)
    return (
        parts.netloc == "seesaawiki.jp"
        and parts.path.startswith(f"{SOURCE_SITE_PREFIX}/e/add")
        and "pagename" in parse_qs(parts.query)
    )


def looks_like_asset(url: str) -> bool:
    parts = urlsplit(url)
    ext = Path(parts.path).suffix.lower()
    return ext in FILE_EXTENSIONS


def guess_extension_from_content_type(content_type: str) -> str:
    content_type = content_type.split(";", 1)[0].strip().lower()
    if content_type in CONTENT_TYPE_EXTENSIONS:
        return CONTENT_TYPE_EXTENSIONS[content_type]
    guessed = mimetypes.guess_extension(content_type)
    return guessed or ".bin"


def asset_output_path(asset_url: str, content_type: str = "") -> tuple[Path, str]:
    parts = urlsplit(asset_url)
    ext = Path(parts.path).suffix.lower()
    if ext not in FILE_EXTENSIONS:
        ext = guess_extension_from_content_type(content_type)
    digest = hashlib.sha1(asset_url.encode("utf-8")).hexdigest()
    relative = Path("assets") / "external" / digest[:2] / f"{digest}{ext}"
    return OUTPUT_ROOT / relative, f"/rance-world-note/{relative.as_posix()}"


def download_asset(asset_url: str) -> str:
    asset_url = normalize_url(asset_url, SOURCE_ORIGIN)
    with _asset_cache_lock:
        cached = _asset_cache.get(asset_url)
        if cached:
            return cached

    precomputed_output, precomputed_href = asset_output_path(asset_url, "")
    if precomputed_output.suffix.lower() in FILE_EXTENSIONS and precomputed_output.exists():
        with _asset_cache_lock:
            _asset_cache[asset_url] = precomputed_href
        return precomputed_href

    try:
        response = request(asset_url, stream=True)
    except requests.RequestException:
        with _asset_cache_lock:
            _asset_cache[asset_url] = asset_url
        return asset_url
    response.raw.decode_content = True
    output_path, href = asset_output_path(asset_url, response.headers.get("Content-Type", ""))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not output_path.exists():
        temp_path = output_path.with_name(f"{output_path.name}.{threading.get_ident()}.tmp")
        with temp_path.open("wb") as file_obj:
            for chunk in response.iter_content(chunk_size=64 * 1024):
                if chunk:
                    file_obj.write(chunk)
        try:
            os.replace(temp_path, output_path)
        except OSError:
            pass
        finally:
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except OSError:
                    pass

    with _asset_cache_lock:
        _asset_cache[asset_url] = href
    return href


def rewrite_style_urls(style_value: str, page_url: str) -> str:
    def replace(match: re.Match[str]) -> str:
        quote_mark = match.group(1) or ""
        raw_url = match.group(2).strip()
        if raw_url.startswith("data:"):
            return match.group(0)
        absolute = normalize_url(raw_url, page_url)
        if looks_like_asset(absolute):
            return f"url({quote_mark}{download_asset(absolute)}{quote_mark})"
        return match.group(0)

    return STYLE_URL_RE.sub(replace, style_value)


def clean_text(value: str) -> str:
    return " ".join(value.split())


def tag_to_missing_span(tag: Tag) -> None:
    tag.name = "span"
    tag.attrs = {"class": ["missing-link"]}


def sanitize_content(fragment: BeautifulSoup, page_record: PageRecord) -> None:
    for tag in list(fragment.find_all(True)):
        tag_attrs = tag.attrs or {}
        if tag.attrs is None:
            tag.attrs = {}
        for attribute in list(tag_attrs):
            if attribute.lower().startswith("on"):
                del tag.attrs[attribute]

        if tag.name in UNWANTED_TAGS:
            tag.decompose()
            continue

        classes = set(tag.get("class", []))
        if "part-edit" in classes or "title-1-part-edit" in classes or "title-2-part-edit" in classes or "title-3-part-edit" in classes:
            tag.decompose()
            continue

        if tag.name == "img":
            src = None
            for attr in URL_ATTRS:
                if tag.get(attr):
                    src = tag.get(attr)
                    break
            if not src:
                tag.decompose()
                continue
            absolute = normalize_url(src, page_record.source_url)
            if "icon_pen.gif" in absolute or "icon_edit.png" in absolute or "spacer.gif" in absolute:
                tag.decompose()
                continue
            tag["src"] = download_asset(absolute)
            tag["loading"] = "lazy"
            tag["decoding"] = "async"
            for attr in ("data-src", "data-original", "srcset"):
                tag.attrs.pop(attr, None)
            continue

        if tag.has_attr("style"):
            tag["style"] = rewrite_style_urls(tag["style"], page_record.source_url)

        if tag.name == "iframe" and tag.get("src"):
            tag["src"] = normalize_url(tag["src"], page_record.source_url)
            tag["loading"] = "lazy"
            continue

        if tag.name != "a" or not tag.get("href"):
            continue

        href = tag["href"].strip()
        if not href:
            tag.unwrap()
            continue

        if href.startswith("#"):
            continue

        absolute = normalize_url(href, page_record.source_url)
        parsed = urlsplit(absolute)

        if is_source_edit_link(absolute):
            if tag.get_text(strip=True):
                tag.unwrap()
            else:
                tag.decompose()
            continue

        if is_missing_page_link(absolute):
            tag_to_missing_span(tag)
            continue

        if is_source_page_link(absolute):
            if parsed.path == page_record.source_path and parsed.fragment:
                tag["href"] = f"#{parsed.fragment}"
            else:
                local_path = source_path_to_route(parsed.path)
                if parsed.fragment:
                    local_path = f"{local_path}#{parsed.fragment}"
                tag["href"] = local_path
            continue

        if is_source_root_or_list(absolute):
            local_path = source_path_to_route(parsed.path)
            if parsed.fragment:
                local_path = f"{local_path}#{parsed.fragment}"
            tag["href"] = local_path
            continue

        if looks_like_asset(absolute) and parsed.netloc.endswith("seesaawiki.jp"):
            tag["href"] = download_asset(absolute)
            continue

        if parsed.scheme in {"http", "https"}:
            tag["href"] = absolute
            tag["rel"] = "noopener noreferrer"
            continue

        tag.unwrap()


def extract_page_title(page_header: Tag | None, soup: BeautifulSoup) -> str:
    if page_header:
        header_clone = BeautifulSoup(str(page_header), "html.parser")
        for tag in header_clone.select("a, img"):
            tag.decompose()
        h2 = header_clone.select_one("h2")
        if h2:
            text = clean_text(h2.get_text(" ", strip=True))
            if text:
                return text
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    if " - " in title:
        return title.split(" - ", 1)[0].strip()
    return title or "無題"


def extract_update_text(page_header: Tag | None) -> str:
    if not page_header:
        return ""
    header_clone = BeautifulSoup(str(page_header), "html.parser")
    for tag in header_clone.select("span.history, img"):
        tag.decompose()
    update = header_clone.select_one("p.update")
    if not update:
        return ""
    return clean_text(update.get_text(" ", strip=True))


def build_page_html(title: str, update_text: str, page_record: PageRecord, content_html: str) -> str:
    escaped_title = html.escape(title)
    escaped_update = html.escape(update_text)
    escaped_source_url = html.escape(page_record.source_url)
    route_path = source_path_to_route(page_record.source_path)
    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escaped_title} | Rance Wiki Local Mirror</title>
  <link rel="stylesheet" href="/rance-world-note/assets/site.css">
</head>
<body>
  <header class="site-header">
    <div class="site-header-inner">
      <div class="site-brand">
        <span class="site-brand-mark" aria-hidden="true"></span>
        <div class="site-brand-text">
          <strong>Rance Wiki Local Mirror</strong>
          <span>広告を除いたローカル閲覧用ミラー</span>
        </div>
      </div>
      <nav class="site-nav" aria-label="Primary">
        <a href="/rance-world-note/">トップ</a>
        <a href="/rance-world-note/l/">ページ一覧</a>
        <a href="{escaped_source_url}" target="_blank" rel="noopener noreferrer">元ページ</a>
      </nav>
    </div>
  </header>
  <main class="site-shell">
    <article class="page-card">
      <header class="page-head">
        <h1 class="page-title">{escaped_title}</h1>
        <div class="page-meta">
          <span><strong>パス:</strong> <code>{html.escape(route_path)}</code></span>
          <span><strong>取得元:</strong> <a href="{escaped_source_url}" target="_blank" rel="noopener noreferrer">{escaped_source_url}</a></span>
          {"<span><strong>更新:</strong> " + escaped_update + "</span>" if escaped_update else ""}
        </div>
      </header>
      <section class="page-content">
        {content_html}
      </section>
    </article>
  </main>
  <footer class="site-footer">
    ミラー生成時刻: {datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")}
  </footer>
</body>
</html>
"""


def build_home_html(page_count: int, generated_at: str, menu_html: str) -> str:
    menu_section = ""
    if menu_html:
        menu_section = f"""
    <section class="page-card">
      <header class="page-head">
        <h2 class="page-title">MenuBar1</h2>
        <div class="page-meta">
          <span><strong>リンク元:</strong> <a href="/rance-world-note/d/MenuBar1/">/rance-world-note/d/MenuBar1/</a></span>
        </div>
      </header>
      <div class="page-content">
        {menu_html}
      </div>
    </section>"""
    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Rance Wiki Local Mirror</title>
  <link rel="stylesheet" href="/rance-world-note/assets/site.css">
</head>
<body>
  <header class="site-header">
    <div class="site-header-inner">
      <div class="site-brand">
        <span class="site-brand-mark" aria-hidden="true"></span>
        <div class="site-brand-text">
          <strong>Rance Wiki Local Mirror</strong>
          <span>広告を除いたローカル閲覧用ミラー</span>
        </div>
      </div>
      <nav class="site-nav" aria-label="Primary">
        <a href="/rance-world-note/l/">ページ一覧</a>
        <a href="/rance-world-note/d/">本文一覧</a>
      </nav>
    </div>
  </header>
  <main class="site-shell overview-grid">
    <section class="overview-card">
      <h1>ローカルミラー</h1>
      <p>Seesaa Wiki の本文ページ {page_count} 件を取得し、広告や編集導線を除いたローカル閲覧用HTMLとして再構成しています。</p>
      <div class="overview-actions">
        <a class="primary" href="/rance-world-note/l/">ページ一覧を開く</a>
        <a href="/rance-world-note/d/">本文URLで辿る</a>
      </div>
    </section>
    <section class="overview-card">
      <h2>情報</h2>
      <p>生成時刻: {html.escape(generated_at)}</p>
      <p>配下URL: <code>/rance-world-note/d/...</code></p>
      <p>ローカルサーバー: <code>python scripts/serve_rance_mirror.py</code></p>
    </section>
    {menu_section}
  </main>
  <footer class="site-footer">
    このページはローカル再構成版です。
  </footer>
</body>
</html>
"""


def build_list_html(pages: list[PageMeta], generated_at: str) -> str:
    rows = []
    for page in pages:
        rows.append(
            "<tr data-page-row data-search=\"{search}\">"
            "<td class=\"num\">{no}</td>"
            "<td><a href=\"{href}\">{title}</a></td>"
            "<td class=\"updated\">{updated}</td>"
            "</tr>".format(
                search=html.escape(f"{page.title} {page.route_path}".lower(), quote=True),
                no=page.no,
                href=html.escape(page.route_path),
                title=html.escape(page.title),
                updated=html.escape(page.updated_text or ""),
            )
        )
    rows_html = "\n".join(rows)
    return f"""<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>ページ一覧 | Rance Wiki Local Mirror</title>
  <link rel="stylesheet" href="/rance-world-note/assets/site.css">
  <script defer src="/rance-world-note/assets/list.js"></script>
</head>
<body>
  <header class="site-header">
    <div class="site-header-inner">
      <div class="site-brand">
        <span class="site-brand-mark" aria-hidden="true"></span>
        <div class="site-brand-text">
          <strong>Rance Wiki Local Mirror</strong>
          <span>広告を除いたローカル閲覧用ミラー</span>
        </div>
      </div>
      <nav class="site-nav" aria-label="Primary">
        <a href="/rance-world-note/">トップ</a>
        <a href="/rance-world-note/d/">本文一覧</a>
      </nav>
    </div>
  </header>
  <main class="site-shell">
    <section class="overview-card">
      <h1>ページ一覧</h1>
      <p>全 {len(pages)} 件。タイトルやパスで絞り込めます。</p>
      <div class="page-list-tools">
        <input type="search" placeholder="タイトルまたはパスで検索" data-page-filter>
        <span class="result-count" data-result-count></span>
      </div>
      <table class="page-list">
        <thead>
          <tr>
            <th class="num">No</th>
            <th>タイトル</th>
            <th class="updated">更新</th>
          </tr>
        </thead>
        <tbody>
          {rows_html}
        </tbody>
      </table>
    </section>
  </main>
  <footer class="site-footer">
    生成時刻: {html.escape(generated_at)}
  </footer>
</body>
</html>
"""


def write_support_files() -> None:
    STYLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STYLE_PATH.write_text(STYLE_CSS, encoding="utf-8")
    LIST_JS_PATH.write_text(LIST_JS, encoding="utf-8")


def read_page_records(limit: int | None = None) -> list[PageRecord]:
    records: list[PageRecord] = []
    with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as file_obj:
        reader = csv.DictReader(file_obj)
        for row in reader:
            if limit is not None and len(records) >= limit:
                break
            source_url = normalize_source_page_url(row["url"])
            source_path = urlsplit(source_url).path
            records.append(PageRecord(no=int(row["no"]), source_url=source_url, source_path=source_path))
    return records


def page_output_file(page_record: PageRecord) -> Path:
    digest = hashlib.sha1(page_record.source_url.encode("utf-8")).hexdigest()
    return PAGE_ROOT / digest[:2] / f"{digest}.html"


def read_existing_page_meta(page_record: PageRecord) -> PageMeta | None:
    output_file = page_output_file(page_record)
    if not output_file.exists():
        return None
    try:
        soup = BeautifulSoup(output_file.read_text(encoding="utf-8"), "html.parser")
    except OSError:
        return None

    title_node = soup.select_one("h1.page-title")
    if not title_node:
        return None

    update_text = ""
    for span in soup.select(".page-meta span"):
        text = clean_text(span.get_text(" ", strip=True))
        if text.startswith("更新:"):
            update_text = text.split("更新:", 1)[1].strip()
            break

    return PageMeta(
        no=page_record.no,
        title=clean_text(title_node.get_text(" ", strip=True)),
        source_url=page_record.source_url,
        route_path=source_path_to_route(page_record.source_path),
        file=output_file.relative_to(OUTPUT_ROOT).as_posix(),
        updated_text=update_text,
    )


def extract_page_content_html(page_meta: PageMeta) -> str:
    page_file = OUTPUT_ROOT / page_meta.file
    soup = BeautifulSoup(page_file.read_text(encoding="utf-8"), "html.parser")
    page_content = soup.select_one(".page-content")
    if not page_content:
        return ""
    return "".join(
        str(node)
        for node in page_content.contents
        if not isinstance(node, NavigableString) or node.strip()
    )


def process_page(page_record: PageRecord) -> PageMeta:
    response = request(page_record.source_url)
    soup = BeautifulSoup(decode_bytes(response.content), "html.parser")

    page_header = soup.select_one("#page-header")
    page_body_inner = soup.select_one("#page-body-inner")
    if not page_body_inner:
        raise RuntimeError(f"本文領域が見つかりません: {page_record.source_url}")

    title = extract_page_title(page_header, soup)
    update_text = extract_update_text(page_header)

    content_parts: list[str] = []
    user_area = page_body_inner.select_one(":scope > .user-area")
    if user_area:
        content_parts.append(str(user_area))
    footer_footnote = page_body_inner.select_one(":scope > .footer-footnote")
    if footer_footnote:
        content_parts.append(str(footer_footnote))
    if not content_parts:
        fallback = BeautifulSoup(str(page_body_inner), "html.parser")
        for tag in fallback.select(".ads-box, #information-box, #page-posted, #page-category, #page-toplink, #pageroot-form-box, script"):
            tag.decompose()
        content_parts.append(str(fallback))

    fragment = BeautifulSoup("\n".join(content_parts), "html.parser")
    sanitize_content(fragment, page_record)
    content_html = "".join(str(node) for node in fragment.contents if not isinstance(node, NavigableString) or node.strip())

    html_text = build_page_html(title, update_text, page_record, content_html)
    output_file = page_output_file(page_record)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(html_text, encoding="utf-8")

    return PageMeta(
        no=page_record.no,
        title=title,
        source_url=page_record.source_url,
        route_path=source_path_to_route(page_record.source_path),
        file=output_file.relative_to(OUTPUT_ROOT).as_posix(),
        updated_text=update_text,
    )


def build_manifest(pages: list[PageMeta], generated_at: str) -> dict[str, object]:
    routes: dict[str, str] = {
        "/rance-world-note/": HOME_FILE.relative_to(OUTPUT_ROOT).as_posix(),
        "/rance-world-note": HOME_FILE.relative_to(OUTPUT_ROOT).as_posix(),
        "/rance-world-note/l/": LIST_FILE.relative_to(OUTPUT_ROOT).as_posix(),
        "/rance-world-note/l": LIST_FILE.relative_to(OUTPUT_ROOT).as_posix(),
        "/rance-world-note/d/": LIST_FILE.relative_to(OUTPUT_ROOT).as_posix(),
        "/rance-world-note/d": LIST_FILE.relative_to(OUTPUT_ROOT).as_posix(),
    }
    for page in pages:
        routes[page.route_path] = page.file
        routes[page.route_path.rstrip("/")] = page.file
    return {
        "generated_at": generated_at,
        "site_title": "Rance Wiki Local Mirror",
        "output_root": OUTPUT_ROOT.as_posix(),
        "routes": routes,
        "pages": [asdict(page) for page in pages],
    }


def build_vercel_routes(manifest_routes: dict[str, str]) -> dict[str, str]:
    routes: dict[str, str] = {}
    for route, target in manifest_routes.items():
        canonical_route = route if route.endswith("/") else route + "/"
        existing_target = routes.get(canonical_route)
        if existing_target is not None and existing_target != target:
            raise ValueError(f"Conflicting Vercel route for {canonical_route}: {existing_target} != {target}")
        routes[canonical_route] = target
    return routes


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a local mirror of Seesaa Wiki pages.")
    parser.add_argument("--limit", type=int, default=None, help="Only build the first N pages.")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS, help="Parallel page fetch workers.")
    parser.add_argument("--force", action="store_true", help="Rebuild pages even if output HTML already exists.")
    args = parser.parse_args()

    if not CSV_PATH.exists():
        raise SystemExit(f"Missing CSV: {CSV_PATH}")

    write_support_files()
    PAGE_ROOT.mkdir(parents=True, exist_ok=True)

    page_records = read_page_records(limit=args.limit)
    total = len(page_records)
    print(f"Building {total} pages into {OUTPUT_ROOT}")

    results: list[PageMeta] = []
    completed = 0
    pending_records: list[PageRecord] = []
    for record in page_records:
        existing = None if args.force else read_existing_page_meta(record)
        if existing is None:
            pending_records.append(record)
            continue
        results.append(existing)
        completed += 1
        if completed == total or completed % 100 == 0:
            print(f"[{completed}/{total}] reused existing page {record.no}: {existing.title}")

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as executor:
        future_map = {executor.submit(process_page, record): record for record in pending_records}
        for future in as_completed(future_map):
            record = future_map[future]
            page_meta = future.result()
            results.append(page_meta)
            completed += 1
            if completed == total or completed % 25 == 0:
                print(f"[{completed}/{total}] {record.no}: {page_meta.title}")

    results.sort(key=lambda item: item.no)
    generated_at = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    menu_page = next((page for page in results if page.source_url == "https://seesaawiki.jp/rance-world-note/d/MenuBar1"), None)
    menu_html = extract_page_content_html(menu_page) if menu_page else ""
    HOME_FILE.parent.mkdir(parents=True, exist_ok=True)
    HOME_FILE.write_text(build_home_html(len(results), generated_at, menu_html), encoding="utf-8")
    LIST_FILE.write_text(build_list_html(results, generated_at), encoding="utf-8")

    manifest = build_manifest(results, generated_at)
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    vercel_routes = build_vercel_routes(manifest["routes"])  # type: ignore[arg-type]
    VERCEL_ROUTES_PATH.write_text(json.dumps(vercel_routes, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote manifest: {MANIFEST_PATH}")
    print(f"Wrote Vercel routes: {VERCEL_ROUTES_PATH}")
    print(f"Pages: {len(results)}")


if __name__ == "__main__":
    main()
