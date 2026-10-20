#!/usr/bin/env python3
"""Caminhos e configuração de lote — ponto único de verdade.

Antes desta versão, cada script tinha os caminhos do lote de julho fixos no
topo, e as decisões editoriais de cada vídeo (faixas de corte, correções de
legenda, quem fica sem P&B) moravam DENTRO do `lote_produzir.py`. Rodar um
lote novo obrigava a editar o código — e editar código para mudar dado é
como se perde o que já funcionava.

Agora:

  * os caminhos de ferramenta e asset vivem aqui;
  * as decisões de cada lote vivem no `lote.json` do próprio lote.

Uso nos scripts:

    import config
    L = config.carregar()            # lê --lote/LOTE, ou o único que existir
    L.trabalho, L.brutos, L.faixas, ...

Na linha de comando:

    python scripts/lote_produzir.py --lote "2026-08 - Dr. Fulano" 3 5
    LOTE="2026-08 - Dr. Fulano" python scripts/lote_produzir.py
"""
import json
import os
import re
import subprocess
import sys

RAIZ = os.path.dirname(os.path.abspath(__file__))
LOTES = os.path.join(RAIZ, "Lotes")
ASSETS = os.path.join(RAIZ, "assets")
FONTES = os.path.join(ASSETS, "fonts")
CLIENTES = os.path.join(ASSETS, "clientes")
# clipes de b-roll, uma subpasta por cliente
BROLL = os.path.join(ASSETS, "broll")
# `referencia/` são os vídeos contra os quais TODO o padrão foi medido: os 6
# que o operador fez no Premiere e os 9 aprovados de julho. São 596 MB e não
# sobem para o repositório — mas sem eles não há como validar medidor nenhum
# contra verdade conhecida, que é a regra 2b. Por isso a pasta local vale
# quando existir, e na falta dela vale a cópia no Drive (`referencia` no
# `caminhos.local.json`). Ver `_local`, mais abaixo.
REFERENCIA = os.path.join(RAIZ, "referencia")

# --- ferramentas e assets que não mudam por lote -------------------------
# Estes três não mudam por LOTE, mas mudam por MÁQUINA: moram fora do projeto,
# em drives (`D:`, `E:`) que só existem no PC de quem montou o pipeline. Com o
# projeto versionado e um segundo editor, caminho absoluto no código chega
# QUEBRADO na outra máquina — e quebra em runtime, no meio de um lote, não na
# hora de instalar. Por isso vivem em `caminhos.local.json`, que fica FORA do
# git: cada máquina tem o seu, escrito uma vez na instalação.
#
# Ordem de resolução, do mais específico ao menos:
#   1. variável de ambiente (`EDICAO_MODELO_WHISPER`, `EDICAO_LEAK`, ...)
#   2. `caminhos.local.json` na raiz do projeto
#   3. nada — e aí o erro diz qual chave falta, em vez de "arquivo não
#      encontrado" três fases adiante.
CAMINHOS_LOCAIS = os.path.join(RAIZ, "caminhos.local.json")
EXEMPLO_LOCAIS = os.path.join(RAIZ, "caminhos.local.exemplo.json")


def _locais():
    try:
        with open(CAMINHOS_LOCAIS, encoding="utf-8") as f:
            return {k: v for k, v in json.load(f).items()
                    if not k.startswith("_")}
    except (OSError, ValueError):
        return {}


_LOCAIS = _locais()


def _local(chave):
    """String sempre — vazia quando não configurado. Nunca None, nunca objeto.

    Estes três são consumidos como STRING de verdade em pontos que não
    aceitam substituto: `MODELO_WHISPER` é fatiado por drive em
    `_modelo_para_filtro`, e `MUSICAS`/`LEAK` entram em `os.path.join` e na
    linha de comando do ffmpeg. Devolver aqui um objeto "preguiçoso" que só
    resolve ao ser usado quebraria o fatiamento — foi a primeira versão
    disto, e o próprio código do projeto a derrubou.
    """
    return os.environ.get("EDICAO_" + chave.upper()) or _LOCAIS.get(chave) or ""


def exigir_caminho(chave, para_que):
    """Chamado por quem VAI usar o caminho, não no import.

    Assim um lote de legendas — que não toca em música nem em leak — roda
    numa máquina que nunca configurou os dois.
    """
    v = _local(chave)
    if v:
        return v
    sys.exit(
        f"Falta o caminho `{chave}` ({para_que}).\n"
        f"Ele é específico desta máquina, então não vem no repositório.\n"
        f"Copie `{os.path.basename(EXEMPLO_LOCAIS)}` para "
        f"`{os.path.basename(CAMINHOS_LOCAIS)}` e preencha, "
        f"ou defina a variável de ambiente `EDICAO_{chave.upper()}`."
    )


MODELO_WHISPER = _local("modelo_whisper")
LEAK = _local("leak")
MUSICAS = _local("musicas")

# Acervo de musica de fundo (02/10/2026, decisao do operador): UMA pasta, sem
# subpasta, onde ele mesmo joga faixa nova. A busca antiga por `Musicas\2`
# saiu (a subpasta nao existia desde 15/08). Fonte UNICA da lista para
# lote_produzir, montar_lote e conferir_lote -- antes cada um tinha a sua
# copia do mesmo laco, e as tres tinham de concordar na ORDEM, porque e' a
# ordem que decide qual faixa cada video recebe.
EXT_MUSICA = (".mp3", ".wav", ".m4a")


def faixas_de_musica(pasta=None):
    """Faixas utilizaveis do acervo, em ordem estavel (nome, `sorted`).

    Ignora "Copia" (duplicata do Windows) e qualquer coisa que nao seja audio
    (desktop.ini, LEIA-ME.txt). Pasta ausente devolve lista vazia.
    """
    pasta = pasta or MUSICAS
    if not pasta or not os.path.isdir(pasta):
        return []
    return [os.path.join(pasta, f) for f in sorted(os.listdir(pasta))
            if f.lower().endswith(EXT_MUSICA) and "Copia" not in f
            and os.path.isfile(os.path.join(pasta, f))]
# Estante dos vídeos que o MÉDICO aprovou (Drive, compartilhada com o
# analista). Só `aprovar_video.py` escreve nela; quem precisa medir um
# aprovado de um cliente lê daqui. Vazio numa máquina sem o Drive.
APROVADOS = _local("aprovados")

# A pasta local vence, quando existir — é mais rápida e não depende do Drive
# montado. Só cai para a cópia compartilhada quando a local não estiver ali.
if not os.path.isdir(REFERENCIA) and _local("referencia"):
    REFERENCIA = _local("referencia")


# Prioridade baixa para todo processo pesado que o pipeline dispara. E' zero
# em qualquer sistema que nao seja Windows, onde o flag nao existe.
PRIORIDADE_BAIXA = getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0) \
    if os.name == "nt" else 0


def fps_de(src):
    """Taxa de quadros do bruto, como fracao exata (24000/1001, nao 23,976).

    Derivada do ARQUIVO, nunca constante — mesmo padrao de `tonemap_de` e
    `nivel_silencio_de`. Assumir lote homogeneo ja custou 3 rodadas (fps
    misto) e 5 pecas entregues lavadas (HLG).
    """
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                        "-show_entries", "stream=r_frame_rate",
                        "-of", "default=nw=1:nk=1", src],
                       capture_output=True, text=True)
    try:
        num, den = r.stdout.strip().split("/")
        f = float(num) / float(den)
        return f if f > 0 else 30.0
    except (ValueError, ZeroDivisionError):
        return 30.0


# Trecho mais curto que isto e' absorvido pelo anterior: o corte que o
# criaria e' descartado.
#
# Por que e REGUA e nao dado de lote: o degrau de zoom acontece em TODO
# corte, entao um trecho de 0,3 s recebe degrau na entrada E na saida --
# duas trocas de enquadramento em menos de um terco de segundo. Isso le como
# piscar, nunca como edicao, em qualquer lote.
#
# Achado no v10 da Dra. Fulana (10/08/2026): trecho de 0,29 s (o "o
# que" de "entende o que resolve", entre duas pausas reais), reportado pelo
# analista como "erro na edicao no segundo 00:22".
#
# Nem `pausa_minima` nem `nivel_silencio` resolvem, e as duas foram testadas:
#   * por DURACAO -- a pausa que cria o trecho mede 0,388 s e ha tres pausas
#     legitimas MENORES (0,346 s). O limiar que mata uma mata as outras: com
#     `pausa_minima: 0.40` o v10 caiu para 6 trechos em 29,3 s (~10 cortes/min
#     contra os 29 do video 7), trocando o piscar por "sem zoom do meio pro
#     fim", que o operador ja reprovou.
#   * por NIVEL -- `nivel_silencio: -46` (contra -41 do automatico) nao mudou
#     nada: a pausa e' silencio fundo de verdade, nao fenda de consoante.
#
# 0,6 s: abaixo disso nenhum trecho do lote 1 (aprovado) cai, e o menor
# trecho do video 7 mede 1,0 s.
MIN_TRECHO = 0.6


# Vao que a absorcao de trecho curto pode reintroduzir sem virar buraco.
#
# Absorver e' ESTICAR O FIM do trecho anterior ate' o curto -- o que ha entre
# os dois volta para dentro da peca. Quando sao vizinhos, o que volta e' a
# respiracao que o corte ia tirar, e o resultado e' o desejado. Quando ha
# silencio longo no meio, o que volta e' BURACO.
#
# 0,35 s cobre o caso que criou o `MIN_TRECHO` (v10 da Dra. Fulana,
# 10/08/2026): la' a pausa detectada media 0,388 s e o vao EFETIVO, depois do
# PAD de 180 ms, e' 0,208 s. O comportamento aprovado naquele lote continua
# identico. Acima disto o trecho curto e' DESCARTADO em vez de absorvido.
MAX_VAO_ABSORVIDO = 0.35

# Piso ABAIXO do qual descartar e' permitido. Na altura em que a decisao e'
# tomada ainda nao existe transcricao, entao nao da' para perguntar "isso e'
# palavra?". O que da' para usar e' a DURACAO, e ela separa bem os dois casos.
#
# A regra de cima nasceu de um CLIQUE de 0,09 s (0,27 s depois do PAD) que,
# absorvido, devolvia 2,53 s de silencio. O docstring do `sem_trechos_curtos`
# concluia dali que "trecho abaixo do piso e isolado por mais de 0,35 s e'
# clique ou respiracao". **Essa conclusao e' falsa perto do piso**, e custou
# fala em duas pecas deste lote (21, Dra. Fulana, 19/08/2026):
#
#   v2, 31,35 s: bloco de 0,50 s DESCARTADO, vao de 0,47 s. Era a palavra
#                "Pode." -- a RESPOSTA da pergunta "Pode ser escoliose?".
#   v6, 10,74 s: bloco de 0,50 s DESCARTADO, vao de 0,47 s. Era "Pois e,".
#
# Nos dois o vao passou de `MAX_VAO_ABSORVIDO` por 12 centesimos, e o preco de
# nao absorver foi apagar uma palavra da peca. **Devolver 0,47 s de pausa e'
# muito menos grave que deletar fala** -- ainda mais em peca de medico, onde
# palavra some queimada e ninguem ouve o que faltou.
#
# 0,40 fica no meio dos dois regimes MEDIDOS: acima do clique da Dra. Fulana
# (0,27 s, que continua sendo descartado -- o comportamento aprovado la' nao
# muda) e abaixo das palavras deste lote (0,50 s, que passam a ser absorvidas).
MIN_DESCARTE = 0.40


