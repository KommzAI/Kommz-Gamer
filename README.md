# Kommz Gamer Community

[Français](README.md) | [English](README.en.md)

> **Édition Community**  
> Noyau desktop open source, auto-hébergeable, conçu pour la personnalisation et les contributions.

![Community Edition](https://img.shields.io/badge/Edition-Community-2563eb?style=for-the-badge)
![License AGPLv3](https://img.shields.io/badge/License-AGPLv3-16a34a?style=for-the-badge)
[![GitHub Release](https://img.shields.io/github/v/release/Kommz-Gamer/Kommz-Gamer?style=for-the-badge)](https://github.com/Kommz-Gamer/Kommz-Gamer/releases)
[![Discord](https://img.shields.io/badge/Discord-Communaute-5865F2?style=for-the-badge&logo=discord&logoColor=white)](https://discord.gg/uv25d6uGKZ)
[![Patreon](https://img.shields.io/badge/Soutenir-Patreon-f96854?style=for-the-badge&logo=patreon&logoColor=white)](https://www.patreon.com/KommzInnovations)

Kommz Gamer Community est l’édition open source de Kommz Gamer, une application desktop de traduction vocale bidirectionnelle en temps réel pour le gaming, le streaming et les échanges multilingues en direct.
La couche moteur vocale est portée par une brique séparée: `Kommz Voice` (XTTS + GPT-SoVITS).

## Commencer ici
- Dernieres releases: https://github.com/Kommz-Gamer/Kommz-Gamer/releases
- Rejoindre la communaute: https://discord.gg/uv25d6uGKZ
- Soutenir le projet: https://www.patreon.com/KommzInnovations
- Site officiel: https://kommz.fr

## Communaute et support
- GitHub: code source, issues, releases, contributions
- Kommz Voice: couche backend moteur dediee (XTTS + GPT-SoVITS)
- Discord: aide, retours, roadmap, discussions
- Patreon: soutien, contexte d'acces anticipe, durabilite du projet

## Ce qui est inclus
- Code source du client desktop
- Interface et modules runtime
- Configuration orientée communauté et exemples
- Documentation et historique des changements

## Ce qui n’est pas inclus
- Infrastructure cloud privée
- Services de licence de production
- Endpoints vocaux hébergés et support managé
- Artéfacts de build internes, secrets locaux et assets de test personnels

## Community vs Pro
### Édition Community (ce dépôt)
- Code source complet de l’application desktop
- Workflow auto-hébergé et auto-configuré
- Contributions et échanges communautaires
- Pas de verrou de licence managée intégré en mode community
- Vous exploitez et maintenez votre propre stack locale/cloud

### Offre Pro / Supportée (hors de ce dépôt)
- Releases Windows stables et onboarding guidé
- Endpoints vocaux hébergés et services cloud managés
- Support prioritaire (setup, dépannage, optimisation)
- Workflows en accès anticipé et accompagnement orienté production

Ce dépôt est conçu pour la transparence et l’extensibilité. L’offre supportée est conçue pour les équipes qui veulent privilégier la vitesse, la fiabilité et l’exploitation managée.

## Démarrage rapide
1. Copiez `.env.example` vers `.env` et renseignez les variables souhaitées.
2. Copiez `settings.example.json` vers `settings.json` si vous voulez une base locale.
3. Créez un environnement virtuel puis installez les dépendances.
4. Lancez l’application depuis les sources.

## Note open source
Ce dépôt est préparé comme édition community. Les services hébergés, le support commercial et l’infrastructure vocale managée restent hors du dépôt public.

## Liens du projet
- Site web: https://kommz.fr
- Discord: https://discord.gg/uv25d6uGKZ
- Patreon: https://www.patreon.com/KommzInnovations

## Template de release
- Template de release EN: `.github/release-template.en.md`
- Template de release FR: `.github/release-template.fr.md`
- Checklist de release: `.github/release-checklist.md`

## Structure du dépôt
- Guide de structure recommandé: `docs/REPO_STRUCTURE.md`

## Workflow de contribution
- Template de pull request: `.github/pull_request_template.md`
- Templates d'issues: `.github/ISSUE_TEMPLATE/`

## Licence
Ce projet est distribué sous GNU Affero General Public License v3.0. Voir `LICENSE`.

