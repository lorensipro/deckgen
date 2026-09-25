#!/usr/bin/env python3
"""Génère un diaporama Beamer à partir de fichiers YAML.

Usage, depuis le dossier du cours (celui du deck) :
    python3 /chemin/deckgen/build.py                      # deck.yaml, français -> <nom>-fr.pdf
    python3 /chemin/deckgen/build.py --deck deck-x.yaml   # un autre deck du même dossier
    python3 build.py --lang en            # anglais (repli sur le français si non traduit)
    python3 build.py --audience public    # ne garde que les transparents/blocs visibles pour « public »
    python3 build.py --lang en --audience experts --out cours-experts-en
    python3 build.py --no-pdf             # écrit seulement build/<nom>.tex
    python3 build.py --slide slides/01-contexte.yaml:42   # aperçu du transparent sous la ligne 42
                                          #   -> build/preview/slide.pdf et slide.png

Les chemins du contenu (slides/, figures/, scripts/, references.yaml, build/) sont relatifs au
dossier du deck. Les gabarits et le préambule sont cherchés d'abord dans ce dossier, puis à côté
de build.py. Le format des fichiers YAML est décrit dans README.md.
Dépendances : python3, PyYAML, pdflatex (TeX Live).
"""
import argparse, os, re, shutil, subprocess, sys
import yaml

ENGINE = os.path.dirname(os.path.abspath(__file__))   # le générateur : build.py, preamble.tex, templates/, scripts/slidefig.py
PROJECT = os.getcwd()                                  # le cours : dossier du deck, fixé dans main()

def find_file(rel):
    """Fichier du cours s'il existe, sinon celui fourni avec le générateur."""
    p = os.path.join(PROJECT, rel)
    return p if os.path.exists(p) else os.path.join(ENGINE, rel)

LANGS = ("fr", "en")
BABEL = {"fr": "french", "en": "english"}

# ------------------------------------------------------------------ utilitaires

LINES = {}   # id(dict ou list) -> numéro de ligne (1-based) dans le YAML source

class LineLoader(yaml.SafeLoader):
    """SafeLoader qui mémorise la ligne de chaque mapping et de chaque liste (pour les messages d'erreur)."""
    def construct_yaml_map(self, node):
        data = {}; LINES[id(data)] = node.start_mark.line + 1
        yield data
        data.update(self.construct_mapping(node))
    def construct_yaml_seq(self, node):
        data = []; LINES[id(data)] = node.start_mark.line + 1
        yield data
        data.extend(self.construct_sequence(node))
LineLoader.add_constructor("tag:yaml.org,2002:map", LineLoader.construct_yaml_map)
LineLoader.add_constructor("tag:yaml.org,2002:seq", LineLoader.construct_yaml_seq)

def load_yaml(path):
    with open(path, encoding="utf8") as f:
        return yaml.load(f, Loader=LineLoader) or []

def line_of(node):
    return LINES.get(id(node))

class SlideError(Exception):
    """Erreur de structure dans un transparent, avec la ligne du nœud fautif."""
    def __init__(self, msg, node=None, line=None):
        super().__init__(msg); self.line = line if line is not None else line_of(node)

WARNINGS = []   # [(ligne, message)] accumulés pendant le rendu

def warn(msg, node=None):
    WARNINGS.append((line_of(node), msg))

SLIDE_KEYS = {"cite", "shrink", "title", "subtitle", "notes", "content", "only", "except", "hide", "meta", "hidden", "plain", "section", "background", "template",
              "image", "figure", "tikz", "args", "full", "height", "width", "source", "tex", "label"}
BLOCK_MAIN = {"text", "bullets", "numbered", "image", "figure", "tikz", "images", "alert", "block", "quote", "stats",
              "columns", "tex", "space", "placeholder"}   # + "source" seul = bloc source
BLOCK_OPTS = {"layout", "step", "only", "except", "hide", "meta", "hidden", "width", "height", "source", "align", "size", "style",
              "title", "bold", "gap", "valign", "reveal", "args", "deps", "format"}
# Dispositions de colonnes nommées (- layout: texte-image puis columns: [...]) : largeurs en fraction de \\textwidth.
LAYOUTS = {"egal": [0.48, 0.48], "texte-image": [0.6, 0.36], "image-texte": [0.36, 0.6]}
REGEN = False   # --regen : forcer la régénération des figures produites par script
OVERRIDE = {}   # --tikz/--buffer : chemin d'un fichier tikz -> fichier temporaire contenant le buffer de l'éditeur

class Ctx:
    def __init__(self, lang, audience, audiences=()):
        self.lang, self.audience, self.audiences = lang, audience, set(audiences)

def is_lang_dict(v):
    return isinstance(v, dict) and v and all(k in LANGS for k in v)

def is_aud_dict(v, ctx):
    """{public: ..., default: ...} : clés = audiences déclarées dans deck.yaml (+ default)."""
    return isinstance(v, dict) and v and ctx.audiences and all(k in ctx.audiences or k == "default" for k in v)

def L(v, ctx):
    """Résout une valeur variable : 'x', {fr: ..., en: ...} (repli : fr, puis 1re valeur),
    {public: ..., default: ...} (repli : default, puis 1re valeur). Les deux formes s'imbriquent."""
    for _ in range(4):
        if is_lang_dict(v):
            v = v.get(ctx.lang) or v.get("fr") or next(iter(v.values()))
        elif is_aud_dict(v, ctx):
            v = v.get(ctx.audience) if ctx.audience in v else v.get("default", next(iter(v.values())))
        else:
            return v
    return v

SHOW_HIDDEN = False   # --show-hidden : ignorer les hide: true

def visible(node, ctx):
    """Filtre : hide: true (sauf --show-hidden), puis audience only: [..] / except: [..],
    sur un transparent, un bloc, une colonne ou un item."""
    if not isinstance(node, dict):
        return True
    if node.get("hide") and not SHOW_HIDDEN:
        return False
    if ctx.audience is None:
        return True
    only, exc = node.get("only"), node.get("except")
    if only and ctx.audience not in only:
        return False
    if exc and ctx.audience in exc:
        return False
    return True

_ESC = {"&": r"\&", "%": r"\%", "#": r"\#", "_": r"\_", "$": r"\$", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}

def esc(s):
    """Échappe les caractères spéciaux hors des maths $...$."""
    out = []
    for i, part in enumerate(re.split(r"(\$(?!\s)[^$\n]*?(?<!\s)\$)", s)):
        if i % 2 == 1:
            out.append(part)
        else:
            out.append("".join(_ESC.get(c, c) for c in part))
    return "".join(out)

