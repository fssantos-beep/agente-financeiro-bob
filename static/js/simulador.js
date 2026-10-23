// Rótulos e formatadores da tela do simulador.
const riscoLabels = { baixo: "Baixo", medio: "Médio", alto: "Alto" };
const cenarioLabels = { pessimista: "Pessimista", base: "Base", otimista: "Otimista" };
const pct = (value) =>
    `${new Intl.NumberFormat("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value)}%`;

// Monta uma linha de tabela. celulas é uma lista de trechos de HTML, um por coluna (tag "th" para cabeçalhos).
const linhaTabela = (celulas, atributos = "", tag = "td") =>
    `<tr${atributos}>${celulas.map((celula) => `<${tag}>${celula}</${tag}>`).join("")}</tr>`;

const cartao = ([titulo, valor, detalhe]) =>
    '<article class="metric">' +
    `<span class="label">${titulo}</span><strong>${valor}</strong><small>${detalhe}</small>` +
    "</article>";

// padrao: valores do perfil; premissas: taxas usadas no cálculo; elegiveis: produtos simulados.
let padrao = null,
    premissas = null,
    taxas = null,
    resultado = null,
    elegiveis = [],
    selecionado = 0;
// ultimaSimulacao: parâmetros da última simulação, que é o que está na tela e o que o Bob enxerga.
let ultimaSimulacao = null,
    chatHistory = [],
    chatIniciado = false;
// bobPensando e simulando evitam envios repetidos enquanto uma resposta ainda está em andamento.
let bobPensando = false,
    simulando = false,
    chaveSimulacao = null;
const sugestoes = [
    "Qual produto parece mais adequado para mim?",
    "Por que o IR é diferente entre os produtos?",
    "O que muda no cenário pessimista?",
];
const formulario = () => $("#sim-form");

// Volta os campos para os valores salvos no perfil.
function preencherPadrao() {
    const form = formulario();
    form.valor_inicial.value = padrao.valor_inicial;
    form.aporte_mensal.value = padrao.aporte_mensal;
    form.tolerancia_risco.value = padrao.tolerancia_risco;
}

// A caixa libera a edição dos dados do perfil; ao desmarcar, os valores do perfil voltam.
function alternarEdicao() {
    const form = formulario();
    const livre = form.editar.checked;
    ["valor_inicial", "aporte_mensal", "tolerancia_risco"].forEach((name) => {
        form[name].disabled = !livre;
    });
    if (!livre) preencherPadrao();
    $("#sim-origem").textContent = livre
        ? "Você está testando valores diferentes dos do seu perfil. Nada disso é salvo."
        : "Usando os dados salvos no seu perfil (aporte mensal = valor disponível por mês).";
}

// A última simulação fica salva só nesta aba (sessionStorage): volta ao navegar entre as telas
// e some quando a sessão acaba. Nada vai para o banco, então não pesa no sistema.
function salvarSimulacao(payload) {
    try {
        sessionStorage.setItem(chaveSimulacao, JSON.stringify({ ...payload, editar: formulario().editar.checked }));
    } catch (_) {
        /* armazenamento indisponível: a simulação continua funcionando, só não é lembrada */
    }
}

function lerSimulacaoSalva() {
    try {
        const salvo = JSON.parse(sessionStorage.getItem(chaveSimulacao));
        const numeros = ["valor_inicial", "aporte_mensal", "meses"].every((chave) => Number.isFinite(salvo?.[chave]));
        const riscos = ["conservador", "moderado", "arrojado"].includes(salvo?.tolerancia_risco);
        return numeros && riscos ? salvo : null;
    } catch (_) {
        return null;
    }
}

