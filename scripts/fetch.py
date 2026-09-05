#!/usr/bin/env python3
"""Coletor do Meu Fla.

Lê feeds RSS de notícias e canais do YouTube e grava data/news.json e
data/videos.json. Só usa a biblioteca padrão do Python.

Para adicionar uma fonte de notícias ou um canal, edite as listas abaixo.
"""

import json
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

USER_AGENT = "Mozilla/5.0 (compatible; MeuFla/1.0; +https://github.com/daniel-burla/meu-fla)"
TIMEOUT = 25

# ---------------------------------------------------------------------------
# Fontes de notícias
# tipo "google-news": busca "Flamengo site:<dominio>" no Google News RSS.
# tipo "rss": lê o feed RSS diretamente.
# ---------------------------------------------------------------------------
# exigir_flamengo: True descarta manchetes que não citam o Flamengo. Use False
# apenas em sites 100% rubro-negros.
NEWS_SOURCES = [
    {"id": "ge", "nome": "ge", "tipo": "google-news", "dominio": "ge.globo.com", "exigir_flamengo": True},
    {"id": "espn", "nome": "ESPN Brasil", "tipo": "google-news", "dominio": "espn.com.br", "exigir_flamengo": True},
    {"id": "colunadofla", "nome": "Coluna do Fla", "tipo": "rss", "url": "https://colunadofla.com/feed/", "exigir_flamengo": False},
    {"id": "lance", "nome": "Lance!", "tipo": "google-news", "dominio": "lance.com.br", "exigir_flamengo": True},
    {"id": "uol", "nome": "UOL", "tipo": "google-news", "dominio": "uol.com.br", "exigir_flamengo": True},
]

