import contextlib
import io
import json
import os
import tempfile
import time
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("TAXAS_AUTOMATICAS", "0")

from src import main, taxas
from src.chatbot import load_products
from src.simulador import TAXAS_REFERENCIA, comparar, descrever_simulacao


class RespostaFalsa:
    def __init__(self, dados, status=200):
        self.dados, self.status = dados, status
        self.status_code = status

    def raise_for_status(self):
        if self.status >= 400:
            raise taxas.requests.HTTPError(f"HTTP {self.status}", response=self)  # como faz a biblioteca de verdade

    def json(self):
        return self.dados


def respostas(selic="13.75", cdi="13.65", ipca="4.14", data="16/10/2026", data_ipca=None):
    valores = {432: selic, 4389: cdi, 13522: ipca}

    def falso_get(url, **kwargs):
        serie = int(url.split("sgs.")[1].split("/")[0])
        return RespostaFalsa([{"data": data_ipca if (serie == 13522 and data_ipca) else data, "valor": valores[serie]}])

    return falso_get


class BaseDeTeste(unittest.TestCase):
    def setUp(self):
        self.pasta = tempfile.TemporaryDirectory()
        ambiente = {"TAXAS_AUTOMATICAS": "1", "TAXAS_CACHE_ARQUIVO": str(Path(self.pasta.name) / "cache.json")}
        self.ambiente = patch.dict(os.environ, ambiente)
        self.ambiente.start()
        taxas._resetar()
        self.threads = []
        self.patch_thread = patch.object(taxas, "_iniciar_thread", lambda: self.threads.append(1))
        self.patch_thread.start()

    def tearDown(self):
        self.patch_thread.stop()
        self.ambiente.stop()
        self.pasta.cleanup()
        taxas._resetar()


class ConsultaAoBancoCentralTest(BaseDeTeste):
    def test_usa_as_series_e_o_formato_da_api_do_bcb(self):
        urls = []

        def falso_get(url, **kwargs):
            urls.append((url, kwargs))
            return RespostaFalsa([{"data": "16/10/2026", "valor": "13.75"}])

        with patch.object(taxas.requests, "get", falso_get):
            valor, data = taxas._buscar_serie("selic")
        self.assertEqual((valor, data), (Decimal("13.75"), "2026-10-16"))
        url, kwargs = urls[0]
        self.assertIn("bcdata.sgs.432/dados/ultimos/1?formato=json", url)
        self.assertTrue(url.startswith("https://api.bcb.gov.br/"))
        self.assertEqual(kwargs["timeout"], taxas.TIMEOUT_SEGUNDOS)

    def test_codigos_das_series(self):
        self.assertEqual(taxas.SERIES, {"selic": 432, "cdi": 4389, "ipca_12m": 13522})

    def test_aceita_virgula_decimal(self):
        with patch.object(taxas.requests, "get", respostas(selic="13,75")):
            self.assertEqual(taxas._buscar_serie("selic")[0], Decimal("13.75"))

    def test_rejeita_valores_invalidos(self):
        for ruim in ("abc", "", "999", "-1", "NaN", "Infinity"):
            with patch.object(taxas.requests, "get", respostas(selic=ruim)):
                with self.assertRaises(ValueError, msg=ruim):
                    taxas._buscar_serie("selic")

    def test_rejeita_resposta_vazia_data_invalida_e_erro_http(self):
        with patch.object(taxas.requests, "get", lambda *a, **k: RespostaFalsa([])):
            with self.assertRaises(ValueError):
                taxas._buscar_serie("selic")
        with patch.object(
            taxas.requests, "get", lambda *a, **k: RespostaFalsa([{"data": "2026-10-16", "valor": "13.75"}])
        ):
            with self.assertRaises(ValueError):
                taxas._buscar_serie("selic")
        with patch.object(taxas.requests, "get", lambda *a, **k: RespostaFalsa([], status=503)):
            with self.assertRaises(Exception):
                taxas._buscar_serie("selic")

    def test_ipca_aceita_valor_negativo_pequeno(self):
        with patch.object(taxas.requests, "get", respostas(ipca="-0.3")):
            self.assertEqual(taxas._buscar_serie("ipca_12m")[0], Decimal("-0.3"))


