# -*- coding: utf-8 -*-
"""PORTAO DE CONTEUDO: o que ela FALOU x o que ficou QUEIMADO na tela.

Todos os portoes deste projeto medem FORMA -- posicao, cobertura, nivel, pico,
sincronismo. Nenhum le a palavra. Foi por isso que o lote da Dra. Fulana saiu com `lote_verificar` OK em quatro pecas nas quais o operador viu
erro de legenda na tela, e o CTA `Agende` virou `A gente` e `Agente` em tres
lotes diferentes (Fulano, Fulano, Fulano -- esta ultima DUAS vezes no mesmo
lote, porque a fase 1 RE-TRANSCREVE e nao e' estavel no mesmo audio).

Duas decisoes que fazem este portao existir de verdade:

**1. O lado esquerdo e' a fala do BRUTO, nao a do corte.** O corte e' o mesmo
insumo que gerou a legenda -- comparar um com o outro e' perguntar ao modelo
se ele concorda consigo mesmo. A fala das TOMADAS vem de
`trabalho/N_palavras_bruto.json`, recortada pelas `faixas` do lote.

**2. O lado direito e' o `.ass`, NUNCA o `_corte.srt`.** As `correcoes` sao
aplicadas na geracao do `.ass` e nao voltam para o srt. A primeira versao
deste comparador, no lote da Fulano, lia o srt -- e acusava `Agente` DEPOIS de
o video ja' ter saido com `AGENDE` na tela. Portao que le o artefato errado
mente com confianca.

**Por que a comparacao e' por LETRA e nao por palavra:** `N_palavras*.json`
traz SUB-PALAVRA (`dens`+`it`+`omet`+`ria`), entao nao existe fronteira de
palavra confiavel do lado da fala. Normalizando os dois lados para uma fita de
letras minusculas sem acento, `agende` x `agente` difere em um caractere e
aparece; `ja trocou` x `trocou` aparece como bloco faltando; `Obrigado.`
alucinado aparece como bloco sobrando.

    python scripts/analise/conteudo.py --lote "2026-08 - Dra. Fulana"
"""
import difflib
import json
import os
import re
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))
import config                                              # noqa: E402

# Bloco divergente menor que isto e' ruido de transcricao (plural comido,
# sufixo). Dois caracteres ja' pegam `agende`/`agente`.
MIN_BLOCO = 2
CONTEXTO = 28


# Reducao coloquial que a legenda escreve por extenso DE PROPOSITO. Decisao
# do operador em 11/08/2026: vale ate' em peca de medico, porque e' registro
# e nao conteudo clinico. Sem isto, `pra` na fala x `PARA` na tela vira
# divergencia -- 4 dos 7 achados do v1 da Fulano eram exatamente isso.
#
# A troca e' por TOKEN INTEIRO, nunca por substring: `ta` dentro de
# `estatura` nao pode virar `esta`.
PLENAS = {
    "pra": "para", "pro": "parao", "pros": "paraos", "pras": "paraas",
    "ta": "esta", "tao": "estao", "to": "estou", "tamos": "estamos",
    "ce": "voce", "ces": "voces", "cadê": "ondeesta",
    "num": "naoum", "numa": "naouma", "ne": "naoe", "vamo": "vamos",
    "aí": "ai", "tava": "estava", "tavam": "estavam", "tá": "esta",
}


def _sem_acento(t):
    t = unicodedata.normalize("NFKD", t)
    return "".join(c for c in t if not unicodedata.combining(c))


# Palavra funcional: artigo, preposicao, conjuncao. Some ou aparece na tela
# sem mudar o que foi dito -- `AGENDE A SUA` x `agende sua` e `APRENDEU O QUE`
# x `aprendeu que` sao os dois casos medidos no lote da Fulano. Nao sao
# parafrase, e reprovar por isso e' o portao reprovando peca aprovada.
FUNCIONAIS = {
    "a", "o", "as", "os", "um", "uma", "uns", "umas", "de", "da", "do",
    "das", "dos", "e", "em", "no", "na", "nos", "nas", "ao", "aos", "por",
    "para", "com", "que", "se", "ja", "la", "ai", "ate", "sua", "seu",
    "suas", "seus", "essa", "esse", "isso", "mais", "muito", "so",
}


def normalizar(texto, sem_funcionais=False):
    """Fita de letras minusculas, sem acento, sem pontuacao, sem espaco.

    Expande a reducao coloquial ANTES de colar os tokens, para os dois lados
    ficarem na mesma lingua. Com `sem_funcionais`, tira tambem artigo e
    preposicao -- e' a segunda passada, que separa "a tela mudou a PALAVRA"
    de "a tela ganhou um artigo".
    """
    limpo = _sem_acento(texto).lower()
    tokens = [PLENAS.get(t, t) for t in re.findall(r"[a-z0-9]+", limpo)]
    if sem_funcionais:
        tokens = [t for t in tokens if t not in FUNCIONAIS]
    return "".join(tokens)


