# deckgen : des diaporamas Beamer écrits en YAML

Les transparents sont décrits dans des fichiers YAML lisibles ; un petit script Python
(`build.py`, sans autre dépendance que PyYAML et pdflatex) les transforme en Beamer puis en PDF.
La langue (français / anglais) et l'audience sont choisies au moment de la génération : un seul
source pour la version française, la version anglaise, la version grand public, etc.

Dépendances : Python 3 avec PyYAML, TeX Live (pdflatex, beamer, TikZ, polices Fira), et pour
l'aperçu d'un transparent ImageMagick (`magick`). matplotlib seulement pour les figures produites par script.

## Organisation : le générateur d'un côté, le cours de l'autre

Ce dépôt contient seulement le générateur. Un cours est un dossier à part (son propre dépôt) :

```
deckgen/                  ce dépôt                   mon-cours/              le contenu
  build.py                le générateur                deck.yaml             un deck (ou plusieurs deck-*.yaml)
  questions.py            banque de questions          slides/*.yaml         les transparents
  preamble.tex            thème par défaut             figures/              images, figures/tikz/, figures/gen/
  templates/              gabarits par défaut          scripts/              scripts de figures
  scripts/slidefig.py     aide pour les figures        references.yaml       bibliographie (optionnel)
  vscode-slide-preview/   plugin d'aperçu              build/                fichiers générés (jetable)
  exemple/                un petit cours complet
```

On lance `build.py` **depuis le dossier du cours** : tous les chemins du contenu sont relatifs au
dossier du deck. `preamble.tex` et `templates/<nom>.*` sont cherchés d'abord dans le cours (pour
changer de thème ou ajouter des gabarits), puis dans deckgen. Dans la suite, `deck` désigne :

```bash
alias deck="python3 /chemin/vers/deckgen/build.py"
```

Pour essayer : `cd exemple && python3 ../build.py` produit `exemple-fr.pdf`.

```bash
deck                              # deck.yaml, français, toutes audiences -> <nom>-fr.pdf
deck --deck deck-autre.yaml       # un autre deck du même dossier
deck --lang en                    # <nom>-en.pdf (repli sur le français si non traduit)
deck --audience public            # <nom>-fr-public.pdf
deck --lang en --audience experts --out cours-experts-en
deck --no-pdf                     # écrit seulement build/<nom>.tex
```

## Aperçu d'un seul transparent (VS Code)

```bash
deck --slide slides/bases.yaml:20             # le transparent qui contient la ligne 20
deck --slide slides/bases.yaml:20 --lang en --audience public
deck --make-format                            # re-précompiler le préambule (après modification de preamble.tex)
```

Produit `build/preview/slide.pdf` (toutes les couches) et `build/preview/slide.png` (transparent
complet ; `slide-0.png`, `slide-1.png`, ... pour chaque couche). Le préambule est précompilé une
fois par langue (`build/preview/preambule-fr.fmt`) : un aperçu prend environ 0,45 s au total,
dont 0,3 s de pdflatex. Sans précompilation : 1,2 s.

Dans VS Code, ouvrir le dossier du cours : la tâche « Aperçu du transparent » (`.vscode/tasks.json`, à copier depuis
`exemple/.vscode/` en corrigeant le chemin de `build.py`) lance cette commande sur le fichier et la ligne du curseur. Ouvrir une fois `build/preview/slide.png`
dans un panneau à droite (clic droit, *Open to the Side*) : VS Code le rafraîchit à chaque exécution.
Pour un raccourci, ajouter dans `keybindings.json` (Commande : *Preferences: Open Keyboard Shortcuts (JSON)*) :

```json
{ "key": "cmd+k cmd+p", "command": "workbench.action.tasks.runTask",
  "args": "Aperçu du transparent", "when": "editorLangId == yaml" }
```

Le format précompilé est refait automatiquement quand le préambule généré change (`preamble.tex` ou les macros ajoutées par `build.py`, comme `\\refline`) ; `--make-format` reste disponible pour forcer.

**Plugin VS Code** (`vscode-slide-preview/`, installé par lien dans `~/.vscode/extensions`) :
`Cmd+K V` dans un fichier YAML ouvre un panneau à droite qui suit le curseur, compile le buffer
même non sauvegardé, et propose langue, audience et couches. Voir son README.

## Plusieurs decks dans un même cours

