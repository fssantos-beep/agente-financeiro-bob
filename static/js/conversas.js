// Guarda as conversas com o Bob só nesta aba do navegador (sessionStorage), uma por tela: "chat" e "simulador".
// Cada tela restaura a própria conversa e manda ao Bob um resumo das outras como contexto.
// Nada vai para o banco, e tudo some ao sair da conta ou fechar a aba.
const Conversas = (() => {
    const LIMITE_SALVAS = 40; // mensagens guardadas por tela
    const LIMITE_CONTEXTO = 6; // mensagens das outras telas enviadas ao Bob
    const LIMITE_TEXTO = 600; // caracteres por mensagem enviada como contexto
    let chave = null;

    function ler() {
        try {
            const dados = JSON.parse(sessionStorage.getItem(chave));
            return dados && typeof dados === "object" && !Array.isArray(dados) ? dados : {};
        } catch (_) {
            return {};
        }
    }

    function valida(mensagem) {
        return mensagem && ["user", "assistant"].includes(mensagem.role) && typeof mensagem.content === "string";
    }

    return {
        // Guarda a chave do usuário e apaga as conversas quando ele sai da conta.
        iniciar(user) {
            chave = `bob_conversas_${user.id}`;
            document.querySelector("#logout")?.addEventListener("click", () => {
                try {
                    sessionStorage.removeItem(chave);
                } catch (_) {
                    /* sem armazenamento: nada a apagar */
                }
            });
        },

        carregar(tela) {
            const lista = ler()[tela];
            return Array.isArray(lista) ? lista.filter(valida) : [];
        },

        salvar(tela, mensagens) {
            try {
                const dados = ler();
                dados[tela] = mensagens.slice(-LIMITE_SALVAS);
                sessionStorage.setItem(chave, JSON.stringify(dados));
            } catch (_) {
                /* armazenamento indisponível: a conversa segue funcionando, só não é lembrada */
            }
        },

        // Últimas mensagens das outras telas, no formato do servidor. Conversa sem pergunta do usuário fica de fora.
        contextoOutras(telaAtual) {
            const dados = ler();
            const contexto = [];
            for (const tela of Object.keys(dados)) {
                if (tela === telaAtual) continue;
                const mensagens = this.carregar(tela);
                if (!mensagens.some((mensagem) => mensagem.role === "user")) continue;
                mensagens.slice(-LIMITE_CONTEXTO).forEach((mensagem) => {
                    contexto.push({ tela, role: mensagem.role, content: mensagem.content.slice(0, LIMITE_TEXTO) });
                });
            }
            return contexto.slice(-LIMITE_CONTEXTO);
        },
    };
})();
