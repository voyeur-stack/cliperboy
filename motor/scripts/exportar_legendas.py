#!/usr/bin/env python3
"""Exporta as legendas do lote para a pasta Legendas do Drive (o analista usa).

Dois arquivos por video, com o NOME de entrega que vem de `nomes` no lote.json
(obrigatorio: o script sai com erro se o video nao tiver nome la' -- o antigo
fallback `Video N` deixava o analista sem ligar legenda a video). Ex.:
`V1 - <o que fala> - Dr. Fulano`.

  <nome>.srt   -- exatamente o que esta QUEIMADO na tela, com o tempo certo.
                  Sai do proprio `.ass` do render, que ja tem as correcoes de
                  revisao aplicadas. O `.ass` tem UM evento por palavra (o
                  destaque em amarelo anda palavra a palavra); aqui os eventos
                  consecutivos de mesmo texto viram uma legenda so.
  <nome>.txt   -- o texto corrido, em caixa normal e com pontuacao, para ler
                  e reaproveitar. Sai do `_corte.srt` com as MESMAS correcoes
                  do render aplicadas por cima (mesma logica do gerar_ass.py).

Por que nao usar o `_corte.srt` direto: ele e a saida crua do whisper e NAO
tem as correcoes ("saiu?" em vez de "saiu,", "lipedema" em vez de "LPDMA",
"Agende sua" em vez de "A gente so"). Entregar ele seria entregar texto que
nao bate com o video.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config                                            # noqa: E402

LOTE = config.carregar()
DEST = os.path.join(LOTE.entrega, "Legendas")

# Origem por video: (.ass do render, .srt do corte). O `.ass` e o que foi
# QUEIMADO na tela; o `.srt` do corte e a base para o texto corrido.
FONTES = {v: (os.path.join(LOTE.trabalho, f"{v}_legenda.ass"),
              os.path.join(LOTE.trabalho, f"{v}_corte.srt"))
          for v in LOTE.videos}
# Videos produzidos fora do fluxo do lote entram por `observacoes.<v>.fontes`
# no lote.json. No lote de julho e o caso do video 7, que foi feito antes por
# produzir_v7b.py e cujos artefatos se chamam v7b_*. Sem isso, uma varredura
# por numero de video pula ele EM SILENCIO e a pasta sai com um a menos.
for v, extra in (LOTE.observacoes.get("_fontes_extras") or {}).items():
    FONTES[v] = (os.path.join(LOTE.trabalho, extra[0]),
                 os.path.join(LOTE.trabalho, extra[1]))


def ts(seg):
    h, seg = divmod(max(0.0, seg), 3600)
    m, seg = divmod(seg, 60)
    return f"{int(h):02d}:{int(m):02d}:{seg:06.3f}".replace(".", ",")


def do_ass(caminho):
    """Eventos do .ass -> [(ini, fim, texto)], juntando repeticoes."""
    cues = []
    for linha in open(caminho, encoding="utf-8"):
        if not linha.startswith("Dialogue:"):
            continue
        p = linha.split(",", 9)

        def seg(t):
            h, m, s = t.split(":")
            return int(h) * 3600 + int(m) * 60 + float(s)

        a, b = seg(p[1]), seg(p[2])
        txt = re.sub(r"\{[^}]*\}", "", p[9]).strip()
        txt = txt.replace(r"\N", "\n")
        if not txt:
            continue
        if cues and cues[-1][2] == txt and abs(cues[-1][1] - a) < 0.15:
            cues[-1][1] = b                      # mesma frase, so mudou o realce
        else:
            cues.append([a, b, txt])
    return cues


def _base(t):
    return re.sub(r"[^\wÀ-ÿ]", "", t).lower()


def do_txt(srt, correcoes):
    """Palavras do _corte.srt com as correcoes do render (gerar_ass.py §CORR)."""
    ref = []
    for linha in open(srt, encoding="utf-8"):
        linha = linha.strip()
        if linha and not linha.isdigit() and "-->" not in linha:
            ref.extend(linha.split())
    fora = []
    for i, p in enumerate(ref):
        b = _base(p)
        prox = _base(ref[i + 1]) if i + 1 < len(ref) else ""
        novo = correcoes.get(f"{b}>{prox}", correcoes.get(b))
        if novo is None:
            continue
        if novo == "":
            fora.append(i)
        elif novo.endswith("~"):
            ref[i] = novo[:-1]
        elif re.search(r"[^\wÀ-ÿ]", novo):
            # MESMO conserto de `gerar_ass.py` (12/08/2026, lote da Dra. Fulana
            # Fulano), e o bug existia aqui pelo mesmo motivo: esta funcao
            # NAO le o `.ass`, ela reaplica as correcoes por conta propria a
            # partir do `_corte.srt`. Duas copias da mesma regra, e o conserto
            # de uma nao chega na outra.
            #
            # `_base` tira pontuacao E poe em minuscula, entao qualquer valor
            # com MAIUSCULA caia aqui e trocava o token inteiro, apagando a
            # pontuacao. Medido: `cidade=Cidade` entregou "em Cidade"
            # sem ponto final, e `termo=TERMO` entregou "o TERMO uma
            # tecnologia" sem virgula -- no `.txt`, que e' o arquivo que o
            # analista usa para a legenda do post.
            #
            # O `.ass` ja estava certo depois do conserto de la': foi comparar
            # os dois que revelou esta segunda copia.
            ref[i] = novo
        else:
            ref[i] = novo + p[len(b):]
    ref = [p for i, p in enumerate(ref) if i not in set(fora)]
    texto = " ".join(ref)
    # Nao quebrar depois de abreviacao: o ponto de "Dr." nao termina frase, e
    # o .txt do Dr. Fulano saia com "I'm Dr." numa linha e o nome na seguinte.
    ABREV = (r"(?<!\bDr\.)(?<!\bDra\.)(?<!\bSr\.)(?<!\bSra\.)"
             r"(?<!\bProf\.)(?<!\bMr\.)(?<!\bMrs\.)")
    # Fim de frase tambem quando a pontuacao vem ANTES de uma aspa de
    # fechamento (`artificial."`): sem isto a citacao e a frase seguinte
    # saiam na mesma linha (v8 da Fulano, 17/09/2026).
    frases = [f.strip()
              for f in re.split(ABREV + r"(?<=[.?!])\s+|(?<=[.?!][\"”])\s+", texto)
              if f.strip()]
    return "\n".join(frases) + "\n"


os.makedirs(DEST, exist_ok=True)
_CARIMBO = __import__("time").strftime("%Y%m%d-%H%M")
for v in sorted(FONTES, key=int):
    ass, srt = FONTES[v]
    # `strip()` na chave nao e' cosmetico: sem ele, "a=b, c=d" produz a chave
    # " c" (com o espaco depois da virgula) e ela NUNCA casa com `_base()`,
    # que ja vem sem espaco. O efeito e' a segunda correcao em diante sumir
    # CALADA — a primeira aplica, o resto nao, e nada avisa. Achado no lote
    # do Dr. Fulano (11/08/2026): o `.txt` entregue saiu com "receita
    # propria" enquanto o video queimado dizia "PRONTA", porque `vazio=`
    # (primeira) pegou e ` propria=` (segunda) nao. O `lote_produzir.py` ja
    # fazia strip+lower desde sempre; era so o exportador que divergia.
    corr = {}
    for par in LOTE.correcoes.get(v, "").split(","):
        if "=" in par:
            k, val = par.split("=", 1)
            corr[k.strip().lower()] = val.strip()
    cues = do_ass(ass)

    # VINHETA: o `.ass` esta na timeline do RENDER, que nao tem a vinheta. A
    # peca ENTREGUE tem a vinheta enfiada no meio, entao tudo que vem depois
    # dela anda para a frente. Sem este deslocamento o `.srt` fica ate 4,9 s
    # adiantado do segundo ato em diante -- no v6 o arquivo terminava em
    # 37,3 s para um video de 47,4 s.
    #
    # A regra do projeto e' que o `.srt` espelha A TELA. Se a tela mudou de
    # relogio, o `.srt` muda junto; senao ele deixa de servir para o unico
    # uso que tem, que e conferir contra o video.
    corte = (LOTE.vinheta_em or {}).get(str(v)) if getattr(LOTE, "vinheta", None) else None
    if corte is not None:
        import subprocess as _sp
        vin = LOTE.vinheta.get("arquivo", "")
        if not os.path.isabs(vin):
            vin = os.path.join(LOTE.pasta, vin)
        _r = _sp.run(["ffprobe", "-v", "error", "-show_entries",
                      "format=duration", "-of", "default=nw=1:nk=1", vin],
                     capture_output=True, text=True)
        if _r.returncode:
            sys.exit(f"v{v} ABORTADO: nao consegui medir a vinheta -> {vin}")
        dur_vin = float(_r.stdout.strip())
        # ENCAIXAR NA GRADE, igual ao `montar_abertura.py`. Ele corta em
        # `round(t*fps)/fps` e o `.srt` tem de usar o MESMO instante, senao a
        # legenda partida sobra ou falta alguns ms sobre a vinheta -- medido
        # em 15/08: 3 ms no v2 (pedido 6,730, real 6,733) e 10 ms no v3
        # (pedido 4,910, real 4,900). Sub-quadro, mas e' a mesma classe de
        # erro que o projeto ja pagou caro: dois lugares calculando o mesmo
        # instante por caminhos diferentes.
        _r2 = _sp.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                       "-show_entries", "stream=r_frame_rate",
                       "-of", "default=nw=1:nk=1",
                       os.path.join(LOTE.saida, f"{v}_PRONTO.mp4")],
                      capture_output=True, text=True)
        _n, _d = (int(x) for x in _r2.stdout.strip().split("/"))
        _fps = _n / _d
        corte = round(float(corte) * _fps) / _fps
        # A legenda que esta na tela NO INSTANTE do corte tem de ser PARTIDA
        # em duas. Ela aparece antes da vinheta, some durante, e volta depois
        # -- deslocar o bloco inteiro declara legenda em cima da vinheta, onde
        # nao ha nenhuma, e deixa de cobrir o trecho em que ela volta.
        # Medido em 15/08/2026: acontecia em 5 das 6 pecas, de 167 ms (v2) a
        # 1100 ms (v5). O `.srt` espelha A TELA -- essa e' a regra, e um bloco
        # atravessando a vinheta nao espelha nada.
        movidos = partidos = 0
        novo = []
        for a, b, t in cues:
            if a < corte < b:
                novo.append((a, corte, t))
                novo.append((corte + dur_vin, b + dur_vin, t))
                partidos += 1
            elif a >= corte:
                novo.append((a + dur_vin, b + dur_vin, t))
                movidos += 1
            else:
                novo.append((a, b, t))
        cues = novo
        print(f"Video {v}: vinheta de {dur_vin:.3f}s em {corte:.3f}s -> "
              f"{movidos} deslocadas, {partidos} partida(s) no corte")

    linhas = []
    for i, (a, b, txt) in enumerate(cues, 1):
        linhas.append(f"{i}\n{ts(a)} --> {ts(b)}\n{txt}\n")
    _n = LOTE.nomes.get(str(v))   # ver `nomes` no config.py
    if not _n:
        # Sem `nomes` o antigo fallback `Vídeo N` publicava no Drive um par
        # que o analista não consegue ligar ao vídeo (08/09/2026: 18 arquivos
        # `Vídeo 1..9` gravados na pasta do cliente). O nome entregue é
        # `V<n> - <o que fala> - <Dr. Fulano>` e mora no lote.json.
        sys.exit(f"Video {v}: falta `nomes[\"{v}\"]` no lote.json — o .srt/.txt "
                 "tem de sair com o nome do vídeo entregue, nunca `Vídeo N`.")
    corpo = do_txt(srt, corr)
    novos = {f"{_n}.srt": "\n".join(linhas), f"{_n}.txt": corpo}
    # NUNCA sobrescrever uma legenda publicada com conteudo DIFERENTE sem
    # guardar a antiga. A regra do COMECAR-UM-LOTE.md ("versao superada vai
    # para V<n>/ COM a Legendas dela") ja foi furada duas vezes por rodar
    # este script antes de copiar a versao anterior: Fulano 11/09/2026 (a
    # `V1 - Montserrat` ficou sem legendas) e Dra. Fulana 21/09/2026 (o par
    # da 1a versao publicada se perdeu, e o .ass de origem ja tinha sido
    # regenerado). A antiga vai para `Legendas/_substituidas-<data-hora>/`;
    # quem preserva a versao move de la para a `V<n>/Legendas`.
    # Caminho > 260 chars morre com WinError 3, identico a "pasta nao existe"
    # (lote 68, 28/09/2026: `Legendas\_substituidas-...\V25 - <nome de 75
    # chars>.srt` deu 268 e abortou o lote no meio). Mesmo prefixo estendido
    # do `_longo()` do aprovar_video.py.
    def _longo(p):
        p = os.path.abspath(p)
        if os.name == "nt" and len(p) > 240 and not p.startswith("\\\\?\\"):
            return "\\\\?\\" + p
        return p

    for nome, conteudo in novos.items():
        alvo = _longo(os.path.join(DEST, nome))
        if os.path.exists(alvo):
            with open(alvo, encoding="utf-8-sig") as f:
                antigo = f.read()
            if antigo != conteudo:
                guarda = os.path.join(DEST, "_substituidas-" + _CARIMBO)
                os.makedirs(guarda, exist_ok=True)
                os.replace(alvo, _longo(os.path.join(guarda, nome)))
                print(f"      {nome}: versao anterior guardada em "
                      f"{os.path.basename(guarda)}/")
        with open(alvo, "w", encoding="utf-8-sig") as f:
            f.write(conteudo)
    print(f"Video {v}: {len(cues):3d} legendas, {cues[-1][1]:5.2f}s | "
          f"txt {len(corpo.split()):3d} palavras, "
          f"{len(corpo.strip().splitlines())} frases")
print(f"\n-> {DEST}")
