#!/usr/bin/env python3
"""Confere se o lote tem tudo para rodar — antes de perder uma hora.

Roda em segundos e responde: os brutos estão lá? a tarja e o card do cliente
existem em ProRes com alpha? o modelo do whisper está no lugar? o light leak?
há música? Cada uma dessas faltas já apareceu numa sessão real, sempre no
meio do caminho, sempre depois de trabalho jogado fora.

    python scripts/conferir_lote.py --lote "2026-08 - Dr. Fulano"
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config                                            # noqa: E402
import relatorio                                         # noqa: E402

LOTE = config.carregar()
print(f"Lote: {LOTE.nome}")
print(f"Cliente: {LOTE.cliente or '(não definido)'}")
print(f"Pasta: {LOTE.pasta}")
print(f"Brutos: {LOTE.brutos}")
print(f"Entrega: {LOTE.entrega or '(não definida)'}\n")

faltas = LOTE.conferir()

# --- a arte tem MESMO alpha? .mov sem canal alfa passa no teste de
# existência e só falha na hora de compor, com a tarja em cima de um
# retângulo preto.
for nome, caminho in (("tarja", LOTE.tarja), ("finalização", LOTE.finalizacao)):
    if not caminho:
        continue
    fmt = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=pix_fmt", "-of", "csv=p=0", caminho],
        capture_output=True, text=True).stdout.strip()
    # Arquivo que NAO ABRE nao chega a ter pix_fmt: o ffprobe devolve vazio,
    # e o teste de alpha abaixo leria isso como "'a' nao esta em ''" e
    # reportaria falta de alpha — diagnostico errado para um arquivo que
    # esta pela metade.
    #
    # Aconteceu na abertura do lote da Dra. Fulana (12/08/2026): a pasta
    # canonica do Drive tinha 'Finalizacao Dra. Fulana.mov' com 22.020.096
    # bytes — 21 MB REDONDOS — e sem moov atom. Upload truncado, nao
    # placeholder do Drive (o atributo era Normal). Mesma familia do ffmpeg
    # truncando extracao no Drive e devolvendo exit 0 (docs/03 §V): arquivo
    # que mora no Drive pode estar pela metade sem ninguem avisar.
    if not fmt:
        faltas.append(f"{nome} '{os.path.basename(caminho)}' NAO ABRE "
                      f"({os.path.getsize(caminho):,} bytes). Arquivo "
                      f"truncado — confira se ha outra versao na pasta "
                      f"canonica do Drive antes de pedir novo export.")
        continue
    if "a" not in fmt:                      # yuva444p12le, rgba, ...
        faltas.append(f"{nome} '{os.path.basename(caminho)}' está em "
                      f"'{fmt}', que NÃO tem alpha. Peça export em ProRes "
                      f"4444 (yuva444p12le) ou sequência PNG.")
    else:
        print(f"  {nome}: {os.path.basename(caminho)} ({fmt}) OK")

if os.path.isdir(config.MUSICAS):
    n = len(config.faixas_de_musica())          # lista unica (02/10/2026)
    print(f"  músicas: {n} faixas em {config.MUSICAS}")
    if n < len(LOTE.videos):
        faltas.append(f"só {n} faixas para {len(LOTE.videos)} vídeos — vai "
                      f"repetir música dentro do lote")
else:
    faltas.append(f"pasta de músicas não existe: {config.MUSICAS}")

for nome, ok in (("faixas", bool(LOTE.faixas)),
                 ("correções de legenda", bool(LOTE.correcoes))):
    print(f"  {nome}: {'definidas' if ok else 'vazias'}"
          + ("" if ok else "  <- normal antes da fase 0/1"))

print()
relatorio.gravar(LOTE, "preflight", {
    "cliente": LOTE.cliente or None,
    "videos": LOTE.videos,
    "entrega": LOTE.entrega or None,
    "faltas": faltas,
    "ok": not faltas,
})
if faltas:
    print(f"{len(faltas)} PROBLEMA(S):")
    for f in faltas:
        print(f"  - {f}")
    sys.exit(1)
print("Tudo no lugar. Pode rodar a fase 0.")
