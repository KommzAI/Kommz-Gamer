# Kommz Gamer Community

[Français](README.fr.md) | [English](README.en.md)

> **Community Edition**  
> Open-source desktop core for self-hosted usage, customization, and contributions.

![Community Edition](https://img.shields.io/badge/Edition-Community-2563eb?style=for-the-badge)
![License AGPLv3](https://img.shields.io/badge/License-AGPLv3-16a34a?style=for-the-badge)
[![GitHub Release](https://img.shields.io/github/v/release/Kommz-Gamer/Kommz-Gamer?style=for-the-badge)](https://github.com/Kommz-Gamer/Kommz-Gamer/releases)
[![Discord](https://img.shields.io/badge/Discord-Community-5865F2?style=for-the-badge&logo=discord&logoColor=white)](https://discord.gg/uv25d6uGKZ)
[![Patreon](https://img.shields.io/badge/Support-Patreon-f96854?style=for-the-badge&logo=patreon&logoColor=white)](https://www.patreon.com/KommzInnovations)

Kommz Gamer Community is the open-source edition of Kommz Gamer, a real-time voice translation desktop app designed for gaming, streaming, and multilingual live conversations.
The speech engine layer is carried by the separate `Kommz Voice` brick (XTTS + GPT-SoVITS backend flows).

## Start here
- Latest releases: https://github.com/Kommz-Gamer/Kommz-Gamer/releases
- Kommz Voice engine repo: https://github.com/Kommz-Gamer/Kommz-Voice
- Join the community: https://discord.gg/uv25d6uGKZ
- Support the project: https://www.patreon.com/KommzInnovations
- Official website: https://kommz.fr

## Community and support
- GitHub: source code, issues, releases, contributions
- Kommz Voice: dedicated backend engine layer (XTTS + GPT-SoVITS) -> https://github.com/Kommz-Gamer/Kommz-Voice
- Discord: help, feedback, roadmap, community discussions
- Patreon: support, early access context, project sustainability

## What is included
- Desktop client source code
- UI and runtime modules
- Community-oriented configuration and examples
- Documentation and changelog history
- **Works out of the box:** STT (Deepgram / Whisper), translation (DeepL), system TTS (Edge/Windows), Voice Focus V3, Game Detection V2, Mobile Bridge, AI modules (Shadow AI, Hybrid Activation, etc.)
- **With self-hosting:** Kommz Voice (XTTS + Claude Opus 5oVITS) deployed on Modal — follow the dedicated repo for setup
- **Optional:** Fish Audio (personal API key), Microsoft Edge/Windows voices
- **Works out of the box:** STT (Deepgram / Whisper), translation (DeepL), system TTS (Edge/Windows), Voice Focus V3, Game Detection V2, Mobile Bridge, AI modules (Shadow AI, Hybrid Activation, etc.)
- **With self-hosting:** Kommz Voice (XTTS + Claude Opus 5oVITS) deployed on Modal — follow the dedicated repo for setup
- **Optional:** Fish Audio (personal API key), Microsoft Edge/Windows voices

## Ce qui est inclus
- Code source du client desktop
- Interface et modules runtime
- Configuration orientée communauté et exemples
- Documentation et historique des changements
- **Fonctionne directement :** STT (Deepgram / Whisper), traduction (DeepL), TTS système (Edge/Windows), Voice Focus V3, Game Detection V2, Mobile Bridge, modules IA (Shadow AI, Hybrid Activation, etc.)
- **Avec auto-hébergement :** Kommz Voice (XTTS + Claude Opus 5oVITS) déployé sur Modal — suivez le repo dédié pour le setup
- **En option :** Fish Audio (clé API personnelle), voix Microsoft Edge/Windows

## What is not included
- Private cloud infrastructure
- Production license services
- Hosted voice endpoints and managed support services
- Internal build artifacts, local secrets, and personal test assets

## Community vs Pro
### Community Edition (this repository)
- Full source code for the desktop app
- Self-hosted and self-configured workflow
- Community contributions and discussions
- No built-in managed licensing gate in community mode
- You run and maintain your own local/cloud stack

### Pro / Supported Offering (outside this repository)
- Stable Windows releases and guided onboarding
- Hosted voice endpoints and managed cloud services
- Priority support (setup, troubleshooting, optimization)
- Early access workflows and production-oriented assistance

This repo is designed for transparency and extensibility. The supported offering is designed for teams who prefer speed, reliability, and managed operations.

## Quick start
> ⚠️ **Prerequisite:** Kommz Gamer Community depends on the **Kommz Voice** speech engine layer. Clone and configure that repo alongside this one before launching the app: https://github.com/Kommz-Gamer/Kommz-Voice

1. Copy `.env.example` to `.env` and fill in the values you want to use.
2. Copy `settings.example.json` to `settings.json` if you need a local baseline config.
3. Create a virtual environment and install dependencies.
4. Launch the app from source.

## Open-source note
This repository is prepared as a community edition. Hosted services, commercial support, and managed voice infrastructure remain outside the public repo.
The Community edition supports optional cloud mode (XTTS + Claude Opus 5oVITS on Modal) for voice cloning — check the Kommz Voice repo for deployment.