def _seg_srt(linha):
    """`00:01:23,456 --> 00:01:25,789` -> (83.456, 85.789)."""
    def s(t):
        h, m, resto = t.split(":")
        seg, ms = resto.replace(".", ",").split(",")
        return int(h) * 3600 + int(m) * 60 + int(seg) + int(ms) / 1000.0
    a, b = linha.split("-->")
    return s(a.strip()), s(b.strip())


def fala_do_bruto(LOTE, v):
    """O que ela falou nas TOMADAS: `trabalho/N.srt` recortado pelas `faixas`.

    A fonte e' o `.srt` da FASE 0, que roda sobre o bruto inteiro e cujos
    tempos estao na linha do tempo do bruto -- a mesma em que `faixas` foi
    escrito.

    **Nao use `N_palavras_bruto.json`.** O nome promete bruto e o conteudo e'
    o CORTE: medido em 14/08/2026 no lote da Dra. Fulana, os dois arquivos tem
    os mesmos 134 tokens e terminam ambos em 27,76 s. A primeira versao deste
    portao leu esse arquivo, o recorte por `faixas` (que sao tempos do bruto)
    devolveu quase nada, e o resultado foi acusar O TEXTO INTEIRO das pecas
    como "so' na tela" em 4 de 8 videos. Portao que le o artefato errado
    reprova com confianca -- e foi por um fio que virou 4 falsos positivos.
    """
    caminho = os.path.join(LOTE.trabalho, f"{v}.srt")
    if not os.path.exists(caminho):
        return None
    faixas = LOTE.faixas.get(str(v)) or LOTE.faixas.get(v) or []
    pedacos, dentro = [], False
    with open(caminho, encoding="utf-8", errors="replace") as f:
        for linha in f:
            linha = linha.rstrip("\n")
            if "-->" in linha:
                try:
                    ini, fim = _seg_srt(linha)
                except ValueError:
                    dentro = False
                    continue
                meio = (ini + fim) / 2.0
                dentro = any(a <= meio <= b for a, b in faixas)
            elif dentro and linha.strip() and not linha.strip().isdigit():
                pedacos.append(linha.strip())
    return " ".join(pedacos)


def texto_queimado(LOTE, v):
    """Texto que o libass desenha, lido do `.ass` -- o artefato, nao a fonte.

    Cada grupo de legenda aparece em varias linhas `Dialogue` (uma por palavra
    destacada), com o MESMO texto. Duplicata consecutiva e' descartada, senao
    a fita fica com cada grupo repetido tres vezes e o diff vira lixo.
    """
    caminho = os.path.join(LOTE.trabalho, f"{v}_legenda.ass")
    if not os.path.exists(caminho):
        return None
    grupos, anterior = [], None
    with open(caminho, encoding="utf-8", errors="replace") as f:
        for linha in f:
            if not linha.startswith("Dialogue:"):
                continue
            corpo = linha.split(",", 9)[-1]
            corpo = re.sub(r"\{[^}]*\}", "", corpo)          # tags do ASS
            corpo = corpo.replace("\\N", " ").strip()
            if corpo and corpo != anterior:
                grupos.append(corpo)
                anterior = corpo
    return grupos


def esperadas(LOTE, v):
    """Trechos que a legenda DEVE ter porque foram corrigidos de proposito.

    `correcoes` do lote.json separa por virgula e usa `alvo=novo` (ou
    `contexto>alvo=novo`). Aqui so' interessa o lado direito: se o bloco que
    divergiu e' exatamente um texto que nos mandamos escrever, a divergencia
    e' a correcao funcionando, nao defeito.
    """
    regra = (LOTE.correcoes or {}).get(str(v), "")
    saida = []
    for parte in regra.split(","):
        if "=" in parte:
            saida.append(normalizar(parte.split("=", 1)[1]))
    return [s for s in saida if s]


