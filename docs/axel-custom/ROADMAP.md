# Roadmap

## Phase 1 — Fork and maintenance baseline

- [x] Create `Axelvrdn/hermes-agent`.
- [x] Separate the development checkout from the running installation.
- [x] Port and test the existing Discord cron approval customization.
- [ ] Add CI for custom commits and upstream-rebase validation.
- [ ] Define a tagged deployment and rollback procedure for `/home/axel/.hermes/hermes-agent`.
- [ ] Add a scheduled upstream-drift report to the appropriate Discord `inbox` channel.

## Phase 2 — Discord improvements

- [x] Produce a current-upstream porting matrix for the FRFlo Discord commits.
- [ ] Port only missing user-visible behavior; avoid importing obsolete architecture wholesale.
- [ ] Add Components V2 progressively behind compatibility fallbacks.
- [ ] Validate message edit/delete synchronization without breaking session role alternation or prompt caching.
- [x] Extend interactive cron controls beyond the calendar-specific protocol through a generic, typed action contract.
- [x] Add deterministic `Relancer` actions to continuable Discord cron deliveries.
- [x] Resolve calendar approval buttons through a local script instead of an LLM interaction.
- [ ] Add interactive input modales (`discord.ui.Modal` + `TextInput`):
  - [ ] **Check-in / Douleurs du jour** (pour le cron workout `a07f7b874d27`) : modal avec notation douleur (épaule, genou, mollets) + fatigue/ressenti, mise à jour directe de la base sqlite `checkins` et recalcul immédiat du plan.
  - [ ] **Saisie de note / question rapide** (pour le cron scolaire `eefcdf90b2c1`) : modal pour consigner une question/remarque directement dans la note de révision ou le brief.
- [ ] Add an Obsidian Vault Quick Action button (adaptation du bouton d'export .md de FRFlo) :
  - [ ] Bouton **« 📝 Créer note Obsidian »** : crée ou synchronise un fichier Markdown structuré directement dans le coffre `/home/axel/Documents/Obsidian Vault/` avec métadonnées YAML et lien de retour Obsidian (`obsidian://`).
- [ ] Add per-job action configuration and additional reviewed actions such as refresh, acknowledge, cancel and export.
- [ ] Contextual initialization on new conversation (Turn 1):
  - [ ] Extract topic signals from the first prompt, thread title, and Discord forum applied tags.
  - [ ] Automatically query relevant notes via Obsidian MCP (`search_notes`, index matching).
  - [ ] Automatically recall past conversations via session search (`session_search` / `state.db`).
  - [ ] Inject retrieved context into Turn 1 system/session prologue without violating prompt caching invariants.


## Phase 3 — Voicebox

- [ ] Inventory the live Voicebox API and authentication model.
- [ ] Choose plugin vs MCP based on whether operations must be first-class model tools.
- [ ] Implement health discovery, synthesis, voice selection, output retrieval, and Discord audio delivery.
- [ ] Add timeouts, file-size limits, allowed-output roots, and deterministic tests with a fake service.

## Phase 4 — ComfyUI

- [ ] Inventory installed workflows, custom nodes, API endpoints, and output directories.
- [ ] Implement workflow-template submission rather than arbitrary graph execution by default.
- [ ] Add progress polling/WebSocket updates, cancellation, artifact collection, and Discord delivery.
- [ ] Keep generated artifacts within configured media-delivery allowlists.
- [ ] Add a skill that maps natural-language creative requests onto reviewed workflow templates.

## Phase 5 — Upstream contribution

- [ ] Split generally useful changes from host-specific behavior.
- [ ] Open focused upstream PRs where behavior is broadly applicable.
- [ ] Keep Axel-specific integrations in plugins or a separate plugin repository when upstream policy requires it.
