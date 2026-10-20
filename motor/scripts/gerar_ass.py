#!/usr/bin/env python3
"""Legenda .ass estilo TikTok, uma linha sempre, com pop de entrada.

O bug da versao anterior: os grupos tinham largura variavel, alguns
quebravam em duas linhas e o bloco "subia e descia". Aqui a largura de
cada grupo e medida na fonte real (Pillow) e o grupo so fecha enquanto
couber numa linha. Posicao fixa por \\pos + \\an5, entao nada se move.

Uso: python gerar_ass.py <palavras.json> <referencia.srt> <saida.ass>
"""
import json, os, re, subprocess, sys
from PIL import ImageFont

tokens_f, srt_f, out_f = sys.argv[1], sys.argv[2], sys.argv[3]

FONTE_TTF  = "fonts/Anton-Regular.ttf"
FONTE      = "Anton"
CORPO      = 128
LARG_MAX   = 860           # px uteis (1080 - margens - contorno)
MAX_PAL    = 3             # teto de palavras por grupo
COR_BASE   = "&H00FFFFFF"
COR_ATIVA  = "&H0000D4FF"  # amarelo (ASS usa BGR)
ALFA_BASE  = "&H00&"       # opaca: o realce padrao e' por COR, nao por brilho
CONTORNO   = 9

# argv[7] opcional: JSON de ESTILO da legenda (`estilo` no lote.json). Existe
# porque cor e fonte sao do CLIENTE, nao do padrao: a Dra. Fulana pediu
# a legenda inteira em #F8E2C2 e Red Hat Display Bold (14/08/2026), e o resto
# do acervo continua em Anton com realce amarelo.
#
# ARMADILHA que isto resolve: com a legenda TODA na mesma cor, o realce da
# palavra falada some -- ele sempre foi diferenca de COR contra o branco. Aqui
# o realce vira diferenca de BRILHO: a palavra falada opaca, as outras do grupo
# em `opacidade_base`. Sem isso a legenda fica bonita e ilegivel como karaoke.
def _ass_cor(hexa):
    """'#F8E2C2' -> '&H00C2E2F8'. O ASS guarda BGR, nao RGB."""
    h = hexa.lstrip("#")
    return f"&H00{h[4:6]}{h[2:4]}{h[0:2]}".upper()


NEGRITO    = 0
ITALICO    = 0
ESPACAMENTO = 0             # px extras por caractere (`Spacing` do ASS)
COR_CONTORNO = "&H00000000"
SOMBRA_BLUR = 0             # `\blur` no contorno: 0 = contorno duro de sempre
REALCE     = True           # False = cor unica, sem destaque de palavra
POS_X, POS_Y = 540, 1320
CAIXA_ALTA = True
POP_MS     = 120           # duracao do pop de entrada do grupo
POP_ESCALA = 88            # % inicial do pop

# ORDEM IMPORTA, e ela ja mordeu: este bloco tem de vir DEPOIS de todos os
# valores que ele sobrescreve. Na primeira versao ele estava acima de
# `CAIXA_ALTA` e `POS_Y`, as duas linhas seguintes redefiniam os dois, e a
# legenda saiu em CAIXA ALTA na posicao velha -- com `caixa_alta: false` e
# `pos_y` escritos no lote.json, exit 0 e nenhum aviso. So' apareceu porque
# eu abri o .ass gerado em vez de confiar no codigo de saida.
if len(sys.argv) > 7 and sys.argv[7]:
    _e = json.loads(open(sys.argv[7], encoding="utf-8").read())
    if _e.get("fonte_ttf"):
        FONTE_TTF = _e["fonte_ttf"]
    if _e.get("fonte"):
        FONTE = _e["fonte"]
    if _e.get("corpo"):
        CORPO = int(_e["corpo"])
    if _e.get("max_palavras"):
        MAX_PAL = int(_e["max_palavras"])
    if _e.get("largura_max"):
        LARG_MAX = int(_e["largura_max"])
    if _e.get("caixa_alta") is not None:
        CAIXA_ALTA = bool(_e["caixa_alta"])
    if _e.get("negrito"):
        NEGRITO = -1
    if _e.get("italico"):
        ITALICO = -1
    if _e.get("espacamento") is not None:
        ESPACAMENTO = int(_e["espacamento"])
    if _e.get("pos_y"):
        POS_Y = int(_e["pos_y"])
    if _e.get("pos_x"):
        POS_X = int(_e["pos_x"])
    if _e.get("contorno") is not None:
        CONTORNO = int(_e["contorno"])
    if _e.get("sombra_blur"):
        SOMBRA_BLUR = float(_e["sombra_blur"])
    if _e.get("sombra_opacidade") is not None:
        _a = int(round((1 - float(_e["sombra_opacidade"])) * 255))
        COR_CONTORNO = f"&H{_a:02X}000000"
    if _e.get("cor_legenda"):
        COR_ATIVA = _ass_cor(_e["cor_legenda"])
        COR_BASE = COR_ATIVA
        # `opacidade_base` 1,0 = a legenda inteira na mesma cor e no mesmo
        # brilho, SEM destacar a palavra falada. Nao e' caso de borda: e' o
        # estilo que o operador usa nas pecas dele da Dra. Fulana,
        # medido em 194 eventos de 6 videos aprovados — cor unica, zero
        # realce. Com realce ligado a peca sairia com um karaoke que a
        # referencia nao tem.
        op = float(_e.get("opacidade_base", 0.60))
        REALCE = op < 0.999
        ALFA_BASE = f"&H{int(round((1 - op) * 255)):02X}&"

