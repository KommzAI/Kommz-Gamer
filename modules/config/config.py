"""
Module de configuration pour KommzGamer V5.4

Ce module contient toutes les constantes de configuration, le dictionnaire AUDIO_CONFIG,
et les fonctions de gestion de la configuration (chargement/sauvegarde).

RÈGLE CRITIQUE: Ce module ne doit JAMAIS importer quoi que ce soit de vtp_core.py
pour éviter les imports circulaires.
"""

import os
import sys
import copy
import json
import time
import re
import shutil
import tempfile
from pathlib import Path

# ============================================================================
# REMOTE ENDPOINT CONSTANTS
# ============================================================================

DEFAULT_KOMMZ_GPT_API_URL = os.environ.get(
    "KOMMZ_DEFAULT_GPT_API_URL",
    "",
).strip().rstrip("/")

# ============================================================================
# CONFIG FILE PATH
# ============================================================================

_BASE_DIR = Path(__file__).parent.parent.parent

def _is_compiled_runtime() -> bool:
    """Détecte PyInstaller/Nuitka, y compris le onefile sans marqueur sys."""
    if getattr(sys, "frozen", False) or getattr(sys, "__compiled__", False):
        return True
    try:
        executable = Path(sys.executable).resolve()
        if executable.suffix.lower() == ".exe" and executable.stem.lower() not in {"python", "pythonw"}:
            return True
        extracted = Path(__file__).resolve()
        temp_root = Path(tempfile.gettempdir()).resolve()
        return temp_root in extracted.parents
    except Exception:
        return False

def _get_persistent_config_dir() -> Path:
    """Retourne le dossier persistant, distinct des fichiers Nuitka temporaires."""
    is_compiled = _is_compiled_runtime()
    if is_compiled:
        appdata = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / "KommzGamer"
    return _BASE_DIR

def _resolve_config_file() -> Path:
    """Résout le fichier runtime depuis le template livré avec l'application."""
    config_dir = _get_persistent_config_dir()
    is_compiled = _is_compiled_runtime()
    # 1. Variable d'environnement si déjà chargée
    env_file = os.environ.get("KOMMZ_SETTINGS_FILE", "")
    if env_file:
        p = config_dir / env_file
        if p.exists():
            return p
    # search_dirs : exe_dir (priorité) + bundle + dossier de configuration.
    search_dirs = [_BASE_DIR]
    if is_compiled:
        try:
            exe_dir = Path(sys.executable).resolve().parent
            if exe_dir not in search_dirs:
                search_dirs.insert(0, exe_dir)
        except Exception:
            pass
        # Les données Nuitka/PyInstaller, lorsqu'elles sont incluses, vivent ici.
        meipass = getattr(sys, "_MEIPASS", "")
        if meipass:
            mp = Path(meipass)
            if mp not in search_dirs:
                search_dirs.append(mp)
    if is_compiled:
        legacy_files = ["settings.json", "settings.private.json"]
    else:
        legacy_files = ["settings.private.json", "settings.json"]
    for fname in legacy_files:
        for base in search_dirs:
            legacy = base / fname
            if not legacy.exists():
                continue
            dest_name = "settings.private.json" if is_compiled else fname
            dest = config_dir / dest_name
            if not dest.exists():
                try:
                    config_dir.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(legacy, dest)
                except Exception as e:
                    print(f"⚠️ Config migration error: {e}", file=sys.stderr, flush=True)
                    try:
                        config_dir.mkdir(parents=True, exist_ok=True)
                        dest.write_text("{}", encoding="utf-8")
                    except Exception as e2:
                        print(f"⚠️ Config fallback create error: {e2}", file=sys.stderr, flush=True)
            if dest.exists():
                return dest
            # migration échouée → continue la boucle
    # fallback si aucun legacy trouvé ou migration impossible
    dest = config_dir / "settings.private.json"
    try:
        config_dir.mkdir(parents=True, exist_ok=True)
        if not dest.exists():
            dest.write_text("{}", encoding="utf-8")
    except Exception as e:
        print(f"⚠️ Config dir create error: {e}", file=sys.stderr, flush=True)
    # Garder un template visible à côté de l'exécutable pour les distributions portables.
    if is_compiled:
        try:
            exe_dir = Path(sys.executable).resolve().parent
            template = exe_dir / "settings.json"
            if not template.exists():
                exe_dir.mkdir(parents=True, exist_ok=True)
                template.write_text("{}", encoding="utf-8")
        except Exception as e:
            print(f"⚠️ Config template create error: {e}", file=sys.stderr, flush=True)
    return dest


