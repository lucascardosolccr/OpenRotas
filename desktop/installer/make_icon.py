# -*- coding: utf-8 -*-
"""OpenRotas Desktop — gerador do ÍCONE do aplicativo/instalador (§38).

Gera um openrotas.ico multi-resolução (16→256 px) com um monograma "OR" sobre um quadrado
arredondado na cor de destaque do produto. É executado em tempo de BUILD (build.ps1 / workflow),
então o binário .ico NÃO precisa ser versionado no git. Requer Pillow (já dependência da app);
se faltar, o chamador simplesmente segue sem ícone (o .iss trata SetupIconFile como opcional).

Uso:  python make_icon.py [saida.ico]
"""
from __future__ import annotations

import sys
from pathlib import Path

ACCENT = (59, 130, 246)      # azul da marca (#3B82F6) — mesmo tom do tema/janela/app
ACCENT2 = (96, 165, 250)     # #60A5FA (clareamento do gradiente)
INK = (255, 255, 255)
TAMANHOS = [16, 24, 32, 48, 64, 128, 256]


def _fonte(px: int):
    from PIL import ImageFont
    # tenta algumas fontes bold comuns; cai para a default do PIL se nenhuma existir.
    for nome in ("DejaVuSans-Bold.ttf", "Arialbd.ttf", "arialbd.ttf", "Arial Bold.ttf"):
        try:
            return ImageFont.truetype(nome, px)
        except Exception:
            continue
    try:
        return ImageFont.load_default(px)      # Pillow 10+: load_default aceita tamanho
    except Exception:
        from PIL import ImageFont as _IF
        return _IF.load_default()


def _render(tamanho: int):
    """Ícone da marca: quadrado arredondado com GRADIENTE da marca e o monograma de ROTA —
    dois 'waypoints' ligados por uma curva (o mesmo motivo do logo/splash/relatórios). Sem texto."""
    from PIL import Image, ImageDraw
    S = tamanho
    # Gradiente diagonal (canto inferior-esquerdo ACCENT → superior-direito ACCENT2).
    g = Image.new("RGB", (S, S), ACCENT)
    px = g.load()
    for y in range(S):
        for x in range(S):
            t = (x + (S - 1 - y)) / (2.0 * max(1, S - 1))
            px[x, y] = (int(ACCENT[0] + (ACCENT2[0] - ACCENT[0]) * t),
                        int(ACCENT[1] + (ACCENT2[1] - ACCENT[1]) * t),
                        int(ACCENT[2] + (ACCENT2[2] - ACCENT[2]) * t))
    # Clipe em quadrado arredondado.
    raio = max(2, int(S * 0.22))
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, S - 1, S - 1], radius=raio, fill=255)
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    img.paste(g, (0, 0), mask)
    d = ImageDraw.Draw(img)
    # Monograma de rota: curva de Bézier entre dois waypoints (branco).
    p1 = (S * 0.30, S * 0.72)
    p2 = (S * 0.70, S * 0.30)
    ctrl = (S * 0.40, S * 0.40)
    pts = []
    for i in range(0, 25):
        t = i / 24.0
        x = (1 - t) ** 2 * p1[0] + 2 * (1 - t) * t * ctrl[0] + t * t * p2[0]
        y = (1 - t) ** 2 * p1[1] + 2 * (1 - t) * t * ctrl[1] + t * t * p2[1]
        pts.append((x, y))
    lw = max(2, int(S * 0.075))
    try:
        d.line(pts, fill=(255, 255, 255, 220), width=lw, joint="curve")
    except Exception:
        d.line(pts, fill=(255, 255, 255, 220), width=lw)
    r = max(3, int(S * 0.115))
    for p in (p1, p2):
        d.ellipse([p[0] - r, p[1] - r, p[0] + r, p[1] + r], fill=INK)
    return img


def gerar(saida="openrotas.ico") -> str | None:
    """Gera o .ico multi-resolução. Devolve o caminho ou None em falha (Pillow ausente, etc.)."""
    try:
        from PIL import Image  # noqa: F401
        base = _render(256)
        destino = Path(saida)
        destino.parent.mkdir(parents=True, exist_ok=True)
        base.save(destino, format="ICO", sizes=[(t, t) for t in TAMANHOS])
        return str(destino)
    except Exception as e:
        sys.stderr.write("make_icon: nao foi possivel gerar o icone (%s)\n" % e)
        return None


if __name__ == "__main__":
    alvo = sys.argv[1] if len(sys.argv) > 1 else str(Path(__file__).resolve().parent / "openrotas.ico")
    r = gerar(alvo)
    print("icone gerado em %s" % r if r else "icone NAO gerado (seguindo sem ele)")
    raise SystemExit(0 if r else 0)      # nunca falha o build por causa do ícone
