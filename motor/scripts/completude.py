#!/usr/bin/env python3
"""Contrato de completude: uma fase tem de dizer o que NAO conferiu, e por que.

**O buraco que isto fecha.** Todos os portoes deste projeto respondem a mesma
pergunta -- "o que eu medi esta' certo?" -- e nenhum responde a anterior:
"eu medi tudo?". Silencio e' indistinguivel de aprovacao. Foi assim que o
detector de tomada refeita passou de "ignorado" para "nem executado" em dois
lotes seguidos (Dra. Fulana 12/08, Dra. Fulana 12/08), e no lote seguinte
quatro pecas com tomada repetida foram publicadas para a cliente.

Um portao que nunca roda produz exatamente a mesma tela que um portao que
rodou e passou: nada. Este modulo torna essa diferenca visivel e cara.

A ideia e' emprestada do inventario do `claude-security` da Anthropic, onde a
varredura devolve DUAS listas -- os componentes varridos e os pulados, cada um
com motivo -- e uma resposta que omite um diretorio e' rejeitada e devolvida
("an answer that omits a directory is invalid... complete it, do not narrow
it"). Aqui a unidade nao e' diretorio, e' video do lote.

    cob = completude.Cobertura("fase 1", LOTE.videos)
    ...
    cob.conferido(v, "corte + transcricao + retimer")
    cob.pulado(v, "bruto ausente no Drive")     # motivo obrigatorio
    cob.fechar(LOTE, "preparacao")              # aborta se sobrou alguem

`fechar` levanta SystemExit quando algum alvo nao foi nem conferido nem
pulado. Nao e' zelo: e' o unico estado em que a fase mentiu sem querer.
"""
import sys


class Cobertura:
    """Leva a conta de quem foi conferido e de quem ficou de fora, com motivo."""

    def __init__(self, fase, alvos):
        self.fase = fase
        self.alvos = [str(a) for a in alvos]
        self._conferidos = {}
        self._pulados = {}

    def conferido(self, v, o_que):
        """Marca `v` como efetivamente verificado, dizendo o que foi feito."""
        self._conferidos[str(v)] = o_que
        self._pulados.pop(str(v), None)

    def pulado(self, v, motivo):
        """Marca `v` como deliberadamente NAO verificado. Motivo e' obrigatorio.

        Pular sem motivo e' o mesmo que esquecer -- e a diferenca entre os dois
        e' justamente o que esta classe existe para registrar.
        """
        motivo = str(motivo).strip()
        if not motivo:
            raise ValueError(f"{self.fase}: v{v} foi pulado sem motivo.")
        self._pulados[str(v)] = motivo
        self._conferidos.pop(str(v), None)

    @property
    def faltando(self):
        vistos = set(self._conferidos) | set(self._pulados)
        return [a for a in self.alvos if a not in vistos]

    def resumo(self):
        """O que vai para o relatorio em disco (e para o semaforo depois)."""
        return {
            "fase": self.fase,
            "alvos": self.alvos,
            "conferidos": dict(self._conferidos),
            "pulados": dict(self._pulados),
            "faltando": self.faltando,
        }

    def imprimir(self):
        c, p, f = len(self._conferidos), len(self._pulados), len(self.faltando)
        print(f"\nCOBERTURA {self.fase}: {c} conferido(s), {p} pulado(s), "
              f"{f} sem resposta - de {len(self.alvos)} no lote.")
        for v, motivo in sorted(self._pulados.items()):
            print(f"   v{v}: PULADO - {motivo}")
        for v in self.faltando:
            print(f"   v{v}: SEM RESPOSTA")

    def fechar(self, LOTE=None, nome=None):
        """Imprime, grava no relatorio e ABORTA se alguem ficou sem resposta."""
        self.imprimir()
        if LOTE is not None and nome:
            try:
                import relatorio
                anterior = relatorio.ler(LOTE, nome) or {}
                anterior["cobertura"] = self.resumo()
                relatorio.gravar(LOTE, nome, anterior)
            except Exception as e:                            # noqa: BLE001
                print(f"   (cobertura nao foi gravada: {e})")
        if self.faltando:
            raise SystemExit(
                f"\n{self.fase}: {len(self.faltando)} video(s) sem resposta "
                f"({', '.join('v' + v for v in self.faltando)}).\n"
                f"Cada video do lote tem de sair desta fase como CONFERIDO ou "
                f"como PULADO com motivo. Nao existe terceira opcao - foi a "
                f"terceira opcao que publicou tomada refeita para a cliente.")


def exigir(fase, esperados, obtidos, o_que="itens"):
    """Versao avulsa: aborta se `obtidos` nao cobre `esperados`.

    Para quando nao vale a pena instanciar a classe -- por exemplo conferir
    que o numero de pecas medidas bate com o numero de pecas do lote.
    """
    falta = [e for e in esperados if e not in obtidos]
    if falta:
        raise SystemExit(f"{fase}: faltaram {len(falta)} {o_que}: {falta}")


if __name__ == "__main__":
    # Autoteste: o modulo tem de reprovar o caso que ele existe para pegar.
    cob = Cobertura("autoteste", [1, 2, 3])
    cob.conferido(1, "ok")
    cob.pulado(2, "bruto ausente")
    assert cob.faltando == ["3"], cob.faltando
    try:
        cob.fechar()
    except SystemExit:
        pass
    else:                                                     # pragma: no cover
        sys.exit("FALHOU: cobertura incompleta nao abortou")
    cob.conferido(3, "ok")
    assert cob.faltando == []
    cob.fechar()
    try:
        cob.pulado(1, "   ")
    except ValueError:
        pass
    else:                                                     # pragma: no cover
        sys.exit("FALHOU: pular sem motivo foi aceito")
    print("autoteste OK")
