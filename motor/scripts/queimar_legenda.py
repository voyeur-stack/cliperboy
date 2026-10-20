# -*- coding: utf-8 -*-
"""Queima o `.ass` sobre a BASE sem legenda -- trocar fonte em minutos.

POR QUE ESTE ARQUIVO EXISTE

25/08/2026, lote do Dr. Fulano. O cliente mandou a fonte Manier em
versao TRIAL (70 glifos, sem acento nenhum) e pediu a completa depois. Trocar
a fonte obrigava a refazer o render inteiro: **2h20 o lote**, para mudar uma
coisa que e' das ULTIMAS do grafo.

A observacao que destrava: quando so' a tipografia muda, TUDO antes da legenda
e' identico -- corte, zoom, P&B, leaks, tarja, card, audio, musica. Entao a
peca pode ser renderizada UMA vez sem legenda (`lote_produzir.py --base`) e a
legenda ser queimada por cima quantas vezes forem precisas.

Medido neste lote: render completo ~2h20; queimar a legenda, ~30 s por video,
**~5 min o lote**. Isso muda o que da' para experimentar -- dez variacoes de
corpo, cor ou posicao numa manha, em vez de uma por dia.

CUSTO DECLARADO, e ele e' real: a peca final passa por DOIS encodes. Por isso
a base sai em `crf 14` (quase transparente) e a queima usa a mesma regua do
render normal. A perda existe, e' pequena, e o operador aprovou em 25/08.

QUANDO **NAO** USAR
  - Video com FRASE EM DESTAQUE. O whip, o blur e a aberracao dela vivem no
    GRAFO, nao no `.ass` -- a base sairia com o borrao e sem o texto. O
    `lote_produzir.py --base` RECUSA esses videos; se um passar por aqui, o
    problema esta la.
  - Mudanca que nao seja de legenda. Corte, zoom, cor, musica, tarja: tudo
    isso e' anterior a legenda e exige render normal.

Uso:
    python scripts/queimar_legenda.py --lote "2026-08 - Dr. Fulano"
    python scripts/queimar_legenda.py --lote "..." 3 7      # so' esses videos
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

LOTE = config.carregar()
alvos = [a for a in sys.argv[1:] if a.isdigit()] or sorted(LOTE.faixas, key=int)


def _probe(f, args):
    r = subprocess.run(["ffprobe", "-v", "error"] + args +
                       ["-of", "csv=p=0", f], capture_output=True, text=True)
    if r.returncode != 0 or not r.stdout.strip():
        return None
    return r.stdout.strip().splitlines()[0].strip().rstrip(",")


def dur(f):
    """Duracao do STREAM DE VIDEO, por `nb_frames / fps`.

    NAO usar `format=duration` aqui. Custo medido no v1 do lote 27 (Dra. Fulana 2, 25/08/2026): a base estava corrompida, a queima parou de escrever
    video em 446 quadros (28,70 s) e o audio, copiado com `-c:a copy`, seguiu
    ate 36,10 s. `format=duration` e' o campo do CONTAINER e o audio sozinho
    o sustentava, entao o portao comparou 36,098 contra 36,098 e imprimiu
    `v1: OK`. O `lote_verificar` pegou depois, com 7398 ms de sync.

    E' o padrao de falha que este projeto mais repete: o portao mediu o
    PROCESSO (container, exit code) em vez do ARTEFATO (os quadros).
    """
    n = _probe(f, ["-select_streams", "v:0", "-show_entries",
                   "stream=nb_frames"])
    fps = _probe(f, ["-select_streams", "v:0", "-show_entries",
                     "stream=r_frame_rate"])
    if not n or not fps or not n.isdigit():
        return None
    try:
        a, b = fps.split("/")
        f_ps = float(a) / float(b)
    except (ValueError, ZeroDivisionError):
        return None
    return int(n) / f_ps if f_ps else None


def dur_audio(f):
    d = _probe(f, ["-select_streams", "a:0", "-show_entries",
                   "stream=duration"])
    try:
        return float(d)
    except (TypeError, ValueError):
        return None


falhas = []
for v in alvos:
    base = os.path.join(LOTE.saida, f"{v}_PRONTO_BASE.mp4")
    ass = f"{v}_legenda.ass"
    saida = os.path.join(LOTE.saida, f"{v}_PRONTO.mp4")

    if not os.path.exists(base):
        print(f"v{v}: SEM BASE -- rode `lote_produzir.py --base {v}` antes")
        falhas.append(v); continue
    d_base = dur(base)
    if d_base is None:
        print(f"v{v}: a base esta QUEBRADA (nao abre) -- refaca com --base")
        falhas.append(v); continue

    # A legenda queimada usa o mesmo derivado sem acento do render normal,
    # quando o lote pede `sem_acento`. Sem isto, trocar de fonte reintroduz
    # o acento que a fonte trial nao tem.
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
    import importlib
    lp = importlib.import_module("lote_produzir")
    arq_ass = lp.ass_para_queimar(v, ass)

    if not os.path.exists(os.path.join(LOTE.trabalho, arq_ass)):
        print(f"v{v}: {arq_ass} nao existe -- rode a fase 2 ou o gerar_ass")
        falhas.append(v); continue

    cmd = (["ffmpeg", "-v", "error", "-y", "-i", base,
            "-vf", f"subtitles={arq_ass}:fontsdir=fonts",
            "-c:a", "copy"]                     # o audio nao muda: copia
           + config.encoder_video()
           + ["-movflags", "+faststart", saida])
    r = subprocess.run(cmd, cwd=LOTE.trabalho, capture_output=True, text=True,
                       creationflags=config.PRIORIDADE_BAIXA)
    if r.returncode:
        print(f"v{v}: FALHOU -> {r.stderr[:200]}")
        falhas.append(v); continue

    # Conferir o ARTEFATO, nao o codigo de saida: render interrompido deixa
    # arquivo com tamanho plausivel (ver docs/03-armadilhas.md §AC4).
    d = dur(saida)
    if d is None:
        print(f"v{v}: saiu QUEBRADO (nao abre)")
        falhas.append(v); continue
    if abs(d - d_base) > 0.05:
        print(f"v{v}: duracao mudou ({d_base:.3f} -> {d:.3f}) -- "
              f"a legenda nao devia mexer nisso")
        falhas.append(v); continue
    # Video contra AUDIO no mesmo arquivo. E' isto que pega base corrompida:
    # o video para de ser escrito e o audio copiado segue ate o fim, entao
    # comparar a saida so' contra a base nao denuncia nada (as duas "duram"
    # o mesmo pelo container). Ver a docstring de `dur`.
    da = dur_audio(saida)
    if da is not None and abs(d - da) > 0.15:
        print(f"v{v}: VIDEO TRUNCADO -- video {d:.2f}s contra audio "
              f"{da:.2f}s ({abs(d - da) * 1000:.0f} ms). A base provavelmente "
              f"esta corrompida: refaca o render em vez de queimar de novo.")
        falhas.append(v); continue
    print(f"v{v}: OK  {d:.3f}s  {os.path.getsize(saida)/1e6:.1f} MB")

if falhas:
    print(f"\nFALHOU em: {', '.join(map(str, falhas))}")
    sys.exit(1)
print(f"\n{len(alvos)} video(s) com a legenda nova.")
