"""session_recorder.py

Grabador de sesión para datos de sensores (RAW 50 Hz) con inserciones por lote.

Objetivos del Sprint 1:
- start_session() -> crea sensor_session en DB
- append_samples_batch() -> buffer en memoria + flush por lote (evita 50 inserts/s)
- stop_session_and_compute_summary() -> calcula métricas + risk index al cerrar (tu decisión fija)

Este módulo NO depende de Dash; se usa desde callbacks (Sprint 2) o desde tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, date
from typing import Dict, List, Optional, Tuple

import db
from posture_engine import PostureEngine, SegmentAngles, compute_risk_index


def _now_ms() -> int:
    # host time ms (unificado)
    return int(datetime.now().timestamp() * 1000)


@dataclass
class RecorderConfig:
    user_id: int
    kind: str              # monitor | routine | baseline
    mode: str              # desk | train
    sport: str             # gym | crossfit
    sample_rate_hz: float = 50.0
    flush_every_s: float = 2.0


class SessionRecorder:
    """Graba muestras RAW (ya fusionadas/alineadas) y acumula métricas para el summary."""

    def __init__(self, cfg: RecorderConfig):
        self.cfg = cfg
        self.session_id: Optional[int] = None
        self._engine = PostureEngine(sample_rate_hz=cfg.sample_rate_hz)

        # buffer DB: lista de tuplas para executemany
        self._raw_rows: List[Tuple] = []
        self._last_flush_ms: Optional[int] = None

        # contadores para summary incremental (no re-leemos DB)
        self._n = 0
        self._thor_red = 0
        self._lum_red = 0
        self._alerts = 0
        self._comp_sum = 0.0
        self._comp_peak = 0.0
        self._last_thor_zone: Optional[str] = None
        self._last_lum_zone: Optional[str] = None

        # para agregado 1 Hz
        self._agg_rows: List[Tuple] = []
        self._last_agg_s: Optional[int] = None

    # -------------------------
    # Ciclo de vida
    # -------------------------
    def start_session(self) -> int:
        if self.session_id is not None:
            return int(self.session_id)

        sid = db.start_sensor_session(
            user_id=int(self.cfg.user_id),
            kind=self.cfg.kind,
            mode=self.cfg.mode,
            sport=self.cfg.sport,
            started_at=datetime.now(),
        )
        self.session_id = int(sid)
        self._last_flush_ms = _now_ms()
        return int(sid)

    def append_samples_batch(self, samples: List[Dict]) -> None:
        """Recibe una lista de samples (dict) y los prepara para DB.

        Cada sample debe traer:
        - ts_ms (host time)
        - T_pitch,T_roll,T_yaw
        - L_pitch,L_roll,L_yaw
        - opcional: T_imu_ts_ms, L_imu_ts_ms

        Si no trae zones/comp_index, se calculan aquí con PostureEngine.
        """
        if not samples:
            return
        if self.session_id is None:
            self.start_session()

        for s in samples:
            ts_ms = int(s.get("ts_ms") or 0)
            if ts_ms <= 0:
                # si no viene, lo asignamos
                ts_ms = _now_ms()

            # angles
            thor = SegmentAngles(
                pitch=float(s.get("T_pitch", 0.0)),
                roll=float(s.get("T_roll", 0.0)),
                yaw=float(s.get("T_yaw", 0.0)),
            )
            lum = SegmentAngles(
                pitch=float(s.get("L_pitch", 0.0)),
                roll=float(s.get("L_roll", 0.0)),
                yaw=float(s.get("L_yaw", 0.0)),
            )

            # zones + comp
            if ("thor_zone" in s) and ("lum_zone" in s) and ("comp_index" in s):
                thor_zone = str(s["thor_zone"])
                lum_zone = str(s["lum_zone"])
                comp_index = float(s["comp_index"])
            else:
                ann = self._engine.annotate(
                    ts_ms=ts_ms,
                    thor=thor,
                    lum=lum,
                    mode=self.cfg.mode,
                    sport=self.cfg.sport,
                    profile=None,
                )
                thor_zone = ann.thor_zone
                lum_zone = ann.lum_zone
                comp_index = ann.comp_index

            t_imu_ts = s.get("T_imu_ts_ms")
            l_imu_ts = s.get("L_imu_ts_ms")
            t_imu_ts = int(t_imu_ts) if t_imu_ts is not None else None
            l_imu_ts = int(l_imu_ts) if l_imu_ts is not None else None

            # ---- summary incremental ----
            self._n += 1
            if thor_zone == "red":
                self._thor_red += 1
            if lum_zone == "red":
                self._lum_red += 1

            if self._last_thor_zone != "red" and thor_zone == "red":
                self._alerts += 1
            if self._last_lum_zone != "red" and lum_zone == "red":
                self._alerts += 1
            self._last_thor_zone = thor_zone
            self._last_lum_zone = lum_zone

            self._comp_sum += comp_index
            self._comp_peak = max(self._comp_peak, comp_index)

            # ---- buffer RAW ----
            self._raw_rows.append(
                (
                    int(self.session_id),
                    ts_ms,
                    thor.pitch,
                    thor.roll,
                    thor.yaw,
                    lum.pitch,
                    lum.roll,
                    lum.yaw,
                    thor_zone,
                    lum_zone,
                    comp_index,
                    t_imu_ts,
                    l_imu_ts,
                )
            )

            # ---- agregado 1 Hz (sample & hold) ----
            ts_s = int(ts_ms // 1000)
            if self._last_agg_s is None or ts_s > self._last_agg_s:
                self._last_agg_s = ts_s
                self._agg_rows.append(
                    (
                        int(self.session_id),
                        ts_s,
                        thor.pitch,
                        lum.pitch,
                        thor_zone,
                        lum_zone,
                        comp_index,
                    )
                )

        self._maybe_flush()

    def _maybe_flush(self) -> None:
        if self.session_id is None:
            return
        now_ms = _now_ms()
        if self._last_flush_ms is None:
            self._last_flush_ms = now_ms

        if (now_ms - self._last_flush_ms) < int(self.cfg.flush_every_s * 1000):
            return

        self.flush()
        self._last_flush_ms = now_ms

    def flush(self) -> None:
        if self.session_id is None:
            return
        if self._raw_rows:
            db.insert_sensor_samples_raw_batch(session_id=int(self.session_id), rows=self._raw_rows)
            self._raw_rows.clear()
        if self._agg_rows:
            db.insert_sensor_samples_agg_batch(session_id=int(self.session_id), rows=self._agg_rows)
            self._agg_rows.clear()

    def stop_session_and_compute_summary(self) -> Dict:
        if self.session_id is None:
            raise RuntimeError("No hay sesión activa")

        self.flush()
        db.end_sensor_session(session_id=int(self.session_id), ended_at=datetime.now())

        # métricas
        dur_s = float(self._n) / max(float(self.cfg.sample_rate_hz), 1e-6)
        thor_red_s = float(self._thor_red) / max(float(self.cfg.sample_rate_hz), 1e-6)
        lum_red_s = float(self._lum_red) / max(float(self.cfg.sample_rate_hz), 1e-6)
        comp_avg = float(self._comp_sum) / max(float(self._n), 1.0)
        comp_peak = float(self._comp_peak)
        alerts = int(self._alerts)
        risk = compute_risk_index(duration_s=dur_s, thor_red_s=thor_red_s, lum_red_s=lum_red_s, comp_avg=comp_avg)

        db.upsert_session_summary(
            session_id=int(self.session_id),
            duration_s=dur_s,
            thor_red_s=thor_red_s,
            lum_red_s=lum_red_s,
            alerts_count=alerts,
            comp_avg=comp_avg,
            comp_peak=comp_peak,
            risk_index=risk,
        )

        # Recalcular daily_summary (consistente)
        d = date.today()
        daily = db.recompute_daily_summary(user_id=int(self.cfg.user_id), day=d)

        summary = {
            "session_id": int(self.session_id),
            "duration_s": dur_s,
            "thor_red_s": thor_red_s,
            "lum_red_s": lum_red_s,
            "alerts_count": alerts,
            "comp_avg": comp_avg,
            "comp_peak": comp_peak,
            "risk_index": risk,
            "daily": daily,
        }

        # reset estado interno (permite reusar el recorder)
        self.session_id = None
        self._engine.reset()
        self._raw_rows.clear()
        self._agg_rows.clear()
        self._last_flush_ms = None
        self._n = 0
        self._thor_red = 0
        self._lum_red = 0
        self._alerts = 0
        self._comp_sum = 0.0
        self._comp_peak = 0.0
        self._last_thor_zone = None
        self._last_lum_zone = None
        self._last_agg_s = None

        return summary
