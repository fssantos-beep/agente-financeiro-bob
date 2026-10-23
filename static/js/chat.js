// O histórico fica salvo só nesta aba (veja conversas.js); nada vai para o banco.
let sessionHistory = [];

// Mensagens do usuário usam textContent para não virarem HTML; as respostas do Bob passam pelo renderizador
// de Markdown (markdown.js), que escapa todo o texto antes de formatar.
function appendMessage(role, content = "", thinking = false) {
    const message = document.createElement("article");
    message.className = `message ${role}${thinking ? " thinking" : ""}`;
    if (role === "assistant" && !thinking) Markdown.mostrar(message, content);
    else message.textContent = content;
    $("#chat-messages").append(message);
    $("#chat-messages").scrollTop = 999999;
    return message;
}

// Lê o corpo NDJSON em blocos para exibir cada trecho recebido do Ollama sem esperar a resposta completa.
document.addEventListener("DOMContentLoaded", async () => {
    const user = await initAuthenticatedPage();
    if (!user) return;

    // Volta a conversa desta tela se ela já existe nesta sessão; senão começa uma nova.
    Conversas.iniciar(user);
    const salvas = Conversas.carregar("chat");
    if (salvas.length) {
        salvas.forEach((mensagem) => appendMessage(mensagem.role, mensagem.content));
        sessionHistory = salvas;
    } else {
        appendMessage("assistant", `Olá, ${user.nome}! Como posso ajudar?`);
        sessionHistory = [{ role: "assistant", content: `Olá, ${user.nome}! Como posso ajudar?` }];
    }

    const form = $("#chat-form");
    const input = $("#chat-text");

    form.addEventListener("submit", async (event) => {
        event.preventDefault();
        const content = input.value.trim();
        if (!content) return;

        // Enquanto o Bob responde, novas mensagens ficam bloqueadas (o Enter também dispara o envio).
        const button = form.querySelector("button");
        if (button.disabled) return;

        // O histórico é copiado antes de incluir a mensagem atual, que já vai no campo "mensagem".
        const historico = sessionHistory.slice(-6);
        appendMessage("user", content);
        sessionHistory.push({ role: "user", content });
        Conversas.salvar("chat", sessionHistory);
        input.value = "";

        button.disabled = true;
        const answer = appendMessage("assistant", "Bob está pensando…", true);

        try {
            const response = await fetch("/api/chat/stream", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    mensagem: content,
                    historico,
                    outras_conversas: Conversas.contextoOutras("chat"),
                }),
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
                        Markdown.mostrar(answer, text);
                        $("#chat-messages").scrollTop = 999999;
                    }
                }
            }
            sessionHistory.push({ role: "assistant", content: text });
            Conversas.salvar("chat", sessionHistory);
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
