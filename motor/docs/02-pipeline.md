# Pipeline técnico

## Ambiente confirmado (30/07/2026)

| | |
|---|---|
| ffmpeg | **8.1.2** full build (gyan.dev) — traz o filtro `whisper` compilado |
| yt-dlp | 2026.07.04 |
| Python | 3.12 com numpy e Pillow |
| GPU | nvenc **indisponível**: o build exige API 13.1, o driver expõe 13.0 → encode em `libx264` |
| Modelo Whisper | `ggml-large-v3-turbo` (1,62 GB) em `D:\Modelos\whisper\` |

Encode padrão: `libx264 -preset medium -crf 19 -profile:v high
-pix_fmt yuv420p`, áudio `aac 192k 48kHz`, `-movflags +faststart`.

---

## Fluxo completo, em ordem

```
1. sondar        ffprobe: duração, codec, ROTAÇÃO
2. detectar      silencedetect (só áudio, -vn)
3. cortar        01-cortar.py  → base para transcrever
4. transcrever   whisper (frase) + whisper max_len=1 (token)
5. legendar      02-legenda.py → .ass estilo TikTok
6. texto grande  03-texto-grande.py → substitui a legenda na janela
7. produzir      05-produzir.py → corte + zoom + efeitos + arte + som
8. verificar     medir sync, dimensão, cor, brilho, sobreposição
```

---

## Ordem do grafo de filtros — o que não pode trocar de lugar

Isto não é preferência; cada item foi descoberto errando.

```
concat dos trechos (4K)
  ↓
scale 1404×2496            ← pré-escala: 1,30× do final, teto de zoom sem upscale
  ↓
perspective (zoom/pan)     ← eval=frame, sub-pixel; NÃO zoompan
  ↓
scale 1080×1920
  ↓
eq (saturação → P&B)
  ↓
gblur (texto)  +  gblur horizontal (whip)
  ↓
format=yuva420p → overlay TARJA     ← por baixo do leak
  ↓
format=gbrp → blend screen (LEAKS) → format=yuv420p
  ↓
subtitles (legenda + texto grande)  ← blur do texto vem ANTES; texto fica nítido
  ↓
perspective (STRETCH horizontal)    ← DEPOIS da legenda; texto estica junto
  ↓
gblur horizontal em 3 níveis
  ↓
eq brightness (estouro do stretch)
  ↓
rgbashift (ABERRAÇÃO)               ← DEPOIS do stretch, senão é apagada
  ↓
tpad preto → overlay FINALIZAÇÃO
```

**As três inversões que quebram tudo:**

1. Blur do texto **antes** da legenda → senão o texto sai borrado
2. Stretch **depois** da legenda → senão o texto não estica junto
3. Aberração **depois** do stretch → senão o esticamento a apaga

---

## Rotação: a pegadinha do iPhone

Os brutos vêm 3840×2160 com `rotation=-90` na metadata → exibem como
2160×3840. Quem lê a metadata crua conclui "é 16:9" e exporta deitado.

`ffprobe -show_entries stream_side_data=rotation` para conferir.
O ffmpeg 8 aplica a rotação automaticamente, inclusive em
`filter_complex` — mas **sempre confirmar olhando um quadro**.

---

## Vantagem do 4K: zoom sem perda

Bruto 2160×3840 → entrega 1080×1920 = **2× de margem**. Zoom até 200%
ainda é *downscale*. A pré-escala para 1404×2496 (1,30×) mantém isso e
deixa o `perspective` barato.

Teto seguro: zoom 120% + punch 5% = 125% < 130%.

---

## Corte de silêncio

Parâmetros do template: `PAD=0.10`, `MINP=0.12`. *(O código vigente usa `PAD=0.18` — `lote_preparar.py`, `lote_produzir.py`, `conferir_bordas.py`; o 0.10 é o valor medido no vídeo 7.)*

O `MINP` mais baixo não é estético — é para ter **âncoras de corte**
suficientes, já que toda transição precisa cair em corte.

Sempre estender a cauda (`TAIL_EXTRA=0.45`), senão o corte come a última
palavra.

---

## Transcrição

Duas passadas no mesmo áudio:

| Passada | Para quê |
|---|---|
| `queue=35` | frases inteiras, com grafia correta |
| `queue=35:max_len=1` | tokens com tempo (subpalavra) |

Os tokens vêm **sem espaço** e em subpalavra ("perde"+"u"). O alinhamento
remonta as palavras casando o fluxo de tokens contra o texto da primeira
passada.

**Correções de revisão entram DEPOIS do alinhamento** — se você alinhar
contra o texto já corrigido, dessincroniza tudo (aconteceu com
"mandar" → "mandaram").

**`queue` pequeno gera artefato de fronteira.** Com `queue=10` a palavra
"hormonal" foi cortada entre blocos e virou "hormônica" + "hormonal".
Para clipes curtos, transcrever em bloco único.

---

## Detecção de retake por texto

O maior ganho da transcrição não é a legenda — é achar tomada repetida.

No vídeo 7 original: a médica errou, alguém pediu para refazer, e ela
refez o trecho final. O dB não vê isso (as duas tomadas têm o mesmo
perfil de volume). O texto vê na primeira leitura:

- Tomada 1: *"por ano sem identificação"*
- Tomada 2: *"por anos se identificarem"*
- No meio: *"Fica aí só um pouquinho. Vamos fazer isso aqui de novo"*

Regra: trechos com >70% de similaridade separados por pausa longa =
mesma fala em duas tomadas. **Fica a última.**

Resultado: 69,74s → 28,80s, e o operador confirmou que o conteúdo tinha
mesmo ~28s.

---

## Verificações obrigatórias antes de entregar

| O quê | Como | Alvo |
|---|---|---|
| Sync | `ffprobe` duração de vídeo × áudio | < 30 ms |
| Dimensão | `ffprobe` | 1080×1920 |
| Nível | `volumedetect` | ~−18 dB médio, pico < −1 |
| Cor neutra | comparar RGB médio com o corte limpo | sem canal isolado subindo |
| Legenda | contar sobreposições no `.ass` | 0 |
| Efeitos em corte | o próprio script imprime | `FORA de corte: nenhum` |
| Enquadramento | olhar 1 quadro | vertical, sujeito com folga |

---

## Custo

Rodar os scripts custa **US$ 0,00** de Claude — é ffmpeg e Python local.
O custo é o meu envolvimento, e ele é dominado por **cache read**
(98,2% dos tokens numa medição): o preço escala com tamanho do contexto
× número de turnos. O que engorda o contexto são **as imagens que eu
olho**.

Consequência prática: conferir 40 vídeos quadro a quadro custa mais que
todo o resto somado. Preferir verificação **numérica** e reservar a
visual para o template e para amostras.