Un dossier de cours peut contenir plusieurs decks : un fichier `deck-<nom>.yaml` par deck, avec
`slides_dir: slides/<dossier>` pour ses parties. `deck --deck deck-<nom>.yaml` produit `<nom>-fr.pdf`.
Les figures et `references.yaml` sont partagés.

## Fichiers d'un cours

| Fichier | Rôle |
|---|---|
| `deck.yaml` | métadonnées (titre, auteur, date), langues, audiences, ordre des parties (`parts:`), `slides_dir:`, `preamble:` |
| `slides/*.yaml` | une partie par fichier, liste de transparents |
| `figures/` | images (PDF vectoriel quand c'est possible) ; `figures/tikz/` les schémas TikZ ; `figures/gen/` les figures produites par script |
| `scripts/` | scripts de figures |
| `references.yaml` | bibliographie, pour `cite:` |
| `preamble.tex`, `templates/` | facultatifs : remplacent ou complètent ceux de deckgen |
| `build/` | fichiers `.tex` générés et auxiliaires (jetable) ; `build/preview/` pour l'aperçu |

Le `preamble.tex` de deckgen définit le thème, les couleurs et les macros LaTeX (`\citer`, `\stat`,
`\sectionframe`, `\fullimage`, styles TikZ `boite`, `fleche`, `etiq`).

## Bilinguisme

Toute chaîne peut être soit un texte, soit un couple `{fr: ..., en: ...}`, au plus près du texte :

```yaml
- title: {fr: Petite histoire, en: A short history}
  content:
    - bullets:
        - {fr: Traduction de textes, en: Text translation}
        - fr: Une centaine d'étudiants en science politique, informatique, philosophie...
          en: About a hundred students in political science, computer science, philosophy...
```

Un texte non traduit s'affiche en français dans la version anglaise : on peut traduire
progressivement. Les guillemets « » deviennent `\og \fg` en français et “ ” en anglais.

**Piège YAML** : dans la forme compacte `{fr: ..., en: ...}`, une valeur qui contient une
virgule ou un deux-points doit être entre guillemets (`{fr: "a, b", en: "c, d"}`), sinon
l'item sort vide et `build.py` affiche un avertissement.

## Valeurs variables selon la langue ou l'audience

La forme `{fr: ..., en: ...}` marche pour toute valeur, pas seulement les textes : chemin d'image,
`tex:`, `placeholder:`, `source:`. De même, `{public: ..., default: ...}` choisit selon l'audience
(clés = audiences de `deck.yaml`, plus `default`). Les deux s'imbriquent :

```yaml
- image: {fr: figures/oecd-emplois.png, en: figures/oecd-jobs.png}      # selon la langue
- image: {public: figures/schema-simple.png, default: figures/schema.png}  # selon l'audience
- image:                                                                # les deux
    fr: {public: figures/a-simple.png, default: figures/a.png}
    en: figures/a-en.png
```

Repli : langue absente → français ; audience absente → `default`, sinon la première valeur.
Pour remplacer un bloc entier plutôt qu'une valeur, utiliser `only:` / `except:` (ci-dessous).

## Masquer rapidement : `hide: true`

Pour bricoler un jeu de transparents sans rien supprimer, `hide: true` sur un transparent, un bloc,
une colonne ou un item de liste le retire de la génération. `deck --show-hidden` réintègre
tout. Dans l'aperçu VS Code, un transparent `hide: true` reste affiché (on l'édite) avec la mention
« MASQUÉ » ; un bloc masqué disparaît comme dans le PDF.

```yaml
- title: Ancienne version du schéma
  hide: true              # gardé dans le fichier, absent du PDF
- title: Exemples
  content:
    - bullets:
        - Reconnaissance de parole
        - {text: Preuves automatiques, hide: true}
```

Les commentaires YAML (`# ...`) servent aux notes pour soi ; ils ne passent jamais dans le `.tex`.

## Gabarits : `template:`

Un transparent récurrent se décrit une fois dans `templates/<nom>.tex` (une frame complète) ou
`templates/<nom>.yaml` (un squelette de transparent), avec des paramètres `@@nom|défaut@@`.
Dans les slides, il suffit ensuite d'une ligne :

