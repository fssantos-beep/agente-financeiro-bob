"""Simulador de investimentos do Bob.

Os cálculos ficam todos aqui. O modelo de linguagem só explica os números, nunca calcula.
"""

import math
import re
from decimal import ROUND_HALF_UP, Decimal

# Taxas de referência (% ao ano). Atualize depois de cada reunião do Copom (bcb.gov.br).
# Selic em 13,75% desde 17/09/2026; a próxima reunião está prevista para 3 e 4 de novembro.
TAXAS_REFERENCIA = {
    "selic": Decimal("13.75"),
    "cdi": Decimal("13.65"),  # fica uns 0,10 ponto abaixo da Selic
    "data_referencia": "2026-09-17",  # início da vigência da meta
}

# Cenários: o pessimista usa o menor valor da faixa de rentabilidade do produto (ex.: 100% em "100% a 110% do CDI")
# e uma Selic/CDI mais baixa; o otimista usa o maior valor e uma Selic/CDI mais alta; o base fica no meio.
# VARIACAO_CENARIO_PP é essa variação, em pontos percentuais.
VARIACAO_CENARIO_PP = Decimal("2")
PONTOS_CENARIO = {
    "pessimista": ("min", -VARIACAO_CENARIO_PP),
    "base": ("base", Decimal("0")),
    "otimista": ("max", VARIACAO_CENARIO_PP),
}
# Hipóteses para produtos sem taxa legível (como o fundo de ações), em pontos percentuais sobre o CDI.
# São premissas de estudo, não previsões. O cenário base paga 3 pontos acima do CDI, porque quem assume mais
# risco espera ganhar mais que a renda fixa. Troque pelos valores da sua fonte e cite no TCC.
CENARIOS_VARIAVEIS_SOBRE_CDI = {
    "pessimista": Decimal("-18"),
    "base": Decimal("3"),
    "otimista": Decimal("12"),
}

# Mesma regra de risco usada no prompt do Bob (chatbot.build_prompt).
RISCOS_PERMITIDOS = {
    "conservador": ["baixo"],
    "moderado": ["baixo", "medio"],
    "arrojado": ["baixo", "medio", "alto"],
}

CENTAVOS = Decimal("0.01")


def _dec(valor) -> Decimal:
    return Decimal(str(valor))


def _arredonda(valor: Decimal) -> float:
    return float(valor.quantize(CENTAVOS, rounding=ROUND_HALF_UP))


def brl(valor) -> str:
    """Formata em reais, no padrão brasileiro (R$ 1.234,56)."""
    texto = f"{float(valor):,.2f}"
    return "R$ " + texto.replace(",", "X").replace(".", ",").replace("X", ".")


def taxas_hipoteticas(taxas: dict = TAXAS_REFERENCIA) -> dict:
    """Taxas anuais (%) dos cenários hipotéticos, calculadas sobre o CDI."""
    return {nome: _dec(taxas["cdi"]) + delta for nome, delta in CENARIOS_VARIAVEIS_SOBRE_CDI.items()}


def dias_corridos(meses: int) -> int:
    """Converte meses em dias corridos (365/12 por mês, arredondando para cima)."""
    return math.ceil(meses * 365 / 12)


def aliquota_ir_regressivo(dias: int) -> Decimal:
    """Alíquota da tabela regressiva do IR da renda fixa, de acordo com os dias aplicados."""
    if dias <= 180:
        return Decimal("0.225")
    if dias <= 360:
        return Decimal("0.20")
    if dias <= 720:
        return Decimal("0.175")
    return Decimal("0.15")


REGRAS_TRIBUTACAO = ("isento", "regressivo", "fixa_15")


