#!/usr/bin/env python3
"""Produz o lote no modo CORTE E LEGENDA: corte confiavel + legenda + box.

E' o `refazer.py` que ficava DENTRO do lote de 03/08, promovido para
`scripts/` em 01/09/2026 -- o resto do modo ja' tinha sido promovido em
10/08, mas o orquestrador ficou para tras, e com ele tres dados de lote
cravados no codigo: `REFEITO`, `range(1, 7)` e as pastas por
`dirname(__file__)`. Sem isto o modo nao rodava em lote nenhum alem
daquele: um lote novo teria de copiar o arquivo e edita-lo.

FASES
  A  corte decidido pelas palavras do faster-whisper, com TRAVA: nenhuma
     borda pode cair dentro de fala (`corte2.conferir`, que mede ENERGIA)
  B  mezanino `{v}_corte.mp4` (1080x1920, crf 12) + `{v}_corte.wav`
  C  transcricao do MEZANINO -> a legenda ja nasce na linha do corte
  D  re-ancoragem das fronteiras no onset de fala (`legenda2`)
  E  render final, com `-c:a copy`: o audio fica bit a bit igual em todas
     as versoes e o corte nao e' re-encodado

QUAIS VIDEOS
    python scripts/corte_legenda/produzir.py --lote "<nome>" 3 4 7 11
Sem numeros, roda as chaves de `refeito`; sem `refeito`, todos os brutos.
Nunca `range(1, 7)`, que era o do lote de 03/08 e sao 6 videos.

COM E SEM BOX
`frases` vazio no lote.json entrega UM arquivo por video, sem box nenhuma,
em `saida/Video {v}.mp4`. Com frases, entrega uma versao por frase em
`saida/Frase {n}/Video {v}.mp4`, que e' a estrutura que o operador pediu em
03/08 (uma subpasta por frase, para o analista pegar o bloco inteiro).

Isto existe porque a box costuma chegar DEPOIS do corte -- foi assim no
lote 33, em que duas frases ja existiam e duas ainda estavam sendo
escritas. A box entra so' na fase E, sobre o mesmo `{v}_corte.mp4` e o
mesmo `{v}.ass`: acrescenta-la depois NAO refaz corte nem legenda.
"""
import json
import os
import subprocess
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)                                  # corte2, legenda2
sys.path.insert(0, os.path.dirname(AQUI))                 # scripts/fw.py

import corte2                                             # noqa: E402
import legenda2                                           # noqa: E402
from lote import (BOXES, BOX_POR_VIDEO, DENOISE, FPS, FRASES,  # noqa: E402
                  REFEITO, SAIDA, TRAB, bruto)

LARG, ALT = 1080, 1920
# A box NAO some: aos BOX_ATE ela SOBE e fica ate o fim do video. Regua
# medida nas 6 pecas aprovadas de `Finalizados/05 08` (02/09/2026), nao
# estimada: a box e' 1080x350 full-width, fica em y 785..1134 (centro exato
# do quadro) ate' o corte, e passa para y 205..554 depois -- deslocamento de
# 580 px para cima, MESMA arte, mesmo tamanho, mesmo texto. Corte SECO de um
# quadro: varrendo a 30 fps nao existe nenhum quadro em posicao intermediaria,
# nem fade, nem easing.
#
# Ate' 02/09/2026 este modo fazia a box SUMIR (`enable='lt(t,5)'`), que era a
# regua do lote de 03/08. O de 05/08 ja' fazia ela subir, e ninguem tinha
# escrito isso em lugar nenhum -- o operador lembrou.
BOX_ATE = 5.0            # instante em que ela sobe
BOX_CENTRO_Y = 959.5     # centro vertical do quadro de 1920
BOX_TOPO_Y = 205         # topo da box depois de subir (medido no 05/08)


def mezanino(v, blocos):
    """Corta o bruto nos blocos e normaliza -- o master de onde tudo sai.

    O `fps={FPS}` vem ANTES do trim de proposito: `trim` de video so' corta
    em quadro e `atrim` de audio corta no instante exato, entao sem a grade
    comum o audio deriva ate' 33 ms por trecho e o erro ACUMULA (100 ms
    medidos no lote de 03/08, em video de 4 trechos). Prender a grade aqui
    tambem e' o que deixa este modo aceitar bruto de 60 fps ao lado de um
    de 30: os dois viram {FPS} antes de qualquer corte.
    """
    src = bruto(v)
    mp4 = os.path.join(TRAB, f"{v}_corte.mp4")
    wav = os.path.join(TRAB, f"{v}_corte.wav")
    n = len(blocos)
    p = [f"[0:v]fps={FPS},split={n}" + "".join(f"[s{i}]" for i in range(n)),
         f"[0:a]asplit={n}" + "".join(f"[t{i}]" for i in range(n))]
    m = []
    for i, (a, b) in enumerate(blocos):
        p.append(f"[s{i}]trim={a}:{b},setpts=PTS-STARTPTS[v{i}]")
        p.append(f"[t{i}]atrim={a}:{b},asetpts=PTS-STARTPTS[a{i}]")
        m.append(f"[v{i}][a{i}]")
    fc = ";".join(p) + ";" + "".join(m) + f"concat=n={n}:v=1:a=1[vc][ac];"
    fc += f"[vc]scale={LARG}:{ALT}:flags=lanczos,setsar=1[vo];"
    # o filtro do lote entra ANTES do loudnorm, para o loudnorm medir o
    # sinal ja tratado -- senao ele normaliza contando com a energia do
    # ruido que vai sair logo em seguida
    f = DENOISE.get(v)
    fc += f"[ac]{f + ',' if f else ''}loudnorm=I=-16:TP=-1.5:LRA=11[ao]"
    r = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", src,
         "-filter_complex", fc, "-map", "[vo]", "-map", "[ao]",
         "-c:v", "libx264", "-preset", "medium", "-crf", "12",
         "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "256k",
         "-ar", "48000", "-ac", "2", mp4], capture_output=True, text=True)
    if r.returncode:
        sys.exit(f"v{v} mezanino falhou: {r.stderr[-500:]}")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", mp4, "-vn",
                    "-ac", "1", "-ar", "16000", wav], check=True)
    # copia COM FOLGA de silencio no fim, so' para transcrever: o whisper
    # descarta conteudo colado na ultima amostra do arquivo. No v5 do lote
    # de 03/08 o "e se cadastre" dos ultimos 0,41 s sumia da legenda. A
    # folga vai no FIM, entao nenhum tempo muda.
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", wav, "-af",
                    "apad=pad_dur=0.8", "-ac", "1", "-ar", "16000",
                    wav.replace(".wav", "_pad.wav")], check=True)
    return mp4, wav


def altura_box(p):
    from PIL import Image
    return Image.open(p).size[1]


