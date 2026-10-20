#!/usr/bin/env python3
"""Onde este modo acha o lote — e o dado que saiu do codigo ao ser promovido.

MODO "corte e legenda": entrega so' corte e legenda queimada, sem zoom,
transicao, P&B, musica, tarja ou card. Nasceu dos lotes da propria agencia
(03/08 e 05/08 de 2026), que sao o primeiro cliente nao-medico — *"somente
corte e legenda, sem zoom, sem transicao, sem nada"*.

Ate 10/08/2026 estes scripts moravam dentro da pasta do lote, e por isso
usavam `dirname(__file__)` como pasta de dados: `brutos/`, `trabalho/`,
`saida/` e `boxes/` eram vizinhos do codigo. Promovidos para `scripts/`,
isso escreveria dentro da propria caixa de ferramentas. Aqui as quatro
pastas vem do LOTE, pelo mesmo `config.carregar()` que o pipeline de Reels
ja' usa (`--lote NOME` ou a variavel de ambiente `LOTE`).

Tres coisas que eram constante e viraram chave de `lote.json`:

  refeito   Trechos de tomada refeita a REMOVER, por video: {"6": [[33.70, 43.92]]}.
            Havia DUAS copias divergentes disto no mesmo lote — `refazer.py`
            dizia `6: [(33.70, 43.92)]` e `planejar_corte.py` dizia
            `6: [(34.90, 43.85)]`. Ninguem sabia qual valia, e nada
            apontava a contradicao: cada script lia a sua. E' o argumento
            inteiro para dado nao morar em codigo, encontrado dentro de casa.

  frases    Texto das boxes grandes, por numero: {"1": "..."}. Era o texto
            literal do lote da agencia dentro do `gerar_boxes.py`.

  fps       Quadros por segundo do corte. Continua 30 por padrao, que e' o
            valor que os dois lotes usaram.

⚠️ O `refeito` daqui NAO e' o mesmo conceito do `faixas` do lote de Reels.
Aqui e' "este trecho e' tomada refeita, tire fora"; la' e' "estas sao as
faixas a manter". Nao unificar os dois sem medir.
"""
import os
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)

import config  # noqa: E402

L = config.carregar()

if L._dados.get("modo") != "corte_legenda":
    sys.exit(
        f"O lote '{L.nome}' nao e' do modo 'corte_legenda' "
        f"(modo={L._dados.get('modo')!r}).\n"
        f"Este conjunto entrega SO' corte e legenda. Para Reels de medico "
        f"use `scripts/`; para extrair legenda de peca ja publicada, "
        f"`scripts/legendas_prontas/`."
    )

TRAB = L.trabalho
SAIDA = L.saida
BOXES = os.path.join(L.pasta, "boxes")

FPS = int(L._dados.get("fps", 30))
# chaves em string no JSON, int no codigo — o resto do modo indexa por int
REFEITO = {int(k): [tuple(p) for p in v]
           for k, v in L._dados.get("refeito", {}).items()}
FRASES = {int(k): v for k, v in L._dados.get("frases", {}).items()}

# Correcoes de revisao da legenda, por video. Vieram do dicionario CORRECOES
# que morava dentro do `legenda2.py` (movidas em 01/09/2026). O motivo e' o
# de sempre -- dado de lote nao mora em codigo --, mas aqui ele ja' tinha
# dente: o dicionario era indexado por NUMERO DE VIDEO e nao sabia de que
# lote era, entao os videos 3 e 4 do lote 33 (Agencia 31/08) herdavam as
# correcoes dos videos 3 e 4 do lote de 03/08 e o render abortava em
# "correcao nao casou". Chave de string no JSON, int no codigo.
CORRECOES_LEGENDA = {
    int(k): v for k, v in L._dados.get("correcoes_legenda", {}).items()
    if not k.startswith("_")
}

# Qual box vai em cada video: {"1": 5} poe a `frase5` no video 1. Existe
# porque o lote de 03/08 entregava TODAS as frases em TODOS os videos (6
# videos x 3 frases = 18 arquivos, uma subpasta por frase), e o lote 33 e' o
# contrario: 14 videos, cada um com UMA das 4 frases, escolhida pelo assunto
# que a peca trata. Vazio = comportamento antigo (uma versao por frase).
BOX_POR_VIDEO = {
    int(k): int(v) for k, v in L._dados.get("box_por_video", {}).items()
    if not k.startswith("_")
}

# Filtro de audio por video, aplicado no mezanino ANTES do loudnorm. A chave
# se chama `denoise` para bater com a do modo Reels (`config.py:1084`, usada
# pelo `lote_produzir.py`): e' a MESMA coisa, e o projeto nao precisa de dois
# nomes para ela. Nasceu como `filtro_audio` em 01/09/2026 e foi renomeada no
# mesmo dia, ao descobrir que a outra ja' existia desde o lote da Dra. Fulana (para o
# loudnorm medir o sinal ja' limpo). E' dado de lote, nao regua: nasceu no
# lote 33, em que 5 pecas tinham CIGARRA de fundo -- ruido tonal de banda
# estreita em ~5,6 kHz, medido, estacionario, e numa faixa em que a voz dele
# tem 34 dB a menos que o corpo dela.
#
# NAO confundir com o `afftdn`, que continua PROIBIDO neste projeto: aquele
# estima e subtrai um espectro inteiro e deixa resíduo borbulhando ("parece
# que ela ta dentro da agua"). Isto aqui e' um EQ parametrico -- filtro
# linear invariante no tempo, que nao inventa residuo. O custo dele e' tirar
# brilho de sibilante, e isso se decide de OUVIDO, com amostras no mesmo
# volume, nunca por medicao.
DENOISE = {
    int(k): v for k, v in L._dados.get("denoise", {}).items()
    if not k.startswith("_")
}


def bruto(v):
    """Caminho do bruto do video `v`, seja qual for a extensao.

    Era `{v}.mov` fixo em cinco lugares. Delegado ao `config.bruto_de`,
    que existe desde o lote do Dr. Fulano — iPhone entrega `.MOV`,
    export de edicao vem `.mp4`, e aquele lote tinha os dois na mesma pasta.
    """
    return L.bruto_de(v)


def trab(*p):
    os.makedirs(TRAB, exist_ok=True)
    return os.path.join(TRAB, *p)
