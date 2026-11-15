# Durable local correction-loop storage

`meshvenn_engine.loop_store.LoopStore` is a filesystem adapter. The pure loop
machine owns phase transitions, budgets, dispatch reservations, reconciliation
and acceptance. Storage does not infer quality, contact a provider or parse GLB.
The host configures its root; an agent action must not accept arbitrary roots.

```python
from meshvenn_engine.loop_store import LoopStore

store = LoopStore("/host/configured/meshvenn-runs")
store.create("session_001", {"phase": "new", "dispatches": []})
state = store.load("session_001")
state = store.update("session_001", pure_machine_transition)
digest = store.put_artifact(glb_bytes, expected_sha256=expected_sha256)
assert store.read_artifact(digest) == glb_bytes
snapshots = store.history("session_001")
```

The synchronous public interface is:

| Operation | Result |
| --- | --- |
| `LoopStore(root, *, lock_timeout=10.0, max_artifact_bytes=268435456)` | Trusted host configuration |
| `create(session_id, state: dict)` | `None`; rejects an existing committed session |
| `load(session_id)` | Independent JSON dictionary for the committed head |
| `update(session_id, callback)` | Independent committed dictionary |
| `history(session_id)` | Tuple of committed dictionaries, oldest first |
| `put_artifact(data: bytes, expected_sha256=None)` | Lowercase SHA-256 string |
| `read_artifact(sha256)` | Exact verified bytes |
| `has_artifact(sha256)` | Verified presence; `False` only when absent |

Session IDs match `[A-Za-z0-9][A-Za-z0-9_-]{0,127}`. A fixed on-disk prefix also
allows IDs such as `CON` on Windows without using reserved filesystem names.
State is a JSON object with only finite JSON values: no tuples, callables,
objects, NaN or infinity. Canonical UTF-8 state is limited to 32 MiB, 2,000,000
JSON nodes and nesting depth 64. A session permits 4,096 revisions; `history`
rejects an aggregate larger than 256 MiB of serialized states rather than
silently truncating it. Artifact bytes default to 256 MiB and may be configured
up to 512 MiB. Lock waits are finite and configurable up to 120 seconds.

## Transactions and restart

Each session uses a permanent lock file. Windows uses `msvcrt` byte-range locks;
POSIX uses `flock`. The lock covers reading the current head, running the callback,
validating its returned state, publishing a revision and replacing the head.
It also serializes creation, reads and history snapshots. Separate store objects
and separate processes use the same lock. Closing the descriptor, process exit
or process termination releases the OS lock. Callbacks must be pure, short JSON
transitions: no provider calls, nested store calls or other blocking I/O.

A callback receives a fresh decoded state. Mutating it and raising an exception
does not change the stored head. A successful update publishes a new revision
even if its state equals the previous state; repeated values remain visible in
history. Application idempotency and dispatch IDs belong to the pure machine.

Before a provider call, persist the machine's dispatch reservation with
`update`. Call the provider outside the callback and outside the lock. On
restart, reconcile the stored dispatch record; the store cannot promise that
an external provider executed exactly once.

Revision files contain a version, session ID, sequence, parent digest and state.
Their filenames are SHA-256 addresses of the complete canonical envelope.
Publication writes and `fsync`s a complete temporary file, then installs its
immutable address without replacing an existing address. POSIX also `fsync`s
directories. Windows uses same-directory `MoveFileExW` with `WRITE_THROUGH` after
the file `fsync`. The small head pointer is replaced atomically only after the
revision is published. Durability ultimately depends on the filesystem and
storage device honoring their flush/rename guarantees; network filesystems are
not qualified by these local-filesystem tests.

A crash after revision publication and before head publication leaves the
previous head authoritative. The unused revision is an orphan, excluded from
history. Retrying the same transition can reuse that verified immutable revision.
An I/O error after head publication can be an uncertain commit: reload/reconcile
the session before retrying any external effect. No rollback or in-place repair
of accepted evidence is performed.

`load` verifies the head and current revision. `history` additionally verifies
every reachable ancestor and its contiguous sequence. Historical corruption
does not disappear behind a shortened returned history. Unreachable orphan
files and temporary files do not become accepted revisions. Cleanup, retention
and backups are host operations, outside this adapter.

## Integrity and errors

Artifacts are opaque bytes. The adapter does not rewrite, sanitize, reinterpret
or certify them. Reusing an address verifies existing bytes and leaves the
accepted file untouched. Corruption is rejected, including an attempt to put the
original bytes back at an already corrupt address. Reads and presence checks
rehash content. Observed symlinks, reparse points and nonregular files are rejected.
The host owns the root and must not let unrelated processes mutate its directory
tree; this is not an adversarial-filesystem security boundary.

Invalid IDs, values, expected hashes and configuration raise `ValueError`.
`LoopStoreError` extends the library's `EngineError` and exposes stable `code`,
`message` and `details` fields:

- `session_not_found`, `session_exists`
- `artifact_not_found`
- `store_corrupt`, `store_unavailable`, `store_lock_timeout`, `store_limit`

Callback exceptions abort the transition. Ordinary callback exceptions propagate;
an `OSError` is normalized as `store_unavailable`. No error is interpreted as
permission to regenerate or overwrite original evidence.

Run the focused tests with `python -m unittest tests.test_loop_store -v`. They
exercise two real writer processes, restart/redo, termination while locked,
an actual process crash between revision and head publication, corruption and
exact GLB byte preservation. POSIX link rejection runs where supported; Windows
hosts without symlink privileges explicitly skip that test.