# argv[6] opcional: Y da legenda, em px de 1920. Existe porque o
# enquadramento muda de video para video: no v3 da Dra. Fulana ela esta
# mais perto da camera e o Y padrao (1320) caia em cima do QUEIXO dela
# ("pega algumas vezes o rosto dela", operador, 03/08/2026). E' dado de
# lote, nao regua -- `legenda_y` no lote.json.
#
# Vem por ULTIMO de proposito: e' override POR VIDEO e tem de vencer o
# `pos_y` do `estilo`, que vale para o lote inteiro.
if len(sys.argv) > 6 and sys.argv[6]:
    POS_Y = int(sys.argv[6])

# argv[5] opcional: JSON com a faixa da legenda queimada do cliente e a curva
# de zoom. Quando o bruto ja vem com legenda do cliente, a tarja que a cobre e
# desenhada ANTES do zoom -- para ter so' a altura dela, e nao a uniao das
# posicoes que ela ocupa em todos os zooms. Em troca, a tarja sobe e desce, e
# a nossa legenda precisa segui-la.
#
# Um Y por EVENTO nao basta: um degrau de zoom caindo no meio de uma palavra
# desloca a tarja em ate 58 px e a legenda sai do centro (reprovado em
# 31/07/2026). Por isso cada evento e' PARTIDO nos instantes em que o zoom
# muda, e cada pedaco ganha o seu Y. O reposicionamento cai no corte, onde a
# imagem muda de qualquer jeito.
TARJA, ZOOM = None, []
if len(sys.argv) > 5 and sys.argv[5]:
    _d = json.loads(open(sys.argv[5], encoding="utf-8").read())
    TARJA, ZOOM = _d["faixa"], _d["zoom"]


def zoom_em(t):
    """Zoom vigente em `t` (segundos)."""
    for t0, t1, z0, z1 in ZOOM:
        if t < t1:
            p = 0.0 if t1 <= t0 else min(max((t - t0) / (t1 - t0), 0.0), 1.0)
            return z0 + (z1 - z0) * p
    return ZOOM[-1][3] if ZOOM else 1.0


def y_em(t_ms):
    """Centro da tarja em `t`, em px de 1920 — é onde a legenda tem de estar."""
    if not TARJA:
        return POS_Y
    c = (TARJA[0] + TARJA[1]) / 2
    return int(1920 * (0.5 + (c - 0.5) * zoom_em(t_ms / 1000.0)))


def pedacos(ini, fim):
    """Divide [ini, fim] nos instantes em que o zoom muda. Em ms."""
    if not ZOOM:
        return [(ini, fim)]
    fulano = sorted({int(t * 1000) for m in ZOOM for t in (m[0], m[1])
                     if ini < int(t * 1000) < fim})
    cortes = [ini] + fulano + [fim]
    return [(a, b) for a, b in zip(cortes, cortes[1:]) if b > a]

CORRECOES = {}
if len(sys.argv) > 4 and sys.argv[4]:
    for par in sys.argv[4].split(","):
        if "=" in par:
            k, v2 = par.split("=", 1)
            CORRECOES[k.strip().lower()] = v2.strip()

fnt = ImageFont.truetype(FONTE_TTF, CORPO)


def larg(txt):
    return fnt.getbbox(txt)[2] - fnt.getbbox(txt)[0]


