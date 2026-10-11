import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from pythonjsonlogger import jsonlogger

from .config import get_settings
from .ctrader import CTraderGateway
from .models import ExecutionResponse, TradingViewSignal
from .store import SignalStore

settings = get_settings()
handler = logging.StreamHandler()
handler.setFormatter(jsonlogger.JsonFormatter('%(asctime)s %(levelname)s %(name)s %(message)s'))
logging.basicConfig(level=settings.log_level.upper(), handlers=[handler], force=True)
log = logging.getLogger('executor')
store = SignalStore(settings.db_path)
gateway = CTraderGateway(settings)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not settings.dry_run:
        required = [settings.ctrader_client_id, settings.ctrader_client_secret, settings.ctrader_access_token]
        if not all(required) or settings.ctrader_account_id <= 0:
            raise RuntimeError('Live execution requires cTrader credentials and CTRADER_ACCOUNT_ID')
        gateway.start()
    yield


app = FastAPI(title='TradingView Oil 3.0 to Pepperstone cTrader Executor', version='1.0.0-oil', lifespan=lifespan)


def validate_signal(signal: TradingViewSignal) -> None:
    if signal.strategy not in settings.strategies:
        raise HTTPException(status_code=403, detail='Strategy is not allowed')
    if signal.symbol.upper() not in settings.symbols:
        raise HTTPException(status_code=403, detail='Symbol is not allowed')
    if settings.max_signal_age_seconds and signal.bar_time:
        age = abs(time.time() - signal.bar_time / 1000)
        if age > settings.max_signal_age_seconds:
            raise HTTPException(status_code=409, detail=f'Signal is stale ({age:.0f}s)')


@app.get('/health')
def health():
    return {
        'status': 'ok',
        'dry_run': settings.dry_run,
        'ctrader_env': settings.ctrader_env,
        'ctrader_ready': settings.dry_run or gateway.ready.is_set(),
        'ctrader_error': gateway.last_error,
        'symbol': settings.ctrader_symbol,
    }


@app.post('/webhook/{token}', response_model=ExecutionResponse)
def webhook(token: str, signal: TradingViewSignal, request: Request):
    if token != settings.webhook_token:
        raise HTTPException(status_code=401, detail='Invalid webhook token')
    validate_signal(signal)
    payload = signal.model_dump()
    if not store.reserve(signal.signal_id, payload):
        return ExecutionResponse(accepted=True, duplicate=True, dry_run=settings.dry_run, action=signal.action, signal_id=signal.signal_id)
    try:
        if settings.dry_run:
            details = {'message': 'DRY_RUN: no broker request sent', 'payload': payload}
        elif signal.action in {'ENTRY_LONG', 'ENTRY_SHORT'}:
            side = 'BUY' if signal.action == 'ENTRY_LONG' else 'SELL'
            if not settings.allow_pyramiding and gateway.has_open_position():
                raise HTTPException(status_code=409, detail='An executor-managed position is already open')
            details = gateway.place_market_order(side, signal.signal_price, signal.stop_price, signal.signal_id)
        elif signal.action == 'EXIT_LONG':
            details = gateway.close_positions('BUY')
        else:
            details = gateway.close_positions('SELL')
        store.finish(signal.signal_id, 'DONE', details)
        log.info('signal_executed', extra={'signal_id': signal.signal_id, 'action': signal.action, 'details': details})
        return ExecutionResponse(accepted=True, dry_run=settings.dry_run, action=signal.action, signal_id=signal.signal_id, details=details)
    except HTTPException as exc:
        store.finish(signal.signal_id, 'REJECTED', {'detail': exc.detail})
        raise
    except Exception as exc:
        store.finish(signal.signal_id, 'ERROR', {'error': str(exc)})
        log.exception('signal_failed', extra={'signal_id': signal.signal_id, 'action': signal.action})
        raise HTTPException(status_code=502, detail=str(exc)) from exc
