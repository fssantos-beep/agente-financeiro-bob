import json
import os
import re
from decimal import Decimal

import requests
import streamlit as st

from database import authenticate, config_error, create_user, get_financial_profile, profile_for_ai, save_financial_profile

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "gpt-oss:latest"
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
EXPENSE_FIELDS = {"gastos_moradia": "Moradia/aluguel", "gastos_alimentacao": "Alimentação", "gastos_transporte": "Transporte", "gastos_contas": "Contas básicas", "gastos_educacao": "Educação", "gastos_saude": "Saúde", "gastos_lazer": "Lazer", "outros_gastos": "Outros gastos"}
OBJECTIVES = {"Criar uma reserva de emergência": "reserva_de_emergencia", "Comprar um imóvel": "comprar_imovel", "Comprar um veículo": "comprar_veiculo", "Viajar": "viajar", "Aposentadoria": "aposentadoria", "Aumentar patrimônio": "aumentar_patrimonio", "Outro": "outro"}


def brl(value):
    return f"R$ {float(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def load_products():
    with open(os.path.join(DATA_DIR, "produtos_financeiros.json"), encoding="utf-8") as file:
        return json.load(file)


def build_prompt(profile, products):
    risks = {"conservador": ["baixo"], "moderado": ["baixo", "medio"], "arrojado": ["baixo", "medio", "alto"]}[profile["tolerancia_risco"]]
    product_text = "\n".join(f"- {p['nome']} ({p['risco']}) — {p['rentabilidade']}" for p in products if p["risco"] in risks)
    return f"""Você é Bob, assistente financeiro educacional. Nunca invente dados e não substitui orientação profissional.
Cliente: {profile['nome']}; renda: {brl(profile['renda_mensal'])}; gastos: {brl(profile['gastos_mensais'])}; disponível: {brl(profile['valor_disponivel_investimento'])}; reserva: {brl(profile['reserva_emergencia'])}; dívidas: {brl(profile['dividas'])}; objetivo: {profile['objetivo_financeiro']}; risco declarado: {profile['tolerancia_risco']}.
Produtos compatíveis:\n{product_text}"""


def chat(message, context, history):
    payload = {"model": MODEL, "messages": [{"role": "system", "content": context}] + history + [{"role": "user", "content": message}], "stream": True}
    try:
        with requests.post(OLLAMA_URL, json=payload, stream=True, timeout=300) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if line:
                    yield json.loads(line).get("message", {}).get("content", "")
    except requests.RequestException as error:
        yield f"Não foi possível conectar ao Ollama local. Inicie o serviço para conversar com o Bob. Erro: {error}"


def metrics(profile):
    expenses = sum(Decimal(str(profile[key])) for key in EXPENSE_FIELDS)
    income = Decimal(str(profile["renda_mensal"]))
    return expenses, max(Decimal("0"), income - expenses), (expenses / income * 100 if income else Decimal("0")), (Decimal(str(profile["reserva_emergencia"])) / expenses if expenses else Decimal("0"))


def logout():
    for key in list(st.session_state):
        del st.session_state[key]
    st.rerun()


def login_page():
    st.title("🤖 Bob")
    st.caption("Seu assistente financeiro pessoal")
    login, signup = st.tabs(["Entrar", "Criar conta"])
    with login:
        with st.form("login_form"):
            email = st.text_input("E-mail")
            password = st.text_input("Senha", type="password")
            submitted = st.form_submit_button("Entrar", type="primary")
        if submitted:
            if not email or not password:
                st.error("Informe e-mail e senha.")
            else:
                try:
                    user = authenticate(email, password)
                    if user:
                        st.session_state.user = user
                        st.session_state.msgs = [{"role": "assistant", "content": f"Olá, {user['nome']}! Como posso ajudar?"}]
                        st.rerun()
                    st.error("E-mail ou senha inválidos.")
                except Exception as error:
                    st.error(f"Não foi possível entrar: {error}")
    with signup:
        with st.form("signup_form"):
            name = st.text_input("Nome")
            email = st.text_input("E-mail", key="signup_email")
            password = st.text_input("Senha", type="password", key="signup_password", help="Use pelo menos 8 caracteres.")
            confirmation = st.text_input("Confirmação da senha", type="password")
            submitted = st.form_submit_button("Criar conta", type="primary")
        if submitted:
            if not all((name.strip(), email.strip(), password, confirmation)):
                st.error("Preencha todos os campos.")
            elif not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
                st.error("Informe um e-mail válido.")
            elif len(password) < 8:
                st.error("A senha deve ter pelo menos 8 caracteres.")
            elif password != confirmation:
                st.error("A confirmação da senha não corresponde.")
            else:
                try:
                    create_user(name, email, password)
                    st.success("Conta criada. Agora entre com seu e-mail e senha.")
                except ValueError as error:
                    st.error(str(error))
                except Exception as error:
                    st.error(f"Não foi possível criar a conta: {error}")


