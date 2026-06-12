# Spec 93 — Fix-Pack: Async Offload of CPU-Bound & Blocking Calls (requirements)

## 1. Summary

This fix-pack resolves **7 confirmed issues** where CPU-bound or blocking work runs
**inline inside `async def` handlers**, stalling Inkstave's single asyncio event
loop under load. Argon2 hashing/verification is deliberately expensive (tens to
hundreds of ms); SHA-256 over large uploads is CPU-bound; and the file-based email
sender performs synchronous filesystem I/O. Each is wrapped in
`await asyncio.to_thread(...)` so the blocking work executes on a worker thread
while the event loop stays responsive. **No behaviour, output, or control flow
changes** — only *where* the work runs.

**Severity breakdown:**
- major: 2 (`#1` login-path Argon2 verify, `#4` streaming upload SHA-256) — hottest paths
- minor: 5 (`#2, #3, #5, #6, #7`)

> This pack is implemented **after spec 90** (it is a late hardening pass) and
> **after spec 92** for the two shared files — see §2.

## 2. Context & dependencies

- **Depends on:** specs 01–90 (the services, compile-output persistence, history
  capture, and file mailer all exist), and **spec 92**, which edits two of the same
  files (`services/auth.py`, `services/user.py`).
- **Sequencing (important):** Per the numerical-order rule in `CLAUDE.md`, specs are
  applied in order. **Spec 93 must be applied AFTER spec 92** so that the
  `asyncio.to_thread` wrapping lands on top of spec 92's version of `services/auth.py`
  and `services/user.py`. Confirm spec 92 is implemented and its tests pass before
  starting; then make the smallest change to the *current* (post-92) lines. Line
  numbers below are indicative and may shift once spec 92 is applied — locate the
  call by name (`hasher.verify`, `hasher.hash`, etc.), not by line.
- **Affected areas:** backend only (auth, account, file upload, compile output,
  history capture, mailer) + a few focused unit tests.

### 2.1 Files in scope

Edit **only** these files.

```
backend/src/inkstave/services/auth.py
backend/src/inkstave/services/user.py
backend/src/inkstave/services/account.py
backend/src/inkstave/services/file_service.py
backend/src/inkstave/compile/outputs.py
backend/src/inkstave/history/capture.py
backend/src/inkstave/mailer/sender.py
backend/tests/unit/                       (new/updated unit test files may be added here)
```

> `services/auth.py` and `services/user.py` are **shared with spec 92** — apply this
> pack after spec 92 (see §2). All other files are exclusive to this pack. If a fix
> appears to require a file outside this set, stop and report.

## 3. Goals

- Every CPU-bound hash and blocking filesystem call listed in §4 runs off the event
  loop via `asyncio.to_thread` (or an equivalent stdlib thread offload).
- Results are **byte-for-byte identical** and control flow (timing mitigation,
  best-effort cleanup, streaming semantics) is preserved.
- No new dependencies; suite stays green and under the 2-minute budget.

## 4. Issues to fix

Each issue names the blocking call, why it stalls the loop, and the exact fix.
Use `await asyncio.to_thread(callable, *args)` — add `import asyncio` to the module
if not already imported.

### 4.1 — `#1` Login-path Argon2 verify runs inline (major · spec 06/08 auth)

- **File:** `backend/src/inkstave/services/auth.py` (`hasher.verify(...)`, ~lines 60, 62).
- **Problem:** The login flow calls `hasher.verify(...)` (Argon2) **inline** inside
  an `async def`. Argon2 verification is intentionally slow (tens–hundreds of ms) and
  fully blocks the event loop for that whole time — under concurrent logins this
  serialises every request on the loop. There are **two** verify calls: the real
  user hash, and the **dummy-hash timing-equalizer** that runs when the user is
  missing (to keep the response time constant and defeat user-enumeration timing
  attacks).
- **Fix:** Offload **both** calls: `await asyncio.to_thread(hasher.verify, <hash>, <password>)`.
  **Preserve the timing-attack mitigation** — when the user does not exist, still
  verify the supplied password against the dummy hash (now via `to_thread`) so the
  branch cost is unchanged. Keep the exception handling (`VerifyMismatchError` /
  invalid-credentials) and the rest of the control flow exactly as-is; only the
  call site is wrapped.

### 4.2 — `#2` Registration password hash runs inline (minor · spec 06/08 user create)

- **File:** `backend/src/inkstave/services/user.py` (`hasher.hash(data.password)`, ~line 53).
- **Problem:** User creation hashes the new password with Argon2 **inline** in an
  `async def`, blocking the loop for the duration of the (deliberately expensive)
  hash.
