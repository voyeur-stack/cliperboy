#!/usr/bin/env python3
"""Verifica os 18 -- inclusive a LEGENDA CONTRA O AUDIO.

A verificacao anterior aprovou 18 arquivos que o operador reprovou de
ouvido. Ela media duracao, sync, nivel, dimensao e presenca de box e de
legenda -- e todos os cinco estavam certos. Nenhum deles ve legenda
adiantada, legenda atrasada nem fala cortada. Numero que nao pode reprovar
o defeito que existe nao e' verificacao, e' decoracao.

O que entra agora:

  ALINHAMENTO  para cada evento de legenda, quanto do seu tempo cai em
               cima de fala de verdade (energia do `_corte.wav`), e, nos
               eventos que comecam depois de uma pausa, a distancia entre
               o inicio do evento e o onset da fala. E' a medida direta de
               "adiantada ou atrasada".

  FALA INTEIRA nenhuma borda de corte pode cair dentro de fala. Fica
               registrada aqui a conferencia feita no plano, porque depois
               de renderizado o corte ja nao da' para separar emenda de
               pausa natural.
"""
import json
import os
import re
import subprocess
import sys

import numpy as np
from PIL import Image

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(AQUI)),
                                "scripts"))
import corte2                                            # noqa: E402
import retimar_legenda as R                              # noqa: E402
# REFEITO vinha do `refazer.py` do lote — script de uma rodada especifica,
# que nao sobe. Agora e' dado de lote, como devia sempre ter sido.
from lote import REFEITO, SAIDA, TRAB                    # noqa: E402
TMP = os.path.join(TRAB, "_vq.png")
BOX_Y, LEG_Y = (900, 1000), (1430, 1480)
TOL_ONSET = 0.20        # atraso/adiantamento aceitavel, em segundos
MIN_SOBRE_FALA = 0.60   # fracao minima do evento em cima de fala


def probe(p, fluxo, campos):
    return subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", fluxo, "-show_entries",
         f"stream={campos}", "-of", "default=nw=1:nk=1", p],
        capture_output=True, text=True).stdout.split()


def sync_real(p):
    nq = int(subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_packets",
         "-show_entries", "stream=nb_read_packets", "-of",
         "default=nw=1:nk=1", p], capture_output=True, text=True).stdout)
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", p, "-vn", "-ac", "1",
                        "-ar", "16000", "-f", "s16le", "-"],
                       capture_output=True)
    return abs(nq / 30 - len(r.stdout) / 2 / 16000)


def quadro(p, t):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(t), "-i", p,
                    "-frames:v", "1", TMP], check=True)
    return np.array(Image.open(TMP).convert('RGB')).astype(int)


def tem_faixa(a):
    b = a.min(2) > 235
    return sum(1 for y in range(*BOX_Y)
               if b[y, :6].all() and b[y, -6:].all() and b[y].mean() > 0.5) > 60


def tem_legenda(a):
    return (a.min(2) > 235)[LEG_Y[0]:LEG_Y[1]].sum() > 50


def eventos(v):
    out = []
    for linha in open(os.path.join(TRAB, f"{v}.ass"), encoding="utf-8"):
        if linha.startswith("Dialogue:"):
            c = linha.split(",", 9)
            h, m, s = c[1].split(":")
            a = int(h) * 3600 + int(m) * 60 + float(s)
            h, m, s = c[2].split(":")
            b = int(h) * 3600 + int(m) * 60 + float(s)
            out.append((a, b, re.sub(r"\{[^}]*\}", "", c[9]).strip()))
    return out


def alinhamento(v):
    """Quanto a legenda cola na fala.

    A pergunta certa e' "HA FALA NO INSTANTE EM QUE A LEGENDA ACENDE?".

    ARMADILHA (03/08/2026): a primeira versao perguntava outra coisa --
    "qual segmento de fala cobre mais este evento?" -- e comparava o inicio
    do evento com o inicio DESSE segmento. Isso reprovou 3 videos com
    505-685 ms de "adiantamento" que nao existiam: no v5 o evento
    '347 leads no' acende em 8,60, dentro da fala 8,13-9,22, mas o medidor
    elegeu dono o segmento 9,29-10,56 por ele cobrir 0,78 s contra 0,62 s.
    A legenda estava certa; a pergunta e' que estava errada.

    ADIANTADA e ATRASADA sao separadas e so' a primeira reprova. Adiantada
    e' defeito puro: legenda no ar antes de a palavra existir. "Atrasada" e'
    quase sempre o detector acendendo em respiracao -- no v5 ele marca fala
    490 ms antes da palavra "347". Reprovar por isso seria mandar a legenda
    entrar ANTES da fala para agradar o medidor.
    """
    segs = [(a / 1000, b / 1000)
            for a, b in R.segmentos_de_fala(os.path.join(
                TRAB, f"{v}_corte.wav"))]
    ev = eventos(v)

    def fala_em(a, b):
        return sum(max(0.0, min(b, sb) - max(a, sa)) for sa, sb in segs)

    fracs, adiant, atras = [], [], []
    for i, (a, b, _) in enumerate(ev):
        if b > a:
            fracs.append(fala_em(a, b) / (b - a))
        anterior = ev[i - 1][1] if i else 0.0
        if a - anterior < 0.30:
            continue
        # o .ass grava o tempo em centesimos e o envelope anda de 5 em 5 ms:
        # uma diferenca de ate' 15 ms e' quantizacao, nao desalinhamento
        dentro = any(sa - 0.015 <= a <= sb + 0.015 for sa, sb in segs)
        if dentro:
            adiant.append(0.0)          # acende com a fala ja no ar
            continue
        depois = [sa for sa, _ in segs if sa > a]
        antes = [sb for _, sb in segs if sb <= a]
        if depois:
            adiant.append(min(depois) - a)      # espera a fala comecar
        if antes:
            atras.append(a - max(antes))        # fala ja tinha comecado
    return (float(np.mean(fracs)) if fracs else 0.0, adiant, atras)


