"""Ready-made monitoring points; each preset becomes a monitoring point with its checks."""
from datetime import time

TEMP = {"parameter": "Temperature", "unit": "°C", "value_type": "number"}
YES_NO = {"parameter": "Check", "unit": None, "value_type": "yes_no"}
ITEM = {"require_reference": True, "reference_label": "Item or product name"}
LOTS = {"trace_lots": True}
START = {"phase": "start"}
FINISH = {"phase": "finish"}


def at(hour: int, minute: int = 0) -> dict:
    return {"timing": "checkpoint", "time_of_day": time(hour, minute)}


def _fryer_oil_checks() -> list[dict]:
    """The daily TPM oil test: the reading (amber from 20%, fail above 25%), the oil's heat and, if wanted, how the oil looks. More times a day can be added to the check."""
    when = at(15)
    return [
        {"stage": "TPM reading", "parameter": "TPM", "unit": "%", "value_type": "number", **when, "min_value": 0, "max_value": 25, "warn_max": 20, "source": "independent_probe"},
        {"stage": "Oil temperature", **TEMP, **when, "min_value": 160, "max_value": 190, "source": "independent_probe"},
        {"stage": "Oil look and smell", "parameter": "Condition", "unit": None, "value_type": "choice", **when, "required": False,
         "options": ["Normal", "Dark", "Foaming", "Smoking", "Off smell"], "fail_options": ["Foaming", "Smoking", "Off smell"]},
    ]


TEMPLATES = [
    {"key": "chiller", "name": "Chiller or fridge", "prefix": "CH", "type": "Cold storage", "checks": [
        {"stage": "Morning temperature", **TEMP, **at(8), "min_value": 0, "max_value": 5, "source": "independent_probe"},
        {"stage": "Afternoon temperature", **TEMP, **at(16), "min_value": 0, "max_value": 5, "source": "independent_probe"}]},
    {"key": "freezer", "name": "Freezer", "prefix": "FZ", "type": "Cold storage", "checks": [
        {"stage": "Morning temperature", **TEMP, **at(8), "min_value": -40, "max_value": -18, "source": "independent_probe"},
        {"stage": "Afternoon temperature", **TEMP, **at(16), "min_value": -40, "max_value": -18, "source": "independent_probe"}]},
    {"key": "defrosting", "name": "Defrosting log", "prefix": "DF", "type": "Defrosting", "checks": [
        {"stage": "Time in", **TEMP, **at(9), **LOTS, **START, "min_value": -40, "max_value": -18, "source": "independent_probe", "max_open_minutes": 24 * 60},  # frozen going in; the time out is due after 24 hours
        {"stage": "Time out", **YES_NO, "parameter": "Fully defrosted", "timing": "checkpoint", **FINISH},
        {"stage": "Time out", **TEMP, "timing": "checkpoint", **FINISH, "min_value": 0, "max_value": 5, "source": "independent_probe"}]},
    {"key": "cooking", "name": "Cooking core temperature", "prefix": "CK", "type": "Cooking", "checks": [
        {"stage": "Lunch core temperature", **TEMP, **at(12), **ITEM, "min_value": 75, "max_value": 120, "source": "independent_probe"},
        {"stage": "Dinner core temperature", **TEMP, **at(18), **ITEM, "min_value": 75, "max_value": 120, "source": "independent_probe"}]},
    {"key": "reheating", "name": "Reheating", "prefix": "RH", "type": "Reheating", "checks": [
        {"stage": "Core temperature after reheating", **TEMP, **at(12), **LOTS, "min_value": 75, "max_value": 120,
         "source": "independent_probe"}]},
    {"key": "cooling", "name": "Cooling", "prefix": "CL", "type": "Cooling", "checks": [
        {"stage": "Time in", **TEMP, **at(14), **LOTS, **START, "min_value": 60, "max_value": 100, "source": "independent_probe"},
        {"stage": "Time out", **TEMP, "timing": "checkpoint", **FINISH, "min_value": -5, "max_value": 10, "source": "independent_probe"}]},
    {"key": "hot_holding", "name": "Hot holding", "prefix": "HH", "type": "Hot holding", "checks": [
        {"stage": "Holding temperature", **TEMP, "timing": "interval", "interval_minutes": 120, "time_of_day": time(11, 0),
         "min_value": 63, "max_value": 100, "source": "independent_probe"}]},
    {"key": "sanitiser", "name": "Sanitiser concentration", "prefix": "SN", "type": "Sanitising", "checks": [
        {"stage": "Start of day strength", "parameter": "Concentration", "unit": "ppm", "value_type": "number", **at(7),
         "min_value": 200, "max_value": 400, "source": "independent_probe"}]},
    {"key": "dishwasher", "name": "Dishwasher", "prefix": "DW", "type": "Dishwasher", "checks": [
        {"stage": "Wash", **TEMP, "timing": "startup", "min_value": 55, "max_value": 65},
        {"stage": "Final rinse", **TEMP, "timing": "startup", "min_value": 80, "max_value": 90}]},
    {"key": "goods_receiving", "name": "Goods receiving traceability", "prefix": "GR", "type": "Traceability", "checks": [
        {"stage": "Delivery temperature", **TEMP, **at(10), "min_value": -25, "max_value": 5, "require_reference": True,
         "source": "independent_probe"},
        {"stage": "Labels, batch and expiry checked", **YES_NO, **at(10, 30), "require_reference": True}]},
    {"key": "fryer_oil", "name": "Frying oil (TPM)", "prefix": "FO", "type": "Frying oil", "checks": _fryer_oil_checks()},
    {"key": "probe_calibration", "name": "Probe calibration", "prefix": "PC", "type": "Calibration", "checks": [
        {"stage": "Ice water test", **YES_NO, **at(8), "weekdays": "0"}]},
]
BY_KEY = {t["key"]: t for t in TEMPLATES}


