-- 0002: creates stores, store products, purchases and purchase items


-- ============================================================
-- Stores
-- ============================================================

CREATE TABLE IF NOT EXISTS stores (
    store_id BIGSERIAL PRIMARY KEY,

    cnpj TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,

    street TEXT,
    address_number TEXT,
    neighborhood TEXT,
    city TEXT,
    state TEXT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);


-- ============================================================
-- Products as identified by each store
-- ============================================================

CREATE TABLE IF NOT EXISTS store_products (
    store_product_id BIGSERIAL PRIMARY KEY,

    store_id BIGINT NOT NULL
        REFERENCES stores(store_id)
        ON DELETE CASCADE,

    code TEXT NOT NULL,
    name TEXT NOT NULL,

    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE (store_id, code)
);


CREATE INDEX IF NOT EXISTS idx_store_products_store_id
    ON store_products(store_id);


-- ============================================================
-- Purchases / NFC-e documents
-- ============================================================

CREATE TABLE IF NOT EXISTS purchases (
    purchase_id BIGSERIAL PRIMARY KEY,

    user_id BIGINT NOT NULL
        REFERENCES users(user_id)
        ON DELETE CASCADE,

    store_id BIGINT NOT NULL
        REFERENCES stores(store_id),

    source_message_id BIGINT
        REFERENCES messages(message_id)
        ON DELETE SET NULL,

    -- NFC-e access key
    access_key TEXT NOT NULL UNIQUE,

    document_number TEXT,
    series TEXT,

    issued_at TIMESTAMPTZ,

    authorization_protocol TEXT,

    total_items INTEGER,
    total_amount NUMERIC(12, 2),
    discount NUMERIC(12, 2),
    amount_to_pay NUMERIC(12, 2),

    payment_method TEXT,
    amount_paid NUMERIC(12, 2),

    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);


CREATE INDEX IF NOT EXISTS idx_purchases_user_id
    ON purchases(user_id);

CREATE INDEX IF NOT EXISTS idx_purchases_store_id
    ON purchases(store_id);

CREATE INDEX IF NOT EXISTS idx_purchases_source_message_id
    ON purchases(source_message_id);

CREATE INDEX IF NOT EXISTS idx_purchases_issued_at
    ON purchases(issued_at);


-- ============================================================
-- Items belonging to a purchase
-- ============================================================

CREATE TABLE IF NOT EXISTS purchase_items (
    purchase_item_id BIGSERIAL PRIMARY KEY,

    purchase_id BIGINT NOT NULL
        REFERENCES purchases(purchase_id)
        ON DELETE CASCADE,

    store_product_id BIGINT NOT NULL
        REFERENCES store_products(store_product_id),

    quantity NUMERIC(12, 3) NOT NULL,

    unit TEXT NOT NULL,

    unit_price NUMERIC(12, 2) NOT NULL,

    total_price NUMERIC(12, 2) NOT NULL,

    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);


CREATE INDEX IF NOT EXISTS idx_purchase_items_purchase_id
    ON purchase_items(purchase_id);

CREATE INDEX IF NOT EXISTS idx_purchase_items_store_product_id
    ON purchase_items(store_product_id);