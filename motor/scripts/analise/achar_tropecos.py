#!/usr/bin/env python3
"""Procura tropeco/refacao dentro do corte: sequencia de palavras repetida
a pouca distancia, ou marcador de auto-correcao ("nao", "desculpa").

O whisper junta tudo numa frase so, entao o olho passa batido -- o caso
real foi "Agenda sua valia... nao, Agende sua avaliacao", que ficou
dentro de um unico bloco de legenda.
"""
import json, os, re, sys, unicodedata

sys.path.insert(0, os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))
import config                                            # noqa: E402

# Era caminho absoluto para o `trabalho/` do lote de julho — ver a mesma
# nota em `achar_frase.py`.
W = config.carregar().trabalho
MARCADORES = {"nao", "desculpa", "peraí", "perai", "espera", "foi"}


def norm(s):
    s = unicodedata.normalize("NFD", s.lower())
    return re.sub(r"[^a-z0-9]", "", "".join(c for c in s if not unicodedata.combining(c)))


def palavras(v):
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
    return pal


for v in sys.argv[1:]:
    pal = palavras(v)
    ch = [norm(p[0]) for p in pal]
    achados = []

    # 1) marcador de auto-correcao
    for i, c in enumerate(ch):
        if c in MARCADORES and 0 < i < len(ch) - 1:
            achados.append(("marcador", pal[i][1], f"...{' '.join(x[0] for x in pal[max(0,i-3):i+4])}..."))

    # 2) bigrama repetido a menos de 6s
    for n in (3, 2):
        for i in range(len(ch) - n):
            a = ch[i:i + n]
            if any(len(x) < 3 for x in a):
                continue
            for j in range(i + n, min(i + n + 14, len(ch) - n + 1)):
                if ch[j:j + n] == a and pal[j][1] - pal[i][1] < 6:
                    achados.append(("repeticao", pal[i][1],
                                    f"'{' '.join(pal[k][0] for k in range(i, i+n))}' "
                                    f"em {pal[i][1]:.2f}s e {pal[j][1]:.2f}s"))
                    break

    vistos, saida = set(), []
    for tipo, t, txt in sorted(achados, key=lambda x: x[1]):
        k = round(t, 1)
        if k in vistos:
            continue
        vistos.add(k); saida.append((tipo, t, txt))
    print(f"-- v{v}: {len(saida)} suspeita(s)")
    for tipo, t, txt in saida:
        print(f"   {t:6.2f}s [{tipo}] {txt}")
