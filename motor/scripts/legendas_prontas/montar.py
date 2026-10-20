#!/usr/bin/env python3
"""Cruza a leitura da tela com o audio e escreve o .srt de cada video.

Divisao de trabalho, que e' a decisao central deste lote:

  a tela decide O QUE esta escrito e COMO esta quebrado em eventos;
  o audio decide QUANDO cada evento entra e sai;
  o audio tambem devolve a ACENTUACAO, que o modelo de OCR nao tem.

COMO SE SABE QUAL LINHA DA TELA E' A LEGENDA. O quadro tem mais texto que a
legenda: tarja de frase em destaque, cartao de nome ("Fulano /
especialista em varizes"), texto de impacto em caixa alta. Nao da' para
escolher por posicao -- a legenda sobe para ~43 % da altura no video de tela
dividida -- nem por tamanho -- o cartao de nome e' MAIOR que a legenda.
O que separa: a legenda contem a palavra que esta sendo falada naquele
instante. Tarja e cartao nao. Por isso a escolha da linha usa o
`word_timestamps` como criterio, e nao a geometria.

Validado contra os cinco .srt ja aprovados desta mesma pasta (`calibrar.py`):
la' a leitura da tela reproduz evento a evento o corte aprovado.
"""
import difflib
import json
import os
import re
import sys
import unicodedata

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
from lista import CORRECOES, FALTANDO, LEGENDAS, SAIDA, trab  # noqa: E402
# linha que fica identica por mais que isto nao e' legenda falada: e' tarja,
# cartao de nome ou marca d'agua. A legenda deste padrao troca a cada ~0,7 s.
PERSISTENCIA = 3.0
# meia altura da faixa da legenda, em pixels do recorte. A legenda oscila
# poucos pixels entre eventos; texto de impacto e cartao de nome ficam a
# centenas de distancia.
TOLERANCIA = 60


def sem_acento(s):
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if unicodedata.category(c) != "Mn")


def chave(s):
    return re.sub(r"[^a-z0-9]", "", sem_acento(s).lower())


def fichas(s):
    return [c for c in (chave(t) for t in s.split()) if c]


def partes(tok):
    """(pontuacao a esquerda, nucleo, pontuacao a direita)."""
    m = re.match(r"^(\W*)(.*?)(\W*)$", tok, re.UNICODE)
    return m.group(1), m.group(2), m.group(3)


def caixa_de(modelo, palavra):
    """Aplica a caixa da TELA sobre a grafia acentuada do audio."""
    if modelo.isupper() and len(modelo) > 1:
        return palavra.upper()
    if modelo[:1].isupper():
        return palavra[:1].upper() + palavra[1:]
    return palavra[:1].lower() + palavra[1:]


def escolher(amostra, fixos, faixas=None):
    """A linha que e' legenda nesta amostra, ou None.

    Criterio principal: conter a palavra falada agora. Quando mais de uma
    linha contem (acontece quando o texto de impacto em caixa alta repete a
    fala), desempata pela proximidade da faixa onde a legenda deste video
    mora -- e' o texto de impacto que muda de altura, nao a legenda.
    """
    alvo = chave(amostra["palavra"])
    livres = [ln for ln in amostra["linhas"] if ln["txt"] not in fixos]
    casam = [ln for ln in livres if alvo and alvo in fichas(ln["txt"])]
    if not faixas:
        return casam[0] if casam else None

    def dist(ln):
        return min(abs(ln["y"] - f) for f in faixas)

    # a legenda mora nas faixas; o que esta fora delas e' texto de impacto ou
    # cartao de nome. Dentro da faixa, casar com a palavra falada so'
    # desempata -- exigir o casamento comia o evento sempre que o whisper
    # errava a palavra ("Observe" transcrito como "O cerebro").
    perto = [ln for ln in livres if dist(ln) <= TOLERANCIA]
    base = min([ln for ln in perto if ln in casam] or perto, key=dist) \
        if perto else (casam[0] if casam else None)
    return bloco(base, livres) if base else None


