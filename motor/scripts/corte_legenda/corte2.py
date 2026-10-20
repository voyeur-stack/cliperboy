#!/usr/bin/env python3
"""Decide o corte, com a trava ancorada na ENERGIA DO AUDIO.

DUAS VERSOES ERRADAS ANTES DESTA, e as duas cortaram fala:

1. A primeira usou os tempos do filtro `whisper` do ffmpeg (erro de
   +-100 ms, sinal aleatorio) para decidir o corte. O v2 perdeu "Como que
   esse" e o v5 cortou "doctor" no meio.

2. A segunda trocou por faster-whisper (bom) mas aplicou as remocoes
   manuais FILTRANDO PALAVRAS pelo tempo delas. Na regiao de tomada
   refeita esse tempo e' justamente o que nao presta: o alinhador estica a
   palavra por cima do audio que nao transcreveu ("concorrencia" saiu
   durando 2,62 s, comecando 1,8 s antes de ser dita). Filtrar por esse
   tempo removeu palavras que sao ditas DEPOIS da janela, e o corte partiu
   "concorrencia" ao meio -- o pedaco "-correncia" virou "a agencia" na
   re-transcricao. E a trava da versao 2 nao pegou, porque ela pulava
   exatamente as palavras da regiao removida.

O QUE ESTA VERSAO FAZ DE DIFERENTE

  * remocao manual e' SUBTRACAO DE INTERVALO sobre os blocos, nunca filtro
    de palavras -- tempo ruim de palavra deixa de influir;
  * a trava final nao olha palavra nenhuma: ela mede os segmentos de fala
    do bruto pela ENERGIA (o mesmo detector do `retimar_legenda.py`, que
    usa limiar relativo a faixa dinamica) e exige que TODA borda de corte
    caia em silencio. Whisper nao participa dessa conferencia.
"""
import json
import os
import subprocess
import sys

import numpy as np

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(os.path.dirname(AQUI))
sys.path.insert(0, AQUI)
from lote import TRAB, bruto  # noqa: E402
sys.path.insert(0, os.path.join(RAIZ, "scripts"))

FPS = 30
LIMITE = 0.50      # vao entre palavras a partir do qual vale cortar
PAD_FIM = 0.22     # folga DEPOIS da ultima palavra antes do corte
PAD_INI = 0.14     # folga ANTES da primeira palavra depois do corte
CABECA = 0.20
RABO = 0.50
FOLGA_SILENCIO = 0.05   # quanto a borda pode encostar na fala, na trava


def palavras(v):
    d = json.load(open(os.path.join(TRAB, f"{v}_fw.json"), encoding="utf-8"))
    return [w for s in d["segmentos"] for w in s["palavras"] if w["txt"]]


def dur_de(src):
    return float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", src],
        capture_output=True, text=True).stdout.strip())


def grade(t):
    return round(t * FPS) / FPS


def subtrair(blocos, remover):
    """Tira cada intervalo de `remover` da lista de blocos."""
    out = list(blocos)
    for ra, rb in remover:
        novo = []
        for a, b in out:
            if rb <= a or ra >= b:
                novo.append((a, b))
                continue
            if a < ra:
                novo.append((a, ra))
            if rb < b:
                novo.append((rb, b))
        out = novo
    return [(a, b) for a, b in out if b - a > 0.15]


def blocos_de(v, remover=()):
    ps = palavras(v)
    dur = dur_de(bruto(v))
    out, ini, ant = [], max(0.0, ps[0]["ini"] - CABECA), ps[0]["fim"]
    for w in ps[1:]:
        if w["ini"] - ant > LIMITE:
            out.append((ini, min(ant + PAD_FIM, dur)))
            ini = max(0.0, w["ini"] - PAD_INI)
        ant = max(ant, w["fim"])
    out.append((ini, min(ant + RABO, dur)))
    out = subtrair(out, remover)
    # a grade so' pode ALARGAR: encolher e' o arredondamento comendo a folga
    return [(max(0.0, grade(a - 1 / FPS / 2)), grade(b + 1 / FPS / 2))
            for a, b in out], dur


def fala_do_bruto(v):
    """Segmentos de fala do bruto, medidos por ENERGIA -- sem whisper."""
    import retimar_legenda as R
    wav = os.path.join(TRAB, f"_energia{v}.wav")
    if not os.path.exists(wav):
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i",
                        bruto(v), "-vn",
                        "-ac", "1", "-ar", "16000", wav], check=True)
    return [(a / 1000, b / 1000) for a, b in R.segmentos_de_fala(wav)]


def envelope(v):
    """(tempos, dB) do bruto, 5 ms de passo, banda de voz. Sem whisper."""
    import retimar_legenda as R
    wav = os.path.join(TRAB, f"_energia{v}.wav")
    if not os.path.exists(wav):
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i",
                        bruto(v), "-vn",
                        "-ac", "1", "-ar", "16000", wav], check=True)
    t, db, piso, faixa = R._envelope(wav)
    return t / 1000.0, db, piso, faixa


