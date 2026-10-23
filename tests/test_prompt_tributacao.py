import os
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("TAXAS_AUTOMATICAS", "0")

from src import chatbot
from src.chatbot import build_prompt, describe_tax, explain_taxes, load_products, load_tax_explanations
from src.database import profile_for_ai
from src.simulador import comparar, descrever_simulacao

USER = {"id": 1, "nome": "Ana", "email": "ana@teste.com"}
PROFILE = {
    "renda_mensal": 5000,
    "gastos_moradia": 1500,
    "gastos_alimentacao": 800,
    "gastos_transporte": 300,
    "gastos_contas": 250,
    "gastos_educacao": 0,
    "gastos_saude": 100,
    "gastos_lazer": 200,
    "outros_gastos": 150,
    "possui_dividas": False,
    "valor_dividas": 0,
    "reserva_emergencia": 2000,
    "possui_investimentos": False,
    "valor_investido": 0,
    "tipos_investimentos": None,
    "objetivo_financeiro": "viajar",
    "tolerancia_risco": "arrojado",
    "valor_disponivel_investimento": Decimal("1700.00"),
}


class DescricaoDaTributacaoTest(unittest.TestCase):
    def test_regressivo_traz_a_tabela_com_virgula_decimal(self):
        texto = describe_tax(
            {
                "tipo": "regressivo",
                "aliquotas": {
                    "ate_180_dias": "22.5%",
                    "181_360_dias": "20%",
                    "361_720_dias": "17.5%",
                    "acima_720_dias": "15%",
                },
            }
        )
        for esperado in (
            "regressivo",
            "até 180 dias: 22,5%",
            "181 a 360 dias: 20%",
            "361 a 720 dias: 17,5%",
            "acima de 720 dias: 15%",
        ):
            self.assertIn(esperado, texto)

    def test_valores_em_reais_nao_sao_alterados(self):
        texto = describe_tax({"tipo": "regressivo", "taxa_custodia_b3": "0.20% a.a. (isenta até R$ 10.000)"})
        self.assertIn("R$ 10.000", texto)
        self.assertNotIn("10,000", texto)

    def test_isento_deixa_claro_que_vale_para_pessoa_fisica(self):
        self.assertIn("pessoa física", describe_tax({"tipo": "isento", "ir": "Isento para pessoa física"}))

    def test_formatos_alternativos(self):
        self.assertEqual(describe_tax(None), "não informada")
        self.assertEqual(describe_tax(""), "não informada")
        self.assertEqual(describe_tax("isento"), "isento")

    def test_todo_produto_do_catalogo_tem_tributacao_legivel(self):
        for produto in load_products():
            self.assertNotEqual(describe_tax(produto.get("tributacao")), "não informada", produto["nome"])


class PromptComTributacaoTest(unittest.TestCase):
    def setUp(self):
        self.prompt = build_prompt(profile_for_ai(USER, PROFILE), load_products())

    def test_cada_produto_chega_ao_bob_com_a_sua_tributacao(self):
        linha = next(l for l in self.prompt.split("\n") if l.startswith("- Tesouro Selic"))
        self.assertIn("tributação: regressivo", linha)
        self.assertIn("até 180 dias: 22,5%", linha)
        lci = next(l for l in self.prompt.split("\n") if l.startswith("- LCI / LCA"))
        self.assertIn("isento", lci)

    def test_regras_gerais_contra_o_erro_de_progressivo(self):
        self.assertIn("REGRESSIVA", self.prompt)
        self.assertIn('nunca diga "progressiva"', self.prompt)
        self.assertIn("só sobre o rendimento", self.prompt)

    def test_pedido_de_formatacao_simples(self):
        self.assertIn("Markdown simples", self.prompt)
        self.assertIn("Não use títulos com #", self.prompt)


