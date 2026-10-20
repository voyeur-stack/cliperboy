"""Teste sem rede: seleção, ficha e leitura de frentes. `python fontes/teste_twitch.py`"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import twitch as T

def c(i, v, d=30, lang="en", vid="v1", off=None):
    return {"id": i, "view_count": v, "duration": d, "language": lang, "video_id": vid,
            "vod_offset": off, "title": f"t{i}", "broadcaster_name": "BurntPeanut",
            "creator_name": "fã", "url": f"https://clips.twitch.tv/{i}",
            "created_at": "2026-10-20T10:00:00Z", "game_id": "1"}

lista = [c("a", 50), c("b", 900, off=100), c("c", 800, off=105), c("d", 700, d=90),
         c("e", 600, lang="pt"), c("f", 500), c("g", 10)]
s = T.selecionar(lista, top=10, min_views=20, lingua="en", max_dur=60, ja={"f"})
ids = [x["id"] for x in s]
assert ids == ["b", "a"], ids          # c = mesmo momento de b; d longo; e pt; f já; g poucas views
f = T.ficha(lista[1])
assert f["credito"].startswith("🎥 BurntPeanut") and f["url"].endswith("/b")
ini, fim = T.periodo(7)
assert ini.endswith("Z") and fim > ini
import json; fr = json.loads((T.RAIZ / "frentes.json").read_text(encoding="utf-8"))
assert set(fr) == {"burntpeanut", "wardogs"}
print("ok —", ids)