def sem_trechos_curtos(segs, minimo=MIN_TRECHO, avisar=None):
    """Absorve trecho curto demais no vizinho — sem ressuscitar silencio.

    A versao anterior fazia `saida[-1][1] = b` sempre, isto e', esticava o fim
    do trecho anterior ate' o curto seja qual fosse a distancia. Medido no v4
    deste lote (Dra. Fulana, 12/08/2026): um bloco de fala de **0,09 s**
    em 66,08 (um clique, nao uma palavra) virou trecho de 0,27 s depois do PAD,
    ficou abaixo do piso, e ao ser absorvido esticou o trecho anterior de 63,64
    ate' 66,27 -- devolvendo **2,53 s de silencio** que o corte tinha acabado
    de remover. Na peca isso e' o vao entre "Para" e "entender": 2,08 s de ar
    morto no meio de uma frase.

    O `silencedetect` tinha achado essa pausa certinho (63,55 -> 66,07). O
    defeito nao estava na deteccao nem no limiar: estava aqui, depois.

    Agora a absorcao so' acontece se o vao a reintroduzir couber em
    `MAX_VAO_ABSORVIDO`. Se nao couber, tenta o vizinho seguinte; se nenhum dos
    dois estiver perto, o trecho curto e' **descartado** e o vao continua
    removido. Descartar e' seguro no caso que motiva a regra porque um trecho
    abaixo do piso, isolado por mais de 0,35 s de silencio dos dois lados, e'
    clique ou respiracao -- mas como isso E' descartar audio, passa `avisar`
    para o chamador imprimir o que saiu, em vez de sumir calado.
    """
    if len(segs) < 2:
        return segs
    saida = [list(segs[0])]
    for a, b in segs[1:]:
        if b - a >= minimo:
            saida.append([a, b])
            continue
        if a - saida[-1][1] <= MAX_VAO_ABSORVIDO or b - a >= MIN_DESCARTE:
            # vizinho: o corte que criaria o trecho some.
            # OU longe, mas grande demais para ser clique: absorve mesmo
            # devolvendo silencio, porque descartar aqui apaga FALA.
            saida[-1][1] = b
        else:
            # curto E longe: e' clique ou respiracao, e o vao continua removido
            if avisar:
                avisar(a, b, a - saida[-1][1])
    if len(saida) > 1 and saida[0][1] - saida[0][0] < minimo:
        if (saida[1][0] - saida[0][1] <= MAX_VAO_ABSORVIDO
                or saida[0][1] - saida[0][0] >= MIN_DESCARTE):
            saida[1][0] = saida[0][0]
        elif avisar:
            avisar(saida[0][0], saida[0][1], saida[1][0] - saida[0][1])
        saida.pop(0)
    return [tuple(s) for s in saida]


MIN_GAP = 0.12


def sem_gaps_curtos(segs, minimo=MIN_GAP):
    """Funde trechos separados por um vao curto demais para valer um CORTE.

    O que existe antes disto: a fusao so acontecia com vao <= 10 ms, isto e',
    quando os trechos praticamente se encostavam. Um vao de 66 ms passava, e
    virava um corte de verdade -- com degrau de zoom junto, porque neste
    padrao TODO corte leva degrau.

    Por que 66 ms nao vale um corte: o corte existe para tirar silencio. Um
    que remove 66 ms nao tira silencio nenhum -- e o menor vao do video (os
    outros vao de 130 a 900 ms) -- e em troca troca o enquadramento no meio
    de uma frase. Medido no lote do Dr. Fulano (11/08/2026): a
    hesitacao de 220 ms dentro de "A tecnologia entra / justamente" virava
    corte, o `PAD` comia 154 ms das bordas, e sobrava um corte de 66 ms que
    deixava a legenda "ENTRA" 0,30 s na tela contra 0,65-0,79 s dos vizinhos.
    O operador leu como *"esse 'entra' passou bem rapido e ai quebrou"*.

    Por que e REGUA e nao dado de lote, pelo mesmo criterio do MIN_TRECHO:
    os dois caminhos de dado foram testados e nenhum serve. `pausa_minima`
    nao alcanca -- a pausa DETECTADA la e 220 ms e passa em qualquer limiar
    razoavel; quem encolhe o vao para 66 ms e o `PAD`, que e regua. E
    `nivel_silencio` mexe em quais pausas existem, nao no tamanho do vao
    depois do PAD.

    E a mesma licao do lote 8 escrita de outro jeito: excecao e limite se
    conferem contra o valor EFETIVO, depois de PAD e snap, nunca contra o
    numero que esta no lote.json.
    """
    if len(segs) < 2:
        return segs
    saida = [list(segs[0])]
    for a, b in segs[1:]:
        if a - saida[-1][1] < minimo:
            saida[-1][1] = b          # o vao nao compensa o corte: funde
        else:
            saida.append([a, b])
    return [tuple(s) for s in saida]


def trechos_das_faixas(blocos, faixas, dur, fps, pad, mingap=MIN_GAP,
                       vetados=(), cauda=False):
    """Blocos de fala -> TRECHOS do corte, com PAD, grade, MIN_GAP e MIN_TRECHO.

    Mora aqui porque `montar` estava COPIADO em `lote_preparar` e
    `lote_produzir`, e este arquivo ja tem duas cicatrizes de conserto feito
    so' de um lado (ver `na_grade`). Duplicata de regra de corte e' divergencia
    esperando data.

    **A fusao acontece DENTRO de cada faixa, nunca entre faixas.** Esse e' o
    conserto de 12/08/2026, no lote da Dra. Fulana, e o motivo importa:

    `sem_trechos_curtos` absorve um trecho curto demais ESTICANDO O FIM do
    trecho anterior (`saida[-1][1] = b`). Entre dois trechos da mesma faixa
    isso e' inofensivo — o que ha no meio e' o silencio que o corte ia tirar.
    Entre faixas e' desastre: o que ha no meio e' exatamente o material que a
    faixa existe para EXCLUIR.

    Medido no v6 deste lote: as faixas eram (47,77-54,05), (64,81-78,61) e
    (105,84-144,68). O primeiro bloco da segunda faixa media 0,23 s depois do
    PAD — abaixo do MIN_TRECHO de 0,6 s. Ele foi absorvido para tras, no
    trecho que terminava em 53,82 da PRIMEIRA faixa, e o resultado foi um
    trecho de 49,22 a 64,96: **10,8 s de direcao de camera ("Congela", "Um,
    dois, tres") de volta para dentro da peca**. O v3 tinha o mesmo defeito,
    com 3,5 s.

    Como isso passa por tudo: a fase 1 sai com exit 0, os arquivos existem e
    tem tamanho plausivel, e o `_corte.wav` toca. O unico sinal e' o corte
    ficar MAIOR que a soma das faixas, que nada media. Mesma familia dos
    portoes que medem o PROCESSO em vez do ARTEFATO (docs/03 §Y).

    Por isso a funcao termina conferindo o artefato: nenhum trecho pode sair
    das faixas. Guarda barata contra a proxima variante do mesmo erro.
    """
    saida = []
    for fs, fe in faixas:
        segs = []
        for a, b in blocos:
            x, y = max(a, fs), min(b, fe)
            if y - x <= 0.05:
                continue
            x, y = max(0.0, x - pad / 2), min(dur, y + pad / 2)
            x, y = na_grade(x, fps), na_grade(y, fps)
            if segs and x <= segs[-1][1] + 0.01:
                segs[-1] = (segs[-1][0], y)
            else:
                segs.append((x, y))
        # vao curto demais nao paga o corte que ele cria (motivo em
        # `sem_gaps_curtos`), e a fusao vem ANTES do piso de trecho: fundir
        # dois trechos pode justamente tirar um deles de baixo do MIN_TRECHO.
        segs = sem_gaps_curtos(segs, mingap)
        # trecho curto demais vira piscar de enquadramento. O `avisar` existe
        # porque descartar trecho e' descartar AUDIO: tem de aparecer no log.
        def _avisar(a, b, vao, _fs=fs):
            print(f"      trecho de {b - a:.2f}s em {a:.2f}s DESCARTADO: "
                  f"absorve-lo devolveria {vao:.2f}s de silencio a peca")
        segs = sem_trechos_curtos(segs, avisar=_avisar)
        # O PAD empurra a borda para fora da faixa em ate' pad/2. Dentro da
        # faixa isso e' o de sempre; para FORA dela e' vazamento, e e' o que
        # deixava o "Congela" aparecer. Corta na faixa e refaz a grade.
        for x, y in segs:
            x, y = na_grade(max(x, fs), fps), na_grade(min(y, fe), fps)
            if y - x > 0.05:
                saida.append((x, y))
    saida.sort()
    # CAUDA MUDA (`cauda` no lote.json, por video).
    #
    # O corte existe para tirar silencio, entao ele descarta por construcao um
    # final sem fala. Mas o operador as vezes termina a faixa DEPOIS da ultima
    # fala de proposito: no lote do Dr. Fulano (02/09/2026) a pessoa
    # que filma aproxima a camera e mostra o medico usando o aparelho, e ele
    # pediu esses segundos em quatro pecas.
    #
    # Por que isto nao e' dado, medido antes de escrever: o unico lever de dado
    # que traz a cauda e' subir `nivel_silencio` ate' o corte voltar para a rota
    # do `silencedetect`. No v4 daquele lote isso exige -30 dB contra RMS -29 --
    # ou seja RMS-1, quando a regua e' RMS-8 e NUNCA acima de RMS-6. E' o mesmo
    # limiar que comeu "in Pinheiros" e devolveu "nheiros". Alem disso trocaria
    # o corte do video inteiro (10 trechos -> 7) e criaria dois cortes DENTRO do
    # silencio, que e' o "corte que nao economiza silencio" da regra 3b.
    #
    # E ele conserta um acidente, nao so' uma falta: no v3 do mesmo lote a cauda
    # ja' entrava, mas por CEGUEIRA do `silencedetect` (que mede pico e nao ve
    # pausa onde o RMS esta' a -51 dB). Com a chave, os dois passam a depender de
    # uma decisao escrita em vez da rota que o detector escolheu.
    if cauda and saida:
        fe = max(fim for _, fim in faixas)
        a, b = saida[-1]
        if fe > b:
            saida[-1] = (a, na_grade(min(fe, dur), fps))
    # Cortes VETADOS por vídeo (`cortes_vetados` no lote.json).
    #
    # Existe porque nem todo corte legítimo por SILÊNCIO é legítimo pela
    # IMAGEM. No v2 da Dra. Fulana (12/08/2026) o corte depois de
    # 51,38 s tira 0,33 s de pausa real -- mas cai no meio de ela
    # reposicionar o cartão que está mostrando. O objeto teleporta, e a
    # analista leu como "ela erra o take e repete, e você deixa". O leak
    # disfarça o CORTE; não disfarça um objeto mudando de lugar.
    #
    # Por que não dá para resolver com o dado que já existe, testado antes
    # de escrever isto: a pausa ali mede 0,51 s detectada, e `pausa_minima`
    # alta o bastante para matá-la mata **7 dos 10 cortes** do vídeo --
    # trocaria o salto do cartão por "sem zoom do meio pro fim", que ele já
    # reprovou. É o mesmo raciocínio do `MIN_TRECHO`: quando os dois
    # caminhos de dado falham MEDIDOS, a régua nova se justifica.
    #
    # É dado de LOTE e não régua: qual corte estraga a imagem depende do que
    # ela faz com as mãos naquele vídeo, não do padrão de edição.
    if vetados:
        fundido, i = [saida[0]] if saida else [], 1
        while i < len(saida):
            x, y = saida[i]
            fim_anterior = fundido[-1][1]
            # o veto casa com a FRONTEIRA do corte, com tolerância de meio
            # quadro para os dois lados (a fronteira passou por `na_grade`)
            if any(fim_anterior - 0.25 <= t <= x + 0.25 for t in vetados):
                fundido[-1] = (fundido[-1][0], y)
                print(f"      corte apos {fim_anterior:.2f}s VETADO pelo "
                      f"lote.json: trechos fundidos, {x - fim_anterior:.2f}s "
                      f"de pausa voltam para a peca")
            else:
                fundido.append((x, y))
            i += 1
        saida = fundido
    for x, y in saida:
        if not any(fs - 0.05 <= x and y <= fe + 0.05 for fs, fe in faixas):
            raise SystemExit(
                f"trecho ({x:.2f}, {y:.2f}) nao cabe em nenhuma faixa "
                f"{faixas} — isto e' o bug de fusao entre faixas voltando. "
                f"NAO renderize: o corte esta com material excluido dentro.")
    return saida


