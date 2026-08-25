-- Execute este script no MySQL Community Server para criar o banco do Bob.
CREATE DATABASE IF NOT EXISTS agente_financeiro_bob
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE agente_financeiro_bob;

CREATE TABLE IF NOT EXISTS usuarios (
    id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    nome VARCHAR(120) NOT NULL,
    email VARCHAR(255) NOT NULL,
    senha_hash VARCHAR(255) NOT NULL,
    data_cadastro TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_usuarios_email (email)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS perfil_financeiro (
    id INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    usuario_id INT UNSIGNED NOT NULL,
    renda_mensal DECIMAL(12,2) NOT NULL,
    gastos_moradia DECIMAL(12,2) NOT NULL DEFAULT 0,
    gastos_alimentacao DECIMAL(12,2) NOT NULL DEFAULT 0,
    gastos_transporte DECIMAL(12,2) NOT NULL DEFAULT 0,
    gastos_educacao DECIMAL(12,2) NOT NULL DEFAULT 0,
    gastos_saude DECIMAL(12,2) NOT NULL DEFAULT 0,
    gastos_lazer DECIMAL(12,2) NOT NULL DEFAULT 0,
    gastos_contas DECIMAL(12,2) NOT NULL DEFAULT 0,
    outros_gastos DECIMAL(12,2) NOT NULL DEFAULT 0,
    possui_dividas BOOLEAN NOT NULL DEFAULT FALSE,
    valor_dividas DECIMAL(12,2) NOT NULL DEFAULT 0,
    tipo_divida VARCHAR(120) NULL,
    juros_divida DECIMAL(5,2) NULL,
    reserva_emergencia DECIMAL(12,2) NOT NULL DEFAULT 0,
    possui_investimentos BOOLEAN NOT NULL DEFAULT FALSE,
    valor_investido DECIMAL(12,2) NOT NULL DEFAULT 0,
    tipos_investimentos VARCHAR(255) NULL,
    objetivo_financeiro VARCHAR(80) NOT NULL,
    objetivo_outro VARCHAR(255) NULL,
    tolerancia_risco VARCHAR(20) NOT NULL,
    valor_disponivel_investimento DECIMAL(12,2) NOT NULL DEFAULT 0,
    atualizado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT uq_perfil_usuario UNIQUE (usuario_id),
    CONSTRAINT fk_perfil_usuario FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE,
    CONSTRAINT chk_renda_nao_negativa CHECK (renda_mensal >= 0),
    CONSTRAINT chk_risco CHECK (tolerancia_risco IN ('conservador', 'moderado', 'arrojado'))
) ENGINE=InnoDB;
