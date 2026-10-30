Main2 credential routing (2026-10-28)
==================================

The Windows CurrentUser DPAPI vault now supports five named slots. Existing
slot identities are unchanged: `primary` is Main1; `primary2` is Main2;
`backup`, `third`, and `fourth` remain the three original secondary APIs.
Keys are never included in result workbooks, configuration or console logs.

The active batch controls retain a global cap of eight HTTP requests. Main2
inherits the four primary lanes. Three baseline lanes use the secondary APIs,
and one floating lane rotates among healthy secondary APIs. Unavailable lanes
move to another healthy key, including Main2; a single healthy key may carry up
to eight requests while the global cap stays eight. Provider concurrency limits
may reduce actual throughput. If every key is unavailable the queue waits for
recovery; it does not invent simulation answers.

The user reported that Main1 has exhausted its allowance for three days. It has
zero baseline lanes and a three-day suspension in `api_suspended_until`. After
the hold and recorded cooldown expire it can receive a real decision as a
recovery probe and can subsequently carry borrowed capacity. Other refused keys
are probed after ten minutes, or later if the provider specifies Retry-After.

The active batch remains in:
`D:/Codex/runs/V7_Optimized_20261027_145124`.
Cooperative pause drains in-flight responses before the control process exits.
The pinned maintenance manifest verifies that prompts, model, population,
experimental factors and per-case budgets are unchanged. Successful answer
caches and completed checkpoints are reused on resume.

To add Main2 to a four-slot deployment, with the controller stopped:
`python scripts/manage_api_keys.py add-primary2`.
Then migrate the routing-state slot maps and per-key capacities before resuming.
For an existing Main2: `python scripts/manage_api_keys.py set-slot --slot primary2`.
The tool requests the credential with hidden input.
