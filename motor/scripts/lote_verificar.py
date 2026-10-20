#!/usr/bin/env python3
"""Fase 3: confere os renders e publica no Drive.

Verificacao numerica, nao visual -- em lote, olhar quadro a quadro custa
mais que todo o resto (ver docs/02-pipeline.md).
"""
import math, os, re, shutil, subprocess, sys, time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import completude                                        # noqa: E402
import config                                            # noqa: E402
import relatorio                                         # noqa: E402

# Este script ficou pela metade na migracao para o config: usava `LOTE.saida`
# sem nunca importar config, e mantinha a pasta de trabalho, a pasta do Drive
# e a lista de videos da Dra. Fulana fixas aqui. Rodava so' naquele lote.
LOTE = config.carregar()
DRIVE = LOTE.entrega
PUBLICAR = "--publicar" in sys.argv
# videos pedidos na linha de comando, ou todos os do lote
VIDEOS = [a for a in sys.argv[1:] if a.isdigit()] or LOTE.videos


def prova(args):
    return subprocess.run(args, capture_output=True, text=True).stdout.strip()


def _mono16k(arquivo):
    """Decodifica para mono 16 kHz em memoria, como float."""
    import numpy as np
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", arquivo, "-ac", "1",
                        "-ar", "16000", "-f", "s16le", "-"],
                       capture_output=True)
    return np.frombuffer(r.stdout, dtype="<i2").astype("f8") / 32768.0


def musica(arquivo, faixa):
    """Quanto da faixa de musica esta' de fato dentro do render, em dB.

    O verificador media dimensao, sync, nivel e pico -- e dava OK num
    render com a musica 30 dB baixa demais, porque nenhuma dessas quatro
    medidas enxerga a musica: ela e' 25-30 dB mais baixa que a fala e nao
    move a media nem o pico. Foi assim que o lote da Dra. Fulana saiu
    inteiro com musica inaudivel e so' o ouvido dele pegou (04/08/2026).

    O teste e' correlacao cruzada com a faixa remixada, que e' o sinal
    exato que entrou na mixagem. Devolve (ganho_db, relativo_db):
    ganho ~ 0 dB significa "esta' la', no nivel esperado"; -inf significa
    ausente. `relativo` e' a distancia da musica para a media do render --
    o numero que descreve o EQUILIBRIO, e o unico que ele escuta.

    O lag e' procurado, nao assumido: o AAC tem priming delay (medido em
    +5 ms aqui) e correlacao em lag 0 devolve ~zero mesmo com a musica
    presente -- foi o primeiro resultado que eu quase reportei como
    "musica ausente".
    """
    import numpy as np
    r, m = _mono16k(arquivo), _mono16k(faixa)
    n = min(len(r), len(m))
    if n < 16000:
        return None, None
    r, m = r[:n], m[:n]
    maxlag = 1600                                    # +-100 ms
    cc = np.fft.irfft(np.fft.rfft(r, 2 * n) * np.conj(np.fft.rfft(m, 2 * n)),
                      2 * n)
    idx = list(range(maxlag)) + list(range(2 * n - maxlag, 2 * n))
    alfa = max(cc[i] for i in idx) / ((m ** 2).sum() + 1e-12)
    db = lambda x: 20 * math.log10(math.sqrt((x ** 2).mean()) + 1e-12)
    return 20 * math.log10(abs(alfa) + 1e-12), db(m) - db(r)


print(f"{'vid':>4} {'dim':>10} {'video':>7} {'audio':>7} {'sync':>6} "
      f"{'nivel':>7} {'pico':>6} {'mus':>6} {'m/fala':>7} {'L-R':>5}  situacao")
ok_todos = True
PECAS = []            # o mesmo que a tabela mostra, em formato que se lê
# quando o lote sai em duas versoes, AS DUAS sao verificadas: publicar uma
# peca que ninguem mediu e' o mesmo que nao verificar.
ALVOS = [(v, "") for v in VIDEOS]
if LOTE.duas_versoes:
    ALVOS = [par for v in VIDEOS
             for par in ((v, ""), (v, "_LEGENDA-MEDICO"))]
# a versao sem b-roll e' peca publicada igual as outras -- entra na conta
# quando existir, senao ela vai para o Drive sem nunca ter sido medida.
ALVOS += [(v, s + "_SEM-BROLL") for v, s in list(ALVOS)
          if os.path.exists(os.path.join(LOTE.saida,
                                         f"{v}_PRONTO{s}_SEM-BROLL.mp4"))]
# Cada peca do lote tem de sair desta fase como MEDIDA ou como pulada com
# motivo. Ver scripts/completude.py -- silencio e' indistinguivel de "passou".
COB = completude.Cobertura(
    "fase 3", [f"{v}{suf}" for v, suf in ALVOS])
