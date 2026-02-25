"""clock_sync.py

Sincronización en software para 2 IMUs con relojes independientes.

Idea:
- Cada IMU entrega su timestamp (imu_ts_ms) en su propia base de tiempo.
- En el host (PC / móvil / SBC) registramos cuándo llegó el paquete (host_recv_ms).
- Estimamos un mapeo lineal: host_ms ≈ a * imu_ms + b (corrige offset + drift).
- Luego alineamos los streams en una línea de tiempo común (host).

Esto sirve tanto para simulación como para hardware real (BLE/Serial/WiFi).
"""

from __future__ import annotations

from dataclasses import dataclass
from collections import deque
from typing import Deque, Optional, Tuple


def _clamp(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else hi if x > hi else x


@dataclass
class SyncParams:
    a: float = 1.0  # slope (drift)
    b: float = 0.0  # intercept (offset)


class LinearClockSync:
    """Estimador lineal host = a*imu + b usando mínimos cuadrados en ventana."""

    def __init__(self, *, max_points: int = 200, min_points: int = 12):
        self._pts: Deque[Tuple[float, float]] = deque(maxlen=max_points)
        self._min_points = int(min_points)
        self.params = SyncParams()

    def update(self, *, imu_ts_ms: float, host_recv_ms: float) -> SyncParams:
        self._pts.append((float(imu_ts_ms), float(host_recv_ms)))
        if len(self._pts) < self._min_points:
            # Offset básico mientras calentamos
            last_imu, last_host = self._pts[-1]
            self.params = SyncParams(a=1.0, b=(last_host - last_imu))
            return self.params

        # Least squares: host = a*imu + b
        xs = [p[0] for p in self._pts]
        ys = [p[1] for p in self._pts]
        n = float(len(xs))

        x_mean = sum(xs) / n
        y_mean = sum(ys) / n

        sxx = sum((x - x_mean) ** 2 for x in xs)
        sxy = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys))

        # Si sxx es ~0, volvemos a offset simple
        if abs(sxx) < 1e-9:
            self.params = SyncParams(a=1.0, b=(y_mean - x_mean))
            return self.params

        a = sxy / sxx
        b = y_mean - a * x_mean

        # Limita a para evitar inestabilidades (drift muy grande no realista en IMUs)
        a = _clamp(a, 0.95, 1.05)
        self.params = SyncParams(a=float(a), b=float(b))
        return self.params

    def to_host_ms(self, imu_ts_ms: float) -> float:
        p = self.params
        return p.a * float(imu_ts_ms) + p.b


class DualStreamAligner:
    """Alineador por sample-and-hold sobre una línea de tiempo común (host)."""

    def __init__(self, *, max_age_ms: int = 250):
        self.max_age_ms = int(max_age_ms)
        self._last_A = None  # (host_ts_ms, imu_ts_ms, payload)
        self._last_B = None

    def push_A(self, *, host_ts_ms: float, imu_ts_ms: float, payload):
        self._last_A = (float(host_ts_ms), float(imu_ts_ms), payload)

    def push_B(self, *, host_ts_ms: float, imu_ts_ms: float, payload):
        self._last_B = (float(host_ts_ms), float(imu_ts_ms), payload)

    def fused_at(self, *, host_ts_ms: float):
        """Devuelve (A_payload, B_payload, A_imu_ts, B_imu_ts) si están frescos."""
        t = float(host_ts_ms)

        def _pick(last):
            if not last:
                return None
            ht, it, pl = last
            if (t - ht) > self.max_age_ms:
                return None
            return (pl, it)

        a = _pick(self._last_A)
        b = _pick(self._last_B)

        if not a or not b:
            return None

        return (a[0], b[0], int(a[1]), int(b[1]))
