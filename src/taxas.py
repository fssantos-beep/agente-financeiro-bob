"""Taxas de referência (Selic, CDI e IPCA) buscadas no Banco Central pela API do SGS.

A consulta roda em segundo plano e nunca atrasa uma página: com o dado velho, o sistema usa o
último valor conhecido e atualiza por trás. O último valor fica em memória e num arquivo
temporário, para sobreviver a reinícios sem internet. Se a API falhar, o motivo vai para o log
e para a tela, e uma nova tentativa só acontece depois de 2 minutos. Valores absurdos são
rejeitados.

O campo `fonte` mostra de onde veio cada valor: "bcb" (atualizado), "cache" (última consulta,
já velha) ou "padrao" (constantes do simulador.py).

Opções no .env:
  TAXAS_AUTOMATICAS=0      usa só os valores padrão (bom para demonstrações)
  TAXAS_TTL_HORAS          quanto tempo o valor vale (padrão 6)
  TAXAS_TIMEOUT_SEGUNDOS   espera máxima por resposta (padrão 8)
  TAXAS_CACHE_ARQUIVO      onde guardar o último valor
  BCB_API_URL              outra origem para a consulta (usada nos testes)

Para testar a conexão: python -m src.taxas
"""

import json
import logging
import os
import platform
import ssl
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

import requests

from .simulador import TAXAS_REFERENCIA

# Séries do SGS: 432 = meta Selic (% a.a.), 4389 = CDI anualizado base 252 (% a.a.)
# e 13522 = IPCA acumulado em 12 meses (%).
SERIES = {"selic": 432, "cdi": 4389, "ipca_12m": 13522}
FAIXAS_VALIDAS = {"selic": (0, 60), "cdi": (0, 60), "ipca_12m": (-10, 100)}
URL_PADRAO = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{serie}/dados/ultimos/1?formato=json"
TIMEOUT_SEGUNDOS = 8  # o BCB às vezes demora; a busca é em segundo plano, então não atrasa a página
ESPERA_APOS_FALHA = 2 * 60  # segundos de espera antes de tentar de novo depois de uma falha

_log = logging.getLogger("bob.taxas")

# Versão do arquivo de cache. Arquivos de versões antigas (ou com data futura) são ignorados,
# para o cache velho não prender o sistema em valores gravados com regras anteriores.
VERSAO_CACHE = 2

_lock = threading.Lock()
_estado = {"valores": None, "buscado_em": 0.0, "falha_em": 0.0, "atualizando": False, "motivo": None}


def _ativado() -> bool:
    return os.getenv("TAXAS_AUTOMATICAS", "1").strip().lower() not in ("0", "false", "nao", "não", "off")


def _ttl() -> float:
    try:
        return float(os.getenv("TAXAS_TTL_HORAS", "6")) * 3600
    except ValueError:
        return 6 * 3600


def _timeout() -> float:
    try:
        return float(os.getenv("TAXAS_TIMEOUT_SEGUNDOS", TIMEOUT_SEGUNDOS))
    except ValueError:
        return TIMEOUT_SEGUNDOS


def motivo_da_falha(erro: Exception) -> str:
    """Explica em poucas palavras, em português, por que a consulta ao Banco Central falhou."""
    excecoes = requests.exceptions
    if isinstance(erro, excecoes.Timeout):
        return f"tempo esgotado: o Banco Central não respondeu em {_timeout():g} s"
    if isinstance(erro, excecoes.SSLError):
        return "erro de certificado SSL (rede, proxy ou antivírus pode estar interceptando a conexão)"
    if isinstance(erro, excecoes.ProxyError):
        return "erro de proxy na conexão"
    if isinstance(erro, excecoes.ConnectionError):
        return "sem conexão com o Banco Central (internet, DNS ou firewall)"
    if isinstance(erro, excecoes.HTTPError):
        resposta = getattr(erro, "response", None)
        status = getattr(resposta, "status_code", None)
        return (
            f"o Banco Central respondeu com erro HTTP {status}" if status else "o Banco Central respondeu com erro HTTP"
        )
    if isinstance(erro, (ValueError, KeyError, IndexError, TypeError)):
        return "resposta inesperada do Banco Central"
    return f"erro inesperado ({type(erro).__name__})"


def _arquivo_cache() -> Path:
    return Path(os.getenv("TAXAS_CACHE_ARQUIVO") or Path(tempfile.gettempdir()) / "bob_taxas_cache.json")


