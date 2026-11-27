# Kommz Gamer — Roadmap

> Dernière mise à jour : 3 octobre 2026 · V5.4 recentrée sur la stabilisation,
> fonctionnalités social / streaming reportées en V5.5

---

## V5.1 — STABILISATION & LONGUE SESSION (✅ terminé)

- [✅] Watchdog longue session renforcé
- [✅] Relance auto si stream écoute bloqué
- [✅] Heartbeat audio/runtime
- [✅] Preset `long_session`, Voice Focus Auto
- [✅] Presets expressifs V5
- [✅] Onglet `Bugs & QA` + endpoints QA backend
- [✅] Builds Community V5.1 + versioning global
- [✅] Nettoyage repo : suppression third_party/Matcha-TTS

---

## V5.2 — FINALISATION & POLISH (✅ terminé)

- [✅] 5 nouveaux presets jeux (Tarkov, Rust, PUBG, LoL, Dota 2)
- [✅] Séparation voix/bruit — 5 profils de bruit
- [✅] 3 nouveaux presets expressifs (Agressif, Cinématique, Streamer)
- [✅] Onboarding testeurs + flux support centralisé
- [✅] Watchdog V5.2, profils de bruit par map
- [✅] Export stats session CSV, alertes watchdog configurables
- [✅] Mode benchmark preset, auto-pause si silence, log rotation
- [✅] Dark mode OLED, tray icon santé, raccourcis clavier globaux
- [✅] Mini overlay desktop, toasts natifs, page stats avec graphiques
- [✅] Installer Windows NSIS + ZIP portable
- [✅] Auto-update check, runtime Python embarqué, nightly GitHub Actions
- [✅] Auto-bug report zip, base bugs connus, mode debug verbose
- [✅] Tests automatiques, feedback in-app

---

## V5.3 — INTELLIGENCE AUDIO & REFACTORING (✅ terminé)

### Game Detection V2
- [✅] Fingerprint audio : détection auto du jeu en 2-3s
- [✅] Fallback chaîne : process → window title → fingerprint → manuel
- [✅] Base fingerprints locale + cloud sync optionnelle
- [✅] Mode preset `Auto`, détection multi-jeu / alt-tab
- [✅] Historique jeux détectés, contribution communautaire fingerprints

### Voice Focus V3
- [✅] Calibration auto (30s écoute initiale)
- [✅] Réduction bruit par bande de fréquence
- [✅] Dé-essing, dé-clicking, dé-clipping
- [✅] Auto-gain riding, VAD v2 + Silero fallback
- [✅] Voiceprint léger utilisateur, anti-réverbération pièce

### Presets Intelligents
- [✅] Preset "Universel" intelligent
- [✅] Presets par type de micro
- [✅] Import/Export preset JSON
- [✅] Preset store communautaire
- [✅] Preset schedule

### Audio Pipeline Avancé
- [✅] Support ASIO basse latence
- [✅] Buffer size auto-tuning
- [✅] Multi-périphérique, VB-Cable / Voicemeeter natif
- [✅] Mix micro + son jeu
- [✅] Persistance de configuration fiable en build Nuitka onefile : profil runtime dans `%LOCALAPPDATA%\KommzGamer`, migration du template et fusion non destructive des clés manquantes

### Monitoring & Analytics
- [✅] Overlay temps réel enrichi
- [✅] Dashboard analytics local HTML
- [✅] Export logs session JSON structuré
- [✅] Métriques avancées latence / CPU / RAM
- [✅] Alertes intelligentes
- [✅] HUD flottant limité à l'onglet `Overlay & Couleurs` et boucle Qt dédiée pour le traitement fiable des commandes show/hide

### Fish Audio Premium
- [✅] Moteur TTS `FISH_AUDIO` intégré au pipeline PTT, avec synthèse WAV et lecture sur le routage audio existant
- [✅] Configuration par clé API et Voice ID Fish Audio, sauvegardée localement dans le profil utilisateur
- [✅] Formulaire Fish protégé contre l'écrasement par le polling et sauvegarde explicite de la configuration
- [✅] Rendu Fish expressif : transmission des signaux détectés vers les marqueurs S2 (`[laughing]`, `[angry]`, `[sad]`, `[nervous]`, `[excited]`)
- [✅] Fish Audio reste client-géré : chaque utilisateur fournit sa propre clé API et son propre Voice ID

### Refactoring Flask / Modularisation
- [✅] 13 blueprints créés : config, license, audio, overlay, tts, stt, listen, privacy, scenes, ui, remote, cloud, subs
- [✅] ~81 routes extraites de vtp_core.py
- [✅] vtp_core.py : **24 `@app.route` restantes** (départ : ~105)
- [✅] python -m py_compile vtp_core.py → exit code 0
- [✅] Nettoyage repo : ~436 fichiers morts, ~3,6 Go libérés
- [✅] module license.py : code mort Supabase supprimé
- [✅] listen.py (doublon) supprimé