def regra_tributacao(produto: dict) -> str:
    """Diz como o produto é tributado: 'isento', 'regressivo' ou 'fixa_15'.

    Lê o campo "tributacao" do catálogo. O come-cotas dos fundos não é simulado, então
    "come_cotas + regressivo" usa só a tabela regressiva. Sem o campo, deduz pelo nome.
    """
    tributacao = produto.get("tributacao")
    if isinstance(tributacao, str) and tributacao in REGRAS_TRIBUTACAO:
        return tributacao
    tipo = str(tributacao.get("tipo", "")).lower() if isinstance(tributacao, dict) else ""
    if "isento" in tipo:
        return "isento"
    if "regressivo" in tipo:
        return "regressivo"
    if tipo == "fixo":
        return "fixa_15"
    nome = produto["nome"].lower()
    if "lci" in nome or "lca" in nome:
        return "isento"
    if "ações" in nome or "acoes" in nome:
        return "fixa_15"
    return "regressivo"


def _aliquota(regra: str, dias: int) -> Decimal:
    if regra == "isento":
        return Decimal("0")
    if regra == "fixa_15":
        return Decimal("0.15")
    return aliquota_ir_regressivo(dias)


_NUM = r"(\d+(?:[.,]\d+)?)"


def _num(texto: str) -> Decimal:
    return Decimal(texto.replace(",", "."))


def analisar_rentabilidade(produto: dict):
    """Interpreta o texto de "rentabilidade" do catálogo. Devolve None se não achar uma taxa.

    Exemplos que entende:
      "100% da Selic", "Geralmente 100% a 110% do CDI"   -> percentual do indexador (valor ou faixa)
      "CDI + 2%", "Variável (meta comum: CDI + 1% a 3%)" -> indexador mais um adicional (valor ou faixa)
    O resto do texto, como "Geralmente" ou observações entre parênteses, é ignorado.
    """
    texto = produto["rentabilidade"].lower()
    percentual = re.search(_NUM + r"\s*%(?:\s*a\s*" + _NUM + r"\s*%)?\s*(?:da|do)\s*(selic|cdi)", texto)
    if percentual:
        minimo = _num(percentual.group(1))
        maximo = _num(percentual.group(2)) if percentual.group(2) else minimo
        return {"tipo": "percentual", "indexador": percentual.group(3), "min": minimo, "max": maximo}
    spread = re.search(r"(selic|cdi)\s*\+\s*" + _NUM + r"\s*%(?:\s*a\s*" + _NUM + r"\s*%)?", texto)
    if spread:
        minimo = _num(spread.group(2))
        maximo = _num(spread.group(3)) if spread.group(3) else minimo
        return {"tipo": "spread", "indexador": spread.group(1), "min": minimo, "max": maximo}
    return None


def rentabilidade_variavel(produto: dict) -> bool:
    """Diz se o retorno não é garantido: sem taxa legível ou descrito como "Variável"."""
    texto = produto["rentabilidade"].lower()
    return analisar_rentabilidade(produto) is None or "variável" in texto or "variavel" in texto


def taxa_anual_produto(produto: dict, taxas: dict = TAXAS_REFERENCIA, ajuste_pp=0, ponto: str = "base"):
    """Converte a rentabilidade do catálogo em taxa anual (%). Devolve None se não houver taxa.

    `ponto` escolhe onde da faixa calcular ('min', 'base' para o meio ou 'max').
    `ajuste_pp` soma pontos percentuais à Selic/CDI, para montar os cenários.
    """
    regra = analisar_rentabilidade(produto)
    if regra is None:
        return None
    valor = {"min": regra["min"], "base": (regra["min"] + regra["max"]) / 2, "max": regra["max"]}[ponto]
    indexador = _dec(taxas[regra["indexador"]]) + _dec(ajuste_pp)
    if regra["tipo"] == "percentual":
        return valor / 100 * indexador
    return indexador + valor