def _timed(check: dict) -> bool:
    """A check that falls at a set clock time (a time in is one); startup, every-N-minutes, on-demand and time-out checks do not."""
    return check.get("timing") == "checkpoint" and check.get("time_of_day") is not None


def _signature(group: list[dict]) -> tuple:
    return tuple(sorted((c["parameter"], c["value_type"], str(c.get("min_value")), str(c.get("max_value")), str(c.get("phase"))) for c in group))


def _groups(preset: dict) -> dict:
    groups: dict = {}
    for c in preset["checks"]:
        if _timed(c):
            groups.setdefault(c["time_of_day"], []).append(c)
    return groups


def _same_check_each_time(groups: dict) -> bool:
    """Morning and afternoon temperature are one check at two times; a delivery temperature and a label check are different checks."""
    return len({_signature(g) for g in groups.values()}) == 1


def default_times(preset: dict) -> list[time] | None:
    """The times a day a template is checked at, or none when it has no clock times to change (startup or every-N-minutes checks).
    A template whose timed checks are different checks (delivery temperature, then labels) gives its first time: they are all done together."""
    groups = _groups(preset)
    if not groups:
        return None
    return sorted(groups) if _same_check_each_time(groups) else [min(groups)]


def with_times(preset: dict, times: list[time]) -> list[dict]:
    """The template's timed checks repeated at the chosen times, with its other checks (such as a time out) kept as they are.
    The first set of checks is the pattern when every time has the same check, so a chiller asked for three times gets three temperature checks."""
    groups = _groups(preset)
    same = _same_check_each_time(groups)
    pattern = groups[min(groups)] if same else [c for g in groups.values() for c in g]
    single = same and len(pattern) == 1 and len(groups) > 1 and not pattern[0].get("phase")  # "Morning temperature" and "Afternoon temperature" become "Temperature" at each time
    fixed = [c for c in preset["checks"] if not _timed(c)]
    return [{**c, "time_of_day": t, **({"stage": c["parameter"]} if single else {})} for t in sorted(times) for c in pattern] + fixed
