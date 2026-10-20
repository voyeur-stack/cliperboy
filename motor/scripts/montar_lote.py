#!/usr/bin/env python3
"""Monta a abertura de TODAS as pecas do lote: gera a musica do corpo e chama
o `montar_abertura.py` em cada uma.

Existe porque a musica, em lote com vinheta, e' mixada na MONTAGEM e nao no
render -- o operador decidiu que ela comeca so' depois da vinheta, e o render
nao sabe em que instante isso e' (a vinheta so' entra depois dele). Ver o
cabecalho de `montar_abertura.py`.

A faixa e' escolhida com a MESMA regra do `lote_produzir.py` (uma por video,
pela ordem das chaves de `faixas`), senao a peca montada sairia com musica
diferente da que o verificador espera.

Uso:
    python montar_lote.py --lote "<nome>" [numeros...]
"""
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config                                            # noqa: E402

SCR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCR)
import musica as M                                       # noqa: E402

LOTE = config.carregar()
MUSICAS = config.exigir_caminho("musicas", "pasta das músicas de fundo")

alvos = [a for a in sys.argv[1:] if a.isdigit()] or list(LOTE.faixas)


def faixa_de(v):
    """Mesma regra do lote_produzir: uma por video, sem repetir, sem copias."""
    fs = config.faixas_de_musica(MUSICAS)      # lista unica (02/10/2026)
    return fs[list(LOTE.faixas).index(v) % len(fs)] if fs else None


def dur(arq):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                        "format=duration", "-of", "default=nw=1:nk=1", arq],
                       capture_output=True, text=True)
    if r.returncode:
        sys.exit(f"ABORTADO: ffprobe falhou em {arq}")
    return float(r.stdout.strip())


vin = LOTE.vinheta.get("arquivo")
if not vin:
    sys.exit("ABORTADO: `vinheta.arquivo` nao esta no lote.json")
if not os.path.isabs(vin):
    vin = os.path.join(LOTE.pasta, vin)

print(f"encoder   {config.encoder_nome()}")
falhas = []
for v in alvos:
    pronto = os.path.join(LOTE.saida, f"{v}_PRONTO.mp4")
    if not os.path.exists(pronto):
        print(f"v{v}: PULADO -- {v}_PRONTO.mp4 nao existe")
        falhas.append(v)
        continue
    corte = LOTE.vinheta_em.get(str(v))
    if corte is None:
        print(f"v{v}: PULADO -- sem `vinheta_em` para este video")
        falhas.append(v)
        continue

    # A musica cobre so' o CORPO: da' entrada da vinheta ate o fim da peca.
    corpo = dur(pronto) - float(corte)
    mus = os.path.join(LOTE.trabalho, f"{v}_musica_corpo.wav")
    src = faixa_de(v)
    if src:
        ganho = float(LOTE.musica_db.get(str(v), -33.0 + 6.0))
        info = M.remixar(src, corpo, mus, ganho)
        print(f"v{v}: musica {os.path.basename(src)[:38]} -> {corpo:.2f}s "
              f"({info.get('emendas', '?')} emenda)")
    else:
        mus = ""
        print(f"v{v}: SEM musica (nenhuma faixa encontrada)")

    saida = os.path.join(LOTE.saida, f"{v}_PRONTO_ABERTURA.mp4")
    r = subprocess.run([sys.executable, os.path.join(SCR, "montar_abertura.py"),
                        pronto, vin, str(corte), saida] + ([mus] if mus else []),
                       capture_output=True, text=True)
    print("\n".join("      " + l for l in r.stdout.strip().split("\n") if l))
    if r.returncode:
        print(f"v{v}: MONTAGEM FALHOU -> {r.stderr.strip()[-400:]}")
        falhas.append(v)

print()
if falhas:
    sys.exit(f"MONTAGEM COM FALHA em: {', '.join(falhas)}")
print("MONTAGEM CONCLUIDA")