### Bugs résolus
- [✅] Config non sauvegardée (réassignation AUDIO_CONFIG)
- [✅] load_settings() : filtre destructeur supprimé (92 params perdus)
- [✅] Licence non persistante au démarrage (sync_license_mgr_from_config)
- [✅] Monitoring casque : dtype mismatch float64/float32
- [✅] HUD flottant figé : timeout poll 0.8s → 2s
- [✅] Overlay sous-titres expérimental retiré proprement

### Bugfix stabilisation post-refactoring — ✅ complet
- [✅] BUG 1 — Crash lancement : doublon route_hud_overlay_pos supprimé
- [✅] BUG 2 — Settings : 7 clés manquantes ajoutées dans AUDIO_CONFIG defaults
- [✅] BUG 3 — Licence VTP/VCV : endpoint + payload + champ réponse corrigés
- [✅] BUG 4 — Trial expiré accepté : vérification timestamp 24h ajoutée
- [✅] BUG 5 — Monitoring -9997 : rate_in/rate_out séparés + soxr VHQ
- [✅] BUG 6 — Sous-titres absents : garde overlay_loop étendue
- [✅] BUG 7 — Messages SYS non violet : tk.Text avec tags couleur
- [✅] BUG 8 — Device invalide -9996 : skip silencieux
- [✅] BUG 9 — Grésillements monitoring : détection sample rate dynamique
- [✅] BUG 10 — Création compte KommzVoice : validation license_key
- [✅] BUG 11 — F2/F3 muets : handlers corrigés

### Bugfix stabilisation V5.3
- [✅] Phase 1 : Audit symboles manquants dans les blueprints → RAS
- [✅] Phase 2A : Doublon _listen_now_utc_iso supprimé (listen_bp.py)
- [✅] Phase 2B : _mobile_connected propagé correctement vers vtp_core
- [✅] Phase 3 : Audit contrôles de licence → architecture saine, RAS
- [✅] Phase 4 : IDs audio canoniques (WASAPI::NOM) — commits f529d43 / dc72b3d
- [✅] Fix config persistence mode compilé (3 bugs : migration silencieuse, return prématuré, CONFIG_FILE non importé dans vtp_core)

---

## V5.3.1 — INTERFACE, I18N & MISE À JOUR (✅ terminé)

### Corrections critiques
- [✅] **Vérification des mises à jour cassée pour tous les utilisateurs** : `UPDATE_CHECK_URL` lisait une variable d'environnement vide par défaut, qu'aucun utilisateur ne définit. Le contrôle s'arrêtait sur « Non configuré » depuis toujours. Adresse inscrite dans le code, variable conservée comme surcharge.
- [✅] `auto_update_active` absent des défauts, avec 11 autres drapeaux de modules (12 ajoutés dans `modules/config/config.py`)
- [✅] `<span>` non fermé dans le bloc licence : le parseur absorbait 2 éléments (334 → 336 `id`)
- [✅] 14 attributs `data-fr=tr('...')` non quotés, affichés littéralement à l'écran
- [✅] Variable CSS `--accent` utilisée mais jamais définie
- [✅] Mode Écoute comparé à son propre texte traduit (passage par `dataset.state`)
- [✅] Bascule de module : libellé mis à jour sans les codes d'état (6 branches)

### Internationalisation
- [✅] 45 clés traduites existantes mais branchées sur aucun élément
- [✅] Phrases traduites à moitié : texte nu entre deux `<span>` traduits
- [✅] **Codes d'état neutres côté backend** : le serveur ne décide plus de la langue. Couvre les 16 modules, le pipeline STT/TTS, la santé d'écoute, le diagnostic cloud, le serveur de clonage. Rétrocompatible (champs texte conservés).
- [✅] `applyLang()` recalcule les blocs assemblés en JavaScript (cause d'une classe entière de textes non traduits)
- [✅] Langue système détectée au premier lancement, choix explicite prioritaire ensuite
- [✅] Placeholders traduisibles, guides et site Kommz Voice couverts
- [✅] Paramètre `lang` transmis au service de mise à jour, changelog par langue

### Interface
- [✅] Jetons `:root` de 10 à 24, deux échelles de gris fusionnées
- [✅] Icônes de navigation en SVG (masque CSS, survit aux réécritures `innerHTML`)
- [✅] Barre latérale regroupée : Essentiel / Studio / Avancé
- [✅] Contours de cartes décoratifs retirés (13)
- [✅] Voyants « Micro » et « Mode Écoute » : chrome de bouton retiré
- [✅] Changelog rendu en Markdown dans la fenêtre des nouveautés (HTML échappé avant formatage)
- [✅] Télécommande mobile alignée sur la palette + traduction FR/EN

### Journal d'usage (nouveau)
- [✅] Une ligne JSONL par phrase synthétisée : moteur, classe de coût, latences, langue
- [✅] Route `/usage/summary?days=30` : répartition par moteur et par classe de coût
- [✅] Constat : le coût suit le chemin emprunté, pas le volume. Edge TTS sans coût marginal, clonage sur GPU facturé, cold starts inclus.
- [ ] `audio_seconds` et `chars` non remplis : coût STT à la minute encore incalculable
- [ ] Classes de coût indicatives, à caler sur les factures réelles

### Site & service
- [✅] Lien de téléchargement dérivé de `APP_VERSION` (pointait encore sur V5.3)
- [✅] Formulaire newsletter masqué tant que l'endpoint n'est pas branché
- [✅] Empreinte SHA256 nettoyée d'un préfixe `sha256:` côté serveur, qui bloquait toute installation
- [✅] Résumé de changelog porté à 8 lignes, cache indexé par URL (donc par langue)

---

## V5.4 — PERFORMANCE, SÉCURITÉ & MISE À JOUR (🔄 en cours)

> **Périmètre décidé le 3 octobre 2026.** La V5.4 sort avec ce qui est déjà
> fait, une fois stabilisé : voix clonée prête en quelques secondes et
> maintenue pendant la partie, protection des routes de synthèse, mise à
> jour intégrée, migration des réglages. Les fonctionnalités social /
> streaming / multijoueur passent en V5.5 : plusieurs semaines de travail en
> solo, pendant lesquelles les utilisateurs resteraient en 5.3.1 avec un
> démarrage de deux minutes.

### Avant la sortie — dans l'ordre
- [✅] Kommz-Voice PR #10 : `/warmup` réveille aussi les relais `/synthesis`
  et `/clone`. Déployée.
- [✅] Privé PR #3 : maintien en éveil (warmup toutes les 240 s, arrêt 900 s
  après la dernière activité vocale). Testée sous Windows, fusionnée.
