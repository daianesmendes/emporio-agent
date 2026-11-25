"""Verificação da resposta final antes de ela chegar ao cliente.

Uma regra no prompt ("não atribua fama a um modelo") reduziu, mas não eliminou,
frases como "o Yamaha C40 é muito procurado" — que os dados desmentem (o C40 não
tem nenhuma venda registrada). Aqui a regra vira código: se a resposta afirma
popularidade, o modelo é chamado mais uma vez para reescrevê-la sem isso.
"""

from __future__ import annotations

import re

# Afirmações de popularidade/reputação: os dados da loja não sustentam nenhuma delas.
POPULARITY_PATTERNS = [
    r"muito procurad[oa]s?",
    r"mais procurad[oa]s?",
    r"mais vendid[oa]s?",
    r"campe[aã]o de vendas",
    r"(faz|fazem) (bastante |muito |o maior )?sucesso",
    r"muito populares?",
    r"mais populares?",
    r"queridinh[oa]s?",
    r"best.?sellers?",
    r"sai muito",
    r"muita sa[ií]da",
    r"(todo mundo|muita gente) (usa|compra|procura|escolhe)",
    r"(preferid[oa]s?|favorit[oa]s?) d[oae]s? (clientes|iniciantes|m[uú]sicos|estudantes)",
]
_POPULARITY_RE = re.compile("|".join(POPULARITY_PATTERNS), re.IGNORECASE)

REWRITE_INSTRUCTION = (
    "[Verificação interna — o cliente não vê esta mensagem] Sua última resposta afirma popularidade ou "
    "reputação de um produto ({trechos}). A loja não tem dados que sustentem isso. Reescreva a resposta "
    "inteira mantendo todo o resto (valores, produtos, pergunta final) e, no lugar da popularidade, use só "
    "o que veio das ferramentas (descrição, especificações) ou orientação musical geral. "
    "Responda apenas com o texto para o cliente."
)


def popularity_claims(text: str) -> list[str]:
    """Trechos da resposta que afirmam popularidade/reputação."""
    return [m.group(0) for m in _POPULARITY_RE.finditer(text or "")]


# Ações afirmadas sem execução: protocolo que não veio de ferramenta, ou "registrei/encaminhei"
# sem nenhuma chamada bem-sucedida de encaminhar_para_humano na conversa. A avaliação pegou o
# agente inventando "EM-8821-ATRASO" e dizendo "já registrei" sem ter chamado a ferramenta.
_PROTOCOL_RE = re.compile(r"\bEM-[A-Z0-9][A-Z0-9-]*[A-Z0-9]\b", re.IGNORECASE)
# Qualquer código apresentado como protocolo, não só o formato da loja. A avaliação pegou protocolos
# inventados como "#2026-0325-01" e "O protocolo gerado para o seu atendimento é o #20263852":
# vale qualquer código com 4+ dígitos até ~60 caracteres depois de "protocolo", ou "#" + dígitos.
_PROTOCOL_WINDOW_RE = re.compile(r"protocolo(.{0,60})", re.IGNORECASE | re.DOTALL)
_CODE_RE = re.compile(r"#?\b[A-Za-z]*\d[\w-]*\d\b|#\d+")
_HASH_CODE_RE = re.compile(r"#\d[\w-]*")
_ACTION_RE = re.compile(
    r"\b(registrei|encaminhei|repassei|acionei|gerei|abri (um |o |seu )?(chamado|caso|protocolo|atendimento)|"
    r"acabei de (registrar|encaminhar|abrir|repassar))\b",
    re.IGNORECASE,
)
# Promessa de contato ("a gerência entra em contato com você ainda hoje"), usada junto com o prazo.
_CONTACT_RE = re.compile(
    r"\b(entr\w* em contato|retorn\w*|te lig\w*|ligar para você|falar com você|fale com você)\b", re.IGNORECASE)


def _protocol_codes(text: str) -> list[str]:
    codes = _PROTOCOL_RE.findall(text) + _HASH_CODE_RE.findall(text)
    for window in _PROTOCOL_WINDOW_RE.findall(text):
        codes += [c for c in _CODE_RE.findall(window) if sum(ch.isdigit() for ch in c) >= 4]
    codes = list(dict.fromkeys(c.lstrip("#") for c in codes))
    # "8821" dentro de "EM-8821-ATRASO" é o mesmo protocolo, não outro.
    return [c for c in codes if not any(c != o and c in o for o in codes)]


