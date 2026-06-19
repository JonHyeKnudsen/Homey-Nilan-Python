"""Modbus register definitions for the Nilan CTS700 controller."""

from modbus_api import RegisterType


def _as_int16(value: int) -> int:
    """Reinterpret unsigned 16-bit as signed 16-bit."""
    return (value << 16) >> 16


def _as_fan_speed(value: int) -> int:
    return ((value << 16) >> 16) - 100


REGISTERS = {
    'prmSystemWorkinMode': {
        'addr': 1047,
        'type': RegisterType.Holding,
        'description': 'System working mode',
        'modifier_read': _as_int16,
    },
    'prmFilterInlet_TimeThreshold': {
        'addr': 1326,
        'type': RegisterType.Holding,
        'description': 'Inlet filter Time threshold',
    },
    'prmFilterExhaust_TimeThreshold': {
        'addr': 1327,
        'type': RegisterType.Holding,
        'description': 'Outlet filter Time threshold',
    },
    'prmFilterInlet_PassDays': {
        'addr': 1328,
        'type': RegisterType.Holding,
        'description': 'Pass days for Inlet software filter',
    },
    'prmFilterExhaust_PassDays': {
        'addr': 1329,
        'type': RegisterType.Holding,
        'description': 'Pass days for Outlet software filter',
    },
    'VAL_DEV_RH_SENSOR': {
        'addr': 4716,
        'type': RegisterType.Holding,
        'description': 'Value of Humidity sensor',
        'modifier_read': _as_int16,
    },
    'prmUserTemperature': {
        'addr': 4746,
        'type': RegisterType.Holding,
        'description': 'User setpoint value',
        'scale': 10,
        'modifier_read': _as_int16,
    },
    'prmUserFanSpeed': {
        'addr': 4747,
        'type': RegisterType.Holding,
        'description': 'User Fan speed setting',
        'modifier_read': _as_fan_speed,
    },
    'DRV_EXT_LN_STATE_Heater': {
        'addr': 5019,
        'type': RegisterType.Holding,
        'description': 'Heater external state',
        'modifier_read': _as_int16,
    },
    'prmTmasterSensor': {
        'addr': 5088,
        'type': RegisterType.Holding,
        'description': 'Temperature of Master sensor',
        'scale': 10,
        'modifier_read': _as_int16,
    },
    'VAL_DEV_TSENS1': {
        'addr': 5152,
        'type': RegisterType.Holding,
        'description': 'Temperature sensor 1',
        'scale': 10,
        'modifier_read': _as_int16,
    },
    'VAL_DEV_TSENS2': {
        'addr': 5153,
        'type': RegisterType.Holding,
        'description': 'Temperature sensor 2',
        'scale': 10,
        'modifier_read': _as_int16,
    },
    'VAL_DEV_TSENS3': {
        'addr': 5154,
        'type': RegisterType.Holding,
        'description': 'Temperature sensor 3',
        'scale': 10,
        'modifier_read': _as_int16,
    },
    'VAL_DEV_TSENS4': {
        'addr': 5155,
        'type': RegisterType.Holding,
        'description': 'Temperature sensor 4',
        'scale': 10,
        'modifier_read': _as_int16,
    },
    'VAL_DEV_TSENS5': {
        'addr': 5156,
        'type': RegisterType.Holding,
        'description': 'Temperature sensor 5',
        'scale': 10,
        'modifier_read': _as_int16,
    },
    'VAL_DEV_TSENS6': {
        'addr': 5157,
        'type': RegisterType.Holding,
        'description': 'Temperature sensor 6',
        'scale': 10,
        'modifier_read': _as_int16,
    },
    'VAL_DEV_TSENS11': {
        'addr': 5162,
        'type': RegisterType.Holding,
        'description': 'Temperature sensor 11',
        'scale': 100,
        'modifier_read': _as_int16,
    },
    'VAL_DEV_TSENS12': {
        'addr': 5163,
        'type': RegisterType.Holding,
        'description': 'Temperature sensor 12',
        'scale': 10,
        'modifier_read': _as_int16,
    },
    'VAL_DEV_TSENS16': {
        'addr': 5167,
        'type': RegisterType.Holding,
        'description': 'Temperature sensor 16',
        'scale': 10,
        'modifier_read': _as_int16,
    },
    'VAL_DEV_TSENS17': {
        'addr': 5168,
        'type': RegisterType.Holding,
        'description': 'Temperature sensor 17',
        'scale': 10,
        'modifier_read': _as_int16,
    },
    'VAL_DEV_TSENS18': {
        'addr': 5169,
        'type': RegisterType.Holding,
        'description': 'Temperature sensor 18',
        'scale': 10,
        'modifier_read': _as_int16,
    },
    'VAL_DEV_TSENS20': {
        'addr': 5171,
        'type': RegisterType.Holding,
        'description': 'Temperature sensor 20',
        'scale': 10,
        'modifier_read': _as_int16,
    },
    'VAL_DEV_TSENS23': {
        'addr': 5174,
        'type': RegisterType.Holding,
        'description': 'Temperature sensor 23',
        'scale': 10,
        'modifier_read': _as_int16,
    },
    'prmRegulationMode': {
        'addr': 5432,
        'type': RegisterType.Holding,
        'description': 'Current regulation mode',
    },
    'prmUserTempDHW': {
        'addr': 5548,
        'type': RegisterType.Holding,
        'description': 'User DHW setpoint value',
        'scale': 10,
        'modifier_read': _as_int16,
    },
}
