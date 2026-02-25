"""posture_engine.py

Motor de postura (MVP) para AxisFit.

Responsabilidades:
- Clasificar postura por zonas (verde/amarillo/rojo) para 2 segmentos: torácico y lumbar.
- Calcular un índice de compensación (0..100) sobre ventana móvil (~10 s).
- Calcular resumen de sesión (tiempo rojo, compensación, risk index) al cerrar sesión.

Notas de convención:
- Pitch positivo = extensión lumbar (hiperextensión). Para torácico usamos la misma convención de signo.
- En este Sprint 1 usamos thresholds *por defecto*. En Sprint 3 se reemplazan/ajustan con el perfil del usuario (questionnaire).

Este módulo es deliberadamente simple para que sea estable y escalable en Dash + SQLite.
"""

from __future__ import annotations

from dataclasses import dataclass
from collections import deque
from typing import Deque, Dict, Optional, Tuple


Zone = str  # "green" | "yellow" | "red"


def _clamp(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else hi if x > hi else x


def _zone_from_abs(pitch: float, roll: float, *, pitch_g: float, pitch_y: float, roll_g: float, roll_y: float) -> Zone:
    """Zonificación simple basada en límites simétricos alrededor de 0.

    - green si abs(pitch) <= pitch_g y abs(roll) <= roll_g
    - yellow si abs(pitch) <= pitch_y y abs(roll) <= roll_y
    - red en otro caso
    """
    ap = abs(float(pitch))
    ar = abs(float(roll))
    if ap <= pitch_g and ar <= roll_g:
        return "green"
    if ap <= pitch_y and ar <= roll_y:
        return "yellow"
    return "red"


DEFAULT_THRESHOLDS: Dict[str, Dict[str, Dict[str, float]]] = {
    # Valores conservadores para vida diaria.
    "desk": {
        "thor": {"pitch_g": 8.0, "pitch_y": 15.0, "roll_g": 7.0, "roll_y": 12.0},
        "lum":  {"pitch_g": 10.0, "pitch_y": 18.0, "roll_g": 7.0, "roll_y": 12.0},
    },
    # Entreno: permitimos rangos algo más amplios (todavía genéricos).
    "train": {
        "thor": {"pitch_g": 12.0, "pitch_y": 20.0, "roll_g": 10.0, "roll_y": 16.0},
        "lum":  {"pitch_g": 14.0, "pitch_y": 24.0, "roll_g": 10.0, "roll_y": 16.0},
    },
}


@dataclass
class SegmentAngles:
    pitch: float
    roll: float
    yaw: float


@dataclass
class AnnotatedSample:
    # host time
    ts_ms: int
    # angles
    T_pitch: float
    T_roll: float
    T_yaw: float
    L_pitch: float
    L_roll: float
    L_yaw: float
    # zones + compensation
    thor_zone: Zone
    lum_zone: Zone
    comp_index: float  # 0..100


class PostureEngine:
    """Motor stateful: mantiene ventana móvil para comp_index."""

    def __init__(self, *, sample_rate_hz: float = 50.0, comp_window_s: float = 10.0, comp_scale_deg: float = 25.0):
        self.sample_rate_hz = float(sample_rate_hz)
        self.comp_window_s = float(comp_window_s)
        self.comp_scale_deg = float(comp_scale_deg)

        n = max(1, int(round(self.sample_rate_hz * self.comp_window_s)))
        self._comp_buf: Deque[float] = deque(maxlen=n)

    def reset(self) -> None:
        self._comp_buf.clear()

    def thresholds(self, *, mode: str, sport: Optional[str] = None, profile: Optional[Dict] = None) -> Dict[str, Dict[str, float]]:
        """Devuelve thresholds (torácico/lumbar) en función del modo.

        sport/profile se usarán más adelante; aquí quedan listos para Sprint 3.
        """
        mode = (mode or "desk").strip().lower()
        if mode not in DEFAULT_THRESHOLDS:
            mode = "desk"
        return DEFAULT_THRESHOLDS[mode]

    def annotate(
        self,
        *,
        ts_ms: int,
        thor: SegmentAngles,
        lum: SegmentAngles,
        mode: str = "desk",
        sport: Optional[str] = None,
        profile: Optional[Dict] = None,
    ) -> AnnotatedSample:
        th = self.thresholds(mode=mode, sport=sport, profile=profile)

        thor_zone = _zone_from_abs(thor.pitch, thor.roll, **th["thor"])
        lum_zone = _zone_from_abs(lum.pitch, lum.roll, **th["lum"])

        # Compensación: discrepancia entre segmentos (pitch) escalada a 0..100
        # (en Sprint 3 podremos incluir baseline_diff por usuario)
        diff = float(lum.pitch) - float(thor.pitch)
        comp_raw = _clamp(abs(diff) / max(self.comp_scale_deg, 1e-6) * 100.0, 0.0, 100.0)

        self._comp_buf.append(comp_raw)
        comp_index = sum(self._comp_buf) / max(len(self._comp_buf), 1)

        return AnnotatedSample(
            ts_ms=int(ts_ms),
            T_pitch=float(thor.pitch),
            T_roll=float(thor.roll),
            T_yaw=float(thor.yaw),
            L_pitch=float(lum.pitch),
            L_roll=float(lum.roll),
            L_yaw=float(lum.yaw),
            thor_zone=thor_zone,
            lum_zone=lum_zone,
            comp_index=float(comp_index),
        )


def compute_risk_index(*, duration_s: float, thor_red_s: float, lum_red_s: float, comp_avg: float) -> float:
    """Risk index 0..100.

    Fórmula MVP (ajustable):
    - 45% peso a tiempo rojo lumbar
    - 35% peso a tiempo rojo torácico
    - 20% peso a compensación media
    """
    dur = max(float(duration_s), 1e-6)
    thor_red_pct = _clamp(float(thor_red_s) / dur, 0.0, 1.0)
    lum_red_pct = _clamp(float(lum_red_s) / dur, 0.0, 1.0)
    comp = _clamp(float(comp_avg) / 100.0, 0.0, 1.0)

    risk = 100.0 * (0.45 * lum_red_pct + 0.35 * thor_red_pct + 0.20 * comp)
    return float(_clamp(risk, 0.0, 100.0))
