# Instructions pour Gemini Code Assist - Projet Askar-Bot

## 1. Contexte Général

Ce projet est un bot Discord personnel nommé "Askar-Bot", développé en Python avec la librairie `discord.py`. L'objectif est de fournir des fonctionnalités variées pour un serveur Discord, allant de la modération ludique à des outils de notification.

**À chaque nouvelle demande, tu dois lire ce fichier pour comprendre le contexte et les conventions du projet.**

## 2. Structure du Projet

Le code est organisé en `cogs` (modules) situés dans le dossier `cogs/`. Chaque fichier `.py` dans ce dossier représente une extension (un ensemble de fonctionnalités).

- **`xp_system.py`**: Gestion de l'expérience (XP), des niveaux et des rôles associés.
- **`genance.py`**: Système de "points de gênance" pour des mots spécifiques.
- **`bug_report.py`**: Outil de rapport de bugs avec modales et suivi par réactions.
- **`auto_message.py`**: Envoi de messages automatiques et planifiés.
- **`alerts.py`**: Système de notifications pour YouTube/Twitch (semble en développement).
- **`youtube.py`**: Système de notification alternatif pour YouTube (basé sur le scraping).
- **`status.py`**: Gestion du statut et de l'activité du bot.
- **`messages.py`**: Commandes pour envoyer/éditer des messages via le bot.
- **`random.py`**, **`mimir.py`**: Commandes diverses et amusantes.

## 3. Technologies et Dépendances

- **Langage** : Python 3.
- **Librairie Discord** : `discord.py` (utilisation des commandes d'application `/` et des `tasks`).
- **Base de données** : MongoDB.
  - La connexion se fait via une variable d'environnement `MONGO_URI`.
  - Plusieurs bases de données et collections sont utilisées :
    - `askar_bot`: pour `xp_data`, `level_roles`, `ignored_channels`, `command_roles`, `genance_data`, `alerts`.
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
- **Systèmes de notification redondants** : Les fichiers `alerts.py` et `youtube.py` semblent avoir des fonctionnalités qui se chevauchent. Il faudra clarifier lequel est le système principal à l'avenir pour éviter les conflits. Le système `youtube.py` utilise du scraping HTML, ce qui est fragile et peut casser si YouTube modifie sa structure. Le système `alerts.py` semble plus moderne mais incomplet.
- **Configuration** : Certaines configurations sont en dur (ex: `report_channel_id` dans `bug_report.py`). Pour plus de flexibilité, il serait préférable de les rendre configurables via des commandes et de les stocker en base de données.
- **Permissions** : La vérification des permissions est déjà en place pour de nombreuses commandes (`has_command_permission`, `interaction.user.guild_permissions.administrator`). C'est une bonne pratique à maintenir pour toutes les commandes sensibles.

## 6. Objectif des Interactions Futures

Mon rôle est de t'assister pour :
- **Ajouter de nouvelles fonctionnalités** en respectant la structure et les conventions existantes.
- **Modifier des fonctionnalités existantes** pour les améliorer, corriger des bugs ou les rendre plus configurables.
- **Refactoriser le code** pour améliorer sa lisibilité, sa performance et sa maintenabilité.
- **Analyser et expliquer** des parties du code.

Je dois toujours proposer des modifications sous forme de `diff` pour que tu puisses les appliquer facilement.