_FONTS = {"gris": r"\color{gris}", "bleugris": r"\color{bleugris}", "encre": r"\color{encre}",
          "small": r"\small", "footnotesize": r"\footnotesize", "tiny": r"\tiny",
          "large": r"\large", "Large": r"\Large", "it": r"\itshape"}

def fonts(s):
    """{{nom:texte}} -> {\\cmd texte}, avec imbrication possible."""
    while True:
        m = re.search(r"\{\{(\w+):", s)
        if not m:
            return s
        depth, i = 1, m.end()
        while i < len(s) and depth:
            if s.startswith("{{", i):   depth += 1; i += 2
            elif s.startswith("}}", i): depth -= 1; i += 2
            else: i += 1
        inner = s[m.end():i - 2]
        s = s[:m.start()] + "{" + _FONTS.get(m.group(1), "") + " " + fonts(inner) + "}" + s[i:]

def md(s, ctx=None, par=True):
    """Markdown minimal -> LaTeX : **gras**, *italique*, `code`, [texte](url), « », ..., {{gris:texte}}.
    Un saut de ligne simple -> \\\\, une ligne vide -> nouveau paragraphe."""
    if s is None:
        return ""
    s = L(s, ctx) if ctx else s
    if isinstance(s, (dict, list)):
        raise SlideError(f"texte mal formé {s} : un {{fr: ..., en: ...}} avec une virgule ou un deux-points "
                         "non protégé ? Mettre la valeur entre guillemets.", s)
    s = str(s).strip("\n")
    # protéger les liens avant échappement
    links = []
    def keep_link(m):
        links.append((m.group(1), m.group(2))); return f"\x00{len(links)-1}\x00"
    s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", keep_link, s)
    s = esc(s)
    s = fonts(s)
    s = re.sub(r"\*\*(.+?)\*\*", r"\\textbf{\1}", s)
    s = re.sub(r"(?<![\w\\])\*(?!\s)(.+?)(?<!\s)\*(?!\w)", r"\\emph{\1}", s)
    s = re.sub(r"`([^`]+)`", r"\\texttt{\1}", s)
    if ctx and ctx.lang == "en":
        s = re.sub(r"«\s*(.+?)\s*»", r"``\1''", s)
    else:
        s = re.sub(r"«\s*(.+?)\s*»", r"\\og \1\\fg{}", s)
    s = s.replace("…", r"\ldots{}").replace("...", r"\ldots{}")
    s = re.sub(r"\x00(\d+)\x00", lambda m: r"\href{%s}{%s}" % (links[int(m.group(1))][1].replace("%", r"\%").replace("#", r"\#"), esc(links[int(m.group(1))][0])), s)
    paras = [p.strip() for p in re.split(r"\n\s*\n", s)]
    sep = "\n\n" if par else r"\\[3pt] "
    return sep.join(p.replace("\n", r"\\ ") for p in paras)

def frac(v, unit):
    """0.3 -> 0.3\\textwidth ; '4cm' -> 4cm"""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return f"{v}{unit}"
    return str(v)

# ------------------------------------------------------------------ figures produites par un script

def generated_figure(b, ctx):
    """Bloc figure: chemin d'un script (Python ou autre exécutable) qui produit une image.
    Le script est appelé ainsi :  script OUT --lang fr --audience experts [--cle valeur ...]
    et doit écrire le fichier OUT (PDF par défaut, ou `format: png`). Il n'est relancé que si OUT
    manque ou est plus vieux que le script, ses `deps:` ou ses `args:` (ou avec --regen)."""
    import hashlib, json, stat
    script = L(b["figure"], ctx)
    script_path = os.path.join(PROJECT, script)
    if not os.path.exists(script_path):
        raise SlideError(f"script introuvable : {script}", b)
    args = L(b.get("args") or {}, ctx)
    if not isinstance(args, dict):
        raise SlideError("'args' doit être un mapping {clé: valeur}", b)
    args = {k: L(v, ctx) for k, v in args.items()}   # chaque valeur peut être {fr: .., en: ..} ou {public: .., default: ..}
    fmt = b.get("format", "pdf")
    key = f"{ctx.lang}" + (f"-{ctx.audience}" if ctx.audience else "")
    if args:
        key += "-" + hashlib.sha1(json.dumps(args, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:8]
    stem = os.path.splitext(os.path.basename(script))[0]
    out_dir = os.path.join(PROJECT, "figures", "gen"); os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, f"{stem}-{key}.{fmt}")
    deps = [script_path] + [os.path.join(PROJECT, d) for d in (b.get("deps") or [])]
    stale = REGEN or not os.path.exists(out) or any(os.path.getmtime(d) > os.path.getmtime(out) for d in deps if os.path.exists(d))
    if stale:
        cmd = ([script_path] if os.stat(script_path).st_mode & stat.S_IXUSR and not script.endswith(".py")
               else [sys.executable, script_path])
        cmd += [out, "--lang", ctx.lang, "--audience", ctx.audience or ""]
        for k, v in args.items():
            cmd += [f"--{k}", str(v)]
        env = dict(os.environ, PYTHONPATH=os.pathsep.join(filter(None, [os.path.join(ENGINE, "scripts"), os.environ.get("PYTHONPATH")])))
        r = subprocess.run(cmd, cwd=PROJECT, capture_output=True, text=True, errors="replace", env=env)
        if r.returncode != 0 or not os.path.exists(out):
            raise SlideError(f"le script {script} a échoué (code {r.returncode}) :\n{(r.stderr or r.stdout)[-1200:]}", b)
        print(f"figure générée : {os.path.relpath(out, PROJECT)}", file=sys.stderr)
    return os.path.relpath(out, PROJECT)

# ------------------------------------------------------------------ blocs

def render_blocks(blocks, ctx, indent="  "):
    out = []
    for b in blocks or []:
        if isinstance(b, str):
            out.append(indent + md(b, ctx) + r"\par")
            continue
        if not visible(b, ctx):
            continue
        body = render_block(b, ctx, indent)
        if body is None:
            continue
        step = b.get("step")
        if step:
            body = f"{indent}\\onslide<{step}->{{\n{body}\n{indent}}}"
        out.append(body)
    return "\n".join(out)