def _merge_missing_template_settings() -> None:
    """Complète un profil AppData ancien sans remplacer ses valeurs existantes."""
    if not _is_compiled_runtime():
        return
    template_name = os.environ.get("KOMMZ_SETTINGS_FILE", "settings.private.json")
    template_candidates = [
        Path(sys.executable).resolve().parent / template_name,
        Path(sys.executable).resolve().parent / "settings.json",
        _BASE_DIR / template_name,
        _BASE_DIR / "settings.json",
    ]
    template_path = next((p for p in template_candidates if p.exists() and p != CONFIG_FILE), None)
    if template_path is None or not CONFIG_FILE.exists():
        return
    try:
        template = json.loads(template_path.read_text(encoding="utf-8-sig"))
        current = json.loads(CONFIG_FILE.read_text(encoding="utf-8-sig"))
        if not isinstance(template, dict) or not isinstance(current, dict):
            return
        # settings_schema_version est exclu : si un template livre avec un
        # build recent l'injectait dans un ancien profil, la migration serait
        # consideree comme deja faite et les defauts corriges ne seraient
        # jamais appliques. Seul _apply_settings_migrations ecrit cette cle.
        missing = {
            key: value
            for key, value in template.items()
            if key not in current and key != "settings_schema_version"
        }
        if missing:
            current.update(missing)
            CONFIG_FILE.write_text(
                json.dumps(current, indent=4, ensure_ascii=False),
                encoding="utf-8",
            )
            print(
                f"[CONFIG] {len(missing)} cles ajoutees depuis {template_path}",
                file=sys.stderr,
                flush=True,
            )
    except Exception as e:
        print(f"[CONFIG] Fusion template ignoree : {e}", file=sys.stderr, flush=True)

CONFIG_FILE = _resolve_config_file()
_merge_missing_template_settings()

# Debug logs
import sys
print(f"[CONFIG] CONFIG_FILE résolu : {CONFIG_FILE}", file=sys.stderr, flush=True)
print(f"[CONFIG] Fichier existe : {CONFIG_FILE.exists()}", file=sys.stderr, flush=True)


# ============================================================================
# EDITION PROFILE CONSTANTS
# ============================================================================

EDITION_PROFILE = str(os.environ.get("KOMMZ_EDITION_PROFILE", "community") or "private").strip().lower()
if EDITION_PROFILE not in {"private", "community"}:
    EDITION_PROFILE = "private"

COMMUNITY_EDITION = EDITION_PROFILE == "community"

CLOUD_FEATURES_ENABLED = str(
    os.environ.get("KOMMZ_CLOUD_FEATURES", "1" if EDITION_PROFILE == "private" else "0") or "0"
).strip().lower() in {"1", "true", "yes", "on"}


# ============================================================================
# DEFAULT KOMMZ CLOUD URLS
# ============================================================================

