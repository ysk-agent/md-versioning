---
file_id: spec-md-versioning
version: 1
tags: [spec, versioning, agent]
aliases: [md-versioning-spec]
updated: 2026-11-05T00:00Z
---

# Markdown + Frontmatter Versioning — Spec

Version control for people who think in documents, not diffs.
Jujutsu's model, Markdown's surface, an agent's hands.

## 1. Principle

The business man's entire vocabulary is three things:

- **directory** — where it lives
- **filename** — what it is
- **tag** — what it's about (a plain word in `tags:` frontmatter)

Versioning is **invisible**. Hash, DAG, parents, version counters are engine
plumbing. They are never spoken, never shown, never required.

## 2. File Format

Every document is a `.md` file with YAML frontmatter.

```markdown
---
file_id: 0f3a-acme-msa     # immutable, engine-assigned
version: 7
tags: [q3-review, legal]
aliases: [acme-msa]
updated: 2026-11-05T14:22Z
---

# Acme MSA

...body...
```

Frontmatter fields

| Field | Owner | Mutability | Purpose |
|---|---|---|---|
| file_id | engine | immutable | stable identity across renames/moves |
| version | engine | bump on save | monotonic counter |
| tags | user/agent | mutable | plain words, no # |
| aliases | engine | append-only | former filenames |
| updated | engine | set on save | ISO-8601 timestamp |

Frontmatter is canonical for metadata. Body is payload. If they disagree,
frontmatter wins and the engine repairs the body silently.

## 3. Storage Layout

```
workspace/
  contracts/
    acme-msa.md
  legal/
    liability-clause.md
  .versioning/              # hidden, engine-only
    blobs/<hash>            # content-addressed bodies (blake3)
    log/<file_id>.jsonl     # append-only version history
    index.db                # sqlite: tags, aliases, file_ids
```

.versioning/ is never surfaced to the business man or the agent.

## 4. Engine Operations

The complete API. Six operations, no more.

### 4.1 read(dir, filename)

Resolve path → parse frontmatter + body → return document.
If path not found, look up aliases in the index. Return None if unknown.

### 4.2 save(dir, filename, body, tags?, intent?)

1. Compute hash = blake3(body).
2. If hash == current_blob_hash, no-op (nothing changed).
3. Write blob to .versioning/blobs/<hash>.
4. Append to .versioning/log/<file_id>.jsonl:
   ```json
   {"v":8,"hash":"9f2a…","parents":["…@7"],"tags":[…],"intent":"…","ts":"…"}
   ```
5. Bump version in frontmatter, update updated, atomic rewrite
   (temp file + os.replace).

Every mutation goes through save. Tags, renames, body edits — one log entry each.

### 4.3 tag(dir, filename, word) / untag(dir, filename, word)

Mutate tags: list → trigger save with intent: "tag <word>" /
"untag <word>". word is a bare string, no #.

### 4.4 find(tags: [...])

Query index.db tags table. AND semantics by default. Returns list of
(dir, filename).

### 4.5 rename(dir, filename, new_name)

Append new_name to aliases, move file on disk, update index path.
file_id stays stable. History follows file_id, not path.

### 4.6 history(dir, filename)

Read log/<file_id>.jsonl → render human-readable: version, intent, tags,
timestamp. No hashes shown.

## 5. Invariants

1. file_id never changes. Rename = alias. Move = path update.
2. Every mutation goes through save. No side channels.
3. Hash check is the no-op guard. Identical content produces no log entry.
4. Atomic writes. Temp file + os.replace. Crash-safe.
5. Frontmatter is canonical. Engine repairs body/frontmatter drift silently.
6. Plain tags. No # in YAML, no # in speech. A tag is a bare word.

## 6. Conflict Handling

Two saves to the same file from two agents:

- Second save's parents = both prior versions.
- Body = the re-emitted full document.
- No three-way merge. No merge UI.
- The agent is told: "file changed, here is current state, re-describe what
  you want." It re-emits the full doc. That becomes the new node.

This is the jj-style move: describe the desired end state, don't reconcile diffs.

## 7. Agent Surface

The agent's tool list contains only these, phrased in user vocabulary:

- open(directory, filename)
- save(directory, filename, body, tags?, intent?)
- tag(directory, filename, word)
- untag(directory, filename, word)
- find(tags)
- rename(directory, filename, new_name)
- history(directory, filename)

The agent's prompt never mentions hash, version, DAG, parents, or blobs.

## 8. What Stays Hidden (and why)

| Hidden | Why |
|---|---|
| hash | dedup + "did it change?" — internal |
| version int | monotonic counter, engine bumps it |
| parents / DAG | conflict resolution + history walk |
| log JSONL | audit trail, engine-read only |
| sqlite index | performance, rebuildable from files |

The index is rebuildable: walk **/*.md, parse frontmatter, repopulate.
The files on disk are the source of truth.

## 9. Build Order

Each step is runnable and testable on its own.

Step 1 — core. read / save / history on one file.
parse_frontmatter, blake3(body), append JSONL, atomic rewrite.
Test: save 5 times, log reflects changes with dedup.

Step 2 — tags. tag / untag as wrappers over save.
find(tags) greps frontmatter (no index yet).
Test: tag 3 files, query returns them.

Step 3 — index. SQLite tags(file_id, word) + files(file_id, dir, filename).
Rebuild on startup, idempotent. find becomes fast.

Step 4 — aliases + rename. rename appends alias, updates index path.
read falls back to alias lookup.
Test: rename, then read by old name.

Step 5 — agent surface. Expose the seven ops as tool calls / JSON-RPC.
Prompt contains only directory, filename, tag.

## 10. Non-Goals

- No branches. Lifecycle is a tags: entry if needed (draft, signed).
- No staging area. The file is the commit.
- No user-visible commit messages. intent is captured but not required reading.
- No merge UI. Conflicts resolved by re-emission.
- No # anywhere. Tags are plain words.