def ajustar_bordas(v, blocos, remover=(), fora=0.60, perto=0.30):
    """Move cada borda de corte para o ponto MAIS SILENCIOSO perto dela.

    Por que nao basta "empurrar a borda para fora do segmento de fala":
    no v6 a direcao de camera ("Segura ai, Fulano") encosta na tomada boa com
    menos de 60 ms de intervalo -- o detector funde as duas num segmento
    so', e nao existe silencio para onde empurrar. Procurar o MINIMO de
    energia resolve os dois casos com a mesma regra: quando ha silencio, o
    minimo cai nele; quando nao ha, cai no ponto de menor estrago, e o
    quanto sobrou fica medido em vez de suposto.

    A DIRECAO da busca importa, e errar nela nao resolve nada. O inicio de
    um bloco procura o silencio PARA TRAS e o fim procura PARA A FRENTE --
    isto e', o bloco so' cresce, nunca invade a fala do vizinho. Com busca
    simetrica o v5 continuava cortando: a janela inteira a' frente de 8,72
    e' fala (o detector acha fala em 8,37, antes da primeira palavra que o
    whisper transcreveu, as 8,86).

    As bordas de REMOCAO MANUAL nao se mexem. Elas foram escolhidas olhando
    a energia em 10 ms (`fino.py`) num trecho onde nao HA silencio, e mover
    desfaz a escolha. No v1 o ajuste automatico empurrou o corte de 38,64
    para 38,83 -- procurando o menor vale numa janela simetrica, ele achou o
    vale SEGUINTE, e o corte passou a manter "formulario, que a su-": o
    tropeco que a remocao existia para tirar. O vale certo, entre
    "formulario," e "que", esta em 38,64 e mede -15,5 dB sob o pico da
    frase.

    A primeira borda e a ultima nao se mexem: sao inicio e fim do video.
    """
    t, db, piso, _ = envelope(v)
    bordas_manuais = [x for par in remover for x in par]

    def manual(alvo):
        return any(abs(alvo - x) < 0.12 for x in bordas_manuais)

    def melhor(alvo, lo, hi):
        m = (t >= lo) & (t <= hi)
        if not m.any():
            return alvo
        idx = np.where(m)[0]
        return float(t[idx[np.argmin(db[idx])]])

    out = []
    for i, (a, b) in enumerate(blocos):
        if i == 0 or manual(a):
            na = a
        else:
            na = melhor(a, a - fora, a)          # cresce para tras
        if i == len(blocos) - 1 or manual(b):
            nb = b
        else:
            nb = melhor(b, b, b + fora)          # cresce para a frente
        out.append((max(0.0, grade(na - 1 / FPS / 2)), grade(nb + 1 / FPS / 2)))

    # Crescer pode fazer um bloco alcancar o seguinte. Quando isso acontece
    # a pausa nao era grande o bastante para justificar corte, e o certo e'
    # NAO cortar ali -- funde os dois. Sem isto os blocos se sobrepoem e o
    # audio do trecho comum sai duas vezes: no v2 a soma dos blocos deu
    # 58,3 s para um bruto de 57,3 s, o que e' impossivel e denuncia o bug.
    dur = dur_de(bruto(v))
    fundido = []
    for a, b in out:
        b = min(b, grade(dur))
        if fundido and a <= fundido[-1][1]:
            fundido[-1] = (fundido[-1][0], max(fundido[-1][1], b))
        else:
            fundido.append((a, b))
    return fundido


def conferir(v, blocos, remover=()):
    """Toda borda de corte tem de cair em silencio. Devolve os problemas.

    Esta e' a conferencia que faltava nas duas versoes anteriores, e e' a
    unica que nao depende do whisper: ela mede o audio.

    Borda de REMOCAO MANUAL nao entra: ela e' uma decisao editorial, e as
    vezes o unico lugar por onde cortar o tropeco esta dentro de uma frase
    emendada, sem silencio nenhum (v1). A guarda existe para pegar corte
    ACIDENTAL em fala -- reprovar o corte deliberado faria ela empurrar o
    tropeco de volta para dentro do video, que foi o que aconteceu.
    """
    bordas_manuais = [x for par in remover for x in par]
    segs = fala_do_bruto(v)
    bordas = []
    for i, (a, b) in enumerate(blocos):
        if i:                       # o inicio do 1o bloco pode ser 0
            bordas.append(("inicio", a))
        if i < len(blocos) - 1:     # o fim do ultimo bloco pode ser o fim
            bordas.append(("fim", b))
    ruins = []
    for nome, t in bordas:
        if any(abs(t - x) < 0.12 for x in bordas_manuais):
            continue
        for sa, sb in segs:
            if sa + FOLGA_SILENCIO < t < sb - FOLGA_SILENCIO:
                ruins.append((nome, t, sa, sb))
                break
    return ruins