DEFAULT_KOMMZ_VOICE_URL = ""
DEFAULT_KOMMZ_SYNTHESIS_URL = ""
DEFAULT_KOMMZ_WHISPER_URL = ""
DEFAULT_KOMMZ_HEALTH_URL = ""
DEFAULT_KOMMZ_WARMUP_URL = ""
DEFAULT_KOMMZ_GENERATE_URL = ""
DEFAULT_KOMMZ_SYNTHESIS_ENDPOINT = ""
DEFAULT_KOMMZ_WHISPER_ENDPOINT = ""
DEFAULT_KOMMZ_VOICE_CLONE_URL = ""
DEFAULT_KOMMZ_VOICE_LIST_URL = ""
DEFAULT_KOMMZ_VOICE_DELETE_URL = ""
DEFAULT_KOMMZ_VOICE_PREVIEW_URL = ""
DEFAULT_KOMMZ_VOICE_DOWNLOAD_URL = ""
DEFAULT_KOMMZ_VOICE_UPLOAD_URL = ""
DEFAULT_KOMMZ_VOICE_SHARE_URL = ""
DEFAULT_KOMMZ_VOICE_IMPORT_URL = ""
DEFAULT_KOMMZ_VOICE_EXPORT_URL = ""
DEFAULT_KOMMZ_VOICE_SEARCH_URL = ""
DEFAULT_KOMMZ_VOICE_RATE_URL = ""
DEFAULT_KOMMZ_VOICE_REPORT_URL = ""


# ============================================================================
# AUDIO_CONFIG - Configuration principale
# ============================================================================

