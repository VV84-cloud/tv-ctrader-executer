import logging
import threading
from dataclasses import dataclass
from typing import Any

from twisted.internet import reactor, threads
from twisted.internet.defer import inlineCallbacks

from ctrader_open_api import Client, EndPoints, Protobuf, TcpProtocol
from ctrader_open_api.messages.OpenApiMessages_pb2 import (
    ProtoOAAccountAuthReq,
    ProtoOAApplicationAuthReq,
    ProtoOAClosePositionReq,
    ProtoOANewOrderReq,
    ProtoOAReconcileReq,
    ProtoOASymbolsListReq,
)
from ctrader_open_api.messages.OpenApiModelMessages_pb2 import ProtoOAOrderType, ProtoOATradeSide

from .config import Settings

log = logging.getLogger(__name__)


@dataclass
class SymbolInfo:
    symbol_id: int
    name: str


class CTraderGateway:
    def __init__(self, settings: Settings):
        self.settings = settings
        host = EndPoints.PROTOBUF_LIVE_HOST if settings.ctrader_env == 'live' else EndPoints.PROTOBUF_DEMO_HOST
        self.client = Client(host, EndPoints.PROTOBUF_PORT, TcpProtocol)
        self.client.setConnectedCallback(self._connected)
        self.client.setDisconnectedCallback(self._disconnected)
        self.client.setMessageReceivedCallback(self._message_received)
        self.ready = threading.Event()
        self.symbol: SymbolInfo | None = None
        self._thread: threading.Thread | None = None
        self.last_error: str | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run_reactor, name='ctrader-reactor', daemon=True)
        self._thread.start()

    def _run_reactor(self):
        reactor.callWhenRunning(self.client.startService)
        reactor.run(installSignalHandlers=False)

    @inlineCallbacks
    def _connected(self, client):
        try:
            log.info('Connected to cTrader %s endpoint', self.settings.ctrader_env)
            app = ProtoOAApplicationAuthReq(
                clientId=self.settings.ctrader_client_id,
                clientSecret=self.settings.ctrader_client_secret,
            )
            yield client.send(app, responseTimeoutInSeconds=self.settings.request_timeout_seconds)
            account = ProtoOAAccountAuthReq(
                ctidTraderAccountId=self.settings.ctrader_account_id,
                accessToken=self.settings.ctrader_access_token,
            )
            yield client.send(account, responseTimeoutInSeconds=self.settings.request_timeout_seconds)
            symbols_req = ProtoOASymbolsListReq(
                ctidTraderAccountId=self.settings.ctrader_account_id,
                includeArchivedSymbols=False,
            )
            raw = yield client.send(symbols_req, responseTimeoutInSeconds=self.settings.request_timeout_seconds)
            result = Protobuf.extract(raw)
            wanted = self.settings.ctrader_symbol.replace('/', '').replace('.', '').upper()
            for item in result.symbol:
                normalized = item.symbolName.replace('/', '').replace('.', '').upper()
                if normalized == wanted:
                    self.symbol = SymbolInfo(symbol_id=item.symbolId, name=item.symbolName)
                    break
            if not self.symbol:
                raise RuntimeError(f'Symbol {self.settings.ctrader_symbol} not found for this account')
            self.last_error = None
            self.ready.set()
            log.info('cTrader authenticated; symbol %s has id %s', self.symbol.name, self.symbol.symbol_id)
        except Exception as exc:
            self.last_error = str(exc)
            self.ready.clear()
            log.exception('cTrader initialisation failed')

    def _disconnected(self, client, reason):
        self.ready.clear()
        self.last_error = str(reason)
        log.error('cTrader disconnected: %s', reason)

    def _message_received(self, client, message):
        log.debug('cTrader event: %s', Protobuf.extract(message))

    def _blocking_send(self, request) -> Any:
        if not self.ready.wait(timeout=self.settings.request_timeout_seconds):
            raise RuntimeError(f'cTrader not ready: {self.last_error or "initialising"}')
        raw = threads.blockingCallFromThread(
            reactor,
            lambda: self.client.send(request, responseTimeoutInSeconds=self.settings.request_timeout_seconds),
        )
        return Protobuf.extract(raw)

    def reconcile(self):
        request = ProtoOAReconcileReq(ctidTraderAccountId=self.settings.ctrader_account_id)
        return self._blocking_send(request)

    def has_open_position(self, side: str | None = None) -> bool:
        response = self.reconcile()
        if not self.symbol:
            return False
        for pos in response.position:
            td = pos.tradeData
            if td.symbolId != self.symbol.symbol_id:
                continue
            if self.settings.close_only_own_label and td.label != self.settings.ctrader_label:
                continue
            if side == 'BUY' and td.tradeSide != ProtoOATradeSide.Value('BUY'):
                continue
            if side == 'SELL' and td.tradeSide != ProtoOATradeSide.Value('SELL'):
                continue
            return True
        return False

    def place_market_order(self, side: str, signal_price: float, stop_price: float, signal_id: str) -> dict:
        if not self.symbol:
            raise RuntimeError('Symbol is not initialised')
        stop_distance = abs(signal_price - stop_price)
        relative_stop = int(round(stop_distance * 100000))
        if relative_stop <= 0:
            raise ValueError('Calculated relative stop must be positive')
        side_enum = ProtoOATradeSide.Value(side)
        request = ProtoOANewOrderReq(
            ctidTraderAccountId=self.settings.ctrader_account_id,
            symbolId=self.symbol.symbol_id,
            orderType=ProtoOAOrderType.Value('MARKET'),
            tradeSide=side_enum,
            volume=self.settings.ctrader_volume,
            relativeStopLoss=relative_stop,
            label=self.settings.ctrader_label,
            comment=self.settings.ctrader_comment,
            clientOrderId=signal_id[:50],
        )
        response = self._blocking_send(request)
        return {
            'response_type': type(response).__name__,
            'symbol': self.symbol.name,
            'symbol_id': self.symbol.symbol_id,
            'volume_protocol': self.settings.ctrader_volume,
            'relative_stop': relative_stop,
        }

    def close_positions(self, side: str) -> dict:
        if not self.symbol:
            raise RuntimeError('Symbol is not initialised')
        response = self.reconcile()
        expected_side = ProtoOATradeSide.Value(side)
        selected = []
        for position in response.position:
            trade = position.tradeData
            if trade.symbolId != self.symbol.symbol_id or trade.tradeSide != expected_side:
                continue
            if self.settings.close_only_own_label and trade.label != self.settings.ctrader_label:
                continue
            selected.append(position)
        results = []
        for position in selected:
            request = ProtoOAClosePositionReq(
                ctidTraderAccountId=self.settings.ctrader_account_id,
                positionId=position.positionId,
                volume=position.tradeData.volume,
            )
            result = self._blocking_send(request)
            results.append({'position_id': position.positionId, 'response_type': type(result).__name__})
        return {'closed': len(results), 'positions': results}
