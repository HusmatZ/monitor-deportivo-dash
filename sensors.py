import pandas as pd
import numpy as np
from scipy.signal import find_peaks

def load_ecg_and_compute_bpm(filepath):
    df = pd.read_csv(filepath)
    t = df["Time"].values
    ecg = df["ECG"].values

    # Normalización básica
    ecg = ecg - np.mean(ecg)

    # Detección de picos (R-peaks)
    peaks, _ = find_peaks(ecg, distance=50, prominence=0.5)

    rr_intervals = np.diff(t[peaks]) * 1000  # en ms
    bpm = 60000 / np.mean(rr_intervals) if len(rr_intervals) > 0 else 0

    return t, ecg, bpm
