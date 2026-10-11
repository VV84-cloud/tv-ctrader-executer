# TradingView Oil 3.0 → Pepperstone cTrader Open API Executor

FastAPI-Ausführungsengine für das Webhookformat der Strategie **WTI Oil EMA9 VWAP Strategy 3.0 - Optimiert**.

## Unterstützte Aktionen

- `ENTRY_LONG`
- `ENTRY_SHORT`
- `EXIT_LONG`
- `EXIT_SHORT`

Unterstützte Exitgründe aus Pine:

- `STOP`
- `BREAK_EVEN`
- `EMA_ADX`
- `TIME_2100`

Die Whitelist erwartet die im Pine-Code tatsächlich verwendete Strategie-ID:

```text
OIL_2_2_OPT_MORNING_AFTERNOON_ADX
```

Der sichtbare Pine-Titel lautet zwar Oil 3.0, die JSON-ID lautet aber Oil 2.2. Die Engine akzeptiert bewusst die JSON-ID, weil nur diese im Webhook ankommt.

## Sicherheitsfunktionen

- Standardmäßig `DRY_RUN=true`
- Demo-Endpoint als Standard
- geheimes Webhook-Token
- Strategie- und Symbol-Whitelist
- Idempotenz über SQLite
- keine zweite Position bei `ALLOW_PYRAMIDING=false`
- Exit nur für Positionen mit dem Label `TV_OIL_3_0`
- Ablehnung veralteter Entry-Signale über `bar_time`
- brokerseitiger relativer Stop beim Entry

## 1. Konfiguration

```bash
cp .env.example .env
```

Eintragen:

```env
CTRADER_CLIENT_ID=...
CTRADER_CLIENT_SECRET=...
CTRADER_ACCESS_TOKEN=...
CTRADER_ACCOUNT_ID=...
CTRADER_SYMBOL=EXAKTER_CTRADER_OEL_SYMBOLNAME
CTRADER_VOLUME=...
WEBHOOK_TOKEN=...
```

### Wichtig: zwei unterschiedliche Symbolnamen

TradingView sendet:

```text
WTOIL-PERP
```

Dieser Wert wird durch `ALLOWED_SYMBOLS=WTOIL-PERP` geprüft.

`CTRADER_SYMBOL` muss dagegen exakt dem Symbolnamen entsprechen, den das Pepperstone-cTrader-Konto über die Open API liefert. Die Engine sucht diesen Namen beim Start in der Symbolliste des Kontos. Deshalb ist in der Vorlage absichtlich kein vermeintlicher Broker-Symbolname vorgegeben.

## 2. Start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Oder mit Docker:

```bash
docker compose up --build -d
```

Health Check:

```bash
curl http://localhost:8000/health
```

## 3. TradingView Alert

Webhook-URL:

```text
https://DEINE-DOMAIN/webhook/DEIN_WEBHOOK_TOKEN
```

Alertbedingung in TradingView:

```text
Any alert() function call
```

Das Pine-Skript erzeugt das JSON dynamisch. Im Nachrichtenfeld des TradingView-Alerts ist daher kein zusätzliches JSON erforderlich.

## 4. Idempotenz ohne signal_id

Das aktuelle Öl-Pine-Skript sendet keine `signal_id`.

- Entry-Signale erhalten eine deterministische ID aus `strategy + bar_time + action`.
- Exit-Signale enthalten aktuell auch kein `bar_time`. Die Engine bildet deshalb eine ID aus Payload und UTC-Minute. Wiederholte identische Exit-Webhooks innerhalb derselben Minute werden ignoriert; ein späterer separater Exit bleibt möglich.

Noch robuster wäre es, zukünftig auch bei Exits `signal_id` und `bar_time` im Pine-JSON zu senden.

## 5. Stop-Loss

Für Entries wird berechnet:

```text
Stopdistanz = abs(signal_price - stop_price)
```

Diese Distanz wird als `relativeStopLoss` an cTrader gesendet. Der Broker berechnet das absolute Stopniveau bezogen auf den tatsächlichen Fill.

## 6. Demo-Aktivierung

1. Zunächst `DRY_RUN=true`.
2. Beispielpayloads gegen den Webhook senden.
3. Dann `DRY_RUN=false` und `CTRADER_ENV=demo`.
4. Im Pepperstone-Demokonto Symbol, Volumen, Fill, Stop, Break-even-Exit, EMA-Exit und 21:00-Uhr-Exit prüfen.
5. Erst nach erfolgreichem Demotest auf das Live-Konto umstellen.

## 7. Tests

```bash
PYTHONPATH=. pytest -q
```
