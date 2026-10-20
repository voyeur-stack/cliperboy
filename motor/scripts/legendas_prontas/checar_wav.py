#!/usr/bin/env python3
"""O .wav extraido cobre o video inteiro?

Existe porque o Video 11 saiu com 5,7 s de audio de um video de 52 s -- e o
ffmpeg devolveu codigo 0. Os brutos moram no stream do Google Drive; uma
falha de leitura no meio encerra a extracao sem erro. Sem esta conferencia o
sintoma aparece la' na frente como "esse video quase nao tem legenda", e a
causa parece ser do OCR, que nao tem nada com isso.
"""
import os
import subprocess
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
from lista import FALTANDO, caminho, trab  # noqa: E402


def dur(p):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                        "format=duration", "-of", "default=nw=1:nk=1", p],
                       capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


ruins = []
for nome, ap in FALTANDO:
    w = trab(f"{ap}.wav")
    if not os.path.exists(w):
        continue
    dv, dw = dur(caminho(nome)), dur(w)
    falta = dv - dw
    marca = ""
    if falta > 0.5:
        marca = f"  <-- FALTAM {falta:.1f}s"
        ruins.append(ap)
    print(f"{ap:>11}: video {dv:6.1f}s  wav {dw:6.1f}s{marca}")

if ruins:
    print("\nrefazer: " + " ".join(ruins))
sys.exit(1 if ruins else 0)