class AtualizacaoETentativasTest(BaseDeTeste):
    def test_atualizar_com_sucesso_publica_os_valores_do_bcb(self):
        with patch.object(taxas.requests, "get", respostas()):
            self.assertTrue(taxas.atualizar())
        t = taxas.obter_taxas()
        self.assertEqual((t["selic"], t["cdi"], t["ipca_12m"]), (Decimal("13.75"), Decimal("13.65"), Decimal("4.14")))
        self.assertEqual((t["fonte"], t["data_referencia"]), ("bcb", "2026-10-16"))
        self.assertEqual(self.threads, [])  # valor fresco: não há nova busca

    def test_sem_nenhum_dado_usa_os_padroes_e_dispara_a_busca(self):
        t = taxas.obter_taxas()
        self.assertEqual(t["fonte"], "padrao")
        self.assertEqual((t["selic"], t["cdi"]), (TAXAS_REFERENCIA["selic"], TAXAS_REFERENCIA["cdi"]))
        self.assertEqual(len(self.threads), 1)

    def test_so_uma_busca_por_vez(self):
        for _ in range(5):
            taxas.obter_taxas()
        self.assertEqual(len(self.threads), 1)

    def test_falha_total_nao_quebra_e_aguarda_antes_de_tentar_de_novo(self):
        def falha(*args, **kwargs):
            raise taxas.requests.ConnectionError("sem internet")

        with patch.object(taxas.requests, "get", falha):
            self.assertFalse(taxas.atualizar())
        self.assertEqual(taxas.obter_taxas()["fonte"], "padrao")
        self.assertEqual(self.threads, [])  # em pausa depois da falha

    def test_depois_da_pausa_tenta_de_novo(self):
        taxas._estado["falha_em"] = time.time() - taxas.ESPERA_APOS_FALHA - 1
        taxas.obter_taxas()
        self.assertEqual(len(self.threads), 1)

    def test_valor_velho_continua_sendo_usado_como_cache(self):
        with patch.object(taxas.requests, "get", respostas(selic="14.25", cdi="14.15")):
            taxas.atualizar()
        taxas._estado["buscado_em"] = time.time() - 7 * 3600  # passou do prazo de 6 horas
        t = taxas.obter_taxas()
        self.assertEqual((t["fonte"], t["selic"]), ("cache", Decimal("14.25")))
        self.assertEqual(len(self.threads), 1)  # pede atualização, mas já responde com o último valor

    def test_falha_depois_de_sucesso_mantem_os_valores_anteriores(self):
        with patch.object(taxas.requests, "get", respostas(selic="14.25", cdi="14.15")):
            taxas.atualizar()
        with patch.object(taxas.requests, "get", lambda *a, **k: RespostaFalsa([], status=500)):
            self.assertFalse(taxas.atualizar())
        self.assertEqual(taxas.obter_taxas()["selic"], Decimal("14.25"))

    def test_sem_ipca_o_resto_atualiza_e_o_ipca_anterior_e_mantido(self):
        with patch.object(taxas.requests, "get", respostas(ipca="4.14")):
            taxas.atualizar()

        def sem_ipca(url, **kwargs):
            if "sgs.13522" in url:
                raise taxas.requests.ConnectionError("fora do ar")
            return respostas(selic="13.5", cdi="13.4")(url)

        with patch.object(taxas.requests, "get", sem_ipca):
            self.assertTrue(taxas.atualizar())
        t = taxas.obter_taxas()
        self.assertEqual((t["selic"], t["ipca_12m"]), (Decimal("13.5"), Decimal("4.14")))

    def test_ipca_ausente_desde_o_inicio_fica_none(self):
        def sem_ipca(url, **kwargs):
            if "sgs.13522" in url:
                raise taxas.requests.ConnectionError("fora do ar")
            return respostas()(url)

        with patch.object(taxas.requests, "get", sem_ipca):
            self.assertTrue(taxas.atualizar())
        self.assertIsNone(taxas.obter_taxas()["ipca_12m"])

    def test_sem_selic_ou_cdi_nada_e_atualizado(self):
        def sem_cdi(url, **kwargs):
            if "sgs.4389" in url:
                raise taxas.requests.ConnectionError("fora do ar")
            return respostas()(url)

        with patch.object(taxas.requests, "get", sem_cdi):
            self.assertFalse(taxas.atualizar())
        self.assertEqual(taxas.obter_taxas()["fonte"], "padrao")


