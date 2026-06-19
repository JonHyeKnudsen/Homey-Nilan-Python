"""CTS700 Device — device implementation for Nilan CTS700 controllers."""

from __future__ import annotations

import asyncio
import ipaddress
import time
from typing import Any, Dict, List, Optional

from homey.device import Device

from modbus_api import ModbusApi, limit_value_range
from drivers.CTS700.constants import (
    SENSOR_REGISTERS,
    CAPABILITIES,
    ValueType,
    new_update_map,
)


class CTS700Device(Device):
    """Device class for Nilan CTS700 Modbus controllers."""

    def _make_fetches(self):
        return [
            {
                'queries': SENSOR_REGISTERS,
                'condition': lambda now, last: (
                    not last
                    or now - last > (self.get_setting('temp-report-interval') or 30) * 1000
                ),
                'timeout': 1000,
                'last': None,
            },
        ]

    # ------------------------------------------------------------------ #
    # Lifecycle                                                            #
    # ------------------------------------------------------------------ #

    async def on_init(self):
        self._api = ModbusApi(
            device=self,
            homey=self.homey,
            logger=self.log,
            on_update_values=self.on_update_values,
        )
        self.fetches = self._make_fetches()
        self.updates: Dict[str, Any] = new_update_map()
        self._fetch_task: Optional[asyncio.Task] = None

        self._add_fetch_timeout(1)
        await self._connect()
        if self._api._client is None or not self._api._client.connected:
            self.log('waiting for connection to device')
        else:
            await self.set_available()
            self.log('device initialized')

    async def on_added(self):
        self.log('device added')

    def on_uninit(self):
        self._api._on_update_values = None
        self._clear_fetch_timeout()
        self._disconnect()
        self.log('device uninitialized')

    def on_deleted(self):
        self._api._on_update_values = None
        self._clear_fetch_timeout()
        self._disconnect()
        self.log('device deleted')

    async def ready(self):
        try:
            await self.reset_alarms()
            self.log('initial values set')
        except Exception as err:
            self.log('failed to set initial capacity values:', err)
        self.log('device ready')
        await self._connect()

    async def on_settings(self, old_settings, new_settings, changed_keys):
        if any(k in changed_keys for k in ('device-ip', 'device-port', 'device-id')):
            if not self.get_available():
                await self.set_available()
                self._add_fetch_timeout(1)
            self._api.reset_socket()
        if 'polling-interval' in changed_keys or 'temp-report-interval' in changed_keys:
            self._add_fetch_timeout()

    # ------------------------------------------------------------------ #
    # Connection helpers                                                   #
    # ------------------------------------------------------------------ #

    async def _connect(self):
        settings = self.get_settings()
        await self._api.connect(
            ip_address=settings.get('device-ip'),
            port=int(settings.get('device-port', 502)),
            unit_id=int(settings.get('device-id', 1)),
        )

    def _disconnect(self):
        self._clear_fetch_timeout()
        if self._api:
            self._api._clear_socket_timeout()
            self._api.disconnect()

    # ------------------------------------------------------------------ #
    # Polling                                                              #
    # ------------------------------------------------------------------ #

    def _add_fetch_timeout(self, seconds: Optional[float] = None):
        self._clear_fetch_timeout()
        settings = self.get_settings()
        interval = seconds if seconds is not None else (settings.get('polling-interval') or 10)
        self._fetch_task = asyncio.create_task(self._delayed_fetch(interval))

    def _clear_fetch_timeout(self):
        if self._fetch_task and not self._fetch_task.done():
            self._fetch_task.cancel()
        self._fetch_task = None

    async def _delayed_fetch(self, seconds: float):
        await asyncio.sleep(seconds)
        await self.fetch_parameters()

    async def fetch_parameters(self):
        ip = self.get_setting('device-ip')
        if not ip or ip.endswith('.xxx') or ip == '':
            self.log('IP address not set')
            await self.set_unavailable(self.homey.i18n.__('unavailable.set_ip_address'))
            self._add_fetch_timeout(5)
            return

        try:
            ipaddress.ip_address(ip)
        except ValueError:
            self.log('Invalid ip address')
            await self.set_unavailable(self.homey.i18n.__('errors.invalid_ip_address'))
            self._add_fetch_timeout(5)
            return

        if self.get_available():
            try:
                settings = self.get_settings()
                await self._api.connect(
                    ip_address=settings.get('device-ip'),
                    port=int(settings.get('device-port', 502)),
                    unit_id=int(settings.get('device-id', 1)),
                )

                now = int(time.time() * 1000)
                for fetch in self.fetches:
                    if fetch['condition'](now, fetch['last']):
                        if fetch['timeout'] == 0:
                            try:
                                await self._api.read(fetch['queries'])
                                fetch['last'] = now
                            except Exception:
                                pass
                        else:
                            async def delayed_read(f, n):
                                await asyncio.sleep(f['timeout'] / 1000)
                                try:
                                    await self._api.read(f['queries'])
                                    f['last'] = n
                                except Exception:
                                    pass
                            asyncio.create_task(delayed_read(fetch, now))

                self._add_fetch_timeout()

            except Exception as err:
                self.log('Connection to device was lost')
                await self.set_unavailable(self.homey.i18n.__('errors.connection_lost'))
                await self._disconnect_async()
                self._add_fetch_timeout(5)

        else:
            try:
                settings = self.get_settings()
                await self._api.connect(
                    ip_address=settings.get('device-ip'),
                    port=int(settings.get('device-port', 502)),
                    unit_id=int(settings.get('device-id', 1)),
                )
                self.log('Device connected')
                await self.set_available()
                self._add_fetch_timeout(2)
            except Exception:
                self._disconnect()
                self._add_fetch_timeout(5)

    async def _disconnect_async(self):
        self._clear_fetch_timeout()
        if self._api:
            self._api._clear_socket_timeout()
            self._api.disconnect()

    # ------------------------------------------------------------------ #
    # Value update callbacks                                               #
    # ------------------------------------------------------------------ #

    async def on_update_values(self, result: Dict[str, float], device) -> None:

        # Alarm processing
        if all(k in result for k in ('Alarm.Status', 'Alarm.List_1_ID',
                                      'Alarm.List_2_ID', 'Alarm.List_3_ID', 'Input.AirFilter')):
            await device.update_alarms(
                result['Alarm.Status'],
                result['Alarm.List_1_ID'],
                result['Alarm.List_2_ID'],
                result['Alarm.List_3_ID'],
                result['Input.AirFilter'],
            )

        for key, value in result.items():
            mapping = CAPABILITIES.get(key)
            if mapping is not None:
                clamped = limit_value_range(
                    value, mapping.get('min'), mapping.get('max'))
                if mapping['type'] != ValueType.Parser:
                    await device.update_number(mapping, clamped)
                else:
                    await device.parse_value(mapping, clamped)

    async def update_number(self, mapping: Dict[str, Any], value: float) -> None:
        factor = mapping.get('factor') or 0.1
        to_value = round(10 * value * factor) * 0.1

        names = mapping['name']
        if isinstance(names, str):
            names = [names]

        for name in names:
            try:
                t = mapping['type']
                if t in (ValueType.State, ValueType.String):
                    await self.set_capability_value(name, str(to_value))
                elif t == ValueType.Bool:
                    await self.set_capability_value(name, to_value != 0)
                else:
                    await self.set_capability_value(name, to_value)
            except Exception as err:
                self.log(err)

    async def parse_value(self, mapping: Dict[str, Any], value: float) -> None:
        name = mapping['name']
        if name in ('filter_days.inlet', 'filter_days.outlet'):
            await self.update_number(mapping, value)

            prev_inlet = self.get_capability_value('alarm_generic.inlet')
            prev_outlet = self.get_capability_value('alarm_generic.outlet')
            new_inlet = (value <= 0) if name == 'filter_days.inlet' else prev_inlet
            new_outlet = (value <= 0) if name == 'filter_days.outlet' else prev_outlet

            if prev_inlet == new_inlet and prev_outlet == new_outlet:
                return

            if prev_inlet != new_inlet:
                await self.set_capability_value('alarm_generic.inlet', new_inlet)
            if prev_outlet != new_outlet:
                await self.set_capability_value('alarm_generic.outlet', new_outlet)

            if not prev_inlet and not prev_outlet and (new_inlet or new_outlet):
                await self.set_warning(self.homey.i18n.__('warnings.filter_change'))
            elif not new_inlet and not new_outlet and (prev_inlet or prev_outlet):
                await self.unset_warning()
        else:
            await self.update_number(mapping, value)

    # ------------------------------------------------------------------ #
    # Alarm management                                                     #
    # ------------------------------------------------------------------ #

    async def reset_alarms(self) -> None:
        prev_inlet = (
            self.get_capability_value('alarm_generic.inlet')
            if self.has_capability('alarm_generic.inlet') else None
        )
        prev_outlet = (
            self.get_capability_value('alarm_generic.outlet')
            if self.has_capability('alarm_generic.outlet') else None
        )

        if self.has_capability('alarm_generic.inlet') and prev_inlet in (None, 'null', True):
            await self.set_capability_value('alarm_generic.inlet', False)
        if self.has_capability('alarm_generic.outlet') and prev_outlet in (None, 'null', True):
            await self.set_capability_value('alarm_generic.outlet', False)

        if prev_inlet or prev_outlet:
            await self.unset_warning()


homey_export = CTS700Device
