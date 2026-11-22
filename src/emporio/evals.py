"""Avaliação automatizada do agente.

Roda cada caso de evals/casos.json numa conversa nova e confere a resposta com
checagens determinísticas (código, sem LLM) e, opcionalmente, com um juiz LLM
para o que o código não mede (tom, empatia, aderência à política).

  uv run emporio-eval                              # todos os casos, modelos do .env
  uv run emporio-eval --modelo openai/gpt-oss-120b # fixa um modelo (sem fallback)
  uv run emporio-eval --juiz gemini-3.6-flash      # liga o juiz LLM
  uv run emporio-eval --casos preco_produto,garantia
  uv run emporio-eval --rejulgar padrao --juiz X    # refaz checagens/juiz sem chamar o agente
  uv run emporio-eval --modelo X --repeticoes 3 --esperar-cota 60 --continuar
  uv run emporio-eval --comparar rotulo1,rotulo2     # tabela lado a lado

Resultados em evals/resultados/<rótulo>.json e .md.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import statistics
import time
import unicodedata

import openai
from collections import Counter, defaultdict
from dataclasses import replace
from pathlib import Path

from . import config, tools
from .agent import Agent
from .data import Store
from .guardrails import popularity_claims, unbacked_actions
from .llm import LLMClient
from .prompts import build_system_prompt

ROOT = Path(__file__).resolve().parents[2]
CASES_FILE = ROOT / "evals" / "casos.json"
RESULTS_DIR = ROOT / "evals" / "resultados"

TOOL_NAMES = list(tools.TOOL_FUNCTIONS)
_MONEY_RE = re.compile(r"R\$\s?(\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?|\d+(?:,\d{1,2})?)")
_NUMBER_RE = re.compile(r"\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?|\d+(?:[.,]\d{1,2})?")


# ----------------------------------------------------------------------
# Checagens determinísticas
# ----------------------------------------------------------------------
def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "").casefold()
    return "".join(c for c in text if not unicodedata.combining(c))


def _contains(text: str, term: str) -> bool:
    """Busca sem acento/caixa. Números e termos curtos exigem fronteira de palavra
    ("7" não casa com "17"; "Ana" não casa com "semana"); termos longos podem ser
    radicais ("fechad" casa com "fechada")."""
    t = _norm(term)
    left = r"\b" if t[:1].isalnum() else ""
    right = r"\b" if t[-1:].isdigit() or (t[-1:].isalpha() and len(t) <= 4) else ""
    return re.search(left + re.escape(t) + right, _norm(text)) is not None


def _to_float(raw: str) -> float:
    raw = raw.strip()
    if "," in raw:
        raw = raw.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(\.\d{3})+", raw):
        raw = raw.replace(".", "")
    return round(float(raw), 2)


def money_values(text: str) -> set[float]:
    return {_to_float(m) for m in _MONEY_RE.findall(text or "")}


def known_numbers(*texts: str) -> set[float]:
    values = set()
    for t in texts:
        for m in _NUMBER_RE.findall(t or ""):
            try:
                values.add(_to_float(m))
            except ValueError:
                pass
    return values


def check_case(case: dict, turns: list[dict], system_prompt: str) -> dict[str, dict]:
    """turns: [{"usuario", "resposta", "ferramentas": [{"nome","argumentos","resultado"}], "reescrita"}]"""
    called = [c["nome"] for t in turns for c in t["ferramentas"]]
    answers = "\n\n".join(t["resposta"] for t in turns)
    final = turns[-1]["resposta"]
    tool_output = "\n".join(c["resultado"] for t in turns for c in t["ferramentas"])
    user_text = "\n".join(t["usuario"] for t in turns)
    checks: dict[str, dict] = {}

    missing = [n for n in case.get("ferramentas_obrigatorias", []) if n not in called]
    forbidden = [n for n in case.get("ferramentas_proibidas", []) if n in called]
    if case.get("ferramentas_obrigatorias") or case.get("ferramentas_proibidas"):
        checks["ferramentas"] = {"ok": not missing and not forbidden,
                                 "detalhe": "; ".join(filter(None, [
                                     missing and f"não chamou {missing}", forbidden and f"chamou {forbidden}"]))}

    if case.get("deve_conter"):
        absent = []
        for item in case["deve_conter"]:
            options = item if isinstance(item, list) else [item]
            if not any(_contains(final, o) for o in options):
                absent.append(" ou ".join(options))
        checks["deve_conter"] = {"ok": not absent, "detalhe": absent and f"faltou {absent}"}

    if case.get("nao_deve_conter"):
        present = [t for t in case["nao_deve_conter"] if _contains(answers, t)]
        checks["nao_deve_conter"] = {"ok": not present, "detalhe": present and f"apareceu {present}"}

    # Todo valor em R$ da resposta precisa existir nos dados consultados, no prompt ou na fala do cliente.
    allowed = known_numbers(tool_output, system_prompt, user_text)
    untraced = sorted(v for v in money_values(answers) if v not in allowed)
    checks["valores_rastreaveis"] = {"ok": not untraced,
                                     "detalhe": untraced and f"R$ sem origem: {untraced}"}

    # Cada turno: protocolo citado precisa ter vindo de ferramenta; "registrei/encaminhei" precisa de execução.
    unbacked, seen = [], []
    for t in turns:
        seen += [(c["nome"], c["resultado"]) for c in t["ferramentas"]]
        unbacked += unbacked_actions(t["resposta"], seen)
    checks["acoes_rastreaveis"] = {"ok": not unbacked, "detalhe": unbacked and f"sem execução: {unbacked}"}

    claims = popularity_claims(answers)
    checks["sem_popularidade"] = {"ok": not claims, "detalhe": claims and f"afirmou {claims}"}

    leaked = [n for n in TOOL_NAMES + ["produto_id", "parcelamento_maximo"] if n in answers]
    checks["sem_vazamento_tecnico"] = {"ok": not leaked, "detalhe": leaked and f"mostrou {leaked}"}
    return checks


# ----------------------------------------------------------------------
# Juiz LLM
# ----------------------------------------------------------------------
JUDGE_RETRIES = 4
JUDGE_WAIT = 20  # segundos; cresce a cada tentativa (limite por minuto do plano gratuito)

JUDGE_PROMPT = """Você avalia um agente de atendimento de uma loja de instrumentos musicais.
Receberá a conversa (com os resultados das ferramentas que o agente consultou) e um critério.
Julgue SOMENTE pelo critério, pelos dados oficiais da loja e pelos resultados das ferramentas — não por conhecimento externo.
Responda apenas com JSON: {"aprovado": true|false, "motivo": "uma frase"}"""


def store_reference(system_prompt: str) -> str:
    """Bloco "Informações da loja" do prompt (endereço, telefone, horário, frete local): o agente responde
    isso sem ferramenta, então o juiz precisa da mesma referência para conferir."""
    start = system_prompt.find("# Informações da loja")
    end = system_prompt.find("# Catálogo", start)
    return system_prompt[start:end].strip() if start >= 0 else ""


def judge(llm: LLMClient, model: str, case: dict, turns: list[dict], reference: str = "") -> dict:
    provider = next(p for p in llm.providers if model in p.models)
    convo = []
    for t in turns:
        convo.append(f"CLIENTE: {t['usuario']}")
        for c in t["ferramentas"]:
            convo.append(f"[ferramenta {c['nome']}({json.dumps(c['argumentos'], ensure_ascii=False)}) -> {c['resultado'][:6000]}]")
        convo.append(f"AGENTE: {t['resposta']}")
    user = (f"CRITÉRIO: {case['criterio']}\n\nDADOS OFICIAIS DA LOJA (o agente os conhece):\n{reference}"
            f"\n\nCONVERSA:\n" + "\n".join(convo))
    extra = {"reasoning_effort": provider.reasoning_effort} if provider.reasoning_effort else {}
    for attempt in range(JUDGE_RETRIES):
        try:
            resp = llm.clients[provider.name].chat.completions.create(
                model=model, temperature=0,
                messages=[{"role": "system", "content": JUDGE_PROMPT}, {"role": "user", "content": user}], **extra,
            )
            break
        except openai.RateLimitError:
            if attempt == JUDGE_RETRIES - 1:
                raise
            time.sleep(JUDGE_WAIT * (attempt + 1))
    raw = resp.choices[0].message.content or ""
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    try:
        data = json.loads(match.group(0)) if match else {}
        return {"ok": bool(data.get("aprovado")), "detalhe": data.get("motivo", ""), "modelo": model}
    except json.JSONDecodeError:
        return {"ok": None, "detalhe": f"resposta do juiz ilegível: {raw[:200]}", "modelo": model}


# ----------------------------------------------------------------------
# Execução
# ----------------------------------------------------------------------
def pinned_client(model: str | None) -> LLMClient:
    llm = LLMClient(config.get_settings())
    if model:
        owner = next((p for p in llm.providers if model in p.models), None)
        if not owner:
            raise SystemExit(f"Modelo {model} não está em LLM_MODELS nem em LLM_FALLBACK_MODELS do .env.")
        llm.providers = [replace(owner, models=[model])]
    return llm


def run_case(case: dict, llm: LLMClient, store: Store, pause: float) -> dict:
    agent = Agent(store=store, llm=llm)
    usage_start = len(llm.usage)
    turns = []
    wall = 0.0  # tempo que o cliente espera, incluindo tentativas que falharam e o fallback
    for i, text in enumerate(case["mensagens"]):
        if i:
            time.sleep(pause)
        started = time.perf_counter()
        reply = agent.reply(text)
        wall += time.perf_counter() - started
        turns.append({
            "usuario": text, "resposta": reply.text, "modelo": reply.model, "reescrita": reply.rewritten,
            "ferramentas": [{"nome": c.name, "argumentos": c.arguments, "resultado": c.result} for c in reply.tool_calls],
        })
    usage = llm.usage[usage_start:]
    return {
        "id": case["id"], "categoria": case["categoria"], "turnos": turns,
        "chamadas_llm": len(usage),
        "segundos": round(wall, 2),
        "tokens_entrada": sum(u["tokens_entrada"] for u in usage),
        "tokens_saida": sum(u["tokens_saida"] for u in usage),
        "sem_resposta": any(t["modelo"] is None for t in turns),
    }


def _int(v: float) -> str:
    return f"{v:,.0f}".replace(",", ".")


def summarize(results: list[dict], label: str, judge_model: str | None) -> str:
    def passed(r):  # ok None = não avaliado (ex.: juiz sem cota): não aprova nem reprova
        return not r["sem_resposta"] and all(c["ok"] is not False for c in r["checagens"].values())

    n = len(results)
    ok = sum(passed(r) for r in results)
    reps = max(r.get("rodada", 1) for r in results)
    n_cases = len({r["id"] for r in results})
    lines = [f"# Avaliação — {label}", "",
             f"_Data de referência do agente: {config.now():%d/%m/%Y %H:%M} · {n_cases} casos"
             + (f" × {reps} rodadas" if reps > 1 else "") + f" · juiz: {judge_model or 'desligado'}_", "",
             f"**Aprovados: {ok}/{n} ({ok / n:.0%})**", ""]
    answered = [r for r in results if not r["sem_resposta"]]
    if len(answered) < n:
        ok_answered = sum(passed(r) for r in answered)
        lines += [f"Sem resposta por cota/erro: {n - len(answered)} · aprovados entre os respondidos: "
                  f"{ok_answered}/{len(answered)} ({ok_answered / max(len(answered), 1):.0%})", ""]
    if reps > 1:
        by_case = defaultdict(list)
        for r in answered:  # rodada sem resposta (cota) não conta como instabilidade
            by_case[r["id"]].append(passed(r))
        unstable = {k: v for k, v in by_case.items() if 0 < sum(v) < len(v)}
        always_bad = [k for k, v in by_case.items() if not any(v)]
        lines += [f"Entre as rodadas respondidas — casos sempre aprovados: {sum(all(v) for v in by_case.values())}/{len(by_case)} · "
                  f"instáveis (passam em algumas rodadas): {len(unstable)} · sempre reprovados: {len(always_bad)}", ""]
        if unstable or always_bad:
            lines += ["| Caso | Rodadas aprovadas |", "|---|---|"]
            for k, v in sorted({**unstable, **{k: by_case[k] for k in always_bad}}.items(), key=lambda kv: sum(kv[1])):
                lines.append(f"| {k} | {sum(v)}/{len(v)} |")
            lines.append("")

    lines += ["| Categoria | Aprovados |", "|---|---|"]
    by_cat = defaultdict(list)
    for r in results:
        by_cat[r["categoria"]].append(passed(r))
    for cat, vals in by_cat.items():
        lines.append(f"| {cat} | {sum(vals)}/{len(vals)} |")

    lines += ["", "| Checagem | Falhas | Não avaliados |", "|---|---|---|"]
    fails = Counter(name for r in results for name, c in r["checagens"].items() if c["ok"] is False)
    skipped = Counter(name for r in results for name, c in r["checagens"].items() if c["ok"] is None)
    names = sorted({name for r in results for name in r["checagens"]})
    for name in names:
        lines.append(f"| {name} | {fails.get(name, 0)} | {skipped.get(name, 0)} |")

    secs = [r["segundos"] for r in results if r["chamadas_llm"]]
    models = Counter(t["modelo"] for r in results for t in r["turnos"])
    judges = Counter((r["checagens"].get("juiz") or {}).get("modelo") for r in results)
    judges.pop(None, None)
    rewrites = sum(bool(t["reescrita"]) for r in results for t in r["turnos"])
    lines += ["", "| Métrica | Valor |", "|---|---|",
              f"| Tempo de espera por caso (mediana / máximo) | {statistics.median(secs):.1f} s / {max(secs):.1f} s |"
              if secs else "| Tempo | — |",
              f"| Chamadas ao LLM por caso (média) | {statistics.mean(r['chamadas_llm'] for r in results):.1f} |",
              f"| Tokens por caso (média, entrada + saída) | "
              f"{_int(statistics.mean(r['tokens_entrada'] for r in results))} + "
              f"{_int(statistics.mean(r['tokens_saida'] for r in results))} |",
              f"| Respostas reescritas pela verificação final | {rewrites} |",
              f"| Casos sem resposta (cota/erro) | {sum(r['sem_resposta'] for r in results)} |",
              f"| Juiz (casos avaliados) | {', '.join(f'{m} ({c})' for m, c in judges.most_common()) or '—'} |",
              f"| Modelos que responderam | {', '.join(f'{m} ({c})' for m, c in models.most_common())} |"]

    failed = [r for r in results if not passed(r)]
    if failed:
        lines += ["", "## Casos reprovados", ""]
        for r in failed:
            reasons = [f"{k}: {c['detalhe']}" for k, c in r["checagens"].items() if c["ok"] is False]
            if r["sem_resposta"]:
                reasons.insert(0, "sem resposta do modelo")
            tag = f" (rodada {r['rodada']})" if reps > 1 else ""
            lines.append(f"<details><summary><b>{r['id']}</b>{tag} — {'; '.join(reasons)}</summary>\n")
            for t in r["turnos"]:
                lines.append(f"**Cliente:** {t['usuario']}\n")
                if t["ferramentas"]:
                    lines.append("Ferramentas: " + ", ".join(f"`{c['nome']}`" for c in t["ferramentas"]) + "\n")
                lines.append(f"**Clave:** {t['resposta']}\n")
            lines.append("</details>\n")
    return "\n".join(lines) + "\n"


def compare(labels: list[str]) -> str:
    """Tabela lado a lado de resultados já salvos (um rótulo por modelo)."""
    lines = ["# Comparação de modelos", "",
             "Falta de cota não é erro do modelo: as taxas são calculadas só sobre as execuções que tiveram resposta.", "",
             "| Rótulo | Modelo(s) | Execuções | Sem resposta (cota) | Aprovadas / respondidas | Valores sem origem "
             "| Ações sem execução | Reprovado pelo juiz | Casos instáveis | Tempo (mediana) | Tokens/caso |",
             "|---|---|---|---|---|---|---|---|---|---|---|"]
    for label in labels:
        results = [r for r in json.loads((RESULTS_DIR / f"{label}.json").read_text(encoding="utf-8"))]
        total, missing = len(results), sum(r["sem_resposta"] for r in results)
        results = [r for r in results if not r["sem_resposta"]]
        ok = [not r["sem_resposta"] and all(c["ok"] is not False for c in r["checagens"].values()) for r in results]
        fail = lambda name: sum(r["checagens"].get(name, {}).get("ok") is False for r in results)
        by_case = defaultdict(list)
        for r, o in zip(results, ok):
            by_case[r["id"]].append(o)
        unstable = sum(0 < sum(v) < len(v) for v in by_case.values())
        models = Counter(t["modelo"] for r in results for t in r["turnos"] if t["modelo"])
        secs = [r["segundos"] for r in results if r["chamadas_llm"]]
        tokens = statistics.mean(r["tokens_entrada"] + r["tokens_saida"] for r in results)
        lines.append(
            f"| {label} | {', '.join(m for m, _ in models.most_common(3))} | {total} | {missing} | "
            f"{sum(ok)}/{len(results)} ({sum(ok) / len(results):.0%}) | "
            f"{fail('valores_rastreaveis')} | {fail('acoes_rastreaveis')} | {fail('juiz')} | {unstable} | "
            f"{statistics.median(secs):.1f} s | {_int(tokens)} |")
    return "\n".join(lines) + "\n"


def _save(path: Path, results: list[dict]) -> None:
    path.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Avaliação automatizada do agente")
    parser.add_argument("--modelo", help="fixa um único modelo do .env (sem fallback), para comparar modelos")
    parser.add_argument("--juiz", help="modelo do .env usado como juiz LLM (omitir = só checagens em código)")
    parser.add_argument("--casos", help="ids separados por vírgula (padrão: todos)")
    parser.add_argument("--rotulo", help="nome dos arquivos de resultado (padrão: o modelo)")
    parser.add_argument("--rejulgar", metavar="ROTULO",
                        help="reaproveita as respostas de um resultado salvo e refaz só as checagens e o juiz")
    parser.add_argument("--refazer-juiz", action="store_true", help="com --rejulgar, julga de novo também os já avaliados")
    parser.add_argument("--repeticoes", type=int, default=1, help="roda cada caso N vezes (mede estabilidade)")
    parser.add_argument("--continuar", action="store_true",
                        help="retoma um resultado parcial do mesmo rótulo (útil quando a cota acaba no meio)")
    parser.add_argument("--esperar-cota", type=int, default=0, metavar="SEG",
                        help="com --modelo: no limite por minuto, espera SEG segundos e tenta de novo")
    parser.add_argument("--comparar", help="rótulos já salvos, separados por vírgula: gera comparacao.md")
    parser.add_argument("--pausa", type=float, default=4.0, help="segundos entre chamadas (cota do plano gratuito)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING, format="[%(levelname)s] %(message)s")

    if args.comparar:
        out = RESULTS_DIR / "comparacao.md"
        out.write_text(compare(args.comparar.split(",")), encoding="utf-8")
        print(out.read_text(encoding="utf-8"))
        return

    cases = json.loads(CASES_FILE.read_text(encoding="utf-8"))
    if args.casos:
        wanted = set(args.casos.split(","))
        cases = [c for c in cases if c["id"] in wanted]

    llm = None if args.rejulgar else pinned_client(args.modelo)
    if llm and args.modelo and args.esperar_cota:
        llm.rate_limit_wait = args.esperar_cota
    judge_llm = pinned_client(None) if args.juiz else None
    store = Store()
    label = args.rotulo or args.rejulgar or (args.modelo or "padrao").replace("/", "_")
    saved = {}
    if args.rejulgar:
        saved = {(r["id"], r.get("rodada", 1)): r
                 for r in json.loads((RESULTS_DIR / f"{args.rejulgar}.json").read_text(encoding="utf-8"))}
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    out_json = RESULTS_DIR / f"{label}.json"
    done = {}
    if args.continuar and out_json.exists():
        # Retoma: mantém o que já tem resposta e refaz o que ficou sem (cota esgotada no meio).
        done = {(r["id"], r.get("rodada", 1)): r for r in json.loads(out_json.read_text(encoding="utf-8"))
                if not r["sem_resposta"]}
    if args.rejulgar:
        jobs = [(c, k[1]) for c in cases for k in sorted(saved) if k[0] == c["id"]]
    else:
        jobs = [(c, rep) for rep in range(1, args.repeticoes + 1) for c in cases]
    # Encaminhamentos da avaliação não se misturam aos casos reais.
    tools.HANDOFF_FILE = RESULTS_DIR / f".encaminhamentos_{label}.jsonl"
    if not args.continuar:
        tools.HANDOFF_FILE.unlink(missing_ok=True)
    system_prompt = build_system_prompt(store, config.now())

    results = []
    for i, (case, rep) in enumerate(jobs, 1):
        key = (case["id"], rep)
        tag = f" #{rep}" if rep > 1 or args.repeticoes > 1 else ""
        print(f"[{i}/{len(jobs)}] {case['id']}{tag}", end=" ", flush=True)
        if key in done:
            print("(já feito)")
            results.append(done[key])
            continue
        if i > 1 and not args.rejulgar:
            time.sleep(args.pausa)
        result = saved[key] if args.rejulgar else {**run_case(case, llm, store, args.pausa), "rodada": rep}
        already = (result.get("checagens", {}).get("juiz") or {}).get("ok") is not None
        previous_judge = result.get("checagens", {}).get("juiz") if args.rejulgar else None
        result["checagens"] = check_case(case, result["turnos"], system_prompt)
        if already and previous_judge and not args.refazer_juiz:
            result["checagens"]["juiz"] = previous_judge  # rejulgar só completa o que faltou
        elif judge_llm and case.get("criterio") and not result["sem_resposta"]:
            time.sleep(args.pausa)
            try:
                result["checagens"]["juiz"] = judge(judge_llm, args.juiz, case, result["turnos"], store_reference(system_prompt))
            except Exception as e:  # o juiz não derruba a avaliação
                msg = (getattr(e, "message", "") or str(e)).split(" in organization")[0]
                result["checagens"]["juiz"] = {"ok": None, "detalhe": f"juiz indisponível: {type(e).__name__} {msg[:160]}"}
        bad = [k for k, c in result["checagens"].items() if c["ok"] is False]
        print("ok" if not bad and not result["sem_resposta"] else f"FALHOU {bad or 'sem resposta'}")
        results.append(result)
        _save(out_json, results + [r for k, r in done.items() if k not in {(x["id"], x.get("rodada", 1)) for x in results}])

    _save(out_json, results)
    report = summarize(results, label, args.juiz)
    (RESULTS_DIR / f"{label}.md").write_text(report, encoding="utf-8")
    print(f"\nRelatório: {RESULTS_DIR / f'{label}.md'}")


if __name__ == "__main__":
    main()