class CacheEmArquivoTest(BaseDeTeste):
    def test_valores_sobrevivem_a_um_reinicio(self):
        with patch.object(taxas.requests, "get", respostas()):
            taxas.atualizar()
        taxas._resetar()  # como se o servidor tivesse sido reiniciado, sem internet
        t = taxas.obter_taxas()
        self.assertEqual((t["selic"], t["fonte"]), (Decimal("13.75"), "bcb"))
        self.assertEqual(self.threads, [])

    def test_arquivo_antigo_vira_cache_e_pede_atualizacao(self):
        with patch.object(taxas.requests, "get", respostas()):
            taxas.atualizar()
        caminho = Path(os.environ["TAXAS_CACHE_ARQUIVO"])
        dados = json.loads(caminho.read_text())
        dados["buscado_em"] = time.time() - 48 * 3600
        caminho.write_text(json.dumps(dados))
        taxas._resetar()
        self.assertEqual(taxas.obter_taxas()["fonte"], "cache")
        self.assertEqual(len(self.threads), 1)

    def test_arquivo_corrompido_e_ignorado(self):
        for conteudo in ("{ruim", "[]", json.dumps({"selic": "abc"}), ""):
            Path(os.environ["TAXAS_CACHE_ARQUIVO"]).write_text(conteudo)
            taxas._resetar()
            self.assertEqual(taxas.obter_taxas()["fonte"], "padrao", conteudo)

    def test_sem_permissao_para_gravar_nao_quebra(self):
        with patch.dict(os.environ, {"TAXAS_CACHE_ARQUIVO": "/proc/nao-existe/cache.json"}):
            with patch.object(taxas.requests, "get", respostas()):
                self.assertTrue(taxas.atualizar())
        self.assertEqual(taxas.obter_taxas()["fonte"], "bcb")


class ConfiguracaoTest(BaseDeTeste):
    def test_desligar_pelo_env_usa_so_os_padroes_e_nunca_busca(self):
        with patch.object(taxas.requests, "get", respostas()):
            taxas.atualizar()
        for valor in ("0", "false", "off"):
            with patch.dict(os.environ, {"TAXAS_AUTOMATICAS": valor}):
                t = taxas.obter_taxas()
                self.assertEqual((t["fonte"], t["selic"]), ("padrao", TAXAS_REFERENCIA["selic"]), valor)
        self.assertEqual(self.threads, [])

    def test_prazo_configuravel_e_valor_invalido_volta_ao_padrao(self):
        with patch.dict(os.environ, {"TAXAS_TTL_HORAS": "1"}):
            self.assertEqual(taxas._ttl(), 3600)
        with patch.dict(os.environ, {"TAXAS_TTL_HORAS": "abc"}):
            self.assertEqual(taxas._ttl(), 6 * 3600)

    def test_url_pode_ser_trocada_pelo_env(self):
        urls = []

        def falso_get(url, **kwargs):
            urls.append(url)
            return RespostaFalsa([{"data": "16/10/2026", "valor": "13.75"}])

        with patch.dict(os.environ, {"BCB_API_URL": "http://local/s/{serie}"}), patch.object(
            taxas.requests, "get", falso_get
        ):
            taxas._buscar_serie("cdi")
        self.assertEqual(urls, ["http://local/s/4389"])


