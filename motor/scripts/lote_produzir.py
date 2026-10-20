#!/usr/bin/env python3
"""Fase 2 do lote -- v4, reescrito sobre o modelo MEDIDO no video 7.

O modelo de zoom foi REESCRITO. O anterior era o inverso deste, ponto por
ponto: rampa continua com degrau pequeno na mesma direcao. O video 7, que
o operador aprovou ("ta perfeito, e o modelo ideal"), e PLATO PARADO com
DEGRAU GRANDE ALTERNADO. Medido nele:

 1. UM NIVEL POR CORTE. Nao existe "movimento" agrupando cortes.
 2. DENTRO DO BLOCO O ZOOM FICA PARADO -- deriva de 0,0 a 0,6 %/s em 10
    dos 11 blocos. A taxa media de deriva do video aprovado e 0,25 %/s,
    sete vezes menor que a que eu perseguia.
 3. DEGRAU NO CORTE de 6 a 14 pontos (mediana 10,5), contra os 2,8 que eu
    usava -- praticamente invisiveis.
 4. UMA rampa forte por video, no bloco do P&B.
 5. PUNCH de volta: 3 por video, +5 pontos em 2 quadros, segurando ate o
    corte. Eu o havia removido na 2a rodada, mas ele esta no aprovado.

Tres bugs corrigidos junto:
 - `fps` agora vem ANTES do `perspective`: `on` conta quadros de entrada,
   e num bruto de 59,94 fps a curva rodava em dobro e congelava na metade
   (v2, v3, v5);
 - o leak e ancorado pelo PICO (233 ms depois do inicio do clipe) no fim
   de frase, nao pelo inicio numa fronteira de zoom;
 - PAD de 0,10 para 0,18: 26% dos cortes comiam cauda de palavra.
"""
import json, os, re, subprocess, sys, unicodedata
from PIL import ImageFont

SCR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(SCR))
sys.path.insert(0, SCR)
import config                                            # noqa: E402
import relatorio                                         # noqa: E402

# O que cada video mediu nesta rodada, para o semaforo juntar depois. A fase
# ja' calculava tudo isto -- so' jogava na tela e esquecia.
MEDIDAS = []

# Tudo que é DADO do lote (onde estão os arquivos, faixas de corte,
# correções de legenda, quem fica sem P&B) vem do lote.json. Só o que é
# RÉGUA do padrão fica aqui embaixo, em constante.
LOTE = config.carregar()
FONTES = config.FONTES
# Caminhos de MÁQUINA: exigidos aqui, na fase que de fato os usa, e não no
# import do config — assim um lote de legendas roda numa máquina que nunca
# configurou leak nem música.
LEAK = config.exigir_caminho("leak", "clipe de light leak das transições")
LEAK_TRECHOS = [(1.16, 1.68), (2.88, 3.36), (4.56, 5.04), (6.24, 6.76)]
# o clarao do asset esta 233 ms depois do inicio do trecho (quadro 7)
LEAK_PICO = 0.233

MUSICAS = config.exigir_caminho("musicas", "pasta das músicas de fundo")
# GANHO sobre o arquivo original, nao alvo de nivel medio. E como ele faz
# no Premiere: "o padrao vem 0db pra tudo, ai eu coloco as musicas a
# -33db". Normalizar a media PARA -33 dBFS -- o que eu fiz na 1a versao --
# deixa 11 a 16 dB mais alto, e ele reclamou ("ainda estao bem altas").
# Efeito colateral aceito: como o ganho e relativo, faixas com masterizacao
# diferente terminam em niveis diferentes (medido: -43,7 a -49,4 dBFS).
MUSICA_FADER_DB = -33.0
# ...MAS o -33 dB dele so' reproduz o equilibrio do Premiere se a FALA
# tambem estiver no fader 0. Aqui ela passa por loudnorm=I=-14, que a
# levanta de +3,9 dB (v8) a +12,3 dB (v4) -- e a musica nao sobe junto.
# Medido no lote da Fulano: no Premiere dele a musica fica -19,4 dB abaixo
# da fala (mediana); no nosso render ficava -30,1 dB. Por isso ele ouviu
# como se nao houvesse musica ("so' falta mesmo a musica", 04/08/2026).
#
# A compensacao e UNIFORME, nao por video, de proposito: ele escolheu de
# ouvido entre tres amostras do v1 (+0, +6, +11 dB) e ficou com +6. Aplicar
# o boost real de cada video daria +12,3 no v4 e +3,9 no v8 -- dois niveis
# que ele nao ouviu. O espalhamento residual entre faixas ja era efeito
# colateral aceito do metodo dele (ver acima).
MUSICA_COMPENSA_LOUDNORM_DB = 6.0
MUSICA_GANHO_DB = MUSICA_FADER_DB + MUSICA_COMPENSA_LOUDNORM_DB

# PAD 0,18 (era 0,10): medido em 73 cortes, a cauda audivel da palavra
# decai em 33 ms na mediana e ate 142 ms. Com 50 ms de folga por lado,
# 26% dos cortes comiam fim de palavra. Com 90 ms, cai para 7%, ao custo
# de +688 ms por video (+3,4%). Nao subir mais: em 0,28 a respiracao volta.
PAD, FPS = 0.18, 30
# pausa minima que conta como corte: dado do lote, ver config.py
# pausa minima por video: dado do lote, ver config.py
# limiar de silencio: dado do lote, ver config.py
# limiar por video: forcado pelo lote.json ou medido no bruto
TAIL_EXTRA = 0.45
# `--sem-broll` refaz o video ignorando o b-roll do lote.json, gravando com
# sufixo. O operador pediu as duas versoes para comparar (03/08/2026): o
# b-roll e' elemento NOVO no padrao, nao esta medido no video 7 aprovado.
SEM_BROLL = "--sem-broll" in sys.argv
SUFIXO_SAIDA = "_SEM-BROLL" if SEM_BROLL else ""
PRE_W, PRE_H = 1404, 2496
# Cor da tarja que tapa a legenda queimada do cliente (ver `produzir`).
# Preta porque o cenario do Dr. Fulano e escuro e a camisa dele e branca:
# tarja branca brigaria com a camisa. E parametro, nao regra do padrao.
COR_TARJA = "black"
# folga de cada lado da faixa medida da legenda do cliente, para absorver
# erro de medicao. Pequena de proposito: e' altura de tarja na tela.
FOLGA_TARJA = 0.004

# Entradas do ffmpeg: 0=bruto, 1=leak, depois tarja, card e musica, cada uma
# so' se existir. Os indices eram fixos ([2:v] tarja, [3:v] card) e um lote
# sem arte do cliente casava o card no lugar da tarja sem reclamar.
#
# Desde 16/09/2026 (lote 48, Fulano) o numero de tarjas muda POR VIDEO
# (`tarjas` no lote.json), entao os indices deixaram de ser globais: sao
# calculados dentro de `produzir` (tarjas em 2..2+n-1, `idx_final`,
# `idx_musica`). Aqui fica so' o que e' fixo por lote.
TEM_FINAL = TEM_FINAL_LOTE = bool(LOTE.finalizacao)
TARJA_SAI, FINAL_OPACO = 4.40, 0.20


def _dur_card(caminho):
    """Duracao REAL do card. Era a constante 5,00 -- e a constante mentia.

    O `tpad` preenche `FINAL_DUR` de PRETO e o card e' sobreposto por cima;
    se o card durar menos que isso, o que sobra e' preto liso no fim da peca,
    com a musica tocando por baixo. Ninguem viu por anos porque a arte que os
    designers mandavam tinha 5 s.

    Medido em 27/08/2026, lote 29 (Dra. Fulana): o card dela tem
    2,87 s e as 16 pecas sairam com 2,10-2,13 s de preto no fim -- exatamente
    5,00 menos 2,87. Nenhum portao pegou: duracao, sync e nivel batem, porque
    o preto E' parte do arquivo e o audio sustenta a duracao.

    Cai para 5,00 se a sonda falhar, que e' o valor que sempre valeu.
    """
    # Por NOME, nunca por posicao: o ffprobe devolve `r_frame_rate` antes de
    # `nb_frames` mesmo quando se pede o contrario, e a primeira versao disto
    # lia '24/1' onde esperava o numero de quadros, caia no except e voltava
    # 5,00 -- em silencio, com exit 0 e a peca saindo com o mesmo preto no fim
    # que o patch existia para tirar.
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=nb_frames,r_frame_rate",
         "-show_entries", "format=duration", "-of", "json", caminho],
        capture_output=True, text=True)
    try:
        d = json.loads(r.stdout)
        v = d["streams"][0]
        # nb_frames / fps, nunca `format=duration`: o container mente, e ja'
        # mentiu duas vezes neste projeto (lotes 9 e 27).
        n = float(v["nb_frames"])
        num, den = v["r_frame_rate"].split("/")
        if n > 0 and float(den):
            return round(n / (float(num) / float(den)), 3)
        return float(d["format"]["duration"])
    except (KeyError, IndexError, ValueError, ZeroDivisionError,
            json.JSONDecodeError):
        return 5.00


FINAL_DUR = _dur_card(LOTE.finalizacao) if TEM_FINAL else 5.00
# Fade de fecho para lote SEM card de finalizacao (decisao dele,
# 26/08/2026). 0,60 s: abaixo de ~0,4 s le como corte e nao como
# fecho; acima de ~0,8 s come fala em peca curta -- o `Botox` deste
# lote tem 8,6 s inteiros.
FADE_FIM = 0.60

# --- zoom: valores MEDIDOS no video 7 (aprovado). Ver docs/01 §17.
# Sequencia de NIVEIS, nao de passos. Incrementar com direcao alternando
# colapsa num pingue-pongue de dois niveis assim que bate no piso de 100%
# (aconteceu no v3: 4 niveis so, entre 1,00 e 1,10). A sequencia abaixo
# reproduz a do video 7 -- 100/110/100/105/115/105/104/110/100/115 -- que
# alterna a maior parte do tempo mas tem dobras, e mantem a mediana de
# degrau em 10 pontos com extremos de 5 e 15.
NIVEIS = [1.00, 1.10, 1.00, 1.05, 1.15, 1.05, 1.10, 1.00, 1.15, 1.05,
          1.10, 1.00, 1.05, 1.15, 1.00, 1.10]
# Deriva DENTRO do bloco: quase nada. Tres dos oito valores sao zero, para
# reproduzir os platos totalmente parados de 1,7-2,2s do video 7.
DERIVAS = [0.000, 0.004, 0.000, -0.003, 0.006, 0.000, -0.003, 0.004]
RAMPA_PB = 0.09           # a UNICA rampa forte do video, no bloco do P&B
PUNCH = 0.05              # +5 pontos em 2 quadros, segurando ate o corte
ZMIN, ZMAX = 1.00, 1.20
# P&B: 1,6-2,5s. Ele autorizou 'partes longas', mas o material dele nao
# exerce isso: 1 dos 6 videos de referencia usa P&B, com 1,63s (3,4% da
# duracao), e o video 7 -- o unico que ele chamou de perfeito -- usa 1,80s
# (5,3%). O v1 com 5,93s (19,2%) foi reprovado pelo analista dele.
PB_MIN, PB_MAX = 1.6, 2.5
# Videos que saem SEM preto e branco (`sem_pb` no lote.json). Use quando ele
# ou o analista pedir. Sem P&B o video tambem fica sem a UNICA rampa forte de
# zoom, que mora nesse bloco -- fica so plato e degrau.
# `{str(x) ...}` como o SEM_TEXTO logo abaixo, e NAO `LOTE.sem_pb` cru: o `v`
# que chega aqui e' STRING (vem das chaves de `faixas` ou do argv), enquanto o
# lote.json escreve `"sem_pb": [1]` com INTEIRO. Ate' 26/08/2026 a comparacao
# era `"1" in {1}` -- sempre falsa, entao a chave era ignorada EM SILENCIO, sem
# erro e sem aviso: o log seguia imprimindo o P&B normalmente. Achado no lote 28
# (Dra. Fulana), quando desligar o P&B do v1 nao surtiu efeito nenhum.
SEM_PB = {str(x) for x in LOTE.sem_pb}
# Videos que saem sem frase em destaque, por decisao (`sem_texto`). Sem isto,
# a escolha automatica repoe o texto justamente onde sobra janela.
SEM_TEXTO = {str(x) for x in LOTE.sem_texto}

# Recorte manual da frase em destaque (`texto_recorte` no lote.json). A
# escolha automatica usa a frase INTEIRA; o recorte e override, para quando o
# texto e pedido num ponto em que a frase inteira nao cabe em 3 linhas.
#
# Ele afrouxou a regra do "frase inteira" em 31/07/2026: "vc pode pegar so uma
# parte do texto, tipo o final ... so tem que colocar no tempo certinho".
# O que continua valendo: trecho CONTIGUO, sem trocar nem reordenar palavra --
# e recorte, nunca parafrase. O tempo sai do `_palavras.json`, entao a
# animacao cai exatamente na fala.
#
# UM texto grande por video: cada um congela o zoom por FOLGA_TEXTO de cada
# lado, e dois proximos congelam um terco do video -- que e o "sem zoom do
# meio pro final" ja reprovado na 3a rodada.
TEXTO_RECORTE = LOTE.texto_recorte
TEXTO_CORPO, K, TEXTO_LARG = 200, 0.57, 950
MAX_LINHAS, MIN_DUR_TEXTO = 3, 20.0
FOLGA_TEXTO = 1.2         # zoom parado nessa folga antes/depois da frase
# Distancia MINIMA da frase ao corte mais proximo para a escolha automatica
# aceitar a frase (`folga_do_corte`). Ate 02/10/2026 era a mesma FOLGA_TEXTO
# (1,2 s); o operador mandou "afrouxar um pouco" depois de 3 lotes seguidos
# com ZERO destaque (Fulano 0/10, Fulano 0/9, Fulano 0/5). Separada do
# congelamento de proposito: o zoom continua parado 1,2 s em volta (regua
# medida), e um corte entre 0,8 e 1,2 s da frase cai dentro do raio de 0,6 s
# do `encaixar` em `curva` -- a borda do congelamento gruda NO corte e o
# degrau de zoom acontece ali, nao vira corte seco.
# MEDIDO em 02/10/2026 sem render (recalculo da escolha nos lotes fechados
# 2026-08 Fulano, 2026-08/09 Fulano, 2026-08/09 Fulano, 2026-09 Fulano):
# 1,2 / 1,0 / 0,9 / 0,85 / 0,8 dao o MESMO numero de destaques (0, 0, 0, 0,
# 1/12); so' 0,7 ganharia 1 (Fulano Pt2 v5, folga 0,77). O gargalo NAO e' a
# folga: quase todo candidato tem corte DENTRO da janela (folga -1).
FOLGA_ESCOLHA = 0.8

