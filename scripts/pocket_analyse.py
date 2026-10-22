"""Analyse Josh's EQ Pocket sweep recordings (WAV) on the PC, the same way the phone page does.

Usage:
  python scripts/pocket_analyse.py <wav or folder> [...] [--cal measurements/umik1/7079072.txt]
         [--win 300] [--out <folder>] [--png chart.png]

For each recording it finds the page's 8 s log sweep (18 Hz - 20 kHz), deconvolves it into an
impulse response, windows it (--win ms), applies the UMIK-1 calibration and writes a REW-style
text file "<name>.txt" (Freq Hz, SPL dB). It also writes "average.txt" (dB average of all
positions), which scripts/design_peq.py reads.
"""
import argparse
import wave
from pathlib import Path

import numpy as np

SWEEP = dict(f1=18.0, f2=20000.0, T=8.0, amp=0.5)
FINE = 20 * 2 ** (np.arange(957) / 96)        # same 1/96-octave grid as the page


def read_wav(path):
    with wave.open(str(path)) as w:
        fs, ch, width, n = w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()
        raw = w.readframes(n)
    if width == 3:
        b = np.frombuffer(raw, np.uint8).reshape(-1, 3)
        v = (b[:, 0].astype(np.int32) | (b[:, 1].astype(np.int32) << 8) | (b[:, 2].astype(np.int32) << 16))
        v = np.where(v >= 1 << 23, v - (1 << 24), v) / float(1 << 23)
    elif width == 2:
        v = np.frombuffer(raw, np.int16) / 32768.0
    elif width == 4:
        v = np.frombuffer(raw, np.int32) / float(1 << 31)
    else:
        raise ValueError(f"{width * 8}-bit WAV not supported")
    v = v.reshape(-1, ch)
    loud = int(np.argmax((v ** 2).sum(axis=0)))     # the page also takes the louder channel
    return v[:, loud], fs, ch


def make_sweep(fs):
    f1, f2, T, amp = SWEEP["f1"], SWEEP["f2"], SWEEP["T"], SWEEP["amp"]
    n = round(T * fs)
    t = np.arange(n) / fs
    L = np.log(f2 / f1)
    s = np.sin(2 * np.pi * f1 * T / L * (np.exp(t * L / T) - 1))
    fi, fo = round(0.05 * fs), round(0.01 * fs)
    s[:fi] *= 0.5 - 0.5 * np.cos(np.pi * np.arange(fi) / fi)
    s[n - fo + 1:] *= 0.5 - 0.5 * np.cos(np.pi * (n - np.arange(n - fo + 1, n)) / fo)
    return s * amp