class DatasDasTaxasTest(BaseDeTeste):
    """A série da meta Selic pode vir com data futura (a da próxima reunião do Copom); a tela não pode exibi-la."""

    def buscar(self, selic_data, cdi_data="16/10/2026", ipca_data="01/09/2026", hoje=date(2026, 10, 19)):
        def falso_get(url, **kwargs):
            serie = int(url.split("sgs.")[1].split("/")[0])
            return RespostaFalsa(
                [
                    {
                        "data": {432: selic_data, 4389: cdi_data, 13522: ipca_data}[serie],
                        "valor": {432: "13.75", 4389: "13.65", 13522: "4.58"}[serie],
                    }
                ]
            )

        with patch.object(taxas, "_hoje", return_value=hoje), patch.object(taxas.requests, "get", falso_get):
            self.assertTrue(taxas.atualizar())
        return taxas.obter_taxas()

    def test_data_futura_da_selic_e_limitada_a_hoje(self):
        t = self.buscar(selic_data="04/11/2026")  # o caso real: a série traz a data da próxima reunião do Copom
        self.assertEqual(t["datas"]["selic"], "2026-10-19")
        self.assertEqual(t["selic"], Decimal("13.75"))  # o valor continua sendo a meta em vigor

    def test_data_de_referencia_e_a_do_cdi_nunca_a_futura(self):
        t = self.buscar(selic_data="04/11/2026")
        self.assertEqual(t["data_referencia"], "2026-10-16")
        self.assertLessEqual(t["data_referencia"], "2026-10-19")

    def test_data_passada_da_selic_e_mantida(self):
        t = self.buscar(selic_data="17/09/2026")  # início da vigência: também é uma data válida
        self.assertEqual(t["datas"]["selic"], "2026-09-17")
        self.assertEqual(t["data_referencia"], "2026-10-16")

    def test_ipca_guarda_o_mes_de_referencia_proprio(self):
        t = self.buscar(selic_data="04/11/2026")
        self.assertEqual(t["datas"], {"selic": "2026-10-19", "cdi": "2026-10-16", "ipca_12m": "2026-09-01"})

    def test_datas_sobrevivem_ao_reinicio_e_arquivo_antigo_sem_datas_funciona(self):
        self.buscar(selic_data="04/11/2026")
        caminho = Path(os.environ["TAXAS_CACHE_ARQUIVO"])
        taxas._resetar()
        self.assertEqual(taxas.obter_taxas()["datas"]["ipca_12m"], "2026-09-01")
        dados = json.loads(caminho.read_text())
        del dados["datas"]
        caminho.write_text(json.dumps(dados))
        taxas._resetar()
        t = taxas.obter_taxas()
        self.assertEqual((t["datas"], t["selic"]), ({}, Decimal("13.75")))

    def test_ipca_ausente_mantem_a_data_do_ipca_anterior(self):
        self.buscar(selic_data="04/11/2026")

        def sem_ipca(url, **kwargs):
            if "sgs.13522" in url:
                raise taxas.requests.ConnectionError("fora do ar")
            return respostas()(url)

        with patch.object(taxas.requests, "get", sem_ipca):
            taxas.atualizar()
        t = taxas.obter_taxas()
        self.assertEqual((t["ipca_12m"], t["datas"]["ipca_12m"]), (Decimal("4.58"), "2026-09-01"))

    def test_diagnostico_avisa_quando_a_data_e_futura(self):
        saida = io.StringIO()
        with patch.object(taxas, "_hoje", return_value=date(2026, 10, 19)), patch.object(
            taxas.requests, "get", respostas(data="04/11/2026")
        ):
            with contextlib.redirect_stdout(saida):
                taxas.diagnosticar()
        self.assertIn("data futura", saida.getvalue())


