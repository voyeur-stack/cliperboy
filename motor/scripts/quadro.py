# -*- coding: utf-8 -*-
"""Quadro de CONFERENCIA -- JPG por padrao, mosaico por padrao.

POR QUE ESTE ARQUIVO EXISTE (medido em 14/08/2026)

Apuracao de custo de token de 12 a 14/08: US$ 1.591 no total, US$ 1.063 so'
neste projeto. A decomposicao:

  - 68 % da conta e' cache read -- reler contexto ja' acumulado.
  - 84 % do contexto sao blocos de `tool_result`.
  - e 90,2 % DESSES sao `Read` de `.png` / `.jpg`.

A integral de contexto do lote da Dra. Fulana (soma do contexto vigente a cada
chamada) deu 879 milhoes de bytes, dos quais 93 % vieram de IMAGEM. Um quadro
aberto no turno 4 e' recobrado em todas as ~340 chamadas seguintes: ele nao
custa uma vez, custa ~340. Foi isso, e nao log de script, que produziu os
US$ 283 daquele lote -- o `lote_produzir.py` inteiro, em 30 execucoes, despejou
22 KB, ou 3,5 % de UM PNG de conferencia.

Volume medido em `Lotes/`: PNG = 388 KB por arquivo, JPG = 33 KB por arquivo.
Fator ~12. Para julgar enquadramento, tarja, colisao de legenda ou cor de leak,
a perda do JPG e' invisivel; a diferenca de custo nao e'.

O QUE ESTE SCRIPT NAO FAZ, DE PROPOSITO

Ele e' so' para quadro que ALGUEM OLHA E DECIDE. Nao use para:

  - asset com canal alfa (`gerar_boxes.py` -> `frase{n}.png`, cards RGBA
    consumidos pelo render): JPG nao tem alfa e o card entra com fundo preto;
  - mascara de alfa medida pixel a pixel (`tarja_alpha.py`, `alphaextract`):
    artefato de bloco desloca a borda e falseia o `tarja_offset`;
  - medicao de cor em imagem pequena (`analisar_referencia.py` a 96 px,
    `cenario.py`, `buraco_preto.py`): quantizacao do JPG contamina o RGB medio.

Nesses tres casos PNG esta' certo e continua certo. Ha' `--png` aqui para eles,
mas se voce esta' medindo pixel, provavelmente quer o script proprio, nao este.

ARMADILHA JA' PAGA: nao existe rotulo desenhado no mosaico. `drawtext` sem
fontconfig da segfault neste ambiente (armadilha registrada). A ordem sai
impressa no stdout -- leia ela junto com a imagem.

ARMADILHA 2: se voce trocar a extracao para JPG e algum script vizinho montar
o contact sheet por `glob("*.png")`, o mosaico sai VAZIO sem erro. Ja' existe
esse padrao em `Lotes/2026-07 - Dra. Fulana/quadros.py`. Falha
silenciosa -- confira o numero de entradas que este script imprime.

USO

  # um quadro em 12,4 s
  python scripts/quadro.py v1.mp4 12.4

  # varios instantes do mesmo video -> vira mosaico automaticamente
  python scripts/quadro.py v1.mp4 3 12.4 28 41.5

  # varios videos, o mesmo instante relativo (fracao da duracao)
  python scripts/quadro.py --frac 0.5 v1.mp4 v2.mp4 v3.mp4

  # sem mosaico, arquivos separados
  python scripts/quadro.py --sem-mosaico v1.mp4 3 12.4

  # medicao de pixel (excecao documentada acima)
  python scripts/quadro.py --png --larg 96 v1.mp4 12.4
"""
import argparse
import os
import subprocess
import sys

LARG_PADRAO = 270   # 2160/8: oito colunas 9:16 cabem numa tela
QUALIDADE = 4       # -q:v do mjpeg; 2 e' quase sem perda, 4 ja' e' invisivel aqui
COLUNAS = 6


def _ff(args):
    return subprocess.run(
        ["ffmpeg", "-hide_banner", "-v", "error", "-y"] + args,
        capture_output=True, text=True, encoding="utf-8", errors="replace")


def duracao(src):
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", src],
        capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        return None
    try:
        return float(r.stdout.strip())
    except ValueError:
        return None


def um_quadro(src, t, destino, larg, png):
    """Extrai UM quadro. `-ss` antes do `-i` para busca rapida."""
    extra = [] if png else ["-q:v", str(QUALIDADE)]
    r = _ff(["-ss", f"{t:.3f}", "-i", src, "-frames:v", "1",
             "-vf", f"scale={larg}:-2"] + extra + [destino])
    if r.returncode != 0:
        print(f"  FALHOU {os.path.basename(destino)}: {r.stderr.strip()[:200]}")
        return False
    # Regra 1b do CLAUDE.md: exit 0 nao prova que o arquivo saiu.
    if not os.path.exists(destino) or os.path.getsize(destino) < 1024:
        print(f"  FALHOU {os.path.basename(destino)}: arquivo ausente ou zero byte")
        return False
    return True


