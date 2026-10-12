from uuid import uuid4
from app.core.db import Database

class FinancialService:
    def __init__(self, db: Database):
        self.db = db

    def _account(self, c, account_id):
        row = c.execute(
            "SELECT account_id,member_id,account_type,status FROM financial_accounts WHERE account_id=?",
            (account_id,),
        ).fetchone()
        if not row:
            raise ValueError("account_not_found")
        if row["status"] != "active":
            raise ValueError("account_inactive")
        return row

    def balance(self, account_id):
        with self.db.connect() as c:
            self._account(c, account_id)
            row = c.execute(
                "SELECT COALESCE(SUM(CASE WHEN direction='credit' THEN amount ELSE -amount END),0) AS balance "
                "FROM financial_ledger WHERE account_id=?",
                (account_id,),
            ).fetchone()
            return int(row["balance"])

    def ledger(self, account_id, limit=100):
        limit = max(1, min(int(limit), 500))
        with self.db.connect() as c:
            self._account(c, account_id)
            rows = c.execute(
                "SELECT id,account_id,direction,amount,reference,created_at "
                "FROM financial_ledger WHERE account_id=? ORDER BY id DESC LIMIT ?",
                (account_id, limit),
            ).fetchall()
            return [dict(r) for r in rows]

    def _post(self, account_id, amount, transaction_type, reference=None, idempotency_key=None):
        if not isinstance(amount, int) or isinstance(amount, bool) or amount <= 0:
            raise ValueError("amount_must_be_positive_integer")
        if transaction_type not in {"credit", "debit"}:
            raise ValueError("unsupported_transaction_type")

        with self.db.connect() as c:
            existing = None
            if idempotency_key:
                existing = c.execute(
                    "SELECT transaction_id,status,amount,transaction_type,reference "
                    "FROM financial_transactions WHERE idempotency_key=?",
                    (idempotency_key,),
                ).fetchone()
                if existing:
                    return dict(existing)

            account = self._account(c, account_id)

            balance = c.execute(
                "SELECT COALESCE(SUM(CASE WHEN direction='credit' THEN amount ELSE -amount END),0) "
                "FROM financial_ledger WHERE account_id=?",
                (account_id,),
            ).fetchone()[0]

            if transaction_type == "debit" and balance < amount:
                raise ValueError("insufficient_balance")

            transaction_id = "fin-" + uuid4().hex

            c.execute(
                "INSERT INTO financial_transactions "
                "(transaction_id,account_id,transaction_type,amount,reference,idempotency_key,status) "
                "VALUES(?,?,?,?,?,?,?)",
                (transaction_id, account_id, transaction_type, amount, reference, idempotency_key, "completed"),
            )
            c.execute(
                "INSERT INTO financial_ledger(account_id,direction,amount,reference) VALUES(?,?,?,?)",
                (account_id, transaction_type, amount, transaction_id),
            )
            c.execute(
                "INSERT INTO audit_events(event_type,entity_type,entity_id,detail) VALUES(?,?,?,?)",
                ("financial", "financial_transaction", transaction_id,
                 f"{transaction_type}:{amount}:account={account['account_id']}"),
            )
            c.commit()

            return {
                "transaction_id": transaction_id,
                "account_id": account_id,
                "transaction_type": transaction_type,
                "amount": amount,
                "reference": reference,
                "status": "completed",
            }

    def credit(self, account_id, amount, reference=None, idempotency_key=None):
        return self._post(account_id, amount, "credit", reference, idempotency_key)

    def debit_on_connection(self, c, account_id, amount, reference=None, idempotency_key=None):
        if not isinstance(amount, int) or isinstance(amount, bool) or amount <= 0:
            raise ValueError("amount_must_be_positive_integer")
        if idempotency_key:
            row = c.execute(
                "SELECT transaction_id,status,amount,transaction_type,reference "
                "FROM financial_transactions WHERE idempotency_key=?",
                (idempotency_key,),
            ).fetchone()
            if row:
                return dict(row)

        account = self._account(c, account_id)
        balance = c.execute(
            "SELECT COALESCE(SUM(CASE WHEN direction='credit' THEN amount ELSE -amount END),0) "
            "FROM financial_ledger WHERE account_id=?",
            (account_id,),
        ).fetchone()[0]
        if balance < amount:
            raise ValueError("insufficient_balance")

        transaction_id = "fin-" + uuid4().hex
        c.execute(
            "INSERT INTO financial_transactions "
            "(transaction_id,account_id,transaction_type,amount,reference,idempotency_key,status) "
            "VALUES(?,?,?,?,?,?,?)",
            (transaction_id, account_id, "debit", amount, reference, idempotency_key, "completed"),
        )
        c.execute(
            "INSERT INTO financial_ledger(account_id,direction,amount,reference) VALUES(?,?,?,?)",
            (account_id, "debit", amount, transaction_id),
        )
        c.execute(
            "INSERT INTO audit_events(event_type,entity_type,entity_id,detail) VALUES(?,?,?,?)",
            ("financial", "financial_transaction", transaction_id,
             f"debit:{amount}:account={account['account_id']}"),
        )
        return {
            "transaction_id": transaction_id,
            "account_id": account_id,
            "transaction_type": "debit",
            "amount": amount,
            "reference": reference,
            "status": "completed",
        }

    def debit(self, account_id, amount, reference=None, idempotency_key=None):
        return self._post(account_id, amount, "debit", reference, idempotency_key)


    def correct_credit(self, member_id, original_transaction_id, corrected_amount, reason, idempotency_key, operator_id):
        if not isinstance(corrected_amount, int) or isinstance(corrected_amount, bool) or corrected_amount <= 0:
            raise ValueError("corrected_amount_must_be_positive_integer")
        if not isinstance(reason, str) or len(reason.strip()) < 5:
            raise ValueError("correction_reason_required")
        if not isinstance(idempotency_key, str) or len(idempotency_key.strip()) < 8:
            raise ValueError("idempotency_key_required")
        if not isinstance(operator_id, str) or not operator_id.strip():
            raise ValueError("operator_id_required")
        with self.db.connect() as c:
            prior = c.execute("SELECT correction_id,original_transaction_id,member_id,account_id,original_amount,corrected_amount,adjustment_amount,reason,operator_id,created_at FROM financial_corrections WHERE idempotency_key=?", (idempotency_key,)).fetchone()
            if prior:
                prior_original = prior["original_transaction_id"]
                matches = prior["member_id"] == member_id and prior_original == original_transaction_id and prior["corrected_amount"] == corrected_amount
                if not matches:
                    deposit = c.execute("SELECT idempotency_key,member_id,status FROM cashier_deposits WHERE transaction_id=?", (original_transaction_id,)).fetchone()
                    if deposit and deposit["member_id"] == member_id and deposit["status"] == "completed":
                        resolved = c.execute("SELECT transaction_id FROM financial_transactions WHERE idempotency_key=?", ("cashier-deposit:" + deposit["idempotency_key"],)).fetchone()
                        matches = bool(resolved and resolved["transaction_id"] == prior_original and prior["corrected_amount"] == corrected_amount)
                if not matches:
                    raise ValueError("idempotency_key_conflict")
                return {**dict(prior), "replayed": True}
            original = c.execute(
                """SELECT t.transaction_id,t.account_id,t.transaction_type,t.amount,t.status,a.member_id
                   FROM financial_transactions t JOIN financial_accounts a ON a.account_id=t.account_id
                   WHERE t.transaction_id=?""", (original_transaction_id,)
            ).fetchone()
            if not original:
                deposit = c.execute(
                    "SELECT transaction_id,member_id,account_id,amount,idempotency_key,status FROM cashier_deposits WHERE transaction_id=?",
                    (original_transaction_id,)
                ).fetchone()
                if deposit and deposit["status"] == "completed" and deposit["member_id"] == member_id:
                    original = c.execute(
                        """SELECT t.transaction_id,t.account_id,t.transaction_type,t.amount,t.status,a.member_id
                           FROM financial_transactions t JOIN financial_accounts a ON a.account_id=t.account_id
                           WHERE t.idempotency_key=?""",
                        ("cashier-deposit:" + deposit["idempotency_key"],)
                    ).fetchone()
            if not original or original["member_id"] != member_id:
                raise ValueError("original_topup_not_found_for_member")
            if original["transaction_type"] != "credit" or original["status"] != "completed":
                raise ValueError("original_transaction_not_correctable")
            if c.execute("SELECT 1 FROM financial_corrections WHERE original_transaction_id=?", (original_transaction_id,)).fetchone():
                raise ValueError("original_transaction_already_corrected")
            original_amount = int(original["amount"])
            delta = corrected_amount - original_amount
            balance = int(c.execute(
                "SELECT COALESCE(SUM(CASE WHEN direction='credit' THEN amount ELSE -amount END),0) FROM financial_ledger WHERE account_id=?",
                (original["account_id"],)
            ).fetchone()[0])
            if delta < 0 and balance < -delta:
                raise ValueError("insufficient_balance_for_correction")
            correction_id = "corr-" + uuid4().hex
            adjustment_tx_id = "fin-" + uuid4().hex
            if delta:
                tx_type = "credit" if delta > 0 else "debit"
                c.execute(
                    """INSERT INTO financial_transactions(transaction_id,account_id,transaction_type,amount,reference,idempotency_key,status)
                       VALUES(?,?,?,?,?,?, 'completed')""",
                    (adjustment_tx_id, original["account_id"], tx_type, abs(delta),
                     "member-correction:" + original_transaction_id, "correction:" + idempotency_key)
                )
                c.execute(
                    "INSERT INTO financial_ledger(account_id,direction,amount,reference) VALUES(?,?,?,?)",
                    (original["account_id"], tx_type, abs(delta), adjustment_tx_id)
                )
            c.execute(
                """INSERT INTO financial_corrections(correction_id,original_transaction_id,member_id,account_id,
                   original_amount,corrected_amount,adjustment_amount,reason,idempotency_key,operator_id)
                   VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (correction_id, original_transaction_id, member_id, original["account_id"],
                 original_amount, corrected_amount, delta, reason.strip(), idempotency_key.strip(), operator_id.strip())
            )
            c.execute(
                "INSERT INTO audit_events(event_type,entity_type,entity_id,detail) VALUES(?,?,?,?)",
                ("financial_correction", "member", member_id,
                 f"correction_id={correction_id};original_transaction_id={original_transaction_id};before={original_amount};after={corrected_amount};adjustment={delta};operator={operator_id.strip()};reason={reason.strip()}")
            )
            c.commit()
            return {"correction_id": correction_id, "original_transaction_id": original_transaction_id,
                    "member_id": member_id, "account_id": original["account_id"],
                    "original_amount": original_amount, "corrected_amount": corrected_amount,
                    "adjustment_amount": delta, "reason": reason.strip(), "operator_id": operator_id.strip(),
                    "replayed": False}
