# -*- coding: utf-8 -*-
"""Acha TOMADA REFEITA: vao entre palavras com fala dentro, e palavra ESTICADA.

Promovido de dentro do lote para `scripts/analise/` em 12/08/2026, no lote da
Dra. Fulana. Ate' aqui ele vivia solto em TRES pastas de lote (Fulano,
Agencia, Fulano) e era reescrito a mao a cada vez.

**A promocao E' o conserto.** O vault registrava o alarme de tomada refeita como
"ignorado 3 vezes", e na terceira o script NEM CHEGOU A SER EXECUTADO. Ler isso
como falta de disciplina e' diagnostico errado: o detector nao era ferramenta do
projeto, entao usa-lo dependia de eu lembrar que ele existia e de achar em qual
lote estava a copia menos velha. Ferramenta que mora dentro de um lote nao e'
ferramenta, e' rascunho.

E a copia que eu teria achado estava com o caminho do bruto fixo em `.MOV`. O
lote da Fulano e' `.MP4`: rodada como estava, ela imprimiria "falta arquivo" nos
seis videos e eu marcaria o alarme como limpo pela quarta vez. Por isso aqui o
caminho vem de `LOTE.bruto_de(v)`, que ja resolve a extensao.

O modo de falha que ele existe para pegar (§H do projeto): a pessoa erra, repete
a frase, e o modelo transcreve **so' a versao limpa**. O texto nunca denuncia —
as duas passadas concordam, porque as duas normalizam. Quem denuncia e' o
RELOGIO, e a energia do audio decide se aquele vao tem fala.

Le o artefato que a fase 1 REALMENTE produz hoje: `trabalho/N_palavras.json`
(JSONL, um token por linha, tempos em MILISSEGUNDOS) medido contra o audio do
corte, `trabalho/N_corte.wav`. A copia antiga esperava `N_fw.json`, que este
pipeline nao gera mais -- e por isso ela imprimia "falta arquivo" nos seis
videos. Ferramenta que espera artefato inexistente nunca roda; era o defeito
de origem dela, junto com o `.MOV` fixo.

E o formato importa: `N_palavras.json` traz SUB-PALAVRA ('rab' + 'o'), nao
palavra. Um teto de duracao em segundos calibrado para palavra, aplicado a
token, produz lixo -- o teto util aqui e' ~0,75 s por TOKEN.

Rodar depois do corte:

    python scripts/analise/repeticao.py --lote "2026-08 - Dra. Fulana"
"""
import array
import json
import math
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
import config

SR = 8000
JAN = 0.02
TETO_TOKEN = 0.75
# Tokens iguais seguidos que caracterizam texto repetido. Sao SUB-palavras
# ('rab'+'o'), entao 6 tokens ~ 4 palavras -- curto o bastante para pegar a
# reentrada do v3 da Dra. Fulana e longo o bastante para nao acusar muleta
# ("e' que a gente", "entao voce").
N_REPET = 6


