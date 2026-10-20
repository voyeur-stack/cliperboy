#!/usr/bin/env python3
"""Confere os .srt gerados antes de copiar para a pasta do cliente.

Numero de arquivo gerado nao e' verificacao. O que pode sair errado e nao
aparece abrindo o arquivo: evento fora da duracao do video, tempo andando
para tras, evento vazio, cobertura de fala baixa demais (legenda faltando
pedaco) e resto de erro bobo de OCR ('rn' por 'm', palavra colada).
"""
import json
import os
import re
import subprocess
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
from calibrar import ler_srt  # noqa: E402
from lista import FALTANDO, SAIDA, caminho, trab  # noqa: E402

SUSPEITO = [
    # so' interessa digito GRUDADO em letra ('s6' por 'só'). Numero sozinho e
    # porcentagem sao legitimos: a tela do Video 7 mostra '-7%' e '86%'.
    (r"[^\W\d_][\d]|[\d][^\W\d_]", "digito grudado em letra"),
    (r"(?i)\b(\w)\1{2,}", "letra repetida 3x"),
    (r"\s{2,}", "espaco duplo"),
    (r"^\s*[.,;:!?]", "evento comecando com pontuacao"),
]


def duracao(v):
    return float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", v],
        capture_output=True, text=True, check=True).stdout.strip())


problemas = 0
for nome, ap in FALTANDO:
    p = os.path.join(SAIDA, os.path.splitext(os.path.basename(nome))[0] + ".srt")
    if not os.path.exists(p):
        print(f"== {ap}: FALTA o .srt")
        problemas += 1
        continue
    ev = ler_srt(p)
    dur = duracao(caminho(nome))
    fw = json.load(open(trab(f"{ap}_fw.json"), encoding="utf-8"))
    fala = sum(s["fim"] - s["ini"] for s in fw["segmentos"])
    coberto = sum(e["fim"] - e["ini"] for e in ev)
    ruins = []
    for i, e in enumerate(ev):
        if not e["txt"].strip():
            ruins.append(f"evento {i+1} vazio")
        if e["fim"] <= e["ini"]:
            ruins.append(f"evento {i+1} com duracao <= 0")
        if i and e["ini"] < ev[i - 1]["fim"]:
            ruins.append(f"evento {i+1} sobrepoe o anterior")
        if e["fim"] > dur + 0.5:
            ruins.append(f"evento {i+1} passa do fim do video")
        for rx, o_que in SUSPEITO:
            if re.search(rx, e["txt"]):
                ruins.append(f"evento {i+1} {e['txt']!r}: {o_que}")
    cob = coberto / fala if fala else 0
    marca = "" if 0.75 <= cob <= 1.25 and not ruins else "  <-- OLHAR"
    print(f"== {ap}: {len(ev)} eventos, {ev[-1]['fim']:.1f}s de "
          f"{dur:.1f}s, cobertura da fala {cob:.0%}{marca}")
    for r in ruins:
        print(f"     {r}")
    problemas += len(ruins) + (0 if 0.75 <= cob <= 1.25 else 1)

print(f"\n{problemas} ponto(s) a olhar")
sys.exit(1 if problemas else 0)
