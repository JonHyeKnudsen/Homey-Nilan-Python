"""CTS602 Driver — handles device pairing for Nilan CTS602 controllers."""

from __future__ import annotations

import ipaddress
from homey.driver import Driver
from modbus_api import ModbusApi
from drivers.CTS602.constants import (
    ID_REGISTERS,
    DEVICE_IDENTIFICATION_REGISTER,
    MACHINE_TYPES,
)


class CTS602Driver(Driver):
    """Driver for Nilan CTS602 Modbus controllers."""

    async def on_init(self):
        self.log('Nilan CTS602 driver has been initialized')

    async def _get_machine_type(self, api: ModbusApi):
        """Read the machine type register and return the type code, or raise on failure."""
        machine_type = await api.read_single(DEVICE_IDENTIFICATION_REGISTER, ID_REGISTERS)

        if machine_type is None:
            raise Exception(self.homey.i18n.__('errors.device_type_read_error'))

        code = int(machine_type)

        if code not in MACHINE_TYPES:
            self.log('Unsupported machine type code', code)
            raise Exception(self.homey.i18n.__('errors.device_unsupported', {'machineType': code}))

        if MACHINE_TYPES[code] == '?':
            self.log('Unsupported machine type code', code, '- reserved for future use')
            raise Exception(self.homey.i18n.__('errors.device_unsupported', {'machineType': code}))

        return code

    async def on_pair(self, session):

        devices = []

        async def on_connection_details_entered(data):
            self.log('onPair: connection_details_entered:', data)

            try:
                ipaddress.ip_address(data['ipaddress'])
            except ValueError:
                raise Exception(self.homey.i18n.__('pair.valid_ip_address'))

            api = ModbusApi(homey=self.homey, logger=self.log)

            await api.connect(
                ip_address=data['ipaddress'],
                port=int(data['port']),
                unit_id=int(data['unitid']),
            )

            machine_type = await self._get_machine_type(api)

            if machine_type is None:
                raise Exception(self.homey.i18n.__('errors.identification_failed'))

            self.log(
                'Machine type', MACHINE_TYPES[machine_type],
                'with type code', machine_type, 'found',
            )

            api.disconnect()

            machine_id = (
                data['ipaddress'] + '.'
                + str(data['port']) + '.'
                + str(data['unitid'])
            )
            self.log('device id: ' + machine_id)

            devices.clear()
            devices.append({
                'name': MACHINE_TYPES[machine_type],
                'data': {
                    'id': machine_id,
                    'model': machine_type,
                    'externalheater': data.get('externalheater', False),
                },
                'settings': {
                    'device-ip': data['ipaddress'],
                    'device-port': data['port'],
                    'device-id': data['unitid'],
                },
            })

            await session.show_view('list_devices')

        async def on_list_devices(data):
            return devices

        session.set_handler('connection_details_entered', on_connection_details_entered)
        session.set_handler('list_devices', on_list_devices)


homey_export = CTS602Driver
