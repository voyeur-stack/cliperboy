#!/usr/bin/env python3
"""Onde cada fase deixa o que mediu, para o semaforo poder juntar depois.

Ate 13/08/2026 cada fase imprimia a sua tabela e acabava ali. Quem quisesse
saber como o lote estava lia tres terminais e juntava na cabeca -- e foi
assim que quatro renders de ZERO BYTE atravessaram a fase 2 com
"FASE 2 CONCLUIDA" na tela (Dra. Fulana, 11/08/2026).

Isto aqui nao mede nada e nao decide nada. So' da' um endereco fixo para o
que ja' estava sendo medido, em formato que outro script consegue ler.

    relatorio.gravar(LOTE, "verificacao", {"pecas": [...]})
    dados = relatorio.ler(LOTE, "verificacao")     # None se nao existir
"""
import json
import os
import time


def pasta(LOTE):
    """`<lote>/relatorio/`, criada na hora se ainda nao existir."""
    p = os.path.join(LOTE.pasta, "relatorio")
    os.makedirs(p, exist_ok=True)
    return p


def caminho(LOTE, nome):
    return os.path.join(pasta(LOTE), f"{nome}.json")


def gravar(LOTE, nome, dados):
    """Grava `dados` carimbado com a hora. Nunca derruba a fase que chamou.

    Uma fase que ja' rodou meia hora de encode nao pode morrer no fim porque
    o relatorio nao conseguiu escrever -- o relatorio e' registro, nao
    portao. Falhou, avisa e segue.
    """
    try:
        pacote = dict(dados)
        pacote["_gravado"] = time.strftime("%Y-%m-%d %H:%M:%S")
        pacote["_lote"] = LOTE.nome
        with open(caminho(LOTE, nome), "w", encoding="utf-8") as f:
            json.dump(pacote, f, ensure_ascii=False, indent=1)
        return True
    except Exception as e:                                   # noqa: BLE001
        print(f"      (relatorio '{nome}' nao foi gravado: {e})")
        return False


def ler(LOTE, nome):
    """Devolve o dicionario gravado, ou None se o arquivo nao existir/estiver
    corrompido. Ausencia nao e' erro: a fase pode simplesmente nao ter rodado
    ainda, e o semaforo precisa saber a diferenca entre 'nao rodou' e 'rodou e
    passou'."""
    try:
        with open(caminho(LOTE, nome), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None
