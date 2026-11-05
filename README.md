# md-versioning

Document-native versioning for Markdown files with YAML frontmatter.
You think in directory, filename, and tag; the engine keeps identity,
history, and search working underneath.

## Run the tests and the demo

```bash
uv sync
uv run pytest
uv run python demo/run_demo.py
```

## Use the engine

```python
from md_versioning import Engine

engine = Engine("path/to/workspace")
engine.save("contracts", "acme-msa.md", "# Acme MSA\n", tags=["legal"])
engine.tag("contracts", "acme-msa.md", "signed")
engine.find(["legal", "signed"])        # [("contracts", "acme-msa.md")]
engine.rename("contracts", "acme-msa.md", "acme-msa-2026.md")
engine.read("contracts", "acme-msa.md") # still found, by its former name
print(engine.history("contracts", "acme-msa-2026.md"))
```

## Use the agent surface

```python
from md_versioning import AgentSurface

surface = AgentSurface("path/to/workspace")
surface.save("notes", "memo.md", "# Memo\n", tags=["idea"])
surface.open("notes", "memo.md")
surface.find(["idea"])
```

The surface also speaks JSON-lines: one request object per line, such as
`{"op": "find", "args": {"tags": ["idea"]}}`, and one response object per
line. If a document changed since the surface last saw it, the response
says the file changed and includes its current text, so the caller can
describe the document in full against that text.

Design and rationale: see `SPEC.md` and `IMPLEMENTATION_PLAN.md`.