def envelope(src):
    r = subprocess.run(
        ["ffmpeg", "-hide_banner", "-v", "error", "-i", src, "-vn",
         "-ac", "1", "-ar", str(SR), "-f", "s16le", "-"], capture_output=True)
    d = array.array("h")
    d.frombytes(r.stdout[: len(r.stdout) // 2 * 2])
    n = int(SR * JAN)
    out = []
    for i in range(0, len(d) - n, n):
        s = 0
        for x in d[i:i + n]:
            s += x * x
        rms = math.sqrt(s / n) / 32768.0
        out.append(20 * math.log10(rms) if rms > 1e-9 else -120.0)
    return out


def _aceita(aceitas, ini, tol=0.05):
    """Devolve o motivo se esta suspeita ja' foi liberada no lote.json."""
    for t, motivo in aceitas:
        if abs(t - ini) <= tol:
            return motivo
    return None


def main(videos=None, vao_min=0.60, fala_min=0.35, vao_mudo_min=1.5,
         dist_repet_max=5.0):
    """Varre o lote e devolve {video: [suspeitas NAO liberadas]}.

    Retorna dado em vez de so' imprimir para poder ser PORTAO -- ver o bloco
    `__main__` e a chamada na fase 1 (`lote_preparar.py`).
    """
    LOTE = config.carregar()
    alvos = videos or LOTE.videos
    # `LOTE.videos` sai de `faixas`, que esta vazio antes da fase 1: sem esta
    # guarda o laco nao roda e o script sai CALADO com exit 0, indistinguivel
    # de "varri tudo e esta limpo". Aconteceu na primeira execucao aqui.
    if not alvos:
        raise SystemExit("nenhum video: `faixas` esta vazio no lote.json. "
                         "Este detector roda DEPOIS da fase 1 — ele precisa "
                         "de trabalho/N_fw.json.")
    faltando = []
    pendentes = {}
    for v in alvos:
        # bruto_de resolve a extensao: a copia antiga fixava .MOV e este
        # lote e .MP4 -- sozinho isso zerava o detector sem erro nenhum.
        # O audio do CORTE, nao o bruto: e o corte que vai ao ar, e os
        # tempos de `N_palavras.json` sao nessa linha do tempo.
        src = os.path.join(LOTE.trabalho, f"{v}_corte.wav")
        fw = os.path.join(LOTE.trabalho, f"{v}_palavras.json")
        if not (os.path.exists(src) and os.path.exists(fw)):
            # Nao basta imprimir e seguir: "falta arquivo" com exit 0 le-se
            # como lote limpo. Acumula e sai com codigo != 0 no fim.
            faltando.append(v)
            print(f"v{v}: FALTA ARQUIVO "
                  f"(corte.wav={os.path.exists(src)} "
                  f"palavras.json={os.path.exists(fw)})")
            continue
        # JSONL, um token por linha, tempos em ms -> segundos
        palavras = [{"ini": t["start"] / 1000.0, "fim": t["end"] / 1000.0,
                     "txt": t["text"]}
                    for t in (json.loads(l) for l in
                              open(fw, encoding="utf-8") if l.strip())]
        env = envelope(src)
        o = sorted(env)
        piso, teto = o[int(len(o) * 0.10)], o[int(len(o) * 0.95)]
        limiar = piso + (teto - piso) * 0.40

        achados = []
        # 1) VAO entre palavras com fala dentro
        for a, b in zip(palavras, palavras[1:]):
            vao = b["ini"] - a["fim"]
            # 1b) VAO MUDO: silencio LONGO sobrevivendo DENTRO da peca.
            #
            # Este ramo nasceu de uma medicao que reprovou o proprio detector.
            # Em 14/08/2026 rodei este script no lote da Dra. Fulana
            # -- o lote em que QUATRO pecas com tomada refeita foram
            # publicadas para a cliente -- e ele devolveu "0 suspeita(s)" nos
            # oito videos. O portao estava certo e o detector, cego.
            #
            # Porque: la' as duas tomadas ficaram INTEIRAS dentro da faixa,
            # separadas por 3,88 s de silencio limpo (v1) e 2,32 s (v6). A
            # checagem de cima procura vao COM FALA dentro, que e' o caso em
            # que o modelo engole a repeticao. Silencio limpo passava batido.
            #
            # E silencio longo aqui e' anomalo por construcao: a fase 1 corta
            # justamente as pausas. Um vao mudo de segundos numa peca ja'
            # cortada quase sempre e' emenda de duas tomadas.
            if vao >= vao_mudo_min:
                i0, i1 = int(a["fim"] / JAN), int(b["ini"] / JAN)
                trecho = env[i0:i1] or [-120]
                n_fala = sum(1 for x in trecho if x >= limiar)
                achados.append(("vao mudo", a["fim"], b["ini"], round(vao, 2),
                                round(n_fala * JAN, 2), a["txt"], b["txt"]))
                continue
            if vao < vao_min:
                continue
            i0, i1 = int(a["fim"] / JAN), int(b["ini"] / JAN)
            trecho = env[i0:i1]
            if not trecho:
                continue
            n_fala = sum(1 for x in trecho if x >= limiar)
            s_fala = n_fala * JAN
            if s_fala >= fala_min:
                achados.append(("vao", a["fim"], b["ini"], round(vao, 2),
                                round(s_fala, 2), a["txt"], b["txt"]))

        # 2) PALAVRA ESTICADA -- e este e' o caso que pega tomada refeita.
        #
        # O modelo nem sempre deixa vao: quando a pessoa repete a frase, ele
        # costuma engolir a repeticao DENTRO da palavra anterior, dando a ela
        # uma duracao impossivel. No v7 deste lote `remodelar` sai com 2,78 s
        # e no v10 `resolve` com 1,58 s — sem vao nenhum, entao a checagem de
        # vao passa limpa. Foram exatamente os dois que o analista reprovou,
        # e o detector de vao nao viu nenhum dos dois.
        #
        # 0,16 s por caractere e' folgado: `artificial?` (11 char) cabe em
        # 1,76 s, e a fala dela roda a ~0,35 s por PALAVRA.
        for w in palavras:
            dur = w["fim"] - w["ini"]
            letras = max(1, len(w["txt"].strip(".,!?;:…\"'()")))
            # 0,75 s por TOKEN: o teto de palavra (0,16 s/caractere, piso
            # 0,9 s) nao vale aqui, porque `rab`+`o` sao dois tokens de
            # 3 e 1 letra. Medido no lote da Dra. Fulana.
            teto_dur = max(TETO_TOKEN, letras * 0.16)
            if dur > teto_dur:
                i0, i1 = int(w["ini"] / JAN), int(w["fim"] / JAN)
                trecho = env[i0:i1] or [-120]
                n_fala = sum(1 for x in trecho if x >= limiar)
                achados.append(("esticada", w["ini"], w["fim"], round(dur, 2),
                                round(n_fala * JAN, 2), w["txt"], ""))
        # 3) TEXTO REPETIDO: a mesma sequencia de palavras aparecendo duas
        # vezes na peca. E' o outro jeito de a tomada refeita sobreviver ao
        # corte -- quando o modelo transcreve AS DUAS versoes, o relogio nao
        # denuncia nada (as duas tem duracao normal) e o vao entre elas pode
        # ser curto. O que denuncia e' o texto se repetir.
        #
        # No lote da Dra. Fulana, v3, a faixa reentrava em "densitometria
        # ossea" -- ja' dita 14 s antes. Nem o detector de vao nem o de
        # palavra esticada viam isso, e a peca foi publicada.
        norm = [w["txt"].strip(" .,!?;:…\"'()-").lower() for w in palavras]
        vistos = {}
        for i in range(len(norm) - N_REPET + 1):
            vistos.setdefault(tuple(norm[i:i + N_REPET]), []).append(i)
        cobertos = set()
        for idxs in vistos.values():
            if len(idxs) < 2:
                continue
            for a_i, b_i in zip(idxs, idxs[1:]):
                if a_i in cobertos or b_i - a_i < N_REPET:
                    continue
                n = N_REPET
                while (b_i + n < len(norm) and norm[a_i + n] == norm[b_i + n]
                       and a_i + n < b_i):
                    n += 1
                # A DISTANCIA e' o que separa tomada refeita de retomada
                # retorica, e este limite foi medido, nao escolhido.
                #
                # Rodando so' com o criterio de texto igual, o lote JA'
                # CORRIGIDO E APROVADO da Dra. Fulana acusou duas pecas:
                # "densitometria ossea" dita aos 0,58 s e de novo aos 19,04 s
                # (v2), e "voce entrou na menopausa e" aos 0,12 s e aos
                # 10,84 s (v4). Sao chamadas de volta -- o Reel abre com a
                # frase e a retoma no fecho. Duas peças que o cliente
                # aprovou seriam reprovadas.
                #
                # Tomada refeita e' colada: a pessoa erra e repete na hora. O
                # maior intervalo real medido neste projeto foi o silencio de
                # 3,88 s entre as duas tomadas do v1 da propria Fulano, entao
                # 5 s cobre o caso real com folga e derruba os dois falsos.
                dist = palavras[b_i]["ini"] - palavras[a_i + n - 1]["fim"]
                if dist > dist_repet_max:
                    continue
                cobertos.update(range(a_i, a_i + n))
                cobertos.update(range(b_i, b_i + n))
                texto = " ".join(norm[b_i:b_i + n])[:60]
                achados.append(("repetido", palavras[b_i]["ini"],
                                palavras[b_i + n - 1]["fim"], n,
                                round(dist, 2), texto,
                                f"1a vez em {palavras[a_i]['ini']:.2f}s"))

        achados.sort(key=lambda x: x[1])
        aceitas = LOTE.repeticoes_aceitas_de(v)
        abertos = []
        print(f"\n=== v{v} === limiar {limiar:.1f} dB · "
              f"{len(palavras)} palavras · {len(achados)} suspeita(s)")
        for tipo, ini, fim, medida, s, pa, pb in achados:
            motivo = _aceita(aceitas, ini)
            marca = "  [LIBERADA]" if motivo else ""
            if tipo == "vao":
                print(f"   {ini:7.2f} -> {fim:7.2f}  VAO {medida:5.2f}s "
                      f"com {s:5.2f}s de fala   ...{pa!r} [ ? ] {pb!r}...{marca}")
            elif tipo == "vao mudo":
                print(f"   {ini:7.2f} -> {fim:7.2f}  VAO MUDO {medida:5.2f}s "
                      f"(duas tomadas na mesma faixa?)   "
                      f"...{pa!r} [ silencio ] {pb!r}...{marca}")
            elif tipo == "repetido":
                print(f"   {ini:7.2f} -> {fim:7.2f}  TEXTO REPETIDO "
                      f"({int(medida)} tokens, {pb})   {pa!r}{marca}")
            else:
                print(f"   {ini:7.2f} -> {fim:7.2f}  PALAVRA ESTICADA "
                      f"{medida:5.2f}s ({s:.2f}s de fala)   {pa!r}{marca}")
            if motivo:
                print(f"              motivo: {motivo}")
            else:
                abertos.append((tipo, ini, fim, medida, s, pa, pb))
        if abertos:
            pendentes[v] = abertos

    if faltando:
        raise SystemExit(f"\nNAO VERIFICADO: {faltando} — rode a fase 1 antes. "
                         f"Nao trate este lote como limpo.")
    return pendentes


def portao(videos=None):
    """Roda a varredura e ABORTA se sobrar suspeita nao liberada.

    Chamado pela fase 1. **Imprimir nao basta** -- foi imprimindo que este
    alarme falhou 5 vezes (10/08 Fulano, 11/08 Fulano, 12/08 Fulano,
    12/08 Fulano, 13/08 Fulano, esta ultima com 4 pecas publicadas para a
    cliente). Nas duas do meio ele nem foi executado, porque nada no caminho
    do trabalho o chamava.

    Liberar uma suspeita e' escrever no lote.json, com o porque:

        "repeticoes_aceitas": {
          "3": [{"t": 31.47, "motivo": "enfase deliberada, 'do naaada'"}]
        }
    """
    pendentes = main(videos)
    if not pendentes:
        print("\nTOMADA REFEITA: nenhuma suspeita em aberto.")
        return
    total = sum(len(a) for a in pendentes.values())
    linhas = [f"\nTOMADA REFEITA: {total} suspeita(s) em aberto em "
              f"{len(pendentes)} video(s)."]
    for v, achados in sorted(pendentes.items()):
        for tipo, ini, fim, medida, s, pa, pb in achados:
            alvo = f"{pa!r} [ ? ] {pb!r}" if tipo == "vao" else repr(pa)
            linhas.append(f"  v{v}  {ini:7.2f}s  {tipo.upper():9s} "
                          f"{medida:5.2f}s  {alvo}")
    linhas.append("")
    linhas.append("Ouca cada uma no bruto. Se for tomada refeita, ajuste a "
                  "faixa. Se for enfase, libere no lote.json:")
    for v, achados in sorted(pendentes.items()):
        exemplos = ", ".join(
            f'{{"t": {a[1]:.2f}, "motivo": "..."}}' for a in achados[:2])
        linhas.append(f'  "repeticoes_aceitas": {{"{v}": [{exemplos}]}}')
    raise SystemExit("\n".join(linhas))


if __name__ == "__main__":
    # Sem numero de video roda o lote inteiro: o alarme so vale como
    # portao se o padrao for varrer tudo, nao escolher o que olhar.
    #
    # So DIGITO conta como video. Filtrar por "nao comeca com --" deixava o
    # VALOR do --lote passar como se fosse um video, e a primeira execucao
    # aqui imprimiu 'v2026-08 - Dra. Fulana: falta arquivo' e saiu com
    # exit 0 -- o mesmo modo de falha silenciosa que este arquivo existe para
    # impedir. Quem pegou foi rodar, nao reler.
    portao([a for a in sys.argv[1:] if a.isdigit()] or None)
