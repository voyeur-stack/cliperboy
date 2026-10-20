#!/usr/bin/env python3
"""Gera o `.txt` de texto corrido a partir do `.srt` ja' gerado.

POR QUE OS DOIS ARQUIVOS. O `.srt` deste cliente sai **por caixa** da legenda
queimada (2 a 4 palavras, 24 a 112 eventos), porque ele tem de bater com a
tela e porque e' o formato dos .srt ja' aprovados na mesma pasta. Isso serve
para conferir contra o video -- e nao serve para o uso que o operador
descreveu em 06/08/2026: ler e copiar para a legenda do post.

A saida foi entregar os dois. Uma frase por linha, caixa normal. Nenhuma das
duas regras precisou ser relaxada: elas so' brigavam porque um arquivo estava
sendo cobrado por dois trabalhos.
"""
import os
import re
import shutil
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
from calibrar import ler_srt  # noqa: E402
from lista import FALTANDO, LEGENDAS, SAIDA  # noqa: E402


def corrido(eventos):
    texto = re.sub(r"\s+", " ", " ".join(e["txt"] for e in eventos)).strip()
    # uma frase por linha; a quebra fica DEPOIS da pontuacao que a fecha
    frases = [f.strip() for f in re.split(r"(?<=[.!?])\s+", texto)]
    return "\n".join(f for f in frases if f) + "\n"


# Ver a nota em copiar.py: destino inexistente vira FileNotFoundError
# [WinError 3] no copy2, e o erro aponta para o arquivo, nao para a pasta.
if not os.path.isdir(LEGENDAS):
    os.makedirs(LEGENDAS, exist_ok=True)
    print(f"criei a pasta de destino: {LEGENDAS}\n")

copiados, pulados = [], []
for nome, ap in FALTANDO:
    base = os.path.splitext(os.path.basename(nome))[0]
    srt = os.path.join(SAIDA, base + ".srt")
    if not os.path.exists(srt):
        print(f"sem .srt: {base}")
        continue
    txt = os.path.join(SAIDA, base + ".txt")
    with open(txt, "w", encoding="utf-8") as f:
        f.write(corrido(ler_srt(srt)))
    destino = os.path.join(LEGENDAS, base + ".txt")
    # destino vazio (resto de rodada que morreu no meio) nao e entrega: sobrescreve
    if os.path.exists(destino) and os.path.getsize(destino) > 16:
        pulados.append(base)
    else:
        shutil.copy2(txt, destino)
        copiados.append(base)

for b in copiados:
    print(f"copiado  {b}.txt")
for b in pulados:
    print(f"JA EXISTIA, nao toquei  {b}.txt")
print(f"\n{len(copiados)} copiados, {len(pulados)} preservados")
