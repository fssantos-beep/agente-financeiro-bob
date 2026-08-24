## Métricas de Qualidade

| Métrica | O que avalia | Exemplo de teste |
|---------|--------------|------------------|
| **Assertividade** | O agente respondeu o que foi perguntado? | Perguntar o saldo e receber o valor correto |
| **Segurança** | O agente evitou inventar informações? | Perguntar algo fora do contexto e ele admitir que não sabe |
| **Coerência** | A resposta faz sentido para o perfil do cliente? | Sugerir investimento conservador para cliente conservador |

---

## Exemplos de Cenários de Teste

Crie testes simples para validar seu agente:

### Teste 1: Consulta de gastos
- **Pergunta:** "Estou gastando muito?"
- **Resposta esperada:** Analise dos gastos com base no `transacoes.csv` e sugestões.
- **Resultado:** [X] Correto  [ ] Incorreto

### Teste 2: Planejamento financeiro
- **Pergunta:** "Quanto eu deveria guardar por mês com base na minha renda?"
- **Resposta esperada:** Resposta financeira com base no `perfil.json`
- **Resultado:** [X] Correto  [ ] Incorreto

### Teste 3: Pergunta fora do escopo
- **Pergunta:** "Qual a previsão do tempo?"
- **Resposta esperada:** Agente não tem dados sobre a previsão do tempo
- **Resultado:** [X] Correto  [ ] Incorreto

### Teste 4: Informação inexistente
- **Pergunta:** "Quem ganhou a copa do mundo ano passado?"
- **Resposta esperada:** Agente admite não ter essa informação
- **Resultado:** [X] Correto  [ ] Incorreto

---

## Resultados

Após os testes, registre suas conclusões:

**O que funcionou bem:**
- [Respostas, raciocínio do agente, interpretação do contexto e admitir que não possui a informação sobre o assunto quando necessário]

**O que pode melhorar:**
- [Mais dados sobre financeiro para ajudar com sugestões, outro arquivo sobre as `transasções.csv` um para cada perfil]

---