def pick_region(rec, fs):
    want = round((SWEEP["T"] + 4) * fs)
    if len(rec) <= want:
        return rec
    hop = round(0.1 * fs)
    e = np.add.reduceat(rec[: len(rec) // hop * hop] ** 2, np.arange(0, len(rec) // hop * hop, hop))
    w = round(SWEEP["T"] * fs / hop)
    best = int(np.argmax(np.convolve(e, np.ones(w), "valid")))
    start = max(0, best * hop - round(1.5 * fs))
    return rec[start:start + want]


CHECK_T = (0.5, 2.5, 4.5, 6.5, 7.6)        # seconds into the sweep


def check_sweep(rec, fs, p0):
    """Return (ok, freq): is the sweep present at each checkpoint? freq = first missing frequency.

    p0 is where the sweep starts in rec (the impulse peak). At each checkpoint the band around the
    sweep's frequency must be >= 6 dB above the same band in the silence before or after the sweep."""
    L = np.log(SWEEP["f2"] / SWEEP["f1"])
    n = 4096
    win = np.hanning(n)
    fr = np.fft.rfftfreq(n, 1 / fs)

    def band_db(start, f):
        if start < 0 or start + n > len(rec):
            return None
        P = np.abs(np.fft.rfft(rec[start:start + n] * win)) ** 2
        m = np.abs(fr - f) <= max(0.18 * f, 2.5 * fs / n)     # at least a few FFT bins
        return 10 * np.log10(P[m].sum() + 1e-30)

    for t in CHECK_T:
        f = SWEEP["f1"] * np.exp(t * L / SWEEP["T"])
        sig = band_db(p0 + round(t * fs) - n // 2, f)
        ref = band_db(p0 - round(1.0 * fs), f)
        if ref is None:
            ref = band_db(p0 + round((SWEEP["T"] + 1.0) * fs), f)
        if sig is None or ref is None or sig - ref < 6:
            return False, f
    return True, None


def analyse(rec, fs, win_ms, cal_f, cal_db):
    rec = pick_region(rec, fs)
    peak = 20 * np.log10(np.abs(rec).max() + 1e-12)
    sw = make_sweep(fs)
    N = 1 << int(np.ceil(np.log2(len(rec) + len(sw))))
    R, S = np.fft.fft(rec, N), np.fft.fft(sw, N)
    f = np.abs(np.fft.fftfreq(N, 1 / fs))
    p = np.abs(S) ** 2
    band = (f >= SWEEP["f1"]) & (f <= SWEEP["f2"])
    mean = p[band].mean()
    eps = np.where((f >= SWEEP["f1"] * 0.9) & (f <= SWEEP["f2"]), 1e-4 * mean, 10 * mean)
    h = np.real(np.fft.ifft(R * np.conj(S) / (p + eps)))
    p0 = int(np.argmax(np.abs(h)))
    complete, missing = check_sweep(rec, fs, p0)
    nn = round(0.2 * fs)
    noise = h[(p0 + round(N * 0.4) + np.arange(nn)) % N]
    snr = 20 * np.log10(np.abs(h[p0]) / np.sqrt(np.mean(noise ** 2) + 1e-30))
    pre, post = round(0.003 * fs), round(win_ms / 1000 * fs)
    fade = round(post * 0.3)
    idx = np.arange(-pre, post)
    w = np.ones(len(idx))
    w[:pre] = 0.5 - 0.5 * np.cos(np.pi * np.arange(pre) / pre)
    tail = idx > post - fade
    w[tail] = 0.5 + 0.5 * np.cos(np.pi * (idx[tail] - (post - fade)) / fade)
    seg = h[(p0 + idx) % N] * w
    M = max(65536, 1 << int(np.ceil(np.log2(len(seg)))))
    P = np.abs(np.fft.rfft(seg, M)) ** 2
    bins = np.arange(len(P)) * fs / M
    out = np.empty(len(FINE))
    for j, fc in enumerate(FINE):
        m = (bins >= fc * 2 ** (-1 / 192)) & (bins <= fc * 2 ** (1 / 192))
        pw = P[m].mean() if m.sum() >= 2 else np.interp(fc, bins, P)
        out[j] = 10 * np.log10(pw + 1e-30)
    out -= np.interp(np.log(FINE), np.log(cal_f), cal_db)
    return out, peak, snr, missing if not complete else None


def load_cal(path):
    rows = []
    for line in Path(path).read_text(errors="replace").splitlines():
        parts = line.split()
        try:
            rows.append((float(parts[0]), float(parts[1])))
        except (ValueError, IndexError):
            pass
    d = np.array(rows)
    return d[:, 0], d[:, 1]


def write_txt(path, f, db, note):
    lines = [f"* {note}", "* Freq(Hz) SPL(dB)"] + [f"{a:.4f} {b:.3f}" for a, b in zip(f, db)]
    Path(path).write_text("\n".join(lines) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("inputs", nargs="+")
    ap.add_argument("--cal", default="measurements/umik1/7079072.txt")
    ap.add_argument("--win", type=float, default=300)
    ap.add_argument("--out")
    ap.add_argument("--png")
    ap.add_argument("--force", action="store_true",
                    help="keep recordings with an incomplete sweep (only the covered low band is valid)")
    a = ap.parse_args()

    wavs = []
    for i in a.inputs:
        p = Path(i)
        wavs += sorted(p.glob("*.wav")) if p.is_dir() else [p]
    out_dir = Path(a.out) if a.out else wavs[0].parent
    cal_f, cal_db = load_cal(a.cal)

    curves = []
    for w in wavs:
        rec, fs, ch = read_wav(w)
        db, peak, snr, missing = analyse(rec, fs, a.win, cal_f, cal_db)
        if missing is not None and a.force:
            print(f"{w.name}: incomplete sweep (first failed check at {missing:.0f} Hz), kept because of --force")
        elif missing is not None:
            print(f"{w.name}: SKIPPED, the sweep is incomplete or missing (first failed check at "
                  f"{missing:.0f} Hz): the recording stopped early, or the sweep was too quiet")
            continue
        flag = "CLIPPED" if peak > -0.2 else "too quiet" if peak < -40 else "noisy" if snr < 35 else "ok"
        print(f"{w.name}: {fs} Hz, {ch} ch, peak {peak:.1f} dBFS, SNR {snr:.0f} dB -> {flag}")
        write_txt(out_dir / (w.stem + ".txt"), FINE, db, f"Pocket EQ analysis of {w.name}, window {a.win:g} ms")
        curves.append(db)
    if not curves:
        print("no usable recordings")
        return
    avg = np.mean(curves, axis=0)
    write_txt(out_dir / "average.txt", FINE, avg, f"dB average of {len(curves)} positions")
    print(f"wrote {len(curves)} position files and average.txt to {out_dir}")

    if a.png:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(10, 5.5))
        for w, c in zip(wavs, curves):
            ax.semilogx(FINE, c, linewidth=1, alpha=0.6, label=w.stem)
        ax.semilogx(FINE, avg, color="black", linewidth=2.5, label="average")
        ax.set_xlim(20, 20000)
        ax.set_xticks([20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000])
        ax.get_xaxis().set_major_formatter(matplotlib.ticker.ScalarFormatter())
        ax.set_xlabel("Frequency (Hz)")
        ax.set_ylabel("dB (relative)")
        ax.grid(True, which="both", alpha=0.3)
        ax.legend(fontsize=8)
        fig.tight_layout()
        fig.savefig(a.png, dpi=110)
        print(f"wrote {a.png}")


if __name__ == "__main__":
    main()
