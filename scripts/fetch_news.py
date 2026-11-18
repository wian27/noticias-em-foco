#!/usr/bin/env python3
"""Build national and local attributed news indexes for the Em Foco GitHub Pages site."""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import html
import json
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse


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
GDELT_ENDPOINT = "https://api.gdeltproject.org/api/v2/doc/doc"

# State capitals provide nationwide city coverage. Additional Mato Grosso cities
# are included because the portal's audience has a strong regional interest there.
STATE_NAMES = {
    "AC": "Acre", "AL": "Alagoas", "AP": "Amapá", "AM": "Amazonas",
    "BA": "Bahia", "CE": "Ceará", "DF": "Distrito Federal", "ES": "Espírito Santo",
    "GO": "Goiás", "MA": "Maranhão", "MT": "Mato Grosso", "MS": "Mato Grosso do Sul",
    "MG": "Minas Gerais", "PA": "Pará", "PB": "Paraíba", "PR": "Paraná",
    "PE": "Pernambuco", "PI": "Piauí", "RJ": "Rio de Janeiro", "RN": "Rio Grande do Norte",
    "RS": "Rio Grande do Sul", "RO": "Rondônia", "RR": "Roraima",
    "SC": "Santa Catarina", "SP": "São Paulo", "SE": "Sergipe", "TO": "Tocantins",
}
CAPITALS = [
    ("Rio Branco", "AC", -9.975, -67.824), ("Maceió", "AL", -9.665, -35.735),
    ("Macapá", "AP", 0.035, -51.070), ("Manaus", "AM", -3.119, -60.021),
    ("Salvador", "BA", -12.977, -38.501), ("Fortaleza", "CE", -3.718, -38.543),
    ("Brasília", "DF", -15.794, -47.883), ("Vitória", "ES", -20.316, -40.313),
    ("Goiânia", "GO", -16.687, -49.265), ("São Luís", "MA", -2.530, -44.307),
    ("Cuiabá", "MT", -15.601, -56.097), ("Campo Grande", "MS", -20.470, -54.620),
    ("Belo Horizonte", "MG", -19.917, -43.935), ("Belém", "PA", -1.456, -48.504),
    ("João Pessoa", "PB", -7.120, -34.845), ("Curitiba", "PR", -25.428, -49.273),
    ("Recife", "PE", -8.048, -34.877), ("Teresina", "PI", -5.092, -42.804),
    ("Rio de Janeiro", "RJ", -22.907, -43.173), ("Natal", "RN", -5.795, -35.211),
    ("Porto Alegre", "RS", -30.035, -51.218), ("Porto Velho", "RO", -8.761, -63.900),
    ("Boa Vista", "RR", 2.824, -60.675), ("Florianópolis", "SC", -27.595, -48.548),
    ("São Paulo", "SP", -23.551, -46.633), ("Aracaju", "SE", -10.947, -37.073),
    ("Palmas", "TO", -10.249, -48.324),
]
MT_CITIES = [
    ("Várzea Grande", "MT", -15.646, -56.132),
    ("Rondonópolis", "MT", -16.470, -54.635),
    ("Sinop", "MT", -11.860, -55.509),
    ("Sorriso", "MT", -12.546, -55.721),
    ("Lucas do Rio Verde", "MT", -13.070, -55.920),
    ("Nova Mutum", "MT", -13.837, -56.082),
    ("Tangará da Serra", "MT", -14.622, -57.493),
    ("Cáceres", "MT", -16.076, -57.681),
    ("Barra do Garças", "MT", -15.891, -52.257),
    ("Primavera do Leste", "MT", -15.556, -54.296),
    ("Alta Floresta", "MT", -9.876, -56.086),
    ("Campo Novo do Parecis", "MT", -13.676, -57.890),
]
CITY_REGIONS = CAPITALS + MT_CITIES


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


class RSSImageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.urls: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "img":
            return
        values = dict(attrs)
        for key in ("src", "data-src", "data-original"):
            value = values.get(key)
            if value:
                self.urls.append(value.strip())
        srcset = values.get("srcset")
        if srcset:
            first = srcset.split(",", 1)[0].strip().split()
            if first:
                self.urls.append(first[0])


