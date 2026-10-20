#!/usr/bin/env python3
"""PRIMEIRA COISA a rodar numa maquina nova: o que falta para o projeto andar.

    python scripts/checar_ambiente.py

Nao instala nada. Confere o que existe, e para o que falta imprime o comando
exato que resolve. Instalar sozinho e' tentador e e' como ambiente quebra: o
Python errado, a build errada do ffmpeg, a versao de CUDA que nao casa com o
driver. Aqui a maquina e' de quem senta nela.

**Sai com 0 mesmo faltando coisa OPCIONAL.** Codigo de saida 1 e' so' para o
que impede QUALQUER trabalho. Um editor que so' vai extrair legenda de peca
pronta nao precisa de musica, nem de light leak, nem do Drive montado -- e o
checador nao pode dizer que a maquina dele esta quebrada.

Isto e' o mesmo principio dos portoes do projeto: dizer o que NAO foi
conferido, e por que, em vez de deixar o silencio parecer aprovacao.
"""
import importlib
import os
import shutil
import subprocess
import sys

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

OK, FALTA, AVISO = "  ok  ", " FALTA", " aviso"
_problemas = []


def linha(estado, nome, detalhe=""):
    print(f"[{estado}] {nome:<34} {detalhe}")


def essencial(nome, detalhe, conserto):
    linha(FALTA, nome, detalhe)
    _problemas.append((nome, conserto))


# --------------------------------------------------------------- Python
print("\n=== Python ===")
v = sys.version_info
if v >= (3, 10):
    linha(OK, "Python", f"{v.major}.{v.minor}.{v.micro}")
else:
    essencial("Python", f"{v.major}.{v.minor} — precisa 3.10+",
              "instale o Python 3.12 em python.org e refaca o pip install")

# --------------------------------------------------------------- ffmpeg
print("\n=== ffmpeg ===")
ff = shutil.which("ffmpeg")
if not ff:
    essencial("ffmpeg", "nao esta no PATH", "winget install Gyan.FFmpeg")
else:
    ver = subprocess.run([ff, "-version"], capture_output=True, text=True)
    linha(OK, "ffmpeg", ver.stdout.split("\n")[0][:58])
    if not shutil.which("ffprobe"):
        essencial("ffprobe", "nao esta no PATH (vem junto do ffmpeg)",
                  "winget install Gyan.FFmpeg")
    # A build "essentials" NAO tem o filtro whisper, e a falha aparece no
    # meio de um lote como erro de filtro -- nao na instalacao.
    filtros = subprocess.run([ff, "-hide_banner", "-filters"],
                             capture_output=True, text=True).stdout
    for f, para_que in [("whisper", "transcricao barata"),
                        ("silencedetect", "deteccao de pausa"),
                        ("loudnorm", "nivel de audio"),
                        ("zscale", "tone-map de bruto HLG"),
                        ("tonemap", "tone-map de bruto HLG")]:
        if f" {f} " in filtros:
            linha(OK, f"filtro {f}", para_que)
        else:
            essencial(f"filtro {f}", f"ausente — {para_que}",
                      "sua build do ffmpeg e' 'essentials'; precisa da FULL: "
                      "winget install Gyan.FFmpeg")

# --------------------------------------------------------------- pacotes
print("\n=== pacotes Python ===")
PACOTES = [
    ("numpy", "numpy", True, "medicao de audio e imagem"),
    ("PIL", "pillow", True, "quadros, boxes, medicao de fonte"),
    ("scipy", "scipy", True, "correlacao (musica, sync)"),
    ("cv2", "opencv-python", True, "leitura de quadro"),
    ("faster_whisper", "faster-whisper", True, "transcricao palavra a palavra"),
    ("rapidocr_onnxruntime", "rapidocr-onnxruntime", False, "OCR — so' na rota com leitura de tela"),
    ("onnxruntime", "onnxruntime", False, "motor do OCR"),
]
faltando_pip = []
for mod, pacote, obrigatorio, para_que in PACOTES:
    try:
        importlib.import_module(mod)
        linha(OK, pacote, para_que)
    except Exception:
        faltando_pip.append(pacote)
        if obrigatorio:
            essencial(pacote, para_que, f"pip install {pacote}")
        else:
            linha(AVISO, pacote, f"opcional — {para_que}")

# --------------------------------------------------------------- GPU
print("\n=== GPU (opcional, mas muda o tempo do lote) ===")
try:
    import glob
    import site
    achou = []
    for sp in site.getsitepackages():
        achou += [os.path.basename(d)
                  for d in glob.glob(os.path.join(sp, "nvidia", "*"))]
    if {"cublas", "cudnn"} <= set(achou):
        linha(OK, "DLLs de CUDA (pip)", " ".join(sorted(set(achou))))
    else:
        linha(AVISO, "DLLs de CUDA (pip)",
              "ausentes — o whisper cai para CPU, ~10x mais lento")
        print("        pip install nvidia-cublas-cu12 nvidia-cuda-nvrtc-cu12 "
              "nvidia-cudnn-cu12")
