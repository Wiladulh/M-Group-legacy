from dataclasses import dataclass
from pathlib import Path
import os

@dataclass(frozen=True)
class Settings:
    data_dir: Path
    host: str
    port: int
    db_path: Path
    admin_token: str

def get_settings() -> Settings:
    data_dir=Path(os.getenv("NVM_DATA_DIR",str(Path.home()/".local/share/nvm"))).expanduser()
    return Settings(
        data_dir,
        os.getenv("NVM_HOST","127.0.0.1"),
        int(os.getenv("NVM_PORT","8011")),
        Path(os.getenv("NVM_DB_PATH",str(data_dir/"nvm.db"))).expanduser(),
        os.getenv("NVM_ADMIN_TOKEN",""),
    )
