#!/usr/bin/env python3
"""Propoe as faixas de corte a partir das PALAVRAS, nao do silencedetect.

Por que nao o silencedetect: nestes 6 brutos o piso de ruido e' alto e a
fala e' continua. Com o limiar da regua (`RMS - 8 dB`) o detector achou
ZERO pausa em 4 dos 6; para achar alguma coisa foi preciso subir a -27 dB,
que e' `RMS - 4` a `RMS - 6` -- ou seja, encostado na fala, exatamente a
faixa em que ele come silaba dita baixo (o 'in Pi' de 'in Pinheiros').

A ancora aqui e' o vao ENTRE palavras da transcricao `max_len=1`. Um vao so'
vira corte se for maior que LIMITE, e ainda assim sobra PAD de cada lado.
Assim nenhum trecho removido encosta em fala transcrita.

Imprime tambem a velocidade de fala por frase: acima de ~0,35 s por palavra
tem tomada refeita escondida -- o whisper normaliza tropeco.
"""
import json
import os
import subprocess
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
from lote import FPS, REFEITO, TRAB, bruto  # noqa: E402

LIMITE = 0.45      # vao entre palavras a partir do qual vale cortar
PAD = 0.14         # folga mantida de cada lado do corte
CABECA = 0.25      # folga antes da primeira palavra
RABO = 0.45        # folga depois da ultima


def palavras(v):
    saida = []
    with open(os.path.join(TRAB, f"{v}_palavras.json"), encoding="utf-8") as f:
        for linha in f:
            linha = linha.strip()
            if not linha:
                continue
            d = json.loads(linha)
            t = d["text"].strip()
            if t:
                saida.append((d["start"] / 1000, d["end"] / 1000, t))
    return saida


def faixas(v, remover=()):
    """Janelas do bruto que ENTRAM, ja tirando `remover` (trechos refeitos)."""
    ps = [p for p in palavras(v)
          if not any(a <= p[0] < b for a, b in remover)]
    dur = float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", bruto(v)],
        capture_output=True, text=True).stdout.strip())

    blocos = []
    ini = max(0.0, ps[0][0] - CABECA)
    ant = ps[0][1]
    for a, b, _ in ps[1:]:
        if a - ant > LIMITE:
            blocos.append((round(ini, 2), round(min(ant + PAD, dur), 2)))
            ini = max(0.0, a - PAD)
        ant = max(ant, b)
    blocos.append((round(ini, 2), round(min(ant + RABO, dur), 2)))
    return blocos, dur


# Tomada refeita vem de `refeito` no lote.json (importado de `lote.py`).
# Achada LENDO a transcricao: no v6 do lote da agencia ele comeca a frase,
# para, recomeca, e ainda fala com quem filma ("Segura ai, Fulano") -- o
# whisper transcreveu as tres tentativas, entao a remocao e' explicita.
#
# ⚠️ Este arquivo tinha a SUA propria copia de REFEITO ({6: (34.90, 43.85)}),
# divergente da que o `refazer.py` do mesmo lote usava ({6: (33.70, 43.92)}).
# Duas verdades para o mesmo video, e nada apontava a contradicao. Ao passar
# para o lote.json, o valor conservado foi o do `refazer.py`, que e' o que
# gerou o mezanino aprovado.


def plano(v):
    """Faixas do video `v`, sem a tomada refeita e presas a' grade de quadros.

    Prender na grade nao e' capricho. Sem isso, o `trim` de video arredonda
    cada trecho para o quadro inteiro e o `atrim` de audio nao arredonda:
    cada trecho descasa ate' 33 ms, e o erro ACUMULA trecho a trecho. Medido
    na primeira leva: 100 ms de deriva nos videos 4 e 5, que tem 4 trechos.
    Com os limites em multiplos de 1/30 s os dois cortes dao o mesmo tanto.
    """
    blocos, dur = faixas(v, REFEITO.get(v, ()))
    return [(round(a * FPS) / FPS, round(b * FPS) / FPS)
            for a, b in blocos], dur


if __name__ == "__main__":
    for v in range(1, 7):
        rem = REFEITO.get(v, ())
        bl, dur = faixas(v, rem)
        total = sum(b - a for a, b in bl)
        print(f"=== video {v}: bruto {dur:.1f}s -> corte {total:.1f}s "
              f"({len(bl)} trechos, -{dur - total:.1f}s)")
        if rem:
            print(f"    tomada refeita removida: "
                  f"{', '.join(f'{a:.2f}-{b:.2f}' for a, b in rem)}")
        for a, b in bl:
            print(f"      [{a:6.2f}, {b:6.2f}]  {b - a:5.2f}s")

    print("\n--- velocidade de fala por frase (>0,35 s/palavra = suspeito) ---")
    for v in range(1, 7):
        ps = palavras(v)
        # agrupa em frases pela pontuacao final
        frase, ini = [], ps[0][0]
        for a, b, t in ps:
            frase.append(t)
            if t.endswith((".", "?", "!")):
                n = len(frase)
                seg = b - ini
                if n >= 3 and seg / n > 0.35:
                    print(f"  v{v} {ini:6.2f}-{b:6.2f}  {seg / n:.2f}s/palavra"
                          f"  {' '.join(frase)[:70]}")
                frase, ini = [], b
