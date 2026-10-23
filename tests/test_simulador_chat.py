import asyncio
import json
import os
import unittest
from decimal import Decimal
from unittest.mock import patch

from pydantic import ValidationError

os.environ.setdefault("TAXAS_AUTOMATICAS", "0")  # os testes não dependem da internet

from src import main
from src.chatbot import build_prompt, load_products
from src.database import profile_for_ai
from src.main import ChatPayload, simulation_context
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
    "tolerancia_risco": "moderado",
    "valor_disponivel_investimento": Decimal("1700.00"),
}


def consumir(resposta):
    # O StreamingResponse entrega o corpo como iterador assíncrono, mesmo vindo de um gerador comum.
    async def ler():
        return [pedaco async for pedaco in resposta.body_iterator]

    return asyncio.run(ler())


def simulacao(**overrides):
    data = {"valor_inicial": 0, "aporte_mensal": 1700, "meses": 24, "tolerancia_risco": "moderado"}
    data.update(overrides)
    return ChatPayload(mensagem="oi", simulacao=data).simulacao


class DescricaoDaSimulacaoTest(unittest.TestCase):
    def texto(self, dados_do_perfil=True, produto=None, **params):
        parametros = {
            "valor_inicial": 0,
            "aporte_mensal": 1700,
            "meses": 24,
            "tolerancia_risco": "moderado",
            "inflacao_anual_pct": None,
        }
        parametros.update(params)
        resultados = comparar(
            load_products(),
            parametros["tolerancia_risco"],
            parametros["valor_inicial"],
            parametros["aporte_mensal"],
            parametros["meses"],
            inflacao_anual_pct=parametros["inflacao_anual_pct"],
        )
        return descrever_simulacao(parametros, dados_do_perfil, resultados, produto_selecionado=produto)

    def test_traz_parametros_taxas_e_produtos(self):
        texto = self.texto()
        self.assertIn("aporte mensal: R$ 1.700,00", texto)
        self.assertIn("prazo: 24 meses", texto)
        self.assertIn("Selic", texto)
        self.assertIn("- LCI / LCA | risco baixo", texto)
        self.assertIn("isento de IR", texto)
        self.assertIn("dados do perfil salvo", texto)

    def test_cenario_hipotetico_fica_explicito(self):
        self.assertIn("CENÁRIO HIPOTÉTICO", self.texto(dados_do_perfil=False))

    def test_produto_selecionado_e_detalhado(self):
        texto = self.texto(produto="Tesouro Selic")
        detalhe = next(linha for linha in texto.split("\n") if linha.startswith("Produto selecionado na tela"))
        self.assertIn("Tesouro Selic", detalhe)
        self.assertIn("alíquota média", detalhe)

    def test_sem_selecao_usa_o_primeiro_da_lista(self):
        detalhe = next(l for l in self.texto().split("\n") if l.startswith("Produto selecionado na tela"))
        self.assertIn("LCI / LCA", detalhe)

    def test_produto_indisponivel_aparece_com_motivo(self):
        texto = self.texto(aporte_mensal=50, tolerancia_risco="conservador")
        self.assertIn("Indisponíveis com esse valor", texto)
        self.assertIn("R$ 1.000,00", texto)

    def test_inflacao_aparece_quando_informada(self):
        texto = self.texto(inflacao_anual_pct=4.5)
        self.assertIn("Inflação anual informada: 4,50%", texto)
        self.assertIn("em valores de hoje", texto)

    def test_fundo_variavel_e_sinalizado(self):
        self.assertIn(
            "rentabilidade variável, não garantida",
            self.texto(tolerancia_risco="arrojado", valor_inicial=5000, aporte_mensal=0),
        )


class PromptComSimulacaoTest(unittest.TestCase):
    def prompt(self, simulation_text=None):
        return build_prompt(profile_for_ai(USER, PROFILE), load_products(), simulation_text)

    def test_sem_simulacao_o_prompt_nao_muda(self):
        self.assertNotIn("SIMULAÇÃO ABERTA", self.prompt())
        self.assertNotIn("Sobre a simulação", self.prompt())

    def test_com_simulacao_o_bloco_e_as_regras_entram(self):
        prompt = self.prompt("SIMULAÇÃO ABERTA NA TELA DO USUÁRIO: teste")
        self.assertIn("SIMULAÇÃO ABERTA NA TELA DO USUÁRIO: teste", prompt)
        self.assertIn("nunca recalcule", prompt)
        self.assertIn("Perfil do cliente:", prompt)  # o perfil continua no prompt


class ContextoNoServidorTest(unittest.TestCase):
    def test_zero_investido_nao_gera_contexto(self):
        self.assertIsNone(simulation_context(simulacao(aporte_mensal=0), PROFILE))

    def test_dados_do_perfil_x_hipotetico(self):
        self.assertIn("dados do perfil salvo", simulation_context(simulacao(), PROFILE))
        self.assertIn("CENÁRIO HIPOTÉTICO", simulation_context(simulacao(aporte_mensal=300), PROFILE))

    def test_payload_do_chat_valida_a_simulacao(self):
        with self.assertRaises(ValidationError):
            simulacao(meses=0)
        with self.assertRaises(ValidationError):
            simulacao(tolerancia_risco="ousado")
        self.assertIsNone(ChatPayload(mensagem="oi").simulacao)

    def test_chat_stream_envia_ao_bob_numeros_calculados_pelo_servidor(self):
        capturado = {}

        def falso_chat(mensagem, contexto, historico):
            capturado["contexto"] = contexto
            yield "ok"

        # O navegador só manda parâmetros; qualquer outro campo (como "resultados") é ignorado.
        payload = ChatPayload(
            mensagem="Por que a LCI rende mais?",
            simulacao={
                "valor_inicial": 0,
                "aporte_mensal": 1700,
                "meses": 24,
                "tolerancia_risco": "moderado",
                "produto_selecionado": "Tesouro Selic",
                "resultados": "R$ 999.999.999,00",
            },
        )
        with patch.object(main, "chat", falso_chat):
            resposta = main.chat_stream(payload, (USER, PROFILE))
            tokens = [json.loads(linha)["token"] for linha in consumir(resposta)]

        self.assertEqual(tokens, ["ok"])
        contexto = capturado["contexto"]
        self.assertIn("SIMULAÇÃO ABERTA NA TELA", contexto)
        self.assertIn("Produto selecionado na tela: Tesouro Selic", contexto)
        self.assertNotIn("999.999.999", contexto)

    def test_chat_sem_simulacao_continua_igual(self):
        capturado = {}

        def falso_chat(mensagem, contexto, historico):
            capturado["contexto"] = contexto
            yield "ok"

        with patch.object(main, "chat", falso_chat):
            resposta = main.chat_stream(ChatPayload(mensagem="oi"), (USER, PROFILE))
            consumir(resposta)
        self.assertNotIn("SIMULAÇÃO ABERTA", capturado["contexto"])


if __name__ == "__main__":
    unittest.main()
