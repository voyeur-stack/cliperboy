#!/usr/bin/env python3
"""Insere a VINHETA de marca no meio de uma peca ja renderizada.

    [ 1a frase ]  [ vinheta ]  [ o resto do video ]

Estrutura decidida pelo operador em 14/08/2026 (lote da Dra. Fulana).
Nada e' copiado e nada se repete: a peca e' partida num ponto e a vinheta
entra ali.

    *(Versao anterior, REPROVADA por ele no mesmo dia: o gancho era um
    RECORTE de qualquer ponto do video, colado na frente, e a frase era
    ouvida duas vezes. Reprovou por quatro motivos de uma vez -- trecho ruim,
    corte picado, audio descasado da imagem e a estrutura em si. Esta versao
    e' mais simples e nao tem como picotar a entrada: a entrada e' o comeco
    do video, que ja esta certo.)*

O PONTO DE CORTE E' MEDIDO NA ENERGIA, nunca no relogio do whisper. Onde a
frase fecha em interrogacao o whisper encerra a ultima palavra ~350 ms cedo
demais (medido nos videos 1 e 4 deste lote) e cortar pelo numero dele
decapita a silaba final -- foi exatamente o defeito da versao reprovada.
Este script recebe o instante pronto; quem mede e' quem preenche
`vinheta_em` no lote.json.

MUSICA -- por que ela e' mixada aqui e nao no render:

O operador decidiu que a musica de fundo comeca SO' DEPOIS da vinheta. O
render nao sabe em que instante isso e' (a vinheta so entra depois dele), e
mixagem nao se desfaz. Entao, em lote com vinheta, o `lote_produzir.py`
renderiza SEM musica e ela entra aqui, com `adelay` ate o inicio do corpo.

Uso:
    python montar_abertura.py <pronto.mp4> <vinheta.mov> <corte_s> <saida.mp4>
                              [musica.wav]
"""
import json
import os
import subprocess
import sys

pronto, vinheta, corte, saida = sys.argv[1:5]
corte = float(corte)
musica = sys.argv[5] if len(sys.argv) > 5 and sys.argv[5] else None


def sondar(arq, campos="width,height,r_frame_rate,nb_frames"):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                        "-show_entries", f"stream={campos}",
                        "-show_entries", "format=duration",
                        "-of", "json", arq], capture_output=True, text=True)
    if r.returncode:
        sys.exit(f"ABORTADO: ffprobe falhou em {arq}\n{r.stderr[:300]}")
    d = json.loads(r.stdout)
    out = dict(d["streams"][0]) if d.get("streams") else {}
    out["duration"] = float(d["format"]["duration"])
    return out


for arq in [pronto, vinheta] + ([musica] if musica else []):
    if not os.path.exists(arq):
        sys.exit(f"ABORTADO: nao existe -> {arq}")

p, vi = sondar(pronto), sondar(vinheta)
LARG, ALT = int(p["width"]), int(p["height"])
num, den = (int(x) for x in p["r_frame_rate"].split("/"))
FPS = num / den

if not 0 < corte < p["duration"]:
    sys.exit(f"ABORTADO: corte em {corte:.3f}s e a peca tem "
             f"{p['duration']:.3f}s")

# O corte cai na GRADE DE QUADROS. Fora da grade, o concat arredonda por
# conta propria e a emenda ganha alguns ms -- e' o mesmo mecanismo que ja
# somou 1,11 s de deriva neste projeto quando se emendou pedaco a pedaco.
q = round(corte * FPS) / FPS
inicio_corpo = q + vi["duration"]

print(f"peca      {LARG}x{ALT} @ {FPS:.3f} fps, {p['duration']:.3f}s")
print(f"vinheta   {vi['width']}x{vi['height']}, {vi['duration']:.3f}s")
print(f"corte     {q:.3f}s"
      + ("" if abs(q - corte) < 1e-6
         else f"  (pedido {corte:.3f}, ajustado a grade de {1000/FPS:.1f} ms)"))
print(f"corpo     comeca em {inicio_corpo:.3f}s da peca montada")
if q > 9.0:
    print(f"      AVISO: {q:.1f}s de fala antes da vinheta. Somando a "
          f"vinheta, o video 'comeca de fato' em {inicio_corpo:.1f}s.")

