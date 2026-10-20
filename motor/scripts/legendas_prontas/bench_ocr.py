#!/usr/bin/env python3
"""Quanto custa uma passada de OCR -- medido, nao estimado.

Sem GPU disponivel para o onnxruntime, o custo do OCR e' que decide a
arquitetura do lote (varrer tudo x varrer so' a faixa da legenda).
"""
import os
import subprocess
import sys
import time

import cv2
import numpy as np

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
from lista import FALTANDO, caminho  # noqa: E402

from rapidocr_onnxruntime import RapidOCR  # noqa: E402

ocr = RapidOCR()
v = caminho(dict((a, n) for n, a in FALTANDO)["v02"])

N = 12
FPS = 4


def quadros(video, fps, n, crop=None):
    vf = f"fps={fps}"
    if crop:
        vf += f",crop={crop}"
    p = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", video, "-vf", vf, "-frames:v", str(n),
         "-f", "rawvideo", "-pix_fmt", "bgr24", "-"],
        capture_output=True, check=True)
    return p.stdout


for rotulo, crop, dims in [("quadro inteiro", None, (1920, 1080)),
                           ("faixa 1080x560", "1080:560:0:760", (560, 1080))]:
    bruto = quadros(v, FPS, N, crop)
    h, w = dims
    tam = h * w * 3
    fr = [np.frombuffer(bruto[i * tam:(i + 1) * tam], np.uint8).reshape(h, w, 3)
          for i in range(N)]
    t0 = time.time()
    for f in fr:
        ocr(f)
    dt = time.time() - t0
    print(f"{rotulo}: {dt/N:.3f}s/quadro  ({dt:.1f}s por {N})")
