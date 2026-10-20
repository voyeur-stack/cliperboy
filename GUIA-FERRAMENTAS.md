# Guia — ferramentas do GitHub para a máquina de clipes

Varredura de 20/10/2026 no GitHub. ⭐ = estrelas, "ativo" = teve commit nos últimos 30 dias.
Nada aqui foi instalado ainda — é o mapa pra montar em casa.

---

## 0. Preparar o PC de casa (uma vez)

No PowerShell, um comando por vez:

```
winget install Git.Git
winget install Python.Python.3.12
winget install Gyan.FFmpeg
winget install GitHub.cli
```

Feche e abra o PowerShell, depois:

```
gh auth login
pip install yt-dlp faster-whisper
```

Placa NVIDIA: atualize o driver. O faster-whisper usa a placa sozinho e transcreve muito mais rápido.

Pasta de trabalho sugerida: `C:\Clipes`. Tudo abaixo é clonado dentro dela:

```
mkdir C:\Clipes\ferramentas
cd C:\Clipes\ferramentas
git clone https://github.com/<dono>/<repo>.git
```

---

## 1. A base (as peças que todo mundo usa por baixo)

| Repo | ⭐ | Pra quê | Licença |
|---|---|---|---|
| [yt-dlp/yt-dlp](https://github.com/yt-dlp/yt-dlp) | 199k · ativo | baixar vídeo/clipe de Twitch, YouTube, Kick | Unlicense |
| [SYSTRAN/faster-whisper](https://github.com/SYSTRAN/faster-whisper) | 26k · ativo | transcrever rápido (GPU) | MIT |
| [m-bain/whisperX](https://github.com/m-bain/whisperX) | 24,7k · ativo | transcrição com tempo **por palavra** — é o que faz legenda estilo TikTok sincronizada | BSD-2 |
| [jianfch/stable-ts](https://github.com/jianfch/stable-ts) | 2,3k | alternativa ao whisperX para tempo por palavra | MIT |
| [Zulko/moviepy](https://github.com/Zulko/moviepy) | 15k | editar vídeo em Python (sobrepor texto, juntar, cortar) | MIT |
| [WyattBlue/auto-editor](https://github.com/WyattBlue/auto-editor) | 5,6k · ativo | corta silêncio e parte parada sozinho | Unlicense |
| [Breakthrough/PySceneDetect](https://github.com/Breakthrough/PySceneDetect) | 5,3k · ativo | acha troca de cena — útil pra separar jogada em compilado | BSD-3 |
| [streamlink/streamlink](https://github.com/streamlink/streamlink) | 11,9k · ativo | gravar live enquanto acontece | BSD-2 |
| [lay295/TwitchDownloader](https://github.com/lay295/TwitchDownloader) | 4k · ativo | baixar VOD/clipe da Twitch **com o chat renderizado** por cima | MIT |
| [remotion-dev/remotion](https://github.com/remotion-dev/remotion) | 65,6k · ativo | montar vídeo por código (React) — intro, ranking "Top 10", placar | própria (grátis pra indivíduo) |
| [mifi/lossless-cut](https://github.com/mifi/lossless-cut) | 44,8k · ativo | cortar na mão sem re-encodar (app com tela) | GPL-2 |

---

## 2. Cortadores prontos (vídeo longo → shorts com legenda)

Os "Opus Clip grátis". Bom pra **estudar e roubar ideia**, e pra testar antes de investir no nosso.

| Repo | ⭐ | O que tem de bom |
|---|---|---|
| [Anil-matcha/AI-Youtube-Shorts-Generator](https://github.com/Anil-matcha/AI-Youtube-Shorts-Generator) | 5,5k · ativo | o mais popular: escolhe o trecho por IA, corta 9:16, legenda. MIT |
| [JayWebtech/autoshorts](https://github.com/JayWebtech/autoshorts) | 1,3k · ativo | app de PC, local, vídeo longo → shorts |
| [RafaelGodoyEbert/ViralCutter](https://github.com/RafaelGodoyEbert/ViralCutter) | 429 | **feito por brasileiro**, entende PT-BR; YouTube → TikTok/Reels. GPL-3 |
| [divyaprakash0426/autoshorts](https://github.com/divyaprakash0426/autoshorts) | 205 · ativo | **feito pra gameplay** — o mais próximo do WARDOGS. Apache-2 |
| [artbyjazi/autoclip](https://github.com/artbyjazi/autoclip) | 187 | local, legenda queimada e **segue quem fala** no 9:16 |
| [NaufalRizqullah/opensource-clipping](https://github.com/NaufalRizqullah/opensource-clipping) | 176 | podcast/live → shorts |
| [fralapo/clippyme](https://github.com/fralapo/clippyme) | 61 · ativo | self-hosted, com tela |
| [ClipsAI/clipsai](https://github.com/ClipsAI/clipsai) | 555 | biblioteca Python: acha o trecho e reenquadra 9:16 (parado desde 2024) |

---

## 3. Compilado da Twitch (o nosso caso do BurntPeanut e do WARDOGS)

| Repo | ⭐ | O que é |
|---|---|---|
| [offish/twitchtube](https://github.com/offish/twitchtube) | 613 | o mais usado: pega os clipes mais vistos e monta compilado pro YouTube. MIT |
| [ContentAutomation/TwitchCompilationCreator](https://github.com/ContentAutomation/TwitchCompilationCreator) | 280 | compilado de gaming automático (parado desde 2022) |
| [viniciusenari/twitch-highlights-bot](https://github.com/viniciusenari/twitch-highlights-bot) | 49 | brasileiro, compilado semanal dos mais vistos. GPL-3 |
| [artkulak/twitch-stream-highlights-detection](https://github.com/artkulak/twitch-stream-highlights-detection) | 58 | detecta momento bom **pelo chat** (explosão de mensagens) — ideia boa pra live sem clipe |

O nosso `fontes/twitch.py` já faz a parte de "pegar os mais vistos"; o twitchtube é a referência pra montagem do compilado.

---

## 4. Postar

| Repo | ⭐ | Atenção |
|---|---|---|
| [eat-pray-ai/yutu](https://github.com/eat-pray-ai/yutu) | 702 · ativo | YouTube pela **API oficial**, com CLI e servidor MCP (dá pra o Claude operar). Apache-2 |
| [tokland/youtube-upload](https://github.com/tokland/youtube-upload) | 2,2k | upload YouTube por linha de comando (velho, mas funciona) |
| [makiisthenes/TiktokAutoUploader](https://github.com/makiisthenes/TiktokAutoUploader) | 1,2k · ativo | ⚠️ não é API oficial — usa o cookie da sua conta |
| [wkaisertexas/tiktok-uploader](https://github.com/wkaisertexas/tiktok-uploader) | 781 | ⚠️ idem, automação do navegador |

**TikTok:** os uploaders do GitHub não usam a API oficial; o TikTok pode marcar a conta como bot e derrubar
alcance ou banir. Pra conta que vai crescer, o caminho seguro é o Upload-Post (pago, aprovado no TikTok).
Os do GitHub servem pra conta de teste.

---

## 5. Fábricas completas (só pra estudar)

| Repo | ⭐ | Por que olhar |
|---|---|---|
| [harry0703/MoneyPrinterTurbo](https://github.com/harry0703/MoneyPrinterTurbo) | 133k · ativo | o maior do gênero: tema → roteiro → vídeo → legenda. Bom de ver a arquitetura |
| [RayVentura/ShortGPT](https://github.com/RayVentura/ShortGPT) | 8k | framework de canal automatizado de shorts |

São pra vídeo **gerado** (faceless), não pra clipe — não é o nosso caso, mas a organização em etapas é a mesma.

---

## 6. Ordem que eu seguiria em casa

1. Preparar o PC (seção 0).
2. Rodar o nosso `fontes/twitch.py` no BurntPeanut e no WARDOGS e ver os clipes baixando.
3. Clonar o **Anil-matcha/AI-Youtube-Shorts-Generator** e o **divyaprakash0426/autoshorts** e passar um vídeo do WARDOGS em cada — ver qual corte fica melhor.
4. Clonar o **offish/twitchtube** e montar um compilado de teste com os clipes da semana.
5. Com isso na mão, decidir o que a gente pega de cada um pro cliperboy.

Antes de rodar qualquer repo clonado: ler o README e o `requirements.txt`. Repo com poucas estrelas e
pedindo chave de API ou senha de rede social → não rodar.
