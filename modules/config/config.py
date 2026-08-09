"""
Module de configuration pour KommzGamer V5.4

Ce module contient toutes les constantes de configuration, le dictionnaire AUDIO_CONFIG,
et les fonctions de gestion de la configuration (chargement/sauvegarde).

RÈGLE CRITIQUE: Ce module ne doit JAMAIS importer quoi que ce soit de vtp_core.py
pour éviter les imports circulaires.
"""

import os
import sys
import json
import time
import re
import shutil
from pathlib import Path


# ============================================================================
# CONFIG FILE PATH
# ============================================================================

_BASE_DIR = Path(__file__).parent.parent.parent

def _get_persistent_config_dir() -> Path:
    """Retourne le répertoire de configuration persistant (APPDATA).
    En mode buildé (PyInstaller frozen OU Nuitka __compiled__),
    on utilise %LOCALAPPDATA%\\KommzGamer pour la persistance réelle."""
    is_compiled = (
        getattr(sys, "frozen", False)       # PyInstaller
        or getattr(sys, "__compiled__", False)  # Nuitka (onefile + standalone)
        or "__compiled__" in dir(sys)           # Nuitka fallback
    )
    if is_compiled:
        appdata = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / "KommzGamer"
    return _BASE_DIR

def _resolve_config_file() -> Path:
    """Trouve le bon fichier settings en cherchant dans l'ordre.

    🔥 FIX PERSISTENCE EXEmode : en frozen onefile, _BASE_DIR pointe vers
    _MEIPSS (répertoire TEMPORAIRE en lecture seule). Si on charge le settings
    directement depuis _MEIPSS, ``save_settings()`` échouera (PermissionError
    sur un dossier temporaire en lecture seule) → AUCUNE persistance possible.

    Donc en frozen, on force TOUJOURS la migration depuis _MEIPSS vers
    %LOCALAPPDATA\\KommzGamer\\settings.private.json (persisté) au premier
    lancement, et on retourne ce chemin persisté comme CONFIG_FILE.
    Cela garantit que load_settings lit le bon fichier ET que save_settings
    peut écrire dessus.
    """
    config_dir = _get_persistent_config_dir()
    # 1. Variable d'environnement si déjà chargée
    env_file = os.environ.get("KOMMZ_SETTINGS_FILE", "")
    if env_file:
        p = config_dir / env_file
        if p.exists():
            return p
    # --- FIX EXEmode : migration forcée vers le dossier persistant ---
    # search_dirs : _MEIPSS (via _BASE_DIR ou sys._MEIPASS) + exe dir + config_dir
    search_dirs = [_BASE_DIR]
    if getattr(sys, "frozen", False):
        # _MEIPSS contient les data files inclus (settings.private.json via --include-data-files)
        meipass = getattr(sys, "_MEIPASS", "")
        if meipass:
            mp = Path(meipass)
            if mp not in search_dirs:
                search_dirs.append(mp)
        try:
            exe_dir = Path(sys.executable).resolve().parent
            if exe_dir not in search_dirs:
                search_dirs.append(exe_dir)
        except Exception:
            pass
    legacy_files = ["settings.private.json", "settings.json"]
    # Si on est en frozen (buildé) : on copie toujours depuis la source livrée
    # (MEIPSS/exe) vers le dossier persistant, même si un settings persistant
    # existe déjà — on ne veut JAMAIS lire/écrire depuis _MEIPSS (lecture seule).
    is_frozen = getattr(sys, "frozen", False)
    for fname in legacy_files:
        for base in search_dirs:
            legacy = base / fname
            if not legacy.exists():
                continue
            dest = config_dir / fname
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
    return dest

CONFIG_FILE = _resolve_config_file()

# Debug logs
import sys
print(f"[CONFIG] CONFIG_FILE résolu : {CONFIG_FILE}", file=sys.stderr, flush=True)
print(f"[CONFIG] Fichier existe : {CONFIG_FILE.exists()}", file=sys.stderr, flush=True)


# ============================================================================
# EDITION PROFILE CONSTANTS
# ============================================================================

EDITION_PROFILE = str(os.environ.get("KOMMZ_EDITION_PROFILE", "private") or "private").strip().lower()
if EDITION_PROFILE not in {"private", "community"}:
    EDITION_PROFILE = "private"

COMMUNITY_EDITION = EDITION_PROFILE == "community"

CLOUD_FEATURES_ENABLED = str(
    os.environ.get("KOMMZ_CLOUD_FEATURES", "1" if EDITION_PROFILE == "private" else "0") or "0"
).strip().lower() in {"1", "true", "yes", "on"}


# ============================================================================
# DEFAULT KOMMZ CLOUD URLS
# ============================================================================

DEFAULT_KOMMZ_VOICE_URL = "https://kommzvoice.onrender.com"
DEFAULT_KOMMZ_SYNTHESIS_URL = "https://kommzvoice.onrender.com"
DEFAULT_KOMMZ_WHISPER_URL = "https://kommzvoice.onrender.com"
DEFAULT_KOMMZ_HEALTH_URL = "https://kommzvoice.onrender.com/health"
DEFAULT_KOMMZ_WARMUP_URL = "https://kommzvoice.onrender.com/warmup"
DEFAULT_KOMMZ_GENERATE_URL = "https://kommzvoice.onrender.com/generate"
DEFAULT_KOMMZ_SYNTHESIS_ENDPOINT = "https://kommzvoice.onrender.com/synthesize"
DEFAULT_KOMMZ_WHISPER_ENDPOINT = "https://kommzvoice.onrender.com/transcribe"
DEFAULT_KOMMZ_VOICE_CLONE_URL = "https://kommzvoice.onrender.com/clone"
DEFAULT_KOMMZ_VOICE_LIST_URL = "https://kommzvoice.onrender.com/voices"
DEFAULT_KOMMZ_VOICE_DELETE_URL = "https://kommzvoice.onrender.com/delete"
DEFAULT_KOMMZ_VOICE_PREVIEW_URL = "https://kommzvoice.onrender.com/preview"
DEFAULT_KOMMZ_VOICE_DOWNLOAD_URL = "https://kommzvoice.onrender.com/download"
DEFAULT_KOMMZ_VOICE_UPLOAD_URL = "https://kommzvoice.onrender.com/upload"
DEFAULT_KOMMZ_VOICE_SHARE_URL = "https://kommzvoice.onrender.com/share"
DEFAULT_KOMMZ_VOICE_IMPORT_URL = "https://kommzvoice.onrender.com/import"
DEFAULT_KOMMZ_VOICE_EXPORT_URL = "https://kommzvoice.onrender.com/export"
DEFAULT_KOMMZ_VOICE_SEARCH_URL = "https://kommzvoice.onrender.com/search"
DEFAULT_KOMMZ_VOICE_RATE_URL = "https://kommzvoice.onrender.com/rate"
DEFAULT_KOMMZ_VOICE_REPORT_URL = "https://kommzvoice.onrender.com/report"


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
    "ptt_key": "f9",
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
    # --- Fish Audio API (V5.4) ---
    "fish_api_key":          "",
    "fish_voice_id":         "",
}




# ============================================================================
# LICENSE API CONSTANTS
# ============================================================================

LICENSE_API_URL = os.environ.get("KOMMZ_LICENSE_API_URL", "https://kommzvoice.onrender.com").strip().rstrip("/")
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
        
        _apply_edition_profile_constraints()
        
    except FileNotFoundError:
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        save_settings()
    except Exception:
        pass


def get_config_path() -> Path:
    """Retourne le chemin du fichier de configuration"""
    return CONFIG_FILE
