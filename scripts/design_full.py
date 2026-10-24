"""Full-range EQ design (car or room) from an averaged response, e.g. pocket_analyse.py's average.txt.

Usage:
  python scripts/design_full.py <average.txt> [--name car_v1] [--out <folder>]
         [--ref-lo 500 --ref-hi 2000] [--bass 8 --bass-from 60 --bass-to 200]
         [--tilt 1.0] [--cut-lo 30 --cut-hi 500 --filters 6 --q-max 5] [--shelf-max 3]

Target, relative to the mean level of the reference band (default 500 Hz-2 kHz):
  - bass shelf: +bass dB below --bass-from, ramping (log f) to 0 dB at --bass-to;
  - flat in the mids;
  - treble tilt: -tilt dB per octave above 2 kHz.
Filters:
  1. one high shelf at 4 kHz (Q 0.7) that matches the average treble error, limited to +-shelf-max dB;
  2. cut-only peaking filters between --cut-lo and --cut-hi (same fit as design_peq.py).
The response is smoothed to 1/6 octave first, so filters follow trends, not comb-filter ripples.
Writes <name>_ParametricEQ.txt (Poweramp / APO), <name>.txt (Wavelet GraphicEQ), <name>.png.
"""
import argparse
from pathlib import Path

import numpy as np

import design_peq as dp

dp.FS = 48000                      # phone EQ apps run at 48 kHz
WAVELET_F = [20, 21, 22, 23, 24, 26, 27, 29, 30, 32, 34, 36, 38, 40, 43, 45, 48, 50, 53, 56, 59, 63, 66, 70, 74, 78,
             83, 87, 92, 97, 103, 109, 115, 121, 128, 136, 143, 151, 160, 169, 178, 188, 199, 210, 222, 235, 248, 262,
             277, 292, 309, 326, 345, 364, 385, 406, 429, 453, 479, 506, 534, 565, 596, 630, 665, 703, 743, 784, 829,
             875, 924, 977, 1032, 1090, 1151, 1216, 1284, 1357, 1433, 1514, 1599, 1689, 1784, 1885, 1991, 2103, 2221,
             2347, 2479, 2618, 2766, 2921, 3086, 3260, 3443, 3637, 3842, 4058, 4287, 4528, 4783, 5052, 5337, 5637,
             5955, 6290, 6644, 7018, 7414, 7831, 8272, 8738, 9230, 9749, 10298, 10878, 11490, 12137, 12821, 13543,
             14305, 15110, 15961, 16860, 17809, 18812, 19871]


def highshelf_db(f, f0, gain, q=0.7071):
    """RBJ high shelf, as CamillaDSP / APO implement it."""
    w0 = 2 * np.pi * f0 / dp.FS
    a = 10 ** (gain / 40)
    alpha = np.sin(w0) / (2 * q)
    c = np.cos(w0)
    sa = 2 * np.sqrt(a) * alpha
    b = np.array([a * ((a + 1) + (a - 1) * c + sa), -2 * a * ((a - 1) + (a + 1) * c), a * ((a + 1) + (a - 1) * c - sa)])
    d = np.array([(a + 1) - (a - 1) * c + sa, 2 * ((a - 1) - (a + 1) * c), (a + 1) - (a - 1) * c - sa])
    z = np.exp(-1j * 2 * np.pi * f / dp.FS)
    h = (b[0] + b[1] * z + b[2] * z ** 2) / (d[0] + d[1] * z + d[2] * z ** 2)
    return 20 * np.log10(np.abs(h))


def smooth(f, db, oct_w):
    out = np.empty_like(db)
    p = 10 ** (db / 10)
    for i, fc in enumerate(f):
        m = (f >= fc * 2 ** (-oct_w / 2)) & (f <= fc * 2 ** (oct_w / 2))
        out[i] = 10 * np.log10(p[m].mean())
    return out


