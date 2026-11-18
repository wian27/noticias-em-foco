#!/usr/bin/env python3
"""Build a small attributed news index from Agência Brasil's public RSS feeds."""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import re
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlparse


FEEDS = [
    ("Brasil", "https://agenciabrasil.ebc.com.br/rss/geral/feed.xml"),
    ("Mundo", "https://agenciabrasil.ebc.com.br/rss/internacional/feed.xml"),
    ("Economia", "https://agenciabrasil.ebc.com.br/rss/economia/feed.xml"),
    ("Política", "https://agenciabrasil.ebc.com.br/rss/politica/feed.xml"),
    ("Saúde", "https://agenciabrasil.ebc.com.br/rss/saude/feed.xml"),
    ("Educação", "https://agenciabrasil.ebc.com.br/rss/educacao/feed.xml"),
    ("Esportes", "https://agenciabrasil.ebc.com.br/rss/esportes/feed.xml"),
]
SOURCE = "Agência Brasil / EBC"
ALLOWED_HOST = "agenciabrasil.ebc.com.br"


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].split(":")[-1].lower()


def child_text(element: ET.Element, name: str) -> str:
    for child in element.iter():
        if local_name(child.tag) == name.lower() and child is not element:
            return "".join(child.itertext()).strip()
    return ""


def clean_summary(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value or "")
    value = html.unescape(value)
    value = re.sub(r"\s+", " ", value).strip()
    if len(value) > 320:
        value = value[:320].rsplit(" ", 1)[0].rstrip(" ,.;:-") + "…"
    return value


def parse_date(value: str) -> str | None:
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.timezone.utc)
        return parsed.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")
    except (TypeError, ValueError, OverflowError):
        try:
            parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=dt.timezone.utc)
            return parsed.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")
        except (TypeError, ValueError, OverflowError):
            return None


def read_feed(category: str, url: str) -> list[dict[str, str | None]]:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "NoticiasEmFoco/1.0 (+https://github.com/wian27/noticias-em-foco)",
                 "Accept": "application/rss+xml, application/xml, text/xml;q=0.9"},
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        if response.status != 200:
            raise urllib.error.URLError(f"HTTP {response.status}")
        root = ET.fromstring(response.read())

    entries = []
    for item in root.iter():
        if local_name(item.tag) != "item":
            continue
        title = clean_summary(child_text(item, "title"))
        link = child_text(item, "link").strip()
        parsed_url = urlparse(link)
        if not title or parsed_url.scheme != "https" or parsed_url.hostname != ALLOWED_HOST:
            continue
        description = child_text(item, "description") or child_text(item, "encoded")
        date_text = child_text(item, "pubdate") or child_text(item, "date")
        entries.append({
            "title": title[:240],
            "summary": clean_summary(description),
            "url": link,
            "source": SOURCE,
            "category": category,
            "publishedAt": parse_date(date_text),
        })
    return entries


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/news.json")
    args = parser.parse_args()
    all_items: dict[str, dict[str, str | None]] = {}
    errors = []
    for category, url in FEEDS:
        try:
            for item in read_feed(category, url):
                all_items.setdefault(item["url"], item)
        except (OSError, ET.ParseError, urllib.error.URLError, TimeoutError) as exc:
            errors.append(f"{category}: {exc}")

    articles = sorted(
        all_items.values(),
        key=lambda item: item["publishedAt"] or "",
        reverse=True,
    )[:36]
    payload = {
        "fetchedAt": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "source": SOURCE,
        "articles": articles,
    }
    if not articles:
        payload["error"] = "As fontes RSS não responderam. Tente novamente mais tarde."
        print("Nenhum feed RSS retornou notícias: " + "; ".join(errors), file=sys.stderr)

    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Gravadas {len(articles)} manchetes em {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
