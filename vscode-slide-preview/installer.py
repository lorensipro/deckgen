#!/usr/bin/env python3
"""Installe le plugin dans VS Code sans marketplace : lien dans ~/.vscode/extensions vers ce dossier
(les modifications du plugin sont prises en compte au rechargement de VS Code) et inscription dans
extensions.json, sans laquelle VS Code récent marque l'extension comme obsolète et l'ignore.
À lancer VS Code fermé :  python3 installer.py   (--desinstaller pour l'enlever)"""
import json, os, sys, time

ICI = os.path.dirname(os.path.abspath(__file__))
pkg = json.load(open(os.path.join(ICI, "package.json"), encoding="utf8"))
ident = f"{pkg['publisher']}.{pkg['name']}"
nom = f"{ident}-{pkg['version']}"
ext = os.path.expanduser("~/.vscode/extensions")
lien, registre, obsolete = os.path.join(ext, nom), os.path.join(ext, "extensions.json"), os.path.join(ext, ".obsolete")

def lire(p, defaut):
    return json.load(open(p, encoding="utf8")) if os.path.exists(p) else defaut

entrees = [e for e in lire(registre, []) if e["identifier"]["id"] != ident]
obs = {k: v for k, v in lire(obsolete, {}).items() if not k.startswith(ident + "-")}
for p in os.listdir(ext):                      # anciennes versions du lien
    if p.startswith(ident + "-") and os.path.islink(os.path.join(ext, p)):
        os.remove(os.path.join(ext, p))
if "--desinstaller" not in sys.argv:
    os.symlink(ICI, lien)
    entrees.append({"identifier": {"id": ident}, "version": pkg["version"],
                    "location": {"$mid": 1, "path": lien, "scheme": "file"}, "relativeLocation": nom,
                    "metadata": {"installedTimestamp": int(time.time() * 1000), "source": "vsix", "pinned": False,
                                 "targetPlatform": "undefined", "updated": False,
                                 "isPreReleaseVersion": False, "hasPreReleaseVersion": False}})
json.dump(entrees, open(registre, "w", encoding="utf8"))
if os.path.exists(obsolete):
    json.dump(obs, open(obsolete, "w", encoding="utf8"), separators=(",", ":"))
print(("désinstallé : " if "--desinstaller" in sys.argv else f"installé : {lien} -> ") + ICI)
print("Relancer VS Code.")
