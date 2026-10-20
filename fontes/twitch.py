"""Robô da Twitch: puxa os clipes mais vistos de um canal ou de um jogo e baixa.

Os clipes da Twitch já são a curadoria do público — quem assistiu à live
apertou "clip" no momento bom. A gente só ordena por views, tira o que já
baixou e guarda a ficha de crédito de cada um (canal + quem clipou), que é o
que vai na tela e na descrição do short e do compilado.

Uso:
    python fontes/twitch.py canal burntpeanut --dias 1 --top 10
    python fontes/twitch.py jogo WARDOGS --dias 7 --top 30 --min-views 200
    python fontes/twitch.py frente burntpeanut          (lê frentes.json)
    python fontes/twitch.py frente wardogs --seco       (só lista, não baixa)

Chaves no `.env` da raiz (nunca sobe):
    TWITCH_CLIENT_ID=...
    TWITCH_CLIENT_SECRET=...
Crie o app em https://dev.twitch.tv/console/apps (grátis, tipo "Confidential",
redirect http://localhost). Só lê dado público — não precisa logar como você.

Baixar usa o `yt-dlp` (precisa estar no PATH).
"""
import argparse
import datetime as dt
import json
import os
import pathlib
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request

RAIZ = pathlib.Path(__file__).resolve().parent.parent
HELIX = "https://api.twitch.tv/helix"


# ---------------------------------------------------------------- chaves

def ler_env():
    env = {}
    arq = RAIZ / ".env"
    if arq.exists():
        for linha in arq.read_text(encoding="utf-8").splitlines():
            linha = linha.strip()
            if linha and not linha.startswith("#") and "=" in linha:
                k, v = linha.split("=", 1)
                env[k.strip()] = v.strip().strip('"')
    for k in ("TWITCH_CLIENT_ID", "TWITCH_CLIENT_SECRET"):
        env[k] = os.environ.get(k, env.get(k, ""))
    falta = [k for k in ("TWITCH_CLIENT_ID", "TWITCH_CLIENT_SECRET") if not env[k]]
    if falta:
        sys.exit(f"falta no .env: {', '.join(falta)} — ver o topo de fontes/twitch.py")
    return env


# ---------------------------------------------------------------- API

class Twitch:
    def __init__(self, client_id, secret):
        self.client_id = client_id
        corpo = urllib.parse.urlencode({
            "client_id": client_id, "client_secret": secret,
            "grant_type": "client_credentials"}).encode()
        with urllib.request.urlopen("https://id.twitch.tv/oauth2/token", corpo) as r:
            self.token = json.load(r)["access_token"]

    def get(self, rota, **params):
        url = f"{HELIX}/{rota}?{urllib.parse.urlencode(params, doseq=True)}"
        req = urllib.request.Request(url, headers={
            "Client-Id": self.client_id, "Authorization": f"Bearer {self.token}"})
        with urllib.request.urlopen(req) as r:
            return json.load(r)

    def id_canal(self, login):
        dados = self.get("users", login=login.lower())["data"]
        if not dados:
            sys.exit(f"canal não encontrado na Twitch: {login}")
        return dados[0]["id"]

    def id_jogo(self, nome):
        dados = self.get("games", name=nome)["data"]
        if not dados:
            sys.exit(f"jogo não encontrado na Twitch: {nome} (use o nome exato da categoria)")
        return dados[0]["id"]

    def clipes(self, inicio, fim, limite=500, **filtro):
        """Todos os clipes do período, paginando (a API devolve 100 por vez)."""
        saida, cursor = [], None
        while len(saida) < limite:
            p = dict(filtro, first=100, started_at=inicio, ended_at=fim)
            if cursor:
                p["after"] = cursor
            r = self.get("clips", **p)
            saida += r["data"]
            cursor = r.get("pagination", {}).get("cursor")
            if not cursor or not r["data"]:
                break
        return saida


# ---------------------------------------------------------------- seleção

