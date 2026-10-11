from typing import Literal
import hashlib
import json
import time
from pydantic import BaseModel, Field, model_validator

Action = Literal['ENTRY_LONG', 'ENTRY_SHORT', 'EXIT_LONG', 'EXIT_SHORT']


class TradingViewSignal(BaseModel):
    strategy: str
    signal_id: str | None = None
    symbol: str = 'WTOIL-PERP'
    action: Action
    side: Literal['BUY', 'SELL'] | None = None
    signal_price: float = Field(gt=0)
    stop_price: float | None = None
    htf_trend: str | None = None
    counter_trend: bool | None = None
    adx: float | None = None
    adx_trigger: float | None = None
    volume_factor: float | None = None
    timeframe: str | None = None
    bar_time: int | None = None
    reason: str | None = None

    @model_validator(mode='after')
    def validate_semantics(self):
        if self.action.startswith('ENTRY_'):
            if self.stop_price is None:
                raise ValueError('stop_price is required for entries')
            if self.action == 'ENTRY_LONG' and self.stop_price >= self.signal_price:
                raise ValueError('Long stop must be below signal_price')
            if self.action == 'ENTRY_SHORT' and self.stop_price <= self.signal_price:
                raise ValueError('Short stop must be above signal_price')
        if self.signal_id is None:
            # Oil 3.0 webhooks do not currently include signal_id. Entries contain
            # bar_time; exits are deduplicated per UTC minute and payload content.
            if self.bar_time:
                self.signal_id = f'{self.strategy}:{self.bar_time}:{self.action}'
            else:
                payload = {
                    'strategy': self.strategy,
                    'symbol': self.symbol,
                    'action': self.action,
                    'signal_price': self.signal_price,
                    'reason': self.reason,
                    'minute': int(time.time() // 60),
                }
                digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:20]
                self.signal_id = f'{self.strategy}:{self.action}:{digest}'
        return self


class ExecutionResponse(BaseModel):
    accepted: bool
    duplicate: bool = False
    dry_run: bool = False
    action: str
    signal_id: str
    details: dict = {}
