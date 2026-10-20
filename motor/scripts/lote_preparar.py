#!/usr/bin/env python3
"""Fase 1 do lote: para cada video, monta o AUDIO do corte e transcreve.

Usa audio-only: a linha do tempo e identica a do video final e evita
encodar 8 videos so para transcrever. Chama o ffmpeg por subprocess com
lista de argumentos -- sem shell no meio, que e o que vinha mutilando
caminho do Windows.
"""
import json, os, re, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config                                            # noqa: E402
import completude                                        # noqa: E402
import pontuacao
import retimar_legenda                                         # noqa: E402

# O detector de tomada refeita vive em scripts/analise/. Ele e' importado
# AQUI, e nao deixado como comando avulso, porque comando avulso foi
# exatamente o modo de falha: 5 alarmes seguidos perdidos, 2 deles porque o
# script nem chegou a ser executado. Ver o docstring de `repeticao.portao`.
sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "analise"))
import repeticao                                         # noqa: E402

LOTE = config.carregar()
PAD = 0.18               # ver comentario em lote_produzir.py
# pausa minima por video: dado do lote, ver config.py
# limiar de silencio: dado do lote, ver config.py
# limiar por video: forcado pelo lote.json ou medido no bruto

# As faixas vem do lote.json (`faixas`), decididas LENDO a transcricao do
# bruto que a fase 0 gerou. Nao existe faixa "automatica": e aqui que se
# remove tomada refeita, direcao de camera e voz de terceiro, e nenhum desses
# tres aparece no volume.
FAIXAS = LOTE.faixas
if not FAIXAS:
    sys.exit("O lote.json nao tem `faixas`. Rode antes:\n"
             "  python scripts/transcrever_brutos.py\n"
             "leia os .srt em trabalho/ e preencha `faixas`.")


def rodar(args, **kw):
    return subprocess.run(args, capture_output=True, text=True, **kw)


def segmentos(src, faixas, nivel, minp, vetados=(), cauda=False):
    dur = float(rodar(["ffprobe", "-v", "error", "-show_entries",
                       "format=duration", "-of", "csv=p=0", src]).stdout.strip())
    err = rodar(["ffmpeg", "-hide_banner", "-i", src, "-vn", "-af",
                 f"silencedetect=noise={nivel}dB:d={minp}", "-f", "null", "-"]).stderr
    sil, ini = [], None
    for m in re.finditer(r"silence_(start|end): (-?[\d.]+)", err):
        if m.group(1) == "start":
            ini = float(m.group(2))
        elif ini is not None:
            sil.append((ini, float(m.group(2)))); ini = None
    if ini is not None:
        sil.append((ini, dur))

    fala, cur = [], 0.0
    for a, b in sil:
        if a > cur:
            fala.append((cur, a))
        cur = b
    if cur < dur:
        fala.append((cur, dur))

    # Ruido de fundo alto cega o `silencedetect` (ele mede PICO, nao energia):
    # se ele achou corte de menos, a fala vem medida por energia de janela.
    # Motivo completo em `config.fala_por_energia`. A MESMA chamada existe em
    # `lote_produzir.segmentos` — as duas copias tem de calcular o mesmo corte,
    # ou a guarda de timeline aborta o render (e ela ja esteve certa duas vezes).
    # A decisao olha os trechos EFETIVOS (`montar`), nunca os blocos crus.
    # As fronteiras caem NA GRADE DE QUADROS do bruto.
    #
    # Por que: o `trim` de video da fase 2 so pode cortar em quadro, e anda o
    # limite ate um; o `atrim` de audio corta no instante exato. Fronteira
    # fora da grade faz video e audio do trecho terem duracoes diferentes, e o
    # erro SOMA trecho a trecho -- a legenda, que e cronometrada nesta linha do
    # tempo, descola da fala que esta no render.
    #
    # Medido neste lote (Dra. Fulana, 10/08/2026), com o bruto a
    # 24000/1001 fps: as 22 fronteiras do v5 tinham resto de -19 a +19 ms
    # (a faixa de meio quadro), e a deriva medida por correlacao subia de
    # 0 ms a +90 ms ao longo do video -- ~9 ms por corte, contra os 10,4 ms
    # de erro medio de meio quadro. Em 7 dos 10 videos passava de 40 ms.
    #
    # Nao aparecera antes porque nenhum lote anterior era 23,976 fps: o quadro
    # aqui dura 41,7 ms, contra 33,4 ms a 30 fps e 16,7 ms a 59,94.
    #
    # O ajuste e de no maximo meio quadro (<=21 ms), abaixo do PAD de 180 ms,
    # entao nao muda o que entra no corte -- so faz o corte cair onde o video
    # consegue cortar.
    fps = config.fps_de(src)

    def montar(blocos, mingap=config.MIN_GAP):
        # A regra inteira vive em `config.trechos_das_faixas`, e nao aqui, para
        # nao haver duas copias: esta funcao era identica a de `lote_produzir`
        # e as duas tinham o bug de fusao ENTRE faixas (12/08/2026).
        # `vetados` vem por PARAMETRO, nunca de global: `segmentos` e' funcao
        # e o `v` do laco so' existe no modulo. Funcionaria por acidente aqui
        # e quebraria na primeira vez que alguem chamasse de outro lugar.
        return config.trechos_das_faixas(blocos, faixas, dur, fps, PAD,
                                         mingap, vetados=vetados, cauda=cauda)

    # Ruido de fundo alto cega o `silencedetect` (ele mede PICO, nao energia):
    # se ele achou corte de menos, a fala vem medida por energia de janela.
    # Motivo completo em `config.fala_por_energia`. A MESMA chamada existe em
    # `lote_produzir.segmentos` — as duas copias tem de calcular o mesmo corte,
    # ou a guarda de timeline aborta o render (e ela ja esteve certa duas vezes).
    fala, por_energia = config.fala_ou_energia(
        src, dur, fala, faixas, minp, montar=montar,
        fw=os.path.join(LOTE.trabalho,
                        os.path.splitext(os.path.basename(src))[0] + "_fw.json"),
        minp_energia=LOTE.pausa_energia_de(
            os.path.splitext(os.path.basename(src))[0]))
    if por_energia:
        print(f"      corte por ENERGIA: o silencedetect a {nivel} dB achou "
              f"pausa de menos neste bruto")
    # o corte por energia tem piso de vao proprio (motivo em config)
    return montar(fala, config.MIN_GAP_ENERGIA if por_energia else config.MIN_GAP)