# Termos que marcam uma manchete como assunto do Flamengo.
TERMOS_FLAMENGO = re.compile(
    r"flameng|meng[aã]o|\bmengo\b|rubro-?negr|\bfla\b|maracan[ãa]|ninho do urubu|g[áa]vea|"
    r"filipe lu[íi]s|na[çc][ãa]o rubro",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Canais do YouTube
# somente_flamengo: True mantém apenas vídeos com "flamengo" no título
# (para canais que cobrem vários times).
# ---------------------------------------------------------------------------
YOUTUBE_CHANNELS = [
    {"id": "UCOa-WaNwQaoyFHLCDk7qKIw", "nome": "Flamengo TV", "somente_flamengo": False},
    {"id": "UCZiYbVptd3PVPf4f6eR6UaQ", "nome": "CazéTV", "somente_flamengo": True},
    {"id": "UCw5-xj3AKqEizC7MvHaIPqA", "nome": "ESPN Brasil", "somente_flamengo": True},
]

MAX_NEWS = 150
MAX_VIDEOS = 60

DESTAQUE_PATTERN = re.compile(r"\b(gols?|melhores momentos|highlights)\b", re.IGNORECASE)


def fetch(url: str) -> bytes:
    req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/xml, text/xml, */*"})
    with urlopen(req, timeout=TIMEOUT) as resp:
        return resp.read()


def parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    value = value.strip()
    try:
        dt = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


# Boilerplate do WordPress: "ATENÇÃO: O post <título> apareceu primeiro em <site> ."
BOILERPLATE = re.compile(r"^\s*(aten[çc][ãa]o:\s*)?o post .*?apareceu primeiro em .*?\s\.\s*", re.IGNORECASE)


def clean_text(value: str | None, limit: int = 220) -> str:
    if not value:
        return ""
    text = re.sub(r"<[^>]+>", " ", value)
    text = unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    text = BOILERPLATE.sub("", text)
    if len(text) > limit:
        text = text[: limit - 1].rstrip() + "…"
    return text


def normalize_title(title: str) -> str:
    title = title.lower()
    title = re.sub(r"\s+-\s+[^-]+$", "", title)  # remove " - ge" que o Google News anexa
    title = re.sub(r"[^a-z0-9à-ú ]", "", title)
    return re.sub(r"\s+", " ", title).strip()


def google_news_url(domain: str) -> str:
    query = quote(f"Flamengo site:{domain}")
    return f"https://news.google.com/rss/search?q={query}&hl=pt-BR&gl=BR&ceid=BR:pt-419"


def parse_rss_items(xml_bytes: bytes, source: dict) -> list[dict]:
    root = ET.fromstring(xml_bytes)
    items = []
    for item in root.iter("item"):
        title = clean_text(item.findtext("title"), limit=300)
        link = (item.findtext("link") or "").strip()
        if not title or not link:
            continue
        if source["tipo"] == "google-news":
            # O Google News anexa " - <veículo>" ao título; remove para exibição limpa.
            title = re.sub(r"\s+-\s+[^-]+$", "", title)
        if source.get("exigir_flamengo") and not TERMOS_FLAMENGO.search(title):
            continue
        published = parse_date(item.findtext("pubDate") or item.findtext("{http://purl.org/dc/elements/1.1/}date"))
        summary = clean_text(item.findtext("description"))
        if source["tipo"] == "google-news":
            summary = ""  # descrição do Google News é só HTML de links relacionados
        items.append(
            {
                "titulo": title,
                "link": link,
                "data": published.isoformat() if published else None,
                "fonte": source["id"],
                "fonteNome": source["nome"],
                "resumo": summary,
            }
        )
    return items


def collect_news() -> dict:
    all_items: list[dict] = []
    status = {}
    for source in NEWS_SOURCES:
        url = source["url"] if source["tipo"] == "rss" else google_news_url(source["dominio"])
        try:
            items = parse_rss_items(fetch(url), source)
            status[source["id"]] = {"ok": True, "itens": len(items)}
            all_items.extend(items)
            print(f"[news] {source['nome']}: {len(items)} itens", file=sys.stderr)
        except Exception as exc:  # noqa: BLE001
            status[source["id"]] = {"ok": False, "erro": str(exc)[:200]}
            print(f"[news] {source['nome']}: ERRO {exc}", file=sys.stderr)

    seen: set[str] = set()
    deduped = []
    for item in sorted(all_items, key=lambda i: i["data"] or "", reverse=True):
        key = normalize_title(item["titulo"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)

    return {
        "atualizadoEm": datetime.now(timezone.utc).isoformat(),
        "fontes": [{"id": s["id"], "nome": s["nome"], **status.get(s["id"], {})} for s in NEWS_SOURCES],
        "itens": deduped[:MAX_NEWS],
    }


ATOM = "{http://www.w3.org/2005/Atom}"
YT = "{http://www.youtube.com/xml/schemas/2015}"


def collect_videos() -> dict:
    videos: list[dict] = []
    status = {}
    for channel in YOUTUBE_CHANNELS:
        url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel['id']}"
        try:
            root = ET.fromstring(fetch(url))
            count = 0
            for entry in root.findall(f"{ATOM}entry"):
                video_id = entry.findtext(f"{YT}videoId")
                title = clean_text(entry.findtext(f"{ATOM}title"), limit=200)
                if not video_id or not title:
                    continue
                mentions_fla = bool(TERMOS_FLAMENGO.search(title))
                if channel["somente_flamengo"] and not mentions_fla:
                    continue
                published = parse_date(entry.findtext(f"{ATOM}published"))
                destaque = bool(DESTAQUE_PATTERN.search(title)) and (mentions_fla or not channel["somente_flamengo"])
                videos.append(
                    {
                        "videoId": video_id,
                        "titulo": title,
                        "data": published.isoformat() if published else None,
                        "canal": channel["nome"],
                        "thumb": f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
                        "url": f"https://www.youtube.com/watch?v={video_id}",
                        "destaque": destaque,
                    }
                )
                count += 1
            status[channel["id"]] = {"ok": True, "itens": count}
            print(f"[videos] {channel['nome']}: {count} vídeos", file=sys.stderr)
        except Exception as exc:  # noqa: BLE001
            status[channel["id"]] = {"ok": False, "erro": str(exc)[:200]}
            print(f"[videos] {channel['nome']}: ERRO {exc}", file=sys.stderr)

    videos.sort(key=lambda v: v["data"] or "", reverse=True)
    return {
        "atualizadoEm": datetime.now(timezone.utc).isoformat(),
        "canais": [{"id": c["id"], "nome": c["nome"], **status.get(c["id"], {})} for c in YOUTUBE_CHANNELS],
        "itens": videos[:MAX_VIDEOS],
    }


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def main() -> int:
    news = collect_news()
    videos = collect_videos()
    write_json(DATA / "news.json", news)
    write_json(DATA / "videos.json", videos)
    print(f"news: {len(news['itens'])} itens | videos: {len(videos['itens'])} itens", file=sys.stderr)
    # Falha só se nenhuma fonte respondeu, para o Action não sobrescrever dados bons com vazio.
    if not news["itens"] and not videos["itens"]:
        print("Nenhuma fonte respondeu.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
