"""Async Modbus TCP API for Nilan devices."""

from __future__ import annotations

import asyncio
import struct
from enum import IntEnum
from typing import Any, Dict, Optional

from pymodbus.client import AsyncModbusTcpClient
from pymodbus.exceptions import ModbusException


class RegisterType(IntEnum):
    Holding = 3
    Input = 4
    Coil = 1
    Discrete = 2


# Register descriptor
Register = Dict[str, Any]
Queries = Dict[str, Register]
Results = Dict[str, float]


def filter_registers(registers: Queries, keys: list[str]) -> Queries:
    """Return a subset of a register map containing only the given keys."""
    return {k: registers[k] for k in keys if k in registers}


def limit_value_range(value: float, min_val: Optional[float], max_val: Optional[float]) -> float:
    if min_val is not None and value < min_val:
        return min_val
    if max_val is not None and value > max_val:
        return max_val
    return value


def _no_modifier(value: int) -> int:
    return value


def _as_int16(value: int) -> int:
    """Reinterpret unsigned 16-bit as signed 16-bit."""
    return (value << 16) >> 16


class ModbusApi:
    """Queue-based async Modbus TCP client."""

    def __init__(self, *, device=None, homey=None, logger=None, on_update_values=None):
        self._device = device
        self._homey = homey
        self._logger = logger if logger else lambda *a: None
        self._on_update_values = on_update_values
        self._client: Optional[AsyncModbusTcpClient] = None
        self._unit_id: int = 1
        self._host: Optional[str] = None
        self._port: int = 502
        self._error_counter: int = 0
        self._socket_timeout_task: Optional[asyncio.Task] = None
        self._queue: asyncio.Queue = asyncio.Queue()
        self._worker_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def reset_socket(self) -> None:
        self._on_socket_timeout()

    async def connect(
        self,
        ip_address: Optional[str] = None,
        port: Optional[int] = None,
        unit_id: Optional[int] = None,
    ) -> Optional[AsyncModbusTcpClient]:
        """Return (or create) a connected Modbus TCP client."""
        async with self._lock:
            if self._client and self._client.connected:
                self._add_socket_timeout()
                return self._client

            # Resolve connection parameters
            host = ip_address or (self._device.get_setting('device-ip') if self._device else None)
            p = port if port is not None else int(
                (self._device.get_setting('device-port') if self._device else None) or 502
            )
            uid = unit_id if unit_id is not None else int(
                (self._device.get_setting('device-id') if self._device else None) or 1
            )

            if not host:
                return None

            self._host = host
            self._port = p
            self._unit_id = uid

            try:
                self._client = AsyncModbusTcpClient(host, port=p)
                connected = await self._client.connect()
                if not connected:
                    self._client = None
                    raise ConnectionError(
                        self._homey.__('pair.connection_refused', {'uri': f'{host}:{p}'})
                        if self._homey else f'Connection refused to {host}:{p}'
                    )
                self._add_socket_timeout()
                return self._client
            except Exception as exc:
                self._client = None
                raise

    def disconnect(self) -> None:
        """Close the Modbus TCP connection."""
        self._clear_socket_timeout()
        if self._client:
            self._client.close()
            self._client = None

    async def read_single(self, name: str, params: Queries) -> Optional[float]:
        """Read a single register by name and return its value."""
        client = await self.connect()
        if client is None:
            return None

        param = params.get(name)
        if param is None:
            return None

        try:
            result = await self._read_register(client, param)
            if result is not None:
                modifier = param.get('modifier_read', _no_modifier)
                scale = param.get('scale', 1) or 1
                raw = _read_int16(result)
                return modifier(raw) / scale
        except Exception as exc:
            self._handle_socket_error('ReadSingle', exc)

        return None

    async def read(self, params: Queries) -> None:
        """Enqueue a batch read of all registers in params."""
        await self._queue.put(params)

        if self._worker_task is None or self._worker_task.done():
            self._worker_task = asyncio.create_task(self._process_queue())

    async def write(self, name: str, params: Queries, value: Any) -> None:
        """Write a value to a named register."""
        param = params.get(name)
        if param is None:
            self._logger('unable to write to register', name, ', entry not found')
            return

        client = await self.connect()
        if client is None:
            return

        try:
            if isinstance(value, bool):
                to_val = 1 if value else 0
            else:
                to_val = float(value) * (param.get('scale', 1) or 1)
                min_v = param.get('min')
                max_v = param.get('max')
                if min_v is not None and to_val < min_v:
                    to_val = min_v
                if max_v is not None and to_val > max_v:
                    to_val = max_v

            modifier = param.get('modifier_write', _no_modifier)
            to_val = int(modifier(to_val))

            self._logger('Write:', param['addr'], name, '=', to_val)
            resp = await client.write_registers(param['addr'], [to_val], slave=self._unit_id)
            if resp is None or resp.isError():
                raise ModbusException(f'Write failed for addr {param["addr"]}')
            self._logger('Write OK:', param['addr'], name)

        except Exception as exc:
            self._handle_socket_error('Write', exc)

    def _handle_socket_error(self, func: str, error: Any) -> None:
        self._error_counter += 1
        self._logger(func, 'error:', error, self._error_counter, 'times')
        if self._error_counter > 5:
            self.reset_socket()

    # ------------------------------------------------------------------ #
    # Internal helpers                                                     #
    # ------------------------------------------------------------------ #

    async def _process_queue(self) -> None:
        """Worker that drains the read queue."""
        while True:
            try:
                params: Queries = self._queue.get_nowait()
            except asyncio.QueueEmpty:
                return
            try:
                client = await self.connect()
            except Exception as exc:
                self._handle_socket_error('Connect', exc)
                continue

            if client is None:
                continue

            matched: Results = {}

            for key, param in params.items():
                try:
                    result = await self._read_register(client, param)
                    if result is not None:
                        modifier = param.get('modifier_read', _no_modifier)
                        scale = param.get('scale', 1) or 1
                        raw = _read_int16(result)
                        val = modifier(raw) / scale
                        matched[key] = val
                except ModbusException as exc:
                    # Individual register unavailable — log and skip, don't penalise the socket
                    self._logger('Read skipped:', key, 'addr', param.get('addr'), '-', exc)
                except Exception as exc:
                    # Unexpected error (e.g. connection dropped mid-batch) — penalise socket
                    self._logger('Read error:', key, 'addr', param.get('addr'), '-', exc)
                    self._handle_socket_error('Read', exc)
                    break  # Stop reading this batch; connection is unreliable

            if matched and self._on_update_values and self._device:
                try:
                    await self._on_update_values(matched, self._device)
                except Exception as exc:
                    self._logger('on_update_values error:', exc)

    async def _read_register(self, client: AsyncModbusTcpClient, param: Register):
        """Dispatch a single register read based on type."""
        addr = param['addr']
        reg_type = param['type']

        if reg_type == RegisterType.Input:
            resp = await client.read_input_registers(addr, count=1, slave=self._unit_id)
        elif reg_type == RegisterType.Holding:
            resp = await client.read_holding_registers(addr, count=1, slave=self._unit_id)
        elif reg_type == RegisterType.Coil:
            resp = await client.read_coils(addr, count=1, slave=self._unit_id)
        elif reg_type == RegisterType.Discrete:
            resp = await client.read_discrete_inputs(addr, count=1, slave=self._unit_id)
        else:
            return None

        if resp is None or resp.isError():
            raise ModbusException(f'Modbus error reading addr {addr}')

        return resp

    def _add_socket_timeout(self) -> None:
        self._clear_socket_timeout()
        self._socket_timeout_task = asyncio.create_task(
            self._socket_timeout_coro(60)
        )

    def _clear_socket_timeout(self) -> None:
        if self._socket_timeout_task and not self._socket_timeout_task.done():
            self._socket_timeout_task.cancel()
        self._socket_timeout_task = None

    async def _socket_timeout_coro(self, seconds: float) -> None:
        await asyncio.sleep(seconds)
        self._on_socket_timeout()

    def _on_socket_timeout(self) -> None:
        self._error_counter = 0
        self._clear_socket_timeout()
        if self._client:
            self._client.close()
            self._client = None


def _read_int16(response) -> int:
    """Extract a signed 16-bit integer from a pymodbus response."""
    try:
        if hasattr(response, 'registers') and response.registers:
            raw = response.registers[0]
            return struct.unpack('>h', struct.pack('>H', int(raw) & 0xFFFF))[0]
        if hasattr(response, 'bits') and response.bits:
            return 1 if response.bits[0] else 0
    except Exception:
        pass
    return 0