def ajustar_inicio_palavra(v, regras):
    """Move o INICIO de um token no `_palavras.json` (ver `inicio_palavra`
    no config). Aplicado depois do retimer e antes de qualquer consumidor,
    porque este arquivo e' a unica fonte de tempo de todos eles. Aborta se a
    palavra nao casar ou se o novo inicio invadir o token anterior -- regra
    que nao casa e' invisivel, e e' assim que a correcao some em silencio."""
    import re
    pal = os.path.join(LOTE.trabalho, f"{v}_palavras.json")
    toks = [json.loads(l) for l in open(pal, encoding="utf-8") if l.strip()]
    def base(s):
        return re.sub(r"[^\w]", "", s, flags=re.U).lower()
    for r in regras:
        alvo, ini = base(r["texto"]), int(round(float(r["inicio"]) * 1000))
        n = int(r.get("ocorrencia", 1))
        idx = [i for i, t in enumerate(toks) if base(t["text"]) == alvo]
        if len(idx) < n:
            sys.exit(f"inicio_palavra v{v}: '{r['texto']}' casou {len(idx)}x, "
                     f"pedida a ocorrencia {n}")
        i = idx[n - 1]
        if i and toks[i - 1]["end"] > ini:
            sys.exit(f"inicio_palavra v{v}: {ini} ms invade o token anterior "
                     f"'{toks[i-1]['text']}' (fim {toks[i-1]['end']} ms)")
        if ini >= toks[i]["end"]:
            sys.exit(f"inicio_palavra v{v}: {ini} ms nao e' antes do fim do "
                     f"token ({toks[i]['end']} ms)")
        print(f"  v{v}: inicio de '{toks[i]['text']}' {toks[i]['start']} -> {ini} ms "
              f"(`inicio_palavra`)")
        toks[i]["start"] = ini
    with open(pal, "w", encoding="utf-8") as f:
        for t in toks:
            f.write(json.dumps(t, ensure_ascii=False) + "\n")


