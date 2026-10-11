import os
from pathlib import Path

os.environ['DRY_RUN'] = 'true'
os.environ['WEBHOOK_TOKEN'] = 'test-token'
os.environ['DB_PATH'] = 'data/oil_test.db'
os.environ['ALLOWED_STRATEGIES'] = 'OIL_2_2_OPT_MORNING_AFTERNOON_ADX'
os.environ['ALLOWED_SYMBOLS'] = 'WTOIL-PERP'
os.environ['MAX_SIGNAL_AGE_SECONDS'] = '0'
Path('data/oil_test.db').unlink(missing_ok=True)

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def entry_payload(bar_time=1760012345000):
    return {
        'strategy': 'OIL_2_2_OPT_MORNING_AFTERNOON_ADX',
        'action': 'ENTRY_LONG',
        'symbol': 'WTOIL-PERP',
        'signal_price': 75.50,
        'stop_price': 75.10,
        'adx_trigger': 21.0,
        'bar_time': bar_time,
    }


def exit_payload():
    return {
        'strategy': 'OIL_2_2_OPT_MORNING_AFTERNOON_ADX',
        'action': 'EXIT_LONG',
        'reason': 'BREAK_EVEN',
        'symbol': 'WTOIL-PERP',
        'signal_price': 75.70,
    }


def test_health():
    result = client.get('/health')
    assert result.status_code == 200
    assert result.json()['dry_run'] is True


def test_oil_entry_without_signal_id_is_idempotent():
    first = client.post('/webhook/test-token', json=entry_payload())
    assert first.status_code == 200
    second = client.post('/webhook/test-token', json=entry_payload())
    assert second.status_code == 200
    assert second.json()['duplicate'] is True


def test_oil_exit_without_signal_id_is_accepted():
    result = client.post('/webhook/test-token', json=exit_payload())
    assert result.status_code == 200
    assert result.json()['accepted'] is True


def test_invalid_short_stop():
    body = entry_payload(1760012346000)
    body['action'] = 'ENTRY_SHORT'
    body['stop_price'] = 75.00
    result = client.post('/webhook/test-token', json=body)
    assert result.status_code == 422


def test_bad_secret():
    result = client.post('/webhook/wrong', json=entry_payload(1760012347000))
    assert result.status_code == 401
