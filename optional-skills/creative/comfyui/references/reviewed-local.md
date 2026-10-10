# Reviewed local ComfyUI integration

This is the **opt-in local** path for issue #6; the existing `run_workflow.py` remains a powerful manual tool accepting arbitrary graphs and is **not** the unattended-agent path. This client accepts only a manifest entry with a SHA-256 pinned API-format workflow and narrowly typed input overrides. No model downloads, custom-node installation, or GPU work run during inventory. A manifest is an operator trust decision: review the node types, model choices, filename prefixes, and installed custom-node Python before adding a template. A hash guards accidental or unreviewed graph edits, not a malicious operator who can change both files.

## Inventory and boundaries

Local ComfyUI exposes `GET /system_stats`, `GET /object_info` (node class inventory including installed custom nodes), `GET /queue`, `GET /history/{prompt_id}`, `GET /view`, `POST /prompt`, `POST /queue` (`delete` queued IDs), `POST /interrupt` (global interrupt), and `WS /ws?clientId=...` (`progress`, `executing`, `executed`, `execution_success/error/interrupted`). The client reports system, classes, reviewed template names, WS URL, and the artifact root. An API response cannot reliably distinguish builtin from custom node classes; compare `/object_info` to the approved graph and inspect custom-node installation separately. No custom-node install endpoint is invoked. The local ComfyUI output root is server-owned and may differ from the Hermes delivery root: artifacts are retrieved from `/view` and written under the latter. Local server path metadata never becomes an arbitrary filesystem read.

Select `--host` from trusted operator configuration (for Axel's LAN this may be `http://100.100.0.5:8188`; never bake it into the core), `--manifest` an operator-reviewed JSON, and `--output-root` a subdirectory of `$HERMES_HOME/cache/images`, `/videos`, `/audio`, or `gateway.media_delivery_allow_dirs`. The latter is bridged through `HERMES_MEDIA_ALLOW_DIRS` at gateway startup. An output root outside these roots is rejected. In strict gateway deployments also set `gateway.strict: true` and `gateway.trust_recent_files: false` for pure-allowlist enforcement. Keep the output root private to this integration; the gateway revalidates paths before delivery.

```text
python optional-skills/creative/comfyui/scripts/reviewed_local.py \
  --host http://127.0.0.1:8188 \
  --manifest optional-skills/creative/comfyui/reviewed-templates.json \
  --output-root "$HERMES_HOME/cache/images/comfyui" inventory
```

`run sd15-image --params '{"prompt":"a sunrise","steps":12}' --timeout 300` submits, polls history/queue and downloads files. It emits JSON with `artifacts` and `discord_message` (`MEDIA:<absolute-path>` lines). Send that text as the bot's final Discord message on its **authorized destination**; the gateway attachment pipeline performs the actual delivery and its own media check. Do not post to another channel or send a raw path as a privileged attachment. The script itself does not have Discord credentials and does not autonomously post. `submit` is an advanced short-lived operation returning a prompt ID; use `run` for completion/collection. For interactive progress, call `ComfyLocal.progress(prompt_id, ws_frames)` with decoded WebSocket frames from the reported URL in the same process; it discards frames from other prompts. Polling is the reliable fallback. `ComfyLocal.cancel(prompt_id)` removes a queued owned job; it interrupts a running job only if it is the **sole** running job because `/interrupt` is server-wide. Ownership is in-process, so resume/recovery after process restart is not provided; a timeout does not cancel the server job. Do not claim delivery merely because a file was downloaded.

## Review procedure

1. Export an API-format graph. Inspect all `class_type`s, inputs, checkpoint, path/string inputs, custom nodes, output node(s), and output size. Remove dangerous/unnecessary nodes. The shipped reviewed starter is SD1.5 text-to-image only; it requires the named checkpoint on the server. This has not been exercised against Axel's GPU.
2. Put the graph under the manifest directory, record its relative `file` and SHA-256. Add only named scalar input overrides with `{node,input,type}` and either `min/max` for integer or `max_length` for text. Never expose `class_type`, graph links, checkpoint names, or filesystem paths as parameters. No request may supply a workflow path or raw graph.
3. Test with a fake service, then with explicit user consent on the real server if desired. Changing the graph means reviewing and updating its hash. Avoid large batches and installing custom nodes on an agent's request.

Natural-language mapping: “create an SD1.5 image of X” → `sd15-image` with `prompt=X`; optional “N steps” → `steps` within 1–60, “seed N” → `seed` in the manifest range. “AnimateDiff video”, “Flux”, “upscale”, “inpaint”, or “run my JSON” → **no reviewed template yet**; ask for operator review and pin a new graph. Never route these to the manual arbitrary-graph scripts by default. A request for Cloud belongs to the `comfy-cloud` MCP route described in the existing skill, not this local client.

Security limitations: ComfyUI custom nodes can execute arbitrary Python; pinning a graph does not sandbox the ComfyUI server. HTTP transport has a no-redirect policy and size cap but assumes a trusted server/network. `POST /interrupt` cannot atomically target one job; avoid shared/multi-user servers. Artifact names from the server are treated as untrusted. Jobs and ownership are deliberately process-local.
