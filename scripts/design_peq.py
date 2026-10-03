"""Design cut-only peaking EQ filters for CamillaDSP from an averaged REW response.

Usage:
  python scripts/design_peq.py <average.txt> [--filters 6] [--lo 18] [--hi 140]
         [--ref-lo 150] [--ref-hi 300] [--lift 2] [--png out.png] [--yaml out.yml]

The target is flat at the average level of the reference band (default 150-300 Hz,
where the speakers are already accurate) plus a gentle bass lift of --lift dB that
ramps in below 120 Hz and is complete by 30 Hz. Only cuts are used: peaks above the
target are pulled down, dips are left alone (they are room cancellations that EQ
cannot fix). Filters are RBJ peaking biquads, as CamillaDSP implements them.
"""
import argparse
from pathlib import Path

import numpy as np

FS = 192000


def load(path):
    rows = []
    for line in Path(path).read_text(errors="replace").splitlines():
        if not line or line[0] in "*#":
            continue
        p = line.split()
        try:
            rows.append((float(p[0]), float(p[1])))
        except (ValueError, IndexError):
            pass
    d = np.array(rows)
    return d[:, 0], d[:, 1]


def peaking_db(f, f0, gain, q):
    w0 = 2 * np.pi * f0 / FS
    a = 10 ** (gain / 40)
    alpha = np.sin(w0) / (2 * q)
    b = np.array([1 + alpha * a, -2 * np.cos(w0), 1 - alpha * a])
    den = np.array([1 + alpha / a, -2 * np.cos(w0), 1 - alpha / a])
    z = np.exp(-1j * 2 * np.pi * f / FS)
    h = (b[0] + b[1] * z + b[2] * z ** 2) / (den[0] + den[1] * z + den[2] * z ** 2)
    return 20 * np.log10(np.abs(h))


def total(f, filters):
    return sum((peaking_db(f, *flt) for flt in filters), np.zeros_like(f))


def cost(f, resp, target, filters):
    err = resp + total(f, filters) - target
    # Above target counts fully; going below target (over-cutting) counts double.
    return float(np.mean(np.where(err > 0, err, -2 * err) ** 2))


def refine(f, resp, target, filters, f_lo, f_hi, q_max):
    """Jointly optimise all filters (frequency, gain, Q) with scipy's bounded least squares."""
    from scipy.optimize import least_squares

    def residual(x):
        flts = [(np.exp(x[i]), x[i + 1], np.exp(x[i + 2])) for i in range(0, len(x), 3)]
        err = resp + total(f, flts) - target
        return np.where(err > 0, err, -2 * err)

    x0, lo, hi = [], [], []
    for f0, g, q in filters:
        x0 += [np.log(f0), g, np.log(min(q, q_max))]
        lo += [np.log(f_lo), -12.0, np.log(0.7)]
        hi += [np.log(f_hi), 0.0, np.log(q_max)]
    x0 = np.clip(x0, np.array(lo) + 1e-9, np.array(hi) - 1e-9)
    x = least_squares(residual, x0, bounds=(lo, hi)).x
    return [(float(np.exp(x[i])), float(x[i + 1]), float(np.exp(x[i + 2]))) for i in range(0, len(x), 3)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("average")
    ap.add_argument("--filters", type=int, default=6)
    ap.add_argument("--lo", type=float, default=18)
    ap.add_argument("--hi", type=float, default=140)
    ap.add_argument("--ref-lo", type=float, default=150)
    ap.add_argument("--ref-hi", type=float, default=300)
    ap.add_argument("--lift", type=float, default=2.0, help="bass lift in dB below ~30 Hz")
    ap.add_argument("--q-max", type=float, default=5.0, help="narrowest filter allowed")
    ap.add_argument("--png")
    ap.add_argument("--yaml")
    a = ap.parse_args()

    f_all, r_all = load(a.average)
    ref = r_all[(f_all >= a.ref_lo) & (f_all <= a.ref_hi)].mean()
    sel = (f_all >= a.lo) & (f_all <= a.hi)
    f, resp = f_all[sel], r_all[sel]
    ramp = np.clip(np.log2(120 / f) / 2, 0, 1)          # 0 at 120 Hz, 1 at 30 Hz
    target = ref + a.lift * ramp

    filters = []
    for _ in range(a.filters):
        err = resp + total(f, filters) - target
        i = int(np.argmax(err))
        if err[i] < 1.0:
            break
        filters.append((float(f[i]), -float(min(err[i], 10)), 3.0))
        filters = refine(f, resp, target, filters, a.lo, a.hi, a.q_max)
    filters = sorted(filters)

    before = resp - target
    after = resp + total(f, filters) - target
    print(f"reference level {ref:.1f} dB ({a.ref_lo:g}-{a.ref_hi:g} Hz), bass lift {a.lift:g} dB")
    print(f"max excess above target: {before.max():.1f} dB -> {after.max():.1f} dB;"
          f" rms deviation {np.sqrt(np.mean(before ** 2)):.1f} -> {np.sqrt(np.mean(after ** 2)):.1f} dB")
    for n, (f0, g, q) in enumerate(filters, 1):
        print(f"  peq {n}: {f0:6.1f} Hz  {g:+5.1f} dB  Q {q:.2f}")

    if a.yaml:
        lines = []
        for n, (f0, g, q) in enumerate(filters, 1):
            lines += [f"  rew {n}:", "    type: Biquad", "    parameters:", "      type: Peaking",
                      f"      freq: {f0:.1f}", f"      gain: {g:.1f}", f"      q: {q:.2f}"]
        Path(a.yaml).write_text("filters:\n" + "\n".join(lines) + "\n")
        print(f"wrote {a.yaml}")

    if a.png:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(figsize=(10, 5.5))
        view = (f_all >= 15) & (f_all <= 500)
        fv = f_all[view]
        ax.semilogx(fv, r_all[view], color="0.55", linewidth=1.5, label="measured average")
        ax.semilogx(fv, r_all[view] + total(fv, filters), color="black", linewidth=2.5, label="predicted with EQ")
        ax.semilogx(f, target, "--", color="tab:green", label="target")
        ax.semilogx(fv, ref - 12 + total(fv, filters), color="tab:red", linewidth=1.2,
                    label="EQ curve (offset -12 dB)")
        ax.set_xlim(15, 500)
        ax.set_xticks([20, 30, 40, 50, 60, 80, 100, 150, 200, 300, 500])
        ax.get_xaxis().set_major_formatter(matplotlib.ticker.ScalarFormatter())
        ax.set_xlabel("Frequency (Hz)")
        ax.set_ylabel("SPL (dB)")
        ax.grid(True, which="both", alpha=0.3)
        ax.legend()
        fig.tight_layout()
        fig.savefig(a.png, dpi=110)
        print(f"wrote {a.png}")


if __name__ == "__main__":
    main()
