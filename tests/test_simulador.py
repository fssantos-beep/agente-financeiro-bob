import unittest

from src.chatbot import load_products
from src.simulador import (
    REGRAS_TRIBUTACAO,
    aliquota_ir_regressivo,
    analisar_rentabilidade,
    brl,
    calcular,
    comparar,
    dias_corridos,
    regra_tributacao,
    rentabilidade_variavel,
    serie_mensal,
    simular_produto,
    taxa_anual_produto,
    taxas_hipoteticas,
)

TAXAS = {"selic": 14, "cdi": 14}  # taxas fixas nos testes para não depender de atualização


def produto(id_produto):
    # Busca o produto pelo id do catálogo, que não muda quando o nome de exibição muda.
    return next(item for item in load_products() if item["id"] == id_produto)


class SimuladorTest(unittest.TestCase):
    def test_tabela_regressiva_nos_limites(self):
        self.assertEqual(float(aliquota_ir_regressivo(180)), 0.225)
        self.assertEqual(float(aliquota_ir_regressivo(181)), 0.20)
        self.assertEqual(float(aliquota_ir_regressivo(360)), 0.20)
        self.assertEqual(float(aliquota_ir_regressivo(361)), 0.175)
        self.assertEqual(float(aliquota_ir_regressivo(720)), 0.175)
        self.assertEqual(float(aliquota_ir_regressivo(721)), 0.15)

    def test_conversao_de_meses_em_dias(self):
        self.assertEqual(dias_corridos(6), 183)
        self.assertEqual(dias_corridos(12), 365)
        self.assertEqual(dias_corridos(24), 730)

    def test_juros_compostos_em_12_meses(self):
        # R$ 1.000 a 12% a.a. por 12 meses, sem aporte e sem imposto: R$ 1.120,00.
        resultado = calcular(1000, 0, 12, 12, regra="isento")
        self.assertAlmostEqual(resultado["valor_bruto"], 1120.00, places=2)
        self.assertEqual(resultado["ir"], 0)
        self.assertEqual(resultado["valor_liquido"], resultado["valor_bruto"])

    def test_ir_regressivo_em_12_meses(self):
        # 365 dias -> 17,5% sobre o rendimento de R$ 120,00 = R$ 21,00.
        resultado = calcular(1000, 0, 12, 12, regra="regressivo")
        self.assertAlmostEqual(resultado["ir"], 21.00, places=2)
        self.assertAlmostEqual(resultado["valor_liquido"], 1099.00, places=2)

    def test_ir_fixo_de_15_por_cento(self):
        resultado = calcular(1000, 0, 6, 12, regra="fixa_15")
        self.assertAlmostEqual(resultado["ir"] / resultado["rendimento_bruto"], 0.15, places=3)

    def test_ir_por_aporte_usa_o_tempo_de_cada_um(self):
        # Com aportes, a alíquota média fica acima da menor alíquota do prazo total,
        # pois os últimos aportes ficam pouco tempo aplicados.
        resultado = calcular(0, 500, 24, 12, regra="regressivo")
        self.assertGreater(resultado["aliquota_media_ir_pct"], 15.0)
        self.assertLess(resultado["aliquota_media_ir_pct"], 22.5)
        self.assertAlmostEqual(resultado["total_investido"], 12000.00, places=2)

    def test_prejuizo_nao_gera_imposto(self):
        resultado = calcular(1000, 0, 12, -5, regra="fixa_15")
        self.assertEqual(resultado["ir"], 0)
        self.assertLess(resultado["valor_liquido"], 1000)

    def test_valor_real_com_inflacao(self):
        resultado = calcular(1000, 0, 12, 12, regra="isento", inflacao_anual_pct=5)
        self.assertAlmostEqual(resultado["valor_liquido_real"], 1120 / 1.05, places=2)

    def test_entradas_invalidas(self):
        with self.assertRaises(ValueError):
            calcular(1000, 0, 0, 12)
        with self.assertRaises(ValueError):
            calcular(-1, 0, 12, 12)

    def test_leitura_da_rentabilidade_do_catalogo(self):
        self.assertAlmostEqual(float(taxa_anual_produto(produto("tesouro_selic"), TAXAS)), 14.0)
        self.assertAlmostEqual(
            float(taxa_anual_produto(produto("cdb_liquidez_diaria"), TAXAS)), 14.70
        )  # ponto médio de 100%-110% do CDI
        self.assertAlmostEqual(
            float(taxa_anual_produto(produto("lci_lca"), TAXAS)), 12.60
        )  # ponto médio de 85%-95% do CDI
        self.assertAlmostEqual(float(taxa_anual_produto(produto("fundo_multimercado"), TAXAS)), 16.0)
        self.assertIsNone(taxa_anual_produto(produto("fundo_acoes"), TAXAS))

    def test_regras_de_tributacao_do_catalogo(self):
        self.assertEqual(regra_tributacao(produto("lci_lca")), "isento")
        self.assertEqual(regra_tributacao(produto("tesouro_selic")), "regressivo")
        self.assertEqual(regra_tributacao(produto("fundo_acoes")), "fixa_15")

    def test_cenarios_seguem_a_ordem_esperada(self):
        valores = [
            simular_produto(produto("tesouro_selic"), 1000, 100, 12, TAXAS, cenario)["valor_liquido"]
            for cenario in ("pessimista", "base", "otimista")
        ]
        self.assertEqual(valores, sorted(valores))

    def test_fundo_variavel_usa_taxa_do_cenario(self):
        pessimista = simular_produto(produto("fundo_acoes"), 1000, 0, 12, TAXAS, "pessimista")
        self.assertLess(pessimista["valor_liquido"], 1000)

    def test_cenario_invalido(self):
        with self.assertRaises(ValueError):
            simular_produto(produto("tesouro_selic"), 1000, 0, 12, TAXAS, "qualquer")

    def test_comparacao_respeita_o_risco_do_usuario(self):
        produtos = load_products()
        conservador = {item["produto"] for item in comparar(produtos, "conservador", 1000, 200, 12, TAXAS)}
        self.assertNotIn("Fundo Multimercado", conservador)
        self.assertNotIn("Fundo de Ações", conservador)
        arrojado = {item["produto"] for item in comparar(produtos, "arrojado", 1000, 200, 12, TAXAS)}
        self.assertIn("Fundo de Ações", arrojado)

    def test_aporte_minimo_marca_produto_como_inelegivel(self):
        itens = comparar(load_products(), "conservador", 0, 50, 12, TAXAS)
        por_nome = {item["produto"]: item for item in itens}
        self.assertTrue(por_nome["Tesouro Selic"]["elegivel"])  # mínimo de R$ 30
        self.assertFalse(por_nome["LCI / LCA"]["elegivel"])  # mínimo de R$ 1.000
        self.assertIn("aporte mínimo", por_nome["LCI / LCA"]["motivo"])
        self.assertEqual(itens[-1]["produto"], "LCI / LCA")  # inelegíveis ficam no fim

    def test_formatacao_em_reais(self):
        self.assertEqual(brl(1234.5), "R$ 1.234,50")
        self.assertEqual(brl(100), "R$ 100,00")

    def test_motivo_do_aporte_minimo_em_reais(self):
        itens = comparar(load_products(), "conservador", 0, 50, 12, TAXAS)
        lci = next(item for item in itens if item["produto"] == "LCI / LCA")
        self.assertEqual(lci["motivo"], "Primeiro depósito abaixo do aporte mínimo de R$ 1.000,00")

    def test_comparacao_ordenada_pelo_liquido_do_cenario_base(self):
        itens = [i for i in comparar(load_products(), "arrojado", 5000, 0, 24, TAXAS) if i["elegivel"]]
        conhecidos = [i for i in itens if not i["rentabilidade_variavel"]]
        liquidos = [i["cenarios"]["base"]["valor_liquido"] for i in conhecidos]
        self.assertEqual(liquidos, sorted(liquidos, reverse=True))

    def test_rentabilidade_variavel_fica_depois_das_conhecidas(self):
        itens = comparar(load_products(), "arrojado", 5000, 0, 24, TAXAS)
        variaveis = [item["rentabilidade_variavel"] for item in itens]
        self.assertEqual(variaveis, sorted(variaveis))  # False (conhecidas) antes de True (variáveis)
        self.assertFalse(variaveis[0])
        self.assertTrue(variaveis[-1])

    def test_leitura_de_faixas_e_formatos_do_catalogo(self):
        casos = {
            "100% da Selic + pequena taxa (atualmente ~13,75% a.a.)": ("percentual", "selic", 100, 100),
            "Geralmente 100% a 110% do CDI (CDI atual ~13,65% a.a.)": ("percentual", "cdi", 100, 110),
            "Geralmente 85% a 95% do CDI (isento de IR)": ("percentual", "cdi", 85, 95),
            "Variável (meta comum: CDI + 1% a 3%)": ("spread", "cdi", 1, 3),
            "102% do CDI": ("percentual", "cdi", 102, 102),
            "CDI + 2,5%": ("spread", "cdi", 2.5, 2.5),
        }
        for texto, (tipo, indexador, minimo, maximo) in casos.items():
            regra = analisar_rentabilidade({"rentabilidade": texto})
            self.assertEqual(
                (regra["tipo"], regra["indexador"], float(regra["min"]), float(regra["max"])),
                (tipo, indexador, minimo, maximo),
                texto,
            )
        self.assertIsNone(analisar_rentabilidade({"rentabilidade": "Variável (acompanha o mercado de ações)"}))

    def test_cenarios_usam_a_faixa_do_produto(self):
        cdb = produto("cdb_liquidez_diaria")  # 100% a 110% do CDI
        self.assertAlmostEqual(float(taxa_anual_produto(cdb, TAXAS, ponto="min")), 14.00)
        self.assertAlmostEqual(float(taxa_anual_produto(cdb, TAXAS, ponto="max")), 15.40)
        pessimista = simular_produto(cdb, 1000, 0, 12, TAXAS, "pessimista")["taxa_anual_pct"]
        otimista = simular_produto(cdb, 1000, 0, 12, TAXAS, "otimista")["taxa_anual_pct"]
        self.assertAlmostEqual(pessimista, 12.00)  # 100% de (14 - 2)
        self.assertAlmostEqual(otimista, 17.60)  # 110% de (14 + 2)

    def test_multimercado_com_meta_e_variavel_mas_projetavel(self):
        fundo = produto("fundo_multimercado")
        self.assertTrue(rentabilidade_variavel(fundo))
        self.assertAlmostEqual(float(taxa_anual_produto(fundo, TAXAS)), 16.0)  # CDI + ponto médio de 1%-3%

    def test_tributacao_lida_do_objeto_do_catalogo(self):
        self.assertEqual(regra_tributacao({"nome": "X", "tributacao": {"tipo": "isento"}}), "isento")
        self.assertEqual(
            regra_tributacao({"nome": "X", "tributacao": {"tipo": "come_cotas + regressivo"}}), "regressivo"
        )
        self.assertEqual(regra_tributacao({"nome": "X", "tributacao": {"tipo": "fixo"}}), "fixa_15")
        self.assertEqual(regra_tributacao({"nome": "X", "tributacao": "isento"}), "isento")

    def test_todo_o_catalogo_e_compativel_com_o_simulador(self):
        # Avisa se alguma edição no JSON deixar o simulador sem conseguir ler um produto.
        for item in load_products():
            nome = item.get("nome", "?")
            self.assertIn(item["risco"], ("baixo", "medio", "alto"), nome)
            self.assertGreater(item["aporte_minimo"], 0, nome)
            self.assertIn(regra_tributacao(item), REGRAS_TRIBUTACAO, nome)
            if analisar_rentabilidade(item) is None:
                self.assertTrue(
                    rentabilidade_variavel(item) and "variável" in item["rentabilidade"].lower(),
                    f"{nome}: rentabilidade ilegível. Use '100% do CDI', 'CDI + 2%' ou comece com 'Variável'.",
                )

    def test_produtos_do_catalogo_geram_resultados_diferentes(self):
        liquidos = {
            item["produto"]: item["cenarios"]["base"]["valor_liquido"]
            for item in comparar(load_products(), "arrojado", 5000, 500, 24, TAXAS)
            if item["elegivel"]
        }
        self.assertGreaterEqual(len(set(liquidos.values())), len(liquidos), liquidos)

    def test_lci_e_isenta_e_os_demais_pagam_imposto(self):
        itens = {
            i["produto"]: i["cenarios"]["base"]
            for i in comparar(load_products(), "arrojado", 5000, 0, 24, TAXAS)
            if i["elegivel"]
        }
        self.assertEqual(itens["LCI / LCA"]["ir"], 0)
        self.assertGreater(itens["Tesouro Selic"]["ir"], 0)
        self.assertGreater(itens["Fundo de Ações"]["ir"], 0)

    def test_hipoteses_variaveis_acompanham_o_cdi_e_pagam_premio_de_risco(self):
        hipoteses = taxas_hipoteticas(TAXAS)
        self.assertGreater(float(hipoteses["base"]), TAXAS["cdi"])  # base acima da renda fixa: há prêmio de risco
        self.assertLess(float(hipoteses["pessimista"]), 0)
        self.assertLess(float(hipoteses["pessimista"]), float(hipoteses["base"]))
        self.assertLess(float(hipoteses["base"]), float(hipoteses["otimista"]))
        mais_juros = taxas_hipoteticas({"selic": 20, "cdi": 20})
        self.assertAlmostEqual(float(mais_juros["base"] - hipoteses["base"]), 6.0)

    def test_fundo_de_acoes_base_rende_mais_que_a_renda_fixa_no_longo_prazo(self):
        fundo = simular_produto(produto("fundo_acoes"), 5000, 500, 120, TAXAS, "base")["valor_liquido"]
        tesouro = simular_produto(produto("tesouro_selic"), 5000, 500, 120, TAXAS, "base")["valor_liquido"]
        self.assertGreater(fundo, tesouro)

    def test_fundo_de_acoes_tem_a_maior_dispersao_entre_cenarios(self):
        faixas = {}
        for item in comparar(load_products(), "arrojado", 5000, 500, 120, TAXAS):
            c = item["cenarios"]
            faixas[item["produto"]] = c["otimista"]["valor_liquido"] - c["pessimista"]["valor_liquido"]
        self.assertEqual(max(faixas, key=faixas.get), "Fundo de Ações")

    def test_serie_mensal_tem_um_ponto_por_mes_e_comeca_no_valor_inicial(self):
        serie = serie_mensal(1000, 200, 12, 12, "regressivo")
        self.assertEqual(len(serie["investido"]), 13)
        self.assertEqual(len(serie["liquido"]), 13)
        self.assertEqual((serie["investido"][0], serie["liquido"][0]), (1000.0, 1000.0))
        self.assertEqual(serie["investido"][12], 1000 + 200 * 12)

    def test_serie_mensal_termina_igual_ao_calculo_final(self):
        for regra in REGRAS_TRIBUTACAO:
            for taxa in (13.65, 0, -5):
                final = calcular(3298, 500, 120, taxa, regra)
                serie = serie_mensal(3298, 500, 120, taxa, regra)
                self.assertAlmostEqual(serie["investido"][-1], final["total_investido"], places=2)
                self.assertAlmostEqual(serie["liquido"][-1], final["valor_liquido"], delta=0.011, msg=f"{regra} {taxa}")

    def test_serie_mensal_cresce_com_rentabilidade_positiva(self):
        liquido = serie_mensal(1000, 300, 60, 12, "regressivo")["liquido"]
        self.assertEqual(liquido, sorted(liquido))

    def test_serie_mensal_longa_e_rapida(self):
        serie = serie_mensal(1000, 300, 600, 12, "regressivo")
        self.assertEqual(len(serie["liquido"]), 601)

    def test_simular_produto_inclui_a_serie_por_padrao(self):
        com = simular_produto(produto("tesouro_selic"), 1000, 100, 24, TAXAS, "base")
        sem = simular_produto(produto("tesouro_selic"), 1000, 100, 24, TAXAS, "base", com_serie=False)
        self.assertEqual(len(com["serie"]["liquido"]), 25)
        self.assertNotIn("serie", sem)
        self.assertEqual(com["serie"]["liquido"][-1], com["valor_liquido"])

    def test_cenarios_tem_series_ordenadas_no_ultimo_mes(self):
        for item in comparar(load_products(), "arrojado", 3298, 500, 120, TAXAS):
            if item["elegivel"]:
                c = item["cenarios"]
                finais = [c[n]["serie"]["liquido"][-1] for n in ("pessimista", "base", "otimista")]
                self.assertEqual(finais, sorted(finais), item["produto"])


if __name__ == "__main__":
    unittest.main()