def mosaico(imagens, destino, colunas=COLUNAS):
    """Empilha com `tile`. Todas as entradas precisam ter a MESMA dimensao --
    e' o que garante o `scale` fixo da extracao."""
    if not imagens:
        return False
    linhas = (len(imagens) + colunas - 1) // colunas
    cmd = []
    for img in imagens:
        cmd += ["-i", img]
    entradas = "".join(f"[{i}:v]" for i in range(len(imagens)))
    cmd += ["-filter_complex",
            f"{entradas}concat=n={len(imagens)}:v=1:a=0[c];"
            f"[c]tile={colunas}x{linhas}:padding=4:color=white[out]",
            "-map", "[out]", "-frames:v", "1"]
    if not destino.lower().endswith(".png"):
        cmd += ["-q:v", str(QUALIDADE)]
    cmd += [destino]
    r = _ff(cmd)
    if r.returncode != 0:
        print(r.stderr.strip()[:400])
        return False
    return os.path.exists(destino) and os.path.getsize(destino) > 1024


def kb(caminho):
    try:
        return f"{os.path.getsize(caminho) / 1024:.0f} KB"
    except OSError:
        return "?"


def main(argv=None):
    p = argparse.ArgumentParser(add_help=True, description=__doc__.split("\n")[0])
    p.add_argument("alvos", nargs="+",
                   help="um video seguido de instantes em segundos, ou varios "
                        "videos quando usar --frac")
    p.add_argument("--frac", type=float, default=None,
                   help="fracao da duracao (0..1) aplicada a CADA video")
    p.add_argument("--saida", default=None, help="pasta de saida (padrao: ./quadros)")
    p.add_argument("--nome", default="q", help="prefixo dos arquivos")
    p.add_argument("--larg", type=int, default=LARG_PADRAO)
    p.add_argument("--colunas", type=int, default=COLUNAS)
    p.add_argument("--png", action="store_true",
                   help="grava PNG (so' para medicao de pixel -- ver docstring)")
    p.add_argument("--sem-mosaico", action="store_true")
    a = p.parse_args(argv)

    ext = "png" if a.png else "jpg"
    saida = a.saida or os.path.join(os.getcwd(), "quadros")
    os.makedirs(saida, exist_ok=True)

    # Monta a lista (video, instante) nos dois modos.
    tarefas = []
    if a.frac is not None:
        for v in a.alvos:
            d = duracao(v)
            if d is None:
                print(f"  IGNORADO (nao sondei a duracao): {v}")
                continue
            tarefas.append((v, d * a.frac))
    else:
        video = a.alvos[0]
        tempos = a.alvos[1:]
        if not tempos:
            p.error("informe ao menos um instante em segundos, ou use --frac")
        for t in tempos:
            try:
                tarefas.append((video, float(t)))
            except ValueError:
                p.error(f"instante invalido: {t!r}")

    feitos, ordem = [], []
    for i, (src, t) in enumerate(tarefas, 1):
        base = os.path.splitext(os.path.basename(src))[0]
        dest = os.path.join(saida, f"{a.nome}{i:02d}_{base}_{t:.2f}s.{ext}")
        if um_quadro(src, t, dest, a.larg, a.png):
            feitos.append(dest)
            ordem.append(f"{i}. {base} @ {t:.2f}s")

    if not feitos:
        print("nenhum quadro extraido")
        return 1

    if len(feitos) == 1 or a.sem_mosaico:
        print(f"\n{len(feitos)} quadro(s):")
        for f in feitos:
            print(f"  {f}  ({kb(f)})")
        print("\nordem:")
        for o in ordem:
            print(f"  {o}")
        return 0

    destino = os.path.join(saida, f"_{a.nome}_mosaico.{ext}")
    if not mosaico(feitos, destino, a.colunas):
        print("mosaico FALHOU -- os quadros individuais ficaram em " + saida)
        return 1

    soltos = sum(os.path.getsize(f) for f in feitos) / 1024
    print(f"\nmosaico: {destino}  ({kb(destino)})")
    print(f"  {len(feitos)} entradas · soltos somariam {soltos:.0f} KB")
    print("\nordem (nao ha rotulo desenhado -- drawtext segfalha aqui):")
    for o in ordem:
        print(f"  {o}")
    print("\nLEIA SO' O MOSAICO. Os quadros soltos ficam em disco para o caso "
          "de precisar de um especifico depois.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
