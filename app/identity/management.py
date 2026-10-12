from uuid import uuid4


class MemberManagementService:
    ALLOWED_STATUS = {"active", "inactive", "suspended"}

    def __init__(self, db):
        self.db = db

    def list(self, include_deleted=False):
        where = "" if include_deleted else "WHERE deleted_at IS NULL"
        with self.db.connect() as c:
            rows = c.execute(
                f"""
                SELECT member_id,name,status,nik,address,birth_place,birth_date,sex,rt,rw,village,district,city_regency,province,religion,marital_status,occupation,citizenship,phone,email,registration_date,created_at,deleted_at,
                       COALESCE((SELECT c.status FROM member_nfc_cards c WHERE c.member_id=identity_members.member_id AND c.status='active' ORDER BY c.created_at DESC LIMIT 1),'unregistered') AS nfc_credential_status
                FROM identity_members
                {where}
                ORDER BY created_at DESC
                """
            ).fetchall()
            return [dict(r) for r in rows]

    def get(self, member_id):
        with self.db.connect() as c:
            row = c.execute(
                """
                SELECT member_id,name,status,nik,address,birth_place,birth_date,sex,rt,rw,village,district,city_regency,province,religion,marital_status,occupation,citizenship,phone,email,registration_date,created_at,deleted_at
                FROM identity_members WHERE member_id=?
                """,
                (member_id,),
            ).fetchone()
            if row is None:
                return None
            cards = c.execute(
                """
                SELECT card_id,member_id,credential_id,CASE WHEN length(card_uid)>4 THEN substr(card_uid,1,2)||'••••'||substr(card_uid,-2) ELSE '••••' END AS card_uid,status,created_at,revoked_at
                FROM member_nfc_cards WHERE member_id=? ORDER BY created_at DESC
                """,
                (member_id,),
            ).fetchall()
            result = dict(row)
            result["nfc_cards"] = [dict(x) for x in cards]
            return result

    def create(self, member_id, name, nik=None, address=None, birth_place=None, birth_date=None, sex=None, rt=None, rw=None, village=None, district=None, city_regency=None, province=None, religion=None, marital_status=None, occupation=None, citizenship=None, phone=None, email=None, registration_date=None):
        member_id = (member_id or "").strip()
        name = (name or "").strip()
        nik = (nik or "").strip() or None
        address = (address or "").strip() or None
        if not member_id or not name:
            raise ValueError("member_id_and_name_required")
        with self.db.connect() as c:
            try:
                c.execute(
                    """
                    INSERT INTO identity_members(member_id,name,status,nik,address,birth_place,birth_date,sex,rt,rw,village,district,city_regency,province,religion,marital_status,occupation,citizenship,phone,email,registration_date)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (member_id, name, "active", nik, address, birth_place, birth_date, sex, rt, rw, village, district, city_regency, province, religion, marital_status, occupation, citizenship, phone, email, registration_date),
                )
                c.commit()
            except Exception as exc:
                if "UNIQUE" in str(exc).upper():
                    raise ValueError("member_id_or_nik_already_exists") from exc
                raise
        return self.get(member_id)

    def update(self, member_id, name=None, nik=None, address=None, status=None, birth_place=None, birth_date=None, sex=None, rt=None, rw=None, village=None, district=None, city_regency=None, province=None, religion=None, marital_status=None, occupation=None, citizenship=None, phone=None, email=None, registration_date=None):
        current = self.get(member_id)
        if current is None:
            raise ValueError("member_not_found")
        values = {
            "name": current["name"] if name is None else (name or "").strip(),
            "nik": current["nik"] if nik is None else ((nik or "").strip() or None),
            "address": current["address"] if address is None else ((address or "").strip() or None),
            "status": current["status"] if status is None else status,
            "birth_place": current["birth_place"] if birth_place is None else birth_place,
            "birth_date": current["birth_date"] if birth_date is None else birth_date,
            "sex": current["sex"] if sex is None else sex,
            "rt": current["rt"] if rt is None else rt,
            "rw": current["rw"] if rw is None else rw,
            "village": current["village"] if village is None else village,
            "district": current["district"] if district is None else district,
            "city_regency": current["city_regency"] if city_regency is None else city_regency,
            "province": current["province"] if province is None else province,
            "religion": current["religion"] if religion is None else religion,
            "marital_status": current["marital_status"] if marital_status is None else marital_status,
            "occupation": current["occupation"] if occupation is None else occupation,
            "citizenship": current["citizenship"] if citizenship is None else citizenship,
            "phone": current["phone"] if phone is None else phone,
            "email": current["email"] if email is None else email,
            "registration_date": current["registration_date"] if registration_date is None else registration_date,
        }
        if not values["name"]:
            raise ValueError("name_required")
        if values["status"] not in self.ALLOWED_STATUS:
            raise ValueError("invalid_member_status")
        with self.db.connect() as c:
            try:
                c.execute(
                    """
                    UPDATE identity_members
                    SET name=?,nik=?,address=?,status=?,birth_place=?,birth_date=?,sex=?,rt=?,rw=?,village=?,district=?,city_regency=?,province=?,religion=?,marital_status=?,occupation=?,citizenship=?,phone=?,email=?,registration_date=?
                    WHERE member_id=?
                    """,
                    (values["name"], values["nik"], values["address"], values["status"], values["birth_place"], values["birth_date"], values["sex"], values["rt"], values["rw"], values["village"], values["district"], values["city_regency"], values["province"], values["religion"], values["marital_status"], values["occupation"], values["citizenship"], values["phone"], values["email"], values["registration_date"], member_id),
                )
                c.commit()
            except Exception as exc:
                if "UNIQUE" in str(exc).upper():
                    raise ValueError("nik_already_exists") from exc
                raise
        return self.get(member_id)

    def soft_delete(self, member_id):
        if self.get(member_id) is None:
            raise ValueError("member_not_found")
        with self.db.connect() as c:
            c.execute(
                """
                UPDATE identity_members
                SET status='inactive',deleted_at=CURRENT_TIMESTAMP
                WHERE member_id=?
                """,
                (member_id,),
            )
            c.commit()
        return self.get(member_id)

    def add_card(self, member_id, card_uid, credential_id=None):
        if self.get(member_id) is None:
            raise ValueError("member_not_found")
        card_uid = (card_uid or "").strip()
        if not card_uid:
            raise ValueError("card_uid_required")
        card_id = "nfc-" + uuid4().hex
        with self.db.connect() as c:
            try:
                c.execute(
                    """
                    INSERT INTO member_nfc_cards
                    (card_id,member_id,credential_id,card_uid,status)
                    VALUES(?,?,?,?, 'active')
                    """,
                    (card_id, member_id, credential_id, card_uid),
                )
                c.commit()
            except Exception as exc:
                if "UNIQUE" in str(exc).upper():
                    raise ValueError("nfc_card_already_registered") from exc
                raise
        return self.get(member_id)

    def revoke_card(self, card_id):
        with self.db.connect() as c:
            row = c.execute(
                "SELECT member_id FROM member_nfc_cards WHERE card_id=?",
                (card_id,),
            ).fetchone()
            if row is None:
                raise ValueError("nfc_card_not_found")
            c.execute(
                """
                UPDATE member_nfc_cards
                SET status='revoked',revoked_at=CURRENT_TIMESTAMP
                WHERE card_id=?
                """,
                (card_id,),
            )
            c.commit()
            member_id = row["member_id"]
        return self.get(member_id)

    def resolve_card(self, card_uid):
        with self.db.connect() as c:
            row = c.execute(
                """
                SELECT c.card_id,c.member_id,c.credential_id,
                       m.name,m.status AS member_status,m.deleted_at
                FROM member_nfc_cards c
                JOIN identity_members m ON m.member_id=c.member_id
                WHERE c.card_uid=? AND c.status='active'
                """,
                ((card_uid or "").strip(),),
            ).fetchone()
            if row is None or row["member_status"] != "active" or row["deleted_at"] is not None:
                return None
            return dict(row)