// Texto com as taxas usadas e de onde vieram: Banco Central, última consulta, busca em andamento
// ou valores padrão (com o motivo, quando a consulta falhou).
function descricaoTaxas(t) {
    const data = t.data_referencia.split("-").reverse().join("/");
    const motivo = t.motivo ? ` (motivo: ${t.motivo})` : "";
    let origem;
    if (t.fonte === "bcb") origem = `Fonte: Banco Central do Brasil, dados de ${data}.`;
    else if (t.fonte === "cache")
        origem =
            `Fonte: última consulta ao Banco Central (dados de ${data}); ` +
            `não foi possível atualizar agora${motivo}.`;
    else if (t.atualizando) origem = "Buscando as taxas atualizadas no Banco Central…";
    else if (t.automatico === false)
        origem = `Atualização automática desligada: valores padrão do sistema (referência de ${data}).`;
    else
        origem =
            `Valores padrão do sistema (referência de ${data}); ` +
            `não foi possível consultar o Banco Central${motivo}.`;
    const meses = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"];
    // o IPCA é do mês de referência, não de hoje
    const dataIpca = t.datas && t.datas.ipca_12m ? t.datas.ipca_12m.split("-") : null;
    const mesIpca = dataIpca ? ` (${meses[Number(dataIpca[1]) - 1]}/${dataIpca[0]})` : "";
    const ipca =
        t.ipca_12m !== null && t.ipca_12m !== undefined ? ` · IPCA em 12 meses ${pct(t.ipca_12m)}${mesIpca}` : "";
    return `Selic ${pct(t.selic)} · CDI ${pct(t.cdi)}${ipca}. ${origem}`;
}

function renderTaxas() {
    if (!taxas) return;
    $("#sim-taxas").textContent = `Taxas de referência: ${descricaoTaxas(taxas)}`;
    const ipca = taxas.ipca_12m;
    formulario().inflacao_anual_pct.placeholder =
        ipca !== null && ipca !== undefined ? `IPCA 12 meses: ${pct(ipca)}` : "Ex.: 4,5";
}

// Logo depois de ligar o servidor a busca no Banco Central pode estar em andamento: tenta de novo algumas vezes.
let tentativasTaxas = 0;
async function atualizarTaxasSeBuscando() {
    if (!taxas || !taxas.atualizando || tentativasTaxas >= 6) return;
    tentativasTaxas += 1;
    await new Promise((resolver) => setTimeout(resolver, 2000));
    try {
        const data = await api("/api/simulador/padrao");
        taxas = data.taxas;
        premissas = data.premissas;
        renderTaxas();
        if (resultado) renderPremissas();
    } catch (_) {
        return;
    }
    atualizarTaxasSeBuscando();
}

function limparAviso() {
    $("#app-notice").textContent = "";
    $("#app-notice").className = "";
}

async function simular() {
    if (simulando) return;
    simulando = true;
    const form = formulario();
    const inflacao = form.inflacao_anual_pct.value;
    const payload = {
        valor_inicial: Number(form.valor_inicial.value),
        aporte_mensal: Number(form.aporte_mensal.value),
        meses: Number(form.meses.value),
        tolerancia_risco: form.tolerancia_risco.value,
        inflacao_anual_pct: inflacao === "" ? null : Number(inflacao),
    };
    const botao = form.querySelector("button");
    botao.disabled = true;
    try {
        resultado = await api("/api/simulador", { method: "POST", body: JSON.stringify(payload) });
        limparAviso();
        elegiveis = resultado.resultados.filter((item) => item.elegivel);
        selecionado = 0;
        taxas = resultado.taxas;
        renderTaxas();
        ultimaSimulacao = payload;
        salvarSimulacao(payload);
        renderResultado();
        iniciarConversa();
    } catch (error) {
        showNotice(error.message, "error");
    } finally {
        botao.disabled = false;
        simulando = false;
    }
}

// Seleciona um produto (pela tabela ou pelas barras) e atualiza tudo que depende dele.
function selecionarProduto(indice) {
    selecionado = indice;
    renderTabela();
    renderBarras();
    renderDetalhe();
}

function renderBarras() {
    Graficos.desenharBarras($("#grafico-barras"), elegiveis, selecionado, selecionarProduto);
}

function renderResultado() {
    const { parametros } = resultado;
    $("#sim-resultado").hidden = false;
    $("#sim-vazio").hidden = true;
    const origem = resultado.dados_do_perfil ? "Dados do seu perfil" : "Cenário hipotético";
    $("#sim-resumo").textContent =
        `${origem}: valor inicial de ${money(parametros.valor_inicial)}, ` +
        `aporte de ${money(parametros.aporte_mensal)} por mês, por ${parametros.meses} meses, ` +
        `perfil ${parametros.tolerancia_risco}. Clique em um produto para ver os detalhes.`;
    renderTabela();
    renderBarras();
    renderIndisponiveis();
    renderDetalhe();
    renderPremissas();
}

