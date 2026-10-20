#!/usr/bin/env python3
"""Fonte unica dos nomes do lote — agora vinda do `lote.json`, nao do codigo.

O modo "legendas prontas" NAO edita nada: le peca ja publicada e devolve o
`.srt` do que esta QUEIMADO na tela. Nao ha faixa de corte, nem zoom, nem
musica para parametrizar — mas ha, sim, dado de lote: onde as pecas moram,
quais faltam, e quais ja tem `.srt` aprovado para servir de gabarito.

Ate 10/08/2026 esses tres dados eram constantes dentro de `lista.py` e
`calibrar.py`, no lote do Dr. Fulano. Isso prendia o modo inteiro
naquele lote: o segundo lote teria de copiar os 12 scripts e editar dois
deles. Aqui eles viram `lote.json`, pela mesma regra que ja vale para o
resto do projeto — dado de lote nao mora em codigo.

Chaves lidas de `lote.json` (ver `Lotes/MODELO-lote-legendas.json`):

    modo       "legendas"  -- obrigatorio, e o que distingue dos lotes de Reels
    origem     pasta das pecas publicadas (absoluta; costuma ser o Drive)
    legendas   subpasta de destino dentro de `origem` (padrao "Legendas")
    arquivos   [[nome do arquivo, apelido curto], ...] -- os que FALTAM
    gabaritos  [[nome do arquivo, apelido curto], ...] -- os que ja tem .srt

Exporta os mesmos nomes que a versao antiga (`PASTA`, `LEGENDAS`,
`FALTANDO`, `caminho`, `trab`), mais `GABARITOS`, `SAIDA` e `CORRECOES`,
que antes moravam espalhados em `calibrar.py` e em `os.path.join(AQUI, ...)`.
"""
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)

import config  # noqa: E402

_L = config.carregar()

if _L._dados.get("modo") != "legendas":
    sys.exit(
        f"O lote '{_L.nome}' nao e' do modo 'legendas' "
        f"(modo={_L._dados.get('modo')!r}).\n"
        f"Este conjunto de scripts le peca JA PUBLICADA e extrai a legenda "
        f"queimada.\nPara Reels de medico use `scripts/`; para so' corte e "
        f"legenda, `scripts/corte_legenda/`."
    )

PASTA = _L._dados.get("origem") or ""
if not PASTA:
    sys.exit(f"Falta `origem` no lote.json de '{_L.nome}' — a pasta onde as "
             f"pecas publicadas moram.")
LEGENDAS = os.path.join(PASTA, _L._dados.get("legendas", "Legendas"))

# `trabalho/` e `saida/` sao do LOTE, nao da pasta dos scripts. Enquanto o
# modo vivia dentro do lote as duas coisas eram a mesma pasta, e por isso
# os scripts usavam `dirname(__file__)`. Promovido, isso escreveria dentro
# de `scripts/` — mistura codigo com artefato de trabalho.
TRAB = _L.trabalho
SAIDA = _L.saida
CORRECOES = os.path.join(_L.pasta, "correcoes.json")

FALTANDO = [tuple(x) for x in _L._dados.get("arquivos", [])]
GABARITOS = [tuple(x) for x in _L._dados.get("gabaritos", [])]


def caminho(nome):
    return os.path.join(PASTA, nome)


def trab(*p):
    os.makedirs(TRAB, exist_ok=True)
    return os.path.join(TRAB, *p)