def bloco(base, livres):
    """Junta as linhas que sao a QUEBRA da mesma legenda, nao outra legenda.

    Ha' legenda de tres linhas neste lote (o cartao "Há quanto tempo você /
    está adiando para / cuidar das suas pernas?"), e pegar so' uma entregava
    um terco da frase. O que separa quebra de linha de outro elemento da tela
    e' a distancia: linha quebrada encosta na de cima (vao menor que a altura
    do texto); tarja e cartao de nome ficam a centenas de pixels.
    """
    def emenda(u, v):
        # mesmo corpo de texto E encostadas. Os dois testes sao necessarios:
        # o cartao de nome do Video 7 fica perto da legenda, mas e' bem
        # MAIOR; e uma legenda de outro bloco tem o mesmo corpo, mas longe.
        perto = v["y"] - u["y"] <= u["h"] * 1.35
        mesmo_corpo = abs(u["h"] - v["h"]) <= max(u["h"], v["h"]) * 0.30
        return perto and mesmo_corpo

    linhas = sorted(livres, key=lambda ln: ln["y"])
    a = b = linhas.index(base)
    while a > 0 and emenda(linhas[a - 1], linhas[a]):
        a -= 1
    while b < len(linhas) - 1 and emenda(linhas[b], linhas[b + 1]):
        b += 1
    return {"y": base["y"], "h": base["h"],
            "txt": " ".join(ln["txt"] for ln in linhas[a:b + 1])}