def na_grade(t, fps):
    """Instante mais proximo que cai EXATAMENTE num quadro do bruto.

    Por que toda fronteira de corte passa por aqui: o `trim` de video so
    corta em quadro e anda o limite ate um; o `atrim` de audio corta no
    instante exato. Fronteira fora da grade da ao trecho um video e um audio
    de duracoes diferentes, e o erro SOMA trecho a trecho -- a legenda, que e
    cronometrada nessa linha do tempo, descola da fala do render.

    Medido no lote da Dra. Fulana (10/08/2026), bruto a 24000/1001
    fps: as 22 fronteiras do v5 tinham resto de -19 a +19 ms, e a deriva
    subia de 0 a +90 ms ao longo do video, ~9 ms por corte (meio quadro da
    10,4 ms). Passava de 40 ms em 7 dos 10 videos.

    Nao aparecera antes porque nenhum lote anterior era 23,976 fps: aqui o
    quadro dura 41,7 ms, contra 33,4 ms a 30 fps e 16,7 ms a 59,94.

    MORA AQUI, e nao dentro dos scripts, porque `segmentos()` esta duplicado
    em `lote_preparar` e `lote_produzir`. Consertei so' um dos dois primeiro,
    e a guarda de timeline abortou o render dizendo que a legenda era de
    outro corte -- ela estava certa: os dois lados calculavam cortes
    diferentes. Funcao compartilhada para o conserto nao ter dois donos.
    """
    return round(t * fps) / fps


def inicio_do_audio(src):
    """`start_time` do 1o stream de audio, em s (0.0 se ilegivel).

    Quem extrai audio com `-ss 0` recebe um wav que comeca AQUI, nao em 0.
    """
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0",
                        "-show_entries", "stream=start_time",
                        "-of", "default=nw=1:nk=1", src],
                       capture_output=True, text=True)
    try:
        return max(0.0, float(r.stdout.strip()))
    except ValueError:
        return 0.0


def exigir_audio_no_inicio(v, src, segs):
    """Aborta se o 1o trecho comeca ANTES de o audio do bruto existir.

    O `trim` de video e o `atrim` de audio cortam no relogio do ARQUIVO. Bruto
    recomprimido (Lavf, cara de WhatsApp) traz o audio com `start_time` > 0:
    o `atrim` de um trecho que comeca antes disso devolve menos audio que o
    `trim` devolve de video, e o concat adianta o audio de TODO o resto da
    peca por essa diferenca. `sync` do lote_verificar nao ve (compara duracao
    total). Medido no lote 67 (Dra. Fulana, 24/09/2026): v9 com audio em
    0,744 s e faixa em 0,11 -> `9_corte.wav` 0,644 s mais curto que o corte.

    Mora aqui pelo mesmo motivo da `na_grade`: `segmentos()` e' duplicado em
    lote_preparar e lote_produzir, e a trava tem de valer nos dois.
    """
    ini = inicio_do_audio(src)
    if segs and segs[0][0] < ini - 0.001:
        raise SystemExit(
            f"v{v}: o 1o trecho comeca em {segs[0][0]:.3f} s e o AUDIO do "
            f"bruto so' comeca em {ini:.3f} s (start_time). O audio do corte "
            f"sairia {ini - segs[0][0]:.3f} s mais curto e adiantaria o resto "
            f"da peca. Suba o inicio da 1a faixa para >= {ini:.3f}.")


_ENCODER = None


def encoder_video():
    """Argumentos de encode de video: `h264_nvenc` se ABRIR, senao libx264.

    O teste e' ABRIR o encoder, nao lista-lo. Este projeto ja' se enganou
    duas vezes com isso: os tres encoders NVIDIA aparecem em `-encoders`
    mesmo quando o driver nao os sustenta, e falham so' na hora de abrir.
    Por isso aqui roda um encode de 1 segundo em `lavfi` e olha o codigo de
    saida.

    Historia, porque ela explica os numeros: ate 10/08/2026 o nvenc era
    inutilizavel nesta maquina -- o build do ffmpeg pede a API 13.1, que
    exige driver 610.00+, e a GTX 1650 estava no 595.97. Em 14/08/2026 o
    driver estava em 610.88 e o teste de abertura passou.

    Preset p7 + `tune hq` + `cq 19` e' o ponto mais alto de qualidade do
    NVENC de Turing, com lookahead e AQ espacial ligados -- e' o que chega
    mais perto do libx264 `medium`/CRF 19 em borda de letra, que e' onde a
    diferenca aparece nas pecas deste projeto (legenda com contorno fino
    sobre fundo desfocado).

    ATENCAO: a GPU tem 4 GB e o faster-whisper ocupa ~3,5 GB quando roda.
    Encodar e transcrever ao mesmo tempo faz os dois brigarem -- medido em
    14/08: a transcricao rendeu 6 s de CPU em 10 min de relogio com os
    renders em cima. Rodar um de cada vez.
    """
    global _ENCODER
    if _ENCODER is not None:
        return list(_ENCODER)
    base_x264 = ["-c:v", "libx264", "-preset", "medium", "-crf", "19",
                 "-profile:v", "high", "-pix_fmt", "yuv420p",
                 "-threads", str(threads_encode())]

    # EDICAO_ENCODER=cpu|gpu forca a escolha. Existe porque o automatico erra
    # nos DOIS sentidos, e os dois aconteceram no mesmo dia (24/08/2026):
    #
    #   - Escolhe CPU por acidente: o teste de abertura roda UMA vez por
    #     processo e fica em cache. Com a GPU momentaneamente cheia (4 agentes
    #     de faster-whisper ocupavam 3,7 dos 4 GB), o teste falhou e o lote
    #     INTEIRO foi para libx264 -- e continuou la depois de a GPU esvaziar.
    #
    #   - Escolhe GPU e TRAVA: com a GPU livre, o teste passa (encoda 1 s de
    #     `testsrc` sem erro) e o pipeline real deste projeto trava. Medido no
    #     v1 do lote do Fulano: 34 min de relogio, `utilization.encoder` em 0 %
    #     em 9 leituras seguidas, ZERO byte escrito em 8 s e um unico nucleo a
    #     105 %. O mesmo video em libx264 fecha em 17 min. O teste de abertura
    #     nao reproduz o grafo real -- filtros pesados em CPU alimentando
    #     encoder em GPU e' outro caminho de codigo.
    #
    # Ou seja: `h264_nvenc` ABRIR nao prova que ele ENCODA este grafo. Ate
    # alguem investigar o travamento, CPU e' a rota confiavel nesta maquina.
    _forcado = os.environ.get("EDICAO_ENCODER", "").strip().lower()
    if _forcado == "cpu":
        _ENCODER = tuple(base_x264)
        return list(_ENCODER)

    try:
        t = subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error",
             "-f", "lavfi", "-i", "testsrc=size=1080x1920:rate=30:duration=1",
             "-c:v", "h264_nvenc", "-f", "null", "-"],
            capture_output=True, text=True, timeout=60)
        ok = t.returncode == 0
    except Exception:
        ok = False
    if _forcado == "gpu":
        ok = True
    _ENCODER = (["-c:v", "h264_nvenc", "-preset", "p7", "-tune", "hq",
                 "-rc", "vbr", "-cq", "19", "-b:v", "0",
                 "-maxrate", "24M", "-bufsize", "48M",
                 "-rc-lookahead", "32", "-spatial-aq", "1", "-aq-strength", "8",
                 "-profile:v", "high", "-pix_fmt", "yuv420p"]
                if ok else base_x264)
    return list(_ENCODER)


def encoder_nome():
    return "h264_nvenc" if "h264_nvenc" in encoder_video() else "libx264"


def threads_encode(deixar_livre=0.5):
    """Quantas threads o libx264 pode usar, deixando maquina para o operador.

    So' vale quando o encode cai em CPU -- ver `encoder_video()`, que hoje
    escolhe `h264_nvenc` nesta maquina (driver 610.88 desde 14/08/2026).

    Sem teto, o libx264 abre uma thread por processador logico e ocupa os 12
    do Ryzen 5600G. O operador reportou, no meio do lote da Dra. Fulana, que nao conseguia usar o proprio PC ("ta matando meu pc"). O lote
    demora mais e ele trabalha -- e o custo de render aqui e' tempo de
    maquina, nao token.

    Se o driver for atualizado para 610+, o caminho certo passa a ser
    `h264_nvenc`, e ai isto vira irrelevante. Mas trocar de encoder muda a
    imagem: medir contra o libx264 antes de adotar.
    """
    total = os.cpu_count() or 4
    return max(1, int(total * (1.0 - deixar_livre)))