for v, suf in ALVOS:
    f = os.path.join(LOTE.saida, f"{v}_PRONTO{suf}.mp4")
    rotulo = f"{v}{'m' if 'MEDICO' in suf else ''}{'b' if 'SEM-BROLL' in suf else ''}"
    if not os.path.exists(f):
        print(f"{rotulo:>4}  FALTANDO"); ok_todos = False
        PECAS.append({"rotulo": rotulo, "video": v, "arquivo": os.path.basename(f),
                      "existe": False, "falhas": ["faltando"]})
        COB.pulado(f"{v}{suf}", "arquivo nao existe em saida/ - nada a medir")
        continue
    dim = prova(["ffprobe", "-v", "error", "-select_streams", "v:0",
                 "-show_entries", "stream=width,height", "-of", "csv=p=0", f])
    # `csv=p=0` as vezes devolve o valor com virgula sobrando ("57.633333,")
    # -- o mesmo defeito que o `dim.strip(",")` logo abaixo ja' contornava.
    # Sem isto o float() explode e derruba o lote INTEIRO no meio da tabela:
    # aconteceu no v3 da Dra. Fulana (31/07/2026), depois de v1 e v2
    # terem passado normalmente.
    def dur(fluxo):
        t = prova(["ffprobe", "-v", "error", "-select_streams", fluxo,
                   "-show_entries", "stream=duration", "-of", "csv=p=0", f])
        return float(next(x for x in t.split(",") if x.strip()))

    vd, ad = dur("v:0"), dur("a:0")
    saida = subprocess.run(["ffmpeg", "-hide_banner", "-i", f, "-af",
                            "volumedetect", "-f", "null", "-"],
                           capture_output=True, text=True).stderr
    med = float(re.search(r"mean_volume: (-?[\d.]+)", saida).group(1))
    pico = float(re.search(r"max_volume: (-?[\d.]+)", saida).group(1))
    sync = abs(vd - ad) * 1000

    # BALANCO ENTRE CANAIS -- eixo que faltava, e que deixou dez pecas irem ao
    # cliente com a voz so' no ouvido esquerdo (Dra. Fulana,
    # 10/08/2026). As quatro medidas acima SOMAM os canais: sinal so' num lado
    # mede igual a sinal centrado 3 dB mais baixo, entao nenhuma delas podia
    # ver. Quem viu foi o operador, no fone.
    #
    # A causa estava no bruto (camera grava o lapela no canal 1 e deixa o 2
    # com o microfone interno, 32 dB abaixo) e o pipeline repassava. Hoje
    # `config.centrar_de` conserta na origem; este portao existe para o
    # conserto nao depender de eu lembrar.
    est = subprocess.run(["ffmpeg", "-hide_banner", "-i", f, "-vn", "-af",
                          "astats=metadata=1:reset=0", "-f", "null", "-"],
                         capture_output=True, text=True,
                         errors="replace").stderr
    niveis, canal = {}, None
    for linha in (est or "").splitlines():
        m = re.search(r"Channel:\s*(\d+)", linha)
        if m:
            canal = int(m.group(1))
        if "Overall" in linha:
            canal = None
        m = re.search(r"RMS level dB:\s*(-?[\d.]+)", linha)
        if m and canal is not None and canal not in niveis:
            niveis[canal] = float(m.group(1))
    balanco = (abs(niveis[1] - niveis[2])
               if len(niveis) >= 2 and 1 in niveis and 2 in niveis else None)

    faixa = os.path.join(LOTE.trabalho, f"{v}_musica.wav")
    g, rel = musica(f, faixa) if os.path.exists(faixa) else (None, None)

    falhas = []
    if dim.strip(",") != "1080,1920":
        falhas.append("dimensao")
    if sync > 40:
        falhas.append("sync")
    if not -21 <= med <= -15:
        falhas.append("nivel")
    if pico > -0.5:
        falhas.append("clip")
    # ganho ~0 dB = a faixa entrou inteira; longe disso e' musica ausente,
    # dobrada ou no nivel errado. Faixa larga de proposito: o AAC e o
    # limitador mexem no valor, o que interessa e' distinguir de ausente.
    if g is not None and not -4.0 <= g <= 4.0:
        falhas.append("musica")
    # 6 dB: a musica e' estereo de verdade e move o balanco alguns dB; voz
    # presa num canal da 20 dB ou mais. A faixa entre os dois e' larga.
    if balanco is not None and balanco > 6.0:
        falhas.append("canal")
    sit = "OK" if not falhas else "REVER: " + ",".join(falhas)
    if falhas:
        ok_todos = False
    COB.conferido(f"{v}{suf}",
                  "dim,sync,nivel,pico,musica,canal" +
                  (f" -> {','.join(falhas)}" if falhas else " -> ok"))
    PECAS.append({
        "rotulo": rotulo, "video": v, "arquivo": os.path.basename(f),
        "existe": True, "bytes": os.path.getsize(f),
        "dimensao": dim.strip(","),
        "dur_video": round(vd, 2), "dur_audio": round(ad, 2),
        "sync_ms": round(sync), "nivel_db": med, "pico_db": pico,
        "musica_db": round(g, 1) if g is not None else None,
        "musica_rel_db": round(rel, 1) if rel is not None else None,
        "balanco_lr_db": round(balanco, 1) if balanco is not None else None,
        "falhas": falhas,
    })
    print(f"{rotulo:>4} {dim.strip(','):>10} {vd:7.2f} {ad:7.2f} {sync:5.0f}ms "
          f"{med:6.1f} {pico:6.1f} "
          f"{('%+5.1f' % g) if g is not None else '    -'} "
          f"{('%6.1f' % rel) if rel is not None else '     -'} "
          f"{('%5.1f' % balanco) if balanco is not None else '    -'}  {sit}")

