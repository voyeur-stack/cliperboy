#!/usr/bin/env python3
"""PAINEL DE 3 LENTES para defeito reportado pelo cliente ou pela analista.

**O problema.** Quando chega "o video 3 ta com defeito aos 00:18", hoje eu vou
la', acho ALGUMA coisa, conserto e devolvo. No lote da Dra. Fulana isso
produziu um conserto republicado que nao consertava nada -- eu tinha achado
UM defeito no ponto reportado, e nao O defeito que ela viu. Na outra ponta, o
`integridade.py` do lote do Dr. Fulano reprovou 17 de 34 pecas boas. Juiz unico
erra para os dois lados, e erra sozinho.

**A mecanica, copiada do `claude-security` da Anthropic** (os prompts de la'
sao literais no repositorio; o que segue e' a adaptacao, nao a copia):

  - Tres lentes, nao tres opinioes. Cada juiz recebe UMA pergunta diferente e
    nao ve o voto dos outros.
  - **A soma e' feita AQUI, em codigo, nunca por um modelo lendo tres
    pareceres.** Painel com menos de 3 votos nao e' aceitavel.
  - Vies travado nos DOIS sentidos: o padrao e' FALSO POSITIVO, mas matar
    achado real com defesa imaginada e' a mesma falha apontada ao contrario.
  - **Voto sem citacao nao conta.** La' e' `arquivo:linha`; aqui e'
    `arquivo:timestamp` mais a medida (dB, ms, quadro).
  - **Teto de confianca em codigo:** painel dividido 2-a-1 nao pode dizer
    confianca alta, e este script REBAIXA se o veredito tentar.

**A inversao que o nosso caso permite.** La' o juiz nao pode executar nada, e
por isso "so' da' para saber rodando" e' automaticamente falso positivo. Aqui
medir o artefato entregue e' barato -- entao a regra vira o contrario:
**juiz que nao mediu o arquivo entregue nao vota.** Por isso a fase 1 deste
script e' MEDICAO, e o dossie que ela produz e' o unico insumo dos juizes.

Uso, em duas etapas:

    # 1) mede o artefato no ponto reportado e escreve o dossie
    python scripts/painel.py --lote "<lote>" 3 00:18

    # 2) depois de colher os 3 votos, soma com quorum e teto de confianca
    python scripts/painel.py --lote "<lote>" --somar relatorio/painel-v3-18.0s.json
"""
import json
import math
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config                                              # noqa: E402
import relatorio                                           # noqa: E402

JANELA = 2.5          # segundos de cada lado do ponto reportado
PASSO = 0.1           # resolucao da leitura de energia
LENTES = ("REPRODUCAO", "IMPACTO", "DEFESAS")
QUORUM = 2            # de 3


def instante(txt):
    """Aceita `18`, `18.4`, `0:18`, `00:18`, `1:02.5`."""
    txt = txt.strip()
    if ":" in txt:
        partes = [float(p) for p in txt.split(":")]
        seg = 0.0
        for p in partes:
            seg = seg * 60 + p
        return seg
    return float(txt)


