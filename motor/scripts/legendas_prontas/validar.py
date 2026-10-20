#!/usr/bin/env python3
"""Roda o gerador nos videos que JA tem .srt aprovado e mostra a diferenca.

E' a verdade conhecida deste lote. Se o gerador nao reproduzir o corte de
eventos e os tempos dos aprovados, ele nao pode ser apontado para os 16 que
faltam -- e um numero bonito de "16 arquivos gerados" nao prova nada.
"""
import difflib
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
from calibrar import GABARITOS, ler_srt  # noqa: E402
from lista import LEGENDAS, trab  # noqa: E402
from montar import montar  # noqa: E402


def rodar(nome, ap):
    aprov = ler_srt(os.path.join(LEGENDAS, os.path.splitext(os.path.basename(nome))[0] + ".srt"))
    meus, avisos = montar(ap)
    print(f"\n########## {ap}: aprovado {len(aprov)} eventos, "
          f"gerado {len(meus)}")
    a = [e["txt"] for e in aprov]
    b = [e["txt"] for e in meus]
    iguais = 0
    sm = difflib.SequenceMatcher(a=a, b=b, autojunk=False)
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            iguais += i2 - i1
            for d in range(i2 - i1):
                dt = meus[j1 + d]["ini"] - aprov[i1 + d]["ini"]
                if abs(dt) > 0.25:
                    print(f"  tempo  {aprov[i1+d]['ini']:6.3f} x "
                          f"{meus[j1+d]['ini']:6.3f} ({dt:+.3f})  "
                          f"{a[i1+d]!r}")
        else:
            print(f"  TEXTO  aprovado {a[i1:i2]}")
            print(f"         gerado   {b[j1:j2]}")
    print(f"  -> {iguais}/{len(a)} eventos identicos ao aprovado")
    if avisos:
        print(f"  -> {len(avisos)} divergencia(s) tela x audio")
    return iguais, len(a)


if __name__ == "__main__":
    tot = ok = 0
    for nome, ap in GABARITOS:
        if not os.path.exists(trab(f"{ap}_ocr.json")):
            print(f"== {ap}: sem OCR ainda")
            continue
        i, n = rodar(nome, ap)
        ok += i
        tot += n
    print(f"\nTOTAL {ok}/{tot} eventos reproduzidos")
