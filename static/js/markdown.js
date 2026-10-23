// Transforma o Markdown simples que o Bob escreve (negrito, itálico, código, listas, tabelas e títulos) em HTML.
// Todo texto é escapado antes de qualquer marcação (escapeHtml, do common.js), então HTML escrito pelo modelo ou
// pelo usuário aparece como texto e nunca vira elemento. Links e imagens não são suportados de propósito.
const Markdown = (() => {
    // Marcações dentro da linha: `código`, **negrito**, __negrito__, *itálico* e _itálico_.
    function inline(texto) {
        const codigos = [];
        let html = escapeHtml(texto).replace(/`([^`\n]+)`/g, (_, codigo) => {
            codigos.push(codigo);
            return `\u0000${codigos.length - 1}\u0000`; // guarda o código para as outras regras não mexerem nele
        });
        html = html
            .replace(/\*\*(?=\S)([^\n]*?\S)\*\*/g, "<strong>$1</strong>")
            .replace(/__(?=\S)([^\n]*?\S)__/g, "<strong>$1</strong>")
            .replace(/(^|[^*\w])\*(?=[^\s*])([^*\n]*?[^\s*])\*(?![*\w])/g, "$1<em>$2</em>")
            .replace(/(^|[^_\w])_(?=[^\s_])([^_\n]*?[^\s_])_(?![_\w])/g, "$1<em>$2</em>");
        return html.replace(/\u0000(\d+)\u0000/g, (_, i) => `<code>${codigos[i]}</code>`);
    }

    const REGEX = {
        vazia: /^\s*$/,
        cerca: /^\s*```/,
        titulo: /^\s{0,3}#{1,6}\s+(.*?)\s*#*\s*$/,
        regua: /^\s{0,3}([-*_])(\s*\1){2,}\s*$/,
        itemLista: /^(\s*)([-*•])\s+(.*)$/,
        itemNumerado: /^(\s*)\d+[.)]\s+(.*)$/,
        separadorTabela: /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/,
    };

    const celulas = (linha) => {
        let texto = linha.trim();
        if (texto.startsWith("|")) texto = texto.slice(1);
        if (texto.endsWith("|")) texto = texto.slice(0, -1);
        return texto.split("|").map((celula) => celula.trim());
    };

    const iniciaTabela = (linhas, i) =>
        linhas[i].includes("|") &&
        i + 1 < linhas.length &&
        linhas[i + 1].includes("-") &&
        REGEX.separadorTabela.test(linhas[i + 1]);
    const ehItem = (linha) => REGEX.itemLista.test(linha) || REGEX.itemNumerado.test(linha);
    const iniciaBloco = (linhas, i) =>
        REGEX.cerca.test(linhas[i]) ||
        REGEX.titulo.test(linhas[i]) ||
        REGEX.regua.test(linhas[i]) ||
        ehItem(linhas[i]) ||
        iniciaTabela(linhas, i);

    function tabela(linhas, i) {
        const cabecalho = celulas(linhas[i]);
        const alinhamentos = celulas(linhas[i + 1]).map((c) =>
            c.startsWith(":") && c.endsWith(":") ? "center" : c.endsWith(":") ? "right" : "left"
        );
        const alinhar = (n) => ` style="text-align:${alinhamentos[n] || "left"}"`;
        let fim = i + 2;
        const corpo = [];
        while (fim < linhas.length && linhas[fim].includes("|") && !REGEX.vazia.test(linhas[fim])) {
            const linha = celulas(linhas[fim]);
            corpo.push(
                `<tr>${cabecalho.map((_, n) => `<td${alinhar(n)}>${inline(linha[n] ?? "")}</td>`).join("")}</tr>`
            );
            fim++;
        }
        const titulos = cabecalho.map((texto, n) => `<th${alinhar(n)}>${inline(texto)}</th>`).join("");
        return {
            html:
                '<div class="md-tabela"><table>' +
                `<thead><tr>${titulos}</tr></thead><tbody>${corpo.join("")}</tbody>` +
                "</table></div>",
            fim,
        };
    }

    // Listas com um nível de aninhamento: itens indentados (2 espaços ou mais) entram dentro do item anterior.
    function lista(linhas, i) {
        const itens = [];
        let fim = i;
        while (fim < linhas.length && !REGEX.vazia.test(linhas[fim])) {
            const marcador = linhas[fim].match(REGEX.itemLista);
            const numerado = linhas[fim].match(REGEX.itemNumerado);
            if (marcador || numerado) {
                const recuo = (marcador ? marcador[1] : numerado[1]).length;
                itens.push({ recuo, ordenada: Boolean(numerado), texto: marcador ? marcador[3] : numerado[2] });
            } else if (/^\s{2,}\S/.test(linhas[fim]) && itens.length) {
                itens[itens.length - 1].texto += ` ${linhas[fim].trim()}`; // continuação do item anterior
            } else {
                break;
            }
            fim++;
        }
        const nivelBase = Math.min(...itens.map((item) => item.recuo));
        const tag = (item) => (item.ordenada ? "ol" : "ul");
        let html = "";
        let aberto = null;
        let subAberto = null;
        for (const item of itens) {
            if (item.recuo - nivelBase >= 2 && aberto) {
                if (!subAberto) {
                    subAberto = tag(item);
                    html = html.replace(/<\/li>$/, `<${subAberto}>`);
                }
                html += `<li>${inline(item.texto)}</li>`;
                continue;
            }
            if (subAberto) {
                html += `</${subAberto}></li>`;
                subAberto = null;
            }
            if (aberto && aberto !== tag(item)) {
                html += `</${aberto}>`;
                aberto = null;
            }
            if (!aberto) {
                aberto = tag(item);
                html += `<${aberto}>`;
            }
            html += `<li>${inline(item.texto)}</li>`;
        }
        if (subAberto) html += `</${subAberto}></li>`;
        if (aberto) html += `</${aberto}>`;
        return { html, fim };
    }

    function renderizar(texto) {
        const linhas = String(texto ?? "")
            .replace(/\r\n?/g, "\n")
            .split("\n");
        const blocos = [];
        let i = 0;
        while (i < linhas.length) {
            const linha = linhas[i];
            if (REGEX.vazia.test(linha)) {
                i++;
                continue;
            }
            if (REGEX.cerca.test(linha)) {
                const codigo = [];
                i++;
                while (i < linhas.length && !REGEX.cerca.test(linhas[i])) codigo.push(linhas[i++]);
                i++; // pula a cerca que fecha o bloco (se a resposta ainda está chegando, o bloco fica aberto)
                blocos.push(`<pre><code>${escapeHtml(codigo.join("\n"))}</code></pre>`);
            } else if (iniciaTabela(linhas, i)) {
                const resultado = tabela(linhas, i);
                blocos.push(resultado.html);
                i = resultado.fim;
            } else if (REGEX.titulo.test(linha)) {
                blocos.push(`<p class="md-titulo"><strong>${inline(linha.match(REGEX.titulo)[1])}</strong></p>`);
                i++;
            } else if (REGEX.regua.test(linha)) {
                blocos.push("<hr>");
                i++;
            } else if (ehItem(linha)) {
                const resultado = lista(linhas, i);
                blocos.push(resultado.html);
                i = resultado.fim;
            } else {
                const paragrafo = [linha.trim()];
                i++;
                while (i < linhas.length && !REGEX.vazia.test(linhas[i]) && !iniciaBloco(linhas, i))
                    paragrafo.push(linhas[i++].trim());
                blocos.push(`<p>${paragrafo.map(inline).join("<br>")}</p>`);
            }
        }
        return blocos.join("");
    }

    // Mostra o texto formatado dentro do balão do chat (chamado a cada trecho que chega no streaming).
    function mostrar(elemento, texto) {
        elemento.classList.add("md");
        elemento.innerHTML = renderizar(texto);
    }

    return { renderizar, mostrar };
})();
