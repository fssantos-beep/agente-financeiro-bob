# Bob — Assistente Financeiro

Aplicação web para TCC com frontend em HTML/CSS/JavaScript puro, backend Python/FastAPI, MySQL e IA local com Ollama (`gpt-oss:latest`). O navegador conversa apenas com o FastAPI; este encaminha o stream ao Ollama.

## Funcionalidades

- **Autenticação**: cadastro e login com senha em `bcrypt` e sessão via cookie `HttpOnly`.
- **Perfil financeiro**: renda, gastos por categoria, dívidas, reserva de emergência, investimentos, objetivo (com opção "Outro") e tolerância a risco (conservador, moderado, arrojado).
- **Dashboard**: cards de renda, gastos, disponível mensal, percentual de renda comprometida e meses de reserva, além de um gráfico de barras por categoria de gasto — tudo calculado no servidor.
- **Chat com o Bob**: respostas em streaming (NDJSON) geradas pelo Ollama, sempre baseadas no perfil salvo e no catálogo de produtos filtrado pela tolerância a risco do usuário, para evitar recomendações fora do perfil ou informações inventadas.

## Estrutura

- `src/main.py`: FastAPI, sessão autenticada e API REST (`/docs`).
- `src/database.py`: MySQL, bcrypt e queries parametrizadas.
- `src/chatbot.py`: regras de negócio, métricas, prompt e streaming do Ollama.
- `templates/`: telas separadas de login, cadastro, dashboard, perfil e chat.
- `static/js/`: scripts específicos por tela e utilitários compartilhados.
- `static/css/`: estilos da interface.
- `database/schema.sql`: script de criação do banco MySQL.
- `data/produtos_financeiros.json`: catálogo usado pelo filtro de risco.
- `tests/`: testes automatizados (`unittest`) do contexto enviado ao Bob.
- `docs/`: documentação do TCC (caso de uso, base de conhecimento, prompts, métricas e pitch).
- `examples/`: protótipo inicial em Streamlit, mantido apenas como referência histórica do projeto.

## Instalação e execução

1. No MySQL Community Server, execute `database/schema.sql` para criar o banco `agente_financeiro_bob` e as tabelas.
2. Copie `.env.example` para `.env`, preencha as credenciais locais do MySQL.
3. Crie o ambiente e instale dependências:

```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
```

   No Linux/macOS:

```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
```

4. Instale/inicie o Ollama e obtenha o modelo:

```powershell
   ollama pull gpt-oss:latest
   ollama serve
```

5. Inicie o sistema:

```powershell
   uvicorn src.main:app --reload
```

Abra `http://127.0.0.1:8000`; não há servidor de frontend separado. Teste APIs em `http://127.0.0.1:8000/docs`.

## Principais endpoints

| Método | Rota | Descrição |
|---|---|---|
| POST | `/api/auth/register` | Cria uma conta nova |
| POST | `/api/auth/login` | Autentica e inicia a sessão |
| POST | `/api/auth/logout` | Encerra a sessão |
| GET | `/api/auth/me` | Retorna o usuário autenticado |
| GET / PUT | `/api/profile` | Consulta ou salva o perfil financeiro |
| GET | `/api/dashboard` | Perfil + métricas calculadas para o painel |
| POST | `/api/chat/stream` | Envia uma mensagem e recebe a resposta do Bob em streaming |
| GET | `/api/health` | Verifica se a API e o banco estão configurados |

A lista completa e interativa fica em `/docs` (Swagger UI).

## Teste completo

1. Crie uma conta (senha de ao menos oito caracteres) e entre.
2. Salve um perfil incluindo condições de dívida, objetivo e risco.
3. Confira cards e gráfico no dashboard; edite o perfil e confirme a atualização.
4. Envie uma pergunta no chat. A resposta chega progressivamente por `/api/chat/stream`.
5. Use **Sair**, reinicie o servidor e entre novamente. O perfil fica no MySQL; o histórico do chat é mantido intencionalmente somente na sessão da página.

## Segurança

Senhas usam `bcrypt`; a sessão fica em cookie `HttpOnly`; o banco usa queries parametrizadas; respostas não retornam hash de senha ou configurações do `.env`. Em produção HTTPS, defina `COOKIE_SECURE=true`.