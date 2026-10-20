#!/usr/bin/env python3
"""Escolhe a frase do 'texto na cara' seguindo as regras do operador.

Regras (dele, 30/07):
  * a frase EXATA que ela fala, inteira, sem reducao
  * no tempo EXATO em que ela fala
  * no maximo 3 linhas; passou disso, nao usa
  * so depois da tarja sair
  * nao e obrigatorio -- e mais para video grande
"""
import json, os, re, sys
from PIL import ImageFont

sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))
import config                                            # noqa: E402

# Os dois eram caminho absoluto de uma máquina só. A fonte, em especial,
# apontava para uma cópia solta em `D:\Downloads\...\Teste de funcionamento`,
# quando a MESMA fonte já vive em `assets/fonts/` e viaja com o projeto —
# duas cópias do mesmo arquivo, e a que o script usava era a que não sobe.
W = config.carregar().trabalho
FONTE = os.path.join(config.FONTES, "Anton-Regular.ttf")
CORPO, K, LARG = 200, 0.57, 950     # K: libass renderiza ~0.57 do que o PIL mede
MAX_LINHAS = 3
DEPOIS_DA_TARJA = 4.8
MIN_DUR_VIDEO = 20.0

fnt = ImageFont.truetype(FONTE, CORPO)


def larg(t):
    return (fnt.getbbox(t)[2] - fnt.getbbox(t)[0]) * K


def quebrar(frase):
    """Quebra em ate MAX_LINHAS sem reordenar nada. None se nao couber."""
    ws = frase.split()
    for n in range(1, MAX_LINHAS + 1):
        # tenta distribuir em n linhas equilibradas
        linhas, atual = [], []
        alvo = len(" ".join(ws)) / n
        for w in ws:
            teste = atual + [w]
            if atual and (larg(" ".join(teste)) > LARG or
                          (len(" ".join(teste)) > alvo * 1.35 and len(linhas) < n - 1)):
                linhas.append(" ".join(atual)); atual = [w]
            else:
                atual = teste
        if atual:
            linhas.append(" ".join(atual))
        if len(linhas) <= n and all(larg(l) <= LARG for l in linhas):
            return linhas
    return None


def palavras(v):
    toks = [json.loads(l) for l in
            open(f"{W}/{v}_palavras.json", encoding="utf-8") if l.strip()]
    ref, frases = [], []
    for bloco in re.findall(r"(\d\d:\d\d:\d\d,\d+) --> .*?\n(.+?)(?=\n\n|\Z)",
                            open(f"{W}/{v}_corte.srt", encoding="utf-8").read(), re.S):
        for f in re.split(r"(?<=[.?!])\s+", bloco[1].strip()):
            if f.strip():
                frases.append(f.strip())
                ref.extend(f.strip().split())
    pal, i = [], 0
    for alvo in ref:
        acc, ini, fim = "", None, None
        while i < len(toks):
            t = toks[i]
            if ini is None:
                ini = t["start"]
            acc += t["text"]; fim = t["end"]; i += 1
            if acc.replace(" ", "") == alvo.replace(" ", ""):
                break
            if len(acc) > len(alvo) + 2:
                break
        pal.append(((ini or 0) / 1000, (fim or 0) / 1000))
    return frases, pal


for v in sys.argv[1:]:
    frases, pal = palavras(v)
    total = pal[-1][1] if pal else 0
    print(f"-- v{v} ({total:.1f}s)")
    if total < MIN_DUR_VIDEO:
        print("   video curto -> sem texto na cara")
        continue
    k, achou = 0, False
    for f in frases:
        n = len(f.split())
        a, b = pal[k][0], pal[k + n - 1][1]
        k += n
        linhas = quebrar(f.upper())
        cabe = linhas is not None and len(linhas) <= MAX_LINHAS
        pos = a >= DEPOIS_DA_TARJA
        marca = "OK " if (cabe and pos) else "   "
        motivo = "" if cabe else " [nao cabe em 3 linhas]"
        if not pos:
            motivo += " [antes da tarja sair]"
        print(f"   {marca}{a:6.2f}-{b:6.2f} ({b-a:.2f}s) {len(linhas) if linhas else '?'}L "
              f'"{f}"{motivo}')
        if cabe and pos and not achou:
            achou = True
            print(f"        -> ESCOLHIDA: {'|'.join(linhas)}")
