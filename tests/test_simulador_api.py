import os
import unittest

from fastapi import HTTPException
from pydantic import ValidationError

os.environ.setdefault("TAXAS_AUTOMATICAS", "0")  # os testes não dependem da internet

from src.main import SimuladorPayload, simulador_padrao, simulate

USER = {"id": 1, "nome": "Ana", "email": "ana@teste.com"}
PROFILE = {"valor_disponivel_investimento": 800, "tolerancia_risco": "moderado"}


def payload(**overrides):
    data = {"valor_inicial": 0, "aporte_mensal": 800, "meses": 12, "tolerancia_risco": "moderado"}
    data.update(overrides)
    return SimuladorPayload(**data)


def run(**overrides):
    # Chama o endpoint direto, sem subir o servidor nem acessar o banco.
    return simulate(payload(**overrides), (USER, PROFILE))


class SimuladorApiTest(unittest.TestCase):
    def test_padrao_vem_do_perfil(self):
        padrao = simulador_padrao(PROFILE)
        self.assertEqual(padrao["aporte_mensal"], 800)
        self.assertEqual(padrao["valor_inicial"], 0)
        self.assertEqual(padrao["tolerancia_risco"], "moderado")

    def test_dados_do_perfil_sao_identificados(self):
        self.assertTrue(run()["dados_do_perfil"])

    def test_alterar_valor_ou_risco_vira_cenario_hipotetico(self):
        self.assertFalse(run(aporte_mensal=1500)["dados_do_perfil"])
        self.assertFalse(run(valor_inicial=2000)["dados_do_perfil"])
        self.assertFalse(run(tolerancia_risco="arrojado")["dados_do_perfil"])

    def test_prazo_e_inflacao_nao_contam_como_alteracao_do_perfil(self):
        self.assertTrue(run(meses=36, inflacao_anual_pct=4.5)["dados_do_perfil"])

    def test_resposta_traz_taxas_e_resultados(self):
        resposta = run()
        self.assertIn("selic", resposta["taxas"])
        self.assertTrue(any(item["elegivel"] for item in resposta["resultados"]))
        self.assertEqual({item["risco"] for item in resposta["resultados"]} <= {"baixo", "medio"}, True)

    def test_resposta_traz_a_serie_mensal_para_os_graficos(self):
        item = next(i for i in run(meses=36)["resultados"] if i["elegivel"])
        for cenario in ("pessimista", "base", "otimista"):
            serie = item["cenarios"][cenario]["serie"]
            self.assertEqual(len(serie["liquido"]), 37)
            self.assertEqual(len(serie["investido"]), 37)

    def test_inflacao_gera_valor_real(self):
        base = run(inflacao_anual_pct=4.5)["resultados"][0]["cenarios"]["base"]
        self.assertIn("valor_liquido_real", base)

    def test_zero_investido_e_recusado(self):
        with self.assertRaises(HTTPException) as erro:
            run(valor_inicial=0, aporte_mensal=0)
        self.assertEqual(erro.exception.status_code, 422)

    def test_payload_invalido(self):
        for campos in ({"meses": 0}, {"meses": 601}, {"valor_inicial": -1}, {"tolerancia_risco": "ousado"}):
            with self.assertRaises(ValidationError):
                payload(**campos)


if __name__ == "__main__":
    unittest.main()