AUDIO_CONFIG = {
    "is_listening": True,
    "is_speaking": False,
    "bypass_mode_active": False,
    "monitoring_enabled": False,
    "monitoring_mic_gain": 1.0,
    "monitoring_game_gain": 0.3,
    "monitoring_output_device": None,
    "game_input_device": None,
    "game_output_device": None,
    "mic_input_device": None,
    "output_device": None,
    # --- Champs canoniques V5.4 (résolution audio stable hostapi+nom) ---
    "game_input_device_key": "",
    "game_output_device_key": "",
    "game_input_device_runtime": {},
    "game_output_device_runtime": {},
    "target_lang": "en",
    "source_lang": "fr",
    "voice": "fr-FR-DeniseNeural",
    "gender": "female",
    "volume": 1.0,
    "speed": 1.0,
    "pitch": 1.0,
    "sensitivity": 0.5,
    "vad_threshold": 0.5,
    "noise_reduction": True,
    "echo_cancellation": True,
    "auto_gain_control": True,
    "buffer_size": 1024,
    "sample_rate": 48000,
    "channels": 2,
    "chunk_size": 1024,
    "format": "int16",
    "latency": "low",
    "quality": "high",
    "engine": "edge",
    "api_key": "",
    "deepgram_api_key": "",
    "openai_api_key": "",
    "elevenlabs_api_key": "",
    "azure_api_key": "",
    "google_api_key": "",
    "aws_access_key": "",
    "aws_secret_key": "",
    "aws_region": "us-east-1",
    "azure_region": "westus",
    "google_region": "us-central1",
    # Canonical PTT key. ``ptt_key`` is migrated on load for older profiles.
    "ptt_hotkey": "f9",
    "voice_gender": "Female",
    "ptt_mode": False,
    "ptt_release_delay": 0.3,
    "overlay_enabled": False,
    "overlay_position": "top-right",
    "overlay_opacity": 0.8,
    "overlay_color": "#00FF00",
    "ally_color": "#00FFFF",
    "subtitle_duration": 5.0,
    "subtitle_max_lines": 3,
    "subtitle_font_size": 24,
    "subtitle_font_family": "Arial",
    "subtitle_background": True,
    "subtitle_background_color": "#000000",
    "subtitle_background_opacity": 0.5,
    "privacy_mode": False,
    "privacy_keywords": [],
    # Drapeaux de modules absents des defauts : sans valeur ici, un poste
    # neuf lisait False via .get(..., False), et la case restait morte.
    # auto_update_active est le seul active par defaut : un correctif de
    # securite que personne ne recoit ne sert a rien. La case reste
    # decochable dans Modules systeme.
    # Traduction spéculative : on traduit les partiels Deepgram pour
    # préchauffer le cache. Aucun texte spéculatif n'est affiché ni prononcé.
    # Coût : quelques appels de traduction en plus. Mesurer speculative_hits
    # contre speculative_misses avant de juger si ça sert.
    "speculative_translation_enabled": True,
    "speculative_translation_min_gap_s": 0.45,
    "speculative_translation_min_new_chars": 3,
    "auto_update_active": True,
    "auto_context_active": False,
    "esport_mode_active": False,
    "privacy_sentinel_active": False,
    "seamless_prefix_active": False,
    "shadow_ai_active": False,
    "smart_marker_active": False,
    "stealth_mode_active": False,
    "stream_connect_active": False,
    "tactical_macros_active": False,
    "teamsync_ai_active": False,
    "turbo_latency_active": False,
    "tilt_shield_active": True,
    "smart_commands_active": True,
    "gaming_context_active": True,
    "polyglot_active": False,
    "hybrid_activation_active": False,
    "hybrid_activation_threshold": 0.6,
    "hybrid_activation_cooldown": 2.0,
    "hybrid_target_lang": "en",
    "hybrid_fr_enabled": True,
    "hybrid_rts_preset": "balanced",
    "expressive_mode": "auto",
    "expressive_intensity": "medium",
    "expressive_stability": "balanced",
    "expressive_engine": "auto",
    "laugh_detection_enabled": True,
    "laugh_reinforcement_enabled": True,
    "voice_focus_mode": "balanced",
    "voice_focus_v3_enabled": False,
    "voice_focus_v3_calibrated": False,
    "ally_voice_focus_mode": "balanced",
    "ally_competitive_lock": False,
    "ally_competitive_lock_auto": False,
    "listen_quality_preset": "balanced",
    "listen_vad_mode": "auto",
    "listen_noise_suppression": "balanced",
    "listen_echo_cancellation": True,
    "listen_auto_gain": True,
    "listen_buffer_size": 1024,
    "listen_sample_rate": 48000,
    "listen_channels": 1,
    "listen_format": "int16",
    "listen_latency": "low",
    "listen_watchdog_enabled": True,
    "listen_watchdog_idle_threshold_s": 240,
    "listen_watchdog_stream_stale_s": 22,
    "listen_watchdog_restart_cooldown_s": 8,
    "listen_preset_schedule_enabled": False,
    "listen_preset_schedule": [],
    "game_auto_detect_enabled": False,
    "game_fingerprint_enabled": False,
    "scene_auto_apply_enabled": False,
    "scene_library": [],
    "voice_library": [],
    "listen_preset_library": [],
    "quality_preset": "balanced",
    "esport_profile_active": False,
    "trial_voice_mode_enabled": False,
    "license_key": "",
    "license_email": "",
    "license_hwid": "",
    "license_status": "inactive",
    "license_expires_at": None,
    "voice_license_status": "inactive",
    "voice_license_expires_at": None,
    "hud_enabled": False,
    "hud_position_x": 100,
    "hud_position_y": 100,
    "hud_opacity": 0.9,
    "hud_show_user": True,
    "hud_show_ally": True,
    "hud_show_translation": True,
    "kommz_voice_url": DEFAULT_KOMMZ_VOICE_URL,
    "kommz_synthesis_url": DEFAULT_KOMMZ_SYNTHESIS_URL,
    "kommz_whisper_url": DEFAULT_KOMMZ_WHISPER_URL,
    "kommz_health_url": DEFAULT_KOMMZ_HEALTH_URL,
    "kommz_warmup_url": DEFAULT_KOMMZ_WARMUP_URL,
    "kommz_generate_url": DEFAULT_KOMMZ_GENERATE_URL,
    "kommz_synthesis_endpoint": DEFAULT_KOMMZ_SYNTHESIS_ENDPOINT,
    "kommz_whisper_endpoint": DEFAULT_KOMMZ_WHISPER_ENDPOINT,
    "save_debug_audio_files": False,
    "teamsync_input_level": 0.0,
    "teamsync_playback_gain": 1.0,
    # Champ pour le mode essai
    "trial_mode": False,
    "trial_voice_seconds_used_local": 0,
    "voice_license_key": "",
    # --- Clés manquantes ajoutées V5.3 (BUG 2 fix) ---
    "tts_volume":            1.0,
    "tts_engine":            "WINDOWS",
    "edge_voice":            "fr-FR-DeniseNeural",
    "ally_recognition_lang": "en-US",
    "mini_overlay_enabled":  False,
    "kommz_client_id":       "",
    "voice_active_id":       "",
    # --- GPT-SoVITS Modal (V5.4) ---
    "gpt_api_url":           DEFAULT_KOMMZ_GPT_API_URL,
    # --- Fish Audio API (V5.4) ---
    "fish_api_key":          "",
    "fish_voice_id":         "",
}


