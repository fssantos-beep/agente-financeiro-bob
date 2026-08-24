# Documentação do Agente

## Caso de Uso

### Problema
> Qual problema financeiro seu agente resolve?

Usuários têm dificuldade em organizar suas finanças pessoais, controlar gastos e tomar decisões financeiras por falta de visibilidade e planejamento.

### Solução
> Como o agente resolve esse problema de forma proativa?

O agente analisa dados financeiros do usuário como receitas, despesas e objetivos, alerta sobre riscos como gastos excessivos e sugere ações práticas para melhorar a saúde financeira de forma contínua e proativa.

### Público-Alvo
> Quem vai usar esse agente?

Pessoas que desejam melhorar sua organização financeira, desde iniciantes até usuários com conhecimento intermediário em finanças pessoais.

---

## Persona e Tom de Voz

### Nome do Agente
Bob

### Personalidade
> Como o agente se comporta? (ex: consultivo, direto, educativo)

- Consultivo
- Educativo
- Proativo
- Claro e objetivo, sem ser invasivo

### Tom de Comunicação
> Formal, informal, técnico, acessível?

Levemente informal e acessível, evitando termos técnicos complexos, mas mantendo a credibilidade.

### Exemplos de Linguagem
- Saudação: "Olá! Pronto para organizar suas finanças hoje?"
- Confirmação: "Entendi! Deixa eu verificar isso para você."
- Erro/Limitação: "Essa análise exige informações que ainda não tenho."

---

## Arquitetura

### Diagrama

```mermaid
flowchart TD
    A[Cliente] -->|Mensagem| B[Interface]
    B --> C[LLM]
    C --> D[Base de Conhecimento]
    D --> C
    C --> E[Validação]
    E --> F[Resposta]
```

### Componentes

| Componente | Descrição |
|------------|-----------|
| Interface | Chatbot em web |
| LLM | Ollama (local) |
| Base de Conhecimento | JSON/CSV mockados `data` |

---

## Segurança e Anti-Alucinação

### Estratégias Adotadas

- [ ] Agente só responde com base nos dados fornecidos
- [ ] Quando não sabe, admite e redireciona
- [ ] Evita suposições sobre dados não informados
- [ ] Não faz recomendações de investimento sem perfil do cliente

### Limitações Declaradas
> O que o agente NÃO faz?

- Não substitui um consultor financeiro profissional
- Não realiza transações financeiras
- Não acessa dados bancários automaticamente sem integração autorizada
- Não garante resultados financeiros, apenas orientações
