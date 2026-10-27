"""Compare a before (Flat) and an after (Room EQ) measurement against the design target.

Usage:
  python scripts/compare_room.py <flat.txt> <eq.txt> [--png out.png] [--lift 2] [--hi 300] [--align]

Reads REW-style text files (Freq Hz, SPL dB), e.g. from scripts/pocket_analyse.py. The target is
the one scripts/design_peq.py used: flat at the Flat curve's 150-300 Hz average plus --lift dB that
ramps in below 120 Hz and is complete by 30 Hz. Prints the error per band and draws the chart.
--align shifts the EQ curve to the Flat curve's 150-300 Hz level, for runs made at different volumes
(valid while the EQ changes nothing in that band).
"""
import argparse

import numpy as np

from design_peq import load

BANDS = [(18, 30), (30, 45), (45, 60), (60, 80), (80, 110), (110, 150), (150, 200), (200, 300)]


def smooth(f, r, frac=6):
    """1/frac-octave smoothing (power average), as REW shows it."""
    p = 10 ** (r / 10)
    out = np.empty_like(r)
    k = 2 ** (1 / (2 * frac))
    for i, fc in enumerate(f):
        m = (f >= fc / k) & (f <= fc * k)
        out[i] = 10 * np.log10(p[m].mean())
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("flat")
    ap.add_argument("eq")
    ap.add_argument("--png")
    ap.add_argument("--lift", type=float, default=2.0)
    ap.add_argument("--hi", type=float, default=300)
    ap.add_argument("--align", action="store_true")
    a = ap.parse_args()

    f0, r0 = load(a.flat)
    f1, r1 = load(a.eq)
    f = np.geomspace(18, 20000, 600)
    flat = smooth(f, np.interp(f, f0, r0))
    eq = smooth(f, np.interp(f, f1, r1))
    band = (f >= 150) & (f <= 300)
    ref = flat[band].mean()
    if a.align:
        shift = ref - eq[band].mean()
        eq = eq + shift
        print(f"EQ curve shifted by {shift:+.1f} dB to the Flat level at 150-300 Hz")
    target = ref + a.lift * np.clip(np.log2(120 / f) / 2, 0, 1)

    print(f"{'band Hz':>10} {'Flat':>7} {'Room EQ':>8}   (dB above (+) / below (-) target, 1/6 oct)")
    for lo, hi in BANDS:
        m = (f >= lo) & (f < hi)
        print(f"{lo:>4}-{hi:<5} {np.mean(flat[m] - target[m]):>+7.1f} {np.mean(eq[m] - target[m]):>+8.1f}")
    m = (f >= 18) & (f <= a.hi)
    for name, r in (("Flat", flat), ("Room EQ", eq)):
        e = r[m] - target[m]
        print(f"{name:>8}: worst peak {e.max():+.1f} dB at {f[m][e.argmax()]:.0f} Hz, "
              f"RMS error 18-{a.hi:.0f} Hz {np.sqrt(np.mean(e ** 2)):.1f} dB")

    if a.png:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(10, 5.2), dpi=110)
        ax.semilogx(f, flat, color="#8a94a6", lw=1.6, label="Flat (no EQ)")
        ax.semilogx(f, eq, color="#ff7a72", lw=2.2, label="Room EQ (rew_v1)")
        mt = f <= a.hi
        ax.semilogx(f[mt], target[mt], color="#3ccfe0", lw=1.6, ls="--", label="Target (design)")
        ax.fill_between(f[mt], target[mt] - 3, target[mt] + 3, color="#3ccfe0", alpha=0.10, label="Target ±3 dB")
        ax.axvspan(18, a.hi, color="#000", alpha=0.03)
        ax.set_xlim(18, 20000)
        # Scale on 20 Hz-10 kHz around the target, so a notch at the top end cannot squash the chart.
        mid = (f >= 20) & (f <= 10000)
        lo = np.floor(min(np.percentile(flat[mid], 3), np.percentile(eq[mid], 3), ref - 15) / 5) * 5
        ax.set_ylim(lo, max(lo + 45, np.ceil((max(flat[mid].max(), eq[mid].max()) + 3) / 5) * 5))
        ax.set_xticks([20, 30, 50, 100, 200, 300, 500, 1000, 2000, 5000, 10000, 20000])
        ax.set_xticklabels(["20", "30", "50", "100", "200", "300", "500", "1k", "2k", "5k", "10k", "20k"])
        ax.set_xlabel("Frequency (Hz)")
        ax.set_ylabel("SPL (dB, 1/6 octave)")
        ax.set_title("Listening position: Flat vs Room EQ (shaded = corrected range)")
        ax.grid(True, which="both", alpha=0.25)
        ax.legend(loc="lower left")
        fig.tight_layout()
        fig.savefig(a.png)
        print(f"wrote {a.png}")


if __name__ == "__main__":
    main()