# Janelas do bruto que entram no corte (`faixas` no lote.json). E aqui que se
# remove tomada refeita, direcao de camera e voz de terceiro -- decisoes que
# saem de LER a transcricao, nunca do volume. A ORDEM das chaves define qual
# musica cada video recebe.
FAIXAS = LOTE.faixas

# Correcoes de legenda (`correcoes` no lote.json), aplicadas DEPOIS do
# alinhamento. Sintaxe completa no MODELO-lote.json. Duas que sempre voltam:
# valor com pontuacao troca o token inteiro (conserta interrogacao sem mudar
# palavra nenhuma), e o whisper varia a grafia do termo clinico a cada passada
# -- ja saiu "LPDMA" e "LPDEMA" para a mesma palavra.
CORR = LOTE.correcoes

# A quebra de linha da frase em destaque tem de ser medida na MESMA fonte que
# vai ser renderizada. Isto estava fixo em Anton e teria quebrado feio no lote
# do Dr. Fulano (21/08/2026): a Manier Heavy e' bem mais larga que a
# Anton no mesmo corpo, entao a frase que a Anton diz que cabe em 3 linhas
# estoura a tela na Manier -- e estouraria CALADO, porque nada no grafo
# reclama de texto largo demais.
#
# `K` (fator Pillow->tela) e' PROPRIO DE CADA FONTE, nao constante do projeto:
# medido 0,573 na Anton e 0,830 na Manier Heavy, 6 textos reais cada. Herdar o
# 0,57 daria 45% de erro na medida de largura, sempre para o lado de achar que
# cabe.
_est = LOTE.estilo or {}
if _est.get("corpo_destaque"):
    TEXTO_CORPO = int(_est["corpo_destaque"])
if _est.get("k_destaque"):
    K = float(_est["k_destaque"])
_ttf_d = _est.get("fonte_destaque_ttf") or _est.get("fonte_ttf")
fnt = ImageFont.truetype(
    os.path.join(FONTES, os.path.basename(_ttf_d)) if _ttf_d
    else os.path.join(FONTES, "Anton-Regular.ttf"), TEXTO_CORPO)


def sem_acento(txt):
    """Tira o diacritico, preservando a letra."""
    return "".join(c for c in unicodedata.normalize("NFD", txt)
                   if unicodedata.category(c) != "Mn")


def ass_para_queimar(v, arq):
    """Devolve o .ass que vai ser QUEIMADO no video.

    Normalmente e' o proprio arquivo. Com `sem_acento` no `estilo`, escreve um
    derivado sem diacritico e devolve ELE, deixando o original intacto.

    POR QUE UM DERIVADO, e nao desacentuar o original: o `.ass` e' a fonte da
    ENTREGA. O `exportar_legendas.py` tira dele o `.srt` e o `.txt` que o
    cliente le e posta, e o portao que compara a fala com o texto queimado
    tambem le ele. Desacentuar o original arrastaria a perda para dentro dos
    arquivos entregues, e ninguem pediu isso -- o operador aceitou perder o
    acento NA TELA, porque a Manier que chegou e' trial e nao tem glifo
    acentuado. Aqui a perda fica exatamente onde ela foi aceita: no pixel.
    """
    if not (LOTE.estilo or {}).get("sem_acento"):
        return arq
    dst = arq.replace(".ass", "_queimar.ass")
    saida = []
    for l in open(os.path.join(LOTE.trabalho, arq), encoding="utf-8"):
        if l.startswith("Dialogue:"):
            p = l.split(",", 9)
            if len(p) == 10:
                l = ",".join(p[:9] + [sem_acento(p[9])])
        saida.append(l)
    open(os.path.join(LOTE.trabalho, dst), "w",
         encoding="utf-8").writelines(saida)
    return dst


def rodar(a, **k):
    return subprocess.run(a, capture_output=True, text=True, **k)


def larg(t):
    return (fnt.getbbox(t)[2] - fnt.getbbox(t)[0]) * K


def quebrar(frase):
    ws = frase.split()
    for n in range(1, MAX_LINHAS + 1):
        linhas, atual = [], []
        alvo = len(" ".join(ws)) / n
        for w in ws:
            teste = atual + [w]
            if atual and (larg(" ".join(teste)) > TEXTO_LARG or
                          (len(" ".join(teste)) > alvo * 1.35 and len(linhas) < n - 1)):
                linhas.append(" ".join(atual)); atual = [w]
            else:
                atual = teste
        if atual:
            linhas.append(" ".join(atual))
        if len(linhas) <= n and all(larg(l) <= TEXTO_LARG for l in linhas):
            return linhas
    return None


def ass_so_do_texto(v, janela, linhas):
    """Escreve um .ass contendo APENAS a frase em destaque.

    Serve a versao que mantem a legenda do proprio cliente: ali a nossa
    legenda nao entra, mas a frase em destaque continua -- ela e' parte da
    EDICAO, nao da legenda, e o blur, o whip e o congelamento de zoom que a
    acompanham seguem no grafo. Sem isto, aquela janela viraria um borrao de
    1,8s sem texto nenhum.
    """
    corpo = "\\N".join(linhas)
    cab = ("[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\n"
           "WrapStyle: 2\nScaledBorderAndShadow: yes\n\n"
           "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, "
           "OutlineColour, BackColour, Bold, Italic, BorderStyle, Outline, "
           "Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
           f"Style: Grande,{_est.get('fonte_destaque') or _est.get('fonte') or 'Anton'},"
           f"{TEXTO_CORPO},&H00FFFFFF,&H00000000,&H80000000,"
           "0,0,1,0,6,5,60,60,60,1\n\n"
           "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, "
           "MarginR, MarginV, Effect, Text\n")

    def ts(s):
        h, s = divmod(max(0.0, s), 3600)
        m, s = divmod(s, 60)
        return f"{int(h)}:{int(m):02d}:{s:05.2f}"

    ev = (f"Dialogue: 0,{ts(janela[0])},{ts(janela[1])},Grande,,0,0,0,,"
          f"{{\\an5\\pos(540,960)}}{corpo}\n")
    caminho = os.path.join(LOTE.trabalho, f"{v}_texto.ass")
    open(caminho, "w", encoding="utf-8").write(cab + ev)
    return f"{v}_texto.ass"


def faixa_coberta(cobre, movs):
    """Faixa que a tarja tem de ocupar para cobrir a legenda do cliente.

    O zoom afasta tudo do CENTRO da tela: uma faixa abaixo do meio desce,
    uma faixa acima do meio sobe. A primeira versao so' considerava o caso
    "abaixo" -- somava o zoom na borda de baixo e deixava a de cima parada.
    Nos videos 2 e 3, cuja legenda queimada esta no TOPO, isso apontava a
    tarja para o lado errado e a legenda do cliente aparecia por cima dela,
    legivel. A verificacao numerica passou "OK" com o vazamento na tela.

    Por isso as duas bordas sao avaliadas nos dois extremos de zoom, e a
    faixa e' a uniao -- o que vale para faixa em cima, embaixo ou a cavalo
    do centro.
    """
    y0, y1 = cobre
    zmax = max(max(m[2], m[3]) for m in movs)
    cantos = [0.5 + (y - 0.5) * z for y in (y0, y1) for z in (1.0, zmax)]
    return min(cantos), max(cantos)


def aplicar_correcoes_sequencia(v):
    """Restaura no corte uma fala que o whisper estilhacou em varios tokens.

    `correcoes` so' troca palavra por palavra. Nao alcanca o caso em que a
    fala vira outro numero de tokens: no v1 do Dr. Fulano, "in Pinheiros"
    saiu como [",", "P", "MS"] no _palavras.json e "office, PMS." no
    _corte.srt. Sem isso, "PMS" ia queimado na tela.

    Reescreve os DOIS artefatos, porque o gerar_ass alinha um contra o
    outro. E idempotente: se a sequencia de origem nao existe mais, nao faz
    nada — entao reexecutar o lote nao aplica duas vezes.
    """
    regras = LOTE.correcoes_sequencia.get(str(v)) or []
    if not regras:
        return []
    tk_f = os.path.join(LOTE.trabalho, f"{v}_palavras.json")
    sr_f = os.path.join(LOTE.trabalho, f"{v}_corte.srt")
    toks = [json.loads(l) for l in open(tk_f, encoding="utf-8") if l.strip()]
    srt = open(sr_f, encoding="utf-8").read()
    feitas = []
    for r in regras:
        de, para = list(r["de"]), list(r["para"])
        # As duas substituicoes sao INDEPENDENTES e cada uma se verifica
        # sozinha. Emendadas, a do SRT falhava calada quando a juncao dos
        # tokens nao reproduzia o texto ("[',','P','MS']" vira ", P MS", mas
        # no SRT esta "office, PMS.") e o corte saia com os tempos corrigidos
        # e a palavra errada -- que e' o pior dos dois mundos.
        i = next((k for k in range(len(toks) - len(de) + 1)
                  if [t["text"] for t in toks[k:k + len(de)]] == de), None)
        if i is not None:
            # o intervalo dos tokens antigos e' repartido entre os novos, para
            # a legenda continuar caindo em cima da fala
            ini, fim = toks[i]["start"], toks[i + len(de) - 1]["end"]
            passo = (fim - ini) / max(len(para), 1)
            toks[i:i + len(de)] = [
                {"start": int(ini + passo * k), "end": int(ini + passo * (k + 1)),
                 "text": p} for k, p in enumerate(para)]
            feitas.append(f"tokens: {' '.join(de)} -> {' '.join(para)}")

        # O texto EXIBIDO sai do SRT de referencia, nao dos tokens: sem esta
        # metade a palavra errada continua indo para a tela.
        s_de = r.get("srt_de") or " ".join(de)
        s_para = r.get("srt_para") or " ".join(para)
        if s_de in srt:
            srt = srt.replace(s_de, s_para, 1)
            feitas.append(f"srt: {s_de!r} -> {s_para!r}")
        elif i is not None and s_para not in srt:
            # Meia aplicacao: tokens trocados, srt nao. A tela (tokens) sai
            # certa e o .txt (srt) sai errado -- calado. Caso real, lote 67
            # v4 (24/09/2026): `srt_de` "ajudar. vamos" atravessava a
            # fronteira de duas legendas do srt e nunca casou; o .txt saiu
            # com "vamos" minusculo. `srt_de` tem de caber numa legenda so'.
            print(f"      AVISO v{v}: correcao de sequencia {de} trocou os "
                  f"TOKENS mas {s_de!r} nao existe no srt (atravessa duas "
                  f"legendas?) -- o .txt vai sair sem o conserto")
        elif i is None and s_para not in srt:
            # so' avisa se o conserto NAO esta feito. As duas versoes do video
            # (nossa legenda / legenda do medico) compartilham os artefatos, e
            # a segunda passada sempre encontra a regra ja' aplicada.
            print(f"      AVISO v{v}: correcao de sequencia {de} nao casou "
                  f"nem nos tokens nem no srt -- confira o lote.json")
    if feitas:
        with open(tk_f, "w", encoding="utf-8") as f:
            for t in toks:
                f.write(json.dumps(t, ensure_ascii=False) + "\n")
        open(sr_f, "w", encoding="utf-8").write(srt)
    return feitas


