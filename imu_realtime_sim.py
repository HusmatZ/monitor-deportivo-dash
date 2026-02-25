"""imu_realtime_sim.py

Simulador de IMU en tiempo real para la vista de Monitorización.

✅ Compatibilidad: mantiene las mismas claves que el código original:
    t, pitch, roll, yaw, sway, score, bad, bpm, events_t, events_label

✅ Nuevas funcionalidades (2 IMUs + RAW 50 Hz):
- Genera 2 segmentos: Torácico (T_*) y Lumbar (L_*).
- Cada IMU tiene su propio reloj (ts_ms propio) para emular la necesidad
  de sincronización en software.
- Se entrega un timestamp unificado (ts_ms) para guardar en DB.
- Añade por muestra: thor_zone, lum_zone (green/yellow/red), comp_index (0..100).
- Añade utilidades para grabación:
    get_samples_since(since_ts_ms) -> lista de dicts (RAW) para insertar por lote.

Uso típico (en Dash):
    from imu_realtime_sim import SIM
    SIM.tick()
    win = SIM.get_window(seconds=20)

    # grabación RAW (evitar duplicados)
    new_rows = SIM.get_samples_since(last_ts_ms)
"""

from __future__ import annotations

import math
import random
import time
from collections import deque
from dataclasses import dataclass
from typing import Deque, Dict, List, Optional