def _buscar_serie(nome: str):
    """Consulta o último valor de uma série no Banco Central. Devolve (valor, data ISO) ou levanta erro."""
    url = os.getenv("BCB_API_URL", URL_PADRAO).format(serie=SERIES[nome])
    resposta = requests.get(
        url, timeout=_timeout(), headers={"Accept": "application/json", "User-Agent": "bob-agente-financeiro/1.0"}
    )
    resposta.raise_for_status()
    # a API devolve uma lista: [{"data": "DD/MM/AAAA", "valor": "13.75"}]
    dados = resposta.json()
    if not dados:
        raise ValueError(f"resposta vazia na série {nome}")
    ultimo = dados[-1]
    try:
        valor = Decimal(str(ultimo["valor"]).strip().replace(",", "."))
    except (InvalidOperation, KeyError) as erro:
        raise ValueError(f"valor inválido na série {nome}: {ultimo!r}") from erro
    minimo, maximo = FAIXAS_VALIDAS[nome]
    if not valor.is_finite() or not minimo <= valor <= maximo:
        raise ValueError(f"valor fora do esperado na série {nome}: {valor}")
    return valor, datetime.strptime(ultimo["data"], "%d/%m/%Y").date().isoformat()


def _hoje() -> date:
    return date.today()


def _salvar_arquivo(valores: dict, buscado_em: float) -> None:
    try:
        conteudo = {
            "selic": str(valores["selic"]),
            "cdi": str(valores["cdi"]),
            "ipca_12m": None if valores.get("ipca_12m") is None else str(valores["ipca_12m"]),
            "data_referencia": valores["data_referencia"],
            "datas": valores.get("datas", {}),
            "buscado_em": buscado_em,
            "versao": VERSAO_CACHE,
        }
        _arquivo_cache().write_text(json.dumps(conteudo), encoding="utf-8")
    except OSError:
        pass  # sem permissão para gravar: o cache em memória continua funcionando


def _ler_arquivo():
    """Lê o último valor salvo em disco. Devolve (valores, momento da busca) ou (None, 0)."""
    try:
        dados = json.loads(_arquivo_cache().read_text(encoding="utf-8"))
        if not isinstance(dados, dict):
            return None, 0.0
        if dados.get("versao") != VERSAO_CACHE or str(dados["data_referencia"]) > _hoje().isoformat():
            return None, 0.0  # arquivo de versão antiga ou com data futura: não dá para confiar
        valores = {
            "selic": Decimal(dados["selic"]),
            "cdi": Decimal(dados["cdi"]),
            "ipca_12m": None if dados.get("ipca_12m") is None else Decimal(dados["ipca_12m"]),
            "data_referencia": str(dados["data_referencia"]),
            "datas": dados["datas"] if isinstance(dados.get("datas"), dict) else {},  # arquivos antigos não têm "datas"
        }
        return valores, float(dados["buscado_em"])
    except (OSError, ValueError, KeyError, TypeError, InvalidOperation):
        return None, 0.0


def _registrar_falha(serie: str, erro: Exception) -> None:
    motivo = motivo_da_falha(erro)
    _log.warning(
        "Falha ao consultar a série %s do Banco Central: %s [%s: %s]", serie, motivo, type(erro).__name__, erro
    )
    with _lock:
        _estado.update(falha_em=time.time(), atualizando=False, motivo=motivo)


def atualizar() -> bool:
    """Consulta o Banco Central agora. Devolve True se Selic e CDI foram atualizados."""
    with ThreadPoolExecutor(max_workers=len(SERIES)) as pool:
        futuros = {nome: pool.submit(_buscar_serie, nome) for nome in SERIES}
        obrigatorias = {}
        for nome in ("selic", "cdi"):
            try:
                obrigatorias[nome] = futuros[nome].result()
            except Exception as erro:
                _registrar_falha(nome, erro)
                return False
        try:
            ipca, data_ipca = futuros["ipca_12m"].result()
        except Exception as erro:
            ipca = data_ipca = None  # o IPCA é opcional: se falhar, fica o anterior (se existir)
            _log.warning("Não foi possível consultar o IPCA no Banco Central: %s", motivo_da_falha(erro))

    # A série da meta Selic pode vir com data futura (a da próxima reunião do Copom, repetindo a meta atual).
    # Por isso a data da Selic nunca passa de hoje. A data mostrada na tela é a do CDI, que é uma
    # observação diária real (o último dia útil divulgado).
    hoje = _hoje().isoformat()
    data_selic = min(obrigatorias["selic"][1], hoje)
    data_cdi = obrigatorias["cdi"][1]

    with _lock:
        anterior = _estado["valores"] or {}
        valores = {
            "selic": obrigatorias["selic"][0],
            "cdi": obrigatorias["cdi"][0],
            "ipca_12m": ipca if ipca is not None else anterior.get("ipca_12m"),
            "data_referencia": data_cdi,
            "datas": {
                "selic": data_selic,
                "cdi": data_cdi,
                "ipca_12m": data_ipca if ipca is not None else (anterior.get("datas") or {}).get("ipca_12m"),
            },
        }
        _estado.update(valores=valores, buscado_em=time.time(), falha_em=0.0, atualizando=False, motivo=None)
    _salvar_arquivo(valores, _estado["buscado_em"])
    return True


def _iniciar_thread() -> None:
    threading.Thread(target=atualizar, daemon=True, name="atualiza-taxas").start()


def iniciar() -> None:
    """Chamado ao ligar o servidor: começa a buscar as taxas sem esperar o primeiro acesso."""
    obter_taxas()