# --- tokens
toks = [json.loads(l) for l in open(tokens_f, encoding="utf-8") if l.strip()]

# --- palavras de referencia
ref = []
for linha in open(srt_f, encoding="utf-8"):
    linha = linha.strip()
    if linha and not linha.isdigit() and "-->" not in linha:
        ref.extend(linha.split())

def _so_letras(s):
    return re.sub(r"[^\wÀ-ÿ]", "", s).lower()


# --- alinha tokens -> palavras
palavras, i = [], 0
for alvo in ref:
    acc, ini, fim = "", None, None
    while i < len(toks):
        t = toks[i]
        # O inicio da palavra e' o primeiro token que CONTRIBUI LETRA, nunca
        # o primeiro token consumido.
        #
        # ARMADILHA CARA (Dra. Fulana, 03/08/2026): o whisper emite
        # ".", ",", "?" como tokens proprios. O token de pontuacao que fecha
        # uma frase SOBRA no casamento por letras e e' engolido pela
        # primeira palavra da frase SEGUINTE -- que assim herdava o instante
        # em que a frase anterior terminou. A palavra acendia em amarelo ate
        # 900 ms ANTES de ser falada, e sempre na entrada de um grupo novo,
        # que e' o momento mais visivel da legenda.
        #
        # Media do estrago neste lote: 143 palavras adiantadas nos 8 videos,
        # mediana 190 ms, maximo 900 ms -- 1 em cada 3 grupos entrava cedo.
        # O operador descreveu como "fica certinho e do NADA ela avanca".
        # O erro residual do proprio whisper e' menor (mediana 168 ms, com
        # sinal aleatorio) e foi tolerado no video 7 aprovado; este aqui era
        # sempre no mesmo sentido, o que o torna muito mais visivel.
        if ini is None and _so_letras(t["text"]):
            ini = t["start"]
        acc += t["text"]
        fim = t["end"]
        i += 1
        # Compara so as LETRAS. Antes comparava o texto cru, e isso quebrava
        # quando a pontuacao do .srt e a do fluxo de tokens divergem -- que
        # e exatamente o caso depois de restaurar pontuacao a partir do
        # bruto: o .srt passa a ter "saiu?" e o token continua "saiu".
        if _so_letras(acc) == _so_letras(alvo):
            break
        if len(_so_letras(acc)) > len(_so_letras(alvo)) + 2:
            break
    palavras.append({"txt": alvo, "ini": ini, "fim": fim,
                     "casou": _so_letras(acc) == _so_letras(alvo)})

if any(p["ini"] is None for p in palavras):
    sys.exit("ERRO: alinhamento falhou")

# O alinhamento tem de FALHAR ALTO. O indice de token e' global e nao
# ressincroniza por frase: se o SRT ganhar ou perder uma palavra em relacao
# aos tokens (o whisper alucina palavra e muda grafia de termo clinico a
# cada passada -- §K2 e §K11), tudo depois disso desliza. Simulado sobre o
# v8 real, uma unica palavra alucinada no SRT desloca 74 das 147 palavras,
# com desvio MEDIANO de 12,3 s e maximo de 26,4 s. Hoje isso passava calado.
# A re-ancoragem no onset de fala NAO mora aqui: ela roda na fase 1
# (scripts/retimar_legenda.py), sobre os proprios tokens. Assim a
# frase em destaque, o punch e as legendas exportadas usam os MESMOS
# tempos da legenda -- consertar so' aqui deixaria o texto grande no
# tempo velho.
_ruins = [p["txt"] for p in palavras if not p["casou"]]
if _ruins:
    sys.exit(f"ERRO: alinhamento dessincronizou em {len(_ruins)} palavra(s): "
             f"{_ruins[:8]} -- os tokens nao fecham com o texto do SRT. "
             f"Reconfira `correcoes`/`correcoes_sequencia` no lote.json "
             f"contra o _corte.srt (a grafia do whisper muda a cada passada).")

# Correcoes de revisao, aplicadas DEPOIS do alinhamento (antes dessincroniza).
# Formatos aceitos:
#   errado=certo          troca a palavra, PRESERVANDO a pontuacao dela
#   errado=certo?         valor com pontuacao troca o TOKEN inteiro
#   errado=certo~         "~" = termina aqui, SEM pontuacao (unico jeito
#                         de REMOVER um sinal)
#   erro>proxima=certo    so troca se a palavra SEGUINTE for essa
#   erro>proxima=         REMOVE a palavra (caso "A gente" -> "Agende")
def _base(t):
    return re.sub(r"[^\wÀ-ÿ]", "", t).lower()


