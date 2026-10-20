#!/usr/bin/env python3
"""Mapeia o padrao de edicao dos videos de referencia por estatistica.

Em vez de olhar centenas de frames, mede cada quadro e detecta:
  * P&B         -> saturacao ~0
  * leak/flash  -> pico de brilho, geralmente com desvio quente (R-B)
  * blur        -> queda brusca de energia de borda
"""
import glob, os, subprocess, sys, shutil
from PIL import Image, ImageFilter, ImageStat

SRC = sys.argv[1]
FPS = float(sys.argv[2]) if len(sys.argv) > 2 else 5
TMP = "_an"

shutil.rmtree(TMP, ignore_errors=True)
os.makedirs(TMP)
subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", SRC,
                "-vf", f"fps={FPS},scale=96:171", f"{TMP}/f%05d.png"],
               check=True)

med = []
for p in sorted(glob.glob(f"{TMP}/f*.png")):
    im = Image.open(p).convert("RGB")
    st = ImageStat.Stat(im)
    r, g, b = st.mean
    mx, mn = max(r, g, b), min(r, g, b)
    sat = (mx - mn) / mx * 100 if mx else 0
    borda = ImageStat.Stat(im.convert("L").filter(ImageFilter.FIND_EDGES)).stddev[0]
    med.append({"t": (len(med)) / FPS, "brilho": (r + g + b) / 3,
                "sat": sat, "quente": r - b, "borda": borda})

bmed = sorted(m["borda"] for m in med)[len(med) // 2]
brmed = sorted(m["brilho"] for m in med)[len(med) // 2]


def faixas(cond, gap=0.6):
    out, ini, ant = [], None, None
    for m in med:
        if cond(m):
            if ini is None:
                ini = m["t"]
            ant = m["t"]
        elif ini is not None and m["t"] - ant > gap:
            out.append((ini, ant)); ini = None
    if ini is not None:
        out.append((ini, ant))
    return out


print(f"\n=== {os.path.basename(SRC)} ===")
print(f"borda mediana {bmed:.1f} | brilho mediano {brmed:.1f}")

pb = faixas(lambda m: m["sat"] < 6)
print(f"P&B ({len(pb)}):", [f"{a:.1f}-{b:.1f}s" for a, b in pb] or "nenhum")

bl = faixas(lambda m: m["borda"] < bmed * 0.55, gap=0.3)
print(f"BLUR ({len(bl)}):", [f"{a:.1f}-{b:.1f}s" for a, b in bl] or "nenhum")

fl = [m for m in med if m["brilho"] > brmed * 1.25]
print(f"FLASH/LEAK ({len(fl)}):",
      [f"{m['t']:.1f}s(br{m['brilho']:.0f} quente{m['quente']:+.0f})"
       for m in fl] or "nenhum")

shutil.rmtree(TMP, ignore_errors=True)
