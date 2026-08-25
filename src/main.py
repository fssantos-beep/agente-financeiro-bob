"""FastAPI do Bob"""
import json
import os
import re
import secrets
from decimal import Decimal
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import FileResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator, model_validator
from starlette.middleware.sessions import SessionMiddleware
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent

# Carrega o .env antes dos módulos que leem a configuração do Ollama e do banco.
load_dotenv(ROOT_DIR / ".env")

from .chatbot import EXPENSE_FIELDS, OBJECTIVES, build_prompt, chat, load_products, metrics
from .database import authenticate, config_error, create_user, get_financial_profile, profile_for_ai, save_financial_profile

# Usa a chave definida no ambiente; caso não exista, uma chave temporária é gerada para a execução local.
app = FastAPI(title="Bob — Assistente Financeiro", version="1.0.0")
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET") or secrets.token_urlsafe(48),
    https_only=os.getenv("COOKIE_SECURE", "false").lower() == "true",
    same_site="lax"
)
app.mount("/static", StaticFiles(directory=ROOT_DIR / "static"), name="static")


class RegisterPayload(BaseModel):
    nome: str = Field(min_length=1, max_length=120)
    email: str
    senha: str = Field(min_length=8, max_length=128)
    confirmacao_senha: str

    @field_validator("email")
    @classmethod
    def valid_email(cls, value):
        # Essa checagem mantém a mesma validação simples do frontend
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
            raise ValueError("Informe um e-mail válido.")
        return value.strip().lower()


class LoginPayload(BaseModel):
    email: str
    senha: str


class ProfilePayload(BaseModel):
    # Pydantic bloqueia valores inválidos antes que eles cheguem ao MySQL.
    renda_mensal: float = Field(gt=0)
    gastos_moradia: float = Field(default=0, ge=0)
    gastos_alimentacao: float = Field(default=0, ge=0)
    gastos_transporte: float = Field(default=0, ge=0)
    gastos_contas: float = Field(default=0, ge=0)
    gastos_educacao: float = Field(default=0, ge=0)
    gastos_saude: float = Field(default=0, ge=0)
    gastos_lazer: float = Field(default=0, ge=0)
    outros_gastos: float = Field(default=0, ge=0)

    possui_dividas: bool = False
    valor_dividas: float = Field(default=0, ge=0)
    juros_divida: float | None = Field(default=None, ge=0, le=100)

    reserva_emergencia: float = Field(default=0, ge=0)
    possui_investimentos: bool = False
    valor_investido: float = Field(default=0, ge=0)
    tipos_investimentos: str | None = Field(default=None, max_length=255)

    objetivo_financeiro: str
    objetivo_outro: str | None = Field(default=None, max_length=255)
    tolerancia_risco: str

    @field_validator("objetivo_financeiro")
    @classmethod
    def valid_objective(cls, value):
        if value not in OBJECTIVES.values():
            raise ValueError("Objetivo financeiro inválido.")
        return value

    @field_validator("tolerancia_risco")
    @classmethod
    def valid_risk(cls, value):
        if value not in ("conservador", "moderado", "arrojado"):
            raise ValueError("Tolerância a risco inválida.")
        return value

    @field_validator("objetivo_outro", "tipos_investimentos")
    @classmethod
    def normalize_optional_text(cls, value):
        return value.strip() or None if value else None

    @model_validator(mode="after")
    def validate_conditional_fields(self):
        if self.objetivo_financeiro == "outro" and not self.objetivo_outro:
            raise ValueError("Descreva o seu objetivo financeiro.")
        return self


class ChatPayload(BaseModel):
    mensagem: str = Field(min_length=1, max_length=4000)
    historico: list[dict[str, str]] = Field(default_factory=list, max_length=6)


def public_user(user):
    return {"id": user["id"], "nome": user["nome"], "email": user["email"]}


def as_json(value):
    return {key: float(item) if isinstance(item, Decimal) else item for key, item in value.items()} if value else value


def current_user(request: Request):
    # A sessão guarda apenas os dados públicos necessários para identificar a conta.
    user = request.session.get("user")
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Faça login para continuar.")
    return user


def require_profile(user=Depends(current_user)):
    # Recomendações sem perfil poderiam ignorar renda, gastos e tolerância a risco.
    profile = get_financial_profile(user["id"])
    if not profile:
        raise HTTPException(409, "Preencha o perfil financeiro antes de conversar com o Bob.")
    return user, profile


def page(name):
    return FileResponse(ROOT_DIR / "templates" / name)


def protected_page(request, name):
    # Páginas HTML privadas redirecionam para login; endpoints de API continuam retornando 401.
    return page(name) if request.session.get("user") else RedirectResponse("/login")