# A vinheta e' 720x1280 e a peca 1080x1920: sobe por escala, sem recorte (a
# proporcao e' a mesma). `setsar` explicito porque concat com SAR diferente
# falha, e a mensagem do ffmpeg nao diz que o problema e' esse.
esc = (f"scale={LARG}:{ALT}:flags=lanczos,setsar=1,fps={FPS:.6f},"
       f"format=yuv420p")
FMT_A = ("aformat=sample_fmts=fltp:sample_rates=48000:"
         "channel_layouts=stereo")

# `asplit` explicito: [0:a] e' usado DUAS vezes (antes e depois do corte) e
# um rotulo de saida se consome uma vez so. Sem isto o ffmpeg nao reclama do
# jeito que se espera -- ele produz audio derivando, com exit 0. Aconteceu
# aqui em 14/08/2026 e custou uma peca inteira montada errada.
partes = [
    f"[0:v]split=2[va][vb]",
    f"[0:a]{FMT_A},asplit=2[aa][ab]",
    f"[va]trim=0:{q:.6f},setpts=PTS-STARTPTS,setsar=1,format=yuv420p[v1]",
    f"[aa]atrim=0:{q:.6f},asetpts=PTS-STARTPTS[a1]",
    f"[1:v]{esc}[v2]",
    f"[1:a]{FMT_A}[a2]",
    f"[vb]trim={q:.6f},setpts=PTS-STARTPTS,setsar=1,format=yuv420p[v3]",
    f"[ab]atrim={q:.6f},asetpts=PTS-STARTPTS[a3]",
    f"[v1][a1][v2][a2][v3][a3]concat=n=3:v=1:a=1[v][afim]",
]
if musica:
    # A musica ja vem remixada para a duracao do CORPO e no nivel certo
    # (musica.py). Aqui ela so' e' atrasada ate o instante em que o corpo
    # comeca. `all=1` porque adelay sem isso atrasa so' o primeiro canal --
    # o audio sai com um canal adiantado e ninguem ouve isso num medidor.
    partes.append(f"[2:a]{FMT_A},adelay={int(round(inicio_corpo*1000))}:all=1"
                  f"[amus]")
    partes.append("[afim][amus]amix=inputs=2:duration=first:normalize=0,"
                  "alimiter=limit=0.89:level=disabled[a]")
    mapa_a = "[a]"
else:
    mapa_a = "[afim]"

# MESMO encoder da peca. Se a montagem encodar diferente do render, a
# vinheta e o corpo saem com tratamento de imagem diferente dentro do mesmo
# arquivo -- e isso aparece na borda da legenda, que e' fina.
kw = {}
enc = ["-c:v", "libx264", "-preset", "medium", "-crf", "19",
       "-profile:v", "high", "-pix_fmt", "yuv420p"]
try:
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    import config
    enc = config.encoder_video()
    kw = {"creationflags": config.PRIORIDADE_BAIXA}
    print(f"encoder   {config.encoder_nome()}")
except Exception:
    pass

cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error",
       "-i", pronto, "-i", vinheta] + (["-i", musica] if musica else []) + [
       "-filter_complex", ";".join(partes), "-map", "[v]", "-map", mapa_a] + enc + [
       "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
       "-movflags", "+faststart", "-y", saida]

r = subprocess.run(cmd, capture_output=True, text=True, **kw)
if r.returncode:
    sys.exit(f"ABORTADO: ffmpeg falhou\n{r.stderr[-800:]}")

# REGRA 1b: exit 0 nao e' o mesmo que "fez o que eu pedi". Este projeto ja'
# teve 4 renders de ZERO BYTE saindo com exit 0 e a palavra CONCLUIDA no log.
if not os.path.exists(saida) or os.path.getsize(saida) < 100_000:
    sys.exit(f"ABORTADO: saida ausente ou pequena demais -> {saida}")

s = sondar(saida)
esperado = p["duration"] + vi["duration"]
delta = (s["duration"] - esperado) * 1000
print(f"saida     {s['width']}x{s['height']}, {s['duration']:.3f}s "
      f"(previsto {esperado:.3f}s, delta {delta:+.0f} ms)")
# "Diferenca entre previsto e real e' defeito ate prova em contrario" --
# regra deste projeto desde o lote do Dr. Fulano, onde 2,23 s de diferenca
# foram descartados como irrelevantes e eram 2,6 s de TELA PRETA na peca.
if abs(delta) > 100:
    sys.exit(f"ABORTADO: a duracao final erra {delta:+.0f} ms contra o "
             f"previsto. Defeito ate prova em contrario -- nao publique sem "
             f"entender de onde vem.")
print(f"OK -> {saida}")