def final(v, ass_rel, frase=None):
    """Render final. `frase=None` entrega a versao SEM box nenhuma."""
    mp4 = os.path.join(TRAB, f"{v}_corte.mp4")
    if frase is None:
        dst = os.path.join(SAIDA, f"Vídeo {v}.mp4")
        entradas = ["-i", mp4]
        fc = f"[0:v]ass='{ass_rel}'[vo]"
    else:
        png = os.path.join(BOXES, f"frase{frase}.png")
        if not os.path.exists(png):
            sys.exit(f"v{v}: falta a box {png} -- rode o gerar_boxes.py, ou "
                     f"copie a arte pronta do designer para {BOXES}")
        # uma box por video entrega UM arquivo; varias boxes por video
        # entregam uma subpasta por frase, que e' a estrutura de 03/08
        dst = (os.path.join(SAIDA, f"Vídeo {v}.mp4") if BOX_POR_VIDEO
               else os.path.join(SAIDA, f"Frase {frase}", f"Vídeo {v}.mp4"))
        y = int(round(BOX_CENTRO_Y - altura_box(png) / 2))
        entradas = ["-i", mp4, "-i", png]
        # sem `enable`: ela fica desenhada o video inteiro, e quem muda e' o Y
        fc = (f"[0:v]ass='{ass_rel}'[vl];[1:v]format=rgba[bx];"
              f"[vl][bx]overlay=0:'if(lt(t,{BOX_ATE}),{y},{BOX_TOPO_Y})'[vo]")
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    r = subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *entradas,
         "-filter_complex", fc, "-map", "[vo]", "-map", "0:a",
         "-c:v", "libx264", "-preset", "medium", "-crf", "19",
         "-pix_fmt", "yuv420p", "-profile:v", "high", "-c:a", "copy",
         "-movflags", "+faststart", dst], capture_output=True, text=True)
    if r.returncode:
        onde = "sem box" if frase is None else f"frase {frase}"
        sys.exit(f"v{v} {onde} falhou: {r.stderr[-500:]}")
    return dst


def confere_arquivo(caminho, v):
    """Exit 0 nao e' o mesmo que fez o que eu pedi.

    O `lote_produzir.py` ja' saiu com exit 0, imprimiu CONCLUIDA e deixou
    4 renders de ZERO BYTE (lote da Dra. Fulana, 12/08). E `format=duration`
    tambem ja' mentiu: a queima usa `-c:a copy` e o audio sustenta a duracao
    de um video truncado. A medida que pega truncamento e' o VIDEO contra o
    AUDIO dentro do mesmo arquivo.
    """
    if not os.path.exists(caminho) or os.path.getsize(caminho) < 100_000:
        sys.exit(f"v{v}: {os.path.basename(caminho)} nao existe ou esta' "
                 f"vazio ({os.path.getsize(caminho) if os.path.exists(caminho) else 0} bytes)")
    def sonda(fluxo, campo):
        # um campo por chamada: pedir dois de uma vez devolve na ordem do
        # ffprobe, nao na que eu escrevi, e o desempacotamento troca os dois
        r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", fluxo,
                            "-show_entries", f"stream={campo}",
                            "-of", "default=nw=1:nk=1", caminho],
                           capture_output=True, text=True)
        return r.stdout.strip()
    num, den = (sonda("v:0", "r_frame_rate").split("/") + ["1"])[:2]
    dur_v = int(sonda("v:0", "nb_frames")) / (float(num) / float(den))
    dur_a = float(sonda("a:0", "duration"))
    if abs(dur_v - dur_a) > 0.20:
        sys.exit(f"v{v}: TRUNCADO -- video {dur_v:.2f}s contra audio "
                 f"{dur_a:.2f}s no mesmo arquivo ({os.path.basename(caminho)})")
    return dur_v