- **Fix:** `hashed = await asyncio.to_thread(hasher.hash, data.password)`. Store the
  resulting hash exactly as before; no format change.

### 4.3 — `#3` Change-password hash runs inline (minor · spec 59 account)

- **File:** `backend/src/inkstave/services/account.py` (`hasher.hash(new_password)`, ~line 69).
- **Problem:** `change_password` hashes the replacement password with Argon2 **inline**
  in an `async def`, blocking the loop.
- **Fix:** `hashed = await asyncio.to_thread(hasher.hash, new_password)`. Keep the
  surrounding current-password verification and persistence unchanged. (If the
  current-password verify in this same function is also an inline `hasher.verify`,
  offload it the same way for consistency — but do not change its semantics.)

### 4.4 — `#4` Streaming upload SHA-256 hashes inline in an async generator (major · spec 14 files)

- **File:** `backend/src/inkstave/services/file_service.py`
  (`hasher.update(chunk)` ~line 150 and `hasher.hexdigest()` ~line 162).
- **Problem:** The upload path consumes an async chunk stream and feeds each chunk to
  an incremental SHA-256 (`hasher.update(chunk)`) **on the event loop**, then calls
  `hasher.hexdigest()`. For large uploads this is meaningful CPU work that blocks the
  loop chunk-by-chunk. The function also performs **best-effort blob cleanup** if the
  upload fails partway — that must be preserved.
- **Fix (preserve streaming + cleanup):** Move the hashing off the loop while keeping
  streaming semantics. Pick the smaller-diff option of:
  - **(a) Per-chunk offload:** keep the incremental hasher but run each update off
    the loop: `await asyncio.to_thread(hasher.update, chunk)` inside the streaming
    loop, and `digest = await asyncio.to_thread(hasher.hexdigest)` after; **or**
  - **(b) Hash the assembled bytes once:** if the implementation already buffers/has
    the full bytes available at the point of digest, compute
    `digest = await asyncio.to_thread(lambda b=data: hashlib.sha256(b).hexdigest())`
    (or `hashlib.sha256(data).hexdigest` via `to_thread`) in one offloaded call.

  Prefer **(a)** if chunks are streamed straight to storage (do not buffer the whole
  file in memory just to satisfy this fix). **Preserve** the existing best-effort
  blob cleanup on failure (the `try/except`/cleanup that removes a partially written
  blob) and the final stored digest value exactly. Do not change chunk size, storage
  writes, or the returned digest format.

### 4.5 — `#5` Compile-output SHA-256 runs inline (minor · spec 23 outputs)

- **File:** `backend/src/inkstave/compile/outputs.py`
  (`hashlib.sha256(data).hexdigest()` in `async def persist()`, ~line 123).
- **Problem:** `persist()` hashes the full output blob with SHA-256 **inline** in an
  `async def`. For multi-MB PDFs/logs this blocks the loop.
- **Fix:** `digest = await asyncio.to_thread(lambda b=data: hashlib.sha256(b).hexdigest())`
  (or pass `hashlib.sha256(data).hexdigest` appropriately to `to_thread`). Identical
  hex digest; no other change to `persist()`.

### 4.6 — `#6` History-capture SHA-256 runs inline (minor · spec 36 history)

- **File:** `backend/src/inkstave/history/capture.py`
  (`hashlib.sha256(update).digest()` in `async def capture_update()`, ~line 86).
- **Problem:** `capture_update()` computes a SHA-256 **digest** of the CRDT update
  **inline** in an `async def`. Hot path during collaborative editing; blocks the loop.
- **Fix:** `digest = await asyncio.to_thread(lambda u=update: hashlib.sha256(u).digest())`.
  Note this uses `.digest()` (raw bytes), not `.hexdigest()` — keep it byte-identical.
  No other change to `capture_update()`.

### 4.7 — `#7` File email sender does blocking filesystem I/O (minor · spec 39 mailer)

