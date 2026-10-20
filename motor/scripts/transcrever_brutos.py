#!/usr/bin/env python3
"""Fase 0 do lote: transcreve os BRUTOS, para você poder ler antes de cortar.

É esta transcrição que revela tomada refeita, direção de câmera gravada
junto, voz de quem está filmando e erro de fala — nada disso aparece no
volume. Foi lendo isto que o vídeo 7 saiu de 69,7s para 28,8s.

Roda antes de existir `faixas` no lote.json: pega todo `N.MOV` da pasta de
brutos, na ordem numérica. Depois de ler, você preenche `faixas` e roda o
`lote_preparar.py`.

    python scripts/transcrever_brutos.py --lote "2026-08 - Dr. Fulano"

Pula o que já existe — reexecutar é barato.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config                                            # noqa: E402

LOTE = config.carregar()
os.makedirs(LOTE.trabalho, exist_ok=True)

if not os.path.isdir(LOTE.brutos):
    sys.exit(f"Pasta de brutos não existe: {LOTE.brutos}")

brutos = sorted(
    (f for f in os.listdir(LOTE.brutos) if re.fullmatch(r"\d+\.(MOV|mov|mp4|MP4)", f)),
    key=lambda f: int(os.path.splitext(f)[0]))
if not brutos:
    sys.exit(f"Nenhum bruto em {LOTE.brutos}. Os arquivos precisam se chamar "
             f"1.MOV, 2.MOV, ... (o número é a identidade do vídeo no lote).")

for f in brutos:
    v = os.path.splitext(f)[0]
    destino = os.path.join(LOTE.trabalho, f"{v}.srt")
    if os.path.exists(destino):
        print(f"v{v}: já transcrito")
        continue
    idioma = LOTE.idioma_de(v)
    ok, err = config.transcrever(os.path.join(LOTE.brutos, f), destino,
                                 idioma=idioma)
    if ok:
        linhas = open(destino, encoding="utf-8").read().count("\n")
        print(f"v{v}: OK ({linhas} linhas, {idioma}) -> trabalho/{v}.srt")
    else:
        print(f"v{v}: FALHOU -> {err}")

print(f"\nFASE 0 CONCLUIDA. Leia os .srt em {LOTE.trabalho} e preencha "
      f"`faixas` no lote.json.")
print("Procure: tomada refeita, direção de câmera ('pode falar', 'foi'), "
      "voz de terceiro, tropeço.")
print("Frase com mais de ~0,35s por palavra tem algo escondido — "
      "ver docs/03-armadilhas.md §H6.")