def tonemap_de(src, npl=100):
    """Cadeia HDR->SDR quando o bruto e' HLG, string vazia quando ja e' SDR.

    O iPhone grava em HLG (`arib-std-b67` / BT.2020, 10 bits) e a camera do
    consultorio alterna isso vídeo a vídeo, sem aviso. Jogar HLG direto no
    libx264 yuv420p NAO converte nada: os codigos sao lidos como se fossem
    BT.709, e o resultado e' imagem clara demais e sem cor.

    Medido no lote da Dra. Fulana (05/08/2026). Dos 8 brutos, 5 eram
    HLG — e foram EXATAMENTE os 5 que o cliente reprovou como "estourada,
    clara demais" e "pessoas amarelas". Nos entregues:

        HLG sem tone-map (v1,3,4,7,8)   YAVG 133-157   SATAVG  6,8-9,3
        SDR normal       (v2,5,6)       YAVG 109-128   SATAVG 12,9-14,7

    O "amarelo" e' consequencia da saturacao pela metade: sem cor na pele,
    a luz quente do consultorio domina. `hable` com `npl=100` foi escolhido
    de OLHO pela analista, entre hable/mobius/npl 200 — nao pelo numero.
    Ele devolve a saturacao (13,0) mantendo a luminancia; se voltar queixa
    de brilho, o ajuste e' o `npl`, nao o diagnostico.

    Nao aplicar em bruto SDR: a cadeia linear->tonemap escureceria material
    que ja esta certo. Por isso a deteccao e' por arquivo, nunca por lote —
    o lote NAO e' homogeneo, e assumir que era foi o erro por tras do bug
    de fps (ver docs/03-armadilhas.md).
    """
    import subprocess

    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                        "-show_entries", "stream=color_transfer",
                        "-of", "default=nw=1:nk=1", src],
                       capture_output=True, text=True)
    transfer = r.stdout.strip().lower()
    if transfer not in ("arib-std-b67", "smpte2084"):
        return ""
    return (f"zscale=t=linear:npl={npl},tonemap=hable:desat=0,"
            "zscale=p=bt709:t=bt709:m=bt709:r=tv,format=yuv420p,")


def cor_de(src, lut):
    """Cadeia que aplica o LUT de cor do cliente, ou string vazia sem LUT.

    Existe para o bruto que chega SEM COR — a Dra. Fulana grava em S-Log3 /
    SGamut3.Cine de proposito, para a cor ser feita na edicao. Isso NAO e'
    HLG nem PQ: o `color_transfer` vem `unknown` e o `tonemap_de` devolve
    string vazia, corretamente. Quem converte aqui e' o LUT, e sem ele a
    imagem sai chapada (saturacao media 1,5 contra 12 depois do LUT).

    Duas coisas que quebram se forem esquecidas:

    **Range.** O bruto e' `yuvj420p` (full) e o LUT da Sony e' `full in
    full out` — esta escrito no cabecalho do arquivo. Tratar como limitado
    em qualquer ponto lava o preto e corta o branco. Por isso o
    `scale=in_range=full:out_range=full` explicito, mesmo parecendo no-op.

    **Precisao.** O `lut3d` interpola, e em 8 bits a interpolacao numa
    imagem log — que e' quase toda meio-tom — gera banda visivel em parede
    lisa. Por isso `gbrp16le` antes, e a volta para 8 bits so' depois.

    O `.cube` de um cliente e' dado de lote (`lut` no lote.json), nunca
    constante: cada medico grava com um perfil, e a Fulano e' a unica ate'
    agora que entrega log. Ver docs/03-armadilhas.md.
    """
    if not lut:
        return ""
    if not os.path.exists(lut):
        raise SystemExit(f"LUT nao encontrado: {lut}")
    # O ffmpeg le' o filtro como texto: em Windows a barra invertida e' fuga
    # e os dois pontos separam opcao. Sem escapar, `C:\...` vira lixo.
    caminho = lut.replace("\\", "/").replace(":", "\\:")
    return ("scale=in_range=full:out_range=full,format=gbrp16le,"
            f"lut3d=file='{caminho}',format=yuv420p,")


def centrar_de(src, limiar=12.0):
    """Cadeia que centra a fala quando o microfone gravou num canal so'.

    Camera profissional grava o lapela no canal 1 e deixa o 2 com o microfone
    interno da camera, 30 dB abaixo. Repassar o estereo como veio prende a voz
    num lado do fone. Medido no lote da Dra. Fulana (10/08/2026), nos
    13 brutos, sem exceção:

        canal 1 (esq)  -27,3 a -32,2 dB
        canal 2 (dir)  -59,6 a -64,9 dB
        diferenca      +32,1 a +32,6 dB

    Os dez videos foram entregues assim, e NENHUMA medida do lote pegou: o
    `volumedetect`, o `astats` agregado e as quatro colunas do
    `lote_verificar` SOMAM os canais, entao sinal so' no esquerdo mede igual
    a sinal centrado 3 dB mais baixo. Quem ouviu foi o operador, no fone:
    "o audio da voz dela ta saindo so de um lado, do lado esquerdo".

    Usa o canal bom nos dois lados em vez de somar os dois: somar traria o
    microfone interno junto, e com ele o ruido de sala que o canal bom nao
    tem.

    Devolve string vazia quando o material ja e' mono ou esta equilibrado --
    a deteccao e' por ARQUIVO, como `tonemap_de` e `nivel_silencio_de`.
    """
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0",
                        "-show_entries", "stream=channels",
                        "-of", "default=nw=1:nk=1", src],
                       capture_output=True, text=True)
    try:
        if int((r.stdout or "0").strip()) < 2:
            return ""                      # ja e' mono
    except ValueError:
        return ""

    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", src, "-vn", "-af",
                        "astats=metadata=1:reset=0", "-f", "null", "-"],
                       capture_output=True, text=True, errors="replace")
    niveis, canal = {}, None
    for l in (r.stderr or "").splitlines():
        m = re.search(r"Channel:\s*(\d+)", l)
        if m:
            canal = int(m.group(1))
        if "Overall" in l:
            canal = None
        m = re.search(r"RMS level dB:\s*(-?[\d.]+)", l)
        if m and canal is not None and canal not in niveis:
            niveis[canal] = float(m.group(1))
    if len(niveis) < 2:
        return ""
    esq, dir_ = niveis.get(1), niveis.get(2)
    if esq is None or dir_ is None:
        return ""
    if esq - dir_ > limiar:
        return "pan=stereo|c0=c0|c1=c0,"
    if dir_ - esq > limiar:
        return "pan=stereo|c0=c1|c1=c1,"
    return ""


def nivel_silencio_de(src, folga=8.0):
    """Limiar de silencio (dB) derivado do RMS do proprio material.

    Um limiar fixo nao sobrevive a materiais de nivel diferente. Com -30 dB
    num bruto de RMS -34,3 dB (v1 do Dr. Fulano), o limiar fica ACIMA da fala
    media: silaba dita baixo vira "silencio" e o corte a remove. O sintoma
    foi 'in Pinheiros' virar 'nheiros' — o detector marcou 0,64s de fala como
    pausa. Os tres brutos daquele lote medem -34,3, -35,1 e -30,9 dB: nenhum
    valor unico serve nos tres.

    A folga de 8 dB e' o que reproduziu, no v1, o -42 dB validado a mao.
    """
    import subprocess

    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", src, "-vn", "-af",
                        "astats=metadata=1:reset=0", "-f", "null", "-"],
                       capture_output=True, text=True)
    achados = re.findall(r"RMS level dB:\s*(-?[\d.]+)", r.stderr)
    if not achados:
        return -30.0                      # o valor de sempre, se nao medir
    return round(float(achados[-1]) - folga)


CORTES_MIN_POR_MIN = 4.0


def palavras_do_fw(caminho):
    """Intervalos de palavra de um `_fw.json`, ou [] se nao houver."""
    import json
    import os

    if not caminho or not os.path.exists(caminho):
        return []
    try:
        d = json.load(open(caminho, encoding="utf-8"))
    except Exception:
        return []
    return [(w["ini"], w["fim"])
            for s in d.get("segmentos", []) for w in s.get("palavras", [])]


ENERGIA_FRACAO = 0.25
ENERGIA_PAUSA_MIN = 0.35

# Piso de vao para o corte POR ENERGIA — o `MIN_GAP` do caminho por
# `silencedetect` continua 0,12 s e nao e' tocado.
#
# Por que os dois nao podem ser o mesmo numero: o detector por energia enxerga
# pausa que o `silencedetect` nao ve, entao a distribuicao de vaos e' outra —
# mais numerosa e mais curta. No v2 da Dra. Fulana (12/08/2026) os seis
# vaos mediam 0,267 · 0,867 · 0,233 · 0,200 · 0,233 · 0,167 s, e o operador
# apontou exatamente o de 0,167: *"la pros secs 42-43 tem um corte todo
# estranho"*. Com 0,12 todos passavam; com 0,25 sobravam so' dois cortes em
# 49 s (sem ritmo nenhum). 0,18 mata o que ele viu e preserva os outros cinco.
#
# 0,18 e' o proprio `PAD`, e a regra le' bem assim: **o silencio que sobra
# depois do corte tem de valer pelo menos o que o PAD comeu**.
#
# Medido antes de aplicar, nos dois sentidos: no lote da Dra. Fulana (ja
# publicado) o fallback de energia NAO dispara, entao nada muda la — o que
# importa porque regua nova nao pode alterar peca aprovada num re-render.
MIN_GAP_ENERGIA = 0.18