def calcular(
    valor_inicial, aporte_mensal, meses: int, taxa_anual_pct, regra: str = "regressivo", inflacao_anual_pct=None
) -> dict:
    """Simula o investimento e devolve valores brutos, IR e líquidos.

    O valor inicial e cada aporte entram no começo do mês. O IR é calculado aporte por aporte,
    porque cada um fica um tempo diferente aplicado (tabela regressiva). Só há IR sobre
    rendimento positivo; prejuízo não gera crédito de imposto.
    """
    valor_inicial, aporte_mensal = _dec(valor_inicial), _dec(aporte_mensal)
    if meses < 1:
        raise ValueError("O prazo deve ser de pelo menos 1 mês.")
    if valor_inicial < 0 or aporte_mensal < 0:
        raise ValueError("Valores não podem ser negativos.")

    taxa_mensal = (1 + _dec(taxa_anual_pct) / 100) ** (Decimal(1) / 12) - 1

    # Cada lote é (valor aplicado, meses que ficará aplicado).
    lotes = []
    if valor_inicial > 0:
        lotes.append((valor_inicial, meses))
    if aporte_mensal > 0:
        lotes += [(aporte_mensal, meses - mes) for mes in range(meses)]

    investido = bruto = ir = Decimal("0")
    for valor, prazo in lotes:
        final = valor * (1 + taxa_mensal) ** prazo
        rendimento = final - valor
        investido += valor
        bruto += final
        if rendimento > 0:
            ir += rendimento * _aliquota(regra, dias_corridos(prazo))

    rendimento_bruto = bruto - investido
    liquido = bruto - ir
    rendimento_liquido = liquido - investido

    resultado = {
        "total_investido": _arredonda(investido),
        "valor_bruto": _arredonda(bruto),
        "rendimento_bruto": _arredonda(rendimento_bruto),
        "ir": _arredonda(ir),
        "aliquota_media_ir_pct": _arredonda(ir / rendimento_bruto * 100) if rendimento_bruto > 0 else 0.0,
        "valor_liquido": _arredonda(liquido),
        "rendimento_liquido": _arredonda(rendimento_liquido),
        "rentabilidade_liquida_pct": _arredonda(rendimento_liquido / investido * 100) if investido else 0.0,
        "taxa_anual_pct": _arredonda(_dec(taxa_anual_pct)),
        "meses": meses,
    }
    if inflacao_anual_pct is not None:
        deflator = (1 + _dec(inflacao_anual_pct) / 100) ** (Decimal(meses) / 12)
        resultado["valor_liquido_real"] = _arredonda(liquido / deflator)
    return resultado


def serie_mensal(valor_inicial, aporte_mensal, meses: int, taxa_anual_pct, regra: str = "regressivo") -> dict:
    """Evolução mês a mês (do mês 0 ao último) do total investido e do valor líquido.

    O líquido de cada mês é o que sobraria se o dinheiro fosse resgatado naquele mês, já sem o IR.
    Um real que ficou `idade` meses aplicado vale L(idade). No mês m o valor inicial tem idade m e
    os aportes têm idades de 1 a m, então basta somar. Assim o cálculo é linear no prazo.
    """
    valor_inicial, aporte_mensal = _dec(valor_inicial), _dec(aporte_mensal)
    taxa_mensal = (1 + _dec(taxa_anual_pct) / 100) ** (Decimal(1) / 12) - 1

    liquido_por_idade = [Decimal(1)]
    for idade in range(1, meses + 1):
        fator = (1 + taxa_mensal) ** idade
        rendimento = fator - 1
        ir = rendimento * _aliquota(regra, dias_corridos(idade)) if rendimento > 0 else Decimal(0)
        liquido_por_idade.append(fator - ir)

    investido, liquido, acumulado = [], [], Decimal(0)
    for mes in range(meses + 1):
        if mes:
            acumulado += liquido_por_idade[mes]
        investido.append(_arredonda(valor_inicial + aporte_mensal * mes))
        liquido.append(_arredonda(valor_inicial * liquido_por_idade[mes] + aporte_mensal * acumulado))
    return {"investido": investido, "liquido": liquido}