class CacheDeVersaoAntigaTest(BaseDeTeste):
    """O cache gravado por uma versão anterior (com a data futura da Selic) não pode prender a tela em dados antigos."""

    def gravar(self, **campos):
        dados = {
            "selic": "13.75",
            "cdi": "13.65",
            "ipca_12m": None,
            "data_referencia": "2026-11-04",
            "buscado_em": time.time() - 3600,
        }
        dados.update(campos)
        Path(os.environ["TAXAS_CACHE_ARQUIVO"]).write_text(json.dumps(dados))
        taxas._resetar()

    def test_arquivo_da_versao_antiga_e_ignorado_e_dispara_nova_busca(self):
        self.gravar()  # sem "versao": é exatamente o arquivo que as versões anteriores gravavam
        t = taxas.obter_taxas()
        self.assertEqual(t["fonte"], "padrao")
        self.assertEqual(len(self.threads), 1)

    def test_arquivo_com_data_de_referencia_futura_e_ignorado_mesmo_na_versao_atual(self):
        with patch.object(taxas, "_hoje", return_value=date(2026, 10, 19)):
            self.gravar(versao=taxas.VERSAO_CACHE)
            self.assertEqual(taxas.obter_taxas()["fonte"], "padrao")

    def test_arquivo_valido_da_versao_atual_continua_sendo_usado(self):
        with patch.object(taxas, "_hoje", return_value=date(2026, 10, 19)):
            self.gravar(versao=taxas.VERSAO_CACHE, data_referencia="2026-10-16", ipca_12m="4.58")
            t = taxas.obter_taxas()
        self.assertEqual((t["fonte"], t["data_referencia"], t["ipca_12m"]), ("bcb", "2026-10-16", Decimal("4.58")))
        self.assertEqual(self.threads, [])

    def test_depois_da_atualizacao_o_arquivo_novo_tem_a_versao_e_a_data_correta(self):
        self.gravar()
        with patch.object(taxas, "_hoje", return_value=date(2026, 10, 19)), patch.object(
            taxas.requests, "get", respostas(data="04/11/2026", ipca="4.58", data_ipca="01/09/2026")
        ):
            # selic e cdi com a mesma data futura só no teste; o que importa é o formato gravado
            taxas.atualizar()
        gravado = json.loads(Path(os.environ["TAXAS_CACHE_ARQUIVO"]).read_text())
        self.assertEqual(gravado["versao"], taxas.VERSAO_CACHE)
        self.assertEqual(gravado["datas"]["ipca_12m"], "2026-09-01")

    def test_diagnostico_informa_a_situacao_do_cache(self):
        for preparar, esperado in (
            (lambda: Path(os.environ["TAXAS_CACHE_ARQUIVO"]).unlink(missing_ok=True), "ainda não existe"),
            (lambda: self.gravar(), "versão antiga"),
            (lambda: Path(os.environ["TAXAS_CACHE_ARQUIVO"]).write_text("{ruim"), "ilegível"),
        ):
            preparar()
            self.assertIn(esperado, taxas._situacao_cache())
        with patch.object(taxas, "_hoje", return_value=date(2026, 10, 19)):
            self.gravar(versao=taxas.VERSAO_CACHE)
            self.assertIn("data de referência futura", taxas._situacao_cache())
            self.gravar(versao=taxas.VERSAO_CACHE, data_referencia="2026-10-16")
            self.assertIn("válido", taxas._situacao_cache())


class MotivoDaFalhaTest(unittest.TestCase):
    def test_cada_tipo_de_erro_tem_uma_explicacao_clara(self):
        e = taxas.requests.exceptions
        resposta = type("R", (), {"status_code": 503})()
        casos = [
            (e.ReadTimeout("x"), "tempo esgotado"),
            (
                e.ConnectTimeout("x"),
                "tempo esgotado",
            ),  # é Timeout e ConnectionError ao mesmo tempo: vale o tempo esgotado
            (e.SSLError("x"), "certificado SSL"),
            (e.ProxyError("x"), "proxy"),
            (e.ConnectionError("x"), "sem conexão"),
            (e.HTTPError("x", response=resposta), "erro HTTP 503"),
            (e.HTTPError("x"), "erro HTTP"),
            (ValueError("x"), "resposta inesperada"),
            (KeyError("x"), "resposta inesperada"),
            (RuntimeError("x"), "erro inesperado (RuntimeError)"),
        ]
        for erro, esperado in casos:
            self.assertIn(esperado, taxas.motivo_da_falha(erro), type(erro).__name__)

    def test_prazo_do_timeout_aparece_na_mensagem_e_e_configuravel(self):
        with patch.dict(os.environ, {"TAXAS_TIMEOUT_SEGUNDOS": "12"}):
            self.assertEqual(taxas._timeout(), 12)
            self.assertIn("12 s", taxas.motivo_da_falha(taxas.requests.exceptions.ReadTimeout("x")))
        with patch.dict(os.environ, {"TAXAS_TIMEOUT_SEGUNDOS": "abc"}):
            self.assertEqual(taxas._timeout(), taxas.TIMEOUT_SEGUNDOS)


