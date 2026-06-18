# Privacy-Safe Codex Notify Example

`notify_safe.py` accepts the JSON payload passed to a Codex notify command. It
processes only `agent-turn-complete` and emits a small JSON record suitable for
later routing to a local file, notification service, or telemetry helper.

It never emits `input-messages`, `last-assistant-message`, raw prompt text, raw
`cwd`, or raw thread ID. Thread, turn, and cwd values are hashed with separate
namespaces. Set a private `CODEX_NOTIFY_HASH_KEY` to use HMAC-SHA256; an unkeyed
SHA-256 fallback is used otherwise. Hashes are pseudonyms, not anonymity: a
secret key is strongly recommended because predictable paths can be guessed.

## Example

Configure Codex to call the script according to the current official notify-hook
configuration format, passing the notify JSON as its argument. Test it directly:

```powershell
$env:CODEX_NOTIFY_HASH_KEY = "use-a-local-secret-not-committed-to-git"
$payload = '{"type":"agent-turn-complete","thread-id":"example-thread","turn-id":"example-turn","cwd":"C:\\work\\example","input-messages":["never exported"],"last-assistant-message":"never exported"}'
$payload | python .\tools\notify-safe\notify_safe.py
```

For stdin-based testing:

```bash
export CODEX_NOTIFY_HASH_KEY='use-a-local-secret-not-committed-to-git'
printf '%s' '{"type":"agent-turn-complete","thread-id":"example","cwd":"/work/private-project"}' | python3 tools/notify-safe/notify_safe.py
```

Project basename is disabled by default. It can leak a private client or project
name. Enable it only after an explicit privacy review:

```powershell
$env:CODEX_NOTIFY_INCLUDE_PROJECT_BASENAME = "1"
```

This helper could later feed Grafana annotations, local completion
notifications, stuck-session detection, or privacy-safe project grouping. Those
integrations are intentionally not implemented in Phase 0.
