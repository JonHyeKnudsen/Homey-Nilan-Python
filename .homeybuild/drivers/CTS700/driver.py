"""CTS700 Driver — handles device pairing for Nilan CTS700 controllers."""

from __future__ import annotations

import ipaddress
import asyncio
from homey.driver import Driver
from modbus_api import ModbusApi


class CTS700Driver(Driver):
    """Driver for Nilan CTS700 Modbus controllers."""

    async def on_init(self):
        self.log('Nilan CTS700 driver has been initialized')

    async def on_pair(self, session):

        devices = []

        async def on_connection_details_entered(data):
            self.log('onPair: connection_details_entered:', data)

            try:
                ipaddress.ip_address(data['ipaddress'])
            except ValueError:
                raise Exception(self.homey.i18n.__('pair.valid_ip_address'))

            api = ModbusApi(homey=self.homey, logger=self.log)
            try:
                # Protect against a stalled TCP connect; fail fast for the pairing UI
                await asyncio.wait_for(
                    api.connect(
                        ip_address=data['ipaddress'],
                        port=int(data['port']),
                        unit_id=int(data['unitid']),
                    ),
                    timeout=10,
                )
            except asyncio.TimeoutError:
                self.log('onPair: connection timeout')
                raise Exception(self.homey.i18n.__('pair.connection_timeout'))
            finally:
                api.disconnect()

            machine_id = (
                data['ipaddress'] + '.'
                + str(data['port']) + '.'
                + str(data['unitid'])
            )

            devices.clear()
            devices.append({
                'name': 'Compact P - Air 9',
                'data': {
                    'id': machine_id,
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


homey_export = CTS700Driver
