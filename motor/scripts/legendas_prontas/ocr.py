#!/usr/bin/env python3
"""Le a legenda QUEIMADA na tela, amostrando um quadro por palavra falada.

POR QUE ASSIM, e nao varrendo o video a 4 fps:

1. Custo. O OCR aqui e' CPU (o onnxruntime desta maquina so' tem
   CPUExecutionProvider) e custa ~1 s por quadro mesmo em faixa recortada.
   A 4 fps os 16 videos dariam ~4000 quadros. Amostrando pelo tempo das
   PALAVRAS dao ~1600 -- e nenhuma amostra cai em buraco entre legendas.

2. Precisao de tempo. Varredura uniforme so' sabe a fronteira dentro do
   passo da amostra. Aqui o tempo nao vem do OCR: vem do `word_timestamps`
   do faster-whisper, que e' fronteira de palavra de verdade. O OCR decide
   O QUE esta escrito e COMO esta agrupado; o whisper decide QUANDO.

O que o OCR NAO resolve: o modelo de reconhecimento e' o latino do
PP-OCR e nao tem o alfabeto acentuado completo -- ele devolve "consistencia"
e "possivel". Por isso a grafia final sai do whisper, casada palavra a
palavra com a leitura da tela SEM acento. Onde as letras divergem, a tela
vence e o caso vai para revisao (`_ocr_divergencia.txt`).
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time
import unicodedata

import cv2
import numpy as np

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
from lista import FALTANDO, caminho, trab  # noqa: E402

from rapidocr_onnxruntime import RapidOCR  # noqa: E402

# faixa varrida: a legenda deste cliente nao mora sempre embaixo -- no video
# de tela dividida ela sobe para ~43 % da altura. 30 %-98 % cobre os dois.
FAIXA = (0.30, 0.98)
CONF = 0.60
# a legenda e' centralizada; a marca d'agua do canto inferior esquerdo nao e'.
# Sem este filtro ela entra como 'LBIVE'/'200RAM' no meio do texto.
CENTRO = (0.33, 0.67)
# a grade de quadros e' descartavel e pesa ~1 GB no lote inteiro: vai para o
# scratchpad da sessao, nao para dentro do projeto (que sincroniza).
QUADROS = os.environ.get("OCR_QUADROS") or trab("_quadros")

# quantas threads o OCR pode tomar. Sem limite ele come os 12 logicos desta
# maquina e o PC para -- e este lote roda ao lado do operador trabalhando.
NUCLEOS = int(os.environ.get("OCR_THREADS", "0"))
try:
    ocr = RapidOCR(intra_op_num_threads=NUCLEOS) if NUCLEOS else RapidOCR()
except TypeError:
    ocr = RapidOCR()


def sem_acento(s):
    s = unicodedata.normalize("NFD", s)
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def chave(s):
    """Forma comparavel: sem acento, sem pontuacao, minuscula."""
    return re.sub(r"[^a-z0-9 ]", "", sem_acento(s).lower()).strip()


def sondar(video):
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height,r_frame_rate",
         "-of", "default=nw=1:nk=1", video],
        capture_output=True, text=True, check=True).stdout.split()
    num, den = r[2].split("/")
    return int(r[0]), int(r[1]), int(num) / int(den)


def quadro(video, t):
    """Quadro BGR unico no instante t, ja recortado na faixa da legenda.

    Vem por stdout porque `cv2.imread`/`VideoCapture` devolvem None em
    caminho com acento no Windows, e o caminho deste projeto tem "Edicao".
    So' para sonda/teste -- o lote usa `quadros`, que decodifica uma vez so'.
    """
    png = subprocess.run(
        ["ffmpeg", "-v", "error", "-ss", f"{t:.3f}", "-i", video,
         "-frames:v", "1", "-f", "image2pipe", "-vcodec", "png", "-"],
        capture_output=True, check=True).stdout
    img = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        return None
    h = img.shape[0]
    return img[int(h * FAIXA[0]):int(h * FAIXA[1])]


GRADE = 5  # quadros por segundo da grade de amostragem


def extrair(video, destino):
    """Descarrega a faixa da legenda em JPEG, a GRADE fps, numa passada so'.

    Um `ffmpeg -ss` por amostra custava ~6 s aqui: o arquivo mora no stream
    do Google Drive (G:) e cada busca paga a latencia de novo. Selecionar os
    ~150 quadros exatos num filtro `select=eq(n\\,X)+...` tambem nao serve --
    com essa quantidade de termos o ffmpeg morre com ENOMEM ao compilar a
    expressao. Entao: uma passada, grade fixa, recorte feito dentro do
    ffmpeg (nao trafega quadro inteiro), e o disco no lugar da RAM.
    """
    w, h, _ = sondar(video)
    y0 = int(h * FAIXA[0]) // 2 * 2
    y1 = int(h * FAIXA[1]) // 2 * 2
    os.makedirs(destino, exist_ok=True)
    for f in os.listdir(destino):
        os.remove(os.path.join(destino, f))
    subprocess.run(
        ["ffmpeg", "-v", "error", "-i", video,
         "-vf", f"fps={GRADE},crop={w}:{y1 - y0}:0:{y0}",
         "-q:v", "2", os.path.join(destino, "%05d.jpg")], check=True)
    return len(os.listdir(destino))


def carregar(destino, k):
    """Le o quadro k da grade (1-based no disco). None se nao existir."""
    p = os.path.join(destino, f"{k + 1:05d}.jpg")
    if not os.path.exists(p):
        return None
    return cv2.imdecode(np.fromfile(p, np.uint8), cv2.IMREAD_COLOR)


def ler(img):
    """Linhas centralizadas do quadro, de cima para baixo.

    Devolve LINHA a LINHA, com y e altura, e nao um texto so'. A legenda
    deste cliente e' ACUMULATIVA: a frase se monta palavra a palavra e quebra
    em linhas de ~24 caracteres, e e' a LINHA que vira evento no .srt
    aprovado. Juntar tudo numa string apagaria justamente a fronteira que o
    .srt precisa.
    """
    if img is None:
        return []
    r = ocr(img)[0] or []
    larg = img.shape[1]
    linhas = []
    for cx, txt, conf in r:
        t = re.sub(r"\s+", " ", txt).strip()
        if conf < CONF or not t:
            continue
        xs = [p[0] for p in cx]
        ys = [p[1] for p in cx]
        meio = (min(xs) + max(xs)) / 2 / larg
        if not (CENTRO[0] <= meio <= CENTRO[1]):
            continue
        linhas.append({"y": round(min(ys), 1),
                       "h": round(max(ys) - min(ys), 1),
                       "txt": t, "conf": round(conf, 3)})
    linhas.sort(key=lambda x: x["y"])
    return linhas


def palavras(ap):
    # o arquivo pode ter acabado de aparecer e ainda estar sendo escrito
    for _ in range(30):
        try:
            d = json.load(open(trab(f"{ap}_fw.json"), encoding="utf-8"))
            break
        except json.JSONDecodeError:
            time.sleep(2)
    else:
        raise RuntimeError(f"{ap}_fw.json ilegivel")
    out = []
    for s in d["segmentos"]:
        for w in s["palavras"]:
            out.append(w)
    return out


def processar(nome, ap):
    v = caminho(nome)
    ws = palavras(ap)
    tempos = [(w["ini"] + w["fim"]) / 2 for w in ws]
    quadros = os.path.join(QUADROS, ap)
    n = extrair(v, quadros)
    print(f"== {ap}: {len(ws)} palavras, {n} quadros na grade", flush=True)
    lidos, cache = [], {}
    for i, (w, t) in enumerate(zip(ws, tempos)):
        k = min(max(int(round(t * GRADE)), 0), n - 1)
        if k not in cache:
            cache[k] = ler(carregar(quadros, k))
        lidos.append({"i": i, "t": round(t, 3), "k": k, "linhas": cache[k],
                      "palavra": w["txt"], "ini": w["ini"], "fim": w["fim"]})
        if (i + 1) % 25 == 0:
            print(f"   {i+1}/{len(ws)}", flush=True)
    with open(trab(f"{ap}_ocr.json"), "w", encoding="utf-8") as f:
        json.dump(lidos, f, ensure_ascii=False, indent=1)
    shutil.rmtree(quadros, ignore_errors=True)
    vazios = sum(1 for x in lidos if not x["linhas"])
    distintos = {ln["txt"] for x in lidos for ln in x["linhas"]}
    print(f"   -> {len(distintos)} linhas distintas, {vazios} quadros sem texto")


if __name__ == "__main__":
    alvos = sys.argv[1:]
    from lista import GABARITOS
    for nome, ap in GABARITOS + FALTANDO:
        if alvos and ap not in alvos:
            continue
        if os.path.exists(trab(f"{ap}_ocr.json")):
            print(f"== {ap}: ja existe, pulando")
            continue
        # o OCR (CPU) roda junto com a transcricao (GPU); espera o video da vez
        espera = 0
        while not os.path.exists(trab(f"{ap}_fw.json")) and espera < 3600:
            time.sleep(10)
            espera += 10
        processar(nome, ap)
