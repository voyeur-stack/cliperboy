# -*- coding: utf-8 -*-
"""Sonda de abertura de lote: fps, color_transfer, rotacao, dimensao, duracao, RMS.

Existe porque assumir que o lote e homogeneo ja custou 3 rodadas (fps misto,
lote 1) e 5 pecas entregues lavadas (HLG sem tone-map, lote 3). Le TODO arquivo
que vai virar bruto, inclusive os que sairam de zip.
"""
import json
import os
import re
import subprocess
import sys

FFPROBE = "ffprobe"
FFMPEG = "ffmpeg"


def probe(caminho):
    out = subprocess.run(
        [FFPROBE, "-v", "error", "-print_format", "json",
         "-show_streams", "-show_format", caminho],
        capture_output=True, text=True, encoding="utf-8",
    )
    if out.returncode != 0:
        return {"erro": out.stderr.strip()[:200]}
    d = json.loads(out.stdout)
    v = next((s for s in d["streams"] if s["codec_type"] == "video"), None)
    a = next((s for s in d["streams"] if s["codec_type"] == "audio"), None)
    if v is None:
        return {"erro": "sem stream de video"}

    num, den = (v.get("r_frame_rate") or "0/1").split("/")
    fps = round(float(num) / float(den), 3) if float(den) else 0.0

    rot = 0
    for sd in v.get("side_data_list", []) or []:
        if "rotation" in sd:
            rot = sd["rotation"]

    return {
        "codec": v.get("codec_name"),
        "w": v.get("width"),
        "h": v.get("height"),
        "fps": fps,
        "pix_fmt": v.get("pix_fmt"),
        "color_transfer": v.get("color_transfer") or "",
        "color_primaries": v.get("color_primaries") or "",
        "rotation": rot,
        "dur": round(float(d["format"].get("duration", 0)), 2),
        "audio": (a.get("codec_name") if a else None),
        "ch": (a.get("channels") if a else None),
        "sr": (a.get("sample_rate") if a else None),
    }


def rms_db(caminho):
    """RMS medio do audio. Serve para derivar o limiar de silencio (RMS - 8 dB)."""
    out = subprocess.run(
        [FFMPEG, "-hide_banner", "-i", caminho, "-map", "0:a:0",
         "-af", "volumedetect", "-f", "null", "-"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    m = re.search(r"mean_volume:\s*(-?\d+(?:\.\d+)?) dB", out.stderr)
    p = re.search(r"max_volume:\s*(-?\d+(?:\.\d+)?) dB", out.stderr)
    return (float(m.group(1)) if m else None, float(p.group(1)) if p else None)


def main(pasta):
    arquivos = sorted(
        f for f in os.listdir(pasta)
        if f.lower().endswith((".mp4", ".mov"))
    )
    linhas = []
    for f in arquivos:
        caminho = os.path.join(pasta, f)
        info = probe(caminho)
        if "erro" in info:
            print(f"{f}: ERRO {info['erro']}")
            continue
        media, pico = rms_db(caminho)
        info["rms"] = media
        info["pico"] = pico
        info["arquivo"] = f
        linhas.append(info)
        print(
            f"{f:22s} {info['w']}x{info['h']} rot={info['rotation']:>4} "
            f"{info['fps']:>7} fps  {info['dur']:>7.2f}s  {info['pix_fmt']:<12} "
            f"trc={info['color_transfer'] or '-':<14} "
            f"rms={media} pico={pico} audio={info['audio']}/{info['ch']}ch"
        )
    with open(os.path.join(pasta, "_sonda.json"), "w", encoding="utf-8") as fh:
        json.dump(linhas, fh, ensure_ascii=False, indent=2)
    print(f"\n{len(linhas)} arquivos sondados -> _sonda.json")


if __name__ == "__main__":
    main(sys.argv[1])