def faixas_da_legenda(lidos, fixos):
    """As alturas onde a legenda mora, medidas no proprio video.

    Plural de proposito. Uma mediana so' nao serve: no video de tela dividida
    a legenda fica a ~43 % da altura numa parte e a ~75 % na outra, e a
    mediana das duas cai num vazio -- nenhuma das duas entrava na tolerancia,
    e o cartao de nome ("Fulano / Especialista em varizes") ganhava o
    evento. Aqui as alturas viram grupos, e grupo com pouca sustentacao (o
    cartao, que so' aparece uns segundos) e' descartado.
    """
    ys = sorted(ln["y"] for x in lidos
                if (ln := escolher(x, fixos)) is not None)
    if not ys:
        return []
    grupos_y, atual = [], [ys[0]]
    for y in ys[1:]:
        if y - atual[-1] <= TOLERANCIA:
            atual.append(y)
        else:
            grupos_y.append(atual)
            atual = [y]
    grupos_y.append(atual)
    minimo = max(3, len(lidos) * 0.05)
    return [g[len(g) // 2] for g in grupos_y if len(g) >= minimo]


def persistentes(lidos):
    """Textos que ficam na tela tempo demais para serem fala."""
    # tempo CONTIGUO na tela, nao primeira-vez ate ultima-vez: a legenda
    # repete texto ("A resposta" abre e fecha este video), e medir de ponta a
    # ponta classificava a abertura como tarja e comia o primeiro evento.
    inicio, fim, maior = {}, {}, {}
    for x in lidos:
        agora = {ln["txt"] for ln in x["linhas"]}
        for t in agora:
            inicio.setdefault(t, x["t"])
            fim[t] = x["t"]
        for t in list(inicio):
            if t not in agora:
                maior[t] = max(maior.get(t, 0), fim[t] - inicio[t])
                del inicio[t]
    for t, a in inicio.items():
        maior[t] = max(maior.get(t, 0), fim[t] - a)
    return {t for t, d in maior.items() if d > PERSISTENCIA}


def grupos(lidos):
    """Amostras consecutivas que mostram a mesma linha de legenda.

    Amostra sem linha escolhida nao vira grupo proprio: ela e' absorvida pelo
    vizinho. Buraco de leitura no meio de um evento e' falha do OCR, nao
    legenda que sumiu -- neste padrao um evento encosta no outro.
    """
    fixos = persistentes(lidos)
    faixas = faixas_da_legenda(lidos, fixos)
    esc = [(ln["txt"] if (ln := escolher(x, fixos, faixas)) else None)
           for x in lidos]
    for i, t in enumerate(esc):
        if t:
            continue
        ant = next((esc[j] for j in range(i - 1, -1, -1) if esc[j]), None)
        prox = next((esc[j] for j in range(i + 1, len(esc)) if esc[j]), None)
        esc[i] = ant if ant == prox else (ant or prox)
    # agrupa por conteudo, nao por string exata: o OCR devolve a MESMA linha
    # escrita de tres jeitos ao longo do evento ('Se voce esta em Cidade',
    # 'Sevoce está em Cidade'...). Comparar string quebrava um evento em tres.
    gs = []
    for i, t in enumerate(esc):
        if not t:
            continue
        if gs and gs[-1]["b"] == i - 1 and parecidos(gs[-1]["vistos"][-1], t):
            gs[-1]["b"] = i
            gs[-1]["vistos"].append(t)
        else:
            gs.append({"a": i, "b": i, "vistos": [t]})
    for g in gs:
        g["txt"] = melhor(g["vistos"])
    return gs


def parecidos(a, b):
    ka, kb = chave(a), chave(b)
    if ka == kb:
        return True
    # a legenda deste cliente se MONTA na tela: 'Há quanto tempo' vira
    # 'Há quanto tempo você está adiando para cuidar das suas pernas?'. Sao
    # amostras do mesmo evento, nao dois eventos -- o comeco e' prefixo do
    # fim. Sem isto o .srt repetia o pedaco antes da frase inteira.
    if ka and kb and (ka.startswith(kb) or kb.startswith(ka)):
        return True
    return difflib.SequenceMatcher(a=ka, b=kb).ratio() >= 0.85


def melhor(vistos):
    """A leitura mais frequente do evento; empate vai para a mais longa.

    Cada amostra le' a mesma linha de novo. Onde as leituras discordam, a
    maioria acerta -- e a variante mais longa e' a que nao perdeu caractere.
    """
    contagem = {}
    for v in vistos:
        contagem[v] = contagem.get(v, 0) + 1
    # se as leituras sao uma o comeco da outra, o evento estava se montando
    # na tela: vale a versao COMPLETA, nao a mais repetida (a parcial aparece
    # em mais quadros, porque fica na tela enquanto o resto entra).
    completa = max(contagem, key=lambda v: len(chave(v)))
    kc = chave(completa)
    if all(kc.startswith(chave(v)) for v in contagem):
        return completa
    return max(contagem, key=lambda v: (contagem[v], len(v)))


def lexico(lidos):
    """chave sem acento -> grafia acentuada, tirada do audio do proprio video.

    O reconhecedor do OCR nao tem o alfabeto acentuado completo: ele devolve
    'consistencia', 'possivel', 'nao'. Restaurar palavra a palavra DENTRO do
    evento so' funciona quando o alinhamento fecha, e ele nao fecha quando o
    OCR cola duas palavras ('Sevoce'). Um lexico do video inteiro nao depende
    de alinhamento nenhum -- e como e' do proprio video, nao inventa grafia
    que o medico nao falou.
    """
    cont = {}
    for x in lidos:
        p = partes(x["palavra"])[1]
        if not p:
            continue
        d = cont.setdefault(chave(p), {})
        d[p] = d.get(p, 0) + 1
    return {k: max(v, key=lambda s: (v[s], sum(1 for c in s if ord(c) > 127)))
            for k, v in cont.items()}


def fundir(tela, pals, lex, vistos=()):
    """Texto final do evento: letras/pontuacao da tela, acento do audio."""
    # Quando a tela e o audio dizem a MESMA coisa e so' o OCR tropecou --
    # 'masaspernas', 'Agendea sua', 'Nós iantiricamos' --, o texto sai do
    # audio. Isto nao e' o audio vencendo a tela: as duas leituras concordam
    # na letra, e a do audio e' a que tem espaco, acento e pontuacao. Quando
    # discordam de verdade (razao baixa), a tela fica de pe' e o caso vai
    # para revisao.
    toks = tela.split()
    pal = [p["palavra"] for p in pals]
    # tudo que a TELA foi lida dizendo neste evento, somando todas as
    # amostras. Serve de arbitro na troca 1 por 1 (ver adiante).
    lidas = {c for v in vistos for c in fichas(v)}
    kt = [chave(partes(t)[1]) for t in toks]
    kp = [chave(partes(p)[1]) for p in pal]

    def acentuar(tok, alvo=None):
        esq, nuc, dir_ = partes(tok)
        alvo = alvo or lex.get(chave(nuc))
        if nuc and alvo and sem_acento(alvo).lower() == sem_acento(nuc).lower():
            nuc = caixa_de(nuc, alvo)
        return esq + nuc + dir_

    saida, avisos = [], []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(
            a=kt, b=kp, autojunk=False).get_opcodes():
        if op == "equal":
            # a grafia do audio traz o acento; a caixa continua sendo a da
            # tela. Aqui vale a palavra DESTE evento, nao o lexico do video:
            # e' o que distingue 'a' de 'à'.
            for d in range(i2 - i1):
                saida.append(acentuar(toks[i1 + d],
                                      partes(pal[j1 + d])[1]))
        elif op == "delete":
            saida += [acentuar(t) for t in toks[i1:i2]]
        elif op == "replace":
            # mesma letra, corte diferente: o OCR colou ou embaralhou
            # ('masaspernas', 'Nós iantiricamos', 'em reiacaoao'). Nesse caso
            # o texto sai do audio -- as duas leituras concordam na letra e a
            # do audio tem espaco, acento e pontuacao. Se NAO concordam, a
            # tela fica de pe' e o caso vai para revisao: pode ser a agencia
            # tendo escrito na tela coisa diferente do que foi falado.
            # Troca 1 por 1 nao vem do audio so' por ser parecida: ai' a tela
            # esta dizendo outra palavra, e quem manda e' a tela. Foi assim
            # que 'Agende sua consulta.' virou 'Agenda' -- erro de whisper que
            # o proprio CLAUDE.md do projeto ja registra.
            # A excecao e' quando A PROPRIA TELA, em outro quadro do mesmo
            # evento, foi lida dizendo a palavra do audio: ai' as duas fontes
            # concordam e o que sobrou foi um quadro de leitura ruim -- e' o
            # que separa 's6'/'só' e 'comega'/'começa' (erro de OCR) de
            # 'vasinhos'/'vazinhos' (a tela escreve com s mesmo).
            r = difflib.SequenceMatcher(a="".join(kt[i1:i2]),
                                        b="".join(kp[j1:j2])).ratio()
            um_a_um = (i2 - i1) == (j2 - j1) == 1
            # letra grudada em digito nao existe em portugues: e' o OCR
            # errando a acentuada ('s6', 's0', 's?' por 'só'). Quando as tres
            # leituras da tela saem assim, o arbitro de leitura nao resolve,
            # e a palavra do audio e' a unica evidencia que sobra.
            impossivel = um_a_um and re.search(
                r"[^\W\d_][\d?]|[\d?][^\W\d_]", partes(toks[i1])[1])
            confirmado = um_a_um and (kp[j1] in lidas or impossivel)
            # 's6' x 'só' tem semelhanca 0,50 -- a mesma faixa em que uma
            # troca de verdade cairia. O que autoriza aqui nao e' a
            # semelhanca, e' o digito no meio da palavra.
            limite = 0.40 if impossivel else 0.65
            if r >= limite and j2 > j1 and (not um_a_um or confirmado):
                trecho = list(pal[j1:j2])
                fim = partes(toks[i2 - 1])[2]
                if fim and not partes(trecho[-1])[2]:
                    trecho[-1] += fim
                saida += trecho
            else:
                saida += [acentuar(t) for t in toks[i1:i2]]
                avisos.append(f"tela {' '.join(toks[i1:i2])!r} x audio "
                              f"{' '.join(pal[j1:j2])!r}")
    return " ".join(saida), avisos


def hms(t):
    ms = int(round(max(t, 0.0) * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def montar(ap):
    lidos = json.load(open(trab(f"{ap}_ocr.json"), encoding="utf-8"))
    lex = lexico(lidos)
    eventos, avisos = [], []
    for g in grupos(lidos):
        pals = lidos[g["a"]:g["b"] + 1]
        texto, av = fundir(g["txt"], pals, lex, g["vistos"])
        avisos += [f"  [{pals[0]['ini']:6.2f}] {a}" for a in av]
        eventos.append({"ini": pals[0]["ini"], "fim": pals[-1]["fim"],
                        "txt": texto})
    # dois eventos seguidos com o mesmo texto sao um evento so': o corte veio
    # de uma leitura ruim no meio, nao de uma troca de legenda.
    juntos = []
    for e in eventos:
        if juntos and juntos[-1]["txt"] == e["txt"]:
            juntos[-1]["fim"] = e["fim"]
        else:
            juntos.append(e)
    eventos = juntos
    for i in range(len(eventos) - 1):
        if eventos[i]["fim"] > eventos[i + 1]["ini"]:
            eventos[i]["fim"] = eventos[i + 1]["ini"] - 0.001
    eventos = [e for e in eventos if e["fim"] - e["ini"] > 0.05]
    return corrigir(ap, eventos), avisos


def corrigir(ap, eventos):
    """Aplica a revisao humana registrada em correcoes.json.

    O que o cruzamento tela x audio nao resolve sozinho -- contador animado
    lido como legenda, texto de impacto invadindo, palavra que so' o olho
    decide -- e' corrigido aqui, com o quadro de prova anotado no JSON. Fica
    em dado e nao em codigo porque e' decisao sobre ESTE lote.
    """
    if not os.path.exists(CORRECOES):
        return eventos
    for c in json.load(open(CORRECOES, encoding="utf-8")).get(ap, []):
        if c["tipo"] == "texto":
            for e in eventos:
                if e["txt"] == c["de"]:
                    e["txt"] = c["para"]
        elif c["tipo"] == "faixa":
            fora = [e for e in eventos
                    if e["fim"] <= c["ini"] or e["ini"] >= c["fim"]]
            eventos = sorted(fora + [dict(x) for x in c["eventos"]],
                             key=lambda e: e["ini"])
    return eventos


def srt(eventos):
    return "\n".join(
        f"{i}\n{hms(e['ini'])} --> {hms(e['fim'])}\n{e['txt']}\n"
        for i, e in enumerate(eventos, 1))


if __name__ == "__main__":
    os.makedirs(SAIDA, exist_ok=True)
    todos = []
    alvos = sys.argv[1:]
    for nome, ap in FALTANDO:
        if alvos and ap not in alvos:
            continue
        if not os.path.exists(trab(f"{ap}_ocr.json")):
            print(f"== {ap}: sem OCR ainda, pulando")
            continue
        eventos, avisos = montar(ap)
        base = os.path.splitext(os.path.basename(nome))[0]
        with open(os.path.join(SAIDA, base + ".srt"), "w",
                  encoding="utf-8") as f:
            f.write(srt(eventos))
        dur = eventos[-1]["fim"] if eventos else 0
        print(f"== {ap}: {len(eventos)} eventos ate {dur:.1f}s, "
              f"{len(avisos)} divergencia(s)  -> {base}.srt")
        if avisos:
            todos.append(f"===== {ap}  ({nome})\n" + "\n".join(avisos))
    with open(os.path.join(SAIDA, "_divergencia.txt"), "w",
              encoding="utf-8") as f:
        f.write("\n\n".join(todos) + "\n")