fora = []
for idx, p in enumerate(palavras):
    b = _base(p["txt"])
    prox = _base(palavras[idx + 1]["txt"]) if idx + 1 < len(palavras) else ""
    novo = CORRECOES.get(f"{b}>{prox}", CORRECOES.get(b))
    if novo is None:
        continue
    if novo == "":
        fora.append(idx)
    elif novo.endswith("~"):
        # "~" = a palavra termina aqui, SEM pontuacao. E o unico jeito de
        # REMOVER um sinal: valor sem pontuacao preserva o sufixo original,
        # e valor com pontuacao troca por outro sinal -- nenhum dos dois
        # apaga. Caso real: "Aqui a abordagem, olha o metabolismo", onde a
        # virgula separa sujeito de verbo.
        p["txt"] = novo[:-1]
    elif re.search(r"[^\wÀ-ÿ]", novo):
        # o valor traz pontuacao -> substitui o token inteiro.
        # E assim que se conserta interrogacao que o whisper fechou com
        # virgula ("saiu," -> "saiu?"): a PALAVRA nao muda, so o sinal.
        #
        # O teste era `_base(novo) != novo`, e `_base` faz DUAS coisas: tira
        # pontuacao E poe em minuscula. Entao qualquer valor com letra
        # MAIUSCULA caia aqui e substituia o token inteiro, apagando a
        # pontuacao original em silencio.
        #
        # Medido no lote da Dra. Fulana (12/08/2026): `termo=TERMO`
        # comeu a virgula de "o TECNOLOGIA, uma tecnologia" e `cidade=Cidade`
        # comeu o ponto final de "em cidade." -- os dois na tela E no .txt
        # que o analista usa para a legenda do post. Nenhuma verificacao
        # numerica ve isso; quem viu foi ler os .txt entregues.
        #
        # Correcao de CAIXA e' o caso mais comum que existe (nome proprio,
        # cidade, sigla), entao o defeito atinge quase todo lote que corrija
        # um nome no fim de frase. Agora o teste pergunta o que interessa:
        # o valor tem caractere que nao e' letra nem numero?
        p["txt"] = novo
    else:
        p["txt"] = novo + p["txt"][len(b):]
if fora:
    palavras = [p for i, p in enumerate(palavras) if i not in set(fora)]
    print(f"  {len(fora)} palavra(s) removida(s) na revisao")

if CAIXA_ALTA:
    for p in palavras:
        p["txt"] = p["txt"].upper()

# --- agrupa por LARGURA MEDIDA (nunca quebra linha)
grupos, atual = [], []
for p in palavras:
    teste = atual + [p]
    if atual and (larg(" ".join(q["txt"] for q in teste)) > LARG_MAX
                  or len(teste) > MAX_PAL):
        grupos.append(atual)
        atual = [p]
    else:
        atual = teste
    if re.search(r"[.?!,;:]$", p["txt"]):     # fecha na pontuacao
        grupos.append(atual)
        atual = []
if atual:
    grupos.append(atual)

larguras = [larg(" ".join(q["txt"] for q in g)) for g in grupos]
# palavra unica pode estourar sozinha (ex.: "DESPROPORCIONAL,").
# nesse caso o grupo encolhe so o necessario, em vez de baixar a fonte toda.
escalas = [min(100, int(100 * LARG_MAX / w)) for w in larguras]
apertados = sum(1 for e in escalas if e < 100)
print(f"{len(palavras)} palavras -> {len(grupos)} grupos | "
      f"largura max {max(larguras)}px (teto {LARG_MAX}) | "
      f"{apertados} grupo(s) reduzido(s) ate {min(escalas)}%")