// Cada linha é um produto compatível com o risco; a primeira tem o maior líquido entre os de rentabilidade conhecida.
function renderTabela() {
    const cabecalho = linhaTabela(
        ["Produto", "Risco", "Investido", "IR", "Líquido (base)", "Pessimista", "Otimista"],
        "",
        "th"
    );
    const linhas = elegiveis.map((item, index) => {
        const base = item.cenarios.base;
        const destaque =
            index === 0 && !item.rentabilidade_variavel ? ' <span class="badge">Melhor retorno conhecido</span>' : "";
        const variavel = item.rentabilidade_variavel ? ' <span class="badge warn">Rentabilidade variável</span>' : "";
        const atributos = ` data-i="${index}" tabindex="0" class="${index === selecionado ? "selected" : ""}"`;
        return linhaTabela(
            [
                `<strong>${escapeHtml(item.produto)}</strong>${destaque}${variavel}`,
                riscoLabels[item.risco] || escapeHtml(item.risco),
                money(base.total_investido),
                money(base.ir),
                `<strong>${money(base.valor_liquido)}</strong>`,
                money(item.cenarios.pessimista.valor_liquido),
                money(item.cenarios.otimista.valor_liquido),
            ],
            atributos
        );
    });
    $("#sim-tabela").innerHTML = elegiveis.length
        ? `<thead>${cabecalho}</thead><tbody>${linhas.join("")}</tbody>`
        : "<tbody><tr><td>Nenhum produto disponível para esse valor e perfil de risco.</td></tr></tbody>";
}

// Produtos permitidos pelo risco, mas com aporte mínimo acima do que foi investido.
function renderIndisponiveis() {
    const fora = resultado.resultados.filter((item) => !item.elegivel);
    $("#sim-indisponiveis").textContent = fora.length
        ? `Indisponíveis com esse valor: ${fora.map((item) => `${item.produto} (${item.motivo})`).join("; ")}.`
        : "";
}

// Detalhe do produto selecionado: valores do cenário base e os três cenários lado a lado.
function renderDetalhe() {
    const painel = $("#detalhe-cards").closest(".panel");
    painel.hidden = !elegiveis.length;
    if (!elegiveis.length) return;
    const item = elegiveis[selecionado];
    Graficos.desenharEvolucao($("#grafico-evolucao"), $("#g-leitura"), item);
    const base = item.cenarios.base;
    $("#detalhe-titulo").textContent = `Detalhes: ${item.produto}`;
    const cards = [
        ["Total investido", money(base.total_investido), `${base.meses} meses`],
        ["Valor bruto", money(base.valor_bruto), `Rendimento bruto: ${money(base.rendimento_bruto)}`],
        [
            "Imposto de renda",
            money(base.ir),
            base.tributacao === "isento"
                ? "Isento para pessoa física"
                : `Alíquota média: ${pct(base.aliquota_media_ir_pct)}`,
        ],
        [
            "Valor líquido",
            money(base.valor_liquido),
            `Rendimento líquido: ${money(base.rendimento_liquido)} (${pct(base.rentabilidade_liquida_pct)})`,
        ],
    ];
    $("#detalhe-cards").innerHTML = cards.map(cartao).join("");
    $("#detalhe-real").textContent =
        base.valor_liquido_real !== undefined
            ? `Em valores de hoje (descontando a inflação informada), ` +
              `o valor líquido equivale a ${money(base.valor_liquido_real)}.`
            : "";
    const linhas = Object.keys(cenarioLabels).map((nome) => {
        const cenario = item.cenarios[nome];
        return linhaTabela([
            `<strong>${cenarioLabels[nome]}</strong>`,
            `${pct(cenario.taxa_anual_pct)} a.a.`,
            money(cenario.valor_bruto),
            money(cenario.ir),
            `<strong>${money(cenario.valor_liquido)}</strong>`,
            pct(cenario.rentabilidade_liquida_pct),
        ]);
    });
    const cabecalhoCenarios = linhaTabela(
        ["Cenário", "Taxa bruta", "Bruto", "IR", "Líquido", "Rentab. líquida"],
        "",
        "th"
    );
    $("#detalhe-cenarios").innerHTML = `<thead>${cabecalhoCenarios}</thead><tbody>${linhas.join("")}</tbody>`;
}

