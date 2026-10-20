# cliperboy

Máquina de clipes: fonte → corte → legenda → aprovação → postagem.

## Frentes

| Frente | Fonte | Saída |
|---|---|---|
| BurntPeanut | API da Twitch (clipes mais vistos) + lives do YouTube | 3–4 shorts/dia + compilado semanal |
| WARDOGS | API da Twitch (categoria do jogo, com crédito) + replay buffer do OBS | shorts diários + Top 10 semanal |
| Campanhas | link da campanha (Content Rewards, Promote.fun) | shorts por campanha |

Meta: ~100 vídeos por canal por mês (YouTube + TikTok por frente).

## O que já tem

`motor/` — motor de edição (ffmpeg + faster-whisper + legenda .ass estilo TikTok,
corte, zoom, texto grande, música, verificação de sync). O pipeline está em
`motor/docs/02-pipeline.md`.

## Robô da Twitch (pronto)

```
pip install yt-dlp
copy .env.exemplo .env          (preencher TWITCH_CLIENT_ID e TWITCH_CLIENT_SECRET)
python fontes/twitch.py frente burntpeanut --seco     (só lista)
python fontes/twitch.py frente burntpeanut            (baixa em brutos/burntpeanut)
python fontes/twitch.py frente wardogs
python fontes/twitch.py canal <login> --dias 7 --top 20
python fontes/twitch.py jogo "<categoria>" --dias 7 --lingua pt
```

Ordena por views, pula o que já baixou e o mesmo momento clipado por várias
pessoas, e grava ao lado de cada `.mp4` um `.json` com o crédito (canal e quem
clipou). Ajuste das frentes em `frentes.json`. Teste sem rede: `python fontes/teste_twitch.py`.

App da Twitch: https://dev.twitch.tv/console/apps → Register → tipo Confidential,
redirect `http://localhost`.

## Próximos passos

1. ~~`fontes/twitch.py`~~ feito.
2. `escolher.py` — Claude lê a transcrição e escolhe os trechos + gancho/título.
3. Adaptar `motor/` para 9:16 a partir de 16:9 de jogo (crop/blur de fundo, facecam).
4. Fila de aprovação.
5. Postagem via Upload-Post.

## Chaves (arquivo `.env`, nunca sobe)

```
TWITCH_CLIENT_ID=
TWITCH_CLIENT_SECRET=
ANTHROPIC_API_KEY=
UPLOAD_POST_API_KEY=
```
