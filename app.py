from homey.app import App


class NilanApp(App):
    """Nilan Air Homey app."""

    async def on_init(self):
        await self._init_flows()
        self.log('NilanApp is running...')

    async def _init_flows(self):

        def _device_listener(capability, arg_key):
            async def _run(args, state):
                device = args.get('device') if isinstance(args, dict) else None
                if device is None:
                    self.log('flow action missing device argument')
                    return False
                value = args.get(arg_key) if isinstance(args, dict) else None
                return await device.trigger_capability_listener(capability, value)
            return _run

        set_water_temperature = _device_listener('target_temperature.water', 'temperature')
        set_state = _device_listener('pump_mode.run', 'state')
        set_mode = _device_listener('pump_mode.mode', 'mode')
        set_air_exchange = _device_listener('pump_mode.air_exchange', 'mode')
        set_power_save = _device_listener('pump_mode.power_save', 'state')
        set_fan_speed = _device_listener('fan_mode.ventilation', 'speed')

        self.homey.flow.get_action_card('nilan_set_water_temperature') \
            .register_run_listener(set_water_temperature)

        self.homey.flow.get_action_card('nilan_set_state') \
            .register_run_listener(set_state)

        self.homey.flow.get_action_card('nilan_set_mode') \
            .register_run_listener(set_mode)

        self.homey.flow.get_action_card('nilan_set_air_exchange') \
            .register_run_listener(set_air_exchange)

        self.homey.flow.get_action_card('nilan_set_power_save') \
            .register_run_listener(set_power_save)

        self.homey.flow.get_action_card('nilan_set_fan_speed') \
            .register_run_listener(set_fan_speed)


homey_export = NilanApp