def fala_por_energia(src, dur, janela=0.02, fracao=ENERGIA_FRACAO,
                     minp=ENERGIA_PAUSA_MIN, palavras=(), folga=0.10):
    """Blocos de FALA medidos por energia de janela, nao por pico instantaneo.

    Existe porque o `silencedetect` mede AMPLITUDE INSTANTANEA: um estalo de
    ruido dentro da pausa ja basta para ele nao ver pausa nenhuma. O sintoma
    conhecido era vao de 1,6 s passando batido no meio do video (lote 11); no
    lote da Dra. Fulana (12/08/2026) ele foi ao extremo — consultorio com
    ar-condicionado ligado, `silencedetect` devolveu ZERO silencios a -40 dB e
    tres videos sairam com UM trecho, ou seja, sem corte nenhum. Sem corte nao
    ha degrau de zoom, e o Reels sai parado.

    Subir o limiar nao resolve: o teto seguro e' `RMS - 6 dB` (acima disso
    silaba dita baixo vira pausa e o corte come palavra — 'in Pinheiros' virou
    'nheiros'), e a -38/-40 dB o detector ja nao via nada.

    A energia media de 20 ms atravessa o ruido: nos 5 brutos daquele lote deu
    17 a 20 cortes/min NA LISTA DE TRECHOS, contra os 29 do video 7 aprovado
    na mesma unidade. (Unidade colada de proposito: 29 e' lista de trechos,
    nao detector de cena. Ver o dossie.)

    O limiar e' RELATIVO ao proprio material — piso (p10) + `fracao` da faixa
    ate o teto (p95).

    DUAS travas que nasceram de erro medido, na primeira versao desta funcao
    (12/08/2026, mesmo lote):

    1. `fracao` era 0,40, herdada do `repeticao.py`. La ela serve para APONTAR
       fala; aqui ela decide o que APAGAR, e as duas coisas nao pedem o mesmo
       rigor. A 0,40 o limiar subia acima de silaba fraca e o corte comeu fala:
       'fertilizacao in vitro' virou 'fertilizante', 'todo o sistema' virou
       'todos os temas', e no v5 sumiram 'voce se sente' e o CTA 'procurar um
       especialista'. Confirmado transcrevendo o AUDIO DO CORTE com o modelo
       bom — nao era erro de transcricao, era fala removida.
    2. `minp` era herdado do `pausa_minima` do lote (0,12 s) — e ERA ELE o
       culpado, nao a fracao. Com 0,12 s qualquer respiracao no meio da frase
       virava candidata a corte. Com `ENERGIA_PAUSA_MIN` (0,35 s) a fala fica
       intacta em TODAS as fracoes testadas (0,08 a 0,25): a transcricao do
       audio do corte bate palavra a palavra com a do bruto. Por isso a fracao
       ficou na mais alta medida, 0,25, que e' a que mais corta sem perder
       nada. Os numeros da varredura estao em `docs/03-armadilhas.md`.

    `palavras` (de um `_fw.json`) veta pausa que encoste em palavra
    transcrita. NAO serve para este material e o motivo vale registrar: os
    timestamps do whisper ja ENGLOBAM as pausas (o `possibilidades` do v4
    ocupa 2,34 s incluindo 0,9 s de silencio), entao o veto elimina toda pausa
    e o corte volta a zero. Fronteira de palavra nao vem do whisper — a
    protecao real e' `minp` mais a conferencia por transcricao.
    """
    import array
    import math
    import subprocess

    sr = 8000
    r = subprocess.run(["ffmpeg", "-hide_banner", "-v", "error", "-i", src,
                        "-vn", "-ac", "1", "-ar", str(sr), "-f", "s16le", "-"],
                       capture_output=True)
    d = array.array("h")
    d.frombytes(r.stdout[: len(r.stdout) // 2 * 2])
    n = int(sr * janela)
    if n <= 0 or len(d) < n:
        return None
    env = []
    for i in range(0, len(d) - n, n):
        s = 0
        for x in d[i:i + n]:
            s += x * x
        rms = math.sqrt(s / n) / 32768.0
        env.append(20 * math.log10(rms) if rms > 1e-9 else -120.0)
    if not env:
        return None
    # O PCM acima comeca na 1a amostra de AUDIO; o `silencedetect` e as
    # `faixas` estao no relogio do CONTAINER. Celular entrega audio com
    # `start_time` de ate 0,74 s (lote 78, 06/10/2026: simulado no v4 com
    # -42 dB, os cortes desta rota sairam ~0,74 s ADIANTADOS). Soma-se o
    # deslocamento para os dois detectores falarem o mesmo relogio.
    desl = 0.0
    sp = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0",
                         "-show_entries", "stream=start_time", "-of",
                         "csv=p=0", src], capture_output=True, text=True)
    try:
        desl = max(0.0, float(sp.stdout.strip()))
    except ValueError:
        pass
    o = sorted(env)
    piso, teto = o[int(len(o) * 0.10)], o[int(len(o) * 0.95)]
    if teto - piso < 6.0:                  # material sem contraste: nao opinar
        return None
    limiar = piso + (teto - piso) * fracao

    # pausas = trechos abaixo do limiar com duracao suficiente
    pausas, ini = [], None
    fim_env = min(dur, desl + len(env) * janela)
    for i, x in enumerate(env):
        t = desl + i * janela
        if x < limiar:
            if ini is None:
                ini = t
        elif ini is not None:
            if t - ini >= minp:
                pausas.append((ini, t))
            ini = None
    if ini is not None and fim_env - ini >= minp:
        pausas.append((ini, fim_env))

    # veto: pausa que encosta em palavra transcrita nao e' pausa
    if palavras:
        pausas = [(a, b) for a, b in pausas
                  if not any(pi - folga < b and pf + folga > a
                             for pi, pf in palavras)]
    if not pausas:
        return None

    fala, cur = [], desl          # antes do 1o audio nao ha fala a medir
    for a, b in pausas:
        if a > cur:
            fala.append((cur, a))
        cur = b
    if cur < fim_env:
        fala.append((cur, fim_env))
    return fala or None


def fala_ou_energia(src, dur, fala, faixas, minp=0.12, montar=None,
                    fw=None, minp_energia=None):
    """`fala` do `silencedetect`, trocada pela medida por ENERGIA se aquela
    tiver achado corte de menos.

    Fallback de proposito, e nao troca de detector: lote que hoje sai bem
    continua saindo identico, porque so' entra aqui quem ficou abaixo de
    CORTES_MIN_POR_MIN. Decisao do operador em 12/08/2026, contra trocar a
    regua para todo mundo — havia outros lotes rodando na mesma maquina, e
    mudanca de regua global vale para todos eles na hora.

    `montar` e' a funcao que transforma blocos de fala em TRECHOS (PAD, grade,
    MIN_GAP, MIN_TRECHO). Ela e' obrigatoria na pratica porque a decisao tem
    de olhar o numero EFETIVO: na primeira versao eu contei os blocos que o
    `silencedetect` devolve, ANTES da fusao do PAD, e o v3 da Fulano — que
    termina com DOIS trechos em 50 s — nao disparou o fallback, porque na
    contagem crua ele tinha 18 blocos. E' a mesma regra que fez o `MIN_GAP`
    existir: exceção se confere depois do PAD, nunca contra o numero escrito.
    """
    util = sum(max(0.0, fe - fs) for fs, fe in faixas) or dur
    if util <= 0:
        return fala, False
    if montar is None:                     # sem como medir o efetivo: nao opina
        return fala, False
    cortes = max(0, len(montar(fala)) - 1)
    if cortes / (util / 60.0) >= CORTES_MIN_POR_MIN:
        return fala, False
    # `minp` NAO herda o `pausa_minima` do lote: ele e' o que impede o corte
    # de entrar na fala, e o valor do lote (0,12 s) apagou o CTA de um video.
    # `pausa_energia` (dado de lote) so' pode SUBIR esse piso — quem quer menos
    # corte pede pausa mais longa; abaixar reabriria o buraco que come fala.
    medida = fala_por_energia(src, dur,
                              minp=max(ENERGIA_PAUSA_MIN, minp_energia or 0))
    if not medida:
        return fala, False
    return medida, True


def transcrever(entrada, destino, extra="", queue=90, idioma="pt"):
    """Transcreve `entrada` com o filtro whisper do ffmpeg, gravando `destino`.

    ARMADILHA que esta função existe para resolver: o parser de filtro do
    ffmpeg usa `:` como separador de opção, e **não há escape que funcione**
    para o caminho do modelo. Testado em 31/07/2026, os três falham:

        model=D\\:/Modelos/...      -> "Error parsing a filter description"
        model='D:/Modelos/...'      -> "Error parsing a filter description"
        model=/Modelos/...          -> só funciona se o cwd estiver no D:

    A forma sem letra de drive é resolvida pelo Windows **contra o drive
    atual**. Então a saída daqui é: rodar com o `cwd` no drive do modelo,
    passar o modelo sem drive e o destino como **nome puro** (sem barra
    nenhuma), e mover o arquivo depois. A entrada pode ser caminho absoluto
    com drive — `-i` é argumento de linha de comando, não passa pelo parser
    de filtro.

    Sem isso, lote gravado em C: e modelo em D: é impossível: não existe
    caminho relativo entre drives no Windows.
    """
    import shutil
    import subprocess

    modelo = exigir_caminho("modelo_whisper", "modelo ggml do filtro whisper")
    drive = os.path.splitdrive(modelo)[0]
    sem_drive = modelo[len(drive):].replace("\\", "/")
    tmp = os.path.join(drive + os.sep, "_transcricao_claude")
    os.makedirs(tmp, exist_ok=True)
    nome = os.path.basename(destino)
    fmt = "json" if nome.lower().endswith(".json") else "srt"
    af = (f"whisper=model={sem_drive}:language={idioma}:queue={queue}{extra}"
          f":destination={nome}:format={fmt}")
    r = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i",
         os.path.abspath(entrada), "-vn", "-af", af, "-f", "null", "-"],
        capture_output=True, text=True, cwd=tmp)
    saiu = os.path.join(tmp, nome)
    if r.returncode == 0 and os.path.exists(saiu):
        os.makedirs(os.path.dirname(os.path.abspath(destino)), exist_ok=True)
        shutil.move(saiu, destino)
        if fmt == "json":
            consertar_aspas_do_json(destino)
        return True, ""
    return False, (r.stderr or "").strip()[:300]


def consertar_aspas_do_json(caminho):
    """Escapa as aspas que o filtro whisper do ffmpeg emite sem escapar.

    ARMADILHA (Dra. Fulana, 31/07/2026): quando a fala tem discurso
    citado, o whisper devolve a propria ASPA como token — e escreve o campo
    de texto como uma aspa solta, sem escape (o valor sai literalmente como
    tres aspas seguidas antes do fecha-chaves). Isso nao e' JSON valido, e
    quem le com json.loads morre com "Expecting ',' delimiter".

    O estrago nao aparece na transcricao: aparece TRES fases depois, no
    render, e derruba o video no meio do lote (o v7 morreu e o v8 nem
    chegou a rodar). No lote da Fulano aconteceu so' no v7, o unico em que
    ela cita a paciente falando.

    Conserta no lugar e devolve quantas linhas arrumou. E' idempotente:
    linha que ja' e' JSON valido nao e' tocada.
    """
    import json

    linhas, arrumadas = [], 0
    padrao = re.compile(r'^\s*\{"start":(-?\d+),"end":(-?\d+),"text":"(.*)"\}\s*$')
    with open(caminho, encoding="utf-8") as f:
        for l in f:
            if not l.strip():
                continue
            try:
                json.loads(l)
                linhas.append(l.rstrip("\n"))
                continue
            except ValueError:
                pass
            m = padrao.match(l)
            if not m:
                linhas.append(l.rstrip("\n"))   # nao sei consertar: preserva
                continue
            linhas.append(json.dumps(
                {"start": int(m.group(1)), "end": int(m.group(2)),
                 "text": m.group(3)}, ensure_ascii=False))
            arrumadas += 1
    if arrumadas:
        with open(caminho, "w", encoding="utf-8") as f:
            f.write("\n".join(linhas) + "\n")
    return arrumadas


