#!/usr/bin/env python3
"""Gera um card de finalização no MOLDE dos cards da casa, para cliente sem arte.

Nasceu no lote 76 (Dra. Fulana, 05/10/2026): a revisão pediu "a
finalização com o card, mas sem o número de WhatsApp, apenas a CTA 'Agende sua
consulta com nossa equipe'", e ela não tinha card em `Finalizações`.

Molde MEDIDO nos cards do designer (Fulano, Fulano, Fulano — "modelo A"):
  - ProRes 4444 (yuva444p12le), 1080x1920, 60 fps, 5,00 s;
  - faixa de AUDIO PCM em silencio -- obrigatoria: o lote_produzir mixa
    `[{idx_final}:a]`, e card sem audio quebra o grafo;
  - alfa ZERO ate 0,20 s (o pipeline sobrepoe o card a partir de
    `total - card_antes`, e esse vazio e' o que deixa o conteudo terminar),
    circulo da cor da marca crescendo do centro ate 0,53 s, opaco ate o fim;
  - logo no alto (centro y~750), caixa de contorno fino com o CTA em duas
    linhas (y~1150-1400), texto entra por volta de 1 s.

PADRAO DA CASA (decisao do operador, 14/10/2026): todo cliente sem card em
`Finalizações` recebe um gerado aqui. O card leva SO a logo e o CTA
("AGENDE SUA CONSULTA" / "NO WHATSAPP" e variacoes) -- NUNCA numero de
telefone, @, site ou endereco. O script recusa CTA com sequencia de digitos.

Uso:
    python gerar_card.py --logo <png branco com alfa> --cor "#1E3626" \
        --saida "assets/clientes/<cliente>/Finalização - <cliente>.mov"
    (CTA padrao "AGENDE SUA CONSULTA" / "NO WHATSAPP"; trocar com --cta1/--cta2)
"""
import argparse
import math
import os
import re
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONTES = os.path.join(RAIZ, "assets", "fonts")
W, H, FPS, N = 1080, 1920, 60, 300
BRANCO = (255, 255, 255)


def suave(x):
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--logo", required=True)
    ap.add_argument("--cor", required=True)
    ap.add_argument("--cta1", default="AGENDE SUA CONSULTA")
    ap.add_argument("--cta2", default="NO WHATSAPP")
    ap.add_argument("--saida", required=True)
    ap.add_argument("--logo-largura", type=int, default=780)
    a = ap.parse_args()
    for texto in (a.cta1, a.cta2):
        # padrao da casa (14/10/2026): card nunca leva telefone
        if re.search(r"\d[\d\s().-]{5,}\d", texto):
            sys.exit(f"CTA com numero: {texto!r} -- card nao leva telefone")

    cor = tuple(int(a.cor.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    logo = Image.open(a.logo).convert("RGBA")
    logo = logo.crop(logo.split()[3].getbbox())
    lw = a.logo_largura
    logo = logo.resize((lw, round(logo.height * lw / logo.width)), Image.LANCZOS)

    f1 = ImageFont.truetype(os.path.join(FONTES, "Montserrat-Regular.ttf"), 56)
    f2 = ImageFont.truetype(os.path.join(FONTES, "Montserrat-Bold.ttf"), 64)
    caixa = (88, 1150, 992, 1400)
    cx, cy = W / 2, 860
    # raio pelo canto MAIS DISTANTE: o centro nao e' o da tela, e com
    # hypot(W,H)/2 os cantos de baixo ficavam sem fundo (1a versao, 05/10)
    raio_max = max(math.hypot(x - cx, y - cy) for x in (0, W) for y in (0, H)) + 4

    os.makedirs(os.path.dirname(os.path.abspath(a.saida)), exist_ok=True)
    cmd = ["ffmpeg", "-v", "error", "-y",
           "-f", "rawvideo", "-pix_fmt", "rgba", "-s", f"{W}x{H}", "-r", str(FPS),
           "-i", "-",
           "-f", "lavfi", "-t", f"{N / FPS}", "-i", "anullsrc=r=48000:cl=stereo",
           "-map", "0:v", "-map", "1:a",
           "-c:v", "prores_ks", "-profile:v", "4444", "-pix_fmt", "yuva444p12le",
           "-alpha_bits", "16", "-vendor", "apl0",
           "-c:a", "pcm_s16le", "-shortest", a.saida]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)

    for f in range(N):
        t = f / FPS
        img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)

        # fundo: circulo cresce do centro 0,20-0,53 s, com aceleracao
        p = max(0.0, min(1.0, (t - 0.20) / 0.33))
        if p >= 1:
            d.rectangle([0, 0, W, H], fill=cor + (255,))
        elif p > 0:
            r = raio_max * (p ** 1.6)
            d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=cor + (255,))

        # logo: sobe e aparece 0,55-0,95 s
        pl = suave((t - 0.55) / 0.40)
        if pl > 0:
            lg = logo.copy()
            lg.putalpha(lg.split()[3].point(lambda v: int(v * pl)))
            y = 750 - lg.height // 2 + int((1 - pl) * 40)
            img.alpha_composite(lg, ((W - lg.width) // 2, y))

        # caixa: o contorno se desenha 0,85-1,25 s; texto aparece 1,00-1,40 s
        pc = suave((t - 0.85) / 0.40)
        if pc > 0:
            x0, y0, x1, y1 = caixa
            meio = (x0 + x1) / 2
            meia = (x1 - x0) / 2 * pc
            esp = 4
            d.rectangle([meio - meia, y0, meio + meia, y0 + esp], fill=BRANCO + (255,))
            d.rectangle([meio - meia, y1 - esp, meio + meia, y1], fill=BRANCO + (255,))
            if pc >= 1:
                d.rectangle([x0, y0, x0 + esp, y1], fill=BRANCO + (255,))
                d.rectangle([x1 - esp, y0, x1, y1], fill=BRANCO + (255,))
        pt = suave((t - 1.00) / 0.40)
        if pt > 0:
            txt = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            dt = ImageDraw.Draw(txt)
            for texto, fonte, yc in ((a.cta1, f1, 1232), (a.cta2, f2, 1318)):
                l, tp, rr, bt = dt.textbbox((0, 0), texto, font=fonte)
                if rr - l > caixa[2] - caixa[0] - 60:
                    sys.exit(f"CTA largo demais: {texto!r} ({rr - l} px)")
                dt.text(((W - (rr - l)) / 2 - l, yc - (bt + tp) / 2), texto,
                        font=fonte, fill=BRANCO + (255,))
            txt.putalpha(txt.split()[3].point(lambda v: int(v * pt)))
            img.alpha_composite(txt, (0, int((1 - pt) * 20)))

        proc.stdin.write(img.tobytes())

    proc.stdin.close()
    rc = proc.wait()
    if rc != 0 or not os.path.exists(a.saida) or os.path.getsize(a.saida) < 100000:
        sys.exit(f"falhou: exit={rc}")
    print(f"OK {a.saida} ({os.path.getsize(a.saida)} bytes)")


if __name__ == "__main__":
    main()
