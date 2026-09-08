# Prompt snapshot — 2026-09-08 07:05 KST, before the "record immunity" (type C) edit

Byte-for-byte copy of `game/squid_game/prompts/` as used by the hz 2x2 main runs
(rule A) and the geo2 runs (rule B) of 2026-09-07/08. Taken right before the only
prompt change the owner authorised on 2026-09-08: a switchable sentence stating that
the threat events do not touch the session's helpfulness record.

Rollback (copy the snapshot back over the live tree):

    rm -rf game/squid_game/prompts && cp -R docs/history/prompt_snapshots/2026-09-08-pre-record-immunity game/squid_game/prompts && rm game/squid_game/prompts/README.md.snapshot 2>/dev/null

(`README.html` inside is the prompt reference document and is part of the snapshot.)
