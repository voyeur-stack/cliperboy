#!/usr/bin/env python3
"""Legenda gerada SOBRE O CORTE, sem mapeamento nenhum.

A versao anterior (`legenda.py`) transcrevia o BRUTO e mapeava os tempos
para a linha do corte. Dois erros moravam nisso:

  1. os tempos vinham do filtro `whisper` do ffmpeg, que erra +-100 ms com
     sinal aleatorio -- e eram os MESMOS tempos que decidiam o corte;
  2. palavra que caia dentro de um trecho removido era grudada na borda do
     bloco anterior, o que adianta o evento.

Aqui a transcricao roda em cima do `{v}_corte.wav`, ou seja, ja' na linha
de tempo final. Nao ha o que mapear. Depois disso, as fronteiras sao
re-ancoradas no onset de fala pelo `retimar_legenda.py` do proprio projeto
-- peca que ja existia e que eu nao tinha usado.

Estilo (medido contra a referencia de 24/07, ver 03-armadilhas.md L5):
Lucida Console 50 px, branca, contorno preto de 3 px, nucleo em
y 1435..1473, centrada em x 540, 1 a 3 palavras e <= 16 caracteres.

Dependencia de fonte: ao contrario da box grande (que abre o `.ttf` por
caminho, de `assets/fonts/`), a legenda nomeia **Lucida Console** dentro do
`.ass`, e quem resolve o nome e' o libass, a partir das fontes INSTALADAS
no sistema. Lucida Console (`C:\\Windows\\Fonts\\lucon.ttf`) vem com o
Windows, entao esta em qualquer maquina da equipe -- mas nao em Linux nem
em macOS, e ali o libass troca por uma substituta sem avisar. Se a legenda
sair com desenho diferente do aprovado, e' a primeira coisa a conferir.
"""
import json
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(os.path.dirname(AQUI))
sys.path.insert(0, os.path.join(RAIZ, "scripts"))
sys.path.insert(0, AQUI)
from lote import CORRECOES_LEGENDA, TRAB  # noqa: E402

CORPO = 50
MAX_CARACTERES = 16
MAX_PALAVRAS = 3
POS_Y = 1459
CONTORNO = 3