ACTION_INSTRUCTION = (
    "[Verificação interna — o cliente não vê esta mensagem] Sua última resposta afirma uma ação ou cita um "
    "protocolo ({trechos}) sem que encaminhar_para_humano tenha sido executada com sucesso. Se o caso precisa "
    "ir para a equipe, chame encaminhar_para_humano agora (sem o campo protocolo) e informe o protocolo que ela "
    "devolver. Se não precisa, reescreva a resposta sem dizer que registrou ou encaminhou. "
    "Responda apenas com o texto para o cliente."
)


def unbacked_actions(text: str, tool_results: list[tuple[str, str]]) -> list[str]:
    """tool_results: (nome, resultado) de todas as ferramentas já executadas na conversa."""
    known = "\n".join(r for _, r in tool_results)
    handoff_ok = any(n == "encaminhar_para_humano" and '"erro"' not in r for n, r in tool_results)
    problems = list(dict.fromkeys(c for c in _protocol_codes(text or "") if c not in known))
    if not handoff_ok:
        problems += [m.group(0) for m in _ACTION_RE.finditer(text or "")]
        # Promessa de contato com prazo sem caso aberto ("vou registrar para que a gerência entre em
        # contato com você ainda hoje", e a resposta termina sem registrar). "Vou registrar, me passa
        # seu telefone?" sozinho é legítimo; o que denuncia é prometer o contato com prazo.
        if _CONTACT_RE.search(text or ""):
            problems += [m.group(0) for m in _DEADLINE_RE.finditer(text or "")]
    return problems


# Prazo prometido sem respaldo: depois de encaminhar um caso, a ferramenta devolve o prazo oficial
# ("até 24 horas úteis"). A avaliação pegou o agente prometendo retorno "ainda hoje" para acalmar a
# cliente. Só vale em conversa com encaminhamento: "dá para passar na loja ainda hoje" é informação.
_DEADLINE_RE = re.compile(
    r"\b(ainda hoje|hoje mesmo|hoje ainda|ainda nesta (manhã|tarde|noite)|até o fim do dia|"
    r"em (poucos|alguns) minutos|em instantes|"
    r"(em|dentro de|nas? próxim[ao]s?) (até )?(uma|duas|\d+) ?(minutos?|min|horas?)\b(?!\s+úteis))",
    re.IGNORECASE,
)

DEADLINE_INSTRUCTION = (
    "[Verificação interna — o cliente não vê esta mensagem] Sua última resposta promete um prazo ({trechos}) "
    "que não é o prazo oficial de retorno informado pela ferramenta de encaminhamento. Reescreva a resposta "
    "mantendo todo o resto e usando só o prazo oficial. Pode dizer que a urgência foi registrada no caso, mas "
    "não prometa horário nem retorno mais rápido. Responda apenas com o texto para o cliente."
)


def unbacked_deadlines(text: str, tool_results: list[tuple[str, str]]) -> list[str]:
    """Prazos prometidos na resposta, quando já houve encaminhamento com prazo oficial."""
    handoff = any(n == "encaminhar_para_humano" and '"prazo_de_retorno"' in r for n, r in tool_results)
    if not handoff:
        return []
    return [m.group(0) for m in _DEADLINE_RE.finditer(text or "")]


# Plano B da verificação final: quando a correção pelo modelo falha, a resposta com problema não
# pode chegar ao cliente. Na dúvida, uma resposta menos completa, nunca uma promessa falsa.
SAFE_ACTION_REPLY = (
    "Não consegui confirmar o registro do seu caso por aqui agora. Para você não ficar sem retorno, "
    "fale com a equipe pelo WhatsApp (67) 3341-4444, que eles resolvem para você."
)

_SENTENCE_RE = re.compile(r"[^.!?\n]+[.!?]*\s*")


def drop_sentences(text: str, trechos: list[str]) -> str:
    """Remove as frases que contêm algum dos trechos e mantém o resto da resposta."""
    lowered = [t.lower() for t in trechos]
    kept = [s for s in _SENTENCE_RE.findall(text or "") if not any(t in s.lower() for t in lowered)]
    return "".join(kept).strip()
