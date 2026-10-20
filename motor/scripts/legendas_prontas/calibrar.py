#!/usr/bin/env python3
"""Valida o gerador contra uma VERDADE CONHECIDA antes de gerar os 16.

Cinco videos desta pasta ja tem .srt aprovado. Eles servem de gabarito: se o
gerador reproduzir o corte de eventos e os tempos DELES, ele pode ser
apontado para os que faltam. Sem isso eu estaria inventando um formato e
chamando de padrao do cliente.

Uso:
    python calibrar.py            # transcreve o gabarito e imprime a compar.
"""
import json
import os
import re
import subprocess
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
sys.path.insert(0, os.path.dirname(AQUI))   # `scripts/`, onde mora o fw.py
from lista import GABARITOS, LEGENDAS, PASTA, trab  # noqa: E402,F401


def ler_srt(p):
    txt = open(p, encoding="utf-8-sig").read()
    ev = []
    for bloco in re.split(r"\n\s*\n", txt.strip()):
        linhas = [x for x in bloco.splitlines() if x.strip()]
        if len(linhas) < 2:
            continue
        m = re.search(r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*"
                      r"(\d+):(\d+):(\d+)[,.](\d+)", linhas[1])
        if not m:
            continue
        g = [int(x) for x in m.groups()]
        ev.append({"ini": g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000,
                   "fim": g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000,
                   "txt": " ".join(linhas[2:])})
    return ev


def transcrever_gabarito():
    from fw import transcrever
    for nome, ap in GABARITOS:
        alvo = trab(f"{ap}_fw.json")
        if os.path.exists(alvo):
            continue
        w = trab(f"{ap}.wav")
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i",
                        os.path.join(PASTA, nome), "-vn", "-ac", "1",
                        "-ar", "16000", w], check=True)
        transcrever(w, alvo, "pt")


def palavras(ap):
    d = json.load(open(trab(f"{ap}_fw.json"), encoding="utf-8"))
    return [w for s in d["segmentos"] for w in s["palavras"]]


if __name__ == "__main__":
    transcrever_gabarito()
    for nome, ap in GABARITOS:
        srt = os.path.join(LEGENDAS, os.path.splitext(os.path.basename(nome))[0] + ".srt")
        ev = ler_srt(srt)
        ws = palavras(ap)
        print(f"\n########## {ap}: {len(ev)} eventos aprovados, "
              f"{len(ws)} palavras no audio")
        npal = [len(e["txt"].split()) for e in ev]
        dur = [e["fim"] - e["ini"] for e in ev]
        car = [len(e["txt"]) for e in ev]
        print(f"  palavras/evento: min {min(npal)} med "
              f"{sorted(npal)[len(npal)//2]} max {max(npal)}")
        print(f"  caracteres/evento: min {min(car)} med "
              f"{sorted(car)[len(car)//2]} max {max(car)}")
        print(f"  duracao/evento: min {min(dur):.2f} med "
              f"{sorted(dur)[len(dur)//2]:.2f} max {max(dur):.2f}")
        print("  --- evento aprovado x palavra do audio mais proxima")
        for e in ev:
            perto = min(ws, key=lambda w: abs(w["ini"] - e["ini"]))
            print(f"   [{e['ini']:6.3f} {e['fim']:6.3f}] {e['txt']!r:42} "
                  f"| audio {perto['ini']:6.3f} {perto['txt']!r}")