@app.get("/", include_in_schema=False)
def index():
    return RedirectResponse("/login")


@app.get("/login", include_in_schema=False)
def login_page():
    return page("login.html")


@app.get("/cadastro", include_in_schema=False)
def register_page():
    return page("cadastro.html")


@app.get("/dashboard", include_in_schema=False)
def dashboard_page(request: Request):
    return protected_page(request, "dashboard.html")


@app.get("/perfil", include_in_schema=False)
def profile_page(request: Request):
    return protected_page(request, "perfil.html")


@app.get("/chat", include_in_schema=False)
def chat_page(request: Request):
    return protected_page(request, "chat.html")


@app.get("/api/health", tags=["Sistema"])
def health():
    return {"status": "ok", "database_configured": config_error() is None}


@app.post("/api/auth/register", status_code=201, tags=["Autenticação"])
def register(payload: RegisterPayload):
    # A confirmação é conferida aqui também, sem depender exclusivamente do JavaScript.
    if payload.senha != payload.confirmacao_senha:
        raise HTTPException(422, "A confirmação da senha não corresponde.")
    try:
        create_user(payload.nome, payload.email, payload.senha)
    except ValueError as error:
        raise HTTPException(409, str(error)) from error
    except Exception:
        raise HTTPException(503, "Não foi possível criar a conta. Verifique a conexão com o banco.")
    return {"message": "Conta criada. Agora entre com seu e-mail e senha."}


@app.post("/api/auth/login", tags=["Autenticação"])
def login(payload: LoginPayload, request: Request):
    user = authenticate(payload.email, payload.senha)
    if not user:
        raise HTTPException(401, "E-mail ou senha inválidos.")
    # Limpa uma sessão anterior antes de associar o cookie à conta autenticada.
    request.session.clear()
    request.session["user"] = public_user(user)
    return {"user": public_user(user)}


@app.post("/api/auth/logout", status_code=204, tags=["Autenticação"])
def logout(request: Request):
    request.session.clear()


@app.get("/api/auth/me", tags=["Autenticação"])
def me(user=Depends(current_user)):
    return public_user(user)


@app.get("/api/profile", tags=["Perfil"])
def get_profile(user=Depends(current_user)):
    return {"profile": as_json(get_financial_profile(user["id"]))}


@app.put("/api/profile", tags=["Perfil"])
def put_profile(payload: ProfilePayload, user=Depends(current_user)):
    # Normaliza os campos condicionais para que dados de dívida/investimento desmarcados não fiquem salvos.
    data = payload.model_dump()
    if data["possui_dividas"] and data["valor_dividas"] <= 0:
        raise HTTPException(422, "Informe o valor das dívidas ou desmarque essa opção.")
    if not data["possui_dividas"]:
        data.update(valor_dividas=0, juros_divida=None)
    if not data["possui_investimentos"]:
        data.update(valor_investido=0, tipos_investimentos=None)
    if data["objetivo_financeiro"] != "outro":
        data["objetivo_outro"] = None
    data["valor_disponivel_investimento"] = max(0, data["renda_mensal"] - sum(data[name] for name in EXPENSE_FIELDS))
    save_financial_profile(user["id"], data)
    return {"message": "Perfil financeiro salvo com segurança."}


@app.get("/api/dashboard", tags=["Dashboard"])
def dashboard(user=Depends(current_user)):
    # O dashboard calcula os indicadores no servidor a partir do perfil persistido.
    profile = get_financial_profile(user["id"])
    if not profile:
        return {"profile": None, "metrics": None}
    expenses, available, committed, months = metrics(profile)
    return {
        "profile": as_json(profile),
        "metrics": {
            "renda_mensal": float(profile["renda_mensal"]),
            "gastos_mensais": float(expenses),
            "disponivel": float(available),
            "percentual_comprometido": float(committed),
            "meses_reserva": float(months),
            "gastos_por_categoria": {key: float(profile[key]) for key in EXPENSE_FIELDS}
        }
    }


@app.post("/api/chat/stream", tags=["Chat"])
def chat_stream(payload: ChatPayload, profile_data=Depends(require_profile)):
    user, profile = profile_data
    # Aceita apenas os papéis esperados e limita o contexto recente enviado ao modelo.
    history = [
        {"role": item.get("role", "user"), "content": item.get("content", "")}
        for item in payload.historico
        if item.get("role") in ("user", "assistant") and item.get("content")
    ]
    context = build_prompt(profile_for_ai(user, profile), load_products())

    def generate():
        # NDJSON permite que o frontend mostre cada trecho assim que o Ollama o produz.
        for token in chat(payload.mensagem.strip(), context, history):
            yield json.dumps({"token": token}, ensure_ascii=False) + "\n"

    return StreamingResponse(
        generate(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )
