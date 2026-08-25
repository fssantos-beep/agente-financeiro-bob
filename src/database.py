"""Acesso ao MySQL e operações restritas ao usuário autenticado."""
import os
from decimal import Decimal

import bcrypt
import mysql.connector
from dotenv import load_dotenv

# Mantém credenciais fora do código e disponíveis para todas as operações abaixo.
load_dotenv()

DB_KEYS = ("DB_HOST", "DB_PORT", "DB_USER", "DB_PASSWORD", "DB_NAME")


def config_error():
    # Centraliza o diagnóstico para evitar mensagens diferentes em cada endpoint.
    missing = [key for key in DB_KEYS if not os.getenv(key)]
    return f"Variáveis ausentes no .env: {', '.join(missing)}" if missing else None


def get_connection():
    # A conexão é aberta por operação e sempre fechada no bloco finally correspondente.
    error = config_error()
    if error:
        raise RuntimeError(error)
    return mysql.connector.connect(
        host=os.environ["DB_HOST"], port=int(os.environ["DB_PORT"]),
        user=os.environ["DB_USER"], password=os.environ["DB_PASSWORD"],
        database=os.environ["DB_NAME"],
        charset="utf8mb4",
    )


def create_user(name, email, password):
    # O banco recebe apenas o hash; a senha original nunca é persistida.
    password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "INSERT INTO usuarios (nome, email, senha_hash) VALUES (%s, %s, %s)",
                (name.strip(), email.strip().lower(), password_hash),
            )
        conn.commit()
    except mysql.connector.IntegrityError as error:
        conn.rollback()
        if error.errno == 1062:
            # O índice único de e-mail é a última barreira contra cadastros duplicados.
            raise ValueError("Este e-mail já está cadastrado.") from error
        raise
    finally:
        conn.close()


def authenticate(email, password):
    # Busca somente o usuário do e-mail informado e compara o hash com bcrypt.
    conn = get_connection()
    try:
        with conn.cursor(dictionary=True) as cursor:
            cursor.execute("SELECT id, nome, email, senha_hash FROM usuarios WHERE email = %s", (email.strip().lower(),))
            user = cursor.fetchone()
        if user and bcrypt.checkpw(password.encode(), user["senha_hash"].encode()):
            # Não deixa o hash seguir para a camada de API ou para a sessão.
            user.pop("senha_hash")
            return user
        return None
    finally:
        conn.close()


def get_financial_profile(user_id):
    # O filtro por usuario_id impede que um perfil seja lido por outra conta.
    conn = get_connection()
    try:
        with conn.cursor(dictionary=True) as cursor:
            cursor.execute("SELECT * FROM perfil_financeiro WHERE usuario_id = %s", (user_id,))
            return cursor.fetchone()
    finally:
        conn.close()


def save_financial_profile(user_id, profile):
    # A lista explícita evita que campos inesperados enviados pela API entrem na query.
    columns = [
        "renda_mensal", "gastos_moradia", "gastos_alimentacao", "gastos_transporte",
        "gastos_educacao", "gastos_saude", "gastos_lazer", "gastos_contas", "outros_gastos",
        "possui_dividas", "valor_dividas", "juros_divida", "reserva_emergencia",
        "possui_investimentos", "valor_investido", "tipos_investimentos", "objetivo_financeiro",
        "objetivo_outro", "tolerancia_risco", "valor_disponivel_investimento",
    ]
    values = [profile.get(column) for column in columns]
    update = ", ".join(f"{column} = VALUES({column})" for column in columns)
    query = f"""
        INSERT INTO perfil_financeiro (usuario_id, {', '.join(columns)})
        VALUES (%s, {', '.join(['%s'] * len(columns))})
        ON DUPLICATE KEY UPDATE {update}
    """
    # O upsert cria o primeiro perfil e atualiza os próximos sem duplicar o usuário.
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(query, [user_id, *values])
        conn.commit()
    finally:
        conn.close()


def profile_for_ai(user, profile):
    # Resume somente o contexto que ajuda o Bob, em vez de enviar o registro inteiro.
    expenses = sum(Decimal(str(profile[key])) for key in (
        "gastos_moradia", "gastos_alimentacao", "gastos_transporte", "gastos_educacao",
        "gastos_saude", "gastos_lazer", "gastos_contas", "outros_gastos",
    ))
    income = Decimal(str(profile["renda_mensal"]))
    available = max(Decimal("0"), income - expenses)
    investments = None
    if profile["possui_investimentos"]:
        investments = {
            "tipos": profile.get("tipos_investimentos"),
            "valor_investido": float(profile["valor_investido"]),
        }

    return {
        "nome": user["nome"], "renda_mensal": float(income), "gastos_mensais": float(expenses),
        "reserva_emergencia": float(profile["reserva_emergencia"]),
        "possui_dividas": bool(profile["possui_dividas"]), "dividas": float(profile["valor_dividas"]),
        "valor_disponivel_investimento": float(available), "objetivo_financeiro": profile["objetivo_financeiro"],
        "objetivo_outro": profile.get("objetivo_outro"), "tolerancia_risco": profile["tolerancia_risco"],
        "investimentos": investments,
    }
