"""End-to-end demonstration through the agent surface only.

Run with: uv run python demo/run_demo.py
Creates a scratch workspace under demo/workspace and walks through
create, tag, find, rename, and history.
"""

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from md_versioning import AgentSurface

ROOT = Path(__file__).resolve().parent / "workspace"


def main() -> None:
    if ROOT.exists():
        shutil.rmtree(ROOT)
    surface = AgentSurface(ROOT)

    surface.save("contracts", "acme-msa.md",
                 "# Acme MSA\n\nTerms for the year.\n", tags=["legal"])
    surface.save("contracts", "beta-msa.md",
                 "# Beta MSA\n\nDraft terms.\n", tags=["legal", "draft"])
    surface.tag("contracts", "acme-msa.md", "signed")

    print("find [legal]:", surface.find(["legal"]))
    print("find [legal, signed]:", surface.find(["legal", "signed"]))

    surface.rename("contracts", "beta-msa.md", "beta-msa-2026.md")
    opened = surface.open("contracts", "beta-msa.md")
    print("open by old name gives:", opened["filename"])

    print("history of acme-msa.md:")
    for line in surface.history("contracts", "acme-msa.md"):
        print(" ", line)


if __name__ == "__main__":
    main()