class FalhasVisiveisTest(BaseDeTeste):
    def falha(self, erro):
        def levanta(*args, **kwargs):
            raise erro

        return levanta

    def test_motivo_chega_ao_resultado_depois_de_uma_falha(self):
        with patch.object(taxas.requests, "get", self.falha(taxas.requests.ConnectionError("dns"))):
            self.assertFalse(taxas.atualizar())
        t = taxas.obter_taxas()
        self.assertEqual(t["fonte"], "padrao")
        self.assertIn("sem conexão", t["motivo"])
        self.assertFalse(t["atualizando"])  # em pausa: nada em andamento
        self.assertTrue(t["automatico"])

    def test_antes_da_primeira_busca_aparece_como_atualizando_sem_motivo(self):
        t = taxas.obter_taxas()
        self.assertEqual((t["fonte"], t["atualizando"], t["motivo"]), ("padrao", True, None))

    def test_sucesso_limpa_o_motivo(self):
        with patch.object(taxas.requests, "get", self.falha(taxas.requests.ConnectionError("dns"))):
            taxas.atualizar()
        with patch.object(taxas.requests, "get", respostas()):
            taxas.atualizar()
        t = taxas.obter_taxas()
        self.assertEqual((t["fonte"], t["motivo"]), ("bcb", None))

    def test_cache_velho_mostra_o_motivo_da_ultima_falha(self):
        with patch.object(taxas.requests, "get", respostas()):
            taxas.atualizar()
        taxas._estado["buscado_em"] = time.time() - 7 * 3600
        with patch.object(taxas.requests, "get", lambda *a, **k: RespostaFalsa([], status=503)):
            taxas.atualizar()
        t = taxas.obter_taxas()
        self.assertEqual(t["fonte"], "cache")
        self.assertIn("HTTP 503", t["motivo"])

    def test_falha_vai_para_o_log_do_servidor_com_o_detalhe_tecnico(self):
        with patch.object(
            taxas.requests, "get", self.falha(taxas.requests.exceptions.SSLError("CERTIFICATE_VERIFY_FAILED"))
        ):
            with self.assertLogs("bob.taxas", level="WARNING") as registro:
                taxas.atualizar()
        texto = "\n".join(registro.output)
        self.assertIn("série selic", texto)
        self.assertIn("certificado SSL", texto)
        self.assertIn("CERTIFICATE_VERIFY_FAILED", texto)

    def test_falha_so_do_ipca_gera_aviso_mas_nao_derruba_o_resto(self):
        def sem_ipca(url, **kwargs):
            if "sgs.13522" in url:
                raise taxas.requests.ConnectionError("fora do ar")
            return respostas()(url)

        with patch.object(taxas.requests, "get", sem_ipca):
            with self.assertLogs("bob.taxas", level="WARNING") as registro:
                self.assertTrue(taxas.atualizar())
        self.assertIn("IPCA", "\n".join(registro.output))
        self.assertIsNone(taxas.obter_taxas()["motivo"])

    def test_desligado_informa_que_nao_e_automatico(self):
        with patch.dict(os.environ, {"TAXAS_AUTOMATICAS": "0"}):
            t = taxas.obter_taxas()
        self.assertEqual((t["automatico"], t["atualizando"], t["motivo"]), (False, False, None))


class DiagnosticoTest(BaseDeTeste):
    def rodar(self):
        saida = io.StringIO()
        with contextlib.redirect_stdout(saida):
            codigo = taxas.diagnosticar()
        return codigo, saida.getvalue()

    def test_tudo_certo_devolve_zero_e_lista_as_tres_series(self):
        with patch.object(taxas.requests, "get", respostas()):
            codigo, texto = self.rodar()
        self.assertEqual(codigo, 0)
        self.assertEqual(texto.count("[OK]"), 3)
        self.assertIn("Tudo certo", texto)
        self.assertIn("série   432", texto)

    def test_falha_devolve_um_e_orienta_o_que_fazer(self):
        def levanta(*args, **kwargs):
            raise taxas.requests.exceptions.SSLError("certificado")

        with patch.object(taxas.requests, "get", levanta):
            codigo, texto = self.rodar()
        self.assertEqual(codigo, 1)
        self.assertEqual(texto.count("[FALHA]"), 3)
        self.assertIn("certificado SSL", texto)
        self.assertIn("detalhe técnico: SSLError", texto)
        self.assertIn("https://api.bcb.gov.br/dados/serie/bcdata.sgs.432", texto)
        self.assertIn("proxy", texto.lower())

    def test_mostra_o_ambiente_para_ajudar_no_diagnostico(self):
        with patch.dict(os.environ, {"HTTPS_PROXY": "http://proxy.local:8080"}), patch.object(
            taxas.requests, "get", respostas()
        ):
            _, texto = self.rodar()
        self.assertIn("Python", texto)
        self.assertIn("proxy.local", texto)