def official_image_url(value: str, article_url: str) -> str | None:
    if not value:
        return None
    image_url = urljoin(article_url, html.unescape(value.strip()))
    parsed = urlparse(image_url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not (host == "ebc.com.br" or host.endswith(".ebc.com.br")):
        return None
    return image_url


def feed_image_url(item: ET.Element, article_url: str) -> str | None:
    # RSS media:content, media:thumbnail and image enclosures are common feed formats.
    for node in item.iter():
        tag = local_name(node.tag)
        attrs = {local_name(key): value for key, value in node.attrib.items()}
        if tag in {"thumbnail", "content", "enclosure"}:
            media_type = (attrs.get("type") or "").lower()
            medium = (attrs.get("medium") or "").lower()
            if tag == "enclosure" and media_type and not media_type.startswith("image/"):
                continue
            if media_type and not media_type.startswith("image/") and medium != "image":
                continue
            candidate = attrs.get("url") or attrs.get("href") or attrs.get("src")
            image = official_image_url(candidate or "", article_url)
            if image:
                return image
        if tag in {"description", "encoded"}:
            parser = RSSImageParser()
            parser.feed("".join(node.itertext()))
            for candidate in parser.urls:
                image = official_image_url(candidate, article_url)
                if image:
                    return image
    return None



class ArticleImageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.urls: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.lower(): value for key, value in attrs}
        if tag.lower() == "meta":
            key = (values.get("property") or values.get("name") or "").lower()
            if key in {"og:image", "og:image:url", "twitter:image", "twitter:image:src"}:
                content = values.get("content")
                if content:
                    self.urls.append(content.strip())
        elif tag.lower() == "link" and "image_src" in (values.get("rel") or "").lower():
            href = values.get("href")
            if href:
                self.urls.append(href.strip())


def article_image_url(article_url: str) -> str | None:
    request = urllib.request.Request(
        article_url,
        headers={"User-Agent": "Mozilla/5.0 (compatible; NoticiasEmFoco/1.0; +https://github.com/wian27/noticias-em-foco)",
                 "Accept": "text/html,application/xhtml+xml"},
    )
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            if response.status != 200:
                return None
            parser = ArticleImageParser()
            parser.feed(response.read(1_500_000).decode("utf-8", errors="replace"))
    except (OSError, urllib.error.URLError, TimeoutError, UnicodeError):
        return None
    for candidate in parser.urls:
        image = official_image_url(candidate, article_url)
        if image:
            return image
    return None

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


def parse_gdelt_date(value: str) -> str | None:
    if re.fullmatch(r"\d{8}T\d{6}Z", value or ""):
        try:
            parsed = dt.datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=dt.timezone.utc)
            return parsed.isoformat().replace("+00:00", "Z")
        except ValueError:
            return None
    return parse_date(value)


def slug(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", normalized.lower()).strip("-")


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
            "imageUrl": feed_image_url(item, link),
        })
    return entries


def query_gdelt(query: str, region_key: str, region_name: str, state_code: str) -> list[dict[str, str | None]]:
    params = urllib.parse.urlencode({
        "query": query,
        "mode": "ArtList",
        "format": "json",
        "maxrecords": "12",
        "timespan": "7d",
        "sort": "DateDesc",
    })
    request = urllib.request.Request(
        GDELT_ENDPOINT + "?" + params,
        headers={"User-Agent": "NoticiasEmFoco/1.0 (+https://github.com/wian27/noticias-em-foco)",
                 "Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=25) as response:
        if response.status != 200:
            raise urllib.error.URLError(f"HTTP {response.status}")
        payload = json.loads(response.read().decode("utf-8"))

    articles = []
    for row in payload.get("articles", []):
        title = clean_summary(row.get("title", ""))
        link = row.get("url", "")
        parsed_url = urlparse(link)
        if not title or parsed_url.scheme != "https" or not parsed_url.hostname:
            continue
        source = (row.get("domain") or parsed_url.hostname or "Fonte externa").removeprefix("www.")
        image_url = row.get("socialimage") or row.get("image")
        image_parsed = urlparse(image_url or "")
        articles.append({
            "title": title[:240],
            "summary": "",
            "url": link,
            "source": source,
            "category": "Local",
            "publishedAt": parse_gdelt_date(row.get("seendate", "")),
            "regionKey": region_key,
            "regionName": region_name,
            "stateCode": state_code,
            "imageUrl": image_url if image_parsed.scheme == "https" else None,
        })
    return articles


def build_local_news() -> dict:
    locations = [
        {"key": f"state:{code}", "type": "state", "name": name, "stateCode": code}
        for code, name in STATE_NAMES.items()
    ]
    locations.extend(
        {"key": f"city:{slug(city)}-{code.lower()}", "type": "city", "name": city,
         "stateCode": code, "lat": lat, "lon": lon}
        for city, code, lat, lon in CITY_REGIONS
    )
    return {
        "fetchedAt": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
        "source": "GDELT DOC 2.0 · consulta regional sob demanda",
        "locations": locations,
        "regions": {},
        "articles": [],
    }

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/news.json")
    parser.add_argument("--local-output", default="data/local-news.json")
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
    # Some official RSS entries omit media tags. Read the article's Open Graph
    # metadata for the first visible stories so their cards can still show photos.
    image_targets = [item for item in articles[:18] if not item.get("imageUrl")]
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        for item, image in zip(image_targets, pool.map(lambda row: article_image_url(row["url"]), image_targets)):
            if image:
                item["imageUrl"] = image
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
    local_destination = Path(args.local_output)
    local_destination.parent.mkdir(parents=True, exist_ok=True)
    local_destination.write_text(json.dumps(build_local_news(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Gravadas {len(articles)} manchetes e notícias locais em {destination.parent}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
