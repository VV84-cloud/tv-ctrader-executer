from functools import lru_cache
from pathlib import Path
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    dry_run: bool = True
    ctrader_env: str = 'demo'
    ctrader_client_id: str = ''
    ctrader_client_secret: str = ''
    ctrader_access_token: str = ''
    ctrader_account_id: int = 0
    ctrader_symbol: str = 'replace_with_exact_pepperstone_oil_symbol'
    ctrader_volume: int = Field(default=100, gt=0)
    ctrader_label: str = 'TV_OIL_3_0'
    ctrader_comment: str = 'TradingView Oil 3.0 Optimiert'

    webhook_token: str = 'change-me'
    allowed_strategies: str = 'OIL_2_2_OPT_MORNING_AFTERNOON_ADX'
    allowed_symbols: str = 'WTOIL-PERP'
    max_signal_age_seconds: int = Field(default=300, ge=0)
    allow_pyramiding: bool = False
    close_only_own_label: bool = True
    request_timeout_seconds: int = Field(default=10, ge=2, le=60)
    db_path: str = 'data/oil_execution.db'
    log_level: str = 'INFO'

    @field_validator('ctrader_env')
    @classmethod
    def validate_environment(cls, value: str) -> str:
        value = value.lower()
        if value not in {'demo', 'live'}:
            raise ValueError('CTRADER_ENV must be demo or live')
        return value

    @property
    def strategies(self) -> set[str]:
        return {item.strip() for item in self.allowed_strategies.split(',') if item.strip()}

    @property
    def symbols(self) -> set[str]:
        return {item.strip().upper() for item in self.allowed_symbols.split(',') if item.strip()}

    def ensure_runtime_paths(self) -> None:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_runtime_paths()
    return settings
