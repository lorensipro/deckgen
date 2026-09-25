#!/usr/bin/env python3
"""Banque de questions attachées aux transparents, et tirage au sort de sujets (QCM / questions ouvertes).

Les questions vivent à deux endroits, au choix :
  1. dans le transparent :      meta: {questions: [ ... ]}            (une ou deux questions courtes)
  2. dans un fichier à côté :   slides/rc/01-xxx.questions.yaml       (dès qu'il y en a plus)
         - slide: sapir-whorf        # le label: du transparent, ou son titre français exact
           questions: [ ... ]
Une question :
    - qcm: "Énoncé"                      # ou   ouverte: "Énoncé"
      choix: ["faux", "*juste", "faux"]  # qcm : * devant la ou les bonnes réponses
      attendu: "éléments de réponse"     # ouverte : pour le corrigé
      niveau: 1                          # optionnel, 1 (cours) à 3 (réflexion)
      points: 2                          # optionnel
      tags: [horn, complexite]           # optionnel
Tout texte peut être bilingue : {fr: ..., en: ...}.

  python3 /chemin/deckgen/questions.py --deck deck-rc-logique.yaml                       # inventaire
  python3 /chemin/deckgen/questions.py --deck deck-rc-logique.yaml --qcm 6 --ouvertes 2  # tirage -> sujet + corrigé (Markdown)
      [--seed 42] [--tags horn,owl] [--niveau-max 2] [--parts 01,03] [--lang en] [--out exam-rc]
"""
import argparse, glob, os, random, re, sys, yaml


def T(v, lang):
    if isinstance(v, dict):
        return str(v.get(lang) or v.get("fr") or next(iter(v.values())))
    return "" if v is None else str(v)

def collect(deck_file, lang):
    here = os.path.dirname(os.path.abspath(deck_file))    # dossier du cours
    deck = yaml.safe_load(open(deck_file, encoding="utf8"))
    sdir = os.path.join(here, deck.get("slides_dir", "slides"))
    bank, errors = [], []
    for part in deck["parts"]:
        path = os.path.join(sdir, part + ".yaml")
        slides = [s for s in yaml.safe_load(open(path, encoding="utf8")) if isinstance(s, dict)]
        index = {}
        for n, s in enumerate(slides, 1):
            title = T(s.get("title") or s.get("section") or "", "fr")
            for key in (s.get("label"), title):
                if key: index.setdefault(str(key), (n, title))
            meta = s.get("meta") or s.get("hidden") or {}
            for q in (meta.get("questions") or []):
                bank.append((part, n, title, q))
        side = path[:-5] + ".questions.yaml"
        if os.path.exists(side):
            for entry in yaml.safe_load(open(side, encoding="utf8")) or []:
                ref = str(entry.get("slide"))
                if ref not in index:
                    errors.append(f"{os.path.relpath(side, here)} : transparent introuvable « {ref} » (label: ou titre français exact)")
                    continue
                n, title = index[ref]
                for q in entry.get("questions") or []:
                    bank.append((part, n, title, q))
    out = []
    for part, n, title, q in bank:
        kind = "qcm" if "qcm" in q else "ouverte" if "ouverte" in q else None
        if not kind:
            errors.append(f"{part} transparent {n} : question sans clé qcm: ni ouverte:")
            continue
        item = {"part": part, "n": n, "slide": title, "type": kind, "enonce": T(q[kind], lang),
                "niveau": q.get("niveau", 1), "points": q.get("points"), "tags": q.get("tags") or [],
                "attendu": T(q.get("attendu"), lang)}
        if kind == "qcm":
            ch = [T(c, lang) for c in q.get("choix") or []]
            item["choix"] = [c.lstrip("*").strip() for c in ch]
            item["bonnes"] = [i for i, c in enumerate(ch) if c.startswith("*")]
            if len(ch) < 2 or not item["bonnes"]:
                errors.append(f"{part} transparent {n} : QCM sans choix ou sans bonne réponse (*) : {item['enonce'][:50]}")
                continue
        out.append(item)
    return out, errors

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--deck", default="deck.yaml")
    ap.add_argument("--lang", default="fr")
    ap.add_argument("--qcm", type=int, default=0); ap.add_argument("--ouvertes", type=int, default=0)
    ap.add_argument("--seed", type=int); ap.add_argument("--tags"); ap.add_argument("--parts")
    ap.add_argument("--niveau-max", type=int, default=3)
    ap.add_argument("--out", help="préfixe de sortie : <out>-sujet.md et <out>-corrige.md (défaut : écran)")
    a = ap.parse_args()
    bank, errors = collect(a.deck, a.lang)
    for e in errors: print("ATTENTION :", e, file=sys.stderr)
    if not (a.qcm or a.ouvertes):                                   # inventaire
        print(f"{len(bank)} questions ({sum(q['type']=='qcm' for q in bank)} QCM, {sum(q['type']=='ouverte' for q in bank)} ouvertes)")
        for part in dict.fromkeys(q["part"] for q in bank):
            qs = [q for q in bank if q["part"] == part]
            print(f"  {part} : {len(qs)}")
            for q in qs: print(f"      [{q['type']:7} n{q['niveau']}] t.{q['n']:<3} {q['enonce'][:80]}")
        return
    pool = [q for q in bank if q["niveau"] <= a.niveau_max
            and (not a.tags or set(a.tags.split(",")) & set(q["tags"]))
            and (not a.parts or any(q["part"].startswith(p) for p in a.parts.split(",")))]
    rnd = random.Random(a.seed)
    pick = []
    for kind, k in (("qcm", a.qcm), ("ouverte", a.ouvertes)):
        cand = [q for q in pool if q["type"] == kind]
        if len(cand) < k: print(f"ATTENTION : {len(cand)} questions « {kind} » disponibles pour {k} demandées", file=sys.stderr)
        pick += rnd.sample(cand, min(k, len(cand)))
    sujet, corrige = [f"# Sujet ({a.deck}, graine {a.seed})\n"], [f"# Corrigé ({a.deck}, graine {a.seed})\n"]
    for i, q in enumerate(pick, 1):
        pts = f" ({q['points']} pt)" if q["points"] else ""
        sujet.append(f"**{i}.** {q['enonce']}{pts}\n"); corrige.append(f"**{i}.** {q['enonce']}\n")
        if q["type"] == "qcm":
            order = list(range(len(q["choix"]))); rnd.shuffle(order)      # l'ordre des choix est aussi tiré au sort
            for j, o in enumerate(order):
                sujet.append(f"- [ ] {chr(65+j)}. {q['choix'][o]}")
            sujet.append("")
            corrige.append("Réponse : " + ", ".join(chr(65+j) for j, o in enumerate(order) if o in q["bonnes"]))
        else:
            sujet.append("\n\n")
            corrige.append("Attendu : " + (q["attendu"] or "(à rédiger)"))
        corrige.append(f"*({q['part']}, transparent {q['n']} : {q['slide']})*\n")
    for name, lines in (("sujet", sujet), ("corrige", corrige)):
        txt = "\n".join(lines) + "\n"
        if a.out:
            open(f"{a.out}-{name}.md", "w", encoding="utf8").write(txt); print(f"-> {a.out}-{name}.md")
        else:
            print(txt)

if __name__ == "__main__":
    main()
