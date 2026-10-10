---
name: voicebox-local
description: Use when synthesizing audio with a reviewed local Voicebox profile through the opt-in connector.
---

# Local Voicebox audio

1. Call `voicebox_discover` to confirm health and list reviewed profiles; if unavailable, ask the operator to configure `VOICEBOX_URL`. Never invent a voice ID.
2. Ask the user which listed profile to use when not already specified. Only a human operator should add IDs to `VOICEBOX_REVIEWED_PROFILES` after reviewing voice provenance/consent.
3. Call `voicebox_synthesize` with `text`, `profile_id`, optionally `language`. Do not retry automatically: generation has cost, and a timed-out job may still complete remotely.
4. Include the exact returned `MEDIA:/absolute/path.wav` tag in the final response for native Discord audio attachment delivery. Do not substitute a Markdown link. For other platforms, follow their media capabilities.

Setup and safety limits: `plugins/voicebox/README.md`.
