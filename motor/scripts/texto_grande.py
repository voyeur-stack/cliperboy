#!/usr/bin/env python3
"""Insere o momento de 'texto na cara' no .ass da legenda.

No padrao do operador, durante esse efeito a legenda pequena SOME e a
frase inteira aparece grande sobre o video borrado. Entao aqui eu removo
os eventos de legenda que caem na janela e ponho o bloco grande no lugar,
com a deriva lenta pra baixo que ele usa.

Uso: python texto_grande.py <ass> <ini> <fim> <"LINHA 1|LINHA 2"> [estilo.json]
"""
import json
import sys

ass, ini, fim, texto = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]), sys.argv[4]

FONTE, CORPO, COR = "Anton", 200, "&H00FFFFFF"

# argv[5] opcional: o MESMO JSON de estilo que o gerar_ass.py recebe.
#
# Por que existe: a frase em destaque e o unico elemento da peca que fica
# fora dos consertos feitos na legenda -- ja aconteceu DUAS vezes aqui (o
# roubo de token de pontuacao e a correcao de termo clinico, que foi para a
# tela em corpo 200 errada enquanto a legenda pequena mostrava o certo, no
# mesmo minuto). Cor e fonte novas nao podem repetir isso: se a legenda e
# #F8E2C2 em Red Hat Display e a frase grande continua branca em Anton, a
# peca sai com duas tipografias.
if len(sys.argv) > 5 and sys.argv[5]:
    _e = json.loads(open(sys.argv[5], encoding="utf-8").read())
    if _e.get("fonte"):
        FONTE = _e["fonte"]
    # `fonte_destaque` troca a fonte SO' da frase grande, mantendo a legenda
    # pequena na `fonte`. Nasceu no lote do Dr. Fulano (21/08/2026): o
    # cliente mandou a familia Manier com DOIS pesos e papeis declarados --
    # "MANIER (Base)" na legenda e "MANIER - Hv (destaque)" na frase grande.
    # Sem esta chave os dois elementos ficam presos ao mesmo peso, e a unica
    # saida seria a peca inteira num peso so'.
    #
    # ARMADILHA: no libass cada peso da Manier e' uma FAMILIA diferente
    # ('Manier -Trial' e 'Manier Heavy-Trial'), nao um peso da mesma familia.
    # Pedir negrito na mesma familia NAO traz a Heavy -- o libass engorda a
    # Regular sinteticamente e sai calado. Por isso a chave e' o nome da
    # fonte, nao um booleano de peso.
    if _e.get("fonte_destaque"):
        FONTE = _e["fonte_destaque"]
    if _e.get("cor_texto_destaque") or _e.get("cor_legenda"):
        h = (_e.get("cor_texto_destaque") or _e["cor_legenda"]).lstrip("#")
        COR = f"&H00{h[4:6]}{h[2:4]}{h[0:2]}".upper()
    if _e.get("corpo_destaque"):
        CORPO = int(_e["corpo_destaque"])

ESTILO = (f"Style: Grande,{FONTE},{CORPO},{COR},&H00000000,&H80000000,"
          "0,0,1,0,6,5,60,60,60,1")


def ts(s):
    h, s = divmod(max(0.0, s), 3600)
    m, s = divmod(s, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def seg(l):
    p = l.split(",", 4)
    def sec(t):
        h, m, s = t.split(":")
        return int(h) * 3600 + int(m) * 60 + float(s)
    return sec(p[1]), sec(p[2])


saida, inseriu, removidos, aparados = [], False, 0, 0
for l in open(ass, encoding="utf-8"):
    if l.startswith("Style:") and "Legenda," in l:
        saida.append(l)
        saida.append(ESTILO + "\n")
        continue
    if l.startswith("Dialogue"):
        a, b = seg(l)
        if b > ini and a < fim:          # colide com a janela
            if not inseriu:
                corpo = texto.replace("|", r"\N")
                saida.append(
                    f"Dialogue: 0,{ts(ini)},{ts(fim)},Grande,,0,0,0,,"
                    f"{{\\an5\\pos(540,960)}}{corpo}\n")
                inseriu = True
            # APARAR, nao apagar. A versao anterior descartava o evento
            # INTEIRO quando ele apenas ENCOSTAVA na janela, e com isso uma
            # palavra que e' dita ANTES do texto grande sumia da tela.
            #
            # Custo real (v5 da Dra. Fulana pt2, 11/08/2026): o grupo
            # 'BALANÇA.' ia de 18,33 a 19,4 s e a janela comecava em 18,99;
            # como o fim caia dentro, o evento foi apagado e a palavra nunca
            # apareceu -- 'E ISSO NÃO MUDA NA' e a frase morria ali. O
            # operador viu na tela; verificacao numerica nenhuma pega isso,
            # porque o .ass fica valido e o texto do .srt continua completo.
            #
            # Agora o evento e' cortado na borda da janela e so' e' descartado
            # quando o pedaco que sobra fica curto demais para ser lido (o
            # mesmo piso de 80 ms que o gerar_ass usa) ou quando ele esta
            # inteiramente dentro da janela, que e' o caso que a regra
            # original queria tratar.
            # 0,25 s, nao os 80 ms do gerar_ass: aquele piso existe para uma
            # PALAVRA destacada dentro de um grupo que continua na tela, e
            # aqui o que sobra e' o grupo inteiro aparecendo sozinho. Medido
            # no v5 (Fulano pt2): 'ROSTO E' sobrou com 0,10 s = 3 quadros, o
            # que se le como piscada, nao como legenda. Abaixo disso o resto
            # e' descartado -- e a perda e' pequena por construcao, porque
            # essas palavras estao dentro da frase que o texto grande mostra.
            PISO = 0.25
            partes = []
            if a < ini - PISO:
                partes.append((a, ini))
            if b > fim + PISO:
                partes.append((fim, b))
            if not partes:
                removidos += 1
                continue
            cab_l, resto = l.split(",", 1)
            campos = resto.split(",", 2)
            for x, y in partes:
                saida.append(f"{cab_l},{ts(x)},{ts(y)},{campos[2]}")
            aparados += 1
            continue
    saida.append(l)


# APARAR TAMBEM POR TEXTO, nao so por tempo. O grupo de legenda e' formado
# antes de o texto grande existir, entao ele pode ATRAVESSAR a borda da
# janela: 'ELEGANTE NA' comecava em 9,04 s, exatamente onde o texto grande
# acabava (lote 62, Dra. Fulana, 21/09/2026). Por tempo o evento
# nao colide -- e 'ELEGANTE', que acabou de sair em corpo 200, volta como
# contexto branco na legenda pequena. O operador viu: "a ultima palavra do
# efeito saiu na legenda depois dele ainda". O simetrico existe antes da
# janela: o grupo que termina em `ini` pode carregar, como contexto final,
# a primeira palavra do texto grande.
#
# Aqui o primeiro evento depois da janela perde as palavras INICIAIS de
# contexto que sao o FIM do texto grande, e o ultimo evento antes dela perde
# as palavras FINAIS de contexto que sao o COMECO do texto. So contexto
# (texto plano fora das tags de cor); a palavra destacada nunca e' tocada.
import re as _re

def _norm(w):
    return _re.sub(r"[^\wÀ-ÿ]", "", w).upper()

_palavras_grande = [_norm(w) for w in _re.split(r"[ |]+", texto) if _norm(w)]
_TOL = 0.05
_RE_INICIO = _re.compile(r"^((?:\{[^}]*\})*)([^{]*)(.*)$", _re.S)


def _apara_inicio(txt):
    """Tira do contexto inicial as palavras que fecham o texto grande."""
    m = _RE_INICIO.match(txt)
    tags, plano, resto = m.group(1), m.group(2), m.group(3)
    palavras = plano.split()
    # o maior bloco INICIAL do evento que e' o bloco FINAL do texto grande
    n = next((k for k in range(min(len(palavras), len(_palavras_grande)), 0, -1)
              if [_norm(w) for w in palavras[:k]] == _palavras_grande[-k:]), 0)
    if not n:
        return txt, 0
    sobra = " ".join(palavras[n:])
    return tags + (sobra + " " if sobra else "") + resto, n


def _apara_fim(txt):
    """Tira do contexto final as palavras que abrem o texto grande."""
    k = txt.rfind("}")
    if k < 0:
        return txt, 0
    cabeca, plano = txt[:k + 1], txt[k + 1:]
    palavras = plano.split()
    # o maior bloco FINAL do evento que e' o bloco INICIAL do texto grande
    n = next((k for k in range(min(len(palavras), len(_palavras_grande)), 0, -1)
              if [_norm(w) for w in palavras[-k:]] == _palavras_grande[:k]), 0)
    if not n:
        return txt, 0
    sobra = " ".join(palavras[:len(palavras) - n])
    return cabeca + (" " + sobra if sobra else ""), n


_por_texto = 0
_antes = _depois = None
for i, l in enumerate(saida):
    if not (l.startswith("Dialogue") and ",Legenda," in l):
        continue
    a, b = seg(l)
    if b <= ini + _TOL:
        _antes = i                      # o ultimo que termina na janela
    if a >= fim - _TOL and _depois is None:
        _depois = i                     # o primeiro que comeca na janela
for i, fn in ((_depois, _apara_inicio), (_antes, _apara_fim)):
    if i is None:
        continue
    cab, resto = saida[i].split(",", 1)
    campos = resto.rstrip("\n").split(",", 8)
    novo, n = fn(campos[8])
    if n:
        campos[8] = novo
        saida[i] = cab + "," + ",".join(campos) + "\n"
        _por_texto += n

open(ass, "w", encoding="utf-8").writelines(saida)
if _por_texto:
    print(f"texto grande: {_por_texto} palavra(s) de contexto repetida(s) "
          f"aparada(s) nos eventos vizinhos")
print(f"texto grande {ini}->{fim}s inserido | {removidos} evento(s) de "
      f"legenda removidos da janela, {aparados} aparado(s) na borda")
