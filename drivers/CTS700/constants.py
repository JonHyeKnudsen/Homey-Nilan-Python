"""Constants and capability mappings for the Nilan CTS700 driver."""

from __future__ import annotations
from enum import Enum
from typing import Any, Dict

from modbus_api import filter_registers, Queries
from drivers.CTS700.registers import REGISTERS


class ValueType(Enum):
    Number = 'number'
    State = 'state'
    Parser = 'parser'
    Bool = 'bool'
    String = 'string'


# ------------------------------------------------------------------ #
# Register groups                                                     #
# ------------------------------------------------------------------ #

SENSOR_REGISTERS: Queries = filter_registers(REGISTERS, [
    'prmFilterInlet_TimeThreshold',
    'prmFilterExhaust_TimeThreshold',
    'prmFilterInlet_PassDays',
    'prmFilterExhaust_PassDays',
    'VAL_DEV_RH_SENSOR',
    'DRV_EXT_LN_STATE_Heater',
    'prmTmasterSensor',
    'VAL_DEV_TSENS1',
    'VAL_DEV_TSENS2',
    'VAL_DEV_TSENS3',
    'VAL_DEV_TSENS4',
    'VAL_DEV_TSENS5',
    'VAL_DEV_TSENS6',
    'VAL_DEV_TSENS11',
    'VAL_DEV_TSENS12',
    'prmRegulationMode',
    'prmSystemWorkinMode',
    'prmUserTemperature',
    'prmUserFanSpeed',
])

# ------------------------------------------------------------------ #
# Capability mappings                                                 #
# ------------------------------------------------------------------ #

CAPABILITIES: Dict[str, Dict[str, Any]] = {
    'prmSystemWorkinMode': {
        'name': 'operational_state.systemworkmode',
        'type': ValueType.State,
        'max': 5,
        'factor': 1,
    },
    'prmUserTemperature': {
        'name': 'measure_temperature.user',
        'type': ValueType.Number,
    },
    'prmUserFanSpeed': {
        'name': 'fanspeed',
        'type': ValueType.Number,
        'factor': 1,
    },
    'prmFilterInlet_PassDays': {
        'name': 'filter_days.inlet',
        'type': ValueType.Parser,
        'factor': 1,
    },
    'prmFilterExhaust_PassDays': {
        'name': 'filter_days.outlet',
        'type': ValueType.Parser,
        'factor': 1,
    },
    'VAL_DEV_RH_SENSOR': {
        'name': 'measure_humidity',
        'type': ValueType.Number,
        'factor': 1,
    },
    'DRV_EXT_LN_STATE_Heater': {
        'name': 'operational_state.external',
        'type': ValueType.State,
        'max': 9,
        'factor': 1,
    },
    'prmTmasterSensor': {
        'name': 'measure_temperature.master',
        'type': ValueType.Number,
    },
    'VAL_DEV_TSENS1': {
        'name': 'measure_temperature.outdoor',
        'type': ValueType.Number,
    },
    'VAL_DEV_TSENS2': {
        'name': 'measure_temperature.supply',
        'type': ValueType.Number,
    },
    'VAL_DEV_TSENS3': {
        'name': 'measure_temperature.extract',
        'type': ValueType.Number,
    },
    'VAL_DEV_TSENS4': {
        'name': 'measure_temperature.discharge',
        'type': ValueType.Number,
    },
    'VAL_DEV_TSENS5': {
        'name': 'measure_temperature.cond',
        'type': ValueType.Number,
    },
    'VAL_DEV_TSENS6': {
        'name': 'measure_temperature.evap',
        'type': ValueType.Number,
    },
    'VAL_DEV_TSENS11': {
        'name': 'measure_temperature.water_top',
        'type': ValueType.Number,
    },
    'VAL_DEV_TSENS12': {
        'name': 'measure_temperature.water_bottom',
        'type': ValueType.Number,
    },
    'prmRegulationMode': {
        'name': 'operational_state.regulation',
        'type': ValueType.State,
        'max': 5,
        'factor': 1,
    },
}


def new_update_map() -> Dict[str, Any]:
    return {}


DEVICE_IDENTIFICATION_REGISTER = 'Control.Type'

MACHINE_TYPES: Dict[int, str] = {
    2: 'Comfort light',
    4: 'VPL 15c',
    10: 'CompactS',
    11: 'VP 18comp',
    12: 'VP18cCom',
    13: 'COMFORT',
    19: 'VP 18c',
    20: 'VP 18ek',
    21: 'VP 18cek',
    25: 'VPL 25c',
    31: 'COMFORTn',
    33: 'COMBI 300 N',
    35: 'COMBI 302',
    36: 'COMBI 302 T',
    38: 'VGU180 ek',
    44: 'CompactP',
}
