CREATE TABLE IF NOT EXISTS financial_transactions(
    transaction_id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL REFERENCES financial_accounts(account_id),
    transaction_type TEXT NOT NULL CHECK(transaction_type IN ('credit','debit')),
    amount INTEGER NOT NULL CHECK(amount>0),
    reference TEXT,
    idempotency_key TEXT,
    status TEXT NOT NULL DEFAULT 'completed',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_financial_tx_idempotency
ON financial_transactions(idempotency_key)
WHERE idempotency_key IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_financial_tx_account_created
ON financial_transactions(account_id,created_at);

CREATE INDEX IF NOT EXISTS ix_financial_ledger_account_created
ON financial_ledger(account_id,created_at);

INSERT OR IGNORE INTO system_meta(key,value)
VALUES('financial_architecture_version','001');
