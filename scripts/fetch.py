#!/usr/bin/env python3
"""Coletor do Meu Fla.

Lê feeds de notícias e grava data/news.json. Só usa a biblioteca padrão do
Python.

Regras importantes:
- Cada fonte pode ter mais de uma URL. A primeira que responder vence.
- Se uma fonte falhar, os itens que ela já tinha no JSON anterior são
  mantidos (até MAX_IDADE_DIAS), então uma queda temporária não apaga nada.

Para mexer nas fontes, edite NEWS_SOURCES abaixo.
"""

import json
import re
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

UA_NAVEGADOR = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
TIMEOUT = 25
TENTATIVAS = 3
MAX_NEWS = 150
MAX_IDADE_DIAS = 10


def google_news(dominio: str) -> str:
    return (
        "https://news.google.com/rss/search?q="
        + quote(f"Flamengo site:{dominio}")
        + "&hl=pt-BR&gl=BR&ceid=BR:pt-419"
    )


def bing_news(dominio: str) -> str:
    return (
        "https://www.bing.com/news/search?q="
        + quote(f"Flamengo site:{dominio}")
        + "&format=RSS&setmkt=pt-BR&setlang=pt-BR"
    )


# ---------------------------------------------------------------------------
# Fontes de notícias.
#   urls            : tentadas em ordem até uma responder.
#   exigir_flamengo : descarta manchetes que não citam o clube. Deixe False
#                     apenas em sites 100% rubro-negros.
#   limpar_sufixo   : remove o " - Veículo" que agregadores anexam ao título.
# ---------------------------------------------------------------------------
NEWS_SOURCES = [
    {
        "id": "ge",
        "nome": "ge",
        # Feed nativo do ge por time. Agregadores só como reserva.
        "urls": ["https://pox.globo.com/rss/ge/futebol/times/flamengo", google_news("ge.globo.com"), bing_news("ge.globo.com")],
        "exigir_flamengo": False,
        "limpar_sufixo": True,
    },
    {
        "id": "espn",
        "nome": "ESPN Brasil",
        "urls": [google_news("espn.com.br"), bing_news("espn.com.br")],
        "exigir_flamengo": True,
        "limpar_sufixo": True,
    },
    {
        "id": "colunadofla",
        "nome": "Coluna do Fla",
        "urls": ["https://colunadofla.com/feed/", bing_news("colunadofla.com")],
        "exigir_flamengo": False,
        "limpar_sufixo": False,
    },
    {
        "id": "lance",
        "nome": "Lance!",
        "urls": [google_news("lance.com.br"), bing_news("lance.com.br")],
        "exigir_flamengo": True,
        "limpar_sufixo": True,
    },
    {
        "id": "uol",
        "nome": "UOL",
        "urls": [google_news("uol.com.br"), bing_news("uol.com.br")],
        "exigir_flamengo": True,
        "limpar_sufixo": True,
    },
]

TERMOS_FLAMENGO = re.compile(
    r"flameng|meng[aã]o|\bmengo\b|rubro-?negr|\bfla\b|maracan[ãa]|ninho do urubu|"
    r"g[áa]vea|filipe lu[íi]s|na[çc][ãa]o rubro",
    re.IGNORECASE,
)
# "ATENÇÃO: O post <título> apareceu primeiro em <site> ." (padrão WordPress)
BOILERPLATE = re.compile(r"^\s*(aten[çc][ãa]o:\s*)?o post .*?apareceu primeiro em .*?\s\.\s*", re.IGNORECASE)
SUFIXO_VEICULO = re.compile(r"\s+-\s+[^-]{2,40}$")

DC_DATE = "{http://purl.org/dc/elements/1.1/}date"


def fetch(url: str) -> bytes:
    """Baixa a URL com cara de navegador, com algumas tentativas."""
    erro = None
    for tentativa in range(TENTATIVAS):
        req = Request(
            url,
            headers={
                "User-Agent": UA_NAVEGADOR,
                "Accept": "application/rss+xml, application/atom+xml, application/xml;q=0.9, */*;q=0.8",
                "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.6",
            },
        )
        try:
            with urlopen(req, timeout=TIMEOUT) as resp:
                return resp.read()
        except (HTTPError, URLError, TimeoutError) as exc:
            erro = exc
            if tentativa < TENTATIVAS - 1:
                time.sleep(2 * (tentativa + 1))
    raise erro  # type: ignore[misc]


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
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


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