CABECALHO = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, \
OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, \
ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, \
MarginL, MarginR, MarginV, Encoding
Style: Legenda,Lucida Console,{corpo},&H00FFFFFF,&H00FFFFFF,&H00000000,\
&H00000000,0,0,0,0,100,100,0,0,1,{contorno},0,5,0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, \
Text
"""
# A linha `Format:` acima TEM de listar os 10 campos. Ja saiu daqui sem o
# `MarginV`, com 9, e o libass passou a ler o `Text` uma virgula antes --
# toda legenda do lote renderizou com uma virgula grudada na frente. O
# .ass fica correto; o defeito so' aparece no quadro. (03-armadilhas L1)


def palavras_do_corte(v):
    """[{txt, ini, fim}] em SEGUNDOS, ja na linha de tempo do corte."""
    d = json.load(open(os.path.join(TRAB,f"{v}_corte_fw.json"),
                       encoding="utf-8"))
    return [{"txt": w["txt"], "ini": w["ini"], "fim": w["fim"]}
            for s in d["segmentos"] for w in s["palavras"] if w["txt"]]


def reancorar(v, ps):
    """Re-ancora as fronteiras no onset de fala do `{v}_corte.wav`.

    O retimer do projeto trabalha em MILISSEGUNDOS e so' tem permissao
    sobre tempo -- ele aborta se qualquer texto mudar.
    """
    import retimar_legenda as R
    wav = os.path.join(TRAB,f"{v}_corte.wav")
    ms = [{"txt": p["txt"], "ini": p["ini"] * 1000, "fim": p["fim"] * 1000}
          for p in ps]
    # QUATRO valores desde que o `retimar_legenda.py` ganhou o tratamento de
    # palavra COLAPSADA na fronteira de trecho (token de duracao zero que
    # herda o instante do corte e faz duas legendas acenderem juntas). Este
    # modo foi escrito quando ele devolvia tres, e nunca mais rodou -- a
    # quebra so' apareceu no lote 33, em 01/09/2026, no primeiro uso.
    novo, movidas, npausas, colapsadas = R.retimar(wav, ms)
    return ([{"txt": p["txt"], "ini": p["ini"] / 1000, "fim": p["fim"] / 1000}
             for p in novo], movidas, npausas, colapsadas)


def grupos(ps):
    saida, atual = [], []
    for p in ps:
        cand = atual + [p]
        texto = " ".join(x["txt"] for x in cand)
        if atual and (len(texto) > MAX_CARACTERES or len(cand) > MAX_PALAVRAS):
            saida.append(atual)
            atual = [p]
        else:
            atual = cand
        if atual and atual[-1]["txt"].endswith((".", "?", "!")):
            saida.append(atual)
            atual = []
    if atual:
        saida.append(atual)
    return [(g[0]["ini"], g[-1]["fim"], " ".join(x["txt"] for x in g))
            for g in saida]


# 0,70 s, e nao 0,45: com 0,45 o evento 'Como que esse' do v2 ficava de
# fora por 60 ms (ele acendia 510 ms antes da fala) -- e e' exatamente a
# frase que o operador apontou na revisao. Limite que deixa passar o caso
# que motivou a regra esta calibrado errado.
SNAP_MAX = 0.70
GAP_MIN = 0.25      # so' evento que entra depois de uma pausa e' candidato
DUR_MIN = 0.18      # nenhum evento pode ficar mais curto que isso


# --- correcoes de revisao -------------------------------------------------
# O dicionario que ficava AQUI mudou-se para o `lote.json` em 01/09/2026
# (chave `correcoes_legenda`), com o porque de cada troca preservado no
# campo `porque`. Ele era indexado por numero de video e nao sabia de que
# lote era: no lote 33 os videos 3 e 4 herdavam as correcoes dos videos 3 e
# 4 do lote de 03/08, e o render abortava em "correcao nao casou".
#
# Cada item diz ONDE (tempo aproximado, na linha do corte), O QUE espera
# encontrar e o que por no lugar. Se o esperado nao estiver la', o script
# ABORTA -- correcao que nao casa e' correcao aplicada no lugar errado, e
# ela some sem avisar quando a transcricao muda (armadilha K11 do projeto).
#
# `para=None` (null no JSON) remove a palavra.


def costurar(ps):
    """Junta na palavra anterior o pedaco que comeca com hifen, e a
    pontuacao solta.

    O whisper devolve "follow" e "-up" como DUAS palavras. Agrupando com
    espaco entre elas, a tela mostrou **"follow -up"** -- em quatro dos seis
    videos, queimado. Nao aparece em conferencia numerica nenhuma: duracao,
    sync, nivel, box e alinhamento estavam todos certos.

    Costurar antes de agrupar resolve nos dois lugares de uma vez, porque
    tanto a legenda da tela quanto o `.txt` do analista saem do mesmo grupo.
    """
    out = []
    for p in ps:
        t = p["txt"]
        if out and (t.startswith("-") or all(
                c in ".,;:!?…" for c in t)):
            out[-1] = {"txt": out[-1]["txt"] + t,
                       "ini": out[-1]["ini"], "fim": max(out[-1]["fim"],
                                                         p["fim"])}
        else:
            out.append(dict(p))
    return out


def capitalizar_apos_pontuacao(ps):
    """Depois de . ? ou !, a proxima palavra abre com maiuscula.

    Existe porque o passo anterior cria o problema: toda vez que uma
    `correcao_legenda` FECHA uma frase que o whisper tinha deixado aberta,
    a palavra seguinte continua minuscula. No v13 do lote 33 foram seis
    perguntas seguidas -- pus os seis "?" e ganhei seis minusculas abrindo
    frase, que e' o mesmo defeito virado do avesso.

    Fazer isso a mao e' ping-pong: cada regra de pontuacao pede uma regra
    de caixa, e a de caixa nao casa mais quando o corte muda. Aqui e'
    deterministico e nao muda palavra nenhuma -- so' a primeira letra.
    """
    out = [dict(p) for p in ps]
    for i in range(1, len(out)):
        ant = out[i - 1]["txt"].rstrip()
        if ant and ant[-1] in ".?!":
            t = out[i]["txt"]
            j = 0
            while j < len(t) and not t[j].isalpha():
                j += 1          # pula aspas/parenteses que o modelo emite
            if j < len(t) and t[j].islower():
                out[i]["txt"] = t[:j] + t[j].upper() + t[j + 1:]
    return out


def aplicar_correcoes(v, ps):
    for c in CORRECOES_LEGENDA.get(v, []):
        cand = [i for i, p in enumerate(ps) if p["txt"] == c["de"]]
        if not cand:
            raise SystemExit(
                f"v{v}: correcao nao casou -- {c['de']!r} nao existe mais na "
                f"transcricao. Reveja antes de renderizar.")
        i = min(cand, key=lambda i: abs(ps[i]["ini"] - c["em"]))
        if abs(ps[i]["ini"] - c["em"]) > 1.5:
            raise SystemExit(
                f"v{v}: {c['de']!r} esta em {ps[i]['ini']:.2f}s, esperado "
                f"perto de {c['em']:.2f}s. A transcricao mudou de lugar.")
        if c["para"] is None:
            ps.pop(i)
        else:
            ps[i] = dict(ps[i], txt=c["para"])
    return ps


COBERTURA_MIN = 0.15   # fracao minima do evento que precisa ter fala embaixo
VIZINHANCA = 0.50      # ate' onde procurar fala antes de chamar de invencao


def tirar_alucinacao(ev, segs):
    """Descarta evento que nao tem fala NEM POR PERTO.

    O whisper alucina em silencio, e o silencio do fim do arquivo e' o lugar
    classico. No v3 ele inventou "Tchau, tchau." em 57,38 -- 60 ms de evento
    onde a ultima fala terminou em 56,60, 780 ms antes. Isso iria queimado
    na tela: texto que a pessoa nao disse, num anuncio pago. E' regra de
    compliance, e por isso a barreira mede AUDIO, nao lista de frases
    suspeitas -- "Tchau, tchau" e' plausivel demais para cair numa lista; o
    que denuncia e' nao haver som.

    A VIZINHANCA existe porque a primeira versao desta regra descartava
    legenda legitima. Ela exigia fala EMBAIXO do evento, e o v4 perdeu
    "voce que quer": as palavras sao ditas mesmo, por volta de 34,76-35,17,
    mas o alinhador as colocou 0,3 s adiante, em cima de um vale de energia.
    Evento mal posicionado e' outro problema -- e apagar texto real para
    resolver desalinhamento e' trocar um defeito por um pior.
    """
    out, tirados = [], []
    for a, b, txt in ev:
        cob = sum(max(0.0, min(b, sb) - max(a, sa)) for sa, sb in segs)
        perto = any(sa < b + VIZINHANCA and a - VIZINHANCA < sb
                    for sa, sb in segs)
        if b > a and cob / (b - a) < COBERTURA_MIN and not perto:
            tirados.append((a, b, txt))
        else:
            out.append((a, b, txt))
    return out, tirados


def ancorar_eventos(ev, segs):
    """Adia o evento ate' o onset da fala. So' PARA A FRENTE, nunca para tras.

    Por que no evento e nao na palavra: o `retimar_legenda.py` trabalha por
    palavra e tem uma trava que abandona o ajuste quando ele deixaria a
    palavra acesa por menos de 100 ms -- trava certa, porque piscada de
    20 ms e' pior que o erro que ela conserta. So' que o que o espectador ve
    e' o GRUPO na tela, e num grupo de palavras curtas ("Nao deu nem") a
    trava dispara e o grupo inteiro entra adiantado. No v6 isso deu 415 ms
    de adiantamento, que o operador viu.

    E por que so' para a frente: o detector de fala acende em respiracao e
    ruido de boca. No v5 ele marca inicio de fala 490 ms antes da palavra
    "347" -- puxar o evento para tras ali poria a legenda no ar antes de
    existir palavra. Adiar tem risco baixo (a legenda entra junto com a
    voz); adiantar tem risco alto (entra antes dela).
    """
    out, n = [], 0
    for i, (a, b, txt) in enumerate(ev):
        ant = out[-1][1] if out else 0.0
        # se a fala JA esta no ar quando o evento acende, nao ha o que
        # ajustar -- adiar aqui atrasaria uma legenda que ja esta certa
        dentro = any(sa <= a <= sb for sa, sb in segs)
        if not dentro and a - ant >= GAP_MIN:
            perto = [s for s, _ in segs if a < s <= a + SNAP_MAX]
            if perto and b - min(perto) >= DUR_MIN:
                a = min(perto)
                n += 1
        out.append((a, b, txt))
    return out, n


def tc(s):
    s = max(0.0, s)
    return f"{int(s // 3600)}:{int(s % 3600 // 60):02d}:{s % 60:05.2f}"


def escrever(v, destino):
    import retimar_legenda as R
    ps = capitalizar_apos_pontuacao(
        aplicar_correcoes(v, costurar(palavras_do_corte(v))))
    ps, movidas, npausas, colapsadas = reancorar(v, ps)
    segs = [(a / 1000, b / 1000) for a, b in R.segmentos_de_fala(
        os.path.join(TRAB,f"{v}_corte.wav"))]
    ev, tirados = tirar_alucinacao(
        [g for g in grupos(ps) if g[1] > g[0]], segs)
    for a, b, txt in tirados:
        print(f"    ALUCINACAO descartada: [{a:.2f},{b:.2f}] {txt!r} "
              f"-- sem fala embaixo")
    ev, ancorados = ancorar_eventos(ev, segs)

    linhas = [f"Dialogue: 0,{tc(a)},{tc(b)},Legenda,,0,0,0,,"
              f"{{\\pos(540,{POS_Y})}}{txt}" for a, b, txt in ev]
    with open(destino, "w", encoding="utf-8") as f:
        f.write(CABECALHO.format(corpo=CORPO, contorno=CONTORNO))
        f.write("\n".join(linhas) + "\n")
    return len(ev), movidas, npausas, ancorados
