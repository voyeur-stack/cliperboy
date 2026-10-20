#!/usr/bin/env python3
"""Curva de zoom de um video renderizado -- versao com referencia por plano.

A primeira tentativa comparava tudo com o quadro 0 e afundou: em 48s a
pessoa muda de posicao e passa a dominar o perfil de bordas. Aqui:

  1. acha os cortes pela queda de correlacao entre quadros vizinhos
  2. dentro de cada plano, mede a escala de cada quadro contra o PRIMEIRO
     quadro daquele plano -> da a rampa interna
  3. mede tambem o salto NO corte, comparando o ultimo quadro antes com o
     primeiro depois (o fundo e o mesmo, entao da pra casar)
  4. encadeia os saltos para montar a curva absoluta

Uso: python medir_zoom2.py <video> [fps]
"""
import subprocess, sys
import numpy as np

SRC = sys.argv[1]
FPS = float(sys.argv[2]) if len(sys.argv) > 2 else 10
W, H = 640, 1138
TOPO = int(H * 0.45)           # fundo: parede, prateleira, planta

raw = subprocess.run(
    ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", SRC,
     "-vf", f"fps={FPS},scale={W}:{H}", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
    capture_output=True).stdout
n = len(raw) // (W * H)
fr = np.frombuffer(raw, dtype=np.uint8)[:n*W*H].reshape(n, H, W).astype(float)


def perfil(f):
    g = np.abs(np.diff(f[:TOPO], axis=1)).sum(axis=0)
    g -= g.mean()
    s = g.std()
    return g / s if s > 1e-6 else g


P = np.array([perfil(f) for f in fr])
L = P.shape[1]
c, x = L / 2.0, np.arange(L)
print(f"{n} quadros a {FPS} fps ({n/FPS:.1f}s)")


def escala(ref, p, zmin, zmax, passo):
    melhor = (-2.0, 1.0)
    for z in np.arange(zmin, zmax, passo):
        pos = c + (x - c) / z
        for d in (-6, -3, 0, 3, 6):
            am = np.interp(pos + d, x, ref)
            m = (pos + d >= 0) & (pos + d < L)
            if m.sum() < L * 0.7:
                continue
            r = float(np.corrcoef(p[m], am[m])[0, 1])
            if r > melhor[0]:
                melhor = (r, z)
    return melhor


viz = np.array([1.0] + [float(np.corrcoef(P[i-1], P[i])[0, 1]) for i in range(1, n)])
cortes = [0] + [i for i in range(1, n) if viz[i] < 0.72] + [n]
planos = [(a, b) for a, b in zip(cortes, cortes[1:]) if b - a >= 4]
print(f"{len(planos)} planos detectados\n")

abs_ini = 1.0
print(f"{'plano':>16} {'dur':>5}   rampa interna        salto no corte   absoluto")
for k, (a, b) in enumerate(planos):
    ref = P[a]
    rs, zs = [], []
    for i in range(a, b):
        r, z = escala(ref, P[i], 0.985, 1.28, 0.0015)
        rs.append(r); zs.append(z)
    bons = [(z, r) for z, r in zip(zs, rs) if r > 0.75]
    if len(bons) < 3:
        print(f"{a/FPS:6.2f}-{b/FPS:5.2f}s  medida pouco confiavel")
        continue
    z_fim = np.median([z for z, _ in bons[-3:]])
    conf = np.mean([r for _, r in bons])

    salto = ""
    if k:
        pa, pb = planos[k-1][1] - 1, a
        r2, z2 = escala(P[pa], P[pb], 0.80, 1.30, 0.0025)
        if r2 > 0.70:
            salto = f"x{z2:.3f}"
            abs_ini = abs_ini * z2
    print(f"{a/FPS:6.2f}-{b/FPS:5.2f}s {(b-a)/FPS:5.2f}   "
          f"100% -> {100*z_fim:5.1f}%  (conf {conf:.2f})   {salto:>8}   "
          f"{100*abs_ini:5.1f}% -> {100*abs_ini*z_fim:5.1f}%")
    abs_ini = abs_ini * z_fim
