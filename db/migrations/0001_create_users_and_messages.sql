-- 0001: cria as tabelas base de usuários e mensagens

CREATE TABLE IF NOT EXISTS users (
    user_id BIGSERIAL PRIMARY KEY,             -- id próprio, interno da aplicação
    telegram_id BIGINT NOT NULL UNIQUE,        -- id do usuário no Telegram (message.from.id)
    username TEXT,                             -- @username no Telegram (pode ser nulo, nem todo usuário tem)
    first_name TEXT,
    last_name TEXT,
    language_code TEXT,                        -- ex: "pt-br", vem do cliente Telegram do usuário
    is_bot BOOLEAN NOT NULL DEFAULT FALSE,
    phone_number TEXT,                         -- só é preenchido se o usuário compartilhar o contato
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS messages (
    message_id BIGSERIAL PRIMARY KEY,          -- id próprio, interno da aplicação
    user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    telegram_message_id BIGINT,                -- id da mensagem dentro do Telegram (message.message_id)
    chat_id BIGINT NOT NULL,                   -- id do chat (útil para responder depois)
    text TEXT,
    sent_at TIMESTAMPTZ,                       -- data/hora que o Telegram registrou o envio (message.date)
    received_at TIMESTAMPTZ NOT NULL DEFAULT now()  -- quando nosso servidor processou
);

CREATE INDEX IF NOT EXISTS idx_messages_user_id ON messages(user_id);
