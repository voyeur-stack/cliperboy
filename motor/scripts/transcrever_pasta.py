#!/usr/bin/env python3
"""Transcreve TODO .mov/.mp4 de uma arvore com faster-whisper large-v3.

Serve ao pedido "transcreve tudo antes de decidir o que editar": bruto de
lote novo, depoimento, b-roll -- material que ainda nao virou lote e por
isso nao tem `lote.json`.

Tres travas, todas por defeito ja visto nesta maquina:

* o wav e' conferido contra a duracao do video (o Drive trunca e o ffmpeg
  devolve codigo 0);
* a transcricao roda em PROCESSO FILHO, em blocos, porque sem VRAM o CUDA
  aborta o processo nativo sem traceback e levaria a fila junto;
* `--retomar` pula o que ja tem `_fw.json` valido, entao rodar de novo
  depois de uma queda continua de onde parou.

Uso:
    python scripts/transcrever_pasta.py <pasta> <saida> [--bloco 8]
    python scripts/transcrever_pasta.py --um <wav> <json>   # interno
"""
import json
import os
import subprocess
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)

EXT = (".mov", ".mp4", ".m4v", ".mkv", ".avi", ".wav", ".m4a", ".mp3")


def duracao(p):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries",
                        "format=duration", "-of", "default=nw=1:nk=1", p],
                       capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def wav(video, destino):
    for tentativa in (1, 2, 3):
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", video,
                        "-vn", "-ac", "1", "-ar", "16000", destino],
                       check=True)
        dv, dw = duracao(video), duracao(destino)
        if dv - dw <= 0.5:
            return
        print(f"  wav truncado ({dw:.1f}s de {dv:.1f}s), tentativa {tentativa}",
              flush=True)
    raise RuntimeError(f"nao consegui extrair o audio inteiro de {video}")


def valido(p):
    if not os.path.exists(p) or os.path.getsize(p) < 40:
        return False
    try:
        json.load(open(p, encoding="utf8"))
        return True
    except Exception:
        return False


def main():
    if sys.argv[1] == "--um":
        from fw import transcrever
        for par in sys.argv[2:]:
            w, j = par.split("|")
            print(f"  ~ {os.path.basename(j)}", flush=True)
            transcrever(w, j, "pt")
        return

    raiz, saida = sys.argv[1], sys.argv[2]
    bloco = int(sys.argv[sys.argv.index("--bloco") + 1]) if "--bloco" in sys.argv else 8
    os.makedirs(saida, exist_ok=True)
    trab = os.path.join(saida, "_wav")
    os.makedirs(trab, exist_ok=True)

    fontes = []
    for dirpath, _, nomes in os.walk(raiz):
        for n in sorted(nomes):
            if n.lower().endswith(EXT):
                fontes.append(os.path.join(dirpath, n))
    fontes.sort()

    # nome plano, unico, legivel: <pasta pai>__<arquivo>
    pend = []
    for f in fontes:
        rel = os.path.relpath(f, raiz)
        ap = rel.replace("\\", "__").replace("/", "__").rsplit(".", 1)[0]
        ap = "".join(c if c.isalnum() or c in " _-.," else "_" for c in ap)
        j = os.path.join(saida, ap + "_fw.json")
        if valido(j):
            continue
        pend.append((f, os.path.join(trab, ap + ".wav"), j))

    print(f"{len(fontes)} arquivos, {len(pend)} a transcrever", flush=True)

    for i, (f, w, j) in enumerate(pend, 1):
        if not os.path.exists(w) or duracao(w) < 0.05:
            print(f"[{i}/{len(pend)}] wav {os.path.basename(f)}", flush=True)
            wav(f, w)

    for k in range(0, len(pend), bloco):
        lote = pend[k:k + bloco]
        print(f"--- bloco {k // bloco + 1}: {len(lote)} arquivos", flush=True)
        args = [sys.executable, os.path.abspath(__file__), "--um"]
        args += [f"{w}|{j}" for _, w, j in lote]
        r = subprocess.run(args)
        for _, _, j in lote:
            if not valido(j):
                print(f"  !! FALHOU (exit {r.returncode}): "
                      f"{os.path.basename(j)}", flush=True)

    faltam = [j for _, _, j in pend if not valido(j)]
    print(f"\nOK. faltam {len(faltam)}", flush=True)
    sys.exit(1 if faltam else 0)


if __name__ == "__main__":
    main()
