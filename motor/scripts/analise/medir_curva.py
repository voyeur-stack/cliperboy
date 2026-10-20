#!/usr/bin/env python3
"""Mede a TRAJETORIA de zoom de um render, nao so o inicio e o fim.

Por que existe: o `medir_zoom2.py` compara o primeiro e o ultimo quadro de
cada plano detectado. Se a curva sobe e e ancorada de volta na fronteira de
movimento, os dois extremos coincidem e ele reporta "sem zoom" -- foi o que
aconteceu ao verificar o lote de julho e quase me fez desfazer um render
correto.

Aqui a referencia e sempre o MESMO quadro (o primeiro), e o perfil vem so
do topo da imagem, que e fundo estatico. Assim cada amostra e comparavel
com todas as outras.

LIMITE CONHECIDO -- leia antes de acreditar no resultado:
mede bem em material CONTINUO (validado contra verdade conhecida: acusou
100% -> 120,4% num clipe cuja curva era exatamente essa), mas devolve
100,0% com confianca alta em cima do render final CONCATENADO, onde o
zoom esta comprovadamente aplicado. Ou seja: **resultado plano aqui nao
prova ausencia de zoom.** Confirme com dois quadros lado a lado antes de
refazer qualquer render -- foi o que evitou eu desfazer um render correto
em 30/07.

Uso: python medir_curva.py <video> [fps_amostra]
"""
import subprocess, sys
import numpy as np

SRC = sys.argv[1]
FPS = float(sys.argv[2]) if len(sys.argv) > 2 else 4
W, H = 640, 1138
TOPO = int(H * 0.55)           # parede e paineis -- nao andam; corta legenda

raw = subprocess.run(
    ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", SRC,
     "-vf", f"fps={FPS},scale={W}:{H}", "-f", "rawvideo",
     "-pix_fmt", "gray", "-"], capture_output=True).stdout
n = len(raw) // (W * H)
fr = np.frombuffer(raw, dtype=np.uint8)[:n * W * H].reshape(n, H, W).astype(float)


def perfil(f):
    g = np.abs(np.diff(f[:TOPO], axis=1)).sum(axis=0)
    g -= g.mean()
    s = g.std()
    return g / s if s > 1e-6 else g


P = np.array([perfil(f) for f in fr])
L = P.shape[1]
c, x = L / 2.0, np.arange(L)
ref = P[0]


def escala(p):
    melhor = (-2.0, 1.0)
    for z in np.arange(0.97, 1.30, 0.002):
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


print(f"{n} amostras a {FPS} fps ({n/FPS:.1f}s) -- referencia = quadro 0\n")
print(f"{'t':>6} {'zoom':>7} {'conf':>6}")
zs, ts = [], []
for i in range(n):
    r, z = escala(P[i])
    t = i / FPS
    marca = "" if r > 0.70 else "  (baixa confianca)"
    print(f"{t:6.2f} {100*z:6.1f}% {r:6.2f}{marca}")
    if r > 0.70:
        zs.append(z); ts.append(t)

if zs:
    zs = np.array(zs)
    d = np.abs(np.diff(zs))
    print(f"\nfaixa medida: {100*zs.min():.1f}% a {100*zs.max():.1f}% "
          f"(amplitude {100*(zs.max()-zs.min()):.1f} pontos)")
    print(f"maior variacao entre amostras vizinhas: {100*d.max():.1f} pontos")
    print(f"amostras confiaveis: {len(zs)}/{n}")
