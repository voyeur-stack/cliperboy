#!/usr/bin/env python3
"""Copia a entrega para o Drive -- e so' se a verificacao passar antes.

Estrutura pedida pelo operador (03/08/2026): uma subpasta por frase, para o
analista pegar um bloco inteiro de uma vez.

    Finalizados/03 08/
        Frase 1/Vídeo 1..6.mp4
        Frase 2/Vídeo 1..6.mp4
        Frase 3/Vídeo 1..6.mp4
        Legendas/Vídeo 1..6.srt + .txt
"""
import os
import shutil
import subprocess
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
from lote import L, SAIDA  # noqa: E402

# Pasta de entrega no Drive, por lote. Era o caminho de 03/08 cravado aqui —
# publicar o lote seguinte levaria a entrega para a pasta do lote anterior.
DRIVE = L.entrega
if not DRIVE:
    sys.exit("Falta `entrega` no lote.json — a pasta do Drive onde a "
             "entrega deste lote vai parar.")

if "--sem-verificar" not in sys.argv:
    # Era `verificar.py`, a versao SUPERADA: ela aprovou 18 arquivos que o
    # operador reprovou de ouvido, porque nao media a legenda contra o audio.
    # O portao de publicacao tem de ser o verificador mais forte que existe.
    r = subprocess.run([sys.executable, os.path.join(AQUI, "verificar2.py")]
                       + (["--lote", L.nome] if L.nome else []))
    if r.returncode != 0:
        sys.exit("verificacao falhou -- nada foi copiado")

# So' o que E' entrega. Ja aconteceu de um script de analise gravar um
# `.wav` temporario ao lado do render e o publicador levar para o Drive
# junto -- a pasta do cliente ficou com "Vídeo 5.mp4.55_60.wav" dentro.
ENTREGAVEIS = (".mp4", ".srt", ".txt")

n, ignorados = 0, []
for raiz, _, arquivos in os.walk(SAIDA):
    rel = os.path.relpath(raiz, SAIDA)
    destino = DRIVE if rel == "." else os.path.join(DRIVE, rel)
    os.makedirs(destino, exist_ok=True)
    for a in arquivos:
        if not a.lower().endswith(ENTREGAVEIS):
            ignorados.append(os.path.join(rel, a))
            continue
        shutil.copy2(os.path.join(raiz, a), os.path.join(destino, a))
        n += 1
if ignorados:
    print(f"{len(ignorados)} arquivo(s) NAO copiado(s) (nao sao entrega):")
    for x in ignorados:
        print("  -", x)
print(f"{n} arquivos copiados para\n  {DRIVE}")
