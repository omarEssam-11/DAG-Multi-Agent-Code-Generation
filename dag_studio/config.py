"""Application configuration, driven by environment variables."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv() -> None:
    """Minimal .env loader (no external dependency)."""
    env_file = BASE_DIR / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


_load_dotenv()


@dataclass
class Settings:
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_base_url: str = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model: str = os.getenv("MODEL", "gpt-4o-mini")
    host: str = os.getenv("HOST", "127.0.0.1")
    port: int = int(os.getenv("PORT", "8000"))
    workspace_dir: Path = Path(os.getenv("WORKSPACE_DIR", str(BASE_DIR / "workspace"))).resolve()
    max_concurrency: int = int(os.getenv("MAX_CONCURRENCY", "4"))
    agent_max_steps: int = int(os.getenv("AGENT_MAX_STEPS", "8"))

    @property
    def mode(self) -> str:
        """'live' when an API key is configured, otherwise 'demo' (simulated agents)."""
        return "live" if self.openai_api_key else "demo"


settings = Settings()
