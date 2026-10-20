#!/usr/bin/env python3
"""Restaura a pontuacao do SRT do corte a partir do SRT do bruto.

Por que existe: com certos audios o whisper devolve o texto INTEIRO sem
pontuacao e em minusculas. E deterministico -- repetir a chamada da o
mesmo resultado -- e aconteceu em 2 dos 8 videos do lote. Nada falha: o
arquivo existe, as palavras estao certas, a legenda sai correta. O que
quebra e tudo que depende de FRASE, porque o divisor procura `.?!`:
escolha de preto e branco, posicao de light leak e frase em destaque
viram None em silencio.

Reduzir o `queue` as vezes traz a pontuacao de volta, mas num teste com 7
valores (90 a 5) as versoes pontuadas do video 1 **perdiam palavra** --
trocar palavra por pontuacao e pessimo negocio numa peca de medico.

Aqui a pontuacao vem do SRT do bruto, que a tem, casando as palavras por
`difflib`. **Nenhuma palavra muda** -- so o sinal viaja.

Uso: python pontuacao.py <bruto.srt> <corte.srt>
"""
import difflib
import re
import sys

FIM = ".?!"
CABECA = re.compile(r"^\d+$|^\d\d:\d\d:\d\d,\d+ -->")


def _norm(p):
    return re.sub(r"[^\wÀ-ÿ]", "", p).lower()


def _tokens(txt):
    return [p for l in txt.splitlines() if l.strip() and not CABECA.match(l)
            for p in l.split()]


def _blocos(txt):
    """[(cabecalho, [palavras])] preservando os tempos."""
    saida, cab, corpo = [], [], []
    for l in txt.splitlines():
        if CABECA.match(l):
            if corpo:
                saida.append((cab, corpo)); cab, corpo = [], []
            cab.append(l)
        elif l.strip():
            corpo.extend(l.split())
    if corpo:
        saida.append((cab, corpo))
    return saida


def restaurar(bruto_txt, corte_txt):
    ref = _tokens(bruto_txt)
    blocos = _blocos(corte_txt)
    cur = [p for _, corpo in blocos for p in corpo]

    sm = difflib.SequenceMatcher(None, [_norm(p) for p in cur],
                                 [_norm(p) for p in ref], autojunk=False)
    trocas = 0
    for a, b, n in sm.get_matching_blocks():
        for k in range(n):
            base = _norm(cur[a + k])
            if not base:
                continue
            # so a pontuacao viaja: reconstroi a palavra do CORTE com o
            # sufixo da palavra do BRUTO
            orig, novo = cur[a + k], ref[b + k]
            sufixo = novo[len(_norm(novo)):] if _norm(novo) else ""
            m = re.match(r"^(.*?)([^\wÀ-ÿ]*)$", orig)
            corpo, suf_atual = m.group(1), m.group(2)
            if sufixo != suf_atual:
                cur[a + k] = corpo + sufixo
                trocas += 1
            # herda a caixa alta do bruto quando ela marca inicio de frase
            if novo[:1].isupper() and corpo[:1].islower():
                cur[a + k] = corpo[:1].upper() + cur[a + k][1:]

    i, linhas = 0, []
    for cab, corpo in blocos:
        linhas.extend(cab)
        linhas.append(" ".join(cur[i:i + len(corpo)]))
        linhas.append("")
        i += len(corpo)
    return "\n".join(linhas), trocas


def precisa(txt):
    """Pontuacao esparsa demais para dividir em frases?"""
    corpo = " ".join(_tokens(txt))
    return sum(txt.count(c) for c in FIM) < max(2, len(corpo) // 140)


if __name__ == "__main__":
    bruto, corte = sys.argv[1], sys.argv[2]
    b = open(bruto, encoding="utf-8").read()
    c = open(corte, encoding="utf-8").read()
    novo, n = restaurar(b, c)
    antes = [p for p in _tokens(c)]
    depois = [p for p in _tokens(novo)]
    assert [_norm(x) for x in antes] == [_norm(x) for x in depois], \
        "ERRO: alguma palavra mudou -- abortado"
    open(corte, "w", encoding="utf-8").write(novo)
    print(f"{n} sinais restaurados; {len(antes)} palavras intactas")
