# Meu Fla

App web (PWA) com jogos, resultados, notícias e vídeos do Flamengo. Custo zero: GitHub Pages para hospedar e GitHub Actions para atualizar os dados.

**App:** https://daniel-burla.github.io/meu-fla/

## Como instalar no iPhone

Abra o link no Safari, toque no botão de compartilhar e escolha "Adicionar à Tela de Início".

## Como funciona

| Aba | Fonte | Atualização |
|---|---|---|
| Jogos | API pública da ESPN, direto do navegador | a cada abertura do app |
| Notícias | RSS do Google News e dos sites, via `scripts/fetch.py` | a cada 30 min pelo GitHub Actions |
| Vídeos | RSS dos canais do YouTube, via `scripts/fetch.py` | a cada 30 min pelo GitHub Actions |

Jogos vêm ao vivo porque a ESPN libera CORS. Notícias e vídeos passam pelo Action porque esses feeds bloqueiam chamadas do navegador; o resultado fica em `data/news.json` e `data/videos.json`.

## Arquivos

```
index.html       o app inteiro (HTML, CSS e JS, sem framework)
icons/           escudo e ícones da tela inicial, gerados por scripts/gerar-icones.py
manifest.json    dados da PWA
sw.js            service worker (abre offline com o último conteúdo)
scripts/fetch.py coletor dos feeds (só biblioteca padrão do Python)
data/*.json      saída do coletor
.github/workflows/update.yml   agendamento a cada 30 min
```

## Mudar as fontes

Tudo fica no topo de `scripts/fetch.py`.

Nova fonte de notícias, em `NEWS_SOURCES`:

```python
{"id": "netflu", "nome": "NetFlu", "tipo": "rss", "url": "https://netflu.com.br/feed/", "exigir_flamengo": False}
```

Use `"tipo": "google-news"` com `"dominio"` quando o site não tiver RSS próprio. Deixe `exigir_flamengo` em `True` para sites que cobrem vários times.

Novo canal de vídeo, em `YOUTUBE_CHANNELS`: pegue o ID do canal (abra a página do canal e procure `/channel/UC...` no código-fonte) e some à lista.

## Refazer os ícones

`python3 scripts/gerar-icones.py` baixa o escudo e regrava os três PNG. Só usa a biblioteca padrão do Python, sem Pillow.

Para testar antes de publicar:

```bash
python3 scripts/fetch.py
python3 -m http.server 8787   # abre http://localhost:8787
```

## Fora do escopo por enquanto

Notificações push, tabela do Brasileirão, Carioca e Mundial, e busca de vídeos pela YouTube Data API (precisa de chave, gratuita).

## Nota para quem for editar

O GitHub Actions faz commit em `data/`. Antes de trabalhar aqui, rode `git pull --rebase`. Se der conflito nos JSON, resolva ficando com qualquer versão e rode `python3 scripts/fetch.py` de novo. Nunca use `-s ours` nesse rebase: ele descarta o seu commit.
