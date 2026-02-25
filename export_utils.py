# export_utils.py
"""
Utilidades de exportación para AxisFit (MVP).

Objetivo:
- Reutilizar exportación CSV/JSON en todas las vistas (Monitor, Progreso, Cuestionario, Rutinas).
- Devolver bytes/listos para dcc.Download sin duplicar lógica.

Notas:
- Dash suele usar: dcc.send_bytes(...) o dcc.send_string(...)
- Este módulo entrega (bytes, mimetype, filename) para que el callback decida cómo enviarlo.
"""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


# -------------------------
# Helpers de nombres
# -------------------------
def make_filename(
    prefix: str,
    *,
    ext: str,
    dt: Optional[datetime] = None,
    suffix: Optional[str] = None,
) -> str:
    """
    Genera un nombre consistente:
      <prefix>_<YYYYMMDD_HHMMSS>[_<suffix>].<ext>

    Ej:
      monitor_history_20260224_101530.csv
      questionnaire_20260224_101530_user00000001.json
    """
    dt = dt or datetime.now()
    stamp = dt.strftime("%Y%m%d_%H%M%S")
    prefix = (prefix or "export").strip().replace(" ", "_")
    ext = (ext or "").lstrip(".").strip()

    parts = [prefix, stamp]
    if suffix:
        parts.append(str(suffix).strip().replace(" ", "_"))

    base = "_".join([p for p in parts if p])
    return f"{base}.{ext}" if ext else base


# -------------------------
# CSV
# -------------------------
def _normalize_rows(rows: Any) -> List[Dict[str, Any]]:
    """
    Acepta:
    - list[dict]
    - dict (-> [dict])
    - None / [] (-> [])
    """
    if rows is None:
        return []
    if isinstance(rows, dict):
        return [rows]
    if isinstance(rows, (list, tuple)):
        out = []
        for r in rows:
            if isinstance(r, dict):
                out.append(r)
            else:
                # si viene algo raro, lo guardamos como string
                out.append({"value": r})
        return out
    return [{"value": rows}]


def _infer_fieldnames(rows: List[Dict[str, Any]]) -> List[str]:
    """Une todas las claves preservando orden de aparición."""
    seen = set()
    fields: List[str] = []
    for r in rows:
        for k in r.keys():
            if k not in seen:
                seen.add(k)
                fields.append(str(k))
    return fields


def rows_to_csv_bytes(
    rows: Any,
    *,
    fieldnames: Optional[Sequence[str]] = None,
    delimiter: str = ",",
    include_bom_utf8: bool = True,
) -> bytes:
    """
    Convierte filas (list[dict]) a CSV (bytes).
    - include_bom_utf8=True mejora compatibilidad con Excel (acentos).
    """
    norm = _normalize_rows(rows)

    if fieldnames is None:
        fieldnames = _infer_fieldnames(norm) if norm else []

    # Escribimos en texto y luego a bytes (UTF-8)
    buf = io.StringIO()
    writer = csv.DictWriter(
        buf,
        fieldnames=list(fieldnames),
        delimiter=delimiter,
        extrasaction="ignore",
    )
    writer.writeheader()
    for r in norm:
        # convierte valores complejos a JSON para no romper CSV
        row_out = {}
        for k in fieldnames:
            v = r.get(k)
            if isinstance(v, (dict, list, tuple)):
                row_out[k] = json.dumps(v, ensure_ascii=False)
            else:
                row_out[k] = "" if v is None else v
        writer.writerow(row_out)

    text = buf.getvalue()
    if include_bom_utf8:
        return ("\ufeff" + text).encode("utf-8")
    return text.encode("utf-8")


def export_csv_payload(
    rows: Any,
    *,
    filename: str,
    fieldnames: Optional[Sequence[str]] = None,
    delimiter: str = ",",
    include_bom_utf8: bool = True,
) -> Tuple[bytes, str, str]:
    """
    Devuelve (bytes, mimetype, filename) para un CSV.
    """
    data = rows_to_csv_bytes(
        rows,
        fieldnames=fieldnames,
        delimiter=delimiter,
        include_bom_utf8=include_bom_utf8,
    )
    return data, "text/csv", filename


# -------------------------
# JSON
# -------------------------
def to_json_bytes(
    payload: Any,
    *,
    indent: int = 2,
    ensure_ascii: bool = False,
) -> bytes:
    """
    Convierte payload a JSON bytes (UTF-8).
    """
    text = json.dumps(payload, indent=indent, ensure_ascii=ensure_ascii, default=str)
    return text.encode("utf-8")


def export_json_payload(
    payload: Any,
    *,
    filename: str,
    indent: int = 2,
    ensure_ascii: bool = False,
) -> Tuple[bytes, str, str]:
    """
    Devuelve (bytes, mimetype, filename) para JSON.
    """
    data = to_json_bytes(payload, indent=indent, ensure_ascii=ensure_ascii)
    return data, "application/json", filename


# -------------------------
# (Opcional) utilidades de alto nivel
# -------------------------
def wrap_export_result(
    *,
    data: bytes,
    filename: str,
    mimetype: str,
) -> Dict[str, Any]:
    """
    Para quien prefiera devolver un dict estándar desde callbacks.
    Nota: Dash dcc.Download normalmente usa dcc.send_bytes / dcc.send_string.
    Aquí dejamos un formato neutro por si lo quieres unificar luego.
    """
    return {"data": data, "filename": filename, "mimetype": mimetype}