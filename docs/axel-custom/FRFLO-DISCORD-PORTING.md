# Analyse de portage — FRFlo Discord

Source étudiée : `FRFlo/hermes-agent`, branche `discord-message-session-sync`.

Commits propres à cette série :

1. `c08cca2b1b` — décomposition de l'adaptateur Discord.
2. `62d25ce187` — Discord Components V2.
3. `10a5e41173` — synchronisation des sessions avec les modifications de messages.
4. `17e2dbf4ae` — réconciliation des mutations et corrélation des réponses.
5. `c9d93070d9` — libération de la session avant la réadmission d'un message modifié.

## Conclusion

Ne pas fusionner ou cherry-pick cette branche en bloc. Elle apporte de bonnes idées, mais repose sur une base ancienne alors que l'upstream a continué à modifier les autorisations, les sessions, la livraison et l'adaptateur Discord. Les fonctionnalités doivent être portées séparément avec les invariants et les tests de la version actuelle.

## Matrice de décision

### `c08cca2b1b` — décomposition de l'adaptateur

**Comportement visible**

- Principalement un refactoring.
- Ajoute également une normalisation des URI de fichiers Windows pour les envois de plusieurs images.

**Architecture FRFlo**

- Répartit commandes, événements, vues, autorisation, messagerie, sessions, threads, voix et cycle de vie dans des modules spécialisés.
- Conserve `adapter.py` comme façade.

**État upstream actuel**

- L'adaptateur reste largement concentré dans `plugins/platforms/discord/adapter.py`.
- Certaines responsabilités sont déjà sorties sous forme de mixins ou modules adjacents.

**Décision**

- **Redessiner progressivement.**
- Ne pas remplacer le fichier actuel par les modules FRFlo : cela écraserait des correctifs upstream récents.
- Extraire une responsabilité à la fois, avec tests de comportement avant/après.
- Isoler le correctif Windows dans un commit indépendant.

### `62d25ce187` — Components V2

**Comportement visible**

- Utilisation de Components V2 pour les messages statiques, pièces jointes, messages de forum et interactions compatibles.
- Repli vers le transport Discord historique en cas d'incompatibilité.
- Amélioration des sélections multiples et de la saisie libre.

**État upstream actuel**

- L'upstream utilise encore principalement `content`, les embeds et `discord.ui.View`.
- Les contrôles interactifs et leurs autorisations existent déjà, avec des protections plus récentes qu'il faut conserver.

**Décision**

- **Portage progressif, pas de cherry-pick.**
- Étape 1 : constructeur V2 pour messages statiques.
- Étape 2 : fichiers et forums.
- Étape 3 : prompts interactifs.
- Garder les voies historiques pour le streaming, la voix et les éditions non compatibles.
- Un repli ne doit être tenté qu'après un rejet certain, afin d'éviter les doubles envois après un succès ambigu.

### `10a5e41173` — synchronisation des mutations

**Comportement visible**

- L'édition d'un message utilisateur rembobine le transcript à ce tour, retire les réponses Discord corrélées et relance la génération.
- La suppression d'un message archive ce tour et sa suite.
- La suppression d'une réponse du bot peut remonter au message utilisateur d'origine.

**État upstream actuel**

- Les événements `message_edited` et `message_deleted` sont déjà normalisés.
- Les IDs de messages de plateforme existent dans les métadonnées.
- La base sait rembobiner un transcript, mais le gateway ne relie pas encore automatiquement les événements Discord à ce mécanisme.

**Risques**

- Interrompre une session avant d'avoir confirmé qu'une cible de rembobinage existe.
- Attribuer des fragments de réponse au mauvais tour lors de générations concurrentes.
- Supprimer des messages distants sans corrélation certaine.
- Une suppression Discord ne prouve pas à elle seule l'identité de la personne ayant supprimé le message.

**Décision**

- **Redessiner comme fonctionnalité opt-in.**
- Persister une association explicite : session + message entrant + génération → tous les IDs de sortie.
- Valider la cible et les gardes transactionnelles avant toute interruption ou suppression distante.

### `17e2dbf4ae` — réconciliation

**Comportement visible**

- Corrige et complète la détection des cibles de rembobinage.
- Propage la corrélation aux réponses finales produites par édition d'un message de streaming.

**Vérification de la branche finale**

- Le schéma final utilise bien `target_message` de façon cohérente entre `rewind_from_platform_message()`, le gateway et les tests.

**Décision**

- **Intégrer les principes au nouveau design de synchronisation.**
- Ne pas porter ce commit seul : il dépend du modèle de données et du traitement introduits par le commit précédent.

### `c9d93070d9` — libération avant réadmission

**Comportement visible**

- Libère le créneau de session occupé avant de réadmettre le message modifié.
- Évite que l'édition soit traitée comme un nouveau message arrivant dans une session encore occupée.

**État upstream actuel**

- `_interrupt_and_clear_session(..., release_running_state=True)` fournit déjà le mécanisme général.
- Il manque le câblage spécifique à la synchronisation des mutations Discord.

**Décision**

- **Réutiliser immédiatement ce principe dans le futur design**, mais pas comme patch isolé.
- Tester qu'une ancienne génération ne peut plus écrire après le rembobinage ni libérer le créneau de sa remplaçante.

## Ordre de réalisation

### 1. Contrats et sûreté

Ajouter des tests couvrant :

- édition et suppression ;
- cible absente ;
- session active ;
- messages composites ou compactés ;
- événements dupliqués ;
- deux éditions rapides ;
- autorisation utilisateur révoquée ;
- échec de suppression Discord ;
- génération ancienne écrivant après interruption.

### 2. Découpage limité

- Extraire la normalisation des événements.
- Extraire les vues interactives communes sans casser le chargement paresseux de `discord.py`.
- Porter séparément la normalisation Windows de `adapter_media.py`.

### 3. Components V2 progressif

- Messages statiques.
- Fichiers et forums.
- Prompts interactifs.
- Streaming et voix restent sur les transports historiques tant qu'ils ne sont pas prouvés compatibles.

### 4. Synchronisation opt-in

- Ajouter la corrélation persistante par génération.
- Valider puis interrompre/libérer le bon tour.
- Archiver une seule fois.
- Supprimer uniquement les sorties corrélées avec certitude.
- Réadmettre l'édition comme nouveau tour contrôlé.
- Activer uniquement après tests d'intégration avec le véritable `SessionDB` et l'adaptateur Discord.

## Fichiers actuels concernés

- `plugins/platforms/discord/adapter.py`
- `plugins/platforms/discord/adapter_media.py`
- `gateway/run_adapters.py`
- `gateway/run_agent_cache.py`
- `gateway/run_turn.py`
- `gateway/run_notifications.py`
- `gateway/platforms/base.py`
- `hermes_state_messages.py`
- `gateway/session_transcript.py`
- `tests/gateway/test_discord_platform_events.py`
- tests de livraison Discord et `tests/hermes_state/`
