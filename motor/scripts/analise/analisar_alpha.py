#!/usr/bin/env python3
"""Mapeia o canal alpha de um .mov ProRes 4444 quadro a quadro.

Serve para achar (a) quando a arte entra e sai e (b) no caso da
finalizacao, a partir de que ponto a transparencia acaba -- que e onde o
operador poe fundo preto (o marcador verde dele no Premiere).
"""
import subprocess, sys
import numpy as np

src, fps = sys.argv[1], 30
W, H = 108, 192

raw = subprocess.run(
    ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", src,
     "-vf", f"scale={W}:{H}", "-f", "rawvideo", "-pix_fmt", "rgba", "-"],
    capture_output=True).stdout

n = len(raw) // (W * H * 4)
a = np.frombuffer(raw, dtype=np.uint8)[:n*W*H*4].reshape(n, H, W, 4)
alpha = a[..., 3].astype(float) / 255

print(f"{src.split(chr(92))[-1]}  |  {n} quadros ({n/fps:.2f}s)")
print(f"{'t(s)':>6} {'cobertura':>10} {'alpha medio':>12}")
ant = None
for i in range(n):
    cob = float((alpha[i] > 0.02).mean())
    med = float(alpha[i].mean())
    marco = ""
    if ant is not None:
        if ant < 0.02 <= cob: marco = "  <- comeca a aparecer"
        if ant > 0.98 >= cob: marco = "  <- deixa de ser opaco total"
        if ant < 0.98 <= cob: marco = "  <- fica OPACO TOTAL (fundo preto ja serve daqui)"
        if ant > 0.02 >= cob: marco = "  <- some"
    if i % 3 == 0 or marco:
        print(f"{i/fps:6.2f} {100*cob:9.1f}% {med:12.3f}{marco}")
    ant = cob
