#!/usr/bin/env python3
"""Escreve o .srt e o .txt SO' com o audio -- sem OCR da tela.

DECISAO DO OPERADOR, 12/08/2026: *"tira isso, confia no whisper e fe"*.
O caminho padrao deste modo cruza a tela (OCR) com o audio, porque em peca
publicada o `.srt` tem de bater com o que esta QUEIMADO. Aqui o OCR foi
dispensado a pedido dele, com o custo declarado: o que o whisper ouviu errado
sai queimado no arquivo, e nao ha segunda fonte para pegar.

O tempo vem do `word_timestamps` (fronteira de palavra de verdade), nao do
inicio/fim do segmento. O corte de evento e' por FRASE -- e' a decisao de
06/08/2026 para peca publicada -- com teto de duracao e de caracteres para
nao virar bloco gigante na tela do analista.

Saida: UTF-8 com BOM e CRLF, que e' o que nao quebra acento no player nem na
leitura pelo Claude dos analistas.
"""
import json
import os
import re
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)

from lista import CORRECOES, FALTANDO, SAIDA, trab  # noqa: E402

MAX_DUR = 6.0      # s por evento
MAX_CHAR = 84      # caracteres por evento
GAP = 0.60         # pausa que fecha evento mesmo sem pontuacao


def costurar(ws):
    """Cola no token anterior o pedaco que comeca com hifen e a pontuacao solta.

    O whisper devolve `follow` e `-up` como DUAS palavras. Agrupando com
    espaco sai "follow -up" na tela e no .txt do analista -- foi assim em
    quatro videos do lote da agencia de 03/08/2026, e voltou nos brutos de
    31/08 (v04, v06 e v07). O conserto e' na ORIGEM, antes de agrupar:
    resolve o .srt e o .txt de uma vez, porque os dois saem do mesmo grupo.

    Nao mexe em palavra nenhuma -- so' remove o espaco que o agrupamento
    inventaria. O tempo do pedaco costurado estende o `fim` do anterior,
    senao a palavra terminaria antes de ser dita por inteiro.
    """
    out = []
    for w in ws:
        t = w["txt"].strip()
        cola = t.startswith("-") and len(t) > 1 or re.fullmatch(r"[.,!?;:]+", t)
        if cola and out:
            out[-1] = {**out[-1], "txt": out[-1]["txt"].rstrip() + t,
                       "fim": w["fim"]}
        else:
            out.append(w)
    return out


def palavras(ap):
    d = json.load(open(trab(f"{ap}_fw.json"), encoding="utf-8"))
    return costurar([w for s in d["segmentos"] for w in s["palavras"]])


def eventos(ws):
    """Agrupa palavra a palavra; fecha em pontuacao, pausa, teto ou tamanho."""
    ev, cur = [], []
    for w in ws:
        cur.append(w)
        txt = " ".join(x["txt"] for x in cur).strip()
        fecha = (
            re.search(r"[.!?]$", w["txt"].strip())
            or len(txt) >= MAX_CHAR
            or (cur[-1]["fim"] - cur[0]["ini"]) >= MAX_DUR
        )
        if fecha:
            ev.append(cur)
            cur = []
    if cur:
        ev.append(cur)
    # segunda passada: quebra por pausa longa dentro de um evento
    saida = []
    for grupo in ev:
        atual = [grupo[0]]
        for a, b in zip(grupo, grupo[1:]):
            if b["ini"] - a["fim"] >= GAP:
                saida.append(atual)
                atual = [b]
            else:
                atual.append(b)
        saida.append(atual)
    saida = [g for g in saida if g]
    # O teto de MAX_CHAR corta no meio da frase e deixa um toco ("dolares.",
    # 0,36 s) como evento proprio. Toco pisca na tela e nao ajuda ninguem:
    # volta para o evento anterior quando nao ha pausa entre os dois e o
    # resultado ainda cabe com folga.
    junto = [saida[0]]
    for g in saida[1:]:
        ant = junto[-1]
        texto = " ".join(w["txt"] for w in ant + g)
        toco = (g[-1]["fim"] - g[0]["ini"]) < 1.2 or len(
            " ".join(w["txt"] for w in g)) < 15
        if (toco and g[0]["ini"] - ant[-1]["fim"] < GAP
                and len(texto) <= MAX_CHAR + 20
                and g[-1]["fim"] - ant[0]["ini"] <= MAX_DUR + 1.5):
            junto[-1] = ant + g
        else:
            junto.append(g)
    return junto


def corrigir(txt):
    """Aplica `correcoes.json` do lote -- a UNICA rede que sobra sem OCR.

    Sem a tela nao ha segunda fonte, e erro de palavra do whisper vai queimado
    no arquivo. Cada regra aqui e' uma palavra FALADA que o modelo trocou, e
    so' entra com evidencia DENTRO do proprio material (outro video do lote
    dizendo a palavra, ou o quadro em que a tela a escreve). Troca de uma
    palavra por outra sem essa prova nao entra: vai ao operador.

    Formato: {"de": "para"} ou {"de": {"para": "...", "prova": "..."}}.
    """
    for de, para in REGRAS.items():
        alvo = para["para"] if isinstance(para, dict) else para
        txt = re.sub(rf"\b{re.escape(de)}\b", alvo, txt)
    return txt


REGRAS = {}
if os.path.exists(CORRECOES):
    REGRAS = {k: v for k, v in
              json.load(open(CORRECOES, encoding="utf-8")).items()
              if not k.startswith("_")}


def tc(t):
    h, r = divmod(t, 3600)
    m, s = divmod(r, 60)
    return f"{int(h):02d}:{int(m):02d}:{int(s):02d},{int(round((s % 1) * 1000)):03d}"


def srt(ev):
    out = []
    for i, g in enumerate(ev, 1):
        txt = corrigir(re.sub(r"\s+", " ", " ".join(w["txt"] for w in g)).strip())
        out.append(f"{i}\n{tc(g[0]['ini'])} --> {tc(g[-1]['fim'])}\n{txt}\n")
    return "\r\n".join("\r\n".join(b.split("\n")) for b in out)


def corrido(ev):
    texto = corrigir(re.sub(r"\s+", " ", " ".join(
        w["txt"] for g in ev for w in g)).strip())
    # "Eu sou o Dr. Fulano" nao e' fim de frase (lote 75: o .txt quebrou no "Dr.")
    frases = [f.strip() for f in re.split(
        r"(?<!\bDr\.)(?<!\bDra\.)(?<!\bSr\.)(?<!\bSra\.)(?<=[.!?])\s+", texto)]
    return "\r\n".join(f for f in frases if f) + "\r\n"


os.makedirs(SAIDA, exist_ok=True)
for nome, ap in FALTANDO:
    ws = palavras(ap)
    if len(ws) <= 2:
        print(f"{ap}: {len(ws)} palavra(s) -- SEM FALA, nao gera legenda")
        continue
    ev = eventos(ws)
    base = os.path.splitext(os.path.basename(nome))[0]
    with open(os.path.join(SAIDA, base + ".srt"), "w",
              encoding="utf-8-sig", newline="") as f:
        f.write(srt(ev))
    with open(os.path.join(SAIDA, base + ".txt"), "w",
              encoding="utf-8-sig", newline="") as f:
        f.write(corrido(ev))
    print(f"{ap}: {len(ev)} eventos, {len(ws)} palavras -> {base}")