def _clamp(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else hi if x > hi else x


def _zone_from_angles(*, pitch: float, roll: float, thr_g: tuple[float, float], thr_y: tuple[float, float]) -> str:
    """Devuelve green/yellow/red según umbrales.

    thr_g: (pitch_g, roll_g) -> por debajo de esto es "green".
    thr_y: (pitch_y, roll_y) -> por debajo de esto es "yellow".
    Por encima de thr_y -> "red".
    """
    ap = abs(float(pitch))
    ar = abs(float(roll))
    if ap <= thr_g[0] and ar <= thr_g[1]:
        return "green"
    if ap <= thr_y[0] and ar <= thr_y[1]:
        return "yellow"
    return "red"


@dataclass
class IMUSample:
    # --- legacy ---
    t: float
    pitch: float
    roll: float
    yaw: float
    sway: float
    score: float
    bad: bool
    bpm: float
    events: List[str]

    # --- new (2-IMU) ---
    ts_ms: int = 0
    T_pitch: float = 0.0
    T_roll: float = 0.0
    T_yaw: float = 0.0
    L_pitch: float = 0.0
    L_roll: float = 0.0
    L_yaw: float = 0.0
    thor_zone: str = "green"
    lum_zone: str = "green"
    comp_index: float = 0.0
    T_imu_ts_ms: int = 0
    L_imu_ts_ms: int = 0


class IMURealtimeSim:
    """Simulador de 2 IMUs (torácico + lumbar) con compatibilidad legacy."""

    def __init__(
        self,
        *,
        rate_hz: float = 50.0,
        max_seconds: float = 120.0,
        seed: Optional[int] = None,
        pitch_thr_deg: float = 18.0,
        roll_thr_deg: float = 14.0,
    ):
        self.rate_hz = float(rate_hz)
        self.dt_nom = 1.0 / max(self.rate_hz, 1e-6)
        self.max_seconds = float(max_seconds)

        # parámetros legacy (se mantienen)
        self.pitch_thr = float(pitch_thr_deg)
        self.roll_thr = float(roll_thr_deg)

        if seed is not None:
            random.seed(seed)

        # contexto (lo setea la UI)
        self.mode = "desk"   # desk | train
        self.sport = "gym"   # gym | crossfit

        self._reset_state()

    def _reset_state(self) -> None:
        self._t0 = time.monotonic()
        self._last_t = self._t0

        # fases base (señales suaves)
        self._phiT = random.random() * 2 * math.pi
        self._phiL = random.random() * 2 * math.pi
        self._phi2 = random.random() * 2 * math.pi

        # drift lento de yaw
        self._yaw_drift_T = random.uniform(-0.25, 0.25)
        self._yaw_drift_L = random.uniform(-0.25, 0.25)

        # bias
        self._T_pitch_bias = random.uniform(-1.5, 1.5)
        self._T_roll_bias = random.uniform(-1.5, 1.5)
        self._L_pitch_bias = random.uniform(-1.5, 1.5)
        self._L_roll_bias = random.uniform(-1.5, 1.5)

        # segmentos de mala postura
        self._badT_until: float = 0.0
        self._badL_until: float = 0.0

        # BPM demo (se deja, pero ya no es la métrica principal)
        self._bpm_base = random.uniform(62, 78)
        self._bpm_phi = random.random() * 2 * math.pi

        # relojes independientes por IMU (offset + drift)
        self._T_offset_ms = random.uniform(-150, 150)
        self._L_offset_ms = random.uniform(-150, 150)
        self._T_drift = 1.0 + random.uniform(-80e-6, 80e-6)  # ±80 ppm
        self._L_drift = 1.0 + random.uniform(-80e-6, 80e-6)

        # comp window
        self._comp_window: Deque[float] = deque()
        self._comp_window_max = int(self.rate_hz * 10.0)  # 10 s

        # últimos estados para eventos
        self._last_thor_zone: Optional[str] = None
        self._last_lum_zone: Optional[str] = None

        # buffer
        self._buf: Deque[IMUSample] = deque()

    def reset(self) -> None:
        """Reinicia simulación y borra buffer."""
        self._reset_state()

    def set_context(self, *, mode: str, sport: str) -> None:
        self.mode = (mode or "desk").strip().lower()
        self.sport = (sport or "gym").strip().lower()

    def _imu_clock_ts_ms(self, *, t_rel_s: float, imu: str) -> int:
        t_ms = float(t_rel_s) * 1000.0
        if imu == "T":
            return int(t_ms * self._T_drift + self._T_offset_ms)
        return int(t_ms * self._L_drift + self._L_offset_ms)

    def _thresholds(self):
        # Umbrales simples (MVP)
        if self.mode == "train":
            # entreno: un poco más permisivo
            thrT_g = (12.0, 10.0)
            thrT_y = (20.0, 16.0)
            thrL_g = (14.0, 12.0)
            thrL_y = (24.0, 18.0)
        else:
            # desk / vida diaria
            thrT_g = (10.0, 8.0)
            thrT_y = (18.0, 14.0)
            thrL_g = (12.0, 10.0)
            thrL_y = (20.0, 16.0)

        # crossfit: un poco más permisivo aún
        if self.sport == "crossfit":
            thrT_g = (thrT_g[0] + 1.5, thrT_g[1] + 1.0)
            thrT_y = (thrT_y[0] + 2.0, thrT_y[1] + 1.5)
            thrL_g = (thrL_g[0] + 1.5, thrL_g[1] + 1.0)
            thrL_y = (thrL_y[0] + 2.0, thrL_y[1] + 1.5)

        return thrT_g, thrT_y, thrL_g, thrL_y

    def _simulate_sample(self, t_rel: float) -> IMUSample:
        # Frecuencias típicas: movimientos posturales lentos
        fT = 0.10
        fL = 0.085

        # Torácico
        T_pitch = 8.0 * math.sin(2 * math.pi * fT * t_rel + self._phiT) + 2.5 * math.sin(2 * math.pi * 0.03 * t_rel + self._phi2) + self._T_pitch_bias
        T_roll = 5.5 * math.sin(2 * math.pi * 0.07 * t_rel + self._phi2) + self._T_roll_bias
        T_yaw = (self._yaw_drift_T * t_rel) + 6.0 * math.sin(2 * math.pi * 0.05 * t_rel + self._phiT)

        # Lumbar (pitch positivo = extensión lumbar)
        L_pitch = 10.0 * math.sin(2 * math.pi * fL * t_rel + self._phiL) + 3.0 * math.sin(2 * math.pi * 0.028 * t_rel + self._phi2) + self._L_pitch_bias
        L_roll = 6.0 * math.sin(2 * math.pi * 0.075 * t_rel + self._phiL) + self._L_roll_bias
        L_yaw = (self._yaw_drift_L * t_rel) + 5.0 * math.sin(2 * math.pi * 0.045 * t_rel + self._phi2)

        # Segmentos de mala postura
        if t_rel > self._badT_until and random.random() < 0.003:
            self._badT_until = t_rel + random.uniform(6.0, 18.0)
        if t_rel > self._badL_until and random.random() < 0.003:
            self._badL_until = t_rel + random.uniform(6.0, 18.0)

        if t_rel < self._badT_until:
            # slouch (flexión torácica -> pitch negativo)
            T_pitch -= random.uniform(10.0, 18.0)
        if t_rel < self._badL_until:
            # hiperextensión lumbar (pitch positivo)
            L_pitch += random.uniform(10.0, 20.0)

        # Ruido
        T_pitch += random.gauss(0.0, 0.35)
        T_roll += random.gauss(0.0, 0.35)
        T_yaw += random.gauss(0.0, 0.25)

        L_pitch += random.gauss(0.0, 0.35)
        L_roll += random.gauss(0.0, 0.35)
        L_yaw += random.gauss(0.0, 0.25)

        # Artefactos
        events: List[str] = []
        if random.random() < 0.006:
            bump = random.choice([-1, 1]) * random.uniform(6, 12)
            T_pitch += bump * 0.6
            L_pitch += bump
            T_roll += random.choice([-1, 1]) * random.uniform(3, 6)
            L_roll += random.choice([-1, 1]) * random.uniform(5, 10)
            events.append("artefacto")

        # Zonas
        thrT_g, thrT_y, thrL_g, thrL_y = self._thresholds()
        thor_zone = _zone_from_angles(pitch=T_pitch, roll=T_roll, thr_g=thrT_g, thr_y=thrT_y)
        lum_zone = _zone_from_angles(pitch=L_pitch, roll=L_roll, thr_g=thrL_g, thr_y=thrL_y)

        # Compensación (rolling 10s): |L_pitch - T_pitch| normalizado
        comp_raw = abs(float(L_pitch) - float(T_pitch))
        self._comp_window.append(comp_raw)
        while len(self._comp_window) > self._comp_window_max:
            self._comp_window.popleft()
        comp_mean = sum(self._comp_window) / max(len(self._comp_window), 1)
        comp_index = _clamp((comp_mean / 30.0) * 100.0, 0.0, 100.0)

        # Events por cambios de zona
        if self._last_thor_zone != thor_zone:
            events.append(f"thor_{thor_zone}")
        if self._last_lum_zone != lum_zone:
            events.append(f"lum_{lum_zone}")
        self._last_thor_zone = thor_zone
        self._last_lum_zone = lum_zone

        # Legacy sway (demo)
        sway = math.sqrt((L_pitch / 20.0) ** 2 + (L_roll / 20.0) ** 2) + abs(random.gauss(0.0, 0.03))

        # Score (0..100): combina zonas + sway + comp
        score = 100.0
        if thor_zone == "yellow":
            score -= 12.0
        elif thor_zone == "red":
            score -= 28.0
        if lum_zone == "yellow":
            score -= 12.0
        elif lum_zone == "red":
            score -= 28.0
        score -= _clamp(comp_index * 0.15, 0.0, 18.0)
        score -= _clamp(sway * 12.0, 0.0, 12.0)
        score = _clamp(score, 0.0, 100.0)

        # bad: rojo en cualquier segmento
        bad = (thor_zone == "red") or (lum_zone == "red")

        # BPM demo
        bpm = self._bpm_base + 4.0 * math.sin(2 * math.pi * 0.012 * t_rel + self._bpm_phi) + random.gauss(0.0, 0.8)
        bpm = _clamp(bpm, 45.0, 180.0)

        # timestamps
        ts_ms = int(t_rel * 1000.0)
        T_imu_ts = self._imu_clock_ts_ms(t_rel_s=t_rel, imu="T")
        L_imu_ts = self._imu_clock_ts_ms(t_rel_s=t_rel, imu="L")

        return IMUSample(
            t=t_rel,
            pitch=L_pitch,
            roll=L_roll,
            yaw=L_yaw,
            sway=sway,
            score=score,
            bad=bool(bad),
            bpm=bpm,
            events=events,
            ts_ms=ts_ms,
            T_pitch=T_pitch,
            T_roll=T_roll,
            T_yaw=T_yaw,
            L_pitch=L_pitch,
            L_roll=L_roll,
            L_yaw=L_yaw,
            thor_zone=thor_zone,
            lum_zone=lum_zone,
            comp_index=comp_index,
            T_imu_ts_ms=T_imu_ts,
            L_imu_ts_ms=L_imu_ts,
        )

    def tick(self) -> None:
        """Avanza el simulador hasta 'ahora' y añade muestras al buffer."""
        now = time.monotonic()
        while (now - self._last_t) >= (self.dt_nom * 0.98):
            self._last_t += self.dt_nom
            t_rel = self._last_t - self._t0
            s = self._simulate_sample(t_rel)
            self._buf.append(s)

        cutoff = (now - self._t0) - self.max_seconds
        while self._buf and self._buf[0].t < cutoff:
            self._buf.popleft()

    def get_window(self, *, seconds: float = 20.0) -> Dict[str, List]:
        """Devuelve datos del último 'seconds' en arrays."""
        self.tick()
        seconds = float(seconds)

        keys = (
            "t",
            "ts_ms",
            "pitch",
            "roll",
            "yaw",
            "sway",
            "score",
            "bad",
            "bpm",
            "events_t",
            "events_label",
            # nuevos
            "T_pitch",
            "T_roll",
            "T_yaw",
            "L_pitch",
            "L_roll",
            "L_yaw",
            "thor_zone",
            "lum_zone",
            "comp_index",
        )

        if not self._buf:
            return {k: [] for k in keys}

        t_end = self._buf[-1].t
        t_start = max(0.0, t_end - seconds)
        win = [s for s in self._buf if s.t >= t_start]
        if not win:
            return {k: [] for k in keys}

        t = [s.t for s in win]
        ts_ms = [int(s.ts_ms) for s in win]

        pitch = [s.pitch for s in win]
        roll = [s.roll for s in win]
        yaw = [s.yaw for s in win]
        sway = [s.sway for s in win]
        score = [s.score for s in win]
        bad = [bool(s.bad) for s in win]
        bpm = [s.bpm for s in win]

        T_pitch = [s.T_pitch for s in win]
        T_roll = [s.T_roll for s in win]
        T_yaw = [s.T_yaw for s in win]
        L_pitch = [s.L_pitch for s in win]
        L_roll = [s.L_roll for s in win]
        L_yaw = [s.L_yaw for s in win]
        thor_zone = [s.thor_zone for s in win]
        lum_zone = [s.lum_zone for s in win]
        comp_index = [s.comp_index for s in win]

        events_t: List[float] = []
        events_label: List[str] = []
        for s in win:
            for ev in (s.events or []):
                events_t.append(s.t)
                events_label.append(ev)

        return {
            "t": t,
            "ts_ms": ts_ms,
            "pitch": pitch,
            "roll": roll,
            "yaw": yaw,
            "sway": sway,
            "score": score,
            "bad": bad,
            "bpm": bpm,
            "events_t": events_t,
            "events_label": events_label,
            "T_pitch": T_pitch,
            "T_roll": T_roll,
            "T_yaw": T_yaw,
            "L_pitch": L_pitch,
            "L_roll": L_roll,
            "L_yaw": L_yaw,
            "thor_zone": thor_zone,
            "lum_zone": lum_zone,
            "comp_index": comp_index,
        }

    def get_samples_since(self, since_ts_ms: Optional[int], *, max_samples: int = 5000) -> List[Dict]:
        """Devuelve muestras RAW nuevas (ts_ms > since_ts_ms).

        Cada item es un dict listo para insertar por lote en DB.
        """
        self.tick()
        if not self._buf:
            return []

        since = int(since_ts_ms or 0)
        out: List[Dict] = []
        for s in self._buf:
            if int(s.ts_ms) <= since:
                continue
            out.append(
                {
                    "ts_ms": int(s.ts_ms),
                    "T_pitch": float(s.T_pitch),
                    "T_roll": float(s.T_roll),
                    "T_yaw": float(s.T_yaw),
                    "L_pitch": float(s.L_pitch),
                    "L_roll": float(s.L_roll),
                    "L_yaw": float(s.L_yaw),
                    "thor_zone": str(s.thor_zone),
                    "lum_zone": str(s.lum_zone),
                    "comp_index": float(s.comp_index),
                    "T_imu_ts_ms": int(s.T_imu_ts_ms),
                    "L_imu_ts_ms": int(s.L_imu_ts_ms),
                }
            )
            if len(out) >= int(max_samples):
                break
        return out

    def latest(self) -> Optional[IMUSample]:
        self.tick()
        return self._buf[-1] if self._buf else None


# Singleton listo para importar
SIM = IMURealtimeSim()
