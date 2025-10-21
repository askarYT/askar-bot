# Instructions pour Gemini Code Assist - Projet Askar-Bot

## 1. Contexte Général

Ce projet est un bot Discord personnel nommé "Askar-Bot", développé en Python avec la librairie `discord.py`. L'objectif est de fournir des fonctionnalités variées pour un serveur Discord, allant de la modération ludique à des outils de notification.

**À chaque nouvelle demande, tu dois lire ce fichier pour comprendre le contexte et les conventions du projet.**
    **En cas de nécessité, tu peux modifier ce fichier en te basant sur sa forme actuelle, tu as aussi le droit d'ajouter, supprimer ou modifier les fichiers demander SAUF mention contraire.**

## 2. Structure du Projet

Le code est organisé en `cogs` (modules) situés dans le dossier `cogs/`. Chaque fichier `.py` dans ce dossier représente une extension (un ensemble de fonctionnalités).

- **`xp_system.py`**: Gestion de l'expérience (XP), des niveaux et des rôles associés.
- **`genance.py`**: Système de "points de gênance" pour des mots spécifiques.
- **`bug_report.py`**: Outil de rapport de bugs avec modales et suivi par réactions.
- **`auto_message.py`**: Envoi de messages automatiques et planifiés.
- **`alerts.py`**: Système de notifications pour YouTube/Twitch (semble en développement).
- **`youtube.py`**: Système de notification alternatif pour YouTube (basé sur le scraping).
- **`twitch_notifier.py`**: Système de notification pour Twitch.
- **`status.py`**: Gestion du statut et de l'activité du bot.
- **`messages.py`**: Commandes pour envoyer/éditer des messages via le bot.
- **`random.py`**, **`mimir.py`**: Commandes diverses et amusantes.

## 3. Technologies et Dépendances

