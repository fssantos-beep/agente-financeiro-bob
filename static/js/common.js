// Pequenos utilitários compartilhados evitam repetir o mesmo tratamento em cada tela.
const $ = (selector) => document.querySelector(selector);
const money = (value) => new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(value || 0);

async function api(url, options = {}) {
    // Todas as telas usam este ponto único para falar com a API JSON do FastAPI.
    const response = await fetch(url, {
        headers: { "Content-Type": "application/json", ...(options.headers || {}) },
        ...options,
    });
    if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        // Uma sessão expirada deve levar o usuário de volta ao fluxo de autenticação.
        if (response.status === 401) window.location.href = "/login";
        throw new Error(data.detail || "Não foi possível concluir a operação.");
    }
    return response.status === 204 ? null : response.json();
}

function showNotice(message, type = "success", target = "#app-notice") {
    // A mesma estrutura de aviso atende erros de formulário e confirmações de sucesso.
    const element = $(target);
    if (!element) return;
    element.textContent = message;
    element.className = `notice ${type}`;
}

async function initAuthenticatedPage() {
    try {
        // Confirma a sessão antes de preencher a navegação privada com o nome do usuário.
        const user = await api("/api/auth/me");
        const userName = $("#user-name");
        if (userName) userName.textContent = user.nome;
        $("#logout")?.addEventListener("click", async () => {
            await api("/api/auth/logout", { method: "POST" });
            window.location.href = "/login";
        });
        $("#menu-toggle")?.addEventListener("click", () => $(".sidebar")?.classList.toggle("open"));
        return user;
    } catch (_) {
        // A função api já faz o redirecionamento quando a API responde sem autenticação.
        return null;
    }
}
