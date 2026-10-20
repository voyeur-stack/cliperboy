#!/usr/bin/env python3
"""Remix de musica de fundo: encurta a faixa sem perder inicio nem fim.

E o que a ferramenta Remix do Premiere faz. As duas alternativas obvias
sao ruins: acelerar muda o tom, e cortar no meio corta a frase musical no
meio dela. O remix remove um numero INTEIRO de frases musicais do miolo e
emenda numa batida -- a introducao e o encerramento ficam intactos, e a
emenda cai onde o ouvido ja espera um acento.

Metodo:
  1. envelope de onset (diferenca positiva da energia em janelas de 23 ms)
  2. andamento por autocorrelacao do envelope, entre 60 e 200 BPM
  3. fase da batida: o deslocamento que maximiza a energia de onset em
     t0 + n*P
  4. remove k frases de 4 compassos (16 batidas) do miolo, emenda com
     crossfade de meia batida
  5. o que sobrar de excesso sai da INTRODUCAO, nunca do fim -- o fim e a
     parte que nao pode ser perdida

Uso: python musica.py <mp3> <duracao_alvo> <saida.wav> [ganho_db]
"""
import os
import re
import subprocess
import sys

import numpy as np

SR = 22050
HOP = 512                       # ~23 ms
XF = 0.25                       # crossfade na emenda
FADE_IN, FADE_OUT = 1.20, 0.90
# Ganho aplicado sobre o arquivo ORIGINAL, como no Premiere: la tudo entra
# em 0 dB e ele baixa a musica para -33. Nao e um alvo de nivel medio --
# normalizar a media PARA -33 dBFS deixa 11 a 13 dB mais alto, que foi o
# erro da primeira versao ("as musicas ainda estao bem altas").
GANHO_PADRAO = -33.0
# Fracao da energia mediana abaixo da qual a faixa ja esta so decaindo.
PISO_CAUDA = 0.35


def rodar(args):
    return subprocess.run(args, capture_output=True)


def envelope(src):
    raw = rodar(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", src,
                 "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"]).stdout
    x = np.frombuffer(raw, dtype=np.float32)
    n = len(x) // HOP
    rms = np.sqrt((x[:n * HOP].reshape(n, HOP) ** 2).mean(axis=1) + 1e-12)
    e = np.log(rms)
    on = np.diff(e, prepend=e[0])
    on[on < 0] = 0.0            # so o ataque conta
    return on, rms, len(x) / SR


def fim_util(rms, dur):
    """Onde a faixa para de tocar e comeca so a decair.

    A maioria destas faixas termina com um fade natural de varios segundos.
    Preservar esse fim -- que era a ideia -- fazia o video acabar quase em
    silencio, ainda por cima com o meu proprio fade por cima dele. O fim
    util e o ultimo ponto com energia de verdade; o fade quem poe sou eu,
    curto, no lugar certo.
    """
    med = float(np.median(rms))
    acima = np.nonzero(rms > PISO_CAUDA * med)[0]
    if not len(acima):
        return dur
    return min(dur, (acima[-1] + 1) * HOP / SR)


def andamento(on):
    """Periodo da batida, em quadros de HOP."""
    o = on - on.mean()
    ac = np.correlate(o, o, mode="full")[len(o) - 1:]
    lo = int(60.0 / 200 * SR / HOP)         # 200 BPM
    hi = int(60.0 / 60 * SR / HOP)          # 60 BPM
    faixa = ac[lo:hi]
    if not len(faixa):
        return None
    p = lo + int(np.argmax(faixa))
    # o pico pode ser um multiplo; prefere o menor periodo com energia
    # comparavel, senao um andamento de 80 BPM vira 40
    for div in (4, 3, 2):
        q = p // div
        if q >= lo and ac[q] > 0.75 * ac[p]:
            p = q
            break
    return p


def fase(on, p):
    """Deslocamento inicial que melhor casa com uma grade de periodo p."""
    melhor, arg = -1.0, 0
    for t0 in range(p):
        idx = np.arange(t0, len(on), p)
        s = float(on[idx].sum())
        if s > melhor:
            melhor, arg = s, t0
    return arg