- **File:** `backend/src/inkstave/mailer/sender.py`
  (`self._dir.mkdir(...)` ~line 61 and `path.write_text(...)` ~line 63 in the file
  email sender's `async def send()`).
- **Problem:** The file-based email sender (writes each email to disk for
  dev/testing) calls `self._dir.mkdir(...)` and `path.write_text(...)` — **synchronous
  blocking filesystem I/O** — directly inside `async def send()`.
- **Fix:** **Materialize the JSON/string payload first** (do the in-memory
  serialisation on the loop, it is cheap), then offload both blocking calls:
  - `await asyncio.to_thread(self._dir.mkdir, parents=True, exist_ok=True)` (preserve
    whatever `mkdir` kwargs are currently used),
  - `await asyncio.to_thread(path.write_text, payload)` (preserve the encoding /
    arguments currently passed).

  The written file contents and path must be identical. Do **not** change the
  SMTP or console senders (only the file sender's blocking I/O is in scope).

## 5. Acceptance criteria

Each is independently verifiable.

1. **`#1`** Both `hasher.verify(...)` calls in `services/auth.py` (real and dummy-hash)
   execute via `asyncio.to_thread`; login still verifies against the dummy hash when
   the user is missing (timing mitigation intact); valid/invalid credential outcomes
   are unchanged.
2. **`#2`** `services/user.py` hashes the registration password via
   `asyncio.to_thread(hasher.hash, ...)`; the stored hash is unchanged in format.
3. **`#3`** `services/account.py` `change_password` hashes the new password via
   `asyncio.to_thread`; current-password verification and persistence are unchanged.
4. **`#4`** `services/file_service.py` performs SHA-256 hashing off the event loop
   (per-chunk `to_thread` update or a single offloaded digest); streaming semantics
   and best-effort blob cleanup on failure are preserved; the stored digest is
   byte-identical.
5. **`#5`** `compile/outputs.py` `persist()` computes its SHA-256 hex digest via
   `asyncio.to_thread`; the digest value is unchanged.
6. **`#6`** `history/capture.py` `capture_update()` computes its SHA-256 **raw**
   digest via `asyncio.to_thread`; the digest bytes are unchanged.
7. **`#7`** The file email sender offloads `mkdir` and `write_text` via
   `asyncio.to_thread`; the written file path and contents are identical; SMTP/console
   senders are untouched.
8. No new dependency is added (no `aiofiles`); only stdlib `asyncio.to_thread` is used.
9. The full test suite is green and runs in **< 2 minutes** (verified via
   `just test-timed`).

## 6. Overleaf reference (study only — never copy)

> **No Overleaf equivalent.** This is a Python/asyncio-specific event-loop hygiene
> fix (offloading CPU-bound hashing and blocking I/O to threads). Overleaf is a
> Node.js codebase with a different concurrency model and shares no code with
> Inkstave; there is nothing to reference for this pack. Implement from the spec.

## 7. Test plan

> Keep the combined suite under 2 minutes. No real LaTeX/SMTP/Redis; mock/stub.

- **Stay green (no behaviour change):** All existing tests for the affected paths must
  continue to pass unchanged:
  - auth/login + register + change-password (services/auth, services/user,
    services/account, and their integration HTTP tests),
  - file upload (`file_service`) including the failure/cleanup path,
  - compile-output persistence (`compile/outputs`),
  - history capture (`history/capture`),
  - the **file** email sender suite (`mailer/sender`).
  These tests already use **low Argon2 cost parameters** in the test config, so the
  offload does not change their runtime.
- **New / updated focused tests (optional but recommended), under `backend/tests/unit/`:**
  - A lightweight test asserting the **offload actually happens** for the Argon2
    verify path — e.g. monkeypatch `asyncio.to_thread` to record that it was called
    (and still delegate to the real function so the result is correct), then drive the
    login service and assert `to_thread` was invoked with `hasher.verify`. Keep it
    minimal; one such test for the verify path is sufficient to lock in the pattern.
  - Optionally, a similar assertion for the file sender's `write_text` offload.
- **Performance/budget note:** `asyncio.to_thread` on fakes/low-cost hashers is
  effectively instant, and the new tests are in-memory/mocked, so there is **no
  impact on the 2-minute budget**. Do not add real sleeps or real high-cost Argon2
  parameters. Run `just test-timed` (xdist) to confirm.

## 8. Definition of Done

- [ ] All 7 issues in §4 fixed (each named blocking call offloaded via
      `asyncio.to_thread`), applied **on top of spec 92** for the two shared files.
- [ ] All acceptance criteria in §5 pass.
- [ ] Existing tests for the affected paths stay green; any optional offload-assertion
      tests in §7 are written and green.
- [ ] Behaviour/outputs are byte-for-byte unchanged (hashes, written files, timing
      mitigation, streaming, cleanup).
- [ ] No new dependency added; only stdlib `asyncio.to_thread` used.
- [ ] Full suite runs in **< 2 minutes** (`just test-timed`).
- [ ] Lint/format/type-check clean (`ruff`, type checker as configured).
- [ ] Edits limited to the files in §2.1 — no out-of-scope files touched.
- [ ] No Overleaf code copied (no Overleaf equivalent exists for this pack).