```yaml
- template: cahier                                              # tout par défaut
- {template: cahier, title: "Exercice 2 : à vous", style: lignes, pas: 8mm}
- {template: cahier, title: Brouillon, style: points, couleur: "bleugris!35"}
```

Toute clé autre que `template`, `only`, `except`, `hide`, `meta`, `notes` est un paramètre ; un
paramètre sans valeur par défaut dans le gabarit et absent de l'appel donne une erreur localisée.
Dans un gabarit `.tex`, les paramètres passent par le mini-markdown ; dans un gabarit `.yaml`, ils
sont insérés tels quels puis rendus normalement (blocs, colonnes, langue, audience).

Gabarits fournis :
- `cahier` : transparent vide quadrillé pour prendre des notes à la main (`style:` grille, lignes ou
  points ; `pas:` ; `couleur:`).
- `nuggets` : QCM à quatre réponses sur fond noir (`question`, `a`, `b`, `c`, `d`, `reponse`).
- `seloupoivre` : « IA ou Y'a pas (ou les deux) ? » (`question`, `reponse`).
  Pour les deux quiz, `reponse:` contient les lettres correctes (`C`, `AB`, ...) : elles passent en
  vert à la deuxième couche ; vide = pas de révélation. Les polices décoratives d'origine
  (Horseshoes and Lemonade, Dimbo) demanderaient XeLaTeX : ici Fira, avec les couleurs d'origine.

## Métadonnées pour soi : `meta:`

`meta:` (ou son synonyme `hidden:`) accueille sur chaque transparent des informations libres qui ne
sont jamais rendues : résumé en une ligne, mots-clés, idées pour une version étudiants, etc.

```yaml
- title: Les bouleversements de l'I.A.
  meta:
    summary: L'IA est partout dans le quotidien, liste d'usages
    keywords: [usages, quotidien]
    students: Demander aux étudiants trois usages qu'ils ont eus cette semaine
```

