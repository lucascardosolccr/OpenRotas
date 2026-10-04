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

ACCENT = (31, 111, 235)      # azul de destaque (mesmo tom do painel)
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
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (tamanho, tamanho), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    raio = max(2, tamanho // 5)
    d.rounded_rectangle([0, 0, tamanho - 1, tamanho - 1], radius=raio, fill=ACCENT)
    texto = "OR"
    fnt = _fonte(int(tamanho * 0.52))
    try:
        cx0, cy0, cx1, cy1 = d.textbbox((0, 0), texto, font=fnt)
        tw, th = cx1 - cx0, cy1 - cy0
        d.text(((tamanho - tw) / 2 - cx0, (tamanho - th) / 2 - cy0), texto, font=fnt, fill=INK)
    except Exception:
        d.text((tamanho * 0.22, tamanho * 0.2), texto, fill=INK)
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
