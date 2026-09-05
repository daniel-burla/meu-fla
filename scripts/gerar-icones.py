"""Gera os ícones da PWA a partir do escudo do Flamengo, sem dependências.

Baixa o escudo do CDN da ESPN e escreve icons/icon-192.png, icons/icon-512.png
(fundo branco, para a tela inicial do iPhone) e icons/escudo.png (fundo
transparente, usado no cabeçalho do app).

Rode com: python3 scripts/gerar-icones.py
"""
import struct, sys, tempfile, zlib
from pathlib import Path
from urllib.request import Request, urlopen

ESCUDO_URL = "https://a.espncdn.com/i/teamlogos/soccer/500/819.png"
RAIZ = Path(__file__).resolve().parent.parent

def ler_png(caminho):
    d = open(caminho, "rb").read()
    assert d[:8] == b"\x89PNG\r\n\x1a\n"
    pos, idat, info = 8, b"", None
    while pos < len(d):
        (ln,) = struct.unpack(">I", d[pos:pos+4]); tag = d[pos+4:pos+8]
        dados = d[pos+8:pos+8+ln]; pos += 12 + ln
        if tag == b"IHDR":
            info = struct.unpack(">IIBBBBB", dados)
        elif tag == b"IDAT":
            idat += dados
        elif tag == b"IEND":
            break
    w, h, bd, ct = info[0], info[1], info[2], info[3]
    assert (bd, ct) == (8, 6), f"esperava RGBA 8 bits, veio {bd}/{ct}"
    raw = zlib.decompress(idat)
    bpp, stride = 4, w * 4
    linhas, ant, i = [], bytearray(stride), 0
    for _ in range(h):
        f = raw[i]; i += 1
        linha = bytearray(raw[i:i+stride]); i += stride
        if f == 1:
            for x in range(bpp, stride): linha[x] = (linha[x] + linha[x-bpp]) & 255
        elif f == 2:
            for x in range(stride): linha[x] = (linha[x] + ant[x]) & 255
        elif f == 3:
            for x in range(stride):
                a = linha[x-bpp] if x >= bpp else 0
                linha[x] = (linha[x] + ((a + ant[x]) >> 1)) & 255
        elif f == 4:
            for x in range(stride):
                a = linha[x-bpp] if x >= bpp else 0
                b = ant[x]; c = ant[x-bpp] if x >= bpp else 0
                p = a + b - c
                pa, pb, pc = abs(p-a), abs(p-b), abs(p-c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                linha[x] = (linha[x] + pr) & 255
        linhas.append(linha); ant = linha
    return w, h, linhas

def grava_png(caminho, size, pixels):
    raw = b"".join(b"\x00" + bytes(v for p in linha for v in p) for linha in pixels)
    def bloco(tag, dados):
        c = tag + dados
        return struct.pack(">I", len(dados)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)
    open(caminho, "wb").write(
        b"\x89PNG\r\n\x1a\n"
        + bloco(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
        + bloco(b"IDAT", zlib.compress(raw, 9))
        + bloco(b"IEND", b"")
    )

INF = 10 ** 9


def distancia_ate_o_escudo(w, h, linhas, limiar=128):
    """Distância aproximada de cada pixel até o escudo, em terços de pixel.

    Chamfer 3-4 em duas passagens. É O(n) e dá um contorno arredondado,
    bem melhor que dilatar com um quadrado.
    """
    d = [[0 if linhas[y][x * 4 + 3] >= limiar else INF for x in range(w)] for y in range(h)]
    for y in range(h):
        linha = d[y]
        acima = d[y - 1] if y else None
        for x in range(w):
            if linha[x] == 0:
                continue
            m = linha[x]
            if x: m = min(m, linha[x - 1] + 3)
            if acima:
                m = min(m, acima[x] + 3)
                if x: m = min(m, acima[x - 1] + 4)
                if x + 1 < w: m = min(m, acima[x + 1] + 4)
            linha[x] = m
    for y in range(h - 1, -1, -1):
        linha = d[y]
        abaixo = d[y + 1] if y + 1 < h else None
        for x in range(w - 1, -1, -1):
            if linha[x] == 0:
                continue
            m = linha[x]
            if x + 1 < w: m = min(m, linha[x + 1] + 3)
            if abaixo:
                m = min(m, abaixo[x] + 3)
                if x + 1 < w: m = min(m, abaixo[x + 1] + 4)
                if x: m = min(m, abaixo[x - 1] + 4)
            linha[x] = m
    return d


def com_contorno(w, h, linhas, raio, cor=(255, 255, 255)):
    """Devolve o escudo sobre um contorno da mesma forma, para destacá-lo do fundo."""
    margem = raio + 2
    nw, nh = w + 2 * margem, h + 2 * margem
    largas = []
    vazia = bytearray(nw * 4)
    for _ in range(margem):
        largas.append(bytearray(vazia))
    for y in range(h):
        nova = bytearray(vazia)
        nova[margem * 4 : margem * 4 + w * 4] = linhas[y]
        largas.append(nova)
    for _ in range(margem):
        largas.append(bytearray(vazia))

    dist = distancia_ate_o_escudo(nw, nh, largas)
    limite = raio * 3
    saida = []
    for y in range(nh):
        origem = largas[y]
        linha_saida = []
        for x in range(nw):
            o = x * 4
            r, g, b, a = origem[o], origem[o + 1], origem[o + 2], origem[o + 3]
            dd = dist[y][x]
            # alpha do contorno: cheio até o raio, some no último pixel
            if dd <= limite:
                ac = 255
            elif dd <= limite + 3:
                ac = int(255 * (limite + 3 - dd) / 3)
            else:
                ac = 0
            if a == 0 and ac == 0:
                linha_saida.append((0, 0, 0, 0))
                continue
            # escudo por cima do contorno
            fa = a + ac * (255 - a) // 255
            if fa == 0:
                linha_saida.append((0, 0, 0, 0))
                continue
            mistura = lambda c, cc: (c * a + cc * ac * (255 - a) // 255) // fa
            linha_saida.append((mistura(r, cor[0]), mistura(g, cor[1]), mistura(b, cor[2]), fa))
        saida.append(linha_saida)
    return nw, nh, saida


def grava_rgba(caminho, size, pixels):
    """Grava PNG RGBA (colortype 6), preservando a transparência."""
    raw = b"".join(b"\x00" + bytes(v for p in linha for v in p) for linha in pixels)

    def bloco(tag, dados):
        c = tag + dados
        return struct.pack(">I", len(dados)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

    open(caminho, "wb").write(
        b"\x89PNG\r\n\x1a\n"
        + bloco(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
        + bloco(b"IDAT", zlib.compress(raw, 9))
        + bloco(b"IEND", b"")
    )


def media_area(w, h, linhas, size):
    """Redimensiona para size x size fazendo a média de cada bloco de origem.

    Trabalha com alpha pré-multiplicado: sem isso, os pixels transparentes da
    borda (que no PNG da ESPN são brancos) sujariam o contorno do escudo.
    """
    saida = []
    for y in range(size):
        y0, y1 = y * h // size, max(y * h // size + 1, (y + 1) * h // size)
        linha_saida = []
        for x in range(size):
            x0, x1 = x * w // size, max(x * w // size + 1, (x + 1) * w // size)
            sr = sg = sb = sa = n = 0
            for sy in range(y0, y1):
                origem = linhas[sy]
                for sx in range(x0, x1):
                    o = sx * 4
                    a = origem[o + 3]
                    sr += origem[o] * a
                    sg += origem[o + 1] * a
                    sb += origem[o + 2] * a
                    sa += a
                    n += 1
            if sa == 0:
                linha_saida.append((0, 0, 0, 0))
            else:
                linha_saida.append((sr // sa, sg // sa, sb // sa, sa // n))
        saida.append(linha_saida)
    return saida


def gerar(origem, destino, size, fundo=(255, 255, 255), margem=0.14):
    """Ícone da tela inicial: escudo centralizado sobre fundo opaco."""
    w, h, linhas = ler_png(origem)
    lado = int(size * (1 - 2 * margem))
    desloc = (size - lado) // 2
    escudo = media_area(w, h, linhas, lado)
    saida = [[fundo] * size for _ in range(size)]
    for y in range(lado):
        for x in range(lado):
            r, g, b, a = escudo[y][x]
            if a == 0:
                continue
            px = saida[y + desloc][x + desloc]
            saida[y + desloc][x + desloc] = (
                (r * a + px[0] * (255 - a)) // 255,
                (g * a + px[1] * (255 - a)) // 255,
                (b * a + px[2] * (255 - a)) // 255,
            )
    grava_png(destino, size, saida)
    print(destino, f"{size}x{size}")


def recorte(origem, destino, size=216, raio_contorno=10):
    """Escudo do cabeçalho: contorno branco na forma do escudo, fundo transparente.

    O contorno existe porque o escudo é vermelho e preto: sem ele, o preto some
    no fundo escuro do app e o vermelho some no cabeçalho vermelho.
    """
    w, h, linhas = ler_png(origem)
    nw, nh, pixels = com_contorno(w, h, linhas, raio_contorno)
    # media_area espera bytes por linha, então reempacota
    empacotado = [bytearray(v for px in linha for v in px) for linha in pixels]
    grava_rgba(destino, size, media_area(nw, nh, empacotado, size))
    print(destino, f"{size}x{size} RGBA, contorno {raio_contorno}px")


def baixar_escudo() -> str:
    req = Request(ESCUDO_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=25) as resp:
        dados = resp.read()
    destino = Path(tempfile.gettempdir()) / "escudo-flamengo.png"
    destino.write_bytes(dados)
    print(f"escudo baixado ({len(dados)} bytes)")
    return str(destino)


if __name__ == "__main__":
    origem = baixar_escudo()
    gerar(origem, str(RAIZ / "icons/icon-192.png"), 192)
    gerar(origem, str(RAIZ / "icons/icon-512.png"), 512)
    recorte(origem, str(RAIZ / "icons/escudo.png"))
