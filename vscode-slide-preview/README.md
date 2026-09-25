# Slide Preview (YAML → Beamer)

Extension VS Code minimale, en JavaScript pur, qui affiche dans un panneau à droite le transparent
Beamer correspondant à la position du curseur dans un fichier YAML de `build.py`.

- Suit le curseur : changer de transparent recompile (délai 250 ms), taper recompile le transparent
  courant après 900 ms d'inactivité, sauvegarder recompile immédiatement. Le buffer est compilé même
  s'il n'est pas sauvegardé.
- Sélecteurs de langue et d'audience (lus dans `deck.yaml`), navigation entre les couches,
  temps de compilation affiché, erreurs pdflatex ou YAML affichées dans le panneau.
- Fichiers TikZ : quand l'éditeur actif est un `.tikz` (ou `.tex`) du projet, le panneau montre le
  transparent qui l'utilise, avec le contenu en cours d'édition, ou le dessin seul s'il n'est pas
  encore référencé. Les macros `\T{fr}{en}` et `\ifaud{public}{..}{..}` suivent les sélecteurs.
  Une erreur LaTeX est soulignée à la ligne fautive du fichier TikZ.
- Erreurs précises : une erreur YAML (ligne et colonne), une erreur de structure (clé ou bloc inconnu,
  item de liste mal formé, avec la ligne du bloc) ou une erreur LaTeX (rattachée au transparent) est
  affichée dans le panneau avec un extrait du source, et soulignée en rouge dans l'éditeur
  (onglet *Problèmes*). Les options inconnues donnent un avertissement jaune.
- Commande : *Slide Preview : ouvrir l'aperçu à côté* (raccourci `Cmd+K V` dans un fichier YAML,
  ou l'icône dans la barre de l'éditeur).

## Installation (sans marketplace, sans compilation)

VS Code fermé, depuis ce dossier :

```bash
python3 installer.py                 # lien dans ~/.vscode/extensions + inscription dans extensions.json
python3 installer.py --desinstaller
```

puis relancer VS Code. Le lien pointe vers ce dossier : une modification du plugin est prise en compte
au prochain *Developer: Reload Window*. Un simple lien ne suffit plus : sans inscription dans
`extensions.json`, VS Code marque l'extension comme obsolète au démarrage et l'ignore.

## Fonctionnement

L'extension repère le cours en remontant depuis le fichier YAML jusqu'au dossier contenant
`deck.yaml`, écrit le contenu du buffer dans `build/preview/current.yaml` et lance, depuis ce dossier,
`python3 <deckgen>/build.py --slide build/preview/current.yaml:LIGNE [--lang ..] [--audience ..]`.
Le `build.py` utilisé est celui du dépôt deckgen qui contient l'extension (réglage `slidePreview.buildScript`
pour en désigner un autre).
Elle lit la ligne `PREVIEW_JSON` imprimée par `build.py` et affiche `build/preview/slide-N.png`.

Réglages : `slidePreview.buildScript`, `slidePreview.python`, `slidePreview.cursorDelay`, `slidePreview.typingDelay`,
`slidePreview.renderOnType`.
