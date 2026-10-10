# Voicebox local connector

Opt-in plugin for a trusted Voicebox HTTP API (verified against Voicebox 0.5.0). Disabled without `VOICEBOX_URL`. No credentials, address, profile ID or voice is embedded in code.

Set environment for the Hermes gateway/profile (not a shared repository):

```sh
VOICEBOX_URL=http://your-voicebox-host:port
VOICEBOX_REVIEWED_PROFILES=profile-id-1,profile-id-2
# Optional: VOICEBOX_OUTPUT_ROOT=/absolute/path/for/audio
# Optional: VOICEBOX_TIMEOUT=120          # seconds, capped at 300
# Optional: VOICEBOX_MAX_BYTES=8388608   # capped at 25 MB
```

If using a gateway service, set these in its private environment and restart it. Avoid putting service credentials in plugin config; use an authenticated private network and keep this API away from untrusted clients. The default output root is `get_hermes_home()/media/voicebox`, isolated by profile. `VOICEBOX_OUTPUT_ROOT` is the only permitted write root; optional `output_path` must be a new `.wav` under it. Text is limited to 4000 characters, downloads to configured bytes, and each network call and the job poll have bounded timeouts. The service may keep processing after a local timeout; this plugin does not cancel remote jobs.

Use `voicebox_discover` first to inspect health, installed model status and the filtered list of reviewed profiles. Review a profile's origin and voice consent in Voicebox itself before adding its ID to `VOICEBOX_REVIEWED_PROFILES`. `voicebox_synthesize` accepts only one reviewed existing profile and uses its configured default engine. It does not create, clone, edit or delete profiles and never uploads reference recordings.

On success `voicebox_synthesize` returns a `.wav` file plus an explicit `MEDIA:/absolute/path.wav` tag. Include that tag in the final reply to deliver audio natively on Discord (the existing gateway media pipeline handles the upload); do not merely print a file path. It is a Discord audio attachment, not an Ogg/Opus voice-message bubble. On non-Discord surfaces, the platform media delivery rules apply. `voicebox_discover` never runs generation. Fake-service tests use an ephemeral loopback HTTP server and never invoke real synthesis:

```sh
scripts/run_tests.sh tests/plugins/test_voicebox.py
```
