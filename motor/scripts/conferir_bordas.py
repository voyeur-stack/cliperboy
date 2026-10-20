# -*- coding: utf-8 -*-
"""Portao de AUDIO nas bordas de `faixas` -- o que faltava em 24/08/2026.

POR QUE ESTE ARQUIVO EXISTE

Lote do Dr. Fulano, 24/08/2026: a bateria inteira deu OK nos 9 videos,
DUAS vezes, e o operador achou defeito de ouvido em minutos -- palavra cortada
no meio ("diferente" -> "difere-") e a frase repetida de uma tomada descartada
entrando na peca com legenda queimada por cima.

Nenhum portao existente podia pegar isso, e a razao e' estrutural:

  `sync`            compara duracao de faixa de video com a de audio
  nivel / pico      estatistica do arquivo inteiro
  musica            correlacao da faixa remixada com o render
  portao de palavra compara TEXTO com TEXTO -- nunca abre o audio

O ultimo e' o mais enganoso: parece medir conteudo. Mas se o fragmento
indevido foi transcrito E legendado, ele aparece dos DOIS lados e o portao
aprova. Foi o que aconteceu.

A varredura das 130 bordas do lote achou 11 defeitos e revelou o padrao:

  - 9 de 11 estao na borda de INICIO, nao de fim;
  - 8 faixas comecavam com material que NAO era a tomada boa;
  - e o descarte vem 4 a 20 dB MAIS BAIXO que a tomada boa.

Esse ultimo numero e' a peneira barata, e e' o que este script explora.

O QUE ELE NAO E'

Nao substitui ouvir. Ele mede energia; nao sabe o que esta sendo dito e nao
julga se 30 ms de cauda a -24 dB incomodam. Serve para dizer ONDE ouvir.

Uso:
    python scripts/conferir_bordas.py --lote "2026-08 - Dr. Fulano"
    python scripts/conferir_bordas.py --lote "..." --faixas outro_lote.json

`--faixas` le as `faixas` de outro arquivo, para conferir uma versao anterior
contra a atual. Foi assim que este script foi validado: rodado contra o
`lote.json.antes-bordas` do Fulano, ele tem de acusar as bordas que ja se sabe
estarem quebradas.

Sai com codigo 1 quando ha borda com defeito -- para poder entrar numa fase.
"""
import argparse
import glob
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

PAD = 0.18                  # igual ao lote_preparar.py
MARGEM = 2.5                # s de audio extraidos de cada lado da borda
QUADRO, PASSO = 0.020, 0.010
MIN_FALA = 0.10             # energia tem de se sustentar 100 ms para ser fala
JUNTA_VAO = 0.06            # vaos menores que isto nao separam blocos

# Uma borda so' e' problema quando a energia ENCOSTA nela. Emenda limpa deste
# lote media -40 dB nos 25 ms antes; as ruins, de -10 a -16 dB. O -33 fica no
# meio do vale, longe das duas populacoes -- nao e' um numero fino.
DB_ENCOSTA = -33.0
# Descarte vem mais baixo que a tomada boa. 4 dB foi o que separou as 8 faixas
# defeituosas do lote do Fulano sem trazer nenhuma boa junto.
DB_DESCARTE = 4.0


def envelope(wav):
    """(instantes, dB) do RMS por quadro. Sem numpy: o projeto ja depende de
    ffmpeg, e uma dependencia a menos e' uma quebra a menos em maquina nova."""
    import array
    import math
    with open(wav, "rb") as f:
        b = f.read()
    i = b.find(b"data")
    a = array.array("h")
    a.frombytes(b[i + 8: i + 8 + (len(b) - i - 8) // 2 * 2])
    sr = 16000
    n, p = int(QUADRO * sr), int(PASSO * sr)
    fora_t, fora_db = [], []
    for k in range(0, max(0, len(a) - n), p):
        s = sum(x * x for x in a[k:k + n]) / n
        fora_t.append(k / sr)
        fora_db.append(10 * math.log10(s / (32768.0 ** 2) + 1e-12))
    return fora_t, fora_db


def blocos_de_fala(t, db, limiar):
    """Runs contiguos acima do limiar, com vaos curtos costurados."""
    br, ini = [], None
    for k, v in enumerate(db):
        if v >= limiar and ini is None:
            ini = t[k]
        elif v < limiar and ini is not None:
            br.append((ini, t[k])); ini = None
    if ini is not None:
        br.append((ini, t[-1]))
    juntos = []
    for a, b in br:
        if juntos and a - juntos[-1][1] < JUNTA_VAO:
            juntos[-1] = (juntos[-1][0], b)
        else:
            juntos.append((a, b))
    return [(a, b) for a, b in juntos if b - a >= MIN_FALA]


def extrair(src, ini, dur, dst):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{max(0, ini):.3f}",
                    "-i", src, "-t", f"{dur:.3f}", "-vn",
                    "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", dst],
                   check=True)


