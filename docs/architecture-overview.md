# Kommz Voice - Architecture Overview

## Purpose

Kommz Voice provides the backend speech engine layer used by Kommz clients.

Main goals:
- low-latency synthesis routing
- voice timbre consistency
- robust fallback paths when remote endpoints are slow or unavailable

## Core engine components

- `modal_xtts.py`
  - XTTS runtime integration
  - multilingual synthesis serving

- `modal_gptsovits.py`
  - GPT-SoVITS runtime integration
  - timbre/style reference handling

- `modal_whisper.py`
  - Whisper transcription endpoint integration

- `vtp_web_server.py`
  - orchestration entrypoint
  - routing, validation, and request handling

## Role in the ecosystem

- `Kommz Gamer Community` is the open client/community app
- `Kommz Voice` is the speech engine backend brick
- Discord and Patreon support operations, community, and sustainability

## Operational notes

- Keep secrets in `.env` only
- Never commit credential material
- Use security runbooks and checklists in `docs/`
