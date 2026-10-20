#!/usr/bin/env python3
"""Gera uma tarja de nome no MOLDE das tarjas da casa, para cliente sem arte.

Nasceu no lote 76 (Dra. Fulana, 05/10/2026): veterinária sem tarja
em `Finalizações`, e o operador pediu "com tarja, sem card".

O molde foi MEDIDO nas tarjas do After Effects (Fulano, Fulano, Fulano,
Fulano, Fulano), que são todas iguais fora texto, cor e altura:
  - ProRes 4444 (yuva444p12le), 1080x1920, 60 fps, 300 quadros (5,000 s);
  - faixa de AUDIO PCM em silencio -- obrigatoria: o lote_produzir mixa
    `[{2+k}:a]` da tarja, e sem stream de audio o ffmpeg aborta;
  - entra 0,8-1,4 s, cheia 1,4-3,4 s, sai 3,5-4,4 s (TARJA_SAI = 4,40);
  - barra fina na cor da marca em cima, nome em caixa alta condensada bold
    off-white com sombra, especialidade em caixa alta leve e espacada embaixo;
    sem fundo, sem CRM.

A animacao aqui e' mais simples que a do AE (barra cresce do centro, nome sobe
de dentro de uma mascara palavra a palavra, especialidade digita letra a
letra; saida espelhada). O pipeline so' depende das janelas de tempo.

Uso:
    python gerar_tarja.py --nome "Dra. Fulana" --linha2 "DERMATOLOGISTA" \
        --cor "#4F7A5C" --saida "assets/clientes/<cliente>/Tarja - <cliente>.mov"
"""
import argparse
import os
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFilter, ImageFont

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONTES = os.path.join(RAIZ, "assets", "fonts")
W, H, FPS, N = 1080, 1920, 60, 300
TEXTO = (242, 241, 242)


def suave(x):
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


def progresso(t, ini, fim):
    """0 antes de `ini`, 1 depois de `fim`, curva suave no meio."""
    return suave((t - ini) / (fim - ini))