def items_to_latex(items, ctx, env, indent):
    lines = [f"{indent}\\begin{{{env}}}"]
    for it in items:
        if isinstance(it, dict) and not is_lang_dict(it) and not is_aud_dict(it, ctx):
            if not visible(it, ctx):
                continue
            unknown = set(it) - {"text", "sub", "only", "except", "hide"}
            if "text" not in it or unknown:
                raise SlideError(f"item de liste mal formé {dict(it)} : clés attendues text/sub/only/except. "
                                 "Une virgule ou un deux-points non protégé dans un {fr: ..., en: ...} ? "
                                 "Mettre la valeur entre guillemets.", it)
            txt = md(it.get("text", ""), ctx)
            sub = it.get("sub")
            lines.append(f"{indent}  \\item {txt}")
            if sub:
                lines.append(items_to_latex(sub, ctx, env, indent + "  "))
        else:
            lines.append(f"{indent}  \\item {md(it, ctx)}")
    lines.append(f"{indent}\\end{{{env}}}")
    return "\n".join(lines)

def render_block(b, ctx, indent):
    i = indent
    mains = [k for k in b if k in BLOCK_MAIN]
    if not mains and "source" in b:
        mains = ["source"]
    if len(mains) != 1:
        raise SlideError(f"bloc sans type reconnu {sorted(b)} : il faut exactement une clé parmi "
                         f"{sorted(BLOCK_MAIN)}", b)
    extra = set(b) - BLOCK_MAIN - BLOCK_OPTS
    if extra:
        warn(f"option(s) inconnue(s) {sorted(extra)} dans le bloc '{mains[0]}' (ignorées)", b)
    if "text" in b:
        pre = "".join(_FONTS.get(k, "") for k in (b.get("style") or "").split())
        if pre:
            pre += " "      # sinon « \\small » se colle au premier mot du texte
        txt = md(b["text"], ctx)
        if b.get("align") == "center":
            return f"{i}\\begin{{center}}{pre}{txt}\\end{{center}}"
        return f"{i}{{{pre}{txt}\\par}}"
    if "bullets" in b or "numbered" in b:
        env = "itemize" if "bullets" in b else "enumerate"
        size = _FONTS.get(b.get("size", ""), "")
        body = items_to_latex(b.get("bullets") or b.get("numbered"), ctx, env, i)
        return f"{i}{{{size}\n{body}\n{i}}}" if size else body
    if "figure" in b:
        gen = generated_figure(b, ctx)
        if b.get("format") in ("tex", "tikz"):
            b = dict(b, tikz=gen)
        else:
            b = dict(b, image=gen)
        del b["figure"]
    if "tikz" in b:  # fichier TikZ/LaTeX externe, inséré par \input, redimensionné si width/height
        path = L(b["tikz"], ctx)
        path = OVERRIDE.get(os.path.normpath(path), path)
        if not os.path.exists(os.path.join(PROJECT, path)):
            raise SlideError(f"fichier TikZ introuvable : {path}", b)
        inner = f"\\input{{{path}}}"
        w = frac(b.get("width"), chr(92) + "linewidth"); h = frac(b.get("height"), chr(92) + "textheight")
        if w or h:
            inner = f"\\resizebox{{{w or '!'}}}{{{h or '!'}}}{{{inner}}}"
        src = f"\n{i}\\source{{{md(b['source'], ctx)}}}" if b.get("source") else ""
        if b.get("align", "center") == "center":
            return f"{i}\\begin{{center}}\n{i}{inner}{src}\n{i}\\end{{center}}"
        return f"{i}{inner}{src}"
    if "image" in b:
        opts = []
        if b.get("width") is not None:  opts.append(f"width={frac(b['width'], chr(92)+'linewidth')}")
        if b.get("height") is not None: opts.append(f"height={frac(b['height'], chr(92)+'textheight')}")
        if not opts: opts.append(r"width=\linewidth")
        if b.get("width") is not None and b.get("height") is not None: opts.append("keepaspectratio")
        s = f"{i}\\includegraphics[{','.join(opts)}]{{{L(b['image'], ctx)}}}"
        if b.get("align", "center") == "center":
            s = f"{i}\\begin{{center}}\n{s}\n" + (f"{i}\\source{{{md(b['source'], ctx)}}}\n" if b.get("source") else "") + f"{i}\\end{{center}}"
        elif b.get("source"):
            s += f"\n{i}\\source{{{md(b['source'], ctx)}}}"
        return s
    if "images" in b:  # rangée d'images
        gap = b.get("gap", "10pt")
        parts = []
        for im in b["images"]:
            if isinstance(im, str): im = {"file": im}
            opts = []
            if im.get("height") is not None: opts.append(f"height={frac(im['height'], chr(92)+'textheight')}")
            if im.get("width") is not None:  opts.append(f"width={frac(im['width'], chr(92)+'linewidth')}")
            parts.append(f"\\includegraphics[{','.join(opts) or 'height=0.6'+chr(92)+'textheight'}]{{{L(im['file'], ctx)}}}")
        return f"{i}\\begin{{center}}\n{i}  " + f"\\hspace{{{gap}}}".join(parts) + f"\n{i}\\end{{center}}"
    if "alert" in b:
        title = md(b.get("title", ""), ctx)
        txt = md(b["alert"], ctx)
        centered = r"\centering " if b.get("align", "center") == "center" else ""
        bold = r"\bfseries " if b.get("bold", True) else ""
        return f"{i}\\begin{{alertblock}}{{{title}}}\n{i}  {centered}{bold}{txt}\n{i}\\end{{alertblock}}"
    if "block" in b:
        blk = b["block"]
        title = md(blk.get("title", ""), ctx)
        inner = render_blocks(blk.get("content"), ctx, i + "  ") if blk.get("content") else i + "  " + md(blk.get("text", ""), ctx)
        return f"{i}\\begin{{block}}{{{title}}}\n{inner}\n{i}\\end{{block}}"
    if "quote" in b:
        q = b["quote"]
        return f"{i}\\citer{{{md(q.get('text',''), ctx)}}}{{{md(q.get('author',''), ctx)}}}{{{q.get('reveal', 1)}}}"
    if "stats" in b:
        return "\n".join(f"{i}\\stat{{{md(s['value'], ctx)}}}{{{md(s['text'], ctx)}}}" for s in b["stats"] if visible(s, ctx))
    if "columns" in b:
        valign = b.get("valign", "T")
        cols = [f"{i}\\begin{{columns}}[{valign}]"]
        layout = None
        if b.get("layout"):     # dispositions nommées : peu de variantes, pour un style constant sur tout le deck
            if b["layout"] not in LAYOUTS:
                raise SlideError(f"layout inconnu '{b['layout']}' : attendu {sorted(LAYOUTS)}", b)
            layout = LAYOUTS[b["layout"]]
            if len(layout) != len(b["columns"]):
                raise SlideError(f"layout '{b['layout']}' : {len(layout)} colonnes attendues, {len(b['columns'])} trouvées", b)
        for n, c in enumerate(b["columns"]):
            if layout:
                c = dict(c, width=layout[n])
            if not isinstance(c, dict) or "content" not in c:
                raise SlideError("chaque colonne doit être un mapping avec 'content' (et 'width' optionnel)", c if isinstance(c, (dict, list)) else b)
            if not visible(c, ctx): continue
            w = frac(c.get("width", round(1.0 / len(b["columns"]) - 0.02, 2)), r"\textwidth")
            cols.append(f"{i}  \\begin{{column}}{{{w}}}\n{render_blocks(c.get('content'), ctx, i + '    ')}\n{i}  \\end{{column}}")
        cols.append(f"{i}\\end{{columns}}")
        return "\n".join(cols)
    if "tex" in b:
        return "\n".join(i + l for l in L(b["tex"], ctx).rstrip("\n").splitlines())
    if "space" in b:
        return f"{i}\\vspace{{{b['space']}}}"
    if "source" in b:
        return f"{i}\\source{{{md(b['source'], ctx)}}}"
    if "placeholder" in b:  # figure EMF non convertie
        return f"{i}\\emfplaceholder{{{L(b['placeholder'], ctx)}}}{{{frac(b.get('width', 0.6), chr(92)+'textwidth')}}}{{{frac(b.get('height', '3cm'), '')}}}"
    raise SlideError(f"bloc inconnu {sorted(b)}", b)