def simular_produto(
    produto: dict,
    valor_inicial,
    aporte_mensal,
    meses: int,
    taxas: dict = TAXAS_REFERENCIA,
    cenario: str = "base",
    inflacao_anual_pct=None,
    com_serie: bool = True,
) -> dict:
    """Simula um produto do catálogo em um cenário ('pessimista', 'base' ou 'otimista').

    Com `com_serie`, inclui também a evolução mês a mês (usada nos gráficos).
    """
    if cenario not in PONTOS_CENARIO:
        raise ValueError("Cenário inválido: use pessimista, base ou otimista.")

    ponto, ajuste = PONTOS_CENARIO[cenario]
    taxa = taxa_anual_produto(produto, taxas, ajuste, ponto)
    if taxa is None:
        taxa = taxas_hipoteticas(taxas)[cenario]  # sem taxa legível: usa a hipótese do cenário, calculada sobre o CDI

    regra = regra_tributacao(produto)
    resultado = calcular(valor_inicial, aporte_mensal, meses, taxa, regra, inflacao_anual_pct)
    if com_serie:
        resultado["serie"] = serie_mensal(valor_inicial, aporte_mensal, meses, taxa, regra)
    resultado.update(
        {
            "produto": produto["nome"],
            "risco": produto["risco"],
            "tributacao": regra,
            "cenario": cenario,
            "rentabilidade_variavel": rentabilidade_variavel(produto),
        }
    )
    return resultado


def comparar(
    produtos: list,
    tolerancia_risco: str,
    valor_inicial,
    aporte_mensal,
    meses: int,
    taxas: dict = TAXAS_REFERENCIA,
    inflacao_anual_pct=None,
    com_serie: bool = True,
) -> list:
    """Simula os produtos compatíveis com o risco nos 3 cenários, ordenados pelo líquido do cenário base.

    Produtos cujo aporte mínimo não é atingido no primeiro depósito voltam com `elegivel: False`
    e o motivo, para o Bob poder explicar.
    """
    permitidos = RISCOS_PERMITIDOS[tolerancia_risco]
    primeiro_deposito = _dec(valor_inicial) + _dec(aporte_mensal)

    itens = []
    for produto in produtos:
        if produto["risco"] not in permitidos:
            continue
        item = {
            "produto": produto["nome"],
            "risco": produto["risco"],
            "elegivel": True,
            "motivo": None,
            "rentabilidade_variavel": rentabilidade_variavel(produto),
        }
        minimo = _dec(produto["aporte_minimo"])
        if primeiro_deposito < minimo:
            item.update(elegivel=False, motivo=f"Primeiro depósito abaixo do aporte mínimo de {brl(minimo)}")
        else:
            item["cenarios"] = {
                nome: simular_produto(
                    produto, valor_inicial, aporte_mensal, meses, taxas, nome, inflacao_anual_pct, com_serie
                )
                for nome in PONTOS_CENARIO
            }
        itens.append(item)

    # Ordem: os elegíveis primeiro; entre eles, retorno conhecido antes do variável (que usa hipótese);
    # em cada grupo, do maior para o menor líquido no cenário base.
    itens.sort(
        key=lambda i: (
            not i["elegivel"],
            i["rentabilidade_variavel"],
            -(i["cenarios"]["base"]["valor_liquido"] if i["elegivel"] else 0),
        )
    )
    return itens


def _pct_br(valor) -> str:
    return f"{float(valor):.2f}".replace(".", ",") + "%"


