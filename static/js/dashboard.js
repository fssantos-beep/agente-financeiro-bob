// Converte as chaves do banco em rótulos no gráfico.
const expenseLabels = { gastos_moradia: "Moradia/aluguel", gastos_alimentacao: "Alimentação", gastos_transporte: "Transporte", gastos_contas: "Contas básicas", gastos_educacao: "Educação", gastos_saude: "Saúde", gastos_lazer: "Lazer", outros_gastos: "Outros gastos" };
document.addEventListener("DOMContentLoaded", async () => {
    const user = await initAuthenticatedPage(); if (!user) return;
    $("#greeting").textContent = `Olá, ${user.nome}!`;

    // Sem perfil não há dados suficientes para calcular os indicadores do painel.
    const data = await api("/api/dashboard"); if (!data.metrics) { window.location.href = "/perfil"; return; }
    const metrics = data.metrics;
    const cards = [["Renda mensal", money(metrics.renda_mensal), "Total informado"], ["Gastos mensais", money(metrics.gastos_mensais), "Soma das categorias"], ["Disponível mensalmente", money(metrics.disponivel), "Após os gastos"], ["Renda comprometida", `${metrics.percentual_comprometido.toFixed(1)}%`, `${metrics.meses_reserva.toFixed(1)} meses de reserva`]];
    
    // Os cards são montados a partir do cálculo retornado pelo servidor, não por valores locais.
    $("#metric-cards").innerHTML = cards.map(([label, value, detail]) => `<article class="metric"><span class="label">${label}</span><strong>${value}</strong><small>${detail}</small></article>`).join("");
    const entries = Object.entries(metrics.gastos_por_categoria), max = Math.max(...entries.map(([, value]) => value), 1);
    
    // Cada barra é proporcional à maior categoria, deixando a comparação visual simples.
    $("#expenses-chart").innerHTML = entries.map(([key, value]) => `<div class="bar-row"><span>${expenseLabels[key]}</span><div class="bar"><i style="width:${value / max * 100}%"></i></div><b>${money(value)}</b></div>`).join("");
});