# ------------------------------------------------------------------ gabarits (templates/<nom>.tex ou .yaml)

TEMPLATE_RESERVED = {"template", "only", "except", "hide", "meta", "hidden", "notes"}

def substitute(text, params, ctx, tex=True):
    """Remplace @@nom|défaut@@ par le paramètre (mini-markdown appliqué si tex=True)."""
    def rep(m):
        key, default = m.group(1), m.group(2)
        if key in params:
            v = L(params[key], ctx)
            return md(v, ctx) if tex and isinstance(v, str) else str(v)
        if default is None:
            raise SlideError(f"paramètre '{key}' manquant pour le gabarit (pas de valeur par défaut)")
        return default
    return re.sub(r"@@(\w+)(?:\|([^@]*))?@@", rep, text)

def expand_template(s, ctx):
    """- template: nom, autres clés = paramètres. Renvoie ('tex', code) ou ('slide', mapping)."""
    name = L(s["template"], ctx)
    params = {k: v for k, v in s.items() if k not in TEMPLATE_RESERVED}
    tex, yml = find_file(os.path.join("templates", name + ".tex")), find_file(os.path.join("templates", name + ".yaml"))
    if os.path.exists(tex):
        with open(tex, encoding="utf8") as f:
            code = f.read()
        # cas particulier du gabarit cahier : le style est aussi une macro LaTeX
        code = "\\def\\cahierstyle{" + str(L(params.get("style", "grille"), ctx)) + "}\n" + code
        return "tex", substitute(code, params, ctx, tex=True)
    if os.path.exists(yml):
        skel = load_yaml(yml)
        def walk(v):
            if isinstance(v, str): return substitute(v, params, ctx, tex=False)
            if isinstance(v, list): return [walk(x) for x in v]
            if isinstance(v, dict):
                d = {k: walk(x) for k, x in v.items()}; LINES[id(d)] = line_of(s); return d
            return v
        slide = walk(skel)
        for k in TEMPLATE_RESERVED - {"template"}:
            if k in s: slide[k] = s[k]
        LINES[id(slide)] = line_of(s)
        return "slide", slide
    raise SlideError(f"gabarit introuvable : templates/{name}.tex ou .yaml", s)

# ------------------------------------------------------------------ transparents

# ------------------------------------------------------------------ références (references.yaml + cite: sur un transparent)

REFS = None          # contenu de references.yaml, chargé à la demande
CITED = []           # clés citées pendant la construction courante, dans l'ordre

def refs():
    global REFS
    if REFS is None:
        path = os.path.join(PROJECT, "references.yaml")
        REFS = load_yaml(path) if os.path.exists(path) else {}
    return REFS

def ref_short(key, r):
    """Forme courte affichée sur le transparent : champ court:, sinon « Auteurs année »."""
    if r.get("court"): return str(r["court"])
    auteurs = str(r.get("auteurs", key)).split(",")
    noms = [a.strip().split()[-1] for a in auteurs if a.strip()]
    qui = noms[0] if len(noms) == 1 else (" & ".join(noms) if len(noms) == 2 else noms[0] + " et al.")
    return f"{qui} {r.get('annee', '')}".strip()

def ref_full(key, r, ctx):
    """Entrée de bibliographie (mini-markdown) : auteurs, titre, où, année, url."""
    titre = L(r.get("titre", key), ctx)
    parts = [str(r.get("auteurs", "")), f"*{titre}*" if r.get("livre") else f"« {titre} »"]
    for k in ("edition", "ou"):
        if r.get(k): parts.append(str(r[k]))
    if r.get("annee"): parts.append(str(r["annee"]))
    out = ", ".join(x for x in parts if x)
    if r.get("url"): out += f" {{{{gris:{{{{footnotesize:[{r['url']}]({r['url']})}}}}}}}}"
    return out

def render_cite(items, node):
    """cite: [cle, {cle: "§3.3"}, ...] -> ligne grise « Pearl 1988, §3.3 · Verma & Pearl 1988 »."""
    if isinstance(items, (str, dict)): items = [items]
    bits = []
    for it in items:
        key, note = (next(iter(it.items())) if isinstance(it, dict) else (str(it), None))
        r = refs().get(key)
        if r is None:
            raise SlideError(f"cite: clé inconnue « {key} » (absente de references.yaml)", node)
        if key not in CITED: CITED.append(key)
        bits.append(ref_short(key, r) + (f", {note}" if note else ""))
    return "  \\refline{" + esc(" · ".join(bits)) + "}"