class Lote:
    """Um lote: onde estão os arquivos e o que decidimos para cada vídeo."""

    def __init__(self, pasta, dados):
        self.pasta = pasta
        self._dados = dados
        self.nome = os.path.basename(pasta)
        self.cliente = dados.get("cliente", "")
        self.entrega = dados.get("entrega", "")
        # idioma da fala, por vídeo: {"1": "en", "3": "pt"}. Falta = `idioma`
        # do lote, e na falta dele, "pt". Existe porque um mesmo cliente pode
        # gravar em dois idiomas no mesmo lote (Dr. Fulano, jul/2026).
        self.idioma = dados.get("idioma", "pt")
        self.idiomas = dados.get("idiomas", {})
        # decisões editoriais, por vídeo (chave = número do vídeo, string)
        self.faixas = {k: [tuple(p) for p in v]
                       for k, v in dados.get("faixas", {}).items()}
        self.correcoes = dados.get("correcoes", {})
        # ESTILO da legenda por lote (cor, fonte, corpo). Cor e fonte sao do
        # CLIENTE, nao do padrao: a Dra. Fulana pediu #F8E2C2 e Red Hat
        # Display Bold (14/08/2026) e o resto do acervo segue em Anton com
        # realce amarelo. Vazio = o padrao de sempre, nada muda.
        # Consumido por gerar_ass.py (argv[7]) E por texto_grande.py (argv[5]) —
        # os dois, porque a frase em destaque ja' ficou de fora de conserto de
        # legenda duas vezes neste projeto.
        self.estilo = {k: v for k, v in (dados.get("estilo") or {}).items()
                       if not k.startswith("_")}
        # ABERTURA: vinheta de marca inserida DEPOIS da primeira frase, com o
        # video seguindo da segunda. Nasceu no lote da Dra. Fulana
        # (14/08/2026), cuja serie "Fulano" ja tem essa vinheta nas pecas
        # publicadas. Nao e' recorte nem copia -- a vinheta entra no meio da
        # peca e nada se repete.
        self.vinheta = {k: v for k, v in (dados.get("vinheta") or {}).items()
                        if not k.startswith("_")}
        # Instante, POR VIDEO, em que a vinheta entra: o fim da 1a frase
        # MEDIDO NA ENERGIA, nunca o relogio do whisper. Onde a frase fecha em
        # interrogacao o whisper encerra a ultima palavra ~350 ms cedo demais
        # (medido nos videos 1 e 4 deste lote) e cortar por ele decapita a
        # silaba final.
        self.vinheta_em = dados.get("vinheta_em", {})
        # NOME de entrega por video: {"1": "Formacao e Foco ... - Dr. Fulano"}.
        # O nome do arquivo entregue e' O QUE ELE FALA no video, nunca
        # "Video N" (decisao de 11/08/2026). Isto viveu so' no CLAUDE.md e no
        # vault ate 21/08/2026, e o custo foi medido: o `--publicar` e o
        # `exportar_legendas.py` continuavam gravando "Video N", entao o lote
        # 15 saiu com "Video 1.mp4" DEPOIS da decisao. Regra que so' existe em
        # texto depende de alguem lembrar; aqui ela e' dado do lote.
        # Vazio = cai no "Video N" de antes, que ainda serve a lote cujo bruto
        # ja' vem nomeado e numerado pelo cliente.
        self.nomes = dados.get("nomes", {})
        self.sem_pb = set(dados.get("sem_pb", []))
        # Videos que saem SEM frase em destaque, mesmo havendo candidata.
        # Nasceu em 12/08/2026: o operador proibiu a frase de ABRIR ou FECHAR
        # o video (*"n pode ter essa animacao de texto e zoom no comeco"*,
        # *"a animacao de texto literalmente no final nao me agrada"*), e sem
        # esta chave a escolha automatica repoe o texto exatamente ali — que
        # e' onde sobra janela quando o corte e' denso.
        self.sem_texto = set(dados.get("sem_texto", []))
        self.texto_recorte = dados.get("texto_recorte", {})
        # Liga a MESMA validacao de folga da escolha automatica no override
        # `texto_recorte` (folga minima ate o corte, e corte DENTRO da janela
        # reprova). Opcao criada em 02/10/2026 por decisao do operador.
        # Padrao False: lote antigo (as 3 pecas congeladas da Dra. Fulana)
        # re-renderiza igual ao publicado. Lote novo deve ligar.
        self.validar_folga_override = bool(dados.get("validar_folga_override", False))
        # Ganho da musica em dB sobre o arquivo original, por video, quando o
        # padrao (`MUSICA_GANHO_DB`, hoje -27) nao serve. Dado de lote, nunca
        # regua: o -27 continua valendo para todo mundo. Ver o `_porque` no
        # lote.json de quem usar.
        self.musica_db = dados.get("musica_db", {})
        # Faixa de musica por video, quando a escolha automatica (round-robin
        # pela ordem de `faixas`) nao serve -- ex.: a faixa sorteada e' mais
        # curta que a peca e o render aborta (lote 38, Fulano, v3: faltavam
        # 74 ms). Nome do arquivo dentro da pasta `musicas`: {"3": "x.mp3"}.
        self.musica = dados.get("musica", {})
        # faixa vertical (fracao da altura) da legenda que o proprio cliente
        # queimou no bruto, por video: {"1": [0.706, 0.790]}. Vazio = bruto
        # limpo, e nenhuma tarja de cobertura e desenhada.
        self.legenda_do_cliente = dados.get("legenda_do_cliente", {})
        # Pausa minima que conta como corte, em segundos. 0,12 serve para
        # bruto CRU. Bruto que ja vem editado (Dr. Fulano, jul/2026) nao tem
        # silencio longo, so respiracao: com 0,12 o corte sai fatiado em 22
        # blocos de ~1s e, como o degrau de zoom acontece em todo corte, a
        # densidade de corte vira densidade de zoom — 64 eventos/min contra
        # os 29 do video 7 aprovado. E o retorno da armadilha I10.
        #
        # UNIDADE: estes numeros sao da LISTA DE TRECHOS, e so' se comparam
        # com outros da lista de trechos. O mesmo video 7 medido por detector
        # de cena da 16,0/min -- o detector nao ve corte em que so' o zoom
        # muda. Comparar as duas unidades ja custou um diagnostico errado
        # (lote da Dra. Fulana, 11/08/2026).
        # escalar (vale para todos) ou dict por vídeo: {"1": 0.35, "2": 0.25}
        self.pausa_minima = dados.get("pausa_minima", 0.12)
        self.pausa_energia = dados.get("pausa_energia")
        # Limiar em dB abaixo do qual o audio conta como silencio. -30 e' o
        # valor de sempre, e serve quando a fala esta em nivel normal. Confira
        # contra o RMS do bruto: no v1 do Dr. Fulano o RMS e' -34,3 dB, ou
        # seja, o limiar estava ACIMA da fala media — e o "in Pi" de "in
        # Pinheiros", dito baixo, foi cortado fora como se fosse pausa. Regra
        # pratica: nao usar limiar acima de RMS - 6 dB.
        # None (ou ausente) = derivar do RMS de cada bruto, que e' o certo
        # quando os videos tem niveis diferentes. Numero = forcar o valor
        # para todos. Dict por video ({"4": -28}) = forcar so' onde precisa,
        # caindo no automatico no resto — igual a `pausa_minima`.
        #
        # O automatico tem um ponto cego, e ele apareceu nos v4 e v5 da Dra.
        # Fulano (31/07/2026): RMS - 8 dB pode cair ABAIXO do ruido de
        # sala. Quando isso acontece o silencedetect nao acha pausa nenhuma,
        # o corte sai com **1 trecho** e o video fica sem corte — ou seja,
        # sem degrau de zoom, um plano estatico do comeco ao fim. O sintoma
        # no log da fase 1 e' "1 trechos". E' o espelho da armadilha do Dr.
        # Fulano: la o limiar ficou ACIMA da fala e comia silaba; aqui ficou
        # ABAIXO do chiado e nao acha nada.
        self.nivel_silencio = dados.get("nivel_silencio")
        # Correcoes de SEQUENCIA de tokens, por video. `correcoes` troca uma
        # palavra por outra e nao alcanca o caso em que o whisper estilhaca a
        # fala: "in Pinheiros" saiu como [",", "P", "MS"] no v1 do Dr. Fulano.
        # Formato: {"1": [{"de": [",","P","MS"], "para": ["in","Pinheiros"]}]}
        # Continua valendo o limite de sempre: isto e' para RESTAURAR o que a
        # pessoa falou, confirmado por outra fonte — nunca para reescrever.
        # Cadeia de filtro de audio aplicada SO' na fala, por video, ANTES do
        # loudnorm. E' dado de lote, nao regua: no lote da Dra. Fulana
        # so' 2 dos 8 tem ruido de maquina, e aplicar os notches nos outros 6
        # tiraria voz sem tirar ruido. Formato: {"4": "highpass=f=150,..."}.
        self.denoise = dados.get("denoise", {})
        # Janela de P&B forcada por video: {"7": [6.22, 9.10]}. Sobrepoe a
        # escolha automatica, inclusive a faixa de 1,6-2,5s -- que e'
        # convencao do operador, e so' ele relaxa.
        self.pb = dados.get("pb", {})
        # Trim de saida da fala, em dB, por video, aplicado DEPOIS do
        # loudnorm: {"4": -1.0}. Serve para dar folga de pico quando o
        # limitador passa a trabalhar o tempo todo e o encoder AAC estoura
        # o teto na saida. Nao e' controle de volume geral -- o nivel do
        # lote continua vindo do loudnorm.
        self.ganho_fala_db = dados.get("ganho_fala_db", {})
        # B-roll por video: lista de {arquivo, de, dur, em}. `arquivo` e' o
        # nome dentro de assets/broll/<cliente>/ ou caminho absoluto; `de` e
        # `dur` recortam o clipe; `em` e' o instante do CORTE onde ele entra.
        # A fala continua rodando por baixo -- b-roll aqui e' so' imagem.
        self.broll = dados.get("broll", {})
        self.correcoes_sequencia = dados.get("correcoes_sequencia", {})
        # Entregar tambem uma versao com a legenda que o proprio cliente
        # queimou no bruto, alem da com a nossa. Mesma edicao nas duas.
        # Pedido do chefe do operador (03/08/2026).
        self.duas_versoes = bool(dados.get("duas_versoes", False))
        # Deslocamento vertical da tarja de nome/CRM, em px de 1920, por
        # video. A arte tem a posicao embutida (o Dr. Fulano cai em
        # 0,731-0,825 da altura), e no v1 dele isso e' exatamente onde esta a
        # legenda — a tarja saiu por cima do texto, ilegivel. Negativo sobe.
        self.tarja_offset = dados.get("tarja_offset", {})
        # MAIS DE UMA TARJA por video: {"3": ["fulana", "beltrana"]}. Nasceu no
        # lote 48 (Clínica X, 16/09/2026): duas profissionais, e em 4 das
        # 12 pecas as duas aparecem. Decisao dele: "quando tem as duas, vc
        # coloca as duas tarjas, a que aparece primeiro vc coloca primeiro, e
        # dps a outra" -- SEQUENCIAIS, nunca ao mesmo tempo. Cada nome casa
        # com um arquivo `Tarja*<nome>*.mov` em assets/clientes/<cliente>/.
        # Video fora do dicionario cai na tarja unica de sempre (`self.tarja`).
        self.tarjas = dados.get("tarjas", {})
        # Instante, em tempo de BRUTO, em que cada tarja ENTRA: {"9": [null,
        # 9.633]}. null = automatico (a 1a sai num corte perto de 4,4 s como
        # sempre; a k-esima entra quando a anterior sai). Existe porque no v9
        # da Fulano o hook e' a Fulana e o teleprompter e' a Beltrana: a 2a
        # tarja tem de entrar na JUNCAO, senao cai o nome de uma sobre o rosto
        # da outra.
        self.tarjas_em = dados.get("tarjas_em", {})
        # Inicio de UMA palavra, por video, em segundos da timeline do CORTE:
        # {"10": [{"texto": "Ultraformer", "inicio": 15.43}]}. Corrige o caso
        # em que o whisper poe o inicio do token na 2a/3a silaba (v10 da
        # Fulano, 17/09/2026: "Ul-tra-" mudo para o modelo, token comecando
        # em "for-", legenda 0,53 s atrasada -- o operador viu). O retimer nao
        # alcanca porque ele so' move fronteira que cai em PAUSA detectada, e
        # aqui a pausa termina 0,5 s antes do token. Aplicado no `_palavras.json`
        # pelo lote_preparar, que e' a UNICA fonte de tempo de todos os
        # consumidores (legenda, texto grande, punch, .srt exportado) -- corrigir
        # so' na legenda deixaria o resto no tempo velho. `texto` casa sem caixa
        # e sem pontuacao; se casar mais de uma vez, `ocorrencia` (1 = primeira).
        self.inicio_palavra = dados.get("inicio_palavra", {})
        # Efeito sonoro ("whoosh") em instantes do CORTE, por video:
        # {"9": [5.2]}. O som e' o do proprio asset de light leak, que traz 4
        # whooshes curtos embutidos e sempre entrou MUDO no render. Nasceu no
        # v9 da Fulano (17/09/2026): a Beltrana entra depois do hook da
        # Fulana com gente falando ao fundo nos primeiros 400 ms, e ele pediu
        # "um efeito" para disfarcar. O pico do whoosh cai no instante dado.
        # Nivel em `sfx_db` (dB sobre o asset). SEM PADRAO desde 02/10/2026
        # (decisao do operador): cada lote informa o seu. Lote com `sfx_em`
        # e sem `sfx_db` aborta aqui -- antes caia em -6 calado. Valor de
        # partida sugerido: -6 (o antigo padrao); a Fulano usou +4.
        self.sfx_em = dados.get("sfx_em", {})
        if "sfx_db" in dados:
            self.sfx_db = float(dados["sfx_db"])
        elif any(self.sfx_em.values()):
            sys.exit("lote.json usa efeito sonoro (`sfx_em`) mas nao informa "
                     "`sfx_db` -- o nivel do whoosh e' dado de CADA lote, nao "
                     "ha padrao. Acrescente, por exemplo, \"sfx_db\": -6 "
                     "(valor de partida; a Fulano usou +4) e ouca o resultado.")
        else:
            self.sfx_db = None
        # Janela em que a MUSICA sobe, por video: {"9": [5.0, 5.9, 8]} =
        # +8 dB entre 5,0 e 5,9 s do corte, rampa de 0,15 s. Ver lote_produzir.
        self.musica_sobe = dados.get("musica_sobe", {})
        # Cortes em que o degrau de zoom fica no MINIMO (5 pt), por video,
        # em instantes de BRUTO: {"2": [31.467]}. Para corte que tem de
        # existir (emenda de tropeco) mas cai no meio da frase -- degrau
        # grande ali evidencia a emenda (v2 da Fulano, 18/09/2026).
        self.degrau_pequeno = dados.get("degrau_pequeno", {})
        # Y da legenda por video, em px de 1920 (padrao 1320). Serve
        # quando o enquadramento e' mais fechado e a legenda cai no
        # rosto -- caso do v3 da Dra. Fulana.
        self.legenda_y = dados.get("legenda_y", {})
        self.observacoes = dados.get("observacoes", {})

    def recorte_base_de(self, v):
        """Recorte FIXO do bruto antes de todo o resto (`recorte_base`).

        [w, h, x, y] em px do bruto, mesma proporcao 9:16 do bruto. Aceita
        uma lista (vale para todos) ou dicionario por video. Existe para
        tirar marca d'agua de app de captacao (Dr. Fulano, set/2026:
        `RECORDED ON BIGVU` em x 939-1060, y 1803-1900 de 1080x1920 —
        `[1014, 1803, 33, 0]` corta o rodape e ancora no topo, 6,5 % de
        zoom fixo). E' recorte de ENQUADRAMENTO, entra antes do zoom por
        corte e nao mexe em legenda, tarja nem transicao — tudo isso ja
        reescala para 1080x1920 sozinho. Vazio = nada.
        """
        r = self._dados.get("recorte_base")
        if isinstance(r, dict):
            r = r.get(str(v))
        if not r:
            return None
        w, h, x, y = (int(n) for n in r)
        if abs(w * 16 - h * 9) > 16:
            raise SystemExit(f"recorte_base v{v}: {w}x{h} nao e' 9:16 — "
                             f"deformaria o quadro. Use h = w*16/9.")
        return w, h, x, y

    def cauda_de(self, v):
        """Manter o final MUDO da ultima faixa (`cauda` no lote.json).

        Aceita `true` (vale para todos) ou dicionario por video.
        Motivo e medicao em `trechos_das_faixas`.
        """
        c = self._dados.get("cauda", False)
        if isinstance(c, dict):
            return bool(c.get(str(v), False))
        return bool(c)

    def card_antes_de(self, v, padrao):
        """Quanto (s) o card de finalizacao cobre o fim do conteudo, por video.

        `card_antes` no lote.json: {"5": 0.35}. Nasceu no V5 do lote 72
        (30/09/2026): ela se inclina e desvia o olhar para parar a gravacao
        ainda DENTRO da ultima palavra, e cortar a faixa comeria o CTA. O card
        entrando mais cedo esconde o gesto e a voz termina por baixo dele.
        """
        return float(self._dados.get("card_antes", {}).get(str(v), padrao))

    def cortes_vetados_de(self, v):
        """Instantes do BRUTO (s) onde o corte nao pode acontecer, por video.

        `{"2": [51.38]}` no lote.json. Casa com a FRONTEIRA do corte, com
        tolerancia de 0,25 s, e funde os dois trechos -- a pausa volta para a
        peca. Ver `trechos_das_faixas` para o porque.
        """
        return [float(t) for t in self._dados.get("cortes_vetados", {})
                .get(str(v), [])]

    def repeticoes_aceitas_de(self, v):
        """Suspeitas de TOMADA REFEITA que ja' foram ouvidas e liberadas.

        `{"3": [{"t": 31.47, "motivo": "enfase deliberada, 'do naaada'"}]}`
        no lote.json. Casa pelo instante de INICIO da suspeita, com tolerancia
        de 0,05 s.

        **Por que isto existe, e por que exige `motivo`:** ate' 13/08/2026 o
        detector de tomada refeita imprimia o alarme e saia com exit 0. A
        excecao era mental -- eu lia "0,94 s" e pensava "le como enfase" -- e
        nao deixava rastro nenhum. Falhou CINCO vezes seguidas, e na quinta
        quatro pecas com tomada repetida foram publicadas para a cliente.
        Duas dessas cinco o detector nem chegou a ser executado.

        A conta que o vault fez: `lembrar tem taxa de acerto zero sob pressao`.
        Entao a excecao passa a custar o mesmo que ela vale -- uma linha
        escrita, com o porque, que fica no lote e pode ser conferida depois.
        Excecao sem `motivo` NAO e' aceita: alarme silenciado sem justificativa
        e' o alarme ignorado de novo, so' que com aparencia de decisao.
        """
        aceitas = []
        for item in self._dados.get("repeticoes_aceitas", {}).get(str(v), []):
            if isinstance(item, dict):
                motivo = str(item.get("motivo", "")).strip()
                if not motivo:
                    raise SystemExit(
                        f"lote.json: repeticoes_aceitas[{v}] em "
                        f"t={item.get('t')} esta' sem `motivo`. Excecao sem "
                        f"porque nao e' excecao, e' alarme desligado.")
                aceitas.append((float(item["t"]), motivo))
            else:
                # Formato curto (so' o instante) recusado de proposito: era
                # por aqui que a excecao voltaria a nao ter rastro.
                raise SystemExit(
                    f"lote.json: repeticoes_aceitas[{v}] tem {item!r}. "
                    f"O formato e' {{\"t\": <segundos>, \"motivo\": \"...\"}}.")
        return aceitas

    @property
    def lut(self):
        """Caminho do `.cube` de cor do lote, ou "" quando nao ha.

        Relativo cai em `assets/clientes/<cliente>/`, que e' onde a tarja e a
        finalizacao ja moram — a cor e' arte do cliente como as outras duas.
        Absoluto passa direto, para apontar um LUT fora do projeto sem copiar.

        Vazio em quase todo lote: so' entra quando o medico grava em log.
        """
        return self._lut_caminho(self._dados.get("lut", ""))

    def _lut_caminho(self, p):
        if not p or isinstance(p, dict):
            return ""
        if os.path.isabs(p):
            return p
        return os.path.join(RAIZ, "assets", "clientes", self.cliente, p)

    def lut_de(self, v):
        """LUT do video `v`: `lut` pode ser string (lote inteiro) ou dict por
        video ({"1": "cor_1.cube", "*": "cor_geral.cube"}). Lote 38 do Dr. Fulano (set/2026): perfil flat mexido, com preto/branco em
        ponto diferente por video -- um stretch por video, nao um LUT so'."""
        p = self._dados.get("lut", "")
        if isinstance(p, dict):
            p = p.get(str(v), p.get("*", ""))
        return self._lut_caminho(p)

    # --- pastas do lote (criadas sob demanda)
    @property
    def brutos(self):
        """`brutos/` dentro do lote, ou o caminho absoluto que o lote.json der.

        O override existe porque bruto de 4K pesa ~230 MB por vídeo e nem
        sempre vale copiar para dentro do projeto. Preferir caminho explícito
        no lote.json a criar junction: junction é dependência invisível, e
        neste repositório já houve uma arrastando conteúdo para onde não devia.
        """
        p = self._dados.get("brutos", "brutos")
        return p if os.path.isabs(p) else os.path.join(self.pasta, p)

    @property
    def trabalho(self):
        return os.path.join(self.pasta, "trabalho")

    @property
    def saida(self):
        return os.path.join(self.pasta, "saida")

    @property
    def videos(self):
        """Números dos vídeos do lote, na ordem em que foram definidos."""
        return list(self.faixas)

    def bruto_de(self, v):
        """Caminho do bruto do vídeo `v`, seja qual for a extensão.

        Era `{v}.MOV` fixo em três lugares. iPhone entrega .MOV, mas export
        de edição vem .mp4 — o lote do Dr. Fulano (jul/2026) tem os dois na
        mesma pasta e quebrava antes de rodar.
        """
        for ext in ("MOV", "mov", "mp4", "MP4", "MTS", "m4v"):
            p = os.path.join(self.brutos, f"{v}.{ext}")
            if os.path.exists(p):
                return p
        return os.path.join(self.brutos, f"{v}.MOV")   # p/ mensagem de erro

    def idioma_de(self, v):
        """Idioma da fala do vídeo `v` (string), com queda para o do lote."""
        return self.idiomas.get(str(v), self.idioma)

    def rabo_de(self, v, padrao):
        """Quanto (s) a peca segue DEPOIS do fim do ultimo trecho de fala.

        O padrao (`TAIL_EXTRA` = 0,45 s no `lote_produzir`) deixa o video
        respirar no fim. Por video, `rabo_final` no lote.json (so' encurta ou
        alonga isso, nunca mexe no corte da fala). Nasceu no lote 78 (Dr. Fulano, 07/10/2026): a analista pediu cortar o fim do V1
        porque ele vira o rosto para o lado logo depois de "comigo" -- e
        encurtar a FAIXA nao resolvia, porque o rabo de 0,45 s era somado
        depois dela, trazendo o olhar de volta."""
        r = self._dados.get("rabo_final", {})
        try:
            return float(r[str(v)]) if str(v) in r else padrao
        except (TypeError, ValueError):
            return padrao

    def pausa_de(self, v):
        """Pausa mínima do vídeo `v`. Cada vídeo tem seu ritmo de fala, e é
        a densidade de corte que vira densidade de zoom — o mesmo valor nos
        três daria 27, 17 e 16 eventos/min contra os 29 do vídeo 7."""
        if isinstance(self.pausa_minima, dict):
            return self.pausa_minima.get(str(v), 0.12)
        return self.pausa_minima

    def pausa_energia_de(self, v):
        """Pausa minima do corte POR ENERGIA (fallback) do video `v`.

        Serve para BAIXAR densidade de corte em bruto que ja veio editado pelo
        cliente: pausa mais longa = menos corte. So' sobe o piso — ver
        `fala_ou_energia`. Ausente = `ENERGIA_PAUSA_MIN`.
        """
        d = getattr(self, "pausa_energia", None)
        if isinstance(d, dict):
            return d.get(str(v))
        return d

    def nivel_de(self, v):
        """Limiar de silêncio do vídeo `v`: o do lote, ou medido no bruto."""
        if isinstance(self.nivel_silencio, dict):
            forcado = self.nivel_silencio.get(str(v))
            if forcado is not None:
                return forcado
        elif self.nivel_silencio is not None:
            return self.nivel_silencio
        if not hasattr(self, "_niveis"):
            self._niveis = {}
        k = str(v)
        if k not in self._niveis:
            self._niveis[k] = nivel_silencio_de(self.bruto_de(v))
        return self._niveis[k]

    def preparar_pastas(self):
        for p in (self.brutos, self.trabalho, self.saida):
            os.makedirs(p, exist_ok=True)

    # --- arte do cliente, com alpha
    def _arte(self, prefixo):
        pasta = os.path.join(CLIENTES, self.cliente)
        if not os.path.isdir(pasta):
            return None
        for f in sorted(os.listdir(pasta)):
            if f.lower().startswith(prefixo) and f.lower().endswith(".mov"):
                return os.path.join(pasta, f)
        return None

    @property
    def tarja(self):
        return self._arte("tarja")

    def _arte_nomeada(self, prefixo, nome):
        """`Tarja*<nome>*.mov` do cliente, casando o nome sem caixa nem acento."""
        import unicodedata
        def chave(s):
            s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
            return s.lower()
        pasta = os.path.join(CLIENTES, self.cliente)
        if not os.path.isdir(pasta):
            return None
        for f in sorted(os.listdir(pasta)):
            fl = chave(f)
            if (fl.startswith(prefixo) and fl.endswith(".mov")
                    and chave(nome) in fl):
                return os.path.join(pasta, f)
        return None

    def tarjas_de(self, v):
        """Lista de arquivos de tarja do video `v`, na ordem em que entram.

        Sem `tarjas` no lote.json e' a tarja unica de sempre (lista de 0 ou 1).
        Com `tarjas`, um arquivo por nome; nome sem arquivo devolve None na
        posicao, e quem chama decide se aborta -- o `conferir()` ja' acusa.
        """
        nomes = self.tarjas.get(str(v))
        if not nomes:
            return [self.tarja] if self.tarja else []
        return [self._arte_nomeada("tarja", n) for n in nomes]

    def tarjas_em_de(self, v):
        """Entrada de cada tarja em tempo de BRUTO (None = automatico)."""
        lista = list(self.tarjas_em.get(str(v)) or [])
        n = len(self.tarjas.get(str(v)) or [])
        return (lista + [None] * n)[:max(n, len(lista))]

    @property
    def sem_finalizacao(self):
        """Lote que sai SEM o card de finalização, só com a tarja.

        Decisão dele em 25/08/2026, no lote 28 (Dra. Fulana): *"sobre a
        finalização, meio q todos vao parar, mas dps te explico melhor"*.
        Enquanto ele não explica o alcance, isto é DADO DE LOTE e não
        mudança de padrão -- o outro caminho seria tirar a exigência de
        todos os clientes achando que era geral, e aí o próximo lote de
        outro médico sai sem o card e ninguém percebe até abrir o vídeo.
        """
        return bool(self._dados.get("sem_finalizacao"))

    @property
    def sem_card(self):
        """Videos que saem SEM o card de finalizacao, com o lote tendo card.

        Padrao de 14/10/2026: card so' em video sem CTA falado, vale video a
        video. Lista de numeros (str). Primeiro uso: lote 87, Dr. Fulano.
        """
        return [str(x) for x in (self._dados.get("sem_card") or [])]

    @property
    def finalizacao(self):
        if self.sem_finalizacao:
            return None
        return self._arte("finaliza")

    def conferir(self):
        """Falta alguma coisa para este lote rodar? Devolve lista de problemas."""
        faltas = []
        if not self.cliente:
            faltas.append("`cliente` não definido no lote.json")
        if not os.path.isdir(self.brutos):
            faltas.append(f"pasta de brutos não existe: {self.brutos}")
        else:
            for v in self.videos:
                if not os.path.exists(self.bruto_de(v)):
                    faltas.append(f"bruto {v}.MOV não encontrado")
        if not self.tarja:
            faltas.append(f"tarja com alpha de '{self.cliente}' ausente em "
                          f"{os.path.join(CLIENTES, self.cliente)} "
                          f"(ProRes 4444, nome começando com 'Tarja')")
        # `tarjas` nomeadas: cada nome precisa do seu arquivo. O `self.tarja`
        # acima pega QUALQUER `Tarja*.mov`, entao um lote com dois nomes e um
        # arquivo so' passaria calado -- e a peca sairia com o nome errado.
        for v, nomes in self.tarjas.items():
            for n in nomes:
                if not self._arte_nomeada("tarja", n):
                    faltas.append(f"v{v}: tarja '{n}' sem arquivo em "
                                  f"{os.path.join(CLIENTES, self.cliente)} "
                                  f"(esperado 'Tarja*{n}*.mov')")
        if not self.finalizacao and not self.sem_finalizacao:
            faltas.append(f"card de finalização de '{self.cliente}' ausente "
                          f"(nome começando com 'Finaliza')")
        if not os.path.exists(MODELO_WHISPER):
            faltas.append(f"modelo do whisper ausente: {MODELO_WHISPER}")
        if not os.path.exists(LEAK):
            faltas.append(f"light leak ausente: {LEAK}")
        return faltas


