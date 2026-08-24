import streamlit as st
import pandas as pd
import json
import requests
import os
import re

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "gpt-oss"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "..", "data")

def brl(v):
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

# ======== Carrega perfil e produtos ========
def load_data(perfil_file):
    try:
        perfil = json.load(open(os.path.join(DATA_DIR, "perfis", perfil_file), encoding="utf-8"))
        produtos = json.load(open(os.path.join(DATA_DIR, "produtos_financeiros.json"), encoding="utf-8"))
        trans = pd.read_csv(os.path.join(DATA_DIR, "transacoes.csv")).tail(5).to_dict("records")
        return perfil, produtos, trans
    except Exception as e:
        st.error(f"Erro ao carregar dados: {e}")
        st.stop()

# ======== Prompt ========
def build_prompt(perfil, produtos, trans):
    tx = "\n".join([f"- {t['data']}: {t['descricao']} - {brl(t['valor'])}" for t in trans])

    riscos = {
        "conservador": ["baixo"],
        "moderado": ["baixo","medio"],
        "arrojado": ["baixo","medio","alto"]
    }.get(perfil["perfil_investidor"], ["baixo","medio"])

    prod = "\n".join([
        f"- {p['nome']} ({p['risco']}) - {p['rentabilidade']}"
        for p in produtos if p["risco"] in riscos
    ])
    return f"""
Voce é Bob, assistente financeiro.

Regras:
- Nunca invente dados
- Use apenas o contexto
- Se faltar informação, peça mais detalhes

Cliente:
Nome: {perfil['nome']}
Perfil: {perfil['perfil_investidor']}
Renda: {brl(perfil['renda_mensal'])}
Reserva: {brl(perfil['reserva_emergencia_atual'])}

Transacoes:
{tx}

Produtos:
{prod}
"""

# ========= LLM =========
def chat(msg, ctx, hist):
    payload = {
        "model": MODEL,
        "messages": [{"role":"system","content":ctx}] + hist + [{"role":"user","content":msg}],
        "stream": True
    }

    try:
        with requests.post(OLLAMA_URL, json=payload, stream=True) as r:
            for line in r.iter_lines():
                if line:
                    data = json.loads(line)
                    yield data.get("message", {}).get("content", "")
    except Exception as e:
        yield f"Erro: {e}"

# ========= Valida a resposta =========
def validate(resp, perfil):
    resp = re.sub(r'\bEstou\b', 'Voce esta', resp)

    if perfil["perfil_investidor"] == "moderado":
        if "acao" in resp.lower() and "recomendo" in resp.lower():
            resp += "\n\n⚠️ Cuidado com renda variável."

    return resp

# ========= Streamlit =========
st.set_page_config(page_title="Bob", page_icon="🤖")
st.title("🤖 Bob")

# Escolha do perfil 
perfis_dir = os.path.join(DATA_DIR, "perfis")
perfis = os.listdir(perfis_dir)
perfil_escolhido = st.selectbox("Escolha o perfil", perfis)

# Reseta o contexto ao trocar o perfil
if "perfil_atual" not in st.session_state:
    st.session_state.perfil_atual = perfil_escolhido

if st.session_state.perfil_atual != perfil_escolhido:
    st.session_state.msgs = []
    st.session_state.perfil_atual = perfil_escolhido

if "msgs" not in st.session_state:
    st.session_state.msgs = [
        {"role":"assistant","content":"Ola! Como posso ajudar?"}
    ]

for m in st.session_state.msgs:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])

if prompt := st.chat_input("Digite..."):
    perfil, produtos, trans = load_data(perfil_escolhido)
    ctx = build_prompt(perfil, produtos, trans)

    st.session_state.msgs.append({"role":"user","content":prompt})

    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        ph = st.empty()
        full = ""

        for tok in chat(prompt, ctx, st.session_state.msgs[-6:]):
            full += tok
            ph.markdown(full)

        full = validate(full, perfil)
        ph.markdown(full)

    st.session_state.msgs.append({"role":"assistant","content":full})
