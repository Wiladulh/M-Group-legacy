CREATE TABLE IF NOT EXISTS vending_machines(
    machine_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS vending_products(
    product_id TEXT PRIMARY KEY,
    machine_id TEXT NOT NULL REFERENCES vending_machines(machine_id),
    name TEXT NOT NULL,
    price INTEGER NOT NULL CHECK(price>0),
    stock INTEGER NOT NULL DEFAULT 0 CHECK(stock>=0),
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_vending_products_machine ON vending_products(machine_id);
CREATE TABLE IF NOT EXISTS vending_transactions(
    transaction_id TEXT PRIMARY KEY,
    machine_id TEXT NOT NULL REFERENCES vending_machines(machine_id),
    product_id TEXT NOT NULL REFERENCES vending_products(product_id),
    credential_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    amount INTEGER NOT NULL CHECK(amount>0),
    status TEXT NOT NULL,
    dispense_status TEXT NOT NULL DEFAULT 'pending',
    idempotency_key TEXT UNIQUE,
    payment_transaction_id TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_vending_tx_machine_created ON vending_transactions(machine_id,created_at);