def _nome_do_argv():
    """Lê --lote NOME de sys.argv e o REMOVE, para o script ver só os vídeos."""
    if "--lote" in sys.argv:
        i = sys.argv.index("--lote")
        nome = sys.argv[i + 1]
        del sys.argv[i:i + 2]
        return nome
    return None


_ULTIMO = None          # nome do último lote carregado nesta execução


def carregar(nome=None):
    """Resolve o lote. O `--lote` é consumido na PRIMEIRA chamada.

    Por isso existe `_ULTIMO`: um módulo importado pelo script principal que
    chame `carregar()` de novo — o `repeticao.portao()` da fase 1 faz isso —
    encontraria o argv já sem `--lote` e cairia no "Há mais de um lote". Foi
    o que aconteceu no lote 18 (Dr. Fulano, 14/08/2026): os 9 vídeos
    prepararam certo, o PORTÃO de tomada refeita morreu no plumbing e a fase
    saiu com exit 1. Portão que aborta por não achar o próprio lote é portão
    medindo o processo em vez do artefato — e, pior, um portão que nunca
    chega a rodar.
    """
    global _ULTIMO
    nome = nome or _nome_do_argv() or os.environ.get("LOTE") or _ULTIMO
    if not nome:
        existentes = [d for d in sorted(os.listdir(LOTES))
                      if os.path.exists(os.path.join(LOTES, d, "lote.json"))] \
            if os.path.isdir(LOTES) else []
        if len(existentes) == 1:
            nome = existentes[0]
        elif not existentes:
            sys.exit(f"Nenhum lote em {LOTES}. Copie "
                     f"'Lotes/MODELO-lote.json' para "
                     f"'Lotes/<AAAA-MM> - <Cliente>/lote.json'.")
        else:
            sys.exit("Há mais de um lote; diga qual com --lote:\n  " +
                     "\n  ".join(existentes))
    pasta = os.path.join(LOTES, nome)
    arq = os.path.join(pasta, "lote.json")
    if not os.path.exists(arq):
        sys.exit(f"Não achei {arq}")
    with open(arq, encoding="utf-8") as f:
        L = Lote(pasta, json.load(f))
    _ULTIMO = nome
    return L
