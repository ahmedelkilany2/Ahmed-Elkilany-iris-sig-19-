"""Settings come from environment variables (optionally a local .env file)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

LEGACY_URL = "https://lokalmatador.de/bekanntmachungen"
KIOSK_INDEX_URL = "https://www.nussbaum.de/kiosk/mitteilungsblaetter"


def load_dotenv(path: str | Path = ".env") -> None:
    """Tiny .env reader so I don't need another dependency. Existing env vars win."""
    p = Path(path)
    if not p.is_file():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


@dataclass(frozen=True)
class Settings:
    database_url: str | None
    user_agent: str
    min_delay: float
    timeout: float
    max_retries: int
    index_url: str = KIOSK_INDEX_URL
    legacy_url: str = LEGACY_URL

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            database_url=os.environ.get("IRIS_DATABASE_URL"),
            user_agent=os.environ.get(
                "HARVEST_USER_AGENT", "iris-gazette-harvester/0.1 (research; contact: set HARVEST_USER_AGENT)"
            ),
            min_delay=float(os.environ.get("HARVEST_MIN_DELAY_SECONDS", "10")),
            timeout=float(os.environ.get("HARVEST_TIMEOUT_SECONDS", "20")),
            max_retries=int(os.environ.get("HARVEST_MAX_RETRIES", "3")),
            index_url=os.environ.get("HARVEST_INDEX_URL", KIOSK_INDEX_URL),
        )
