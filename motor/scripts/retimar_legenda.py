#!/usr/bin/env python3
"""Ancora o tempo da legenda no AUDIO, nao no palpite do whisper.

Roda na fase 1, logo depois da transcricao.

O PROBLEMA
----------
Os tokens do whisper saem CONTIGUOS: o `end` de um e' o `start` do seguinte,
em 94-99,5% dos casos deste lote. A fala nao e' contigua -- ela respira. O
resultado e' que a pausa fica absorvida na palavra anterior, e a palavra
seguinte acende no meio do silencio, as vezes antes de a fala voltar.
Medido nos 8 videos do lote da Dra. Fulana: em 32% das pausas reais (>= 200 ms)
NAO existe nenhuma fronteira de palavra dentro da pausa -- o karaoke nao para
quando ela para.

A CORRECAO
----------
Detecta a fala no `_corte.wav` (energia RMS na banda 200-4000 Hz, com
histerese relativa a faixa dinamica do arquivo) e, para cada pausa real:

    fim da palavra anterior    -> inicio da pausa
    inicio da palavra seguinte -> fim da pausa (quando a fala volta)

NAO mexe em mais nada. Palavra nenhuma muda, some ou troca de ordem -- ha
verificacao explicita disso, que ABORTA se acontecer. E' peca de medica: o
retimer so' tem permissao sobre TEMPO.

DUAS TRAVAS QUE NASCERAM DE MEDIR
---------------------------------
1. O limiar de fala e' FRACAO da faixa dinamica, nao dB fixo. Com dB fixo o
   v4 (piso -28,7 dB, p95 -13,9 dB) ficava quase todo classificado como
   silencio, e a medida acusava 74% das palavras "em cima do silencio" --
   artefato do medidor, nao do audio (ver 03-armadilhas.md I7).
2. Se o avanco deixasse a palavra acesa por menos de MIN_ACESA, o conserto e'
   ABANDONADO naquela fronteira. Palavras de uma letra que o whisper ja
   timbrou com 30-80 ms viravam piscada de 20 ms -- trocar erro de
   sincronismo por defeito visual nao e' conserto.

NAO E' IDEMPOTENTE. Aplicar duas vezes muda 1 a 4 tokens em 4 dos 8 videos.
Por isso o bruto e' preservado em `{v}_palavras_bruto.json` e o retime sai
SEMPRE dele -- nunca do arquivo ja corrigido.

Uso: python retimar_legenda.py <trabalho> <v> [<v> ...]
"""
import json, os, re, sys
import numpy as np
from scipy.io import wavfile
from scipy import signal

# --- deteccao de fala -------------------------------------------------------
HOP_MS, WIN_MS = 5.0, 20.0
FR_ALTO, FR_BAIXO = 0.44, 0.28   # fracao da faixa dinamica (entra / sai)
MIN_FALA, MIN_PAUSA = 60.0, 60.0
PERC_PISO, PERC_TOPO = 10, 95

# --- re-temporizacao --------------------------------------------------------
PAUSA_FIX = 250.0   # so' pausa >= isso justifica mexer (oclusiva vai ate ~150)
JANELA = 400.0      # a fronteira tem de estar a ate isso da pausa
MIN_DUR = 60.0      # nenhuma palavra pode ficar mais curta que isso
MIN_ACESA = 100.0   # abaixo disso o conserto e' abandonado (ver trava 2)


