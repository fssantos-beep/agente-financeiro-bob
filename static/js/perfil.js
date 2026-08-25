// Essas chaves precisam acompanhar os nomes aceitos pelo endpoint de perfil.
const fields = {
    renda_mensal: "Renda mensal líquida (R$)",
    gastos_moradia: "Moradia/aluguel (R$)",
    gastos_alimentacao: "Alimentação (R$)",
    gastos_transporte: "Transporte (R$)",
    gastos_contas: "Contas básicas (R$)",
    gastos_educacao: "Educação (R$)",
    gastos_saude: "Saúde (R$)",
    gastos_lazer: "Lazer (R$)",
    outros_gastos: "Outros gastos (R$)"
};

const objectives = {
    reserva_de_emergencia: "Criar uma reserva de emergência",
    comprar_imovel: "Comprar um imóvel",
    comprar_veiculo: "Comprar um veículo",
    viajar: "Viajar",
    aposentadoria: "Aposentadoria",
    aumentar_patrimonio: "Aumentar patrimônio",
    outro: "Outro"
};

// Evita pedir valores que não fazem sentido quando dívida ou investimento não foram marcados.
function toggleConditional() {
    const form = $("#profile-form");
    const debt = form.possui_dividas.checked;
    const investment = form.possui_investimentos.checked;

    ["valor_dividas", "juros_divida"].forEach((name) => {
        form[name].disabled = !debt;
    });

    ["valor_investido", "tipos_investimentos"].forEach((name) => {
        form[name].disabled = !investment;
    });

    $("#other-objective").hidden = form.objetivo_financeiro.value !== "outro";
    form.objetivo_outro.disabled = form.objetivo_financeiro.value !== "outro";
}

// Reconstrói os campos e preenche os valores persistidos antes de permitir a edição.
function fillProfile(profile = {}) {
    $("#expense-fields").innerHTML = Object.entries(fields)
        .map(([name, label]) => `<label>${label}<input name="${name}" type="number" min="0" step="0.01" ${name === "renda_mensal" ? "required" : ""}></label>`)
        .join("");

    $("#objective").innerHTML = Object.entries(objectives)
        .map(([value, label]) => `<option value="${value}">${label}</option>`)
        .join("");

    Object.entries(profile).forEach(([key, value]) => {
        const input = $(`[name="${key}"]`);
        if (input) {
            input.type === "checkbox" 
                ? (input.checked = Boolean(value)) 
                : (input.value = value ?? "");
        }
    });

    toggleConditional();
}

// Converte os números do formulário antes de enviá-los, para preservar o contrato JSON da API.
document.addEventListener("DOMContentLoaded", async () => {
    if (!await initAuthenticatedPage()) return;

    const form = $("#profile-form");
    fillProfile((await api("/api/profile")).profile || {});

    form.addEventListener("change", toggleConditional);

    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        const data = Object.fromEntries(new FormData(form));

        ["possui_dividas", "possui_investimentos"].forEach((key) => {
            data[key] = form[key].checked;
        });

        if (data.objetivo_financeiro === "outro") {
            data.objetivo_outro = (data.objetivo_outro || "").trim();
        } else {
            data.objetivo_outro = null;
        }

        Object.keys(fields)
            .filter((key) => key !== "renda_mensal")
            .concat(["valor_dividas", "juros_divida", "reserva_emergencia", "valor_investido"])
            .forEach((key) => {
                data[key] = Number(data[key] || 0);
            });

        try {
            const result = await api("/api/profile", {
                method: "PUT",
                body: JSON.stringify(data)
            });
            showNotice(result.message);
        } catch (error) {
            showNotice(error.message, "error");
        }
    });
});
