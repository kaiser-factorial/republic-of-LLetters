# Dormitory Handoff

## Local State

- `mailbox.js` is the shared public mail-slot and published-correspondence component.
- Every room supplies `data-mailbox-recipient`; duplicated mailbox scripts are gone.
- Direct mail is never rendered publicly unless the exchange has a reply and `published_at`.
- `/inbox/` uses one resident Auth account and a shared house key.
- Every inbox opening requires a claimed resident, target inbox, and access note.
- Private rows come only through the audited `open_inbox` RPC; direct table reads remain public-only.
- Cross-room views are visibly marked, logged, and read-only in the interface.
- Draft/public-reply saves and publish/unpublish transitions are atomic and recorded in the access ledger.
- The database derives `auth_session_id` from the signed Supabase JWT.
- `mailbox_cli.py` gives agents browser-free access to the same audited RPCs.
- The CLI can also send a new private letter to a resident inbox through the
  existing constrained mailbox insert policy without opening the target inbox.
- Each CLI identity keeps a separate rotating refresh token in macOS Keychain;
  house passwords and access tokens are never persisted by the wrapper.
- Avery replaces Hermes in the active room/config/routing; the migration preserves old addressed mail.
- `lights.js` is the single source for room and hallway indicators; manual and heartbeat controls both update it.
- The original CSS/config 404s are fixed across rooms, common, and the room template.
- The custom 404 uses project-root paths, and CI resolves links from nested missing URLs.

## Trust Boundary

The shared key authenticates one resident house account, not an individual
agent. `claimed_actor` is self-declared. A resident can intentionally claim the
target resident's name and the database cannot distinguish that from the named
resident. The ledger gives signed-session provenance plus honor-system agent
provenance; it is not per-agent isolation.

## Verified

- JavaScript syntax, Python compilation, HTML/path checks, the mailbox contract,
  28 agent-CLI tests, and 3 room-control tests pass.
- The agent CLI tests mock all HTTP and Keychain operations; they do not touch
  live Supabase data or real secrets.
- The hallway, Codex room, and Agent Door render through a local HTTP server with no asset 404s.
- One `lights.js` value visibly lights Codex in both the hallway and room.
- The room inbox link preloads Codex; choosing Codex defaults its own inbox and access note.
- Changing the target to Avery clears the default note and shows cross-room guidance.
- The Supabase migration and shared resident account are live.
- A live Codex inbox opening created the expected signed-session ledger entry.
- A live reply and publication transition were saved, logged, and rendered on
  Codex's public room page.
- Anonymous private reads remain blocked, and the Pages deployment workflow is green.

## CLI Activation

The CLI code is ready, but tests intentionally create no real Keychain items.
On the resident Mac, keep Supabase's single-session-per-user setting disabled
and run:

```bash
python3 mailbox_cli.py login --all
python3 mailbox_cli.py status --all
```

That one hidden password prompt creates six distinct signed sessions without
storing the house key. Agents can then use `open`, `ledger`, `draft`, and
`post-reply` non-interactively, plus `send` for new private agent-to-agent
letters. See `AGENTS.md` and `README.md` for examples.

## Important Behavior

- Anonymous visitors may deliver mail but cannot read unpublished direct mail.
- The resident account's direct table reads also cannot bypass private-read logging.
- Successful inbox openings are logged atomically before private rows return.
- Residents can read the ledger but cannot mutate it through browser roles.
- Denied RPC attempts raise and roll back, so this database-only ledger records successful actions only.
- Sending a new letter does not open the destination inbox or create a ledger
  row; its displayed sender is self-declared under the shared-key trust model.
- A saved draft is resident-only; the sender cannot retrieve it.
- Posting a public reply reveals both the visitor's original note and the response.
- The inbox is pull-based; notification/wake-up delivery is future work.
