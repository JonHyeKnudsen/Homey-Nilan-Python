"""CTS602 Device — full device implementation for Nilan CTS602 controllers."""

from __future__ import annotations

import asyncio
import ipaddress
import time
from typing import Any, Dict, List, Optional

from homey.device import Device

from modbus_api import ModbusApi, limit_value_range
from drivers.CTS602.constants import (
    ID_REGISTERS,
    OPERATION_REGISTERS,
    SENSOR_REGISTERS,
    ALARM_REGISTERS,
    CAPABILITIES,
    ValueType,
    new_update_map,
)
from drivers.CTS602.capabilities import (
    get_device_capabilities,
    has_fw_caps,
    cap_is_fw_related,
    cap_is_insights_number,
    cap_is_alarm_related,
)


# Map of driver-settings checkbox id -> capability id that the user can
# show/hide from the device card.
TOGGLEABLE_CAPS: Dict[str, str] = {
    'show-compressor-state': 'compressor_state',
    'show-hot-water-state':  'hot_water_state',
    'show-electric-heater':  'electricheater',
    'show-external-heater':  'externalheater',
    'show-waterpump-state':  'waterpump_state',
}


class CTS602Device(Device):
    """Device class for Nilan CTS602 Modbus controllers."""

    def _make_fetches(self):
        """Return the list of fetch descriptors (re-created on each init)."""
        return [
            {
                'queries': OPERATION_REGISTERS,
                'condition': lambda now, last: True,
                'timeout': 0,
                'last': None,
            },
            {
                'queries': SENSOR_REGISTERS,
                'condition': lambda now, last: (
                    not last
                    or now - last > (self.get_setting('temp-report-interval') or 30) * 1000
                ),
                'timeout': 1000,
                'last': None,
            },
            {
                'queries': ALARM_REGISTERS,
                'condition': lambda now, last: (not last or now - last > 10_000),
                'timeout': 5000,
                'last': None,
            },
            {
                'queries': ID_REGISTERS,
                'condition': lambda now, last: (not last or now - last > 300_000),
                'timeout': 8000,
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
        self.updates: Dict[str, Dict[str, Any]] = new_update_map()
        self._fetch_task: Optional[asyncio.Task] = None
        self.cap_ids: List[str] = []

        data = self.get_data()
        model = data.get('model')
        external_heater = data.get('externalheater', False)
        devid = (int(model) + (1000 if external_heater else 0)) if model is not None else -1

        cap_ids_for_model = get_device_capabilities(devid)
        cur_ids = list(self.get_capabilities())
        did_add_alarms = False

        for cap_id in cap_ids_for_model:
            if cap_id not in cur_ids:
                if cap_id == 'measure_co2':
                    co2_enable = (
                        'hidden_number.co2_enable' not in cur_ids
                        or self.get_capability_value('hidden_number.co2_enable') is None
                        or self.get_capability_value('hidden_number.co2_enable') > 0
                    )
                    if co2_enable:
                        await self.add_capability(cap_id)
                else:
                    await self.add_capability(cap_id)

                try:
                    if cap_is_fw_related(cap_id):
                        await self.set_capability_value(
                            cap_id, '-' if cap_id == 'firmware_version' else ''
                        )
                    elif cap_is_insights_number(cap_id):
                        await self.set_capability_value(cap_id, 0)
                    elif cap_is_alarm_related(cap_id):
                        did_add_alarms = True
                    elif cap_id == 'hidden_number.co2_enable':
                        await self.set_capability_value(cap_id, 1)
                except Exception as err:
                    self.log('failed to set initial capacity value for', cap_id, ':', err)

        self.cap_ids = list(self.get_capabilities())

        await self._sync_toggleable_capabilities()

        if did_add_alarms:
            try:
                await self.reset_alarms()
            except Exception as err:
                self.log('initial alarm reset failed:', err)

        for key, item in self.updates.items():
            if item['id'] in item['queries'] and key in self.cap_ids:
                async def make_listener(k):
                    async def listener(value, **kwargs):
                        await self.update_value(k, value, kwargs)
                    return listener
                self.register_capability_listener(key, await make_listener(key))

        self._add_fetch_timeout(1)
        await self._connect()
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

    async def on_settings(self, old_settings, new_settings, changed_keys):
        if any(k in changed_keys for k in ('device-ip', 'device-port', 'device-id')):
            if not self.get_available():
                await self.set_available()
                self._add_fetch_timeout(1)
            self._api.reset_socket()
        if 'polling-interval' in changed_keys or 'temp-report-interval' in changed_keys:
            self._add_fetch_timeout()
        if any(k in changed_keys for k in TOGGLEABLE_CAPS):
            await self._sync_toggleable_capabilities()

    async def _sync_toggleable_capabilities(self) -> None:
        """Add or remove user-toggleable capabilities to match driver settings."""
        for setting_key, cap_id in TOGGLEABLE_CAPS.items():
            want = self.get_setting(setting_key)
            want = True if want is None else bool(want)
            has = self.has_capability(cap_id)
            if want and not has:
                try:
                    await self.add_capability(cap_id)
                except Exception as err:
                    self.log('add_capability', cap_id, 'failed:', err)
            elif not want and has:
                try:
                    await self.remove_capability(cap_id)
                except Exception as err:
                    self.log('remove_capability', cap_id, 'failed:', err)
        self.cap_ids = list(self.get_capabilities())

    async def ready(self):
        self.log('preparing device')
        await self._connect()

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
        connection_lost = False
        connection_restored = False

        try:
            if self.get_available():
                ip = self.get_setting('device-ip')
                if not ip or ip.endswith('.xxx') or ip == '':
                    self.log('IP address not set')
                    await self.set_unavailable(self.homey.i18n.__('unavailable.set_ip_address'))
                    return

                try:
                    ipaddress.ip_address(ip)
                except ValueError:
                    self.log('Invalid IP address')
                    await self.set_unavailable(self.homey.i18n.__('errors.invalid_ip_address'))
                    return

                if self._api._client is None or not self._api._client.connected:
                    self.log('Connection to device was lost')
                    connection_lost = True
                    await self.set_unavailable(self.homey.i18n.__('errors.connection_lost'))
                else:
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
            else:
                await self._connect()
                if self._api._client and self._api._client.connected:
                    await self.set_available()
                    connection_restored = True
                    self.log('Connection to device was restored')

        except Exception as err:
            self.log('fetchParameters error', err)
        finally:
            if connection_lost:
                self._add_fetch_timeout(5)
            elif connection_restored:
                self._add_fetch_timeout(1)
            else:
                self._add_fetch_timeout()

    # ------------------------------------------------------------------ #
    # Capability value helpers                                             #
    # ------------------------------------------------------------------ #

    async def set_capability_value2(self, cap_id: str, value) -> None:
        if cap_id in self.cap_ids:
            try:
                await self.set_capability_value(cap_id, value)
            except Exception as err:
                self.log(err)

    # ------------------------------------------------------------------ #
    # Value update callbacks                                               #
    # ------------------------------------------------------------------ #

    async def on_update_values(self, result: Dict[str, float], device) -> None:
        if not device.get_available():
            return

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

        # Derived combined capabilities
        if 'Output.WaterHeat' in result and 'Output.WaterHeatEl' in result:
            wh = result['Output.WaterHeat']
            whe = result['Output.WaterHeatEl']
            state = '1' if (wh == 1 and whe == 0) else ('2' if (wh == 1 and whe != 0) else '0')
            await device.set_capability_value2('hot_water_state', state)
            await device.set_capability_value2(
                'insights_number.hot_water_state', int(state))

        if 'Output.Compressor' in result:
            await device.set_capability_value2(
                'insights_number.compressor_state',
                0 if result['Output.Compressor'] == 0 else 1,
            )

        if all(k in result for k in ('Output.CenHeat_1', 'Output.CenHeat_2', 'Output.CenHeat_3')):
            h1 = result['Output.CenHeat_1']
            h2 = result['Output.CenHeat_2']
            h3 = result['Output.CenHeat_3']
            combo = {
                (0, 0, 0): 0,
                (1, 0, 0): 1,
                (0, 1, 0): 2,
                (1, 1, 0): 3,
                (0, 0, 1): 4,
                (1, 0, 1): 5,
                (0, 1, 1): 6,
                (1, 1, 1): 7,
            }.get((int(h1), int(h2), int(h3)), 0)
            await device.set_capability_value2('electricheater', str(combo))
            await device.set_capability_value2('insights_number.electricheater', combo)

        if 'Output.Defrosting' in result:
            await device.set_capability_value2(
                'insights_number.defrosting_state',
                0 if result['Output.Defrosting'] == 0 else 1,
            )

        if 'Output.CenHeatExt' in result:
            await device.set_capability_value2(
                'insights_number.externalheater',
                0 if result['Output.CenHeatExt'] == 0 else 1,
            )

        if 'Output.CenCircPump' in result:
            await device.set_capability_value2(
                'insights_number.waterpump_state',
                0 if result['Output.CenCircPump'] == 0 else 1,
            )

        if 'Control.RunAct' in result:
            await device.set_capability_value2(
                'insights_number.run_state',
                0 if result['Control.RunAct'] == 0 else 1,
            )

        if 'AirFlow.InletAct' in result:
            await device.set_capability_value2(
                'insights_number.ventilation', result['AirFlow.InletAct'])

        # CO2 capability management
        if 'AirQual.CO2_Enable' in result:
            co2_en = result['AirQual.CO2_Enable']
            if co2_en == 0 and 'measure_co2' in device.cap_ids:
                await device.remove_capability('measure_co2')
                device.cap_ids.remove('measure_co2')
            elif co2_en != 0 and 'measure_co2' not in device.cap_ids:
                await device.add_capability('measure_co2')
                device.cap_ids.append('measure_co2')

        # General capability mapping
        for key, value in result.items():
            mapping = CAPABILITIES.get(key)
            if mapping is not None:
                clamped = limit_value_range(
                    value, mapping.get('min'), mapping.get('max'))
                if mapping['type'] != ValueType.Parser:
                    await device.update_number(mapping, clamped)
                else:
                    await device.parse_value(mapping, clamped)

    async def update_number(self, mapping: Dict[str, Any], value: float,
                            override: bool = False) -> None:
        update_key = mapping.get('update')
        if not override and update_key and update_key in self.updates:
            if self.updates[update_key].get('timeout') is not None:
                return

        factor = mapping.get('factor') or 1
        to_value = round(10 * value / factor) * 0.1

        names = mapping['name']
        if isinstance(names, str):
            names = [names]

        for name in names:
            try:
                t = mapping['type']
                if t in (ValueType.State, ValueType.String):
                    await self.set_capability_value2(name, str(to_value))
                elif t == ValueType.Bool:
                    await self.set_capability_value2(name, to_value != 0)
                else:
                    await self.set_capability_value2(name, to_value)
            except Exception as err:
                self.log(err)

    async def parse_value(self, mapping: Dict[str, Any], value: float) -> None:
        update_key = mapping.get('update')
        if update_key and update_key in self.updates:
            if self.updates[update_key].get('timeout') is not None:
                return

        name = mapping['name'] if isinstance(mapping['name'], str) else mapping['name']
        if name in (
            'hidden_string.version_major',
            'hidden_string.version_minor',
            'hidden_string.version_release',
        ):
            ver = self._parse_version_number(int(value))
            if ver != '' and has_fw_caps(self.cap_ids):
                await self.set_capability_value2(name, ver)
                major = self.get_capability_value('hidden_string.version_major')
                minor = self.get_capability_value('hidden_string.version_minor')
                release = self.get_capability_value('hidden_string.version_release')
                current_fw = self.get_capability_value('firmware_version')
                combined = f'{major}.{minor}.{release}'
                if (major and minor and release and current_fw != combined):
                    await self.set_capability_value2('firmware_version', combined)
        else:
            await self.update_number(mapping, value)

    def _parse_version_number(self, value: int) -> str:
        high = (value >> 8) & 0xFF
        low = value & 0xFF
        result = ''
        if 47 < high < 58:
            result += str(high - 48)
        if 47 < low < 58:
            result += str(low - 48)
        return result

    # ------------------------------------------------------------------ #
    # Alarm management                                                     #
    # ------------------------------------------------------------------ #

    async def set_alarms(self, alarms: List[int]) -> None:
        filter_state = self.get_capability_value('alarm_generic.filter')
        alarm_state = self.get_capability_value('alarm_pump_device')

        if alarm_state is False or alarm_state is None:
            if filter_state is True:
                await self.unset_warning()
            await self.set_capability_value2('alarm_pump_device', True)
            await self.set_warning(self.homey.i18n.__('warnings.alarm'))

        for idx, alarm_id in enumerate(alarms[:3], start=1):
            cap = f'alarm_nilan.id{idx}'
            if not self.has_capability(cap):
                await self.add_capability(cap)
            await self.set_capability_value2(cap, str(alarm_id))

        for idx in range(len(alarms) + 1, 4):
            cap = f'alarm_nilan.id{idx}'
            if self.has_capability(cap):
                await self.remove_capability(cap)

        await self.set_capability_value2('hidden_number.alarm_count', len(alarms))

    async def unset_alarms(self) -> None:
        filter_state = self.get_capability_value('alarm_generic.filter')
        alarm_state = self.get_capability_value('alarm_pump_device')

        for idx in range(3, 0, -1):
            cap = f'alarm_nilan.id{idx}'
            if self.has_capability(cap):
                await self.remove_capability(cap)

        if alarm_state is True or alarm_state is None:
            await self.set_capability_value2('alarm_pump_device', False)
            await self.unset_warning()
            if filter_state is True:
                await self.set_warning(self.homey.i18n.__('warnings.filter_change'))
            await self.set_capability_value2('hidden_number.alarm_count', 0)

    async def set_filter_alarm(self) -> None:
        filter_state = self.get_capability_value('alarm_generic.filter')
        alarm_state = self.get_capability_value('alarm_pump_device')
        if filter_state is False or filter_state is None:
            await self.set_capability_value2('alarm_generic.filter', True)
            if alarm_state is not True:
                await self.set_warning(self.homey.i18n.__('warnings.filter_change'))

    async def unset_filter_alarm(self) -> None:
        filter_state = self.get_capability_value('alarm_generic.filter')
        alarm_state = self.get_capability_value('alarm_pump_device')
        if filter_state is True or filter_state is None:
            await self.set_capability_value2('alarm_generic.filter', False)
            if filter_state is True and alarm_state is not True:
                await self.unset_warning()

    async def reset_alarms(self) -> None:
        filter_state = self.get_capability_value('alarm_generic.filter')
        alarm_state = self.get_capability_value('alarm_pump_device')
        warning_state = filter_state is True or alarm_state is True

        if alarm_state in (None, 'null', True):
            await self.set_capability_value2('alarm_pump_device', False)
        if filter_state in (None, 'null', True):
            await self.set_capability_value2('alarm_generic.filter', False)
        if warning_state:
            await self.unset_warning()

        for idx in range(1, 4):
            cap = f'alarm_nilan.id{idx}'
            if self.has_capability(cap):
                await self.remove_capability(cap)

        await self.set_capability_value2('hidden_number.alarm_count', 0)
        await self.set_capability_value2('alarm_pump_device', False)

    async def _previous_alarm_code(self, idx: int) -> int:
        cap = f'alarm_nilan.id{idx}'
        if self.has_capability(cap):
            v = self.get_capability_value(cap)
            if v is not None:
                return int(v)
        return 0

    def _parse_filter(self, status: int, id1: int, id2: int, id3: int, filt: int) -> bool:
        if filt != 0:
            return True
        cnt = status & 0x03
        if cnt > 0 and id1 == 19:
            return True
        if cnt > 1 and id2 == 19:
            return True
        if cnt > 2 and id3 == 19:
            return True
        return False

    def _parse_alarms(self, status: int, id1: int, id2: int, id3: int, filt: int) -> List[int]:
        arr = []
        cnt = status & 0x03
        if cnt > 0:
            if id1 not in (0, 19):
                arr.append(id1)
            if cnt > 1 and id2 not in (0, 19):
                arr.append(id2)
            if cnt > 2 and id3 not in (0, 19):
                arr.append(id3)
        return arr

    async def _parse_previous_alarms(self) -> List[int]:
        arr = []
        prev_count = self.get_capability_value('hidden_number.alarm_count') or 0
        id1 = await self._previous_alarm_code(1)
        id2 = await self._previous_alarm_code(2)
        id3 = await self._previous_alarm_code(3)
        if prev_count > 0 and id1 not in (0, 19):
            arr.append(id1)
        if prev_count > 1 and id2 not in (0, 19):
            arr.append(id2)
        if prev_count > 2 and id3 not in (0, 19):
            arr.append(id3)
        return arr

    def _alarms_changed(self, prev: List[int], current: List[int]) -> bool:
        if len(prev) != len(current):
            return True
        if len(prev) == 0:
            return False
        return prev != current

    async def update_alarms(
        self, status: float, id1: float, id2: float, id3: float, filt: float
    ) -> None:
        try:
            prev_filter_state = self.get_capability_value('alarm_generic.filter')
            prev_alarms = await self._parse_previous_alarms()
            new_alarms = self._parse_alarms(
                int(status), int(id1), int(id2), int(id3), int(filt))
            new_filter_state = self._parse_filter(
                int(status), int(id1), int(id2), int(id3), int(filt))

            if prev_filter_state != new_filter_state:
                if new_filter_state:
                    await self.set_filter_alarm()
                else:
                    await self.unset_filter_alarm()

            if not self._alarms_changed(prev_alarms, new_alarms):
                return

            if len(new_alarms) == 0:
                await self.unset_alarms()
                return

            await self.set_alarms(new_alarms)

        except Exception as err:
            self.log('Update alarms error:', err)

    # ------------------------------------------------------------------ #
    # Write-back (capability → Modbus)                                    #
    # ------------------------------------------------------------------ #

    async def update_value(self, key: str, value: Any, opts: Any) -> None:
        if not self.get_available() or key not in self.updates:
            return

        try:
            self._clear_fetch_timeout()

            item = self.updates[key]

            async def _clear_timeout():
                await asyncio.sleep(5)
                item['timeout'] = None

            item['timeout'] = asyncio.create_task(_clear_timeout())

            factor = item.get('factor', 1) or 1
            to_value = float(value) * factor
            await self._api.write(item['id'], item['queries'], to_value)

            cap = item.get('capability')
            if cap and self.has_capability(cap):
                await self.set_capability_value2(cap, value)

        finally:
            self._add_fetch_timeout()


homey_export = CTS602Device
