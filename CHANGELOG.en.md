# CHANGELOG

[Français](CHANGELOG.md) | [English](CHANGELOG.en.md)

## Kommz Gamer 5.3 - 2026-08-05

### Audio and real-time pipeline
- Consolidated the remote voice pipeline with Whisper Modal, GPT-SoVITS Modal, and XTTS Modal, with explicit fallback when cloud services are unavailable.
- Stabilized routing between the configured microphone, virtual output, headset monitoring, and synthesis engines.
- Fixed monitoring sample-rate fallback to preserve reliable playback when devices do not share the same native sample rate.
- Added runtime diagnostics for the STT engine, Hybrid routing, active TTS engine, and audio-module state.
- Added automatic game detection through audio fingerprints, with process, window-title, fingerprint, and manual-selection fallback.
- Added ASIO support, buffer auto-tuning, multi-device support, and native VB-Cable / Voicemeeter integration.

### Voice processing and presets
- Voice Focus V3: automatic calibration, frequency-band noise reduction, de-essing, de-clicking, de-clipping, auto-gain riding, VAD v2 with Silero fallback, lightweight voiceprint, and anti-reverberation processing.
- Added Intelligent Universal preset, microphone-type presets, JSON import/export, community preset store, and preset scheduling.
- Added Auto preset mode with multi-game detection and alt-tab handling.

### UI and operations
- Added separate visual states for transcription, Hybrid, and final synthesis in the voice pipeline.
- Added runtime module supervision and audio-service health information.
- Strengthened the listening watchdog and session reporting for long-running diagnostics.
- Added enriched real-time overlay, local analytics dashboard, structured JSON session export, and latency, CPU, and RAM metrics.

### Architecture
- Modularized Flask into 13 blueprints covering configuration, licensing, audio, overlay, TTS, STT, listening, scenes, UI, and remote access.
- Extracted about 81 routes from `vtp_core.py`, retaining runtime routes tied to audio globals and HUD state.
- Cleaned the repository and removed code or files made obsolete by the refactor.

### Stabilization and configuration
- Audited blueprints (`modules/listen`, `modules/guide`, `modules/remote`, `modules/scenes`) for missing symbols: zero missing symbols confirmed in `vtp_core.py`.
- Removed the duplicate `_listen_now_utc_iso` (`listen_bp.py`); fixed `_mobile_connected` to propagate correctly to `vtp_core` instead of a local `globals()` write.
- Audited license checks: already centralized in `modules/license/license.py`, no rework needed.
- Migrated audio device IDs (`game_input_device` / `game_output_device`) from raw PortAudio indexes to canonical stable `"{hostapi}::{name}"` signatures (for example `WASAPI::CABLE OUTPUT`), with a separate runtime cache and backward compatibility for existing configurations.
- Fixed configuration persistence in compiled mode: template migration, durable runtime path, and explicit `CONFIG_FILE` import.
- Addressed post-refactor stability issues: missing audio defaults, license persistence, monitoring rate mismatch, HUD polling, overlay loop, subtitle output, device validation, and F2/F3 handlers.

### Verification
- Syntax compilation of `vtp_core.py` and `modules/config/config.py` was validated after the stabilization fixes.
- Targeted validation covered audio-signature resolution: host API, name fallback, input/output direction, and compatibility with existing configurations.

## Kommz Gamer 4.6 - 2026-03-22

### Audio and stability
- Fixed microphone selection to prioritize the configured input device (`game_input_device`) instead of blindly forcing Windows default.
- Improved input-device resolution with clean fallback logic (config -> system default -> safe detection).
- Stabilized Hybrid Activation to reuse a valid and consistent microphone context.

### Modules and UI
- Added `Scenes Vocales` tab to save/apply full presets (language, engine, modules, voice) in one click.
- Added auto-apply by active process (for example `cod.exe`).
- Unified all 16 modules into a single compact grid in the Modules tab.
- Hybrid Activation now appears in the same runtime area as other modules.
- Added `Voix Studio` tab to save, activate, test, and remove `voice_id` profiles.
- Added `default voice on startup` mode.

### UX cleanup
- Cleaned visible audio-engine messages (micro/log errors) and removed malformed strings.

## Kommz Gamer 4.5 - 2026-03-19

### UI and readability
- Added vocal pipeline card with separate transcription, Hybrid, and final synthesis states.
- Added runtime module supervision card for key modules.
- Reworked updater card for clearer target version, install status, and release notes.
- Additional cleanup for visible UI and embedded guide strings.

### Runtime and diagnostics
- Exposed more runtime details on `/status` for STT engine, Hybrid routing, and active TTS engine.
- Improved backend module-state reporting (warmups, boosts, caches, OBS export).
- Cleaned update-system messages to avoid unreadable/malformed output.

### Versioning
- Client and embedded guides updated to `4.5`.
- Release tooling kept compatible.

## Kommz Gamer 4.4 - 2026-03-18

### Major changes
- Significant reinforcement of Hybrid `GPT-SoVITS -> XTTS` mode.
- Better timbre fidelity and more natural voice output in real usage.
- Extended Hybrid language support (`FR`, `EN`, `JA`, `KO`, `ZH`).
- Consolidated remote pipeline with `Whisper Modal`, `GPT-SoVITS Modal`, and `XTTS Modal`.

### Fixes and stability
- Improved fallback behavior when services are unavailable.
- Improved routing between `voice_id`, direct clone, and Hybrid pipeline.
- Fixed multiple encoding/display issues.
- Improved overall real-time pipeline stability.
