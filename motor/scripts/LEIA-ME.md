# Scripts

Os scripts rodam **da raiz do projeto** e leem o lote do `lote.json`:

```bash
python scripts/lote_produzir.py --lote "2026-08 - Dr. Fulano" 3 5
```

Sem `--lote`, usa a variável de ambiente `LOTE`; sem ela, usa o único lote
existente; se houver mais de um, lista e para.

> Até 31/07/2026 os arquivos daqui eram numerados (`07-lote-produzir.py`) e
> os caminhos do lote de julho estavam fixos no topo de cada um — rodar um
> lote novo exigia editar código. A numeração foi removida porque os scripts
> se importam pelo nome (`import musica`, `import pontuacao`), e os dados do
> lote saíram do código para o `lote.json`.

## Fluxo

| # | Script | O que faz |
|---|---|---|
| −1 | `conferir_lote.py` | falta algo para rodar? brutos, arte com alpha, modelo, leak, músicas |
| 0 | `transcrever_brutos.py` | transcreve os brutos **para você ler** e decidir as faixas |
| 1 | `lote_preparar.py` | áudio do corte + transcrição do corte (+ guarda de pontuação) |
| 2 | `lote_produzir.py` | o render. Zoom, legenda, leak, punch, P&B, texto, tarja, card, música |
| 3 | `lote_verificar.py` | dimensão, sync, nível, pico — e publica no Drive com `--publicar` |
| 4 | `exportar_legendas.py` | `.srt` e `.txt` para o analista |

Chamados pela fase 2: `gerar_ass.py`, `texto_grande.py`, `musica.py`.
Chamado pela fase 1: `pontuacao.py`.

## Fora do fluxo

- `musica_no_render.py` — põe trilha num vídeo já aprovado copiando o vídeo
  bit a bit (`-c:v copy`). Foi assim que o vídeo 7 ganhou música sem
  re-renderizar o que ele aprovou.
- `analise/` — medição e diagnóstico. Não entram no render.
- `legado/` — o caminho de um vídeo por vez, anterior ao lote.
  `produzir_v7b.py` é o que gerou o **vídeo 7**, o template aprovado; está
  aqui porque é a origem de quase todo número do padrão.

## Ler antes de mexer

`../docs/03-armadilhas.md`. Cada armadilha ali aconteceu de verdade. As que
mais voltam:

- **§I9** — `fps` tem de vir **antes** do `perspective`. Bruto de 59,94 fps
  fazia a curva de zoom rodar em dobro. Sobreviveu a 3 rodadas de revisão
  disfarçado de problema estético.
- **§I7** — o medidor de zoom **mente** em render concatenado. Resultado
  plano não prova ausência; confirme com dois quadros lado a lado.
- **§I14** — constante derivada de um parâmetro precisa ser escrita **em
  função** dele. Mudar o `PAD` sem recalcular a tolerância do leak zerou os
  leaks de dois vídeos, sem dar erro.
- **§I16** — recorte de frase em destaque é permitido; paráfrase não.

## Uma armadilha que mora no `config.py`

O parser de filtro do ffmpeg usa `:` como separador de opção e **não existe
escape que funcione** para o caminho do modelo do whisper — testados
`D\:/...`, `'D:/...'` e drive-less, os três em 31/07/2026. A saída é rodar
com o `cwd` no drive do modelo, passar o modelo sem letra de drive e o
destino como **nome puro**, e mover o arquivo depois. É o que
`config.transcrever()` faz. Sem isso, lote em `C:` com modelo em `D:` é
impossível — não existe caminho relativo entre drives no Windows.
