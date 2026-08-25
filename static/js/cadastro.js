document.addEventListener("DOMContentLoaded", () => {
    $("#register-form").addEventListener("submit", async (event) => {
        event.preventDefault();
        try {
            // A validação definitiva acontece no FastAPI antes da criação no MySQL.
            await api("/api/auth/register", { method: "POST", body: JSON.stringify(Object.fromEntries(new FormData(event.currentTarget))) });
            window.location.href = "/login?cadastro=sucesso";
        } catch (error) { // Mantém o formulário aberto para que o usuário possa corrigir os dados.
            showNotice(error.message, "error", "#notice");
        }
    });
});