- **Langage** : Python 3.
- **Librairie Discord** : `discord.py` (utilisation des commandes d'application `/` et des `tasks`).
- **Base de données** : MongoDB.
  - La connexion se fait via une variable d'environnement `MONGO_URI`.
  - Plusieurs bases de données et collections sont utilisées :
    - `askar_bot`: pour `xp_data`, `level_roles`, `ignored_channels`, `command_roles`, `genance_data`, `alerts`, `twitch_notifications`.
    - `discord_bot`: pour `bot_status`.
    - `youtube_notify_db`: pour `youtube_channels`.
  - **Pour les nouvelles fonctionnalités, utilise la base de données `askar_bot` et crée une nouvelle collection si nécessaire, sauf si une autre base est plus pertinente (à discuter).**
- **Autres librairies notables** : `pymongo`, `aiohttp`, `python-dotenv` (implicite pour `os.getenv`), `twitchAPI`.

## 4. Conventions de Code et Style

- **Langue** : Le code (commentaires, noms de variables) est un mélange de français et d'anglais. **Les messages destinés aux utilisateurs Discord doivent impérativement être en français.**
- **Formatage** : Le code suit globalement les conventions PEP 8. Maintiens ce style.
- **Logging** : Le module `logging` est utilisé pour tracer les informations, erreurs et avertissements. Continue de l'utiliser pour les messages système.
- **Commandes** : Privilégier les commandes d'application (`app_commands`) pour les nouvelles fonctionnalités.
- **Sécurité** : Les informations sensibles (token du bot, URI MongoDB, clés API) sont stockées dans des variables d'environnement. Ne jamais les écrire en dur dans le code.
- **Robustesse** : Utiliser des blocs `try...except` pour gérer les erreurs potentielles (appels API, accès à la base de données, permissions Discord manquantes).

## 5. Points d'Attention Particuliers

- **Cohérence de la base de données** : Il y a plusieurs bases de données (`askar_bot`, `discord_bot`, `youtube_notify_db`). Lors de l'ajout de fonctionnalités, évaluer s'il est pertinent de consolider ou de continuer cette séparation.
- **Systèmes de notification redondants** : Les fichiers `alerts.py`, `youtube.py` et `twitch_notifier.py` semblent avoir des fonctionnalités qui se chevauchent. Il faudra clarifier lequel est le système principal à l'avenir pour éviter les conflits. Le système `youtube.py` utilise du scraping HTML, ce qui est fragile.
- **Configuration** : Certaines configurations sont en dur (ex: `report_channel_id` dans `bug_report.py`). Pour plus de flexibilité, il serait préférable de les rendre configurables via des commandes et de les stocker en base de données.
- **Permissions** : La vérification des permissions est déjà en place pour de nombreuses commandes (`has_command_permission`, `interaction.user.guild_permissions.administrator`). C'est une bonne pratique à maintenir pour toutes les commandes sensibles.

## 6. Objectif des Interactions Futures

Mon rôle est de t'assister pour :
- **Ajouter de nouvelles fonctionnalités** en respectant la structure et les conventions existantes.
- **Modifier des fonctionnalités existantes** pour les améliorer, corriger des bugs ou les rendre plus configurables.
- **Refactoriser le code** pour améliorer sa lisibilité, sa performance et sa maintenabilité.
- **Analyser et expliquer** des parties du code.

## 7. Liste des Commandes par Cog

Cette section liste toutes les commandes d'application (`/`) disponibles, classées par cog. Elle doit être maintenue à jour à chaque ajout ou suppression de commande.

### `xp_system.py`
- `/xp [user]`: Affiche l'XP et le niveau d'un utilisateur.
- `/xp-add <user> <xp_amount>`: Ajoute de l'XP à un utilisateur.
- `/xp-remove <user> <xp_amount>`: Retire de l'XP à un utilisateur.
- `/ignore-channel <channel>`: Ajoute un salon (textuel ou vocal) à la liste des salons ignorés pour les gains d'XP.
- `/unignore-channel <channel>`: Supprime un salon (textuel ou vocal) de la liste des salons ignorés pour les gains d'XP.
- `/set-command-role <command> <role>`: Définit un rôle autorisé à utiliser une commande du bot.
- `/remove-command-role <command> <role>`: Retire un rôle autorisé à utiliser une commande du bot.
- `/set-level-role <level> <role>`: Assigne un rôle à donner à partir d'un certain niveau.
- `/resync-roles`: Force la resynchronisation des rôles par niveau pour tous les membres.

### `genance.py`
- `/genance [member]`: Consulte les points de gênance d'un utilisateur.

### `bug_report.py`
- `/report-bug <bug_name>`: Signaler un bug.

### `auto_message.py`
- `/set_message <salon_id> <message> [heure] [timezone]`: Configure un message automatique dans un salon spécifique.
- `/edit_time <heure>`: Modifie l'heure de l'envoi du message automatique.
- `/view_message`: Affiche les détails du message automatique configuré.
- `/stop_message`: Arrête l'envoi automatique du message.
- `/edit_message`: Modifie le message automatique actuel.

### `twitch_notifier.py`
- `/twitch-add <twitch_username> <channel> [role]`: Ajoute une notification de live Twitch.
- `/twitch-remove <twitch_username>`: Supprime une notification de live Twitch.
- `/twitch-edit <twitch_username> [channel] [role]`: Modifie une alerte Twitch existante.
- `/twitch-set-message <twitch_username> <message>`: Définit un message personnalisé pour une notification Twitch.
- `/twitch-list`: Affiche toutes les alertes Twitch configurées sur le serveur.
- `/twitch-test <twitch_username>`: Envoie une fausse notification de live pour tester la configuration.

### `status.py`
- `/setstatus [activity_type] [activity_text] [status]`: Change l'activité et le statut du bot.
- `/setcycle <interval> <activities>`: Alterner entre plusieurs activités à intervalles réguliers.

### `random.py`
- `/random [min] [max]`: Génère un nombre aléatoire.

### `youtube.py`
- `/set_alert <channel_id> <channel_name> <notif_channel>`: Ajoute une chaîne YouTube à surveiller.
- `/set_alert_roles [video_role] [short_role] [twitch_role]`: Définit les rôles globaux à mentionner pour toutes les chaînes.
- `/remove_alert <channel_name>`: Supprime une alerte YouTube par nom de chaîne.

### `alerts.py`
- `/alerts`: Afficher les alertes et les utilisateurs inscrits.
- `/alerts-add <platform> <channel_identifier> <content_type>`: Ajouter une alerte.
- `/alerts-set-role <platform> <channel_identifier> <content_type> <role>`: Définir un rôle pour une alerte.
- `/alerts-set-channel <platform> <channel_identifier> <channel>`: Définir le salon des notifications pour une alerte.

### `ping.py`
- `/ping`: Affiche la latence du bot.

### Autres cogs (sans commandes d'application)
- `mimir.py`
- `poke.py`
- `sun.py`
- `messages.py` (Contient des commandes mais elles ne sont pas définies comme `app_commands` dans le code fourni)
