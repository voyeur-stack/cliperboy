#!/usr/bin/env python3
"""Numeracao de lote: o numero mora em DISCO, nunca no dossie.

**O problema, na palavra do operador (14/08/2026):** *"as vezes to fazendo um
lote em um chat, outro em outro, e assim vai e eles nao se comunicam"*.

**A causa, medida:** nenhum `lote.json` deste projeto tinha campo `numero`. O
numero do lote existia SO' na prosa do dossie do vault de notas. Duas sessoes
abertas ao mesmo tempo leem o mesmo dossie, os dois acham que o proximo e' o
mesmo, e ninguem percebe -- porque as duas estao certas sobre o que leram.
Ja' aconteceu de verdade em 13/08: as oito capturas da Dra. Fulana dizem
"lote 12" porque a numeracao saiu do dossie lido na abertura, enquanto outra
sessao corrigia esse mesmo dossie no meio do dia.

**A correcao e' de endereco, nao de disciplina.** O disco e' a unica coisa que
os chats compartilham em tempo real. Entao:

  - o numero passa a ser campo `numero` dentro de cada `lote.json`;
  - o proximo numero e' `max(numero) + 1` **lido dos arquivos, toda vez**;
  - a alocacao e' atomica (arquivo de trava com O_EXCL), entao dois chats
    pedindo numero ao mesmo tempo recebem numeros diferentes;
  - **nao existe indice.** Um `_registro.json` seria uma SEGUNDA fonte, e
    segunda fonte e' exatamente a doenca que se esta' curando. Varrer 18
    pastas custa milissegundos.

O dossie continua contando a historia do lote. Ele so' deixa de ser o lugar
de onde se tira o numero.

Uso:

    python scripts/lotes.py --listar
    python scripts/lotes.py --novo "Dra. Fulana de Tal"
    python scripts/lotes.py --novo --legendas "Dra. Fulana de Tal"   # so legenda
    python scripts/lotes.py --numerar "2026-08 - Dra. Fulana" 14
    python scripts/lotes.py --fechar 15
"""
import json
import os
import shutil
import sys
import time

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOTES = os.path.join(RAIZ, "Lotes")
TRAVA = os.path.join(LOTES, ".numero.lock")
MODELO = os.path.join(LOTES, "MODELO-lote.json")
MODELO_LEGENDAS = os.path.join(LOTES, "MODELO-lote-legendas.json")


def _carregar(caminho):
    try:
        with open(caminho, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _gravar(caminho, dados):
    tmp = caminho + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=1)
    os.replace(tmp, caminho)          # troca atomica: nunca deixa meio arquivo


def varrer():
    """Todo lote em disco. Fonte unica -- e' isto que os chats compartilham."""
    saida = []
    if not os.path.isdir(LOTES):
        return saida
    for nome in sorted(os.listdir(LOTES)):
        caminho = os.path.join(LOTES, nome, "lote.json")
        if not os.path.isfile(caminho):
            continue
        d = _carregar(caminho) or {}
        saida.append({
            "pasta": nome,
            "caminho": caminho,
            "numero": d.get("numero"),
            "cliente": d.get("cliente", ""),
            "estado": d.get("estado", "aberto" if d.get("numero") else ""),
            "fechado_em": d.get("fechado_em", ""),
        })
    return saida