def obter_taxas() -> dict:
    """Devolve as taxas de referência: selic, cdi, ipca_12m, data_referencia, fonte e dados de status.

    Nunca bloqueia nem levanta erro por falha de rede. Selic e CDI são Decimal; ipca_12m pode ser None.
    """
    if not _ativado():
        return {
            **TAXAS_REFERENCIA,
            "ipca_12m": None,
            "datas": {},
            "fonte": "padrao",
            "automatico": False,
            "atualizando": False,
            "motivo": None,
        }

    agora = time.time()
    with _lock:
        if _estado["valores"] is None:
            valores, buscado_em = _ler_arquivo()
            if valores:
                _estado.update(valores=valores, buscado_em=buscado_em)
        valores, buscado_em, motivo = _estado["valores"], _estado["buscado_em"], _estado["motivo"]
        vencido = valores is None or agora - buscado_em > _ttl()
        em_pausa = agora - _estado["falha_em"] < ESPERA_APOS_FALHA
        iniciar_busca = vencido and not em_pausa and not _estado["atualizando"]
        if iniciar_busca:
            _estado["atualizando"] = True
    if iniciar_busca:
        _iniciar_thread()
    # "atualizando" vale enquanto há uma consulta em andamento; "motivo" explica a última falha, se houve
    status = {"automatico": True, "atualizando": iniciar_busca or _estado["atualizando"]}

    if valores is None:
        return {**TAXAS_REFERENCIA, "ipca_12m": None, "datas": {}, "fonte": "padrao", "motivo": motivo, **status}
    fonte = "bcb" if agora - buscado_em <= _ttl() else "cache"
    return {**valores, "fonte": fonte, "motivo": None if fonte == "bcb" else motivo, **status}


def _resetar() -> None:
    """Zera o estado em memória (para os testes)."""
    with _lock:
        _estado.update(valores=None, buscado_em=0.0, falha_em=0.0, atualizando=False, motivo=None)


def _situacao_cache() -> str:
    caminho = _arquivo_cache()
    if not caminho.exists():
        return f"{caminho} (ainda não existe)"
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return f"{caminho} (ilegível: será ignorado)"
    if not isinstance(dados, dict):
        return f"{caminho} (ilegível: será ignorado)"
    if dados.get("versao") != VERSAO_CACHE:
        return f"{caminho} (formato de uma versão antiga: será ignorado e substituído)"
    if str(dados.get("data_referencia", "")) > _hoje().isoformat():
        return f"{caminho} (data de referência futura: será ignorado e substituído)"
    idade = (time.time() - float(dados.get("buscado_em", 0))) / 3600
    return f"{caminho} (válido, gravado há {idade:.1f} h; dados de {dados.get('data_referencia')})"


def diagnosticar() -> int:
    """Testa a conexão com o Banco Central e explica o resultado. Uso: python -m src.taxas"""
    print("Diagnóstico das taxas automáticas (API do Banco Central)\n")
    print(
        f"Python {sys.version.split()[0]} em {platform.system()} | "
        f"requests {requests.__version__} | {ssl.OPENSSL_VERSION}"
    )
    proxies = {
        k: v for k, v in os.environ.items() if k.lower() in ("http_proxy", "https_proxy", "all_proxy", "no_proxy")
    }
    print(f"Proxy configurado no ambiente: {proxies or 'nenhum'}")
    print(
        f"TAXAS_AUTOMATICAS={os.getenv('TAXAS_AUTOMATICAS', '(não definida: ligada)')} | timeout de {_timeout():g} s\n"
    )
    print(f"Arquivo de cache: {_situacao_cache()}\n")
    falhas = 0
    for nome, codigo in SERIES.items():
        inicio = time.time()
        try:
            valor, data = _buscar_serie(nome)
            futura = "  <- data futura: o sistema usa a data de hoje no lugar" if data > _hoje().isoformat() else ""
            print(
                f"[OK]    {nome:9} série {codigo:>5}: {valor}  (dados de {data}, {time.time() - inicio:.1f} s){futura}"
            )
        except Exception as erro:
            falhas += 1
            print(
                f"[FALHA] {nome:9} série {codigo:>5}: {motivo_da_falha(erro)}\n"
                f"        detalhe técnico: {type(erro).__name__}: {erro}"
            )
    if falhas:
        print(
            "\nO que fazer: abra no navegador "
            "https://api.bcb.gov.br/dados/serie/bcdata.sgs.432/dados/ultimos/1?formato=json"
        )
        print("- Se abrir lá e falhar aqui: suspeite de proxy, antivírus ou firewall bloqueando o Python.")
        print(
            "- Se também não abrir no navegador: o problema é a rede ou o Banco Central está fora do ar. "
            "O sistema segue com os"
        )
        print("  valores padrão e tenta de novo sozinho.")
    else:
        print(
            "\nTudo certo: o sistema consegue buscar as taxas. "
            "Se a tela ainda mostra valores padrão, reinicie o servidor."
        )
    return 1 if falhas else 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    raise SystemExit(diagnosticar())