def _envelope(path):
    sr, x = wavfile.read(path)
    x = x.astype(np.float64)
    if x.ndim > 1:
        x = x.mean(axis=1)
    m = np.abs(x).max()
    if m > 0:
        x /= m
    sos = signal.butter(4, [200.0, 4000.0], btype="band", fs=sr, output="sos")
    x = signal.sosfiltfilt(sos, x)
    hop, win = int(round(sr * HOP_MS / 1000)), int(round(sr * WIN_MS / 1000))
    n = 1 + max(0, (len(x) - win) // hop)
    idx = np.arange(win)[None, :] + hop * np.arange(n)[:, None]
    rms = np.sqrt((x[idx] ** 2).mean(axis=1) + 1e-20)
    db = 20 * np.log10(rms)
    t = np.arange(n) * HOP_MS + WIN_MS / 2.0
    piso = float(np.percentile(db, PERC_PISO))
    return t, db, piso, max(float(np.percentile(db, PERC_TOPO)) - piso, 6.0)


def segmentos_de_fala(wav):
    t, db, piso, faixa = _envelope(wav)
    alto, baixo = piso + FR_ALTO * faixa, piso + FR_BAIXO * faixa
    dentro, segs, ini = False, [], 0.0
    for i in range(len(db)):
        if not dentro and db[i] >= alto:
            j = i
            while j > 0 and db[j - 1] >= baixo:
                j -= 1
            dentro, ini = True, t[j]
        elif dentro and db[i] < baixo:
            dentro = False
            segs.append((ini, t[i]))
    if dentro:
        segs.append((ini, t[-1]))
    fund = []
    for a, b in segs:
        if fund and a - fund[-1][1] < MIN_PAUSA:
            fund[-1] = (fund[-1][0], b)
        else:
            fund.append((a, b))
    return [(a, b) for a, b in fund if b - a >= MIN_FALA]


def pausas_de(segs):
    out, prev = [], 0.0
    for a, b in segs:
        if a > prev:
            out.append((prev, a))
        prev = b
    return out


# --- palavras (mesmo alinhamento do gerar_ass.py) ---------------------------
def _so_letras(s):
    return re.sub(r"[^\wÀ-ÿ]", "", s).lower()


def _fatiar(toks, ref):
    """Quais tokens formam cada palavra. Copia da regra do gerar_ass.py."""
    fatias, i = [], 0
    for alvo in ref:
        acc, ini = "", i
        while i < len(toks):
            acc += toks[i]["text"]
            i += 1
            if _so_letras(acc) == _so_letras(alvo):
                break
            if len(_so_letras(acc)) > len(_so_letras(alvo)) + 2:
                break
        fatias.append((ini, i))
    return fatias


def _palavras_do_srt(srt_f):
    ref = []
    for linha in open(srt_f, encoding="utf-8"):
        linha = linha.strip()
        if linha and not linha.isdigit() and "-->" not in linha:
            ref.extend(linha.split())
    return ref


def retimar(wav, palavras):
    """palavras = [{'txt','ini','fim'}]. Devolve nova lista, so' com tempos."""
    segs = segmentos_de_fala(wav)
    if not segs:
        return [dict(p) for p in palavras]
    ps = [(a, b) for a, b in pausas_de(segs) if b - a >= PAUSA_FIX]
    out = [dict(p) for p in palavras]

    usados = set()
    for a, b in ps:
        cand = [k for k in range(1, len(out))
                if k not in usados and a - JANELA <= out[k]["ini"] <= b + JANELA]
        if not cand:
            continue
        k = min(cand, key=lambda k: abs(out[k]["ini"] - (a + b) / 2.0))
        ant, atual = out[k - 1], out[k]
        novo_fim = max(ant["ini"] + MIN_DUR, min(ant["fim"], a))
        novo_ini = max(novo_fim, min(b, atual["fim"] - MIN_DUR))
        if k + 1 < len(out) and out[k + 1]["ini"] - novo_ini < MIN_ACESA:
            continue                      # trava 2: nao criar piscada
        ant["fim"], atual["ini"] = novo_fim, novo_ini
        usados.add(k)

    # --- palavra COLAPSADA na fronteira de trecho -------------------------
    #
    # O whisper emite tokens de duracao zero (2 a 10 por video, ja registrado
    # no gerar_ass). Enquanto caem no meio da frase eles sao inofensivos: o
    # piso de 80 ms do gerar_ass resolve. Quando caem na PRIMEIRA palavra de
    # um trecho, nao: a palavra herda o instante do corte, e o GRUPO dela
    # nasce com o mesmo inicio do grupo seguinte. As duas legendas acendem
    # juntas, empilhadas -- e o guarda de sobreposicao do gerar_ass e' pulado
    # justamente ai, porque ele so' roda `if prox > ini`.
    #
    # Custo real (Dra. Fulana pt1, 11/08/2026): o operador viu
    # 'QUEM MARCA' por baixo de 'UMA CONSULTA' no v1, e 'AQUI' e 'O PRIMEIRO'
    # sumindo no v3. Nos tres casos a palavra e' a primeira de uma tomada em
    # que o modelo ancora o inicio em 0,00 com ENERGIA ZERO -- o mesmo
    # artefato que faz o detector de tomada refeita acusar 'palavra esticada'
    # falsa. Ele aparece nos dois lados do pipeline pela mesma causa.
    #
    # O conserto puxa a palavra para tras, ate onde a fala realmente comeca,
    # usando os segmentos de energia que este modulo ja calculou. Espaco
    # insuficiente => nao mexe (o piso do gerar_ass continua valendo): trocar
    # sobreposicao por piscada de 20 ms nao e' conserto, mesma logica da
    # trava 2.
    colapsadas = 0
    k = 0
    while k < len(out):
        if out[k]["fim"] > out[k]["ini"]:
            k += 1
            continue
        j = k
        while j + 1 < len(out) and out[j + 1]["fim"] <= out[j + 1]["ini"]:
            j += 1
        n = j - k + 1
        dir_ = out[j + 1]["ini"] if j + 1 < len(out) else out[j]["fim"]
        esq = out[k - 1]["fim"] if k > 0 else 0.0
        # onde a fala volta depois da ultima palavra com tempo de verdade
        inicios = [a for a, b in segs if a >= esq and a < dir_]
        ancora = max(esq, inicios[0]) if inicios else esq
        if dir_ - ancora >= n * MIN_DUR:
            passo = (dir_ - ancora) / n
            for m in range(n):
                out[k + m]["ini"] = ancora + passo * m
                out[k + m]["fim"] = ancora + passo * (m + 1)
            colapsadas += n
        elif j + 1 < len(out):
            # Sem espaco a ESQUERDA. E o caso comum na fronteira de trecho:
            # a ancoragem por pausa ja empurrou a palavra anterior ate o
            # instante em que a fala volta, e as colapsadas ficam espremidas
            # contra ele. O tempo que falta esta a DIREITA -- essas palavras
            # sao ditas DEPOIS da ancora, nao antes; quem esta errado e' o
            # token, que as colocou no silencio.
            #
            # Entao empresta MIN_DUR de cada uma do vizinho seguinte, desde
            # que ele continue com MIN_DUR. Sem isso o grupo inteiro nasce no
            # mesmo instante do grupo seguinte e as duas legendas empilham.
            # Emprestimo de uma SEQUENCIA de vizinhos, nao de um so'.
            #
            # A versao anterior olhava apenas `out[j+1]`. Quando ESSE vizinho
            # tambem e' minusculo, a condicao falhava e a funcao DESISTIA EM
            # SILENCIO -- o grupo colapsado ficava com os tres eventos no
            # mesmo instante e o .ass saia com Dialogue empilhado.
            #
            # Medido no v2 da Dra. Fulana (12/08/2026), na emenda de
            # trecho em 26,63 s: 'E', 'a', 'ris' colapsados em 26,680 e o
            # vizinho 'ca' com 30 ms -- precisa de 3x60=180 ms e ha 30. O
            # .ass ganhou TRES eventos em 0:00:26.68 -> 0:00:26.71, todos no
            # mesmo pixel: "E A RISCA" aparecia empilhado por UM quadro
            # (33 ms) e sumia. O operador leu como "bugada no corte", porque
            # cai 47 ms depois do corte.
            #
            # O tempo existe logo adiante ('do' 230 ms, 'meio' 470 ms); so'
            # nao esta no vizinho imediato. Aqui a janela cresce para a
            # direita ate' caber o grupo colapsado E deixar MIN_DUR para cada
            # vizinho consumido. Os vizinhos sao entao comprimidos na
            # proporcao da duracao original, com piso de MIN_DUR -- comprimir
            # proporcional preserva o ritmo relativo da fala, que dividir por
            # igual destruiria.
            precisa = n * MIN_DUR
            m_viz, base = 0, out[j + 1]["ini"]
            while j + 1 + m_viz < len(out):
                m_viz += 1
                fim_janela = out[j + m_viz]["fim"]
                if fim_janela - base - precisa >= m_viz * MIN_DUR:
                    break
            else:
                m_viz = 0                      # nao ha espaco em lugar nenhum
            if m_viz:
                fim_janela = out[j + m_viz]["fim"]
                for m in range(n):             # o grupo colapsado
                    out[k + m]["ini"] = base + MIN_DUR * m
                    out[k + m]["fim"] = base + MIN_DUR * (m + 1)
                sobra = fim_janela - (base + precisa)
                orig = [out[j + 1 + i]["fim"] - out[j + 1 + i]["ini"]
                        for i in range(m_viz)]
                soma = sum(orig) or 1.0
                # proporcional, com piso; o excedente do piso sai de quem tem
                # folga, na mesma proporcao
                dur = [max(MIN_DUR, sobra * d / soma) for d in orig]
                excesso = sum(dur) - sobra
                if excesso > 0:
                    folga = [d - MIN_DUR for d in dur]
                    tot = sum(folga) or 1.0
                    dur = [d - excesso * f / tot for d, f in zip(dur, folga)]
                t = base + precisa
                for i in range(m_viz):
                    out[j + 1 + i]["ini"] = t
                    out[j + 1 + i]["fim"] = t + dur[i]
                    t += dur[i]
                colapsadas += n
            else:
                # Falhar ALTO: sem isto o .ass sai com eventos empilhados e
                # ninguem fica sabendo. E' o modo de falha que este bloco
                # existe para impedir.
                print(f"      AVISO: {n} palavra(s) colapsada(s) em "
                      f"{out[k]['ini'] / 1000:.2f}s SEM espaco para reposicionar "
                      f"— o .ass vai sair com legenda empilhada aqui")
        k = j + 1

    for k in range(len(out) - 1):
        out[k]["fim"] = min(out[k]["fim"],
                            max(out[k]["ini"] + MIN_DUR, out[k + 1]["ini"]))

    # invariante de compliance: nada alem de tempo pode ter mudado
    if len(out) != len(palavras):
        sys.exit("RETIMER: mudou a quantidade de palavras")
    for x, y in zip(palavras, out):
        if x["txt"] != y["txt"]:
            sys.exit(f"RETIMER: texto mudou: {x['txt']!r} -> {y['txt']!r}")
    t = -1.0
    for y in out:
        if y["ini"] < t or y["fim"] < y["ini"]:
            sys.exit(f"RETIMER: tempo nao monotono em {y['txt']!r}")
        t = y["ini"]
    return out, len(usados), len(ps), colapsadas


def retimar_arquivo(trabalho, v):
    """Le `{v}_palavras_bruto.json` (ou promove o atual a bruto) e reescreve
    `{v}_palavras.json` re-temporizado."""
    wav = os.path.join(trabalho, f"{v}_corte.wav")
    srt = os.path.join(trabalho, f"{v}_corte.srt")
    alvo = os.path.join(trabalho, f"{v}_palavras.json")
    bruto = os.path.join(trabalho, f"{v}_palavras_bruto.json")
    if not os.path.exists(bruto):
        os.replace(alvo, bruto)

    toks = [json.loads(l) for l in open(bruto, encoding="utf-8") if l.strip()]
    ref = _palavras_do_srt(srt)
    fatias = _fatiar(toks, ref)
    P = []
    for (a, b), txt in zip(fatias, ref):
        if b <= a:
            sys.exit(f"RETIMER v{v}: alinhamento falhou em {txt!r}")
        P.append({"txt": txt, "ini": toks[a]["start"], "fim": toks[b - 1]["end"]})

    novo, movidas, npausas, colapsadas = retimar(wav, P)

    out = [dict(t) for t in toks]
    for (a, b), velho, nv in zip(fatias, P, novo):
        o0, o1 = velho["ini"], velho["fim"]
        n0, n1 = nv["ini"], nv["fim"]
        f = (n1 - n0) / (o1 - o0) if o1 > o0 else 1.0
        for j in range(a, b):
            out[j]["start"] = round(n0 + (out[j]["start"] - o0) * f)
            out[j]["end"] = round(n0 + (out[j]["end"] - o0) * f)
    if [t["text"] for t in out] != [t["text"] for t in toks]:
        sys.exit("RETIMER: o fluxo de tokens mudou de texto")

    with open(alvo, "w", encoding="utf-8", newline="\n") as f:
        for t in out:
            f.write(json.dumps(t, ensure_ascii=False) + "\n")
    print(f"  v{v}: {npausas} pausas >= {PAUSA_FIX:.0f} ms, "
          f"{movidas} fronteiras ancoradas no audio"
          + (f", {colapsadas} palavra(s) colapsada(s) reposicionada(s)"
             if colapsadas else ""))


if __name__ == "__main__":
    trabalho, vs = sys.argv[1], sys.argv[2:]
    for v in vs:
        retimar_arquivo(trabalho, v)
