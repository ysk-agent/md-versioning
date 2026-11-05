# Markdown + Frontmatter Versioning — Implementation Plan

Status: plan for approval. No engine code has been written yet.
Source spec: `spec-md-versioning`, version 1, shared 2026-11-05.
Proposed project location: `~/workspace/md-versioning/`

## 1. Goal

Build the versioning engine described in the spec so that an agent can work
with documents using only three concepts — directory, filename, and tag —
while the engine privately maintains stable identity, a version history, and
a searchable index. The finished result is a small Python package, a test
suite that proves each invariant in the spec, and a thin agent surface that
exposes only the seven permitted operations.

Success means every test named in Section 9 of this plan passes, and a short
demonstration run can create, edit, tag, rename, find, and show the history
of a document without any hidden term appearing in the agent-facing output.

## 2. Decisions taken from the spec (not open for re-decision)

- Documents are `.md` files with YAML frontmatter. Frontmatter is canonical
  for metadata; the body is the payload.
- Identity is an engine-assigned `file_id` that never changes. A rename adds
  the old filename to `aliases` and keeps the same `file_id`.
- Every mutation goes through one save path and produces exactly one entry
  in an append-only per-file log. There are no side channels.
- Storage is a hidden `.versioning/` directory at the workspace root,
  containing content-addressed body blobs, one JSONL log per file, and a
  SQLite index. Files on disk are the source of truth; the index is
  rebuildable by walking the documents.
- Conflicts are never merged. The agent is given the current state and
  re-emits the full desired document; that re-emission becomes the new
  version.
- Tags are plain words. No `#` character in storage, in speech, or in the
  agent prompt.
- Non-goals from the spec remain non-goals: no branches, no staging area,
  no merge interface, no user-visible commit messages.

## 3. Proposed defaults where the spec is silent or inconsistent

These defaults resolve the gaps found on review. Each one is internal and
none changes the user-facing vocabulary. Approving this plan approves these
defaults; any one of them can be changed without affecting the others.

### 3.1 The no-op guard must cover metadata, not only the body

The spec says an unchanged body hash makes a save a no-op, and also says a
tag change, an untag, and a rename each produce one log entry. A tag-only
change leaves the body unchanged, so a body-only guard would silently
discard it.

Default: a save is a no-op only when body, tags, and filename are all
unchanged. Any change to one of them writes one log entry and bumps the
version counter. The stored blob is still keyed by the body alone, so an
unchanged body reuses the existing blob.

### 3.2 Conflict detection needs a base version, kept internal

The spec's conflict rule requires the engine to know that an edit was based
on an older state, but the save signature carries no such information.

Default: the engine's internal save accepts an optional `base_version`,
meaning "the version the caller last read". It is never exposed in the
agent surface and never mentioned to the user.

- If `base_version` is absent, the save is an ordinary sequential edit.
- If `base_version` equals the current version, the save is ordinary.
- If `base_version` is older than the current version, the save is a
  conflict: its log entry records both the caller's parent and the current
  version as parents, and the caller first receives the current document
  together with a plain indication that the file changed, so it can
  re-emit. The re-emitted save, made against the now-current version,
  becomes the new version.

### 3.3 File identity generation

Default: on first save of a new document, generate the `file_id` as four
lowercase hexadecimal characters, a hyphen, and a slug derived from the
filename without its extension, for example `0f3a-acme-msa`. The four
characters are drawn at random and checked against every existing
`file_id` in the workspace and in the log directory; on a collision a new
value is drawn. The slug is fixed at creation and does not change when the
file is later renamed, because the `file_id` is immutable.

### 3.4 Rename and move

Default: rename changes the filename within the same directory. Moving a
document to another directory is the same operation with a different
target directory recorded in the engine's path bookkeeping; the
`file_id`, history, and aliases are unaffected. The agent surface keeps
the spec's single rename operation; the target directory is an engine
detail supplied by the caller's context, not a new user concept.

### 3.5 Tag and filename validation

Default: a tag must be a single word containing no whitespace and no `#`;
an invalid tag is rejected with an error rather than silently rewritten.
A filename must end in `.md` and must not contain a path separator.
Directory names are relative to the workspace root; absolute paths and
parent-directory escapes are rejected.

### 3.6 Timestamp format

Default: `updated` and log timestamps use UTC, second precision, in the
form `2026-11-05T14:22:31Z`. This remains ISO-8601, matches the spec's
style, and keeps log entries orderable when two saves occur within the
same minute.

