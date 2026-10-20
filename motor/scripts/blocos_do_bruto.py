#!/usr/bin/env python3
"""Lista os BLOCOS DE FALA de um bruto, com texto e nivel, para escolher tomada.

POR QUE ISTO EXISTE (lote Clínica X, 04/09/2026):

Montar `faixas` a partir dos SEGMENTOS do faster-whisper falha neste tipo de
cliente. O medico grava cada frase 2-3 vezes seguidas, e o whisper cola duas
ou tres tomadas dentro de um mesmo segmento -- com texto limpo, sem nenhum
sinal de que ali ha repeticao. No lote Fulano isso produziu 47 faixas erradas
na primeira montagem e, mesmo depois de duas rodadas de correcao pontual, o
corte ainda entregava a mesma frase TRES vezes no v3 e no v4.

O que este script faz diferente: reagrupa as PALAVRAS (que tem tempo proprio e
confiavel, alinhadas por DTW) em blocos separados por um vao real, e mede o
NIVEL de cada bloco. Nesse cliente a tomada descartada sai ~16 dB abaixo da
boa, entao nivel + texto juntos decidem o que os segmentos do whisper escondem.

O vao que separa TOMADA de PAUSA nao e universal: 0,35 s dava falso positivo
em 75 de 88 faixas aqui, e 0,60 s acertou. E parametro, nao constante.

Uso:
    python blocos_do_bruto.py <N_bruto_fw.json> <bruto.MOV> [--vao 0.6]
"""
import json
import subprocess
import sys


def blocos(palavras, vao):
    """Agrupa palavras consecutivas; vao maior que `vao` abre bloco novo."""
    out = []
    for w in palavras:
        if out and w["ini"] - out[-1][-1]["fim"] <= vao:
            out[-1].append(w)
        else:
            out.append([w])
    return out


def nivel(caminho, ini, fim):
    """p50 do RMS em janelas de 30 ms. Mediana, nao media: a media de um bloco
    com pausa interna e puxada pelo silencio e nivela tomada boa com ruim."""
    cmd = ["ffmpeg", "-v", "error", "-ss", f"{ini:.3f}", "-to", f"{fim:.3f}",
           "-i", caminho, "-vn", "-ac", "1", "-ar", "16000",
           "-af", "astats=metadata=1:reset=1:length=0.03,"
                  "ametadata=print:key=lavfi.astats.Overall.RMS_level:file=-",
           "-f", "null", "-"]
    txt = subprocess.run(cmd, capture_output=True, text=True).stdout
    vals = []
    for linha in txt.splitlines():
        if "=" in linha:
            try:
                v = float(linha.split("=")[-1])
            except ValueError:
                continue
            if v > -120:
                vals.append(v)
    if not vals:
        return float("nan")
    vals.sort()
    return vals[len(vals) // 2]


def inicio_do_audio(caminho):
    """`start_time` do stream de audio no container.

    Celular entrega audio comecando DEPOIS do video (lote 78, Dr. Fulano, 06/10/2026: 0,736 s no v3 e 0,741 s no v4). O `_fw.json` vem do
    audio extraido, entao esta no relogio do AUDIO; o `-ss` do `nivel()` e as
    `faixas` do lote.json estao no relogio do .MOV. Sem somar isto, a janela
    medida caia 0,74 s antes da fala e o CTA do v3 saiu a -50 dB (era -22 dB),
    lendo como "fala inaudivel / alucinacao" o que era fala normal."""
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0",
                        "-show_entries", "stream=start_time", "-of", "csv=p=0",
                        caminho], capture_output=True, text=True)
    try:
        return max(0.0, float(r.stdout.strip()))
    except ValueError:
        return 0.0


def main():
    fw, bruto = sys.argv[1], sys.argv[2]
    vao = 0.6
    if "--vao" in sys.argv:
        vao = float(sys.argv[sys.argv.index("--vao") + 1])
    d = json.load(open(fw, encoding="utf-8"))
    palavras = [w for s in d["segmentos"] for w in s["palavras"]]
    desl = inicio_do_audio(bruto)
    if desl > 0.02:
        print(f"# audio comeca em {desl:.3f}s: tempos abaixo ja no relogio do "
              f".MOV (o das faixas), = fw.json + {desl:.3f}")
    for b in blocos(palavras, vao):
        ini, fim = b[0]["ini"] + desl, b[-1]["fim"] + desl
        if fim - ini < 0.25:
            continue
        texto = " ".join(w["txt"] for w in b)
        print(f"{ini:7.2f} {fim:7.2f} {fim-ini:5.2f}s "
              f"{nivel(bruto, ini, fim):6.1f}dB  {texto}")


if __name__ == "__main__":
    main()
