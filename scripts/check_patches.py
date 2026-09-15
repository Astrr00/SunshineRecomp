"""Prueft, ob die Patches noch auf die angehefteten Upstream-Commits passen.

Warum das noetig ist: Sechs Patches mit ueber tausend Zeilen liegen gegen drei
fremde Baeume. Ob sie noch passen, zeigte sich bisher erst beim naechsten
vollstaendigen Bootstrap unter Windows -- also spaet. Diese Pruefung laeuft
unter Linux in wenigen Minuten und braucht weder LLVM noch Spieldaten.

Einzige Quelle der Wahrheit ist ``scripts/bootstrap.ps1``. Repository-Adressen,
Commits, Patchliste und Reihenfolge werden von dort gelesen, statt hier
wiederholt zu werden; sonst koennte die Pruefung gruen bleiben, waehrend der
echte Bootstrap etwas anderes tut.

Geholt wird nur, was die Patches anfassen (partieller Klon ohne Blobs plus
Sparse-Checkout). Der Dolphin-Baum von RecompCore waere sonst unverhaeltnismaessig.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
BOOTSTRAP = PROJECT / "scripts" / "bootstrap.ps1"
PATCHES = PROJECT / "patches"

# Das Vendor-Submodul wird im Bootstrap auf einen anderen Branch gesetzt als den
# in .gitmodules eingetragenen; die Adresse selbst stammt aber von dort.
VENDOR_SUBMODULE = "vendor/dolphin"


class CheckError(Exception):
    """Die Pruefung kann nicht durchgefuehrt werden."""


@dataclass
class Dependency:
    name: str
    url: str
    commit: str


@dataclass
class PatchStep:
    file: str
    target: str          # Pfad unterhalb von ref/, wie im Bootstrap
    repository: str = ""  # aufgeloest: DolRecomp, ModernGekko oder RecompCore


@dataclass
class Bootstrap:
    dependencies: list[Dependency] = field(default_factory=list)
    recompcore_commit: str = ""
    recompcore_branch: str = ""
    patches: list[PatchStep] = field(default_factory=list)


def parse_bootstrap(text: str) -> Bootstrap:
    """Liest Abhaengigkeiten, Vendor-Commit und Patchreihenfolge aus dem Skript."""
    result = Bootstrap()

    for block in re.finditer(
            r"Name\s*=\s*'([^']+)'\s*\n\s*Url\s*=\s*'([^']+)'\s*\n"
            r"\s*Commit\s*=\s*'([0-9a-f]{40})'", text):
        result.dependencies.append(
            Dependency(name=block.group(1), url=block.group(2),
                       commit=block.group(3)))

    commit = re.search(r"\$RecompCoreCommit\s*=\s*'([0-9a-f]{40})'", text)
    branch = re.search(r"\$RecompCoreBranch\s*=\s*'([^']+)'", text)
    if not commit or not branch:
        raise CheckError("RecompCore-Commit oder -Branch fehlt in bootstrap.ps1.")
    result.recompcore_commit = commit.group(1)
    result.recompcore_branch = branch.group(1)

    for block in re.finditer(
            r"File\s*=\s*'([^']+\.patch)'\s*\n\s*Target\s*=\s*Join-Path\s+"
            r"\$RefRoot\s+'([^']+)'", text):
        result.patches.append(
            PatchStep(file=block.group(1),
                      target=block.group(2).replace("\\", "/")))

    if not result.dependencies or not result.patches:
        raise CheckError(
            "bootstrap.ps1 liess sich nicht auswerten. Wurde die Struktur der "
            "Listen $Dependencies oder $patches geaendert? Dann muss diese "
            "Pruefung nachgezogen werden.")
    return result


def resolve_targets(bootstrap: Bootstrap) -> None:
    """Ordnet jedem Patch das Repository zu, in dem er landet."""
    known = {dependency.name for dependency in bootstrap.dependencies}
    for step in bootstrap.patches:
        if step.target == f"ModernGekko/{VENDOR_SUBMODULE}":
            step.repository = "RecompCore"
        elif step.target in known:
            step.repository = step.target
        else:
            raise CheckError(
                f"Unbekanntes Patchziel \"{step.target}\" fuer {step.file}.")


def patched_paths(patch: Path) -> set[str]:
    """Die im Patch genannten Pfade, fuer den Sparse-Checkout."""
    paths: set[str] = set()
    for line in patch.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith(("--- ", "+++ ")):
            name = line[4:].split("\t")[0].strip()
            if name == "/dev/null":
                continue
            if name[:2] in ("a/", "b/"):
                name = name[2:]
            paths.add(name)
    return paths


def run(command: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(command, cwd=cwd, capture_output=True, text=True)


def must(command: list[str], cwd: Path | None = None, what: str = "") -> str:
    done = run(command, cwd)
    if done.returncode != 0:
        raise CheckError(
            f"{what or ' '.join(command[:3])} fehlgeschlagen "
            f"(Code {done.returncode}):\n{done.stderr.strip()[:800]}")
    return done.stdout


def sparse_clone(url: str, commit: str, destination: Path,
                 paths: set[str], verbose: bool) -> None:
    """Holt genau die Dateien eines Commits, die gebraucht werden."""
    if verbose:
        print(f"    klonen: {url} @ {commit[:12]}")
    must(["git", "init", "--quiet", str(destination)], what="git init")
    must(["git", "remote", "add", "origin", url], destination)
    # Ohne Blobs und ohne Baum-Vorabruf: es werden nur die Objekte geholt,
    # die der Sparse-Checkout tatsaechlich auspackt.
    must(["git", "fetch", "--quiet", "--depth", "1", "--filter=blob:none",
          "origin", commit], destination, what=f"fetch {commit[:12]}")
    must(["git", "sparse-checkout", "init", "--no-cone"], destination)
    directories = sorted({str(Path(path).parent) for path in paths})
    patterns = [f"/{directory}/*" for directory in directories if directory != "."]
    patterns += [f"/{path}" for path in sorted(paths)]
    must(["git", "sparse-checkout", "set", "--no-cone", *patterns], destination)
    must(["git", "checkout", "--quiet", "FETCH_HEAD"], destination,
         what="checkout")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--keep", type=Path,
                        help="Arbeitsverzeichnis behalten statt loeschen")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)
    verbose = not args.quiet

    try:
        bootstrap = parse_bootstrap(BOOTSTRAP.read_text(encoding="utf-8"))
        resolve_targets(bootstrap)
    except (CheckError, OSError) as error:
        print(f"Fehler: {error}", file=sys.stderr)
        return 2

    print("Aus bootstrap.ps1 gelesen:")
    for dependency in bootstrap.dependencies:
        print(f"  {dependency.name:<12} {dependency.commit}")
    print(f"  {'RecompCore':<12} {bootstrap.recompcore_commit} "
          f"(Branch {bootstrap.recompcore_branch})")
    print(f"  {len(bootstrap.patches)} Patches\n")

    missing = [step.file for step in bootstrap.patches
               if not (PATCHES / step.file).is_file()]
    if missing:
        print(f"Fehler: Im Bootstrap genannte Patches fehlen: "
              f"{', '.join(missing)}", file=sys.stderr)
        return 2

    on_disk = {path.name for path in PATCHES.glob("*.patch")}
    listed = {step.file for step in bootstrap.patches}
    for orphan in sorted(on_disk - listed):
        print(f"  Hinweis: patches/{orphan} wird vom Bootstrap nicht angewandt.")

    # Pro Repository alle Pfade sammeln, die irgendein Patch anfasst.
    needed: dict[str, set[str]] = {}
    for step in bootstrap.patches:
        needed.setdefault(step.repository, set()).update(
            patched_paths(PATCHES / step.file))

    urls = {dependency.name: dependency.url
            for dependency in bootstrap.dependencies}
    commits = {dependency.name: dependency.commit
               for dependency in bootstrap.dependencies}

    root = Path(args.keep) if args.keep else Path(tempfile.mkdtemp(prefix="patchcheck-"))
    root.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []

    try:
        if "RecompCore" in needed:
            # Die Adresse steht in ModernGekkos .gitmodules, der Commit im
            # Bootstrap. Beides zusammen ergibt den Vendor-Stand.
            gekko = root / "ModernGekko-probe"
            sparse_clone(urls["ModernGekko"], commits["ModernGekko"], gekko,
                         {".gitmodules"}, verbose)
            modules = (gekko / ".gitmodules").read_text(encoding="utf-8")
            found = re.search(
                rf"\[submodule \"{re.escape(VENDOR_SUBMODULE)}\"\][^\[]*?"
                rf"url\s*=\s*(\S+)", modules, re.S)
            if not found:
                raise CheckError(
                    f"In ModernGekkos .gitmodules fehlt {VENDOR_SUBMODULE}.")
            urls["RecompCore"] = found.group(1)
            commits["RecompCore"] = bootstrap.recompcore_commit
            print(f"  RecompCore-Adresse aus .gitmodules: {urls['RecompCore']}\n")

        trees: dict[str, Path] = {}
        for repository, paths in sorted(needed.items()):
            print(f"Hole {repository} ({len(paths)} Dateien) ...")
            tree = root / repository
            sparse_clone(urls[repository], commits[repository], tree, paths, verbose)
            trees[repository] = tree
            for path in sorted(paths):
                if not (tree / path).exists():
                    # Neu angelegte Dateien fehlen erwartungsgemaess.
                    if verbose:
                        print(f"    nicht im Baum (wird angelegt): {path}")

        print("\nPatches in Bootstrap-Reihenfolge:")
        for step in bootstrap.patches:
            tree = trees[step.repository]
            patch = PATCHES / step.file
            check = run(["git", "apply", "--check", str(patch)], tree)
            if check.returncode != 0:
                failures.append(step.file)
                print(f"  FEHLER    {step.file} -> {step.repository}")
                for line in check.stderr.strip().splitlines()[:6]:
                    print(f"            {line}")
                continue
            must(["git", "apply", str(patch)], tree, what=f"apply {step.file}")

            # Wie bootstrap.ps1 fuer die Idempotenz: ein angewandter Patch muss
            # sich rueckwaerts erkennen, sonst liefe ein zweiter Bootstrap auf
            # einen Fehler statt auf ein "bereits vorhanden".
            reverse = run(["git", "apply", "--reverse", "--check", str(patch)], tree)
            if reverse.returncode != 0:
                failures.append(f"{step.file} (rueckwaerts)")
                print(f"  FEHLER    {step.file} laesst sich nach dem Anwenden "
                      f"nicht rueckwaerts erkennen; Bootstrap waere nicht "
                      f"wiederholbar.")
                continue
            print(f"  OK        {step.file} -> {step.repository}")
    except CheckError as error:
        print(f"\nFehler: {error}", file=sys.stderr)
        return 2
    finally:
        if not args.keep:
            shutil.rmtree(root, ignore_errors=True)
        else:
            print(f"\nArbeitsverzeichnis behalten: {root}")

    if failures:
        print(f"\n{len(failures)} Patch(es) passen nicht mehr: "
              f"{', '.join(failures)}", file=sys.stderr)
        print("Upstream hat sich bewegt oder der Patch ist veraltet. "
              "docs/PLAN.md, Abschnitt 2.2 schlaegt Forks statt Patchdateien vor.",
              file=sys.stderr)
        return 1

    print(f"\nAlle {len(bootstrap.patches)} Patches passen auf die "
          f"angehefteten Commits.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
