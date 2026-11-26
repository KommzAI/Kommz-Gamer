# CHANGELOG

[Français](CHANGELOG.md) | [English](CHANGELOG.en.md)

## Kommz Gamer 5.4 - 2026-10-05

### Points forts
- À partir de cette version, le bouton « Mettre à jour » installe les nouvelles versions, avec la progression affichée jusqu'au bout.
- Le logiciel démarre environ trois fois plus vite, après le premier lancement d'une nouvelle version.
- Mode Écoute : la traduction se fait dans la langue de votre choix (12 langues), et plus seulement en français.
- Mode Écoute : le français et 9 autres langues sont reconnus correctement, quelle que soit votre langue cible.
- La voix clonée reste prête pendant la partie, même après plusieurs minutes de silence.
- Vos clés et vos réglages ne sont plus accessibles depuis le réseau local ni depuis un site web ouvert dans votre navigateur.
- Un avertissement s'affiche si le fichier de mise à jour ne peut pas être vérifié.
- Le voyant « serveur prêt » ne s'allume plus quand le réveil du serveur a échoué.

### Mode Écoute
- Nouveau menu « Traduire en » dans les réglages rapides du Mode Écoute, avec 12 langues : français, anglais, espagnol, allemand, italien, portugais, russe, polonais, turc, japonais, chinois et coréen. « Auto » (par défaut) suit la langue de l'interface.
- La voix de lecture parle la langue de traduction choisie, au lieu de toujours parler français.
- Nouveau modèle de reconnaissance vocale : le français, l'anglais, l'espagnol, l'allemand, l'italien, le portugais, le russe, le japonais, le néerlandais et l'hindi sont reconnus dans une même session, et chaque phrase est reconnue dans sa langue réelle.
- La reconnaissance ne dépend plus de la langue cible réglée dans l'onglet Intelligence Artificielle : avec une cible en français, un coéquipier anglophone est maintenant compris.
- Meilleure reconnaissance du vocabulaire du jeu et du streaming (Steam, Twitch, Discord, noms de jeux, etc.).
- Une phrase déjà dans votre langue de traduction est affichée telle que reconnue, sans passer par la traduction : texte plus fidèle et quota de traduction économisé. Si la langue est incertaine, la phrase est traduite comme avant.
- La traduction anticipée est désactivée par défaut : elle consommait environ cinq fois plus d'appels de traduction pour un gain imperceptible.
- Le Mode Écoute peut être désactivé puis réactivé sans redémarrer le logiciel.
- Les termes de jeu ne déforment plus les mots ordinaires qui les contiennent (par exemple « résultat » ou « culture »).
- Conseil : si la reconnaissance invente des mots sur une voix claire (vidéo, chat vocal), essayez Voice Focus sur Off.

### Voix clonée et performances
- Le serveur de voix se réveille en 6 secondes environ au lieu de près de 2 minutes, et la première phrase en voix clonée part bien plus vite.
- Le serveur de voix est maintenu éveillé pendant une partie : une phrase après un long silence ne paie plus le temps de réveil.
- Le voyant « serveur prêt » ne s'allume qu'après un réveil réussi, et un réveil raté est retenté au bout de quelques secondes.
- Démarrage plus rapide : le logiciel est décompressé une seule fois par version, puis réutilisé aux lancements suivants. Le premier lancement d'une nouvelle version reste plus long.

### Mises à jour
- Depuis la 5.3.1, le passage à la 5.4 se fait une seule fois à la main : téléchargez la 5.4 et lancez-la, vos réglages sont conservés. Le bouton « Mettre à jour » de la 5.3.1 ne peut pas installer de nouvelle version.
- Le bouton « Mettre à jour » télécharge, vérifie et installe la nouvelle version, puis redémarre le logiciel en conservant vos réglages.
- La progression s'affiche étape par étape (téléchargement, vérification, installation), dans la langue de l'interface.
- Un avertissement s'affiche si la mise à jour ne peut pas être vérifiée.

### Réglages
- Les réglages par défaut corrigés atteignent aussi les installations existantes (par exemple, la mise à jour automatique est réactivée). Vos propres réglages sont conservés.
- Les réglages sont toujours enregistrés dans votre profil utilisateur, jamais dans le fichier modèle livré avec le logiciel.
- Le numéro de version affiché dans l'interface correspond toujours à la version qui tourne.

### Sécurité
- Vos clés et vos réglages ne sont accessibles qu'au logiciel lui-même : les autres appareils du réseau local ne peuvent utiliser que la télécommande mobile, l'overlay et les sous-titres.
- Les sites web ouverts dans votre navigateur ne peuvent plus communiquer avec le logiciel.
- Sécurité des serveurs de voix renforcée.

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
