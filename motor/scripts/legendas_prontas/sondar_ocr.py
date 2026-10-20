#!/usr/bin/env python3
"""Sonda: onde na tela mora a legenda queimada, e o OCR le' isso?

Roda o OCR no quadro INTEIRO de algumas amostras e imprime cada caixa com a
posicao relativa. E' assim que se descobre a faixa da legenda em vez de
chutar: neste cliente ela nao esta sempre embaixo -- no video de tela
dividida ela fica a ~35 % da altura.
"""
import os
import subprocess
import sys

import cv2
import numpy as np

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
from lista import FALTANDO, caminho, trab  # noqa: E402

from rapidocr_onnxruntime import RapidOCR  # noqa: E402

ocr = RapidOCR()


def quadro(video, t):
    """Devolve o quadro como array BGR.

    Via stdout, nao via arquivo: `cv2.imread` volta None em caminho com
    acento no Windows -- e o caminho deste projeto tem "Edicao" com cedilha.
    """
    png = subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-ss", str(t), "-i", video,
         "-frames:v", "1", "-f", "image2pipe", "-vcodec", "png", "-"],
        capture_output=True, check=True).stdout
    return cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)


alvos = sys.argv[1:] or ["v02", "u_adiou", "v10"]
for ap in alvos:
    nome = dict((a, n) for n, a in FALTANDO)[ap]
    v = caminho(nome)
    dur = float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", v],
        capture_output=True, text=True, check=True).stdout.strip())
    print(f"\n########## {ap}  ({dur:.1f}s)  {nome}")
    for t in (dur * 0.25, dur * 0.5, dur * 0.75):
        img = quadro(v, t)
        h, w = img.shape[:2]
        r = ocr(img)[0] or []
        print(f"  --- t={t:.1f}s  ({w}x{h})")
        for caixa, txt, conf in r:
            ys = [p[1] for p in caixa]
            xs = [p[0] for p in caixa]
            print(f"    y {min(ys)/h:5.1%}-{max(ys)/h:5.1%}  "
                  f"x {min(xs)/w:5.1%}-{max(xs)/w:5.1%}  "
                  f"c={conf:.2f}  {txt!r}")