def descrever_simulacao(
    parametros: dict,
    dados_do_perfil: bool,
    resultados: list,
    taxas: dict = TAXAS_REFERENCIA,
    produto_selecionado: str = None,
) -> str:
    """Resume a simulação da tela em texto, para o Bob explicar sem recalcular nada."""
    origem = (
        "dados do perfil salvo do usuário"
        if dados_do_perfil
        else "CENÁRIO HIPOTÉTICO: o usuário alterou valores ou o risco; estes NÃO são os dados reais do perfil dele"
    )
    inflacao = parametros.get("inflacao_anual_pct")
    data = "/".join(reversed(str(taxas["data_referencia"]).split("-")))
    fonte = {"bcb": "Banco Central, consulta automática", "cache": "Banco Central, última consulta bem-sucedida"}.get(
        taxas.get("fonte"), "valores padrão do sistema"
    )
    ipca = f"; IPCA em 12 meses {_pct_br(taxas['ipca_12m'])}" if taxas.get("ipca_12m") is not None else ""
    linhas = [
        "SIMULAÇÃO ABERTA NA TELA DO USUÁRIO (valores calculados pelo sistema):",
        f"- Origem dos dados: {origem}",
        f"- Valor inicial: {brl(parametros['valor_inicial'])}; aporte mensal: {brl(parametros['aporte_mensal'])}; "
        f"prazo: {parametros['meses']} meses; risco considerado: {parametros['tolerancia_risco']}",
        (
            f"- Inflação anual informada: {_pct_br(inflacao)}"
            if inflacao is not None
            else "- Inflação anual: não informada"
        ),
        f"- Taxas de referência: Selic {_pct_br(taxas['selic'])} e CDI {_pct_br(taxas['cdi'])} ao ano{ipca} "
        f"(fonte: {fonte}; data: {data})",
    ]

    elegiveis = [item for item in resultados if item["elegivel"]]
    if elegiveis:
        linhas.append("Produtos comparados (valores no fim do prazo, já com IR):")
        for item in elegiveis:
            cenarios = item["cenarios"]
            base = cenarios["base"]
            notas = []
            if item["rentabilidade_variavel"]:
                notas.append("rentabilidade variável, não garantida")
            if base["tributacao"] == "isento":
                notas.append("isento de IR para pessoa física")
            nota = f" ({'; '.join(notas)})" if notas else ""
            linhas.append(
                f"- {item['produto']} | risco {item['risco']} | investido {brl(base['total_investido'])} | "
                f"IR {brl(base['ir'])} | líquido base {brl(base['valor_liquido'])} | "
                f"pessimista {brl(cenarios['pessimista']['valor_liquido'])} | "
                f"otimista {brl(cenarios['otimista']['valor_liquido'])}{nota}"
            )
        # O produto destacado é o que o usuário está vendo na tela; sem seleção, o primeiro da lista.
        escolhido = next((item for item in elegiveis if item["produto"] == produto_selecionado), elegiveis[0])
        base = escolhido["cenarios"]["base"]
        detalhe = (
            f"Produto selecionado na tela: {escolhido['produto']} — valor bruto {brl(base['valor_bruto'])}, "
            f"rendimento bruto {brl(base['rendimento_bruto'])}, IR {brl(base['ir'])} "
            f"(alíquota média {_pct_br(base['aliquota_media_ir_pct'])}), valor líquido {brl(base['valor_liquido'])}, "
            f"rendimento líquido {brl(base['rendimento_liquido'])} "
            f"({_pct_br(base['rentabilidade_liquida_pct'])} sobre o total investido)"
        )
        if "valor_liquido_real" in base:
            detalhe += f"; em valores de hoje (descontada a inflação): {brl(base['valor_liquido_real'])}"
        linhas.append(detalhe)
    else:
        linhas.append("Nenhum produto está disponível para esse valor e risco.")

    if elegiveis:
        regressiva = ", ".join(
            f"{_pct_br(aliquota_ir_regressivo(dias) * 100)} {prazo}"
            for dias, prazo in ((180, "até 180 dias"), (360, "até 360"), (720, "até 720"), (721, "acima de 720"))
        )
        linhas.append(
            "Como o IR foi calculado: nos produtos tributados pela tabela REGRESSIVA "
            f"(a alíquota cai quanto mais tempo o dinheiro fica aplicado: {regressiva}), "
            "o imposto incide só sobre o rendimento e é calculado separadamente para cada aporte, "
            "conforme o tempo que ele ficou aplicado. Por isso a alíquota média pode ficar entre 15% e 22,5% "
            "e depende do prazo e dos aportes (aportes recentes pagam mais). "
            "LCI/LCA são isentas para pessoa física e o fundo de ações paga 15% fixos sobre o rendimento no resgate."
        )

    indisponiveis = [item for item in resultados if not item["elegivel"]]
    if indisponiveis:
        linhas.append(
            "Indisponíveis com esse valor: " + "; ".join(f"{i['produto']} ({i['motivo']})" for i in indisponiveis)
        )
    return "\n".join(linhas)
