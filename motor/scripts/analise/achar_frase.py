#!/usr/bin/env python3
"""Localiza no tempo do CORTE uma sequencia de palavras.

Reaproveita o mesmo alinhamento token->palavra do gerador de legenda, e
por isso devolve exatamente os tempos que a legenda vai usar.

Uso: python scripts/analise/achar_frase.py --lote "<lote>" <video> "<trecho>" ...
"""
import json, os, re, sys, unicodedata

sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))
import config                                            # noqa: E402

# Era o `trabalho/` do lote de julho, em caminho absoluto de uma máquina
# (`D:\Downloads\Estudo post editor\...`). Ficou apontando para um lote
# específico mesmo depois de o projeto virar multi-lote, e não existiria em
# outra máquina. Agora sai do lote pedido, como o resto do projeto.
W = config.carregar().trabalho
v = sys.argv[1]

toks = [json.loads(l) for l in
        open(f"{W}/{v}_palavras.json", encoding="utf-8") if l.strip()]
ref = []
for l in open(f"{W}/{v}_corte.srt", encoding="utf-8"):
    l = l.strip()
    if l and not l.isdigit() and "-->" not in l:
        ref.extend(l.split())

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
    pal.append((alvo, (ini or 0) / 1000, (fim or 0) / 1000))


def norm(s):
    s = unicodedata.normalize("NFD", s.lower())
    return re.sub(r"[^a-z0-9]", "", "".join(c for c in s if not unicodedata.combining(c)))


chaves = [norm(p[0]) for p in pal]

for trecho in sys.argv[2:]:
    alvo = [norm(x) for x in trecho.split()]
    achou = False
    for k in range(len(chaves) - len(alvo) + 1):
        if chaves[k:k + len(alvo)] == alvo:
            a, b = pal[k][1], pal[k + len(alvo) - 1][2]
            print(f'  {a:6.2f} -> {b:6.2f}  ({b-a:.2f}s)  "{trecho}"')
            achou = True
            break
    if not achou:
        print(f'  NAO ENCONTRADO: "{trecho}"')