class IntegracaoComOSimuladorTest(unittest.TestCase):
    PERFIL = {"valor_disponivel_investimento": Decimal("1000"), "tolerancia_risco": "moderado"}
    USUARIO = {"id": 1, "nome": "Ana", "email": "a@a.com"}

    def taxas_falsas(self, selic, cdi, fonte="bcb", ipca=Decimal("4.14")):
        return {
            "selic": Decimal(selic),
            "cdi": Decimal(cdi),
            "ipca_12m": ipca,
            "data_referencia": "2026-10-16",
            "fonte": fonte,
        }

    def simular(self, taxas_do_dia):
        payload = main.SimuladorPayload(valor_inicial=0, aporte_mensal=1000, meses=24, tolerancia_risco="moderado")
        with patch.object(main, "obter_taxas", return_value=taxas_do_dia):
            return main.simulate(payload, (self.USUARIO, self.PERFIL))

    def test_o_simulador_usa_as_taxas_do_dia(self):
        alta = self.simular(self.taxas_falsas("15", "14.9"))
        baixa = self.simular(self.taxas_falsas("8", "7.9"))
        liquido = lambda r: next(i for i in r["resultados"] if i["produto"] == "Tesouro Selic")["cenarios"]["base"][
            "valor_liquido"
        ]
        self.assertGreater(liquido(alta), liquido(baixa))
        self.assertEqual(alta["taxas"]["selic"], 15.0)

    def test_resposta_informa_fonte_data_e_ipca(self):
        resposta = self.simular(self.taxas_falsas("13.75", "13.65"))
        self.assertEqual(
            resposta["taxas"],
            {
                "selic": 13.75,
                "cdi": 13.65,
                "ipca_12m": 4.14,
                "data_referencia": "2026-10-16",
                "datas": {},
                "fonte": "bcb",
                "automatico": False,
                "atualizando": False,
                "motivo": None,
            },
        )

    def test_ipca_ausente_vira_nulo_na_resposta(self):
        resposta = self.simular(self.taxas_falsas("13.75", "13.65", ipca=None))
        self.assertIsNone(resposta["taxas"]["ipca_12m"])

    def test_hipoteses_do_fundo_de_acoes_acompanham_o_cdi_do_dia(self):
        with patch.object(main, "obter_taxas", return_value=self.taxas_falsas("20", "19.9")):
            premissas = main.simulator_defaults((self.USUARIO, self.PERFIL))["premissas"]
        self.assertAlmostEqual(premissas["cenarios_variaveis"]["base"], 22.9)  # CDI + 3 p.p.

    def test_texto_enviado_ao_bob_cita_a_fonte_das_taxas(self):
        parametros = {
            "valor_inicial": 0,
            "aporte_mensal": 500,
            "meses": 12,
            "tolerancia_risco": "moderado",
            "inflacao_anual_pct": None,
        }
        for fonte, esperado in (
            ("bcb", "Banco Central, consulta automática"),
            ("cache", "última consulta bem-sucedida"),
            ("padrao", "valores padrão do sistema"),
        ):
            t = self.taxas_falsas("13.75", "13.65", fonte=fonte)
            resultados = comparar(load_products(), "moderado", 0, 500, 12, taxas=t, com_serie=False)
            texto = descrever_simulacao(parametros, True, resultados, taxas=t)
            self.assertIn(esperado, texto)
            self.assertIn("IPCA em 12 meses 4,14%", texto)
            self.assertIn("data: 16/10/2026", texto)


if __name__ == "__main__":
    unittest.main()
