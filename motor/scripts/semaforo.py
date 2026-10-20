#!/usr/bin/env python3
"""Junta o que as tres fases mediram e diz, peca por peca, o que olhar.

    python scripts/semaforo.py --lote "2026-08 - Dr. Fulano"

Ate 13/08/2026 nao existia nada assim: `conferir_lote`, `lote_produzir` e
`lote_verificar` imprimiam cada um a sua tabela, em terminais diferentes, e
quem quisesse saber como o lote estava juntava na cabeca. Isso e' o que fez
quatro renders de ZERO BYTE atravessarem a fase 2 (Dra. Fulana,
11/08/2026) e o que faz o operador reler tres logs para achar uma peca.

Este script NAO mede nada. Ele le' o que ja' foi medido, em
`<lote>/relatorio/*.json`, e pinta:

  VERMELHO  portao objetivo reprovou -- nao entrega assim
  AMARELO   regua do padrao fora da faixa -- OLHA, mas nao bloqueia
  VERDE     passou em tudo que sabemos medir

O AMARELO nunca bloqueia, por decisao do operador em 13/08/2026: as reguas de
disfarce/deriva/degrau/P&B ja' eram calculadas pela fase 2 e nunca reprovaram
ninguem. Transforma-las em portao reprovaria peca ja' aprovada e publicada --
foi o que aconteceu na Dra. Fulana quando a regua de folga do texto virou
portao, e a saida foi congelar, nao refazer. Entao aqui elas informam.

Codigo de saida: 1 se houver VERMELHO, 0 se so' houver amarelo ou verde.
"""
import os
import sys
import time

SCR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(SCR))
sys.path.insert(0, SCR)
import config                                            # noqa: E402
import relatorio                                         # noqa: E402

LOTE = config.carregar()

# Reguas do padrao, copiadas de COMECAR-UM-LOTE.md (linhas 112-115). Elas
# vivem la' em texto desde sempre; aqui viram numero para poderem ser lidas.
# Mudou a regua? muda nos dois lugares -- regua em dois enderecos que divergem
# e' pior que regua em nenhum.
REGUAS = {
    "disfarce_pct": (100.0, None, "corte seco na tela"),
    "degrau_mediana": (6.0, 15.0, "degrau invisivel ou solavanco"),
    "deriva_p90": (None, 1.0, "zoom frenetico"),
    "pb_s": (1.6, 2.5, "P&B fora da faixa"),
}


def fora(chave, valor):
    """None quando esta' na faixa (ou quando nao ha' o que medir)."""
    if valor is None:
        return None
    lo, hi, motivo = REGUAS[chave]
    # Sem travessao nem acento no que vai para o terminal: o console do
    # Windows aqui e' cp1252 e devolve '?' no lugar, o que faz a linha do
    # semaforo parecer defeito de dado quando e' so' codificacao.
    if lo is not None and valor < lo:
        return f"{chave}={valor} (min {lo}) - {motivo}"
    if hi is not None and valor > hi:
        return f"{chave}={valor} (max {hi}) - {motivo}"
    return None


pre = relatorio.ler(LOTE, "preflight")
prod = relatorio.ler(LOTE, "producao")
ver = relatorio.ler(LOTE, "verificacao")

print(f"\n  SEMAFORO - {LOTE.nome}")
print(f"  {'=' * 66}")

for nome, dados in (("pre-voo", pre), ("producao (fase 2)", prod),
                    ("verificacao (fase 3)", ver)):
    if dados is None:
        print(f"  {nome:<22} NAO RODOU  (sem relatorio)")
    else:
        print(f"  {nome:<22} rodou em {dados.get('_gravado', '?')}")

# Ausencia de relatorio nao e' aprovacao. Um lote em que a fase 3 nunca rodou
# nao tem peca verde -- tem peca nao medida, que e' outra coisa.
if ver is None and prod is None:
    print("\n  Nada medido ainda. Rode as fases antes do semaforo.\n")
    sys.exit(0)

if pre and pre.get("faltas"):
    print(f"\n  PRE-VOO com {len(pre['faltas'])} pendencia(s):")
    for f in pre["faltas"]:
        print(f"    - {f}")

# indexa a producao por (video, versao) para cruzar com a verificacao
por_video = {}
for p in (prod or {}).get("pecas", []):
    por_video.setdefault(str(p["video"]), []).append(p)

