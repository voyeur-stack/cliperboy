#!/usr/bin/env python3
"""Copia os .srt gerados para a pasta Legendas do cliente.

Nunca sobrescreve. Os cinco .srt que ja estavam la' sao material aprovado e
publicado -- este lote existe para completar o que falta, nao para revisar o
que existe. Se um destino ja existir, o arquivo fica de fora e e' avisado.
"""
import os
import shutil
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
from lista import FALTANDO, LEGENDAS, SAIDA  # noqa: E402

# A subpasta de destino pode nao existir ainda -- e' o caso quando o pedido e'
# a PRIMEIRA leva de legendas daquela pasta (lote 17, Fulano agosto/2026).
# Sem isto o shutil.copy2 morre com FileNotFoundError [WinError 3], que nao
# parece o que e': o arquivo de origem existe, quem falta e' a pasta.
if not os.path.isdir(LEGENDAS):
    os.makedirs(LEGENDAS, exist_ok=True)
    print(f"criei a pasta de destino: {LEGENDAS}\n")

copiados, pulados, faltando = [], [], []
for nome, ap in FALTANDO:
    base = os.path.splitext(os.path.basename(nome))[0] + ".srt"
    origem = os.path.join(SAIDA, base)
    destino = os.path.join(LEGENDAS, base)
    if not os.path.exists(origem):
        faltando.append(base)
    # destino vazio (resto de rodada que morreu no meio) nao e entrega: sobrescreve
    elif os.path.exists(destino) and os.path.getsize(destino) > 16:
        pulados.append(base)
    else:
        shutil.copy2(origem, destino)
        copiados.append(base)

for b in copiados:
    print(f"copiado  {b}")
for b in pulados:
    print(f"JA EXISTIA, nao toquei  {b}")
for b in faltando:
    print(f"NAO GERADO  {b}")
print(f"\n{len(copiados)} copiados, {len(pulados)} preservados, "
      f"{len(faltando)} faltando")
print(f"destino: {LEGENDAS}")
