#!/usr/bin/env python3
"""Gera um .cube (64^3, full in/full out) a partir de uma correcao parametrica.

POR QUE EXISTE (lote 38, Dr. Fulano, 11/09/2026): o medico gravou com
Picture Profile mexido (`CaptureGammaEquation=user9`) -- nao e' S-Log3, nem
709: preto levantado (p1 46-66 de 255) e croma pela metade. O LUT oficial da
Sony estoura o branco e o da Dra. Fulana deixa a pele laranja, porque os dois
esperam uma curva log que este material nao tem. O que bateu com o bruto de
agosto (que tinha cor) foi um stretch de niveis por video + saturacao. O
pipeline so' sabe aplicar `.cube` (`config.cor_de`), entao a correcao vira
`.cube` por aqui -- via Hald CLUT: o ffmpeg aplica o filtro numa imagem
identidade e o resultado E' a tabela.

Uso:
    python scripts/cubo_de_levels.py <saida.cube> --imin 0.18 --imax 0.88 [--sat 1.7]

`imin`/`imax` sao p1/p99 do bruto em fracao de 255; a saida vai para 16/235
(0.063/0.922). Medir p1/p99 em 5 quadros de fala do bruto, por video.
"""
import argparse, os, subprocess, tempfile
import numpy as np

ap = argparse.ArgumentParser()
ap.add_argument("saida")
ap.add_argument("--imin", type=float, required=True)
ap.add_argument("--imax", type=float, required=True)
ap.add_argument("--sat", type=float, default=1.7)
ap.add_argument("--omin", type=float, default=0.063)
ap.add_argument("--omax", type=float, default=0.922)
a = ap.parse_args()

N = 64
hald = os.path.join(tempfile.gettempdir(), "hald_tmp.raw")
f = (f"format=rgb48le,colorlevels=rimin={a.imin}:gimin={a.imin}:bimin={a.imin}"
     f":rimax={a.imax}:gimax={a.imax}:bimax={a.imax}"
     f":romin={a.omin}:gomin={a.omin}:bomin={a.omin}:romax={a.omax}:gomax={a.omax}:bomax={a.omax},"
     f"format=yuv444p16le,eq=saturation={a.sat},format=rgb48le")
subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "haldclutsrc=8",
                "-vf", f, "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb48le", hald],
               check=True)
# rawvideo, NAO png+PIL: o PIL abre PNG RGB de 16 bits como uint8 (0-255) e a
# tabela inteira caia para <=0,004 -- .cube preto, que o lut3d aplica calado.
im = np.fromfile(hald, np.uint16).reshape(-1, 3).astype(np.float64) / 65535.0
assert im.shape[0] == N ** 3
assert im.max() > 0.9, f"cube suspeito: max={im.max():.4f}"
with open(a.saida, "w") as fp:
    fp.write(f'TITLE "levels {a.imin}->{a.imax} out {a.omin}->{a.omax} sat {a.sat} (full in/out)"\n'
             f"LUT_3D_SIZE {N}\nDOMAIN_MIN 0 0 0\nDOMAIN_MAX 1 1 1\n")
    for r, g, b in im:
        fp.write(f"{r:.6f} {g:.6f} {b:.6f}\n")
print("ok", a.saida)