def selecionar(clipes, top, min_views=0, lingua=None, max_dur=60.0, ja=()):
    """Ordena por views e corta: já baixado, poucas views, língua, duração."""
    vistos, bons = set(), []
    for c in sorted(clipes, key=lambda c: c["view_count"], reverse=True):
        if c["id"] in ja or c["id"] in vistos:
            continue
        if c["view_count"] < min_views or c["duration"] > max_dur:
            continue
        if lingua and c.get("language") != lingua:
            continue
        # o mesmo momento clipado por várias pessoas: fica o mais visto
        chave = (c.get("video_id") or c["id"], c.get("vod_offset") and int(c["vod_offset"]) // 20)
        if c.get("vod_offset") is not None and chave in vistos:
            continue
        vistos.add(c["id"])
        vistos.add(chave)
        bons.append(c)
        if len(bons) >= top:
            break
    return bons


def ficha(c):
    """O que o resto da máquina precisa: crédito, link e números."""
    return {
        "id": c["id"],
        "titulo": c["title"],
        "canal": c["broadcaster_name"],
        "clipado_por": c["creator_name"],
        "url": c["url"],
        "views": c["view_count"],
        "duracao": c["duration"],
        "criado_em": c["created_at"],
        "lingua": c.get("language"),
        "jogo_id": c.get("game_id"),
        "credito": f"🎥 {c['broadcaster_name']} — twitch.tv/{c['broadcaster_name'].lower()}",
    }


# ---------------------------------------------------------------- disco

def pasta_frente(nome):
    p = RAIZ / "brutos" / nome
    p.mkdir(parents=True, exist_ok=True)
    return p


def ler_ja(pasta):
    arq = pasta / "_baixados.json"
    return set(json.loads(arq.read_text(encoding="utf-8"))) if arq.exists() else set()


def gravar_ja(pasta, ids):
    (pasta / "_baixados.json").write_text(json.dumps(sorted(ids), indent=0), encoding="utf-8")


def baixar(f, pasta):
    if not shutil.which("yt-dlp"):
        sys.exit("yt-dlp não está no PATH — instale com: pip install yt-dlp")
    dia = f["criado_em"][:10]
    destino = pasta / f"{dia}_{f['views']:06d}v_{f['id']}.mp4"
    if destino.exists():
        return destino
    r = subprocess.run(["yt-dlp", "-q", "--no-warnings", "-f", "best[ext=mp4]/best",
                        "-o", str(destino), f["url"]], capture_output=True, text=True)
    if r.returncode != 0 or not destino.exists():
        print(f"  ✗ falhou {f['id']}: {r.stderr.strip()[:200]}")
        return None
    destino.with_suffix(".json").write_text(json.dumps(f, ensure_ascii=False, indent=2), encoding="utf-8")
    return destino


# ---------------------------------------------------------------- CLI

def periodo(dias):
    fim = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    ini = fim - dt.timedelta(days=dias)
    return ini.isoformat().replace("+00:00", "Z"), fim.isoformat().replace("+00:00", "Z")


def rodar(tipo, alvo, nome_frente, dias, top, min_views, lingua, max_dur, seco):
    env = ler_env()
    tw = Twitch(env["TWITCH_CLIENT_ID"], env["TWITCH_CLIENT_SECRET"])
    filtro = ({"broadcaster_id": tw.id_canal(alvo)} if tipo == "canal"
              else {"game_id": tw.id_jogo(alvo)})
    ini, fim = periodo(dias)
    todos = tw.clipes(ini, fim, **filtro)
    pasta = pasta_frente(nome_frente)
    ja = ler_ja(pasta)
    escolha = selecionar(todos, top, min_views, lingua, max_dur, ja)
    print(f"{alvo}: {len(todos)} clipes em {dias}d, {len(escolha)} novos escolhidos")
    for c in escolha:
        f = ficha(c)
        print(f"  {f['views']:>7} views  {f['duracao']:>4.0f}s  {f['canal']:<18} {f['titulo'][:60]}")
        if not seco and baixar(f, pasta):
            ja.add(f["id"])
    if not seco:
        gravar_ja(pasta, ja)
        print(f"→ {pasta}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("tipo", choices=["canal", "jogo", "frente"])
    ap.add_argument("alvo", help="login do canal, nome do jogo, ou nome da frente em frentes.json")
    ap.add_argument("--dias", type=int)
    ap.add_argument("--top", type=int)
    ap.add_argument("--min-views", type=int)
    ap.add_argument("--lingua", help="ex.: en, pt (vazio = todas)")
    ap.add_argument("--max-dur", type=float, help="segundos (padrão 60)")
    ap.add_argument("--seco", action="store_true", help="só lista, não baixa")
    a = ap.parse_args(argv)

    cfg = {"dias": 1, "top": 10, "min_views": 0, "lingua": None, "max_dur": 60.0}
    tipo, alvo, nome = a.tipo, a.alvo, a.alvo.lower()
    if a.tipo == "frente":
        frentes = json.loads((RAIZ / "frentes.json").read_text(encoding="utf-8"))
        if a.alvo not in frentes:
            sys.exit(f"frente '{a.alvo}' não existe em frentes.json ({', '.join(frentes)})")
        fr = frentes[a.alvo]
        tipo, alvo = fr["tipo"], fr["alvo"]
        cfg.update({k: v for k, v in fr.items() if k in cfg})
    for k in cfg:
        v = getattr(a, k)
        if v is not None:
            cfg[k] = v
    rodar(tipo, alvo, nome, cfg["dias"], cfg["top"], cfg["min_views"],
          cfg["lingua"], cfg["max_dur"], a.seco)


if __name__ == "__main__":
    main()
