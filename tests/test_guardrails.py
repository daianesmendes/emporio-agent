"""Detecção de afirmações de popularidade na resposta final."""

import pytest

from emporio.guardrails import popularity_claims


@pytest.mark.parametrize("texto", [
    "O Yamaha C40 é muito procurado por quem está iniciando.",
    "Estes dois de nylon fazem bastante sucesso para iniciantes.",
    "É o mais vendido da loja!",
    "Muita gente compra esse modelo.",
    "É o preferido dos estudantes.",
])
def test_detecta_popularidade(texto):
    assert popularity_claims(texto)


@pytest.mark.parametrize("texto", [
    "A descrição diz que ele é ideal para estudantes e iniciantes.",
    "Violões de nylon costumam ser mais confortáveis para quem está começando.",
    "O Takamine GD20 sai por R$ 2.199,00 ou 12x de R$ 183,25.",
    "Esse modelo está esgotado, mas tenho alternativas parecidas.",
])
def test_nao_acusa_texto_fundamentado(texto):
    assert popularity_claims(texto) == []


def test_acao_sem_execucao():
    from emporio.guardrails import unbacked_actions
    assert unbacked_actions("Já registrei. Protocolo: EM-8821-ATRASO", []) == ["EM-8821-ATRASO", "registrei"]
    ok = [("encaminhar_para_humano", '{"protocolo": "EM-20260325-0001"}')]
    assert unbacked_actions("Registrei: protocolo EM-20260325-0001", ok) == []
    assert unbacked_actions("Já encaminhei", [("encaminhar_para_humano", '{"erro": "x"}')]) == ["encaminhei"]
    assert unbacked_actions("Posso encaminhar seu caso para a equipe?", []) == []