- [✅] Kommz-Voice PR #11 : identifiant de conteneur dans les journaux, fin
  de l'`AsyncUsageWarning`. Fusionnée, **`modal deploy` à faire**.
- [🔄] **Privé PR #1** : le client envoie sa clé à `/warmup` et `/clone`.
  À tester sur `test-v5.4`.
- [🔄] **Bug prioritaire** : le runtime écrit dans `settings.json`, le modèle
  livré avec l'exécutable. Cause trouvée et corrigée (privé PR #4), à tester.
- [✅] Traduction spéculative mesurée sur une session plus longue (voir plus
  bas) : désactivée par défaut, migration de schéma 2 pour les profils 5.3.x.
- [🔄] Auditer les autres routes servies sur `0.0.0.0` (voir Sécurité) :
  garde réseau (privé PR #5), à tester.
- [🔄] Render : statut « chaud » à 600 s au lieu des 300 s de Modal
  (Kommz-Voice PR #12).
- [🔄] Nettoyage : copies obsolètes `modal_*.py` et `vtp_web_server.py` du
  dépôt privé, doublon inutilisé de `kommz_tts_generator` dans
  `modules/tts/tts.py`, fichier parasite nommé `main` à la racine
  (privé PR #6).
- [ ] **En dernier** : build 5.4, puis test du circuit de mise à jour
  5.3.1 → 5.4 sur un vrai PC.
- [ ] Après la sortie : contacter la chaîne IA Professeur (e-mail prêt).

### Mise à jour — finir le circuit
> La V5.3.1 a réparé la détection. L'installation n'avait jamais pu être
> testée : la notification ne s'affichait jamais, donc le bouton n'avait
> jamais servi et la route manquante n'avait jamais été remarquée.

- [✅] **Route `POST /update/install` créée**. Le frontend l'appelait
  (`#btnUpdateNow`) mais elle n'existait ni dans `vtp_core.py` ni dans un
  blueprint : le `fetch` échouait sur « Erreur ouverture mise à jour ».
- [✅] Elle lance `_install_update_background()` (`vtp_core.py` ~L5458) dans
  un thread et répond immédiatement, ce que le frontend attendait déjà.
  Cette fonction existait et faisait déjà tout, sans jamais être appelée.
- [✅] Refus explicites : aucune mise à jour disponible ou URL absente → 409.
  Installation déjà en cours → `ok` sans second téléchargement.
- [✅] Champ `unverified` quand le serveur ne fournit pas de SHA256 : le
  client avertit au lieu de laisser installer un binaire non vérifié.
- [✅] Suivi de l'avancement : le client interroge `/status` toutes les 1,5 s
  et relaie chaque état. Le bouton restait muet pendant tout le
  téléchargement.
- [✅] Les 8 messages de progression suivent `CURRENT_UI_LANG`.
- [ ] **Tester le circuit complet 5.3.1 → 5.4** : détection, téléchargement,
  checksum, installation, redémarrage. Jamais fait de bout en bout.
- [ ] Point le plus fragile : `_launch_windows_self_replacer()`, jamais
  exécuté en conditions réelles. Un exécutable qui se remplace pendant qu'il
  tourne, Windows verrouillant le fichier d'un processus actif.

### Sécurité — `/status` exposé sur le réseau local (✅ corrigé)
- [✅] **Toutes les clés d'API étaient lisibles sans authentification** sur
  `http://<ip-lan>:8770/status`, le serveur écoutant sur `0.0.0.0` pour la
  télécommande mobile. Deepgram, OpenAI, Azure, ElevenLabs, Google, AWS,
  Fish, Kommz Voice, les deux licences, l'e-mail du compte, le chemin
  contenant le nom de session Windows.
- [✅] Valeurs complètes réservées à `127.0.0.1`. Masquage ailleurs, 4
  derniers caractères conservés. `?safe=1` force le masquage en local pour
  produire un dump partageable (`status_redacted: true`).
- [✅] Vérifié sur un dump réel : 15 champs sensibles, 0 fuite, 342 champs
  non sensibles intacts.
- [ ] Auditer les **autres routes** servies sur `0.0.0.0` avec le même
  regard. `/status` a été corrigé parce qu'on l'a regardé ; rien ne dit que
  c'est la seule.
- [ ] Décider si `/remote` doit exiger un jeton d'appairage plutôt que la
  seule présence sur le réseau.

### Tests qui testent vraiment le logiciel (✅ prêt)
> 23 fonctions de `tests/` comparaient des nombres écrits dans le test lui-même (par exemple
> `default_threshold = 120`) : elles ne pouvaient jamais échouer.
- [✅] `tests/_source.py` relit `vtp_core.py` avec `ast` (le fichier ne s'importe pas hors Windows) :
  tables de presets, profils de bruit, presets expressifs, et la fonction `_apply_voice_focus_signal`.
- [✅] `test_presets.py`, `test_voice_focus.py`, `test_watchdog.py` réécrits sur les vraies données et le vrai
  code (le script `watchdog.py` avec un faux sous-processus). Contrôle par mutation : casser un gain, une borne,
  une clé de preset ou la relance du watchdog fait échouer au moins un test.
- [✅] `.github/workflows/tests.yml` lance `pytest` à chaque PR (hors `test_smoke.py`, réservé à Windows).
- [ ] Écart connu, marqué `xfail` : le réglage par défaut `listen_watchdog_idle_threshold_s` vaut 240 s dans
  `config.py` alors que le moteur le ramène à 180 s. À corriger avec `SETTINGS_SCHEMA_VERSION` et
  `_SETTINGS_MIGRATIONS`.
### Test de démarrage : le bon port et les vraies routes (✅ prêt, à exécuter sous Windows)
> `tests/test_smoke.py` interrogeait le port 8790 et les routes `/config` et `/audio/listen/health`, qui n'existent pas :
> il ne pouvait pas passer. L'application écoute sur 8770.
- [✅] Port 8770, routes `/status`, `/audio/devices`, `/` et `/guide/view/general`. Si Kommz Gamer tourne déjà, le test
  se saute avec un message ; si l'application ne démarre pas, il échoue avec le code de sortie.
- [✅] Deux tests statiques, valables partout, vérifient que le port et les routes existent dans le code ;
  les 4 tests qui lancent l'application se sautent hors Windows. La CI exécute donc tout le dossier `tests/`.
- [ ] À exécuter sous Windows : `.venv\Scripts\python.exe -m pytest tests\test_smoke.py -v` (Kommz Gamer fermé).

### Compilation : refuser un exe dont les deux versions diffèrent (✅ prêt, à tester sous Windows)
> Lancée depuis les sources, l'application lit `version.txt` ; compilée, elle utilise `APP_BUILD_VERSION`
> (`vtp_core.py`) ; `final_build.bat` nomme l'exe d'après `version.txt`. Des valeurs différentes donnent un
> exe qui porte un numéro et en affiche un autre.
- [✅] `scripts/check_version.py` compare les deux valeurs et affiche les deux, avec la ligne de `vtp_core.py`.
- [✅] `final_build.bat` l'appelle en étape 0, avant le nettoyage de `dist`, et s'arrête si elles diffèrent.
- [✅] `tests/test_check_version.py` : 8 tests, dont un qui échoue si `version.txt` et `APP_BUILD_VERSION`
  divergent dans le dépôt, et un qui garde `final_build.bat` en ASCII avec fins de ligne CRLF.
- [ ] À essayer sous Windows : lancer `final_build.bat` avec des versions identiques, puis avec `version.txt`
  modifié.

### Liens GitHub : l'organisation KommzAI partout (✅ prêt)
> Le code, les scripts et les modèles renvoyaient encore vers `Kommz-Gamer/Kommz-Gamer` et `Kommz-Gamer/Kommz-Voice`,
> alors que le site et la bannière AGPL utilisent `KommzAI`. L'ancienne adresse redirige, mais mieux vaut une seule.
- [✅] `modules/listen/__init__.py`, `web/index.html`, `scripts/build_portable.bat`, `scripts/build_installer.nsi`,
  `release-template.*.md` et `.github/ISSUE_TEMPLATE/config.yml` pointent vers `KommzAI/...`.
- [ ] Prend effet dans le dépôt public au prochain `export_community.ps1`.

### Premier lancement : aide au câble audio virtuel (✅ prêt, à tester sur Windows)
> Un joueur sans VB-Cable ne comprenait pas pourquoi le jeu n'entendait pas la voix traduite.
- [✅] `web/index.html` : `showCableHintIfNeeded()` affiche une carte discrète (bas gauche) si aucune
  sortie audio ne contient « cable », « vb-audio » ou « voicemeeter ». Boutons : guide d'installation,
  « Plus tard », « Ne plus afficher » (mémorisé dans `kommz_cable_hint_dismissed`). Elle attend la fin de
  l'écran de démarrage et passe au-dessus du portail de licence.
- [ ] À vérifier sur un PC Windows réel : avec et sans VB-Cable, avec Voicemeeter seul.
- [ ] Idée : une courte vidéo d'installation de VB-Cable dans le guide.

### Cold start TTS — diagnostiqué, corrigé côté client (🔄 reste à mesurer)
> `tts_ms: 20334.7` pendant que l'interface affichait « en ligne ».
> Hypothèse initiale démentie : le warmup **atteint bien** le conteneur GPU
> (`warmup` appelle `xtts_actor.warmup.remote()`, méthode de la classe A10G).
> Le problème était ailleurs, et il y en avait trois.

- [✅] **Un warmup raté comptait comme réussi.** `_last_xtts_warmup_ts` était
  écrit hors du `if ok`. Voyant vert sur un serveur froid, et cooldown de 90 s
  bloquant la nouvelle tentative. Corrigé : `_last_xtts_warmup_ok_ts` séparé,
  retry à 12 s après échec.
- [✅] **Le repli sur `/health` ne réveillait rien.** Côté Modal, `health` est
  une `@app.function` distincte, sans GPU, qui renvoie une constante. Repli
  supprimé.
- [✅] **L'indicateur comparait `cooldown * 1.5` (135 s)** à la place de la
  fenêtre d'extinction Modal (300 s). Corrigé, réglable via
  `KOMMZ_XTTS_SCALEDOWN_WINDOW`.
- [✅] `/status` expose `xtts_warmup_last_ok_ts` et `xtts_warmup_last_error`.
- [✅] Modal : les 4 relais web tournaient sur l'image complète (torch + TTS +
  transformers) pour renvoyer un JSON. Image légère, volume retiré.
- [✅] Modal : `health` annonce `reflects_gpu_state: false`.
- [✅] Modal : `min_containers` / `scaledown_window` sont lus **au déploiement,
  sur la machine qui déploie**. Un secret Modal arrive trop tard. Documenté
  dans le fichier, valeurs affichées pendant le deploy.
- [✅] **Mesuré : `load_time=62.20s`.** Le volume `kommz-xtts-cache` était
  monté sur `/root/.local/share/tts` mais un `modal.Volume` ne conserve rien
  sans `commit()`, jamais appelé. Le modèle était donc retéléchargé à chaque
  cold start. Modèle figé dans l'image via `.run_function(_bake_xtts_model)`,
  volume retiré du montage (un volume monté masque l'image au même chemin).
- [✅] **`xtts_warmup_last_ts` valait 0.0 après un démarrage complet** : le
  warmup ne partait jamais. Il était placé derrière
  `refresh_license_states_from_server()`, dont le timeout sur Render en
  gratuit déclenchait l'exception qui sautait l'appel. Warmup hissé avant la
  vérification de licence, sans condition.
- [✅] **Les 28 s manquantes identifiées** : `import_tts=26.64s`, contre
  `import_torch=2.21s` et `cuda_init=0.05s`. C'est l'import du paquet Coqui,
  lu fichier par fichier sur le système de fichiers paresseux de l'image.
- [✅] **Instantané mémoire Modal** : chargement scindé en
  `@modal.enter(snap=True)` (imports + modèle CPU, 57 s) et
  `@modal.enter(snap=False)` (CUDA + transfert, **1,21 s**). Vérifié : après
  `Restoring Function from memory snapshot`, aucune ligne `load_cpu`.
  Réversible par `XTTS_MEMORY_SNAPSHOT=0`.
- [✅] **Référence réduite côté relais** : 5 097 682 → 896 044 octets (5,7×),
  après le téléchargement Supabase et avant le saut vers le GPU. La réduction
  côté client ne concerne que le chemin `/clone`, pas `/v1/synthesis`.
- [✅] **Cache de référence dans le relais**, clé = SHA-1 de
  `clé d'API | voice_id`. Elle était retéléchargée à chaque phrase (1,19 s).
- [✅] Requête complète sur conteneur chaud : **6,19 s**, contre 116,5 s puis
  26,7 s. `rtf` de 1,254 à 0,431.
- [ ] **Mesurer un démarrage à froid propre** : attendre l'extinction (300 s)
  sans redéployer entre-temps. Chaque `modal deploy` invalide l'instantané et
  le premier démarrage suivant le refabrique.
- [ ] Vérifier `ref_source=cache` sur la deuxième phrase d'une session.
- [ ] Surveiller la montée en charge : trois conteneurs démarrés dans un même
  test, chacun payant le chargement complet tant que l'instantané n'existe
  pas. Envisager `max_containers` si le cas se reproduit après stabilisation.
- [ ] Décider `min_containers=1` ou non **sur le coût mesuré**. A10G en
  continu ≈ 790 $/mois : hors de question par défaut. Piste réaliste :
  warmup déclenché à l'ouverture de l'application et à l'entrée en partie,
  plutôt qu'un conteneur maintenu allumé.
- [✅] Démarrage à froid propre mesuré : warmup 6,2 s au lieu de 115,6 s.
- [✅] Relais `/synthesis` réveillé par chaque warmup (Kommz-Voice PR #10).
- [✅] Maintien en éveil côté client pendant une partie : un warmup toutes
  les 4 min tant qu'il y a eu une activité vocale dans les 15 dernières
  minutes (réglable). Testé sous Windows : phrase après 10 min de silence en
  6,78 s, arrêt à 904 s.
- [ ] Un redémarrage du relais `/synthesis` observé malgré les pings : à
  trancher avec les identifiants de conteneur (PR #11).

### Render — keepalive désactivé et statut faux
- [ ] `XTTS_KEEPALIVE_ENABLED` vaut `"0"` par défaut : **le keepalive ne tourne
  pas** sauf variable définie sur Render.
- [ ] `prewarm_xtts_sync()` porte le même bug que le client : horodatage écrit
  quel que soit le résultat, repli sur `/health` qui ne réveille rien.
- [ ] `_get_xtts_runtime_status()` considère « chaud » pendant **600 s** alors
  que Modal éteint à **300 s**. Il est donc structurellement faux la moitié du
  temps. Aligner sur la fenêtre réelle.
- [ ] Rappel : Render en gratuit s'endort, ce qui tue le thread de keepalive.
  Un keepalive hébergé là n'est pas fiable par construction.

### Configuration — les corrections de défauts n'atteignaient personne
> Découvert en cherchant pourquoi un seuil abaissé de 6 à 3 restait à 6 sur
> une machine de test. Le problème dépasse largement ce réglage.

- [✅] **Versionnement du schéma de configuration**
  (`SETTINGS_SCHEMA_VERSION`, `_SETTINGS_MIGRATIONS` dans `config.py`). Le
  fichier utilisateur gagne toujours sur le défaut du code : un utilisateur
  existant gardait donc éternellement une ancienne valeur, même quand cette
  valeur était un bug corrigé depuis. C'est ce qui est arrivé à
  `auto_update_active` en V5.3.1, puis à
  `speculative_translation_min_new_chars`. **Les utilisateurs les plus
  anciens étaient ceux qui recevaient le moins de correctifs.**
- [✅] Seules les clés explicitement listées sont réalignées, une seule fois,
  puis le numéro de schéma est avancé. Aucune autre clé n'est touchée :
  périphériques, raccourcis, clés d'API, presets sont conservés.
- [✅] Migration non répétée : après réalignement, un réglage manuel est de
  nouveau respecté, y compris s'il reprend l'ancienne valeur.
- [✅] `settings_schema_version` exclu de `_merge_missing_template_settings()`
  — sinon un modèle livré avec un build récent l'injecterait dans un ancien
  profil et la migration se croirait déjà faite.
- [✅] Vérifié sur trois cas : ancien profil migré, réglage manuel postérieur
  conservé, installation neuve correcte dès le départ.
- [ ] Documenter la procédure côté support : **fermer l'application avant**
  toute modification manuelle du fichier. Tant qu'elle tourne, le premier
  réglage touché dans l'interface réécrit tout le fichier depuis la mémoire.

### Voice Focus : mesuré, à trancher en vraie partie
- [✅] Mesure du 5 octobre 2026 (vidéo française propre, nova-3) : avec
  Voice Focus « Auto », mots inventés (« couchonnements », « guichet sous
  souvenir ») ; avec « Off », phrases presque exactes. Sur une voix propre,
  le filtre dégrade le signal envoyé à la reconnaissance.
- [ ] Mesurer en vraie partie (bruits de jeu) : « Off » contre « Normal »,
  mêmes lignes `⚡ [Allié]` comparées. Si « Off » gagne aussi, changer le
  défaut (`ally_voice_focus_mode`, aujourd'hui `balanced`) avec une migration
  de schéma ; sinon corriger le filtre pour qu'il épargne la voix.

### Traduction spéculative — mesurée, dépriorisée
- [✅] Première mesure valide (seuil réellement à 3) : 17 lancées, 1 réussite,
  12 échecs. Fonctionne, mais rarement.
- [✅] Diagnostic d'échec ajouté : `speculative_near_misses`,
  `speculative_last_miss_ratio`, texte final et clé la plus proche. Un échec
  de deux caractères et un échec total se comptaient pareil.
- [✅] Normalisation corrigée : apostrophes supprimées au lieu d'être
  remplacées par une espace (`hes` vs `he's`, `lennemi` vs `l ennemi`).
- [✅] **Seconde mesure (5 octobre 2026)** : 23 phrases, 105 lancées,
  4 réussites, 19 échecs dont 17 de peu (dernier ratio 0,985). Le dernier
  partiel manque presque toujours les derniers mots de la phrase.
- [✅] **Désactivée par défaut en 5.4** : environ 5,5 fois plus d'appels
  DeepL (quota en caractères) pour une phrase sur six accélérée. Migration
  de schéma 2 pour réaligner les profils existants. Code et compteurs
  conservés.
- [ ] Piste pour une reprise : ne traduire qu'un partiel jugé stable (fin de
  phrase détectée, ou partiel inchangé depuis un court délai) plutôt qu'à
  chaque croissance du texte.

---

## V5.5 — SOCIAL, STREAMING & MULTIJOUEUR

> Reporté de la V5.4 le 3 octobre 2026. Contenu inchangé.

### Endpointing & tours de parole
> Piste issue d'un échange public. Deux corrections apportées par
> l'interlocuteur sont intégrées ci-dessous : elles changent le coût réel de
> la tâche et le levier à actionner. **Rien n'est encore mesuré.**

**Étape 1 — Mesurer avant de décider**
- [ ] Relever `ally_voice_rate_limited` (déjà exposé dans `/status`) sur une vraie session à 4-5 joueurs. Jamais consulté à ce jour.
- [ ] Comparer la somme `stt_ms + translate_ms + tts_ms` au délai réellement ressenti. L'écart est l'endpointing.
- [ ] Sans ces deux chiffres, tout ce qui suit est de la spéculation.

**Étape 2 — Le moins coûteux en temps de développement d'abord**
- [✅] **Traduction spéculative sur les partiels.** Deux obstacles trouvés en ouvrant le code : `interim_results` n'était pas activé (Deepgram ne l'active pas par défaut, donc **aucun partiel n'arrivait**), et le gestionnaire les rejetait dès sa première ligne.
  - Approche retenue : **préchauffage** plutôt que restructuration de la validation. `translate_text()` a déjà un cache `SHADOW_CACHE` clé `(texte, langue)`. On traduit les partiels en tâche de fond ; si le texte final correspond, la traduction est prête. Sinon le chemin normal s'applique.
  - Conséquence : aucun texte spéculatif affiché ni prononcé, logique de validation **strictement inchangée**. Le risque de divergence disparaît.
  - Garde-fous : un seul appel en vol, intervalle minimum, delta de texte minimum, interrupteur `speculative_translation_enabled`. Mesuré : 40 partiels en rafale → 8 traductions, jamais 2 simultanées.
- [✅] **Première mesure : échec.** 63 spéculations, 0 réussite sur 21 phrases. `smart_format` ajoute ponctuation et majuscules à la finalisation, donc partiel et final n'ont jamais la même clé.
- [✅] **Corrigé** : cache dédié indexé sur une forme normalisée, `translate_text()` laissée intacte. Second défaut trouvé au test : le seuil de caractères nouveaux (6) écartait le dernier partiel, celui qui compte. Abaissé à 3 après mesure comparative.
- [ ] **Remesurer en session réelle.** La simulation donne 4/4 sur des callouts typiques, mais une simulation ne prouve rien. Si le taux reste faible, désactiver via `speculative_translation_enabled`.
  - Coût financier : traduire sur le partiel génère quelques appels annulés,
    marginal chez Deepgram. **Ne jamais spéculer sur le TTS cloné** : une
    synthèse GPU lancée puis jetée se paie plein tarif, cold start compris.
    La spéculation s'arrête à la traduction.
- [ ] **Éviction prioritaire de la file voix alliés, plutôt que relèvement du plafond.**
  - Correction d'une idée fausse : augmenter la limite (6 lectures / 8 s) n'aide pas en squad. La lecture est **séquentielle** : jouer cinq lignes traduites à la suite produit une latence pire que d'en abandonner quatre.
  - Le vrai levier est donc *quoi* abandonner. Aujourd'hui l'éviction est arbitraire, premier arrivé premier servi. Elle devrait être prioritaire : dernier locuteur, ou celui qui appelle le jeu.
  - Prérequis manquant : aucun signal de priorité n'existe. Rien ne distingue un callout tactique d'une discussion de fond.
- [ ] Remesurer après ces deux changements.

**Étape 3 — Décision, pas tâche**
- [ ] **Décider** si l'endpointing par locuteur vaut son coût, au vu des mesures.
  - **Correction importante** : je pensais que l'étiquetage (voiceprint matching, prévu plus bas) et l'endpointing par locuteur étaient deux chantiers distincts, le second exigeant une diarisation complète. C'est faux. L'embedding calculé pour dire « qui a parlé » est **le même signal** qui sert à détecter un changement de locuteur. Un seul passage sur le flux mélangé produit les deux, il suffit d'un seuil de changement.
  - Conséquence : pas besoin de diarisation générale ni de séparation de sources. Juste assez d'embedding pour savoir que le tour a changé. Le chantier est nettement plus petit que les « plusieurs semaines » initialement estimées.
  - À grouper avec le voiceprint matching de la section Voice Profiles : les deux sortent du même calcul, les traiter séparément serait du travail en double.
- [ ] Si retenu : dimensionner les presets d'endpointing selon la taille du squad, et non seulement selon le jeu (`LISTEN_GAME_PRESETS` fait varier `hard_flush_words` 6↔7 et `punct_min_words` 2↔3 par jeu, jamais par nombre de joueurs).

### Overlay OBS / Streaming
- [ ] Overlay HTML5 natif pour OBS Studio
- [ ] Widgets customisables (couleurs, polices, position, animations)
- [ ] Overlay transcription temps réel
- [ ] Overlay traduction
- [ ] Overlay mode équipe
- [ ] Intégration StreamElements / Streamlabs
- [ ] Alertes overlay streaming (don, sub, follow, raid → TTS vocal)
- [ ] Chat overlay inversé (Twitch/YouTube → TTS casque)

### Multilingue Avancé
- [ ] Traduction simultanée vers N langues en parallèle
- [ ] Détection automatique de la langue source
- [ ] Glossaire custom par jeu
- [ ] Mode interprète bidirectionnel
- [ ] Sous-titres overlay in-game
- [ ] Traduction texte + voix simultanée

### Voice Profiles & Équipe
- [ ] Reconnaissance vocale du joueur (voiceprint matching)
  - **À traiter avec l'endpointing par locuteur ci-dessus** : le même
    embedding sert à étiqueter et à détecter le changement de tour. Un
    seul passage, deux usages.
- [ ] Profil vocal par contact, icônes/couleurs par joueur
- [ ] Log "qui a dit quoi" exportable
- [ ] Mode Squad Sync
- [ ] Partage de preset entre amis

### TTS & Soundboard
- [ ] TTS thématiques par jeu
- [ ] Soundboard intégrée (sons custom, hotkeys F1-F12)
- [ ] Banque de sons communautaire
- [ ] TTS personnalisé (pitch, speed, modèle vocal)
- [ ] Voice changer léger temps réel

### Intégrations Discord
- [ ] Rich Presence (jeu détecté, preset actif, langue)
- [ ] Bot slash commands (/stats, /preset, /langue)
- [ ] Webhooks sortants (état session → serveur Discord custom)
- [ ] Twitch/YouTube chat → TTS casque
- [ ] Intégration Stream Deck
- [ ] Ducking Spotify automatique

### Benchmark Fish Speech sur Modal
- [ ] Vérifier la licence commerciale Fish Speech avant tout déploiement client
- [ ] Créer un endpoint Modal isolé, sans modifier les endpoints GPT-SoVITS et XTTS existants
- [ ] Benchmark sur GPU adapté : chargement modèle, VRAM, cold start, temps au premier audio, durée de rendu et RTF
- [ ] Mesurer la concurrence PTT (1, puis 2, puis 3 requêtes), la file d'attente et le coût GPU par minute générée
- [ ] Comparer Fish Speech, GPT-SoVITS et XTTS sur la qualité de clonage, l'expressivité, la latence jeu/Discord et le coût
- [ ] Décider sur résultats mesurés si Fish remplace totalement, partiellement ou reste une option Premium

---

## V5.6 — PLATEFORME & ÉCOSYSTÈME

- [ ] Plugin Marketplace intégrée (parcourir, installer, désinstaller)
- [ ] SDK développeur (API Python + JS + doc)
- [ ] Sandbox plugins (permissions, sécurité)
- [ ] API REST stable v1 (OpenAPI/Swagger)
- [ ] WebSocket API (flux audio, état, événements)
- [ ] SDKs officiels : Python, JS/TS, C#/.NET
- [ ] App companion Android + iOS
- [ ] Compte Kommz (inscription, connexion, profil)
- [ ] Sync presets + config cloud
- [ ] Cloud stats dashboard web
- [ ] Leaderboard communautaire
- [ ] Patreon intégration native
- [ ] Auto-updater silencieux (delta updates, rollback, canaux stable/beta/nightly)
- [ ] Abonnement Premium (voix TTS pro, traduction avancée, support prioritaire)
- [ ] Mode tournoi / esport (logs certifiés, export preuves)
- [ ] Site web : kommzgamer.com (landing, docs, forum, wiki)

---

## Vision V6+ — IA & INNOVATION

- [ ] STT local 100% offline (Whisper.cpp / Faster-Whisper)
- [ ] TTS local (Piper TTS, XTTS v2)
- [ ] Traduction locale (NLLB / OPUS-MT)
- [ ] Voice cloning (30s d'enregistrement)
- [ ] Ta voix traduite dans TA voix
- [ ] Anti-bruit deep learning sur ton setup
- [ ] Séparation de sources audio (demucs)
- [ ] Intégration console (PS5, Xbox via carte acquisition)
- [ ] Mode Coach IA (analyse callouts, suggestions tactiques)
- [ ] Traduction temps réel <200ms
- [ ] Parties clés open source + programme contributeurs
