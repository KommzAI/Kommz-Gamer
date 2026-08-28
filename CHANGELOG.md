# CHANGELOG

[Français](CHANGELOG.md) | [English](CHANGELOG.en.md)

## Kommz Gamer 5.3 - 2026-08-05

### Audio et pipeline temps reel
- Consolidation du pipeline vocal distant avec Whisper Modal, GPT-SoVITS Modal et XTTS Modal, avec fallback explicite lorsque les services cloud sont indisponibles.
- Stabilisation du routage entre le micro configure, la sortie virtuelle, le retour casque et les moteurs de synthese.
- Correction du fallback de frequence d'echantillonnage pour le monitoring afin de conserver une lecture fiable lorsque les peripheriques n'utilisent pas la meme frequence native.
- Ajout de diagnostics runtime pour suivre le moteur STT, le routage Hybrid, le moteur TTS actif et l'etat des modules audio.
- Ajout de la detection automatique de jeu par fingerprint audio, avec chaine de repli processus, titre de fenetre, fingerprint, puis selection manuelle.
- Ajout du support ASIO, de l'auto-tuning du buffer, du multi-peripherique et de l'integration native VB-Cable / Voicemeeter.

### Traitement vocal et presets
- Voice Focus V3 : calibration automatique, reduction du bruit par bandes, de-essing, de-clicking, de-clipping, auto-gain riding, VAD v2 avec fallback Silero, voiceprint leger et traitement anti-reverberation.
- Preset Universel intelligent, presets par type de microphone, import/export JSON, preset store communautaire et planification des presets.
- Mode Auto pour les presets avec detection multi-jeu et gestion de l'alt-tab.

### Interface et exploitation
- Ajout d'etats visuels separes pour la transcription, Hybrid et la synthese finale dans le pipeline vocal.
- Ajout de supervision runtime des modules et d'informations de sante des services audio.
- Renforcement du watchdog d'ecoute et des rapports de session pour faciliter les diagnostics de longue duree.
- Overlay temps reel enrichi, dashboard analytics local, export JSON structure des sessions et metriques de latence, CPU et RAM.

### Architecture
- Modularisation Flask en 13 blueprints couvrant notamment la configuration, licence, audio, overlay, TTS, STT, ecoute, scenes, interface et acces distant.
- Extraction d'environ 81 routes depuis `vtp_core.py`, avec conservation des routes runtime liees aux globals audio et au HUD.
- Nettoyage du depot et suppression de code ou fichiers devenus inutiles apres le refactoring.

### Stabilisation et configuration
- Audit des symboles manquants dans les blueprints (`modules/listen`, `modules/guide`, `modules/remote`, `modules/scenes`) : zero symbole manquant confirme dans `vtp_core.py`.
- Suppression du doublon `_listen_now_utc_iso` (`listen_bp.py`) ; propagation correcte de `_mobile_connected` vers `vtp_core` au lieu d'une ecriture locale via `globals()`.
- Audit des controles de licence : architecture deja centralisee dans `modules/license/license.py`, aucune refonte necessaire.
- Migration des identifiants de peripheriques audio (`game_input_device` / `game_output_device`) d'un index PortAudio brut vers une signature canonique stable `"{hostapi}::{nom}"` (ex : `WASAPI::CABLE OUTPUT`), avec cache runtime separe et retrocompatibilite assuree pour les configurations existantes.
- Correction de la persistance de configuration en mode compile : migration du template, chemin runtime durable et import explicite de `CONFIG_FILE`.
- Corrections de stabilite post-refactoring : defaults audio manquants, persistance de licence, rate mismatch monitoring, polling HUD, boucle overlay, sortie de sous-titres, validation de peripheriques et handlers F2/F3.

### Verification
- Compilation syntaxique de `vtp_core.py` et `modules/config/config.py` validee apres les correctifs de stabilisation.
- Verification ciblee de la resolution des signatures audio : host API, fallback par nom, sens input/output et compatibilite des anciennes configurations.

## Kommz Gamer 4.6 - 2026-03-22

### Audio et stabilité
- Correction de la sélection du microphone pour prioriser le périphérique d'entrée configuré (`game_input_device`) au lieu de forcer aveuglément le périphérique Windows par défaut.
- Amélioration de la résolution du périphérique d'entrée avec une logique de repli propre (config -> défaut système -> détection sûre).
- Stabilisation de l'Activation Hybrid pour réutiliser un contexte micro valide et cohérent.

### Modules et interface
- Ajout de l'onglet `Scenes Vocales` pour sauvegarder/appliquer des presets complets (langue, moteur, modules, voix) en un clic.
- Ajout de l'auto-application par processus actif (par exemple `cod.exe`).
- Unification des 16 modules dans une seule grille compacte dans l'onglet Modules.
- L'Activation Hybrid apparaît maintenant dans la même zone runtime que les autres modules.
- Ajout de l'onglet `Voix Studio` pour sauvegarder, activer, tester et supprimer des profils `voice_id`.
- Ajout du mode `voix par défaut au démarrage`.

### Nettoyage UX
- Nettoyage des messages visibles du moteur audio (erreurs micro/log) et suppression des chaînes malformées.

## Kommz Gamer 4.5 - 2026-03-19

### Interface et lisibilité
- Ajout d'une carte de pipeline vocal avec états séparés pour transcription, Hybrid et synthèse finale.
- Ajout d'une carte de supervision des modules runtime pour les modules clés.
- Refonte de la carte de mise à jour pour une version cible, un statut d'installation et des notes de version plus clairs.
- Nettoyage supplémentaire pour l'interface visible et les chaînes du guide intégré.

### Runtime et diagnostics
- Exposition de plus de détails runtime sur `/status` pour le moteur STT, le routage Hybrid et le moteur TTS actif.
- Amélioration du rapport d'état des modules backend (warmups, boosts, caches, export OBS).
- Nettoyage des messages du système de mise à jour pour éviter les sorties illisibles/malformées.

### Versioning
- Client et guides intégrés mis à jour vers `4.5`.
- Outillage de release maintenu compatible.

## Kommz Gamer 4.4 - 2026-03-18

### Changements majeurs
- Renforcement significatif du mode Hybrid `GPT-SoVITS -> XTTS`.
- Meilleure fidélité de timbre et sortie vocale plus naturelle en usage réel.
- Extension du support linguistique Hybrid (`FR`, `EN`, `JA`, `KO`, `ZH`).
- Consolidation du pipeline distant avec `Whisper Modal`, `GPT-SoVITS Modal` et `XTTS Modal`.

### Corrections et stabilité
- Amélioration du comportement de repli quand les services sont indisponibles.
- Amélioration du routage entre `voice_id`, clonage direct et pipeline Hybrid.
- Correction de plusieurs problèmes d'encodage/affichage.
- Amélioration de la stabilité globale du pipeline temps réel.
