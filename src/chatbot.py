"""Regras de negócio compartilhadas pelo backend do Bob."""
import json
import os
from decimal import Decimal
from pathlib import Path
from typing import Iterator

import requests

# A URL e o modelo continuam configuráveis pelo .env para manter o Ollama local separado.
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/chat")
MODEL = os.getenv("OLLAMA_MODEL", "gpt-oss:latest")
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
EXPENSE_FIELDS = {"gastos_moradia": "Moradia/aluguel", "gastos_alimentacao": "Alimentação", "gastos_transporte": "Transporte", "gastos_contas": "Contas básicas", "gastos_educacao": "Educação", "gastos_saude": "Saúde", "gastos_lazer": "Lazer", "outros_gastos": "Outros gastos"}
OBJECTIVES = {"Criar uma reserva de emergência": "reserva_de_emergencia", "Comprar um imóvel": "comprar_imovel", "Comprar um veículo": "comprar_veiculo", "Viajar": "viajar", "Aposentadoria": "aposentadoria", "Aumentar patrimônio": "aumentar_patrimonio", "Outro": "outro"}

def brl(value):
    return f"R$ {float(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def load_products():
    # O catálogo vem do JSON do projeto; o Bob não cria produtos ou rentabilidades.
    with (DATA_DIR / "produtos_financeiros.json").open(encoding="utf-8") as file: return json.load(file)

def build_prompt(profile, products):
    # Cada perfil só recebe produtos dentro do risco declarado pelo próprio usuário.
    risks = {
        "conservador": ["baixo"],
        "moderado": ["baixo", "medio"],
        "arrojado": ["baixo", "medio", "alto"],
    }[profile["tolerancia_risco"]]
    objective_name = next(
        (name for name, value in OBJECTIVES.items() if value == profile["objetivo_financeiro"]),
        profile["objetivo_financeiro"],
    )
    product_text = "\n".join(
        f"- {product['nome']} | risco: {product['risco']} | rentabilidade: {product['rentabilidade']} "
        f"| aporte mínimo: {brl(product['aporte_minimo'])} | indicado para: {product['indicado_para']}"
        for product in products
        if product["risco"] in risks
    )
    debt_text = brl(profile["dividas"]) if profile["possui_dividas"] else "Não possui dívidas informadas"
    investment = profile["investimentos"]
    investment_text = (
        f"- Tipo(s): {investment['tipos'] or 'não informado'}\n"
        f"- Valor investido: {brl(investment['valor_investido'])}"
        if investment
        else "Não possui investimentos informados"
    )
    objective_detail = (
        f"\nDetalhamento do objetivo: {profile['objetivo_outro']}"
        if profile["objetivo_financeiro"] == "outro" and profile["objetivo_outro"]
        else ""
    )
    return f"""Você é Bob, assistente financeiro educacional. Responda diretamente à pergunta, em português do Brasil, com linguagem natural, clara e 
    conversacional. Seja conciso; não use tabelas grandes nem repita informações.

Baseie recomendações apenas no perfil abaixo e nos produtos fornecidos. Ao sugerir um produto, 
explique brevemente por que ele é compatível com o objetivo, risco e situação financeira. Não invente características, taxas, rentabilidades, 
liquidez ou outras informações. Se faltarem dados para recomendar algo, diga exatamente o que falta ou faça uma única pergunta objetiva.
Não responda automaticamente que o usuário deve procurar um consultor; ofereça ajuda útil dentro deste escopo. Deixe claro, quando fizer recomendação,
que ela se baseia nos dados informados e nos produtos disponíveis.

Perfil do cliente:
- Nome: {profile['nome']}
- Renda mensal: {brl(profile['renda_mensal'])}
- Gastos mensais: {brl(profile['gastos_mensais'])}
- Valor mensal disponível: {brl(profile['valor_disponivel_investimento'])}
- Reserva de emergência: {brl(profile['reserva_emergencia'])}
- Dívidas: {debt_text}
- Objetivo financeiro: {objective_name}{objective_detail}
- Tolerância a risco: {profile['tolerancia_risco']}
- Investimentos atuais:
{investment_text}

Produtos compatíveis disponíveis no sistema:
{product_text}"""

def chat(message: str, context: str, history: list[dict]) -> Iterator[str]:
    # O backend intermedeia o stream para que o navegador nunca acesse o Ollama diretamente.
    payload = {"model": MODEL, "messages": [{"role": "system", "content": context}] + history + [{"role": "user", "content": message}], "stream": True}
    try:
        with requests.post(OLLAMA_URL, json=payload, stream=True, timeout=300) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if line: yield json.loads(line).get("message", {}).get("content", "")
    except requests.RequestException:
        # Uma indisponibilidade local não derruba a API nem expõe detalhes da infraestrutura.
        yield "Não foi possível conectar ao Ollama local. Inicie o serviço para conversar com o Bob."

def metrics(profile):
    # Os mesmos calculos alimentam o dashboard e evitam desentendimento com o contexto do Bob.
    expenses = sum(Decimal(str(profile[key])) for key in EXPENSE_FIELDS)
    income = Decimal(str(profile["renda_mensal"]))
    return expenses, max(Decimal("0"), income - expenses), (expenses / income * 100 if income else Decimal("0")), (Decimal(str(profile["reserva_emergencia"])) / expenses if expenses else Decimal("0"))