class Trava:
    """Trava entre PROCESSOS, que e' o caso real: dois chats, dois pythons.

    `O_CREAT | O_EXCL` falha se o arquivo ja' existir -- e' a primitiva certa
    aqui, e nao depende de nenhuma biblioteca de plataforma. Trava velha
    (mais de 30 s) e' considerada abandonada: um chat morto nao pode travar
    o lote de outro.
    """

    def __init__(self, espera=10.0):
        self.espera = espera
        self.fd = None

    def __enter__(self):
        limite = time.time() + self.espera
        while True:
            try:
                if os.path.exists(TRAVA) and \
                        time.time() - os.path.getmtime(TRAVA) > 30:
                    os.remove(TRAVA)
                self.fd = os.open(TRAVA, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(self.fd, str(os.getpid()).encode())
                return self
            except FileExistsError:
                if time.time() > limite:
                    raise SystemExit(
                        "outro chat esta' alocando numero de lote agora. "
                        "Espere alguns segundos e tente de novo.")
                time.sleep(0.2)

    def __exit__(self, *_):
        try:
            if self.fd is not None:
                os.close(self.fd)
            os.remove(TRAVA)
        except OSError:
            pass


def proximo():
    numeros = [l["numero"] for l in varrer() if isinstance(l["numero"], int)]
    return (max(numeros) + 1) if numeros else 1


def listar():
    lotes = varrer()
    com, sem = [l for l in lotes if l["numero"]], [l for l in lotes if not l["numero"]]
    print(f"{'no':>4}  {'estado':10s} {'pasta':44s} cliente")
    print("-" * 100)
    for l in sorted(com, key=lambda x: (x["numero"], x["pasta"])):
        print(f"{l['numero']:>4}  {l['estado'] or '-':10s} "
              f"{l['pasta'][:44]:44s} {l['cliente']}")
    for l in sem:
        print(f"{'?':>4}  {'SEM NUMERO':10s} {l['pasta'][:44]:44s} {l['cliente']}")
    print("-" * 100)
    print(f"{len(com)} numerado(s), {len(sem)} sem numero. "
          f"PROXIMO NUMERO LIVRE: {proximo()}")
    if sem:
        print("\nPastas sem numero nao entram na conta do proximo. Numere com:")
        for l in sem[:5]:
            print(f'  python scripts/lotes.py --numerar "{l["pasta"]}" <n>')
    # Mesma pasta com numero repetido e' NORMAL quando um lote foi entregue em
    # partes (Fulano L1/L2/L3, Fulano pt1/pt2, Fulano + Clínica X).
    repetidos = {}
    for l in com:
        repetidos.setdefault(l["numero"], []).append(l["pasta"])
    multi = {n: p for n, p in repetidos.items() if len(p) > 1}
    if multi:
        print("\nLotes entregues em mais de uma pasta (normal):")
        for n, p in sorted(multi.items()):
            print(f"  {n}: {', '.join(p)}")


def novo(cliente, legendas=False):
    """`legendas=True` parte do MODELO-lote-legendas.json (peca ja' publicada,
    rota so'-whisper): a pasta ganha o sufixo ` legendas`, como no modelo, e
    nao tem `brutos/` -- as pecas moram em `origem`. Antes desta opcao o
    modelo de Reels era copiado e o de legendas tinha de ser mesclado a mao."""
    if not cliente.strip():
        raise SystemExit('uso: --novo [--legendas] "Nome do Cliente"')
    with Trava():
        n = proximo()                      # relido DENTRO da trava, sempre
        sufixo = " legendas" if legendas else ""
        pasta = os.path.join(
            LOTES, f"{time.strftime('%Y-%m')} - {cliente}{sufixo}")
        if os.path.exists(pasta):
            raise SystemExit(f"a pasta ja' existe: {pasta}")
        modelo = MODELO_LEGENDAS if legendas else MODELO
        base = _carregar(modelo)
        if base is None:
            raise SystemExit(f"nao consegui ler o modelo: {modelo}")
        os.makedirs(pasta if legendas else os.path.join(pasta, "brutos"))
        lote = {k: v for k, v in base.items() if not k.startswith("_")}
        lote["numero"] = n
        lote["cliente"] = cliente
        lote["estado"] = "aberto"
        lote["aberto_em"] = time.strftime("%Y-%m-%d %H:%M:%S")
        if not legendas:
            lote["faixas"] = {}
            lote["correcoes"] = {}
        _gravar(os.path.join(pasta, "lote.json"), lote)
    nome = os.path.basename(pasta)
    print(f"LOTE {n} criado: {os.path.relpath(pasta, RAIZ)}")
    print(f"  numero alocado em disco, dentro da trava - "
          f"outro chat que pedir agora recebe {n + 1}.")
    if legendas:
        print("  proximos passos: preencher `origem` e `arquivos` no lote.json,")
        print(f'  depois LOTE="{nome}" python scripts/legendas_prontas/transcrever.py')
    else:
        print("  proximos passos: por os brutos em brutos/ como 1.MOV, 2.MOV, ...")
        print(f'  python scripts/conferir_lote.py --lote "{nome}"')


def numerar(pasta, n):
    caminho = os.path.join(LOTES, pasta, "lote.json")
    d = _carregar(caminho)
    if d is None:
        raise SystemExit(f"nao achei {caminho}")
    with Trava():
        antes = d.get("numero")
        d["numero"] = int(n)
        _gravar(caminho, d)
    print(f"{pasta}: numero {antes} -> {n}")


def fechar(n):
    achou = False
    for l in varrer():
        if l["numero"] == int(n):
            d = _carregar(l["caminho"])
            d["estado"] = "fechado"
            d["fechado_em"] = time.strftime("%Y-%m-%d")
            _gravar(l["caminho"], d)
            print(f"lote {n} ({l['pasta']}): fechado em {d['fechado_em']}")
            achou = True
    if not achou:
        raise SystemExit(f"nenhum lote com numero {n}")


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a or "--listar" in a:
        listar()
    elif "--novo" in a:
        leg = "--legendas" in a
        resto = [x for x in a[a.index("--novo") + 1:] if x != "--legendas"]
        novo(" ".join(resto), legendas=leg)
    elif "--numerar" in a:
        i = a.index("--numerar")
        numerar(a[i + 1], a[i + 2])
    elif "--fechar" in a:
        fechar(a[a.index("--fechar") + 1])
    else:
        raise SystemExit(__doc__.split("Uso:")[1])