def segmentos(src, faixas, nivel, minp, vetados=(), cauda=False,
              rabo=None):
    dur = float(rodar(["ffprobe", "-v", "error", "-show_entries",
                       "format=duration", "-of", "csv=p=0", src]).stdout.strip())
    err = rodar(["ffmpeg", "-hide_banner", "-i", src, "-vn", "-af",
                 f"silencedetect=noise={nivel}dB:d={minp}", "-f", "null", "-"]).stderr
    sil, ini = [], None
    for m in re.finditer(r"silence_(start|end): (-?[\d.]+)", err):
        if m.group(1) == "start":
            ini = float(m.group(2))
        elif ini is not None:
            sil.append((ini, float(m.group(2)))); ini = None
    if ini is not None:
        sil.append((ini, dur))
    fala, cur = [], 0.0
    for a, b in sil:
        if a > cur:
            fala.append((cur, a))
        cur = b
    if cur < dur:
        fala.append((cur, dur))
    # Ruido de fundo alto cega o `silencedetect` (ele mede PICO, nao energia):
    # se ele achou corte de menos, a fala vem medida por energia de janela.
    # Motivo completo em `config.fala_por_energia`. A MESMA chamada existe em
    # `lote_preparar.segmentos` — e e' por isso que ela esta aqui tambem.
    # (a chamada vem depois de `montar`, que e' o que mede o numero EFETIVO)
    # Fronteiras NA GRADE DE QUADROS do bruto -- a mesma conta da fase 1,
    # pela mesma funcao (`config.na_grade`). Esta copia de `segmentos()` e
    # quase identica a de `lote_preparar`, e foi a duplicacao que mordeu:
    # consertei so' la, e a guarda de timeline abortou o render dizendo que a
    # legenda era de outro corte. Ela estava certa -- as duas fases estavam
    # calculando cortes diferentes. Motivo da grade em `config.na_grade`.
    fps = config.fps_de(src)

    def montar(blocos, mingap=config.MIN_GAP):
        # Mesma funcao compartilhada da fase 1. As duas copias tem de calcular
        # o MESMO corte, ou a guarda de timeline aborta o render -- e ela ja
        # esteve certa duas vezes. Por isso a regra mora em `config`.
        # `vetados` vem por PARAMETRO, nunca de global: `segmentos` e' funcao
        # e o `v` do laco so' existe no modulo. Funcionaria por acidente aqui
        # e quebraria na primeira vez que alguem chamasse de outro lugar.
        return config.trechos_das_faixas(blocos, faixas, dur, fps, PAD,
                                         mingap, vetados=vetados, cauda=cauda)

    # Ruido de fundo alto cega o `silencedetect`: mesmo fallback da fase 1, com
    # a mesma funcao e o mesmo criterio EFETIVO. Motivo em `config`.
    fala, por_energia = config.fala_ou_energia(
        src, dur, fala, faixas, minp, montar=montar,
        fw=os.path.join(LOTE.trabalho,
                        os.path.splitext(os.path.basename(src))[0] + "_fw.json"),
        minp_energia=LOTE.pausa_energia_de(
            os.path.splitext(os.path.basename(src))[0]))
    # o corte por energia tem piso de vao proprio (motivo em config) — e a
    # fase 1 faz EXATAMENTE esta conta, senao a guarda de timeline aborta.
    segs = montar(fala, config.MIN_GAP_ENERGIA if por_energia else config.MIN_GAP)
    # A MESMA fusao de vao curto e a MESMA absorcao de trecho curto da fase 1,
    # pelas mesmas funcoes e NA MESMA ORDEM -- as duas copias de `segmentos()`
    # tem de calcular o mesmo corte, senao a guarda de timeline aborta o
    # render. Ela ja abortou duas vezes por isto, com um ano de distancia
    # nenhum: quando `na_grade` entrou (lote 8) e quando `sem_gaps_curtos`
    # entrou (lote do Dr. Fulano, 11/08/2026) -- nas duas eu consertei
    # so um lado. A guarda estava certa das duas vezes. Enquanto esta copia
    # existir, toda mudanca aqui e' em DOIS arquivos.
    # `rabo`: o TAIL_EXTRA por video (`rabo_final` no lote.json). So' a fase 2
    # o soma -- a guarda de timeline ignora o fim do ultimo segmento.
    rabo = TAIL_EXTRA if rabo is None else rabo
    segs[-1] = (segs[-1][0],
                config.na_grade(min(dur, segs[-1][1] + rabo), fps))
    return segs


def so_letras(s):
    return re.sub(r"[^\wÀ-ÿ]", "", s).lower()


def frases_com_tempo(v):
    toks = [json.loads(l) for l in
            open(f"{LOTE.trabalho}/{v}_palavras.json", encoding="utf-8") if l.strip()]
    txt = open(f"{LOTE.trabalho}/{v}_corte.srt", encoding="utf-8").read()
    frases, ref = [], []
    for b in re.findall(r"\d\d:\d\d:\d\d,\d+ --> .*?\n(.+?)(?=\n\n|\Z)", txt, re.S):
        for f in re.split(r"(?<=[.?!])\s+", b.strip()):
            if f.strip():
                frases.append(f.strip()); ref.extend(f.strip().split())
    pal, i = [], 0
    for alvo in ref:
        acc, ini, fim = "", None, None
        while i < len(toks):
            t = toks[i]
            # O inicio sai do primeiro token COM LETRA, nao do primeiro token.
            #
            # O whisper emite pontuacao como token proprio, e `so_letras` a
            # ignora na comparacao -- entao o '.' que fecha a frase anterior
            # sobra e e' consumido junto com a primeira palavra da seguinte.
            # A frase herdava o inicio DO PONTO FINAL DA FRASE ANTERIOR.
            #
            # Medido no v2 do L1 do Dr. Fulano (11/08/2026):
            #   33,290-33,580  '.'    <- fim de "...aumentando aos poucos."
            #   33,720-33,730  'A'    <- inicio real de "A boa noticia..."
            # A frase em destaque entrava em 33,29 e a fala so' comecava em
            # 33,72. O operador viu: "a animacao de texto aparece antes do
            # corte para a fala em si". Sao 0,43 s -- e o zoom congela 1,2 s
            # em volta dessa janela, entao o erro arrasta o congelamento junto.
            if ini is None and so_letras(t["text"]):
                ini = t["start"]
            acc += t["text"]; fim = t["end"]; i += 1
            # compara so as letras -- ver comentario igual em gerar_ass.py
            if so_letras(acc) == so_letras(alvo):
                break
            if len(so_letras(acc)) > len(so_letras(alvo)) + 2:
                break
        pal.append(((ini or 0) / 1000, (fim or 0) / 1000))
    saida, k = [], 0
    for f in frases:
        n = len(f.split())
        if k + n > len(pal):
            break
        saida.append((corrigir_frase(v, f), pal[k][0], pal[k + n - 1][1]))
        k += n
    return saida


def corrigir_frase(v, frase):
    """Aplica as `correcoes` do lote.json ao texto de uma frase.

    ARMADILHA (Dra. Fulana, 03/08/2026): as correcoes eram aplicadas
    so' na legenda pequena, dentro do gerar_ass.py. A FRASE EM DESTAQUE sai
    daqui, lendo o `_corte.srt` cru -- entao ela ignorava as correcoes.

    O v4 foi para a tela com "DO LICHEN PLAN." em corpo 200, no meio do
    quadro, enquanto a legenda pequena do mesmo video mostrava "LÍQUEN
    PLANO" corrigido no mesmo minuto. O elemento MAIS visivel da peca era o
    unico que nao passava pela correcao -- e e' termo clinico de medica.

    Mesma semantica do gerar_ass.py: valor com pontuacao troca o token
    inteiro, "~" termina sem pontuacao, "erro>proxima" e' condicional e
    "erro>proxima=" remove a palavra.
    """
    corr = {}
    for par in (CORR.get(str(v)) or "").split(","):
        if "=" in par:
            k, val = par.split("=", 1)
            corr[k.strip().lower()] = val.strip()
    if not corr:
        return frase
    ws, out = frase.split(), []
    for i, w in enumerate(ws):
        b = so_letras(w)
        prox = so_letras(ws[i + 1]) if i + 1 < len(ws) else ""
        novo = corr.get(f"{b}>{prox}", corr.get(b))
        if novo is None:
            out.append(w)
        elif novo == "":
            continue
        elif novo.endswith("~"):
            out.append(novo[:-1])
        elif so_letras(novo) != novo:
            out.append(novo)
        else:
            out.append(novo + w[len(b):])
    return " ".join(out)


def recorte_texto(v, alvo):
    """Casa um trecho contiguo da fala com os tokens e devolve (ini, fim).

    O whisper devolve PEDACO de palavra ("marc"+"adores", "vir"+"ar"), entao
    nao da para casar token a token: a comparacao e feita sobre o fluxo de
    LETRAS, com um indice de volta para o token. Mesma razao do casamento por
    letras em `frases_com_tempo` -- pontuacao e caixa variam entre passadas,
    letra nao.
    """
    toks = [json.loads(l) for l in
            open(f"{LOTE.trabalho}/{v}_palavras.json", encoding="utf-8") if l.strip()]
    letras, de_quem = "", []
    for k, t in enumerate(toks):
        for ch in so_letras(t["text"]):
            letras += ch
            de_quem.append(k)
    chave = so_letras(alvo)
    p = letras.find(chave)
    if p < 0 or letras.find(chave, p + 1) >= 0:
        return None                      # nao achou, ou achou mais de uma vez
    i, j = de_quem[p], de_quem[p + len(chave) - 1]
    return (round(toks[i]["start"] / 1000, 2), round(toks[j]["end"] / 1000, 2))


def escolher_musica(v):
    """Uma faixa por video, sem repetir dentro do lote e sem as copias.

    `musica` do lote.json sobrepoe a escolha NESTE video (dado de lote):
    a faixa sorteada pode ser mais curta que a peca, e ai o render aborta.
    """
    fixa = LOTE.musica.get(str(v))
    if fixa:
        c = os.path.join(MUSICAS, fixa)
        if os.path.isfile(c):
            return c
        raise SystemExit(f"v{v}: `musica` do lote.json aponta para {fixa!r}, "
                         f"que nao existe em {MUSICAS}")
    # Lista unica do acervo (config.faixas_de_musica, 02/10/2026).
    faixas = config.faixas_de_musica(MUSICAS)
    if not faixas:
        return None
    return faixas[list(FAIXAS).index(v) % len(faixas)]


def encaixar(t, cortes, tol=0.6):
    """Puxa t para o corte mais proximo, se houver um perto o bastante."""
    c = min(cortes, key=lambda x: abs(x - t))
    return c if abs(c - t) <= tol else t


def curva(cortes, total, janela, pb, punches=(), pequenos=()):
    """Curva de zoom -- modelo MEDIDO no video 7, que o operador aprovou.

    Devolve [(t0, t1, z0, z1)], linear dentro de cada trecho.

    O modelo anterior era o inverso deste, ponto por ponto: rampa continua
    com degrau pequeno na mesma direcao. O video 7 e PLATO PARADO com
    DEGRAU GRANDE ALTERNADO. Medido:

      - um nivel por CORTE (nao existe "movimento" agrupando cortes);
      - dentro do bloco o zoom fica PARADO -- deriva de 0,0 a 0,6 %/s em
        10 dos 11 blocos. A taxa media de deriva do video aprovado e
        0,25 %/s, sete vezes menor que a que eu perseguia;
      - degrau no corte de 6 a 14 pontos (mediana 10,5), contra os 2,8
        que eu usava -- quase invisiveis;
      - a direcao ALTERNA a quase todo corte;
      - niveis sempre em multiplo de 5, entre 100 e 120;
      - reset a 100 EXATO a cada ~10s;
      - UMA rampa forte por video (+9 pts a ~4,8 %/s), no bloco do P&B.

    Sobre o "vai e vem": nao vinha do degrau (que eu tirei na 2a rodada)
    nem da alternancia (que eu travei na 3a). Vinha da RAMPA. O video 7 e
    o material do Premiere alternam a direcao a quase todo corte; com o
    bloco parado, alternar le como troca de enquadramento.
    """
    congelado = None
    if janela:
        congelado = (encaixar(janela[0] - FOLGA_TEXTO, cortes),
                     encaixar(janela[1] + FOLGA_TEXTO, cortes))

    def gelado(a, b):
        return bool(congelado and b > congelado[0] + 0.01
                    and a < congelado[1] - 0.01)

    def no_pb(a, b):
        return bool(pb and a >= pb[0] - 0.30 and b <= pb[1] + 0.30)

    trechos, z = [], 1.00
    blocos = list(zip(cortes, cortes[1:]))
    # desloca a sequencia por video para que dois videos seguidos nao
    # tenham a mesma progressao de niveis
    desloc = len(blocos) * 3
    for i, (a, b) in enumerate(blocos):
        if i > 0:
            # O degrau acontece em TODO corte, inclusive no que entra e no
            # que sai da frase em destaque -- a regra dele e nao ter zoom
            # em movimento JUNTO com o texto, e um degrau seco no corte nao
            # e movimento. Suprimir o degrau tambem no bloco vizinho
            # deixava esse corte sem disfarce nenhum.
            # O nivel tem de ser DIFERENTE do nivel em que o bloco anterior
            # terminou, senao o degrau e zero e o corte fica seco -- que e a
            # unica coisa que o padrao dele nao admite. Acontecia de verdade:
            # o zoom comeca em 1,00 e a sequencia tem 1,00 em varias
            # posicoes, entao bastava (i+desloc) cair num deles. No lote da
            # Dra. Fulana (31/07/2026) derrubou o primeiro corte do v7 e
            # do v8 e um corte do meio do v2 -- 3 dos 8 videos. O punch piora,
            # porque termina o bloco num nivel que nao esta na sequencia.
            # Anda na sequencia ate achar um nivel que produza degrau.
            # `degrau_pequeno` (lote.json, instantes de BRUTO): neste corte o
            # degrau fica em 5 pt, o minimo do padrao. Nasceu na emenda de
            # tropeco do v2 da Fulano (18/09/2026): o corte tem de existir
            # (tira o "resolu-"), mas cai no MEIO da frase, e um degrau de
            # 10-15 pt ali "ajuda a evidenciar o erro" (ele). Escolhe o nivel
            # mais proximo da sequencia que ainda produza degrau.
            teto = 0.051 if any(abs(a - t) <= 0.25 for t in pequenos) else None
            for k in range(len(NIVEIS)):
                cand = NIVEIS[(i + desloc + k) % len(NIVEIS)]
                if abs(cand - z) >= 0.004 and (teto is None or abs(cand - z) <= teto):
                    if teto is not None:
                        print(f"      degrau pequeno em {a:.2f}s: "
                              f"{round((cand - z) * 100):+d} pt (`degrau_pequeno`)")
                    z = cand
                    break

        if gelado(a, b):
            zf = z                          # parado durante a frase
        elif no_pb(a, b):
            zf = round(min(ZMAX, z + RAMPA_PB), 4)   # a unica rampa forte
        else:
            zf = round(z + DERIVAS[i % len(DERIVAS)] * (b - a), 4)
            zf = max(ZMIN, min(ZMAX, zf))

        # punch: +5 pontos em 2 quadros que SEGURAM ate o corte seguinte
        pch = [t for t in punches if a + 0.35 < t < b - 0.35]
        if pch and not gelado(a, b) and not no_pb(a, b):
            t = pch[0]
            meio = round(z + (zf - z) * (t - a) / max(b - a, 0.01), 4)
            alto = round(min(ZMAX, meio + PUNCH), 4)
            trechos.append((a, t, z, meio))
            trechos.append((t, t + 2.0 / FPS, meio, alto))
            trechos.append((t + 2.0 / FPS, b, alto, alto))
            z = alto
            continue

        trechos.append((a, b, z, zf))
        z = zf
    return trechos


