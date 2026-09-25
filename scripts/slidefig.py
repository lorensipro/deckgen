"""Aide pour les scripts de figures appelés par build.py (bloc `figure:`).

Un script de figure reçoit :  OUT --lang fr --audience experts [--cle valeur ...]
et doit écrire le fichier OUT. Squelette minimal :

    from slidefig import figure_args, setup, save
    import matplotlib.pyplot as plt
    a = figure_args()                 # a.out, a.lang, a.audience, a.extra (dict des --cle valeur)
    setup()                           # palette et police du diaporama
    fig, ax = plt.subplots(figsize=(6, 3.4))
    ...
    save(fig, a.out)
"""
import argparse, os, subprocess, sys

PALETTE = {"encre": "#1B2A41", "bleugris": "#4A5D7A", "gris": "#6B7280", "brume": "#EEF1F5",
           "accent": "#4A5D7A"}
CYCLE = ["#4A5D7A", "#C8502B", "#2E8B57", "#8B6BB1", "#D4A017", "#1B2A41"]

def figure_args(argv=None):
    """Lit OUT, --lang, --audience et les options libres --cle valeur (dans .extra)."""
    ap = argparse.ArgumentParser()
    ap.add_argument("out"); ap.add_argument("--lang", default="fr"); ap.add_argument("--audience", default="")
    a, rest = ap.parse_known_args(argv)
    a.extra = {}
    it = iter(rest)
    for k in it:
        if k.startswith("--"):
            v = next(it, "true")
            try: v = int(v)
            except ValueError:
                try: v = float(v)
                except ValueError: pass
            a.extra[k[2:]] = v
    return a

def T(lang, **texts):
    """T('en', fr='Époque', en='Epoch') -> texte dans la langue, repli sur fr."""
    return texts.get(lang) or texts.get("fr") or next(iter(texts.values()))

def _fira():
    """Utilise Fira Sans de TeX Live si matplotlib peut la charger (sinon police par défaut)."""
    try:
        import matplotlib.font_manager as fm
        p = subprocess.run(["kpsewhich", "FiraSans-Regular.otf"], capture_output=True, text=True).stdout.strip()
        if p:
            d = os.path.dirname(p)
            for f in os.listdir(d):
                if f.startswith("FiraSans-") and f.endswith(".otf") and any(w in f for w in ("Regular", "Bold", "Italic", "Light")):
                    fm.fontManager.addfont(os.path.join(d, f))
            return "Fira Sans"
    except Exception:
        pass
    return None

def setup():
    """rcParams sobres, cohérents avec le thème Beamer (couleurs, police, axes épurés)."""
    import matplotlib as mpl
    mpl.use("Agg")
    font = _fira()
    mpl.rcParams.update({
        "font.family": [font] if font else ["sans-serif"],
        "font.size": 11, "axes.titlesize": 12, "axes.labelsize": 11,
        "axes.edgecolor": PALETTE["gris"], "axes.labelcolor": PALETTE["encre"],
        "xtick.color": PALETTE["gris"], "ytick.color": PALETTE["gris"],
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.prop_cycle": mpl.cycler(color=CYCLE),
        "axes.grid": True, "grid.color": PALETTE["brume"], "grid.linewidth": 0.8,
        "legend.frameon": False, "figure.dpi": 150, "savefig.bbox": "tight",
        "pdf.fonttype": 42,
    })
    return PALETTE

def save(fig, out):
    fig.savefig(out)   # le format suit l'extension (pdf vectoriel, ou png)
