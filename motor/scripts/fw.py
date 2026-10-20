#!/usr/bin/env python3
"""Transcricao palavra a palavra com faster-whisper (large-v3).

POR QUE TROCAR o filtro `whisper` do ffmpeg, que o projeto ja usava:

O filtro do ffmpeg devolve TOKENS com tempo, nao palavras, e os tempos sao
grosseiros -- o proprio `03-armadilhas.md` ja registrava "erro de timestamp
do whisper, +-100 ms, com sinal aleatorio". Isso era tolerado enquanto os
tempos serviam so' a' legenda (e o `retimar_legenda.py` consertava as
fronteiras de pausa). Neste lote eu usei os mesmos tempos para decidir ONDE
CORTAR, e o erro virou fala comida: o v2 perdeu "Como que esse" e o v5
cortou "doctor" no meio.

O `word_timestamps=True` do faster-whisper alinha por DTW sobre a atencao
cruzada do modelo, o que da fronteira de PALAVRA de verdade, nao de token.

Uso:
    python fw.py <entrada> <saida.json> [--idioma pt]
"""
import json
import os
import sys

MODELO = "large-v3"


def _cuda_no_path():
    """Poe as DLLs de CUDA vindas do pip no caminho de busca.

    Sem isso o modelo CARREGA em `cuda` sem reclamar e so' explode no
    primeiro encode, com 'Library cublas64_12.dll is not found' -- ou seja,
    o try/except em volta do construtor nao protege nada.
    """
    import glob
    import site
    for sp in site.getsitepackages():
        for d in glob.glob(os.path.join(sp, "nvidia", "*", "bin")):
            if hasattr(os, "add_dll_directory"):
                os.add_dll_directory(d)
            os.environ["PATH"] = d + os.pathsep + os.environ["PATH"]


def transcrever(entrada, saida, idioma="pt"):
    _cuda_no_path()
    from faster_whisper import WhisperModel

    def carregar():
        m = WhisperModel(MODELO, device="cuda", compute_type="int8_float16")
        # forca um encode de verdade: e' onde a falta de cublas aparece
        next(iter(m.transcribe(entrada, language=idioma, beam_size=1)[0]))
        return m

    try:
        m, onde = carregar(), "cuda"
    except Exception as e:
        print(f"  cuda indisponivel ({type(e).__name__}), indo de cpu: "
              f"{str(e)[:100]}", flush=True)
        m, onde = WhisperModel(MODELO, device="cpu", compute_type="int8"), "cpu"

    segmentos, info = m.transcribe(
        entrada,
        language=idioma,
        word_timestamps=True,
        beam_size=5,
        # sem VAD: tropeco, gaguejo e direcao de camera ("Segura ai, Fulano")
        # tem de APARECER -- e' lendo isso que se decide o corte
        vad_filter=False,
        # sem condicionar no texto anterior: e' o que faz o whisper
        # "limpar" tomada refeita, transcrevendo so' a versao boa
        condition_on_previous_text=False,
    )

    dados = {"idioma": info.language, "onde": onde, "segmentos": []}
    for s in segmentos:
        dados["segmentos"].append({
            "ini": round(s.start, 3),
            "fim": round(s.end, 3),
            "texto": s.text.strip(),
            "palavras": [{"ini": round(w.start, 3), "fim": round(w.end, 3),
                          "txt": w.word.strip(), "prob": round(w.probability, 3)}
                         for w in (s.words or [])],
        })
        print(f"  [{s.start:7.2f} -> {s.end:7.2f}] {s.text.strip()[:78]}",
              flush=True)

    os.makedirs(os.path.dirname(os.path.abspath(saida)), exist_ok=True)
    with open(saida, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=1)
    n = sum(len(s["palavras"]) for s in dados["segmentos"])
    print(f"  -> {len(dados['segmentos'])} segmentos, {n} palavras ({onde})")
    return dados


if __name__ == "__main__":
    idioma = "pt"
    if "--idioma" in sys.argv:
        i = sys.argv.index("--idioma")
        idioma = sys.argv[i + 1]
        del sys.argv[i:i + 2]
    transcrever(sys.argv[1], sys.argv[2], idioma)
