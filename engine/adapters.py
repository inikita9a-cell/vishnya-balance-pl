"""Адаптеры входных форматов: любой файл ответа -> python dict.

JSON читается orjson. XML — xmltodict с тремя поправками, чтобы XML и JSON
одной заявки давали одинаковые различия:
  1) массивы из конфигурации принудительно делаются списками
     (иначе массив из 1 элемента в XML превращается в dict);
  2) обёртки элементов (<item>) разворачиваются;
  3) строки приводятся к типам: "710"->710, "0.5"->0.5, "false"->False, пусто/nil->None.
Новый формат = новая функция в READERS, движок не меняется.
"""
import re
from pathlib import Path
import orjson

_INT = re.compile(r"^-?\d+$")
_FLOAT = re.compile(r"^-?\d+\.\d+(?:[eE][-+]?\d+)?$|^-?\d+[eE][-+]?\d+$")


def read_json(path: Path, cfg: dict) -> dict:
    return orjson.loads(Path(path).read_bytes())


def _coerce(v):
    if isinstance(v, dict):
        if v.get("xsi:nil") in ("true", "1") or v.get("nil") in ("true", "1"):
            return None
        return {k: _coerce(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_coerce(x) for x in v]
    if v is None:
        return None
    if isinstance(v, str):
        s = v.strip()
        if s == "":
            return None
        if s in ("true", "false"):
            return s == "true"
        if s.lower() == "null":
            return None
        if _INT.match(s) and not (len(s) > 1 and s.lstrip("-").startswith("0")):
            return int(s)          # "007" оставляем строкой — это код, а не число
        if _FLOAT.match(s):
            return float(s)
    return v


def _unwrap_items(v, item_tags):
    if isinstance(v, dict):
        if len(v) == 1:
            (k, inner), = v.items()
            if k in item_tags:
                inner = inner if isinstance(inner, list) else [inner]
                return [_unwrap_items(x, item_tags) for x in inner]
        return {k: _unwrap_items(x, item_tags) for k, x in v.items()}
    if isinstance(v, list):
        return [_unwrap_items(x, item_tags) for x in v]
    return v


def read_xml(path: Path, cfg: dict) -> dict:
    import xmltodict
    xcfg = cfg.get("xml", {})
    from .paths import ArrayRules
    rules = ArrayRules(cfg.get("flatten", {}).get("arrays", {}))
    strip_root = xcfg.get("strip_root", True)
    doc = xmltodict.parse(Path(path).read_bytes(), attr_prefix="", cdata_key="value")
    if strip_root and isinstance(doc, dict) and len(doc) == 1:
        doc = next(iter(doc.values())) or {}
    doc = _unwrap_items(doc, set(xcfg.get("item_tags", ["item"])))
    def normalize_arrays(value, path="", element=False):
        if not element and rules.lookup(path) and not isinstance(value, list):
            value = [] if value is None else [value]
        if isinstance(value, list):
            return [normalize_arrays(x, path, True) for x in value]
        if isinstance(value, dict):
            return {k: normalize_arrays(v, f"{path}.{k}" if path else k) for k, v in value.items()}
        return value
    doc = normalize_arrays(doc)
    if xcfg.get("coerce_types", True):
        doc = _coerce(doc)
    return doc


READERS = {".json": read_json, ".xml": read_xml}


def read_any(path, cfg: dict) -> dict:
    """Читает файл ответа по расширению. Ошибка -> исключение (его ловит load и пишет в quality)."""
    p = Path(path)
    reader = READERS.get(p.suffix.lower())
    if reader is None:
        raise ValueError(f"Неизвестный формат: {p.suffix}")
    doc = reader(p, cfg)
    if not isinstance(doc, dict):
        raise ValueError(f"Корень ответа не объект: {type(doc).__name__}")
    return doc


def app_id_from_path(path) -> str:
    return Path(path).stem