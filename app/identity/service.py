import hashlib
import hmac
import secrets
from app.core.db import Database


class IdentityService:
    PIN_ITERATIONS = 120000

    def __init__(self, db: Database):
        self.db = db

    @classmethod
    def _hash_pin(cls, pin, salt):
        return hashlib.pbkdf2_hmac(
            "sha256", pin.encode(), salt.encode(), cls.PIN_ITERATIONS
        ).hex()

    def set_pin(self, member_id, pin, actor_id="system"):
        if not isinstance(pin, str) or not pin.isdigit() or not 4 <= len(pin) <= 6:
            raise ValueError("pin_must_be_4_to_6_digits")
        salt = secrets.token_hex(16)
        digest = self._hash_pin(pin, salt)
        with self.db.connect() as c:
            row = c.execute(
                "SELECT member_id FROM identity_members WHERE member_id=?",
                (member_id,),
            ).fetchone()
            if not row:
                raise ValueError("member_not_found")
            c.execute(
                "UPDATE identity_members SET pin_salt=?,pin_hash=? WHERE member_id=?",
                (salt, digest, member_id),
            )
            c.execute(
                "INSERT INTO audit_events(event_type,entity_type,entity_id,detail) "
                "VALUES(?,?,?,?)",
                ("identity", "member", member_id, f"pin_updated:operator={actor_id}"),
            )
            c.commit()
        return {"member_id": member_id, "status": "pin_set"}

    def verify_pin(self, member_id, pin):
        if not isinstance(pin, str) or not pin.isdigit() or not 4 <= len(pin) <= 6:
            return False
        with self.db.connect() as c:
            row = c.execute(
                "SELECT pin_salt,pin_hash FROM identity_members WHERE member_id=?",
                (member_id,),
            ).fetchone()
        if not row or not row["pin_salt"] or not row["pin_hash"]:
            return False
        return hmac.compare_digest(
            self._hash_pin(pin, row["pin_salt"]), row["pin_hash"]
        )

    def authorize_credential(self, credential_id):
        with self.db.connect() as c:
            r = c.execute(
                "SELECT c.credential_id,c.member_id,c.status,c.enabled,"
                "c.pin_blocked,m.status member_status "
                "FROM identity_credentials c "
                "JOIN identity_members m ON m.member_id=c.member_id "
                "WHERE c.credential_id=?",
                (credential_id,),
            ).fetchone()
            if not r:
                r = c.execute(
                    "SELECT c.credential_id,c.member_id,c.status,c.enabled,"
                    "c.pin_blocked,m.status member_status "
                    "FROM credential_registry c "
                    "JOIN identity_members m ON m.member_id=c.member_id "
                    "WHERE c.credential_id=?",
                    (credential_id,),
                ).fetchone()
        if not r:
            return {"authorized": False, "reason": "credential_not_found"}
        if r["status"] != "active" or r["enabled"] != 1 or r["member_status"] != "active":
            return {"authorized": False, "reason": "inactive"}
        if r["pin_blocked"] == 1:
            return {"authorized": False, "reason": "credential_pin_blocked"}
        return {
            "authorized": True,
            "credential_id": r["credential_id"],
            "member_id": r["member_id"],
            "reason": "authorized",
        }

    def verify_credential_pin(self, credential_id, pin):
        auth = self.authorize_credential(credential_id)
        if not auth["authorized"]:
            raise PermissionError(auth["reason"])

        ok = self.verify_pin(auth["member_id"], pin)
        table = None
        with self.db.connect() as c:
            if c.execute(
                "SELECT 1 FROM identity_credentials WHERE credential_id=?",
                (credential_id,),
            ).fetchone():
                table = "identity_credentials"
            elif c.execute(
                "SELECT 1 FROM credential_registry WHERE credential_id=?",
                (credential_id,),
            ).fetchone():
                table = "credential_registry"

            if not table:
                raise PermissionError("credential_not_found")

            if ok:
                c.execute(
                    f"UPDATE {table} SET pin_failed_attempts=0 WHERE credential_id=?",
                    (credential_id,),
                )
                c.execute(
                    "INSERT INTO audit_events(event_type,entity_type,entity_id,detail) "
                    "VALUES(?,?,?,?)",
                    ("identity", "credential", credential_id, "pin_verified"),
                )
                c.commit()
                return True

            c.execute(
                f"UPDATE {table} SET pin_failed_attempts=pin_failed_attempts+1 "
                "WHERE credential_id=?",
                (credential_id,),
            )
            c.execute(
                "INSERT INTO audit_events(event_type,entity_type,entity_id,detail) "
                "VALUES(?,?,?,?)",
                ("identity", "credential", credential_id, "pin_failed"),
            )
            c.commit()

        return False

    def unblock_credential_pin(self, credential_id):
        with self.db.connect() as c:
            table = None
            if c.execute(
                "SELECT 1 FROM identity_credentials WHERE credential_id=?",
                (credential_id,),
            ).fetchone():
                table = "identity_credentials"
            elif c.execute(
                "SELECT 1 FROM credential_registry WHERE credential_id=?",
                (credential_id,),
            ).fetchone():
                table = "credential_registry"
            if not table:
                raise ValueError("credential_not_found")
            c.execute(
                f"UPDATE {table} SET pin_failed_attempts=0,pin_blocked=0 "
                "WHERE credential_id=?",
                (credential_id,),
            )
            c.execute(
                "INSERT INTO audit_events(event_type,entity_type,entity_id,detail) "
                "VALUES(?,?,?,?)",
                ("identity", "credential", credential_id, "pin_unblocked"),
            )
            c.commit()
        return {"credential_id": credential_id, "status": "pin_unblocked"}

    def account_for_credential(self, credential_id):
        auth = self.authorize_credential(credential_id)
        if not auth["authorized"]:
            return {"authorized": False, "reason": auth["reason"]}
        with self.db.connect() as c:
            r = c.execute(
                "SELECT account_id,account_type,status FROM financial_accounts "
                "WHERE member_id=? AND status='active' "
                "ORDER BY CASE WHEN account_type='savings' THEN 0 ELSE 1 END, "
                "created_at LIMIT 1",
                (auth["member_id"],),
            ).fetchone()
        if not r:
            return {"authorized": False, "reason": "account_not_found"}
        return {
            "authorized": True,
            "credential_id": credential_id,
            "member_id": auth["member_id"],
            "account_id": r["account_id"],
            "account_type": r["account_type"],
        }