def conferir(v, faixas, bruto, tmp):
    """Uma linha por borda. Devolve a lista de defeitos."""
    achados = []
    # Onde o AUDIO do bruto comeca. Bruto recomprimido (Lavf) traz o audio
    # com start_time > 0, e `-ss` antes dele devolve um wav que comeca no
    # 1o som, nao em `ini`: `rel` saia deslocado pelo start_time. Medido no
    # lote 67 (Dra. Fulana, 24/09/2026): 4 alarmes falsos, todos no inicio da
    # 1a faixa ("fala em curso desde 0.21" com audio so' a partir de 0,744).
    a0 = config.inicio_do_audio(bruto)
    for i, (a, b) in enumerate(faixas):
        for lado, borda in (("inicio", a), ("fim", b)):
            w = os.path.join(tmp, f"b{v}_{i}_{lado}.wav")
            # O MESMO clamp que o `extrair` faz. Sem ele, borda < MARGEM
            # media o lugar ERRADO: o ffmpeg comeca o wav em 0, o codigo
            # acreditava que comecava em `ini` (negativo), e `rel` apontava
            # para ~2,50 s do bruto -- no meio da fala. Resultado medido no
            # lote da Dra. Fulana (27/08/2026): 13 defeitos em 32
            # bordas, TODOS falsos, todos em faixa que comeca antes de 2,5 s.
            # Os instantes saiam negativos ("fala em curso desde -2.28"), que
            # foi o sinal de que o sistema de referencia estava quebrado.
            ini = max(0.0, a0, borda - MARGEM)
            extrair(bruto, ini, MARGEM * 2, w)
            t, db = envelope(w)
            if not db:
                continue
            ord_db = sorted(db)
            p5 = ord_db[len(ord_db) // 20]
            p90 = ord_db[len(ord_db) * 9 // 10]
            limiar = max(p5 + 10, p90 - 22)
            blocos = blocos_de_fala(t, db, limiar)
            rel = borda - ini                      # a borda, no tempo do wav

            # dB nos 25 ms do lado que interessa
            def db_em(t0, t1):
                vs = [d for tt, d in zip(t, db) if t0 <= tt <= t1]
                return max(vs) if vs else -99.0

            dentro = any(x < rel < y for x, y in blocos)
            if lado == "fim":
                nivel = db_em(rel - 0.025, rel)
                # o PAD so' age se a fala terminar ANTES da borda; quando ela
                # atravessa, quem corta e' a borda -- e e' esse o defeito
                if dentro and nivel > DB_ENCOSTA:
                    seg = [y for x, y in blocos if x < rel < y]
                    achados.append((v, i, lado, borda, nivel,
                                    f"fala atravessa a borda, segue ate "
                                    f"{ini + seg[0]:.2f} (+{(seg[0] - rel) * 1000:.0f} ms)"))
            else:
                nivel = db_em(rel, rel + 0.025)
                if dentro and nivel > DB_ENCOSTA:
                    seg = [x for x, y in blocos if x < rel < y]
                    achados.append((v, i, lado, borda, nivel,
                                    f"abre com fala em curso desde "
                                    f"{ini + seg[0]:.2f} ({(rel - seg[0]) * 1000:.0f} ms colados)"))
                else:
                    # Tomada DESCARTADA: o primeiro bloco depois da borda vem
                    # mais baixo que o corpo da faixa. Foi o caso que escapou
                    # de tres medicoes seguidas no lote do Fulano.
                    dps = [(x, y) for x, y in blocos if x >= rel]
                    if len(dps) >= 2:
                        pri = db_em(dps[0][0], dps[0][1])
                        corpo = max(db_em(x, y) for x, y in dps[1:])
                        if corpo - pri >= DB_DESCARTE:
                            achados.append((v, i, lado, borda, pri,
                                            f"1o bloco {corpo - pri:.1f} dB abaixo do corpo "
                                            f"-- possivel TOMADA DESCARTADA "
                                            f"({(dps[0][1] - dps[0][0]) * 1000:.0f} ms)"))
    return achados


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--faixas", default=None,
                    help="ler `faixas` de outro JSON (para comparar versoes)")
    a, _ = ap.parse_known_args()
    LOTE = config.carregar()

    faixas = LOTE.faixas
    if a.faixas:
        d = json.load(open(a.faixas, encoding="utf-8"))
        faixas = {k: [tuple(p) for p in v] for k, v in d["faixas"].items()}
        print(f"faixas lidas de {a.faixas}\n")

    # O corte nem sempre mora em `faixas`. No modo `corte_legenda` o lote
    # descreve o que SAI (`refeito`), e os trechos que FICAM sao gravados em
    # `trabalho/{v}_plano.json` pelo render. Sem isto, este portao lia um
    # dicionario vazio, nao media borda nenhuma e saia com CODIGO 0 --
    # aprovando um lote inteiro sem olhar para ele. Aconteceu no lote 33
    # (Agencia 31/08, 01/09/2026): 20 emendas, "0 bordas medidas", exit 0.
    if not faixas and not a.faixas:
        planos = sorted(glob.glob(os.path.join(LOTE.trabalho, "*_plano.json")),
                        key=lambda f: int(os.path.basename(f).split("_")[0]))
        for f in planos:
            v = os.path.basename(f).split("_")[0]
            _d = json.load(open(f, encoding="utf-8"))
            # tolera o formato antigo (dict com "blocos"), que existiu por
            # algumas horas em 01/09/2026 e fez este portao estourar
            faixas[v] = [tuple(x) for x in
                         (_d["blocos"] if isinstance(_d, dict) else _d)]
        if faixas:
            print(f"faixas derivadas de {len(planos)} `_plano.json` "
                  f"(este lote descreve o corte por `refeito`)\n")

    tmp = os.path.join(LOTE.trabalho, "_bordas")
    os.makedirs(tmp, exist_ok=True)
    todos, n_bordas = [], 0
    for v in sorted(faixas, key=int):
        bruto = LOTE.bruto_de(v)
        if not os.path.exists(bruto):
            print(f"v{v}: bruto nao encontrado ({bruto}) -- PULADO")
            continue
        n_bordas += len(faixas[v]) * 2
        ach = conferir(v, faixas[v], bruto, tmp)
        todos += ach
        print(f"v{v}: {len(faixas[v]) * 2:3d} bordas, {len(ach)} com defeito")

    print(f"\nCOBERTURA: {n_bordas} bordas medidas, "
          f"{n_bordas - len(todos)} OK, {len(todos)} com defeito")
    # ZERO borda nao e' aprovacao -- e' o portao nao tendo o que medir, e
    # sair com 0 aqui e' pior que reprovar: o lote passa sem ser olhado.
    if not n_bordas:
        print("\nABORTADO: nenhuma borda para medir. Ou o lote nao tem "
              "`faixas`, ou nao ha `_plano.json` em trabalho/ (o render "
              "ainda nao rodou), ou os brutos nao estao no lugar.")
        return 2
    if todos:
        print("\nDEFEITOS (ouca cada um antes de mexer no lote.json):")
        for v, i, lado, borda, nivel, txt in todos:
            print(f"  v{v} faixa {i:2d} {lado:6s} {borda:8.2f}  {nivel:6.1f} dB  {txt}")
        # 0,5 s, nao 0,20: o "fim da fala" que se mede por energia (-35 dB)
        # e' o fim do nucleo da palavra, e a cauda (nasal, expiracao) segue
        # 0,2-0,4 s abaixo disso. Borda a 0,05-0,20 s desse ponto ainda
        # decapita ('iss-', 'confian-', lote 62, 21/09/2026). Com 0,5 s a
        # borda para de ser a faca e o corte de silencio + PAD fecha sozinho.
        print("\nConserto: dar FOLGA a borda no lote.json. Com vao >= "
              f"{config.MIN_GAP}s use >= 0,5 s alem do fim da fala -- assim a "
              "borda deixa de ser a faca e quem manda volta a ser o PAD. "
              "Vao menor: as tomadas estao coladas, mire em onset-0,10 e "
              "saiba que sobram alguns ms.")
    return 1 if todos else 0


if __name__ == "__main__":
    sys.exit(main())