def comparar(grupos, falado, aceitas):
    """Todo grupo que aparece NA TELA tem de existir na fala. Nada de diff.

    O primeiro desenho comparava as duas fitas inteiras com `difflib`, e nao
    funcionou: os segmentos do `.srt` da fase 0 duram ~4,5 s e um segmento que
    atravessa a borda da `faixa` arrasta para dentro fala que foi cortada
    fora -- direcao de camera, tomada descartada, "nao, nao, ta top". Com isso
    o alinhamento escorrega e o v3 da Fulano gerou 19 divergencias, quase todas
    ruido de borda.

    Containment nao depende de alinhamento: sobra de fala nao atrapalha, e as
    `faixas` sao coladas na ordem, entao grupo que cai em cima de uma emenda
    continua sendo achado.

    **A assimetria e' de proposito.** So' interessa texto que esta' NA TELA e
    nao foi dito -- e' esse que engana o paciente e queima CTA errado. O
    contrario (falou e nao entrou na tela) e' o corte funcionando.
    """
    fita = normalizar(falado)
    fita_nf = normalizar(falado, sem_funcionais=True)
    achados = []
    for texto in grupos:
        alvo = normalizar(texto)
        if len(alvo) < MIN_BLOCO or alvo in fita:
            continue
        if any(exp and exp in alvo for exp in aceitas):
            continue                     # e' uma `correcoes` nossa
        # Segunda passada: se casa ignorando artigo e preposicao, a PALAVRA
        # nao mudou -- so' a costura. Vira aviso, nao reprovacao.
        alvo_nf = normalizar(texto, sem_funcionais=True)
        if alvo_nf and alvo_nf in fita_nf:
            achados.append({"tela": texto.strip(), "normalizado": alvo,
                            "parecido_na_fala": "", "funcional": True})
            continue
        # Quase-achado: mostra o trecho da fala mais parecido, para dar o
        # contexto de onde ele DEVERIA estar.
        perto = difflib.get_close_matches(
            alvo, [fita[i:i + len(alvo)]
                   for i in range(0, max(1, len(fita) - len(alvo)), 4)],
            n=1, cutoff=0.5)
        achados.append({"tela": texto.strip(), "normalizado": alvo,
                        "parecido_na_fala": perto[0] if perto else "",
                        "funcional": False})
    return achados


def portao(videos=None):
    LOTE = config.carregar()
    alvos = videos or LOTE.videos
    if not alvos:
        raise SystemExit("nenhum video: `faixas` esta vazio no lote.json.")
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))))
    import completude                                       # noqa: E402
    cob = completude.Cobertura("portao de conteudo", alvos)
    pendentes = {}
    for v in alvos:
        falado, grupos = fala_do_bruto(LOTE, v), texto_queimado(LOTE, v)
        if falado is None or grupos is None:
            cob.pulado(v, "falta trabalho/N.srt (fase 0) ou N_legenda.ass "
                          "(fase 2)")
            print(f"v{v}: NAO COMPARADO (falta artefato)")
            continue
        achados = comparar(grupos, falado, esperadas(LOTE, v))
        # GUARDA DE ARTEFATO VELHO. Divergencia em quase tudo nao e' peca
        # com quase tudo errado -- e' o lado esquerdo nao sendo desta peca.
        # Medido no v3 da Fulano: 32 de 35 grupos "ausentes", com a fala
        # tratando de menopausa e a tela de osteoporose. Este foi o lote em
        # que os brutos foram RENUMERADOS na fonte, e o `.srt` da fase 0 ficou
        # apontando para o video antigo. Acusar 32 defeitos ali seria o
        # medidor cego se vendendo como laudo.
        if grupos and len(achados) > 0.6 * len(grupos):
            cob.pulado(v, f"{len(achados)}/{len(grupos)} grupos sem par - "
                          f"trabalho/{v}.srt parece ser de outro bruto "
                          f"(fase 0 anterior a uma renumeracao?). "
                          f"Rode a fase 0 de novo antes de confiar.")
            print(f"\n=== v{v} === {len(achados)}/{len(grupos)} sem par -> "
                  f"NAO COMPARAVEL (srt da fase 0 desatualizado)")
            continue
        cob.conferido(v, f"{len(grupos)} grupo(s) na tela, "
                         f"{len(achados)} nao encontrado(s) na fala")
        graves = [d for d in achados if not d["funcional"]]
        avisos = [d for d in achados if d["funcional"]]
        print(f"\n=== v{v} === {len(grupos)} grupos na tela, "
              f"{len(graves)} divergencia(s), {len(avisos)} aviso(s)")
        for d in graves:
            print(f"   NA TELA E NAO NA FALA: {d['tela']!r}")
            if d["parecido_na_fala"]:
                print(f"      mais parecido na fala: {d['parecido_na_fala']!r}")
        for d in avisos:
            print(f"   aviso (so' palavra funcional): {d['tela']!r}")
        if graves:
            pendentes[v] = graves
    cob.fechar(LOTE, "conteudo")
    if not pendentes:
        print("\nCONTEUDO: a tela diz o que ela falou.")
        return
    total = sum(len(a) for a in pendentes.values())
    raise SystemExit(
        f"\nCONTEUDO: {total} divergencia(s) em {len(pendentes)} video(s).\n"
        f"Ouca o trecho. Se a tela esta' errada, corrija com `correcoes` no "
        f"lote.json e REGERE a legenda. Se a fala foi transcrita errada e a "
        f"tela esta' certa, `correcoes` tambem e' o lugar -- o que nao pode "
        f"e' publicar sem olhar.")


if __name__ == "__main__":
    portao([a for a in sys.argv[1:] if a.isdigit()] or None)