def bibliography_frames(ctx, per_frame=4):
    """Transparents de bibliographie pour les clés citées (bibliographie: true dans le deck)."""
    keys = sorted(CITED, key=lambda k: (str(refs()[k].get("auteurs", k)).lower(), str(refs()[k].get("annee", ""))))
    frames, chunk = [], [keys[i:i + per_frame] for i in range(0, len(keys), per_frame)]
    for n, ks in enumerate(chunk, 1):
        titre = ("Références" if ctx.lang == "fr" else "References") + (f" ({n}/{len(chunk)})" if len(chunk) > 1 else "")
        items = "\n".join("      \\item " + md(ref_full(k, refs()[k], ctx), ctx) for k in ks)
        frames.append(f"\\begin{{frame}}{{{titre}}}\n  \\relax\n  \\begin{{itemize}}\n{items}\n  \\end{{itemize}}\n\\end{{frame}}")
    return frames

def render_slide(s, ctx):
    r = _render_slide(s, ctx)
    if r is not None and isinstance(s, dict) and s.get("background"):   # background: black -> fond de page
        r = f"{{\\setbeamercolor{{background canvas}}{{bg={s['background']}}}\n{r}\n}}"
    return r

def _render_slide(s, ctx):
    if isinstance(s, dict) and "template" in s:
        if not visible(s, ctx):
            return None
        kind, x = expand_template(s, ctx)
        if kind == "tex":
            return x
        s = x
    if not isinstance(s, dict):
        raise SlideError(f"un transparent doit être un mapping (title:, content: ...), trouvé {type(s).__name__}", s if isinstance(s, list) else None)
    extra = set(s) - SLIDE_KEYS
    if extra:
        raise SlideError(f"clé(s) inconnue(s) {sorted(extra)} dans le transparent : attendu {sorted(SLIDE_KEYS)}", s)
    if not any(k in s for k in ("title", "content", "section", "image", "tex", "plain")):
        raise SlideError("transparent vide : il faut title, content, section, image ou tex", s)
    if "content" in s and not isinstance(s["content"], list):
        raise SlideError("'content' doit être une liste de blocs (commençant par '- ')", s)
    if not visible(s, ctx):
        return None
    if "section" in s:
        return f"\\sectionframe{{{md(s['section'], ctx)}}}{{{md(s.get('subtitle',''), ctx)}}}"
    if "tex" in s and "content" not in s:
        return L(s["tex"], ctx)
    if "figure" in s:
        s = dict(s, image=generated_figure(dict(figure=s["figure"], args=s.get("args"), deps=s.get("deps"), format=s.get("format", "pdf")), ctx))
    if "tikz" in s and "content" not in s:
        s = dict(s, content=[{"tikz": s["tikz"], "width": s.get("width"), "height": s.get("height"), "source": s.get("source")}])
    if "image" in s and s.get("full"):
        return f"\\fullimage{{{L(s['image'], ctx)}}}" + (f"\n\\note{{{md(s['notes'], ctx)}}}" if s.get("notes") else "")
    opts = "[plain]" if s.get("plain") or not s.get("title") else ""
    title = "" if opts else f"{{{md(s['title'], ctx)}}}"
    if s.get("shrink"):     # shrink: 15 -> réduit le contenu d'au plus 15 % pour qu'il tienne (transparents chargés)
        opts = f"[{'plain,' if opts else ''}shrink={int(s['shrink'])}]"
    lines = [f"\\begin{{frame}}{opts}{title}"]
    if title:
        lines.append("  \\relax")    # sinon le premier groupe « {...} » serait avalé par Beamer comme sous-titre de frame
    if s.get("subtitle"):
        lines.append(f"  {{\\small\\color{{gris}}{md(s['subtitle'], ctx)}\\par}}")
    content = s.get("content")
    if content is None and "image" in s:
        content = [{"image": s["image"], "height": s.get("height", 0.8), "source": s.get("source")}]
        LINES[id(content[0])] = line_of(s)
    lines.append(render_blocks(content, ctx))
    if s.get("cite"):
        lines.append(render_cite(s["cite"], s))
    if s.get("notes"):
        lines.append(f"  \\note{{{md(s['notes'], ctx)}}}")
    lines.append("\\end{frame}")
    return "\n".join(lines)

# ------------------------------------------------------------------ document

def document(deck, ctx, body, titlepage=True):
    """Assemble le document complet : classe, préambule, métadonnées, corps."""
    with open(find_file(deck.get("preamble", "preamble.tex")), encoding="utf8") as f:
        pre = f.read().replace("@@BABEL@@", BABEL[ctx.lang])
    meta = deck.get("meta", {})
    lang_macros = "\n".join([
        "% \\T{français}{english} : texte selon la langue de génération (utilisable dans les fichiers TikZ)",
        "\\newcommand{\\T}[2]{#1}" if ctx.lang == "fr" else "\\newcommand{\\T}[2]{#2}",
        "" if ctx.lang == "fr" else "\\providecommand{\\og}{``}\\providecommand{\\fg}{''}  % guillemets français hors babel-french",
        "\\newcommand{\\ifaud}[3]{\\ifdefstring{\\audience}{#1}{#2}{#3}}  % \\ifaud{public}{si public}{sinon}",
        "\\newcommand{\\refline}[1]{\\vfill{\\tiny\\color{gris}#1\\par}}  % ligne de références (cite:) en bas du transparent",
    ])
    return "\n".join([
        f"% Fichier généré par build.py (lang={ctx.lang}, audience={ctx.audience}) -- ne pas éditer",
        "\\documentclass[aspectratio=169,11pt]{beamer}", lang_macros, pre,
        f"\\title{{{md(meta.get('title',''), ctx, par=False)}}}",
        f"\\subtitle{{{md(meta.get('subtitle',''), ctx, par=False)}}}",
        f"\\author{{{md(meta.get('author',''), ctx, par=False)}}}",
        f"\\date{{{md(meta.get('date',''), ctx, par=False)}}}",
        "\\begin{document}", f"\\def\\audience{{{ctx.audience or ''}}}", "\\maketitle" if titlepage else "",
        *body, "\\end{document}", ""])

