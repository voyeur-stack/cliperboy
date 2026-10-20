# -*- coding: utf-8 -*-
"""Fonte nova serve para portugues? Meça ANTES de calibrar qualquer coisa.

POR QUE ESTE ARQUIVO EXISTE

21/08/2026: o cliente do Dr. Fulano mandou a familia **Manier** para os
Reels. Instalei, calibrei corpo, largura, contorno e posicao, renderizei o
lote. So' que era a versao **TRIAL**: 70 glifos, **zero acento**. Em portugues
isso atinge 32% das legendas -- `PROTESE`, `RESSONANCIA`, `DECISAO`, `VOCE`.
O libass nao reclama: ele troca de fonte **so' no glifo que falta**, e a
palavra sai com duas tipografias, sem erro nenhum no log.

O sinal barato estava no tamanho do arquivo: **13 KB**. Fonte com acentuacao
tem centenas de KB.

NAO existe regra sobre trial. Medido nos 12 pesos da Manier (25/08/2026): 70
glifos em TODOS, nenhum acento, mas com kerning normal -- a fundicao entregou
a fonte funcionando e cortou o alfabeto. Outra fundicao pode entregar
acentuacao completa e limitar so' na licenca. Por isso: **medir, nunca
presumir**.

Uso:
    python scripts/checar_fonte.py <arquivo.otf|ttf> [outro...]
    python scripts/checar_fonte.py "D:/Downloads/manier/*.otf"

Sai com codigo 1 se qualquer fonte falhar no portugues.
"""
import glob
import os
import sys
import unicodedata

try:
    from fontTools.ttLib import TTFont
except ImportError:
    sys.exit("falta o fontTools: pip install fonttools")

# O que uma legenda de medico brasileiro exige de verdade.
PT = "ÁÂÃÀÉÊÍÓÔÕÚÜÇÑáâãàéêíóôõúüçñ"
BASE = ("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
        "0123456789 .,;:!?-—()'\"%/")


def checar(arq):
    t = TTFont(arq, fontNumber=0)
    cmap = set(t.getBestCmap())
    nomes = {r.nameID: str(r) for r in t["name"].names if r.platformID == 3}

    falta_pt = [c for c in PT if ord(c) not in cmap]
    falta_base = [c for c in BASE if c != " " and ord(c) not in cmap]
    kb = os.path.getsize(arq) / 1024
    trial = any("trial" in (nomes.get(i) or "").lower() for i in (1, 4, 16, 17))

    print(f"\n=== {os.path.basename(arq)} ===")
    print(f"  familia (o que vai no lote.json): {nomes.get(1)!r}")
    if nomes.get(16) and nomes.get(16) != nomes.get(1):
        print(f"  familia tipografica ...........: {nomes.get(16)!r}")
    print(f"  peso (usWeightClass) ..........: {t['OS/2'].usWeightClass}")
    print(f"  glifos ........................: {len(cmap)}   ({kb:.0f} KB)")
    print(f"  kerning .......................: "
          f"{'sim' if ('kern' in t or 'GPOS' in t) else 'NAO -- texto sai mal espacado'}")
    if trial:
        print("  *** o NOME diz TRIAL -- confira a licenca antes de publicar")

    if falta_pt:
        print(f"  ACENTUACAO ....................: FALTAM {len(falta_pt)} de "
              f"{len(PT)} -> {''.join(falta_pt)}")
        print("     Em portugues isso NAO da erro: o libass troca de fonte so'")
        print("     no glifo que falta, e a palavra sai com duas tipografias.")
    else:
        print("  ACENTUACAO ....................: COMPLETA")
    if falta_base:
        print(f"  BASICO ........................: faltam {''.join(falta_base)}")

    return not falta_pt


alvos = []
for a in sys.argv[1:]:
    alvos += sorted(glob.glob(a)) or ([a] if os.path.exists(a) else [])
if not alvos:
    sys.exit(__doc__.split("Uso:")[1].strip())

ok = 0
for a in alvos:
    try:
        ok += checar(a)
    except Exception as e:
        print(f"\n=== {os.path.basename(a)} ===\n  NAO ABRIU: {e}")

print(f"\n{ok}/{len(alvos)} fonte(s) servem para portugues.")
sys.exit(0 if ok == len(alvos) else 1)