// Mostra de onde vêm as taxas e o que o cálculo simplifica, para o resultado não parecer uma promessa.
function renderPremissas() {
    const variaveis = premissas.cenarios_variaveis;
    const sobreCdi = premissas.cenarios_variaveis_sobre_cdi_pp;
    const sinalPp = (valor) => `${valor > 0 ? "+" : "−"}${Math.abs(valor)} p.p.`;
    const itens = [
        `${descricaoTaxas(taxas)} As taxas reais mudam com o tempo.`,
        "Cenários: o base usa o ponto médio da faixa de rentabilidade do produto; " +
            `o pessimista usa o extremo inferior com Selic/CDI ${premissas.variacao_cenario_pp} p.p. mais baixos; ` +
            `o otimista, o extremo superior com ${premissas.variacao_cenario_pp} p.p. mais altos.`,
        "Produtos de rentabilidade variável não têm retorno garantido: " +
            "os que informam uma meta (ex.: CDI + 1% a 3%) usam essa faixa. " +
            "Os sem meta (como o fundo de ações) usam hipóteses sobre o CDI: " +
            `pessimista ${sinalPp(sobreCdi.pessimista)}, base ${sinalPp(sobreCdi.base)} (prêmio de risco) ` +
            `e otimista ${sinalPp(sobreCdi.otimista)}, hoje equivalentes a ${pct(variaveis.pessimista)}, ` +
            `${pct(variaveis.base)} e ${pct(variaveis.otimista)} ao ano. ` +
            "São premissas educativas, não previsões: risco maior significa resultado mais incerto, " +
            "não retorno garantido.",
        "IR pela tabela regressiva da renda fixa, calculado por aporte " +
            "(22,5% até 180 dias, 20% até 360, 17,5% até 720 e 15% acima). " +
            "LCI/LCA isentas; fundo de ações com 15% fixo.",
        "Não estão incluídos: come-cotas dos fundos, taxa de custódia do Tesouro, " +
            "IOF de resgates com menos de 30 dias e taxas de administração.",
        "Simulação educativa: os valores são estimativas e não garantem rentabilidade futura.",
    ];
    $("#sim-premissas").innerHTML = itens.map((texto) => `<li>${texto}</li>`).join("");
}

// Conversa com o Bob sobre a simulação
function adicionarMensagem(role, content = "", thinking = false) {
    const mensagem = document.createElement("article");
    mensagem.className = `message ${role}${thinking ? " thinking" : ""}`;
    // As respostas do Bob são formatadas (Markdown escapado, veja markdown.js); o resto entra como texto puro.
    if (role === "assistant" && !thinking) Markdown.mostrar(mensagem, content);
    else mensagem.textContent = content;
    $("#sim-chat-messages").append(mensagem);
    $("#sim-chat-messages").scrollTop = 999999;
    return mensagem;
}

// A saudação aparece uma vez; nas simulações seguintes o Bob só avisa que os números mudaram.
function iniciarConversa() {
    if (!chatIniciado) {
        if (chatHistory.length) {
            chatHistory.forEach((mensagem) => adicionarMensagem(mensagem.role, mensagem.content));
        } else {
            const saudacao =
                "Olá! Posso explicar os números desta simulação, comparar os produtos " +
                "ou dizer o que muda se você alterar algum valor. O que você quer saber?";
            adicionarMensagem("assistant", saudacao);
            chatHistory.push({ role: "assistant", content: saudacao });
            Conversas.salvar("simulador", chatHistory);
        }
        $("#sim-sugestoes").innerHTML = sugestoes
            .map((texto) => `<button type="button" class="chip">${escapeHtml(texto)}</button>`)
            .join("");
        chatIniciado = true;
    } else {
        adicionarMensagem("assistant thinking", "Simulação atualizada: o Bob agora enxerga os novos números.");
    }
}

// Manda a pergunta com os parâmetros da simulação e o produto selecionado; a resposta chega em streaming.
async function perguntarAoBob(content) {
    if (!ultimaSimulacao || bobPensando) return;
    bobPensando = true;
    const historico = chatHistory.slice(-6);
    adicionarMensagem("user", content);
    chatHistory.push({ role: "user", content });
    Conversas.salvar("simulador", chatHistory);
    const botao = $("#sim-chat-form").querySelector("button");
    botao.disabled = true;
    alternarSugestoes(true);
    const resposta = adicionarMensagem("assistant", "Bob está pensando…", true);
    try {
        const response = await fetch("/api/chat/stream", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                mensagem: content,
                historico,
                outras_conversas: Conversas.contextoOutras("simulador"),
                simulacao: { ...ultimaSimulacao, produto_selecionado: elegiveis[selecionado]?.produto ?? null },
            }),
        });
        if (!response.ok) {
            const erro = await response.json().catch(() => ({}));
            throw new Error(typeof erro.detail === "string" ? erro.detail : "Não foi possível conversar agora.");
        }
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "",
            texto = "";
        resposta.classList.remove("thinking");
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            const linhas = buffer.split("\n");
            buffer = linhas.pop();
            for (const linha of linhas) {
                if (!linha) continue;
                texto += JSON.parse(linha).token;
                Markdown.mostrar(resposta, texto);
                $("#sim-chat-messages").scrollTop = 999999;
            }
        }
        chatHistory.push({ role: "assistant", content: texto });
        Conversas.salvar("simulador", chatHistory);
    } catch (error) {
        resposta.classList.remove("thinking");
        resposta.textContent = error.message || "Não foi possível conversar agora.";
    } finally {
        botao.disabled = false;
        alternarSugestoes(false);
        bobPensando = false;
        $("#sim-chat-text").focus();
    }
}