# ============================================================================
# SETTINGS SCHEMA VERSION & MIGRATIONS (V5.4)
# ============================================================================
# Probleme resolu ici : le fichier utilisateur gagne toujours sur le defaut du
# code. Un utilisateur qui a deja lance une version precedente garde donc
# eternellement l'ancienne valeur, meme si on corrige le defaut. C'est ce qui
# est arrive a auto_update_active (personne ne recevait les mises a jour) puis
# a speculative_translation_min_new_chars (seuil 6 = zero cache hit mesure).
#
# Regle : on ne touche PAS au fichier utilisateur en general. On realigne
# uniquement les cles listees ci-dessous, une seule fois, quand le profil vient
# d'une version de schema anterieure. Apres migration, un reglage manuel de
# l'utilisateur est respecte de nouveau.
SETTINGS_SCHEMA_VERSION = 1

AUDIO_CONFIG["settings_schema_version"] = SETTINGS_SCHEMA_VERSION

# Copie figee des defauts, prise avant tout chargement de fichier.
_DEFAULT_AUDIO_CONFIG = copy.deepcopy(AUDIO_CONFIG)

# version de schema cible -> cles a realigner sur le defaut du code
_SETTINGS_MIGRATIONS = {
    1: (
        # Seuil mesure : a 6, le dernier partiel Deepgram (le seul qui a une
        # chance de correspondre au texte finalise) etait ignore. 3 hits.
        "speculative_translation_min_new_chars",
        "speculative_translation_min_gap_s",
    ),
}


def _apply_settings_migrations(loaded: dict) -> bool:
    """Realigne les cles dont le defaut a change depuis le schema du profil.

    Retourne True si quelque chose a ete modifie (l'appelant doit sauvegarder).
    """
    try:
        from_version = int(loaded.get("settings_schema_version", 0) or 0)
    except (TypeError, ValueError):
        from_version = 0

    if from_version >= SETTINGS_SCHEMA_VERSION:
        return False

    realigned = []
    for target in range(from_version + 1, SETTINGS_SCHEMA_VERSION + 1):
        for key in _SETTINGS_MIGRATIONS.get(target, ()):
            if key not in _DEFAULT_AUDIO_CONFIG:
                continue
            new_value = copy.deepcopy(_DEFAULT_AUDIO_CONFIG[key])
            if AUDIO_CONFIG.get(key) == new_value:
                continue
            AUDIO_CONFIG[key] = new_value
            realigned.append(f"{key}={new_value!r}")

    AUDIO_CONFIG["settings_schema_version"] = SETTINGS_SCHEMA_VERSION
    if realigned:
        print(
            f"[CONFIG] Migration schema {from_version} -> {SETTINGS_SCHEMA_VERSION} : "
            + ", ".join(realigned),
            file=sys.stderr,
            flush=True,
        )
    return True




# ============================================================================
# LICENSE API CONSTANTS
# ============================================================================

LICENSE_API_URL = os.environ.get("KOMMZ_LICENSE_API_URL", "").strip().rstrip("/")
LICENSE_API_CONNECT_TIMEOUT = float(os.environ.get("KOMMZ_LICENSE_CONNECT_TIMEOUT", "8"))
LICENSE_API_READ_TIMEOUT = float(os.environ.get("KOMMZ_LICENSE_READ_TIMEOUT", "45"))
LICENSE_API_RETRIES = int(os.environ.get("KOMMZ_LICENSE_RETRIES", "2"))
LICENSE_ACTIVATE_CONNECT_TIMEOUT = float(os.environ.get("KOMMZ_LICENSE_ACTIVATE_CONNECT_TIMEOUT", "15"))
LICENSE_ACTIVATE_READ_TIMEOUT = float(os.environ.get("KOMMZ_LICENSE_ACTIVATE_READ_TIMEOUT", "45"))
LICENSE_ACTIVATE_RETRIES = int(os.environ.get("KOMMZ_LICENSE_ACTIVATE_RETRIES", "1"))
EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")


# ============================================================================
# HELPER FUNCTIONS (Config-specific only)
# ============================================================================

def _decode_escaped_utf8_runs(text: str) -> str:
    """Décode les séquences UTF-8 échappées dans le texte."""
    import re
    
    def _repl(match):
        chunk = match.group(0)
        try:
            decoded = chunk.encode('latin1').decode('utf-8')
            return decoded
        except Exception:
            return chunk
    
    try:
        return re.sub(r'[À-ÿ]+', _repl, text)
    except Exception:
        return text


def _repair_display_text(value):
    if value is None or not isinstance(value, str):
        return value
    
    try:
        repaired = _decode_escaped_utf8_runs(value)
        return repaired
    except Exception:
        return value
    
    try:
        return value.encode('latin1').decode('utf-8')
    except Exception:
        return value