def target(f, ref, a):
    bass = a.bass * np.clip(np.log(a.bass_to / f) / np.log(a.bass_to / a.bass_from), 0, 1)
    tilt = -a.tilt * np.clip(np.log2(f / 2000), 0, None)
    return ref + bass + tilt


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("average")
    ap.add_argument("--name", default="eq_v1")
    ap.add_argument("--out")
    ap.add_argument("--ref-lo", type=float, default=500)
    ap.add_argument("--ref-hi", type=float, default=2000)
    ap.add_argument("--bass", type=float, default=8, help="bass lift in dB below --bass-from")
    ap.add_argument("--bass-from", type=float, default=60)
    ap.add_argument("--bass-to", type=float, default=200)
    ap.add_argument("--tilt", type=float, default=1.0, help="treble roll-off in dB per octave above 2 kHz")
    ap.add_argument("--cut-lo", type=float, default=30)
    ap.add_argument("--cut-hi", type=float, default=500)
    ap.add_argument("--filters", type=int, default=6)
    ap.add_argument("--q-max", type=float, default=5)
    ap.add_argument("--shelf-max", type=float, default=3)
    a = ap.parse_args()

    f_all, raw = dp.load(a.average)
    keep = (f_all >= 20) & (f_all <= 20000)
    f_all, raw = f_all[keep], raw[keep]
    resp = smooth(f_all, raw, 1 / 6)
    ref = resp[(f_all >= a.ref_lo) & (f_all <= a.ref_hi)].mean()
    tgt = target(f_all, ref, a)

    # 1. treble shelf: average error 3-12 kHz, limited
    hf = (f_all >= 3000) & (f_all <= 12000)
    shelf = float(np.clip(-(resp[hf] - tgt[hf]).mean(), -a.shelf_max, a.shelf_max))
    shelf = round(shelf * 2) / 2
    resp_s = resp + highshelf_db(f_all, 4000, shelf)

    # 2. cut-only peaking filters in the bass / low mids
    sel = (f_all >= a.cut_lo) & (f_all <= a.cut_hi)
    f, r, t = f_all[sel], resp_s[sel], tgt[sel]
    filters = []
    for _ in range(a.filters):
        err = r + dp.total(f, filters) - t
        i = int(np.argmax(err))
        if err[i] < 1.0:
            break
        filters.append((float(f[i]), -float(min(err[i], 10)), 2.0))
        filters = dp.refine(f, r, t, filters, a.cut_lo, a.cut_hi, a.q_max)
    merged = True
    while merged and len(filters) > 1:
        merged = False
        filters = sorted(filters)
        for i in range(len(filters) - 1):
            (f1, g1, q1), (f2, g2, q2) = filters[i], filters[i + 1]
            if np.log2(f2 / f1) < 0.1:
                filters[i:i + 2] = [(float(np.sqrt(f1 * f2)), max(-12.0, g1 + g2), max(q1, q2))]
                filters = dp.refine(f, r, t, filters, a.cut_lo, a.cut_hi, a.q_max)
                merged = True
                break
    filters = sorted((round(x, 1), round(g, 1), round(q, 2)) for x, g, q in filters)

    def eq(fr):
        return highshelf_db(fr, 4000, shelf) + dp.total(fr, filters)

    after = resp + eq(f_all)
    pre = -max(0.0, float(eq(np.geomspace(20, 20000, 400)).max()) + 0.1) if shelf > 0 else 0.0
    band = (f_all >= 30) & (f_all <= 16000)
    rms = lambda e: float(np.sqrt(np.mean(e ** 2)))
    print(f"reference {a.ref_lo:g}-{a.ref_hi:g} Hz = {ref:.1f} dB; target bass +{a.bass:g} dB, tilt -{a.tilt:g} dB/oct above 2 kHz")
    print(f"deviation from target 30 Hz-16 kHz: {rms(resp[band] - tgt[band]):.1f} -> {rms(after[band] - tgt[band]):.1f} dB rms")
    print(f"  high shelf 4000 Hz {shelf:+.1f} dB Q 0.71")
    for n, (x, g, q) in enumerate(filters, 1):
        print(f"  peq {n}: {x:7.1f} Hz {g:+5.1f} dB Q {q:.2f}")
    print(f"  preamp {pre:.1f} dB")

    out = Path(a.out) if a.out else Path(a.average).parent
    lines = [f"Preamp: {pre:.1f} dB"]
    k = 1
    if shelf:
        lines.append(f"Filter {k}: ON HSC Fc 4000 Hz Gain {shelf:.1f} dB Q 0.71")
        k += 1
    for x, g, q in filters:
        lines.append(f"Filter {k}: ON PK Fc {x:.1f} Hz Gain {g:.1f} dB Q {q:.2f}")
        k += 1
    (out / f"{a.name}_ParametricEQ.txt").write_text("\n".join(lines) + "\n", newline="\n")
    wf = np.array(WAVELET_F, float)
    (out / f"{a.name}.txt").write_text("GraphicEQ: " + "; ".join(f"{x} {v + pre:.1f}" for x, v in zip(WAVELET_F, eq(wf))) + "\n",
                                     newline="\n")

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(11, 5.8))
    ax.semilogx(f_all, resp - ref, color="0.55", lw=1.5, label="measured average (1/6 oct)")
    ax.semilogx(f_all, after - ref, color="black", lw=2.4, label=f"with {a.name}")
    ax.semilogx(f_all, tgt - ref, "--", color="tab:green", lw=1.6, label="target")
    ax.semilogx(f_all, eq(f_all) - 20, color="tab:red", lw=1.3, label="EQ curve (offset -20 dB)")
    ax.set_xlim(20, 20000)
    ax.set_xticks([20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000])
    ax.get_xaxis().set_major_formatter(matplotlib.ticker.ScalarFormatter())
    ax.set_xlabel("Frequency (Hz)")
    ax.set_ylabel(f"dB re. {a.ref_lo:g}-{a.ref_hi:g} Hz")
    ax.grid(True, which="both", alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(out / f"{a.name}.png", dpi=100)
    print(f"wrote {a.name}_ParametricEQ.txt, {a.name}.txt, {a.name}.png in {out}")


if __name__ == "__main__":
    main()