falhas = []
print("--- corte: alguma borda dentro de fala? ---")
for v in range(1, 7):
    rem = REFEITO.get(v, ())
    bl, _ = corte2.blocos_de(v, rem)
    bl = corte2.ajustar_bordas(v, bl, rem)
    ruins = corte2.conferir(v, bl, rem)
    print(f"  v{v}: {len(bl)} trechos, {len(ruins)} borda(s) em fala")
    if ruins:
        falhas.append(f"v{v}: {len(ruins)} borda(s) de corte dentro de fala")

print("\n--- legenda contra o audio ---")
for v in range(1, 7):
    frac, adiant, atras = alinhamento(v)
    pa = max(adiant) if adiant else 0.0
    pt = max(atras) if atras else 0.0
    print(f"  v{v}: {frac * 100:5.1f}% em cima de fala; "
          f"ADIANTADA em {len(adiant):2d} entradas (pior {pa*1000:4.0f} ms); "
          f"atrasada em {len(atras):2d} (pior {pt*1000:4.0f} ms)")
    if frac < MIN_SOBRE_FALA:
        falhas.append(f"v{v}: so' {frac*100:.0f}% da legenda cai em fala")
    if pa > TOL_ONSET:
        falhas.append(f"v{v}: legenda adiantada em {pa*1000:.0f} ms")

print("\n--- arquivos ---")
print(f"{'arquivo':<20} {'dur':>7} {'sync':>7} {'dim':>10} {'nivel':>8} "
      f"{'pico':>7}  box  leg")
for frase in (1, 2, 3):
    for v in range(1, 7):
        p = os.path.join(SAIDA, f"Frase {frase}", f"Vídeo {v}.mp4")
        nome = f"F{frase}/Vídeo {v}"
        if not os.path.exists(p):
            falhas.append(f"{nome}: nao existe")
            continue
        w, h = probe(p, "v:0", "width,height")[:2]
        dv = float(probe(p, "v:0", "duration")[0])
        r = subprocess.run(["ffmpeg", "-hide_banner", "-i", p, "-vn", "-af",
                            "astats=metadata=1:reset=0", "-f", "null", "-"],
                           capture_output=True, text=True)
        rms = float(re.findall(r"RMS level dB:\s*(-?[\d.]+)", r.stderr)[-1])
        pico = float(re.findall(r"Peak level dB:\s*(-?[\d.]+)", r.stderr)[-1])
        sync = sync_real(p)
        box_ok = tem_faixa(quadro(p, 2.0)) and not tem_faixa(quadro(p, 7.0))
        ev = eventos(v)
        passo = max(1, len(ev) // 5)
        sondas = [(a + b) / 2 for a, b, _ in ev[::passo][:5]]
        leg = sum(tem_legenda(quadro(p, t)) for t in sondas)
        print(f"{nome:<20} {dv:>6.2f}s {sync*1000:>6.0f}ms "
              f"{w+'x'+h:>10} {rms:>7.1f}dB {pico:>6.1f}dB"
              f"  {'ok' if box_ok else 'FALHA':>5}  {leg}/{len(sondas)}")
        if (w, h) != ("1080", "1920"):
            falhas.append(f"{nome}: dimensao {w}x{h}")
        if sync > 0.040:
            falhas.append(f"{nome}: sync {sync*1000:.0f} ms")
        if not -21 <= rms <= -15:
            falhas.append(f"{nome}: nivel {rms:.1f} dB")
        if pico > -0.5:
            falhas.append(f"{nome}: pico {pico:.1f} dB")
        if not box_ok:
            falhas.append(f"{nome}: box fora de hora")
        if leg < len(sondas):
            falhas.append(f"{nome}: legenda ausente em sonda")

print()
if falhas:
    print(f"{len(falhas)} FALHA(S):")
    for f in falhas:
        print("  -", f)
    sys.exit(1)
print("todos passaram")