function alternarSugestoes(bloqueado) {
    document.querySelectorAll("#sim-sugestoes .chip").forEach((chip) => {
        chip.disabled = bloqueado;
    });
}

function enviarPergunta(texto) {
    const pergunta = texto.trim();
    // Com o Bob respondendo, o texto digitado fica na caixa para ser enviado depois.
    if (!pergunta || bobPensando) return;
    $("#sim-chat-text").value = "";
    perguntarAoBob(pergunta);
}

function selecionarLinha(event) {
    if (event.type === "keydown" && event.key !== "Enter") return;
    const linha = event.target.closest("tr[data-i]");
    if (!linha) return;
    selecionarProduto(Number(linha.dataset.i));
}

document.addEventListener("DOMContentLoaded", async () => {
    const user = await initAuthenticatedPage();
    if (!user) return;
    const form = formulario();

    try {
        // Sem perfil salvo, a API responde 409 pedindo para preenchê-lo.
        const data = await api("/api/simulador/padrao");
        padrao = data.padrao;
        premissas = data.premissas;
        taxas = data.taxas;
    } catch (error) {
        showNotice(error.message, "error");
        return;
    }

    chaveSimulacao = `bob_simulacao_${user.id}`;
    // A conversa do simulador também volta quando o usuário retorna a esta tela.
    Conversas.iniciar(user);
    chatHistory = Conversas.carregar("simulador");
    $("#logout")?.addEventListener("click", () => {
        try {
            sessionStorage.removeItem(chaveSimulacao);
        } catch (_) {
            // sem armazenamento: não há o que apagar
        }
    });

    // Se já houve simulação nesta sessão, os campos voltam como estavam; senão partem do perfil.
    const salvo = lerSimulacaoSalva();
    renderTaxas();
    atualizarTaxasSeBuscando();
    preencherPadrao();
    form.meses.value = salvo ? salvo.meses : padrao.meses;
    form.inflacao_anual_pct.value = salvo?.inflacao_anual_pct ?? "";
    form.editar.checked = Boolean(salvo?.editar);
    alternarEdicao();
    // Sem edição, os dados do perfil valem sempre os atuais (o perfil pode ter mudado desde a última simulação).
    if (salvo?.editar) {
        form.valor_inicial.value = salvo.valor_inicial;
        form.aporte_mensal.value = salvo.aporte_mensal;
        form.tolerancia_risco.value = salvo.tolerancia_risco;
    }

    form.editar.addEventListener("change", alternarEdicao);
    form.addEventListener("submit", (event) => {
        event.preventDefault();
        simular();
    });
    $("#sim-tabela").addEventListener("click", selecionarLinha);
    $("#sim-tabela").addEventListener("keydown", selecionarLinha);

    $("#sim-chat-form").addEventListener("submit", (event) => {
        event.preventDefault();
        enviarPergunta($("#sim-chat-text").value);
    });
    $("#sim-chat-text").addEventListener("keydown", (event) => {
        if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            $("#sim-chat-form").requestSubmit();
        }
    });
    $("#sim-sugestoes").addEventListener("click", (event) => {
        const chip = event.target.closest(".chip");
        if (chip) enviarPergunta(chip.textContent);
    });

    // Nada é simulado sozinho: a comparação só aparece depois que o usuário simula (ou se já simulou nesta sessão).
    if (salvo) simular();
    else if (padrao.aporte_mensal + padrao.valor_inicial <= 0) {
        showNotice(
            "Seu valor disponível por mês é R$ 0,00. Marque a opção de alterar os dados para simular um aporte.",
            "error"
        );
    }
});