if __name__ == "__main__":
    quais = [int(x) for x in sys.argv[1:] if x.isdigit()]
    if not quais:
        quais = sorted(REFEITO) or sorted(
            int(os.path.splitext(f)[0])
            for f in os.listdir(os.path.dirname(bruto(1)))
            if os.path.splitext(f)[0].isdigit())
    if BOX_POR_VIDEO:
        faltam = [v for v in quais if v not in BOX_POR_VIDEO]
        if faltam:
            sys.exit(f"box_por_video nao diz qual frase vai nos videos "
                     f"{faltam}. Escreva no lote.json ou tire-os da lista.")
        print(f"videos: {quais} | uma box por video: "
              f"{ {v: BOX_POR_VIDEO[v] for v in quais} }", flush=True)
    else:
        frases = sorted(FRASES) or [None]
        print(f"videos: {quais} | versoes por video: "
              f"{'sem box' if frases == [None] else frases}", flush=True)

    from fw import transcrever

    for v in quais:
        rem = REFEITO.get(v, ())
        blocos, dur = corte2.blocos_de(v, rem)
        blocos = corte2.ajustar_bordas(v, blocos, rem)
        ruins = corte2.conferir(v, blocos, rem)
        if ruins:
            print(f"v{v}: {len(ruins)} borda(s) de corte DENTRO DE FALA:")
            for nome, t, sa, sb in ruins:
                print(f"   {nome} do bloco em {t:.2f}s, dentro da fala "
                      f"{sa:.2f}-{sb:.2f}")
            sys.exit(f"v{v}: ABORTADO -- o corte cortaria fala")
        total = sum(b - a for a, b in blocos)
        print(f"=== video {v}: {dur:.1f}s -> {total:.1f}s em {len(blocos)} "
              f"trechos (-{dur - total:.1f}s)", flush=True)

        # o mezanino e a transcricao do corte so' dependem do PLANO DE
        # CORTE; mexer na legenda nao os invalida. A assinatura do plano
        # fica gravada, e o cache e' descartado quando ela muda -- legenda
        # de um corte antigo sobre um corte novo ja' passou despercebida.
        # DOIS arquivos, de proposito. O `{v}_plano.json` e' a LISTA de
        # blocos e nada mais: e' dele que o `conferir_bordas.py` deriva as
        # faixas deste modo, e ele nao pode mudar de forma. A assinatura de
        # cache mora separada, e leva o FILTRO junto -- senao trocar o
        # filtro de audio nao invalidaria o mezanino e o render sairia com
        # o audio antigo, em silencio.
        #
        # Ja custou caro: em 01/09/2026 eu juntei os dois num arquivo so',
        # o `conferir_bordas.py` estourou ValueError no primeiro video novo
        # e saiu com codigo 1 -- o MESMO codigo de "achei defeito". O
        # traceback passou por reprovacao e 6 dos 14 videos nao foram
        # olhados por ninguem.
        plano = [[round(a, 3), round(b, 3)] for a, b in blocos]
        assin = json.dumps({"blocos": plano,
                            "filtro": DENOISE.get(v)})
        marca = os.path.join(TRAB, f"{v}_assinatura.json")
        vale = (os.path.exists(marca)
                and open(marca, encoding="utf-8").read() == assin
                and os.path.exists(os.path.join(TRAB, f"{v}_corte.mp4"))
                and os.path.exists(os.path.join(TRAB, f"{v}_corte_fw.json")))
        if vale:
            print("  mezanino e transcricao do corte reaproveitados",
                  flush=True)
        else:
            mezanino(v, blocos)
            confere_arquivo(os.path.join(TRAB, f"{v}_corte.mp4"), v)
            print("  mezanino ok, transcrevendo o CORTE...", flush=True)
            transcrever(os.path.join(TRAB, f"{v}_corte_pad.wav"),
                        os.path.join(TRAB, f"{v}_corte_fw.json"))
            open(marca, "w", encoding="utf-8").write(assin)
            json.dump(plano, open(os.path.join(TRAB, f"{v}_plano.json"),
                                  "w", encoding="utf-8"))

        ass = os.path.join(TRAB, f"{v}.ass")
        n, movidas, npausas, ancorados = legenda2.escrever(v, ass)
        print(f"  {n} eventos; {movidas} de {npausas} fronteiras "
              f"re-ancoradas; {ancorados} eventos adiados ate' o onset",
              flush=True)

        cwd = os.getcwd()
        os.chdir(TRAB)          # o libass resolve o .ass pelo cwd
        try:
            quais_box = ([BOX_POR_VIDEO[v]] if BOX_POR_VIDEO
                         else (sorted(FRASES) or [None]))
            saidas = [final(v, os.path.basename(ass), f)
                      for f in quais_box]
        finally:
            os.chdir(cwd)
        for s in saidas:
            d = confere_arquivo(s, v)
            print(f"  gravado: {os.path.relpath(s, SAIDA)}  ({d:.2f}s)",
                  flush=True)
    print("FIM")
