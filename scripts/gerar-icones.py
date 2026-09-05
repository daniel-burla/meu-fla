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

def gerar(origem, destino, size, fundo=(255, 255, 255), margem=0.14):
    w, h, linhas = ler_png(origem)
    lado = int(size * (1 - 2 * margem))
    desloc = (size - lado) // 2
    saida = [[fundo] * size for _ in range(size)]
    for y in range(lado):
        sy = min(h - 1, y * h // lado)
        origem_linha = linhas[sy]
        for x in range(lado):
            sx = min(w - 1, x * w // lado)
            o = sx * 4
            r, g, b, a = origem_linha[o], origem_linha[o+1], origem_linha[o+2], origem_linha[o+3]
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



# --- distintivo do cabeçalho: escudo dentro de um círculo branco, fora transparente
def grava_rgba(caminho, size, pixels):
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

def recorte(origem, destino, size=180):
    """Escudo em RGBA, fundo transparente, sem moldura."""
    w, h, linhas = ler_png(origem)
    saida = [[(0, 0, 0, 0)] * size for _ in range(size)]
    for y in range(size):
        sy = min(h - 1, y * h // size)
        linha = linhas[sy]
        for x in range(size):
            sx = min(w - 1, x * w // size)
            o = sx * 4
            saida[y][x] = (linha[o], linha[o+1], linha[o+2], linha[o+3])
    grava_rgba(destino, size, saida)
    print(destino, f"{size}x{size} RGBA")


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
