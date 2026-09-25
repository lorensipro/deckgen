#!/usr/bin/env python3
"""Exemple de figure générée : lois d'échelle et émergence (courbe sigmoïde jouet).
Appelé par build.py :  exemple_sigmoide.py OUT --lang fr --audience public --seuil 22
"""
from slidefig import figure_args, setup, save, T   # scripts/slidefig.py du générateur (PYTHONPATH fixé par build.py)
import numpy as np
import matplotlib.pyplot as plt

a = figure_args()
pal = setup()
seuil = a.extra.get("seuil", 22)          # exposant (FLOPs) où la capacité « émerge »
x = np.linspace(18, 25, 200)
y = 100 / (1 + np.exp(-2.2 * (x - seuil)))
fig, ax = plt.subplots(figsize=(6, 3.4))
ax.plot(x, y, lw=2.2, label=T(a.lang, fr="précision sur la tâche", en="task accuracy"))
ax.axhline(25, ls="--", color=pal["gris"], lw=1, label=T(a.lang, fr="hasard", en="random"))
ax.axvline(seuil, color=pal["brume"], lw=8, zorder=0)
ax.set_xlabel(T(a.lang, fr="échelle du modèle (log10 FLOPs d'entraînement)", en="model scale (log10 training FLOPs)"))
ax.set_ylabel("%")
if a.audience != "public":                # détail réservé aux étudiants
    ax.annotate(T(a.lang, fr="seuil d'émergence", en="emergence threshold"), (seuil, 50),
                xytext=(seuil - 2.6, 70), color=pal["bleugris"],
                arrowprops=dict(arrowstyle="->", color=pal["bleugris"]))
ax.legend(loc="upper left")
save(fig, a.out)