print(f"\n  {'peca':>6}  {'cor':<9} o que olhar")
print(f"  {'-' * 66}")

vermelhos, amarelos, verdes, obsoletas = [], [], [], []
pecas_ver = (ver or {}).get("pecas", [])

for p in pecas_ver:
    rot = p["rotulo"]
    graves = list(p.get("falhas") or [])
    avisos = []

    # medicao vencida: o mp4 e' mais novo que a medicao dele
    arq = os.path.join(LOTE.saida, p.get("arquivo", ""))
    if p.get("_medido") and os.path.exists(arq):
        mudou = time.strftime("%Y-%m-%d %H:%M:%S",
                              time.localtime(os.path.getmtime(arq)))
        if mudou > p["_medido"]:
            avisos.append(f"medida em {p['_medido']}, mas o arquivo e' de {mudou}")
            obsoletas.append(rot)

    # o que a fase 2 mediu para este video entra como AVISO, nunca como grave
    if prod and str(p["video"]) not in por_video:
        # verificada sem medida de producao: era assim que um AMARELO virava
        # VERDE em silencio quando a fase 2 rodava num subconjunto e
        # reescrevia o producao.json so' com as pecas daquela rodada (lote 62,
        # 21/09/2026). O lote_produzir agora mescla; isto e' a rede.
        avisos.append("sem medida da fase 2 (producao.json nao tem esta peca)")
    for m in por_video.get(str(p["video"]), []):
        if not m.get("artefato_ok", True):
            graves.append(f"artefato invalido ({m.get('bytes', 0):,} bytes)")
        if not m.get("render_ok", True):
            graves.append("render falhou")
        for chave in REGUAS:
            aviso = fora(chave, m.get(chave))
            if aviso:
                avisos.append(aviso)
        if m.get("secos"):
            avisos.append(f"cortes secos em {m['secos']}")

    if graves:
        cor, destino = "VERMELHO", vermelhos
    elif avisos:
        cor, destino = "AMARELO", amarelos
    else:
        cor, destino = "VERDE", verdes
    destino.append(rot)

    # um motivo por linha: a primeira versao juntava tudo com "; ", cortava em
    # 120 caracteres e depois repetia os itens embaixo -- o motivo do meio
    # aparecia duas vezes e o do fim sumia.
    itens = graves + avisos
    print(f"  {rot:>6}  {cor:<9} "
          f"{itens[0] if itens else 'passou em tudo que sabemos medir'}")
    for extra in itens[1:]:
        print(f"  {'':>6}  {'':<9} {extra}")

# peca que a fase 2 produziu e a fase 3 nunca mediu e' o buraco classico:
# ela existe na pasta e ninguem olhou.
medidos = {str(p["video"]) for p in pecas_ver}
orfas = [m for v, ms in por_video.items() if v not in medidos for m in ms]
for m in orfas:
    print(f"  {m['video']:>6}  {'AMARELO':<9} produzida mas NAO verificada "
          f"(fase 3 nao cobriu esta peca)")
    amarelos.append(str(m["video"]))

print(f"  {'-' * 66}")
print(f"  {len(verdes)} verde(s) | {len(amarelos)} amarelo(s) | "
      f"{len(vermelhos)} vermelho(s)")

if obsoletas:
    # A pergunta util nao e' "as medicoes sao da mesma hora?" -- rodar o
    # verificador em um video so' e' rotina, e cinco segundos de diferenca nao
    # significam nada. A pergunta e' "o render mudou DEPOIS de eu medir?".
    # Essa tem resposta objetiva: a data do arquivo contra a data da medicao.
    # Sem isso, um "VERDE" de antes do re-render passa por aprovacao do render
    # novo, que e' exatamente o erro que este semaforo existe para impedir.
    print(f"\n  MEDICAO VENCIDA - o arquivo mudou depois de ser medido:")
    for rot in obsoletas:
        print(f"    peca {rot}: rode o verificador de novo antes de entregar")

if vermelhos:
    print(f"\n  NAO ENTREGAR: {', '.join(vermelhos)}")
if amarelos:
    print(f"  OLHAR ANTES DE ENTREGAR: {', '.join(amarelos)}")
if not vermelhos and not amarelos and verdes:
    print("\n  Tudo verde no que e' medivel. O julgamento visual continua seu:")
    print("  ritmo, tremor de movimento e escolha de tomada nao tem medidor.")
print()

sys.exit(1 if vermelhos else 0)
