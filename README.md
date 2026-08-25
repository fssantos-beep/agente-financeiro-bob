# Bob — Assistente Financeiro

Projeto de TCC em Streamlit com autenticação, perfil financeiro persistente em MySQL e chat local via Ollama.

## Arquitetura

- `src/chatbot.py`: interface Streamlit (cadastro, login, perfil, dashboard e chat).
- `src/database.py`: conexão MySQL, hash de senha e acesso aos dados com queries parametrizadas.
- `database/schema.sql`: schema reproduzível do MySQL Community Server.
- `data/`: catálogo de produtos e dados demonstrativos já existentes.

## Configuração

1. Instale e inicie o MySQL Community Server.
2. Execute `database/schema.sql` no MySQL Workbench ou no terminal:

   ```powershell
   mysql -u root -p < database/schema.sql
   ```

3. Copie `.env.example` para `.env` e informe as credenciais locais:

   ```env
   DB_HOST=localhost
   DB_PORT=3306
   DB_USER=root
   DB_PASSWORD=sua_senha
   DB_NAME=agente_financeiro_bob
   ```

4. Crie e ative um ambiente virtual, instale as dependências e execute:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   streamlit run src/chatbot.py
   ```

O chat depende opcionalmente de um Ollama local em `http://localhost:11434` com o modelo configurado no código. Cadastro, login, perfil e dashboard funcionam independentemente dele.

## Fluxo e testes manuais

1. Crie uma conta com nome, e-mail válido, senha de oito ou mais caracteres e confirmação igual.
2. Tente cadastrar o mesmo e-mail: o sistema deve informar duplicidade.
3. Tente senhas diferentes: o cadastro deve bloquear.
4. Entre com credenciais corretas e depois teste uma senha incorreta.
5. No primeiro acesso, preencha e salve o perfil. Valores negativos são bloqueados pelos campos; renda igual a zero e dívida marcada sem valor também são recusadas.
6. Edite o perfil no dashboard e confirme a atualização dos indicadores.
7. Saia pelo botão **Sair**, entre com outra conta e confirme que os dados não aparecem: toda leitura/gravação usa o `usuario_id` da sessão autenticada.

## Segurança e preparação para IA

- Senhas usam `bcrypt`; nenhum texto puro é armazenado.
- Credenciais ficam somente no `.env`, que está ignorado pelo Git.
- O banco tem e-mail único e chave estrangeira entre `usuarios` e `perfil_financeiro`.
- As queries usam parâmetros, evitando SQL injection.
- `profile_for_ai()` produz um resumo calculado e pronto para uma integração futura, sem enviar dados a serviços externos.