def energia(src, t0, t1):
    """dB por janela de PASSO segundos no trecho, lido do arquivo ENTREGUE."""
    r = subprocess.run(
        ["ffmpeg", "-hide_banner", "-v", "error", "-ss", f"{max(0, t0):.3f}",
         "-t", f"{t1 - t0:.3f}", "-i", src, "-vn", "-ac", "1", "-ar", "8000",
         "-f", "s16le", "-"], capture_output=True)
    import array
    d = array.array("h")
    d.frombytes(r.stdout[: len(r.stdout) // 2 * 2])
    n = int(8000 * PASSO)
    out = []
    for i in range(0, max(0, len(d) - n), n):
        s = sum(x * x for x in d[i:i + n])
        rms = math.sqrt(s / n) / 32768.0
        out.append(round(20 * math.log10(rms) if rms > 1e-9 else -120.0, 1))
    return out


def para_bruto(segs, t):
    """Instante da peca -> (indice do trecho, instante no bruto)."""
    acc = 0.0
    for i, (a, b) in enumerate(segs):
        dur = b - a
        if t <= acc + dur:
            return i, round(a + (t - acc), 3)
        acc += dur
    return None, None


def emendas(segs):
    """Instantes da PECA em que dois trechos do bruto foram colados."""
    acc, pontos = 0.0, []
    for a, b in segs[:-1]:
        acc += b - a
        pontos.append(round(acc, 3))
    return pontos


def texto_na_tela(LOTE, v, t0, t1):
    """O que o libass desenha na janela -- do `.ass`, que e' o que foi ao ar."""
    caminho = os.path.join(LOTE.trabalho, f"{v}_legenda.ass")
    if not os.path.exists(caminho):
        return []
    def s(x):
        h, m, resto = x.split(":")
        return int(h) * 3600 + int(m) * 60 + float(resto)
    vistos, saida = None, []
    for linha in open(caminho, encoding="utf-8", errors="replace"):
        if not linha.startswith("Dialogue:"):
            continue
        campos = linha.split(",", 9)
        try:
            ini, fim = s(campos[1]), s(campos[2])
        except ValueError:
            continue
        if fim < t0 or ini > t1:
            continue
        corpo = re.sub(r"\{[^}]*\}", "", campos[-1]).replace("\\N", " ").strip()
        if corpo and corpo != vistos:
            saida.append({"ini": round(ini, 2), "fim": round(fim, 2),
                          "texto": corpo})
            vistos = corpo
    return saida


def medir(LOTE, v, t, descricao=""):
    saida = os.path.join(LOTE.saida, f"{v}_PRONTO.mp4")
    if not os.path.exists(saida):
        raise SystemExit(f"peca entregue nao encontrada: {saida}")
    segs = []
    corte = os.path.join(LOTE.trabalho, f"{v}_corte.json")
    if os.path.exists(corte):
        segs = json.load(open(corte, encoding="utf-8"))
    t0, t1 = max(0.0, t - JANELA), t + JANELA
    idx, no_bruto = para_bruto(segs, t) if segs else (None, None)
    pontos = emendas(segs) if segs else []
    perto = [p for p in pontos if abs(p - t) <= JANELA]
    dur = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", saida], capture_output=True, text=True).stdout.strip()
    dossie = {
        "lote": LOTE.nome, "video": v, "reportado_em": round(t, 2),
        "descricao_recebida": descricao,
        "arquivo": {
            "caminho": saida,
            "bytes": os.path.getsize(saida),
            "mtime": os.path.getmtime(saida),
            "duracao_s": float(dur) if dur else None,
        },
        "janela": [round(t0, 2), round(t1, 2)],
        "no_bruto": {"trecho": idx, "instante": no_bruto,
                     "arquivo": os.path.basename(LOTE.bruto_de(v))},
        "emendas_na_janela": perto,
        "energia_db": energia(saida, t0, t1),
        "energia_passo_s": PASSO,
        "texto_na_tela": texto_na_tela(LOTE, v, t0, t1),
        "votos": [],
    }
    return dossie


def somar(caminho):
    """Aplica quorum e TETO DE CONFIANCA. E' a unica parte que decide."""
    d = json.load(open(caminho, encoding="utf-8"))
    votos = d.get("votos", [])
    if len(votos) != 3:
        raise SystemExit(
            f"painel incompleto: {len(votos)} voto(s) de 3. Painel com menos "
            f"de tres votos nao e' aceitavel -- o quorum deixa de existir.")
    lentes = {v.get("lente") for v in votos}
    if lentes != set(LENTES):
        raise SystemExit(f"as tres lentes tem de ser {LENTES}; vieram {lentes}")
    # Voto sem citacao nao conta. E' a trava contra o parecer bonito e vazio.
    sem_prova = [v["lente"] for v in votos if not str(v.get("citacao", "")).strip()]
    if sem_prova:
        raise SystemExit(
            f"voto sem citacao em {sem_prova}. Todo voto cita arquivo:timestamp "
            f"e a medida que o sustenta (dB, ms, quadro). Quem nao mediu o "
            f"arquivo entregue nao vota.")
    reais = sum(1 for v in votos if v.get("veredito") == "DEFEITO_REAL")
    manter = reais >= QUORUM
    teto = "alta" if reais == 3 else "media"
    pedida = str(d.get("confianca_pedida", "")).lower()
    confianca = teto
    if pedida in ("alta", "media", "baixa"):
        ordem = {"baixa": 0, "media": 1, "alta": 2}
        confianca = pedida if ordem[pedida] <= ordem[teto] else teto
        if confianca != pedida:
            print(f"   confianca REBAIXADA de '{pedida}' para '{teto}': "
                  f"painel {reais}-{3 - reais} nao sustenta mais que isso.")
    d["resultado"] = {"votos_reais": reais, "quorum": QUORUM,
                      "defeito_confirmado": manter, "confianca": confianca}
    json.dump(d, open(caminho, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"\nPAINEL v{d['video']} @ {d['reportado_em']}s: "
          f"{reais}/3 confirmam -> "
          f"{'DEFEITO REAL' if manter else 'NAO CONFIRMADO'} "
          f"(confianca {confianca})")
    for v in votos:
        print(f"   {v['lente']:11s} {v.get('veredito', '?'):14s} "
              f"{v.get('citacao', '')}")
    if not manter:
        print("\nNao vira conserto. Registrado como nao confirmado -- e' o "
              "passo que faltou quando republiquei um conserto que nao "
              "consertava nada.")
    return d


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if "--somar" in sys.argv:
        i = sys.argv.index("--somar")
        return somar(sys.argv[i + 1])
    LOTE = config.carregar()
    numeros = [a for a in args if a.isdigit()]
    tempos = [a for a in args if a not in numeros and re.match(r"^[\d:.]+$", a)]
    if not numeros or not tempos:
        raise SystemExit(
            'uso: painel.py --lote "<lote>" <video> <timestamp> ["descricao"]')
    v, t = int(numeros[0]), instante(tempos[0])
    descricao = " ".join(a for a in args if a not in numeros and a not in tempos)
    d = medir(LOTE, v, t, descricao)
    nome = f"painel-v{v}-{t:g}s"
    caminho = os.path.join(relatorio.pasta(LOTE), f"{nome}.json")
    json.dump(d, open(caminho, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    print(f"\nDOSSIE v{v} @ {t:g}s  ->  {caminho}")
    print(f"  arquivo entregue: {d['arquivo']['bytes']:,} bytes, "
          f"{d['arquivo']['duracao_s']}s")
    print(f"  no bruto: trecho {d['no_bruto']['trecho']} @ "
          f"{d['no_bruto']['instante']}s de {d['no_bruto']['arquivo']}")
    print(f"  emendas na janela: {d['emendas_na_janela'] or 'nenhuma'}")
    print(f"  energia (dB, passo {PASSO}s): {d['energia_db']}")
    print("  texto na tela:")
    for g in d["texto_na_tela"]:
        print(f"     {g['ini']:6.2f}-{g['fim']:6.2f}  {g['texto']!r}")
    print(f"""
Agora despache TRES juizes independentes, um por lente, cada um recebendo
SO' este dossie e a sua pergunta. Nenhum ve o voto do outro.

  REPRODUCAO - o defeito descrito esta' no arquivo entregue, neste instante?
  IMPACTO    - quem assiste percebe? e' a peca que foi publicada?
  DEFESAS    - algum passo posterior ja' corrigiu isto sozinho?

Regra dada a todos, nos dois sentidos:
  O padrao e' FALSO_POSITIVO. So' vote DEFEITO_REAL com a medida que sustenta,
  citada como arquivo:timestamp. E nao mate um achado com uma defesa que voce
  nao mediu -- matar defeito real com defesa imaginada e' a mesma falha
  apontada ao contrario. Julgue o defeito COMO FOI DESCRITO: outro problema
  real ali perto nao torna este verdadeiro.

Escreva os votos em `votos` no proprio json:
  {{"lente": "REPRODUCAO", "veredito": "DEFEITO_REAL"|"FALSO_POSITIVO",
    "citacao": "{os.path.basename(d['arquivo']['caminho'])}:{t:g}s -21,3 dB",
    "razao": "uma ou duas linhas"}}

Depois:  python scripts/painel.py --lote "{LOTE.nome}" --somar "{caminho}"
""")


if __name__ == "__main__":
    main()
