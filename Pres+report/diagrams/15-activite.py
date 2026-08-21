"""Generate diagrams/15-activite.png -- daily commits over the repository's life.

    python diagrams/15-activite.py

Read from git rather than typed, and regenerated deliberately rather than at
build time: the figure has to agree with the counts quoted in the surrounding
prose, and a chart that redraws itself on every build would drift away from
them without anyone noticing.

The palette is the report's own -- the AZNET blue, one hue, opacity carrying
intensity. Same figure as the defence deck's, drawn twice on purpose: the deck
builds its version from rectangles because PowerPoint has no honest chart, and
this one is a bitmap because Word has none either.
"""

import subprocess
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import MultipleLocator  # noqa: E402

BLUE = "#0278E4"
GREY = "#575656"
MUTE = "#8A8A8A"
LINE = "#DFE1DE"
HERE = Path(__file__).parent
REPO = HERE.parents[1]


def series():
    """[(date, count)] over every calendar day, gaps included as zeros."""
    out = subprocess.run(
        ["git", "log", "--pretty=format:%ad", "--date=short"],
        cwd=REPO, capture_output=True, text=True, check=True).stdout
    counts = Counter(out.split())
    lo = date.fromisoformat(min(counts))
    hi = date.fromisoformat(max(counts))
    days = [lo + timedelta(days=i) for i in range((hi - lo).days + 1)]
    return [(d, counts.get(d.isoformat(), 0)) for d in days]


def main():
    data = series()
    vals = [v for _, v in data]
    top = max(vals)
    mean = sum(vals) / len(vals)

    fig, ax = plt.subplots(figsize=(9.2, 2.9), dpi=300)
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")

    for i, v in enumerate(vals):
        if v:
            # One hue. Opacity carries intensity, as everywhere else.
            ax.bar(i, v, width=0.72, color=BLUE, alpha=0.34 + 0.66 * v / top,
                   linewidth=0)
        else:
            ax.bar(i, top * 0.012, width=0.72, color=LINE, linewidth=0)

    ax.axhline(mean, color=MUTE, linewidth=0.7)
    ax.text(0.3, mean + top * 0.03,
            ("moyenne %.1f / jour" % mean).replace(".", ","),
            color=MUTE, fontsize=7, va="bottom")
    peak = vals.index(top)
    ax.text(peak, top + top * 0.04, str(top), color=BLUE, fontsize=8,
            fontweight="bold", ha="center", va="bottom")

    ax.set_xlim(-0.9, len(vals) - 0.1)
    ax.set_ylim(0, top * 1.16)
    ax.set_xticks(range(0, len(data), 7))
    ax.set_xticklabels([d.strftime("%d/%m") for d, _ in data[::7]],
                       fontsize=7, color=MUTE)
    ax.yaxis.set_major_locator(MultipleLocator(10))
    ax.tick_params(axis="y", labelsize=7, colors=MUTE, length=0)
    ax.tick_params(axis="x", length=0, pad=5)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color("#C3C7C9")
    ax.spines["bottom"].set_linewidth(0.8)
    ax.grid(axis="y", color=LINE, linewidth=0.5, zorder=0)
    ax.set_axisbelow(True)
    ax.set_ylabel("commits", fontsize=7.5, color=GREY, labelpad=6)

    fig.tight_layout(pad=0.4)
    out = HERE / "15-activite.png"
    fig.savefig(out, facecolor="white")
    print("%s  (%d jours, %d commits, pic %d)"
          % (out, len(vals), sum(vals), top))


if __name__ == "__main__":
    main()