## 4. Alternatives considered

- **Language.** Python is proposed because this workspace already
  standardises on Python with uv, YAML and SQLite support are immediate,
  and the engine is I/O-bound rather than compute-bound. TypeScript would
  suit a future web interface but adds a second toolchain for no present
  benefit. Go would produce a single binary, but its YAML and templating
  ergonomics are weaker for a document tool, and distribution as a binary
  is not a stated requirement.
- **Hash function.** The spec names blake3. The Python `blake3` package
  will be used. If that package were unavailable on a target machine, the
  fallback would be SHA-256 from the standard library, accepting longer
  blob names; this is a deployment fallback only, not a design choice, and
  the two must never be mixed inside one workspace.
- **Index.** SQLite, as the spec states, using only the Python standard
  library. A plain scan of frontmatter is kept as the Step 2 behaviour and
  as the rebuild path, so the engine still works if the index is deleted.
- **Concurrency.** Optimistic detection through `base_version` (Section
  3.2) plus atomic file replacement. No lock server and no multi-process
  write lock in the first version; two processes writing the same file at
  the same moment are handled by the conflict path, not prevented.

## 5. Package layout

```
md-versioning/
  pyproject.toml            # uv project; dependencies: blake3, PyYAML
  IMPLEMENTATION_PLAN.md    # this plan
  SPEC.md                   # the source spec, stored unchanged
  src/
    md_versioning/
      __init__.py           # public engine API only
      errors.py             # UnknownFile, InvalidTag, Conflict, ...
      frontmatter.py        # parse and serialise frontmatter + body
      store.py              # blobs and per-file JSONL logs
      index.py              # SQLite schema, updates, rebuild
      engine.py             # read, save, tag, untag, find, rename, history
      surface.py            # Step 5: agent operations + JSON-lines protocol
  tests/
    test_core.py            # Step 1
    test_tags.py            # Step 2
    test_index.py           # Step 3
    test_rename.py          # Step 4
    test_surface.py         # Step 5
    test_conflict.py        # Section 6 behaviour
  demo/
    run_demo.py             # end-to-end demonstration on a scratch workspace
```

Frontmatter serialisation is fixed: field order is `file_id`, `version`,
`tags`, `aliases`, `updated`; lists use flow style as in the spec example;
the body follows the closing fence unchanged, byte for byte.

## 6. Data formats

### 6.1 Log entry (one JSON object per line, engine-only)

```json
{
  "v": 8,
  "hash": "<blake3 hex of body>",
  "parents": ["<file_id>@7"],
  "tags": ["q3-review", "legal"],
  "aliases": ["acme-msa"],
  "intent": "tag legal",
  "ts": "2026-11-05T14:22:31Z"
}
```

A conflict entry lists two parents. A rename entry additionally carries an
internal `rename` object with the previous and new filename and directory;
`history` renders it in plain words and never shows the raw object.

### 6.2 SQLite index schema

```sql
CREATE TABLE files (
  file_id  TEXT PRIMARY KEY,
  dir      TEXT NOT NULL,
  filename TEXT NOT NULL,
  UNIQUE (dir, filename)
);
CREATE TABLE tags (
  file_id TEXT NOT NULL,
  word    TEXT NOT NULL,
  PRIMARY KEY (file_id, word)
);
CREATE TABLE aliases (
  file_id TEXT NOT NULL,
  alias   TEXT NOT NULL,
  PRIMARY KEY (file_id, alias)
);
```

Rebuild walks every `.md` file outside `.versioning/`, parses frontmatter,
and repopulates all three tables inside one transaction. Rebuild is
idempotent: running it twice produces the same contents.

## 7. Operation contracts

- **read(directory, filename)** — Resolve the path. If the file is absent,
  look the filename up in aliases, then in former paths. Return the parsed
  document (metadata plus body) or `None` when the name is unknown. If
  frontmatter is missing or malformed, repair it by assigning identity and
  defaults and rewriting the file atomically, then return the document.
- **save(directory, filename, body, tags?, intent?)** — Create the document
  if it does not exist (assigning a `file_id`, version 1, empty aliases).
  Otherwise apply the Section 3.1 guard, write the blob if it is new,
  append one log entry, bump the version, refresh `updated`, update the
  index, and rewrite the file atomically (temporary file in the same
  directory, then `os.replace`).
- **tag / untag(directory, filename, word)** — Validate the word, adjust
  the tag list without duplicates, and save with intent `tag <word>` or
  `untag <word>`. Tagging with an existing word, or untagging an absent
  word, is a no-op and writes no log entry.
