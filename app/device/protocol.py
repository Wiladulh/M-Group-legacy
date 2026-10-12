from dataclasses import dataclass
from datetime import datetime,timezone
@dataclass(frozen=True)
class DeviceEvent:
    device_id:str
    event_type:str
    payload:dict
    created_at:str
    @classmethod
    def create(cls,device_id,event_type,payload):
        return cls(device_id,event_type,payload,datetime.now(timezone.utc).isoformat())
