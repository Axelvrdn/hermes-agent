# Actions cron Discord typées (#8)

Sur un job Discord continuable (`attach_to_session: true`) avec un `origin.user_id`, le bouton `Relancer` reste disponible. Les boutons optionnels sont configurés par job dans `discord_actions` (création via `cron.jobs.create_job(..., discord_actions=...)` ou `update_job(id, {"discord_actions": ...})`; les jobs historiques sans configuration restent inchangés) :

```json
{
  "actions": ["workout_checkin", "school_note", "obsidian_capture"],
  "workout": {"database": "/chemin/optionnel/workout.db"},
  "obsidian": {
    "vault": "/chemin/du/vault",
    "folder": "School",
    "allowed_folders": ["School"],
    "bridge_url": "https://passerelle.example/?file={file}"
  }
}
```

`workout_checkin` ouvre une modale native (épaule, genou, mollets et fatigue, entiers 0–10, commentaire optionnel) ; `school_note` ouvre une note/question rapide. Les soumissions sont enregistrées dans `<HERMES_HOME>/cron/discord_actions.sqlite3` avec ID de job, auteur, horodatage et expiration (7 jours). Le prochain prompt du *même job* lit les entrées non expirées comme données non fiables. Un plan d'entraînement conservateur est calculé localement au moment du check-in. L'adaptateur `workout.database`, facultatif et explicitement configuré, écrit aussi les nouveaux check-ins dans une table `checkins` du SQLite choisi ; ne pas pointer vers une base dont la table `checkins` possède un schéma différent sans adapter dédié.

`obsidian_capture`/`obsidian_save` archivent le brief livré en Markdown sous le dossier allowlisté ; le nom est déterministe par message/job et les clics répétés ne remplacent pas la note. Le lien HTTP est formé depuis `bridge_url` en substituant le chemin relatif encodé au placeholder `{file}`. Le dossier doit déjà exister ; les chemins absolus, `..` et liens symboliques de sortie sont refusés. Aucune de ces actions n'envoie de message à l'agent ni n'appelle le LLM. Le check-in adapte le contexte du prochain cron ; il ne force pas une relance automatique.

À vérifier lors d'une intégration réelle distincte : schéma exact de la base workout de l'installation, configuration de la passerelle et chemin du vault, ainsi que permissions du bot. Aucun service live n'a été modifié pour cette issue.