def ts(ms):
    ms = max(0, int(ms))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h}:{m:02d}:{s:02d}.{ms//10:02d}"


cab = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, Italic, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Spacing, Encoding
Style: Legenda,{FONTE},{CORPO},{COR_BASE[:2]}{ALFA_BASE[2:4]}{COR_BASE[4:]},{COR_CONTORNO},&H80000000,{NEGRITO},{ITALICO},1,{CONTORNO},{0 if SOMBRA_BLUR else 4},5,40,40,40,{ESPACAMENTO},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

linhas = []
sobrepostos = []
for gi, g in enumerate(grupos):
    esc = escalas[gi]
    # o grupo nao pode invadir o proximo: duas legendas na mesma \pos
    # apareceriam empilhadas
    prox = grupos[gi + 1][0]["ini"] if gi + 1 < len(grupos) else None
    # ...mas o clamp abaixo so' roda `if prox > ini`. Quando o grupo comeca
    # NO MESMO instante do seguinte -- o que acontece com token de duracao
    # zero na fronteira de um trecho -- ele e' pulado e saem duas legendas
    # empilhadas. Aconteceu em 3 pontos do lote da Dra. Fulana
    # (11/08/2026) e chegou publicado: 'QUEM MARCA' por baixo de
    # 'UMA CONSULTA'. O `retimar_legenda.py` agora conserta a causa; este
    # aviso existe para o caso que escapar dele nao sair calado de novo.
    if prox is not None and prox <= g[0]["ini"]:
        sobrepostos.append((round(g[0]["ini"] / 1000, 2),
                            " ".join(q["txt"] for q in g)))
    for k, p in enumerate(g):
        ini = p["ini"]
        if k + 1 < len(g):
            fim = g[k + 1]["ini"]
        else:
            fim = p["fim"] + 220
            if prox is not None:
                fim = min(fim, prox)
        # Piso de 80 ms (~2,4 quadros a 30 fps). Antes era `continue`, e a
        # palavra simplesmente NAO era destacada: com token de duracao zero
        # (o whisper emite 2 a 10 por video) duas palavras ficavam com o
        # mesmo inicio e o evento da primeira era jogado fora em silencio.
        # No v8 o karaoke pulava de "E" direto para "UM", deixando "CHEGA"
        # sem destaque nenhum -- o operador le isso como "a legenda atrasou",
        # porque o amarelo fica preso na palavra errada.
        if fim <= ini:
            fim = ini + 80
            if prox is not None and prox > ini:
                fim = min(fim, prox)
            if fim <= ini:
                continue
        # pop so na primeira palavra do grupo: escala em torno do \pos,
        # entao nada reposiciona
        if k == 0:
            de = int(esc * POP_ESCALA / 100)
            pop = (f"\\fscx{de}\\fscy{de}"
                   f"\\t(0,{POP_MS},\\fscx{esc}\\fscy{esc})")
        else:
            pop = f"\\fscx{esc}\\fscy{esc}"
        partes = []
        for j, q in enumerate(g):
            # `\c` troca a COR e `\1a` a OPACIDADE -- as duas, sempre. Quando o
            # realce e' por brilho (legenda toda numa cor so), `\c` sozinho nao
            # muda nada e a palavra falada fica indistinguivel das vizinhas;
            # quando e' por cor, `\1a` repete o valor e nao atrapalha.
            partes.append(
                f"{{\\c{COR_ATIVA}\\1a&H00&}}{q['txt']}"
                f"{{\\c{COR_BASE}\\1a{ALFA_BASE}}}"
                if (REALCE and j == k) else q["txt"])
        texto = " ".join(partes)
        # um pedaco por trecho de zoom estavel, cada um no centro da tarja
        # naquele instante. O pop so' entra no PRIMEIRO pedaco -- repeti-lo
        # faria a palavra pulsar de novo no meio dela mesma.
        for n, (a, b) in enumerate(pedacos(ini, fim)):
            este = pop if n == 0 else f"\\fscx{esc}\\fscy{esc}"
            # `\blur` nao existe como campo de Style, so' inline. E' ele que
            # transforma o contorno duro no brilho escuro difuso que o
            # operador usa nas pecas da Dra. Fulana (medido: opacidade
            # ~0,62 a 3 px do glifo, some em 14-18 px, centrado — nao e' drop
            # shadow deslocada).
            desfoque = f"\\blur{SOMBRA_BLUR:g}" if SOMBRA_BLUR else ""
            linhas.append(
                f"Dialogue: 0,{ts(a)},{ts(b)},Legenda,,0,0,0,,"
                f"{{\\an5\\pos({POS_X},{y_em((a + b) // 2)}){desfoque}{este}}}"
                + texto)

open(out_f, "w", encoding="utf-8").write(cab + "\n".join(linhas) + "\n")
print(f"{len(linhas)} eventos -> {out_f}")
for t, txt in sobrepostos:
    print(f"      AVISO: legenda EMPILHADA em {t:.2f}s -- {txt!r} nasce no "
          f"mesmo instante do grupo seguinte e vai aparecer por baixo dele")