if PUBLICAR and ok_todos:
    # Quando o lote sai em duas versoes, as duas vao para o Drive, em
    # subpastas separadas -- o analista precisa comparar lado a lado, e nome
    # com sufixo no meio da lista se perde.
    def nome_de(v):
        """O nome de entrega do video, ou 'Video N' quando o lote nao declarar.

        `Video N` nao e' nome de entrega desde 11/08/2026 -- o nome e' O QUE
        ELE FALA no video. Fica como fallback porque lote cujo bruto ja' chega
        nomeado e numerado pelo cliente NAO se renomeia.
        """
        return LOTE.nomes.get(str(v)) or f"Vídeo {v}"

    # Entrega em subpasta nova (`Finalizados\Lote 2`, lote 68) ainda nao
    # existe na 1a publicacao: sem isto o copy morre com FileNotFoundError.
    os.makedirs(DRIVE, exist_ok=True)
    n = 0
    for v in VIDEOS:
        alvo = DRIVE
        if LOTE.duas_versoes:
            alvo = os.path.join(DRIVE, "Com a nossa legenda")
            os.makedirs(alvo, exist_ok=True)
        shutil.copy(os.path.join(LOTE.saida, f"{v}_PRONTO.mp4"),
                    os.path.join(alvo, f"{nome_de(v)}.mp4"))
        n += 1
        if LOTE.duas_versoes:
            outra = os.path.join(DRIVE, "Com a legenda do médico")
            os.makedirs(outra, exist_ok=True)
            shutil.copy(
                os.path.join(LOTE.saida, f"{v}_PRONTO_LEGENDA-MEDICO.mp4"),
                os.path.join(outra, f"{nome_de(v)}.mp4"))
            n += 1
    print(f"\n{n} videos publicados em Finalizados")
elif PUBLICAR:
    print("\nNAO publicado: ha video com pendencia acima")

# Rodar o verificador em UM video (`lote_verificar.py 3`) e' rotina durante a
# revisao. A primeira versao disto sobrescrevia o relatorio inteiro com essa
# unica peca, e o semaforo passava a dizer que as outras "nao rodaram" -- o
# lote inteiro sumia porque alguem conferiu um video. Aqui a rodada parcial
# MESCLA: substitui so' o que mediu agora e preserva o resto, cada peca com a
# hora em que foi medida, para nao existir medicao velha se passando por nova.
_agora = time.strftime("%Y-%m-%d %H:%M:%S")
for _p in PECAS:
    _p["_medido"] = _agora
_antes = relatorio.ler(LOTE, "verificacao") or {}
_medidas_agora = {p["rotulo"] for p in PECAS}
# So' sobrevive peca que AINDA pertence ao lote. Sem este filtro, um numero
# digitado errado na linha de comando (`lote_verificar.py 77`) entrava no
# relatorio como "faltando" e ficava vermelho para sempre, sem nenhum jeito
# de sair a nao ser apagando o arquivo a mao.
_do_lote = {str(v) for v in LOTE.videos}
_mantidas = [p for p in _antes.get("pecas", [])
             if p.get("rotulo") not in _medidas_agora
             and str(p.get("video")) in _do_lote]
_todas = sorted(PECAS + _mantidas, key=lambda p: (str(p.get("video")), p.get("rotulo", "")))
relatorio.gravar(LOTE, "verificacao",
                 {"pecas": _todas,
                  "ok_todos": all(not p.get("falhas") for p in _todas),
                  "medidos_nesta_rodada": sorted(_medidas_agora),
                  "publicado": bool(PUBLICAR and ok_todos)})

# DEPOIS de gravar, nunca antes: `fechar` aborta quando alguma peca ficou sem
# resposta, e abortar antes do registro perderia a medicao que ja' custou o
# encode. O relatorio e' registro; a cobertura e' portao.
COB.fechar(LOTE, "verificacao")

# O verificador ja' sabia que a peca tinha reprovado -- e saia com codigo 0
# assim mesmo, inclusive sem `--publicar`. Quem chamasse este script de dentro
# de outro (ou lesse `$?`) recebia "passou" com peca defeituosa na pasta. E' o
# mesmo defeito que a regra 1 do CLAUDE.md manda procurar, cometido aqui
# dentro: o portao media certo e reportava errado.
sys.exit(0 if ok_todos else 1)
