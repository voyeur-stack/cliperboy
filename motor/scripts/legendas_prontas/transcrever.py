#!/usr/bin/env python3
"""Transcreve o audio dos 16 videos com faster-whisper large-v3.

O audio e' a SEGUNDA fonte, nao a primeira: o que vai no .srt e' o que esta
queimado na tela (ocr.py). O whisper entra para cruzar -- e' ele que pega o
acento e a pontuacao que o OCR perde, e e' ele que denuncia quando o OCR leu
uma palavra que ninguem falou.
"""
import json
import os
import subprocess
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
sys.path.insert(0, os.path.dirname(AQUI))   # `scripts/`, onde mora o fw.py

from lista import FALTANDO, caminho, trab  # noqa: E402
from fw import transcrever  # noqa: E402


def duracao(p):
    return float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", p],
        capture_output=True, text=True, check=True).stdout.strip())


def wav(video, destino):
    """16 kHz mono -- e' o que o modelo consome; poupa o decode de video.

    Confere a duracao depois de extrair. O Video 11 saiu com 5,7 s de um
    video de 52 s e o ffmpeg devolveu codigo 0: os brutos moram no stream do
    Google Drive e uma falha de leitura encerra a extracao em silencio. Sem
    esta conferencia o vídeo chega ao fim do lote com 4 legendas e a culpa
    parece ser do OCR.
    """
    for tentativa in (1, 2, 3):
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", video,
                        "-vn", "-ac", "1", "-ar", "16000", destino],
                       check=True)
        dv, dw = duracao(video), duracao(destino)
        if dv - dw <= 0.5:
            return
        print(f"  wav truncado ({dw:.1f}s de {dv:.1f}s), tentativa "
              f"{tentativa}", flush=True)
    raise RuntimeError(f"nao consegui extrair o audio inteiro de {video}")


def um(nome, ap):
    """Transcreve UM video. Roda no processo filho quando ha' fila."""
    alvo = trab(f"{ap}_fw.json")
    w = trab(f"{ap}.wav")
    if not os.path.exists(w):
        wav(caminho(nome), w)
    transcrever(w, alvo, "pt")


# UM PROCESSO POR VIDEO -- nao e' preciosismo, e' a unica blindagem que
# funciona contra o modo de falha desta maquina.
#
# Medido em 24/08/2026 (lote 25, Clínica X): a placa e' uma GTX 1650
# de 4 GB e o `large-v3` vive na fronteira disso. Quando a VRAM acaba no meio
# da fila, o CUDA **aborta o processo nativo** -- nao levanta excecao Python,
# entao nem o try/except do fw.py nem um `assert` depois da chamada chegam a
# rodar. O script morre com exit 1, **sem traceback e sem uma linha de
# stderr**, e leva junto todos os videos que ainda estavam na fila. No lote 25
# isso derrubou 11 dos 15 videos de uma pasta duas vezes, e nas duas o log so'
# mostrava o cabecalho do video em que parou.
#
# Rodando um por processo, o filho morre sozinho e devolve a VRAM; o pai
# confere o ARTEFATO (o _fw.json existe?), tenta de novo uma vez, e segue a
# fila. Regra 1b do projeto: "exit 0" nao e' o mesmo que "fez o que eu pedi".
if os.environ.get("FW_UM"):
    nome, ap = json.loads(os.environ["FW_UM"])
    um(nome, ap)
    sys.exit(0)

faltou = []
for nome, ap in FALTANDO:
    alvo = trab(f"{ap}_fw.json")
    if os.path.exists(alvo):
        print(f"== {ap}: ja existe, pulando")
        continue
    print(f"\n== {ap}  ({nome})", flush=True)
    for tentativa in (1, 2):
        env = dict(os.environ, FW_UM=json.dumps([nome, ap]))
        r = subprocess.run([sys.executable, os.path.abspath(__file__)], env=env)
        if os.path.exists(alvo):
            break
        print(f"  MORREU sem gerar o _fw.json (exit {r.returncode}), "
              f"tentativa {tentativa}", flush=True)
    else:
        faltou.append(ap)

if faltou:
    sys.exit(f"\nNAO TRANSCREVERAM: {', '.join(faltou)}\n"
             f"Provavel falta de VRAM. Feche o que estiver usando a GPU "
             f"(outro whisper, subagente, navegador) e rode de novo -- o que "
             f"ja' existe e' pulado.")
print(f"\nOK: {len(FALTANDO)} video(s) com _fw.json em disco.")
