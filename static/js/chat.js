// O histórico existe apenas enquanto esta tela permanece aberta; nada é salvo no banco.
let sessionHistory = [];

// Cria um balão usando textContent para que mensagens do usuário não virem HTML na página.
function appendMessage(role, content = "", thinking = false) {
    const message = document.createElement("article");
    message.className = `message ${role}${thinking ? " thinking" : ""}`;
    message.textContent = content;
    $("#chat-messages").append(message);
    $("#chat-messages").scrollTop = 999999;
    return message;
}

// Lê o corpo NDJSON em blocos para exibir cada trecho recebido do Ollama sem esperar a resposta completa.
document.addEventListener("DOMContentLoaded", async () => {
    const user = await initAuthenticatedPage();
    if (!user) return;

    appendMessage("assistant", `Olá, ${user.nome}! Como posso ajudar?`);
    sessionHistory = [{ role: "assistant", content: `Olá, ${user.nome}! Como posso ajudar?` }];

    const form = $("#chat-form");
    const input = $("#chat-text");

    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        const content = input.value.trim();
        if (!content) return;

        appendMessage("user", content);
        sessionHistory.push({ role: "user", content });
        input.value = "";

        const button = form.querySelector("button");
        button.disabled = true;
        const answer = appendMessage("assistant", "Bob está pensando…", true);

        try {
            const response = await fetch("/api/chat/stream", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ 
                    mensagem: content, 
                    historico: sessionHistory.slice(-6) 
                })
            });

            if (!response.ok) {
                throw new Error((await response.json()).detail);
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = "";
            let text = "";
            
            answer.classList.remove("thinking");

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split("\n");
                buffer = lines.pop();

                for (const line of lines) {
                    if (line) {
                        text += JSON.parse(line).token;
                        answer.textContent = text;
                        $("#chat-messages").scrollTop = 999999;
                    }
                }
            }
            sessionHistory.push({ role: "assistant", content: text });
        } catch (error) {
            answer.classList.remove("thinking");
            answer.textContent = error.message || "Não foi possível conversar agora.";
        } finally {
            button.disabled = false;
            input.focus();
        }
    });

    input.addEventListener("keydown", (event) => {
        if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            form.requestSubmit();
        }
    });
});