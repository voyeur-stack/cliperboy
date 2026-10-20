#!/usr/bin/env python3
"""Legendas da entrega: um `.srt` e um `.txt` por video, saidos do `.ass`.

E' o `exportar_legendas.py` que ficava dentro do lote de 03/08, promovido
para `scripts/` em 01/09/2026 junto com o `produzir.py`. La' ele tinha
`range(1, 7)` e as pastas por `dirname(__file__)`; aqui vem tudo do lote.

O texto sai do PROPRIO `.ass` do render -- e' a unica fonte que bate com o
que esta na tela, porque ja passou pelo alinhamento, pelo agrupamento e
pelas `correcoes_legenda`. O `_corte.srt` cru do whisper NAO serve: as
correcoes nao voltam para ele, e entregar o cru e' entregar texto que nao
bate com o video.

CAIXA: o `.srt` espelha a TELA, nao um padrao. Neste modo a queimada esta
em caixa normal (modelo da referencia de 24/07), entao o `.srt` sai em
caixa normal. A regra de caixa alta e' do Reels com realce amarelo.

NOME: se o lote tiver a chave `nomes` ({"1": "01 - Titulo"}), os arquivos
saem com ela -- e' o mesmo nome do `.mp4`, para o analista conseguir ligar
a legenda ao video. Sem ela, cai em `Video {v}`, que e' o do lote de 03/08.

    python scripts/corte_legenda/exportar.py --lote "<nome>" [numeros...]
"""
import os
import re
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)

from lote import L, REFEITO, SAIDA, TRAB  # noqa: E402

DEST = os.path.join(SAIDA, "Legendas")
NOMES = {int(k): v for k, v in L._dados.get("nomes", {}).items()
         if not k.startswith("_")}


def eventos(v):
    saida = []
    for linha in open(os.path.join(TRAB, f"{v}.ass"), encoding="utf-8"):
        if not linha.startswith("Dialogue:"):
            continue
        campos = linha.split(",", 9)
        texto = re.sub(r"\{[^}]*\}", "", campos[9]).strip()
        if texto:
            saida.append((campos[1], campos[2], texto))
    return saida


PAUSA_LINHA = 0.45   # s de silencio entre eventos que fecha uma linha do .txt


def _seg(t):
    h, m, x = t.split(":")
    return int(h) * 3600 + int(m) * 60 + float(x)


def para_srt(t):
    """0:00:19.82 -> 00:00:19,820"""
    h, m, s = t.split(":")
    return f"{int(h):02d}:{int(m):02d}:{float(s):06.3f}".replace(".", ",")


if __name__ == "__main__":
    quais = [int(x) for x in sys.argv[1:] if x.isdigit()]
    if not quais:
        quais = sorted(int(os.path.basename(f).split(".")[0])
                       for f in os.listdir(TRAB)
                       if re.fullmatch(r"\d+\.ass", os.path.basename(f)))
    os.makedirs(DEST, exist_ok=True)
    for v in quais:
        ev = eventos(v)
        if not ev:
            sys.exit(f"v{v}: o .ass nao tem evento nenhum -- nao exporto "
                     f"legenda vazia")
        base = NOMES.get(v, f"Vídeo {v}")
        with open(os.path.join(DEST, base + ".srt"), "w",
                  encoding="utf-8") as f:
            for i, (a, b, t) in enumerate(ev, 1):
                f.write(f"{i}\n{para_srt(a)} --> {para_srt(b)}\n{t}\n\n")

        # texto corrido, uma frase por linha: e' o que o analista reaproveita
        # na legenda do post, e por isso nao leva tempo nem numeracao.
        #
        # A quebra NAO pode sair so' da pontuacao. O whisper as vezes nao
        # pontua trecho nenhum, e ai o `.txt` vira um paragrafo unico: no
        # lote 33 o v13 saiu com uma "frase" de 105 palavras, o v10 com 90 e
        # o v8 com 69 -- e nesses dois nem o bruto tinha pontuacao para
        # restaurar. Entao a PAUSA DA FALA tambem quebra linha: vao de
        # PAUSA_LINHA entre o fim de um evento e o inicio do proximo. Isso
        # nao inventa pontuacao e nao muda palavra nenhuma -- so' decide
        # onde a linha termina.
        frases, atual, fim_ant = [], [], None
        for a, b, t in ev:
            if atual and fim_ant is not None and _seg(a) - fim_ant >= PAUSA_LINHA:
                frases.append(" ".join(atual))
                atual = []
            atual.append(t)
            fim_ant = _seg(b)
            if re.search(r"[.?!]$", t):
                frases.append(" ".join(atual))
                atual = []
        if atual:
            frases.append(" ".join(atual))
        frases = [x.strip() for x in frases if x.strip()]
        with open(os.path.join(DEST, base + ".txt"), "w",
                  encoding="utf-8") as f:
            f.write("\n".join(frases) + "\n")
        print(f"v{v}: {len(ev)} eventos, {len(frases)} frases -> {base}")
    print(f"\n{len(quais)} pares em {DEST}")