except Exception as e:
    linha(AVISO, "DLLs de CUDA (pip)", f"nao consegui conferir: {e}")

if shutil.which("nvidia-smi"):
    linha(OK, "driver NVIDIA", "nvidia-smi encontrado")
else:
    linha(AVISO, "driver NVIDIA",
          "sem nvidia-smi — sem GPU o projeto RODA, so' devagar")

# --------------------------------------------------------------- fontes
print("\n=== fontes ===")
for arq, para_que in [("Anton-Regular.ttf", "legenda dos Reels"),
                      ("Hoefler Text Regular.ttf", "box grande")]:
    p = os.path.join(RAIZ, "assets", "fonts", arq)
    if os.path.exists(p):
        linha(OK, arq, f"{para_que} (vem no repositorio)")
    else:
        essencial(arq, para_que,
                  "deveria vir no repositorio — rode `git pull`")

# Lucida Console e' resolvida pelo NOME dentro do .ass, pelo libass, a partir
# das fontes instaladas no sistema. Copiar para assets/ nao adiantaria.
if os.name == "nt" and os.path.exists(r"C:\Windows\Fonts\lucon.ttf"):
    linha(OK, "Lucida Console", "legenda do modo corte+legenda (vem no Windows)")
else:
    linha(AVISO, "Lucida Console",
          "ausente — a legenda do modo corte+legenda sai com OUTRO desenho, "
          "sem aviso")

# ------------------------------------------------- caminhos desta maquina
print("\n=== caminhos desta maquina (caminhos.local.json) ===")
local = os.path.join(RAIZ, "caminhos.local.json")
exemplo = os.path.join(RAIZ, "caminhos.local.exemplo.json")

if not os.path.exists(local) and os.path.exists(exemplo) and sys.stdin.isatty():
    # Primeira configuracao. O padrao e' a pasta compartilhada no Drive; a
    # pergunta existe porque nem toda maquina tem o Drive montado, e porque
    # ler de disco local e' mais rapido para quem quiser copiar o acervo.
    import json
    with open(exemplo, encoding="utf-8") as f:
        base = {k: v for k, v in json.load(f).items() if not k.startswith("_")}
    print("  Esta maquina ainda nao tem `caminhos.local.json`.")
    print("  O padrao do projeto e' a pasta compartilhada `Assets Edicao`:\n")
    for k, v in base.items():
        print(f"    {k:16} {v}")
    r = input("\n  Usar estes caminhos? [S/n] (n = eu digito os meus) ").strip().lower()
    if r in ("", "s", "sim", "y"):
        escolhido = base
    else:
        escolhido = {}
        for k, v in base.items():
            novo = input(f"    {k} [{v}]: ").strip()
            escolhido[k] = novo or v
    escolhido["_leia"] = ("Caminhos desta maquina. Nao sobe para o git. "
                          "Gerado por `scripts/checar_ambiente.py`.")
    with open(local, "w", encoding="utf-8") as f:
        json.dump(escolhido, f, ensure_ascii=False, indent=2)
    print(f"\n  Gravado em {local}\n")

if not os.path.exists(local):
    linha(AVISO, "caminhos.local.json",
          "nao existe — so' faz falta em lote de Reels")
    print(f"        copie `caminhos.local.exemplo.json` para "
          f"`caminhos.local.json` e preencha")
else:
    sys.path.insert(0, RAIZ)
    import config                                        # noqa: E402
    for chave, para_que in [("modelo_whisper", "rota barata de transcricao"),
                            ("leak", "transicoes"),
                            ("musicas", "musica de fundo")]:
        v = config._local(chave)
        if not v:
            linha(AVISO, chave, f"nao preenchido — {para_que}")
        elif os.path.exists(v):
            linha(OK, chave, para_que)
        else:
            linha(AVISO, chave, f"preenchido mas NAO EXISTE: {v}")

# --------------------------------------------------------------- Drive
print("\n=== Google Drive (opcional) ===")
print("  O projeto RODA sem o Drive montado: da' para clonar, rodar os testes")
print("  e transcrever arquivo local. O Drive so' faz falta quando o lote")
print("  aponta para bruto ou entrega que moram nele.")
if os.name == "nt" and os.path.isdir("G:\\"):
    linha(OK, "unidade G:", "montada")
else:
    linha(AVISO, "unidade G:",
          "nao montada — lote que aponta para o Drive vai falhar ao abrir")

# --------------------------------------------------------------- resumo
print("\n" + "=" * 68)
if not _problemas:
    print("Nada essencial faltando. O que estiver como `aviso` acima limita")
    print("um TIPO de trabalho, nao o projeto inteiro.")
    print("\nProximo passo: `python scripts/lotes.py --listar`")
    sys.exit(0)

print(f"{len(_problemas)} item(ns) ESSENCIAL(is) faltando:\n")
for nome, conserto in _problemas:
    print(f"  {nome}")
    print(f"      {conserto}")
if faltando_pip:
    print(f"\nDe uma vez:\n  pip install {' '.join(faltando_pip)}")
print("\nDepois rode este script de novo.")
sys.exit(1)