def run_pdflatex(tex_path, out_dir, passes=2, fmt=None):
    """Compile depuis le dossier du projet (figures/ relatif). fmt : nom d'un format précompilé dans out_dir."""
    cmd = ["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "-output-directory", out_dir]
    if fmt:
        cmd.insert(1, f"-fmt={fmt}")
    env = dict(os.environ, TEXFORMATS=out_dir + ":", TEXINPUTS=PROJECT + ":" + ENGINE + ":")
    for _ in range(passes):
        r = subprocess.run(cmd + [tex_path], cwd=PROJECT, capture_output=True, text=True, errors="replace", env=env)
    if r.returncode != 0:
        import json
        log = r.stdout
        i = log.find("\n!")
        msg = log[i:i + 1500] if i >= 0 else log[-1500:]
        m = re.search(r"^! (.*)$", msg, re.M)
        short = m.group(1) if m else "erreur pdflatex"
        ml = re.search(r"^l\.(\d+)", msg, re.M)
        print(msg)
        print("PREVIEW_JSON " + json.dumps({"error": f"LaTeX : {short}", "kind": "latex", "detail": msg.strip(),
                                            "tex_line": int(ml.group(1)) if ml else None}, ensure_ascii=False))
        sys.exit("Échec pdflatex")

def build(deck, ctx, out_name, make_pdf=True):
    slides_dir = os.path.join(PROJECT, deck.get("slides_dir", "slides"))
    body = []
    kept = total = 0
    CITED.clear()
    for p in deck["parts"]:
        path = os.path.join(slides_dir, p if p.endswith(".yaml") else p + ".yaml")
        try:
            slides = load_yaml(path)
        except yaml.YAMLError as e:
            sys.exit(f"{os.path.relpath(path, PROJECT)} : erreur YAML\n{e}")
        body.append(f"\n% ==================== {os.path.basename(path)} ====================")
        for s in slides:
            total += 1
            try:
                r = render_slide(s, ctx)
            except SlideError as e:
                sys.exit(f"{os.path.relpath(path, PROJECT)}:{e.line} : {e}")
            if r:
                kept += 1
                body.append(r + "\n")
    if deck.get("bibliographie") and CITED:
        body.append("\n% ==================== bibliographie (references.yaml) ====================")
        body += [f + "\n" for f in bibliography_frames(ctx)]
    tex = document(deck, ctx, body, deck.get("titlepage", True))
    build_dir = os.path.join(PROJECT, "build"); os.makedirs(build_dir, exist_ok=True)
    tex_path = os.path.join(build_dir, out_name + ".tex")
    with open(tex_path, "w", encoding="utf8") as f:
        f.write(tex)
    print(f"{kept}/{total} transparents -> {os.path.relpath(tex_path, PROJECT)}")
    for line, msg in WARNINGS:
        print(f"avertissement ligne {line} : {msg}", file=sys.stderr)
    if not make_pdf:
        return
    run_pdflatex(tex_path, build_dir)
    shutil.copy(os.path.join(build_dir, out_name + ".pdf"), os.path.join(PROJECT, out_name + ".pdf"))
    print(f"-> {out_name}.pdf")

# ------------------------------------------------------------------ export des métadonnées

def slide_meta(s):
    """Contenu de meta: (ou hidden:, synonyme) d'un transparent : jamais rendu dans le .tex."""
    m = {}
    for k in ("meta", "hidden"):
        v = s.get(k) if isinstance(s, dict) else None
        if isinstance(v, dict): m.update(v)
        elif v is not None: m.setdefault("note", v)
    return m

def export_meta(deck, ctx, target):
    """--export FICHIER : liste des transparents (titre, position, filtres, meta) en .md, .json ou .yaml ;
    '-' écrit du Markdown sur la sortie standard. Les filtres d'audience et hide ne sont pas appliqués :
    la colonne « filtres » les indique."""
    import json
    slides_dir = os.path.join(PROJECT, deck.get("slides_dir", "slides"))
    rows, n = [], 0
    for p in deck["parts"]:
        path = os.path.join(slides_dir, p if p.endswith(".yaml") else p + ".yaml")
        for i, s in enumerate(load_yaml(path)):
            n += 1
            if not isinstance(s, dict): continue
            title = s.get("section") or s.get("title") or ("[image]" if "image" in s else "[sans titre]")
            filters = []
            if s.get("hide"): filters.append("hide")
            if s.get("only"): filters.append("only:" + ",".join(s["only"]))
            if s.get("except"): filters.append("except:" + ",".join(s["except"]))
            rows.append({"n": n, "file": os.path.relpath(path, PROJECT), "line": line_of(s), "index": i + 1,
                         "kind": "section" if "section" in s else "slide",
                         "title": L(title, ctx) if not isinstance(title, dict) or is_lang_dict(title) else str(title),
                         "filters": filters, "meta": slide_meta(s)})
    ext = os.path.splitext(target)[1].lower() if target != "-" else ".md"
    if ext == ".json":
        out = json.dumps(rows, ensure_ascii=False, indent=2)
    elif ext in (".yaml", ".yml"):
        out = yaml.safe_dump(rows, allow_unicode=True, sort_keys=False)
    else:
        keys = sorted({k for r in rows for k in r["meta"]})
        head = ["n", "titre", "filtres"] + keys
        lines = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
        for r in rows:
            cells = [str(r["n"]), ("**" + r["title"] + "**") if r["kind"] == "section" else r["title"], " ".join(r["filters"])]
            cells += [(", ".join(map(str, v)) if isinstance(v, list) else str(v)).replace("\n", " ")
                      for v in (r["meta"].get(k, "") for k in keys)]
            lines.append("| " + " | ".join(c.replace("|", "\\|") for c in cells) + " |")
        out = "\n".join(lines) + "\n"
    if target == "-":
        print(out)
    else:
        with open(os.path.join(PROJECT, target), "w", encoding="utf8") as f: f.write(out)
        print(f"{len(rows)} transparents -> {target}")

# ------------------------------------------------------------------ aperçu d'un seul transparent

def slide_index_at(path, line):
    """Numéro (0-based) du transparent contenant la ligne `line` (1-based) : les transparents
    sont les éléments de la liste de premier niveau, i.e. les lignes commençant par '- ' en colonne 0."""
    idx = -1
    with open(path, encoding="utf8") as f:
        for n, l in enumerate(f, 1):
            if n > line:
                break
            if re.match(r"-(\s|$)", l):
                idx += 1
    return idx

def make_format(deck, ctx, out_dir):
    """Précompile le préambule (mylatexformat) -> out_dir/preambule-<lang>.fmt. Renvoie le nom du format."""
    name = f"preambule-{ctx.lang}"
    src = os.path.join(out_dir, name + ".tex")
    with open(src, "w", encoding="utf8") as f:
        f.write(document(deck, ctx, [], titlepage=False))
    env = dict(os.environ, TEXINPUTS=PROJECT + ":" + ENGINE + ":")
    r = subprocess.run(["pdflatex", "-ini", "-interaction=nonstopmode", f"-jobname={name}",
                        "-output-directory", out_dir, "&pdflatex", "mylatexformat.ltx", src],
                       cwd=PROJECT, capture_output=True, text=True, errors="replace", env=env)
    if r.returncode != 0 or not os.path.exists(os.path.join(out_dir, name + ".fmt")):
        print(r.stdout[-1500:]); sys.exit("Échec de la précompilation du préambule")
    print(f"format précompilé : build/preview/{name}.fmt")
    return name

def format_a_jour(deck, ctx, out_dir):
    """Le format précompilé du préambule est refait si le préambule généré (preamble.tex + macros de build.py)
    a changé depuis sa dernière compilation : on compare son texte à un fichier témoin .src."""
    name = f"preambule-{ctx.lang}"
    fmt, temoin = os.path.join(out_dir, name + ".fmt"), os.path.join(out_dir, name + ".src")
    courant = document(deck, ctx, [], titlepage=False)
    ancien = open(temoin, encoding="utf8").read() if os.path.exists(temoin) else None
    if not os.path.exists(fmt) or ancien != courant:
        os.makedirs(out_dir, exist_ok=True)
        make_format(deck, ctx, out_dir)
        with open(temoin, "w", encoding="utf8") as f: f.write(courant)
    return name

def find_tikz_users(deck, rel):
    """[(fichier yaml, index, transparent)] des transparents dont un bloc tikz: référence `rel`."""
    slides_dir = os.path.join(PROJECT, deck.get("slides_dir", "slides"))
    found = []
    def uses(node):
        if isinstance(node, dict):
            t = node.get("tikz")
            if t is not None:
                vals = [t] if isinstance(t, str) else [v for v in _flatten(t)]
                if any(os.path.normpath(v) == rel for v in vals if isinstance(v, str)):
                    return True
            return any(uses(v) for v in node.values())
        if isinstance(node, list):
            return any(uses(v) for v in node)
        return False
    for p in deck["parts"]:
        path = os.path.join(slides_dir, p if p.endswith(".yaml") else p + ".yaml")
        try:
            slides = load_yaml(path)
        except yaml.YAMLError:
            continue
        for i, s in enumerate(slides):
            if uses(s):
                found.append((path, i, s))
    return found

def _flatten(d):
    for v in d.values():
        if isinstance(v, dict): yield from _flatten(v)
        else: yield v

def preview_tikz(deck, ctx, tikz_path, buffer_path=None, png=True, use_fmt=True):
    """--tikz fichier.tikz [--buffer tmp] : aperçu d'un fichier TikZ, dans le transparent qui l'utilise
    s'il y en a un, sinon seul dans une frame."""
    import json
    rel = os.path.normpath(os.path.relpath(os.path.abspath(tikz_path), PROJECT))
    src = os.path.normpath(os.path.relpath(os.path.abspath(buffer_path), PROJECT)) if buffer_path else rel
    if buffer_path:
        OVERRIDE[rel] = src
    users = find_tikz_users(deck, rel)
    info = {"mode": "tikz", "file": rel}
    if users:
        path, i, s = users[0]
        WARNINGS.clear()
        try:
            r = render_slide(s, ctx)
        except SlideError as e:
            print("PREVIEW_JSON " + json.dumps({"error": f"Structure : {e}", "kind": "structure", "line": None}, ensure_ascii=False)); sys.exit(1)
        if r is None:   # masqué pour cette audience : on montre le dessin seul
            users = []
        else:
            info.update(slide=i + 1, used_by=f"{os.path.relpath(path, PROJECT)}:{line_of(s)}", slide_line=line_of(s))
    if not users:
        r = ("\\begin{frame}[plain]\\begin{center}\\input{" + src + "}\\end{center}"
             "\\vfill{\\tiny\\color{gris}" + esc(rel) + "}\\end{frame}")
    _compile_preview(deck, ctx, r, png, use_fmt, info)

def _compile_preview(deck, ctx, frame_tex, png, use_fmt, info):
    import json
    out_dir = os.path.join(PROJECT, "build", "preview"); os.makedirs(out_dir, exist_ok=True)
    for p in os.listdir(out_dir):
        if re.fullmatch(r"slide(-\d+)?\.(png|pdf)", p):
            os.remove(os.path.join(out_dir, p))
    fmt = None
    if use_fmt:
        fmt = format_a_jour(deck, ctx, out_dir)
    tex_path = os.path.join(out_dir, "slide.tex")
    with open(tex_path, "w", encoding="utf8") as f:
        f.write(document(deck, ctx, [frame_tex], titlepage=False))
    run_pdflatex(tex_path, out_dir, passes=1, fmt=fmt)
    pdf = os.path.join(out_dir, "slide.pdf")
    layers = 1
    if png:
        subprocess.run(["magick", "-density", "110", pdf, "-background", "white", "-alpha", "remove",
                        os.path.join(out_dir, "slide-%d.png")], check=True)
        pages = sorted(p for p in os.listdir(out_dir) if re.fullmatch(r"slide-\d+\.png", p))
        shutil.copy(os.path.join(out_dir, pages[-1]), os.path.join(out_dir, "slide.png"))
        layers = len(pages)
    info.update(layers=layers, lang=ctx.lang, audience=ctx.audience, dir=out_dir,
                warnings=[{"line": l, "message": m} for l, m in WARNINGS])
    print("PREVIEW_JSON " + json.dumps(info, ensure_ascii=False))

def preview(deck, ctx, spec, png=True, use_fmt=True):
    """--slide fichier.yaml:ligne : compile le seul transparent sous cette ligne.
    Termine par une ligne PREVIEW_JSON {...} pour les outils (plugin VS Code)."""
    import json
    path, _, line = spec.rpartition(":")
    line = int(line)
    path = os.path.abspath(path)
    idx = slide_index_at(path, line)
    def fail(**kw):
        print("PREVIEW_JSON " + json.dumps(kw, ensure_ascii=False)); sys.exit(1)
    try:
        slides = load_yaml(path)
    except yaml.YAMLError as e:
        mark = getattr(e, "problem_mark", None)
        ctxm = getattr(e, "context_mark", None)
        problem = getattr(e, "problem", None) or str(e)
        context = getattr(e, "context", None)
        msg = f"YAML : {problem}" + (f" ({context})" if context else "")
        fail(error=msg, kind="yaml", line=mark.line + 1 if mark else None, column=mark.column + 1 if mark else None,
             context_line=ctxm.line + 1 if ctxm else None)
    if idx < 0 or idx >= len(slides):
        fail(error=f"Aucun transparent à la ligne {line}", kind="structure", line=line)
    hidden = False
    WARNINGS.clear()
    slide = slides[idx]
    hide_flag = bool(slide.get("hide")) if isinstance(slide, dict) else False
    if hide_flag and not SHOW_HIDDEN:      # on édite ce transparent : on le montre quand même
        slide = dict(slide); del slide["hide"]; LINES[id(slide)] = line_of(slides[idx])
    try:
        r = render_slide(slide, ctx)
    except SlideError as e:
        fail(error=f"Structure : {e}", kind="structure", line=e.line or line_of(slides[idx]))
    if r is None:
        hidden = True
        r = ("\\begin{frame}[plain]\\centering\\vspace*{0.4\\textheight}{\\large\\color{gris}"
             f"Transparent {idx+1} masqué pour l'audience \\og {ctx.audience}\\fg{{}}}}\\end{{frame}}")
    out_dir = os.path.join(PROJECT, "build", "preview"); os.makedirs(out_dir, exist_ok=True)
    for p in os.listdir(out_dir):
        if re.fullmatch(r"slide(-\d+)?\.(png|pdf)", p):
            os.remove(os.path.join(out_dir, p))
    fmt = None
    if use_fmt:
        fmt = format_a_jour(deck, ctx, out_dir)
    tex_path = os.path.join(out_dir, "slide.tex")
    with open(tex_path, "w", encoding="utf8") as f:
        f.write(document(deck, ctx, [r], titlepage=False))
    run_pdflatex(tex_path, out_dir, passes=1, fmt=fmt)
    pdf = os.path.join(out_dir, "slide.pdf")
    print(f"transparent {idx+1} de {os.path.basename(path)} -> build/preview/slide.pdf")
    if png:
        # dernière page = transparent complet ; une image par couche en plus
        subprocess.run(["magick", "-density", "110", pdf, "-background", "white", "-alpha", "remove",
                        os.path.join(out_dir, "slide-%d.png")], check=True)
        pages = sorted(p for p in os.listdir(out_dir) if re.fullmatch(r"slide-\d+\.png", p))
        shutil.copy(os.path.join(out_dir, pages[-1]), os.path.join(out_dir, "slide.png"))
        print(f"-> build/preview/slide.png ({len(pages)} couche(s))")
        print("PREVIEW_JSON " + json.dumps({"slide": idx + 1, "total": len(slides), "layers": len(pages),
              "hidden": hidden or hide_flag, "hide_reason": "hide" if hide_flag else ("audience" if hidden else None),
              "lang": ctx.lang, "audience": ctx.audience, "dir": out_dir,
              "slide_line": line_of(slides[idx]),
              "warnings": [{"line": l, "message": m} for l, m in WARNINGS]}, ensure_ascii=False))

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lang", default=None, choices=LANGS)
    ap.add_argument("--audience", default=None)
    ap.add_argument("--out", default=None, help="nom de sortie sans extension")
    ap.add_argument("--deck", default="deck.yaml")
    ap.add_argument("--no-pdf", action="store_true")
    ap.add_argument("--slide", metavar="FICHIER.yaml:LIGNE", help="aperçu du seul transparent sous cette ligne")
    ap.add_argument("--no-png", action="store_true", help="avec --slide : ne pas produire de PNG")
    ap.add_argument("--no-fmt", action="store_true", help="avec --slide : ne pas utiliser le préambule précompilé")
    ap.add_argument("--make-format", action="store_true", help="(re)précompile le préambule pour --slide")
    ap.add_argument("--regen", action="store_true", help="régénérer toutes les figures produites par des scripts")
    ap.add_argument("--show-hidden", action="store_true", help="inclure les transparents et blocs marqués hide: true")
    ap.add_argument("--refs", action="store_true", help="lister les références citées (cite:) par le deck, et celles de references.yaml jamais citées")
    ap.add_argument("--export", metavar="FICHIER|-", help="exporter titres, filtres et meta: des transparents (.md, .json, .yaml ; - = Markdown sur stdout)")
    ap.add_argument("--tikz", metavar="FICHIER.tikz", help="aperçu d'un fichier TikZ (dans le transparent qui l'utilise, sinon seul)")
    ap.add_argument("--buffer", metavar="TMP", help="avec --tikz : fichier contenant le contenu non sauvegardé de l'éditeur")
    a = ap.parse_args()
    global PROJECT
    deck_path = os.path.abspath(a.deck)
    if not os.path.exists(deck_path):
        sys.exit(f"Deck introuvable : {deck_path}")
    PROJECT = os.path.dirname(deck_path)
    with open(deck_path, encoding="utf8") as f:
        deck = yaml.safe_load(f)
    lang = a.lang or deck.get("lang", "fr")
    audience = a.audience or deck.get("audience")
    if audience and audience not in deck.get("audiences", [audience]):
        sys.exit(f"Audience inconnue : {audience} (connues : {deck.get('audiences')})")
    out = a.out or f"{deck.get('name', 'slides')}-{lang}" + (f"-{audience}" if audience else "")
    global REGEN, SHOW_HIDDEN; REGEN = a.regen; SHOW_HIDDEN = a.show_hidden
    ctx = Ctx(lang, audience, deck.get("audiences", []))
    if a.export:
        export_meta(deck, ctx, a.export); return
    if a.refs:
        build(deck, ctx, out, make_pdf=False)
        print(f"\n{len(CITED)} références citées par {a.deck} :")
        for k in CITED: print(f"  {k:28} {ref_short(k, refs()[k])}")
        rest = [k for k in refs() if k not in CITED]
        if rest: print(f"\njamais citées ici ({len(rest)}) : " + ", ".join(rest))
        return
    if a.make_format:
        make_format(deck, ctx, os.path.join(PROJECT, "build", "preview")); return
    if a.slide:
        preview(deck, ctx, a.slide, png=not a.no_png, use_fmt=not a.no_fmt); return
    if a.tikz:
        preview_tikz(deck, ctx, a.tikz, a.buffer, png=not a.no_png, use_fmt=not a.no_fmt); return
    build(deck, ctx, out, make_pdf=not a.no_pdf)

if __name__ == "__main__":
    main()