def chave(titulo: str) -> str:
    t = SUFIXO_VEICULO.sub("", titulo.lower())
    t = re.sub(r"[^a-z0-9à-ú ]", "", t)
    return re.sub(r"\s+", " ", t).strip()


def parse_news(xml_bytes: bytes, source: dict) -> list[dict]:
    root = ET.fromstring(xml_bytes)
    itens = []
    for item in root.iter("item"):
        titulo = clean_text(item.findtext("title"), limit=300)
        link = (item.findtext("link") or "").strip()
        if not titulo or not link:
            continue
        if source["limpar_sufixo"]:
            titulo = SUFIXO_VEICULO.sub("", titulo)
        if source["exigir_flamengo"] and not TERMOS_FLAMENGO.search(titulo):
            continue
        publicado = parse_date(item.findtext("pubDate") or item.findtext(DC_DATE))
        resumo = clean_text(item.findtext("description"))
        # Agregadores põem só HTML de links relacionados na descrição.
        if "news.google.com" in link or resumo.lower().startswith(titulo.lower()[:30]):
            resumo = ""
        itens.append(
            {
                "titulo": titulo,
                "link": link,
                "data": publicado.isoformat() if publicado else None,
                "fonte": source["id"],
                "fonteNome": source["nome"],
                "resumo": resumo,
            }
        )
    return itens


def carrega_anterior(caminho: Path) -> dict:
    try:
        return json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def recentes(itens: list[dict]) -> list[dict]:
    limite = (datetime.now(timezone.utc) - timedelta(days=MAX_IDADE_DIAS)).isoformat()
    return [i for i in itens if not i.get("data") or i["data"] >= limite]


def collect_news() -> dict:
    anterior = carrega_anterior(DATA / "news.json")
    antigos_por_fonte: dict[str, list[dict]] = {}
    for item in anterior.get("itens", []):
        antigos_por_fonte.setdefault(item.get("fonte", ""), []).append(item)

    todos: list[dict] = []
    status: dict[str, dict] = {}

    for source in NEWS_SOURCES:
        itens: list[dict] = []
        erro = ""
        for url in source["urls"]:
            try:
                itens = parse_news(fetch(url), source)
                if itens:
                    break
            except Exception as exc:  # noqa: BLE001
                erro = f"{type(exc).__name__}: {exc}"[:150]

        if itens:
            status[source["id"]] = {"ok": True, "itens": len(itens)}
            print(f"[news] {source['nome']}: {len(itens)} itens", file=sys.stderr)
        else:
            guardados = recentes(antigos_por_fonte.get(source["id"], []))
            itens = guardados
            status[source["id"]] = {"ok": bool(guardados), "itens": len(guardados), "aviso": erro or "sem itens"}
            print(f"[news] {source['nome']}: FALHOU ({erro or 'sem itens'}), reaproveitando {len(guardados)}", file=sys.stderr)
        todos.extend(itens)

    vistos: set[str] = set()
    final = []
    for item in sorted(todos, key=lambda i: i.get("data") or "", reverse=True):
        k = chave(item["titulo"])
        if k in vistos:
            continue
        vistos.add(k)
        final.append(item)

    return {
        "atualizadoEm": datetime.now(timezone.utc).isoformat(),
        "fontes": [{"id": s["id"], "nome": s["nome"], **status.get(s["id"], {})} for s in NEWS_SOURCES],
        "itens": final[:MAX_NEWS],
    }


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def main() -> int:
    news = collect_news()
    write_json(DATA / "news.json", news)
    print(f"news: {len(news['itens'])}", file=sys.stderr)
    if not news["itens"]:
        print("Nenhuma fonte respondeu e não havia dados guardados.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
