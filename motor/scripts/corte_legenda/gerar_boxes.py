#!/usr/bin/env python3
"""Gera os PNGs das 3 boxes no modelo da referencia de 24/07.

Nada aqui e' estimativa. A regua saiu medida do PNG aprovado
`Frases/Consultório lotado Caixa vazio.png` (1081x185):

  * fonte     Hoefler Text -- casada por diferenca de pixel contra a
              referencia: 4,75% de discordancia, contra 13,0% do segundo
              colocado (Times). Ver `scripts/analise` do lote.
  * corpo     67 px -> "Consultório lotado." mede 547 px, exatamente a
              largura da referencia; "Caixa vazio." da 332 contra 331.
  * linhas    passo de 66 px entre as bases (83 -> 149 no PNG)
  * margens   34 px acima do topo das maiusculas, 35 px abaixo da ultima
  * sirene    recortada do proprio PNG aprovado (x 27..103, y 41..142),
              nao redesenhada -- e' o mesmo bitmap, com a mesma sombra
  * largura   texto limitado a 830 px, o vao entre as sirenes com folga

O corpo cai abaixo de 67 px so' quando a linha mais longa nao couber nos
830 px -- que e' o que a propria arte do operador faz nas frases longas.
"""
import os
import sys

from PIL import Image, ImageDraw, ImageFont

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
from lote import BOXES as SAIDA, FRASES, L, RAIZ  # noqa: E402

# PNG de referencia da regua das boxes. E' so' consulta visual — o modelo ja'
# esta medido nas constantes abaixo. Fica no lote.json porque e' caminho de
# Drive, e Drive nao tem a mesma letra em toda maquina.
REF = L._dados.get("referencia_box", "")


def _fonte():
    """Acha a fonte das boxes, em ordem: lote.json > assets/fonts > perfil.

    ⚠️ Ate 10/08/2026 isto era caminho fixo para `Hoefler Text Regular.ttf`
    dentro de `%LOCALAPPDATA%\\Microsoft\\Windows\\Fonts` — fonte instalada
    NO PERFIL de um usuario especifico. Em outra maquina o script morre com
    "cannot open resource", e o erro nao diz que o problema e' a fonte.

    Por decisao do operador (10/08/2026), a fonte foi COPIADA para
    `assets/fonts/Hoefler Text Regular.ttf` e viaja com o repositorio — que
    e' privado e tem a equipe de edicao como unico publico. E' de la' que
    ela resolve agora; o caminho do perfil ficou so' como ultimo recurso.
    """
    do_lote = L._dados.get("fonte_box")
    if do_lote and os.path.exists(do_lote):
        return do_lote
    nosso = os.path.join(RAIZ, "assets", "fonts", "Hoefler Text Regular.ttf")
    if os.path.exists(nosso):
        return nosso
    perfil = os.path.join(os.environ.get('LOCALAPPDATA', ''),
                          r'Microsoft\Windows\Fonts\Hoefler Text Regular.ttf')
    if os.path.exists(perfil):
        return perfil
    sys.exit(
        "Nao achei a fonte das boxes ('Hoefler Text Regular.ttf').\n"
        "Procurei em: `fonte_box` do lote.json, `assets/fonts/` e o perfil "
        "do usuario.\nInstale a fonte, ou aponte `fonte_box` no lote.json "
        "para o arquivo .ttf."
    )


FONTE = _fonte()

LARG = 1081
CORPO_MAX = 67
LARG_TEXTO = 830
MARGEM_TOPO = 34
MARGEM_BASE = 35
SIRENE = (27, 41, 104, 143)      # caixa da sirene esquerda no PNG de ref

# Texto validado com o operador em 03/08/2026: vale o que ele digitou, com
# FRASES vem de `frases` no lote.json (importado de `lote.py`). Cada valor e'
# a lista de LINHAS ja' quebradas, porque a quebra e' decisao de layout.
# Duas correcoes que ele aceitou estao gravadas la': "horarios" no plural (a
# arte dele e o primeiro anexo dizem plural) e "ta" com acento.


def sirenes():
    ref = Image.open(REF).convert('RGBA')
    esq = ref.crop(SIRENE)
    return esq, esq.transpose(Image.FLIP_LEFT_RIGHT)


def corpo_que_cabe(linhas):
    """Maior corpo <= CORPO_MAX em que a linha mais longa cabe em LARG_TEXTO."""
    for s in range(CORPO_MAX, 20, -1):
        f = ImageFont.truetype(FONTE, s)
        if max(f.getbbox(l)[2] - f.getbbox(l)[0] for l in linhas) <= LARG_TEXTO:
            return s, f
    raise SystemExit("nenhum corpo serve")


def montar(linhas):
    corpo, f = corpo_que_cabe(linhas)
    passo = round(66 * corpo / 67)
    # altura das maiusculas neste corpo (medida em 'H', sem acento nem descida)
    bb = f.getbbox("H")
    alt_cap = bb[3] - bb[1]
    alt = MARGEM_TOPO + alt_cap + (len(linhas) - 1) * passo + MARGEM_BASE

    im = Image.new('RGBA', (LARG, alt), (255, 255, 255, 255))
    d = ImageDraw.Draw(im)
    esq, dir_ = sirenes()
    ys = (alt - esq.height) // 2
    im.alpha_composite(esq, (SIRENE[0], ys))
    im.alpha_composite(dir_, (LARG - SIRENE[0] - esq.width, ys))

    # a base da 1a linha fica em MARGEM_TOPO + alt_cap
    base1 = MARGEM_TOPO + alt_cap
    for i, linha in enumerate(linhas):
        lb = f.getbbox(linha)
        x = (LARG - (lb[2] - lb[0])) // 2 - lb[0]
        # getbbox e' relativo ao topo do desenho; bb[3] e' a base do 'H'
        y = base1 + i * passo - bb[3]
        d.text((x, y), linha, font=f, fill=(0, 0, 0, 255))
    return im, corpo, alt


if __name__ == "__main__":
    os.makedirs(SAIDA, exist_ok=True)
    for n, linhas in FRASES.items():
        im, corpo, alt = montar(linhas)
        p = os.path.join(SAIDA, f"frase{n}.png")
        im.save(p)
        print(f"frase {n}: {LARG}x{alt}, corpo {corpo} px, "
              f"{len(linhas)} linhas -> {os.path.basename(p)}")
