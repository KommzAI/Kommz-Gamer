# CHANGELOG

[Français](CHANGELOG.md) | [English](CHANGELOG.en.md)

## Kommz Gamer 5.4 - 2026-10-05

### Highlights
- From this version on, the "Update" button installs new versions, with progress shown until the end.
- The app starts about three times faster, after the first launch of a new version.
- Listen Mode: translation goes to the language of your choice (12 languages), not only French.
- Listen Mode: French and 9 other languages are now recognized correctly, whatever your target language.
- The cloned voice stays ready during the game, even after several minutes of silence.
- Your keys and settings can no longer be reached from the local network or from a website open in your browser.
- A warning is shown if the update file cannot be verified.
- The "server ready" light no longer turns on when waking up the server failed.

### Listen Mode
- New "Translate to" menu in the Listen Mode quick settings, with 12 languages: French, English, Spanish, German, Italian, Portuguese, Russian, Polish, Turkish, Japanese, Chinese and Korean. "Auto" (default) follows the interface language.
- The reading voice now speaks the chosen translation language instead of always speaking French.
- New speech recognition model: French, English, Spanish, German, Italian, Portuguese, Russian, Japanese, Dutch and Hindi are recognized in the same session, and each sentence is recognized in its actual language.
- Recognition no longer depends on the target language set in the Artificial Intelligence tab: with a French target, an English teammate is now understood.
- Better recognition of gaming and streaming vocabulary (Steam, Twitch, Discord, game names, etc.).
- A sentence already in your translation language is shown as recognized, without going through translation: more faithful text and less translation quota used. When the language is uncertain, the sentence is translated as before.
- Speculative translation is now off by default: it used about five times more translation calls for a gain that was not noticeable.
- Listen Mode can be turned off and on again without restarting the app.
- Gaming terms no longer distort ordinary words that contain them (for example "result" or "default").
- Tip: if recognition makes up words on a clear voice (video, voice chat), try setting Voice Focus to Off.

### Cloned voice and performance
- The voice server now wakes up in about 6 seconds instead of nearly 2 minutes, and the first cloned sentence comes out much sooner.
- The voice server is kept awake during a game, so a sentence after a long silence no longer pays the wake-up time.
- The "server ready" light only turns on after a successful wake-up, and a failed wake-up is retried after a few seconds.
- Faster startup: the app is unpacked once per version and reused on later launches. The first launch of a new version takes longer.

### Updates
- Coming from 5.3.1, moving to 5.4 is a one-time manual step: download 5.4 and run it, your settings are kept. The "Update" button in 5.3.1 cannot install a new version.
- The "Update" button downloads, verifies and installs the new version, then restarts the app with your settings kept.
- Progress is shown step by step (download, verification, installation) in the interface language.
- A warning is shown if the update cannot be verified.

### Settings
- Corrected default settings now also reach existing installations (for example, automatic updates are turned back on). Your own settings are kept.
- Settings are always saved in your user profile, never in the template file shipped with the app.
- The version number shown in the interface always matches the running version.

### Security
- Your keys and settings are only available to the app itself: other devices on the local network can only use the mobile remote, the overlay and the subtitles.
- Websites open in your browser can no longer talk to the app.
- Strengthened security of the voice servers.

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