class ExplicacoesTributariasTest(unittest.TestCase):
    def linha(self, texto, nome):
        return next(l for l in texto.split("\n") if l.startswith(f"- {nome} "))

    def test_lci_explica_o_motivo_a_base_legal_e_para_quem_vale(self):
        texto = explain_taxes(load_products())
        lci = self.linha(texto, "LCI / LCA")
        self.assertIn("incentivo", lci)
        self.assertIn("crédito imobiliário", lci)
        self.assertIn("agronegócio", lci)
        self.assertIn("Vale para: pessoa física", lci)
        self.assertIn("pessoa jurídica", lci)
        self.assertIn("Lei 11.033/2004, art. 3º", lci)

    def test_regressiva_explica_por_que_a_aliquota_cai(self):
        tesouro = self.linha(explain_taxes(load_products()), "Tesouro Selic")
        self.assertIn("quanto mais tempo", tesouro)
        self.assertIn("Lei 11.033/2004, art. 1º", tesouro)

    def test_multimercado_avisa_que_o_simulador_nao_calcula_o_come_cotas(self):
        fundo = self.linha(explain_taxes(load_products()), "Fundo Multimercado")
        self.assertIn("come-cotas", fundo)
        self.assertIn("NÃO calcula o come-cotas", fundo)

    def test_so_os_produtos_mostrados_entram(self):
        texto = explain_taxes([p for p in load_products() if p["id"] == "lci_lca"])
        self.assertEqual(len(texto.split("\n")), 1)

    def test_produto_sem_explicacao_e_ignorado_e_sem_arquivo_devolve_none(self):
        self.assertIsNone(explain_taxes([{"id": "novo", "nome": "Novo"}]))
        produtos = load_products()  # carregados antes de trocar a pasta de dados
        with patch.object(chatbot, "DATA_DIR", Path("/nao/existe")):
            self.assertEqual(load_tax_explanations(), {})
            self.assertIsNone(explain_taxes(produtos))

    def test_arquivo_corrompido_nao_quebra(self):
        with patch.object(chatbot, "DATA_DIR", Path("/proc")):
            self.assertEqual(load_tax_explanations(), {})

    def test_prompt_traz_o_bloco_e_a_instrucao_de_explicar_isencoes(self):
        prompt = build_prompt(profile_for_ai(USER, PROFILE), load_products())
        self.assertIn("Por que cada regra de imposto existe e para quem vale", prompt)
        self.assertIn('não diga apenas "a LCI/LCA é isenta"', prompt)
        self.assertIn("explique o motivo e para quem vale", prompt)
        self.assertIn("pessoa jurídica", prompt)

    def test_prompt_sem_explicacoes_continua_funcionando(self):
        with patch.object(chatbot, "load_tax_explanations", return_value={}):
            prompt = build_prompt(profile_for_ai(USER, PROFILE), load_products())
        self.assertNotIn("Por que cada regra de imposto existe", prompt)
        self.assertIn("REGRESSIVA", prompt)

    def test_texto_da_simulacao_marca_a_isencao_como_de_pessoa_fisica(self):
        parametros = {
            "valor_inicial": 0,
            "aporte_mensal": 1500,
            "meses": 12,
            "tolerancia_risco": "moderado",
            "inflacao_anual_pct": None,
        }
        resultados = comparar(
            load_products(), "moderado", 0, 1500, 12, com_serie=False
        )  # 1.500 já cobre o mínimo da LCI/LCA
        self.assertIn("isento de IR para pessoa física", descrever_simulacao(parametros, True, resultados))


class ArquivoDeExplicacoesTest(unittest.TestCase):
    """Garante que o catálogo e as explicações continuam combinando quando o JSON for editado."""

    def test_todo_produto_do_catalogo_tem_explicacao_completa(self):
        explicacoes = load_tax_explanations()
        for produto in load_products():
            dados = explicacoes.get(produto["id"])
            self.assertIsNotNone(dados, f"falta explicação tributária para {produto['id']}")
            for campo in ("por_que", "vale_para", "fonte", "conferido_em"):
                self.assertTrue(dados.get(campo), f"{produto['id']}: falta o campo {campo}")

    def test_produto_com_come_cotas_avisa_a_limitacao_do_simulador(self):
        explicacoes = load_tax_explanations()
        for produto in load_products():
            if "come_cotas" in str(produto.get("tributacao", {}).get("tipo", "")):
                self.assertTrue(explicacoes[produto["id"]].get("limitacao_do_simulador"), produto["id"])

    def test_nao_ha_explicacao_para_produto_que_nao_existe(self):
        ids = {p["id"] for p in load_products()}
        for chave in load_tax_explanations():
            self.assertIn(chave, ids, f"explicação órfã: {chave}")


class TextoDaSimulacaoSobreIRTest(unittest.TestCase):
    def texto(self):
        parametros = {
            "valor_inicial": 0,
            "aporte_mensal": 500,
            "meses": 12,
            "tolerancia_risco": "moderado",
            "inflacao_anual_pct": None,
        }
        resultados = comparar(load_products(), "moderado", 0, 500, 12, com_serie=False)
        return descrever_simulacao(parametros, True, resultados)

    def test_explica_como_o_ir_foi_calculado(self):
        texto = self.texto()
        self.assertIn("Como o IR foi calculado", texto)
        self.assertIn("REGRESSIVA", texto)
        for faixa in ("22,50% até 180 dias", "20,00% até 360", "17,50% até 720", "15,00% acima de 720"):
            self.assertIn(faixa, texto)
        self.assertIn("cada aporte", texto)
        self.assertIn("isentas para pessoa física", texto)


if __name__ == "__main__":
    unittest.main()
