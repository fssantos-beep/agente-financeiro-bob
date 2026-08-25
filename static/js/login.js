document.addEventListener("DOMContentLoaded", () => {
    // O cadastro usa a query string para exibir a confirmação já na tela de login.
    if (new URLSearchParams(window.location.search).get("cadastro") === "sucesso") showNotice("Conta criada. Agora entre com seu e-mail e senha.", "success", "#notice");
    $("#login-form").addEventListener("submit", async (event) => {
        event.preventDefault();
        try {
            // Envia as credenciais ao backend; a senha não é mantida no navegador após o envio.
            await api("/api/auth/login", { method: "POST", body: JSON.stringify(Object.fromEntries(new FormData(event.currentTarget))) });
            window.location.href = "/dashboard";
        } catch (error) { // Mostra a mensagem retornada pela API sem sair da página.
            showNotice(error.message, "error", "#notice");
        }
    });
});