def escolher_punches(v, total, tarja_fim, janela, pb, cortes):
    """Ate 3 palavras de impacto por video, longe de corte e de efeito.

    O video 7 tem 3 punches (4,53 / 17,31 / 26,35s). Eu os removi na 2a
    rodada porque estavam gerando zoom bruto demais -- mas na epoca TODO
    corte tambem levava degrau. Com 3 no video inteiro, eles estao no
    material aprovado.
    """
    toks = [json.loads(l) for l in
            open(f"{LOTE.trabalho}/{v}_palavras.json", encoding="utf-8") if l.strip()]
    cand = []
    for t in toks:
        p = re.sub(r"[^\wÀ-ÿ]", "", t["text"])
        if len(p) < 8:
            continue
        ini = t["start"] / 1000
        if ini < tarja_fim + 0.6 or ini > total - 2.5:
            continue
        if janela and janela[0] - FOLGA_TEXTO < ini < janela[1] + FOLGA_TEXTO:
            continue
        if pb and pb[0] - 0.4 < ini < pb[1] + 0.4:
            continue
        if any(abs(ini - c) < 0.35 for c in cortes):
            continue
        cand.append((ini, len(p)))
    saida = []
    for ini, _ in sorted(cand, key=lambda x: -x[1]):
        if len(saida) >= min(3, int(total // 9)):
            break
        if all(abs(ini - s) >= 5.0 for s in saida):
            saida.append(ini)
    return sorted(saida)


def escolher_leaks(v, total, tarja_fim, janela, pb, cortes):
    """Leak ancorado no FIM DE FRASE, com o PICO no ponto final.

    Dois erros corrigidos aqui:

    1. A posicao era decidida pela estrutura do ZOOM (fronteira de
       movimento). Nos 10 leaks do operador o pico cai a 0 ms da fronteira
       de frase (mediana), 8 de 10 a menos de 113 ms. Nos meus 17, a
       mediana era 1198 ms -- e 17 de 17 tinham o pico dentro de palavra.

    2. O clarao do asset nao esta no inicio do clipe: esta 233 ms depois
       (quadro 7). Como o codigo alinhava o INICIO com o corte, o clarao
       vazava sempre para dentro da fala seguinte. Foi o caso do "comigo"
       no v9: leak em 23,480 (inicio exato da palavra), pico em 23,713.

    Densidade calibrada pelo video 7 (3 leaks em 33,7s = 1 a cada 11,2s),
    nao pela media dos 6 de referencia (1 a cada 33,7s) -- o video 7 e o
    unico que ele chamou de perfeito.
    """
    # TOL cobre o descasamento ESTRUTURAL entre "fim da frase" e "corte":
    # o corte fica em `fim da palavra + silencio restante + PAD/2`, o que
    # mede 260 a 420 ms com PAD=0,18. A tolerancia era 0,15s, calibrada
    # quando o PAD era 0,10 -- e nao foi rederivada quando o PAD subiu, o
    # que zerou os leaks de dois videos. Regra: tolerancia que depende de
    # um parametro tem de ser recalculada quando o parametro muda.
    tol = 0.30 + PAD * 1.4

    # Nao existe mais veto de "meio de palavra". Ele fazia sentido quando o
    # leak era ancorado pelo INICIO numa fronteira de zoom -- foi assim que
    # o clarao caiu dentro de "comigo". Com o PICO ancorado no CORTE, e o
    # corte sendo por construcao um silencio, o clarao nao tem como cair
    # dentro de fala. O problema foi resolvido na estrutura, nao no filtro.
    alvos = [tarja_fim]                     # o 1o leak e o da saida da tarja
    for _f, _a, fim in frases_com_tempo(v):
        alvos.append(fim)

    def cabe(c):
        if c < 0.5 or c > total - 0.8:
            return False
        if janela and janela[0] - 1.0 < c < janela[1] + 1.0:
            return False                    # texto grande leva stretch, nao leak
        return not (pb and pb[0] - 0.4 < c < pb[1] + 0.4)

    escolhidos = []
    orcamento = max(1, round(total / 11.2))
    for t in alvos:
        if len(escolhidos) >= orcamento:
            break
        c = min(cortes, key=lambda x: abs(x - t))
        if abs(c - t) > tol or not cabe(c):
            continue
        if any(abs(c - e) < 4.0 for e in escolhidos):
            continue
        escolhidos.append(round(c, 3))

    if not escolhidos:                      # nenhum video sai sem leak
        livres = [c for c in cortes[1:-1] if cabe(c)]
        if livres:
            escolhidos = [round(min(livres, key=lambda x: abs(x - total / 3)), 3)]
    return escolhidos


def folga_do_corte(a, b, cortes):
    """Distancia da janela do texto ate o corte mais proximo. -1 se houver
    corte DENTRO dela.

    Existe porque a escolha automatica da frase em destaque nao olhava para os
    cortes, e a regua exige que o zoom fique parado FOLGA_TEXTO de cada lado
    da frase. Uma janela colada num corte transforma esse congelamento em
    armadilha: a animacao do texto sai e, fracoes de segundo depois, o
    enquadramento troca sem nada disfarcando.

    Medido no lote da Dra. Fulana pt2 (11-12/08/2026), nos DOIS videos
    em que houve texto: no v6 a escolha caiu a 0,18 s de um corte e o operador
    viu "duas transicoes em 0,45 s" -- o whip saindo do texto e um corte seco
    logo atras; no v5, depois de eu aparar uma tomada, ela caiu a 0,05 s.
    Das 9 frases do v5, TRES tinham corte dentro delas.

    O -1 para corte interno nao e' detalhe: minha primeira medida procurava o
    corte DEPOIS do fim da frase e por isso nao enxergava corte no meio; com
    ela eu escolhi uma frase pior que a original e so' percebi conferindo.
    """
    dentro = [c for c in cortes[1:-1] if a <= c <= b]
    if dentro:
        return -1.0
    d = [min(abs(c - a), abs(c - b)) for c in cortes[1:-1]]
    return min(d) if d else 99.0


def escolher_pb(v, total, tarja_fim, janela, cortes):
    """Janela de preto e branco, montada A PARTIR DOS CORTES.

    Antes eu montava a janela com 1 a 3 frases inteiras e depois encaixava
    as bordas em corte. Nao funciona com o teto medido no video 7 (1,77s):
    as frases destes roteiros duram 4 a 5 segundos, entao nenhuma cabe e o
    lote inteiro saia sem P&B.

    Como a janela precisa comecar e terminar em corte de qualquer forma, o
    candidato natural e um par de cortes. O texto falado dentro dele serve
    para pontuar, nao para delimitar.
    """
    # Janela forcada pelo lote.json (`pb` por video). Existe porque a escolha
    # automatica so' enxerga PARES DE CORTE dentro de 1,6-2,5s, e as vezes o
    # ponto que o operador quer nao tem par nenhum -- ou tem um so', ruim.
    # Caso real (v7 da Dra. Fulana, 03/08/2026): ele pediu o P&B
    # comecando no inicio da citacao da paciente, e o unico par que comeca la
    # tem 2,88s. Ele autorizou; PB_MAX e' convencao DELE, calibrada no video
    # 7 aprovado, entao ele pode relaxa-la -- eu nao.
    forcada = LOTE.pb.get(str(v))
    if forcada:
        return (round(float(forcada[0]), 2), round(float(forcada[1]), 2))
    fr = frases_com_tempo(v)
    if len(fr) < 3 or total < 18:
        return None
    cta = fr[-1][1]                      # inicio da ultima frase = CTA
    melhor = None
    for i, a in enumerate(cortes[:-1]):
        for b in cortes[i + 1:]:
            if not PB_MIN <= b - a <= PB_MAX:
                continue
            if a < tarja_fim + 0.5 or b > min(cta - 0.3, total * 0.72):
                continue
            if janela and not (b < janela[0] - 1.0 or a > janela[1] + 1.0):
                continue
            # B-roll fica FORA do P&B (regua do b-roll). A escolha automatica
            # nao sabia do b-roll e, no v4 do lote 84 (14/10/2026), pos o P&B
            # exatamente no trecho do insert -- o render nao avisou; quem viu
            # foi a conferencia de quadro. Com `--sem-broll` a regra nao se
            # aplica, para a versao sem b-roll sair igual a de sempre.
            if not SEM_BROLL and any(
                    a < float(br["em"]) + float(br["dur"]) and b > float(br["em"])
                    for br in LOTE.broll.get(str(v), [])):
                continue
            txt = " ".join(f for f, fa, fb in fr if fb > a and fa < b).lower()
            # Proxy do "trecho de tristeza". Nao entendo o roteiro; uso os
            # dois sinais que o roteiro destes anuncios sempre carrega:
            # a dor vem negada ("nao sai", "sem resultado") e a solucao vem
            # na voz da clinica ("nos avaliamos", "aqui investigamos").
            dor = sum(txt.count(p) for p in (" não", " nem ", " sem ",
                                             "parou", "anos", "cansa", "dor"))
            clinica = sum(txt.count(p) for p in ("nós ", "aqui ", "agende",
                                                 "avaliamos", "buscamos",
                                                 "investigamos", "pedimos"))
            nota = (abs((a + b) / 2 - total * 0.30) - (b - a) * 0.5
                    - dor * 1.5 + clinica * 3.0)
            if melhor is None or nota < melhor[0]:
                melhor = (nota, a, b)
    return (round(melhor[1], 2), round(melhor[2], 2)) if melhor else None


def conferir_timeline(v, segs_f1):
    """Aborta se a legenda foi gerada sobre um corte que nao existe mais.

    ARMADILHA CARA (Dra. Fulana, 31/07/2026): a fase 1 regrava o
    `_corte.wav` mas pulava a transcricao se o arquivo ja existisse. Mudar
    `nivel_silencio` no lote.json e rodar de novo produzia video novo com
    legenda VELHA -- 1 a 2,6 s de atraso em tres videos, e o pipeline nao
    imprimia absolutamente nada. Quem viu foi o operador, na tela.

    A fase 1 ja' foi consertada (ela descarta a transcricao quando o corte
    muda). Isto aqui e' a segunda barreira: mesmo que alguem edite artefato
    a mao, ou rode as fases fora de ordem, o render nao sai errado calado.

    O `total` daqui inclui o TAIL_EXTRA, que so' existe na fase 2 -- por
    isso ele e' descontado antes de comparar.
    """
    marca = os.path.join(LOTE.trabalho, f"{v}_corte.json")
    if not os.path.exists(marca) or not segs_f1:
        return
    # Compara a LISTA DE SEGMENTOS com a que a fase 1 gravou, e nao duracoes.
    #
    # A versao por duracao descontava TAIL_EXTRA do total, supondo que ele
    # sempre entra. Nao entra: `segmentos()` faz `min(dur, fim + TAIL_EXTRA)`,
    # entao num video cujo corte ja termina no fim do bruto ele e' engolido —
    # e a guarda acusava 0,46s de desvio inexistente no v2 do Dr. Fulano,
    # abortando um render correto. Guarda que da falso positivo e' pior que
    # guarda nenhuma: ensina a ignorar o aviso.
    #
    # A assinatura ignora o FIM do ultimo segmento, que e' justamente o unico
    # ponto onde as duas fases divergem de proposito.
    def assinar(segs):
        corpo = [[round(a, 3), round(b, 3)] for a, b in segs[:-1]]
        return json.dumps(corpo + [round(segs[-1][0], 3)])

    velha = open(marca, encoding="utf-8").read()
    try:
        antes = json.loads(velha)
        agora = json.loads(assinar(segs_f1))
        igual = ([p for p in antes[:-1]] == agora[:-1]
                 and abs(antes[-1][0] - agora[-1]) < 0.02) if antes else True
    except (ValueError, IndexError, TypeError, KeyError):
        igual = True                      # formato antigo: nao sei conferir
    if not igual:
        sys.exit(
            f"v{v} ABORTADO: a legenda foi gerada sobre outro corte.\n"
            f"  os segmentos mudaram desde a fase 1 — a legenda esta na\n"
            f"  timeline errada e sairia dessincronizada.\n"
            f"  Conserto: apague trabalho/{v}_corte.srt e "
            f"trabalho/{v}_palavras.json e rode a fase 1 de novo.")


def _bruto_para_corte(t, segs):
    """Instante do BRUTO -> instante na timeline do CORTE.

    Dentro de um trecho, e' o deslocamento dentro dele; num vao (silencio
    descartado), e' o inicio do trecho seguinte -- o mais perto que existe
    na peca. Serve para `tarjas_em`, que o operador escreve em tempo de
    bruto (e' o relogio que ele tem, o do juncoes.json e do N_corte.json).
    """
    acum = 0.0
    for a, b in segs:
        if t < a:
            return round(acum, 3)
        if t <= b:
            return round(acum + (t - a), 3)
        acum += b - a
    return round(acum, 3)


def produzir(v, legenda_nossa=True, base=False):
    """Renderiza o video `v`.

    `base=True` entrega a peca SEM legenda nenhuma, em `<v>_BASE.mp4` e em
    qualidade alta. Serve para TROCAR A FONTE (ou a cor, o corpo, a posicao)
    sem refazer o render inteiro: a legenda e' das ultimas coisas do grafo, e
    tudo antes dela -- corte, zoom, P&B, leaks, tarja, card, audio, musica --
    e' identico quando so' a tipografia muda. Depois basta queimar o `.ass`
    por cima com `scripts/queimar_legenda.py`.

    Medido em 25/08/2026, lote do Dr. Fulano: render completo ~2h20 o
    lote; queimar a legenda sobre a base, ~5 min o lote. O cliente mandou a
    fonte Manier em versao Trial e prometeu a completa depois, o que obrigaria
    a um segundo render inteiro.

    CUSTO DECLARADO: a peca final passa por DOIS encodes (a base e a versao
    com legenda). Por isso a base sai em `crf 14`, quase transparente -- ocupa
    ~4x mais disco e existe justamente para o segundo encode nao herdar
    artefato do primeiro.

    ARMADILHA: com `base=True` a frase em destaque some do texto, mas o whip,
    o blur e a aberracao que a acompanham CONTINUAM no grafo -- eles vivem no
    filtro, nao no `.ass` (e' o mesmo erro que o `duas_versoes` ja' cometeu, ver
    `ass_so_do_texto`). Ficaria um borrao sem texto. Por isso video com janela
    de texto grande e' RECUSADO aqui, em vez de sair errado calado.

    `legenda_nossa=False` entrega a MESMA edicao com a legenda que o proprio
    cliente queimou no bruto: sem a nossa legenda e, por consequencia, sem a
    tarja preta que cobria a dele. Pedido do chefe dele em 03/08/2026 -- ele
    quer as duas versoes para escolher. Corte, zoom, leaks, P&B, frase em
    destaque, musica e tarja de nome/CRM sao identicos nas duas: a unica
    diferenca e' de quem e' a legenda.
    """
    # Card por VIDEO (padrao de 14/10/2026: card so' onde o video NAO tem CTA
    # falado, decidido video a video). `sem_card` no lote.json lista os videos
    # que saem sem ele; o `sem_finalizacao` continua desligando o lote inteiro.
    # Local de proposito: sombreia o TEM_FINAL do modulo so' neste video.
    TEM_FINAL = TEM_FINAL_LOTE and str(v) not in LOTE.sem_card
    if TEM_FINAL_LOTE and not TEM_FINAL:
        print(f"      v{v}: SEM card (sem_card no lote.json -- CTA falado)")
    src = LOTE.bruto_de(v)
    segs = segmentos(src, FAIXAS[v], LOTE.nivel_de(v), LOTE.pausa_de(v),
                     LOTE.cortes_vetados_de(v), LOTE.cauda_de(v),
                     LOTE.rabo_de(v, TAIL_EXTRA))
    config.exigir_audio_no_inicio(v, src, segs)
    total = sum(b - a for a, b in segs)
    conferir_timeline(v, segs)
    cortes = [0.0]
    for a, b in segs:
        cortes.append(round(cortes[-1] + (b - a), 3))
    cortes[-1] = round(total, 3)

    # A tarja sai junto com um corte -- regra dele. Mas so vale encaixar
    # num corte PERTO: com o PAD de 0,18 o v4 ficou com 3 cortes internos,
    # o mais proximo de 4,40s estava em 7,87s, e a tarja ficava 7,9s na
    # tela (o dobro). Quando nao ha corte na janela, sair fora de corte e
    # o menor prejuizo -- a tarja tem fase firme ate 3,8s e some em 4,4s.
    perto = [c for c in cortes[1:-1] if 3.6 <= c <= 5.8]
    atraso = (min(perto, key=lambda c: abs(c - TARJA_SAI)) - TARJA_SAI
              if perto else 0.0)

    # MAIS DE UMA TARJA (lote 48, Clínica X, 16/09/2026): duas
    # profissionais, e em 4 pecas as duas aparecem. Decisao dele: as duas
    # tarjas, SEQUENCIAIS, na ordem em que aparecem. A 1a segue a regra de
    # sempre (sai num corte perto de 4,4 s); a k-esima entra quando a
    # anterior sai -- ou no instante de BRUTO que `tarjas_em` mandar, para o
    # caso em que quem fala TROCA no meio da peca (v9: hook da Fulana, corpo
    # da Beltrana -- a 2a tarja entra na juncao, senao cai o nome de uma sobre
    # o rosto da outra). Os indices de entrada do ffmpeg viram locais, porque
    # o numero de tarjas agora muda por video.
    tarjas = LOTE.tarjas_de(v)
    if any(t is None for t in tarjas):
        sys.exit(f"v{v} ABORTADO: tarja nomeada sem arquivo -- "
                 f"{LOTE.tarjas.get(str(v))} (ver conferir_lote.py)")
    atrasos = [atraso]
    for k in range(1, len(tarjas)):
        em = LOTE.tarjas_em_de(v)[k]
        if em is None:
            ini = atrasos[-1] + TARJA_SAI
        else:
            ini = _bruto_para_corte(float(em), segs)
        fim = ini + TARJA_SAI
        perto = [c for c in cortes[1:-1] if fim - 0.8 <= c <= fim + 1.4]
        if perto:
            cand = min(perto, key=lambda c: abs(c - fim)) - TARJA_SAI
            # com instante explicito, nunca ADIANTAR: a tarja entraria antes
            # da troca de pessoa, que e' exatamente o que ela evita.
            if em is None or cand >= ini:
                ini = cand
        atrasos.append(round(ini, 3))
    tarja_fim = atrasos[-1] + TARJA_SAI
    idx_final = 2 + len(tarjas)
    idx_musica = idx_final + TEM_FINAL
    if len(tarjas) > 1:
        print(f"      tarjas: {len(tarjas)} -- entram em "
              + ", ".join(f"{a:.2f}s" for a in atrasos)
              + f" (ultima sai em {tarja_fim:.2f}s)")

    # As correcoes de SEQUENCIA vem ANTES da escolha da frase em destaque:
    # `frases_com_tempo` le o `_corte.srt` do disco, e com a correcao depois
    # a 1a rodada escolhia o texto do srt AINDA CRU. Lote 87 v4 (15/10/2026):
    # o token duplicado "Certo?", que a regra apagava, foi para a tela em
    # corpo grande; a 2a rodada (srt ja' corrigido) saiu certa.
    for f in aplicar_correcoes_sequencia(v):
        print(f"      corrigido no corte: {f}")

    janela, linhas = None, None
    if v in SEM_TEXTO:
        print(f"      v{v}: sem frase em destaque (`sem_texto` no lote.json)")
    elif v in TEXTO_RECORTE:
        alvo = TEXTO_RECORTE[v]
        # O alvo se escreve COMO O WHISPER TRANSCREVEU, porque `recorte_texto`
        # casa por letras contra o `_palavras.json` cru -- escrever o termo ja
        # corrigido faz o casamento falhar. Mas a TELA tem de mostrar o texto
        # corrigido: sem o `corrigir_frase` aqui, o recorte era o unico caminho
        # que exibia texto sem passar pelas `correcoes`, e ia para o quadro em
        # corpo 200 com o erro do whisper enquanto a legenda pequena do mesmo
        # video mostrava o certo. E' a armadilha do "LIQUEN PLANO" (Dra. Fulana
        # Fulano, 03/08/2026) sobrevivendo no caminho do override -- achada no
        # lote do Dr. Fulano (11/08/2026), onde o termo e' `vasinho`.
        janela = recorte_texto(v, alvo)
        linhas = quebrar(corrigir_frase(v, alvo).upper())
        if not janela or not linhas or len(linhas) > MAX_LINHAS:
            print(f"v{v}: recorte de texto FALHOU -> {janela} {linhas}")
            return False
        # O override NAO pode furar a borda que a escolha automatica respeita.
        # Ate 12/08/2026 ele furava, e fui EU quem furou: pus a frase em
        # 0,00-3,62 no v2, 0,09-2,06 no v4 e 30,44-31,70 no v5 (de 32,40),
        # e o operador reprovou os tres — *"n pode ter essa animacao de texto
        # e zoom no comeco"*, *"a animacao de texto literalmente no final nao
        # me agrada"*. A regra ja existia no `elif` abaixo; o caminho manual
        # e' que passava por cima dela em silencio.
        if janela[0] < tarja_fim + 0.4 or janela[1] > total - 2.0:
            print(f"v{v}: recorte de texto RECUSADO -> {janela[0]:.2f}-"
                  f"{janela[1]:.2f} abre ou fecha o video "
                  f"(livre: {tarja_fim + 0.4:.2f} a {total - 2.0:.2f})")
            return False
        # `validar_folga_override` (02/10/2026): ligado no lote.json, o
        # override passa pela MESMA folga da escolha automatica. Desligado
        # (padrao), segue a valvula de escape de 14/09 -- ver CLAUDE.md.
        if LOTE.validar_folga_override:
            fo = folga_do_corte(janela[0], janela[1], cortes)
            if fo < FOLGA_ESCOLHA:
                print(f"v{v}: recorte de texto RECUSADO -> {janela[0]:.2f}-"
                      f"{janela[1]:.2f} " + ("tem corte DENTRO da janela"
                      if fo < 0 else f"fica a {fo:.2f}s do corte")
                      + f" (minimo {FOLGA_ESCOLHA:.1f}s; "
                      f"`validar_folga_override` ligado)")
                return False
    elif total >= MIN_DUR_TEXTO:
        for f, a, b in frases_com_tempo(v):
            if a < tarja_fim + 0.4 or b > total - 2.0:
                continue
            if f.lower().startswith(("que ", "mas ", "e ", "para ", "como ")):
                continue                 # fragmento, nao frase inteira
            if folga_do_corte(a, b, cortes) < FOLGA_ESCOLHA:
                continue                 # ver `folga_do_corte`
            L = quebrar(f.upper())
            if L and len(L) <= MAX_LINHAS:
                janela, linhas = (round(a, 2), round(b, 2)), L
                break
        if janela is None:
            print(f"      v{v}: nenhuma frase tem {FOLGA_ESCOLHA:.1f}s de folga "
                  f"ate o corte -- video SEM texto em destaque "
                  f"(use `texto_recorte` se quiser um)")

    if base and janela:
        # O whip, o blur e a aberracao da frase em destaque vivem no GRAFO;
        # so' o TEXTO vive no `.ass`. Sem a legenda, aquela janela viraria um
        # borrao mudo -- e sairia calado, que e' a familia de defeito que este
        # projeto mais apanhou. Recusar e' melhor que entregar errado.
        print(f"v{v}: RECUSADO como base -- tem frase em destaque em "
              f"{janela[0]}-{janela[1]}s. Sem a legenda sobraria o borrao sem "
              f"texto. Use `sem_texto` no lote.json, ou renderize normal.")
        return False

    # a ordem importa: o P&B define onde vai a unica rampa forte, e tanto
    # ele quanto a frase em destaque vetam punch e leak.
    pb = None if v in SEM_PB else escolher_pb(v, total, tarja_fim, janela, cortes)
    punches = escolher_punches(v, total, tarja_fim, janela, pb, cortes)
    leaks_t = escolher_leaks(v, total, tarja_fim, janela, pb, cortes)
    pequenos = [_bruto_para_corte(float(t), segs)
                for t in LOTE.degrau_pequeno.get(str(v), [])]
    movs = curva(cortes, total, janela, pb, punches, pequenos)
    T = f"on/{FPS}"

    # Onde a legenda cai: sem tarja, no lugar de sempre; com tarja, no CENTRO
    # dela. Tarja e legenda sao as duas fixas, entao a legenda fica
    # centralizada por construcao. A versao anterior movia a tarja com o zoom
    # e dava um Y por EVENTO para a legenda -- o que nao acompanha degrau nem
    # punch dentro do evento, e ela saia do centro.
    # A tarja escala com o zoom, entao a legenda tem de segui-la. O gerar_ass
    # PARTE cada evento nos instantes em que o zoom muda e calcula um Y por
    # pedaco -- e o reposicionamento cai no corte, onde a imagem ja muda.
    pos_arq = ""
    if cobre_v := LOTE.legenda_do_cliente.get(str(v)):
        pos_arq = f"{v}_legenda_pos.json"
        json.dump({"faixa": cobre_v,
                   "zoom": [[m[0], m[1], m[2], m[3]] for m in movs]},
                  open(os.path.join(LOTE.trabalho, pos_arq), "w"))

    # Estilo (cor/fonte) e do lote inteiro, entao um arquivo so. Escrito aqui
    # e nao no config para os DOIS consumidores lerem exatamente o mesmo JSON.
    est_arq = ""
    if LOTE.estilo:
        est_arq = "_estilo.json"
        json.dump(LOTE.estilo,
                  open(os.path.join(LOTE.trabalho, est_arq), "w",
                       encoding="utf-8"), ensure_ascii=False)

    r = rodar([sys.executable, os.path.join(SCR, "gerar_ass.py"),
               f"{v}_palavras.json", f"{v}_corte.srt", f"{v}_legenda.ass",
               CORR.get(v, ""), pos_arq,
               str(LOTE.legenda_y.get(str(v), "")), est_arq],
              cwd=LOTE.trabalho)
    if r.returncode:
        print(f"v{v}: legenda FALHOU -> {r.stdout} {r.stderr[:200]}")
        return False
    if r.stdout.strip():
        print(r.stdout.rstrip())
    if janela:
        rodar([sys.executable, os.path.join(SCR, "texto_grande.py"),
               f"{v}_legenda.ass", str(janela[0]), str(janela[1]),
               "|".join(linhas), est_arq], cwd=LOTE.trabalho)

    def prog(m):
        return f"min(max(({T}-{m[0]})/{max(m[1]-m[0],0.01):.4f},0),1)"

    e = f"({movs[-1][2]}+{movs[-1][3]-movs[-1][2]:.4f}*{prog(movs[-1])})"
    for m in reversed(movs[:-1]):
        e = f"if(lt({T},{m[1]}),({m[2]}+{m[3]-m[2]:.4f}*{prog(m)}),{e})"
    zx = f"({e})"
    w, h = f"(W/{zx})", f"(H/{zx})"
    persp = (f"perspective=eval=frame:interpolation=cubic:"
             f"x0='(W-{w})/2':y0='(H-{h})/2':x1='(W+{w})/2':y1='(H-{h})/2':"
             f"x2='(W-{w})/2':y2='(H+{h})/2':x3='(W+{w})/2':y3='(H+{h})/2'")

    # O PICO do asset esta 233 ms depois do inicio do clipe (quadro 7).
    # Ancorar o inicio no corte punha o clarao dentro da fala seguinte em
    # 17 de 17 leaks do lote anterior. Ancorando o pico, ele estoura no
    # ponto final da frase -- que e onde os 10 leaks do operador caem.
    leaks = [(max(0.0, t - LEAK_PICO), *LEAK_TRECHOS[i % len(LEAK_TRECHOS)])
             for i, t in enumerate(leaks_t)]

    # O trim de VIDEO corta meio quadro antes da fronteira. `na_grade` poe
    # `a` e `b` exatamente num quadro, mas escritos com 3 casas os quadros em
    # x,xx67 arredondam para DEPOIS do quadro (2,1666.. -> 2,167) e o trim,
    # cujo fim e' exclusivo, levava 1 quadro a mais; o `concat` completava o
    # audio com 33 ms de silencio e tudo que e' cronometrado pela timeline do
    # corte (legenda, degrau, leak, stretch) ficava ADIANTADO em relacao ao
    # render -- 131 ms no V1 do lote 78 (Dr. Fulano, 07/10/2026),
    # 33-66 ms nos lotes 76 e 77, com A/V do render em sincronia e o
    # `lote_verificar` aprovando. Com meio quadro de margem a escolha do
    # quadro deixa de depender de arredondamento. O audio continua exato.
    meio_q = 0.5 / config.fps_de(src)
    partes, lbl = [], []
    for i, (a, b) in enumerate(segs):
        partes.append(f"[0:v]trim={max(0.0, a - meio_q):.6f}:{b - meio_q:.6f},"
                      f"setpts=PTS-STARTPTS[v{i}]")
        partes.append(f"[0:a]atrim={a:.3f}:{b:.3f},asetpts=PTS-STARTPTS[a{i}]")
        lbl.append(f"[v{i}][a{i}]")
    partes.append("".join(lbl) + f"concat=n={len(segs)}:v=1:a=1[vc][ac]")
    # fps ANTES do perspective, nao depois. O `perspective` so conhece `on`
    # (contador de quadros), nunca `t`, e `on` conta quadros de ENTRADA. Com
    # o fps depois, um bruto de 59,94 fps fazia a curva inteira rodar a
    # 1,998x da velocidade: acabava na metade do video e o zoom congelava
    # ate o fim. Era a causa de "sem zoom do meio pro final" (v3, v5),
    # "zoom estranho" (v2) e "degrau fora de corte" nos tres.
    # Tarja que cobre a legenda que o PROPRIO cliente queimou no bruto.
    #
    # ANTES do zoom: assim ela escala junto com a legenda dele, que esta
    # gravada no video, e precisa ter apenas a altura DELA -- nao a uniao das
    # posicoes que ela ocupa entre 100% e o zoom maximo. No v3 isso e' a
    # diferenca entre 375 px e ~275 px na tela.
    #
    # Isso so' e' possivel porque a nossa legenda passou a ser PARTIDA nos
    # instantes em que o zoom muda (ver gerar_ass.py): com um Y unico por
    # evento, um degrau caindo no meio de uma palavra deslocava a legenda em
    # ate 58 px e ela saia do centro da tarja -- que foi o que ele reprovou.
    tapa = ""
    if (cobre := LOTE.legenda_do_cliente.get(str(v))) and legenda_nossa:
        y0, y1 = cobre[0] - FOLGA_TARJA, cobre[1] + FOLGA_TARJA
        tapa = (f"drawbox=x=0:y={int(PRE_H*y0)}:w={PRE_W}:"
                f"h={int(PRE_H*(y1-y0))}:color={COR_TARJA}:t=fill,")
    # HDR->SDR quando o bruto e' HLG, string vazia quando ja e' SDR (a
    # deteccao e' por ARQUIVO: no lote da Fulano 5 dos 8 eram HLG e 3 nao).
    # Vem antes de tudo de propósito: o `eq` de contraste/saturacao la'
    # embaixo foi calibrado em material BT.709, e aplicá-lo sobre codigos
    # HLG e' o que produzia a imagem lavada. Ver config.tonemap_de.
    tm = config.tonemap_de(src)
    # LUT de cor do cliente, quando o bruto chega em log (Dra. Fulana, S-Log3).
    # Ao lado do tone-map e pelo MESMO motivo: os dois trazem a imagem para o
    # espaco em que o `eq` la' embaixo foi calibrado. Aplicar o `eq` sobre log
    # e' a mesma classe de erro que aplica-lo sobre HLG.
    #
    # Na ordem, o LUT vem DEPOIS do tone-map (que nunca dispara junto: log nao
    # e' HLG) e ANTES do `scale` de trabalho — corrigir cor em imagem ja
    # reamostrada mistura os dois erros e nao da' para separar depois.
    cor = config.cor_de(src, LOTE.lut_de(v))
    # Recorte fixo de enquadramento (marca d'agua de app de captacao). Entra
    # DEPOIS da cor e ANTES do scale de trabalho: o crop e' em px do bruto,
    # e tudo que vem depois (zoom, tarja, legenda, stretch) parte do
    # PRE_W x PRE_H reescalado, entao nao percebe a diferenca.
    rb = LOTE.recorte_base_de(v)
    rec = f"crop={rb[0]}:{rb[1]}:{rb[2]}:{rb[3]}," if rb else ""
    partes.append(f"[vc]{tm}{cor}{rec}fps={FPS},scale={PRE_W}:{PRE_H}:flags=lanczos,{tapa}"
                  f"{persp},scale=1080:1920:flags=lanczos[vz]")

    SAT = 1.12
    sat = str(SAT) if not pb else (
        f"if(lt(t,{pb[0]}),{SAT},if(lt(t,{pb[0]+0.10}),"
        f"{SAT}*({pb[0]+0.10}-t)/0.10,if(lt(t,{pb[1]}),0,{SAT})))")
    cad = [f"eq=eval=frame:contrast=1.05:saturation='{sat}'"]
    # Tarja que cobre a legenda que o PROPRIO cliente queimou no bruto.
    #
    # DEPOIS do zoom (o [vz] ja veio escalado), e fixa na tela: cobre a
    # UNIAO das posicoes que a legenda dele ocupa entre 100% e o zoom
    # maximo. A primeira versao a punha ANTES do zoom, para escalar junto
    # com a legenda dele e usar a altura minima -- mas ai a tarja se mexe, e
    # a nossa legenda, com um Y por evento, nao acompanha degrau nem punch
    # DENTRO do evento: ela saia do centro. Fixa custa altura e devolve a
    # sincronia, que e' o que se ve.
    #
    # E ANTES do blur da frase em destaque, nao na cauda: desenhada depois,
    # a tarja ficava nitida e chapada sobre um fundo borrado, virando uma
    # barra dura no meio da imagem. Aqui ela borra junto com o resto.
    if janela:
        cad.append(f"gblur=sigma=46:steps=3:"
                   f"enable='between(t,{janela[0]},{janela[1]})'")
    if pb:
        cad.append(f"gblur=sigma=26:sigmaV=0:steps=2:"
                   f"enable='between(t,{pb[1]},{pb[1]+0.18})'")
    partes.append("[vz]" + ",".join(cad) + ",format=yuva420p[vtar]")

    # --- B-ROLL: imagem de apoio por cima, a FALA continua por baixo.
    #
    # Entra AQUI, no dominio yuva420p, e nao la' embaixo depois do
    # `format=gbrp`. ARMADILHA (03/08/2026): a primeira versao fazia o
    # overlay com os dois lados em gbrp, e o video INTEIRO saiu magenta --
    # nao so' a janela do b-roll. Os planos G/B/R se embaralham na
    # negociacao de formato do overlay. A tarja, que sempre funcionou, e' a
    # prova de qual dominio serve: ela faz overlay em yuva420p e so' DEPOIS
    # converte para gbrp. Mesmo caminho aqui.
    #
    # Fica antes dos leaks e da legenda de proposito: o leak passa por cima
    # (e' ele que disfarca a entrada/saida, que sao cortes) e a legenda fica
    # legivel em cima de tudo.
    #
    # O material do AF ACADEMY e' 16:9 HORIZONTAL (3840x2160, sem metadado de
    # rotacao -- conferido em quadro, o raw ja' esta' de pe). Para 1080x1920
    # sobra 31,6% da largura, entao e' recorte CENTRAL: escolher clipe com o
    # assunto no meio do quadro, senao o corte decapita a acao.
    #
    # O indice da entrada no ffmpeg so' e' conhecido depois que a musica for
    # escolhida, la' embaixo -- por isso o marcador @BRk@, trocado na hora de
    # montar a linha de comando.
    cadeia = "vtar"
    brolls = [] if SEM_BROLL else LOTE.broll.get(str(v), [])
    for k, b in enumerate(brolls):
        em, dur, de = float(b["em"]), float(b["dur"]), float(b.get("de", 0))
        # GRADE DE QUADROS (lote 81, 07/10/2026): o `enable` compara o t de
        # cada QUADRO com `em` em ms. Com em=8,467 o quadro 254 (t=8,4667)
        # ficava de fora e piscava 1 quadro do plano seguinte antes do
        # b-roll -- e o mesmo na saida (V7: 1 quadro dela entre o b-roll e o
        # corte). Entrada e saida viram quadro inteiro, e o `enable` usa o
        # MEIO-quadro como limite, que nao tem empate de arredondamento.
        q0, q1 = round(em * FPS), round((em + dur) * FPS)
        em, dur = q0 / FPS, (q1 - q0) / FPS
        partes.append(
            f"[@BR{k}@:v]trim={de:.3f}:{de + dur:.3f},setpts=PTS-STARTPTS,"
            # CABE INTEIRO, nao recorta. Um 16:9 recortado para 9:16 perde
            # 68% da largura, e o operador viu o resultado como "muuuuuito
            # zoom, ta estranho" (03/08/2026) -- com razao: o recorte
            # transformava um plano de procedimento num close de mao.
            # Agora o clipe entra inteiro, largura 1080, e o resto do quadro
            # e' preenchido com uma copia dele mesmo desfocada e ampliada
            # (o mesmo truque que a legenda em destaque ja usa como fundo).
            f"split=2[bf{k}][bn{k}];"
            f"[bf{k}]scale=1080:1920:force_original_aspect_ratio=increase,"
            f"crop=1080:1920,gblur=sigma=40,eq=brightness=-0.12[bg{k}];"
            f"[bn{k}]scale=1080:-2[bv{k}];"
            f"[bg{k}][bv{k}]overlay=0:(H-h)/2,"
            f"fps={FPS},format=yuva420p,"
            f"tpad=start_duration={em:.3f}:color=black[br{k}]")
        partes.append(
            f"[{cadeia}][br{k}]overlay=0:0:eof_action=pass:"
            f"enable='between(t,{em - 0.5 / FPS:.4f},{em + dur - 0.5 / FPS:.4f})'"
            f"[vbr{k}]")
        cadeia = f"vbr{k}"

    # Tarja e card sao OPCIONAIS: um lote de teste roda antes de a arte do
    # cliente existir (Dr. Fulano, 31/07/2026 — ele so terá tarja nos finais).
    # Os indices de entrada do ffmpeg passam a ser calculados, nao fixos:
    # com a tarja ausente, o que era [3:v] vira [2:v] e o grafo casaria o
    # card no lugar da tarja, em silencio.
    if tarjas:
        for k, a_k in enumerate(atrasos):
            partes.append(f"[{2 + k}:v]trim={max(0.0,-a_k):.3f},"
                          f"setpts=PTS-STARTPTS+{max(0,a_k):.3f}/TB,"
                          f"scale=1080:1920,format=yuva420p[tar{k}]")
        dy = LOTE.tarja_offset.get(str(v), 0)
        # `gbrap`, nao `gbrp`. A sequencia yuva420p -> gbrp esbarra num bug de
        # cauda SIMD do swscale: ele processa a linha em blocos de 16 px e NAO
        # escreve o resto, que fica no valor de inicializacao do buffer -- preto
        # de faixa limitada (Y=16). Como 1080 = 67*16 + 8, sobrava uma COLUNA
        # PRETA DE 8 px na borda direita de toda peca 1080 de largura.
        #
        # Medido em 27/08/2026: reproduz com resto 4 e 8 (1076, 1080, 1092,
        # 1096) e nao reproduz com resto 0 e 12 (1072, 1084, 1088, 1104, 1920).
        # Nao e' o scale, nem o persp, nem o zoom -- os tres saem limpos; e
        # `format=gbrp` sozinho tambem sai limpo. So' a SEQUENCIA enegrece.
        #
        # E' antigo e nao e' deste lote: varridos 155 renders de 20 lotes, os
        # 20 tem a coluna. Todas as pecas entregues desde julho/2026 saíram com
        # ela, e nenhum portao a viu -- dimensao, sync, nivel e RGB medio
        # continuam batendo, porque 8 px em 1080 e' 0,74% da largura.
        #
        # `gbrap` e' o mesmo RGB planar com o plano alfa, e nao passa pelo
        # caminho quebrado. Nao muda geometria: nenhum scale/crop/pad/coordenada
        # se move -- devolve 8 px que estavam sendo apagados.
        # Uma tarja por overlay, encadeados: a k-esima entra em cima da
        # anterior ja' composta. Com uma tarja so' e' o grafo de sempre.
        ent = cadeia
        for k in range(len(atrasos)):
            rot = "vrgb" if k == len(atrasos) - 1 else f"vt{k}"
            fmt = ",format=gbrap" if k == len(atrasos) - 1 else ""
            partes.append(f"[{ent}][tar{k}]overlay=0:{dy}:eof_action=pass"
                          f"{fmt}[{rot}]")
            ent = rot
    else:
        partes.append(f"[{cadeia}]format=gbrap[vrgb]")

    atual = "vrgb"
    if leaks:
        partes.append(f"[1:v]split={len(leaks)}" +
                      "".join(f"[s{k}]" for k in range(len(leaks))))
        for k, (t0, a, b) in enumerate(leaks):
            d = b - a
            # `stop_duration` era **60 fixo**, e com `shortest=1` no blend o
            # video inteiro morria quando o leak acabava: o leak dura
            # t0 + d + 60, entao todo video mais longo que isso era TRUNCADO.
            #
            # Medido no L1 do Dr. Fulano (11/08/2026): o v3 tem o
            # primeiro leak em t0=2,77 s com d=0,50 s -> 3,27 + 60 = **63,27 s**,
            # exatamente onde a imagem morre num video de 65,23 s. O v6 idem
            # (63,87 s). Os outros quatro escaparam por terem menos de 60 s ou
            # o primeiro leak mais tarde.
            #
            # O sintoma na tela era o card entrar no tempo certo sobre um vazio:
            # o operador viu "a tela fica preta so com o audio ate a finalizacao".
            # Nenhuma verificacao pegou -- `lote_verificar` compara video com
            # audio, e os dois incluiam o buraco.
            #
            # A cauda agora cobre o video inteiro com folga do card, para o
            # `shortest=1` nunca ser decidido pelo leak.
            cauda_leak = total + FINAL_DUR + 1.0
            partes.append(
                f"[s{k}]trim={a}:{b},setpts=PTS-STARTPTS,scale=1080:1920,fps={FPS},"
                f"fade=t=in:d=0.05,fade=t=out:st={d-0.05:.2f}:d=0.05,format=gbrp,"
                f"colorchannelmixer=rr=1.35:gg=1.50:bb=2.00,"
                f"tpad=start_duration={t0}:stop_duration={cauda_leak:.2f}:"
                f"color=black[lk{k}]")
            partes.append(f"[{atual}][lk{k}]blend=all_mode=screen:shortest=1[vb{k}]")
            atual = f"vb{k}"

    cauda = ["format=yuv420p"]
    if base:
        pass          # nenhuma legenda -- ver docstring
    elif legenda_nossa:
        cauda.append(f"subtitles={ass_para_queimar(v, f'{v}_legenda.ass')}"
                     f":fontsdir=fonts")
    elif janela:
        cauda.append(f"subtitles="
                     f"{ass_para_queimar(v, ass_so_do_texto(v, janela, linhas))}"
                     f":fontsdir=fonts")
    if janela:
        t0, t1 = janela
        sino = "+".join(f"pow(max(1-if(lt(VAR,{t}),({t}-VAR)/0.20,(VAR-{t})/0.30),0),2)"
                        for t in (t0, t1))
        ws = f"(W/(1+6.0*({sino.replace('VAR', T)})))"
        cauda.append(f"perspective=eval=frame:interpolation=cubic:"
                     f"x0='(W-{ws})/2':y0=0:x1='(W+{ws})/2':y1=0:"
                     f"x2='(W-{ws})/2':y2=H:x3='(W+{ws})/2':y3=H")
        for t in (t0, t1):
            for frac, sig in ((1.0, 12), (0.62, 28), (0.30, 46)):
                cauda.append(f"gblur=sigma={sig}:sigmaV=0:steps=2:"
                             f"enable='between(t,{t-0.20*frac:.3f},{t+0.30*frac:.3f})'")
        cauda.append(f"eq=eval=frame:brightness='0.30*({sino.replace('VAR','t')})'")
        # rgbashift so' aceita RGB: a conversao automatica yuv420p->gbrp cai no
        # bug de cauda SIMD do swscale (ver acima) e apaga as colunas 1072-1079
        # no video INTEIRO, mesmo com o `enable` (lote 72, 29/09). gbrap explicito, e volta.
        cauda.append(f"format=gbrap,rgbashift=rh=-4:bh=4:"
                     f"enable='between(t,{t1+0.33:.2f},{t1+0.51:.2f})',format=yuv420p")
    entra = total - LOTE.card_antes_de(v, FINAL_OPACO)
    dur_total = entra + FINAL_DUR if TEM_FINAL else total
    if TEM_FINAL:
        cauda.append(f"tpad=stop_duration={FINAL_DUR:.2f}:color=black")
    partes.append(f"[{atual}]" + ",".join(cauda) + "[vbase]")
    if TEM_FINAL:
        partes.append(f"[{idx_final}:v]scale=1080:1920,format=yuva420p,"
                      f"setpts=PTS-STARTPTS+{entra:.3f}/TB[fin]")
        partes.append("[vbase][fin]overlay=0:0:eof_action=pass[v]")
    else:
        # SEM card de finalizacao a peca terminava em CORTE SECO -- o card era
        # o que dava o fecho. Decisao dele em 26/08/2026, no lote 28 (Dra.
        # Fulano, primeiro lote sem finalizacao): *"como não temos
        # finalização, coloca o fim sempre com fade no final"*.
        # O fade e' de VIDEO e de AUDIO: so' escurecer a imagem deixa a musica
        # sendo decapitada no ultimo quadro, que e' o mesmo defeito com outra
        # cara. O audio e' fechado la' embaixo, junto com o loudnorm.
        partes.append(f"[vbase]fade=t=out:st={max(0.0, total - FADE_FIM):.3f}:"
                      f"d={FADE_FIM:.2f}:color=black[v]")

    # Denoise ANTES do loudnorm, e a ordem foi medida, nao escolhida: com
    # `loudnorm -> denoise` o v4 fecha em -16,0 LUFS, 1,2 abaixo dos outros
    # 7 do lote, porque o loudnorm normaliza contando o ruido que so' sai
    # depois. Com `denoise -> loudnorm` fica em -14,8, junto com o resto.
    # (Alem disso o loudnorm em passada unica levanta o chao de ruido nas
    # pausas antes de voce trata-lo.)
    av = []
    # PRIMEIRA coisa da cadeia: centrar a fala quando o microfone gravou num
    # canal so'. Antes do denoise e do loudnorm de proposito -- os dois
    # medem/tratam o sinal, e tratar um estereo desequilibrado e' tratar a
    # coisa errada. Motivo e medicao em `config.centrar_de`.
    centrar = config.centrar_de(LOTE.bruto_de(v))
    if centrar:
        av.append(centrar.rstrip(","))
    if LOTE.denoise.get(str(v)):
        av.append(LOTE.denoise[str(v)])
    av.append("loudnorm=I=-14:TP=-1.5:LRA=11")
    # Trim de pico, DEPOIS do loudnorm (senao o loudnorm o desfaz).
    # Caso real (v4 da Dra. Fulana, 03/08/2026): tirar o P&B tirou junto
    # o passa-banda de 700-2000 Hz do "radio velho", que era o que segurava a
    # janela mais alta do video. Sem ele o limitador passou a trabalhar o
    # tempo todo e o AAC estourou na saida -- true peak de -0,1 dBFS contra
    # -1,2 a -1,4 dos outros sete. O trim devolve a folga sem mexer no
    # limitador, que e' regua do padrao.
    trim = LOTE.ganho_fala_db.get(str(v))
    if trim:
        av.append(f"volume={float(trim):+.2f}dB")
    if pb:
        j = f"enable='between(t,{pb[0]},{pb[1]})'"
        # ganho do "radio velho". Era 1.8, calibrado numa janela de 1,6s;
        # com o P&B podendo chegar a 7s ele encontra transiente que antes
        # nao encontrava e o pico batia em -0,0 dB (v1). 1.55 mantem o
        # timbre -- que e o que ele aprovou -- e devolve o pico a -1 dB.
        av += [f"highpass=f=700:poles=2:{j}", f"highpass=f=700:poles=2:{j}",
               f"lowpass=f=2000:poles=2:{j}", f"lowpass=f=2000:poles=2:{j}",
               f"volume=1.55:{j}"]
    av.append(f"apad=whole_dur={dur_total:.3f}")
    partes.append("[ac]" + ",".join(av) + "[afala]")
    for k, a_k in enumerate(atrasos):
        partes.append(f"[{2 + k}:a]adelay={int(max(0,a_k)*1000)}:all=1[atar{k}]")
    if TEM_FINAL:
        partes.append(f"[{idx_final}:a]adelay={int(entra*1000)}:all=1[afin]")

    # Musica de fundo, ja remixada para a duracao exata e no nivel certo
    # (ver musica.py). Entra como 5a entrada e como 4a fonte da mixagem.
    mus_src, mus = escolher_musica(v), None
    info = {}
    # Lote COM abertura: a musica sai daqui e vai para a montagem. O operador
    # decidiu (14/08/2026) que ela comeca so depois da vinheta, e este passe
    # nao sabe em que instante isso e' -- a vinheta so entra depois. Mixar
    # aqui e tentar remendar la' nao funciona: mixagem nao se desfaz.
    if mus_src and getattr(LOTE, "vinheta", None):
        print(f"      musica adiada para a montagem (lote com vinheta) -- "
              f"entra quando o corpo comeca")
        mus_src = None
    if mus_src:
        mus = os.path.join(LOTE.trabalho, f"{v}_musica.wav")
        import musica as M
        # `musica_db` do lote.json sobrepoe o padrao NESTE video (dado de
        # lote, ver config). Nasceu no lote da Dra. Fulana, 12/08/2026.
        ganho = float(LOTE.musica_db.get(str(v), MUSICA_GANHO_DB))
        if ganho != MUSICA_GANHO_DB:
            print(f"      musica em {ganho:.0f} dB (padrao {MUSICA_GANHO_DB:.0f}) "
                  f"-- `musica_db` do lote.json")
        info = M.remixar(mus_src, dur_total, mus, ganho)
        # `musica_sobe`: ganho extra na musica SO' numa janela do corte, com
        # rampa de 0,15 s nas bordas -- [ini, fim, dB] por video. Mascara fundo
        # que esta' DEBAIXO da fala (v9 da Fulano, 17/09/2026: gente falando
        # ao fundo enquanto a Beltrana diz "Isso" baixinho; nao ha' como tirar
        # sem tirar a fala, entao a musica sobe ali e volta).
        janela = LOTE.musica_sobe.get(str(v))
        if janela:
            a, b, db = float(janela[0]), float(janela[1]), float(janela[2])
            g = 10 ** (db / 20)
            r = 0.15
            expr = (f"if(between(t,{a:.3f},{b:.3f}),"
                    f"1+({g:.3f}-1)*min(1,min((t-{a:.3f})/{r},({b:.3f}-t)/{r})),1)")
            partes.append(f"[{idx_musica}:a]volume=volume='{expr}':eval=frame[amus]")
            print(f"      musica sobe {db:+.0f} dB em {a:.2f}-{b:.2f}s (`musica_sobe`)")
        else:
            partes.append(f"[{idx_musica}:a]anull[amus]")
    # Whoosh do proprio asset de leak, nos instantes de `sfx_em` (ver config).
    # O 1o whoosh do asset vive em 0,10-0,90 s com pico em 0,40; o trim pega
    # so' ele e o adelay poe o pico no instante pedido. `asplit` porque um
    # rotulo de saida se consome uma vez (ver a nota do .wav derivando abaixo).
    sfx = [float(t) for t in (LOTE.sfx_em.get(str(v)) or [])]
    if sfx:
        partes.append(f"[1:a]asplit={len(sfx)}"
                      + "".join(f"[sx{k}]" for k in range(len(sfx))))
        for k, t in enumerate(sfx):
            partes.append(f"[sx{k}]atrim=0.10:0.90,asetpts=PTS-STARTPTS,"
                          f"volume={LOTE.sfx_db:.1f}dB,"
                          f"adelay={max(0, int((t - 0.30) * 1000))}:all=1[asfx{k}]")
        print(f"      sfx: whoosh em " + ", ".join(f"{t:.2f}s" for t in sfx)
              + f" ({LOTE.sfx_db:+.0f} dB)")
    entradas = (["[afala]"] + [f"[atar{k}]" for k in range(len(atrasos))]
                + [f"[asfx{k}]" for k in range(len(sfx))]
                + (["[afin]"] if TEM_FINAL else []) + (["[amus]"] if mus else []))
    # limit=0.89 (-1,0 dBFS) e level=disabled: com 0.95 e auto-nivel ligado
    # o limitador ELEVA o sinal ate o teto, e o v1 (P&B de 6s) saia com pico
    # de -0,3 dB. Quem fixava o teto era o limitador, nao o ganho do P&B.
    # O `afade` vai DEPOIS do alimiter, pelo mesmo motivo que o trim de pico:
    # o limitador eleva o sinal ate o teto e desfaria a rampa se viesse por
    # ultimo. Casado com o fade de video la' de cima -- sem este, a musica era
    # decapitada no ultimo quadro enquanto a imagem escurecia.
    fade_a = (f",afade=t=out:st={max(0.0, dur_total - FADE_FIM):.3f}:"
              f"d={FADE_FIM:.2f}" if not TEM_FINAL else "")
    partes.append("".join(entradas) +
                  f"amix=inputs={len(entradas)}:duration=first:"
                  f"normalize=0,alimiter=limit=0.89:level=disabled{fade_a}[a]")

    # NAO tente escrever aqui uma 2a mixagem "sem musica" reusando [afala],
    # [atar] e [afin]. Eu fiz isso em 14/08/2026 e o resultado foi um .wav
    # com o TAMANHO EXATO e o conteudo DERIVANDO -- +484 ms aos 2 s, +1234 ms
    # aos 18 s, +2168 ms aos 38 s. Num grafo de ffmpeg um rotulo de saida se
    # consome UMA vez; para usa-lo duas e' preciso `asplit` explicito. O
    # comando saiu com exit 0 e sem aviso, e o gancho montado com aquele
    # arquivo mostrava uma frase na tela enquanto tocava outra.
    #
    # Quando o lote tem `vinheta`, a musica NAO entra aqui -- ela e' mixada
    # na montagem (`montar_abertura.py`), que e' onde se sabe em que instante
    # o corpo comeca. Ver o bloco de `mus_src` acima.

    sufixo = ("_BASE" if base else
              ("" if legenda_nossa else "_LEGENDA-MEDICO")) + SUFIXO_SAIDA
    saida = os.path.join(LOTE.saida, f"{v}_PRONTO{sufixo}.mp4")
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", src, "-i", LEAK]
    for t in tarjas:
        cmd += ["-i", t]
    if TEM_FINAL:
        cmd += ["-i", LOTE.finalizacao]
    if mus:
        cmd += ["-i", mus]
    # b-roll: entram por ultimo, e so' agora da' para saber o indice de cada
    # um (depende de tarja/card/musica existirem). Troca o marcador @BRk@.
    grafo = ";".join(partes)
    n_entradas = 2 + len(tarjas) + TEM_FINAL + (1 if mus else 0)
    for k, b in enumerate(brolls):
        arq = b["arquivo"]
        if not os.path.isabs(arq):
            arq = os.path.join(config.BROLL, LOTE.cliente, arq)
        if not os.path.exists(arq):
            sys.exit(f"v{v} ABORTADO: b-roll nao encontrado -> {arq}")
        grafo = grafo.replace(f"@BR{k}@", str(n_entradas + k))
        cmd += ["-i", arq]
    cmd += ["-t", f"{dur_total:.3f}", "-filter_complex", grafo,
           "-map", "[v]", "-map", "[a]", "-shortest"] + (
           # A base e' ARQUIVO DE TRABALHO, nao entrega: o que importa nela e'
           # sair RAPIDO, porque ela existe so' para receber a legenda depois.
           #
           # `preset veryfast` em vez de `medium`: o preset e' o esforco que o
           # compressor faz para deixar o arquivo PEQUENO, nao a qualidade --
           # quem manda na qualidade e' o `crf`. Baixando o preset o arquivo
           # cresce e o tempo despenca, e tamanho de arquivo temporario nao e'
           # problema.
           #
           # Custo medido do erro anterior (25/08/2026): com `medium -crf 14`
           # a base do v1 levou 43 min contra os 20 min do render NORMAL dele
           # -- o dobro, para gerar um intermediario. O lote inteiro daria ~7 h.
           # O operador cortou isso na hora: *"a ideia e fazer os videos leves
           # ... esses videos vao pra uma tela de celular, faz o mais rapido
           # que der"*. Estava certo: a peca e' Reels, vista em celular.
           ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18",
            "-profile:v", "high", "-pix_fmt", "yuv420p",
            "-threads", str(config.threads_encode())]
           if base else config.encoder_video()) + [
           # O encoder sai de `config.encoder_video()`, que TESTA ABRIR o
           # h264_nvenc e cai no libx264 se ele nao abrir. Ate 10/08/2026 o
           # nvenc era inutilizavel aqui (driver 595.97 contra os 610.00 que
           # o build pede); em 14/08 o driver estava em 610.88 e passou.
           # Quando cai em CPU, o teto de threads vem junto: sem ele o
           # libx264 toma os 12 threads do 5600G e o operador nao consegue
           # usar o proprio PC enquanto o lote roda -- foi ele quem apontou.
           "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
           "-movflags", "+faststart", "-y", saida]
    r = subprocess.run(cmd, cwd=LOTE.trabalho,
                       capture_output=True, text=True,
                       creationflags=config.PRIORIDADE_BAIXA)
    # cobertura de disfarce: todo corte tem degrau de zoom OU animacao em
    # cima. So o congelamento da frase e excecao -- la o texto disfarca.
    nivel = {round(t0, 3): (z0, z1) for t0, t1, z0, z1 in movs}
    fim_de = {round(t1, 3): z1 for t0, t1, z0, z1 in movs}
    secos = []
    for c in cortes[1:-1]:
        c = round(c, 3)
        salto = abs(nivel.get(c, (0, 0))[0] - fim_de.get(c, nivel.get(c, (0, 0))[0]))
        anim = any(abs(c - lk[0]) < 0.25 for lk in leaks) or \
            (janela and janela[0] - FOLGA_TEXTO - .05 <= c <= janela[1] + FOLGA_TEXTO + .05) or \
            (pb and abs(c - pb[0]) < 0.25) or (pb and abs(c - pb[1]) < 0.25)
        if salto < 0.004 and not anim:
            secos.append(c)
    cob = 100 * (1 - len(secos) / max(len(cortes) - 2, 1))

    # taxa local de zoom: e a metrica que separou "frenetico" (v9, p90 de
    # 6,64 pt/s) de "muito devagar" (v6, 1,20). O video 7 aprovado tem
    # deriva media de 0,25 pt/s -- quase todo o movimento esta nos degraus.
    taxas = [abs(z1 - z0) / max(t1 - t0, 0.01) * 100 for t0, t1, z0, z1 in movs
             if t1 - t0 > 0.2]
    taxas.sort()
    p90 = taxas[int(len(taxas) * 0.9)] if taxas else 0.0
    saltos = [abs(movs[k + 1][2] - movs[k][3]) * 100 for k in range(len(movs) - 1)]
    saltos_reais = [s for s in saltos if s > 0.4]

    if saltos_reais:
        s = sorted(saltos_reais)
        deg = f"{len(s)} degraus, med {s[len(s) // 2]:.1f}pt"
    else:
        deg = "sem degrau"

    # DUAS variaveis de proposito. O `[:26]` existe para a tabela do console
    # caber na linha, e ate 25/08/2026 a MESMA variavel ia para o
    # `producao.json` -- entao o relatorio gravava `DAR UM CONTORNO|FACIAL BON`
    # e eu abri um quadro do render achando que a legenda estava truncada. Na
    # tela estava `DAR UM CONTORNO / FACIAL BONITO.`, inteira. Relatorio que
    # trunca em silencio produz caca ao fantasma: o JSON leva o texto COMPLETO.
    txt_completo = "|".join(linhas) if linhas else None
    txt = txt_completo[:26] if txt_completo else "-"
    print(f"v{v}: {len(segs)}c {total:5.2f}s+card={dur_total:5.2f}s | "
          f"{len(leaks)} leaks | {len(punches)} punch | disfarce {cob:5.1f}%"
          f"{' secos=' + str(secos) if secos else ''}")
    if info:
        print(f"      musica {os.path.basename(mus_src)[:34]} | "
              f"{info['bpm']}bpm, frase {info['frase_s']}s | "
              f"{info['dur_original']}s (util {info['fim_util']}s) -> "
              f"{dur_total:.2f}s, {info['emendas']} emenda | "
              f"{info['media_origem']}dB {info['ganho_db']:+.0f}dB = "
              f"{info['media_final']}dB")
    print(f"      zoom {min(z for _, _, z, _ in movs):.3f}-"
          f"{max(z for _, _, _, z in movs):.3f} | {deg} | "
          f"deriva p90 {p90:.2f}pt/s | texto {janela or '-'} {txt} | "
          f"P&B {pb or '-'}"
          f"{' ' + format(pb[1] - pb[0], '.2f') + 's' if pb else ''} | "
          f"{'OK' if r.returncode == 0 else 'ERRO ' + r.stderr[:180]}")

    # REGRA 1b do CLAUDE.md, agora em codigo. O codigo de saida do ffmpeg NAO
    # basta: na Dra. Fulana (11/08/2026) a fase escreveu 4 arquivos de
    # ZERO BYTE e imprimiu "FASE 2 CONCLUIDA". O portao aqui mede o ARTEFATO --
    # ele existe, e tem tamanho plausivel para a duracao?
    #
    # 20 KB/s e' um piso absurdamente baixo para 1080x1920 em crf 19 (o real
    # fica em centenas de KB/s). Ele nao existe para julgar qualidade de
    # encode: existe para separar "arquivo" de "vazio ou truncado", sem risco
    # de reprovar render legitimo.
    tam = os.path.getsize(saida) if os.path.exists(saida) else 0
    piso = max(100_000, int(dur_total * 20_000))
    artefato_ok = tam >= piso
    if r.returncode == 0 and not artefato_ok:
        print(f"      ARTEFATO INVALIDO: {tam:,} bytes para {dur_total:.2f}s "
              f"(minimo {piso:,}) -- {os.path.basename(saida)}")

    # O bloco abaixo e' REGISTRO, e roda depois de um encode que levou
    # minutos. Se ele estourar, o render bom vai junto -- e o operador perde o
    # trabalho por causa da anotacao, nao do video. Mesma politica do
    # `relatorio.gravar`: falhou, avisa e segue. O portao do artefato acima
    # NAO esta aqui dentro de proposito: aquele e' decisao, este e' anotacao.
    try:
        _registrar_medidas(v, sufixo, saida, tam, dur_total, segs, leaks,
                           punches, cob, secos, p90, saltos_reais, pb, txt,
                           linhas, r, artefato_ok)
    except Exception as e:                                   # noqa: BLE001
        print(f"      (medidas de v{v} nao entraram no relatorio: {e})")
    return r.returncode == 0 and artefato_ok


def _registrar_medidas(v, sufixo, saida, tam, dur_total, segs, leaks, punches,
                       cob, secos, p90, saltos_reais, pb, txt, linhas, r,
                       artefato_ok):
    med_degrau = (sorted(saltos_reais)[len(saltos_reais) // 2]
                  if saltos_reais else None)
    MEDIDAS.append({
        "video": v,
        "versao": sufixo or "principal",
        "arquivo": os.path.basename(saida),
        "bytes": tam,
        "duracao": round(dur_total, 2),
        "cortes": len(segs),
        "leaks": len(leaks),
        "punches": len(punches),
        "disfarce_pct": round(cob, 1),
        "secos": secos,
        "deriva_p90": round(p90, 2),
        "degrau_mediana": round(med_degrau, 1) if med_degrau else None,
        "pb_s": round(pb[1] - pb[0], 2) if pb else None,
        # `txt_completo` e local do CHAMADOR -- referencia-lo daqui era
        # NameError, e o `except` de cima engolia com "(medidas de vN nao
        # entraram no relatorio)". Exit 0, render certo, producao.json SEM
        # a peca. `linhas` ja chega por parametro; a conta e a mesma.
        "texto": "|".join(linhas) if linhas else None,
        "render_ok": r.returncode == 0,
        "artefato_ok": artefato_ok,
        "erro": r.stderr[:300] if r.returncode != 0 else None,
    })


if __name__ == "__main__":
    import shutil
    LOTE.preparar_pastas()
    dst = os.path.join(LOTE.trabalho, "fonts")
    # Copiar so' quando a pasta NAO existe deixava lote antigo sem fonte nova:
    # o libass nao acha, cai num substituto e o render sai com outra tipografia
    # SEM erro nenhum no log -- mesma classe da fonte variavel que renderiza
    # Regular calada. Agora completa o que falta, arquivo a arquivo.
    os.makedirs(dst, exist_ok=True)
    for _f in os.listdir(FONTES):
        if _f.lower().endswith((".ttf", ".otf")) and \
           not os.path.exists(os.path.join(dst, _f)):
            shutil.copy2(os.path.join(FONTES, _f), os.path.join(dst, _f))
    # `duas_versoes` no lote.json: alem da versao com a nossa legenda, sai uma
    # com a legenda que o proprio cliente queimou no bruto. Mesma edicao nas
    # duas -- so muda de quem e' a legenda.
    # So' numero de video conta como alvo. O `config.carregar()` ja' tira
    # `--lote <nome>` do argv, mas qualquer OUTRA flag sobrava e virava
    # "video": com `--sem-broll` o lote rodava inteiro e certo, e so' depois
    # morria com KeyError: '--sem-broll'. Filtrar por digito e' o que
    # sobrevive a flag nova.
    alvos = [a for a in sys.argv[1:] if a.isdigit()]
    # `produzir` ja' devolvia False quando o ffmpeg falhava, e ninguem lia.
    # Custo real (Dra. Fulana pt1, 11/08/2026): os 4 renders morreram
    # no mesmo erro de filtergraph, a fase escreveu 4 arquivos de ZERO BYTE,
    # imprimiu "FASE 2 CONCLUIDA" e saiu com codigo 0. A regra 1 do CLAUDE.md
    # ("verifique o codigo de saida, sempre") nao protege deste caso, porque
    # quem mente e' o script, nao o `| tail` -- so' peguei olhando a pasta.
    falhas = []
    SO_BASE = "--base" in sys.argv
    for v in (alvos or list(FAIXAS)):
        if SO_BASE:
            if not produzir(v, base=True):
                falhas.append(f"{v} (base)")
            continue
        if not produzir(v):
            falhas.append(str(v))
        if LOTE.duas_versoes:
            if not produzir(v, legenda_nossa=False):
                falhas.append(f"{v} (legenda do medico)")
    # MESCLAR quando a fase roda num subconjunto (`... 2`): antes, o
    # producao.json era reescrito so' com as pecas desta rodada, e as outras
    # SUMIAM do relatorio. O semaforo, sem medida de producao para elas,
    # deixava de ver o amarelo que tinha acabado de mostrar -- lote 62 (Dra.
    # Fulano, 21/09/2026): V1 estava AMARELO (deriva_p90 2,83); re-renderizei
    # so' o V2 e o V1 voltou VERDE sem ninguem ter tocado nele. Mesma regra
    # que o lote_verificar ja' segue: substitui a peca desta rodada, preserva
    # o resto.
    pecas = list(MEDIDAS)
    if alvos:
        feitas = {(str(p["video"]), p.get("versao")) for p in pecas}
        antigo = relatorio.ler(LOTE, "producao") or {}
        pecas = [p for p in antigo.get("pecas", [])
                 if (str(p["video"]), p.get("versao")) not in feitas
                 and str(p["video"]) not in alvos] + pecas
        falhas = [f for f in antigo.get("falhas", [])
                  if f.split(" ")[0] not in alvos] + falhas
    relatorio.gravar(LOTE, "producao", {"pecas": pecas,
                                        "falhas": falhas})
    if falhas:
        print(f"FASE 2 FALHOU em: {', '.join(falhas)}")
        sys.exit(1)
    print("FASE 2 CONCLUIDA")