`deck --export plan.md` (ou `.json`, `.yaml`, ou `-` pour l'écran) sort la liste de tous
les transparents avec numéro, fichier et ligne, titre, filtres (`hide`, `only`, `except`) et le
contenu de `meta:`. Le JSON ou le YAML sert de base à un autre script, par exemple pour générer un
polycopié ou un deck étudiants à partir des résumés.

## Anecdotes et digressions

Une anecdote courte va en `notes:` du transparent concerné (notes du présentateur). Quand il y en a trop, ou qu'elle
mérite d'être projetée à l'occasion, elle devient un transparent `hide: true` placé juste après, titré « Anecdote : … »,
avec `meta: {anecdote: true}` et sa référence `cite:`. Elle n'est jamais dans le PDF par défaut ; `--show-hidden` les
réintègre toutes, ou on retire `hide` sur celle qu'on veut.

## Références bibliographiques : `references.yaml` et `cite:`

Toutes les références vivent dans `references.yaml` (une clé par entrée : `auteurs`, `titre`, `livre: true` pour un
ouvrage, `edition` ou `ou`, `annee`, `url`, `court` pour la forme courte, `verifie:` date de contrôle). Sur un transparent :

```yaml
- title: La d-séparation
  cite: [{pearl1988: "§3.3"}, verma-pearl-1988]     # -> ligne grise en bas : « Pearl 1988, §3.3 · Verma & Pearl 1988 »
```

Une clé inconnue arrête la génération avec le fichier et la ligne. `bibliographie: true` dans le deck ajoute en fin de
cours les transparents « Références » (entrées citées seulement, triées par auteur, cinq par page).
`deck --deck deck-bayes.yaml --refs` liste les clés citées et celles de `references.yaml` jamais citées.
Le bloc `source:` reste réservé aux images et aux données (« Source : … » sous le bloc).

## Questions attachées aux transparents (QCM, examens)

Chaque transparent peut porter des questions, collectées ensuite par `questions.py` (PyYAML seul) pour
tirer au sort un sujet. Deux emplacements, pour ne pas encombrer les slides :

```yaml
# 1. dans le transparent, pour une question courte
- title: Représenter le monde... sans ambiguïté
  meta:
    questions:
      - {ouverte: "Pourquoi Java ne suffit-il pas à décrire le monde ?", attendu: "...", niveau: 2}

# 2. dans un fichier à côté, slides/rc/03-systemes-experts.questions.yaml, dès qu'il y en a plus
- slide: horn                    # le label: du transparent (stable), ou son titre français exact
  questions:
    - qcm: "Pourquoi se restreindre aux formules de Horn ?"
      choix: ["*La déduction est linéaire", "Elles expriment la disjonction", "..."]   # * = bonne(s) réponse(s)
      niveau: 1                  # 1 cours, 2 application, 3 réflexion (optionnel)
      tags: [horn, complexite]   # optionnel ; points: aussi
```

`label: horn` sur un transparent lui donne un identifiant qui survit aux changements de titre. Les textes
peuvent être bilingues `{fr: ..., en: ...}`. Rien de tout cela ne passe dans le PDF.

```bash
python3 /chemin/vers/deckgen/questions.py --deck deck-rc-logique.yaml                        # inventaire par partie
python3 /chemin/vers/deckgen/questions.py --deck deck-rc-logique.yaml --qcm 10 --ouvertes 3 --seed 2027 --out exam-rc
        # -> exam-rc-sujet.md et exam-rc-corrige.md ; options : --tags horn,owl --parts 01,03 --niveau-max 2 --lang en
```

La graine (`--seed`) rend un tirage reproductible ; l'ordre des choix d'un QCM est tiré au sort lui aussi, et le
corrigé rappelle le transparent d'origine de chaque question.

## Audiences

`only:` et `except:` s'appliquent à un transparent, à un bloc, à une colonne ou à un item de liste.
Sans `only`/`except`, l'élément est toujours présent. Les noms d'audience acceptés sont listés
dans `deck.yaml` (`audiences:`).

```yaml
- title: Lois d'échelle et émergence
  only: [experts]             # absent de la version grand public
- title: Convention citoyenne
  except: [public]
```

## Structure d'un transparent

```yaml
- title: ...              # titre (sinon frame sans titre, ou plain: true)
  subtitle: ...           # ligne grise sous le titre
  notes: ...              # notes du présentateur
  background: black       # couleur de fond de la page (optionnel)
  shrink: 15              # dépannage seulement : réduit le contenu d'au plus 15 %. Règle du projet : texte à taille
                          # unique, on coupe un transparent trop chargé en deux plutôt que de réduire
  only: [...] / except: [...]
  content:                # liste de blocs empilés verticalement
    - ...
```

Formes courtes :

```yaml
- section: Apprendre                 # page de section
  subtitle: (programmer l'intuition)
- image: figures/roi-ia.jpg          # image plein écran
  full: true
- title: Quels métiers impactés ?    # une seule image avec source
  image: figures/oecd-emplois.png
  height: 0.7
  source: "[OCDE (2024)](https://...)"
- tex: |                             # transparent entièrement en LaTeX
    \begin{frame}...\end{frame}
```

## Figures produites par un script

```yaml
- figure: scripts/exemple_sigmoide.py     # le script produit l'image
  args: {seuil: 22}                       # options libres passées en --seuil 22
  height: 0.62
  source: courbe jouet
```

`build.py` appelle `script OUT --lang fr --audience experts --seuil 22` et insère le fichier `OUT`
comme une image (mêmes options que `image:`). La sortie va dans `figures/gen/<script>-<lang>[-<audience>][-<hash des args>].pdf`
et n'est régénérée que si le script (ou un fichier de `deps: [...]`) est plus récent, ou avec
`deck --regen`. `format: png` pour une image matricielle. Un script qui échoue donne
une erreur localisée sur le bloc, avec sa sortie d'erreur.

Le script reçoit toujours `--lang` et `--audience` : il peut traduire ses légendes et alléger la
figure pour le grand public. Les valeurs de `args:` peuvent aussi être `{fr: ..., en: ...}` ou
`{public: ..., default: ...}` : elles sont résolues avant l'appel, ce qui permet de garder les
traductions dans le YAML (`args: {titre: {fr: Émergence, en: Emergence}}` donne `--titre Emergence`
en anglais). `scripts/slidefig.py` (dans deckgen, mis dans le `PYTHONPATH` du script par `build.py` : `from slidefig import ...`) fournit `figure_args()`, `setup()` (palette et police
Fira du diaporama pour matplotlib), `T(lang, fr=..., en=...)` et `save()`. Voir
`exemple/scripts/exemple_sigmoide.py`. Les scripts peuvent être en Python ou tout exécutable.

## Fichiers TikZ externes

```yaml
- tikz: figures/tikz/syntaxe-semantique.tikz
  width: 0.85            # redimensionné à 85 % de la largeur (height: fraction de la page)
```

Le fichier contient un `tikzpicture` complet et profite des styles du préambule (`boite`, `fleche`,
`etiq`, couleurs). Deux macros permettent à un seul fichier de suivre la génération :
`\T{texte français}{english text}` choisit selon la langue, `\ifaud{public}{si public}{sinon}`
selon l'audience. Un script (`figure:` avec `format: tex`) peut aussi produire un tel fichier.

Aperçu d'un fichier TikZ : `deck --tikz figures/tikz/x.tikz [--buffer tmp]` compile le
transparent qui l'utilise (le premier trouvé dans `slides/`), ou le dessin seul s'il n'est référencé
nulle part ; `--buffer` remplace le fichier par une copie non sauvegardée (plugin VS Code). Une erreur
LaTeX dans le fichier est rapportée avec sa ligne (`tex_line`).

## Blocs

| Bloc | Exemple |
|---|---|
| texte | `- text: "Un paragraphe"` (+ `align: center`, `style: small gris`) |
| liste | `- bullets: [a, b, {text: c, sub: [d, e]}]` (+ `size: small`) ; `numbered:` pour une énumération |
| image | `- image: figures/x.png` (+ `width: 0.8` fraction de la colonne, `height: 0.6` fraction de la page, `source:`, `align: left`) |
| figure par script | `- figure: scripts/x.py` (+ `args: {...}`, `deps: [...]`, `format: png` ou `tex`, et les options de `image`) |
| TikZ externe | `- tikz: figures/tikz/x.tikz` (+ `width`, `height`, `source`) ; macros `\T{fr}{en}` et `\ifaud{public}{..}{..}` dans le fichier |
| rangée d'images | `- images: [{file: a.png, height: 0.4}, {file: b.png, height: 0.4}]` (+ `gap: 10pt`) |
| alerte | `- alert: "Texte en évidence"` (+ `title:`, `align: left`, `bold: false`) |
| bloc titré | `- block: {title: Dangers, content: [...]}` ou `{title: ..., text: ...}` |
| citation | `- quote: {text: ..., author: ..., reveal: 2}` (l'auteur apparaît à la couche 2) |
| grands chiffres | `- stats: [{value: "99 %", text: des étudiants...}, ...]` |
| colonnes | `- layout: texte-image` puis `columns: [{content: [...]}, {content: [...]}]` (+ `valign: c`) ; dispositions nommées : `egal` (48/48), `texte-image` (60/36), `image-texte` (36/60), définies dans `LAYOUTS` de `build.py`. `width:` par colonne reste possible mais à éviter : peu de dispositions = style constant |
| LaTeX brut | `- tex: \|` puis le code (TikZ, tableaux, ...) ; peut être bilingue `tex: {fr: ..., en: ...}` |
| espace | `- space: 8pt` |
| source | `- source: "Wikipédia"` |
| figure EMF manquante | `- placeholder: image95.emf` (+ `width`, `height`) |

Tout bloc accepte `step: N` (apparaît à partir de la couche N), `only:`, `except:` et `hide: true`.

## Mini-markdown dans les textes

`**gras**`, `*italique*`, `` `code` ``, `[texte](url)`, `« guillemets »`, `...` → points de suspension,
`{{small:...}}`, `{{gris:...}}`, `{{bleugris:...}}`, `{{footnotesize:...}}`, `{{it:...}}` (imbricables).
Un saut de ligne = retour à la ligne, une ligne vide = nouveau paragraphe.
Les caractères `& % # _ $` sont échappés automatiquement ; `$x^2$` reste une formule.
Pour du LaTeX brut, utiliser un bloc `tex:`.

## Erreurs

`build.py` vérifie la structure avant de compiler : clé de transparent inconnue, bloc sans type
reconnu, item de liste mal formé (typiquement une virgule non protégée dans un `{fr: ..., en: ...}`),
colonne sans `content`. Chaque erreur indique le fichier et la ligne du nœud fautif ; une option
inconnue dans un bloc donne un avertissement. Avec `--slide`, l'erreur est aussi émise sous forme
`PREVIEW_JSON {"error": ..., "kind": "yaml|structure|latex", "line": ...}` pour le plugin VS Code.
