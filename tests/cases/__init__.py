"""Aggregates per-module golden case tables."""
import importlib
import pkgutil


def load_all_cases():
    cases = []
    for info in pkgutil.iter_modules(__path__):
        if info.name.startswith("_"):
            continue
        mod = importlib.import_module(f"{__name__}.{info.name}")
        for case in getattr(mod, "CASES", []):
            case = dict(case)
            case["_module"] = info.name
            cases.append(case)
    return cases
