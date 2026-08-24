# Base de Conhecimento

## Dados Utilizados

| Arquivo | Formato | Utilização no Agente |
|---------|---------|---------------------|
| `historico_atendimento.csv` | CSV | Contextualizar interações anteriores, permitindo respostas personalizada e continuidade no atendimento |
| `perfil_investidor.json` | JSON | Define o perfil de risco do cliente para orientar recomendações adequadas |
| `produtos_financeiros.json` | JSON | Lista produtos disponíveis, usados para sugerir opções compatíveis com o perfil |
| `transacoes.csv` | CSV | Analisar padrão de comportamento financeiro do cliente |

---

## Adaptações nos Dados

> Você modificou ou expandiu os dados mockados? Descreva aqui.

Não

---

## Estratégia de Integração

### Como os dados são carregados?
> Descreva como seu agente acessa a base de conhecimento.

Os dados são carregados no início de cada sessão a partir de arquivos estruturados (CSV e JSON) e convertidos para estruturas manipuláveis
- Ingestão: Leitura dos arquivos (.csv e .json)
- Tratamento: Limpeza, padronização e categorização dos dados
- Indexação: Organização das informações por relevância

### Como os dados são usados no prompt?
> Os dados vão no system prompt? São consultados dinamicamente?

A utilização dos dados equilibra contexto e eficiência:
- System prompt:
- - Perfil do investidor
  - Regras de comportamento do agente
  - Restrições para não recomendar investimento incompativeis
- Contexto:
- - Resumo financeiro do cliente
  - Ultimas transações

---

## Exemplo de Contexto Montado

> Mostre um exemplo de como os dados são formatados para o agente.

```
Dados do Cliente:
- Nome: João Silva
- Perfil: Moderado
- Saldo disponível: R$ 5.000

Últimas transações:
- 01/11: Supermercado - R$ 450
- 03/11: Streaming - R$ 55
...
```