def medir_media(f):
    err = subprocess.run(["ffmpeg", "-hide_banner", "-i", f, "-af",
                          "volumedetect", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    m = re.search(r"mean_volume: (-?[\d.]+)", err)
    return float(m.group(1)) if m else None


def remixar(src, alvo, saida, ganho=GANHO_PADRAO):
    on, rms, dur = envelope(src)
    util = fim_util(rms, dur)                   # ignora a cauda que so decai
    p = andamento(on)
    if p is None or util <= alvo + 1.0:
        corte1 = corte2 = None
        bpm, frase = 0.0, 0.0
    else:
        seg = HOP / SR
        bpm = 60.0 / (p * seg)
        t0 = fase(on, p) * seg
        frase = 16 * p * seg                    # 4 compassos
        # PISO, nunca `round`. Com `round` o 5,897 do v10 deste lote virou 6, e
        # remover UMA frase a mais do que a faixa comporta deixou a musica
        # 0,908 s mais curta que a peca. O `apad` la embaixo completou com
        # AMOSTRA NULA, e a peca terminou em 0,833 s de silencio DIGITAL --
        # nao "baixo", zero. Segunda vez desta mesma cliente (lote 18).
        # Medido nas 10 faixas deste lote: `k` e IDENTICO nas outras 9 (nelas o
        # `while corte2 > util - 2.0` ja limita antes) e so muda no v10, que
        # passa de 27,96 s (curta) para 34,28 s. O excedente sai da INTRODUCAO
        # pelo `recorte`, que ja existe. Risco zero para as outras.
        # E desconta o XF: a emenda come XF segundos (`depois` abaixo). Sem
        # isso, quando a sobra (util - alvo) mod frase < XF, o remix ficava
        # curto e a GUARDA abortava -- lote 87 v3 (15/10/2026) abortou com DUAS
        # faixas diferentes (faltam 0,214 e 0,168 s). So' muda `k` nesses casos.
        k = max(1, int((util - alvo - XF) / frase))
        # a emenda cai a ~30% da faixa, num inicio de frase musical
        n1 = max(1, int(round((0.30 * util - t0) / frase)))
        corte1 = t0 + n1 * frase
        corte2 = corte1 + k * frase
        while corte2 > util - 2.0 and k > 1:    # nao come o encerramento
            k -= 1
            corte2 = corte1 + k * frase
        if corte2 > util - 2.0:
            corte1 = corte2 = None

    tmp = saida + ".tmp.wav"
    if corte1 is None:
        pos = max(0.0, util - alvo)
        rodar(["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss",
               f"{pos:.3f}", "-i", src, "-t", f"{alvo:.3f}", "-ac", "2",
               "-ar", "48000", "-y", tmp])
        emendas = 0
    else:
        depois = corte1 + (util - corte2) - XF
        recorte = max(0.0, depois - alvo)       # o excesso sai da INTRODUCAO
        # GUARDA: se ainda assim nao houver material para o alvo, o `apad`
        # abaixo mascararia a falta com silencio digital em vez de falhar --
        # que e' exatamente o modo de falha que este projeto persegue: portao
        # que mede o PROCESSO e deixa o ARTEFATO sair errado. Falha alto.
        if depois < alvo - 0.05:
            raise SystemExit(
                f"ABORTADO: {os.path.basename(src)} rende {depois:.3f}s de "
                f"musica para uma peca de {alvo:.3f}s (faltam "
                f"{alvo - depois:.3f}s). O `apad` encheria isso de silencio "
                f"digital. Escolha outra faixa ou reveja o remix.")
        fc = (f"[0:a]atrim=0:{corte1:.3f},asetpts=N/SR/TB[a1];"
              f"[0:a]atrim={corte2:.3f}:{util:.3f},asetpts=N/SR/TB[a2];"
              f"[a1][a2]acrossfade=d={XF}:c1=tri:c2=tri,"
              f"atrim={recorte:.3f}:{recorte + alvo:.3f},asetpts=N/SR/TB[a]")
        rodar(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", src,
               "-filter_complex", fc, "-map", "[a]", "-ac", "2",
               "-ar", "48000", "-y", tmp])
        emendas = 1

    antes = medir_media(tmp)
    rodar(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", tmp, "-af",
           f"volume={ganho:.2f}dB,afade=t=in:d={FADE_IN},"
           f"afade=t=out:st={max(0.0, alvo - FADE_OUT):.3f}:d={FADE_OUT},"
           f"apad=whole_dur={alvo:.3f}",
           "-t", f"{alvo:.3f}", "-ac", "2", "-ar", "48000", "-y", saida])
    os.remove(tmp)
    return {"bpm": round(bpm, 1), "dur_original": round(dur, 2),
            "fim_util": round(util, 2), "frase_s": round(frase, 2),
            "emendas": emendas, "ganho_db": ganho,
            "media_origem": antes, "media_final": medir_media(saida)}


if __name__ == "__main__":
    src, alvo, saida = sys.argv[1], float(sys.argv[2]), sys.argv[3]
    g = float(sys.argv[4]) if len(sys.argv) > 4 else GANHO_PADRAO
    print(remixar(src, alvo, saida, g))