def financial_profile_page(user, existing):
    st.title("Perfil financeiro")
    st.write("Essas informações orientam seus cálculos e futuras recomendações do Bob.")
    existing = existing or {}
    get = lambda field: float(existing.get(field) or 0)
    with st.form("financial_profile"):
        st.subheader("Renda e gastos mensais")
        income = st.number_input("Renda mensal líquida (R$)", min_value=0.0, value=get("renda_mensal"), step=100.0)
        entries, columns = {}, st.columns(2)
        for index, (field, label) in enumerate(EXPENSE_FIELDS.items()):
            with columns[index % 2]:
                entries[field] = st.number_input(f"{label} (R$)", min_value=0.0, value=get(field), step=50.0)
        st.subheader("Dívidas, reserva e investimentos")
        has_debt = st.checkbox("Possuo dívidas", value=bool(existing.get("possui_dividas")))
        debt_value = st.number_input("Valor aproximado das dívidas (R$)", min_value=0.0, value=get("valor_dividas"), step=100.0, disabled=not has_debt)
        debt_type = st.text_input("Tipo da dívida (opcional)", value=existing.get("tipo_divida") or "", disabled=not has_debt)
        debt_interest = st.number_input("Taxa de juros mensal aproximada (%)", min_value=0.0, max_value=100.0, value=get("juros_divida"), step=0.1, disabled=not has_debt)
        emergency = st.number_input("Valor guardado para emergências (R$)", min_value=0.0, value=get("reserva_emergencia"), step=100.0)
        has_investments = st.checkbox("Possuo investimentos", value=bool(existing.get("possui_investimentos")))
        invested = st.number_input("Valor aproximado investido (R$)", min_value=0.0, value=get("valor_investido"), step=100.0, disabled=not has_investments)
        investment_types = st.text_input("Tipos de investimentos (opcional)", value=existing.get("tipos_investimentos") or "", disabled=not has_investments)
        st.subheader("Objetivos e tolerância a risco")
        labels = list(OBJECTIVES)
        current = {value: label for label, value in OBJECTIVES.items()}.get(existing.get("objetivo_financeiro"), labels[0])
        objective = st.selectbox("Objetivo principal", labels, index=labels.index(current))
        other = st.text_input("Descreva o outro objetivo", value=existing.get("objetivo_outro") or "", disabled=objective != "Outro")
        risks = ["conservador", "moderado", "arrojado"]
        risk = st.selectbox("Tolerância a risco", risks, index=risks.index(existing.get("tolerancia_risco", "moderado")), help="Uma indicação inicial; poderá ser refinada por questionário futuro.")
        submitted = st.form_submit_button("Salvar perfil", type="primary")
    if submitted:
        if income <= 0:
            st.error("Informe uma renda mensal maior que zero.")
        elif has_debt and debt_value <= 0:
            st.error("Informe o valor das dívidas ou desmarque essa opção.")
        elif objective == "Outro" and not other.strip():
            st.error("Descreva o seu objetivo financeiro.")
        else:
            profile = {**entries, "renda_mensal": income, "possui_dividas": has_debt, "valor_dividas": debt_value if has_debt else 0, "tipo_divida": debt_type.strip() or None if has_debt else None, "juros_divida": debt_interest if has_debt else None, "reserva_emergencia": emergency, "possui_investimentos": has_investments, "valor_investido": invested if has_investments else 0, "tipos_investimentos": investment_types.strip() or None if has_investments else None, "objetivo_financeiro": OBJECTIVES[objective], "objetivo_outro": other.strip() or None if objective == "Outro" else None, "tolerancia_risco": risk, "valor_disponivel_investimento": max(0, income - sum(entries.values()))}
            try:
                save_financial_profile(user["id"], profile)
                st.success("Perfil financeiro salvo com segurança.")
                st.rerun()
            except Exception as error:
                st.error(f"Não foi possível salvar o perfil: {error}")


def dashboard(user, profile):
    expenses, available, committed, emergency_months = metrics(profile)
    st.title(f"Olá, {user['nome']} 👋")
    st.caption("Resumo do seu perfil financeiro")
    cols = st.columns(4)
    for column, label, value in zip(cols, ["Renda mensal", "Gastos mensais", "Disponível mensalmente", "Renda comprometida"], [brl(profile["renda_mensal"]), brl(expenses), brl(available), f"{committed:.1f}%"]):
        column.metric(label, value)
    st.info(f"Sua reserva cobre aproximadamente **{emergency_months:.1f} meses** dos gastos atuais.")
    with st.expander("Editar perfil financeiro"):
        financial_profile_page(user, profile)
    st.subheader("Converse com o Bob")
    for message in st.session_state.msgs:
        with st.chat_message(message["role"]): st.markdown(message["content"])
    if prompt := st.chat_input("Digite sua pergunta financeira..."):
        context = build_prompt(profile_for_ai(user, profile), load_products())
        st.session_state.msgs.append({"role": "user", "content": prompt})
        with st.chat_message("user"): st.markdown(prompt)
        with st.chat_message("assistant"):
            place, response = st.empty(), ""
            for token in chat(prompt, context, st.session_state.msgs[-6:]):
                response += token; place.markdown(response)
        st.session_state.msgs.append({"role": "assistant", "content": response})


st.set_page_config(page_title="Bob | Assistente Financeiro", page_icon="🤖", layout="wide")
error = config_error()
if error:
    st.error(f"Banco de dados não configurado. {error}. Copie .env.example para .env e configure o MySQL.")
    st.stop()
if "user" not in st.session_state:
    login_page()
else:
    with st.sidebar:
        st.title("🤖 Bob"); st.write(f"Conectado como **{st.session_state.user['nome']}**")
        if st.button("Sair", use_container_width=True): logout()
    try:
        profile = get_financial_profile(st.session_state.user["id"])
        financial_profile_page(st.session_state.user, None) if profile is None else dashboard(st.session_state.user, profile)
    except Exception as error:
        st.error(f"Erro ao acessar seus dados: {error}")