def _repair_payload_strings(value):
    if isinstance(value, dict):
        return {k: _repair_payload_strings(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [_repair_payload_strings(item) for item in value]
    elif isinstance(value, str):
        return _repair_display_text(value)
    else:
        return value


# Domaines heberges par Kommz. Une edition Community ne doit jamais les
# appeler : ce sont nos GPU et notre facture.
_KOMMZ_HOSTED_DOMAINS = (
    "kommzvoice.onrender.com",
    "kommz-innovations--",
)

# Cles de configuration portant une adresse de service.
_COMMUNITY_ENDPOINT_KEYS = (
    "kommz_voice_url",
    "kommz_synthesis_url",
    "kommz_synthesis_endpoint",
    "kommz_whisper_url",
    "kommz_whisper_endpoint",
    "kommz_health_url",
    "kommz_warmup_url",
    "kommz_generate_url",
    "kommz_url",
    "gpt_api_url",
    "whisper_api_url",
)


def _is_kommz_hosted_url(value: str) -> bool:
    """Vrai si l'adresse pointe vers l'infrastructure Kommz.

    Volontairement base sur une liste de domaines plutot que sur une
    correspondance exacte : les endpoints Modal changent de suffixe selon la
    fonction appelee (`-tts`, `-clone`, `-warmup`, `-health`).
    """
    lowered = str(value or "").strip().lower()
    if not lowered:
        return False
    return any(domain in lowered for domain in _KOMMZ_HOSTED_DOMAINS)


def _apply_edition_profile_constraints() -> bool:
    """
    Applique les contraintes de l'édition Community si nécessaire.
    Retourne True si des modifications ont été appliquées.
    """
    if not COMMUNITY_EDITION:
        return False
    
    modified = False

    # Désactive les fonctionnalités cloud en Community Edition
    if AUDIO_CONFIG.get("hybrid_activation_active", False):
        AUDIO_CONFIG["hybrid_activation_active"] = False
        modified = True

    if AUDIO_CONFIG.get("polyglot_active", False):
        AUDIO_CONFIG["polyglot_active"] = False
        modified = True

    # V5.4 : neutralisation des services heberges par Kommz.
    #
    # L'edition Community n'utilise pas notre infrastructure : chaque
    # utilisateur deploie la sienne. Vider les constantes `DEFAULT_KOMMZ_*`
    # quand CLOUD_FEATURES_ENABLED est faux ne suffit pas, parce que le
    # fichier de configuration l'emporte toujours sur les defauts du code.
    # Un profil copie depuis un modele qui contenait ces URL les conserve
    # donc indefiniment, et l'utilisateur appelle nos GPU sans le savoir.
    #
    # On ne vide QUE les adresses pointant vers nos domaines. L'adresse que
    # l'utilisateur a configuree lui-meme est laissee intacte : l'effacer a
    # chaque demarrage rendrait l'edition Community inutilisable.
    for key in _COMMUNITY_ENDPOINT_KEYS:
        value = str(AUDIO_CONFIG.get(key, "") or "").strip()
        if value and _is_kommz_hosted_url(value):
            AUDIO_CONFIG[key] = ""
            modified = True

    return modified


# ============================================================================
# CONFIG MANAGEMENT FUNCTIONS
# ============================================================================

def save_settings() -> bool:
    """Sauvegarde universelle pour Kommz V8.3 — avec retry atomique.
    Retourne True si la sauvegarde a réussi, False sinon."""
    last_err = None
    for attempt in range(3):
        try:
            CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
            tmp = str(CONFIG_FILE) + ".tmp"
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(_repair_payload_strings(AUDIO_CONFIG), f, indent=4, ensure_ascii=False)
            os.replace(tmp, str(CONFIG_FILE))
            return True
        except PermissionError as e:
            last_err = e
            if attempt < 2:
                time.sleep(0.05)
        except Exception as e:
            last_err = e
            if attempt < 2:
                time.sleep(0.05)
    print(
        f"⚠️ save_settings() échec après 3 tentatives : "
        f"{last_err} — chemin : {CONFIG_FILE}",
        file=sys.stderr,
        flush=True,
    )
    return False


def load_settings():
    """Charge la configuration depuis le fichier JSON"""
    global AUDIO_CONFIG
    
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8-sig') as f:
            loaded = json.load(f)
            
        for key in loaded:
            raw_value = loaded[key]
            AUDIO_CONFIG[key] = _repair_display_text(raw_value) if isinstance(raw_value, str) else raw_value

        # V5.4: ``ptt_key`` was used by an older capture path while the runtime
        # and status API use ``ptt_hotkey``. Keep one persisted source of truth.
        legacy_ptt_key = str(loaded.get("ptt_key") or "").strip()
        persisted_ptt_hotkey = str(loaded.get("ptt_hotkey") or "").strip()
        migrated_ptt_key = "ptt_key" in AUDIO_CONFIG
        if persisted_ptt_hotkey:
            AUDIO_CONFIG["ptt_hotkey"] = persisted_ptt_hotkey
        elif legacy_ptt_key:
            AUDIO_CONFIG["ptt_hotkey"] = legacy_ptt_key
        if migrated_ptt_key:
            AUDIO_CONFIG.pop("ptt_key", None)

        # V5.4 : realignement unique des defauts corriges (voir
        # _SETTINGS_MIGRATIONS). Doit tourner avant la sauvegarde ci-dessous.
        migrated_schema = _apply_settings_migrations(loaded)

        if migrated_schema or migrated_ptt_key or (not persisted_ptt_hotkey and legacy_ptt_key):
            save_settings()

        _apply_edition_profile_constraints()
        
    except FileNotFoundError:
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        save_settings()
    except Exception:
        pass


def get_config_path() -> Path:
    """Retourne le chemin du fichier de configuration"""
    return CONFIG_FILE