def entra_sai(t, e0, e1, s0, s1):
    """Entrada em [e0,e1] e saida espelhada em [s0,s1]."""
    if t < s0:
        return progresso(t, e0, e1)
    return 1 - progresso(t, s0, s1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--nome", required=True)
    ap.add_argument("--linha2", required=True)
    ap.add_argument("--cor", required=True, help="cor da barra, #RRGGBB")
    ap.add_argument("--saida", required=True)
    ap.add_argument("--centro-y", type=int, default=1530)
    a = ap.parse_args()

    cor = tuple(int(a.cor.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    f_nome = ImageFont.truetype(os.path.join(FONTES, "Anton-Regular.ttf"), 100)
    f_l2 = ImageFont.truetype(os.path.join(FONTES, "Montserrat-Regular.ttf"), 34)
    esp_l2 = 7  # espacamento entre letras da linha 2, px

    # Posicao pela TINTA das letras, nao pela caixa da fonte: a caixa do Anton
    # tem ~30 px de folga acima das maiusculas, e posicionar por ela deixou a
    # barra longe do nome e a linha 2 colada nele (1a versao, 05/10/2026).
    cy = a.centro_y
    nome_y = cy - 75                        # origem do texto do nome
    _, topo_n, _, base_n = f_nome.getbbox("DRAGIOVZ")
    # Acento de MAIUSCULA (o I de Fulano, lote 80) sobe acima de "DRAGIOVZ":
    # medir a tinta so' por essas letras deixou a mascara 3 px acima das caixas
    # altas e o acento saiu cortado, com a barra a 18 px que nem cabia ele.
    # Topo pela tinta do NOME REAL; nome sem acento continua igual.
    topo_n = min(topo_n, f_nome.getbbox(a.nome.upper())[1])
    _, topo_l, _, _ = f_l2.getbbox("MEDICA")
    barra_h, barra_w = 14, 760
    barra_y = nome_y + topo_n - 18 - barra_h
    l2_y = nome_y + base_n + 22 - topo_l

    palavras = a.nome.split()
    larg = [f_nome.getlength(p) for p in palavras]
    vao = 26
    total = sum(larg) + vao * (len(palavras) - 1)
    if total > W - 120:
        sys.exit(f"nome largo demais: {total:.0f} px (max {W - 120})")
    x0 = (W - total) / 2
    xs = []
    for lw in larg:
        xs.append(x0)
        x0 += lw + vao
    asc, desc = f_nome.getmetrics()
    nome_h = base_n - topo_n + 6  # altura da TINTA: a mascara recorta so' ela

    letras = list(a.linha2)
    larg_l2 = sum(f_l2.getlength(c) for c in letras) + esp_l2 * (len(letras) - 1)
    l2_x0 = (W - larg_l2) / 2

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
        txt = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(txt)

        # barra: cresce do centro 0,80-1,15 / encolhe 4,05-4,40
        pb = entra_sai(t, 0.80, 1.15, 4.05, 4.40)
        if pb > 0:
            bw = max(4, barra_w * pb)
            ImageDraw.Draw(img).rectangle(
                [W / 2 - bw / 2, barra_y, W / 2 + bw / 2, barra_y + barra_h],
                fill=cor + (255,))

        # nome: cada palavra sobe de dentro da mascara, escalonada
        for k, (p, x) in enumerate(zip(palavras, xs)):
            atraso = 0.07 * k
            pp = entra_sai(t, 0.95 + atraso, 1.35 + atraso,
                           3.50 + 0.05 * (len(palavras) - 1 - k),
                           3.85 + 0.05 * (len(palavras) - 1 - k))
            if pp <= 0:
                continue
            # alterna a direcao: a ultima palavra desce de cima, como no AE
            sinal = -1 if k == len(palavras) - 1 and len(palavras) > 1 else 1
            dy = sinal * (1 - pp) * nome_h
            camada = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            ImageDraw.Draw(camada).text((x, nome_y + dy), p, font=f_nome,
                                        fill=TEXTO + (255,))
            mascara = Image.new("L", (W, H), 0)
            ImageDraw.Draw(mascara).rectangle(
                [0, nome_y + topo_n - 3, W, nome_y + base_n + 3], fill=255)
            txt.alpha_composite(Image.composite(
                camada, Image.new("RGBA", (W, H), (0, 0, 0, 0)), mascara))

        # linha 2: digita 1,15-1,45 / apaga 3,45-3,80
        n = len(letras)
        if t < 3.45:
            vis = int(round(n * progresso(t, 1.15, 1.45)))
        else:
            vis = int(round(n * (1 - progresso(t, 3.45, 3.80))))
        x = l2_x0
        for c in letras[:vis]:
            d.text((x, l2_y), c, font=f_l2, fill=TEXTO + (255,))
            x += f_l2.getlength(c) + esp_l2

        # sombra suave para baixo/direita, como nas tarjas do AE, MAIS um halo
        # escuro largo: sem ele a tarja branca sumiu sobre a mesa branca do v2
        # do lote 76 ("MEDICA VETERINARIA" quase ilegivel) -- o AE nao precisa
        # porque o designer escolhe a altura vendo o fundo; aqui nao.
        alfa = txt.split()[3]
        halo = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        halo.putalpha(alfa.filter(ImageFilter.MaxFilter(9))
                      .filter(ImageFilter.GaussianBlur(14))
                      .point(lambda v: min(255, int(v * 0.9))))
        img.alpha_composite(halo)
        sombra = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        sombra.putalpha(alfa.point(lambda v: int(v * 0.75)))
        sombra = sombra.filter(ImageFilter.GaussianBlur(4))
        img.alpha_composite(sombra, (4, 5))
        img.alpha_composite(txt)
        proc.stdin.write(img.tobytes())

    proc.stdin.close()
    rc = proc.wait()
    if rc != 0 or not os.path.exists(a.saida) or os.path.getsize(a.saida) < 100000:
        sys.exit(f"falhou: exit={rc}")
    print(f"OK {a.saida} ({os.path.getsize(a.saida)} bytes)")


if __name__ == "__main__":
    main()
