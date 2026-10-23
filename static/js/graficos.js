// Gráficos do simulador em SVG puro, sem bibliotecas: barras de comparação e evolução ao longo do tempo.
// Os valores já chegam calculados do servidor; aqui só tem desenho. As cores ficam no style.css (classes .g-*).
const Graficos = (() => {
    const numero = (opcoes) => new Intl.NumberFormat("pt-BR", opcoes);
    const reais = (valor) => `R$ ${numero({ maximumFractionDigits: 0 }).format(valor)}`;
    const compacto = (valor) =>
        valor === 0 ? "R$ 0" : `R$ ${numero({ notation: "compact", maximumFractionDigits: 1 }).format(valor)}`;
    const riscos = { baixo: "risco baixo", medio: "risco médio", alto: "risco alto" };

    // Monta um elemento como texto. Os valores dos atributos são escapados aqui; o conteúdo entra como vier,
    // então quem chama escapa o texto que não for seu. Atributos nulos ou falsos ficam de fora.
    function el(tag, atributos = {}, conteudo = "") {
        const texto = Object.entries(atributos)
            .filter(([, valor]) => valor !== null && valor !== undefined && valor !== false)
            .map(([nome, valor]) => ` ${nome}="${escapeHtml(valor)}"`)
            .join("");
        return `<${tag}${texto}>${conteudo}</${tag}>`;
    }

    const legenda = (itens) =>
        el(
            "ul",
            { class: "g-legenda" },
            itens.map(([chave, texto]) => el("li", {}, `${el("span", { class: `g-chave ${chave}` })}${texto}`)).join("")
        );

    // Arredonda o topo do eixo para um número redondo e devolve também o passo entre as linhas de grade.
    function escalaNice(maximo, divisoes = 4) {
        const bruto = maximo / divisoes || 1;
        const potencia = 10 ** Math.floor(Math.log10(bruto));
        const passo = [1, 2, 2.5, 5, 10].map((f) => f * potencia).find((p) => p >= bruto);
        return { passo, topo: Math.ceil(maximo / passo) * passo };
    }

    // Barras: valor líquido de cada produto, com a faixa do pessimista ao otimista
    function desenharBarras(container, itens, selecionado, aoSelecionar) {
        if (!itens.length) {
            container.innerHTML = "";
            return;
        }
        const W = 720;
        const esquerda = 178;
        const direita = 164;
        const topo = 40;
        const alturaLinha = 54;
        const baixo = 10;
        const H = topo + itens.length * alturaLinha + baixo;
        const investido = itens[0].cenarios.base.total_investido;
        const maximo = Math.max(investido, ...itens.map((i) => i.cenarios.otimista.valor_liquido)) * 1.04;
        const x = (valor) => esquerda + (valor / maximo) * (W - esquerda - direita);
        const numeroPlano = (valor) => numero({ maximumFractionDigits: 0 }).format(valor);

        const linhas = itens
            .map((item, i) => {
                const { pessimista, base, otimista } = item.cenarios;
                const y = topo + i * alturaLinha;
                const cy = y + alturaLinha / 2;
                const variavel = item.rentabilidade_variavel;
                const [valorPess, valorBase, valorOtim] = [pessimista, base, otimista].map((c) => c.valor_liquido);

                // A faixa é uma caixa em volta do fim da barra; se for muito estreita, ganha uma largura mínima
                // para continuar visível.
                let faixaEsq = x(valorPess);
                let faixaDir = x(valorOtim);
                if (faixaDir - faixaEsq < 14) {
                    const meio = (faixaEsq + faixaDir) / 2;
                    faixaEsq = meio - 7;
                    faixaDir = meio + 7;
                }
                const xTexto = (faixaDir + 10).toFixed(1);
                const larguraBarra = Math.max(0, x(valorBase) - esquerda).toFixed(1);

                const descricao =
                    `${item.produto}: líquido no cenário base ${reais(valorBase)}, ` +
                    `entre ${reais(valorPess)} (pessimista) e ${reais(valorOtim)} (otimista)`;
                const dicaFaixa =
                    `Faixa de resultados: de ${reais(valorPess)} (cenário pessimista) ` +
                    `a ${reais(valorOtim)} (cenário otimista)`;

                const partes = [
                    el("rect", { class: "g-fundo-linha", x: 0, y, width: W, height: alturaLinha }),
                    el(
                        "text",
                        { class: "g-nome", x: esquerda - 12, y: cy - 2, "text-anchor": "end" },
                        escapeHtml(item.produto)
                    ),
                    el(
                        "text",
                        { class: "g-sub", x: esquerda - 12, y: cy + 13, "text-anchor": "end" },
                        variavel ? "rentabilidade variável" : riscos[item.risco] || ""
                    ),
                    el("rect", {
                        class: variavel ? "g-barra-var" : "g-barra",
                        fill: variavel ? "url(#g-listras)" : null,
                        x: esquerda,
                        y: cy - 10,
                        width: larguraBarra,
                        height: 20,
                        rx: 3,
                    }),
                    el(
                        "rect",
                        {
                            class: "g-faixa",
                            x: faixaEsq.toFixed(1),
                            y: cy - 15,
                            width: (faixaDir - faixaEsq).toFixed(1),
                            height: 30,
                            rx: 7,
                        },
                        el("title", {}, dicaFaixa)
                    ),
                    el("text", { class: "g-valor", x: xTexto, y: cy - 1 }, reais(valorBase)),
                    el(
                        "text",
                        { class: "g-faixa-texto", x: xTexto, y: cy + 14 },
                        `faixa ${reais(valorPess)} a ${numeroPlano(valorOtim)}`
                    ),
                ];
                const atributos = {
                    class: `g-linha${i === selecionado ? " sel" : ""}`,
                    "data-i": i,
                    tabindex: 0,
                    role: "button",
                    "aria-label": descricao,
                };
                return el("g", atributos, partes.join(""));
            })
            .join("");

        const listras = el(
            "defs",
            {},
            el(
                "pattern",
                {
                    id: "g-listras",
                    width: 7,
                    height: 7,
                    patternUnits: "userSpaceOnUse",
                    patternTransform: "rotate(45)",
                },
                el("rect", { width: 7, height: 7, class: "g-listra-a" }) +
                    el("rect", { width: 3.5, height: 7, class: "g-listra-b" })
            )
        );
        const xInvestido = x(investido).toFixed(1);
        const linhaInvestido = el("line", {
            class: "g-invest",
            x1: xInvestido,
            x2: xInvestido,
            y1: topo - 10,
            y2: H - baixo,
        });
        const textoInvestido = el(
            "text",
            { class: "g-invest-texto", x: xInvestido, y: topo - 16, "text-anchor": "middle" },
            `Total investido: ${reais(investido)}`
        );

        container.innerHTML =
            el(
                "svg",
                {
                    class: "grafico",
                    viewBox: `0 0 ${W} ${H}`,
                    role: "group",
                    "aria-label":
                        "Valor líquido final por produto, com a faixa entre os cenários pessimista e otimista",
                },
                listras + linhaInvestido + textoInvestido + linhas
            ) +
            legenda([
                ["g-chave-barra", "Valor líquido no cenário base"],
                ["g-chave-faixa", "Caixa: faixa de resultados do pessimista ao otimista"],
                ["g-chave-invest", "Total investido"],
                ["g-chave-listra", "Rentabilidade variável (hipótese)"],
            ]);

        const escolher = (evento) => {
            if (evento.type === "keydown" && evento.key !== "Enter" && evento.key !== " ") return;
            const grupo = evento.target.closest("g[data-i]");
            if (!grupo) return;
            evento.preventDefault();
            aoSelecionar(Number(grupo.dataset.i));
        };
        const svg = container.querySelector("svg");
        svg.addEventListener("click", escolher);
        svg.addEventListener("keydown", escolher);
    }

    // Linhas: evolução mês a mês do produto selecionado
    function desenharEvolucao(container, leitura, item) {
        const serie = item?.cenarios?.base?.serie;
        if (!serie) {
            container.innerHTML = "";
            leitura.textContent = "";
            return;
        }
        const c = item.cenarios;
        const base = serie.liquido;
        const invest = serie.investido;
        const pess = c.pessimista.serie.liquido;
        const otim = c.otimista.serie.liquido;
        const N = base.length - 1;

        const W = 720;
        const H = 340;
        const ml = 76;
        const mr = 22;
        const mt = 16;
        const mb = 46;
        const pw = W - ml - mr;
        const ph = H - mt - mb;
        const { passo, topo } = escalaNice(Math.max(...otim, ...invest));
        const x = (mes) => ml + (mes / N) * pw;
        const y = (valor) => mt + ph - (valor / topo) * ph;
        const caminho = (valores) =>
            valores.map((v, m) => `${m ? "L" : "M"}${x(m).toFixed(1)} ${y(v).toFixed(1)}`).join("");
        // A faixa sombreada sobe pela linha do otimista e volta pela do pessimista.
        const voltaPessimista = pess.map((_, m) => `L${x(N - m).toFixed(1)} ${y(pess[N - m]).toFixed(1)}`).join("");
        const banda = `${caminho(otim)}${voltaPessimista}Z`;

        let grade = "";
        for (let valor = 0; valor <= topo + passo / 2; valor += passo) {
            const yGrade = y(valor).toFixed(1);
            grade +=
                el("line", { class: "g-grade", x1: ml, x2: W - mr, y1: yGrade, y2: yGrade }) +
                el(
                    "text",
                    { class: "g-eixo", x: ml - 8, y: (y(valor) + 4).toFixed(1), "text-anchor": "end" },
                    compacto(valor)
                );
        }

        const passoMeses = [1, 2, 3, 6, 12, 24, 36, 60, 120, 240].find((p) => N / p <= 8) || 240;
        const rotulo = (mes) => (mes % 12 === 0 && N > 24 ? `${mes / 12} ${mes === 12 ? "ano" : "anos"}` : `${mes} m`);
        let marcas = "";
        for (let mes = 0; mes <= N; mes += passoMeses) {
            // O último rótulo fica alinhado à direita para não ser cortado na borda.
            const ancora = x(mes) > W - 44 ? "end" : "middle";
            marcas += el(
                "text",
                { class: "g-eixo", x: x(mes).toFixed(1), y: H - mb + 20, "text-anchor": ancora },
                mes === 0 ? "início" : rotulo(mes)
            );
        }

        const desenho =
            grade +
            marcas +
            el("path", { class: "g-banda", d: banda }) +
            el("path", { class: "g-l-borda", d: caminho(otim) }) +
            el("path", { class: "g-l-borda", d: caminho(pess) }) +
            el("path", { class: "g-l-invest", d: caminho(invest) }) +
            el("path", { class: "g-l-base", d: caminho(base) }) +
            el("line", { class: "g-guia", id: "g-guia", y1: mt, y2: mt + ph, visibility: "hidden" }) +
            el("circle", { class: "g-ponto-invest", id: "g-ponto-invest", r: 4, visibility: "hidden" }) +
            el("circle", { class: "g-ponto-base", id: "g-ponto-base", r: 5, visibility: "hidden" });

        const descricao = `Evolução do total investido e do valor líquido de ${item.produto} ao longo de ${N} meses`;
        container.innerHTML =
            el(
                "svg",
                {
                    class: "grafico",
                    viewBox: `0 0 ${W} ${H}`,
                    role: "img",
                    "aria-label": descricao,
                },
                desenho
            ) +
            legenda([
                ["g-chave-linha", "Valor líquido (cenário base)"],
                ["g-chave-banda", "Faixa do pessimista ao otimista"],
                ["g-chave-invest", "Total investido"],
            ]);

        const anos = (mes) => (mes >= 12 ? ` (${numero({ maximumFractionDigits: 1 }).format(mes / 12)} anos)` : "");
        const texto = (mes, prefixo) =>
            `${prefixo} ${mes}${anos(mes)}: investido ${reais(invest[mes])} · líquido base ${reais(base[mes])} · ` +
            `faixa de ${reais(pess[mes])} a ${reais(otim[mes])}`;
        const svg = container.querySelector("svg");
        const guia = svg.querySelector("#g-guia");
        const pontoBase = svg.querySelector("#g-ponto-base");
        const pontoInvest = svg.querySelector("#g-ponto-invest");
        const mostrar = (mes) => {
            const visivel = mes === null ? "hidden" : "visible";
            [guia, pontoBase, pontoInvest].forEach((elemento) => elemento.setAttribute("visibility", visivel));
            if (mes === null) {
                leitura.textContent = texto(N, "No fim do prazo, mês");
                return;
            }
            guia.setAttribute("x1", x(mes));
            guia.setAttribute("x2", x(mes));
            pontoBase.setAttribute("cx", x(mes));
            pontoBase.setAttribute("cy", y(base[mes]));
            pontoInvest.setAttribute("cx", x(mes));
            pontoInvest.setAttribute("cy", y(invest[mes]));
            leitura.textContent = texto(mes, "Mês");
        };
        const mover = (evento) => {
            const caixa = svg.getBoundingClientRect();
            if (!caixa.width) return;
            const xSvg = ((evento.clientX - caixa.left) / caixa.width) * W;
            mostrar(Math.min(N, Math.max(0, Math.round(((xSvg - ml) / pw) * N))));
        };
        svg.addEventListener("pointermove", mover);
        svg.addEventListener("pointerdown", mover);
        svg.addEventListener("pointerleave", () => mostrar(null));
        mostrar(null);
    }

    return { desenharBarras, desenharEvolucao, escalaNice };
})();
