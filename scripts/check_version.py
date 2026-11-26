#!/usr/bin/env python3
"""Controle de coherence : version.txt et APP_BUILD_VERSION (vtp_core.py).

Lancee depuis les sources, l'application lit version.txt ; compilee, elle utilise
APP_BUILD_VERSION. final_build.bat nomme l'exe d'apres version.txt. Si les deux
valeurs different, on obtient un exe qui porte un numero et en affiche un autre.

Code de sortie : 0 si les deux sont identiques, 1 sinon (message en clair).
Bibliotheque standard seulement.
"""
import argparse
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATTERN = re.compile(r'^APP_BUILD_VERSION\s*=\s*["\']([^"\']+)["\']', re.MULTILINE)


def read_versions(version_file, source_file):
    with open(version_file, encoding="utf-8-sig") as fh:
        from_file = fh.read().strip()
    with open(source_file, encoding="utf-8") as fh:
        text = fh.read()
    match = PATTERN.search(text)
    if not match:
        return from_file, None, None
    line = text.count("\n", 0, match.start()) + 1
    return from_file, match.group(1).strip(), line


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version-file", default=os.path.join(ROOT, "version.txt"))
    parser.add_argument("--source-file", default=os.path.join(ROOT, "vtp_core.py"))
    args = parser.parse_args(argv)

    try:
        from_file, from_code, line = read_versions(args.version_file, args.source_file)
    except OSError as exc:
        print(f"[ERREUR] Lecture impossible : {exc}")
        return 1

    if from_code is None:
        print("[ERREUR] APP_BUILD_VERSION introuvable dans vtp_core.py.")
        return 1
    if not from_file:
        print("[ERREUR] version.txt est vide.")
        return 1
    if from_file != from_code:
        print("[ERREUR] Les deux versions different :")
        print(f"         version.txt        : {from_file}")
        print(f"         APP_BUILD_VERSION  : {from_code}  (vtp_core.py, ligne {line})")
        print("         Mettez la meme valeur dans les deux, ou recuperez la bonne branche :")
        print("         git status, git branch --show-current, git log --oneline -3")
        return 1

    print(f"[OK] Version {from_file} : version.txt et APP_BUILD_VERSION concordent.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