- **find(tags)** — Return the `(directory, filename)` pairs whose documents
  carry every given tag (AND semantics). Before Step 3 this scans
  frontmatter; afterwards it queries the index. An empty tag list is
  rejected, because "every document" is a listing request the spec does
  not define.
- **rename(directory, filename, new_name)** — Validate the new name, fail
  if a different document already uses it, append the current filename to
  aliases, move the file, update the index path, and record one log entry
  with intent `rename <new_name>`.
- **history(directory, filename)** — Read the file's log and render one
  line per version: version number, intent in plain words, tags, and
  timestamp. No hashes, no parent information, no file_id.

## 8. Build order, deliverables, and exit criteria

Each step ends with its tests green before the next step begins. Estimates
are for guidance only and are not commitments.

**Step 1 — Core.** Frontmatter parsing, blob storage, JSONL log, atomic
rewrite, read / save / history.
Exit: saving the same document five times with three distinct bodies
produces exactly three log entries and version 3; an unchanged re-save
changes nothing on disk.

**Step 2 — Tags.** Tag and untag as wrappers over save; find by scanning.
Exit: three tagged documents are returned by a single-tag query, a
two-tag query returns only documents carrying both, and a tag-only change
produces a log entry (this is the Section 3.1 regression test).

**Step 3 — Index.** SQLite schema, incremental updates inside save, and a
full rebuild on startup when the index is missing or stale.
Exit: deleting `index.db` and restarting reproduces identical find
results; running rebuild twice changes nothing the second time.

**Step 4 — Aliases and rename.** Rename with alias recording and alias
fallback in read.
Exit: after a rename, reading by the old filename returns the document,
its history is unchanged in content and one entry longer, and its
`file_id` is identical to before.

**Step 5 — Agent surface.** The seven operations exposed as plain
functions and as a JSON-lines protocol (one request object per line with
an operation name and arguments; one response object per line with either
a result or an error). The accompanying prompt text uses only directory,
filename, and tag.
Exit: a scripted session performs create, edit, tag, find, rename, and
history entirely through the surface, and a scan of the surface's prompts
and outputs finds none of the hidden terms.

**Conflict check (with Step 5).** Two saves based on the same version: the
second is reported as a change conflict, receives the current document,
re-emits, and the resulting log entry records two parents while history
still renders in plain words.

## 9. Test matrix

| Area | Cases |
|---|---|
| Core save | new file; body edit; identical re-save; five saves with dedup |
| Guard (3.1) | tag-only change logs; rename-only change logs; no-change save does not |
| Frontmatter | missing fields repaired; field order stable; body preserved byte for byte |
| Tags | add; duplicate add is a no-op; remove; remove absent is a no-op; `#` and whitespace rejected |
| Find | one tag; two tags AND; unknown tag returns empty; before and after index rebuild agree |
| Rename | read by old name; alias accumulates over two renames; target-name collision fails; history follows identity |
| Index | rebuild idempotent; deleted index recovered; stale entry corrected by rebuild |
| Conflict | stale base reported; re-emission succeeds; entry has two parents; history hides parents |
| Atomicity | interrupted write simulation leaves either the old or the new file, never a partial one |
| Surface | all seven operations round-trip; hidden terms absent from outputs |

Tests use pytest with a temporary directory per test, following this
workspace's uv convention (`uv run pytest`).

## 10. Risks and open points

- **No delete operation exists in the spec.** Deleting a document is out of
  scope for this build. If deletion is wanted later it needs a spec
  decision, because it interacts with aliases and history retention.
- **Listing all documents is undefined.** Find requires at least one tag.
  A future "list a directory" operation would be a spec addition.
- **Single-writer assumption.** The conflict path handles sequential
  interleaving between agents. True simultaneous writes from separate
  processes are detected after the fact, not locked against; acceptable
  for the first version, worth revisiting only if real use shows it.
- **blake3 availability.** Verified installable in this environment
  through uv before Step 1 begins; the check is part of Step 1 setup, with
  a few-second timeout, and the SHA-256 fallback in Section 4 applies only
  if that check fails.

## 11. What approval starts

Approving this plan starts Steps 1 to 5 in order, in
`~/workspace/md-versioning/`, with the Section 3 defaults applied. The
result delivered back is the package, the passing test suite, and the demo
run output. Approving a smaller scope, for example Step 1 only, is equally
workable because each step ends in a runnable state.
