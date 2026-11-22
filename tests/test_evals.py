"""Checagens determinísticas da avaliação (sem LLM)."""

import json

from emporio.evals import CASES_FILE, _contains, check_case, money_values


def _turn(resposta, ferramentas=(), usuario="oi"):
    return {"usuario": usuario, "resposta": resposta, "reescrita": [],
            "ferramentas": [{"nome": n, "argumentos": {}, "resultado": r} for n, r in ferramentas]}


def test_casos_bem_formados():
    casos = json.loads(CASES_FILE.read_text(encoding="utf-8"))
    ids = [c["id"] for c in casos]
    assert len(ids) == len(set(ids)) >= 30
    assert all(c["mensagens"] and c.get("criterio") for c in casos)


def test_contains_respeita_fronteiras():
    assert _contains("Prazo de 7 dias", "7")
    assert not _contains("Prazo de 17 dias", "7")
    assert not _contains("Na semana passada", "Ana")
    assert _contains("A loja fica fechada", "fechad")
    assert _contains("Endereço inválido", "endereco")


def test_money_values():
    assert money_values("R$ 2.199,00 ou R$ 35 e R$1000") == {2199.0, 35.0, 1000.0}


def test_valor_sem_origem_reprova():
    caso = {"id": "x"}
    turno = _turn("Sai por R$ 2.199,00, ou R$ 1.999,00 à vista.",
                  [("detalhes_produto", '{"preco_tabela": "R$ 2.199,00"}')])
    checks = check_case(caso, [turno], system_prompt="")
    assert not checks["valores_rastreaveis"]["ok"]
    assert "1999.0" in str(checks["valores_rastreaveis"]["detalhe"])


def test_caso_aprovado_e_reprovado_por_ferramenta():
    caso = {"id": "x", "ferramentas_proibidas": ["consultar_pedido"], "deve_conter": [["e-mail", "telefone"]]}
    ok = check_case(caso, [_turn("Me passa o e-mail da compra?")], "")
    assert all(c["ok"] for c in ok.values())
    ruim = check_case(caso, [_turn("Achei!", [("consultar_pedido", "{}")])], "")
    assert not ruim["ferramentas"]["ok"] and not ruim["deve_conter"]["ok"]


def test_vazamento_e_popularidade():
    checks = check_case({"id": "x"}, [_turn("Usei buscar_produtos: é o mais vendido!")], "")
    assert not checks["sem_vazamento_tecnico"]["ok"]
    assert not checks["sem_popularidade"]["ok"]


def test_acao_sem_execucao_por_turno():
    turnos = [_turn("Já registrei! Protocolo EM-8821-ATRASO"),
              _turn("Pronto", [("encaminhar_para_humano", '{"protocolo": "EM-20260325-0001"}')])]
    checks = check_case({"id": "x"}, turnos, "")
    assert not checks["acoes_rastreaveis"]["ok"]
