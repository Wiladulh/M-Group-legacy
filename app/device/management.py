class DeviceManagementService:
    ALLOWED_TYPES = {"esp32-cashier", "esp32-vending", "esp32-s3-vending", "cashier", "vending"}
    ALLOWED_STATUS = {"active", "pending", "offline", "disabled", "maintenance", "unassigned"}

    def __init__(self, db):
        self.db = db

    def list(self, include_deleted=False):
        where = "" if include_deleted else "WHERE deleted_at IS NULL"
        with self.db.connect() as c:
            rows = c.execute(
                f"""SELECT device_id,hardware_id,device_type,mac_address,display_name,
                           status,last_seen,auth_key_hint,created_at,updated_at,deleted_at
                    FROM device_registry {where}
                    ORDER BY device_id"""
            ).fetchall()
            return [dict(r) for r in rows]

    def get(self, device_id):
        with self.db.connect() as c:
            row = c.execute(
                """SELECT device_id,hardware_id,device_type,mac_address,display_name,
                          status,last_seen,auth_key_hint,created_at,updated_at,deleted_at
                   FROM device_registry WHERE device_id=?""",
                (device_id,),
            ).fetchone()
            return dict(row) if row else None

    def update(self, device_id, device_type=None, status=None, display_name=None):
        current = self.get(device_id)
        if current is None:
            raise ValueError("device_not_found")
        if device_type is not None and device_type not in self.ALLOWED_TYPES:
            raise ValueError("invalid_device_type")
        if status is not None and status not in self.ALLOWED_STATUS:
            raise ValueError("invalid_device_status")
        if display_name is not None and not display_name.strip():
            raise ValueError("display_name_required")
        new_type = device_type or current["device_type"]
        new_status = status or current["status"]
        new_name = display_name if display_name is not None else current["display_name"]
        with self.db.connect() as c:
            c.execute(
                """UPDATE device_registry
                   SET device_type=?,status=?,display_name=?,updated_at=CURRENT_TIMESTAMP
                   WHERE device_id=?""",
                (new_type, new_status, new_name, device_id),
            )
            c.commit()
        return self.get(device_id)

    def soft_delete(self, device_id):
        current = self.get(device_id)
        if current is None:
            raise ValueError("device_not_found")
        with self.db.connect() as c:
            c.execute(
                """UPDATE device_registry
                   SET status='disabled',deleted_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP
                   WHERE device_id=?""",
                (device_id,),
            )
            c.commit()
        return self.get(device_id)