resumo = {}
# Cada video do lote tem de sair desta fase como CONFERIDO ou como PULADO
# com motivo. Ver scripts/completude.py para o porque.
COB = completude.Cobertura("fase 1", list(FAIXAS))
LOTE.preparar_pastas()
for v, faixas in FAIXAS.items():
    src = LOTE.bruto_de(v)
    segs = segmentos(src, faixas, LOTE.nivel_de(v), LOTE.pausa_de(v),
                     LOTE.cortes_vetados_de(v), LOTE.cauda_de(v))
    config.exigir_audio_no_inicio(v, src, segs)
    total = sum(b - a for a, b in segs)
    cortes = [0.0]
    for a, b in segs:
        cortes.append(round(cortes[-1] + (b - a), 3))

    # audio do corte
    partes = [f"[0:a]atrim={a:.3f}:{b:.3f},asetpts=PTS-STARTPTS[a{i}]"
              for i, (a, b) in enumerate(segs)]
    partes.append("".join(f"[a{i}]" for i in range(len(segs))) +
                  f"concat=n={len(segs)}:v=0:a=1[a]")
    wav = os.path.join(LOTE.trabalho, f"{v}_corte.wav")
    r = rodar(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", src,
               "-filter_complex", ";".join(partes), "-map", "[a]",
               "-ar", "48000", "-y", wav])
    if r.returncode:
        print(f"v{v} FALHOU no audio: {r.stderr[:200]}"); continue

    # ARMADILHA CARA (lote da Dra. Fulana, 31/07/2026): o cache abaixo
    # so' olhava se o arquivo EXISTIA. Quando eu mudei `nivel_silencio` de
    # tres videos no lote.json e rodei a fase 1 de novo, o `_corte.wav` foi
    # regravado com um corte DIFERENTE e a transcricao velha ficou intacta --
    # entao o render casou video novo com legenda de uma timeline que nao
    # existia mais. O operador viu legenda 1 a 2,6 SEGUNDOS atrasada em tres
    # videos, e nada no pipeline reclamou.
    #
    # A assinatura do estrago e' util: o desvio e' CONSTANTE dentro do bloco
    # e SALTA no corte (o degrau e' a pausa que o corte novo removeu e o
    # velho nao). Deriva que acumula dentro do bloco seria outra coisa.
    #
    # A guarda e' a propria lista de segmentos, nao o mtime: rodar a fase 1
    # duas vezes no mesmo segundo derrota mtime, e comparar o corte e' o que
    # realmente importa.
    assinatura = json.dumps([[round(a, 3), round(b, 3)] for a, b in segs])
    marca = os.path.join(LOTE.trabalho, f"{v}_corte.json")
    velha = None
    if os.path.exists(marca):
        velha = open(marca, encoding="utf-8").read()
    if velha is not None and velha != assinatura:
        for saida in (f"{v}_corte.srt", f"{v}_palavras.json",
                      f"{v}_palavras_bruto.json"):
            p = os.path.join(LOTE.trabalho, saida)
            if os.path.exists(p):
                os.remove(p)
        print(f"  v{v}: o corte mudou -> transcricao anterior descartada")
    with open(marca, "w", encoding="utf-8") as f:
        f.write(assinatura)

    # PALAVRAS: faster-whisper (`fw.py`), NAO o filtro `whisper` do ffmpeg.
    #
    # Trocado em 14/08/2026, depois de medir a peca entregue. O filtro do
    # ffmpeg com `:max_len=1` devolve TOKEN, nao palavra -- a assinatura fica
    # no arquivo: "segur"+"ar", "col"+"o", "miss"+"ao", "imposs"+"ivel", e
    # entradas de duracao ZERO. Esses tempos viravam o relogio da legenda.
    #
    # MEDIDO no v5 deste lote, contra o inicio de fala por energia:
    #   filtro do ffmpeg -> mediana -640 ms, pior caso -1010 ms
    #   fw.py            -> mediana -250 ms, sem picos
    # O sinal e' NEGATIVO: a legenda acendia ANTES da fala. O erro tem forma
    # de arco (zero nas pontas, maximo no meio da frase), que e' a assinatura
    # de um relogio continuo aplicado a uma fala que respira -- o
    # `retimar_legenda.py` so' conserta fronteira que cai em pausa DETECTADA,
    # e a pausa de 470 ms dentro da frase nao era vista.
    #
    # O `.srt` de FRASE continua vindo do filtro do ffmpeg: medido, o relogio
    # de frase esta certo (7,080 contra 7,070 da energia). Quem errava era so'
    # o de token.
    #
    # Isto e' a regra §4b do CLAUDE.md aplicada onde ela ainda nao estava: ela
    # ja proibia decidir CORTE pelo relogio do filtro desde o lote 5, e a
    # legenda continuou nele por dois meses.
    fw_json = os.path.join(LOTE.trabalho, f"{v}_fw.json")
    pal_json = os.path.join(LOTE.trabalho, f"{v}_palavras.json")
    if not os.path.exists(pal_json):
        # O `retimar_legenda.py` guarda a versao crua em
        # `{v}_palavras_bruto.json` e, se ela existir, e' DELA que ele parte.
        # Apagar so' o `_palavras.json` nao basta: o bruto velho sobrevive e
        # sobrescreve o arquivo novo com os tokens antigos, com exit 0 e o
        # nome de arquivo certo. Aconteceu aqui em 14/08/2026, na propria
        # troca de rota -- o log dizia "110 palavras (faster-whisper)" e o
        # arquivo final tinha os 156 tokens do filtro.
        velho_bruto = os.path.join(LOTE.trabalho, f"{v}_palavras_bruto.json")
        if os.path.exists(velho_bruto):
            os.remove(velho_bruto)
            print(f"  v{v}: bruto de palavras anterior descartado "
                  f"(a rota de transcricao mudou)")
        import fw as FW
        dados = FW.transcrever(wav, fw_json, idioma=LOTE.idioma_de(v))
        n = 0
        with open(pal_json, "w", encoding="utf-8") as f:
            for s in dados["segmentos"]:
                for p in s["palavras"]:
                    # o consumidor (gerar_ass, retimar_legenda) le JSONL com
                    # start/end em MILISSEGUNDOS e a chave `text`
                    f.write(json.dumps(
                        {"start": int(round(p["ini"] * 1000)),
                         "end": int(round(p["fim"] * 1000)),
                         "text": p["txt"]}, ensure_ascii=False) + "\n")
                    n += 1
        print(f"  v{v}: {n} palavras (faster-whisper, fronteira de PALAVRA)")

        # O `.srt` de FRASE sai da MESMA transcricao, e nao do filtro do
        # ffmpeg. Deixar meio a meio quebra: o `retimar_legenda.py` casa
        # palavra a palavra o arquivo de palavras contra o `.srt`, e com os
        # dois vindo de modelos diferentes o texto diverge e o alinhador
        # aborta ("alinhamento falhou em 'ladinho'"). Enquanto os dois saiam
        # do mesmo filtro isso nunca aparecia.
        srt_alvo = os.path.join(LOTE.trabalho, f"{v}_corte.srt")
        if os.path.exists(srt_alvo):
            os.remove(srt_alvo)

        def _ts(seg):
            h, r = divmod(max(0.0, seg), 3600)
            m, s = divmod(r, 60)
            return f"{int(h):02d}:{int(m):02d}:{s:06.3f}".replace(".", ",")

        with open(srt_alvo, "w", encoding="utf-8") as f:
            for i, s in enumerate(dados["segmentos"], 1):
                f.write(f"{i}\n{_ts(s['ini'])} --> {_ts(s['fim'])}\n"
                        f"{s['texto']}\n\n")
        print(f"  v{v}: {len(dados['segmentos'])} frases -> {v}_corte.srt "
              f"(mesma transcricao das palavras)")

    # (o filtro `whisper` do ffmpeg saiu daqui em 14/08/2026 -- ver acima)
    for saida, extra in ():
        alvo = os.path.join(LOTE.trabalho, saida)
        if os.path.exists(alvo):
            continue
        # idioma explicito: sem ele o whisper autodetecta, e autodeteccao
        # varia com o trecho — num corte curto ele ja voltou para o idioma
        # errado. O lote do Dr. Fulano e misto (1 e 2 em ingles, 3 em pt).
        ok, err = config.transcrever(wav, alvo, extra,
                                     idioma=LOTE.idioma_de(v))
        if not ok:
            print(f"  v{v}: transcricao de {saida} FALHOU -> {err}")
            continue

        # ARMADILHA (v1 e v3, 31/07): com certos audios o whisper devolve o
        # texto INTEIRO sem pontuacao e em minusculas. E deterministico --
        # repetir a chamada da o mesmo resultado -- e nada falha: o arquivo
        # existe e as palavras estao certas. O que quebra e tudo que depende
        # de FRASE (P&B, posicao de leak, frase em destaque), porque o
        # divisor procura `.?!`.
        # Baixar o `queue` as vezes traz a pontuacao, mas num teste com 7
        # valores as versoes pontuadas PERDIAM PALAVRA -- inaceitavel numa
        # peca de medico. A pontuacao vem do SRT do bruto, que a tem.
        bruto_srt = os.path.join(LOTE.trabalho, f"{v}.srt")
        if saida.endswith(".srt") and os.path.exists(bruto_srt):
            t = open(alvo, encoding="utf-8").read()
            if pontuacao.precisa(t):
                bruto = open(bruto_srt, encoding="utf-8").read()
                novo_txt, n = pontuacao.restaurar(bruto, t)
                antes = [pontuacao._norm(p) for p in pontuacao._tokens(t)]
                depois = [pontuacao._norm(p) for p in pontuacao._tokens(novo_txt)]
                if antes == depois:
                    open(alvo, "w", encoding="utf-8").write(novo_txt)
                    print(f"  v{v}: pontuacao ausente -> {n} sinais "
                          f"restaurados do bruto, {len(antes)} palavras intactas")
                else:
                    print(f"  v{v}: ALERTA -- restauracao mudaria palavra, "
                          f"mantida a transcricao sem pontuacao")

    # Ancora o tempo de cada palavra no AUDIO. Tem de rodar AQUI, na fase 1,
    # e sobre os TOKENS -- nao dentro do gerador de legenda: assim a frase em
    # destaque, o punch, o P&B e as legendas exportadas usam todos os mesmos
    # tempos. Consertar so' na legenda deixaria o texto grande no tempo velho.
    # Ver scripts/retimar_legenda.py para o porque (tokens contiguos).
    ok = all(os.path.exists(os.path.join(LOTE.trabalho, n))
             for n in (f"{v}_corte.srt", f"{v}_palavras.json"))
    if ok:
        try:
            retimar_legenda.retimar_arquivo(LOTE.trabalho, v)
        except SystemExit as e:
            print(f"  v{v}: RETIMER abortou -> {e}")
            ok = False
    if ok and LOTE.inicio_palavra.get(str(v)):
        ajustar_inicio_palavra(v, LOTE.inicio_palavra[str(v)])
    resumo[v] = {"segs": len(segs), "dur": round(total, 2), "cortes": cortes, "ok": ok}
    print(f"v{v}: {len(segs)} trechos, {total:.2f}s, transcricao {'OK' if ok else 'FALHOU'}")
    if ok:
        COB.conferido(v, f"corte ({len(segs)} trechos) + transcricao + retimer")
    else:
        COB.pulado(v, "transcricao/retimer falhou - sem palavras.json confiavel")

json.dump(resumo, open(os.path.join(LOTE.trabalho, "resumo.json"), "w"), indent=1)

# Contrato de completude ANTES do portao: se algum video do lote nao saiu
# desta fase nem como conferido nem como pulado-com-motivo, a fase mentiu.
COB.fechar(LOTE, "preparacao")

# PORTAO DE TOMADA REFEITA -- roda aqui dentro, e ABORTA.
#
# Ate' 13/08/2026 isto era um comando separado que imprimia e saia com exit 0.
# Falhou cinco vezes seguidas (Fulano 10/08, Fulano 11/08, Fulano 12/08,
# Fulano 12/08, Fulano 13/08) e na quinta quatro pecas com tomada repetida
# foram publicadas para a cliente. Nas duas do meio ele nem foi executado.
#
# O diagnostico do vault: a causa raiz nao era ignorar o alarme, era o
# detector nao estar no caminho do trabalho. Lembrar tem taxa de acerto zero
# sob pressao. Entao ele deixa de depender de lembranca.
#
# Liberar suspeita e' escrever `repeticoes_aceitas` no lote.json, com motivo.
repeticao.portao(list(FAIXAS))

print("\nFASE 1 CONCLUIDA")
