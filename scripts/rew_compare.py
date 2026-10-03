"""Compare REW measurements exported as text (File > Export > Export measurement as text).

Usage:
  python scripts/rew_compare.py <file.txt> [<file.txt> ...] [--lo 20] [--hi 300] [--smooth 6] [--png out.png]

Prints the 1/N-octave smoothed level at a set of bass frequencies for each
measurement, a short summary of the 40-120 Hz region (average level, spread,
deepest dip) and, with --png, writes an overlay chart.
"""
import argparse
from pathlib import Path

import numpy as np

TABLE_FREQS = [20, 25, 31.5, 40, 50, 63, 70, 80, 90, 100, 125, 160, 200, 250, 315]


def load(path):
    rows = []
    for line in Path(path).read_text(errors="replace").splitlines():
        if not line or line[0] in "*#":
            continue
        parts = line.replace(",", " ").split()
        try:
            rows.append((float(parts[0]), float(parts[1])))
        except (ValueError, IndexError):
            continue
    data = np.array(rows)
    return data[:, 0], data[:, 1]


def smooth(freq, spl, fraction):
    """1/fraction-octave smoothing on a log grid, averaging in power (as REW does for SPL)."""
    grid = np.geomspace(10, 1000, 600)
    power = 10 ** (spl / 10)
    half = 2 ** (1 / (2 * fraction))
    out = np.empty_like(grid)
    for i, f in enumerate(grid):
        sel = (freq >= f / half) & (freq <= f * half)
        out[i] = 10 * np.log10(power[sel].mean()) if sel.any() else np.nan
    return grid, out


def at(grid, curve, f):
    return float(np.interp(np.log10(f), np.log10(grid), curve))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--lo", type=float, default=20)
    ap.add_argument("--hi", type=float, default=300)
    ap.add_argument("--smooth", type=float, default=6, help="1/N octave")
    ap.add_argument("--png")
    ap.add_argument("--average", action="store_true", help="add the power average of all curves")
    ap.add_argument("--save-average", help="write the average as a REW-importable text file")
    a = ap.parse_args()

    curves = {}
    for f in a.files:
        name = Path(f).stem.rstrip(".")
        curves[name] = smooth(*load(f), a.smooth)
    if a.average or a.save_average:
        grid = next(iter(curves.values()))[0]
        avg = 10 * np.log10(np.nanmean([10 ** (c / 10) for _, c in curves.values()], axis=0))
        if a.save_average:
            ok = ~np.isnan(avg)
            lines = ["* Average of: " + ", ".join(curves), "* Freq(Hz) SPL(dB) Phase(degrees)"]
            lines += [f"{f:.4f} {v:.3f} 0" for f, v in zip(grid[ok], avg[ok])]
            Path(a.save_average).write_text("\n".join(lines) + "\n")
            print(f"wrote {a.save_average}")
        curves["AVERAGE"] = (grid, avg)

    width = max(len(n) for n in curves)
    print(f"1/{a.smooth:g}-octave smoothed SPL (dB)")
    print(" " * width + "".join(f"{f:>7g}" for f in TABLE_FREQS))
    for name, (g, c) in curves.items():
        print(name.ljust(width) + "".join(f"{at(g, c, f):7.1f}" for f in TABLE_FREQS))

    print("\n40-120 Hz region: mean, spread (max-min), deepest point")
    for name, (g, c) in curves.items():
        sel = (g >= 40) & (g <= 120)
        seg, fs = c[sel], g[sel]
        print(f"{name.ljust(width)}  mean {seg.mean():5.1f} dB  spread {seg.max() - seg.min():4.1f} dB"
              f"  dip {seg.min():5.1f} dB at {fs[seg.argmin()]:5.1f} Hz")

    if a.png:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(10, 5.5))
        for name, (g, c) in curves.items():
            sel = (g >= a.lo) & (g <= a.hi)
            style = dict(color="black", linewidth=3) if name == "AVERAGE" else dict(linewidth=1.3, alpha=0.8)
            ax.semilogx(g[sel], c[sel], label=name, **style)
        ax.set_xlim(a.lo, a.hi)
        ax.set_xticks([20, 30, 40, 50, 60, 80, 100, 150, 200, 300])
        ax.get_xaxis().set_major_formatter(matplotlib.ticker.ScalarFormatter())
        ax.axvspan(60, 100, color="0.85", alpha=0.5, label="crossover region")
        ax.set_xlabel("Frequency (Hz)")
        ax.set_ylabel(f"SPL (dB), 1/{a.smooth:g} octave")
        ax.grid(True, which="both", alpha=0.3)
        ax.legend()
        fig.tight_layout()
        fig.savefig(a.png, dpi=110)
        print(f"\nwrote {a.png}")


if __name__ == "__main__":
    main()
