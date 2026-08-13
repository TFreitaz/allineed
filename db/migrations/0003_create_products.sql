-- 0003: creates the canonical products table
-- and adds the manual product relationship to store_products


CREATE TABLE IF NOT EXISTS products (
    product_id BIGSERIAL PRIMARY KEY,

    name TEXT NOT NULL UNIQUE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);


ALTER TABLE store_products
    ADD COLUMN IF NOT EXISTS product_id BIGINT
        REFERENCES products(product_id)
        ON DELETE SET NULL;


ALTER TABLE store_products
    RENAME COLUMN name TO base_name;


CREATE INDEX IF NOT EXISTS idx_store_products_product_id
    ON store_products(product_id);