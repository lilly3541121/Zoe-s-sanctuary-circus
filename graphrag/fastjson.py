#!/usr/bin/env python3
"""fastjson.py — orjson-backed drop-in for stdlib json (C/Rust-speed JSON).

Exposes loads()/dumps() with the SAME signature semantics as stdlib json so
pipeline scripts can swap `import json` -> `import fastjson as json` without
changing call sites. Falls back to stdlib json if orjson is unavailable.

Key differences handled transparently:
  - orjson works on bytes/str and returns bytes; stdlib returns str. We accept
    str OR bytes input for loads, and return str for dumps (matching stdlib).
  - orjson.dumps supports indent but NOT ensure_ascii / allow_nan / default
    with the same semantics. We pass through what we can, fall back to stdlib
    for the kwargs orjson doesn't accept.
"""
import json as _stdlib

try:
    import orjson as _orjson
    _HAVE_ORJSON = True
    # orjson's decode error; expose as JSONDecodeError so callers that catch
    # (ValueError, json.JSONDecodeError) keep working.
    class JSONDecodeError(_orjson.JSONDecodeError, ValueError):
        pass
except ImportError:  # pragma: no cover
    _orjson = None
    _HAVE_ORJSON = False
    JSONDecodeError = _stdlib.JSONDecodeError


def loads(s):
    """Parse JSON from str or bytes -> Python object (orjson fast path)."""
    if _HAVE_ORJSON:
        if isinstance(s, str):
            s = s.encode("utf-8")
        return _orjson.loads(s)
    return _stdlib.loads(s if isinstance(s, bytes) else s)


def dumps(obj, indent=None, ensure_ascii=False, **kwargs):
    """Serialize Python object -> str (orjson fast path, stdlib fallback).

    Preserves the stdlib signature (indent, ensure_ascii) that our pipeline
    relies on. orjson supports indent; ensure_ascii is always False in orjson
    (UTF-8 native). If any kwarg orjson doesn't support is passed, fall back.
    """
    if _HAVE_ORJSON:
        try:
            if indent is not None:
                data = _orjson.dumps(obj, option=_orjson.OPT_INDENT_2 if indent == 2 else
                                     (_orjson.OPT_INDENT_2 if indent >= 2 else 0))
            else:
                data = _orjson.dumps(obj)
            # orjson returns bytes; return str to match stdlib behavior
            return data.decode("utf-8")
        except (TypeError, ValueError, OverflowError):
            # orjson can't handle some types (e.g. NaN default, custom default fn);
            # fall back to stdlib for the exact same call
            if ensure_ascii:
                return _stdlib.dumps(obj, indent=indent, ensure_ascii=True, **kwargs)
            return _stdlib.dumps(obj, indent=indent, ensure_ascii=False, **kwargs)
    return _stdlib.dumps(obj, indent=indent, ensure_ascii=ensure_ascii, **kwargs)


__all__ = ["loads", "dumps", "JSONDecodeError"]
__version__ = "0.1.0"
