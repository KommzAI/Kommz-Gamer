#!/usr/bin/env python3
import os
os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "0"
os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "0"
os.environ["QT_SCALE_FACTOR"] = "1"
"""
VTP Core - DIAMOND EDITION v8.3 (STABLE & FINAL)
- Moteur Audio : Deepgram Nova-2 (Optimisé 7.1 / 16ch)
- Output : Correction MME/WASAPI pour ROG Theta & VB-Cable
- Fix : NumPy 2.0 Compatibility (frombuffer)
"""

# Fix DPI Awareness pour Qt/PyWebView (avant tous les imports)
try:
    import ctypes
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass

# --- ÉTAPE 1 : IMPORTS ---
import re
import hmac
import collections
import itertools
from pathlib import Path
try:
    from deep_translator import GoogleTranslator
except ImportError:
    GoogleTranslator = None
import ctypes # Pour communiquer avec les bibliothèques Windows
import json
import os
import sys
import subprocess
import requests
import webbrowser
from urllib.parse import urlsplit, urlunsplit
import threading  # TRÈS IMPORTANT pour webview
import webview
import traceback
try:
    from waitress import serve as WAITRESS_SERVE
except Exception:
    WAITRESS_SERVE = None
import sounddevice as sd
import math
try:
    from ftfy import fix_text as _ftfy_fix_text
except ImportError:
    _ftfy_fix_text = None
try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

# Evite les crashs d'encodage cp1252 sur Windows (emojis/accents dans print).
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# Runtime imports
import logging
from datetime import datetime

# ✅ NEW: Configuration logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# V5.3: Import fingerprint audio pour Game Detection V2
try:
    import audio_fingerprint as _afp
except Exception:
    _afp = None

# ============================================================================
# ENVIRONMENT LOADING
# ============================================================================
def load_local_env_file():
    """Charge .env local (utile pour exe desktop), avec fallback sans python-dotenv."""
    candidates = []
    try:
        exe_dir = Path(sys.argv[0]).resolve().parent
        candidates.append(exe_dir / ".env")
        candidates.append(exe_dir.parent / ".env")  # fallback: parent (exe dans dist_standalone/)
    except Exception:
        pass
    candidates.append(Path.cwd() / ".env")
    candidates.append(Path.cwd().parent / ".env")  # fallback: parent du cwd
    for p in candidates:
        try:
            if p.exists():
                if load_dotenv:
                    load_dotenv(dotenv_path=p, override=False)
                else:
                    for raw in p.read_text(encoding="utf-8", errors="ignore").splitlines():
                        line = raw.strip()
                        if not line or line.startswith("#") or "=" not in line:
                            continue
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip('"').strip("'")
                        if k and k not in os.environ:
                            os.environ[k] = v
                break
        except Exception:
            pass

load_local_env_file()

# ============================================================================
# CONFIGURATION MODULE IMPORT
# ============================================================================
from modules.config.config import (
    AUDIO_CONFIG,
    save_settings,
    load_settings,
    EDITION_PROFILE,
    CONFIG_FILE,
    _repair_payload_strings,
    _repair_display_text,
)

# LICENSE MODULE IMPORT
# ============================================================================
from modules.license import *

# AUDIO MODULE IMPORT
# ============================================================================
from modules.audio.utils import (
    StreamBuffer,
    resample_audio,
    pcm_bytes_to_float32,
    CHUNK_SIZE,
    _STREAM_BUFFER_TOTAL_DROPS,
    _STREAM_BUFFER_DROPS_LOCK,
)

# TTS MODULE IMPORT
# ============================================================================
from modules.tts import register_tts_module
from modules.stt import register_stt_module
from modules.privacy import privacy_bp
from modules.license import license_bp
from modules.overlay import overlay_bp, register_scenes_runtime
from modules.listen import listen_bp
from modules.remote import remote_bp
from modules.guide import guide_bp
from modules.scenes import scenes_bp
from modules.config import config_bp
from modules.ui import ui_bp
from modules.audio import audio_bp
from modules.cloud import cloud_bp
from modules.subs import subs_bp

# --- AJOUT CRITIQUE POUR ÉVITER L'ECHO ---
AUDIO_GATE_LOCKED = False  # Quand c'est True, l'IA arrête d'écouter
import threading
AUDIO_LOCK = threading.Lock()

# FIX #5: Event global pour remplacer time.sleep() dans les boucles watchdog/background.
# Permet de libérer le GIL proprement et de réveiller les threads immédiatement si besoin.
_PERF_STOP_EVENT = threading.Event()
# Stockage Audio en RAM (Pour éviter le disque dur)
LAST_AUDIO_BUFFER = None
# --- MEMOIRE RAM (VITESSE LUMIÈRE) ---
LAST_USER_AUDIO_BUFFER = None   # Stocke le micro du joueur (Capture instantanée)
PRESET_VOICE_BUFFER = None      # Stocke la voix téléchargée depuis Supabase (Batman, etc.)
CURRENT_PRESET_ID = None        # Pour savoir quelle voix est chargée

# Edition profile:
# - private   : full cloud stack (Modal/Supabase/License)
# - community : local/community mode (no cloud keys required)
if EDITION_PROFILE not in {"private", "community"}:
    EDITION_PROFILE = "private"
COMMUNITY_EDITION = EDITION_PROFILE == "community"
CLOUD_FEATURES_ENABLED = str(
    os.environ.get("KOMMZ_CLOUD_FEATURES", "1" if EDITION_PROFILE == "private" else "0") or "0"
).strip().lower() in {"1", "true", "yes", "on"}

# Optional cloud defaults.
DEFAULT_KOMMZ_CLONE_URL = os.environ.get(
    "KOMMZ_DEFAULT_CLONE_URL",
    "",
).strip()
DEFAULT_KOMMZ_SYNTHESIS_URL = os.environ.get(
    "KOMMZ_DEFAULT_SYNTHESIS_URL",
    "",
).strip()
DEFAULT_KOMMZ_WHISPER_URL = os.environ.get(
    "KOMMZ_DEFAULT_WHISPER_URL",
    os.environ.get(
        "KOMMZ_WHISPER_URL",
        "",
    ),
).strip()
DEFAULT_KOMMZ_WHISPER_MODEL = (
    str(os.environ.get("KOMMZ_DEFAULT_WHISPER_MODEL", "small") or "small").strip().lower()
    or "small"
)
if not CLOUD_FEATURES_ENABLED:
    DEFAULT_KOMMZ_CLONE_URL = ""
    DEFAULT_KOMMZ_SYNTHESIS_URL = ""
    DEFAULT_KOMMZ_WHISPER_URL = ""

# 1. UNE SEULE DÉFINITION COMPLÈTE (Ne pas en remettre une autre plus bas !)

MOJIBAKE_MARKERS = ("Ã", "â", "ð", "Â", "ï¸", "œ", "ž", "¢")
_ESCAPED_UTF8_RUN_RE = re.compile(r"(?:\\u00[0-9a-fA-F]{2}){2,}")


def _mojibake_score(text) -> int:
    s = str(text or "")
    return sum(s.count(marker) for marker in MOJIBAKE_MARKERS)


def _decode_escaped_utf8_runs(text: str) -> str:
    """
    Decode runs like "\\u00c3\\u00a9" (UTF-8 bytes escaped as unicode literals)
    into proper unicode ("é"), without touching normal text.
    """
    if not text or "\\u00" not in text:
        return text

    def _repl(match):
        chunk = match.group(0)
        try:
            hex_values = re.findall(r"\\u00([0-9a-fA-F]{2})", chunk)
            data = bytes(int(h, 16) for h in hex_values)
            decoded = data.decode("utf-8", errors="strict")
            return decoded
        except Exception:
            return chunk

    try:
        return _ESCAPED_UTF8_RUN_RE.sub(_repl, text)
    except Exception:
        return text






# Répare immédiatement les valeurs par défaut visibles (UI/logs/config)
# pour éviter que des chaînes historiques mojibakées ne réapparaissent
# avant même le chargement du settings.json.
# IMPORTANT : mutation EN PLACE (clear+update) au lieu de réassignation,
# pour conserver la même référence dict que modules.config.config.AUDIO_CONFIG.
# Sinon save_settings() / load_settings() agiraient sur l'ancien dict, et
# les modifs faites depuis les routes Flask seraient invisibles côté disque.
_repaired_initial = _repair_payload_strings(AUDIO_CONFIG)
AUDIO_CONFIG.clear()
AUDIO_CONFIG.update(_repaired_initial)
del _repaired_initial




def _utc_now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _normalize_voice_library_entry(raw: dict) -> dict:
    item = dict(raw or {})
    voice_id = str(
        item.get("voice_id")
        or item.get("id")
        or item.get("client_id")
        or item.get("kommz_id")
        or ""
    ).strip()
    name = str(item.get("name") or voice_id or "Voix sans nom").strip()
    lang = str(item.get("lang") or "").strip().lower()
    tags = item.get("tags")
    if isinstance(tags, str):
        tags = [t.strip().lower() for t in tags.split(",") if t.strip()]
    elif isinstance(tags, list):
        tags = [str(t).strip().lower() for t in tags if str(t).strip()]
    else:
        tags = []
    return {
        "name": _repair_display_text(name),
        "voice_id": voice_id,
        "lang": lang,
        "tags": tags[:8],
        "updated_at": str(item.get("updated_at") or _utc_now_iso()),
    }


def _get_voice_library() -> list:
    lib = AUDIO_CONFIG.get("voice_library")
    if not isinstance(lib, list):
        lib = []
    normalized = []
    seen = set()
    for raw in lib:
        item = _normalize_voice_library_entry(raw)
        vid = item.get("voice_id", "")
        if not vid or vid in seen:
            continue
        seen.add(vid)
        normalized.append(item)
    AUDIO_CONFIG["voice_library"] = normalized
    return normalized


def _set_voice_active_id(voice_id: str, persist: bool = False):
    vid = str(voice_id or "").strip()
    AUDIO_CONFIG["voice_active_id"] = vid
    if vid:
        AUDIO_CONFIG["kommz_client_id"] = vid
    if persist:
        save_settings()


SCENE_CAPTURE_KEYS = [
    "tts_engine",
    "edge_voice",
    "target_lang",
    "kommz_client_id",
    "voice_active_id",
    "gpt_style_to_xtts_fr",
    "seamless_prefix_active",
    "smart_commands_active",
    "teamsync_ai_active",
    "turbo_latency_active",
    "esport_mode_active",
    "stealth_mode_active",
    "shadow_ai_active",
    "auto_context_active",
    "auto_update_active",
    "hybrid_activation_active",
    "tilt_shield_active",
    "stream_connect_active",
    "tactical_macros_active",
    "polyglot_active",
    "privacy_sentinel_active",
    "smart_marker_active",
]

_SCENE_AUTO_LAST_PROCESS = ""
_SCENE_AUTO_LAST_SCENE = ""


def _scene_now_utc_iso() -> str:
    return _utc_now_iso()


def _normalize_scene_entry(raw: dict) -> dict:
    item = dict(raw or {})
    name = str(item.get("name") or item.get("scene_name") or "").strip()
    if not name:
        name = "Scene"
    process_name = str(item.get("process_name") or "").strip().lower()
    config = item.get("config")
    if not isinstance(config, dict):
        config = {}

    cleaned_cfg = {}
    for k in SCENE_CAPTURE_KEYS:
        if k in config:
            cleaned_cfg[k] = config[k]

    return {
        "name": _repair_display_text(name[:48]),
        "process_name": _repair_display_text(process_name[:64]),
        "config": _repair_payload_strings(cleaned_cfg),
        "updated_at": str(item.get("updated_at") or _utc_now_iso()),
        "applied_at": str(item.get("applied_at") or item.get("last_applied_at") or ""),
    }


def _get_scene_library() -> list:
    lib = AUDIO_CONFIG.get("scene_library")
    if not isinstance(lib, list):
        lib = []
    normalized = []
    seen = set()
    for raw in lib:
        item = _normalize_scene_entry(raw)
        key = str(item.get("name") or "").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        normalized.append(item)
    AUDIO_CONFIG["scene_library"] = normalized
    return normalized


def _capture_scene_config() -> dict:
    snap = {}
    for k in SCENE_CAPTURE_KEYS:
        snap[k] = AUDIO_CONFIG.get(k)
    return _repair_payload_strings(snap)


def _apply_target_lang_for_scene(raw_lang_value):
    global CURRENT_TARGET_LANG
    raw_lang = str(raw_lang_value or "").strip().upper()
    if not raw_lang:
        return
    DEEPGRAM_MAP = {
        "EN": "en-US", "FR": "fr-FR", "ES": "es-ES", "DE": "de-DE",
        "IT": "it-IT", "PT": "pt-PT", "RU": "ru-RU", "JA": "ja-JP",
        "KO": "ko-KR", "ZH": "zh-CN", "TR": "tr-TR", "PL": "pl-PL",
        "NL": "nl-NL", "SV": "sv-SE", "UA": "uk-UA", "ID": "id-ID",
        "TH": "th-TH", "VN": "vi-VN", "IN": "hi-IN", "BR": "pt-BR"
    }
    deepl_map = {
        "EN": "EN-US", "PT": "PT-PT", "UA": "UK",
        "BR": "PT-BR", "IN": "HI", "VN": "VI",
        "JP": "JA", "ZH": "ZH"
    }
    AUDIO_CONFIG["ally_recognition_lang"] = DEEPGRAM_MAP.get(raw_lang, AUDIO_CONFIG.get("ally_recognition_lang", "multi"))
    CURRENT_TARGET_LANG = deepl_map.get(raw_lang, raw_lang)
    AUDIO_CONFIG["target_lang"] = raw_lang


def _apply_scene_config(config: dict):
    if not isinstance(config, dict):
        return
    for k in SCENE_CAPTURE_KEYS:
        if k not in config:
            continue
        if k == "target_lang":
            _apply_target_lang_for_scene(config.get(k))
            continue
        AUDIO_CONFIG[k] = config.get(k)

    active_vid = str(AUDIO_CONFIG.get("voice_active_id") or "").strip()
    if active_vid and not str(AUDIO_CONFIG.get("kommz_client_id") or "").strip():
        AUDIO_CONFIG["kommz_client_id"] = active_vid


def _apply_scene_by_name(scene_name: str, source: str = "manual"):
    name = str(scene_name or "").strip()
    if not name:
        return False, "Nom de scène manquant", None
    lib = _get_scene_library()
    scene = next((s for s in lib if str(s.get("name") or "").strip().lower() == name.lower()), None)
    if not scene:
        return False, "Scène introuvable", None
    _apply_scene_config(scene.get("config") or {})
    AUDIO_CONFIG["scene_active_name"] = str(scene.get("name") or name)
    applied_at = _scene_now_utc_iso()
    scene["applied_at"] = applied_at
    AUDIO_CONFIG["scene_last_applied_at"] = applied_at
    save_settings()
    stealth_print(f"🎬 Scène appliquée ({source}): {AUDIO_CONFIG['scene_active_name']}")
    return True, "", scene


def _get_foreground_process_name() -> str:
    try:
        import ctypes
        import ctypes.wintypes as wt
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return ""
        pid = wt.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if not pid.value:
            return ""
        try:
            import psutil
            return str(psutil.Process(int(pid.value)).name() or "").strip().lower()
        except Exception:
            return ""
    except Exception:
        return ""


# V5.2: Récupère le titre de la fenêtre foreground (pour détection de map)
def _get_foreground_window_title() -> str:
    try:
        import ctypes
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return ""
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return ""
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        return str(buf.value or "").strip()
    except Exception:
        return ""


def scene_auto_apply_loop():
    global _SCENE_AUTO_LAST_PROCESS, _SCENE_AUTO_LAST_SCENE
    while True:
        try:
            if not _to_bool(AUDIO_CONFIG.get("scene_auto_apply_enabled", False), False):
                _PERF_STOP_EVENT.wait(1.5)
                continue
            current_proc = _get_foreground_process_name()
            if not current_proc:
                _PERF_STOP_EVENT.wait(1.2)
                continue
            if current_proc == _SCENE_AUTO_LAST_PROCESS:
                _PERF_STOP_EVENT.wait(1.2)
                continue
            _SCENE_AUTO_LAST_PROCESS = current_proc
            target_scene = None
            for sc in _get_scene_library():
                proc = str(sc.get("process_name") or "").strip().lower()
                if proc and proc == current_proc:
                    target_scene = sc
                    break
            if target_scene:
                scene_name = str(target_scene.get("name") or "").strip()
                if scene_name and scene_name != _SCENE_AUTO_LAST_SCENE:
                    ok, _, _ = _apply_scene_by_name(scene_name, source=f"auto:{current_proc}")
                    if ok:
                        _SCENE_AUTO_LAST_SCENE = scene_name
            else:
                forced_proc = str(AUDIO_CONFIG.get("scene_auto_process") or "").strip().lower()
                forced_scene = str(AUDIO_CONFIG.get("scene_active_name") or "").strip()
                if forced_proc and forced_scene and current_proc == forced_proc and forced_scene != _SCENE_AUTO_LAST_SCENE:
                    ok, _, _ = _apply_scene_by_name(forced_scene, source=f"auto-force:{current_proc}")
                    if ok:
                        _SCENE_AUTO_LAST_SCENE = forced_scene
        except Exception:
            pass
        _PERF_STOP_EVENT.wait(1.2)

# V5.3: Game auto-detect loop — detecte et applique le preset automatiquement
def game_auto_detect_loop():
    global _game_detect_auto_mode, _game_detect_last_fingerprint
    last_detected_game = None
    last_apply_ts = 0.0
    apply_cooldown_s = 10.0
    while True:
        try:
            _PERF_STOP_EVENT.wait(2.0)
            if not _to_bool(AUDIO_CONFIG.get("game_auto_detect_enabled", False), False):
                _game_detect_auto_mode = False
                last_detected_game = None
                continue
            _game_detect_auto_mode = True
            current_preset = str(AUDIO_CONFIG.get("ally_game_preset", "custom") or "custom").strip().lower()
            if current_preset != "auto":
                _PERF_STOP_EVENT.wait(5.0)
                continue
            proc = _get_foreground_process_name()
            win_title = _get_foreground_window_title() or ""
            detected = None
            detected_map = None
            proc_lower = str(proc or "").strip().lower()
            game_map = {
                "cod": "warzone", "modernwarfare": "warzone", "warzone": "warzone",
                "cs2": "cs2", "csgo": "cs2", "counterstrike2": "cs2",
                "valorant": "valorant", "riotclient": "valorant",
                "fortnite": "fortnite", "fortniteclient-win64-shipping": "fortnite",
                "r5apex": "apex", "apex": "apex",
                "overwatch": "overwatch",
                "rainbowsix": "r6", "rainbow six": "r6",
                "escapefromtarkov": "tarkov", "tarkov": "tarkov",
                "rust": "rust", "rustclient": "rust",
                "tslgame": "pubg", "pubg": "pubg",
                "league of legends": "lol", "leagueclient": "lol",
                "dota2": "dota2", "dota": "dota2",
            }
            for key, preset in game_map.items():
                if key in proc_lower:
                    detected = preset
                    break
            if detected == "tarkov" and win_title:
                win_lower = win_title.lower()
                tarkov_maps = {
                    "factory": "tarkov_factory", "woods": "tarkov_woods",
                    "customs": "tarkov_customs", "interchange": "tarkov_interchange",
                    "reserve": "tarkov", "shoreline": "tarkov", "labs": "tarkov",
                    "streets": "tarkov", "lighthouse": "tarkov",
                }
                for kw, mp in tarkov_maps.items():
                    if kw in win_lower:
                        detected_map = mp
                        break
            effective = detected_map or detected
            if effective and effective != last_detected_game:
                last_detected_game = effective
                now = time.time()
                if now - last_apply_ts >= apply_cooldown_s:
                    app_preset = LISTEN_GAME_PRESETS.get(effective) or {}
                    label = str(app_preset.get("label", effective))
                    if effective in LISTEN_GAME_PRESETS:
                        _apply_listen_game_preset(effective)
                        try:
                            stealth_print(f"🎮 V5.3 Auto-detect: jeu={effective} ({label}) appliqué")
                        except Exception:
                            pass
                        last_apply_ts = now
                        try:
                            AUDIO_CONFIG["ally_game_preset_last_auto"] = effective
                            save_settings()
                        except Exception:
                            pass
            if not effective:
                last_detected_game = None
        except Exception:
            _PERF_STOP_EVENT.wait(3.0)

def save_config():
    """Sauvegarde la configuration actuelle dans le fichier de profil."""
    try:
        from modules.config.config import save_settings
        save_settings()
        # On utilise stealth_print si dispo, sinon print
        try:
            stealth_print("💾 Config sauvegardée.")
        except:
            print("💾 Config sauvegardée.")
    except Exception as e:
        print(f"❌ Erreur sauvegarde : {e}")

# --- AU TOUT DÉBUT DU FICHIER (après les imports et AUDIO_CONFIG) ---

def stealth_print(*args, **kwargs):
    """Écrit dans log_discret.txt et affiche en console de manière sécurisée"""
    import datetime
    
    # 1. Conversion des arguments en une seule chaîne de texte
    try:
        output = " ".join(map(str, args))
    except:
        output = str(args)
    output = _repair_display_text(output)

    # 2. Gestion du Timestamp
    try:
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
    except:
        timestamp = "Log"
    
    # 3. ÉCRITURE FICHIER (Sécurisée)
    try:
        # L'encodage utf-8 est vital ici pour les émojis
        with open("log_discret.txt", "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {output}\n")
    except Exception:
        # Si le fichier est verrouillé ou inaccessible, on ignore silencieusement
        pass

    # 4. AFFICHAGE CONSOLE (La partie critique pour Nuitka)
    # On vérifie si on doit afficher (Stealth Mode désactivé OU message important)
    should_print = False
    if not AUDIO_CONFIG.get("stealth_mode_active", False):
        should_print = True
    elif "❌" in output or "⚠️" in output:
        should_print = True

    if "_set_module_runtime" in globals():
        try:
            if AUDIO_CONFIG.get("stealth_mode_active", False):
                _set_module_runtime("stealth", "Masqué", "Console réduite, logs non critiques cachés")
            else:
                _set_module_runtime("stealth", "Console", "Logs visibles dans la console")
        except Exception:
            pass

    if should_print:
        try:
            # Tentative d'affichage normal
            print(output, **kwargs)
        except UnicodeEncodeError:
            # CRASH EVITÉ : Si la console ne supporte pas les émojis
            try:
                # On essaie d'imprimer une version "propre" sans accents/emojis
                clean_output = output.encode('ascii', 'ignore').decode('ascii')
                print(f"[{timestamp}] {clean_output}", **kwargs)
            except:
                pass # Si même ça échoue, on abandonne l'affichage console sans planter l'app
        except Exception:
            pass


_RATE_LIMITED_LOG_STATE = {}


def stealth_print_rl(key: str, message: str, cooldown: float = 20.0) -> bool:
    """
    Log anti-spam: n'affiche pas plusieurs fois le même type d'erreur sur une courte fenêtre.
    Retourne True si un log a été affiché, sinon False.
    """
    try:
        now = time.time()
        k = str(key or "default")
        state = _RATE_LIMITED_LOG_STATE.get(k) or {"last": 0.0, "suppressed": 0}
        last_ts = float(state.get("last") or 0.0)
        suppressed = int(state.get("suppressed") or 0)
        if (now - last_ts) < float(cooldown):
            state["suppressed"] = suppressed + 1
            _RATE_LIMITED_LOG_STATE[k] = state
            return False
        txt = _repair_display_text(str(message or ""))
        if suppressed > 0:
            txt = f"{txt} (+{suppressed} similaires masqués)"
        _RATE_LIMITED_LOG_STATE[k] = {"last": now, "suppressed": 0}
        stealth_print(txt)
        return True
    except Exception:
        stealth_print(message)
        return True




def _is_turbo_mode_active() -> bool:
    return bool(AUDIO_CONFIG.get("turbo_latency_active", False))


def _is_stealth_mode_active() -> bool:
    return bool(AUDIO_CONFIG.get("stealth_mode_active", False))


def _is_stealth_critical_message(text: str) -> bool:
    msg = _repair_display_text(str(text or ""))
    if not msg:
        return False
    critical_markers = (
        "ERREUR",
        "ERROR",
        "ECHEC",
        "ÉCHEC",
        "WARNING",
        "ALERTE",
        "PANIC",
        "QUOTA",
        "UPDATE OBLIGATOIRE",
        "CHECKSUM INVALIDE",
        "LICENSE",
        "LICENCE",
    )
    msg_up = msg.upper()
    return any(marker in msg_up for marker in critical_markers)



            

import speech_recognition as sr
import pyaudio
from difflib import SequenceMatcher
import langid
langid.set_languages(['fr', 'en'])

import sys
import os

# Shared HTTP session for lower latency (connection pooling) without keeping Modal workers alive.
_HTTP = requests.Session()
import ctypes # INDISPENSABLE POUR LE FIX COM WINDOWS

# ============================================================
# 🛡️ PROTECTION RÉSEAU ULTIME (BYPASS DNS TOTAL)
# ============================================================
import socket
import ssl

# --- IMPORT DEEPL (NOUVEAU) ---
try:
    import deepl
    DEEPL_AVAILABLE = True
except ImportError:
    DEEPL_AVAILABLE = False
    print("⚠️ ATTENTION : Tapez 'pip install deepl' pour activer la qualité maximale.")

# 🔑 Clé DeepL via variable d'environnement (jamais en dur dans le code)
DEEPL_AUTH_KEY = os.environ.get("DEEPL_AUTH_KEY", "").strip()

# Initialisation du traducteur DeepL
deepl_translator = None
if DEEPL_AVAILABLE:
    try:
        if DEEPL_AUTH_KEY:
            deepl_translator = deepl.Translator(DEEPL_AUTH_KEY)
            print("✅ DeepL Connecté avec succès.")
        else:
            print("⚠️ DeepL non configuré (DEEPL_AUTH_KEY manquante) -> fallback traduction secondaire.")
    except Exception as e:
        print(f"⚠️ DeepL indisponible ({e}) -> fallback traduction secondaire.")

MICROSOFT_IPS = ['204.79.197.200', '13.107.213.19', '204.79.197.203']

old_getaddrinfo = socket.getaddrinfo
def new_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    if host == "speech.platform.bing.com":
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', (ip, port)) for ip in MICROSOFT_IPS]
    return old_getaddrinfo(host, port, family, type, proto, flags)

socket.getaddrinfo = new_getaddrinfo

try:
    ssl._create_default_https_context = ssl._create_unverified_context
except:
    pass
# ============================================================

# --- TRAPPE D'ERREUR GLOBALE ---
import traceback
def global_crash_logger(exctype, value, tb):
    # Ajout de encoding="utf-8" pour supporter les émojis comme ⏳
    with open("CRASH_REPORT_VTP.txt", "a", encoding="utf-8") as f:
        f.write("\n--- CRASH AU DEMARRAGE ---\n")
        traceback.print_exception(exctype, value, tb, file=f)

# Importation conditionnelle de GhostEars pour éviter le crash si absent
try:
    from ghost_ears import GhostEars
except Exception:
    GhostEars = None

import time, logging, threading, asyncio, hashlib, subprocess, json, datetime, re, urllib.request
import tkinter as tk 
from tkinter import font as tkfont
from tkinter import filedialog
import numpy as np
from logging.handlers import RotatingFileHandler
from pathlib import Path
from flask import Flask, request, jsonify, Response, send_from_directory, render_template, send_file
from flask_cors import CORS
from unidecode import unidecode
import edge_tts
import miniaudio
import keyboard
import webview
import tempfile
import soundfile as sf
import qrcode

# Import soundfile pour les modules
import soundfile
import io
import psutil
import warnings
from lingua import Language, LanguageDetectorBuilder
import queue

# Compat NumPy 2.x: certaines libs audio tierces appellent encore np.fromstring(..., sep='')
# ce mode binaire est supprimé. On redirige proprement vers frombuffer.
try:
    _np_fromstring_orig = np.fromstring

    def _np_fromstring_compat(obj, dtype=float, count=-1, sep='', like=None):
        if sep == '':
            try:
                view = memoryview(obj)
                if count is None or int(count) < 0:
                    return np.frombuffer(view, dtype=dtype)
                return np.frombuffer(view, dtype=dtype, count=int(count))
            except Exception:
                pass
        return _np_fromstring_orig(obj, dtype=dtype, count=count, sep=sep, like=like)

    np.fromstring = _np_fromstring_compat
except Exception:
    pass

import sys
import os

# --- CONFIGURATION ENCODAGE (VITAL POUR WINDOWS & NUITKA) ---
# Ceci force la console à accepter l'UTF-8 (Emojis)
try:
    if sys.stdout is not None:
        sys.stdout.reconfigure(encoding='utf-8')
    if sys.stderr is not None:
        sys.stderr.reconfigure(encoding='utf-8')
except AttributeError:
    # Si on est sur une très vieille version de Python ou un environnement restreint
    pass
except Exception:
    # Si Nuitka a totalement verrouillé la console
    pass

# CONFIG_FILE est défini plus haut via la variable d'environnement
# KOMMZ_SETTINGS_FILE (fallback: settings.json).
# Mémorise les traductions pour une réponse instantanée
SHADOW_CACHE = collections.OrderedDict()
SHADOW_AUDIO_CACHE = collections.OrderedDict()
SHADOW_CACHE_MAX_ITEMS = 200
SHADOW_AUDIO_CACHE_MAX_ITEMS = 48
POLYGLOT_TARGET_LANG = "ES"
POLYGLOT_OBS_FILE = "obs_subtitles_ES.txt"
TEAMSYNC_RUNTIME = {"level": 0.0, "updated_at": 0.0, "last_gain": 1.0, "last_log_at": 0.0}
# --- INITIALISATION COM (CRITIQUE POUR ROG THETA) ---
try:
    ctypes.windll.ole32.CoInitialize(None)
except:
    pass

# --- IMPORT DEEPGRAM (VERSION NETTOYÉE POUR EXE) ---
# On importe sans try/except pour forcer Nuitka à l'inclure correctement.
# Si ça plante ici au démarrage, c'est qu'il manque 'deepgram-sdk' dans le pip install.
import sys

# --- IMPORT DEEPGRAM OFFICIEL ---
# Nuitka doit maintenant voir ces lignes clairement.
import deepgram
from deepgram import (
    DeepgramClient, DeepgramClientOptions, PrerecordedOptions, 
    LiveTranscriptionEvents, LiveOptions, Microphone
)

DEEPGRAM_AVAILABLE = True

# 🔑 TA CLÉ API
DEEPGRAM_API_KEY = "e83f74e7893af98d996cdc1b14ab87dd8dc1b6f8"


warnings.filterwarnings("ignore", message="data discontinuity in recording")
# Runtime WebView: "cedge" n'est pas fiable en EXE sur certaines machines.
# On force Edge Chromium, avec normalisation des anciennes valeurs.
_wv_gui = str(os.environ.get("PYWEBVIEW_GUI", "") or "").strip().lower()
if _wv_gui in ("", "cedge", "edge"):
    os.environ["PYWEBVIEW_GUI"] = "edgechromium"

if getattr(sys, 'frozen', False):
    # En onefile, _MEIPASS est temporaire (supprimé à la sortie).
    # On travaille depuis le dossier de l'EXE pour garder logs/settings stables.
    try:
        os.chdir(os.path.dirname(os.path.abspath(sys.argv[0])))
    except Exception:
        pass
 
def is_strictly_french(text):
    """Version équilibrée : Bloque le français sans casser l'anglais"""
    if not text or len(text) < 3: return False # On laisse passer les mots courts
    
    try:
        if detector:
            # On n'agit que si Lingua est sûr à 90% que c'est du français
            confidence = detector.compute_language_confidence(text, Language.FRENCH)
            if confidence > 0.9: return True
    except: pass

    # On garde uniquement les mots qui sont EXCLUSIVEMENT français
    # On a retiré "son", "ton", "on", "plus", "as" car ils existent en anglais
    FRENCH_HARD_STOP = {
        "est", "sont", "avec", "dans", "pour", "était", "étaient",
        "mec", "gars", "ouais", "grave", "quoi", "mais", "fait",
        "cette", "ceux", "celles", "parce", "donc", "avez", "êtes"
    }
    
    words = re.sub(r'[^\w\s]', '', text.lower().strip()).split()
    for w in words:
        if w in FRENCH_HARD_STOP: return True
            
    return False
 
def apply_privacy_sentinel(text):
    """
    Censure :
    1. Les mots définis par l'utilisateur dans settings.json
    2. Les motifs automatiques (Numéros de téléphone, Emails...)
    """
    if not AUDIO_CONFIG.get("privacy_sentinel_active", False):
        return text, False

    censored = False
    original_text = text # On garde une copie pour comparer à la fin
    
    # --- A. LISTE PERSONNALISÉE (Depuis le fichier de config) ---
    # L'utilisateur ajoute ses propres mots interdits dans AUDIO_CONFIG
    # Ex: AUDIO_CONFIG["privacy_words"] = ["mon_mdp_trop_secret", "12 rue des lilas"]
    user_secrets = AUDIO_CONFIG.get("privacy_words", []) 
    
    for secret in user_secrets:
        if secret and secret.lower() in text.lower():
            # Remplacement insensible à la casse
            pattern = re.compile(re.escape(secret), re.IGNORECASE)
            text = pattern.sub("[PRIVÉ]", text)
            censored = True

    # --- B. DÉTECTION AUTOMATIQUE (Intelligence) ---
    
    # 1. Détecter les numéros de téléphone (Format FR : 06 12 34 56 78 ou 0612345678)
    # Regex : Cherche un 0 suivi de 9 chiffres, avec ou sans espaces/tirets
    phone_pattern = r"\b0[1-9](?:[\s.-]*\d{2}){4}\b"
    if re.search(phone_pattern, text):
        text = re.sub(phone_pattern, "[TÉLÉPHONE]", text)
        censored = True

    # 2. Détecter les Emails
    email_pattern = r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"
    if re.search(email_pattern, text):
        text = re.sub(email_pattern, "[EMAIL]", text)
        censored = True
            
    if censored:
        stealth_print(f"🛡️ PRIVACY : '{original_text}' -> BLOQUÉ")
        _set_module_runtime("privacy", "Blocage", "Donnée sensible détectée et censurée")
    else:
        _set_module_runtime("privacy", "Actif", "Aucune donnée sensible détectée")
        
    return text, censored
    
# À DÉPLACER V5.5 — appelé depuis vtp_core runtime
def _norm_dev_name(name):
    try:
        return unidecode(str(name or "")).upper().strip()
    except Exception:
        return str(name or "").upper().strip()


def _normalize_device_signature(name, hostapi):
    n = _norm_dev_name(name)
    h = _norm_dev_name(hostapi)
    return f"{h}::{n}" if h else f"::{n}"


def _device_runtime_payload(idx):
    devs = sd.query_devices()
    hostapis = sd.query_hostapis()
    dev = devs[int(idx)]
    hidx = int(dev.get("hostapi", -1))
    hname = str(hostapis[hidx].get("name", "")) if 0 <= hidx < len(hostapis) else ""
    return {
        "index": int(idx),
        "name": str(dev.get("name", "")),
        "hostapi": hname,
    }


def _resolve_device_signature(signature, as_output=False):
    """signature => runtime payload dict or None."""
    try:
        if not signature:
            return None
        sig = str(signature).strip()
        if not sig:
            return None
        devs = sd.query_devices()
        hostapis = sd.query_hostapis()
        if "::" in sig:
            host_part, name_part = sig.split("::", 1)
            host_part = _norm_dev_name(host_part)
            name_part = _norm_dev_name(name_part)
        else:
            host_part, name_part = "", _norm_dev_name(sig)
        for i, dev in enumerate(devs):
            if as_output and int(dev.get("max_output_channels", 0)) <= 0:
                continue
            if (not as_output) and int(dev.get("max_input_channels", 0)) <= 0:
                continue
            d_name = _norm_dev_name(dev.get("name", ""))
            hidx = int(dev.get("hostapi", -1))
            hname = _norm_dev_name(hostapis[hidx].get("name", "")) if 0 <= hidx < len(hostapis) else ""
            if name_part and name_part in d_name and (not host_part or host_part == hname):
                return _device_runtime_payload(i)
        return None
    except Exception:
        return None


def find_cable_output_device():
    """
    Device de sortie Python vers applis (souvent 'CABLE Input' / 'CABLE In').
    """
    try:
        cands = []
        for i, dev in enumerate(sd.query_devices()):
            if int(dev.get("max_output_channels", 0)) <= 0:
                continue
            n = _norm_dev_name(dev.get("name", ""))
            if "CABLE" not in n and "VB-AUDIO" not in n and "VIRTUAL" not in n:
                continue
            score = 0
            if "CABLE INPUT" in n or "INPUT CABLE" in n or "CABLE IN" in n or "ENTREE" in n:
                score += 10
            if "VOICEMEETER INPUT" in n:
                score += 7
            score += 2
            cands.append((score, i, dev.get("name", "")))
        if not cands:
            return None
        cands.sort(reverse=True)
        return int(cands[0][1])
    except Exception:
        return None


def find_cable_input_device():
    """
    Device d'entrée Python pour écoute alliés (souvent 'CABLE Output' / 'CABLE Out').
    """
    try:
        cands = []
        for i, dev in enumerate(sd.query_devices()):
            if int(dev.get("max_input_channels", 0)) <= 0:
                continue
            n = _norm_dev_name(dev.get("name", ""))
            if "CABLE" not in n and "VB-AUDIO" not in n and "VIRTUAL" not in n:
                continue
            score = 0
            if "CABLE OUTPUT" in n or "OUTPUT CABLE" in n or "CABLE OUT" in n or "SORTIE" in n:
                score += 10
            if "VOICEMEETER OUTPUT" in n:
                score += 7
            score += 2
            cands.append((score, i, dev.get("name", "")))
        if not cands:
            return None
        cands.sort(reverse=True)
        return int(cands[0][1])
    except Exception:
        return None


def _is_wdm_ks_input_device(device_index):
    try:
        devs = sd.query_devices()
        hostapis = sd.query_hostapis()
        idx = int(device_index)
        if idx < 0 or idx >= len(devs):
            return False
        hidx = int(devs[idx].get("hostapi", -1))
        if hidx < 0 or hidx >= len(hostapis):
            return False
        hname = str(hostapis[hidx].get("name", "")).upper()
        return "WDM-KS" in hname
    except Exception:
        return False


def find_cable_input_device_non_wdmks():
    """
    Renvoie un CABLE input exploitable par InputStream (priorise WASAPI/MME/DSOUND).
    Evite WDM-KS qui échoue souvent en mode bloquant sur certains pilotes Windows.
    """
    try:
        devs = sd.query_devices()
        hostapis = sd.query_hostapis()
        best = None
        best_score = -1
        for i, dev in enumerate(devs):
            if int(dev.get("max_input_channels", 0)) <= 0:
                continue
            n = _norm_dev_name(dev.get("name", ""))
            if "CABLE" not in n and "VB-AUDIO" not in n and "VIRTUAL" not in n:
                continue

            hidx = int(dev.get("hostapi", -1))
            hname = ""
            if 0 <= hidx < len(hostapis):
                hname = str(hostapis[hidx].get("name", "")).upper()
            if "WDM-KS" in hname:
                continue

            score = 0
            if "WASAPI" in hname:
                score += 60
            elif "MME" in hname:
                score += 50
            elif "DSOUND" in hname or "DIRECTSOUND" in hname:
                score += 40
            else:
                score += 20
            if "CABLE OUTPUT" in n or "OUTPUT CABLE" in n or "CABLE OUT" in n or "SORTIE" in n:
                score += 20
            if score > best_score:
                best_score = score
                best = int(i)

        if best is not None:
            return best
    except Exception:
        pass
    return find_cable_input_device()


def find_system_mix_input_device_non_wdmks():
    """
    Cherche une entrée système exploitable hors WDM-KS:
    Stereo Mix / Mixage Stéréo / What U Hear / Monitor.
    """
    try:
        devs = sd.query_devices()
        hostapis = sd.query_hostapis()
        best = None
        best_score = -1
        for i, dev in enumerate(devs):
            if int(dev.get("max_input_channels", 0)) <= 0:
                continue
            n = _norm_dev_name(dev.get("name", ""))

            hidx = int(dev.get("hostapi", -1))
            hname = ""
            if 0 <= hidx < len(hostapis):
                hname = str(hostapis[hidx].get("name", "")).upper()
            if "WDM-KS" in hname:
                continue

            if not any(k in n for k in ["STEREO MIX", "MIXAGE STEREO", "WHAT U HEAR", "MONITOR OF", "LOOPBACK"]):
                continue

            score = 0
            if "WASAPI" in hname:
                score += 60
            elif "MME" in hname:
                score += 50
            elif "DSOUND" in hname or "DIRECTSOUND" in hname:
                score += 40
            else:
                score += 20
            if "STEREO MIX" in n or "MIXAGE STEREO" in n:
                score += 30
            if "WHAT U HEAR" in n:
                score += 25
            if "LOOPBACK" in n or "MONITOR OF" in n:
                score += 20

            if score > best_score:
                best_score = score
                best = int(i)

        return best
    except Exception:
        return None


def patch_soundcard_numpy2():
    """
    Patch runtime pour soundcard (mediafoundation) sur NumPy 2.x.
    Certaines versions appellent encore numpy.fromstring(..., sep='') en mode binaire.
    """
    try:
        import soundcard.mediafoundation as sc_mf
        np_mod = sc_mf.numpy
        orig = getattr(np_mod, "fromstring", None)
        if not callable(orig):
            return False

        def _fromstring_compat(obj, dtype=float, count=-1, sep=''):
            if sep == '':
                try:
                    view = memoryview(obj)
                    if count is None or int(count) < 0:
                        return np_mod.frombuffer(view, dtype=dtype)
                    return np_mod.frombuffer(view, dtype=dtype, count=int(count))
                except Exception:
                    pass
            return orig(obj, dtype=dtype, count=count, sep=sep)

        np_mod.fromstring = _fromstring_compat
        return True
    except Exception:
        return False


def resolve_output_device_cfg(value):
    """Accepte int, str num, str nom de device."""
    try:
        devs = sd.query_devices()
    except Exception:
        return None

    def valid_out(idx):
        try:
            idx = int(idx)
            return 0 <= idx < len(devs) and int(devs[idx].get("max_output_channels", 0)) > 0
        except Exception:
            return False

    if isinstance(value, int) and valid_out(value):
        return int(value)
    if isinstance(value, str):
        s = value.strip()
        if s.isdigit() and valid_out(int(s)):
            return int(s)
        idx = get_device_index(s, as_output=True)
        if idx is not None and valid_out(idx):
            return int(idx)
    return None


def resolve_input_device_cfg(value):
    """Accepte int, str num, str nom de device (entrée micro)."""
    try:
        devs = sd.query_devices()
    except Exception:
        return None

    def valid_in(idx):
        try:
            idx = int(idx)
            return 0 <= idx < len(devs) and int(devs[idx].get("max_input_channels", 0)) > 0
        except Exception:
            return False

    if isinstance(value, int) and valid_in(value):
        return int(value)
    if isinstance(value, str):
        s = value.strip()
        if s.isdigit() and valid_in(int(s)):
            return int(s)
        idx = get_device_index(s, as_output=False)
        if idx is not None and valid_in(idx):
            return int(idx)
    return None
        
# ==========================================
# 🧠 DÉTECTEUR DE LANGUE (LINGUA)
# ==========================================

stealth_print("⏳ Initialisation du détecteur de langue Lingua...")

# 1. CONFIGURATION DU DÉTECTEUR
# ⚠️ IMPORTANT : On LAISSE 'Language.FRENCH' ici !
# Il faut que l'IA sache reconnaître le français pour pouvoir l'ignorer (Bypass).
try:
    languages = [
        Language.ENGLISH, 
        Language.FRENCH, 
        Language.SPANISH, 
        Language.GERMAN, 
        Language.RUSSIAN, 
        Language.PORTUGUESE
    ]
    detector = LanguageDetectorBuilder.from_languages(*languages).build()
    stealth_print("✅ Détecteur Lingua prêt.")
except Exception as e:
    stealth_print(f"⚠️ Erreur Lingua : {e}")
    # Fallback simple si Lingua plante
    detector = None

    
def _set_process_priority(mode="above_normal"):
    try:
        if sys.platform != "win32":
            return False
        p = psutil.Process(os.getpid())
        mode = str(mode or "above_normal").strip().lower()
        if mode == "high":
            priority = getattr(psutil, "HIGH_PRIORITY_CLASS", None)
        elif mode == "normal":
            priority = getattr(psutil, "NORMAL_PRIORITY_CLASS", None)
        else:
            priority = getattr(psutil, "ABOVE_NORMAL_PRIORITY_CLASS", None) or getattr(psutil, "NORMAL_PRIORITY_CLASS", None)
        if priority is None:
            return False
        p.nice(priority)
        return True
    except Exception:
        return False


def apply_esport_profile(force_log=False):
    enabled = bool(AUDIO_CONFIG.get("esport_mode_active", False))
    wanted = "high" if enabled else "above_normal"
    ok = _set_process_priority(wanted)
    if enabled:
        _set_module_runtime("esport", "Performance", "Priorité CPU/process élevée")
    else:
        _set_module_runtime("esport", "Normal+", "Priorité process standard améliorée")
    if ok and (force_log or enabled):
        if enabled:
            stealth_print("🏁 Profil e-sport actif : priorité CPU élevée.")
        else:
            stealth_print("🏁 Profil e-sport désactivé : priorité CPU normale+.")
    return ok


_set_process_priority("above_normal")


def _shadow_cache_get(store, key):
    if not AUDIO_CONFIG.get("shadow_ai_active", False):
        return None
    if key not in store:
        return None
    value = store.pop(key)
    store[key] = value
    return value


def _shadow_cache_put(store, key, value, max_items):
    if not AUDIO_CONFIG.get("shadow_ai_active", False):
        return value
    store.pop(key, None)
    store[key] = value
    while len(store) > max_items:
        store.popitem(last=False)
    return value


def _clear_shadow_caches():
    SHADOW_CACHE.clear()
    SHADOW_AUDIO_CACHE.clear()
    _set_module_runtime("shadow", "Actif" if AUDIO_CONFIG.get("shadow_ai_active", False) else "Inactif", "Caches Shadow AI vidés")


def _derive_shadow_service_urls():
    urls = []
    try:
        clone_url = str(_resolve_kommz_voice_endpoint() or "").strip()
        if clone_url:
            urls.append(_derive_modal_endpoint(clone_url, "warmup"))
            urls.append(_derive_modal_endpoint(clone_url, "health"))
    except Exception:
        pass
    try:
        gpt_url = str(AUDIO_CONFIG.get("gpt_api_url", "") or "").strip()
        if gpt_url:
            urls.append(_derive_modal_endpoint(gpt_url, "health"))
    except Exception:
        pass
    try:
        whisper_url = str(AUDIO_CONFIG.get("whisper_api_url", "") or "").strip()
        if whisper_url:
            urls.append(_derive_modal_endpoint(whisper_url, "health"))
    except Exception:
        pass
    return [u for u in urls if u]


def warm_shadow_services_async(reason="shadow"):
    _set_module_runtime("shadow", "Warmup", f"Préchargement des services ({reason})")
    def _run():
        try:
            prewarm_kommz_xtts(force=True)
        except Exception as warm_err:
            stealth_print(f"⚠️ Shadow warmup XTTS: {warm_err}")
        for url in _derive_shadow_service_urls():
            try:
                requests.get(url, timeout=(2.5, 6))
            except Exception:
                pass
        stealth_print(f"👻 Shadow AI prêt ({reason}).")
        _set_module_runtime("shadow", "Prêt", f"Warmup terminé ({reason})")

    threading.Thread(target=_run, daemon=True).start()


def _normalize_teamsync_level(raw_level):
    try:
        level = abs(float(raw_level))
    except Exception:
        return 0.0
    if level > 1.5:
        level /= 32768.0
    return max(0.0, min(1.0, level))


def update_teamsync_input_level(raw_level):
    level = _normalize_teamsync_level(raw_level)
    TEAMSYNC_RUNTIME["level"] = (TEAMSYNC_RUNTIME["level"] * 0.82) + (level * 0.18)
    TEAMSYNC_RUNTIME["updated_at"] = time.time()


def get_teamsync_playback_gain():
    if not AUDIO_CONFIG.get("teamsync_ai_active", False):
        TEAMSYNC_RUNTIME["last_gain"] = 1.0
        _set_module_runtime("teamsync", "Inactif", "Boost automatique désactivé")
        return 1.0
    age = time.time() - float(TEAMSYNC_RUNTIME.get("updated_at", 0.0) or 0.0)
    if age > 3.0:
        TEAMSYNC_RUNTIME["last_gain"] = 1.0
        _set_module_runtime("teamsync", "Veille", "Aucun niveau jeu/chat récent")
        return 1.0
    level = float(TEAMSYNC_RUNTIME.get("level", 0.0) or 0.0)
    gain = 1.0
    if level >= 0.18:
        gain = 1.40
    elif level >= 0.10:
        gain = 1.22
    now = time.time()
    if gain > 1.0 and (now - float(TEAMSYNC_RUNTIME.get("last_log_at", 0.0) or 0.0)) > 8.0:
        stealth_print(f"🔊 Team-Sync AI actif : boost volume x{gain:.2f} (niveau jeu/chat={level:.2f})")
        TEAMSYNC_RUNTIME["last_log_at"] = now
    if gain > 1.0:
        _set_module_runtime("teamsync", "Boost", f"Volume x{gain:.2f} · niveau jeu/chat {level:.2f}")
    else:
        _set_module_runtime("teamsync", "Actif", f"Surveillance en cours · niveau jeu/chat {level:.2f}")
    TEAMSYNC_RUNTIME["last_gain"] = gain
    return gain

if sys.platform == "win32":
    import winsound

log = logging.getLogger('werkzeug')
log.setLevel(logging.ERROR)


# ==================== PACK DE VOIX ====================
FALLBACK_VOICES = [
    {"ShortName": "fr-FR-VivienneMultilingualNeural", "Gender": "Female", "Locale": "fr-FR"},
    {"ShortName": "fr-FR-RemyMultilingualNeural", "Gender": "Male", "Locale": "fr-FR"},
    {"ShortName": "en-US-JennyNeural", "Gender": "Female", "Locale": "en-US"},
    {"ShortName": "en-US-GuyNeural", "Gender": "Male", "Locale": "en-US"}
]

# ==================== CONFIGURATION ====================
# ==================== CONFIGURATION ====================
EDGE_VOICE_MAP = {
    # --- MAJUSCULES (Interface) ---
    "FR": {"F": "fr-FR-VivienneMultilingualNeural", "M": "fr-FR-RemyMultilingualNeural"},
    "EN": {"F": "en-US-JennyNeural", "M": "en-US-GuyNeural"},
    "ES": {"F": "es-ES-ElviraNeural", "M": "es-ES-AlvaroNeural"},
    "DE": {"F": "de-DE-KatjaNeural", "M": "de-DE-KillianNeural"},
    "IT": {"F": "it-IT-ElsaNeural", "M": "it-IT-DiegoNeural"},
    "RU": {"F": "ru-RU-SvetlanaNeural", "M": "ru-RU-DmitryNeural"},
    "PT": {"F": "pt-PT-RaquelNeural", "M": "pt-PT-DuarteNeural"},
    "PL": {"F": "pl-PL-ZofiaNeural", "M": "pl-PL-MarekNeural"},
    "TR": {"F": "tr-TR-EmelNeural", "M": "tr-TR-AhmetNeural"},
    "JA": {"F": "ja-JP-NanamiNeural", "M": "ja-JP-KeitaNeural"},
    "ZH": {"F": "zh-CN-XiaoxiaoNeural", "M": "zh-CN-YunxiNeural"},
    "KO": {"F": "ko-KR-SunHiNeural", "M": "ko-KR-InJoonNeural"},

    # --- MINUSCULES (Traduction) ---
    "fr": {"F": "fr-FR-VivienneMultilingualNeural", "M": "fr-FR-RemyMultilingualNeural"},
    "en": {"F": "en-US-JennyNeural", "M": "en-US-GuyNeural"},
    "es": {"F": "es-ES-ElviraNeural", "M": "es-ES-AlvaroNeural"},
    "de": {"F": "de-DE-KatjaNeural", "M": "de-DE-KillianNeural"},
    "it": {"F": "it-IT-ElsaNeural", "M": "it-IT-DiegoNeural"},
    "ru": {"F": "ru-RU-SvetlanaNeural", "M": "ru-RU-DmitryNeural"},
    "pt": {"F": "pt-PT-RaquelNeural", "M": "pt-PT-DuarteNeural"},
    "pl": {"F": "pl-PL-ZofiaNeural", "M": "pl-PL-MarekNeural"},
    "tr": {"F": "tr-TR-EmelNeural", "M": "tr-TR-AhmetNeural"},
    "ja": {"F": "ja-JP-NanamiNeural", "M": "ja-JP-KeitaNeural"},
    "zh-cn": {"F": "zh-CN-XiaoxiaoNeural", "M": "zh-CN-YunxiNeural"}, # Chinois
    "ko": {"F": "ko-KR-SunHiNeural", "M": "ko-KR-InJoonNeural"}
}

def normalize_lang_for_voice(lang_code):
    """Normalise un code langue vers les clés de EDGE_VOICE_MAP."""
    s = str(lang_code or "").strip().lower()
    if not s:
        return "en"
    if s in ("zh", "zh-cn", "zh-hans", "chinese"):
        return "zh-cn"
    if s.startswith("en"):
        return "en"
    if s.startswith("fr"):
        return "fr"
    if s.startswith("es"):
        return "es"
    if s.startswith("de"):
        return "de"
    if s.startswith("it"):
        return "it"
    if s.startswith("ru"):
        return "ru"
    if s.startswith("pt"):
        return "pt"
    if s.startswith("pl"):
        return "pl"
    if s.startswith("tr"):
        return "tr"
    if s.startswith("ja") or s.startswith("jp"):
        return "ja"
    if s.startswith("ko"):
        return "ko"
    return "en"

def get_auto_ally_voice(lang_code):
    """Choisit une voix Edge pour l'allié.
    Par défaut, on force le rendu FR pour rester cohérent avec la traduction affichée.
    """
    gender_key = "F" if app_state.get("gender", "MALE") == "FEMALE" else "M"
    if AUDIO_CONFIG.get("ally_force_french_voice", True):
        by_lang_fr = EDGE_VOICE_MAP.get("fr", {})
        forced = by_lang_fr.get(gender_key)
        if forced:
            return forced

    key = normalize_lang_for_voice(lang_code)
    by_lang = EDGE_VOICE_MAP.get(key) or EDGE_VOICE_MAP.get("en", {})
    return by_lang.get(gender_key) or "en-US-GuyNeural"

def detect_ally_language(text, dg_result=None):
    """Détecte la langue alliée à partir de Deepgram live puis fallback Lingua."""
    # 1) Tentative via résultat Deepgram live
    try:
        if dg_result is not None:
            ch = getattr(dg_result, "channel", None)
            if ch is not None:
                v = getattr(ch, "detected_language", None)
                if v:
                    return normalize_lang_for_voice(v)
                alts = getattr(ch, "alternatives", None) or []
                if alts:
                    a0 = alts[0]
                    v2 = getattr(a0, "detected_language", None)
                    if v2:
                        return normalize_lang_for_voice(v2)
    except Exception:
        pass

    # 2) Fallback Lingua (déjà initialisé plus haut)
    try:
        if detector and text:
            lang_obj = detector.detect_language_of(text)
            if lang_obj is not None:
                name = str(lang_obj).upper()
                map_lingua = {
                    "ENGLISH": "en",
                    "FRENCH": "fr",
                    "SPANISH": "es",
                    "GERMAN": "de",
                    "RUSSIAN": "ru",
                    "PORTUGUESE": "pt",
                    "JAPANESE": "ja",
                    "CHINESE": "zh-cn",
                    "KOREAN": "ko",
                    "ITALIAN": "it",
                    "POLISH": "pl",
                    "TURKISH": "tr",
                }
                for k, v in map_lingua.items():
                    if k in name:
                        return v
    except Exception:
        pass

    return "en"

def normalize_live_deepgram_lang(lang_code):
    """Normalise la langue LiveOptions Deepgram vers un code robuste."""
    s = str(lang_code or "").strip().lower()
    if not s:
        return "multi"
    # Normalisation des locales (it-IT, en-US, fr-FR...) vers langue simple.
    if "-" in s:
        s = s.split("-", 1)[0]
    if s in {"multi", "en", "fr", "es", "de", "it", "pt", "ru", "ja", "ko", "zh", "tr", "pl", "nl", "sv", "uk", "id", "th", "vi", "hi"}:
        return s
    return "multi"


def _apply_voice_focus_signal(mono, sample_rate, mode="off"):
    """
    Filtre vocal léger pour limiter le son du jeu dans le flux STT.
    Retour: (signal_filtre, peak_abs)
    """
    try:
        x = np.asarray(mono, dtype=np.float32).flatten()
        # Garde-fou numérique: élimine NaN/Inf dès l'entrée.
        x = np.nan_to_num(x, nan=0.0, posinf=0.0, neginf=0.0)
        if x.size == 0:
            return x, 0.0
        # V5.3 FIX: normalise si signal int16 non converti (évite overflow np.square)
        peak_raw = float(np.max(np.abs(x))) if x.size else 0.0
        if peak_raw > 1.0:
            x = x / max(peak_raw, 1e-6)

        m = str(mode or "off").strip().lower()
        if m == "auto":
            rms = float(np.sqrt(np.mean(np.square(x)))) if x.size else 0.0
            peak_raw = float(np.max(np.abs(x))) if x.size else 0.0
            crest = (peak_raw / max(rms, 1e-6)) if peak_raw > 0 else 1.0

            prev_rms = float(_listen_focus_auto_state.get("noise_rms_ema", 0.0) or 0.0)
            prev_crest = float(_listen_focus_auto_state.get("crest_ema", 0.0) or 0.0)
            rms_ema = (prev_rms * 0.86) + (rms * 0.14)
            crest_ema = (prev_crest * 0.82) + (crest * 0.18) if prev_crest > 0 else crest
            _listen_focus_auto_state["noise_rms_ema"] = rms_ema
            _listen_focus_auto_state["crest_ema"] = crest_ema

            now_auto = time.time()
            prev_mode_eff = str(_listen_focus_auto_state.get("mode_effective", "balanced") or "balanced")
            mode_eff = prev_mode_eff
            should_aggressive = (rms_ema >= 0.0145 and crest_ema <= 3.4) or (rms_ema >= 0.0200)
            should_balanced = (rms_ema <= 0.0105 and crest_ema >= 3.9)
            if should_aggressive:
                mode_eff = "aggressive"
            elif should_balanced:
                mode_eff = "balanced"

            last_sw = float(_listen_focus_auto_state.get("last_switch_at", 0.0) or 0.0)
            if mode_eff != prev_mode_eff:
                if (now_auto - last_sw) >= 2.5:
                    _listen_focus_auto_state["mode_effective"] = mode_eff
                    _listen_focus_auto_state["last_switch_at"] = now_auto
                else:
                    mode_eff = prev_mode_eff
            else:
                _listen_focus_auto_state["mode_effective"] = mode_eff
            m = mode_eff

        if m in ("off", "none", "0", "false"):
            peak = float(np.max(np.abs(x))) if x.size else 0.0
            return x, peak

        sr = int(sample_rate or 48000)
        if sr < 8000:
            sr = 8000

        # Paramètres selon agressivité.
        if m == "aggressive":
            low_hz, high_hz = 170.0, 3600.0
            stop_gain = 0.01
            gate_floor = 0.0016
        else:  # balanced
            low_hz, high_hz = 120.0, 4200.0
            stop_gain = 0.04
            gate_floor = 0.0011

        n = int(x.size)
        if n < 64:
            peak = float(np.max(np.abs(x))) if x.size else 0.0
            return x, peak

        w = np.hanning(n).astype(np.float32)
        X = np.fft.rfft(x * w)
        f = np.fft.rfftfreq(n, d=(1.0 / float(sr)))
        passband = (f >= low_hz) & (f <= high_hz)
        X[~passband] *= stop_gain
        y = np.fft.irfft(X, n=n).astype(np.float32)
        y = np.nan_to_num(y, nan=0.0, posinf=0.0, neginf=0.0)

        peak = float(np.max(np.abs(y))) if y.size else 0.0
        # Noise gate simple.
        if peak < gate_floor:
            y *= 0.0
            peak = 0.0

        return y, peak
    except Exception:
        x = np.asarray(mono, dtype=np.float32).flatten()
        x = np.nan_to_num(x, nan=0.0, posinf=0.0, neginf=0.0)
        peak = float(np.max(np.abs(x))) if x.size else 0.0
        return x, peak

# V5.3: Voice Focus V3 — état calibré + per-band + de-essing + auto-gain
_voice_focus_v3_state = {
    "calibrated": False,
    "calibration_started_at": 0.0,
    "calibration_duration_s": 30.0,
    "calibration_samples": 0,
    "noise_floor_low": 0.0,
    "noise_floor_mid": 0.0,
    "noise_floor_high": 0.0,
    "voice_target_rms": 0.08,
    "gain_riding_ema": 1.0,
    "gain_riding_alpha": 0.03,
    "sibilance_threshold": 0.0,
    "click_threshold": 0.0,
    "room_decay_ema": 0.0,
    "vad_threshold_adaptive": 0.025,
    "vad_noise_floor_ema": 0.0,
    "vad_voice_peak_ema": 0.0,
    "voiceprint_centroid_ema": 500.0,
    "voiceprint_spread_ema": 800.0,
    "voiceprint_initialized": False,
    "last_frame_processed_at": 0.0,
}

_voice_focus_v3_voiceprint_buf = collections.deque(maxlen=300)

def _voice_focus_v3_reset_calibration():
    global _voice_focus_v3_state
    _voice_focus_v3_state["calibrated"] = False
    _voice_focus_v3_state["calibration_started_at"] = 0.0
    _voice_focus_v3_state["calibration_samples"] = 0
    _voice_focus_v3_state["noise_floor_low"] = 0.0
    _voice_focus_v3_state["noise_floor_mid"] = 0.0
    _voice_focus_v3_state["noise_floor_high"] = 0.0
    _voice_focus_v3_state["gain_riding_ema"] = 1.0
    _voice_focus_v3_state["vad_threshold_adaptive"] = float(AUDIO_CONFIG.get("vad_threshold", 0.025) or 0.025)
    _voice_focus_v3_state["vad_noise_floor_ema"] = 0.0
    _voice_focus_v3_state["vad_voice_peak_ema"] = 0.0
    _voice_focus_v3_state["voiceprint_centroid_ema"] = 500.0
    _voice_focus_v3_state["voiceprint_spread_ema"] = 800.0
    _voice_focus_v3_state["voiceprint_initialized"] = False
    _voice_focus_v3_state["last_frame_processed_at"] = 0.0
    _voice_focus_v3_state["room_decay_ema"] = 0.0
    _voice_focus_v3_voiceprint_buf.clear()


def _voice_focus_v3_calibrate_step(x, sr, peak, rms):
    st = _voice_focus_v3_state
    if st["calibration_started_at"] <= 0:
        st["calibration_started_at"] = time.time()
    st["calibration_samples"] += 1
    now = time.time()
    elapsed = now - st["calibration_started_at"]
    n = min(len(x), sr // 4) if len(x) >= 64 else len(x)
    if n >= 64:
        w = np.hanning(n).astype(np.float32) if n <= len(x) else np.hanning(len(x)).astype(np.float32)
        X = np.abs(np.fft.rfft(x[:n] * w[:n]))
        sr_eff = int(sr or 48000)
        freqs = np.fft.rfftfreq(n, d=1.0 / float(sr_eff))
        low_mask = freqs < 250.0
        mid_mask = (freqs >= 250.0) & (freqs < 4000.0)
        high_mask = freqs >= 4000.0
        el = float(np.mean(X[low_mask] ** 2)) if np.any(low_mask) else 0.0
        em = float(np.mean(X[mid_mask] ** 2)) if np.any(mid_mask) else 0.0
        eh = float(np.mean(X[high_mask] ** 2)) if np.any(high_mask) else 0.0
        alpha = 0.15
        st["noise_floor_low"] = st["noise_floor_low"] * (1.0 - alpha) + el * alpha
        st["noise_floor_mid"] = st["noise_floor_mid"] * (1.0 - alpha) + em * alpha
        st["noise_floor_high"] = st["noise_floor_high"] * (1.0 - alpha) + eh * alpha
        centroid = float(np.sum(freqs * X) / (np.sum(X) + 1e-12))
        spread = float(np.sqrt(np.sum((freqs - centroid) ** 2 * X) / (np.sum(X) + 1e-12)))
        _voice_focus_v3_voiceprint_buf.append((centroid, spread))
    st["vad_noise_floor_ema"] = st["vad_noise_floor_ema"] * 0.92 + rms * 0.08
    if peak > 0.01:
        st["vad_voice_peak_ema"] = st["vad_voice_peak_ema"] * 0.88 + peak * 0.12
    room_rms = rms * 0.15
    st["room_decay_ema"] = st["room_decay_ema"] * 0.95 + room_rms * 0.05
    if elapsed >= st["calibration_duration_s"]:
        st["calibrated"] = True
        st["vad_threshold_adaptive"] = max(0.008, min(0.06, st["vad_noise_floor_ema"] * 3.5))
        st["voice_target_rms"] = max(0.03, min(0.15, st["vad_voice_peak_ema"] * 0.45))
        st["sibilance_threshold"] = st["noise_floor_high"] * 1.8
        st["click_threshold"] = rms * 6.0
        if _voice_focus_v3_voiceprint_buf:
            cents = [c for c, s in _voice_focus_v3_voiceprint_buf if c > 10]
            spreads = [s for c, s in _voice_focus_v3_voiceprint_buf if s > 10]
            if cents:
                st["voiceprint_centroid_ema"] = float(np.mean(cents))
            if spreads:
                st["voiceprint_spread_ema"] = float(np.mean(spreads))
        st["voiceprint_initialized"] = True
        AUDIO_CONFIG["vad_threshold"] = round(st["vad_threshold_adaptive"], 6)
        AUDIO_CONFIG["voice_focus_v3_calibrated"] = True
        try:
            stealth_print(f"✅ Voice Focus V3 calibré: seuil VAD={st['vad_threshold_adaptive']:.4f}, target_rms={st['voice_target_rms']:.3f}")
        except Exception:
            pass
        try:
            save_settings()
        except Exception:
            pass
    return st["calibrated"]


def _apply_voice_focus_v3(mono, sample_rate):
    try:
        x = np.asarray(mono, dtype=np.float32).flatten()
        x = np.nan_to_num(x, nan=0.0, posinf=0.0, neginf=0.0)
        if x.size == 0:
            return x, 0.0, False
        # V5.3 FIX: normalise si le signal vient d'un format int16 non converti (évite overflow np.square)
        peak_raw = float(np.max(np.abs(x))) if x.size else 0.0
        if peak_raw > 1.0:
            x = x / max(peak_raw, 1e-6)
        sr = int(sample_rate or 48000)
        if sr < 8000:
            sr = 8000
        rms = float(np.sqrt(np.mean(np.square(x)))) if x.size else 0.0
        peak = float(np.max(np.abs(x))) if x.size else 0.0
        st = _voice_focus_v3_state
        st["last_frame_processed_at"] = time.time()

        # Calibration si pas encore fait
        calibrated = st["calibrated"]
        if not calibrated:
            calibrated = _voice_focus_v3_calibrate_step(x, sr, peak, rms)
            if not calibrated:
                sig, pk = _apply_voice_focus_signal(x, sr, mode="balanced")
                return sig, pk, False  # False = pas encore calibré

        n = len(x)
        if n < 64:
            return x, peak, True

        # --- Per-band noise reduction ---
        w = np.hanning(n).astype(np.float32)
        X = np.fft.rfft(x * w)
        f = np.fft.rfftfreq(n, d=1.0 / float(sr))
        low_mask = f < 250.0
        mid_mask = (f >= 250.0) & (f < 4000.0)
        high_mask = f >= 4000.0

        # Calculer les gains par bande à partir des floors calibrés
        el_now = float(np.mean(np.abs(X[low_mask]) ** 2)) if np.any(low_mask) else 1e-12
        em_now = float(np.mean(np.abs(X[mid_mask]) ** 2)) if np.any(mid_mask) else 1e-12
        eh_now = float(np.mean(np.abs(X[high_mask]) ** 2)) if np.any(high_mask) else 1e-12

        # Réduction adaptative: si l'énergie dépasse le floor, on garde; sinon on atténue
        nf_low = max(st["noise_floor_low"], 1e-10)
        nf_mid = max(st["noise_floor_mid"], 1e-10)
        nf_high = max(st["noise_floor_high"], 1e-10)

        gain_low = min(1.0, float(np.sqrt(nf_low / max(el_now, nf_low * 0.01)) + 0.10))
        gain_mid = 1.0
        gain_high = min(1.0, float(np.sqrt(nf_high / max(eh_now, nf_high * 0.05)) + 0.15))

        # Apply per-band gains
        X_low = X.copy()
        X_low[~low_mask] = 0.0
        X_mid = X.copy()
        X_mid[~(mid_mask)] = 0.0
        X_high = X.copy()
        X_high[~(high_mask)] = 0.0

        X_out = X_low * gain_low + X_mid * gain_mid + X_high * gain_high

        # --- De-essing (suppression sifflantes 5-10kHz) ---
        sib_mask = (f >= 5000.0) & (f <= 10000.0)
        if np.any(sib_mask) and st["sibilance_threshold"] > 0:
            sib_energy = float(np.mean(np.abs(X_out[sib_mask]) ** 2))
            if sib_energy > st["sibilance_threshold"]:
                X_out[sib_mask] *= 0.35

        # --- De-clicking (transitoires brèves) ---
        if st["click_threshold"] > 0 and peak > st["click_threshold"] * rms + 0.01:
            diff = np.abs(np.diff(x))
            click_positions = np.where(diff > peak * 0.7)[0]
            if len(click_positions) < n * 0.05:
                for cp in click_positions:
                    lo = max(0, cp - 4)
                    hi = min(n, cp + 5)
                    x[lo:hi] *= 0.2

        # --- Anti-echo / dereverb (room decay compensation) ---
        room_decay = float(st.get("room_decay_ema", 0.0))
        if room_decay > 0.002:
            derev_alpha = min(0.6, room_decay * 8.0)
            X_out = X_out * (1.0 - derev_alpha * 0.4)
            peak_decay = np.abs(X_out).max() if X_out.size > 0 else 0.0
            if peak_decay < 1e-6:
                X_out = X

        # --- Auto-gain riding ---
        target = st["voice_target_rms"]
        if target > 0 and rms > target * 0.15:
            desired_gain = target / (rms + 1e-12)
            desired_gain = max(0.3, min(3.5, desired_gain))
            alpha = st["gain_riding_alpha"]
            st["gain_riding_ema"] = st["gain_riding_ema"] * (1.0 - alpha) + desired_gain * alpha
        applied_gain = st["gain_riding_ema"]
        X_out *= applied_gain

        y = np.fft.irfft(X_out, n=n).astype(np.float32)
        y = np.nan_to_num(y, nan=0.0, posinf=0.0, neginf=0.0)

        return y, peak, True
    except Exception:
        x = np.asarray(mono, dtype=np.float32).flatten()
        x = np.nan_to_num(x, nan=0.0, posinf=0.0, neginf=0.0)
        peak = float(np.max(np.abs(x))) if x.size else 0.0
        return x, peak, False


# ============================================================
# V5.3 — VAD V2 : WebRTC VAD + Silero-style RMS fallback
# ============================================================
_vad_v2_state = {
    "backend": "rms",          # "webrtc" | "rms"
    "webrtc_vad": None,
    "initialized": False,
    "speech_ratio_ema": 0.0,
    "frame_rate": 16000,
    "frame_ms": 30,            # webrtcvad accepts 10/20/30ms frames
}

def _vad_v2_init():
    """Try to load webrtcvad-wheels; fall back to RMS-based VAD silently."""
    st = _vad_v2_state
    if st["initialized"]:
        return
    st["initialized"] = True
    try:
        import webrtcvad
        vad_obj = webrtcvad.Vad(2)  # aggressiveness 0-3
        st["webrtc_vad"] = vad_obj
        st["backend"] = "webrtc"
        stealth_print("✅ VAD V2: webrtcvad actif (aggressiveness=2)")
    except ImportError:
        try:
            import webrtcvad_wheels as webrtcvad
            vad_obj = webrtcvad.Vad(2)
            st["webrtc_vad"] = vad_obj
            st["backend"] = "webrtc"
            stealth_print("✅ VAD V2: webrtcvad_wheels actif (aggressiveness=2)")
        except ImportError:
            st["backend"] = "rms"
            stealth_print("⚠️ VAD V2: webrtcvad indisponible, fallback RMS adaptatif")
    except Exception as e:
        st["backend"] = "rms"
        stealth_print(f"⚠️ VAD V2: init échouée ({e}), fallback RMS adaptatif")


def _vad_v2_is_speech(mono_float32: "np.ndarray", sample_rate: int) -> bool:
    """
    V5.3: Détecte si le frame contient de la parole.
    Essaie webrtcvad, fallback RMS adaptatif.
    """
    st = _vad_v2_state
    if not st["initialized"]:
        _vad_v2_init()

    rms = float(np.sqrt(np.mean(np.square(mono_float32)))) if mono_float32.size else 0.0
    threshold = float(AUDIO_CONFIG.get("vad_threshold", 0.025) or 0.025)

    if st["backend"] == "webrtc" and st["webrtc_vad"] is not None:
        try:
            # webrtcvad needs 16kHz int16 PCM, 10/20/30ms frames
            target_sr = 16000
            frame_ms = 30
            frame_samples = int(target_sr * frame_ms / 1000)

            # Resample if needed
            if sample_rate != target_sr:
                from_len = len(mono_float32)
                to_len = int(from_len * target_sr / sample_rate)
                if to_len > 0:
                    indices = np.linspace(0, from_len - 1, to_len)
                    resampled = np.interp(indices, np.arange(from_len), mono_float32).astype(np.float32)
                else:
                    resampled = mono_float32
            else:
                resampled = mono_float32

            # Process in 30ms frames, take majority vote
            pcm_int16 = np.clip(resampled * 32767, -32768, 32767).astype(np.int16)
            total_frames = len(pcm_int16) // frame_samples
            if total_frames == 0:
                raise ValueError("Frame trop courte pour webrtcvad")

            speech_frames = 0
            for i in range(total_frames):
                frame = pcm_int16[i * frame_samples:(i + 1) * frame_samples]
                frame_bytes = frame.tobytes()
                try:
                    if st["webrtc_vad"].is_speech(frame_bytes, target_sr):
                        speech_frames += 1
                except Exception:
                    pass  # frame size mismatch — skip

            ratio = speech_frames / max(total_frames, 1)
            # EMA smoothing
            st["speech_ratio_ema"] = st["speech_ratio_ema"] * 0.7 + ratio * 0.3
            AUDIO_CONFIG["_vad_v2_speech_ratio"] = round(float(st["speech_ratio_ema"]), 3)
            return st["speech_ratio_ema"] > 0.35

        except Exception as e:
            stealth_print(f"⚠️ VAD V2 webrtc frame error, fallback RMS: {e}")
            # Fallback silently to RMS for this frame
            st["backend"] = "rms"

    # RMS-based VAD with adaptive threshold (Silero-style behavior)
    v3_thresh = float(_voice_focus_v3_state.get("vad_threshold_adaptive", threshold))
    effective_thresh = v3_thresh if _voice_focus_v3_state.get("calibrated", False) else threshold
    speech = rms > effective_thresh
    # EMA smoothing
    st["speech_ratio_ema"] = st["speech_ratio_ema"] * 0.8 + (1.0 if speech else 0.0) * 0.2
    AUDIO_CONFIG["_vad_v2_speech_ratio"] = round(float(st["speech_ratio_ema"]), 3)
    return speech


def get_vad_v2_status() -> dict:
    """V5.3: Retourne l'état du VAD V2 pour /status."""
    st = _vad_v2_state
    return {
        "vad_v2_backend": st["backend"],
        "vad_v2_speech_ratio": round(float(st.get("speech_ratio_ema", 0.0)), 3),
        "vad_v2_initialized": st["initialized"],
        "vad_threshold_adaptive": round(float(_voice_focus_v3_state.get("vad_threshold_adaptive", 0.025)), 6),
    }

# Auto-init VAD V2 at import time (non-blocking)
try:
    threading.Thread(target=_vad_v2_init, daemon=True).start()
except Exception:
    pass

VOICES_LIBRARY = {
    "Moi (Défaut)": "DEFAULT_USER_VOICE",   
    "Rachel (Femme)": "21m00Tcm4TlvDq8ikWAM",   
    "Clyde (Grave)": "2EiwWnXFnvU5JabPnv8n",    
    "Charlie (Sympa)": "IKne3meq5aSn9XLyUdCD",  
    "Nicole (Rapide)": "piTKgcLEGmPE4e6mEKli"   
}

DEFAULT_VOICE_ID = ""
VTP_CORE_PORT = 8770
UPDATE_URL = "https://pastebin.com/raw/dummy" 
APP_BUILD_VERSION = "5.3"

def _load_current_version(default: str = APP_BUILD_VERSION) -> str:
    # In packaged builds, rely on the embedded build version instead of an
    # external version.txt that can be replaced independently of the EXE.
    if getattr(sys, "frozen", False):
        return default
    candidates = []
    try:
        base = Path(sys.argv[0]).resolve().parent
        candidates.append(base / "version.txt")
    except Exception:
        pass
    candidates.append(Path.cwd() / "version.txt")
    for p in candidates:
        try:
            if p.exists():
                raw = p.read_text(encoding="utf-8", errors="ignore").strip()
                if raw:
                    return raw
        except Exception:
            pass
    return default

CURRENT_VERSION = _load_current_version()
UPDATE_CHANNEL = os.environ.get("KOMMZ_UPDATE_CHANNEL", "stable").strip().lower() or "stable"
UPDATE_CHECK_URL = os.environ.get(
    "KOMMZ_UPDATE_CHECK_URL",
    ""
).strip()

UPDATE_STATE = {
    "checked_at": 0,
    "update_available": False,
    "latest_version": CURRENT_VERSION,
    "download_url": "",
    "changelog_url": "",
    "download_sha256": "",
    "force_update": False,
    "minimum_version": "",
    "message": "",
    "error": "",
    "installing": False,
    "install_status": "",
}

VOICE_CLOUD_LIMIT_STATE = {
    "reached": False,
    "message": "",
}

PIPELINE_RUNTIME_STATE = {
    "stt_engine": "En attente",
    "stt_detail": "Aucune transcription récente",
    "hybrid_engine": "En attente",
    "hybrid_detail": "Aucune génération Hybrid récente",
    "tts_engine": "En attente",
    "tts_route": "Aucune synthèse récente",
    "updated_at": 0.0,
}

LATENCY_RUNTIME_STATE = {
    "stt_ms": None,
    "translate_ms": None,
    "tts_ms": None,
    "total_ms": None,
    "stage": "idle",
    "detail": "Aucune activité récente",
    "updated_at": 0.0,
    # V5.3: Percentiles p50/p95/p99
    "stt_p50": None, "stt_p95": None, "stt_p99": None,
    "tts_p50": None, "tts_p95": None, "tts_p99": None,
    "total_p50": None, "total_p95": None, "total_p99": None,
    "sample_count": 0,
}

_latency_runtime_lock = threading.Lock()
# V5.3: Circular history buffer for percentile computation (last 200 calls)
_stt_latency_history   = collections.deque(maxlen=200)
_tts_latency_history   = collections.deque(maxlen=200)
_total_latency_history = collections.deque(maxlen=200)

def _compute_latency_percentiles():
    """V5.3: Compute p50/p95/p99 from history buffers. Called inside _latency_runtime_lock."""
    for key, buf in [("stt", _stt_latency_history), ("tts", _tts_latency_history), ("total", _total_latency_history)]:
        if len(buf) < 5:
            LATENCY_RUNTIME_STATE[f"{key}_p50"] = None
            LATENCY_RUNTIME_STATE[f"{key}_p95"] = None
            LATENCY_RUNTIME_STATE[f"{key}_p99"] = None
            continue
        arr = sorted(buf)
        n = len(arr)
        LATENCY_RUNTIME_STATE[f"{key}_p50"] = round(arr[int(n * 0.50)], 1)
        LATENCY_RUNTIME_STATE[f"{key}_p95"] = round(arr[min(int(n * 0.95), n - 1)], 1)
        LATENCY_RUNTIME_STATE[f"{key}_p99"] = round(arr[min(int(n * 0.99), n - 1)], 1)
    LATENCY_RUNTIME_STATE["sample_count"] = len(_stt_latency_history)

EXPRESSIVE_RUNTIME_STATE = {
    "enabled": True,
    "profile": "gaming",
    "transcript_mode": "keep",
    "tts_mode": "styled",
    "effective_tts_mode": "styled",
    "intensity_mode": "auto",
    "intensity": "soft",
    "noise_mode": "smart",
    "engine_target": "xtts",
    "engine_mode": "auto",
    "stability_mode": "balanced",
    "fallback_guard": True,
    "source_mode": "manual",
    "usage_mode": "safe",
    "confidence": 0.0,
    "smoothed": False,
    "primary": "",
    "active": [],
    "detail": "Expressivité en veille",
    "updated_at": 0.0,
}

HYBRID_FAST_RUNTIME_STATE = {
    "fast_path": False,
    "cache_hot": False,
    "cache_age_seconds": -1,
    "detail": "RTS fast path en veille",
    "updated_at": 0.0,
}

QUALITY_LOG_MAX_ITEMS = 40
QUALITY_LOG_STATE = collections.deque(maxlen=QUALITY_LOG_MAX_ITEMS)
_quality_log_lock = threading.Lock()
TTS_FALLBACK_RUNTIME_STATE = {
    "count": 0,
    "last_code": "",
    "last_message": "Aucun fallback recent",
    "last_detail": "",
    "last_endpoint": "",
    "last_http_status": 0,
    "last_attempts": "",
    "last_at": 0.0,
}

MODULE_RUNTIME_STATE = {
    "updated_at": 0.0,
    "seamless": {"state": "Inactif", "detail": "Nettoyage des préfixes désactivé", "updated_at": 0.0},
    "smart": {"state": "Inactif", "detail": "Commandes vocales désactivées", "updated_at": 0.0},
    "teamsync": {"state": "Actif", "detail": "En veille, en attente de niveau jeu/chat", "updated_at": 0.0},
    "turbo": {"state": "Actif", "detail": "Latence réduite prête", "updated_at": 0.0},
    "shadow": {"state": "Inactif", "detail": "Warmup désactivé", "updated_at": 0.0},
    "autocontext": {"state": "Actif", "detail": "Contexte gaming prêt", "updated_at": 0.0},
    "autoupdate": {"state": "Actif", "detail": "Veille des releases active", "updated_at": 0.0},
    "esport": {"state": "Normal+", "detail": "Priorité process standard améliorée", "updated_at": 0.0},
    "stealth": {"state": "Inactif", "detail": "Logs visibles dans la console", "updated_at": 0.0},
    "tilt": {"state": "Actif", "detail": "Filtre anti-toxicité prêt", "updated_at": 0.0},
    "polyglot": {"state": "Inactif", "detail": "Export OBS secondaire désactivé", "updated_at": 0.0},
    "privacy": {"state": "Inactif", "detail": "Protection des données désactivée", "updated_at": 0.0},
    "marker": {"state": "Inactif", "detail": "Marqueurs stream désactivés", "updated_at": 0.0},
    "macros": {"state": "Actif", "detail": "Macros vocales prêtes", "updated_at": 0.0},
    "stream": {"state": "Actif", "detail": "Export OBS principal prêt", "updated_at": 0.0},
    "hybrid": {"state": "Inactif", "detail": "Détection automatique de la voix désactivée", "updated_at": 0.0},
}


def _short_runtime_text(value, limit=140):
    txt = _repair_display_text(str(value or "").strip())
    if len(txt) <= limit:
        return txt
    return txt[: limit - 1].rstrip() + "…"


def _short_runtime_url(url: str, limit: int = 96) -> str:
    value = str(url or "").strip()
    if not value:
        return ""
    try:
        parsed = urlsplit(value)
        host = (parsed.netloc or "").strip()
        path = (parsed.path or "").strip()
        compact = host + path
        if compact:
            value = compact
    except Exception:
        pass
    return _short_runtime_text(value, limit)


def _set_pipeline_runtime(**kwargs):
    for key, value in kwargs.items():
        if key in PIPELINE_RUNTIME_STATE and value is not None:
            PIPELINE_RUNTIME_STATE[key] = _short_runtime_text(value, 160)
    PIPELINE_RUNTIME_STATE["updated_at"] = time.time()


def _set_module_runtime(name, state=None, detail=None):
    entry = MODULE_RUNTIME_STATE.setdefault(
        name,
        {"state": "Inconnu", "detail": "", "updated_at": 0.0},
    )
    if state is not None:
        entry["state"] = _short_runtime_text(state, 48)
    if detail is not None:
        entry["detail"] = _short_runtime_text(detail, 180)
    entry["updated_at"] = time.time()
    MODULE_RUNTIME_STATE["updated_at"] = entry["updated_at"]


def _runtime_age_seconds(ts_value) -> int:
    try:
        ts = float(ts_value or 0.0)
    except Exception:
        return -1
    if ts <= 0:
        return -1
    return max(0, int(time.time() - ts))


def _build_pipeline_runtime_payload():
    payload = dict(PIPELINE_RUNTIME_STATE)
    payload["age_seconds"] = _runtime_age_seconds(payload.get("updated_at", 0.0))
    return payload


def _build_modules_runtime_payload():
    out = {}
    for key, entry in MODULE_RUNTIME_STATE.items():
        if key == "updated_at":
            continue
        item = dict(entry)
        item["age_seconds"] = _runtime_age_seconds(item.get("updated_at", 0.0))
        out[key] = item
    out["updated_at"] = MODULE_RUNTIME_STATE.get("updated_at", 0.0)
    out["age_seconds"] = _runtime_age_seconds(out["updated_at"])
    return out


def _build_tts_fallback_runtime_payload():
    payload = dict(TTS_FALLBACK_RUNTIME_STATE)
    payload["age_seconds"] = _runtime_age_seconds(payload.get("last_at", 0.0))
    return payload


def _normalize_quality_preset(preset) -> str:
    value = str(preset or "balanced").strip().lower()
    if value in {"ultra", "ultrafast", "ultra_fast", "ultra-fast"}:
        return "ultra_fast"
    if value in {"natural", "quality"}:
        return "natural"
    return "balanced"


def _apply_quality_preset(preset, emit_log: bool = True):
    normalized = _normalize_quality_preset(preset)
    AUDIO_CONFIG["quality_preset"] = normalized
    if normalized == "ultra_fast":
        AUDIO_CONFIG["turbo_latency_active"] = True
        AUDIO_CONFIG["hybrid_rts_preset"] = "fast"
        AUDIO_CONFIG["hybrid_fast_rts"] = True
        AUDIO_CONFIG["ptt_release_tail_ms"] = 120
    elif normalized == "natural":
        AUDIO_CONFIG["turbo_latency_active"] = False
        AUDIO_CONFIG["hybrid_rts_preset"] = "quality"
        AUDIO_CONFIG["hybrid_fast_rts"] = False
        AUDIO_CONFIG["ptt_release_tail_ms"] = 220
    else:
        AUDIO_CONFIG["turbo_latency_active"] = True
        AUDIO_CONFIG["hybrid_rts_preset"] = "fast"
        AUDIO_CONFIG["hybrid_fast_rts"] = True
        AUDIO_CONFIG["ptt_release_tail_ms"] = 180
    if emit_log:
        _push_quality_log(
            "info",
            "quality_preset",
            f"Preset qualité: {normalized}",
            f"turbo={AUDIO_CONFIG.get('turbo_latency_active')} · hybrid={AUDIO_CONFIG.get('hybrid_rts_preset')}",
        )
    return normalized


def _push_quality_log(level: str, code: str, message: str, detail: str = ""):
    entry = {
        "ts": _utc_now_iso(),
        "level": str(level or "info").strip().lower(),
        "code": _short_runtime_text(code or "event", 48),
        "message": _short_runtime_text(message or "", 220),
        "detail": _short_runtime_text(detail or "", 280),
    }
    with _quality_log_lock:
        QUALITY_LOG_STATE.append(entry)


# V5.2: Queue de toasts pour notifications desktop (Python → JS via polling)
QUEUED_TOASTS = []
_toast_lock = threading.Lock()

def _push_toast(message: str):
    """Ajoute un toast qui sera récupéré par l'UI au prochain poll."""
    try:
        msg = str(message or "").strip()
        if not msg:
            return
        with _toast_lock:
            QUEUED_TOASTS.append(msg)
            # Garde max 20 toasts en attente pour éviter fuite mémoire
            if len(QUEUED_TOASTS) > 20:
                QUEUED_TOASTS[:] = QUEUED_TOASTS[-20:]
    except Exception:
        pass


TTS_FALLBACK_REASON_MAP = {
    "NO_REFERENCE_AUDIO_BUFFER": "Aucune reference audio disponible (micro/preset).",
    "EMPTY_MODAL_URL": "Endpoint XTTS non configure.",
    "NO_MODAL_CANDIDATE_URL": "Aucun endpoint XTTS exploitable.",
    "ALL_MODAL_ENDPOINTS_FAILED": "Tous les endpoints XTTS ont echoue.",
    "TRIAL_QUOTA_REACHED": "Quota cloud atteint, bascule automatique Windows.",
    "VOICE_ID_TRIAL_QUOTA": "Quota essai voice_id atteint, bascule clone direct.",
    "VOICE_ID_URL_MISSING": "Endpoint voice_id non configure, bascule clone direct.",
    "VOICE_ID_UNAVAILABLE": "Voice_id indisponible, bascule clone direct.",
    "HTTP_ERROR": "Erreur HTTP sur le moteur cloud.",
    "EXCEPTION_DURING_KOMMZ_TTS": "Exception pendant generation cloud.",
}


def _register_tts_fallback(
    reason_code: str,
    detail: str = "",
    endpoint: str = "",
    http_status: int | None = None,
    attempts: str = "",
):
    code = str(reason_code or "UNKNOWN").strip().upper()
    friendly = TTS_FALLBACK_REASON_MAP.get(code, "Fallback moteur cloud.")
    msg = f"{friendly} ({code})"
    detail_txt = _short_runtime_text(detail or "", 220)
    endpoint_txt = _short_runtime_url(endpoint or "", 120)
    attempts_txt = _short_runtime_text(attempts or "", 280)
    status_num = 0
    try:
        status_num = int(http_status or 0)
    except Exception:
        status_num = 0
    try:
        TTS_FALLBACK_RUNTIME_STATE["count"] = int(TTS_FALLBACK_RUNTIME_STATE.get("count", 0) or 0) + 1
        TTS_FALLBACK_RUNTIME_STATE["last_code"] = code
        TTS_FALLBACK_RUNTIME_STATE["last_message"] = friendly
        TTS_FALLBACK_RUNTIME_STATE["last_detail"] = detail_txt
        TTS_FALLBACK_RUNTIME_STATE["last_endpoint"] = endpoint_txt
        TTS_FALLBACK_RUNTIME_STATE["last_http_status"] = status_num
        TTS_FALLBACK_RUNTIME_STATE["last_attempts"] = attempts_txt
        TTS_FALLBACK_RUNTIME_STATE["last_at"] = time.time()
    except Exception:
        pass
    pipeline_detail_parts = []
    if endpoint_txt:
        pipeline_detail_parts.append(endpoint_txt)
    if status_num > 0:
        pipeline_detail_parts.append(f"HTTP {status_num}")
    if detail_txt:
        pipeline_detail_parts.append(detail_txt)
    if attempts_txt:
        pipeline_detail_parts.append(attempts_txt)
    _set_pipeline_runtime(
        tts_engine="Fallback",
        tts_route=_short_runtime_text(
            f"{msg} · {' | '.join(pipeline_detail_parts)}" if pipeline_detail_parts else msg,
            160,
        ),
    )
    _push_quality_log("warn", f"tts_fallback_{code.lower()}", friendly, detail_txt or attempts_txt)


def _build_quality_log_payload():
    with _quality_log_lock:
        items = list(QUALITY_LOG_STATE)
    items.reverse()
    return items


def _refresh_latency_total_locked():
    values = []
    for key in ("stt_ms", "translate_ms", "tts_ms"):
        raw = LATENCY_RUNTIME_STATE.get(key)
        if isinstance(raw, (int, float)):
            values.append(float(raw))
    LATENCY_RUNTIME_STATE["total_ms"] = round(sum(values), 1) if values else None


def _reset_latency_runtime(detail: str = "Traitement en attente"):
    with _latency_runtime_lock:
        LATENCY_RUNTIME_STATE["translate_ms"] = None
        LATENCY_RUNTIME_STATE["tts_ms"] = None
        LATENCY_RUNTIME_STATE["total_ms"] = None
        LATENCY_RUNTIME_STATE["stage"] = "pipeline"
        LATENCY_RUNTIME_STATE["detail"] = _short_runtime_text(detail, 180)
        LATENCY_RUNTIME_STATE["updated_at"] = time.time()


def _record_latency(stage: str, detail: str = "", stt_ms=None, translate_ms=None, tts_ms=None):
    with _latency_runtime_lock:
        if isinstance(stt_ms, (int, float)):
            v = round(float(stt_ms), 1)
            LATENCY_RUNTIME_STATE["stt_ms"] = v
            _stt_latency_history.append(v)  # V5.3: feed percentile buffer
        if isinstance(translate_ms, (int, float)):
            LATENCY_RUNTIME_STATE["translate_ms"] = round(float(translate_ms), 1)
        if isinstance(tts_ms, (int, float)):
            v = round(float(tts_ms), 1)
            LATENCY_RUNTIME_STATE["tts_ms"] = v
            _tts_latency_history.append(v)  # V5.3: feed percentile buffer
        LATENCY_RUNTIME_STATE["stage"] = _short_runtime_text(stage or "pipeline", 48)
        if detail:
            LATENCY_RUNTIME_STATE["detail"] = _short_runtime_text(detail, 180)
        _refresh_latency_total_locked()
        # V5.3: feed total latency buffer
        total = LATENCY_RUNTIME_STATE.get("total_ms")
        if isinstance(total, (int, float)):
            _total_latency_history.append(round(float(total), 1))
        # Compute percentiles every 5 samples (not every call, for performance)
        if len(_stt_latency_history) % 5 == 0:
            _compute_latency_percentiles()
        LATENCY_RUNTIME_STATE["updated_at"] = time.time()


def _build_latency_runtime_payload():
    with _latency_runtime_lock:
        payload = dict(LATENCY_RUNTIME_STATE)
    payload["age_seconds"] = _runtime_age_seconds(payload.get("updated_at", 0.0))
    payload["quality_preset"] = _normalize_quality_preset(AUDIO_CONFIG.get("quality_preset", "balanced"))
    return payload


def _set_expressive_runtime(**kwargs):
    for key, value in kwargs.items():
        if key not in EXPRESSIVE_RUNTIME_STATE:
            continue
        if key == "active":
            EXPRESSIVE_RUNTIME_STATE[key] = [str(v) for v in (value or [])][:6]
        elif isinstance(value, str):
            EXPRESSIVE_RUNTIME_STATE[key] = _short_runtime_text(value, 180)
        else:
            EXPRESSIVE_RUNTIME_STATE[key] = value
    EXPRESSIVE_RUNTIME_STATE["updated_at"] = time.time()


def _build_expressive_runtime_payload():
    payload = dict(EXPRESSIVE_RUNTIME_STATE)
    payload["age_seconds"] = _runtime_age_seconds(payload.get("updated_at", 0.0))
    return payload


def _set_hybrid_fast_runtime(fast_path=None, cache_hot=None, cache_age_seconds=None, detail=None):
    if fast_path is not None:
        HYBRID_FAST_RUNTIME_STATE["fast_path"] = bool(fast_path)
    if cache_hot is not None:
        HYBRID_FAST_RUNTIME_STATE["cache_hot"] = bool(cache_hot)
    if cache_age_seconds is not None:
        try:
            HYBRID_FAST_RUNTIME_STATE["cache_age_seconds"] = int(cache_age_seconds)
        except Exception:
            HYBRID_FAST_RUNTIME_STATE["cache_age_seconds"] = -1
    if detail is not None:
        HYBRID_FAST_RUNTIME_STATE["detail"] = _short_runtime_text(detail, 180)
    HYBRID_FAST_RUNTIME_STATE["updated_at"] = time.time()


def _build_hybrid_fast_runtime_payload():
    payload = dict(HYBRID_FAST_RUNTIME_STATE)
    payload["age_seconds"] = _runtime_age_seconds(payload.get("updated_at", 0.0))
    return payload


def _module_runtime_defaults(name, state=None):
    enabled = bool(state) if state is not None else False
    defaults = {
        "seamless": ("Actif" if enabled else "Inactif", "Nettoyage des préfixes prêt" if enabled else "Nettoyage des préfixes désactivé"),
        "smart": ("Actif" if enabled else "Inactif", "Commandes vocales prêtes" if enabled else "Commandes vocales désactivées"),
        "teamsync": ("Actif" if enabled else "Inactif", "Boost selon le niveau jeu/chat" if enabled else "Boost automatique désactivé"),
        "turbo": ("Actif" if enabled else "Inactif", "Latence réduite activée" if enabled else "Mode rapide désactivé"),
        "esport": ("Performance" if enabled else "Normal+", "Priorité CPU/process élevée" if enabled else "Priorité process standard améliorée"),
        "stealth": ("Actif" if enabled else "Inactif", "Logs discrets activés" if enabled else "Logs visibles dans la console"),
        "shadow": ("Actif" if enabled else "Inactif", "Warmup et cache audio prêts" if enabled else "Warmup désactivé"),
        "autocontext": ("Actif" if enabled else "Inactif", "Contexte gaming prêt" if enabled else "Contexte gaming désactivé"),
        "autoupdate": ("Actif" if enabled else "Inactif", "Veille des releases active" if enabled else "Vérification automatique désactivée"),
        "tilt": ("Actif" if enabled else "Inactif", "Filtre anti-toxicité prêt" if enabled else "Filtre anti-toxicité désactivé"),
        "stream": ("Actif" if enabled else "Inactif", "Export OBS principal prêt" if enabled else "Export OBS principal désactivé"),
        "macros": ("Actif" if enabled else "Inactif", "Macros vocales prêtes" if enabled else "Macros vocales désactivées"),
        "polyglot": ("Actif" if enabled else "Inactif", "Export OBS secondaire actif" if enabled else "Export OBS secondaire désactivé"),
        "privacy": ("Actif" if enabled else "Inactif", "Protection des données prête" if enabled else "Protection des données désactivée"),
        "marker": ("Actif" if enabled else "Inactif", "Marqueurs stream prêts" if enabled else "Marqueurs stream désactivés"),
        "hybrid": ("Actif" if enabled else "Inactif", "Détection automatique de la voix active" if enabled else "Détection automatique de la voix désactivée"),
    }
    return defaults.get(name, ("Inconnu", "État module indisponible"))


def _refresh_module_runtime_defaults():
    module_flags = {
        "seamless": AUDIO_CONFIG.get("seamless_prefix_active", False),
        "smart": AUDIO_CONFIG.get("smart_commands_active", False),
        "teamsync": AUDIO_CONFIG.get("teamsync_ai_active", False),
        "turbo": AUDIO_CONFIG.get("turbo_latency_active", False),
        "esport": AUDIO_CONFIG.get("esport_mode_active", False),
        "stealth": AUDIO_CONFIG.get("stealth_mode_active", False),
        "shadow": AUDIO_CONFIG.get("shadow_ai_active", False),
        "autocontext": AUDIO_CONFIG.get("auto_context_active", False),
        "autoupdate": AUDIO_CONFIG.get("auto_update_active", False),
        "tilt": AUDIO_CONFIG.get("tilt_shield_active", False),
        "stream": AUDIO_CONFIG.get("stream_connect_active", False),
        "macros": AUDIO_CONFIG.get("tactical_macros_active", False),
        "polyglot": AUDIO_CONFIG.get("polyglot_active", False),
        "privacy": AUDIO_CONFIG.get("privacy_sentinel_active", False),
        "marker": AUDIO_CONFIG.get("smart_marker_active", False),
        "hybrid": AUDIO_CONFIG.get("hybrid_activation_active", False),
    }
    for module_name, enabled in module_flags.items():
        state_value, detail_value = _module_runtime_defaults(module_name, enabled)
        _set_module_runtime(module_name, state_value, detail_value)


_refresh_module_runtime_defaults()


def _is_trial_voice_mode_enabled() -> bool:
    voice_key = (AUDIO_CONFIG.get("voice_license_key") or "").strip().upper()
    desktop_key = (AUDIO_CONFIG.get("license_key") or "").strip().upper()
    return voice_key.startswith("TRIAL-") or desktop_key.startswith("TRIAL-")


def _wav_duration_seconds(payload: bytes) -> int:
    """Retourne la durée (sec) d'un WAV en mémoire, sinon 0."""
    try:
        import wave
        bio = io.BytesIO(payload)
        with wave.open(bio, "rb") as w:
            frames = w.getnframes()
            rate = w.getframerate() or 0
            if rate <= 0:
                return 0
            return max(0, int(round(frames / float(rate))))
    except Exception:
        return 0


def _looks_like_cloud_trial_limit(status_code: int, body_text: str) -> bool:
    if status_code == 403:
        txt = (body_text or "").lower()
        markers = [
            "quota",
            "essai",
            "trial",
            "30 min",
            "remaining_seconds",
            "max_audio_seconds",
            "expir",
            "limite",
        ]
        return any(m in txt for m in markers)
    return False

# ✅ OPTIMIZED: Endpoints XTTS (configurables via env)
DEFAULT_KOMMZ_VOICE_ENDPOINT = os.environ.get(
    "KOMMZ_XTTS_GENERATE_URL",
    DEFAULT_KOMMZ_CLONE_URL,
).strip()
KOMMZ_VOICE_ENDPOINT = DEFAULT_KOMMZ_VOICE_ENDPOINT


def _build_kommz_modal_base_candidates(base_url: str):
    """Retourne les bases Modal probables, avec fallback sur la valeur par défaut embarquée."""
    out = []
    seen = set()

    def _push(url):
        u = (url or "").strip()
        if not u:
            return
        if not u.lower().startswith(("http://", "https://")):
            u = "https://" + u
        u = u.rstrip("/")
        if u and u not in seen:
            seen.add(u)
            out.append(u)

    _push(base_url)
    _push(os.environ.get("KOMMZ_XTTS_GENERATE_URL", ""))
    _push(DEFAULT_KOMMZ_CLONE_URL)
    _push(DEFAULT_KOMMZ_VOICE_ENDPOINT)
    return out


def _build_kommz_aux_candidates(target: str, base_url: str = ""):
    """Construit les URLs auxiliaires (health/warmup) avec fallback hôte et auto-réparation possible."""
    target = (target or "").strip().lower()
    out = []
    seen = set()

    def _push(url, source_base=""):
        u = (url or "").strip()
        if not u:
            return
        if not u.lower().startswith(("http://", "https://")):
            u = "https://" + u
        u = u.rstrip("/")
        if u and u not in seen:
            seen.add(u)
            out.append({"url": u, "base_url": (source_base or "").strip().rstrip("/")})

    forced = ""
    if target == "warmup":
        forced = str(os.environ.get("KOMMZ_XTTS_WARMUP_URL", "") or "").strip()
    elif target == "health":
        forced = str(os.environ.get("KOMMZ_XTTS_HEALTH_URL", "") or "").strip()
    if forced:
        _push(forced)

    for base in _build_kommz_modal_base_candidates(base_url or _resolve_kommz_voice_endpoint()):
        _push(_derive_modal_endpoint(base, target), base)
    return out


def _remember_working_kommz_base(working_base: str):
    """Mémorise automatiquement une base Modal valide si la config pointe vers un worker périmé."""
    try:
        base = (working_base or "").strip()
        if not base:
            return
        if not base.lower().startswith(("http://", "https://")):
            base = "https://" + base
        base = base.rstrip("/")
        current = _resolve_kommz_voice_endpoint().rstrip("/")
        if not base or base == current:
            return
        AUDIO_CONFIG["kommz_api_url"] = base
        save_settings()
        stealth_print(f"✅ URL Modal corrigée automatiquement: {base}")
    except Exception:
        pass


def _derive_modal_endpoint(base_url: str, target: str) -> str:
    """
    Déduit les endpoints Modal warmup/health depuis un endpoint clone/generate.
    Couvre:
      - Function URL: https://xxx--app-clone.modal.run
      - Path URL:     https://xxx.modal.run/clone
    """
    target = (target or "").strip().lower()
    url = (base_url or "").strip()
    if not url:
        return ""
    try:
        sp = urlsplit(url)
        host = (sp.netloc or "").strip()
        path = (sp.path or "").rstrip("/")
        if host.endswith(".modal.run"):
            for src in ("-clone.modal.run", "-generate.modal.run", "-warmup.modal.run", "-health.modal.run"):
                if host.endswith(src):
                    host = host[: -len(src)] + f"-{target}.modal.run"
                    return urlunsplit((sp.scheme or "https", host, "", "", ""))
        if path.endswith("/clone"):
            path = path[:-6] + f"/{target}"
        elif path.endswith("/generate"):
            path = path[:-9] + f"/{target}"
        elif path.endswith("/warmup") or path.endswith("/health"):
            path = path.rsplit("/", 1)[0] + f"/{target}"
        else:
            path = (path + f"/{target}").replace("//", "/")
        return urlunsplit((sp.scheme or "https", sp.netloc, path, "", ""))
    except Exception:
        return f"{url.rstrip('/')}/{target}"

def _resolve_kommz_voice_endpoint() -> str:
    """
    Priorité endpoint XTTS:
      1) settings.json -> AUDIO_CONFIG['kommz_api_url']
      2) env KOMMZ_XTTS_GENERATE_URL
      3) default embarqué
    """
    cfg_url = ""
    try:
        cfg_url = str(AUDIO_CONFIG.get("kommz_api_url", "") or "").strip()
    except Exception:
        cfg_url = ""

    env_url = str(os.environ.get("KOMMZ_XTTS_GENERATE_URL", "") or "").strip()
    chosen = cfg_url or env_url or DEFAULT_KOMMZ_VOICE_ENDPOINT
    if chosen and not chosen.lower().startswith(("http://", "https://")):
        chosen = "https://" + chosen
    return chosen.strip()


def _resolve_kommz_synthesis_base() -> str:
    """
    Base URL pour endpoint API voice_id (/v1/synthesis).
    Priorité:
      1) settings.json -> AUDIO_CONFIG['kommz_synthesis_url']
      2) env KOMMZ_SYNTHESIS_URL
      3) fallback sur kommz_api_url uniquement si ce n'est pas un domaine modal.run
    """
    cfg_url = str(AUDIO_CONFIG.get("kommz_synthesis_url", "") or "").strip()
    env_url = str(os.environ.get("KOMMZ_SYNTHESIS_URL", "") or "").strip()
    chosen = cfg_url or env_url
    if not chosen:
        base = _resolve_kommz_voice_endpoint()
        # Evite de cibler les workers Modal clone qui n'exposent pas /v1/synthesis.
        if "modal.run" in base.lower():
            return ""
        chosen = base
    if chosen and not chosen.lower().startswith(("http://", "https://")):
        chosen = "https://" + chosen
    return chosen.strip()

def _resolve_kommz_aux_endpoint(target: str) -> str:
    target = (target or "").strip().lower()
    if target == "warmup":
        forced = str(os.environ.get("KOMMZ_XTTS_WARMUP_URL", "") or "").strip()
        return forced or _derive_modal_endpoint(_resolve_kommz_voice_endpoint(), "warmup")
    if target == "health":
        forced = str(os.environ.get("KOMMZ_XTTS_HEALTH_URL", "") or "").strip()
        return forced or _derive_modal_endpoint(_resolve_kommz_voice_endpoint(), "health")
    return _derive_modal_endpoint(_resolve_kommz_voice_endpoint(), target)

def _build_kommz_generate_candidates(base_url: str):
    """
    Construit une liste d'URLs de génération à tester.
    Utile quand la build EXE pointe vers un mauvais path worker Modal.
    """
    out = []
    seen = set()

    def _push(url):
        u = (url or "").strip()
        if not u:
            return
        if not u.lower().startswith(("http://", "https://")):
            u = "https://" + u
        u = u.rstrip("/")
        if u and u not in seen:
            seen.add(u)
            out.append(u)

    for b in _build_kommz_modal_base_candidates(base_url):
        try:
            sp = urlsplit(b)
            base = urlunsplit((sp.scheme or "https", sp.netloc, "", "", "")).rstrip("/")
            path = (sp.path or "").rstrip("/")

            _push(b)
            # Variantes path (fréquentes selon déploiement worker/app).
            if not path:
                _push(base + "/diamond-generate")
                _push(base + "/generate")
            else:
                if not path.endswith("/diamond-generate"):
                    _push(base + "/diamond-generate")
                if not path.endswith("/generate"):
                    _push(base + "/generate")
                # Aussi tenter la racine si la config a un path erroné.
                _push(base)
        except Exception:
            continue
    return out


def _build_kommz_synthesis_candidates(base_url: str):
    """
    Construit les endpoints API pour forcer une voix via voice_id.
    Priorité: /v1/synthesis sur la racine du domaine.
    """
    out = []
    seen = set()

    def _push(url):
        u = (url or "").strip()
        if not u:
            return
        if not u.lower().startswith(("http://", "https://")):
            u = "https://" + u
        u = u.rstrip("/")
        if u and u not in seen:
            seen.add(u)
            out.append(u)

    b = (base_url or "").strip()
    if not b:
        return out
    if not b.lower().startswith(("http://", "https://")):
        b = "https://" + b

    _push(b)
    try:
        sp = urlsplit(b)
        root = urlunsplit((sp.scheme or "https", sp.netloc, "", "", "")).rstrip("/")
        _push(root + "/v1/synthesis")
        _push(root + "/api/v1/synthesis")
    except Exception:
        pass
    return out


def _resolve_kommz_whisper_endpoint() -> str:
    cfg_url = ""
    try:
        cfg_url = str(AUDIO_CONFIG.get("whisper_api_url", "") or "").strip()
    except Exception:
        cfg_url = ""

    env_url = str(
        os.environ.get("KOMMZ_WHISPER_URL", "")
        or os.environ.get("KOMMZ_DEFAULT_WHISPER_URL", "")
        or ""
    ).strip()
    chosen = cfg_url or env_url or DEFAULT_KOMMZ_WHISPER_URL
    if chosen and not chosen.lower().startswith(("http://", "https://")):
        chosen = "https://" + chosen
    return chosen.strip().rstrip("/")


def _build_kommz_whisper_candidates(base_url: str):
    out = []
    seen = set()

    def _push(url):
        u = (url or "").strip()
        if not u:
            return
        if not u.lower().startswith(("http://", "https://")):
            u = "https://" + u
        u = u.rstrip("/")
        if u and u not in seen:
            seen.add(u)
            out.append(u)

    b = (base_url or "").strip()
    if not b:
        return out
    if not b.lower().startswith(("http://", "https://")):
        b = "https://" + b

    _push(b)
    try:
        sp = urlsplit(b)
        root = urlunsplit((sp.scheme or "https", sp.netloc, "", "", "")).rstrip("/")
        host = (sp.netloc or "").strip()
        path = (sp.path or "").rstrip("/")

        if host.endswith("-health.modal.run"):
            transcribe_host = host[: -len("-health.modal.run")] + "-transcribe.modal.run"
            transcribe_root = urlunsplit((sp.scheme or "https", transcribe_host, "", "", "")).rstrip("/")
            _push(transcribe_root)
            _push(transcribe_root + "/transcribe")

        if host.endswith("-transcribe.modal.run"):
            _push(root + "/transcribe")
        else:
            if not path:
                _push(root + "/transcribe")
            else:
                if not path.endswith("/transcribe"):
                    _push(root + "/transcribe")
                _push(root)
    except Exception:
        pass

    return out


def _remember_working_kommz_whisper_url(working_url: str):
    try:
        url = (working_url or "").strip()
        if not url:
            return
        if not url.lower().startswith(("http://", "https://")):
            url = "https://" + url
        url = url.rstrip("/")
        current = _resolve_kommz_whisper_endpoint().rstrip("/")
        if not url or url == current:
            return
        AUDIO_CONFIG["whisper_api_url"] = url
        save_settings()
        stealth_print(f"✅ URL Whisper corrigée automatiquement: {url}")
    except Exception:
        pass


def _to_bool(value, default=False):
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    s = str(value).strip().lower()
    if s in {"1", "true", "yes", "on"}:
        return True
    if s in {"0", "false", "no", "off"}:
        return False
    return default


HYBRID_SUPPORTED_TARGET_LANGS = {"fr", "en", "ja", "ko", "zh"}
XTTS_SUPPORTED_REQUEST_LANGS = {
    "en", "es", "fr", "de", "it", "pt", "pl", "tr", "ru", "nl", "cs", "ar", "zh-cn", "hu", "ko", "ja", "hi"
}
XTTS_LANGUAGE_FALLBACKS = {
    "zh": "zh-cn",
    "zh-tw": "zh-cn",
    "kk": "ru",
    "uk": "ru",
    "bg": "ru",
    "sr": "ru",
    "mk": "ru",
    "be": "ru",
}


def _normalize_hybrid_target_lang(lang_value) -> str:
    txt = str(lang_value or "").strip().lower().replace("_", "-")
    if not txt:
        return ""
    if txt.startswith("zh"):
        return "zh"
    return txt.split("-", 1)[0]


def _is_hybrid_supported_target_lang(lang_value) -> bool:
    return _normalize_hybrid_target_lang(lang_value) in HYBRID_SUPPORTED_TARGET_LANGS


def _get_hybrid_supported_langs_label() -> str:
    return "FR, EN, JA, KO, ZH"


def _normalize_xtts_request_lang(lang_value, text: str = "") -> str:
    txt = str(lang_value or "").strip().lower().replace("_", "-")
    if not txt:
        return "fr"
    if txt in XTTS_SUPPORTED_REQUEST_LANGS:
        return txt
    if txt in XTTS_LANGUAGE_FALLBACKS:
        return XTTS_LANGUAGE_FALLBACKS[txt]

    short = txt.split("-", 1)[0]
    if short in XTTS_SUPPORTED_REQUEST_LANGS:
        return short
    if short in XTTS_LANGUAGE_FALLBACKS:
        return XTTS_LANGUAGE_FALLBACKS[short]
    if short == "zh":
        return "zh-cn"

    sample = str(text or "")
    if re.search(r"[\u0600-\u06FF]", sample):
        return "ar"
    if re.search(r"[\u0900-\u097F]", sample):
        return "hi"
    if re.search(r"[\uAC00-\uD7AF]", sample):
        return "ko"
    if re.search(r"[\u3040-\u30FF]", sample):
        return "ja"
    if re.search(r"[\u4E00-\u9FFF]", sample):
        return "zh-cn"
    if re.search(r"[\u0400-\u04FF]", sample):
        return "ru"
    return "en"


def _get_hybrid_fr_config_status():
    gpt_base = str(AUDIO_CONFIG.get("gpt_api_url", "") or "").strip().rstrip("/")
    ref_path = str(AUDIO_CONFIG.get("gpt_ref_audio_path", "") or "").strip()
    prompt_text = str(AUDIO_CONFIG.get("gpt_prompt_text", "") or "").strip()
    style_text = str(AUDIO_CONFIG.get("gpt_style_text", "") or "").strip()
    enabled = bool(_to_bool(AUDIO_CONFIG.get("gpt_style_to_xtts_fr", False), False))
    ref_exists = bool(ref_path and os.path.exists(ref_path))
    issues = []
    if not gpt_base:
        issues.append("API GPT absente")
    if not ref_path:
        issues.append("référence absente")
    elif not ref_exists:
        issues.append("référence introuvable")
    if not prompt_text:
        issues.append("prompt absent")

    ready = len(issues) == 0
    ref_name = os.path.basename(ref_path) if ref_path else ""
    supported_label = _get_hybrid_supported_langs_label()
    if ready:
        message = f"Hybrid prêt ({supported_label})"
    elif issues:
        message = "Hybrid incomplet: " + ", ".join(issues[:2])
    else:
        message = "Hybrid non configuré"

    return {
        "enabled": enabled,
        "ready": ready,
        "message": message,
        "ref_name": ref_name,
        "has_style_text": bool(style_text),
        "api_url": gpt_base,
        "ref_path": ref_path,
        "ref_exists": ref_exists,
    }


def _maybe_enable_hybrid_fr_default():
    target_lang_value = AUDIO_CONFIG.get("target_lang") or CURRENT_TARGET_LANG
    if not _is_hybrid_supported_target_lang(target_lang_value):
        return False

    status = _get_hybrid_fr_config_status()
    if not status.get("ready") or status.get("enabled"):
        return False

    AUDIO_CONFIG["gpt_style_to_xtts_fr"] = True
    return True


def _gpt_style_to_xtts_ref_bytes(text: str, fast_mode: bool = False) -> bytes:
    """
    Génère un WAV de style via GPT-SoVITS (api_v2 /tts), à utiliser
    comme speaker_wav pour XTTS en mode hybride.
    """
    gpt_base = str(AUDIO_CONFIG.get("gpt_api_url", "") or "").strip().rstrip("/")
    ref_path = str(AUDIO_CONFIG.get("gpt_ref_audio_path", "") or "").strip()
    prompt_text = str(AUDIO_CONFIG.get("gpt_prompt_text", "") or "").strip()
    prompt_lang = str(AUDIO_CONFIG.get("gpt_prompt_lang", "ja") or "ja").strip().lower()
    style_text = str(AUDIO_CONFIG.get("gpt_style_text", "") or "").strip()
    style_lang = str(AUDIO_CONFIG.get("gpt_style_text_lang", "ja") or "ja").strip().lower()
    if not style_text:
        style_text = (text or "").strip()

    if not gpt_base:
        raise RuntimeError("gpt_api_url vide")
    if not ref_path or not os.path.exists(ref_path):
        raise RuntimeError("gpt_ref_audio_path invalide/introuvable")
    if not prompt_text:
        raise RuntimeError("gpt_prompt_text manquant")
    if not style_text:
        raise RuntimeError("gpt_style_text manquant")

    lowered = gpt_base.lower()
    is_local_api = lowered.startswith("http://127.0.0.1") or lowered.startswith("https://127.0.0.1") or lowered.startswith("http://localhost") or lowered.startswith("https://localhost")
    engine_label = "GPT-SoVITS Local" if is_local_api else "GPT-SoVITS Modal"
    if gpt_base.endswith("/tts") or gpt_base.endswith("/api/gptsovits/style") or lowered.endswith("-tts.modal.run"):
        url = gpt_base
    else:
        url = f"{gpt_base}/tts"

    def _post_once(timeout_value):
        if is_local_api:
            payload = {
                "text": style_text,
                "text_lang": style_lang,
                "ref_audio_path": ref_path.replace("\\", "/"),
                "prompt_lang": prompt_lang,
                "prompt_text": prompt_text,
                "media_type": "wav",
                "streaming_mode": False,
            }
            return _HTTP.post(url, json=payload, timeout=timeout_value)

        with open(ref_path, "rb") as f:
            files = {
                "ref_audio": (os.path.basename(ref_path), f, "audio/wav"),
            }
            data = {
                "text": style_text,
                "text_lang": style_lang,
                "prompt_lang": prompt_lang,
                "prompt_text": prompt_text,
                "style_text": style_text,
                "media_type": "wav",
            }
            return _HTTP.post(url, data=data, files=files, timeout=timeout_value)

    if is_local_api:
        req_timeout = (2.5, 14) if fast_mode else 180
        retry_timeout = 35 if fast_mode else req_timeout
    else:
        req_timeout = (3, 18) if fast_mode else 300
        retry_timeout = (4, 45) if fast_mode else req_timeout

    try:
        r = _post_once(req_timeout)
    except requests.exceptions.Timeout as timeout_err:
        if not fast_mode:
            raise
        stealth_print(f"⏳ Hybrid GPT timeout rapide, retry étendu: {timeout_err}")
        _push_quality_log("warn", "hybrid_gpt_retry", "Retry Hybrid après timeout rapide", str(timeout_err))
        r = _post_once(retry_timeout)
    except requests.exceptions.RequestException as req_err:
        if not fast_mode:
            raise
        stealth_print(f"⚠️ Hybrid GPT erreur réseau rapide, retry étendu: {req_err}")
        _push_quality_log("warn", "hybrid_gpt_retry", "Retry Hybrid après erreur réseau", str(req_err))
        r = _post_once(retry_timeout)
    if not r.ok:
        body = (r.text or "")[:280]
        raise RuntimeError(f"GPT /tts HTTP {r.status_code}: {body}")

    ctype = (r.headers.get("Content-Type") or "").lower()
    if "audio/" in ctype:
        _set_pipeline_runtime(
            hybrid_engine=engine_label,
            hybrid_detail=f"Référence style prête · {style_lang.upper()}",
        )
        return r.content

    try:
        j = r.json()
    except Exception:
        j = {}
    wav_path = str(j.get("path") or j.get("audio_path") or "").strip()
    if wav_path and os.path.exists(wav_path):
        _set_pipeline_runtime(
            hybrid_engine=engine_label,
            hybrid_detail=f"Référence style prête · {style_lang.upper()}",
        )
        with open(wav_path, "rb") as f:
            return f.read()
    raise RuntimeError("GPT /tts n'a pas renvoyé d'audio exploitable")


def _get_hybrid_rts_preset() -> str:
    preset = str(AUDIO_CONFIG.get("hybrid_rts_preset", "fast") or "fast").strip().lower()
    if preset not in {"fast", "quality"}:
        preset = "fast"
    # Compat ancien booléen.
    if preset == "fast" and not _to_bool(AUDIO_CONFIG.get("hybrid_fast_rts", True), True):
        preset = "quality"
    return preset


def _transcribe_via_modal_whisper(buffer_data: bytes, user_multilang: bool = True):
    whisper_base = _resolve_kommz_whisper_endpoint()
    if not whisper_base:
        raise RuntimeError("whisper_api_url vide")

    whisper_model = str(
        AUDIO_CONFIG.get("whisper_model", DEFAULT_KOMMZ_WHISPER_MODEL)
        or DEFAULT_KOMMZ_WHISPER_MODEL
    ).strip().lower()
    if whisper_model == "large":
        whisper_model = "large-v3"
    if whisper_model not in {"small", "large-v3"}:
        whisper_model = DEFAULT_KOMMZ_WHISPER_MODEL

    candidate_urls = _build_kommz_whisper_candidates(whisper_base)
    if not candidate_urls:
        raise RuntimeError("aucune URL Whisper Modal candidate")

    last_err = ""
    for idx, url in enumerate(candidate_urls, start=1):
        try:
            files = {
                "audio": ("audio.wav", buffer_data, "audio/wav"),
            }
            data = {"model": whisper_model}
            stealth_print(f"🎤 Whisper Modal -> {url} ({idx}/{len(candidate_urls)})")
            turbo_mode = _is_turbo_mode_active()
            timeout_cfg = (3, 12) if turbo_mode else (6, 45)
            r = requests.post(url, files=files, data=data, timeout=timeout_cfg)
            if r.ok:
                payload = r.json() if r.content else {}
                transcript = str(payload.get("text") or payload.get("transcript") or "").strip()
                detected = str(payload.get("language") or "fr").strip().lower()
                if "-" in detected:
                    detected = detected.split("-", 1)[0]
                if not user_multilang:
                    detected = "fr"
                if not detected:
                    detected = "fr"
                if not transcript:
                    last_err = "transcription vide"
                    continue
                transcript = clean_gaming_text(transcript)
                transcript = _reinforce_laugh_transcript(transcript)
                _set_pipeline_runtime(
                    stt_engine="Whisper Modal",
                    stt_detail=f"{whisper_model} · langue détectée {detected.upper()}",
                )
                if url != whisper_base:
                    _remember_working_kommz_whisper_url(url)
                return transcript, detected
            body = ""
            try:
                body = (r.text or "").strip().replace("\n", " ")[:220]
            except Exception:
                body = ""
            last_err = f"HTTP {r.status_code} {body}".strip()
        except Exception as e:
            last_err = str(e)

    raise RuntimeError(last_err or "Whisper Modal indisponible")


def _transcribe_ref_via_modal_whisper(ref_path: str, lang_hint: str = "ja"):
    whisper_base = _resolve_kommz_whisper_endpoint()
    if not whisper_base:
        raise RuntimeError("whisper_api_url vide")

    ref_name = os.path.basename(str(ref_path or "").strip()) or "reference.wav"
    with open(ref_path, "rb") as f:
        ref_bytes = f.read()

    whisper_model = str(
        AUDIO_CONFIG.get("whisper_model", DEFAULT_KOMMZ_WHISPER_MODEL)
        or DEFAULT_KOMMZ_WHISPER_MODEL
    ).strip().lower()
    if whisper_model == "large":
        whisper_model = "large-v3"
    if whisper_model not in {"small", "large-v3"}:
        whisper_model = DEFAULT_KOMMZ_WHISPER_MODEL

    candidate_urls = _build_kommz_whisper_candidates(whisper_base)
    if not candidate_urls:
        raise RuntimeError("aucune URL Whisper Modal candidate")

    lang_hint = str(lang_hint or "").strip().lower()
    if "-" in lang_hint:
        lang_hint = lang_hint.split("-", 1)[0]

    last_err = ""
    for idx, url in enumerate(candidate_urls, start=1):
        try:
            files = {
                "audio": (ref_name, ref_bytes, "application/octet-stream"),
            }
            data = {"model": whisper_model}
            if lang_hint:
                data["language"] = lang_hint
            stealth_print(f"🧠 Auto prompt Whisper Modal -> {url} ({idx}/{len(candidate_urls)})")
            r = requests.post(url, files=files, data=data, timeout=(6, 180))
            if r.ok:
                payload = r.json() if r.content else {}
                transcript = str(payload.get("text") or payload.get("transcript") or "").strip()
                detected = str(payload.get("language") or lang_hint or "").strip().lower()
                if "-" in detected:
                    detected = detected.split("-", 1)[0]
                if not transcript:
                    last_err = "transcription vide"
                    continue
                if url != whisper_base:
                    _remember_working_kommz_whisper_url(url)
                return transcript, (detected or lang_hint or "ja"), url
            body = ""
            try:
                body = (r.text or "").strip().replace("\n", " ")[:220]
            except Exception:
                body = ""
            last_err = f"HTTP {r.status_code} {body}".strip()
        except Exception as e:
            last_err = str(e)

    raise RuntimeError(last_err or "Whisper Modal indisponible")


def _norm_path_for_match(p: str) -> str:
    raw = str(p or "").strip().replace("\\", "/")
    if not raw:
        return ""
    try:
        return os.path.abspath(raw).replace("\\", "/").lower()
    except Exception:
        return raw.lower()


def _find_list_text_for_ref(ref_path: str):
    """
    Cherche la transcription correspondante dans des fichiers .list existants.
    Retour: (text, lang, source_list_path) ou (None, None, None)
    """
    ref_norm = _norm_path_for_match(ref_path)
    ref_base = os.path.basename(ref_path or "").lower()
    if not ref_norm and not ref_base:
        return None, None, None

    candidate_dirs = [
        Path.cwd() / "FINE_TUNE" / "transcripts",
        Path.home() / "Desktop" / "GPT-SoVITS-v2pro" / "FINE_TUNE" / "transcripts",
    ]
    try:
        rp = Path(ref_path)
        candidate_dirs.append(rp.parent)
        candidate_dirs.append(rp.parent.parent / "transcripts")
    except Exception:
        pass

    seen = set()
    for d in candidate_dirs:
        try:
            dd = Path(d).resolve()
        except Exception:
            dd = Path(d)
        k = str(dd).lower()
        if k in seen:
            continue
        seen.add(k)
        if not dd.exists() or not dd.is_dir():
            continue
        for lf in dd.glob("*.list"):
            try:
                with open(lf, "r", encoding="utf-8", errors="ignore") as f:
                    lines = f.read().splitlines()
            except Exception:
                continue
            exact_hit = None
            base_hit = None
            for ln in lines:
                parts = ln.split("|", 3)
                if len(parts) < 4:
                    continue
                pth = parts[0].strip()
                lng = parts[2].strip().lower()
                txt = parts[3].strip()
                txt_u = txt.upper()
                if (not txt) or txt_u.startswith("TODO_") or txt_u == "TODO_TRANSCRIPTION_EXACTE":
                    continue
                p_norm = _norm_path_for_match(pth)
                p_base = os.path.basename(pth).lower()
                if ref_norm and p_norm == ref_norm:
                    exact_hit = (txt, lng, str(lf))
                    break
                if (not base_hit) and ref_base and p_base == ref_base:
                    base_hit = (txt, lng, str(lf))
            if exact_hit:
                return exact_hit
            if base_hit:
                return base_hit
    return None, None, None


def _find_gptsovits_root(ref_path: str):
    cands = [
        Path.home() / "Desktop" / "GPT-SoVITS-v2pro",
        Path.home() / "Desktop" / "GPT-SoVITS-main",
    ]
    try:
        rp = Path(ref_path).resolve()
        for p in [rp.parent, *rp.parents]:
            cands.append(p)
    except Exception:
        pass
    for c in cands:
        try:
            if (c / "tools" / "asr" / "fasterwhisper_asr.py").exists() and (c / "runtime" / "python.exe").exists():
                return c
        except Exception:
            pass
    return None


def _run_whisper_for_ref(ref_path: str, lang_hint: str = "ja"):
    """
    Lance fasterwhisper_asr sur le dossier du ref_path et retourne (text, lang).
    """
    root = _find_gptsovits_root(ref_path)
    if not root:
        raise RuntimeError("GPT-SoVITS root introuvable")
    ref = Path(ref_path)
    if not ref.exists():
        raise RuntimeError("Référence audio introuvable")

    asr_script = root / "tools" / "asr" / "fasterwhisper_asr.py"
    py = root / "runtime" / "python.exe"
    out_dir = root / "FINE_TUNE" / "transcripts"
    out_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        str(py),
        str(asr_script),
        "-i", str(ref.parent),
        "-o", str(out_dir),
        "-s", "large-v3",
        "-l", (lang_hint or "ja").lower(),
        "-p", "int8",
    ]
    subprocess.run(cmd, cwd=str(root), check=True, timeout=900)

    list_path = out_dir / f"{ref.parent.name}.list"
    if not list_path.exists():
        raise RuntimeError(f"Fichier ASR introuvable: {list_path}")
    with open(list_path, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.read().splitlines()
    ref_norm = _norm_path_for_match(str(ref))
    ref_base = ref.name.lower()
    for ln in lines:
        parts = ln.split("|", 3)
        if len(parts) < 4:
            continue
        pth = parts[0].strip()
        lng = parts[2].strip().lower()
        txt = parts[3].strip()
        if not txt:
            continue
        if _norm_path_for_match(pth) == ref_norm or os.path.basename(pth).lower() == ref_base:
            return txt, lng
    raise RuntimeError("Transcription Whisper introuvable pour ce fichier")

KOMMZ_XTTS_WARMUP_URL = os.environ.get("KOMMZ_XTTS_WARMUP_URL", "").strip() or _derive_modal_endpoint(DEFAULT_KOMMZ_VOICE_ENDPOINT, "warmup")
KOMMZ_XTTS_HEALTH_URL = os.environ.get("KOMMZ_XTTS_HEALTH_URL", "").strip() or _derive_modal_endpoint(DEFAULT_KOMMZ_VOICE_ENDPOINT, "health")
KOMMZ_XTTS_WARMUP_COOLDOWN = int(os.environ.get("KOMMZ_XTTS_WARMUP_COOLDOWN", "90"))
_last_xtts_warmup_ts = 0.0
_last_xtts_activity_ts = 0.0
_xtts_warmup_lock = threading.Lock()
_xtts_runtime_cache = {
    "state": "unknown",   # ready | cold | offline | unknown
    "message": "Vérification en cours...",
    "checked_at": 0.0,
}
_cloud_diag_cache = {
    "checked_at": 0.0,
    "summary": "Diagnostic cloud en attente",
    "items": [],
}
# Cache court pour éviter de régénérer la référence Hybrid à chaque phrase RTS.
_hybrid_style_ref_cache = {
    "bytes": None,
    "lang": "",
    "key": "",
    "ts": 0.0,
}


def prewarm_kommz_xtts(force=False, timeout_connect=3, timeout_read=20):
    """Réveille le worker XTTS en arrière-plan pour réduire le cold start."""
    global _last_xtts_warmup_ts, _last_xtts_activity_ts
    now = time.time()
    if not force and (now - _last_xtts_warmup_ts) < KOMMZ_XTTS_WARMUP_COOLDOWN:
        return

    def _run():
        global _last_xtts_warmup_ts
        try:
            with _xtts_warmup_lock:
                now2 = time.time()
                if not force and (now2 - _last_xtts_warmup_ts) < KOMMZ_XTTS_WARMUP_COOLDOWN:
                    return
                ok = False
                for candidate in _build_kommz_aux_candidates("warmup"):
                    warmup_url = candidate["url"]
                    try:
                        r = requests.post(
                            warmup_url,
                            timeout=(timeout_connect, timeout_read),
                        )
                        ok = r.ok
                    except Exception:
                        ok = False

                    if not ok:
                        try:
                            r = requests.get(warmup_url, timeout=(timeout_connect, 10))
                            ok = bool(getattr(r, "ok", False))
                        except Exception:
                            ok = False

                    if ok:
                        _remember_working_kommz_base(candidate.get("base_url", ""))
                        break
                _last_xtts_warmup_ts = time.time()
                _last_xtts_activity_ts = _last_xtts_warmup_ts
        except Exception:
            pass

    threading.Thread(target=_run, daemon=True).start()


def get_kommz_xtts_runtime_status(force=False, cache_ttl=20):
    """Etat runtime du serveur XTTS pour l'UI desktop."""
    now = time.time()
    if (
        not force
        and _xtts_runtime_cache.get("checked_at")
        and (now - float(_xtts_runtime_cache.get("checked_at", 0))) < cache_ttl
    ):
        return dict(_xtts_runtime_cache)

    state = "offline"
    message = "Serveur clonage: hors ligne"
    last_err = ""
    try:
        for candidate in _build_kommz_aux_candidates("health"):
            health_url = candidate["url"]
            try:
                r = requests.get(health_url, timeout=(2.5, 6))
                if not r.ok:
                    last_err = f"HTTP {r.status_code}"
                    if r.status_code in (400, 404, 405):
                        continue
                    break
                _remember_working_kommz_base(candidate.get("base_url", ""))
                # On considère "cold" si pas d'activité récente côté desktop.
                idle_for = now - max(_last_xtts_activity_ts, _last_xtts_warmup_ts, 0.0)
                if idle_for > (KOMMZ_XTTS_WARMUP_COOLDOWN * 1.5):
                    state = "cold"
                    message = "Serveur clonage: en veille (première génération plus lente)"
                else:
                    state = "ready"
                    message = "Serveur clonage: en ligne"
                break
            except Exception as ex:
                last_err = str(ex)
                continue
    except Exception:
        pass

    _xtts_runtime_cache["state"] = state
    _xtts_runtime_cache["message"] = message if state != "offline" else "Serveur clonage: hors ligne"
    _xtts_runtime_cache["checked_at"] = now
    return dict(_xtts_runtime_cache)


def _probe_cloud_endpoint(url: str, method: str = "GET", timeout=(2.5, 6)):
    endpoint = _short_runtime_url(url or "", 120)
    out = {
        "endpoint": endpoint,
        "ok": False,
        "http_status": 0,
        "latency_ms": -1,
        "detail": "",
    }
    raw = str(url or "").strip()
    if not raw:
        out["detail"] = "URL vide"
        return out
    start = time.time()
    try:
        if str(method or "GET").upper() == "OPTIONS":
            r = _HTTP.options(raw, timeout=timeout)
        else:
            r = _HTTP.get(raw, timeout=timeout)
        out["http_status"] = int(getattr(r, "status_code", 0) or 0)
        out["latency_ms"] = int(max(0.0, (time.time() - start) * 1000))
        status = out["http_status"]
        out["ok"] = 200 <= status < 500
        out["detail"] = f"HTTP {status}" if status else "Réponse vide"
    except Exception as ex:
        out["latency_ms"] = int(max(0.0, (time.time() - start) * 1000))
        out["detail"] = _short_runtime_text(str(ex), 160)
    return out


def get_cloud_endpoints_diag(force=False, cache_ttl=25):
    now = time.time()
    if (
        not force
        and _cloud_diag_cache.get("checked_at")
        and (now - float(_cloud_diag_cache.get("checked_at", 0.0))) < cache_ttl
    ):
        return dict(_cloud_diag_cache)

    items = []

    whisper_base = _resolve_kommz_whisper_endpoint()
    whisper_url = ""
    for cand in _build_kommz_whisper_candidates(whisper_base):
        whisper_url = cand
        break
    items.append({
        "name": "Whisper",
        **_probe_cloud_endpoint(whisper_url, "GET", timeout=(2.5, 6)),
    })

    xtts_health = ""
    for cand in _build_kommz_aux_candidates("health"):
        xtts_health = str(cand.get("url") or "").strip()
        if xtts_health:
            break
    items.append({
        "name": "XTTS health",
        **_probe_cloud_endpoint(xtts_health, "GET", timeout=(2.5, 6)),
    })

    gpt_url = str(AUDIO_CONFIG.get("gpt_api_url", "") or "").strip()
    items.append({
        "name": "GPT-SoVITS",
        **_probe_cloud_endpoint(gpt_url, "GET", timeout=(2.5, 6)),
    })

    synth_url = ""
    for cand in _build_kommz_synthesis_candidates(_resolve_kommz_synthesis_base()):
        if "/v1/synthesis" in cand or "/api/v1/synthesis" in cand:
            synth_url = cand
            break
        if not synth_url:
            synth_url = cand
    synth_probe = _probe_cloud_endpoint(synth_url, "OPTIONS", timeout=(2.5, 6))
    if (not synth_probe.get("ok")) and synth_url:
        synth_probe = _probe_cloud_endpoint(synth_url, "GET", timeout=(2.5, 6))
    items.append({
        "name": "Voice API",
        **synth_probe,
    })

    ok_count = sum(1 for it in items if it.get("ok"))
    total = len(items)
    summary = f"{ok_count}/{total} endpoints joignables"
    if ok_count == 0:
        summary = "0 endpoint joignable (vérifier URLs Modal / cloud)"
    elif ok_count < total:
        summary = f"{ok_count}/{total} endpoints joignables (fallback probable)"
    else:
        summary = "Tous les endpoints cloud répondent"

    _cloud_diag_cache["checked_at"] = now
    _cloud_diag_cache["summary"] = summary
    _cloud_diag_cache["items"] = items
    return dict(_cloud_diag_cache)


def _get_xtts_warmup_retry_after_seconds(now_ts: float | None = None) -> int:
    try:
        now = float(now_ts if now_ts is not None else time.time())
    except Exception:
        now = time.time()
    try:
        last = float(_last_xtts_warmup_ts or 0.0)
    except Exception:
        last = 0.0
    wait = (last + float(KOMMZ_XTTS_WARMUP_COOLDOWN)) - now
    if wait <= 0:
        return 0
    try:
        return int(wait + 0.999)
    except Exception:
        return 1

def get_base_paths():
    is_compiled = "__compiled__" in globals() or getattr(sys, 'frozen', False)
    if is_compiled:
        return Path(os.path.dirname(__file__)).resolve(), Path(sys.argv[0]).resolve().parent
    return Path(__file__).resolve().parent, Path(__file__).resolve().parent

BASE_INTERNAL, BASE_EXTERNAL = get_base_paths()
WEB_DIR = BASE_INTERNAL / "web"
LOGS_DIR = BASE_EXTERNAL / "logs"
try: LOGS_DIR.mkdir(parents=True, exist_ok=True)
except: pass

logger = logging.getLogger("vtp_core"); logger.setLevel(logging.INFO)
file_handler = RotatingFileHandler(LOGS_DIR / "vtp_core.log", maxBytes=5000000, backupCount=3, encoding='utf-8')
file_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
logger.addHandler(file_handler)
_console_stream = sys.stdout if sys.stdout is not None else sys.__stdout__
if _console_stream is None:
    _console_stream = open(os.devnull, "w", encoding="utf-8", errors="ignore")
stream_handler = logging.StreamHandler(_console_stream)
stream_handler.setFormatter(logging.Formatter('%(asctime)s %(message)s'))
logger.addHandler(stream_handler)


class _DeepgramNoiseFilter(logging.Filter):
    def filter(self, record):
        try:
            msg = str(record.getMessage() or "").lower()
        except Exception:
            msg = ""
        # Timeout d'inactivit? attendu sur les flux live: on le traite c?t? runtime,
        # inutile de polluer la console avec des erreurs r?p?titives.
        if ("dpgr.am/net0001" in msg) or ("deepgram did not receive audio data" in msg):
            return False
        return True


class QtDpiFilter(logging.Filter):
    def filter(self, record):
        try:
            message = str(record.getMessage() or "")
        except Exception:
            message = ""
        return "SetProcessDpiAwarenessContext() failed: Accès refusé" not in message


_DG_NOISE_FILTER = _DeepgramNoiseFilter()
_QT_DPI_FILTER = QtDpiFilter()
for _h in list(logger.handlers):
    try:
        _h.addFilter(_DG_NOISE_FILTER)
        _h.addFilter(_QT_DPI_FILTER)
    except Exception:
        pass
for _h in list(logging.getLogger().handlers):
    try:
        _h.addFilter(_DG_NOISE_FILTER)
        _h.addFilter(_QT_DPI_FILTER)
    except Exception:
        pass
try:
    logging.getLogger().addFilter(_QT_DPI_FILTER)
except Exception:
    pass
for _name in ("deepgram", "websockets", "urllib3"):
    try:
        _named_logger = logging.getLogger(_name)
        _named_logger.addFilter(_DG_NOISE_FILTER)
        _named_logger.addFilter(_QT_DPI_FILTER)
    except Exception:
        pass


class _StderrNoiseFilter:
    def __init__(self, stream):
        self._stream = stream
    def write(self, msg):
        try:
            txt = str(msg or "")
            low = txt.lower()
            if ("dpgr.am/net0001" in low) or ("did not receive audio data" in low):
                return len(txt)
            if "setprocessdpiawarenesscontext() failed: accès refusé" in low:
                return len(txt)
        except Exception:
            pass
        try:
            target = self._stream if self._stream is not None else sys.__stderr__
            if target is None:
                return len(str(msg or ""))
            return target.write(msg)
        except Exception:
            return len(str(msg or ""))
    def flush(self):
        try:
            target = self._stream if self._stream is not None else sys.__stderr__
            if target is None:
                return None
            return target.flush()
        except Exception:
            return None

if str(os.environ.get("KOMMZ_FILTER_NET0001", "1")).strip() not in ("0", "false", "False"):
    try:
        sys.stderr = _StderrNoiseFilter(sys.stderr if sys.stderr is not None else sys.__stderr__)
    except Exception:
        pass

# ==================== LICENSE ====================

CURRENT_TARGET_LANG = "EN" 
USER_NATIVE_LANG = "FR"     
SHOW_MY_SUBS = False        
CURRENT_HOTKEY = "ctrl+shift" # Tu peux changer par "shift" si besoin
BYPASS_HOTKEY = "f4" 

LAST_TTS_SENTENCE = ""
_last_tts_end_time = 0 

import threading # (Déjà présent normalement)
# --------------------

app_state = {
    "is_active": True, 
    "last_text": "Système prêt.", 
    "available_voices": VOICES_LIBRARY, 
    "current_voice_id": "DEFAULT_USER_VOICE", 
    "premium_unlocked": False,
    "gender": "MALE", 
    "target_lang": "EN", 
    "windows_voice_name": "" 
}
app_state = _repair_payload_strings(app_state)


subs_buffer = []
transcription_queue = queue.Queue(maxsize=3)
USER_PIPELINE_QUEUE = queue.PriorityQueue(maxsize=8)
_user_pipeline_sequence = itertools.count()
_user_pipeline_active = False
_user_pipeline_active_source = ""
last_f4_press = 0
last_subtitles = []
_ptt_lock = threading.Lock(); _ptt_chunks = []; _ptt_rec = False; _ptt_stream = None
# Pre-roll micro pour ne pas couper le debut de phrase (actif surtout en mode Turbo).
_ptt_preroll = collections.deque(maxlen=16)  # ~250-350ms selon samplerate/blocksize
_ptt_stream_device = None
_ptt_last_start_ts = 0.0
_ptt_last_stop_ts = 0.0
_listen_buffer = []; _listen_lock = threading.Lock(); _listen_stream = None
_is_speaking = False 
_last_bypass_release_time = 0 
_last_monitoring_toggle_ts = 0.0
ALL_EDGE_VOICES = [] 
_hybrid_running = False # <--- AJOUTE CETTE LIGNE OBLIGATOIREMENT
PLAYBACK_LOCK = threading.Lock()
_listen_runtime = {
    "ally_text_events": 0,
    "ally_voice_played": 0,
    "ally_voice_skipped": 0,
    "ally_voice_rate_limited": 0,
    "ally_short_merged": 0,
    "last_event_at": time.time(),  # V5.3 FIX: init à now() — évite idle_age=999999s au démarrage
    "listen_conn_state": "idle",
    "listen_conn_detail": "En attente audio",
    "listen_conn_retry_after": 0.0,
    "listen_conn_updated_at": 0.0,
    "watchdog_restarts": 0,
    "watchdog_flaps": 0,
    "watchdog_cooldown_hits": 0,
    "watchdog_last_restart_at": 0.0,
    "watchdog_last_restart_reason": "",
    "watchdog_last_tick_at": 0.0,
    "watchdog_idle_restarts": 0,
    "watchdog_last_idle_age_s": 0.0,
    "watchdog_stream_stale_restarts": 0,
    "last_audio_seen_at": 0.0,
}

# V5.3: Timeline historique des jeux détectés
_game_timeline = []
_game_timeline_history = collections.deque(maxlen=200)
_game_detect_last_fingerprint = {}
_game_detect_auto_mode = False

_listen_decisions = collections.deque(maxlen=24)  # 1=played, 0=skipped
_listen_autotune_state = {
    "level": 0,
    "ratio": 1.0,
    "last_update_at": 0.0,
}
_listen_engine_guard = threading.Lock()
_listen_engine_active = False
_listen_watchdog_last_restart_ts = 0.0
_listen_focus_auto_state = {
    "mode_effective": "balanced",
    "noise_rms_ema": 0.0,
    "crest_ema": 0.0,
    "last_switch_at": 0.0,
}


def _bump_listen_runtime(kind: str):
    try:
        if kind not in _listen_runtime:
            return
        _listen_runtime[kind] = int(_listen_runtime.get(kind, 0) or 0) + 1
        _listen_runtime["last_event_at"] = time.time()
    except Exception:
        pass


def _reset_listen_runtime_stats():
    try:
        _listen_runtime["ally_text_events"] = 0
        _listen_runtime["ally_voice_played"] = 0
        _listen_runtime["ally_voice_skipped"] = 0
        _listen_runtime["ally_voice_rate_limited"] = 0
        _listen_runtime["ally_short_merged"] = 0
        _listen_runtime["last_event_at"] = time.time()
        _listen_decisions.clear()
        _listen_autotune_state["level"] = 0
        _listen_autotune_state["ratio"] = 1.0
        _listen_autotune_state["last_update_at"] = time.time()
        _listen_runtime["listen_conn_state"] = "idle"
        _listen_runtime["listen_conn_detail"] = "En attente audio"
        _listen_runtime["listen_conn_retry_after"] = 0.0
        _listen_runtime["listen_conn_updated_at"] = time.time()
        _listen_runtime["watchdog_restarts"] = 0
        _listen_runtime["watchdog_flaps"] = 0
        _listen_runtime["watchdog_cooldown_hits"] = 0
        _listen_runtime["watchdog_last_restart_at"] = 0.0
        _listen_runtime["watchdog_last_restart_reason"] = ""
        _listen_runtime["watchdog_last_tick_at"] = time.time()
        _listen_runtime["watchdog_idle_restarts"] = 0
        _listen_runtime["watchdog_last_idle_age_s"] = 0.0
        _listen_runtime["watchdog_stream_stale_restarts"] = 0
        _listen_runtime["last_audio_seen_at"] = 0.0
    except Exception:
        pass


def _reset_listen_health_runtime():
    try:
        _listen_runtime["watchdog_restarts"] = 0
        _listen_runtime["watchdog_flaps"] = 0
        _listen_runtime["watchdog_cooldown_hits"] = 0
        _listen_runtime["watchdog_idle_restarts"] = 0
        _listen_runtime["watchdog_last_restart_at"] = 0.0
        _listen_runtime["watchdog_last_restart_reason"] = ""
        _listen_runtime["watchdog_last_idle_age_s"] = 0.0
        _listen_runtime["watchdog_last_tick_at"] = time.time()
        _listen_runtime["watchdog_stream_stale_restarts"] = 0
    except Exception:
        pass


def _set_listen_conn_state(state: str, detail: str = "", retry_after: float = 0.0):
    try:
        _listen_runtime["listen_conn_state"] = str(state or "idle")
        _listen_runtime["listen_conn_detail"] = str(detail or "")
        _listen_runtime["listen_conn_retry_after"] = float(retry_after or 0.0)
        _listen_runtime["listen_conn_updated_at"] = time.time()
    except Exception:
        pass


def _register_listen_decision(played: bool):
    try:
        _listen_decisions.append(1 if played else 0)
        if not _listen_decisions:
            return
        ratio = float(sum(_listen_decisions)) / float(len(_listen_decisions))
        level = 0
        if bool(AUDIO_CONFIG.get("ally_autotune_enabled", True)):
            if len(_listen_decisions) >= 12 and ratio < 0.35:
                level = 2
            elif len(_listen_decisions) >= 8 and ratio < 0.50:
                level = 1
        _listen_autotune_state["level"] = level
        _listen_autotune_state["ratio"] = ratio
        _listen_autotune_state["last_update_at"] = time.time()
    except Exception:
        pass


def _build_listen_health_snapshot() -> dict:
    try:
        state = str(_listen_runtime.get("listen_conn_state", "idle") or "idle").strip().lower()
        idle_restarts = int(_listen_runtime.get("watchdog_idle_restarts", 0) or 0)
        flaps = int(_listen_runtime.get("watchdog_flaps", 0) or 0)
        cooldown_hits = int(_listen_runtime.get("watchdog_cooldown_hits", 0) or 0)
        voice_played = int(_listen_runtime.get("ally_voice_played", 0) or 0)
        voice_skipped = int(_listen_runtime.get("ally_voice_skipped", 0) or 0)
        idle_age = float(_listen_runtime.get("watchdog_last_idle_age_s", 0.0) or 0.0)
        stream_age = max(0.0, time.time() - float(_listen_runtime.get("last_audio_seen_at", 0.0) or 0.0))
        stale_restarts = int(_listen_runtime.get("watchdog_stream_stale_restarts", 0) or 0)

        level = "ok"
        summary = "Écoute stable"
        if state in {"reconnecting", "restarting"}:
            level = "warn"
            summary = f"Écoute en reprise ({state})"
        if cooldown_hits >= 3 or flaps >= 3:
            level = "warn"
            summary = f"Écoute instable ({flaps} flaps, {cooldown_hits} cooldown hits)"
        if idle_restarts >= 4:
            level = "err"
            summary = f"Écoute fragile (relances idle: {idle_restarts})"
        elif idle_restarts >= 1 and level == "ok":
            level = "warn"
            summary = f"Écoute auto-réparée (relances idle: {idle_restarts})"
        if (voice_played + voice_skipped) == 0 and idle_age > 120 and state in {"connected", "waiting_audio"}:
            level = "warn"
            summary = "Aucun événement voix récent (session silencieuse)"
        if stale_restarts >= 2:
            level = "warn"
            summary = f"Écoute auto-réparée (stale stream: {stale_restarts})"
        if state == "connected" and stream_age > 90 and level == "ok":
            level = "warn"
            summary = "Flux audio inactif prolongé (surveillance active)"
        return {
            "level": level,
            "summary": summary,
            "state": state,
        }
    except Exception:
        return {
            "level": "info",
            "summary": "Santé écoute indisponible",
            "state": "unknown",
        }


# À DÉPLACER V5.5 — appelé depuis vtp_core runtime
def _restart_listen_engine(reason: str = "") -> bool:
    global DG_ENGINE, _listen_watchdog_last_restart_ts
    now = time.time()
    previous_restart_ts = float(_listen_watchdog_last_restart_ts or 0.0)
    if (now - previous_restart_ts) < 8.0:
        try:
            _listen_runtime["watchdog_cooldown_hits"] = int(_listen_runtime.get("watchdog_cooldown_hits", 0) or 0) + 1
            _listen_runtime["watchdog_last_restart_reason"] = f"cooldown:{str(reason or '').strip()[:120]}"
        except Exception:
            pass
        return False
    if not bool(AUDIO_CONFIG.get("is_listening", True)):
        return False
    try:
        _set_listen_conn_state("restarting", "Relance auto mode ecoute...", 2.0)
        _push_quality_log("warn", "listen_watchdog_restart", "Relance auto mode ecoute", reason)
        try:
            if "DG_ENGINE" in globals() and DG_ENGINE:
                DG_ENGINE.is_running = False
        except Exception:
            pass
        time.sleep(0.25)
        try:
            listen_dev_id = int(AUDIO_CONFIG.get("game_input_device", 0) or 0)
        except Exception:
            listen_dev_id = 0
        DG_ENGINE = DeepgramEngine()
        threading.Thread(target=DG_ENGINE.start_streaming, args=(listen_dev_id,), daemon=True).start()
        _listen_watchdog_last_restart_ts = time.time()
        try:
            last_restart_at = float(_listen_runtime.get("watchdog_last_restart_at", 0.0) or 0.0)
            if last_restart_at > 0.0 and (now - last_restart_at) < 25.0:
                _listen_runtime["watchdog_flaps"] = int(_listen_runtime.get("watchdog_flaps", 0) or 0) + 1
            _listen_runtime["watchdog_restarts"] = int(_listen_runtime.get("watchdog_restarts", 0) or 0) + 1
            _listen_runtime["watchdog_last_restart_at"] = now
            _listen_runtime["watchdog_last_restart_reason"] = str(reason or "").strip()[:120]
        except Exception:
            pass
        stealth_print(f"♻️ Watchdog écoute: relance effectuée ({reason})")
        _push_toast(f"♻️ Écoute relancée automatiquement")
        return True
    except Exception as e:
        stealth_print(f"⚠️ Watchdog écoute: relance impossible ({e})")
        return False


_watchdog_last_alert_at = 0.0  # V5.2: cooldown anti-spam alertes


def _watchdog_alert(reason: str = ""):
    """V5.2: Alerte watchdog configurable — son, overlay, log."""
    global _watchdog_last_alert_at
    now = time.time()
    cooldown = int(AUDIO_CONFIG.get("watchdog_alert_flap_cooldown_s", 30) or 30)
    if now - _watchdog_last_alert_at < cooldown:
        return  # cooldown anti-spam
    _watchdog_last_alert_at = now
    # Son système
    if AUDIO_CONFIG.get("watchdog_alert_sound", True):
        try:
            import winsound
            winsound.MessageBeep(0x00000010)  # MB_ICONHAND
        except Exception:
            pass
    # Toast overlay
    if AUDIO_CONFIG.get("watchdog_alert_overlay", True):
        try:
            _push_toast("⚠️ Watchdog: " + reason[:80])
        except Exception:
            pass
    # Log fichier
    if AUDIO_CONFIG.get("watchdog_alert_logfile", True):
        logger.warning("Watchdog restart — %s", reason[:120])


def listen_watchdog_loop():
    while True:
        try:
            _PERF_STOP_EVENT.wait(1.5)
            _listen_runtime["watchdog_last_tick_at"] = time.time()
            if not bool(AUDIO_CONFIG.get("is_listening", True)):
                continue
            state = str(_listen_runtime.get("listen_conn_state", "idle") or "idle").strip().lower()
            updated_at = float(_listen_runtime.get("listen_conn_updated_at", 0.0) or 0.0)
            retry_after = float(_listen_runtime.get("listen_conn_retry_after", 0.0) or 0.0)
            if updated_at <= 0:
                continue
            age = time.time() - updated_at
            now_ts = time.time()
            try:
                last_evt = float(_listen_runtime.get("last_event_at", 0.0) or 0.0)
            except Exception:
                last_evt = 0.0
            idle_age = (now_ts - last_evt) if last_evt > 0 else 999999.0
            _listen_runtime["watchdog_last_idle_age_s"] = max(0.0, float(idle_age))
            try:
                last_audio_seen_at = float(_listen_runtime.get("last_audio_seen_at", 0.0) or 0.0)
            except Exception:
                last_audio_seen_at = 0.0
            stream_age = (now_ts - last_audio_seen_at) if last_audio_seen_at > 0 else 999999.0
            if state in {"connecting", "reconnecting"}:
                threshold = max(14.0, retry_after + 8.0)
                if age > threshold:
                    reason = f"etat {state} bloque depuis {int(age)}s"
                    if _restart_listen_engine(reason):
                        _watchdog_alert(reason)
            elif state == "restarting" and age > 18.0:
                reason_restart = f"restarting bloque depuis {int(age)}s"
                if _restart_listen_engine(reason_restart):
                    _watchdog_alert(reason_restart)
            elif state == "paused" and age > 4.0:
                # Auto-récupération: si la pause PTT/Hybrid est terminée,
                # on force un retour "waiting_audio" pour relancer la connexion live.
                if (not _ptt_rec) and (not _hybrid_running) and (not _is_speaking):
                    _set_listen_conn_state("waiting_audio", "Reprise auto après pause", 0.0)
            elif state in {"connected", "waiting_audio"}:
                # Longue session: si on reste "connecté" mais sans activité trop longtemps,
                # on relance le stream pour éviter les sessions silencieuses bloquées.
                try:
                    idle_threshold_s = int(AUDIO_CONFIG.get("listen_watchdog_idle_threshold_s", 75) or 75)
                except Exception:
                    idle_threshold_s = 75
                idle_threshold_s = max(25, min(180, idle_threshold_s))
                if idle_age > idle_threshold_s and stream_age > (stale_threshold_s * 2) and (not _ptt_rec) and (not _hybrid_running) and (not _is_speaking):
                    # V5.2: Auto-pause au lieu de restart si active
                    auto_pause_enabled = bool(AUDIO_CONFIG.get("auto_pause_enabled", True))
                    auto_pause_threshold = int(AUDIO_CONFIG.get("auto_pause_silence_threshold_s", 120) or 120)
                    if auto_pause_enabled and idle_age > auto_pause_threshold:
                        # Pause au lieu de restart pour economiser ressources
                        try:
                            if "DG_ENGINE" in globals() and DG_ENGINE:
                                DG_ENGINE.is_running = False
                            AUDIO_CONFIG["is_listening"] = False
                            _set_listen_conn_state("paused", f"Auto-pause: silence {int(idle_age)}s", 0.0)
                            _push_toast(f"⏸️ Écoute en pause auto (silence {int(idle_age)}s)")
                            stealth_print(f"⏸️ Auto-pause écoute: silence détecté depuis {int(idle_age)}s")
                            _listen_runtime["watchdog_auto_pauses"] = int(_listen_runtime.get("watchdog_auto_pauses", 0) or 0) + 1
                        except Exception:
                            pass
                    else:
                        reason_idle = f"idle {state} depuis {int(idle_age)}s"
                        if _restart_listen_engine(reason_idle):
                            _watchdog_alert(reason_idle)
                            try:
                                _listen_runtime["watchdog_idle_restarts"] = int(_listen_runtime.get("watchdog_idle_restarts", 0) or 0) + 1
                            except Exception:
                                pass
                # Flux "connecté" mais aucune trame audio envoyée depuis trop longtemps:
                # relance préventive pour les longues sessions.
                try:
                    stale_threshold_s = int(AUDIO_CONFIG.get("listen_watchdog_stream_stale_s", 22) or 22)
                except Exception:
                    stale_threshold_s = 22
                stale_threshold_s = max(12, min(90, stale_threshold_s))
                if (
                    state == "connected"
                    and stream_age > stale_threshold_s
                    and (not _ptt_rec)
                    and (not _hybrid_running)
                    and (not _is_speaking)
                ):
                    if _restart_listen_engine(f"stream stale depuis {int(stream_age)}s"):
                        _watchdog_alert(f"stream stale depuis {int(stream_age)}s")
                        try:
                            _listen_runtime["watchdog_stream_stale_restarts"] = int(
                                _listen_runtime.get("watchdog_stream_stale_restarts", 0) or 0
                            ) + 1
                        except Exception:
                            pass
        except Exception:
            _PERF_STOP_EVENT.wait(1.0)

# ==================== API ====================
app = Flask('vtp_core', static_folder=str(WEB_DIR), template_folder=str(WEB_DIR))
CORS(app)

# Force UTF-8 headers for text responses to avoid mojibake in embedded webviews.
@app.after_request
def _force_utf8_headers(response):
    try:
        ctype = (response.headers.get("Content-Type") or "").lower()
        if response.mimetype == "application/json" and not getattr(response, "direct_passthrough", False):
            raw = response.get_data(as_text=True)
            if raw:
                try:
                    payload = json.loads(raw)
                    repaired = _repair_payload_strings(payload)
                    if repaired != payload:
                        response.set_data(
                            json.dumps(
                                repaired,
                                ensure_ascii=False,
                                separators=(",", ":"),
                            ).encode("utf-8")
                        )
                except Exception:
                    pass
        if (
            "text/" in ctype
            or "application/json" in ctype
            or "application/javascript" in ctype
        ) and "charset=" not in ctype:
            response.headers["Content-Type"] = f"{response.mimetype}; charset=utf-8"
    except Exception:
        pass
    return response
_mobile_connected = False


from fastapi import UploadFile, File


# ============================================================
# V5.3 — Buffer size auto-tuning
# ============================================================
_buffer_autotune_state = {
    "last_buffer_size": 1024,
    "last_latency_ms": None,
    "last_tuned_at": 0.0,
}

def _measure_audio_latency_ms(buffer_size: int, sample_rate: int = 48000) -> float:
    """Estime la latence introduite par un buffer donné."""
    return round((buffer_size / max(sample_rate, 1)) * 1000.0, 2)

def _autotune_buffer_size(target_latency_ms: float = 20.0) -> dict:
    """
    V5.3: Choisit automatiquement la taille de buffer optimale selon la cible de latence
    et la charge CPU actuelle.
    """
    import psutil
    cpu = psutil.cpu_percent(interval=0.2)
    sr = int(AUDIO_CONFIG.get("mic_sample_rate", 48000) or 48000)

    # Candidate buffer sizes (power of 2)
    candidates = [64, 128, 256, 512, 1024, 2048]

    # Under high CPU load, prefer larger buffers (more stable)
    if cpu > 75:
        candidates = [512, 1024, 2048]
    elif cpu > 50:
        candidates = [256, 512, 1024]

    best_size = 1024
    best_latency = None
    for size in candidates:
        lat = _measure_audio_latency_ms(size, sr)
        if lat <= target_latency_ms:
            best_size = size
            best_latency = lat
        else:
            break  # sorted ascending, stop when we exceed target

    # If no candidate meets target, pick smallest
    if best_latency is None:
        best_size = candidates[0]
        best_latency = _measure_audio_latency_ms(best_size, sr)

    # Apply
    AUDIO_CONFIG["audio_blocksize"] = best_size
    _buffer_autotune_state["last_buffer_size"] = best_size
    _buffer_autotune_state["last_latency_ms"] = best_latency
    _buffer_autotune_state["last_tuned_at"] = time.time()

    stealth_print(f"⚡ Buffer auto-tuné: {best_size} frames · {best_latency}ms · CPU={cpu:.0f}%")
    return {
        "ok": True,
        "buffer_size": best_size,
        "latency_ms": best_latency,
        "sample_rate": sr,
        "cpu_percent": round(cpu, 1),
        "target_latency_ms": target_latency_ms,
    }


# ============================================================
# V5.3 — Monitoring mix: micro + son jeu pour streamers
# ============================================================
_monitoring_mix_state = {
    "enabled": False,
    "mic_gain": 0.8,
    "game_gain": 0.5,
    "stream": None,
}




# ============================================================
# V5.3 — Smart Alerts
# ============================================================
_smart_alerts_state = {
    "alerts": [],
    "last_check_at": 0.0,
    "check_interval_s": 5.0,
}

def _check_smart_alerts() -> list:
    """
    V5.3: Vérifie les métriques et génère des alertes intelligentes.
    Appelé depuis /status pour ne pas surcharger le polling.
    """
    now = time.time()
    st = _smart_alerts_state
    if (now - st["last_check_at"]) < st["check_interval_s"]:
        return st["alerts"]

    st["last_check_at"] = now
    alerts = []

    try:
        # 1. Saturation micro (RMS trop élevé)
        rms = float(_listen_focus_auto_state.get("noise_rms_ema", 0.0) or 0.0)
        if rms > 0.25:
            alerts.append({
                "level": "warn",
                "code": "mic_saturation",
                "message": f"⚠️ Ton micro sature (RMS={rms:.3f}) — baisse le gain ou éloigne-toi du micro",
            })

        # 2. Bruit de fond anormal (RMS élevé sans voix)
        speech_ratio = float(AUDIO_CONFIG.get("_vad_v2_speech_ratio", 0.0) or 0.0)
        if rms > 0.04 and speech_ratio < 0.1:
            alerts.append({
                "level": "warn",
                "code": "high_noise",
                "message": f"⚠️ Bruit de fond anormal (RMS={rms:.3f}) — vérifie ton environnement audio",
            })

        # 3. Latence STT élevée
        stt_p95 = LATENCY_RUNTIME_STATE.get("stt_p95")
        if isinstance(stt_p95, (int, float)) and stt_p95 > 3000:
            alerts.append({
                "level": "warn",
                "code": "high_stt_latency",
                "message": f"⚠️ Latence STT élevée (p95={stt_p95:.0f}ms) — vérifie ta connexion internet",
            })

        # 4. Trop de redémarrages watchdog
        from_runtime = AUDIO_CONFIG.get("_listen_runtime", {})
        restarts = int(from_runtime.get("watchdog_restarts", 0) or 0)
        if restarts > 5:
            alerts.append({
                "level": "err",
                "code": "watchdog_restarts",
                "message": f"🔴 {restarts} redémarrages watchdog — instabilité détectée",
            })

        # 5. Santé écoute dégradée
        health = str(AUDIO_CONFIG.get("_listen_health_level", "") or "")
        if health == "err":
            summary = str(AUDIO_CONFIG.get("_listen_health_summary", "") or "")
            alerts.append({
                "level": "err",
                "code": "listen_health_err",
                "message": f"🔴 Santé écoute dégradée: {summary or 'vérifier les logs'}",
            })

        # 6. Quota cloud atteint
        if AUDIO_CONFIG.get("voice_cloud_limit_reached", False):
            alerts.append({
                "level": "warn",
                "code": "cloud_quota",
                "message": "⏱️ Quota cloud TTS atteint — bascule sur moteur local",
            })

        # 7. SNR trop faible
        snr = float(_listen_focus_auto_state.get("crest_ema", 0.0) or 0.0)
        if 0 < snr < 2.0:
            alerts.append({
                "level": "warn",
                "code": "low_snr",
                "message": f"⚠️ SNR très faible (crest={snr:.2f}) — voix difficile à isoler du bruit",
            })

    except Exception as e:
        stealth_print(f"⚠️ Smart alerts check error: {e}")

    st["alerts"] = alerts
    return alerts


@app.route("/hud/config", methods=["POST"])
def route_hud_config():
    """V5.3: Reçoit opacité + visibilité des lignes depuis index.html et les sauvegarde."""
    try:
        data = request.get_json(silent=True) or {}
        # Opacité — fond seulement, texte 100% opaque
        if "opacity" in data:
            pct = int(data["opacity"])
            AUDIO_CONFIG["hud_opacity"] = pct
            if _HUD_QT_WINDOW is not None:
                try:
                    _HUD_QT_WINDOW.set_opacity(pct)
                except Exception as e:
                    stealth_print(f"⚠️ HUD opacity update error: {e}")
        # Visibilité des lignes
        row_keys = ["hudShowPreset","hudShowRMS","hudShowSNR","hudShowFocus",
                    "hudShowUptime","hudShowMic","hudShowListen","hudShowGame"]
        for k in row_keys:
            if k in data:
                AUDIO_CONFIG[k] = bool(data[k])
        if _HUD_QT_WINDOW is not None:
            try:
                _HUD_QT_WINDOW.apply_row_visibility()
            except Exception as e:
                stealth_print(f"⚠️ HUD row visibility update error: {e}")
        save_settings()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/hud/move", methods=["POST"])
def route_hud_move():
    """V5.3: Déplace la fenêtre HUD Qt à la position demandée."""
    try:
        data = request.get_json(silent=True) or {}
        x = int(data.get("x", 40))
        y = int(data.get("y", 40))
        AUDIO_CONFIG["mini_overlay_x"] = x
        AUDIO_CONFIG["mini_overlay_y"] = y
        save_settings()
        if _HUD_QT_WINDOW is not None:
            try:
                _HUD_QT_WINDOW.move(x, y)
            except Exception as e:
                stealth_print(f"⚠️ HUD move error: {e}")
        return jsonify({"ok": True, "x": x, "y": y})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route('/config/reset', methods=['POST'])
def api_factory_reset():
    """ Supprime les réglages et recharge les défauts """
    global AUDIO_CONFIG
    
    # 1. On appelle notre fonction de reset définie plus haut
    reset_to_factory() 
    
    # 2. On ré-applique les raccourcis par défaut
    keyboard.unhook_all_hotkeys()
    if AUDIO_CONFIG.get('hotkey_f2_enabled', True): keyboard.add_hotkey('f2', toggle_tts_action)
    if AUDIO_CONFIG.get('hotkey_f3_enabled', True): keyboard.add_hotkey('f3', toggle_monitoring_action)
    keyboard.add_hotkey('f4', toggle_bypass_action)
    keyboard.add_hotkey('f8', panic_reset)
    
    return jsonify({"ok": True, "message": "Réinitialisation effectuée"})

@app.route('/audio/config', methods=['POST'])
def save_audio_api():
    data = request.json
    global AUDIO_CONFIG
    
    try:
        # 🔥 FIX PERSISTENCE : on persiste l'indice NUMÉRIQUE reçu du JS
        # (sinon le polling /status le remet toujours à la valeur précédente →
        #  le <select> est écrasé 2-3s après la sélection).
        out_idx = data.get('game_output_index')
        if out_idx is not None and str(out_idx).strip().isdigit():
            out_idx_int = int(str(out_idx).strip())
            AUDIO_CONFIG["game_output_device"] = out_idx_int
            # Résoudre la clé canonique depuis l'indice si le JS n'a pas envoyé de clé
            out_key = str(data.get('game_output_key') or "").strip()
            if not out_key:
                out_rt = _device_runtime_payload(out_idx_int) or {}
                out_name = out_rt.get("name", "")
                out_hostapi = out_rt.get("hostapi", "")
                out_key = _normalize_device_signature(out_name, out_hostapi)
            AUDIO_CONFIG["game_output_device_key"] = out_key
            AUDIO_CONFIG["game_output_device_runtime"] = _resolve_device_signature(
                out_key, as_output=True
            ) or {}

        in_idx = data.get('game_input_index')
        if in_idx is not None and str(in_idx).strip().isdigit():
            in_idx_int = int(str(in_idx).strip())
            AUDIO_CONFIG["game_input_device"] = in_idx_int
            in_key = str(data.get('game_input_key') or "").strip()
            if not in_key:
                in_rt = _device_runtime_payload(in_idx_int) or {}
                in_name = in_rt.get("name", "")
                in_hostapi = in_rt.get("hostapi", "")
                in_key = _normalize_device_signature(in_name, in_hostapi)
            AUDIO_CONFIG["game_input_device_key"] = in_key
            AUDIO_CONFIG["game_input_device_runtime"] = _resolve_device_signature(
                in_key, as_output=False
            ) or {}

        if data.get('tts_volume') is not None:
            try:
                vol = float(data.get('tts_volume'))
                AUDIO_CONFIG["tts_volume"] = max(0.0, min(2.0, vol))
            except Exception:
                pass
        
        # mini overlay desktop toggle (V5.3)
        if 'mini_overlay_enabled' in data:
            raw_overlay_enabled = data.get('mini_overlay_enabled')
            stealth_print(
                f"🔍 HUD toggle payload raw={raw_overlay_enabled!r} "
                f"type={type(raw_overlay_enabled).__name__}"
            )
            AUDIO_CONFIG['mini_overlay_enabled'] = bool(raw_overlay_enabled)
            stealth_print(
                f"🔍 HUD toggle coerced={AUDIO_CONFIG['mini_overlay_enabled']} "
                f"timer_started={_HUD_CMD_TIMER is not None} "
                f"window_exists={_HUD_QT_WINDOW is not None}"
            )
            if AUDIO_CONFIG['mini_overlay_enabled']:
                _hud_enqueue_command("show")
            else:
                _hud_enqueue_command("hide")
            stealth_print(f"🖥️ Mini overlay: {'activé' if AUDIO_CONFIG['mini_overlay_enabled'] else 'désactivé'}")

        # 💾 Sauvegarde dans le fichier settings.json
        saved = save_settings()
        
        stealth_print(
            f"{'✅' if saved else '⚠️'} "
            f"RÉGLAGES AUDIO {'VALIDÉS' if saved else 'ÉCHEC SAUVEGARDE'} : "
            f"Sortie={AUDIO_CONFIG['game_output_device_key']}, "
            f"Entrée={AUDIO_CONFIG['game_input_device_key']}, "
            f"Volume TTS={int(float(AUDIO_CONFIG.get('tts_volume', 1.0) or 1.0) * 100)}%"
        )
        return jsonify({
            "ok": saved,
            "config_file": str(CONFIG_FILE),
        }), (200 if saved else 500)
    except Exception as e:
        stealth_print(f"❌ Erreur lors du mapping audio : {e}")
        return jsonify({"ok": False, "error": str(e)}), 400

@app.route("/status")
def status_core(): 
    # 1. Fonction robuste pour l'IP LAN (utile pour QR Code mobile)
    def get_lan_ip_with_candidates():
        def _is_private_ipv4(ip: str) -> bool:
            if not ip or ip.startswith("127.") or ip.startswith("169.254."):
                return False
            if ip.startswith("10.") or ip.startswith("192.168."):
                return True
            if ip.startswith("172."):
                try:
                    second = int(ip.split(".")[1])
                    return 16 <= second <= 31
                except Exception:
                    return False
            return False

        candidates = []

        def _push_candidate(ip: str):
            if _is_private_ipv4(ip) and ip not in candidates:
                candidates.append(ip)

        # 1) Méthode rapide (route par défaut)
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            _push_candidate(ip)
        except Exception:
            pass

        # 2) Fallback offline: interfaces locales
        try:
            host_ips = socket.gethostbyname_ex(socket.gethostname())[2]
            for ip in host_ips:
                _push_candidate(ip)
        except Exception:
            pass

        # 3) Fallback robuste via psutil (Wi-Fi / Ethernet)
        try:
            import psutil
            preferred = []
            others = []
            for if_name, addrs in (psutil.net_if_addrs() or {}).items():
                for a in addrs:
                    if getattr(a, "family", None) == socket.AF_INET:
                        ip = getattr(a, "address", "")
                        if not _is_private_ipv4(ip):
                            continue
                        lower = str(if_name).lower()
                        if any(k in lower for k in ["wi-fi", "wifi", "wlan", "ethernet", "eth"]):
                            if ip not in preferred:
                                preferred.append(ip)
                        else:
                            if ip not in others:
                                others.append(ip)
            for ip in preferred + others:
                _push_candidate(ip)
        except Exception:
            pass

        best = candidates[0] if candidates else "127.0.0.1"
        return best, candidates

    def safe_int(val):
        try: return int(val) if str(val).isdigit() else 0
        except: return 0

    # 2. On prend toute la config audio (Turbo, Micro, Volume...)
    st = {k: v for k, v in AUDIO_CONFIG.items()}
    desktop_key = (AUDIO_CONFIG.get("license_key") or "").strip().upper()
    voice_key = (AUDIO_CONFIG.get("voice_license_key") or "").strip().upper()
    # BUG 4 fix — vérifier le timestamp AVANT de considérer un trial actif
    def _trial_not_expired(key):
        """True seulement si clé TRIAL- avec timestamp < 24h."""
        if not key.startswith("TRIAL-"):
            return False
        try:
            import time as _t
            ts = int(key.split("-")[1])
            return (_t.time() - ts) / 3600 < 24
        except Exception:
            return False
    trial_desktop = False if (COMMUNITY_EDITION or (not CLOUD_FEATURES_ENABLED)) else _trial_not_expired(desktop_key)
    trial_voice   = False if (COMMUNITY_EDITION or (not CLOUD_FEATURES_ENABLED)) else _trial_not_expired(voice_key)
    trial_mode    = False if (COMMUNITY_EDITION or (not CLOUD_FEATURES_ENABLED)) else (trial_desktop or trial_voice)
    trial_expiration = ""
    if (not COMMUNITY_EDITION) and CLOUD_FEATURES_ENABLED:
        if trial_desktop and LICENSE_MGR.expiration_str and LICENSE_MGR.expiration_str != "N/A":
            trial_expiration = LICENSE_MGR.expiration_str
        elif trial_voice and VOICE_LICENSE_MGR.expiration_str and VOICE_LICENSE_MGR.expiration_str != "N/A":
            trial_expiration = VOICE_LICENSE_MGR.expiration_str
    voice_licensed = False if (not CLOUD_FEATURES_ENABLED) else (True if COMMUNITY_EDITION else has_voice_license())
    voice_active = voice_licensed and AUDIO_CONFIG.get("tts_engine") == "KOMMZ_VOICE"
    trial_quota_seconds = 1800
    trial_used_local = int(AUDIO_CONFIG.get("trial_voice_seconds_used_local", 0) or 0)
    trial_used_local = max(0, min(trial_quota_seconds, trial_used_local))
    trial_remaining_local = max(0, trial_quota_seconds - trial_used_local)
    mm = trial_remaining_local // 60
    ss = trial_remaining_local % 60
    xtts_runtime = get_kommz_xtts_runtime_status(force=False)
    cloud_diag = get_cloud_endpoints_diag(force=False)
    hybrid_cfg = _get_hybrid_fr_config_status()
    listen_health = _build_listen_health_snapshot()
    
    # 3. --- AJOUT CRITIQUE POUR REMOTE V5 ---
    global app_state
    lan_ip, lan_candidates = get_lan_ip_with_candidates()
    st.update({
        "is_active": app_state["is_active"],          # Pour le bouton MAIN (ON/OFF)
        "gender": app_state.get("gender", "MALE"),    # Pour le bouton GENRE
        "local_ip": lan_ip,
        "local_ips": lan_candidates,
        "remote_url": f"http://{lan_ip}:{VTP_CORE_PORT}/remote",
        "licensed": True if COMMUNITY_EDITION else LICENSE_MGR.is_active,
        "expiration": "COMMUNITY" if COMMUNITY_EDITION else LICENSE_MGR.expiration_str,
        "hwid": LICENSE_MGR.hwid,
        "edition_profile": EDITION_PROFILE,
        "cloud_features_enabled": bool(CLOUD_FEATURES_ENABLED),
        "license_email": (AUDIO_CONFIG.get("license_email") or "").strip().lower(),
        "voice_licensed": voice_licensed,
        "voice_active": voice_active,
        "voice_expiration": "COMMUNITY" if COMMUNITY_EDITION else VOICE_LICENSE_MGR.expiration_str,
        "trial_mode": trial_mode,
        "trial_desktop": trial_desktop,
        "trial_voice": trial_voice,
        "trial_expiration": trial_expiration,
        "desktop_activated": True if COMMUNITY_EDITION else (LICENSE_MGR.is_activated or trial_desktop),
        "voice_activated": True if COMMUNITY_EDITION else (VOICE_LICENSE_MGR.is_activated or trial_voice),
        "trial_voice_seconds_quota": trial_quota_seconds,
        "trial_voice_seconds_used_local": trial_used_local,
        "trial_voice_seconds_remaining_local": trial_remaining_local,
        "trial_voice_remaining_local_mmss": f"{mm:02d}:{ss:02d}",
        "community_mode": bool(COMMUNITY_EDITION),
        "mobile_connected": _mobile_connected,
        "current_version": CURRENT_VERSION,
        "update_available": bool(UPDATE_STATE.get("update_available")),
        "update_latest_version": UPDATE_STATE.get("latest_version", CURRENT_VERSION),
        "update_download_url": UPDATE_STATE.get("download_url", ""),
        "update_changelog_url": UPDATE_STATE.get("changelog_url", ""),
        "update_download_sha256": UPDATE_STATE.get("download_sha256", ""),
        "update_force": bool(UPDATE_STATE.get("force_update")),
        "update_minimum_version": UPDATE_STATE.get("minimum_version", ""),
        "update_message": UPDATE_STATE.get("message", ""),
        "update_error": UPDATE_STATE.get("error", ""),
        "update_installing": bool(UPDATE_STATE.get("installing")),
        "update_install_status": UPDATE_STATE.get("install_status", ""),
        "voice_cloud_limit_reached": bool(VOICE_CLOUD_LIMIT_STATE.get("reached")),
        "voice_cloud_limit_message": VOICE_CLOUD_LIMIT_STATE.get("message", ""),
        "xtts_runtime_state": xtts_runtime.get("state", "unknown"),
        "xtts_runtime_message": xtts_runtime.get("message", "Vérification en cours..."),
        "xtts_runtime_checked_at": xtts_runtime.get("checked_at", 0),
        "cloud_endpoints_diag": cloud_diag,
        "xtts_warmup_cooldown_seconds": int(KOMMZ_XTTS_WARMUP_COOLDOWN or 0),
        "xtts_warmup_last_ts": float(_last_xtts_warmup_ts or 0.0),
        "xtts_warmup_retry_after": _get_xtts_warmup_retry_after_seconds(),
        "pipeline_runtime": _build_pipeline_runtime_payload(),
        "tts_fallback_runtime": _build_tts_fallback_runtime_payload(),
        "latency_runtime": _build_latency_runtime_payload(),
        "expressive_runtime": _build_expressive_runtime_payload(),
        "hybrid_fast_runtime": _build_hybrid_fast_runtime_payload(),
        "modules_runtime": _build_modules_runtime_payload(),
        "quality_log": _build_quality_log_payload(),
        "pipeline_queue_size": USER_PIPELINE_QUEUE.qsize(),
        "pipeline_queue_active": bool(_user_pipeline_active),
        "pipeline_queue_active_source": str(_user_pipeline_active_source or ""),
        "voice_focus_v3_state": {
            "calibrating": bool(_voice_focus_v3_state.get("calibration_started_at", 0) and not _voice_focus_v3_state.get("calibrated", False)),
            "calibrated": bool(_voice_focus_v3_state.get("calibrated", False)),
            "noise_rms_ema": float(_voice_focus_v3_state.get("noise_floor_mid", 0.0) or 0.0),
            "snr_approx_db": float(_voice_focus_v3_state.get("vad_voice_peak_ema", 0.0) / max(0.0001, float(_voice_focus_v3_state.get("vad_noise_floor_ema", 0.0001) or 0.0001))),
            "gain_riding_ema": float(_voice_focus_v3_state.get("gain_riding_ema", 1.0) or 1.0),
            "vad_threshold_adaptive": float(_voice_focus_v3_state.get("vad_threshold_adaptive", 0.025) or 0.025),
            "voiceprint_initialized": bool(_voice_focus_v3_state.get("voiceprint_initialized", False)),
        },
        
        # Sécurités pour éviter les bugs d'affichage
        "is_listening": AUDIO_CONFIG.get("is_listening", True),
        "user_overlay_color": str(AUDIO_CONFIG.get("user_overlay_color", "#00FFFF") or "#00FFFF"),
        "ally_overlay_color": str(AUDIO_CONFIG.get("ally_overlay_color", "#FFFF00") or "#FFFF00"),
        "turbo_latency_active": AUDIO_CONFIG.get("turbo_latency_active", False),
        # V5.3: STT/TTS latency percentiles
        "stt_p50": LATENCY_RUNTIME_STATE.get("stt_p50"),
        "stt_p95": LATENCY_RUNTIME_STATE.get("stt_p95"),
        "stt_p99": LATENCY_RUNTIME_STATE.get("stt_p99"),
        "tts_p50": LATENCY_RUNTIME_STATE.get("tts_p50"),
        "tts_p95": LATENCY_RUNTIME_STATE.get("tts_p95"),
        "tts_p99": LATENCY_RUNTIME_STATE.get("tts_p99"),
        "total_p50": LATENCY_RUNTIME_STATE.get("total_p50"),
        "total_p95": LATENCY_RUNTIME_STATE.get("total_p95"),
        "total_p99": LATENCY_RUNTIME_STATE.get("total_p99"),
        "latency_sample_count": LATENCY_RUNTIME_STATE.get("sample_count", 0),
        # V5.3: VAD V2
        **get_vad_v2_status(),
        # V5.3: Smart alerts (cached, 5s interval)
        "smart_alerts": _check_smart_alerts(),
        "smart_alerts_count": len(_smart_alerts_state.get("alerts", [])),
        # V5.3: Monitoring mix
        "monitoring_mix_enabled": bool(AUDIO_CONFIG.get("monitoring_mix_enabled", False)),
        "monitoring_mix_mic_gain":  float(AUDIO_CONFIG.get("monitoring_mix_mic_gain", 0.8)),
        "monitoring_mix_game_gain": float(AUDIO_CONFIG.get("monitoring_mix_game_gain", 0.5)),
        # V5.3: Buffer autotune
        "audio_blocksize": int(AUDIO_CONFIG.get("audio_blocksize", 1024) or 1024),
        "buffer_last_latency_ms": _buffer_autotune_state.get("last_latency_ms"),
        "mini_overlay_enabled": bool(AUDIO_CONFIG.get("mini_overlay_enabled", False)),
        # FIX #2: StreamBuffer drop counter
        "stream_buffer_total_drops": int(_STREAM_BUFFER_TOTAL_DROPS),
    })

    # 4. FIX AFFICHAGE LANGUE (Codes drapeaux)
    current_engine_lang = AUDIO_CONFIG.get("target_lang", "en")
    
    if current_engine_lang.lower() == "zh-cn":
        display_lang = "ZH"
    elif current_engine_lang.lower() == "jw": 
        display_lang = "JV"
    elif current_engine_lang.lower() == "iw": 
        display_lang = "HE"
    else:
        display_lang = current_engine_lang.upper()

    st["target_lang"] = display_lang 
    
    # 5. Infos Voix
    voice_library = _get_voice_library()
    voice_active_id = str(AUDIO_CONFIG.get("voice_active_id") or AUDIO_CONFIG.get("kommz_client_id") or "").strip()
    scene_library = _get_scene_library()
    listen_preset_library = _get_listen_preset_library()
    st.update({
        "kommz_url": AUDIO_CONFIG.get("kommz_api_url", ""),
        "kommz_synthesis_url": AUDIO_CONFIG.get("kommz_synthesis_url", ""),
        "kommz_key": AUDIO_CONFIG.get("kommz_api_key", ""),       # AJOUT
        "kommz_id": AUDIO_CONFIG.get("kommz_client_id", ""),      # AJOUT  
        "kommz_speed": float(AUDIO_CONFIG.get("kommz_speed", 1.0) or 1.0),
        "kommz_xtts_preset": str(AUDIO_CONFIG.get("kommz_xtts_preset", "stable") or "stable").strip().lower(),
        "kommz_top_k": int(AUDIO_CONFIG.get("kommz_top_k", 60) or 60),
        "kommz_top_p": float(AUDIO_CONFIG.get("kommz_top_p", 0.90) or 0.90),
        "kommz_repetition_penalty": float(AUDIO_CONFIG.get("kommz_repetition_penalty", 2.2) or 2.2),
        "kommz_length_penalty": float(AUDIO_CONFIG.get("kommz_length_penalty", 1.0) or 1.0),
        "kommz_enable_text_splitting": bool(AUDIO_CONFIG.get("kommz_enable_text_splitting", True)),
        "kommz_gpt_cond_len": int(AUDIO_CONFIG.get("kommz_gpt_cond_len", 12) or 12),
        "kommz_gpt_cond_chunk_len": int(AUDIO_CONFIG.get("kommz_gpt_cond_chunk_len", 4) or 4),
        "kommz_max_ref_len": int(AUDIO_CONFIG.get("kommz_max_ref_len", 10) or 10),
        "kommz_sound_norm_refs": bool(AUDIO_CONFIG.get("kommz_sound_norm_refs", False)),
        "whisper_api_url": AUDIO_CONFIG.get("whisper_api_url", ""),
        "whisper_model": AUDIO_CONFIG.get("whisper_model", DEFAULT_KOMMZ_WHISPER_MODEL),
        "gpt_style_to_xtts_fr": bool(AUDIO_CONFIG.get("gpt_style_to_xtts_fr", False)),
        "gpt_api_url": AUDIO_CONFIG.get("gpt_api_url", ""),
        "gpt_ref_audio_path": AUDIO_CONFIG.get("gpt_ref_audio_path", ""),
        "gpt_prompt_text": AUDIO_CONFIG.get("gpt_prompt_text", ""),
        "gpt_prompt_lang": AUDIO_CONFIG.get("gpt_prompt_lang", "ja"),
        "gpt_style_text": AUDIO_CONFIG.get("gpt_style_text", ""),
        "gpt_style_text_lang": AUDIO_CONFIG.get("gpt_style_text_lang", "ja"),
        "hybrid_rts_preset": str(AUDIO_CONFIG.get("hybrid_rts_preset", "fast") or "fast").strip().lower(),
        "quality_preset": _normalize_quality_preset(AUDIO_CONFIG.get("quality_preset", "balanced")),
        "expressive_sounds_enabled": bool(AUDIO_CONFIG.get("expressive_sounds_enabled", True)),
        "expressive_profile": str(AUDIO_CONFIG.get("expressive_profile", "gaming") or "gaming"),
        "expressive_transcript_mode": str(AUDIO_CONFIG.get("expressive_transcript_mode", "keep") or "keep"),
        "expressive_tts_mode": str(AUDIO_CONFIG.get("expressive_tts_mode", "styled") or "styled"),
        "expressive_intensity_mode": str(AUDIO_CONFIG.get("expressive_intensity_mode", "auto") or "auto"),
        "expressive_noise_mode": str(AUDIO_CONFIG.get("expressive_noise_mode", "smart") or "smart"),
        "expressive_xtts_mode": str(AUDIO_CONFIG.get("expressive_xtts_mode", "auto") or "auto"),
        "expressive_hybrid_mode": str(AUDIO_CONFIG.get("expressive_hybrid_mode", "auto") or "auto"),
        "expressive_stability_mode": str(AUDIO_CONFIG.get("expressive_stability_mode", "balanced") or "balanced"),
        "expressive_fallback_guard": bool(AUDIO_CONFIG.get("expressive_fallback_guard", True)),
        "expressive_ptt_mode": str(AUDIO_CONFIG.get("expressive_ptt_mode", "full") or "full"),
        "expressive_rts_mode": str(AUDIO_CONFIG.get("expressive_rts_mode", "safe") or "safe"),
        "hybrid_fr_ready": bool(hybrid_cfg.get("ready")),
        "hybrid_fr_message": hybrid_cfg.get("message", ""),
        "hybrid_fr_ref_name": hybrid_cfg.get("ref_name", ""),
        "hybrid_fr_ref_exists": bool(hybrid_cfg.get("ref_exists")),
        "recording": _ptt_rec, 
        "ptt_key": AUDIO_CONFIG.get("ptt_hotkey", "ctrl+shift"),
        "game_output_index": safe_int(AUDIO_CONFIG.get("game_output_device")),
        "game_input_index": safe_int(AUDIO_CONFIG.get("game_input_device")),
        "tts_volume": float(AUDIO_CONFIG.get("tts_volume", 1.0) or 1.0),
        "edge_voice": AUDIO_CONFIG.get("edge_voice", ""),
        "current_voice_id": AUDIO_CONFIG.get("edge_voice", ""),
        "voice_library": voice_library,
        "voice_active_id": voice_active_id,
        "voice_default_at_startup": bool(AUDIO_CONFIG.get("voice_default_at_startup", True)),
        "scene_library": scene_library,
        "scene_active_name": str(AUDIO_CONFIG.get("scene_active_name") or ""),
        "scene_last_applied_at": str(AUDIO_CONFIG.get("scene_last_applied_at") or ""),
        "scene_auto_apply_enabled": bool(AUDIO_CONFIG.get("scene_auto_apply_enabled", False)),
        "scene_auto_process": str(AUDIO_CONFIG.get("scene_auto_process") or ""),
        "ally_recognition_lang": str(AUDIO_CONFIG.get("ally_recognition_lang", "multi") or "multi").strip(),
        "ally_block_french": bool(AUDIO_CONFIG.get("ally_block_french", False)),
        "ally_voice_focus_mode": str(AUDIO_CONFIG.get("ally_voice_focus_mode", "balanced") or "balanced").strip().lower(),
        "ally_voice_focus_effective": str(_listen_focus_auto_state.get("mode_effective", "balanced") or "balanced"),
        "ally_voice_focus_auto_noise_rms": float(_listen_focus_auto_state.get("noise_rms_ema", 0.0) or 0.0),
        "ally_voice_focus_auto_crest": float(_listen_focus_auto_state.get("crest_ema", 0.0) or 0.0),
        "ally_listen_profile": str(AUDIO_CONFIG.get("ally_listen_profile", "default") or "default").strip().lower(),
        "ally_game_preset": str(AUDIO_CONFIG.get("ally_game_preset", "custom") or "custom").strip().lower(),
        "ally_competitive_lock": bool(AUDIO_CONFIG.get("ally_competitive_lock", False)),
        "ally_competitive_lock_effective": bool(_is_competitive_listen_locked()),
        "ally_competitive_unlock_remaining_s": max(
            0,
            int((float(AUDIO_CONFIG.get("ally_competitive_unlock_until_ts", 0.0) or 0.0) - time.time()) + 0.999)
        ),
        "ally_competitive_lock_auto": bool(AUDIO_CONFIG.get("ally_competitive_lock_auto", True)),
        "ally_preset_library": [str(it.get("name") or "") for it in listen_preset_library],
        "listen_health_level": str(listen_health.get("level", "info") or "info"),
        "listen_health_summary": str(listen_health.get("summary", "Santé écoute indisponible") or "Santé écoute indisponible"),
        "listen_health_state": str(listen_health.get("state", "unknown") or "unknown"),
        "listen_runtime": {
            "ally_text_events": int(_listen_runtime.get("ally_text_events", 0) or 0),
            "ally_voice_played": int(_listen_runtime.get("ally_voice_played", 0) or 0),
            "ally_voice_skipped": int(_listen_runtime.get("ally_voice_skipped", 0) or 0),
            "ally_voice_rate_limited": int(_listen_runtime.get("ally_voice_rate_limited", 0) or 0),
            "ally_short_merged": int(_listen_runtime.get("ally_short_merged", 0) or 0),
            "last_event_at": float(_listen_runtime.get("last_event_at", 0.0) or 0.0),
            "autotune_level": int(_listen_autotune_state.get("level", 0) or 0),
            "autotune_ratio": float(_listen_autotune_state.get("ratio", 1.0) or 1.0),
            "autotune_last_update_at": float(_listen_autotune_state.get("last_update_at", 0.0) or 0.0),
            "autotune_enabled": bool(AUDIO_CONFIG.get("ally_autotune_enabled", True)),
            "listen_conn_state": str(_listen_runtime.get("listen_conn_state", "idle") or "idle"),
            "listen_conn_detail": str(_listen_runtime.get("listen_conn_detail", "") or ""),
            "listen_conn_retry_after": float(_listen_runtime.get("listen_conn_retry_after", 0.0) or 0.0),
            "listen_conn_updated_at": float(_listen_runtime.get("listen_conn_updated_at", 0.0) or 0.0),
            "watchdog_restarts": int(_listen_runtime.get("watchdog_restarts", 0) or 0),
            "watchdog_flaps": int(_listen_runtime.get("watchdog_flaps", 0) or 0),
            "watchdog_cooldown_hits": int(_listen_runtime.get("watchdog_cooldown_hits", 0) or 0),
            "watchdog_idle_restarts": int(_listen_runtime.get("watchdog_idle_restarts", 0) or 0),
            "watchdog_stream_stale_restarts": int(_listen_runtime.get("watchdog_stream_stale_restarts", 0) or 0),
            "watchdog_last_idle_age_s": float(_listen_runtime.get("watchdog_last_idle_age_s", 0.0) or 0.0),
            "last_audio_seen_at": float(_listen_runtime.get("last_audio_seen_at", 0.0) or 0.0),
            "watchdog_last_restart_at": float(_listen_runtime.get("watchdog_last_restart_at", 0.0) or 0.0),
            "watchdog_last_restart_reason": str(_listen_runtime.get("watchdog_last_restart_reason", "") or ""),
            "watchdog_last_tick_at": float(_listen_runtime.get("watchdog_last_tick_at", 0.0) or 0.0),
        },
    })

    return jsonify(_repair_payload_strings(st))




def _download_file(url: str, out_path: str) -> None:
    with requests.get(url, stream=True, timeout=(8, 120)) as r:
        r.raise_for_status()
        with open(out_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 256):
                if chunk:
                    f.write(chunk)


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _resolve_running_launcher_exe() -> str:
    temp_root = os.path.abspath(tempfile.gettempdir()).lower()
    candidates = []
    seen = set()

    for raw in (sys.argv[0], sys.executable):
        try:
            ap = os.path.abspath(raw)
        except Exception:
            continue
        key = ap.lower()
        if not key.endswith(".exe") or not os.path.exists(ap) or key in seen:
            continue
        seen.add(key)
        candidates.append(ap)

    if not candidates:
        return os.path.abspath(sys.executable)

    def _score(path: str) -> int:
        score = 0
        low = path.lower()
        name = os.path.basename(low)
        if not low.startswith(temp_root):
            score += 20
        if re.match(r"^kommz_(gamer|diamond)(?:_v[\w.\-]+)?\.exe$", name):
            score += 50
        if low == os.path.abspath(sys.argv[0]).lower():
            score += 10
        return score

    candidates.sort(key=_score, reverse=True)
    return candidates[0]


def _is_kommz_versioned_exe_name(name: str) -> bool:
    return bool(re.match(r"^kommz_(gamer|diamond)_v[\w.\-]+\.exe$", name.lower()))


def _spawn_detached_exe(path: str) -> bool:
    try:
        subprocess.Popen(
            [os.path.abspath(path)],
            shell=False,
            creationflags=0x00000008 | 0x00000200,
            close_fds=True,
        )
        return True
    except Exception:
        try:
            os.startfile(os.path.abspath(path))
            return True
        except Exception:
            return False


def _redirect_to_stable_launcher_if_needed() -> bool:
    if os.name != "nt" or not getattr(sys, "frozen", False):
        return False

    current_exe = _resolve_running_launcher_exe()
    current_name = os.path.basename(current_exe)
    if not _is_kommz_versioned_exe_name(current_name):
        return False

    current_dir = os.path.dirname(current_exe)
    for candidate in (
        os.path.join(current_dir, "Kommz_Gamer.exe"),
        os.path.join(current_dir, "Kommz_Diamond.exe"),
    ):
        if not os.path.exists(candidate):
            continue
        if os.path.abspath(candidate).lower() == os.path.abspath(current_exe).lower():
            continue
        if _spawn_detached_exe(candidate):
            return True
    return False


def _launch_windows_self_replacer(downloaded_exe_path: str) -> bool:
    if os.name != "nt" or not getattr(sys, "frozen", False):
        return False
    current_exe = _resolve_running_launcher_exe()
    downloaded_exe = os.path.abspath(downloaded_exe_path)
    if not current_exe.lower().endswith(".exe") or not os.path.exists(downloaded_exe):
        return False

    current_dir = os.path.dirname(current_exe)
    current_name = os.path.basename(current_exe)
    downloaded_name = os.path.basename(downloaded_exe)
    generic_alias = os.path.join(current_dir, "Kommz_Gamer.exe")
    diamond_alias = os.path.join(current_dir, "Kommz_Diamond.exe")
    versioned_target = os.path.join(current_dir, downloaded_name)

    copy_targets = []
    seen_targets = set()

    def _push_target(path: str) -> None:
        ap = os.path.abspath(path)
        key = ap.lower()
        if key == downloaded_exe.lower() or key in seen_targets:
            return
        seen_targets.add(key)
        copy_targets.append(ap)

    launch_target = current_exe
    current_lower = current_name.lower()
    known_kommz_name = re.match(r"^kommz_(gamer|diamond)(?:_v[\w.\-]+)?\.exe$", current_lower)

    if known_kommz_name:
        # Toujours remplacer d'abord l'exe en cours d'utilisation pour garantir
        # qu'un raccourci existant redémarre bien sur la nouvelle version.
        _push_target(current_exe)
        _push_target(versioned_target)
        _push_target(generic_alias)
        _push_target(diamond_alias)

        if current_lower == "kommz_diamond.exe":
            launch_target = diamond_alias
        elif current_lower == "kommz_gamer.exe":
            launch_target = generic_alias
        else:
            # Si on tourne depuis un exe versionné, relancer ce même binaire
            # évite de retomber sur un alias potentiellement obsolète.
            launch_target = versioned_target
    else:
        _push_target(current_exe)
        launch_target = current_exe

    if not copy_targets:
        copy_targets.append(current_exe)

    current_pid = os.getpid()
    batch_path = os.path.join(tempfile.gettempdir(), f"kommz_update_{current_pid}.cmd")
    copy_lines = []
    first_target = copy_targets[0]
    copy_lines.append(f'copy /Y "%SRC%" "{first_target}" >nul')
    copy_lines.append("if errorlevel 1 goto end")
    for extra_target in copy_targets[1:]:
        copy_lines.append(f'copy /Y "{first_target}" "{extra_target}" >nul')
    copy_block = "\n".join(copy_lines)
    batch_script = f"""@echo off
setlocal
set "SRC={downloaded_exe}"
set "LAUNCH={os.path.abspath(launch_target)}"
set "PID={current_pid}"
for /L %%I in (1,1,90) do (
  tasklist /FI "PID eq %PID%" | find "%PID%" >nul
  if errorlevel 1 goto replace
  timeout /t 1 /nobreak >nul
)
:replace
{copy_block}
start "" "%LAUNCH%"
:end
del /Q "%SRC%" >nul 2>&1
del /Q "%~f0" >nul 2>&1
"""
    with open(batch_path, "w", encoding="utf-8", newline="\r\n") as f:
        f.write(batch_script)
    subprocess.Popen(["cmd.exe", "/c", batch_path], shell=False, creationflags=0x08000000)
    return True


def _install_update_background():
    url = (UPDATE_STATE.get("download_url") or "").strip()
    expected_sha256 = (UPDATE_STATE.get("download_sha256") or "").strip().lower()
    if not url:
        UPDATE_STATE["installing"] = False
        UPDATE_STATE["install_status"] = "URL de mise à jour introuvable"
        return
    try:
        UPDATE_STATE["installing"] = True
        UPDATE_STATE["install_status"] = "Téléchargement en cours..."
        add_subtitle("SYSTEM >> UPDATE: TELECHARGEMENT", "SYS")

        base_name = (url.split("?")[0].rstrip("/").split("/")[-1] or "Kommz_Update.exe").strip()
        if not base_name.lower().endswith(".exe"):
            base_name += ".exe"

        update_dir = Path(os.environ.get("TEMP", ".")) / "KommzUpdate"
        update_dir.mkdir(parents=True, exist_ok=True)
        installer_path = str(update_dir / base_name)

        _download_file(url, installer_path)

        if expected_sha256:
            got_sha256 = _sha256_file(installer_path).lower()
            if got_sha256 != expected_sha256:
                UPDATE_STATE["installing"] = False
                UPDATE_STATE["install_status"] = "Échec mise à jour : checksum invalide"
                UPDATE_STATE["error"] = "Checksum SHA256 invalide pour l'installateur téléchargé"
                add_subtitle("SYSTEM >> UPDATE: CHECKSUM INVALIDE", "SYS")
                return

        UPDATE_STATE["install_status"] = "Téléchargement terminé. Lancement..."
        add_subtitle("SYSTEM >> UPDATE: INSTALLER LANCE", "SYS")

        if _launch_windows_self_replacer(installer_path):
            UPDATE_STATE["install_status"] = "Mise à jour prête. Redémarrage..."
            add_subtitle("SYSTEM >> UPDATE: REDEMARRAGE", "SYS")

            def _exit_for_update():
                time.sleep(1.2)
                os._exit(0)

            threading.Thread(target=_exit_for_update, daemon=True).start()
            UPDATE_STATE["installing"] = False
            return

        subprocess.Popen([installer_path], shell=False)
        UPDATE_STATE["installing"] = False
        UPDATE_STATE["install_status"] = "Installateur lancé"
    except Exception as e:
        UPDATE_STATE["installing"] = False
        UPDATE_STATE["install_status"] = f"Échec mise à jour : {e}"
        UPDATE_STATE["error"] = str(e)

import keyboard # Assure-toi que ce module est importé

@app.route('/hotkey/start_capture', methods=['POST'])
def start_hotkey_capture():
    """ Déclenche l'écoute de la prochaine touche pressée pour le PTT """
    def capture_logic():
        global AUDIO_CONFIG
        stealth_print("⌨️ Mode Capture PTT : Appuyez sur une touche...")
        
        # On attend la pression d'une touche
        event = keyboard.read_event()
        
        if event.event_type == keyboard.KEY_DOWN:
            new_key = event.name
            
            # 1. On enregistre la touche UNIQUEMENT dans le dictionnaire
            AUDIO_CONFIG["ptt_hotkey"] = new_key
            save_settings()
            
            # 2. 🛡️ FIX : On réinitialise les raccourcis système pour être propre
            # MAIS on ne lie JAMAIS la nouvelle touche 'new_key' à 'toggle_bypass_action'
            try:
                keyboard.unhook_all_hotkeys()
                if AUDIO_CONFIG.get('hotkey_f2_enabled', True): keyboard.add_hotkey('f2', toggle_tts_action)
                
                # ON REBRANCHE F4 SUR LE BYPASS (Uniquement F4)
                keyboard.add_hotkey('f4', toggle_bypass_action)
                
                # ON REBRANCHE LES AUTRES TOUCHES SYSTÈME
                if AUDIO_CONFIG.get('hotkey_f3_enabled', True): keyboard.add_hotkey('f3', toggle_monitoring_action)
                keyboard.add_hotkey('f8', panic_reset)
                
                stealth_print(f"✅ PTT enregistré : {new_key} | F4 reste configuré sur BYPASS")
            except Exception as e:
                stealth_print(f"❌ Erreur ré-assignation hotkeys : {e}")

    # Lancement dans un thread séparé pour ne pas bloquer l'interface
    threading.Thread(target=capture_logic, daemon=True).start()
    return jsonify({"ok": True})

    # --- CES LIGNES DOIVENT ÊTRE DANS LA FONCTION MAÎTRESSE ---
    threading.Thread(target=capture_logic, daemon=True).start()
    
    # C'est ce return qui posait problème : il doit être décalé (indented)
    return jsonify({"ok": True})

from pynput import mouse, keyboard as pynk

def capture_next_key_thread():
    global AUDIO_CONFIG
    AUDIO_CONFIG["is_capturing"] = True
    stealth_print("🖱️ En attente d'une touche ou d'un bouton de souris...")
    
    captured_key = None

    # --- ÉCOUTEUR SOURIS ---
    def on_click(x, y, button, pressed):
        nonlocal captured_key
        if pressed:
            btn_str = str(button)
            if "x1" in btn_str: captured_key = "xbutton1"   # Souris 4
            elif "x2" in btn_str: captured_key = "xbutton2" # Souris 5
            return False # Arrête l'écouteur souris

    # --- ÉCOUTEUR CLAVIER ---
    def on_press(key):
        nonlocal captured_key
        try:
            # Touche normale (a, b, c...)
            captured_key = key.char
        except AttributeError:
            # Touche spéciale (ctrl, alt, f9...)
            k_name = str(key).replace("Key.", "")
            if "shift" in k_name: captured_key = "shift"
            elif "ctrl" in k_name or "control" in k_name: captured_key = "ctrl"
            else: captured_key = k_name
        return False # Arrête l'écouteur clavier

    # On lance les deux écouteurs en mode non-bloquant
    m_listener = mouse.Listener(on_click=on_click)
    k_listener = pynk.Listener(on_press=on_press)
    
    m_listener.start()
    k_listener.start()

    # On attend que l'un des deux capture quelque chose
    while captured_key is None and AUDIO_CONFIG["is_capturing"]:
        time.sleep(0.1)

    # On arrête tout proprement
    m_listener.stop()
    k_listener.stop()

    if captured_key:
        AUDIO_CONFIG["ptt_key"] = captured_key
        stealth_print(f"✅ ENREGISTRÉ : {captured_key}")

    AUDIO_CONFIG["is_capturing"] = False
    
from flask import send_from_directory

# --- GESTION DES GUIDES INTEGRES ---

@app.route('/guide/view/<name>')
def view_guide(name):
    """Sert le fichier HTML du guide"""
    # 1. Liste des fichiers possibles. On garde une compat pour l'ancien nom
    # "Guide _Kommz_Gamer.html" (avec espace) qui a pu etre distribue.
    files = {
        "streamer": ["Guide_Streamer_Kommz.html"],
        "general": ["Guide_Kommz_Gamer.html", "Guide _Kommz_Gamer.html"],
    }
    
    # 2. IMPORTANT : On récupère le nom du fichier ici
    candidates = files.get(name) or []
    filename = None
    try:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        folder_web = os.path.join(base_dir, "web")
        for cand in candidates:
            cand_path = os.path.join(folder_web, cand)
            if os.path.exists(cand_path):
                filename = cand
                break
    except Exception:
        filename = candidates[0] if candidates else None
    
    # 3. On vérifie si on a trouvé un fichier
    if filename:
        try:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            folder_web = os.path.join(base_dir, "web")
            return send_from_directory(folder_web, filename)
        except Exception as e:
            return f"Erreur technique : {str(e)}"
            
    return "Guide introuvable (Nom incorrect)."

@app.route('/guide/open/<name>')
def open_guide_window(name):
    """Ouvre le guide dans une nouvelle fenetre APP (pywebview) au lieu du navigateur."""
    import webview
    
    # Titre de la fenêtre selon le guide
    titles = {
        "streamer": "Guide Streamer - Studio Edition",
        "general": "Manuel Utilisateur Complet",
    }
    window_title = titles.get(name, "Guide Kommz")
    
    # L'URL locale interne
    url = f"http://127.0.0.1:{VTP_CORE_PORT}/guide/view/{name}"
    
    # ON CRÉE UNE NOUVELLE FENÊTRE "NATIVE"
    webview.create_window(
        title=window_title,
        url=url,
        width=1000,      # Largeur confortable pour lire
        height=800,      # Hauteur
        resizable=True,  # L'utilisateur peut agrandir
        min_size=(800, 600),
        background_color='#09090b' # Fond noir pour éviter le flash blanc au chargement
    )
    
    return "OK"

@app.route("/remote")
def remote_page():
    global _mobile_connected; _mobile_connected = True
    return render_template("remote.html")

@app.route("/remote/qr.png")
def remote_qr_png():
    """QR PNG backend (fiable) pour accès mobile à /remote."""
    try:
        ip = get_local_ip()
        remote_url = f"http://{ip}:{VTP_CORE_PORT}/remote"
        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=8,
            border=0,
        )
        qr.add_data(remote_url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        resp = send_file(buf, mimetype="image/png")
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        return resp
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/remote/qr.svg")
def remote_qr_svg():
    """QR SVG backend (sans dépendance PIL) pour accès mobile à /remote."""
    try:
        from qrcode.image.svg import SvgImage
        ip = get_local_ip()
        remote_url = f"http://{ip}:{VTP_CORE_PORT}/remote"
        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=8,
            border=0,
            image_factory=SvgImage,
        )
        qr.add_data(remote_url)
        qr.make(fit=True)
        img = qr.make_image()
        buf = io.BytesIO()
        img.save(buf)
        buf.seek(0)
        resp = send_file(buf, mimetype="image/svg+xml")
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        return resp
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# --- SOUS-TITRES SSE + VTT ---

@app.route('/subs/stream')
def subs_sse_stream():
    import json as _json
    def generate():
        import time as _time
        last_key = ""
        while True:
            try:
                _time.sleep(0.35)
                recent = [x for x in subs_buffer
                          if (_time.time() - float(x.get("timestamp", 0) or 0)) < 10.0]
                if not recent:
                    yield "data: {}\n\n"
                    continue
                last = recent[-1]
                lang = str(last.get("lang", "") or "")
                is_ally = "ALLI\u00c9" in lang or "ALLY" in lang
                role = "SYS" if "SYS" in lang else ("ALLY" if is_ally else "USER")
                txt = str(last.get("text", "") or "").strip()
                key = role + "|" + txt
                if key != last_key and txt:
                    last_key = key
                    payload = _json.dumps({
                        "role": role,
                        "text": txt,
                        "user_color": AUDIO_CONFIG.get("user_overlay_color", "#00FFFF"),
                        "ally_color": AUDIO_CONFIG.get("ally_overlay_color", "#FFFF00"),
                    })
                    yield "data: " + payload + "\n\n"
                else:
                    yield ": keep-alive\n\n"
            except GeneratorExit:
                break
            except Exception:
                yield ": error\n\n"
    from flask import Response as _Resp
    resp = _Resp(generate(), mimetype="text/event-stream")
    resp.headers["Cache-Control"] = "no-cache"
    resp.headers["X-Accel-Buffering"] = "no"
    return resp


@app.route('/subs/live.vtt')
def subs_live_vtt():
    import time as _time
    recent = [x for x in subs_buffer
              if (_time.time() - float(x.get("timestamp", 0) or 0)) < 10.0]
    if not recent:
        return "WEBVTT\n\n", 200, {"Content-Type": "text/vtt; charset=utf-8"}
    last = recent[-1]
    lang = str(last.get("lang", "") or "")
    is_ally = "ALLI\u00c9" in lang or "ALLY" in lang
    role = "SYS" if "SYS" in lang else ("ALLY" if is_ally else "USER")
    txt = str(last.get("text", "") or "").strip()
    vtt = "WEBVTT\n\n1\n00:00:00.000 --> 00:00:06.000\n<v " + role + ">" + txt + "\n"
    return vtt, 200, {"Content-Type": "text/vtt; charset=utf-8"}

@app.route('/')
def index():
    resp = send_from_directory(WEB_DIR, "index.html")
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    return resp

@app.route('/favicon.ico')
def favicon():
    import os
    ico = os.path.join(WEB_DIR, 'favicon.ico')
    if os.path.isfile(ico):
        return send_from_directory(WEB_DIR, 'favicon.ico')
    return '', 204

@app.route('/<path:path>')
def serve_static(path): return send_from_directory(WEB_DIR, path)


# Configuration globale moteur/voix
@app.route("/config/full", methods=["POST"])
def set_full_config():
    d = request.get_json()
    global AUDIO_CONFIG
    
    # 1. Moteur & Langue
    requested_engine = d.get("engine")
    if requested_engine == "KOMMZ_VOICE" and not CLOUD_FEATURES_ENABLED:
        AUDIO_CONFIG["tts_engine"] = "WINDOWS"
        save_settings()
        return jsonify({
            "ok": False,
            "error": "CLOUD_DISABLED",
            "message": "Kommz Voice Cloud est désactivé en édition Community."
        }), 403
    if requested_engine == "KOMMZ_VOICE" and not has_voice_license():
        AUDIO_CONFIG["tts_engine"] = "WINDOWS"
        save_settings()
        return jsonify({
            "ok": False,
            "error": "VOICE_LICENSE_REQUIRED",
            "message": "Licence Voice requise pour activer Kommz Voice."
        }), 403
    if requested_engine:
        AUDIO_CONFIG["tts_engine"] = requested_engine
    
    # 2. Edge
    if d.get("edge_voice"): 
        AUDIO_CONFIG["edge_voice"] = d.get("edge_voice")
        if 'app_state' in globals():
            app_state["windows_voice_name"] = d.get("edge_voice")
    
    save_settings()
    stealth_print("Configuration generale sauvegardee.")
    return jsonify({"ok": True})
    
    
@app.route("/config/kommz", methods=["POST"])
def set_kommz_config():
    try:
        d = request.get_json() or {}
        global AUDIO_CONFIG
        if not CLOUD_FEATURES_ENABLED:
            AUDIO_CONFIG["tts_engine"] = "WINDOWS"
            save_settings()
            return jsonify({
                "ok": False,
                "error": "CLOUD_DISABLED",
                "message": "Configuration cloud désactivée en édition Community."
            }), 403
        if not has_voice_license():
            AUDIO_CONFIG["tts_engine"] = "WINDOWS"
            save_settings()
            return jsonify({
                "ok": False,
                "error": "VOICE_LICENSE_REQUIRED",
                "message": "Licence Voice requise."
            }), 403
        
        if "url" in d:
            AUDIO_CONFIG["kommz_api_url"] = str(d["url"] or "").strip()
        if "synthesis_url" in d:
            AUDIO_CONFIG["kommz_synthesis_url"] = str(d["synthesis_url"] or "").strip()
        if "synth_url" in d:
            AUDIO_CONFIG["kommz_synthesis_url"] = str(d["synth_url"] or "").strip()
        if "key" in d:
            AUDIO_CONFIG["kommz_api_key"] = str(d["key"] or "").strip()

        # Compat UI: accepte plusieurs noms de champs pour l'ID voix.
        incoming_id = (
            d.get("id")
            or d.get("voice_id")
            or d.get("client_id")
            or d.get("kommz_id")
        )
        if incoming_id is not None:
            AUDIO_CONFIG["kommz_client_id"] = str(incoming_id or "").strip()
            if AUDIO_CONFIG["kommz_client_id"]:
                AUDIO_CONFIG["voice_active_id"] = AUDIO_CONFIG["kommz_client_id"]

        if "mode" in d: AUDIO_CONFIG["kommz_model_mode"] = d["mode"]
        if "speed" in d: AUDIO_CONFIG["kommz_speed"] = float(d["speed"])
        if "temp" in d: AUDIO_CONFIG["kommz_temp"] = float(d["temp"])
        if "xtts_preset" in d: AUDIO_CONFIG["kommz_xtts_preset"] = str(d.get("xtts_preset") or "stable").strip().lower()
        if "top_k" in d: AUDIO_CONFIG["kommz_top_k"] = int(d["top_k"])
        if "top_p" in d: AUDIO_CONFIG["kommz_top_p"] = float(d["top_p"])
        if "repetition_penalty" in d: AUDIO_CONFIG["kommz_repetition_penalty"] = float(d["repetition_penalty"])
        if "length_penalty" in d: AUDIO_CONFIG["kommz_length_penalty"] = float(d["length_penalty"])
        if "enable_text_splitting" in d: AUDIO_CONFIG["kommz_enable_text_splitting"] = _to_bool(d.get("enable_text_splitting"), True)
        if "gpt_cond_len" in d: AUDIO_CONFIG["kommz_gpt_cond_len"] = int(d["gpt_cond_len"])
        if "gpt_cond_chunk_len" in d: AUDIO_CONFIG["kommz_gpt_cond_chunk_len"] = int(d["gpt_cond_chunk_len"])
        if "max_ref_len" in d: AUDIO_CONFIG["kommz_max_ref_len"] = int(d["max_ref_len"])
        if "sound_norm_refs" in d: AUDIO_CONFIG["kommz_sound_norm_refs"] = _to_bool(d.get("sound_norm_refs"), False)
        if "gpt_style_to_xtts_fr" in d:
            AUDIO_CONFIG["gpt_style_to_xtts_fr"] = _to_bool(d.get("gpt_style_to_xtts_fr"), False)
        if "gpt_api_url" in d:
            AUDIO_CONFIG["gpt_api_url"] = str(d.get("gpt_api_url") or "").strip()
        if "gpt_ref_audio_path" in d:
            AUDIO_CONFIG["gpt_ref_audio_path"] = str(d.get("gpt_ref_audio_path") or "").strip()
        if "gpt_prompt_text" in d:
            AUDIO_CONFIG["gpt_prompt_text"] = str(d.get("gpt_prompt_text") or "").strip()
        if "gpt_prompt_lang" in d:
            AUDIO_CONFIG["gpt_prompt_lang"] = str(d.get("gpt_prompt_lang") or "").strip().lower()
        if "gpt_style_text" in d:
            AUDIO_CONFIG["gpt_style_text"] = str(d.get("gpt_style_text") or "").strip()
        if "gpt_style_text_lang" in d:
            AUDIO_CONFIG["gpt_style_text_lang"] = str(d.get("gpt_style_text_lang") or "").strip().lower()
        if "hybrid_rts_preset" in d:
            preset = str(d.get("hybrid_rts_preset") or "fast").strip().lower()
            if preset not in {"fast", "quality"}:
                preset = "fast"
            AUDIO_CONFIG["hybrid_rts_preset"] = preset
            AUDIO_CONFIG["hybrid_fast_rts"] = (preset == "fast")
        if "quality_preset" in d:
            _apply_quality_preset(d.get("quality_preset"), emit_log=True)
        if "expressive_sounds_enabled" in d:
            AUDIO_CONFIG["expressive_sounds_enabled"] = _to_bool(d.get("expressive_sounds_enabled"), True)
        if "expressive_profile" in d:
            profile = str(d.get("expressive_profile") or "gaming").strip().lower()
            AUDIO_CONFIG["expressive_profile"] = profile if profile in {"gaming", "pro", "roleplay"} else "gaming"
        if "expressive_transcript_mode" in d:
            transcript_mode = str(d.get("expressive_transcript_mode") or "keep").strip().lower()
            AUDIO_CONFIG["expressive_transcript_mode"] = transcript_mode if transcript_mode in {"keep", "ignore"} else "keep"
        if "expressive_tts_mode" in d:
            tts_mode = str(d.get("expressive_tts_mode") or "styled").strip().lower()
            AUDIO_CONFIG["expressive_tts_mode"] = tts_mode if tts_mode in {"styled", "neutral"} else "styled"
        if "expressive_intensity_mode" in d:
            intensity_mode = str(d.get("expressive_intensity_mode") or "auto").strip().lower()
            AUDIO_CONFIG["expressive_intensity_mode"] = intensity_mode if intensity_mode in {"auto", "soft", "medium", "strong"} else "auto"
        if "expressive_noise_mode" in d:
            noise_mode = str(d.get("expressive_noise_mode") or "smart").strip().lower()
            AUDIO_CONFIG["expressive_noise_mode"] = noise_mode if noise_mode in {"smart", "keep", "clean"} else "smart"
        if "expressive_xtts_mode" in d:
            xtts_mode = str(d.get("expressive_xtts_mode") or "auto").strip().lower()
            AUDIO_CONFIG["expressive_xtts_mode"] = xtts_mode if xtts_mode in {"auto", "styled", "neutral"} else "auto"
        if "expressive_hybrid_mode" in d:
            hybrid_mode = str(d.get("expressive_hybrid_mode") or "auto").strip().lower()
            AUDIO_CONFIG["expressive_hybrid_mode"] = hybrid_mode if hybrid_mode in {"auto", "styled", "neutral"} else "auto"
        if "expressive_stability_mode" in d:
            stability_mode = str(d.get("expressive_stability_mode") or "balanced").strip().lower()
            AUDIO_CONFIG["expressive_stability_mode"] = stability_mode if stability_mode in {"reactive", "balanced", "stable"} else "balanced"
        if "expressive_fallback_guard" in d:
            AUDIO_CONFIG["expressive_fallback_guard"] = _to_bool(d.get("expressive_fallback_guard"), True)
        if "expressive_ptt_mode" in d:
            ptt_mode = str(d.get("expressive_ptt_mode") or "full").strip().lower()
            AUDIO_CONFIG["expressive_ptt_mode"] = ptt_mode if ptt_mode in {"full", "safe", "neutral"} else "full"
        if "expressive_rts_mode" in d:
            rts_mode = str(d.get("expressive_rts_mode") or "safe").strip().lower()
            AUDIO_CONFIG["expressive_rts_mode"] = rts_mode if rts_mode in {"full", "safe", "neutral"} else "safe"
        if "whisper_api_url" in d:
            AUDIO_CONFIG["whisper_api_url"] = str(d.get("whisper_api_url") or "").strip()
        if "whisper_model" in d:
            whisper_model = str(d.get("whisper_model") or DEFAULT_KOMMZ_WHISPER_MODEL).strip().lower()
            AUDIO_CONFIG["whisper_model"] = "large-v3" if whisper_model == "large" else whisper_model
        
        AUDIO_CONFIG["tts_engine"] = "KOMMZ_VOICE"
        prewarm_kommz_xtts(force=False)
        
        save_settings()
        stealth_print(
            f"🎙️ Kommz Configuré (ID: {AUDIO_CONFIG['kommz_client_id']}) "
            f"| Clone URL: {_resolve_kommz_voice_endpoint()} "
            f"| Synthesis URL: {_resolve_kommz_synthesis_base() or '(non définie)'}"
        )
        hybrid_status = _get_hybrid_fr_config_status()
        return jsonify({
            "ok": True,
            "saved_id": AUDIO_CONFIG.get("kommz_client_id", ""),
            "saved_key_present": bool(str(AUDIO_CONFIG.get("kommz_api_key", "") or "").strip()),
            "gpt_style_to_xtts_fr": bool(AUDIO_CONFIG.get("gpt_style_to_xtts_fr", False)),
            "hybrid_rts_preset": _get_hybrid_rts_preset(),
            "quality_preset": _normalize_quality_preset(AUDIO_CONFIG.get("quality_preset", "balanced")),
            "hybrid_fr_ready": bool(hybrid_status.get("ready")),
            "hybrid_fr_message": hybrid_status.get("message", ""),
            "hybrid_fr_ref_name": hybrid_status.get("ref_name", ""),
            "hybrid_fr_ref_exists": bool(hybrid_status.get("ref_exists")),
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/config/kommz/autofill-prompt", methods=["POST"])
def kommz_autofill_prompt():
    """
    Auto-remplit gpt_prompt_text à partir de la référence audio:
    1) cherche dans les fichiers .list existants
    2) fallback Whisper local (fasterwhisper_asr.py)
    """
    try:
        d = request.get_json() or {}
        ref_path = str(d.get("gpt_ref_audio_path") or AUDIO_CONFIG.get("gpt_ref_audio_path") or "").strip()
        lang_hint = str(d.get("gpt_prompt_lang") or AUDIO_CONFIG.get("gpt_prompt_lang") or "ja").strip().lower()
        use_whisper = _to_bool(d.get("use_whisper", True), True)

        if not ref_path:
            return jsonify({"ok": False, "error": "gpt_ref_audio_path manquant"}), 400
        if not os.path.exists(ref_path):
            return jsonify({"ok": False, "error": "Fichier de référence introuvable"}), 404

        text, lang, src = _find_list_text_for_ref(ref_path)
        source = "list"
        if not text and use_whisper:
            try:
                text, lang, used_url = _transcribe_ref_via_modal_whisper(ref_path, lang_hint=lang_hint)
                source = "Whisper Modal"
                src = used_url
            except Exception as modal_err:
                stealth_print(f"⚠️ Auto prompt Whisper Modal indisponible, fallback local: {modal_err}")
                text, lang = _run_whisper_for_ref(ref_path, lang_hint=lang_hint)
                source = "Whisper local"
                src = "fasterwhisper_asr.py"

        if text:
            txt_u = str(text).strip().upper()
            if txt_u.startswith("TODO_") or txt_u == "TODO_TRANSCRIPTION_EXACTE":
                text = ""

        if not text:
            return jsonify({"ok": False, "error": "Impossible d'auto-remplir le prompt texte"}), 404

        AUDIO_CONFIG["gpt_ref_audio_path"] = ref_path
        AUDIO_CONFIG["gpt_prompt_text"] = text
        if lang:
            AUDIO_CONFIG["gpt_prompt_lang"] = str(lang).lower()
        save_settings()

        return jsonify({
            "ok": True,
            "gpt_prompt_text": AUDIO_CONFIG.get("gpt_prompt_text", ""),
            "gpt_prompt_lang": AUDIO_CONFIG.get("gpt_prompt_lang", lang_hint),
            "source": source,
            "source_detail": src,
        })
    except subprocess.TimeoutExpired:
        return jsonify({"ok": False, "error": "Timeout Whisper (trop long)"}), 504
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/dialog/select-audio-file", methods=["GET"])
def dialog_select_audio_file():
    """
    Ouvre un sélecteur de fichier audio Windows et retourne le chemin choisi.
    Utile pour remplir gpt_ref_audio_path sans copier/coller.
    """
    try:
        init_dir = str(request.args.get("initial_dir") or "").strip()
        if not init_dir:
            init_dir = str(Path.cwd())
        if not os.path.isdir(init_dir):
            init_dir = str(Path.cwd())

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        file_path = filedialog.askopenfilename(
            parent=root,
            title="Sélectionner un audio de référence GPT",
            initialdir=init_dir,
            filetypes=[
                ("Audio files", "*.wav *.mp3 *.flac *.m4a *.ogg *.webm *.aac"),
                ("WAV", "*.wav"),
                ("All files", "*.*"),
            ],
        )
        try:
            root.destroy()
        except Exception:
            pass

        if not file_path:
            return jsonify({"ok": False, "cancelled": True, "path": ""})

        AUDIO_CONFIG["gpt_ref_audio_path"] = file_path
        save_settings()
        return jsonify({"ok": True, "path": file_path})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

# ✅ OPTIMIZED: Version améliorée de kommz_tts_generator avec buffering et TTFB
def kommz_tts_generator(text):
    import requests
    import os
    from datetime import datetime

    audio_source_bytes = None
    source_mode = "none"
    client_id_cfg = str(AUDIO_CONFIG.get("kommz_client_id", "") or "").strip()
    api_key_cfg = str(AUDIO_CONFIG.get("kommz_api_key", "") or "").strip()
    target_lang = AUDIO_CONFIG.get("target_lang", "en").lower()
    xtts_lang = _normalize_xtts_request_lang(target_lang, text)
    tts_speed = float(AUDIO_CONFIG.get("kommz_speed", 1.0) or 1.0)
    tts_temp = float(AUDIO_CONFIG.get("kommz_temp", 0.7) or 0.7)
    tts_top_k = max(1, min(200, int(AUDIO_CONFIG.get("kommz_top_k", 60) or 60)))
    tts_top_p = max(0.1, min(1.0, float(AUDIO_CONFIG.get("kommz_top_p", 0.90) or 0.90)))
    tts_repetition_penalty = max(1.0, min(10.0, float(AUDIO_CONFIG.get("kommz_repetition_penalty", 2.2) or 2.2)))
    tts_length_penalty = max(0.1, min(5.0, float(AUDIO_CONFIG.get("kommz_length_penalty", 1.0) or 1.0)))
    tts_enable_split = bool(AUDIO_CONFIG.get("kommz_enable_text_splitting", True))
    tts_gpt_cond_len = max(1, min(30, int(AUDIO_CONFIG.get("kommz_gpt_cond_len", 12) or 12)))
    tts_gpt_cond_chunk_len = max(1, min(10, int(AUDIO_CONFIG.get("kommz_gpt_cond_chunk_len", 4) or 4)))
    tts_max_ref_len = max(3, min(20, int(AUDIO_CONFIG.get("kommz_max_ref_len", 10) or 10)))
    tts_sound_norm_refs = bool(AUDIO_CONFIG.get("kommz_sound_norm_refs", False))
    base_url_modal = _resolve_kommz_voice_endpoint()
    synth_base = _resolve_kommz_synthesis_base()
    hybrid_enabled = _to_bool(AUDIO_CONFIG.get("gpt_style_to_xtts_fr", False), False) and _is_hybrid_supported_target_lang(target_lang)
    turbo_mode = _is_turbo_mode_active()
    if turbo_mode:
        tts_enable_split = True
    if xtts_lang != target_lang:
        stealth_print(f"ℹ️ XTTS langue adaptée: {target_lang} -> {xtts_lang}")

    hybrid_cache_key = "|".join([
        xtts_lang,
        str(AUDIO_CONFIG.get("gpt_api_url", "") or "").strip(),
        str(AUDIO_CONFIG.get("gpt_ref_audio_path", "") or "").strip().lower(),
        str(AUDIO_CONFIG.get("gpt_prompt_text", "") or "").strip(),
        str(AUDIO_CONFIG.get("gpt_style_text", "") or "").strip(),
        "fast" if (hybrid_enabled and turbo_mode and _get_hybrid_rts_preset() == "fast") else "quality",
    ])

    def _try_voice_id_api():
        if client_id_cfg and api_key_cfg and synth_base:
            synth_candidates = _build_kommz_synthesis_candidates(synth_base)
            stealth_print(f"🎯 Mode voice_id forcé actif: {client_id_cfg}")
            last_api_err = ""
            last_api_status = 0
            last_api_url = ""
            attempt_notes = []
            trial_quota_hit = False
            for idx, api_url in enumerate(synth_candidates, start=1):
                try:
                    stealth_print(f"📤 API synthesis -> {api_url} ({idx}/{len(synth_candidates)})")
                    last_api_url = api_url
                    r = _HTTP.post(
                        api_url,
                        headers={
                            "Authorization": f"Bearer {api_key_cfg}",
                            "Content-Type": "application/json",
                        },
                        json={
                            "text": text,
                            "voice_id": client_id_cfg,
                            "speed": tts_speed,
                            "temperature": tts_temp,
                            "top_k": tts_top_k,
                            "top_p": tts_top_p,
                            "repetition_penalty": tts_repetition_penalty,
                            "length_penalty": tts_length_penalty,
                            "enable_text_splitting": tts_enable_split,
                            "gpt_cond_len": tts_gpt_cond_len,
                            "gpt_cond_chunk_len": tts_gpt_cond_chunk_len,
                            "max_ref_len": tts_max_ref_len,
                            "sound_norm_refs": tts_sound_norm_refs,
                            "language": xtts_lang,
                        },
                        timeout=(4, 60) if turbo_mode else 120,
                    )
                    if not r.ok:
                        last_api_status = int(r.status_code or 0)
                        body = _repair_display_text((r.text or "")[:240])
                        if _looks_like_cloud_trial_limit(r.status_code, body):
                            last_api_err = "Quota essai voice_id atteint ou expiré"
                            trial_quota_hit = True
                        else:
                            last_api_err = _repair_display_text(f"HTTP {r.status_code} {body}")
                        attempt_notes.append(f"{idx}:{_short_runtime_url(api_url, 72)}=HTTP{r.status_code}")
                        continue

                    ctype = (r.headers.get("Content-Type") or "").lower()
                    if "audio/wav" in ctype or "audio/x-wav" in ctype:
                        attempt_notes.append(f"{idx}:{_short_runtime_url(api_url, 72)}=OK")
                        stealth_print("✅ Voice_id forcé OK (audio direct).")
                        _set_pipeline_runtime(
                            hybrid_engine="Bypass Hybrid",
                            hybrid_detail="voice_id prioritaire",
                            tts_engine="Kommz Voice API",
                            tts_route="voice_id / audio direct",
                        )
                        return r.content

                    payload = r.json()
                    audio_url = (payload or {}).get("audio_url", "")
                    if not audio_url:
                        last_api_err = "audio_url manquante dans réponse /v1/synthesis"
                        attempt_notes.append(f"{idx}:{_short_runtime_url(api_url, 72)}=NO_AUDIO_URL")
                        continue
                    dl = _HTTP.get(audio_url, timeout=(4, 60) if turbo_mode else 120)
                    if not dl.ok:
                        last_api_err = f"download audio_url HTTP {dl.status_code}"
                        attempt_notes.append(f"{idx}:{_short_runtime_url(api_url, 72)}=DL_HTTP{dl.status_code}")
                        continue
                    attempt_notes.append(f"{idx}:{_short_runtime_url(api_url, 72)}=OK_URL")
                    stealth_print("✅ Voice_id forcé OK (audio_url).")
                    _set_pipeline_runtime(
                        hybrid_engine="Bypass Hybrid",
                        hybrid_detail="voice_id prioritaire",
                        tts_engine="Kommz Voice API",
                        tts_route="voice_id / audio_url",
                    )
                    return dl.content
                except Exception as api_ex:
                    last_api_err = _repair_display_text(str(api_ex))
                    attempt_notes.append(f"{idx}:{_short_runtime_url(api_url, 72)}=ERR")
                    continue

            stealth_print_rl(
                "voice_id_forced_fallback",
                f"⚠️ Voice_id forcé indisponible, fallback clone. Détail: {last_api_err}",
                cooldown=30.0,
            )
            _register_tts_fallback(
                "VOICE_ID_TRIAL_QUOTA" if trial_quota_hit else "VOICE_ID_UNAVAILABLE",
                last_api_err or "voice_id fallback clone",
                endpoint=_short_runtime_url(last_api_url or synth_base, 120),
                http_status=last_api_status,
                attempts=" | ".join(attempt_notes[-6:]),
            )
            return None

        if client_id_cfg and api_key_cfg and not synth_base:
            stealth_print("⚠️ Voice_id forcé ignoré: Synthesis URL non configurée.")
            stealth_print("ℹ️ Définir kommz_synthesis_url (ou env KOMMZ_SYNTHESIS_URL) vers votre serveur web /v1/synthesis.")
            _register_tts_fallback(
                "VOICE_ID_URL_MISSING",
                "synth_base vide",
            )
        return None

    # V5: si un voice_id est configuré, on le tente en priorité stricte
    # avant Hybrid/clone pour respecter la voix demandée par l'utilisateur.
    if client_id_cfg and api_key_cfg:
        voice_audio = _try_voice_id_api()
        if voice_audio:
            yield voice_audio
            return

    # Sur FR/EN/JA/KO/ZH, on privilégie d'abord Hybrid pour le timbre.
    # Si GPT échoue, on repasse automatiquement sur voice_id API.
    if hybrid_enabled:
        hybrid_rts_preset = _get_hybrid_rts_preset()
        hybrid_fast_mode = turbo_mode and hybrid_rts_preset == "fast"
        try:
            style_wav = None
            if hybrid_fast_mode:
                now_ts = time.time()
                cached = _hybrid_style_ref_cache.get("bytes")
                cached_lang = str(_hybrid_style_ref_cache.get("lang") or "")
                cached_key = str(_hybrid_style_ref_cache.get("key") or "")
                cached_ts = float(_hybrid_style_ref_cache.get("ts") or 0.0)
                if cached and cached_lang == xtts_lang and cached_key == hybrid_cache_key and (now_ts - cached_ts) <= 150.0:
                    style_wav = cached
                    _set_hybrid_fast_runtime(
                        fast_path=True,
                        cache_hot=True,
                        cache_age_seconds=(now_ts - cached_ts),
                        detail=f"Cache Hybrid réutilisé · {target_lang.upper()}",
                    )
                    stealth_print(f"🧪 Hybrid cache réutilisé ({target_lang.upper()}).")
                    _set_pipeline_runtime(
                        hybrid_engine="GPT-SoVITS Hybrid",
                        hybrid_detail=f"Référence cache · {target_lang.upper()}",
                    )

            if style_wav is None:
                style_wav = _gpt_style_to_xtts_ref_bytes(text, fast_mode=hybrid_fast_mode)
                if hybrid_fast_mode and style_wav:
                    _hybrid_style_ref_cache["bytes"] = style_wav
                    _hybrid_style_ref_cache["lang"] = xtts_lang
                    _hybrid_style_ref_cache["key"] = hybrid_cache_key
                    _hybrid_style_ref_cache["ts"] = time.time()
                    _set_hybrid_fast_runtime(
                        fast_path=True,
                        cache_hot=False,
                        cache_age_seconds=0,
                        detail=f"Référence Hybrid régénérée · {target_lang.upper()}",
                    )

            if style_wav:
                audio_source_bytes = style_wav
                source_mode = "gpt_style_cache" if hybrid_fast_mode else "gpt_style_ref"
                if not hybrid_fast_mode:
                    _set_hybrid_fast_runtime(
                        fast_path=False,
                        cache_hot=False,
                        cache_age_seconds=-1,
                        detail=f"Hybrid qualité actif · {target_lang.upper()}",
                    )
                stealth_print(f"🧪 Hybrid prioritaire actif ({target_lang.upper()}): GPT-SoVITS -> XTTS")
                _set_pipeline_runtime(
                    hybrid_detail=f"Timbre prioritaire · {target_lang.upper()}",
                )
        except Exception as hy_err:
            stealth_print(f"⚠️ Hybrid GPT->XTTS indisponible, fallback voice_id/local: {hy_err}")
            _set_hybrid_fast_runtime(
                fast_path=hybrid_fast_mode,
                cache_hot=False,
                cache_age_seconds=-1,
                detail=f"Fallback Hybrid · {_short_runtime_text(hy_err, 96)}",
            )
            _set_pipeline_runtime(
                hybrid_engine="Fallback",
                hybrid_detail=f"GPT indisponible · {_short_runtime_text(hy_err, 96)}",
            )
            voice_audio = _try_voice_id_api()
            if voice_audio:
                yield voice_audio
                return
    else:
        _set_hybrid_fast_runtime(
            fast_path=False,
            cache_hot=False,
            cache_age_seconds=-1,
            detail="Hybrid non actif · voice_id / clone direct",
        )
        _set_pipeline_runtime(
            hybrid_engine="Bypass Hybrid",
            hybrid_detail="voice_id / clone direct prioritaire",
        )
        voice_audio = _try_voice_id_api()
        if voice_audio:
            yield voice_audio
            return

    if audio_source_bytes is None:
        if PRESET_VOICE_BUFFER is not None:
            stealth_print("🎛️ Référence preset utilisée (fallback).")
            audio_source_bytes = PRESET_VOICE_BUFFER
            source_mode = "preset_buffer"
        elif LAST_USER_AUDIO_BUFFER is not None:
            stealth_print("🎤 Micro Joueur utilisé (Mode Normal).")
            audio_source_bytes = LAST_USER_AUDIO_BUFFER
            source_mode = "micro_buffer"
        else:
            stealth_print("⚠️ Kommz Voice ignoré: aucune référence audio en RAM (micro/preset).")
            stealth_print("ℹ️ Fallback reason: NO_REFERENCE_AUDIO_BUFFER")
            _register_tts_fallback("NO_REFERENCE_AUDIO_BUFFER", "reference audio buffer absent")
            return

    stealth_print(
        f"🧭 TTS route | engine={AUDIO_CONFIG.get('tts_engine','WINDOWS')} "
        f"| source={source_mode} | client_id={'set' if client_id_cfg else 'empty'} "
        f"| api_key={'set' if api_key_cfg else 'empty'}"
    )
    route_labels = {
        "gpt_style_ref": "Clone direct · référence Hybrid",
        "gpt_style_cache": "Clone direct · cache Hybrid rapide",
        "micro_buffer": "Clone direct · buffer micro",
        "preset_buffer": "Clone direct · preset voix",
    }
    _set_pipeline_runtime(
        tts_engine="XTTS Modal",
        tts_route=route_labels.get(source_mode, f"Clone direct · {source_mode}") + (" · turbo" if turbo_mode else ""),
    )
    if client_id_cfg:
        stealth_print("ℹ️ Note: clone direct en fallback (voice_id indisponible/non configuré).")

    try:
        if not base_url_modal:
            stealth_print("⚠️ Kommz Voice ignoré: URL Modal vide.")
            stealth_print("ℹ️ Fallback reason: EMPTY_MODAL_URL")
            _register_tts_fallback(
                "EMPTY_MODAL_URL",
                "base_url_modal vide",
                endpoint=_short_runtime_url(_resolve_kommz_voice_endpoint(), 120),
            )
            return
        candidate_urls = _build_kommz_generate_candidates(base_url_modal)
        if hybrid_enabled and turbo_mode and _get_hybrid_rts_preset() == "fast":
            candidate_urls = candidate_urls[:2]
        if not candidate_urls:
            stealth_print("⚠️ Kommz Voice ignoré: aucune URL Modal candidate.")
            stealth_print("ℹ️ Fallback reason: NO_MODAL_CANDIDATE_URL")
            _register_tts_fallback(
                "NO_MODAL_CANDIDATE_URL",
                "candidate_urls vide",
                endpoint=_short_runtime_url(base_url_modal, 120),
            )
            return
        prewarm_kommz_xtts(force=False, timeout_connect=2 if turbo_mode else 3, timeout_read=10 if turbo_mode else 20)

        files = {'speaker_wav': ('audio.wav', audio_source_bytes, 'audio/wav')}
        data = {
            'text': text,
            'language': xtts_lang,
            'speed': tts_speed,
            'reference_text': "Mode Normal.",
            'temperature': tts_temp,
            'top_k': tts_top_k,
            'top_p': tts_top_p,
            'repetition_penalty': tts_repetition_penalty,
            'length_penalty': tts_length_penalty,
            'enable_text_splitting': "1" if tts_enable_split else "0",
            'gpt_cond_len': tts_gpt_cond_len,
            'gpt_cond_chunk_len': tts_gpt_cond_chunk_len,
            'max_ref_len': tts_max_ref_len,
            'sound_norm_refs': "1" if tts_sound_norm_refs else "0",
        }

        response = None
        used_url = ""
        last_err = ""
        attempt_notes = []
        for idx, url_modal in enumerate(candidate_urls, start=1):
            try:
                stealth_print(f"📤 Envoi requête vers {url_modal}... ({idx}/{len(candidate_urls)})")
                if hybrid_enabled and turbo_mode and _get_hybrid_rts_preset() == "fast":
                    req_timeout = (3, 35)
                else:
                    req_timeout = (5, 180) if turbo_mode else 300
                r = _HTTP.post(url_modal, files=files, data=data, timeout=req_timeout)
                stealth_print(f"📥 Réponse reçue, status: {r.status_code}")
                if r.status_code == 200:
                    response = r
                    used_url = url_modal
                    attempt_notes.append(f"{idx}:{_short_runtime_url(url_modal, 72)}=OK")
                    break
                body = r.text[:300] if r.text else ""
                last_err = f"HTTP {r.status_code} {body}"
                attempt_notes.append(f"{idx}:{_short_runtime_url(url_modal, 72)}=HTTP{r.status_code}")
                # 400/404/405 => on teste URL suivante (souvent mauvais path worker)
                if r.status_code in (400, 404, 405):
                    continue
                # Autres codes: on garde quand même la réponse pour gestion existante.
                response = r
                used_url = url_modal
                break
            except Exception as ex_try:
                last_err = str(ex_try)
                attempt_notes.append(f"{idx}:{_short_runtime_url(url_modal, 72)}=ERR")
                continue

        if response is None:
            stealth_print(f"❌ Erreur Serveur: aucune URL Modal valide. Dernière erreur: {last_err}")
            stealth_print("ℹ️ Fallback reason: ALL_MODAL_ENDPOINTS_FAILED")
            _register_tts_fallback(
                "ALL_MODAL_ENDPOINTS_FAILED",
                str(last_err or ""),
                endpoint=_short_runtime_url(base_url_modal, 120),
                attempts=" | ".join(attempt_notes[-6:]),
            )
            return

        # Auto-réparation: si une variante a marché, on la mémorise.
        if used_url and used_url != base_url_modal:
            AUDIO_CONFIG["kommz_api_url"] = used_url
            save_settings()
            stealth_print(f"✅ URL Modal corrigée automatiquement: {used_url}")

        if response.status_code == 200:
            global _last_xtts_activity_ts
            _last_xtts_activity_ts = time.time()
            VOICE_CLOUD_LIMIT_STATE["reached"] = False
            VOICE_CLOUD_LIMIT_STATE["message"] = ""
            if _is_trial_voice_mode_enabled():
                # Suivi local du quota essai cloud basé sur la durée du WAV généré.
                used = int(AUDIO_CONFIG.get("trial_voice_seconds_used_local", 0) or 0)
                dur = _wav_duration_seconds(response.content)
                if dur <= 0:
                    # Fallback simple si la durée n'est pas lisible.
                    dur = max(1, int(len(text.split()) / 2.2))
                used = max(0, min(1800, used + dur))
                AUDIO_CONFIG["trial_voice_seconds_used_local"] = used
                remaining = max(0, 1800 - used)
                VOICE_CLOUD_LIMIT_STATE["remaining_seconds_local"] = remaining
                VOICE_CLOUD_LIMIT_STATE["message"] = f"Temps essai clonage restant: {remaining//60:02d}:{remaining%60:02d}"
                save_settings()
            # Debug audio: optionnel + nettoyage automatique pour éviter l'accumulation.
            # - save_debug_audio_files: False => aucune sauvegarde locale
            # - debug_audio_keep_last: nombre de fichiers debug à conserver (défaut: 2)
            try:
                if AUDIO_CONFIG.get("save_debug_audio_files", False):
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    filename = f"debug_audio_{timestamp}.wav"
                    with open(filename, "wb") as f:
                        f.write(response.content)
                    stealth_print(f"📁 Audio sauvegardé dans {filename}")

                keep_last = int(AUDIO_CONFIG.get("debug_audio_keep_last", 2) or 2)
                keep_last = max(0, keep_last)
                debug_files = [
                    fn for fn in os.listdir(".")
                    if fn.startswith("debug_audio_") and fn.endswith(".wav")
                ]
                debug_files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
                for old_file in debug_files[keep_last:]:
                    try:
                        os.remove(old_file)
                    except Exception:
                        pass
            except Exception as dbg_err:
                stealth_print(f"⚠️ Nettoyage debug_audio ignoré: {dbg_err}")

            yield response.content
        else:
            body = response.text[:2000] if response.text else ""
            stealth_print(f"❌ Erreur Serveur: {response.status_code} - {body[:200]}")
            if _looks_like_cloud_trial_limit(response.status_code, body):
                msg = "Quota essai Kommz Voice atteint (30 min). Passage automatique en voix Windows."
                VOICE_CLOUD_LIMIT_STATE["reached"] = True
                VOICE_CLOUD_LIMIT_STATE["message"] = msg
                AUDIO_CONFIG["trial_voice_seconds_used_local"] = 1800
                AUDIO_CONFIG["tts_engine"] = "WINDOWS"
                save_settings()
                add_subtitle("SYSTEM >> QUOTA ESSAI VOICE ATTEINT (30 MIN)", "SYS")
                stealth_print(f"⚠️ {msg}")
                stealth_print("ℹ️ Fallback reason: TRIAL_QUOTA_REACHED -> WINDOWS")
                _register_tts_fallback("TRIAL_QUOTA_REACHED", "quota essai 30m atteint")
            else:
                stealth_print(f"ℹ️ Fallback reason: HTTP_{response.status_code}")
                _register_tts_fallback(
                    "HTTP_ERROR",
                    f"HTTP_{response.status_code} {body[:140]}",
                    endpoint=_short_runtime_url(used_url or base_url_modal, 120),
                    http_status=response.status_code,
                    attempts=" | ".join(attempt_notes[-6:]),
                )

    except Exception as e:
        stealth_print(f"❌ Erreur lors de l'envoi : {e}")
        stealth_print("ℹ️ Fallback reason: EXCEPTION_DURING_KOMMZ_TTS")
        _register_tts_fallback(
            "EXCEPTION_DURING_KOMMZ_TTS",
            str(e),
            endpoint=_short_runtime_url(_resolve_kommz_voice_endpoint(), 120),
        )
        import traceback
        traceback.print_exc()

@app.route("/module/<name>/toggle", methods=["POST"])
def toggle_module(name):
    # Récupération de l'état (vrai/faux)
    data = request.json
    state = data.get("toggle", False)

    map_keys = {
        # --- Modules de base ---
        "seamless": "seamless_prefix_active",
        "smart": "smart_commands_active",
        "teamsync": "teamsync_ai_active",
        "turbo": "turbo_latency_active",
        "esport": "esport_mode_active",
        "stealth": "stealth_mode_active",
        "shadow": "shadow_ai_active",
        "autocontext": "auto_context_active",
        "autoupdate": "auto_update_active",
        "hybrid": "hybrid_activation_active",
        
        # --- Modules Titanium (Virgules bien présentes !) ---
        "tilt": "tilt_shield_active",
        "stream": "stream_connect_active",
        "macros": "tactical_macros_active",

        # --- Modules Streamer (Nouveaux) ---
        "polyglot": "polyglot_active",
        "privacy": "privacy_sentinel_active",
        "marker": "smart_marker_active",

        # --- Options d'affichage ---
        "show_own_subs": "show_own_subs_active",
        "show_ally_subs": "show_ally_subs_active",
        "bypass": "bypass_mode_active"
    }

    if name in map_keys:
        key = map_keys[name]
        AUDIO_CONFIG[key] = state  # Mise à jour mémoire
        runtime_names = {
            "seamless": "seamless",
            "smart": "smart",
            "teamsync": "teamsync",
            "turbo": "turbo",
            "esport": "esport",
            "stealth": "stealth",
            "shadow": "shadow",
            "autocontext": "autocontext",
            "autoupdate": "autoupdate",
            "hybrid": "hybrid",
            "tilt": "tilt",
            "stream": "stream",
            "macros": "macros",
            "polyglot": "polyglot",
            "privacy": "privacy",
            "marker": "marker",
        }
        if name == "esport":
            apply_esport_profile(force_log=True)
        elif name == "shadow":
            if state:
                warm_shadow_services_async("toggle")
            else:
                _clear_shadow_caches()
                stealth_print("👻 Shadow AI désactivé : caches vidés.")
        elif name == "polyglot" and not state:
            try:
                with open(POLYGLOT_OBS_FILE, "w", encoding="utf-8") as f:
                    f.write("")
            except Exception:
                pass
        if name in runtime_names:
            module_name = runtime_names[name]
            module_state, module_detail = _module_runtime_defaults(module_name, state)
            _set_module_runtime(module_name, module_state, module_detail)
        save_config()              # Sauvegarde JSON
        stealth_print(f"MODULE {name} -> {state}")
        return jsonify({"ok": True, "state": state})
    
    return jsonify({"ok": False})

@app.route("/hotkey/set", methods=["POST"])
def shk(): global CURRENT_HOTKEY; CURRENT_HOTKEY = request.get_json().get("key"); return jsonify({"ok": True})
@app.route("/hotkey/bypass/set", methods=["POST"])
def shkb(): global BYPASS_HOTKEY; BYPASS_HOTKEY = request.get_json().get("key"); return jsonify({"ok": True})
@app.route('/config/target', methods=['POST'])
def update_target_lang():
    # Déclaration Globales
    global CURRENT_TARGET_LANG, AUDIO_CONFIG, DG_ENGINE
    
    try:
        data = request.get_json()
        raw_lang = data.get('lang', 'EN').upper()
        
        # 1. MAPPING DEEPGRAM
        DEEPGRAM_MAP = {
            "EN": "en-US", "FR": "fr-FR", "ES": "es-ES", "DE": "de-DE",
            "IT": "it-IT", "PT": "pt-PT", "RU": "ru-RU", "JA": "ja-JP",
            "KO": "ko-KR", "ZH": "zh-CN", "TR": "tr-TR", "PL": "pl-PL",
            "NL": "nl-NL", "SV": "sv-SE", "UA": "uk-UA", "ID": "id-ID",
            "TH": "th-TH", "VN": "vi-VN", "IN": "hi-IN", "BR": "pt-BR"
        }
        
        old_deepgram_code = AUDIO_CONFIG.get("ally_recognition_lang", "en-US")
        new_deepgram_code = DEEPGRAM_MAP.get(raw_lang, "en-US")
        AUDIO_CONFIG["ally_recognition_lang"] = new_deepgram_code
        
        # 2. MAPPING DEEPL
        deepl_map = {
            "EN": "EN-US", "PT": "PT-PT", "UA": "UK", 
            "BR": "PT-BR", "IN": "HI", "VN": "VI", 
            "JP": "JA", "ZH": "ZH"
        }
        CURRENT_TARGET_LANG = deepl_map.get(raw_lang, raw_lang)
        AUDIO_CONFIG["target_lang"] = raw_lang 
        
        # 3. MAPPING EDGE
        gender_val = app_state.get("gender", "MALE")
        gender_key = "F" if gender_val == "FEMALE" else "M"
        
        new_voice = "en-US-ChristopherNeural"
        if raw_lang in EDGE_VOICE_MAP:
            new_voice = EDGE_VOICE_MAP[raw_lang].get(gender_key)
        elif raw_lang.lower() in EDGE_VOICE_MAP:
             new_voice = EDGE_VOICE_MAP[raw_lang.lower()].get(gender_key)
            
        if new_voice:
            AUDIO_CONFIG["edge_voice"] = new_voice
            app_state["windows_voice_name"] = new_voice

        hybrid_auto_enabled = _maybe_enable_hybrid_fr_default()
        
        save_settings()
        stealth_print(f"📱 LANGUE : {raw_lang} -> Reconnaissance [{new_deepgram_code}]")
        if hybrid_auto_enabled:
            stealth_print("🧪 Hybrid auto-activé après changement de langue.")
        
        # FIX REDEMARRAGE MOTEUR
        # On relance le thread Deepgram si le mode écoute est actif, même si la langue
        # ne change pas (sinon au redémarrage l'utilisateur doit "changer de langue" pour relancer).
        if bool(AUDIO_CONFIG.get("is_listening", True)):
            if new_deepgram_code != old_deepgram_code:
                stealth_print("🔄 Reboot Moteur Audio pour nouvelle langue...")
            else:
                stealth_print("🔄 Reboot Moteur Audio (resync) ...")
            if 'DG_ENGINE' in globals() and DG_ENGINE:
                # Reboot soft
                try:
                    DG_ENGINE.is_running = False
                    import time, threading
                    time.sleep(0.5)
                    
                    # On relance proprement
                    target_mic_id = AUDIO_CONFIG.get("game_input_device", 0)
                    DG_ENGINE = DeepgramEngine()
                    t = threading.Thread(target=DG_ENGINE.start_streaming, args=(target_mic_id,))
                    t.daemon = True
                    t.start()
                    stealth_print("✅ Moteur Relancé.")
                except Exception as ex_reboot:
                    stealth_print(f"⚠️ Erreur Reboot : {ex_reboot}")
        
        hybrid_status = _get_hybrid_fr_config_status()
        return jsonify({
            "ok": True,
            "voice": new_voice,
            "gpt_style_to_xtts_fr": bool(AUDIO_CONFIG.get("gpt_style_to_xtts_fr", False)),
            "hybrid_fr_ready": bool(hybrid_status.get("ready")),
            "hybrid_fr_message": hybrid_status.get("message", ""),
            "hybrid_fr_ref_name": hybrid_status.get("ref_name", ""),
            "hybrid_fr_ref_exists": bool(hybrid_status.get("ref_exists")),
        })

    except Exception as e:
        stealth_print(f"❌ Erreur Remote : {e}")
        return jsonify({"ok": False})

LISTEN_GAME_PRESETS = {
    "auto": {
        "label": "Auto (Detection intelligente V5.3)",
        "ally_voice_focus_mode": "auto",
        "ally_sentence_punct_min_words": 3,
        "ally_sentence_hard_flush_words": 7,
        "ally_tts_similarity_play_below": 0.94,
        "ally_tts_duplicate_window_s": 1.8,
        "ally_tts_force_min_chars": 8,
        "ally_tts_min_gap_s": 0.65,
        "ally_tts_short_merge_words": 3,
        "ally_tts_short_merge_chars": 20,
        "ally_tts_short_merge_window_s": 1.2,
        "ally_tts_rate_limit_window_s": 9.0,
        "ally_tts_rate_limit_max_plays": 5,
        "vad_threshold": 0.02,
        "game_noise_profile": "stable",
        "listen_watchdog_idle_threshold_s": 85,
        "listen_watchdog_stream_stale_s": 24,
        "auto_detect": True,
    },
    "cs2": {
        "label": "CS2 / FPS compétitif (Agressif)",
        "ally_voice_focus_mode": "aggressive",
        "ally_sentence_punct_min_words": 2,
        "ally_sentence_hard_flush_words": 6,
        "ally_tts_similarity_play_below": 0.92,
        "ally_tts_duplicate_window_s": 1.7,
        "ally_tts_force_min_chars": 8,
        "ally_tts_min_gap_s": 0.58,
        "ally_tts_short_merge_words": 3,
        "ally_tts_short_merge_chars": 18,
        "ally_tts_short_merge_window_s": 1.15,
        "ally_tts_rate_limit_window_s": 8.0,
        "ally_tts_rate_limit_max_plays": 5,
        "vad_threshold": 0.018,
    },
    "cs2_safe": {
        "label": "CS2 / FPS compétitif (Safe)",
        "ally_voice_focus_mode": "balanced",
        "ally_sentence_punct_min_words": 3,
        "ally_sentence_hard_flush_words": 7,
        "ally_tts_similarity_play_below": 0.95,
        "ally_tts_duplicate_window_s": 2.0,
        "ally_tts_force_min_chars": 10,
        "ally_tts_min_gap_s": 0.68,
        "ally_tts_short_merge_words": 4,
        "ally_tts_short_merge_chars": 22,
        "ally_tts_short_merge_window_s": 1.35,
        "ally_tts_rate_limit_window_s": 10.0,
        "ally_tts_rate_limit_max_plays": 4,
        "vad_threshold": 0.019,
    },
    "valorant": {
        "label": "Valorant / FPS tactique (Agressif)",
        "ally_voice_focus_mode": "aggressive",
        "ally_sentence_punct_min_words": 2,
        "ally_sentence_hard_flush_words": 6,
        "ally_tts_similarity_play_below": 0.91,
        "ally_tts_duplicate_window_s": 1.9,
        "ally_tts_force_min_chars": 8,
        "ally_tts_min_gap_s": 0.62,
        "ally_tts_short_merge_words": 3,
        "ally_tts_short_merge_chars": 18,
        "ally_tts_short_merge_window_s": 1.25,
        "ally_tts_rate_limit_window_s": 9.0,
        "ally_tts_rate_limit_max_plays": 5,
        "vad_threshold": 0.0185,
    },
    "valorant_safe": {
        "label": "Valorant / FPS tactique (Safe)",
        "ally_voice_focus_mode": "balanced",
        "ally_sentence_punct_min_words": 3,
        "ally_sentence_hard_flush_words": 7,
        "ally_tts_similarity_play_below": 0.94,
        "ally_tts_duplicate_window_s": 2.2,
        "ally_tts_force_min_chars": 10,
        "ally_tts_min_gap_s": 0.72,
        "ally_tts_short_merge_words": 4,
        "ally_tts_short_merge_chars": 22,
        "ally_tts_short_merge_window_s": 1.35,
        "ally_tts_rate_limit_window_s": 10.0,
        "ally_tts_rate_limit_max_plays": 4,
        "vad_threshold": 0.019,
    },
    "warzone": {
        "label": "Warzone / FPS bruyant (Agressif)",
        "ally_voice_focus_mode": "auto",
        "ally_sentence_punct_min_words": 2,
        "ally_sentence_hard_flush_words": 5,
        "ally_tts_similarity_play_below": 0.93,
        "ally_tts_duplicate_window_s": 1.6,
        "ally_tts_force_min_chars": 7,
        "ally_tts_min_gap_s": 0.58,
        "ally_tts_short_merge_words": 3,
        "ally_tts_short_merge_chars": 20,
        "ally_tts_short_merge_window_s": 1.20,
        "ally_tts_rate_limit_window_s": 9.0,
        "ally_tts_rate_limit_max_plays": 4,
        "vad_threshold": 0.019,
    },
    "warzone_safe": {
        "label": "Warzone / FPS bruyant (Safe)",
        "ally_voice_focus_mode": "balanced",
        "ally_sentence_punct_min_words": 3,
        "ally_sentence_hard_flush_words": 7,
        "ally_tts_similarity_play_below": 0.95,
        "ally_tts_duplicate_window_s": 2.0,
        "ally_tts_force_min_chars": 10,
        "ally_tts_min_gap_s": 0.66,
        "ally_tts_short_merge_words": 4,
        "ally_tts_short_merge_chars": 24,
        "ally_tts_short_merge_window_s": 1.30,
        "ally_tts_rate_limit_window_s": 10.0,
        "ally_tts_rate_limit_max_plays": 4,
        "vad_threshold": 0.020,
    },
    "fortnite": {
        "label": "Fortnite / BR (Agressif)",
        "ally_voice_focus_mode": "auto",
        "ally_sentence_punct_min_words": 2,
        "ally_sentence_hard_flush_words": 6,
        "ally_tts_similarity_play_below": 0.93,
        "ally_tts_duplicate_window_s": 1.4,
        "ally_tts_force_min_chars": 8,
        "ally_tts_min_gap_s": 0.50,
        "ally_tts_short_merge_words": 3,
        "ally_tts_short_merge_chars": 18,
        "ally_tts_short_merge_window_s": 1.10,
        "ally_tts_rate_limit_window_s": 8.0,
        "ally_tts_rate_limit_max_plays": 6,
        "vad_threshold": 0.0175,
    },
    "fortnite_safe": {
        "label": "Fortnite / BR (Safe)",
        "ally_voice_focus_mode": "balanced",
        "ally_sentence_punct_min_words": 3,
        "ally_sentence_hard_flush_words": 7,
        "ally_tts_similarity_play_below": 0.95,
        "ally_tts_duplicate_window_s": 1.9,
        "ally_tts_force_min_chars": 10,
        "ally_tts_min_gap_s": 0.62,
        "ally_tts_short_merge_words": 4,
        "ally_tts_short_merge_chars": 22,
        "ally_tts_short_merge_window_s": 1.25,
        "ally_tts_rate_limit_window_s": 10.0,
        "ally_tts_rate_limit_max_plays": 5,
        "vad_threshold": 0.0185,
    },
    "apex": {
        "label": "Apex Legends / BR",
        "ally_voice_focus_mode": "auto",
        "ally_sentence_punct_min_words": 2,
        "ally_sentence_hard_flush_words": 6,
        "ally_tts_similarity_play_below": 0.94,
        "ally_tts_duplicate_window_s": 1.3,
        "ally_tts_force_min_chars": 8,
        "ally_tts_min_gap_s": 0.48,
        "ally_tts_short_merge_words": 3,
        "ally_tts_short_merge_chars": 16,
        "ally_tts_short_merge_window_s": 1.05,
        "ally_tts_rate_limit_window_s": 8.0,
        "ally_tts_rate_limit_max_plays": 6,
        "vad_threshold": 0.0165,
    },
    "overwatch": {
        "label": "Overwatch / Hero Shooter",
        "ally_voice_focus_mode": "auto",
        "ally_sentence_punct_min_words": 2,
        "ally_sentence_hard_flush_words": 6,
        "ally_tts_similarity_play_below": 0.93,
        "ally_tts_duplicate_window_s": 1.5,
        "ally_tts_force_min_chars": 8,
        "ally_tts_min_gap_s": 0.50,
        "ally_tts_short_merge_words": 3,
        "ally_tts_short_merge_chars": 18,
        "ally_tts_short_merge_window_s": 1.10,
        "ally_tts_rate_limit_window_s": 8.0,
        "ally_tts_rate_limit_max_plays": 6,
        "vad_threshold": 0.017,
    },
    "r6": {
        "label": "Rainbow Six / Tactical Voice",
        "ally_voice_focus_mode": "auto",
        "ally_sentence_punct_min_words": 2,
        "ally_sentence_hard_flush_words": 5,
        "ally_tts_similarity_play_below": 0.95,
        "ally_tts_duplicate_window_s": 1.3,
        "ally_tts_force_min_chars": 7,
        "ally_tts_min_gap_s": 0.46,
        "ally_tts_short_merge_words": 3,
        "ally_tts_short_merge_chars": 16,
        "ally_tts_short_merge_window_s": 1.00,
        "ally_tts_rate_limit_window_s": 7.0,
        "ally_tts_rate_limit_max_plays": 6,
        "vad_threshold": 0.0155,
    },
    "tarkov": {
        "label": "Escape from Tarkov / Mil-Sim",
        "ally_voice_focus_mode": "auto",
        "ally_sentence_punct_min_words": 2,
        "ally_sentence_hard_flush_words": 5,
        "ally_tts_similarity_play_below": 0.94,
        "ally_tts_duplicate_window_s": 1.5,
        "ally_tts_force_min_chars": 7,
        "ally_tts_min_gap_s": 0.48,
        "ally_tts_short_merge_words": 3,
        "ally_tts_short_merge_chars": 16,
        "ally_tts_short_merge_window_s": 1.05,
        "ally_tts_rate_limit_window_s": 8.0,
        "ally_tts_rate_limit_max_plays": 6,
        "vad_threshold": 0.0165,
        "game_noise_profile": "combat_mixed",
        "listen_watchdog_idle_threshold_s": 90,
        "listen_watchdog_stream_stale_s": 26,
    },
    # V5.2: Sous-presets Tarkov par map (si la map est détectée via le window title)
    "tarkov_factory": {
        "label": "Escape from Tarkov — Factory",
        "ally_voice_focus_mode": "aggressive",
        "ally_sentence_punct_min_words": 1,
        "ally_sentence_hard_flush_words": 4,
        "ally_tts_similarity_play_below": 0.95,
        "ally_tts_duplicate_window_s": 1.2,
        "ally_tts_force_min_chars": 5,
        "ally_tts_min_gap_s": 0.40,
        "ally_tts_short_merge_words": 2,
        "ally_tts_short_merge_chars": 12,
        "ally_tts_short_merge_window_s": 0.85,
        "ally_tts_rate_limit_window_s": 6.0,
        "ally_tts_rate_limit_max_plays": 8,
        "vad_threshold": 0.014,
        "game_noise_profile": "tarkov_factory",
        "listen_watchdog_idle_threshold_s": 75,
        "listen_watchdog_stream_stale_s": 20,
    },
    "tarkov_woods": {
        "label": "Escape from Tarkov — Woods",
        "ally_voice_focus_mode": "auto",
        "ally_sentence_punct_min_words": 2,
        "ally_sentence_hard_flush_words": 6,
        "ally_tts_similarity_play_below": 0.93,
        "ally_tts_duplicate_window_s": 1.6,
        "ally_tts_force_min_chars": 8,
        "ally_tts_min_gap_s": 0.50,
        "ally_tts_short_merge_words": 3,
        "ally_tts_short_merge_chars": 16,
        "ally_tts_short_merge_window_s": 1.10,
        "ally_tts_rate_limit_window_s": 8.0,
        "ally_tts_rate_limit_max_plays": 5,
        "vad_threshold": 0.017,
        "game_noise_profile": "tarkov_woods",
        "listen_watchdog_idle_threshold_s": 100,
        "listen_watchdog_stream_stale_s": 28,
    },
    "tarkov_customs": {
        "label": "Escape from Tarkov — Customs",
        "ally_voice_focus_mode": "auto",
        "ally_sentence_punct_min_words": 2,
        "ally_sentence_hard_flush_words": 5,
        "ally_tts_similarity_play_below": 0.94,
        "ally_tts_duplicate_window_s": 1.5,
        "ally_tts_force_min_chars": 7,
        "ally_tts_min_gap_s": 0.48,
        "ally_tts_short_merge_words": 3,
        "ally_tts_short_merge_chars": 16,
        "ally_tts_short_merge_window_s": 1.05,
        "ally_tts_rate_limit_window_s": 7.5,
        "ally_tts_rate_limit_max_plays": 6,
        "vad_threshold": 0.016,
        "game_noise_profile": "tarkov_customs",
        "listen_watchdog_idle_threshold_s": 90,
        "listen_watchdog_stream_stale_s": 26,
    },
    "tarkov_interchange": {
        "label": "Escape from Tarkov — Interchange",
        "ally_voice_focus_mode": "aggressive",
        "ally_sentence_punct_min_words": 1,
        "ally_sentence_hard_flush_words": 4,
        "ally_tts_similarity_play_below": 0.96,
        "ally_tts_duplicate_window_s": 1.3,
        "ally_tts_force_min_chars": 5,
        "ally_tts_min_gap_s": 0.42,
        "ally_tts_short_merge_words": 2,
        "ally_tts_short_merge_chars": 14,
        "ally_tts_short_merge_window_s": 0.90,
        "ally_tts_rate_limit_window_s": 6.5,
        "ally_tts_rate_limit_max_plays": 7,
        "vad_threshold": 0.015,
        "game_noise_profile": "tarkov_interchange",
        "listen_watchdog_idle_threshold_s": 80,
        "listen_watchdog_stream_stale_s": 22,
    },
    "rust": {
        "label": "Rust / Survival PvP",
        "ally_voice_focus_mode": "auto",
        "ally_sentence_punct_min_words": 2,
        "ally_sentence_hard_flush_words": 5,
        "ally_tts_similarity_play_below": 0.93,
        "ally_tts_duplicate_window_s": 1.4,
        "ally_tts_force_min_chars": 7,
        "ally_tts_min_gap_s": 0.46,
        "ally_tts_short_merge_words": 3,
        "ally_tts_short_merge_chars": 16,
        "ally_tts_short_merge_window_s": 1.00,
        "ally_tts_rate_limit_window_s": 7.0,
        "ally_tts_rate_limit_max_plays": 6,
        "vad_threshold": 0.0155,
        "game_noise_profile": "survival",
        "listen_watchdog_idle_threshold_s": 85,
        "listen_watchdog_stream_stale_s": 24,
    },
    "pubg": {
        "label": "PUBG / BR Militaire",
        "ally_voice_focus_mode": "auto",
        "ally_sentence_punct_min_words": 2,
        "ally_sentence_hard_flush_words": 6,
        "ally_tts_similarity_play_below": 0.93,
        "ally_tts_duplicate_window_s": 1.6,
        "ally_tts_force_min_chars": 8,
        "ally_tts_min_gap_s": 0.52,
        "ally_tts_short_merge_words": 3,
        "ally_tts_short_merge_chars": 18,
        "ally_tts_short_merge_window_s": 1.15,
        "ally_tts_rate_limit_window_s": 8.0,
        "ally_tts_rate_limit_max_plays": 5,
        "vad_threshold": 0.0175,
        "game_noise_profile": "br_large",
        "listen_watchdog_idle_threshold_s": 90,
        "listen_watchdog_stream_stale_s": 26,
    },
    "lol": {
        "label": "League of Legends / MOBA",
        "ally_voice_focus_mode": "balanced",
        "ally_sentence_punct_min_words": 2,
        "ally_sentence_hard_flush_words": 7,
        "ally_tts_similarity_play_below": 0.91,
        "ally_tts_duplicate_window_s": 1.8,
        "ally_tts_force_min_chars": 8,
        "ally_tts_min_gap_s": 0.55,
        "ally_tts_short_merge_words": 4,
        "ally_tts_short_merge_chars": 20,
        "ally_tts_short_merge_window_s": 1.30,
        "ally_tts_rate_limit_window_s": 10.0,
        "ally_tts_rate_limit_max_plays": 5,
        "vad_threshold": 0.020,
        "game_noise_profile": "moba",
        "listen_watchdog_idle_threshold_s": 80,
        "listen_watchdog_stream_stale_s": 24,
    },
    "dota2": {
        "label": "Dota 2 / MOBA",
        "ally_voice_focus_mode": "balanced",
        "ally_sentence_punct_min_words": 2,
        "ally_sentence_hard_flush_words": 7,
        "ally_tts_similarity_play_below": 0.91,
        "ally_tts_duplicate_window_s": 1.8,
        "ally_tts_force_min_chars": 8,
        "ally_tts_min_gap_s": 0.55,
        "ally_tts_short_merge_words": 4,
        "ally_tts_short_merge_chars": 20,
        "ally_tts_short_merge_window_s": 1.30,
        "ally_tts_rate_limit_window_s": 10.0,
        "ally_tts_rate_limit_max_plays": 5,
        "vad_threshold": 0.020,
        "game_noise_profile": "moba",
        "listen_watchdog_idle_threshold_s": 80,
        "listen_watchdog_stream_stale_s": 24,
    },
    "discord_party": {
        "label": "Discord / Party chat",
        "ally_voice_focus_mode": "balanced",
        "ally_sentence_punct_min_words": 2,
        "ally_sentence_hard_flush_words": 7,
        "ally_tts_similarity_play_below": 0.90,
        "ally_tts_duplicate_window_s": 1.8,
        "ally_tts_force_min_chars": 8,
        "ally_tts_min_gap_s": 0.55,
        "ally_tts_short_merge_words": 4,
        "ally_tts_short_merge_chars": 24,
        "ally_tts_short_merge_window_s": 1.35,
        "ally_tts_rate_limit_window_s": 10.0,
        "ally_tts_rate_limit_max_plays": 5,
        "vad_threshold": 0.020,
    },
    "long_session": {
        "label": "Longue session / Stable V5.2",
        "ally_voice_focus_mode": "balanced",
        "ally_sentence_punct_min_words": 3,
        "ally_sentence_hard_flush_words": 8,
        "ally_tts_similarity_play_below": 0.95,
        "ally_tts_duplicate_window_s": 2.4,
        "ally_tts_force_min_chars": 10,
        "ally_tts_min_gap_s": 0.72,
        "ally_tts_short_merge_words": 4,
        "ally_tts_short_merge_chars": 22,
        "ally_tts_short_merge_window_s": 1.35,
        "ally_tts_rate_limit_window_s": 12.0,
        "ally_tts_rate_limit_max_plays": 4,
        "vad_threshold": 0.019,
        "game_noise_profile": "stable",
        "listen_watchdog_idle_threshold_s": 100,
        "listen_watchdog_stream_stale_s": 30,
    },
    "universel": {
        "label": "V5.3 Universel Intelligent (Auto-tout)",
        "ally_voice_focus_mode": "v3",
        "ally_sentence_punct_min_words": 3,
        "ally_sentence_hard_flush_words": 7,
        "ally_tts_similarity_play_below": 0.94,
        "ally_tts_duplicate_window_s": 1.8,
        "ally_tts_force_min_chars": 8,
        "ally_tts_min_gap_s": 0.65,
        "ally_tts_short_merge_words": 3,
        "ally_tts_short_merge_chars": 20,
        "ally_tts_short_merge_window_s": 1.2,
        "ally_tts_rate_limit_window_s": 9.0,
        "ally_tts_rate_limit_max_plays": 5,
        "vad_threshold": 0.02,
        "game_noise_profile": "stable",
        "listen_watchdog_idle_threshold_s": 85,
        "listen_watchdog_stream_stale_s": 24,
        "auto_detect": True,
        "voice_focus_v3": True,
    },
    "mic_headset_gaming": {
        "label": "Micro Casque Gaming",
        "ally_voice_focus_mode": "v3",
        "ally_sentence_punct_min_words": 2,
        "ally_sentence_hard_flush_words": 6,
        "ally_tts_similarity_play_below": 0.93,
        "ally_tts_duplicate_window_s": 1.6,
        "ally_tts_force_min_chars": 7,
        "ally_tts_min_gap_s": 0.55,
        "ally_tts_short_merge_words": 3,
        "ally_tts_short_merge_chars": 16,
        "ally_tts_short_merge_window_s": 1.1,
        "ally_tts_rate_limit_window_s": 7.0,
        "ally_tts_rate_limit_max_plays": 5,
        "vad_threshold": 0.016,
        "game_noise_profile": "combat_mixed",
        "listen_watchdog_idle_threshold_s": 70,
        "listen_watchdog_stream_stale_s": 20,
        "mic_type": "headset",
    },
    "mic_desktop": {
        "label": "Micro Bureau",
        "ally_voice_focus_mode": "v3",
        "ally_sentence_punct_min_words": 3,
        "ally_sentence_hard_flush_words": 8,
        "ally_tts_similarity_play_below": 0.95,
        "ally_tts_duplicate_window_s": 2.0,
        "ally_tts_force_min_chars": 10,
        "ally_tts_min_gap_s": 0.7,
        "ally_tts_short_merge_words": 4,
        "ally_tts_short_merge_chars": 22,
        "ally_tts_short_merge_window_s": 1.35,
        "ally_tts_rate_limit_window_s": 10.0,
        "ally_tts_rate_limit_max_plays": 4,
        "vad_threshold": 0.022,
        "game_noise_profile": "stable",
        "listen_watchdog_idle_threshold_s": 80,
        "listen_watchdog_stream_stale_s": 25,
        "mic_type": "desktop",
    },
    "mic_lavalier": {
        "label": "Micro Cravate",
        "ally_voice_focus_mode": "balanced",
        "ally_sentence_punct_min_words": 2,
        "ally_sentence_hard_flush_words": 5,
        "ally_tts_similarity_play_below": 0.90,
        "ally_tts_duplicate_window_s": 1.4,
        "ally_tts_force_min_chars": 6,
        "ally_tts_min_gap_s": 0.5,
        "ally_tts_short_merge_words": 2,
        "ally_tts_short_merge_chars": 14,
        "ally_tts_short_merge_window_s": 1.0,
        "ally_tts_rate_limit_window_s": 6.0,
        "ally_tts_rate_limit_max_plays": 6,
        "vad_threshold": 0.014,
        "game_noise_profile": "stable",
        "listen_watchdog_idle_threshold_s": 75,
        "listen_watchdog_stream_stale_s": 22,
        "mic_type": "lavalier",
    },
    "mic_studio": {
        "label": "Micro Studio",
        "ally_voice_focus_mode": "balanced",
        "ally_sentence_punct_min_words": 4,
        "ally_sentence_hard_flush_words": 10,
        "ally_tts_similarity_play_below": 0.96,
        "ally_tts_duplicate_window_s": 2.2,
        "ally_tts_force_min_chars": 12,
        "ally_tts_min_gap_s": 0.75,
        "ally_tts_short_merge_words": 4,
        "ally_tts_short_merge_chars": 28,
        "ally_tts_short_merge_window_s": 1.5,
        "ally_tts_rate_limit_window_s": 12.0,
        "ally_tts_rate_limit_max_plays": 4,
        "vad_threshold": 0.008,
        "game_noise_profile": "stable",
        "listen_watchdog_idle_threshold_s": 90,
        "listen_watchdog_stream_stale_s": 30,
        "mic_type": "studio",
    },
}

LISTEN_PRESET_EXPORT_KEYS = [
    "ally_recognition_lang",
    "ally_block_french",
    "ally_sentence_punct_min_words",
    "ally_sentence_hard_flush_words",
    "ally_tts_similarity_play_below",
    "ally_tts_duplicate_window_s",
    "ally_tts_force_on_speech_final",
    "ally_tts_force_min_chars",
    "ally_tts_min_gap_s",
    "ally_tts_short_merge_words",
    "ally_tts_short_merge_chars",
    "ally_tts_short_merge_window_s",
    "ally_tts_rate_limit_window_s",
    "ally_tts_rate_limit_max_plays",
    "ally_voice_focus_mode",
    "ally_autotune_enabled",
    "ally_listen_profile",
    "ally_game_preset",
    "vad_threshold",
    "quality_preset",
    "game_noise_profile",
    "listen_watchdog_idle_threshold_s",
    "listen_watchdog_stream_stale_s",
]

# V5.2: Dernier preset expressif appliqué (pour le support template)
last_expressive_preset_key = ""

# V5.2: Profils de séparation voix/bruit par type de jeu
GAME_NOISE_PROFILES = {
    "combat_mixed": {
        "label": "Combat mixte (FPS tactique)",
        "noise_floor_ema_alpha": 0.18,
        "voice_snr_threshold": 2.8,
        "transient_suppress_ms": 48,
        "steady_noise_reduce_db": 3.5,
    },
    "survival": {
        "label": "Survival (ambiant variable)",
        "noise_floor_ema_alpha": 0.15,
        "voice_snr_threshold": 2.5,
        "transient_suppress_ms": 55,
        "steady_noise_reduce_db": 4.0,
    },
    "br_large": {
        "label": "Battle Royale large (véhicules + armes)",
        "noise_floor_ema_alpha": 0.16,
        "voice_snr_threshold": 3.0,
        "transient_suppress_ms": 42,
        "steady_noise_reduce_db": 3.0,
    },
    "moba": {
        "label": "MOBA (effets + musique)",
        "noise_floor_ema_alpha": 0.22,
        "voice_snr_threshold": 3.2,
        "transient_suppress_ms": 35,
        "steady_noise_reduce_db": 2.0,
    },
    "stable": {
        "label": "Stable (longue session)",
        "noise_floor_ema_alpha": 0.25,
        "voice_snr_threshold": 3.5,
        "transient_suppress_ms": 60,
        "steady_noise_reduce_db": 5.0,
    },
    # V5.2: Profils de bruit par map Tarkov
    "tarkov_factory": {
        "label": "Tarkov — Factory (CQB intense)",
        "noise_floor_ema_alpha": 0.12,
        "voice_snr_threshold": 2.2,
        "transient_suppress_ms": 35,
        "steady_noise_reduce_db": 2.0,
    },
    "tarkov_woods": {
        "label": "Tarkov — Woods (extérieur variable)",
        "noise_floor_ema_alpha": 0.18,
        "voice_snr_threshold": 3.0,
        "transient_suppress_ms": 50,
        "steady_noise_reduce_db": 3.5,
    },
    "tarkov_customs": {
        "label": "Tarkov — Customs (mix indoor/outdoor)",
        "noise_floor_ema_alpha": 0.15,
        "voice_snr_threshold": 2.6,
        "transient_suppress_ms": 42,
        "steady_noise_reduce_db": 2.8,
    },
    "tarkov_interchange": {
        "label": "Tarkov — Interchange (indoor écho)",
        "noise_floor_ema_alpha": 0.14,
        "voice_snr_threshold": 2.4,
        "transient_suppress_ms": 38,
        "steady_noise_reduce_db": 2.5,
    },
}

LISTEN_PRESET_NAME_MAX = 40
LISTEN_PRESET_LIBRARY_MAX = 30

COMMUNITY_PRESET_STORE = [
    {
        "id": "fps_competitive_pro",
        "name": "FPS Compétitif Pro",
        "description": "Optimisé pour CS2/Valorant — voix claire, bruit de pas réduit",
        "author": "Kommz",
        "category": "fps",
        "tags": ["cs2", "valorant", "competitive", "fps"],
        "rating_avg": 4.7,
        "downloads": 1240,
        "config": {
            "ally_recognition_lang": "multi",
            "ally_voice_focus_mode": "aggressive",
            "ally_game_preset": "cs2",
            "vad_threshold": 0.025,
            "quality_preset": "fast",
            "game_noise_profile": "combat_mixed",
            "ally_block_french": True,
            "ally_sentence_punct_min_words": 3,
            "ally_sentence_hard_flush_words": 8,
            "ally_tts_similarity_play_below": 0.88,
            "ally_tts_duplicate_window_s": 2.5,
            "ally_tts_force_on_speech_final": True,
            "ally_tts_force_min_chars": 6,
            "ally_tts_min_gap_s": 0.4,
            "ally_tts_short_merge_words": 2,
            "ally_tts_short_merge_chars": 14,
            "ally_tts_short_merge_window_s": 1.0,
            "ally_tts_rate_limit_window_s": 8.0,
            "ally_tts_rate_limit_max_plays": 6,
            "ally_autotune_enabled": True,
            "ally_listen_profile": "default",
            "listen_watchdog_idle_threshold_s": 60,
            "listen_watchdog_stream_stale_s": 18,
        },
    },
    {
        "id": "br_survival_tactical",
        "name": "BR Survival Tactique",
        "description": "PUBG/Warzone/Apex — réduction bruit ambiant véhicules, voix prioritaire",
        "author": "Kommz",
        "category": "fps",
        "tags": ["pubg", "warzone", "apex", "survival", "br"],
        "rating_avg": 4.5,
        "downloads": 980,
        "config": {
            "ally_recognition_lang": "multi",
            "ally_voice_focus_mode": "auto",
            "ally_game_preset": "warzone",
            "vad_threshold": 0.03,
            "quality_preset": "fast",
            "game_noise_profile": "br_large",
            "ally_block_french": True,
            "ally_sentence_punct_min_words": 3,
            "ally_sentence_hard_flush_words": 9,
            "ally_tts_similarity_play_below": 0.85,
            "ally_tts_duplicate_window_s": 3.0,
            "ally_tts_force_on_speech_final": True,
            "ally_tts_force_min_chars": 7,
            "ally_tts_min_gap_s": 0.5,
            "ally_tts_short_merge_words": 3,
            "ally_tts_short_merge_chars": 16,
            "ally_tts_short_merge_window_s": 1.2,
            "ally_tts_rate_limit_window_s": 10.0,
            "ally_tts_rate_limit_max_plays": 5,
            "ally_autotune_enabled": True,
            "ally_listen_profile": "default",
            "listen_watchdog_idle_threshold_s": 80,
            "listen_watchdog_stream_stale_s": 22,
        },
    },
    {
        "id": "moba_clear_comms",
        "name": "MOBA Comms Claire",
        "description": "LoL/Dota 2 — filtre bruit capacité, appels courts prioritaires",
        "author": "Kommz",
        "category": "moba",
        "tags": ["lol", "dota2", "moba", "competitive"],
        "rating_avg": 4.3,
        "downloads": 750,
        "config": {
            "ally_recognition_lang": "multi",
            "ally_voice_focus_mode": "balanced",
            "ally_game_preset": "lol",
            "vad_threshold": 0.022,
            "quality_preset": "fast",
            "game_noise_profile": "moba",
            "ally_block_french": True,
            "ally_sentence_punct_min_words": 2,
            "ally_sentence_hard_flush_words": 7,
            "ally_tts_similarity_play_below": 0.9,
            "ally_tts_duplicate_window_s": 2.0,
            "ally_tts_force_on_speech_final": True,
            "ally_tts_force_min_chars": 5,
            "ally_tts_min_gap_s": 0.35,
            "ally_tts_short_merge_words": 2,
            "ally_tts_short_merge_chars": 12,
            "ally_tts_short_merge_window_s": 0.8,
            "ally_tts_rate_limit_window_s": 6.0,
            "ally_tts_rate_limit_max_plays": 7,
            "ally_autotune_enabled": True,
            "ally_listen_profile": "default",
            "listen_watchdog_idle_threshold_s": 55,
            "listen_watchdog_stream_stale_s": 15,
        },
    },
    {
        "id": "tarkov_stealth",
        "name": "Tarkov Stealth Mil-Sim",
        "description": "Tarkov — audio minimal, bruit de pas amplifié, suppression bruit ambient",
        "author": "Kommz",
        "category": "fps",
        "tags": ["tarkov", "survival", "milsim", "stealth"],
        "rating_avg": 4.8,
        "downloads": 1890,
        "config": {
            "ally_recognition_lang": "multi",
            "ally_voice_focus_mode": "aggressive",
            "ally_game_preset": "tarkov",
            "vad_threshold": 0.02,
            "quality_preset": "fast",
            "game_noise_profile": "survival",
            "ally_block_french": True,
            "ally_sentence_punct_min_words": 2,
            "ally_sentence_hard_flush_words": 6,
            "ally_tts_similarity_play_below": 0.9,
            "ally_tts_duplicate_window_s": 2.0,
            "ally_tts_force_on_speech_final": True,
            "ally_tts_force_min_chars": 4,
            "ally_tts_min_gap_s": 0.3,
            "ally_tts_short_merge_words": 2,
            "ally_tts_short_merge_chars": 10,
            "ally_tts_short_merge_window_s": 0.7,
            "ally_tts_rate_limit_window_s": 5.0,
            "ally_tts_rate_limit_max_plays": 8,
            "ally_autotune_enabled": True,
            "ally_listen_profile": "default",
            "listen_watchdog_idle_threshold_s": 50,
            "listen_watchdog_stream_stale_s": 12,
        },
    },
    {
        "id": "streamer_clean_output",
        "name": "Streamer Clean Output",
        "description": "Streaming — voix propre, musique duckée, sorties nettes pour OBS",
        "author": "Kommz",
        "category": "streaming",
        "tags": ["streamer", "obs", "streaming", "clean"],
        "rating_avg": 4.6,
        "downloads": 1520,
        "config": {
            "ally_recognition_lang": "multi",
            "ally_voice_focus_mode": "v3",
            "ally_game_preset": "custom",
            "vad_threshold": 0.028,
            "quality_preset": "quality",
            "game_noise_profile": "stable",
            "ally_block_french": False,
            "ally_sentence_punct_min_words": 3,
            "ally_sentence_hard_flush_words": 10,
            "ally_tts_similarity_play_below": 0.85,
            "ally_tts_duplicate_window_s": 3.0,
            "ally_tts_force_on_speech_final": True,
            "ally_tts_force_min_chars": 8,
            "ally_tts_min_gap_s": 0.55,
            "ally_tts_short_merge_words": 3,
            "ally_tts_short_merge_chars": 18,
            "ally_tts_short_merge_window_s": 1.25,
            "ally_tts_rate_limit_window_s": 10.0,
            "ally_tts_rate_limit_max_plays": 5,
            "ally_autotune_enabled": True,
            "ally_listen_profile": "default",
            "listen_watchdog_idle_threshold_s": 75,
            "listen_watchdog_stream_stale_s": 22,
        },
    },
    {
        "id": "discord_party_chill",
        "name": "Discord Party Détendu",
        "description": "Discord/party — équilibré, longue session stable, bruit doux",
        "author": "Kommz",
        "category": "social",
        "tags": ["discord", "party", "chill", "long"],
        "rating_avg": 4.2,
        "downloads": 650,
        "config": {
            "ally_recognition_lang": "multi",
            "ally_voice_focus_mode": "balanced",
            "ally_game_preset": "discord_party",
            "vad_threshold": 0.03,
            "quality_preset": "quality",
            "game_noise_profile": "stable",
            "ally_block_french": False,
            "ally_sentence_punct_min_words": 3,
            "ally_sentence_hard_flush_words": 10,
            "ally_tts_similarity_play_below": 0.82,
            "ally_tts_duplicate_window_s": 3.5,
            "ally_tts_force_on_speech_final": True,
            "ally_tts_force_min_chars": 8,
            "ally_tts_min_gap_s": 0.6,
            "ally_tts_short_merge_words": 3,
            "ally_tts_short_merge_chars": 18,
            "ally_tts_short_merge_window_s": 1.3,
            "ally_tts_rate_limit_window_s": 12.0,
            "ally_tts_rate_limit_max_plays": 4,
            "ally_autotune_enabled": True,
            "ally_listen_profile": "default",
            "listen_watchdog_idle_threshold_s": 100,
            "listen_watchdog_stream_stale_s": 30,
        },
    },
    {
        "id": "long_session_stable_v5",
        "name": "Longue Session Stable V5",
        "description": "Sessions 4h+ — anti-fatigue, watchdog renforcé, stable et fiable",
        "author": "Kommz",
        "category": "general",
        "tags": ["long", "stable", "session", "endurance"],
        "rating_avg": 4.4,
        "downloads": 870,
        "config": {
            "ally_recognition_lang": "multi",
            "ally_voice_focus_mode": "auto",
            "ally_game_preset": "long_session",
            "vad_threshold": 0.028,
            "quality_preset": "quality",
            "game_noise_profile": "stable",
            "ally_block_french": True,
            "ally_sentence_punct_min_words": 3,
            "ally_sentence_hard_flush_words": 10,
            "ally_tts_similarity_play_below": 0.85,
            "ally_tts_duplicate_window_s": 3.0,
            "ally_tts_force_on_speech_final": True,
            "ally_tts_force_min_chars": 8,
            "ally_tts_min_gap_s": 0.55,
            "ally_tts_short_merge_words": 3,
            "ally_tts_short_merge_chars": 18,
            "ally_tts_short_merge_window_s": 1.25,
            "ally_tts_rate_limit_window_s": 10.0,
            "ally_tts_rate_limit_max_plays": 5,
            "ally_autotune_enabled": True,
            "ally_listen_profile": "default",
            "listen_watchdog_idle_threshold_s": 100,
            "listen_watchdog_stream_stale_s": 30,
        },
    },
    {
        "id": "r6_tactical_callouts",
        "name": "R6 Tactical Callouts",
        "description": "Rainbow Six — appels courts prioritaires, bruit CQB filtré",
        "author": "Kommz",
        "category": "fps",
        "tags": ["r6", "tactical", "cqb", "competitive"],
        "rating_avg": 4.5,
        "downloads": 540,
        "config": {
            "ally_recognition_lang": "multi",
            "ally_voice_focus_mode": "aggressive",
            "ally_game_preset": "r6",
            "vad_threshold": 0.022,
            "quality_preset": "fast",
            "game_noise_profile": "combat_mixed",
            "ally_block_french": True,
            "ally_sentence_punct_min_words": 2,
            "ally_sentence_hard_flush_words": 7,
            "ally_tts_similarity_play_below": 0.88,
            "ally_tts_duplicate_window_s": 2.0,
            "ally_tts_force_on_speech_final": True,
            "ally_tts_force_min_chars": 5,
            "ally_tts_min_gap_s": 0.35,
            "ally_tts_short_merge_words": 2,
            "ally_tts_short_merge_chars": 10,
            "ally_tts_short_merge_window_s": 0.8,
            "ally_tts_rate_limit_window_s": 6.0,
            "ally_tts_rate_limit_max_plays": 7,
            "ally_autotune_enabled": True,
            "ally_listen_profile": "default",
            "listen_watchdog_idle_threshold_s": 55,
            "listen_watchdog_stream_stale_s": 15,
        },
    },
]

EXPRESSIVE_V5_PRESETS = {
    "v5_balanced": {
        "label": "V5 Balanced",
        "expressive_sounds_enabled": True,
        "expressive_profile": "gaming",
        "expressive_transcript_mode": "keep",
        "expressive_tts_mode": "styled",
        "expressive_intensity_mode": "auto",
        "expressive_noise_mode": "smart",
        "expressive_xtts_mode": "auto",
        "expressive_hybrid_mode": "auto",
        "expressive_stability_mode": "balanced",
        "expressive_fallback_guard": True,
        "expressive_ptt_mode": "full",
        "expressive_rts_mode": "safe",
    },
    "v5_long_session_stable": {
        "label": "V5 Long Session Stable",
        "expressive_sounds_enabled": True,
        "expressive_profile": "gaming",
        "expressive_transcript_mode": "keep",
        "expressive_tts_mode": "neutral",
        "expressive_intensity_mode": "soft",
        "expressive_noise_mode": "clean",
        "expressive_xtts_mode": "neutral",
        "expressive_hybrid_mode": "neutral",
        "expressive_stability_mode": "stable",
        "expressive_fallback_guard": True,
        "expressive_ptt_mode": "safe",
        "expressive_rts_mode": "safe",
    },
    "v5_aggressive": {
        "label": "V5.2 Agressif",
        "expressive_sounds_enabled": True,
        "expressive_profile": "gaming",
        "expressive_transcript_mode": "keep",
        "expressive_tts_mode": "styled",
        "expressive_intensity_mode": "strong",
        "expressive_noise_mode": "keep",
        "expressive_xtts_mode": "styled",
        "expressive_hybrid_mode": "styled",
        "expressive_stability_mode": "reactive",
        "expressive_fallback_guard": True,
        "expressive_ptt_mode": "full",
        "expressive_rts_mode": "full",
    },
    "v5_cinematic": {
        "label": "V5.2 Cinématique",
        "expressive_sounds_enabled": True,
        "expressive_profile": "gaming",
        "expressive_transcript_mode": "keep",
        "expressive_tts_mode": "styled",
        "expressive_intensity_mode": "strong",
        "expressive_noise_mode": "clean",
        "expressive_xtts_mode": "styled",
        "expressive_hybrid_mode": "styled",
        "expressive_stability_mode": "balanced",
        "expressive_fallback_guard": True,
        "expressive_ptt_mode": "full",
        "expressive_rts_mode": "full",
    },
    "v5_streamer": {
        "label": "V5.2 Streamer",
        "expressive_sounds_enabled": True,
        "expressive_profile": "gaming",
        "expressive_transcript_mode": "ignore",
        "expressive_tts_mode": "styled",
        "expressive_intensity_mode": "medium",
        "expressive_noise_mode": "clean",
        "expressive_xtts_mode": "styled",
        "expressive_hybrid_mode": "auto",
        "expressive_stability_mode": "balanced",
        "expressive_fallback_guard": True,
        "expressive_ptt_mode": "full",
        "expressive_rts_mode": "safe",
    },
}


def _listen_now_utc_iso() -> str:
    return _utc_now_iso()


def _sanitize_listen_config_guards():
    AUDIO_CONFIG["ally_voice_focus_mode"] = str(AUDIO_CONFIG.get("ally_voice_focus_mode", "balanced") or "balanced").strip().lower()
    if AUDIO_CONFIG["ally_voice_focus_mode"] not in {"off", "balanced", "aggressive", "auto"}:
        AUDIO_CONFIG["ally_voice_focus_mode"] = "balanced"
    AUDIO_CONFIG["ally_game_preset"] = str(AUDIO_CONFIG.get("ally_game_preset", "custom") or "custom").strip().lower()
    if AUDIO_CONFIG["ally_game_preset"] not in {
        "custom",
        "cs2", "cs2_safe",
        "valorant", "valorant_safe",
        "warzone", "warzone_safe",
        "fortnite", "fortnite_safe",
        "apex", "overwatch", "r6", "discord_party",
        "long_session",
        "tarkov", "rust", "pubg", "lol", "dota2"
    }:
        AUDIO_CONFIG["ally_game_preset"] = "custom"
    try:
        AUDIO_CONFIG["ally_tts_short_merge_words"] = max(1, min(8, int(AUDIO_CONFIG.get("ally_tts_short_merge_words", 3) or 3)))
        AUDIO_CONFIG["ally_tts_short_merge_chars"] = max(6, min(80, int(AUDIO_CONFIG.get("ally_tts_short_merge_chars", 18) or 18)))
        AUDIO_CONFIG["ally_tts_short_merge_window_s"] = max(0.30, min(4.0, float(AUDIO_CONFIG.get("ally_tts_short_merge_window_s", 1.25) or 1.25)))
        AUDIO_CONFIG["ally_tts_rate_limit_window_s"] = max(2.0, min(30.0, float(AUDIO_CONFIG.get("ally_tts_rate_limit_window_s", 10.0) or 10.0)))
        AUDIO_CONFIG["ally_tts_rate_limit_max_plays"] = max(1, min(20, int(AUDIO_CONFIG.get("ally_tts_rate_limit_max_plays", 5) or 5)))
    except Exception:
        AUDIO_CONFIG["ally_tts_short_merge_words"] = 3
        AUDIO_CONFIG["ally_tts_short_merge_chars"] = 18
        AUDIO_CONFIG["ally_tts_short_merge_window_s"] = 1.25
        AUDIO_CONFIG["ally_tts_rate_limit_window_s"] = 10.0
        AUDIO_CONFIG["ally_tts_rate_limit_max_plays"] = 5


def _is_competitive_listen_locked() -> bool:
    if not bool(AUDIO_CONFIG.get("ally_competitive_lock", False)):
        return False
    try:
        unlock_until = float(AUDIO_CONFIG.get("ally_competitive_unlock_until_ts", 0.0) or 0.0)
    except Exception:
        unlock_until = 0.0
    return time.time() >= unlock_until


def _listen_lock_block_response():
    return jsonify({
        "ok": False,
        "locked": True,
        "error": "Verrou compétition actif. Désactive le verrou pour modifier ces réglages."
    }), 423


def _maybe_enable_competitive_lock_auto():
    if bool(AUDIO_CONFIG.get("ally_competitive_lock_auto", True)):
        AUDIO_CONFIG["ally_competitive_lock"] = True


def _capture_listen_preset_config() -> dict:
    out = {}
    for k in LISTEN_PRESET_EXPORT_KEYS:
        out[k] = AUDIO_CONFIG.get(k)
    return _repair_payload_strings(out)


def _sanitize_listen_preset_name(raw_name: str) -> str:
    name = _repair_display_text(str(raw_name or "").strip())
    name = re.sub(r"\s+", " ", name)
    return name[:LISTEN_PRESET_NAME_MAX]


def _normalize_listen_preset_entry(raw: dict) -> dict:
    item = dict(raw or {})
    name = _sanitize_listen_preset_name(item.get("name") or item.get("preset_name") or "")
    if not name:
        name = "Preset"
    cfg = item.get("config")
    if not isinstance(cfg, dict):
        cfg = {}
    cleaned_cfg = {}
    for k in LISTEN_PRESET_EXPORT_KEYS:
        if k in cfg:
            cleaned_cfg[k] = cfg[k]
    return {
        "name": name,
        "config": _repair_payload_strings(cleaned_cfg),
        "updated_at": str(item.get("updated_at") or _listen_now_utc_iso()),
    }


def _get_listen_preset_library() -> list:
    lib = AUDIO_CONFIG.get("ally_preset_library")
    if isinstance(lib, dict):
        tmp = []
        for k, v in lib.items():
            cfg = v if isinstance(v, dict) else {}
            tmp.append({"name": str(k), "config": cfg})
        lib = tmp
    if not isinstance(lib, list):
        lib = []
    normalized = []
    seen = set()
    for raw in lib:
        item = _normalize_listen_preset_entry(raw)
        key = str(item.get("name") or "").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        normalized.append(item)
    AUDIO_CONFIG["ally_preset_library"] = normalized[:LISTEN_PRESET_LIBRARY_MAX]
    return AUDIO_CONFIG["ally_preset_library"]


def _apply_listen_game_preset(preset_key: str):
    key = str(preset_key or "").strip().lower()
    cfg = LISTEN_GAME_PRESETS.get(key)
    if not cfg:
        return False, "Preset inconnu"

    AUDIO_CONFIG["is_listening"] = True
    AUDIO_CONFIG["ally_recognition_lang"] = "multi"
    AUDIO_CONFIG["ally_block_french"] = False
    AUDIO_CONFIG["ally_tts_force_on_speech_final"] = True
    AUDIO_CONFIG["ally_autotune_enabled"] = True
    AUDIO_CONFIG["ally_tts_short_merge_words"] = 3
    AUDIO_CONFIG["ally_tts_short_merge_chars"] = 18
    AUDIO_CONFIG["ally_tts_short_merge_window_s"] = 1.20
    AUDIO_CONFIG["ally_tts_rate_limit_window_s"] = 9.0
    AUDIO_CONFIG["ally_tts_rate_limit_max_plays"] = 5
    AUDIO_CONFIG["listen_watchdog_idle_threshold_s"] = 75
    AUDIO_CONFIG["listen_watchdog_stream_stale_s"] = 22
    AUDIO_CONFIG["quality_preset"] = "balanced"
    _apply_quality_preset("balanced", emit_log=False)

    for k in (
        "ally_voice_focus_mode",
        "ally_sentence_punct_min_words",
        "ally_sentence_hard_flush_words",
        "ally_tts_similarity_play_below",
        "ally_tts_duplicate_window_s",
        "ally_tts_force_min_chars",
        "ally_tts_min_gap_s",
        "ally_tts_short_merge_words",
        "ally_tts_short_merge_chars",
        "ally_tts_short_merge_window_s",
        "ally_tts_rate_limit_window_s",
        "ally_tts_rate_limit_max_plays",
        "vad_threshold",
        "listen_watchdog_idle_threshold_s",
        "listen_watchdog_stream_stale_s",
    ):
        if k in cfg:
            AUDIO_CONFIG[k] = cfg[k]

    AUDIO_CONFIG["ally_listen_profile"] = "competitive"
    AUDIO_CONFIG["ally_game_preset"] = key
    _maybe_enable_competitive_lock_auto()
    save_settings()
    return True, cfg.get("label", key)


def _apply_expressive_v5_preset(preset_key: str):
    key = str(preset_key or "").strip().lower()
    cfg = EXPRESSIVE_V5_PRESETS.get(key)
    if not cfg:
        return False, "Preset expressif inconnu"
    for k, v in cfg.items():
        if k == "label":
            continue
        AUDIO_CONFIG[k] = v
    save_settings()
    return True, str(cfg.get("label", key) or key)



@app.route("/audio/expressive/preset/apply", methods=["POST"])
def apply_expressive_v5_preset():
    try:
        data = request.get_json(silent=True) or {}
        key = str(data.get("preset", "") or "").strip().lower()
        ok, info = _apply_expressive_v5_preset(key)
        if not ok:
            return jsonify({"ok": False, "error": info}), 400
        global last_expressive_preset_key
        last_expressive_preset_key = key
        stealth_print(f"🎚️ Preset expressif appliqué: {info} ({key})")
        _push_toast(f"🎚️ Expressivité: {info}")
        return jsonify({
            "ok": True,
            "preset": key,
            "label": info,
            "expressive_profile": str(AUDIO_CONFIG.get("expressive_profile", "gaming") or "gaming"),
            "expressive_tts_mode": str(AUDIO_CONFIG.get("expressive_tts_mode", "styled") or "styled"),
            "expressive_intensity_mode": str(AUDIO_CONFIG.get("expressive_intensity_mode", "auto") or "auto"),
            "expressive_noise_mode": str(AUDIO_CONFIG.get("expressive_noise_mode", "smart") or "smart"),
            "expressive_stability_mode": str(AUDIO_CONFIG.get("expressive_stability_mode", "balanced") or "balanced"),
            "expressive_ptt_mode": str(AUDIO_CONFIG.get("expressive_ptt_mode", "full") or "full"),
            "expressive_rts_mode": str(AUDIO_CONFIG.get("expressive_rts_mode", "safe") or "safe"),
        })
    except Exception as e:
        stealth_print(f"❌ Erreur preset expressif V5: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


def _preset_schedule_check_loop():
    import datetime
    while True:
        try:
            schedules = AUDIO_CONFIG.get("ally_preset_schedule", [])
            if isinstance(schedules, list):
                now = datetime.datetime.now()
                day_name = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"][now.weekday()]
                current_hm = now.hour * 60 + now.minute
                for s in schedules:
                    if not s.get("enabled", True):
                        continue
                    days = s.get("days", [])
                    if days and day_name not in days:
                        continue
                    sched_hm = int(s.get("hour", 0)) * 60 + int(s.get("minute", 0))
                    if current_hm == sched_hm:
                        last = s.get("last_applied", "")
                        today_str = now.strftime("%Y-%m-%d")
                        if last != today_str:
                            preset = str(s.get("preset", "")).strip()
                            ok, info = _apply_listen_game_preset(preset)
                            if ok:
                                s["last_applied"] = today_str
                                AUDIO_CONFIG["ally_preset_schedule"] = schedules
                                save_settings()
                                stealth_print(f"📅 Planning auto-appliqué: {s.get('name')} → {preset}")
                                _push_toast(f"📅 Planning: {s.get('name')} appliqué")
        except Exception:
            pass
        _PERF_STOP_EVENT.wait(60)


def temp_unlock_competitive_listen_lock():
    try:
        data = request.get_json(silent=True) or {}
        seconds = int(data.get("seconds", 30)) if isinstance(data, dict) else 30
        seconds = max(5, min(120, seconds))
        if not bool(AUDIO_CONFIG.get("ally_competitive_lock", False)):
            return jsonify({
                "ok": True,
                "ally_competitive_lock": False,
                "ally_competitive_lock_effective": False,
                "ally_competitive_unlock_remaining_s": 0,
                "message": "Verrou déjà désactivé.",
            })
        AUDIO_CONFIG["ally_competitive_unlock_until_ts"] = float(time.time() + seconds)
        save_settings()
        stealth_print(f"⏱️ Verrou compétition: déverrouillage temporaire {seconds}s.")
        return jsonify({
            "ok": True,
            "ally_competitive_lock": True,
            "ally_competitive_lock_effective": bool(_is_competitive_listen_locked()),
            "ally_competitive_unlock_remaining_s": seconds,
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


def reset_listen_health_runtime():
    try:
        _reset_listen_health_runtime()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# V5.3: Detection V2 avec fingerprint audio
def contribute_fingerprint():
    try:
        if not _afp:
            return jsonify({"ok": False, "error": "Module fingerprint non disponible"}), 500
        data = request.get_json(silent=True) or {}
        game_key = str(data.get("game_key", "")).strip().lower()
        if not game_key:
            detected = detect_current_game(use_fingerprint=False).get_json()
            game_key = (detected.get("effective_preset") or detected.get("detected_game") or "").strip().lower()
        if not game_key:
            return jsonify({"ok": False, "error": "game_key requis (ex: cs2, valorant, tarkov...)"}), 400
        duration = float(data.get("duration_s", 2.5))
        duration = max(1.0, min(duration, 5.0))
        fp = _afp.capture_and_fingerprint(duration_s=duration)
        if not fp:
            return jsonify({"ok": False, "error": "Aucun audio capturé."}), 500
        label = str(data.get("label", game_key) or game_key).strip()
        _afp.add_fingerprint(game_key, fp, label=label)
        proc = _get_foreground_process_name()
        _afp.set_cached_match(proc, {"game_key": game_key, "confidence": 1.0})
        return jsonify({
            "ok": True,
            "game_key": game_key,
            "label": label,
            "fingerprint_hash": fp["hash"],
            "message": f"Fingerprint ajouté pour {game_key}. La détection audio sera plus précise.",
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


def toggle_auto_detect():
    global _game_detect_auto_mode
    try:
        data = request.get_json(silent=True) or {}
        enabled = data.get("enabled")
        if enabled is not None:
            _game_detect_auto_mode = bool(enabled)
        else:
            _game_detect_auto_mode = not _game_detect_auto_mode
        AUDIO_CONFIG["game_auto_detect_enabled"] = _game_detect_auto_mode
        save_settings()
        return jsonify({"ok": True, "auto_detect_enabled": _game_detect_auto_mode})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# V5.2: Onboarding / support flow — template Discord prêt à poster


@app.route("/audio/devices")
def gad():
    """
    PATCH V5.3 : Retourne les périphériques audio avec fallback multi-API.
    Ordre de priorité : WASAPI → DirectSound → MME → tout.
    Corrige le bug où la liste était vide si WASAPI n'avait pas de devices.
    """
    try:
        hostapis = sd.query_hostapis()
        all_devs = sd.query_devices()

        def collect_for_api(api_idx):
            ins, outs = [], []
            for i, dev in enumerate(all_devs):
                if dev.get('hostapi') != api_idx:
                    continue
                name = str(dev.get('name', '') or '').strip()
                if not name:
                    continue
                if dev.get('max_input_channels', 0) > 0:
                    ins.append({"index": i, "name": name})
                if dev.get('max_output_channels', 0) > 0:
                    outs.append({"index": i, "name": name})
            return ins, outs

        # Ordre de préférence des APIs
        API_PRIORITY = ["WASAPI", "DIRECTSOUND", "DIRECTX", "MME", "WINDOWS WDM-KS"]
        preferred_idx = None
        for priority_name in API_PRIORITY:
            for i, api in enumerate(hostapis):
                if priority_name in api.get('name', '').upper():
                    ins, outs = collect_for_api(i)
                    if ins or outs:
                        preferred_idx = i
                        break
            if preferred_idx is not None:
                break

        if preferred_idx is not None:
            unique_i, unique_o = collect_for_api(preferred_idx)
        else:
            # Dernier fallback : collecter TOUS les périphériques toutes APIs
            unique_i, unique_o = [], []
            seen_i, seen_o = set(), set()
            for i, dev in enumerate(all_devs):
                name = str(dev.get('name', '') or '').strip()
                if not name:
                    continue
                if dev.get('max_input_channels', 0) > 0 and name not in seen_i:
                    unique_i.append({"index": i, "name": name})
                    seen_i.add(name)
                if dev.get('max_output_channels', 0) > 0 and name not in seen_o:
                    unique_o.append({"index": i, "name": name})
                    seen_o.add(name)

        return jsonify({
            "ok": True,
            "output_devices": unique_o,
            "input_devices": unique_i,
            "api_used": hostapis[preferred_idx]['name'] if preferred_idx is not None else "all"
        })
    except Exception as _e:
        stealth_print(f"[audio/devices] erreur: {_e}")
        return jsonify({"ok": False, "error": str(_e)})
    


# ==================== AUDIO LOGIC ====================

def audio_bypass_loop():
    try: ctypes.windll.ole32.CoInitialize(None)
    except: pass
    
    stream_in = None
    stream_out = None
    last_ids = (None, None)
    RATE = 48000 

    while True:
        if not AUDIO_CONFIG.get("bypass_mode_active", False):
            if stream_in:
                try: 
                    stream_in.stop(); stream_in.close()
                    stream_out.stop(); stream_out.close()
                except: pass
                stream_in = stream_out = None
                stealth_print("⚪ Bypass : OFF")
            time.sleep(0.5); continue

        try:
            # Micro physique par défaut
            mic_id = int(sd.default.device[0])

            # Sortie virtuelle cible (CABLE Input / CABLE In)
            cable_id = find_cable_output_device()
            if cable_id is None:
                # fallback configuration utilisateur
                cable_id = resolve_output_device_cfg(AUDIO_CONFIG.get("game_output_device", 0))

            if cable_id is None:
                stealth_print("⚠️ Bypass : sortie CABLE introuvable.")
                time.sleep(1.0); continue
            
            # OUVERTURE DES FLUX
            if stream_in is None or last_ids != (mic_id, cable_id):
                last_ids = (mic_id, cable_id)
                stealth_print(f"🚀 BYPASS : Micro[{mic_id}] -> Câble[{cable_id}]")

                stream_in = sd.InputStream(device=mic_id, samplerate=RATE, channels=1, blocksize=1024, dtype="float32")
                stream_out = sd.OutputStream(device=cable_id, samplerate=RATE, channels=2, blocksize=1024, dtype="float32")
                
                stream_in.start()
                stream_out.start()

            # TRANSFERT DES DONNÉES
            data, _ = stream_in.read(1024)
            stereo_data = np.column_stack((data, data)) # Mono -> Stéréo
            stream_out.write(stereo_data)

        except Exception as e:
            stealth_print(f"⚠️ Bypass stream error: {e}")
            if stream_in: stream_in.close(); stream_in = None
            if stream_out: stream_out.close(); stream_out = None
            time.sleep(1.0)


def monitoring_loop():
    """
    Retour casque matériel:
    lit le flux CABLE Output (input côté Python) et le renvoie vers une sortie physique.
    Ce chemin est indépendant du TTS pour fiabiliser F3 en version compilée.
    """
    try:
        ctypes.windll.ole32.CoInitialize(None)
    except Exception:
        pass

    stream_in = None
    stream_out = None
    last_tuple = (None, None, None)
    _resampler = None  # soxr.ResampleStream — état persistant entre blocs

    while True:
        enabled = bool(AUDIO_CONFIG.get("monitoring_enabled", False))
        if not enabled:
            if stream_in is not None:
                try:
                    stream_in.stop()
                    stream_in.close()
                except Exception:
                    pass
                stream_in = None
            if stream_out is not None:
                try:
                    stream_out.stop()
                    stream_out.close()
                except Exception:
                    pass
                stream_out = None
            time.sleep(0.2)
            continue

        try:
            # Priorité device CABLE compatible non-WDM-KS, puis fallback CABLE standard.
            src_in = find_cable_input_device_non_wdmks()
            if src_in is None:
                src_in = find_cable_input_device()
            if src_in is None:
                time.sleep(0.8)
                continue

            cable_out = find_cable_output_device()
            dst_out = AUDIO_CONFIG.get("output_device") or get_default_output_device_id()
            if dst_out is None:
                time.sleep(0.8)
                continue

            src_info = sd.query_devices(int(src_in))
            dst_info = sd.query_devices(int(dst_out))
            rate = int(float(src_info.get("default_samplerate", 48000) or 48000))
            if rate < 8000 or rate > 192000:
                rate = 48000
            in_ch = max(1, min(2, int(src_info.get("max_input_channels", 1))))
            out_ch = max(1, min(2, int(dst_info.get("max_output_channels", 2))))

            # BUG1 fix — rates séparés pour InputStream (CABLE) et OutputStream (casque)
            # _find_compatible_rate testait uniquement le device de sortie → rate 192000Hz
            # appliqué au CABLE qui ne supporte que 48000Hz → PaErrorCode -9997
            def _find_compatible_in_rate(device, preferred, channels):
                import sounddevice as _sd
                for c in [preferred, 48000, 44100, 32000, 16000]:
                    try:
                        t = _sd.InputStream(device=device, samplerate=c, channels=channels, blocksize=512, dtype="float32")
                        t.start(); t.stop(); t.close()
                        return c
                    except Exception:
                        pass
                return preferred

            def _find_compatible_out_rate(device, preferred, channels):
                import sounddevice as _sd
                # Tester rate_in en premier → si accepté, pas de resampling du tout
                # puis preferred (natif), puis fallbacks
                for c in [rate_in, preferred, 48000, 44100, 32000, 16000]:
                    try:
                        t = _sd.OutputStream(device=device, samplerate=c, channels=channels, blocksize=512, dtype="float32")
                        t.start(); t.stop(); t.close()
                        return c
                    except Exception:
                        pass
                return preferred

            rate_in  = _find_compatible_in_rate(int(src_in),  int(float(src_info.get("default_samplerate", 48000) or 48000)), in_ch)
            rate_out = _find_compatible_out_rate(int(dst_out), int(float(dst_info.get("default_samplerate", 48000) or 48000)), out_ch)

            cur_tuple = (int(src_in), int(dst_out), int(rate_in), int(rate_out))
            if (stream_in is None) or (stream_out is None) or (cur_tuple != last_tuple):
                # Fermer les anciens streams
                for s in set([stream_in, stream_out]):
                    if s is not None:
                        try: s.stop(); s.close()
                        except Exception: pass
                stream_in = None; stream_out = None

                # OutputStream ouvert séparément (devices différents → pas de duplex)
                stream_out = sd.OutputStream(
                    device=int(dst_out),
                    samplerate=rate_out,
                    channels=out_ch,
                    blocksize=1024,
                    dtype="float32",
                    latency='low',
                )
                stream_out.start()

                # ResampleStream soxr si nécessaire
                _rs = None
                if rate_in != rate_out:
                    try:
                        import soxr as _sx
                        _rs = _sx.ResampleStream(rate_in, rate_out, in_ch, quality="VHQ", dtype="float32")
                    except Exception:
                        pass
                _resampler = _rs
                _stream_out_ref = stream_out

                # Callback InputStream — s'exécute dans le thread C PortAudio
                def _in_cb(indata, frames, time_info, status):
                    try:
                        src = indata.copy()
                        if _rs is not None:
                            src = _rs.resample_chunk(src, last=False).astype(np.float32)
                            if src.ndim == 1:
                                src = src[:, np.newaxis]
                        # Adapter les canaux
                        if src.shape[1] == 1 and out_ch >= 2:
                            payload = np.column_stack([src[:, 0], src[:, 0]])
                        elif src.shape[1] >= 2 and out_ch == 1:
                            payload = src[:, :2].mean(axis=1, keepdims=True)
                        else:
                            payload = src[:, :out_ch]
                        _stream_out_ref.write(payload.astype(np.float32))
                    except Exception:
                        pass

                stream_in = sd.InputStream(
                    device=int(src_in),
                    samplerate=rate_in,
                    channels=in_ch,
                    blocksize=1024,
                    dtype="float32",
                    latency='low',
                    callback=_in_cb,
                )
                stream_in.start()
                last_tuple = cur_tuple
                stealth_print(f"🎧 Monitoring stream: CABLE[{src_in}] -> CASQUE[{dst_out}] @ SRC:{rate_in}Hz DST:{rate_out}Hz")

            # Callback actif — juste surveiller que les streams sont vivants
            if not stream_in.active or not stream_out.active:
                stream_in = None; stream_out = None
                continue
            time.sleep(0.05)

        except Exception as e:
            stealth_print(f"⚠️ Monitoring loop error: {e}")
            if stream_in is not None:
                try:
                    stream_in.stop()
                    stream_in.close()
                except Exception:
                    pass
                stream_in = None
            if stream_out is not None:
                try:
                    stream_out.stop()
                    stream_out.close()
                except Exception:
                    pass
                stream_out = None
            time.sleep(0.8)
            
def find_device_by_name(is_output=True):
    """
    Recherche intelligente du VB-CABLE.
    is_output=True pour 'CABLE Input' (le côté où on écrit le son).
    """
    devices = sd.query_devices()
    # Mots-clés universels pour VB-CABLE
    keywords = ["CABLE", "VIRTUAL"]
    sub_keywords = ["IN", "INPUT"]

    for i, dev in enumerate(devices):
        name = dev['name'].upper()
        # On vérifie si le nom contient les mots-clés
        if any(k in name for k in keywords):
            # On vérifie si c'est bien une entrée de câble (Output pour Python)
            if is_output and dev['max_output_channels'] > 0:
                # On affine : est-ce que ça contient 'IN' ou 'INPUT' ?
                if any(sk in name for sk in sub_keywords):
                    return i
    return None     

def clean_prefix(text):
    if not AUDIO_CONFIG.get("seamless_prefix_active", False): return text
    original_text = text
    text = text.strip(); prefixes = ["you know", "so", "like", "uh", "um", "i mean", "yeah", "okay", "alright"]
    words = text.lower().split()
    if len(words) > 1 and words[0] in prefixes: text = " ".join(words[1:])
    if text != original_text.strip():
        _set_module_runtime("seamless", "Filtrage", f"Préfixe supprimé: {words[0]}")
    else:
        _set_module_runtime("seamless", "Actif", "Aucun préfixe à nettoyer")
    return text.strip()
    
def apply_tilt_shield(text):
    """Module Anti-Toxicité : Remplace les insultes par du positif"""
    if not AUDIO_CONFIG.get("tilt_shield_active", False): return text
    
    # Dictionnaire de "Désamorçage"
    toxic_map = {
        "connard": "allié", "merde": "zut", "putain": "mince", "fuck": "attention",
        "noob": "débutant", "trash": "en difficulté", "idiot": "incompris",
        "suicide": "reset", "tg": "silence", "shut up": "calme", "report": "signaler",
        "troll": "joueur créatif", "diff": "écart de niveau", "useless": "passif"
    }
    
    processed = text
    lower_text = text.lower()
    
    for bad, good in toxic_map.items():
        if bad in lower_text:
            # Remplacement insensible à la casse
            pattern = re.compile(re.escape(bad), re.IGNORECASE)
            processed = pattern.sub(good, processed)
            
    if processed != text:
        _set_module_runtime("tilt", "Filtré", "Expression toxique désamorcée")
    else:
        _set_module_runtime("tilt", "Actif", "Aucune toxicité détectée")
    return processed    

def handle_smart_commands(text, src_lang):
    global CURRENT_TARGET_LANG 
    if not AUDIO_CONFIG.get("smart_commands_active", False): return text, False 
    lower = unidecode(text.lower().strip())
    
    # --- COMMANDES EXISTANTES ---
    if "switch" in lower:
        lang_map = {"english":"EN", "french":"FR", "spanish":"ES", "german":"DE", "italian":"IT", "russian":"RU", "japanese":"JA", "chinese":"ZH", "portuguese":"PT"}
        for k, v in lang_map.items():
            if k in lower: 
                CURRENT_TARGET_LANG = v
                logger.info(f"🎙️ COMMANDE VOCALE : Switch -> {v}")
                add_subtitle(f"SYSTEM >> Langue Cible : {v}", "SYS")
                _set_module_runtime("smart", "Commande", f"Langue cible -> {v}")
                return "", True
                
    if "switch engine" in lower:
        if AUDIO_CONFIG["tts_engine"] == "KOMMZ_VOICE":
            AUDIO_CONFIG["tts_engine"] = "WINDOWS"
        else:
            if has_voice_license():
                AUDIO_CONFIG["tts_engine"] = "KOMMZ_VOICE"
            else:
                AUDIO_CONFIG["tts_engine"] = "WINDOWS"
                add_subtitle("SYSTEM >> Licence Voice requise", "SYS")
        _set_module_runtime("smart", "Commande", f"Moteur vocal -> {AUDIO_CONFIG['tts_engine']}")
        add_subtitle(f"SYSTEM >> Moteur : {AUDIO_CONFIG['tts_engine']}", "SYS"); return "", True

    # --- MODULE 3 : TACTICAL MACROS ---
    if AUDIO_CONFIG.get("tactical_macros_active", False):
        # Dis "Capture" pour faire F12 (Screenshot Steam)
        if "capture" in lower or "screenshot" in lower or "photo" in lower:
            keyboard.press_and_release('f12')
            stealth_print("📸 Macro : F12 (Screenshot)")
            _set_module_runtime("macros", "Déclenché", "Macro screenshot F12 exécutée")
            return "", True
            
        # Dis "Clip ça" pour faire Alt+F10 (Shadowplay)
        if "clip" in lower and ("ça" in lower or "it" in lower):
            keyboard.press_and_release('alt+f10')
            stealth_print("🎬 Macro : Alt+F10 (Clip)")
            _set_module_runtime("macros", "Déclenché", "Macro clip Alt+F10 exécutée")
            return "", True
            
        # Dis "Mute Discord" pour Ctrl+Maj+M
        if "mute" in lower and "discord" in lower:
            keyboard.press_and_release('ctrl+shift+m')
            stealth_print("🔇 Macro : Mute Discord")
            _set_module_runtime("macros", "Déclenché", "Macro mute Discord exécutée")
            return "", True

    # --- MODULE STREAMER 3 : SMART MARKER (NOUVEAU) ---
    if AUDIO_CONFIG.get("smart_marker_active", False):
        if "marqueur" in lower or "marker" in lower:
            import datetime
            import sys
            
            # Récupère l'heure actuelle
            timestamp = datetime.datetime.now().strftime("%H:%M:%S")
            
            try:
                # Écrit dans le fichier CSV
                with open("stream_markers.csv", "a", encoding="utf-8") as f:
                    f.write(f"{timestamp};Marker posé\n")
                
                stealth_print(f"📌 MARKER AJOUTÉ À {timestamp}")
                _set_module_runtime("marker", "Déclenché", f"Marqueur stream ajouté à {timestamp}")
                
                # Petit Bip sonore de confirmation (Windows uniquement)
                if sys.platform == "win32":
                    try:
                        import winsound
                        winsound.Beep(1000, 150) # Fréquence 1000Hz, durée 150ms
                    except: pass
                    
            except Exception as e:
                stealth_print(f"⚠️ Erreur Marker: {e}")
                
            return "", True

    _set_module_runtime("smart", "Actif", "En écoute des commandes vocales")
    if AUDIO_CONFIG.get("tactical_macros_active", False):
        _set_module_runtime("macros", "Actif", "Macros vocales en attente")
    if AUDIO_CONFIG.get("smart_marker_active", False):
        _set_module_runtime("marker", "Actif", "En attente d'un marqueur vocal")
    return text, False

def apply_gaming_context(text):
    if not AUDIO_CONFIG.get("auto_context_active", False): return text
    context_map = { " camp ": " tend une embuscade ", " camping ": " reste immobile ", " low ": " vie faible ", " hp ": " points de vie ", " rez ": " réanime ", " res ": " réanime ", " ult ": " capacité ultime " }
    processed = " " + text.lower() + " "; modified = False
    for term, replacement in context_map.items():
        if term in processed: processed = processed.replace(term, replacement); modified = True
    if modified:
        _set_module_runtime("autocontext", "Enrichi", "Contexte gaming injecté dans le texte")
    else:
        _set_module_runtime("autocontext", "Actif", "Aucun terme gaming à enrichir")
    return processed.strip() if modified else text

def translate_text(text, target, source=None):
    global SHADOW_CACHE
    if not text or len(text) < 2: return text
    
    # --- 1. CONVERSION DE SÉCURITÉ (Mise à jour complète) ---
    target = target.upper()
    
    # Les classiques
    if target == "EN": target = "EN-US"
    if target == "PT": target = "PT-PT"
    
    # Les cas spéciaux (Pays -> Langue)
    if target == "UA": target = "UK"     # DeepL utilise 'UK' pour l'Ukrainien
    if target == "BR": target = "PT-BR"  # DeepL utilise 'PT-BR' pour le Brésil
    
    # 2. Cache
    cache_key = (text, target)
    cached = _shadow_cache_get(SHADOW_CACHE, cache_key)
    if cached is not None:
        return cached

    try:
        # 3. Essai DeepL
        if deepl_translator:
            result = deepl_translator.translate_text(text, target_lang=target)
            translated = result.text
            return _shadow_cache_put(SHADOW_CACHE, cache_key, translated, SHADOW_CACHE_MAX_ITEMS)
    except Exception as e:
        stealth_print(f"⚠️ DeepL Error: {e}")

    # 4. Fallback Google
    try:
        if GoogleTranslator:
            # Google préfère "en" tout court, et "vi" pour Vietnam (pas VN)
            if target == "VN": google_target = "vi"
            elif target == "JP": google_target = "ja"
            elif "EN" in target: google_target = "en"
            else: google_target = target.lower()

            translated = GoogleTranslator(source='auto', target=google_target).translate(text)
            if translated and "500" not in translated:
                return _shadow_cache_put(SHADOW_CACHE, cache_key, translated, SHADOW_CACHE_MAX_ITEMS)
    except:
        pass
    
    return text


def update_polyglot_obs_subtitle(text, source_lang_label="MOI"):
    if not AUDIO_CONFIG.get("polyglot_active", False):
        return
    if not AUDIO_CONFIG.get("stream_connect_active", False):
        return
    if not text or str(source_lang_label).upper() == "SYS":
        return
    try:
        poly_text = translate_text(str(text), POLYGLOT_TARGET_LANG) or str(text)
        with open(POLYGLOT_OBS_FILE, "w", encoding="utf-8") as f:
            f.write(f"[{POLYGLOT_TARGET_LANG}] {poly_text}")
        _set_module_runtime("polyglot", "Actif", f"Export OBS {POLYGLOT_TARGET_LANG} mis à jour")
    except Exception as poly_err:
        stealth_print(f"⚠️ Polyglot Stream indisponible: {poly_err}")
        _set_module_runtime("polyglot", "Erreur", f"Export OBS secondaire indisponible: {poly_err}")

def add_subtitle(text, lang="FR"):
    if str(lang).upper() == "ALLY":
        lang = "ALLIÉ"
    is_user = (lang == "MOI")
    is_system = (str(lang).upper() == "SYS")

    if _is_stealth_mode_active() and is_system and not _is_stealth_critical_message(text):
        _set_module_runtime("stealth", "Masqué", "Messages système non essentiels cachés de l'overlay")
        return
    
    # --- FIX: Respecter la case "Ma Voix" de l'interface ---
    # Si c'est toi qui parles ET que l'option est décochée -> On arrête tout.
    if is_user and not AUDIO_CONFIG.get("show_own_subs_active", True):
        return 

    # Si on passe le test, on affiche normalement
    subs_buffer.append({"text": text, "lang": lang, "timestamp": time.time(), "is_user": is_user})
    if len(subs_buffer) > 10: subs_buffer.pop(0)
    try:
        if ("ALLIÉ" in str(lang)) or ("ALLY" in str(lang)):
            stealth_print(f"📝 Sub ally: {str(text)[:80]}")
    except Exception:
        pass

    # --- MODULE STREAM CONNECT (OBS) ---
    if AUDIO_CONFIG.get("stream_connect_active", False):
        try:
            with open("obs_subtitles.txt", "w", encoding="utf-8") as f:
                f.write(f"[{lang}] {text}")
            _set_module_runtime("stream", "Actif", f"OBS principal: [{lang}] {str(text)[:64]}")
        except Exception: 
            pass
        update_polyglot_obs_subtitle(text, lang)

async def _get_edge_audio_async(text, voice_name):
    communicate = edge_tts.Communicate(text, voice_name); mp3_data = b""
    async for chunk in communicate.stream():
        if chunk["type"] == "audio": mp3_data += chunk["data"]
    return mp3_data
    
def hybrid_activation_loop():
    stealth_print("🎙️ [HYBRID] Mode Master-Logic (Bypass Texte Actif).")
    import collections, numpy as np, io, soundfile as sf
    from difflib import SequenceMatcher

    CHUNK = 1024 
    last_text = ""
    pre_roll = collections.deque(maxlen=40) 
    
    while True:
        # On garde la détection vocale active même si l'audio sortant est bypassé.
        if not AUDIO_CONFIG.get("hybrid_activation_active") or _ptt_rec:
            if not AUDIO_CONFIG.get("hybrid_activation_active"):
                _set_module_runtime("hybrid", "Inactif", "Détection automatique de la voix désactivée")
            time.sleep(1.0); pre_roll.clear(); continue
        _set_module_runtime("hybrid", "Écoute", "En attente d'une phrase micro")

        try:
            tid = resolve_input_device_cfg(AUDIO_CONFIG.get("game_input_device"))
            if tid is None:
                tid = resolve_input_device_cfg(sd.default.device[0])
            if tid is None:
                raise RuntimeError("Aucun micro valide pour Hybrid.")
            AUDIO_CONFIG["game_input_device_key"] = _normalize_device_signature(
                sd.query_devices()[int(tid)].get("name", ""),
                str(sd.query_hostapis()[int(sd.query_devices()[int(tid)].get("hostapi", -1))].get("name", "")) if int(sd.query_devices()[int(tid)].get("hostapi", -1)) >= 0 else ""
            )
            AUDIO_CONFIG["game_input_device_runtime"] = _device_runtime_payload(tid)
            info = sd.query_devices(tid)
            rate = int(info['default_samplerate'])
            
            chs = min(info['max_input_channels'], 2)
            thresh = float(AUDIO_CONFIG.get("vad_threshold", 0.02)) * 32768

            with sd.InputStream(device=tid, channels=chs, samplerate=rate, blocksize=CHUNK, dtype="int16") as stream:
                recording = False
                phrase_buffer = []
                silence_frames = 0

                while AUDIO_CONFIG.get("hybrid_activation_active") and not _ptt_rec:
                    data, _ = stream.read(CHUNK)
                    
                    if chs == 2: mono = data.mean(axis=1).astype(np.int16)
                    else: mono = data.flatten()
                    
                    vol = np.abs(mono).max()

                    if not recording:
                        if vol > thresh:
                            stealth_print(f"🎤 [Auto] Phrase...")
                            _set_module_runtime("hybrid", "Déclenché", "Voix détectée automatiquement")
                            recording = True; global _hybrid_running; _hybrid_running = True
                            phrase_buffer = list(pre_roll); phrase_buffer.append(mono); silence_frames = 0
                        else:
                            pre_roll.append(mono)
                    else:
                        phrase_buffer.append(mono)
                        if vol < (thresh * 0.4): silence_frames += 1
                        else: silence_frames = 0
                        
                        if silence_frames > 90 or len(phrase_buffer) > 1400:
                            all_audio = np.concatenate(phrase_buffer)
                            recording = False; _hybrid_running = False
                            
                            if len(all_audio) > (rate * 0.5):
                                audio_f = all_audio.astype(np.float32)
                                peak = np.abs(audio_f).max()
                                if peak > 0: audio_f = (audio_f / peak) * 0.9
                                ready = (audio_f * 32767).astype(np.int16)
                                
                                mem = io.BytesIO(); sf.write(mem, ready, rate, format='WAV'); mem.seek(0)
                                txt, det_lang = transcribe_safe(mem, rate)
                                
                                if txt and len(txt.strip()) > 1:
                                    if SequenceMatcher(None, last_text, txt).ratio() < 0.8:
                                        stealth_print(f"🤖 AUTO: {txt}")
                                        enqueue_user_pipeline(txt, (det_lang or "fr"), source="rts")
                                        last_text = txt
                            
                            phrase_buffer = []; silence_frames = 0; pre_roll.clear()
        except: time.sleep(2.0)
        
        
def deepgram_transcribe_local(audio_path, api_key):
    """Transcrire l'audio localement via Deepgram API (Ultra rapide)"""
    import requests
    try:
        with open(audio_path, "rb") as f:
            # On utilise nova-2 en mode 'detect_language' pour savoir ce que tu as dit
            url = "https://api.deepgram.com/v1/listen?model=nova-2&smart_format=true&detect_language=true"
            res = requests.post(url, headers={"Authorization": f"Token {api_key}", "Content-Type": "audio/wav"}, data=f, timeout=5)
            
            if res.status_code == 200:
                data = res.json()
                transcript = data['results']['channels'][0]['alternatives'][0]['transcript']
                detected_lang = data['results']['channels'][0]['detected_language']
                return transcript, detected_lang
    except Exception as e:
        stealth_print(f"⚠️ Erreur Deepgram Local: {e}")
    return "", "fr"        

def windows_natural_generator(text, specific_speed=None, voice_override=None):
    """
    Générateur Polyvalent :
    - voice_override : Permet de forcer une voix (ex: Française pour les alliés)
    """
    import asyncio
    import edge_tts
    import miniaudio 
    
    def _normalize_edge_rate(raw_rate):
        """Normalise le format Edge rate et applique des bornes sûres."""
        val = str(raw_rate or "").strip()
        m = re.match(r"^([+-]?)(\d{1,3})%$", val)
        if not m:
            return "-10%"
        sign = -1 if m.group(1) == "-" else 1
        num = int(m.group(2)) * sign
        # Garde-fou global: éviter une voix trop rapide/lente.
        num = max(-30, min(10, num))
        return f"{num:+d}%"

    configured_rate = AUDIO_CONFIG.get("windows_tts_rate", "-10%")
    rate = _normalize_edge_rate(specific_speed if specific_speed is not None else configured_rate)
    
    # --- LOGIQUE DE CHOIX DE VOIX + FALLBACKS ROBUSTES ---
    if voice_override:
        preferred_voice = str(voice_override).strip()
    else:
        preferred_voice = str(AUDIO_CONFIG.get("edge_voice") or "").strip()
    if not preferred_voice:
        preferred_voice = "fr-FR-VivienneMultilingualNeural"

    voice_candidates = [preferred_voice]
    # Fallbacks sûrs en EXE si la voix configurée n'est pas dispo localement.
    for v in ("fr-FR-VivienneMultilingualNeural", "en-US-GuyNeural"):
        if v not in voice_candidates:
            voice_candidates.append(v)

    async def _fetch_with_voice(voice_name):
        try:
            communicate = edge_tts.Communicate(text, voice_name, rate=rate)
            audio_data = b""
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_data += chunk["data"]
            return audio_data
        except Exception as e:
            stealth_print(f"⚠️ Edge TTS voice '{voice_name}' error: {e}")
            return b""

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        mp3_bytes = b""
        used_voice = ""
        for candidate in voice_candidates:
            mp3_bytes = loop.run_until_complete(_fetch_with_voice(candidate))
            if mp3_bytes:
                used_voice = candidate
                break
        loop.close()
        if mp3_bytes:
            if used_voice:
                stealth_print(f"🗣️ Edge TTS voice utilisée: {used_voice} ({rate})")
            decoded = miniaudio.decode(mp3_bytes, nchannels=1, sample_rate=16000, output_format=miniaudio.SampleFormat.SIGNED16)
            yield decoded.samples.tobytes()
        else:
            stealth_print("⚠️ Edge TTS: aucun audio généré (toutes les voix fallback ont échoué).")
    except Exception as e:
        stealth_print(f"⚠️ Edge TTS generator error: {e}")
        yield []
    
    
def get_real_speakers():
    """Cherche une sortie audio physique et affiche ce qu'il trouve."""
    try:
        candidates = []
        stealth_print("🔍 Recherche Casque/Haut-parleurs :")
        
        for i, dev in enumerate(sd.query_devices()):
            if dev['max_output_channels'] > 0:
                name = dev['name'].upper()
                # On ignore les Câbles virtuels et drivers Nvidia HDMI souvent silencieux
                if "CABLE" not in name and "VB-AUDIO" not in name and "NVIDIA" not in name:
                    candidates.append((i, dev['name']))
                    stealth_print(f"   [ID {i}] Trouvé : {dev['name']}")

        # Si on a trouvé des candidats, on prend le premier qui contient "SPEAKERS" ou "CASQUE"
        # Sinon on prend le premier de la liste
        if candidates:
            for cid, cname in candidates:
                if "CASQUE" in cname.upper() or "HEADSET" in cname.upper() or "SPEAKERS" in cname.upper():
                    return cid
            return candidates[0][0] # Le premier de la liste filtrée
            
        # Si vraiment rien, on retourne le défaut Windows
        return sd.default.device[1]
    except:
        return 0   
 
def get_physical_output_candidates(exclude_ids=None):
    """Retourne des sorties physiques triées (casque/HP), hors virtual audio."""
    try:
        ex = set()
        for x in (exclude_ids or []):
            try:
                ex.add(int(x))
            except Exception:
                pass

        # Récupérer le NOM du device de sortie par défaut Windows via pycaw (Core Audio API).
        # sd.default.device est mis en cache par PortAudio au démarrage et ne suit PAS
        # un changement de périphérique par défaut fait dans Windows en live (Panneau son) —
        # pycaw interroge Windows directement à chaque appel, donc toujours à jour.
        _dflt_out_name = None
        try:
            from pycaw.pycaw import AudioUtilities
            _dflt_dev_id = AudioUtilities.GetSpeakers().GetId()
            for _d in AudioUtilities.GetAllDevices():
                if _d.id == _dflt_dev_id:
                    _dflt_out_name = _norm_dev_name(_d.FriendlyName)
                    break
        except Exception:
            _dflt_out_name = None

        # Trouver l'index PortAudio correspondant à ce nom (fallback sur sd.default.device si échec)
        _dflt_out_idx = -1
        devs = sd.query_devices()
        if _dflt_out_name:
            for i, dev in enumerate(devs):
                if int(dev.get("max_output_channels", 0)) <= 0:
                    continue
                if _norm_dev_name(dev.get("name", "")) == _dflt_out_name:
                    _dflt_out_idx = i
                    break
        if _dflt_out_idx < 0:
            try:
                _dflt = sd.default.device
                for _getter in [
                    lambda d: int(d[1]),
                    lambda d: int(d.output),
                    lambda d: int(list(d)[1]),
                ]:
                    try:
                        _dflt_out_idx = _getter(_dflt)
                        if _dflt_out_idx >= 0:
                            break
                    except Exception:
                        continue
            except Exception:
                _dflt_out_idx = -1
        hostapis = sd.query_hostapis()
        scored = []
        for i, dev in enumerate(devs):
            if i in ex:
                continue
            if int(dev.get("max_output_channels", 0)) <= 0:
                continue
            n = _norm_dev_name(dev.get("name", ""))
            if any(x in n for x in ["CABLE", "VB-AUDIO", "VIRTUAL", "VOICEMEETER", "LOOPBACK"]):
                continue

            score = 0
            # Priorité absolue au device par défaut Windows (+200)
            if _dflt_out_idx >= 0 and i == _dflt_out_idx:
                score += 200
            if any(x in n for x in ["HEADSET", "CASQUE", "SPEAKERS", "HAUT-PARLEUR"]):
                score += 50
            if any(x in n for x in ["REALTEK", "USB", "AUDIO"]):
                score += 20
            try:
                hidx = int(dev.get("hostapi", -1))
                if 0 <= hidx < len(hostapis):
                    hname = str(hostapis[hidx].get("name", "")).upper()
                    if "WASAPI" in hname:
                        score += 10
            except Exception:
                pass
            scored.append((score, int(i)))

        scored.sort(reverse=True)
        return [i for _, i in scored]
    except Exception:
        return []


def get_monitor_output_device_ids(exclude_ids=None, max_devices=2):
    """
    Retourne des sorties de monitoring robustes:
    1) devices physiques détectés
    2) fallback sur toute sortie non exclue
    """
    ex = set()
    for x in (exclude_ids or []):
        try:
            ex.add(int(x))
        except Exception:
            pass

    candidates = get_physical_output_candidates(exclude_ids=list(ex))
    if candidates:
        dflt = get_default_output_device_id()
        ordered = list(candidates)
        if dflt is not None and dflt not in ex:
            try:
                did = int(dflt)
                if did in ordered:
                    ordered.remove(did)
                ordered.insert(0, did)
            except Exception:
                pass
        return ordered[:max_devices]

    try:
        devs = sd.query_devices()
        fallback = []
        dflt = get_default_output_device_id()
        if dflt is not None and dflt not in ex:
            if 0 <= int(dflt) < len(devs) and int(devs[int(dflt)].get("max_output_channels", 0)) > 0:
                fallback.append(int(dflt))
        for i, d in enumerate(devs):
            if i in ex:
                continue
            if int(d.get("max_output_channels", 0)) > 0:
                if int(i) not in fallback:
                    fallback.append(int(i))
        return fallback[:max_devices]
    except Exception:
        return []


def get_default_output_device_id():
    """Compat: sd.default.device peut être tuple/list ou objet avec .output."""
    def _to_int_idx(v):
        try:
            if isinstance(v, (list, tuple)):
                if len(v) >= 2:
                    return int(v[1])
                if len(v) == 1:
                    return int(v[0])
                return None
            # sounddevice >=0.5 peut exposer un _InputOutputPair
            # (itérable mais non tuple/list) avec attributs input/output.
            if hasattr(v, "__getitem__"):
                try:
                    return int(v[1])
                except Exception:
                    pass
            if hasattr(v, "output"):
                outv = getattr(v, "output")
                if outv is not v:
                    got = _to_int_idx(outv)
                    if got is not None:
                        return got
                try:
                    return int(outv)
                except Exception:
                    pass
            if hasattr(v, "index"):
                return int(getattr(v, "index"))
            return int(v)
        except Exception:
            return None

    try:
        d = sd.default.device
        out_idx = _to_int_idx(d)
        if out_idx is not None and out_idx >= 0:
            return out_idx
    except Exception:
        pass
    return None


def find_wasapi_loopback_input_device():
    """Trouve un device input WASAPI loopback dans sounddevice."""
    try:
        devs = sd.query_devices()
        hostapis = sd.query_hostapis()
        default_out = get_default_output_device_id()
        default_name = ""
        if default_out is not None and 0 <= int(default_out) < len(devs):
            default_name = _norm_dev_name(devs[int(default_out)].get("name", ""))

        cands = []
        for i, dev in enumerate(devs):
            if int(dev.get("max_input_channels", 0)) <= 0:
                continue
            hidx = int(dev.get("hostapi", -1))
            hname = str(hostapis[hidx].get("name", "")).upper() if 0 <= hidx < len(hostapis) else ""
            if "WASAPI" not in hname:
                continue
            n = _norm_dev_name(dev.get("name", ""))
            if "LOOPBACK" not in n:
                continue
            score = 10
            if default_name and default_name.split(" (")[0] in n:
                score += 30
            cands.append((score, int(i)))
        if not cands:
            return None
        cands.sort(reverse=True)
        return int(cands[0][1])
    except Exception:
        return None


def get_physical_headset(exclude_ids=None):
    """Détecte une sortie physique (casque/HP) en excluant les devices virtuels."""
    try:
        def _is_virtual_output_name(name: str):
            n = str(name or "").upper()
            return any(x in n for x in ["CABLE", "VB-AUDIO", "VIRTUAL", "VOICEMEETER"])

        candidates = get_physical_output_candidates(exclude_ids=exclude_ids)
        if candidates:
            return int(candidates[0])

        # 2) Fallback: défaut Windows seulement s'il n'est pas virtuel
        devices = sd.query_devices()
        default_out = int(sd.default.device[1])
        if 0 <= default_out < len(devices):
            dname = str(devices[default_out].get("name", ""))
            if (not _is_virtual_output_name(dname)) and (default_out not in set(exclude_ids or [])):
                return default_out
    except Exception:
        pass
    return None


# ✅ OPTIMIZED: Version modifiée de resample_and_play
def resample_and_play(audio_gen, text_to_show="", speaker_name="MOI", source_hz=48000, emotion_hint=""):
    global _is_speaking
    if text_to_show:
        add_subtitle(text_to_show, speaker_name)

    is_me = (speaker_name == "MOI")
    if AUDIO_CONFIG.get("bypass_mode_active", False) and is_me:
        return

    target_ids = []

    def _append_valid_output_device(dev_idx):
        try:
            if dev_idx is None:
                return
            dev_idx = int(dev_idx)
            devs = sd.query_devices()
            if 0 <= dev_idx < len(devs) and int(devs[dev_idx].get("max_output_channels", 0)) > 0:
                target_ids.append(dev_idx)
        except Exception:
            return

    if is_me:
        cid = find_cable_output_device()
        if cid is None:
            cid = resolve_output_device_cfg(AUDIO_CONFIG.get("game_output_device", 0))
        if cid is not None:
            target_ids.append(int(cid))
        # F3 actif : monitoring_loop relaie déjà CABLE→casque
        # Ne pas ajouter les devices physiques — conflit de streams → silence
        if AUDIO_CONFIG.get("monitoring_enabled", False):
            pass  # monitoring_loop gère le relai, TTS → CABLE suffit
    else:
        # ALLY TTS désactivé: pas d'erreur, on quitte silencieusement.
        if not AUDIO_CONFIG.get("tts_active", True):
            return
        cid = find_cable_output_device()
        # 1) Même stratégie que monitoring (priorité casque/HP physique hors CABLE).
        for did in get_monitor_output_device_ids(exclude_ids=[cid], max_devices=2):
            _append_valid_output_device(did)

        # 2) Fallback sur sortie Windows par défaut, même si le nom n'est pas reconnu.
        if not target_ids:
            dflt = get_default_output_device_id()
            if dflt is not None and (cid is None or int(dflt) != int(cid)):
                _append_valid_output_device(dflt)

        # 3) Ultime fallback: première sortie dispo hors CABLE.
        if not target_ids:
            try:
                devs = sd.query_devices()
                first_any = None
                for i, d in enumerate(devs):
                    if int(d.get("max_output_channels", 0)) <= 0:
                        continue
                    if first_any is None:
                        first_any = int(i)
                    if cid is not None and int(i) == int(cid):
                        continue
                    _append_valid_output_device(int(i))
                    break
                if (not target_ids) and (first_any is not None):
                    _append_valid_output_device(first_any)
            except Exception:
                pass

        # 4) Fallback final: ne jamais rester muet, utiliser CABLE / sortie jeu.
        if not target_ids:
            if cid is not None:
                _append_valid_output_device(cid)
            if not target_ids:
                _append_valid_output_device(resolve_output_device_cfg(AUDIO_CONFIG.get("game_output_device", 0)))

    if not target_ids:
        # Filet de sécurité ultime: tenter la sortie Windows par défaut.
        target_ids = [None]
        stealth_print("⚠️ Aucune sortie audio résolue -> fallback sortie Windows par défaut.")
    try:
        stealth_print(f"🔈 Playback targets ({speaker_name}): {list(dict.fromkeys(target_ids))}")
    except Exception:
        pass

    import numpy as np
    import wave
    import io

    try:
        # Collecter tous les chunks (normalement un seul)
        all_data = b""
        for chunk in audio_gen:
            if chunk:
                all_data += chunk

        if not all_data:
            return

        # Détection du format WAV
        if all_data.startswith(b'RIFF'):
            # C'est un fichier WAV, on extrait les données PCM
            with io.BytesIO(all_data) as f:
                with wave.open(f, 'rb') as wav:
                    frames = wav.getnframes()
                    audio_bytes = wav.readframes(frames)
                    audio_float = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
                    audio_float = np.clip(audio_float, -1.0, 1.0)
                    sr = wav.getframerate()
        else:
            # Sinon, considérer que c'est du PCM brut à la fréquence source_hz
            audio_float = pcm_bytes_to_float32(all_data)
            sr = source_hz

        if len(audio_float) == 0:
            return

        # Resampling si nécessaire pour atteindre 48 kHz (sortie du casque)
        if sr != 48000:
            audio_48k = resample_audio(audio_float, sr_from=sr, sr_to=48000)
        else:
            audio_48k = audio_float

        # Anti-saturation at playback stage (device-dependent clipping protection).
        try:
            vol_cfg = float(AUDIO_CONFIG.get("tts_volume", 1.0) or 1.0)
        except Exception:
            vol_cfg = 1.0
        vol_cfg = max(0.20, min(1.00, vol_cfg))
        emotion_text = str(emotion_hint or "")
        laugh_play = bool(re.search(r"\b(?:ha+|haha+|hahaha+|はは|ふふ)\b", emotion_text, re.IGNORECASE))
        sigh_play = bool(re.search(r"\b(?:pff+|phew+|sigh|ふぅ|はぁ)\b", emotion_text, re.IGNORECASE))
        hesitation_play = bool(re.search(r"\b(?:euh+|heu+|uh+|hum+|hmm+|えっと)\b", emotion_text, re.IGNORECASE))
        # Keep fixed headroom then soft-clip harsh peaks.
        base_gain = 0.82 * vol_cfg
        limiter_drive = 1.12
        teamsync_gain = get_teamsync_playback_gain()
        if teamsync_gain > 1.0:
            base_gain *= teamsync_gain
        if laugh_play:
            base_gain *= 0.72
            limiter_drive = 1.35
        elif sigh_play or hesitation_play:
            base_gain *= 0.84
            limiter_drive = 1.18
        audio_48k = audio_48k * base_gain
        audio_48k = np.tanh(audio_48k * limiter_drive) / np.tanh(limiter_drive)
        audio_48k = np.clip(audio_48k, -1.0, 1.0)

        # File FIFO par flux (MOI / ALLIÉ) — remplace l'ancien lock à timeout 8s
        # qui abandonnait silencieusement une phrase si la précédente durait plus longtemps.
        # Ici : chaque phrase attend son tour et est TOUJOURS jouée, dans l'ordre d'arrivée.
        queue_name = "MOI" if is_me else "ALLIÉ"
        _ensure_playback_worker(queue_name)
        try:
            _playback_queues[queue_name].put(
                (list(dict.fromkeys(target_ids)), audio_48k, speaker_name),
                timeout=30,
            )
        except queue.Full:
            stealth_print(f"⚠️ File playback {queue_name} saturée (>6 phrases en attente), audio ignoré.")

    except Exception as e:
        stealth_print(f"⚠️ Erreur Stream : {e}")


# File d'attente FIFO de lecture — une par flux (MOI/ALLIÉ), pour ne jamais perdre
# de phrase même si la synthèse va plus vite que la lecture audio.
_playback_queues = {"MOI": queue.Queue(maxsize=6), "ALLIÉ": queue.Queue(maxsize=6)}
_playback_workers_started = {}
_playback_workers_lock = threading.Lock()


def _ensure_playback_worker(queue_name):
    with _playback_workers_lock:
        if not _playback_workers_started.get(queue_name):
            t = threading.Thread(target=_playback_worker, args=(queue_name,), daemon=True, name=f"PlaybackWorker-{queue_name}")
            t.start()
            _playback_workers_started[queue_name] = True


def _playback_worker(queue_name):
    q = _playback_queues[queue_name]
    while True:
        item = q.get()
        if item is None:
            continue
        target_ids, audio_48k, speaker_name = item
        _do_playback(target_ids, audio_48k, speaker_name)


def _do_playback(target_ids, audio_48k, speaker_name):
    global _is_speaking
    _is_speaking = True
    if _is_turbo_mode_active():
        _set_module_runtime("turbo", "Lecture", "Sortie audio priorisée")
    try:
        for did in target_ids:
            try:
                if did is None:
                    sd.play(audio_48k, samplerate=48000)
                    sd.wait()
                else:
                    # BUG 2 fix — valider que le device existe avant d'ouvrir le stream
                    try:
                        dev_info = sd.query_devices(int(did))
                        if int(dev_info.get("max_output_channels", 0)) <= 0:
                            stealth_print(f"⚠️ Device [{did}] sans canaux de sortie, ignoré.")
                            continue
                        dev_sr = int(float(dev_info.get("default_samplerate", 48000) or 48000))
                    except Exception as dev_err:
                        stealth_print(f"⚠️ Device [{did}] invalide ({dev_err}), ignoré.")
                        continue
                    # BUG B fix — rééchantillonner pour matcher le device de sortie
                    if dev_sr != 48000 and dev_sr > 0:
                        audio_dev = resample_audio(audio_48k, sr_from=48000, sr_to=dev_sr)
                    else:
                        audio_dev = audio_48k
                    sd.play(audio_dev, samplerate=dev_sr, device=int(did))
                    sd.wait()
            except Exception as e:
                dev_label = "DEFAULT" if did is None else str(did)
                err_str = str(e)
                # -9996 = paDeviceUnavailable (device occupé/exclusif) → skip silencieux
                if "-9996" in err_str or "unavailable" in err_str.lower():
                    stealth_print(f"ℹ️ Device [{dev_label}] occupé (skip): {e}")
                else:
                    stealth_print(f"⚠️ Lecture échouée sur device [{dev_label}]: {e}")
        stealth_print("🔊 Lecture terminée")
    except Exception as e:
        stealth_print(f"⚠️ Erreur Stream : {e}")
    finally:
        _is_speaking = False

# ==================== MOTEUR DE CAPTURE PTT ====================

# MOVED TO modules/stt/stt.py
def mic_cb(indata, frames, time, status):
    """
    Cette fonction est appelée automatiquement par la carte son
    à chaque fois qu'elle a des données audio (toutes les millisecondes).
    """
    if status:
        stealth_print(f"⚠️ Status Micro: {status}")
    
    b = bytes(indata)
    # Toujours garder un petit buffer pour pre-roll (utile si on garde le stream ouvert).
    _ptt_preroll.append(b)
    # Si l'enregistrement est actif, on stocke le son
    if _ptt_rec:
        _ptt_chunks.append(b)


# MOVED TO modules/stt/stt.py
def _ptt_keepalive_enabled() -> bool:
    # "Turbo" => mode reactivite: on garde le stream micro chaud + pre-roll.
    # Si besoin, on pourra exposer un toggle UI plus tard.
    return bool(AUDIO_CONFIG.get("turbo_latency_active", False))


# MOVED TO modules/stt/stt.py
def _ensure_ptt_stream_open(target_mic_id: int, native_rate: int, channels: int):
    """Ouvre (ou re-ouvre) le RawInputStream PTT et le laisse actif en mode keepalive."""
    global _ptt_stream, _ptt_stream_device, _ptt_rec
    # Si device change, on re-ouvre proprement.
    if _ptt_stream is not None and _ptt_stream_device is not None and int(_ptt_stream_device) != int(target_mic_id):
        try:
            _ptt_stream.stop(); _ptt_stream.close()
        except Exception:
            pass
        _ptt_stream = None
        _ptt_stream_device = None
        _ptt_rec = False
        try:
            _ptt_preroll.clear()
        except Exception:
            pass

    if _ptt_stream is None:
        _ptt_stream = sd.RawInputStream(
            samplerate=native_rate,
            blocksize=1024,
            channels=int(channels),
            dtype="int16",
            callback=mic_cb,
            device=int(target_mic_id),
        )
        _ptt_stream.start()
        _ptt_stream_device = int(target_mic_id)

# MOVED TO modules/stt/stt.py
def start_rec():
    global _ptt_stream, _ptt_rec, _ptt_chunks, _ptt_stream_device, _ptt_preroll
    global _ptt_last_start_ts
    now = time.time()
    if (now - float(_ptt_last_start_ts or 0.0)) < 0.08:
        return
    _ptt_last_start_ts = now
    
    # ⚠️ MODIFICATION : On a retiré le blocage "if bypass return" ici.
    # On veut que ça enregistre et transcrive (texte), c'est plus loin qu'on bloquera le son (TTS).
    
    if (not COMMUNITY_EDITION) and (not LICENSE_MGR.is_activated):
        stealth_print("⚠️ Licence non active.")
        return
    
    target_mic_id = resolve_input_device_cfg(AUDIO_CONFIG.get("game_input_device"))
    if target_mic_id is None:
        target_mic_id = resolve_input_device_cfg(sd.default.device[0])
    if target_mic_id is None:
        stealth_print("❌ Aucun micro d'entrée valide détecté.")
        return
    AUDIO_CONFIG["game_input_device_key"] = _normalize_device_signature(
        sd.query_devices()[int(target_mic_id)].get("name", ""),
        str(sd.query_hostapis()[int(sd.query_devices()[int(target_mic_id)].get("hostapi", -1))].get("name", "")) if int(sd.query_devices()[int(target_mic_id)].get("hostapi", -1)) >= 0 else ""
    )
    AUDIO_CONFIG["game_input_device_runtime"] = _device_runtime_payload(target_mic_id)

    with _ptt_lock:
        if _ptt_rec: return 
        # Seed avec preroll si keepalive actif (sinon ce buffer est quasi vide).
        _ptt_chunks = list(_ptt_preroll) if _ptt_keepalive_enabled() else []
        
        try:
            dev_info = sd.query_devices(target_mic_id)
            native_rate = int(dev_info['default_samplerate'])
            max_in_ch = int(dev_info.get("max_input_channels", 0) or 0)
            dev_name = str(dev_info.get("name", target_mic_id))
            AUDIO_CONFIG["mic_sample_rate"] = native_rate 

            stealth_print(f"🔴 REC ({native_rate}Hz)...")

            if max_in_ch <= 0:
                raise RuntimeError(f"Device sans entrée micro: {dev_name} (id={target_mic_id})")

            # Fallback channels: prefer mono, then stereo, then max supported.
            ch_candidates = []
            for ch in (1, 2, max_in_ch):
                ch = int(ch)
                if 1 <= ch <= max_in_ch and ch not in ch_candidates:
                    ch_candidates.append(ch)

            last_open_err = None
            opened_ch = None
            for ch in ch_candidates:
                try:
                    # En mode keepalive: on garde le stream ouvert entre les press/release.
                    if _ptt_keepalive_enabled():
                        _ensure_ptt_stream_open(target_mic_id, native_rate, ch)
                    else:
                        _ptt_stream = sd.RawInputStream(
                            samplerate=native_rate,
                            blocksize=1024,
                            channels=ch,
                            dtype="int16",
                            callback=mic_cb,
                            device=target_mic_id
                        )
                        _ptt_stream.start()
                        _ptt_stream_device = int(target_mic_id)
                    opened_ch = int(ch)
                    AUDIO_CONFIG["mic_input_channels"] = int(ch)
                    break
                except Exception as open_err:
                    last_open_err = open_err
                    _ptt_stream = None
                    _ptt_stream_device = None

            if _ptt_stream is None or opened_ch is None:
                raise RuntimeError(
                    f"Ouverture micro impossible (id={target_mic_id}, name={dev_name}, "
                    f"max_in={max_in_ch}, tried={ch_candidates}): {last_open_err}"
                )

            _ptt_rec = True
            if AUDIO_CONFIG.get("turbo_latency_active", False):
                _set_module_runtime("turbo", "Capture", "Pipeline rapide actif pendant l'enregistrement micro")
            
        except Exception as e:
            stealth_print(f"❌ Erreur REC : {e}")
            _ptt_rec = False


GAMING_CORRECTIONS = {
    "valo rente": "Valorant", "valo rang": "Valorant", "cs go": "CS:GO", "cs 2": "CS2",
    "league of legend": "League of Legends", "lol": "LoL", "rocket ligue": "Rocket League",
    "fort night": "Fortnite", "call of": "Call of Duty", "war zone": "Warzone", "over watch": "Overwatch",
    "gg wp": "GG WP", "jiji": "GG", "afk": "AFK", "a f k": "AFK", "p v p": "PVP", "p v e": "PVE",
    "low h p": "Low HP", "lo life": "Low Life", "rez moi": "Rez-moi", "res moi": "Rez-moi",
    "ult": "Ultimate", "ulti": "Ultimate", "smurf": "Smurf", "cheat": "Cheater", "aim bot": "Aimbot"
}

def clean_gaming_text(text):
    text_lower = text.lower()
    for error, fix in GAMING_CORRECTIONS.items():
        if error in text_lower:
            pattern = re.compile(re.escape(error), re.IGNORECASE)
            text = pattern.sub(fix, text)
    return text


def normalize_emotion_cues_for_tts(text: str) -> str:
    """Convert explicit laugh cues into pronounceable laughter for TTS."""
    s = str(text or "").strip()
    if not s:
        return s
    s = re.sub(r"\b(?:je\s+rigole|je\s+ris|rire|rires|rigole|rigoler)\b", "ha ha ha", s, flags=re.IGNORECASE)
    s = re.sub(r"\b(?:mdr|lol)\b", "ha ha ha", s, flags=re.IGNORECASE)
    # Keep sequences like "ah ah ah" literal and stable.
    s = re.sub(r"\b(?:a+h?|h+a?)(?:[\s,.;:!?-]+(?:a+h?|h+a?)){2,}\b", "ha ha ha", s, flags=re.IGNORECASE)
    return re.sub(r"\s{2,}", " ", s).strip()


def _lang_token_variant(kind: str, lang_hint: str = "fr", profile: str = "gaming", intensity: str = "medium") -> str:
    lang = str(lang_hint or "fr").strip().lower()
    profile = str(profile or "gaming").strip().lower()
    intensity = str(intensity or "medium").strip().lower()
    if lang.startswith("ja"):
        mapping = {
            "laugh": "ははは..." if intensity != "strong" else "ははっ、ははは!",
            "sigh": "ふぅ..." if profile != "roleplay" else "はぁ...",
            "hesitation": "えっと..." if profile != "pro" else "少し...",
            "interjection": "おっ!" if intensity == "strong" else "おっ...",
            "breath": "ん..." if profile == "pro" else "ふぅ...",
            "cough": "ごほ..." if intensity != "strong" else "ごほっ...",
            "sniff": "すっ..." if profile != "pro" else "...",
        }
        return mapping.get(kind, "")
    if lang.startswith("en"):
        mapping = {
            "laugh": "ha... ha... ha..." if intensity != "strong" else "ha! ha! ha!",
            "sigh": "phew..." if profile == "gaming" else "sigh...",
            "hesitation": "uh..." if profile != "pro" else "well...",
            "interjection": "oh!" if intensity == "strong" else "oh...",
            "breath": "hmm..." if profile != "pro" else "...",
            "cough": "ahem..." if intensity != "strong" else "ahem!",
            "sniff": "sniff..." if profile != "pro" else "...",
        }
        return mapping.get(kind, "")
    mapping = {
        "laugh": "ha... ha... ha..." if intensity != "strong" else "ha ! ha ! ha !",
        "sigh": "pff..." if profile == "gaming" else ("ah..." if profile == "roleplay" else "..."),
        "hesitation": "euh..." if profile != "pro" else "hum...",
        "interjection": "oh !" if intensity == "strong" else "oh...",
        "breath": "hmm..." if profile != "pro" else "...",
        "cough": "hem..." if intensity != "strong" else "hem !",
        "sniff": "snif..." if profile != "pro" else "...",
    }
    return mapping.get(kind, "")


def _analyze_expressive_cues(text: str) -> dict:
    s = str(text or "").strip()
    lower = s.lower()
    patterns = {
        "laugh": r"\b(?:je\s+rigole|je\s+ris|rigole|rigoler|rire|rires|rires?|mdr|lol|lmao|haha+|hahaha+|hehe+|hihi+|ah ah+|ha ha+)\b",
        "sigh": r"\b(?:soupir|soupire|pff+|pfou+|pfiou+|ouf+|rah+|roh+|meh+)\b",
        "hesitation": r"\b(?:euh+|heu+|hum+|hmm+|mmh+|mmm+|bah+|ben+)\b",
        "interjection": r"\b(?:oh+|ah+|eh+|wow+|whoa+|allez+|go+|let's\s+go|vas-y)\b",
        "breath": r"\b(?:souffle|respire|inspire|expire|souffler|respiration)\b",
    }
    counts = {key: len(re.findall(pattern, lower, flags=re.IGNORECASE)) for key, pattern in patterns.items()}
    total = sum(counts.values())
    if total >= 4:
        intensity = "strong"
    elif total >= 2:
        intensity = "medium"
    else:
        intensity = "soft"
    active = [key for key, value in counts.items() if value > 0]
    primary = active[0] if active else ""
    confidence = min(
        1.0,
        (0.22 * len(active))
        + (0.18 * total)
        + (0.16 if primary in {"laugh", "interjection"} else (0.08 if primary else 0.0)),
    )
    return {
        "counts": counts,
        "active": active,
        "primary": primary,
        "total": total,
        "intensity": intensity,
        "confidence": round(confidence, 2),
    }


def _strip_expressive_cues_for_display(text: str) -> str:
    s = str(text or "")
    if not s:
        return s
    cleanup_patterns = [
        r"\b(?:je\s+rigole|je\s+ris|rigole|rigoler|rire|rires|mdr|lol|haha+|hahaha+|hehe+|hihi+)\b",
        r"\b(?:soupir|soupire|pff+|pfou+|pfiou+|ouf+|rah+)\b",
        r"\b(?:euh+|heu+|hum+|hmm+|mmh+|mmm+)\b",
        r"\b(?:souffle|respire|inspire|expire)\b",
    ]
    for pattern in cleanup_patterns:
        s = re.sub(pattern, " ", s, flags=re.IGNORECASE)
    s = re.sub(r"\s{2,}", " ", s)
    s = re.sub(r"\s+([,.;:!?])", r"\1", s)
    return s.strip(" ,.;:!?") or str(text or "").strip()


def _resolve_expressive_engine_target() -> str:
    try:
        target_lang = str(CURRENT_TARGET_LANG or AUDIO_CONFIG.get("target_lang") or "fr").strip().lower()
    except Exception:
        target_lang = "fr"
    hybrid_on = _to_bool(AUDIO_CONFIG.get("gpt_style_to_xtts_fr", False), False)
    if hybrid_on and _is_hybrid_supported_target_lang(target_lang):
        return "hybrid"
    return "xtts"


def _resolve_expressive_intensity(analysis: dict) -> str:
    mode = str(AUDIO_CONFIG.get("expressive_intensity_mode", "auto") or "auto").strip().lower()
    if mode in {"soft", "medium", "strong"}:
        return mode
    return str(analysis.get("intensity") or "soft").strip().lower()


def _resolve_expressive_engine_mode(engine_target: str) -> str:
    global_mode = str(AUDIO_CONFIG.get("expressive_tts_mode", "styled") or "styled").strip().lower()
    if engine_target == "hybrid":
        specific = str(AUDIO_CONFIG.get("expressive_hybrid_mode", "auto") or "auto").strip().lower()
    else:
        specific = str(AUDIO_CONFIG.get("expressive_xtts_mode", "auto") or "auto").strip().lower()
    if specific in {"styled", "neutral"}:
        return specific
    return global_mode if global_mode in {"styled", "neutral"} else "styled"


def _resolve_expressive_stability_mode() -> str:
    mode = str(AUDIO_CONFIG.get("expressive_stability_mode", "balanced") or "balanced").strip().lower()
    return mode if mode in {"reactive", "balanced", "stable"} else "balanced"


EXPRESSIVE_SOURCE_MEMORY = {
    "ptt": {"updated_at": 0.0},
    "rts": {"updated_at": 0.0},
    "manual": {"updated_at": 0.0},
}


def _normalize_expressive_source_mode(source_mode: str) -> str:
    src = str(source_mode or "").strip().lower()
    if src == "ptt":
        return "ptt"
    if src in {"rts", "listen", "ally"}:
        return "rts"
    return "manual"


def _resolve_expressive_source_mode(source_mode: str = "") -> str:
    src = _normalize_expressive_source_mode(source_mode)
    if src != "manual":
        return src
    active = _normalize_expressive_source_mode(_user_pipeline_active_source)
    return active if active != "manual" else src


def _resolve_expressive_usage_mode(source_mode: str) -> str:
    src = _resolve_expressive_source_mode(source_mode)
    if src == "ptt":
        mode = str(AUDIO_CONFIG.get("expressive_ptt_mode", "full") or "full").strip().lower()
        return mode if mode in {"full", "safe", "neutral"} else "full"
    if src == "rts":
        mode = str(AUDIO_CONFIG.get("expressive_rts_mode", "safe") or "safe").strip().lower()
        return mode if mode in {"full", "safe", "neutral"} else "safe"
    return "safe"


def _get_recent_expressive_runtime(source_mode: str = "", max_age_s: float = 8.0) -> dict:
    src = _resolve_expressive_source_mode(source_mode)
    slot = EXPRESSIVE_SOURCE_MEMORY.get(src) or {}
    try:
        updated_at = float(slot.get("updated_at") or 0.0)
    except Exception:
        updated_at = 0.0
    if updated_at <= 0.0 or (time.time() - updated_at) > float(max_age_s):
        return {}
    return dict(slot)


def _update_expressive_source_memory(source_mode: str, analysis: dict):
    src = _resolve_expressive_source_mode(source_mode)
    EXPRESSIVE_SOURCE_MEMORY[src] = {
        "updated_at": time.time(),
        "primary": str(analysis.get("primary") or ""),
        "active": list(analysis.get("active") or [])[:6],
        "intensity": str(analysis.get("intensity") or "soft"),
        "confidence": float(analysis.get("confidence") or 0.0),
    }


def _smooth_expressive_analysis(analysis: dict, stability_mode: str, source_mode: str = "") -> dict:
    mode = str(stability_mode or "balanced").strip().lower()
    if mode not in {"balanced", "stable"}:
        analysis["smoothed"] = False
        return analysis
    previous = _get_recent_expressive_runtime(source_mode, 8.0 if mode == "stable" else 5.0)
    prev_primary = str(previous.get("primary") or "").strip().lower()
    prev_active = [str(v).strip().lower() for v in (previous.get("active") or []) if str(v).strip()]
    prev_intensity = str(previous.get("intensity") or "").strip().lower()
    if not prev_primary:
        analysis["smoothed"] = False
        return analysis
    confidence = float(analysis.get("confidence") or 0.0)
    total = int(analysis.get("total") or 0)
    current_primary = str(analysis.get("primary") or "").strip().lower()
    if mode == "stable" and confidence < 0.56:
        analysis["primary"] = prev_primary
        analysis["active"] = list(dict.fromkeys(prev_active or [prev_primary]))
        if prev_intensity in {"soft", "medium", "strong"} and total <= 1:
            analysis["intensity"] = prev_intensity
        analysis["smoothed"] = True
        return analysis
    if mode == "balanced" and confidence < 0.36 and not current_primary:
        analysis["primary"] = prev_primary
        analysis["active"] = list(dict.fromkeys(prev_active or [prev_primary]))
        if prev_intensity in {"soft", "medium", "strong"} and total == 0:
            analysis["intensity"] = prev_intensity
        analysis["smoothed"] = True
        return analysis
    analysis["smoothed"] = False
    return analysis


def _protect_expressive_tokens(text: str, noise_mode: str = "smart") -> str:
    s = protect_laugh_tokens(text)
    replacements = {
        r"\b(?:pff+|pfou+|pfiou+|soupir|soupire|ouf+|rah+)\b": "__SIGH__",
        r"\b(?:euh+|heu+|hum+|hmm+|mmh+|mmm+)\b": "__HESITATION__",
        r"\b(?:oh+|ah+|eh+|wow+|whoa+)\b": "__INTERJECTION__",
        r"\b(?:souffle|respire|inspire|expire)\b": "__BREATH__",
        r"\b(?:toux|tousse|tousser|cough+|ahem+|khm+|hem+)\b": "__COUGH__",
        r"\b(?:renifle|reniflement|sniff+|snif+)\b": "__SNIFF__",
    }
    mode = str(noise_mode or "smart").strip().lower()
    if mode == "clean":
        replacements.pop(r"\b(?:souffle|respire|inspire|expire)\b", None)
        replacements.pop(r"\b(?:toux|tousse|tousser|cough+|ahem+|khm+|hem+)\b", None)
        replacements.pop(r"\b(?:renifle|reniflement|sniff+|snif+)\b", None)
    elif mode == "smart":
        replacements.pop(r"\b(?:toux|tousse|tousser|cough+|ahem+|khm+|hem+)\b", None)
        replacements.pop(r"\b(?:renifle|reniflement|sniff+|snif+)\b", None)
    for pattern, token in replacements.items():
        s = re.sub(pattern, f" {token} ", s, flags=re.IGNORECASE)
    return re.sub(r"\s{2,}", " ", s).strip()


def _restore_expressive_tokens(text: str, lang_hint: str = "fr", profile: str = "gaming", intensity: str = "medium", tts_mode: str = "styled") -> str:
    s = restore_laugh_tokens(text, lang_hint)
    if str(tts_mode or "styled").strip().lower() == "neutral":
        replacements = {
            "__SIGH__": "...",
            "__HESITATION__": "...",
            "__INTERJECTION__": "",
            "__BREATH__": "...",
        }
    else:
        replacements = {
            "__SIGH__": _lang_token_variant("sigh", lang_hint, profile, intensity),
            "__HESITATION__": _lang_token_variant("hesitation", lang_hint, profile, intensity),
            "__INTERJECTION__": _lang_token_variant("interjection", lang_hint, profile, intensity),
            "__BREATH__": _lang_token_variant("breath", lang_hint, profile, intensity),
            "__COUGH__": _lang_token_variant("cough", lang_hint, profile, intensity),
            "__SNIFF__": _lang_token_variant("sniff", lang_hint, profile, intensity),
        }
    for token, replacement in replacements.items():
        s = s.replace(token, replacement)
    return re.sub(r"\s{2,}", " ", s).strip()


def _apply_expressive_pack(text: str, src_lang: str, source_mode: str = ""):
    profile = str(AUDIO_CONFIG.get("expressive_profile", "gaming") or "gaming").strip().lower()
    transcript_mode = str(AUDIO_CONFIG.get("expressive_transcript_mode", "keep") or "keep").strip().lower()
    configured_tts_mode = str(AUDIO_CONFIG.get("expressive_tts_mode", "styled") or "styled").strip().lower()
    noise_mode = str(AUDIO_CONFIG.get("expressive_noise_mode", "smart") or "smart").strip().lower()
    intensity_mode = str(AUDIO_CONFIG.get("expressive_intensity_mode", "auto") or "auto").strip().lower()
    stability_mode = _resolve_expressive_stability_mode()
    fallback_guard = _to_bool(AUDIO_CONFIG.get("expressive_fallback_guard", True), True)
    source_mode = _resolve_expressive_source_mode(source_mode)
    usage_mode = _resolve_expressive_usage_mode(source_mode)
    engine_target = _resolve_expressive_engine_target()
    engine_mode = _resolve_expressive_engine_mode(engine_target)
    enabled = bool(AUDIO_CONFIG.get("expressive_sounds_enabled", True))
    analysis = _analyze_expressive_cues(text)
    analysis["intensity"] = _resolve_expressive_intensity(analysis)
    if usage_mode == "neutral":
        stability_mode = "stable"
        fallback_guard = True
        noise_mode = "clean"
        analysis["intensity"] = "soft"
    elif usage_mode == "safe":
        if stability_mode == "reactive":
            stability_mode = "balanced"
        fallback_guard = True
        if noise_mode == "keep":
            noise_mode = "smart"
        if analysis.get("intensity") == "strong":
            analysis["intensity"] = "medium"
    analysis = _smooth_expressive_analysis(analysis, stability_mode, source_mode)
    display_text = str(text or "").strip()
    text_tts = normalize_emotion_cues_for_tts(text)
    protected = protect_laugh_tokens(text_tts)
    effective_tts_mode = engine_mode
    if enabled:
        protected = _protect_expressive_tokens(text_tts, noise_mode)
        if noise_mode == "clean" and analysis["active"]:
            display_text = _strip_expressive_cues_for_display(display_text)
        # If cues are too weak/uncertain, keep a neutral rendering to avoid fake emotions.
        if usage_mode == "neutral":
            effective_tts_mode = "neutral"
        elif fallback_guard and float(analysis.get("confidence") or 0.0) < 0.28:
            effective_tts_mode = "neutral"
        elif analysis["total"] <= 1 and analysis["primary"] not in {"laugh", "interjection"}:
            effective_tts_mode = "neutral"
        if analysis["active"]:
            detail = ", ".join(analysis["active"])
            smooth_tag = " · lissé" if analysis.get("smoothed") else ""
            _set_module_runtime("hybrid", "Expressif", f"Profil {profile} · {source_mode.upper()} · {detail} · intensité {analysis['intensity']} · {engine_target}{smooth_tag}")
        else:
            _set_module_runtime("hybrid", "Actif", f"Profil {profile} · {source_mode.upper()} · expressivité prête")
        if transcript_mode == "ignore" and analysis["active"]:
            display_text = _strip_expressive_cues_for_display(display_text)
    else:
        effective_tts_mode = "neutral"
        _set_module_runtime("hybrid", "Actif", "Expressivité désactivée · rendu neutre")
    _update_expressive_source_memory(source_mode, analysis)
    _set_expressive_runtime(
        enabled=enabled,
        profile=profile,
        transcript_mode=transcript_mode,
        tts_mode=configured_tts_mode,
        effective_tts_mode=effective_tts_mode,
        intensity_mode=intensity_mode,
        intensity=analysis.get("intensity", "soft"),
        noise_mode=noise_mode,
        engine_target=engine_target,
        engine_mode=engine_mode,
        stability_mode=stability_mode,
        fallback_guard=fallback_guard,
        source_mode=source_mode,
        usage_mode=usage_mode,
        confidence=float(analysis.get("confidence") or 0.0),
        smoothed=bool(analysis.get("smoothed")),
        primary=analysis.get("primary", ""),
        active=analysis.get("active", []),
        detail=(
            f"{source_mode.upper()} · {usage_mode} · {', '.join(analysis['active'])} · intensité {analysis['intensity']} · confiance {float(analysis.get('confidence') or 0.0):.2f} · bruitages {noise_mode} · {engine_target}{' · lissé' if analysis.get('smoothed') else ''}"
            if analysis.get("active")
            else f"{source_mode.upper()} · {usage_mode} · Aucun son expressif détecté"
        ),
    )
    return {
        "display_text": display_text,
        "tts_protected": protected,
        "analysis": analysis,
        "profile": profile,
        "tts_mode": effective_tts_mode,
        "configured_tts_mode": configured_tts_mode,
        "engine_target": engine_target,
        "engine_mode": engine_mode,
        "noise_mode": noise_mode,
        "source_mode": source_mode,
        "usage_mode": usage_mode,
        "stability_mode": stability_mode,
        "fallback_guard": fallback_guard,
        "enabled": enabled,
        "src_lang": src_lang,
    }


def protect_laugh_tokens(text: str) -> str:
    s = str(text or "")
    # Protect laugh blocks from translation rewrite.
    s = re.sub(r"\bha(?:\s+ha){1,}\b", " __LAUGH__ ", s, flags=re.IGNORECASE)
    return re.sub(r"\s{2,}", " ", s).strip()


def restore_laugh_tokens(text: str, lang_hint: str = "fr") -> str:
    s = str(text or "")
    lang = str(lang_hint or "fr").strip().lower()
    repl = "ha... ha... ha..." if lang not in {"ja"} else "ははは…"
    s = s.replace("__LAUGH__", repl)
    return re.sub(r"\s{2,}", " ", s).strip()


def _has_laugh_intent(text: str) -> bool:
    s = str(text or "")
    if not s:
        return False
    return bool(
        re.search(
            r"\b(?:je\s+rigole|je\s+ris|rigole|rigoler|rire|rires|mdr|lol|haha+|hahaha+)\b",
            s,
            flags=re.IGNORECASE,
        )
    )


def _reinforce_laugh_transcript(text: str) -> str:
    """
    Keep laugh intent explicit in transcript so downstream TTS cannot lose it.
    """
    s = str(text or "").strip()
    if not s:
        return s
    if _has_laugh_intent(s):
        # Ensure a visible laugh token in transcript/logs and TTS pipeline.
        if not re.search(r"\bha(?:\s+ha){1,}\b", s, flags=re.IGNORECASE):
            s = f"{s} ha ha ha"
    return re.sub(r"\s{2,}", " ", s).strip()
    

# 2. AUDIO EN PARALLÈLE (SEULEMENT SI PAS DE BYPASS)
    if not AUDIO_CONFIG.get("bypass_mode_active", False):
        
        # On récupère le moteur actuel
        current_engine = AUDIO_CONFIG.get("tts_engine", "WINDOWS")
        stealth_print(f"🎙️ Moteur sélectionné : {current_engine}")

        # --- OPTION 1 : WINDOWS ---
        if current_engine == "WINDOWS": 
            stealth_print("🔊 Lancement Edge TTS...")
            gen = windows_natural_generator(trans)
            threading.Thread(target=resample_and_play, args=(gen, "", "MOI", 16000)).start()
      

        # --- OPTION 2 : KOMMZ VOICE ---
        elif current_engine == "KOMMZ_VOICE" and has_voice_license():
            stealth_print("🔊 Lancement Kommz Voice...")
            gen = kommz_tts_generator(trans)
            threading.Thread(target=resample_and_play, args=(gen, "", "MOI", 24000)).start()
        else:
            stealth_print("🔊 Lancement Edge TTS...")
            gen = windows_natural_generator(trans)
            threading.Thread(target=resample_and_play, args=(gen, "", "MOI", 16000)).start()


def _build_shadow_audio_cache_key(text, engine):
    return (
        str(engine or "WINDOWS"),
        str(CURRENT_TARGET_LANG or "").upper(),
        str(AUDIO_CONFIG.get("edge_voice", "") or ""),
        str(AUDIO_CONFIG.get("kommz_client_id", "") or ""),
        str(AUDIO_CONFIG.get("kommz_xtts_preset", "stable") or "stable"),
        float(AUDIO_CONFIG.get("kommz_speed", 1.0) or 1.0),
        bool(AUDIO_CONFIG.get("gpt_style_to_xtts_fr", False)),
        str(text or ""),
    )


def _user_pipeline_priority(source: str) -> int:
    src = str(source or "").strip().lower()
    if src == "ptt":
        return 0
    if src in {"manual", "file"}:
        return 1
    return 2


def enqueue_user_pipeline(text, src_lang, source="rts"):
    cleaned_text = str(text or "").strip()
    cleaned_lang = str(src_lang or "fr").strip().lower() or "fr"
    cleaned_source = str(source or "rts").strip().lower() or "rts"
    if not cleaned_text:
        return False

    item = (
        _user_pipeline_priority(cleaned_source),
        next(_user_pipeline_sequence),
        cleaned_source,
        cleaned_text,
        cleaned_lang,
    )
    try:
        USER_PIPELINE_QUEUE.put_nowait(item)
        queued = USER_PIPELINE_QUEUE.qsize()
        if cleaned_source == "ptt":
            _set_module_runtime("turbo", "PTT prioritaire", f"File pipeline: {queued} tâche(s)")
        elif cleaned_source == "rts":
            _set_module_runtime("hybrid", "File RTS", f"Phrase auto en attente ({queued})")
            if _is_turbo_mode_active() and _to_bool(AUDIO_CONFIG.get("gpt_style_to_xtts_fr", False), False):
                try:
                    prewarm_kommz_xtts(force=False, timeout_connect=2, timeout_read=8)
                except Exception:
                    pass
        return True
    except queue.Full:
        _push_quality_log(
            "warn",
            "pipeline_queue_full",
            "File pipeline saturée",
            f"source={cleaned_source}",
        )
        if cleaned_source == "ptt":
            stealth_print("⚠️ File pipeline saturée: requête PTT ignorée.")
        return False


def _user_pipeline_worker_loop():
    global _user_pipeline_active, _user_pipeline_active_source
    while True:
        priority, _seq, source, text, lang = USER_PIPELINE_QUEUE.get()
        _user_pipeline_active = True
        _user_pipeline_active_source = source
        try:
            if source == "ptt":
                _set_module_runtime("turbo", "PTT en cours", "Pipeline prioritaire actif")
            elif source == "rts":
                _set_module_runtime("hybrid", "RTS en cours", "Pipeline auto actif")
            process_text_pipeline(text, lang)
        except Exception as worker_err:
            stealth_print(f"⚠️ Pipeline worker error: {worker_err}")
            _push_quality_log(
                "error",
                "pipeline_worker",
                "Erreur file pipeline",
                str(worker_err),
            )
        finally:
            _user_pipeline_active = False
            _user_pipeline_active_source = ""
            USER_PIPELINE_QUEUE.task_done()


def process_text_pipeline(text, src_lang):
    """Le cerveau du logiciel : Affiche le FR, Traduit, et Parle"""
    if not app_state.get("is_active", True): return 
    pipeline_started = time.perf_counter()
    _reset_latency_runtime("Pipeline lancé")
    if AUDIO_CONFIG.get("turbo_latency_active", False):
        _set_module_runtime("turbo", "Pipeline", "Traitement temps réel priorisé")
    
    # 1. Nettoyage
    text, is_cmd = handle_smart_commands(text, src_lang)
    if is_cmd: return
    text = clean_prefix(text)
    text = apply_tilt_shield(text)
    text, has_leak = apply_privacy_sentinel(text)
    if has_leak: add_subtitle(text, "MOI"); return
    expressive_state = _apply_expressive_pack(text, src_lang, _user_pipeline_active_source)
    display_text = expressive_state["display_text"]
    text_tts_protected = expressive_state["tts_protected"]
    expressive_analysis = expressive_state["analysis"]
    expressive_profile = expressive_state["profile"]
    expressive_tts_mode = expressive_state["tts_mode"]
    laugh_intent = _has_laugh_intent(text)

    # 2. Traduction (On la fait quand même pour l'audio)
    try:
        translate_started = time.perf_counter()
        trans = translate_text(text_tts_protected, CURRENT_TARGET_LANG, src_lang)
        translate_ms = (time.perf_counter() - translate_started) * 1000.0
        _record_latency("translate", f"Traduction vers {str(CURRENT_TARGET_LANG or '').upper()}", translate_ms=translate_ms)
        if not trans or "500" in trans:
            trans = text_tts_protected
        trans = _restore_expressive_tokens(
            trans,
            CURRENT_TARGET_LANG,
            expressive_profile,
            expressive_analysis.get("intensity", "medium"),
            expressive_tts_mode,
        )
        # Guardrail: if user clearly expressed laughter but translation lost it, force it back.
        if laugh_intent and ("ha" not in trans.lower()) and ("はは" not in trans):
            trans = (trans + " ha... ha... ha...").strip()
        
        # --- PATCH GAMER ---
        if "top un" in text.lower() or "top 1" in text.lower():
            trans = trans.replace("first place", "Top 1").replace("First place", "Top 1")
            trans = trans.replace("victory", "Top 1")
        if "skin" in text.lower(): trans = trans.replace("outfit", "skin").replace("costume", "skin")
        if "kill" in text.lower(): trans = trans.replace("elimination", "kill")
        # -------------------
        
    except:
        _push_quality_log(
            "warn",
            "translate_fallback",
            "Fallback traduction: texte source conservé",
            f"src={src_lang} target={CURRENT_TARGET_LANG}",
        )
        trans = _restore_expressive_tokens(
            text_tts_protected,
            CURRENT_TARGET_LANG,
            expressive_profile,
            expressive_analysis.get("intensity", "medium"),
            expressive_tts_mode,
        )
        if laugh_intent and ("ha" not in trans.lower()) and ("はは" not in trans):
            trans = (trans + " ha... ha... ha...").strip()
    
    # 4. AFFICHAGE (texte original reconnu)
    # On affiche 'text' (ce que tu as dit en FR) au lieu de 'trans'
    add_subtitle(f"{display_text}", "MOI") 

    # 5. Audio
    if not AUDIO_CONFIG.get("bypass_mode_active", False):
        current_engine = AUDIO_CONFIG.get("tts_engine", "WINDOWS")
        stealth_print(f"🎙️ Moteur actif : {current_engine}")
        shadow_audio_key = _build_shadow_audio_cache_key(trans, current_engine)

        if current_engine == "WINDOWS": 
            _record_latency("tts", "Windows / Edge en cours", tts_ms=0.0)
            _set_pipeline_runtime(
                hybrid_engine="Bypass Hybrid",
                hybrid_detail="Windows / Edge utilisé directement",
                tts_engine="Windows / Edge",
                tts_route=f"Edge TTS · cible {str(CURRENT_TARGET_LANG or '').upper()}",
            )
            gen = windows_natural_generator(trans)
            # Windows est en 16000 Hz
            threading.Thread(target=resample_and_play, args=(gen, "", "MOI", 16000), kwargs={"emotion_hint": trans}).start()
            
        elif current_engine == "KOMMZ_VOICE" and has_voice_license():
            cached_audio = _shadow_cache_get(SHADOW_AUDIO_CACHE, shadow_audio_key)
            if cached_audio is not None:
                stealth_print("👻 Shadow AI: audio en cache réutilisé.")
                _set_module_runtime("shadow", "Cache hit", "Audio Shadow AI réutilisé")
                _set_pipeline_runtime(
                    tts_engine="KOMMZ_VOICE",
                    tts_route="Cache audio Shadow AI",
                )
                threading.Thread(target=resample_and_play, args=([cached_audio], "", "MOI", 24000), kwargs={"emotion_hint": trans}, daemon=True).start()
                return
            # ✅ OPTIMIZED: Utilisation du nouveau générateur
            gen = kommz_tts_generator(trans)
            if _is_turbo_mode_active():
                _set_module_runtime("turbo", "Synthèse", "Kommz Voice priorisé avec timeouts réduits")
            
            def run_kommz():
                tts_started = time.perf_counter()
                try:
                    if gen:
                        audio_blob = b"".join(chunk for chunk in gen if chunk)
                        if not audio_blob:
                            stealth_print("⚠️ Shadow AI: génération audio vide.")
                            _push_quality_log("warn", "tts_empty", "Génération audio vide", "KOMMZ_VOICE n'a retourné aucun audio")
                            return
                        tts_ms = (time.perf_counter() - tts_started) * 1000.0
                        total_ms = (time.perf_counter() - pipeline_started) * 1000.0
                        _record_latency("tts", "KOMMZ_VOICE rendu audio prêt", tts_ms=tts_ms)
                        with _latency_runtime_lock:
                            LATENCY_RUNTIME_STATE["total_ms"] = round(total_ms, 1)
                            LATENCY_RUNTIME_STATE["updated_at"] = time.time()
                        _shadow_cache_put(SHADOW_AUDIO_CACHE, shadow_audio_key, audio_blob, SHADOW_AUDIO_CACHE_MAX_ITEMS)
                        # La fonction resample_and_play a été modifiée pour utiliser le resampling efficace
                        resample_and_play([audio_blob], "", "MOI", 24000, emotion_hint=trans)
                    else:
                        stealth_print("⚠️ Erreur : Le générateur Kommz est vide.")
                except Exception as e:
                    stealth_print(f"⚠️ Erreur Kommz : {e}")
                    _push_quality_log("warn", "tts_fallback_windows", "Fallback TTS Windows après erreur Kommz", str(e))
                    # Fallback
                    w_gen = windows_natural_generator(trans)
                    _record_latency("tts", "Fallback Windows après erreur Kommz", tts_ms=0.0)
                    resample_and_play(w_gen, "", "MOI", 16000, emotion_hint=trans)

            threading.Thread(target=run_kommz, daemon=True).start()
            
def load_voice_from_id(voice_id, audio_url):
    """
    Télécharge la voix depuis Supabase et la stocke en RAM.
    Ne le fait qu'une seule fois par voix pour ne pas ralentir le jeu.
    """
    global PRESET_VOICE_BUFFER, CURRENT_PRESET_ID
    
    # Si c'est déjà la bonne voix en mémoire, on ne fait rien (Gain de temps !)
    if voice_id == CURRENT_PRESET_ID and PRESET_VOICE_BUFFER is not None:
        return

    stealth_print(f"📥 Téléchargement de la voix ID: {voice_id}...")
    
    try:
        import requests
        # On télécharge le fichier WAV depuis l'URL Supabase
        response = requests.get(audio_url, timeout=(5, 30))
        
        if response.status_code == 200:
            PRESET_VOICE_BUFFER = response.content # On stocke les octets en RAM
            CURRENT_PRESET_ID = voice_id
            stealth_print("✅ Voix chargée en mémoire RAM (Prête à l'emploi).")
        else:
            stealth_print(f"❌ Erreur téléchargement : {response.status_code}")
            PRESET_VOICE_BUFFER = None # On remet à zéro en cas d'erreur
            
    except Exception as e:
        stealth_print(f"❌ Erreur LoadVoice: {e}")            

# MOVED TO modules/stt/stt.py
def stop_rec():
    global _ptt_stream, _ptt_rec, _ptt_chunks, LAST_USER_AUDIO_BUFFER, _ptt_stream_device # <--- AJOUT GLOBAL
    global _ptt_last_stop_ts
    now_stop = time.time()
    if (now_stop - float(_ptt_last_stop_ts or 0.0)) < 0.08:
        return
    _ptt_last_stop_ts = now_stop
    # Capture a tiny tail after key release to keep final syllables/emotions.
    try:
        tail_ms = int(AUDIO_CONFIG.get("ptt_release_tail_ms", 220) or 220)
    except Exception:
        tail_ms = 120
    tail_ms = max(0, min(300, tail_ms))
    if tail_ms > 0:
        try:
            time.sleep(tail_ms / 1000.0)
        except Exception:
            pass

    # 1. Arrêt immédiat du flux
    with _ptt_lock:
        if not _ptt_rec: return
        try:
            # En mode keepalive on garde le stream ouvert, sinon on le ferme.
            if not _ptt_keepalive_enabled():
                _ptt_stream.stop(); _ptt_stream.close()
                _ptt_stream = None
                _ptt_stream_device = None
        except: pass
        _ptt_rec = False
    
    if not _ptt_chunks: return
    raw = b"".join(_ptt_chunks); _ptt_chunks = []
    
    try:
        # 2. Vérification rapide
        audio_int16 = np.frombuffer(raw, dtype=np.int16)
        if len(audio_int16) < 1000: return 
        try:
            rec_rate = int(AUDIO_CONFIG.get("mic_sample_rate", 48000) or 48000)
        except Exception:
            rec_rate = 48000
        try:
            rec_ch = int(AUDIO_CONFIG.get("mic_input_channels", 1) or 1)
        except Exception:
            rec_ch = 1
        rec_ch = max(1, min(2, rec_ch))
        try:
            min_record_ms = int(AUDIO_CONFIG.get("ptt_min_record_ms", 90) or 90)
        except Exception:
            min_record_ms = 90
        min_record_ms = max(40, min(500, min_record_ms))
        duration_ms = (float(len(audio_int16)) / float(max(1, rec_rate * rec_ch))) * 1000.0
        if duration_ms < float(min_record_ms):
            return
        
        volume = np.abs(audio_int16).mean()
        if volume < 50: return # Seuil
        
        # 3. CRÉATION DU FICHIER EN RAM
        import io
        import soundfile as sf
        
        # FIX DEFORMATION : On récupère la vraie fréquence détectée dans start_rec
        rec_rate = AUDIO_CONFIG.get("mic_sample_rate", 48000) 
        
        memory_file = io.BytesIO()
        memory_file.name = "audio.wav" 
        # On écrit le fichier à la bonne vitesse
        sf.write(memory_file, audio_int16, rec_rate, format='WAV')
        memory_file.seek(0)
        
        # 🔥 C'EST ICI QUE TOUT SE JOUE 🔥
        # On sauvegarde l'audio du micro dans la variable globale
        LAST_USER_AUDIO_BUFFER = memory_file.getvalue()
        
        # FIX IA : On envoie la fréquence correcte à l'IA pour la transcription
        text, lang = transcribe_safe(memory_file, sample_rate=rec_rate)
        text = _reinforce_laugh_transcript(text)
        
        if text:
            stealth_print(f"⚡ REÇU ({lang}): [{text}]")
            if AUDIO_CONFIG.get("turbo_latency_active", False):
                _set_module_runtime("turbo", "Traitement", "Transcription et routage audio lancés")
            enqueue_user_pipeline(text, lang, source="ptt")

    except Exception as e:
        stealth_print(f"❌ Erreur StopRec: {e}")
        
class Api:
    def update_voice_id(self, new_id):
        stealth_print("INFO: Moteur legacy retire, update_voice_id ignore.")
        return False
            
                    

# À DÉPLACER V5.5
# DeepgramEngine reste dans vtp_core.py car encore fortement couplé au runtime legacy.
class DeepgramEngine:
    def __init__(self):
        try: ctypes.windll.ole32.CoInitialize(None)
        except: pass
        self.dg_client = None
        self.is_running = True

    def start_streaming(self, dev_id):
        import ctypes, time, threading, numpy as np
        from difflib import SequenceMatcher
        global _listen_engine_active

        with _listen_engine_guard:
            if _listen_engine_active:
                stealth_print("ℹ️ Mode écoute: moteur deja actif, lancement ignore.")
                return
            _listen_engine_active = True
        # COM doit être initialisé dans CE thread (WASAPI/loopback), sinon 0x800401f0.
        try:
            ctypes.windll.ole32.CoInitialize(None)
        except Exception:
            pass
        stealth_print("🚀 Moteur Espion Platinum (V3 Stable)")
        
        sentence_buffer = ""
        last_send_time = time.time()
        last_printed_text = "" 
        last_audio_norm = ""
        last_audio_ts = 0.0
        ally_recent_play_ts = collections.deque(maxlen=20)
        last_logged_live_lang = ""
        last_cable_silence_log = 0.0
        last_loopback_retry_ts = 0.0
        # Mode écoute par défaut: loopback système (capture directe du son Windows).
        prefer_loopback = True
        loopback_soundcard_disabled = False

        while self.is_running:
            if not AUDIO_CONFIG.get("is_listening", True):
                time.sleep(1.0); continue

            try:
                listen_id = find_cable_input_device_non_wdmks()
                use_loopback = bool(prefer_loopback and (not loopback_soundcard_disabled))
                listen_rate = 16000
                if listen_id is None and not use_loopback:
                    use_loopback = True
                    listen_rate = 48000
                    stealth_print("ℹ️ Mode écoute: CABLE Output introuvable, fallback loopback système.")
                elif not use_loopback:
                    # Evite WDM-KS avec InputStream bloquant (PaError -9999).
                    try:
                        devs = sd.query_devices()
                        hostapis = sd.query_hostapis()
                        selected = devs[int(listen_id)]
                        host_idx = int(selected.get("hostapi", -1))
                        host_name = str(hostapis[host_idx].get("name", "")) if host_idx >= 0 else ""
                        host_name_up = host_name.upper()

                        if "WDM-KS" in host_name_up:
                            alt_id = None
                            best_score = -1
                            for i, dev in enumerate(devs):
                                if int(dev.get("max_input_channels", 0)) <= 0:
                                    continue
                                n = _norm_dev_name(dev.get("name", ""))
                                if "CABLE" not in n and "VB-AUDIO" not in n and "VIRTUAL" not in n:
                                    continue
                                alt_host_idx = int(dev.get("hostapi", -1))
                                alt_host = ""
                                if alt_host_idx >= 0 and alt_host_idx < len(hostapis):
                                    alt_host = str(hostapis[alt_host_idx].get("name", "")).upper()
                                if "WDM-KS" in alt_host:
                                    continue

                                score = 0
                                if "WASAPI" in alt_host:
                                    score += 50
                                elif "MME" in alt_host:
                                    score += 40
                                elif "DSOUND" in alt_host or "DIRECTSOUND" in alt_host:
                                    score += 30
                                else:
                                    score += 10
                                if "CABLE OUTPUT" in n or "OUTPUT CABLE" in n or "CABLE OUT" in n or "SORTIE" in n:
                                    score += 20

                                if score > best_score:
                                    best_score = score
                                    alt_id = int(i)

                            if alt_id is not None:
                                stealth_print(f"ℹ️ Mode écoute: WDM-KS détecté sur [{listen_id}] -> switch [{alt_id}]")
                                listen_id = alt_id
                            else:
                                use_loopback = True
                                stealth_print("ℹ️ Mode écoute: aucun CABLE compatible (non WDM-KS), fallback loopback système.")
                    except Exception:
                        pass

                    if not use_loopback:
                        try:
                            dev_info = sd.query_devices(int(listen_id))
                            native_rate = int(float(dev_info.get("default_samplerate", 48000)))
                            # Garde-fou simple
                            if native_rate < 8000 or native_rate > 192000:
                                native_rate = 48000
                            listen_rate = native_rate
                        except Exception:
                            listen_rate = 48000
                        stealth_print(f"👂 Mode écoute: CABLE Output [{listen_id}] @ {listen_rate}Hz")
                else:
                    listen_rate = 48000
                    stealth_print("👂 Mode écoute: loopback système")

                if use_loopback:
                    # Priorité: loopback WASAPI via sounddevice (stable avec NumPy 2).
                    rec_ctx = None
                    rec_mode = "none"
                    try:
                        dflt_out = get_default_output_device_id()
                        if dflt_out is not None and hasattr(sd, "WasapiSettings"):
                            out_dev = sd.query_devices(int(dflt_out))
                            lp_rate = int(float(out_dev.get("default_samplerate", listen_rate) or listen_rate))
                            if lp_rate < 8000 or lp_rate > 192000:
                                lp_rate = listen_rate
                            listen_rate = lp_rate
                            loop_ch = min(2, max(1, int(out_dev.get("max_output_channels", 2))))
                            rec_ctx = sd.InputStream(
                                device=int(dflt_out),
                                samplerate=listen_rate,
                                channels=loop_ch,
                                blocksize=1024,
                                dtype="float32",
                                extra_settings=sd.WasapiSettings(loopback=True),
                            )
                            rec_mode = "sd_wasapi_loopback"
                            stealth_print(f"👂 Mode écoute: WASAPI loopback défaut [{dflt_out}] @ {listen_rate}Hz")
                    except Exception as e_lp_default:
                        stealth_print(f"⚠️ Loopback WASAPI défaut indisponible: {e_lp_default}")

                    if rec_ctx is None:
                        try:
                            lp_in = find_wasapi_loopback_input_device()
                            if lp_in is not None:
                                lp_dev = sd.query_devices(int(lp_in))
                                lp_rate = int(float(lp_dev.get("default_samplerate", listen_rate) or listen_rate))
                                if lp_rate < 8000 or lp_rate > 192000:
                                    lp_rate = listen_rate
                                listen_rate = lp_rate
                                rec_ctx = sd.InputStream(
                                    device=int(lp_in),
                                    samplerate=listen_rate,
                                    channels=min(2, max(1, int(lp_dev.get("max_input_channels", 1)))),
                                    blocksize=1024,
                                    dtype="float32",
                                )
                                rec_mode = "sd_wasapi_loopback_input"
                                stealth_print(f"👂 Mode écoute: WASAPI loopback input [{lp_in}] @ {listen_rate}Hz")
                        except Exception as e_lp:
                            stealth_print(f"⚠️ Loopback WASAPI indisponible: {e_lp}")

                    if rec_ctx is None:
                        # Fallback soundcard (avec patch NumPy2 actif plus haut).
                        try:
                            import soundcard as sc
                            patch_soundcard_numpy2()
                            def_spk = sc.default_speaker()
                            if def_spk is not None:
                                mic = sc.get_microphone(id=def_spk.id, include_loopback=True)
                                rec_ctx = mic.recorder(samplerate=listen_rate)
                                rec_mode = "soundcard"
                                stealth_print("👂 Mode écoute: fallback soundcard loopback")
                        except Exception as e_sc:
                            stealth_print(f"⚠️ Mode écoute: soundcard loopback indisponible: {e_sc}")

                    if rec_ctx is None:
                        # Si soundcard n'est pas dispo, on tente SYSTEM MIX / CABLE.
                        loopback_soundcard_disabled = True
                        prefer_loopback = False
                        mix_id = find_system_mix_input_device_non_wdmks()
                        if mix_id is not None:
                            try:
                                mix_info = sd.query_devices(int(mix_id))
                                mix_rate = int(float(mix_info.get("default_samplerate", 48000)))
                                if mix_rate < 8000 or mix_rate > 192000:
                                    mix_rate = 48000
                                listen_rate = mix_rate
                                mix_ch = min(2, max(1, int(mix_info.get("max_input_channels", 1))))
                                rec_ctx = sd.InputStream(
                                    device=int(mix_id),
                                    samplerate=listen_rate,
                                    channels=mix_ch,
                                    blocksize=1024,
                                    dtype="float32",
                                )
                                rec_mode = "system_mix"
                                stealth_print(f"ℹ️ Mode écoute: fallback SYSTEM MIX [{mix_id}] @ {listen_rate}Hz")
                            except Exception as e_mix:
                                stealth_print(f"⚠️ Mode écoute: SYSTEM MIX indisponible: {e_mix}")

                    if rec_ctx is None:
                        # Dernier fallback: CABLE input
                        if listen_id is None:
                            listen_id = find_cable_input_device_non_wdmks()
                        if listen_id is None:
                            stealth_print("⚠️ Mode écoute: loopback indisponible (WASAPI) et CABLE introuvable.")
                            time.sleep(1.0)
                            continue
                        try:
                            dev_info = sd.query_devices(int(listen_id))
                            native_rate = int(float(dev_info.get("default_samplerate", 48000)))
                            if native_rate < 8000 or native_rate > 192000:
                                native_rate = 48000
                            listen_rate = native_rate
                        except Exception:
                            listen_rate = 48000
                        rec_ctx = sd.InputStream(device=listen_id, samplerate=listen_rate, channels=1, blocksize=1024, dtype="float32")
                        rec_mode = "cable"
                        stealth_print(f"ℹ️ Mode écoute: fallback CABLE [{listen_id}] @ {listen_rate}Hz")
                else:
                    rec_ctx = sd.InputStream(device=listen_id, samplerate=listen_rate, channels=1, blocksize=1024, dtype="float32")
                    rec_mode = "cable"

                with rec_ctx as rec:
                    is_con = False
                    dg_conn = None
                    connected_live_lang = ""
                    last_lang_check_ts = 0.0
                    pause_since_ts = 0.0
                    vol_threshold = 0.0022
                    silence_fallback_after = 6.0
                    last_non_silent_ts = time.time()
                    last_connect_try_ts = 0.0
                    reconnect_backoff_s = 1.0
                    reconnect_backoff_max_s = 4.0
                    next_connect_after_ts = 0.0
                    _set_listen_conn_state("waiting_audio", "En attente audio", 0.0)
                    
                    while self.is_running and AUDIO_CONFIG.get("is_listening"):
                        # Si TU parles, on met en pause l'écoute (Anti-écho)
                        if _ptt_rec or _hybrid_running or _is_speaking:
                            if pause_since_ts <= 0.0:
                                pause_since_ts = time.time()
                            # Evite les erreurs Deepgram 1011 (idle timeout) en fermant
                            # proprement la session live pendant les pauses prolongées.
                            if is_con and dg_conn and (time.time() - pause_since_ts) > 1.5:
                                try:
                                    dg_conn.finish()
                                except Exception:
                                    pass
                                is_con = False
                                connected_live_lang = ""
                                _set_listen_conn_state("paused", "Ecoute en pause (PTT/Hybrid)", 0.0)
                            time.sleep(0.1); continue
                        else:
                            pause_since_ts = 0.0

                        # Si la langue de reconnaissance change (via UI), on force une reconnexion
                        # pour eviter le "il faut recliquer 2-3 fois".
                        if is_con and dg_conn:
                            now_lc = time.time()
                            if (now_lc - last_lang_check_ts) > 1.0:
                                last_lang_check_ts = now_lc
                                try:
                                    lang_cfg_curr = str(AUDIO_CONFIG.get("ally_recognition_lang", "multi") or "multi").strip()
                                    curr_live_lang = normalize_live_deepgram_lang(lang_cfg_curr)
                                    if use_loopback and curr_live_lang.lower() in ("en", "english"):
                                        curr_live_lang = "multi"
                                    if connected_live_lang and curr_live_lang != connected_live_lang:
                                        try:
                                            dg_conn.finish()
                                        except Exception:
                                            pass
                                        is_con = False
                                        connected_live_lang = curr_live_lang
                                        continue
                                except Exception:
                                    pass

                        if use_loopback:
                            if rec_mode == "soundcard":
                                try:
                                    data = rec.record(numframes=1024)
                                except Exception as e_sc_rec:
                                    e_txt = str(e_sc_rec).lower()
                                    if ("fromstring" in e_txt) and ("frombuffer" in e_txt):
                                        stealth_print("⚠️ soundcard NumPy2 incompatible -> désactivation soundcard, retry WASAPI/SYSTEM MIX.")
                                        loopback_soundcard_disabled = True
                                        prefer_loopback = False
                                        try:
                                            if is_con and dg_conn:
                                                dg_conn.finish()
                                        except Exception:
                                            pass
                                        break
                                    raise
                                mono = data.mean(axis=1) if len(data.shape) > 1 else data.flatten()
                            else:
                                data, _ = rec.read(1024)
                                if len(data.shape) > 1:
                                    mono = data.mean(axis=1)
                                else:
                                    mono = data.flatten()
                        else:
                            data, _ = rec.read(1024)
                            mono = data.flatten()
                        focus_mode = str(AUDIO_CONFIG.get("ally_voice_focus_mode", "balanced") or "balanced").strip().lower()
                        # V5.3: Voice Focus V3 — calibration adaptative + per-band + auto-gain
                        if focus_mode == "v3":
                            mono_stt, vol, _ = _apply_voice_focus_v3(mono, listen_rate)
                        else:
                            mono_stt, vol = _apply_voice_focus_signal(mono, listen_rate, mode=focus_mode)
                        update_teamsync_input_level(vol)
                        if vol > vol_threshold:
                            last_non_silent_ts = time.time()
                            _listen_runtime["last_audio_seen_at"] = last_non_silent_ts
                        elif (not use_loopback) and ((time.time() - last_non_silent_ts) > silence_fallback_after):
                            # Si le CABLE est silencieux trop longtemps, on passe en loopback
                            # pour capter le son système (ex: YouTube navigateur).
                            if loopback_soundcard_disabled:
                                now_sl = time.time()
                                if (now_sl - last_cable_silence_log) > 10.0:
                                    stealth_print("ℹ️ Mode écoute: CABLE silencieux et loopback indisponible (WASAPI).")
                                    last_cable_silence_log = now_sl
                                last_non_silent_ts = now_sl
                                # Retente périodiquement le loopback WASAPI (ex: pilote prêt après démarrage).
                                if (now_sl - last_loopback_retry_ts) > 20.0:
                                    loopback_soundcard_disabled = False
                                    prefer_loopback = True
                                    last_loopback_retry_ts = now_sl
                            else:
                                stealth_print("ℹ️ Mode écoute: CABLE silencieux -> bascule loopback système.")
                                prefer_loopback = True
                                try:
                                    if is_con and dg_conn:
                                        dg_conn.finish()
                                except Exception:
                                    pass
                                break
                        
                        # Connexion Deepgram: démarrage immédiat (sinon début de phrase perdu).
                        now_connect = time.time()
                        has_recent_audio = (now_connect - last_non_silent_ts) <= 4.0
                        periodic_probe = (now_connect - last_connect_try_ts) >= 8.0
                        if (not is_con) and (now_connect >= next_connect_after_ts) and (has_recent_audio or periodic_probe):
                            last_connect_try_ts = time.time()
                            _set_listen_conn_state("connecting", "Connexion Deepgram...", 0.0)
                            try:
                                self.dg_client = DeepgramClient(DEEPGRAM_API_KEY)
                                dg_conn = self.dg_client.listen.websocket.v("1")

                                def on_msg(h, result, **kwargs):
                                    nonlocal sentence_buffer, last_send_time, last_printed_text
                                    nonlocal last_audio_norm, last_audio_ts, ally_recent_play_ts
                                    if not getattr(result, "is_final", False):
                                        return
                                    try:
                                        ts = result.channel.alternatives[0].transcript
                                    except Exception:
                                        ts = ""
                                    if len((ts or "").strip()) <= 1:
                                        return

                                    if AUDIO_CONFIG.get("ally_block_french", False) and is_strictly_french(ts):
                                        sentence_buffer = ""
                                        return

                                    cleaned = clean_gaming_text(ts)
                                    sentence_buffer = (sentence_buffer + " " + cleaned).strip()
                                    speech_final = bool(getattr(result, "speech_final", False))
                                    end_punct = bool(re.search(r"[.!?…]\s*$", cleaned.strip()))
                                    word_count = len(sentence_buffer.split())
                                    punct_min_words = int(AUDIO_CONFIG.get("ally_sentence_punct_min_words", 3) or 3)
                                    hard_flush_words = int(AUDIO_CONFIG.get("ally_sentence_hard_flush_words", 10) or 10)
                                    punct_min_words = max(1, min(6, punct_min_words))
                                    hard_flush_words = max(3, min(20, hard_flush_words))
                                    short_merge_words = int(AUDIO_CONFIG.get("ally_tts_short_merge_words", 3) or 3)
                                    short_merge_chars = int(AUDIO_CONFIG.get("ally_tts_short_merge_chars", 18) or 18)
                                    short_merge_window_s = float(AUDIO_CONFIG.get("ally_tts_short_merge_window_s", 1.25) or 1.25)
                                    short_merge_words = max(1, min(8, short_merge_words))
                                    short_merge_chars = max(6, min(80, short_merge_chars))
                                    short_merge_window_s = max(0.30, min(4.0, short_merge_window_s))
                                    now_msg_ts = time.time()
                                    # Anti-coupures: on retarde les micro-fragments speech_final
                                    # pour fusionner avec la phrase suivante.
                                    if speech_final and (not end_punct):
                                        if (word_count < short_merge_words) and (len(sentence_buffer) < short_merge_chars):
                                            if (now_msg_ts - last_send_time) < short_merge_window_s:
                                                _bump_listen_runtime("ally_short_merged")
                                                return
                                    should_flush = speech_final or (end_punct and word_count >= punct_min_words) or (word_count >= hard_flush_words)
                                    if not should_flush:
                                        return

                                    trad = translate_text(sentence_buffer, "FR") or sentence_buffer
                                    trad = (trad or sentence_buffer).strip()
                                    if not trad:
                                        sentence_buffer = ""
                                        last_send_time = time.time()
                                        return

                                    ratio = SequenceMatcher(None, last_printed_text, trad).ratio()
                                    ally_lang = detect_ally_language(sentence_buffer, result)
                                    ally_voice = get_auto_ally_voice(ally_lang)
                                    now_ts = time.time()
                                    norm = re.sub(r"\s+", " ", unidecode(trad.lower())).strip()

                                    # Sous-titre: toujours afficher pour ne rien perdre côté overlay.
                                    stealth_print(f"⚡ [Allié] {trad}")
                                    add_subtitle(trad, "ALLIÉ")
                                    _bump_listen_runtime("ally_text_events")

                                    # Audio anti-spam: configurable pour mieux gérer le vocal in-game.
                                    similarity_play_below = float(AUDIO_CONFIG.get("ally_tts_similarity_play_below", 0.85) or 0.85)
                                    similarity_play_below = max(0.60, min(0.99, similarity_play_below))
                                    duplicate_window_s = float(AUDIO_CONFIG.get("ally_tts_duplicate_window_s", 3.0) or 3.0)
                                    duplicate_window_s = max(0.5, min(8.0, duplicate_window_s))
                                    force_on_speech_final = bool(AUDIO_CONFIG.get("ally_tts_force_on_speech_final", True))
                                    force_min_chars = int(AUDIO_CONFIG.get("ally_tts_force_min_chars", 8) or 8)
                                    force_min_chars = max(3, min(40, force_min_chars))
                                    min_gap_s = float(AUDIO_CONFIG.get("ally_tts_min_gap_s", 0.55) or 0.55)
                                    min_gap_s = max(0.20, min(2.50, min_gap_s))
                                    rate_limit_window_s = float(AUDIO_CONFIG.get("ally_tts_rate_limit_window_s", 10.0) or 10.0)
                                    rate_limit_max_plays = int(AUDIO_CONFIG.get("ally_tts_rate_limit_max_plays", 5) or 5)
                                    rate_limit_window_s = max(2.0, min(30.0, rate_limit_window_s))
                                    rate_limit_max_plays = max(1, min(20, rate_limit_max_plays))
                                    autotune_level = int(_listen_autotune_state.get("level", 0) or 0)
                                    if bool(AUDIO_CONFIG.get("ally_autotune_enabled", True)):
                                        if autotune_level >= 2:
                                            similarity_play_below = min(0.99, similarity_play_below + 0.07)
                                            duplicate_window_s = max(0.40, duplicate_window_s * 0.60)
                                        elif autotune_level == 1:
                                            similarity_play_below = min(0.99, similarity_play_below + 0.03)
                                            duplicate_window_s = max(0.50, duplicate_window_s * 0.80)
                                    is_audio_dup = (norm and norm == last_audio_norm and (now_ts - last_audio_ts) < duplicate_window_s)
                                    force_short_final = (
                                        force_on_speech_final
                                        and speech_final
                                        and (word_count >= 2)
                                        and (len(norm) >= force_min_chars)
                                        and ((now_ts - last_audio_ts) >= min_gap_s)
                                    )
                                    while ally_recent_play_ts and (now_ts - ally_recent_play_ts[0]) > rate_limit_window_s:
                                        ally_recent_play_ts.popleft()
                                    is_rate_limited = len(ally_recent_play_ts) >= rate_limit_max_plays
                                    should_play_audio = ((ratio < similarity_play_below) or force_short_final) and (not is_audio_dup) and (not is_rate_limited)
                                    if should_play_audio:
                                        stealth_print(f"🗣️ Voix auto allié: {ally_lang} -> {ally_voice}")
                                        gen = windows_natural_generator(trad, voice_override=ally_voice)
                                        threading.Thread(target=resample_and_play, args=(gen, "", "ALLIÉ", 16000)).start()
                                        _bump_listen_runtime("ally_voice_played")
                                        _register_listen_decision(True)
                                        ally_recent_play_ts.append(now_ts)
                                        last_printed_text = trad
                                        last_audio_norm = norm
                                        last_audio_ts = now_ts
                                    else:
                                        _bump_listen_runtime("ally_voice_skipped")
                                        if is_rate_limited:
                                            _bump_listen_runtime("ally_voice_rate_limited")
                                        _register_listen_decision(False)

                                    sentence_buffer = ""
                                    last_send_time = now_ts

                                dg_conn.on(LiveTranscriptionEvents.Transcript, on_msg)
                                lang_cfg = str(AUDIO_CONFIG.get("ally_recognition_lang", "multi") or "multi").strip()
                                live_lang = normalize_live_deepgram_lang(lang_cfg)
                                # En loopback (YouTube/son système), en-US capte mal le multilingue.
                                if use_loopback and live_lang.lower() in ("en", "english"):
                                    live_lang = "multi"
                                if live_lang != last_logged_live_lang:
                                    stealth_print(f"🌐 Mode écoute langue: {live_lang}")
                                    last_logged_live_lang = live_lang
                                connected_live_lang = live_lang
                                start_ok = False
                                tried = []
                                candidates = [live_lang]
                                if live_lang != "multi":
                                    candidates.append("multi")
                                if "en" not in candidates:
                                    candidates.append("en")

                                for idx, cand_lang in enumerate(candidates, start=1):
                                    tried.append(cand_lang)
                                    # Réseau instable: on réessaie plusieurs fois "multi"
                                    # avant de dégrader en "en".
                                    max_tries = 3 if cand_lang == "multi" else 1
                                    for att in range(1, max_tries + 1):
                                        try:
                                            dg_conn.start(
                                                LiveOptions(
                                                    model="nova-2",
                                                    language=cand_lang,
                                                    smart_format=True,
                                                    encoding="linear16",
                                                    channels=1,
                                                    sample_rate=listen_rate,
                                                )
                                            )
                                            start_ok = True
                                            if cand_lang != live_lang:
                                                stealth_print(f"ℹ️ Deepgram live start fallback: {live_lang} -> {cand_lang}")
                                            break
                                        except Exception as e_lang:
                                            err_txt = str(e_lang).lower()
                                            if "timed out" in err_txt or "handshake" in err_txt or "timeout" in err_txt:
                                                stealth_print(f"⚠️ Deepgram live timeout réseau ({cand_lang}) tentative {att}/{max_tries}")
                                            else:
                                                stealth_print(f"⚠️ Deepgram live start error ({cand_lang}): {e_lang}")
                                            if att < max_tries:
                                                time.sleep(0.45 * att)
                                    if start_ok:
                                        break
                                    if idx < len(candidates):
                                        time.sleep(0.35 * idx)

                                if not start_ok:
                                    stealth_print(f"⚠️ Deepgram live indisponible (tentatives: {', '.join(tried)})")
                                    is_con = False
                                    next_connect_after_ts = time.time() + reconnect_backoff_s
                                    _set_listen_conn_state("reconnecting", "Reconnexion ecoute...", reconnect_backoff_s)
                                    reconnect_backoff_s = min(reconnect_backoff_max_s, reconnect_backoff_s * 2.0)
                                    continue
                                is_con = True
                                reconnect_backoff_s = 1.0
                                next_connect_after_ts = 0.0
                                _set_listen_conn_state("connected", "Ecoute connectee", 0.0)
                            except Exception as e_conn:
                                is_con = False
                                next_connect_after_ts = time.time() + reconnect_backoff_s
                                _set_listen_conn_state("reconnecting", f"Reconnexion ecoute... ({str(e_conn)[:60]})", reconnect_backoff_s)
                                reconnect_backoff_s = min(reconnect_backoff_max_s, reconnect_backoff_s * 2.0)

                        # Envoi des donnees
                        if is_con:
                            try:
                                mono_safe = np.nan_to_num(mono_stt, nan=0.0, posinf=0.0, neginf=0.0)
                                audio_bytes = (np.clip(mono_safe, -1, 1) * 32767).astype(np.int16).tobytes()
                                dg_conn.send(audio_bytes)
                                _listen_runtime["last_audio_seen_at"] = time.time()
                                # Si long silence, on ferme proprement et on revient en attente audio.
                                if vol <= vol_threshold and (time.time() - last_non_silent_ts > 10):
                                    try:
                                        dg_conn.finish()
                                    except Exception:
                                        pass
                                    is_con = False
                                    _set_listen_conn_state("waiting_audio", "En attente audio", 0.0)
                            except Exception as e_send:
                                is_con = False
                                e_txt = str(e_send).lower()
                                is_idle_timeout = ("net0001" in e_txt) or ("did not receive audio data" in e_txt)
                                next_connect_after_ts = time.time() + reconnect_backoff_s
                                if is_idle_timeout:
                                    _set_listen_conn_state("waiting_audio", "En attente audio (silence)", reconnect_backoff_s)
                                else:
                                    _set_listen_conn_state("reconnecting", "Reconnexion ecoute...", reconnect_backoff_s)
                                reconnect_backoff_s = min(reconnect_backoff_max_s, reconnect_backoff_s * 2.0)
                                break
            except Exception as e:
                stealth_print(f"⚠️ Mode écoute error: {e}")
                time.sleep(1.0)

        with _listen_engine_guard:
            _listen_engine_active = False

DG_ENGINE = DeepgramEngine()


def select_microphone_at_startup():
    global SELECTED_MIC_ID, SELECTED_MIC_NAME
    stealth_print("\n" + "="*50)
    stealth_print("🎙️ CONFIGURATION DU MICROPHONE")
    stealth_print("="*50)

    # Priorité: micro sauvegardé dans la configuration utilisateur.
    saved_mic_sig = AUDIO_CONFIG.get("game_input_device_key") or AUDIO_CONFIG.get("game_input_device")
    saved_mic = _resolve_device_signature(saved_mic_sig, as_output=False)
    if saved_mic is not None:
        try:
            SELECTED_MIC_ID = int(saved_mic["index"])
            SELECTED_MIC_NAME = saved_mic["name"]
            AUDIO_CONFIG["game_input_device_runtime"] = saved_mic
            stealth_print(f"🎯 CIBLE UTILISÉE : {SELECTED_MIC_NAME} (ID {SELECTED_MIC_ID}) [config]")
            stealth_print("="*50 + "\n")
            return
        except Exception as e:
            stealth_print(f"⚠️ Micro sauvegardé invalide/indisponible ({saved_mic}) : {e}")

    try:
        # Récupère l'ID du micro par défaut configuré dans Windows.
        default_device_index = sd.default.device[0]
        devices = sd.query_devices()

        if default_device_index >= 0:
            SELECTED_MIC_ID = default_device_index
            SELECTED_MIC_NAME = devices[SELECTED_MIC_ID]['name']
        else:
            raise ValueError("Périphérique par défaut non détecté.")

    except Exception as e:
        stealth_print(f"⚠️ Erreur détection Windows, recherche du premier micro dispo : {e}")
        # Fallback: on cherche le premier périphérique avec une entrée.
        for i, dev in enumerate(sd.query_devices()):
            if dev['max_input_channels'] > 0:
                SELECTED_MIC_ID = i
                SELECTED_MIC_NAME = dev['name']
                break

    # Synchronise la configuration avec le micro résolu.
    AUDIO_CONFIG["game_input_device_runtime"] = _device_runtime_payload(SELECTED_MIC_ID)
    
    stealth_print(f"🎯 CIBLE UTILISÉE : {SELECTED_MIC_NAME} (ID {SELECTED_MIC_ID})")
    stealth_print("="*50 + "\n")


# --- LE FORCEUR VISUEL ---
def visual_hammer_loop(text_content):
    """
    Cette fonction ne touche PAS à l'audio.
    Elle bombarde l'interface avec le texte pour l'empêcher de s'éteindre.
    """
    # 1. Calcul de la durée de lecture (min 4 secondes)
    duration = max(4.0, len(text_content.split()) * 0.4)
    start_time = time.time()
    
    stealth_print(f"🔨 BYPASS : Forçage affichage '{text_content}' pendant {duration}s")
    
    # 2. BOUCLE DE MAINTIEN (Le Spam)
    while time.time() - start_time < duration:
        # On force toutes les variables d'état à "VRAI"
        app_state["is_speaking"] = True
        app_state["is_playing"] = True
        app_state["last_text"] = text_content
        
        # ON RENVOIE LA COMMANDE D'AFFICHAGE (C'est ça le secret)
        add_subtitle(text_content, "MOI")
        
        # On attend un tout petit peu (10 fois par seconde)
        time.sleep(0.1)
        
    # 3. Relâchement
    app_state["is_speaking"] = False
    app_state["is_playing"] = False
    stealth_print("🔨 Fin du forçage.")


def record_and_recognize():
    try:
        global SELECTED_MIC_ID, SELECTED_MIC_NAME
        if SELECTED_MIC_ID is None: select_microphone_at_startup()

        # 1. DÉTECTION INTELLIGENTE DE LA FRÉQUENCE
        dev_info = sd.query_devices(SELECTED_MIC_ID)
        native_channels = dev_info['max_input_channels']
        
        # On prend la fréquence native du micro (ex: 44100 ou 48000)
        # C'est CRUCIAL pour que la voix ne soit pas déformée
        fs = int(dev_info['default_samplerate'])
        
        stealth_print(f"🎤 Rec ({SELECTED_MIC_NAME} @ {fs}Hz)...", end='', flush=True)
        
        recording = []
        PTT_KEY = AUDIO_CONFIG.get("ptt_key", "ctrl+shift")

        # 2. Enregistrement
        with sd.InputStream(samplerate=fs, device=SELECTED_MIC_ID, channels=native_channels, dtype='float32') as stream:
            start_time = time.time()
            while True:
                chunk, overflowed = stream.read(1024)
                recording.append(chunk)
                if not keyboard.is_pressed(PTT_KEY): break 
                if time.time() - start_time > 10.0: break
        
        stealth_print(" Fin.")
        app_state["is_recording"] = False 
        
        # 3. Traitement
        full_audio_raw = np.concatenate(recording, axis=0)
        if len(full_audio_raw.shape) > 1:
            full_audio = np.mean(full_audio_raw, axis=1)
        else:
            full_audio = full_audio_raw
            
        if np.max(np.abs(full_audio)) < 0.005:
            stealth_print("⚠️ SILENCE")
            return

        audio_int16 = (full_audio * 32767).astype(np.int16)
        
        import io
        import soundfile as sf
        mem_file = io.BytesIO()
        
        # ON UTILISE LA VRAIE FRÉQUENCE (fs) ICI
        sf.write(mem_file, audio_int16, fs, format='WAV')
        mem_file.seek(0)

        # ON PASSE LA FRÉQUENCE (fs) A LA FONCTION DE TRADUCTION
        full_text, lang = transcribe_safe(mem_file, sample_rate=fs)

        if lang == "fr" and not full_text: return 
        
        if len(full_text) > 0:
            enqueue_user_pipeline(full_text, lang, source="manual")
        else:
            stealth_print("⚠️ Pas compris.")

    except Exception as e:
        stealth_print(f"❌ Erreur REC : {e}")
        app_state["is_recording"] = False


# =========================================================
# 🎮 TRADUCTEUR DE TOUCHES (INTERFACE -> PYTHON)
# =========================================================
def get_clean_hotkey(ui_value):
    """
    V4 CORE : Traduit les entrées UI et matérielles pour le Hook clavier.
    Supporte les anciens noms (dropdown) et les nouveaux (assignation directe).
    """
    if not ui_value: return "ctrl+shift"
    
    # Nettoyage de la valeur reçue
    val = str(ui_value).lower().strip()
    
    # 1. Mapping de compatibilité (Ancien menu vers Code Keyboard)
    legacy_mapping = {
        "ctrl + maj (défaut)": "ctrl+shift",
        "alt (gauche)": "alt",
        "souris 4": "xbutton1",
        "souris 5": "xbutton2",
        "control": "ctrl",
        "shift": "shift"
    }
    
    # Si c'est un ancien nom, on le traduit
    if val in legacy_mapping:
        return legacy_mapping[val]
    
    # 2. Sinon, on retourne la valeur brute (ex: 'f9', 'v', 'ctrl')
    # car le moteur V4 l'accepte directement.
    return val


import ctypes

def is_key_held_v4(key_name):
    """
    Vérifie si une touche est maintenue (Clavier + Souris).
    Inclut un nettoyage automatique du nom de la touche.
    """
    if not key_name: return False
    
    # 1. Nettoyage du nom (Conversion "Souris 4" -> "xbutton1")
    # On réutilise ta fonction get_clean_hotkey pour être sûr
    try:
        clean_key = get_clean_hotkey(key_name)
    except:
        clean_key = key_name.lower().strip()

    # 2. Détection Souris (Via Windows API directe)
    if "xbutton1" in clean_key: # Souris 4 (Précédent)
        return ctypes.windll.user32.GetAsyncKeyState(0x05) & 0x8000
    if "xbutton2" in clean_key: # Souris 5 (Suivant)
        return ctypes.windll.user32.GetAsyncKeyState(0x06) & 0x8000
    if "middle" in clean_key:   # Molette (Clic)
        return ctypes.windll.user32.GetAsyncKeyState(0x04) & 0x8000

    # 3. Détection Clavier (Librairie keyboard)
    try:
        return keyboard.is_pressed(clean_key)
    except:
        return False

# =========================================================
# ⌨️ BOUCLE CLAVIER (CORRIGÉE AVEC TON MENU)
# =========================================================
def hotkey_loop():
    stealth_print("🎹 Monitoring PTT V6 (Debug Mode)")
    global _hybrid_running, _ptt_rec
    
    # Sécurité : Si pas de touche, on met Ctrl par défaut
    if "ptt_hotkey" not in AUDIO_CONFIG or not AUDIO_CONFIG["ptt_hotkey"]:
        AUDIO_CONFIG["ptt_hotkey"] = "ctrl"
        stealth_print("⚠️ Aucune touche PTT définie -> 'ctrl' par défaut")

    last_state = False
    stable_state = False
    candidate_state = False
    candidate_since_ts = time.time()
    last_f3_state = False

    while True:
        try:
            # 1. Récupération de la touche actuelle
            PTT_KEY = AUDIO_CONFIG.get("ptt_hotkey", "ctrl")

            # Fallback F3 (utile en EXE si hook global keyboard échoue)
            try:
                f3_now = bool(keyboard.is_pressed("f3"))
            except Exception:
                f3_now = False
            if f3_now and not last_f3_state:
                toggle_monitoring_action()
            last_f3_state = f3_now
            
            # 2. Si le Bypass (F4) est actif, on désactive le PTT
            if AUDIO_CONFIG.get("bypass_mode_active", False):
                time.sleep(0.5)
                continue

            # 3. Vérification de l'appui
            raw_pressed = bool(is_key_held_v4(PTT_KEY))
            now = time.time()
            if raw_pressed != candidate_state:
                candidate_state = raw_pressed
                candidate_since_ts = now
            try:
                debounce_ms = int(AUDIO_CONFIG.get("ptt_debounce_ms", 35) or 35)
            except Exception:
                debounce_ms = 35
            debounce_s = max(0.01, min(0.20, float(debounce_ms) / 1000.0))
            if candidate_state != stable_state and (now - candidate_since_ts) >= debounce_s:
                stable_state = candidate_state
            
            # --- DEBUG VISUEL (Optionnel : aide à savoir si la touche est vue) ---
            # Si l'état change, on l'affiche dans la console pour tester
            if stable_state != last_state:
                if stable_state:
                    stealth_print(f"⬇️ TOUCHE ENFONCÉE : {PTT_KEY}")
                else:
                    stealth_print(f"⬆️ TOUCHE RELÂCHÉE")
                last_state = stable_state
            # -------------------------------------------------------------------

            if stable_state:
                # Si on appuie et que ça n'enregistre pas encore -> START
                if not _ptt_rec:
                    start_rec()
            else:
                # Si on relâche et que ça enregistre -> STOP
                if _ptt_rec:
                    # On ne coupe que si ce n'est pas le mode Hybride qui tourne tout seul
                    if not _hybrid_running:
                        stop_rec()
            
            # Pause courte pour ne pas surcharger le CPU (30 checks par seconde)
            time.sleep(0.03)
            
        except Exception as e:
            # En cas d'erreur critique, on affiche et on attend un peu
            stealth_print(f"⚠️ Erreur boucle PTT : {e}")
            time.sleep(1)


# MOVED TO modules/stt/stt.py
def transcribe_safe(audio_source, sample_rate=16000):
    """
    Version robuste : Whisper Modal prioritaire + fallback Deepgram.
    """
    try:
        # 1. Extraction des bytes
        if isinstance(audio_source, io.BytesIO):
            audio_source.seek(0)
            buffer_data = audio_source.read()
        else:
            with open(audio_source, "rb") as f:
                buffer_data = f.read()

        if not buffer_data or len(buffer_data) < 500:
            return "", "fr"

        user_multilang = bool(AUDIO_CONFIG.get("user_multilang_active", True))
        turbo_mode = _is_turbo_mode_active()
        stt_started = time.perf_counter()
        try:
            transcript, detected = _transcribe_via_modal_whisper(
                buffer_data,
                user_multilang=user_multilang,
            )
            if transcript:
                stt_ms = (time.perf_counter() - stt_started) * 1000.0
                _record_latency(
                    "stt",
                    f"Whisper Modal · {str(detected or 'fr').upper()}",
                    stt_ms=stt_ms,
                )
                if turbo_mode:
                    _set_module_runtime("turbo", "STT", "Whisper Modal priorisé en mode rapide")
                return transcript, detected
        except Exception as modal_err:
            stealth_print(f"⚠️ Whisper Modal indisponible, fallback Deepgram: {modal_err}")
            _push_quality_log(
                "warn",
                "stt_modal_fallback",
                "Whisper Modal indisponible, fallback Deepgram",
                str(modal_err),
            )

        # 2. Appel HTTP Deepgram avec retries (évite le crash handshake timeout)
        #    Multi-langue activé par défaut pour la voix utilisateur.
        url = "https://api.deepgram.com/v1/listen"
        params = {
            "model": "nova-2",
            # Keep transcript as literal as possible (avoid rewriting interjections).
            "smart_format": "false",
            "punctuate": "false",
            "filler_words": "true",
        }
        if user_multilang:
            params["detect_language"] = "true"
        else:
            params["language"] = "fr"
        # Bias STT to keep laugh/interjection tokens instead of dropping them.
        # Deepgram "keywords" format: "<term>:<boost>" (boost in [-100, 100]).
        params["keywords"] = ",".join([
            "haha:20",
            "ha ha:20",
            "ah ah:20",
            "ah ah ah:24",
            "ha ha ha:24",
            "rire:14",
            "rigole:14",
            "mdr:10",
            "lol:8",
        ])
        headers = {
            "Authorization": f"Token {DEEPGRAM_API_KEY}",
            "Content-Type": "audio/wav",
        }

        last_err = None
        max_attempts = 2 if turbo_mode else 3
        timeout_cfg = (4, 20) if turbo_mode else (6, 45)
        for attempt in range(1, max_attempts + 1):
            try:
                r = requests.post(
                    url,
                    params=params,
                    headers=headers,
                    data=buffer_data,
                    timeout=timeout_cfg,
                )
                if r.ok:
                    res_json = r.json()
                    try:
                        ch0 = res_json["results"]["channels"][0]
                        alts = ch0.get("alternatives") or []
                        if not alts:
                            return "", "fr"

                        laugh_hint_re = re.compile(
                            r"\b(?:ha+|ah+|haha+|hahaha+|rire|rigole|mdr|lol|hehe+|hihi+)\b",
                            re.IGNORECASE,
                        )
                        filler_hint_re = re.compile(
                            r"\b(?:euh+|heu+|hum+|hmm+|oh+|ah+|wow+|pff+|snif+|grr+)\b",
                            re.IGNORECASE,
                        )

                        def _score_alt(alt: dict) -> float:
                            txt = str((alt or {}).get("transcript") or "")
                            if not txt.strip():
                                return -1e9
                            conf = float((alt or {}).get("confidence") or 0.0)
                            laugh_hits = len(laugh_hint_re.findall(txt))
                            filler_hits = len(filler_hint_re.findall(txt))
                            # Prefer alternatives that keep emotive words/interjections.
                            return (conf * 10.0) + (laugh_hits * 4.0) + (filler_hits * 1.5) - (0.002 * len(txt))

                        alt0 = max(alts, key=_score_alt)
                        transcript = str(alt0.get("transcript") or "")
                        detected = (ch0.get("detected_language") or alt0.get("detected_language") or "")
                        if not user_multilang:
                            detected = "fr"
                        detected = str(detected).strip().lower()
                        if "-" in detected:
                            detected = detected.split("-", 1)[0]
                        if not detected:
                            detected = "fr"
                        transcript = clean_gaming_text(transcript)
                        transcript = _reinforce_laugh_transcript(transcript)
                        stt_ms = (time.perf_counter() - stt_started) * 1000.0
                        _record_latency(
                            "stt",
                            f"Deepgram fallback · {detected.upper()}",
                            stt_ms=stt_ms,
                        )
                        _set_pipeline_runtime(
                            stt_engine="Deepgram Nova-2",
                            stt_detail=f"{detected.upper()} · fallback STT" + (" · turbo" if turbo_mode else ""),
                        )
                        if turbo_mode:
                            _set_module_runtime("turbo", "Fallback STT", "Deepgram lancé avec timeouts réduits")
                        return transcript, detected
                    except (KeyError, IndexError):
                        return "", "fr"
                body_snip = ""
                try:
                    body_snip = (r.text or "").strip().replace("\n", " ")[:220]
                except Exception:
                    body_snip = ""
                last_err = f"HTTP {r.status_code} {body_snip}".strip()
            except Exception as e:
                last_err = e
                # Backoff court pour lisser les timeouts TLS intermittents.
                time.sleep(0.6 * attempt)

        stealth_print(f"⚠️ IA Transcription Error: {last_err}")
        _push_quality_log(
            "error",
            "stt_failed",
            "Transcription indisponible",
            str(last_err),
        )
        return "", "fr"

    except Exception as e:
        stealth_print(f"⚠️ IA Transcription Error: {e}")
        _push_quality_log(
            "error",
            "stt_exception",
            "Exception transcription",
            str(e),
        )
        return "", "fr"

def overlay_loop():
    while not (AUDIO_CONFIG.get("gamesense_overlay_active", False)
               or AUDIO_CONFIG.get("overlay_enabled", False)
               or AUDIO_CONFIG.get("show_own_subs_active", False)
               or AUDIO_CONFIG.get("show_ally_subs_active", False)):
        time.sleep(1)
        
    try:
        root = tk.Tk(); root.title("Kommz Overlay")
        w = root.winfo_screenwidth(); h = root.winfo_screenheight()
        
        # Hauteur réduite à 150px (suffisant pour taille 18)
        root.geometry(f"{w}x150+0+{h-220}")
        
        root.overrideredirect(True); root.wm_attributes("-topmost", True)
        root.wm_attributes("-transparentcolor", "#000001")
        root.configure(bg='#000001')

        if sys.platform == "win32":
            hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
            style = ctypes.windll.user32.GetWindowLongW(hwnd, -20)
            ctypes.windll.user32.SetWindowLongW(hwnd, -20, style | 0x00080000 | 0x00000020)

        canvas = tk.Canvas(root, bg="#000001", highlightthickness=0)
        canvas.pack(fill="both", expand=True)
        
        # --- CORRECTION TAILLE : 18 ---
        font = tkfont.Font(family="Arial Black", size=18)

        # Placement ajusté pour la taille 18
        s_txt = canvas.create_text(w//2+2, 77, text="", font=font, fill="black", justify="center", width=w-300)
        m_txt = canvas.create_text(w//2, 75, text="", font=font, fill="#00FFFF", justify="center", width=w-300)

        def update_ui():
                root.deiconify()
                root.lift()
                root.wm_attributes("-topmost", True)

                if subs_buffer:
                    last = None
                    now_ts = time.time()
                    for item in reversed(subs_buffer):
                        if (now_ts - item.get('timestamp', 0)) >= 4.0:
                            continue
                        lang = str(item.get('lang', ''))
                        is_user = bool(item.get('is_user', False))
                        is_ally = ("ALLIÉ" in lang) or ("ALLY" in lang)

                        if is_user and not AUDIO_CONFIG.get("show_own_subs_active", True):
                            continue
                        if is_ally and not AUDIO_CONFIG.get("show_ally_subs_active", True):
                            continue
                        last = item
                        break

                    if last:
                        c = "#FFFFFF"
                        lang = str(last.get('lang', ''))
                        if "SYS" in lang:
                            c = "#FF00FF"
                        elif ("ALLIÉ" in lang) or ("ALLY" in lang):
                            c = AUDIO_CONFIG.get("ally_overlay_color", "#FFFF00")
                        else:
                            c = AUDIO_CONFIG.get("user_overlay_color", "#00FFFF")

                        txt = str(last.get('text', ''))
                        canvas.itemconfig(s_txt, text=txt)
                        canvas.itemconfig(m_txt, text=txt, fill=c)
                    else:
                        canvas.itemconfig(s_txt, text="")
                        canvas.itemconfig(m_txt, text="")
                else: 
                    canvas.itemconfig(s_txt, text="")
                    canvas.itemconfig(m_txt, text="")
                
                root.after(20, update_ui)
        
        root.after(100, update_ui)
        root.mainloop()
    except Exception: pass
    
  # ── V5.2 Bloc 4: Mini overlay desktop always-on-top (stats temps reel) ──
def mini_stats_overlay_loop():
    """
    V5.3: No-op — le HUD externe est maintenant créé directement sur le thread principal
    via _create_hud_window_if_enabled(), juste avant webview.start().
    Conservé pour compatibilité avec le thread de démarrage.
    """
    pass  # Handled on main thread in main()


# ═══════════════════════════════════════════════════════════════════════════
# V5.3 — HUD PYSIDE6 (fenêtre vraiment transparente, always-on-top)
# Fenêtre HUD Qt pilotée depuis le thread principal avant webview.start()
# ═══════════════════════════════════════════════════════════════════════════

_HUD_QT_WINDOW  = None  # fenêtre PySide6 du HUD
_HUD_QT_THREAD  = None  # reliquat compat/debug : toujours None en mode main-thread
_HUD_VISIBLE    = False
_HUD_QT_APP     = None  # QApplication singleton
_HUD_LABELS     = {}    # clé -> QLabel
_HUD_QT_TIMER   = None  # timer polling status HUD
_HUD_CMD_TIMER  = None  # timer de polling des commandes cross-thread
_HUD_CMD_QUEUE  = queue.Queue()


def _hud_default_xy():
    try:
        screen_w = ctypes.windll.user32.GetSystemMetrics(0)
        screen_h = ctypes.windll.user32.GetSystemMetrics(1)
    except Exception:
        screen_w, screen_h = 1920, 1080
    saved_x = int(AUDIO_CONFIG.get("mini_overlay_x", -1) or -1)
    saved_y = int(AUDIO_CONFIG.get("mini_overlay_y", 40) or 40)
    if saved_x < 0 or saved_x > screen_w - 50:
        saved_x = screen_w - 240
    if saved_y < 0 or saved_y > screen_h - 50:
        saved_y = 40
    return saved_x, saved_y


def _ensure_hud_qt_app():
    """Garantit l'existence d'une unique QApplication sur le thread principal."""
    global _HUD_QT_APP
    if _HUD_QT_APP is not None:
        return _HUD_QT_APP
    try:
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import QCoreApplication
    except Exception as e:
        stealth_print(f"⚠️ PySide6 erreur QApplication: {e}")
        return None
    import sys
    _HUD_QT_APP = QApplication.instance() or QApplication(sys.argv)
    try:
        qt_app_dir = Path(QCoreApplication.applicationDirPath()).resolve()
    except Exception:
        qt_app_dir = BASE_EXTERNAL
    try:
        stealth_print(f"[Qt] applicationDirPath={qt_app_dir}")
    except Exception:
        pass
    try:
        qt_conf_source = BASE_INTERNAL / "qt.conf"
        qt_conf_target = qt_app_dir / "qt.conf"
        if qt_conf_source.exists():
            qt_conf_content = qt_conf_source.read_text(encoding="utf-8")
            if (not qt_conf_target.exists()) or (qt_conf_target.read_text(encoding="utf-8") != qt_conf_content):
                qt_conf_target.write_text(qt_conf_content, encoding="utf-8")
                stealth_print(f"[Qt] qt.conf copié vers {qt_conf_target}")
        elif qt_app_dir == BASE_EXTERNAL:
            qt_conf_target.write_text("[Platforms]\nWindowsArguments = dpiawareness=0\n", encoding="utf-8")
            stealth_print(f"[Qt] qt.conf régénéré dans {qt_conf_target}")
    except Exception as e:
        stealth_print(f"⚠️ Qt config copy error: {e}")
    return _HUD_QT_APP


def _hud_build_window():
    """Construit la fenêtre HUD PySide6 sur le thread principal."""
    global _HUD_QT_WINDOW, _HUD_LABELS, _HUD_QT_APP, _HUD_QT_TIMER

    try:
        from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame
        from PySide6.QtCore import Qt, QTimer
        from PySide6.QtGui import QColor, QPainter, QPen, QBrush
    except Exception as _e:
        stealth_print(f"⚠️ PySide6 erreur: {_e}")
        return None

    _HUD_QT_APP = _ensure_hud_qt_app()
    if _HUD_QT_APP is None:
        return None

    BORDER  = "#2f81f7"
    FG_TTL  = "#2f81f7"
    FG_KEY  = "#8b949e"
    FG_VAL  = "#a855f7"
    FG_OK   = "#4ade80"
    FG_WARN = "#fbbf24"
    FG_ERR  = "#f87171"

    rows_def = [
        ("hudShowPreset", "PRESET",  FG_VAL,  "hudPreset"),
        ("hudShowRMS",    "RMS",     FG_VAL,  "hudRMS"),
        ("hudShowSNR",    "SNR",     FG_VAL,  "hudSNR"),
        ("hudShowFocus",  "FOCUS",   FG_VAL,  "hudFocus"),
        ("hudShowUptime", "UPTIME",  FG_OK,   "hudUptime"),
        ("hudShowMic",    "MICRO",   FG_OK,   "hudMic"),
        ("hudShowListen", "ÉCOUTE",  FG_VAL,  "hudListen"),
        ("hudShowGame",   "JEU",     FG_VAL,  "hudGame"),
    ]

    class HUDWindow(QWidget):
        def __init__(self):
            super().__init__()
            self.setWindowFlags(
                Qt.FramelessWindowHint |
                Qt.WindowStaysOnTopHint |
                Qt.Window
            )
            self.setAttribute(Qt.WA_TranslucentBackground)
            self._drag_pos = None
            self._bg_alpha = max(10, min(255, int(AUDIO_CONFIG.get("mini_overlay_opacity", 85) * 2.55)))
            self._setup_ui()
            x0, y0 = _hud_default_xy()
            self.move(x0, y0)
            self.setWindowOpacity(0.92)
            self.raise_()
            self.activateWindow()

        def _setup_ui(self):
            outer = QVBoxLayout(self)
            outer.setContentsMargins(1, 1, 1, 1)
            outer.setSpacing(0)

            title_row = QHBoxLayout()
            title_row.setContentsMargins(8, 5, 8, 5)
            lbl_title = QLabel("⚡ KOMMZ HUD")
            lbl_title.setStyleSheet(
                f"color:{FG_TTL}; font:bold 9pt 'Segoe UI'; background:transparent;")
            title_row.addWidget(lbl_title)
            title_row.addStretch()
            self._close_btn = QLabel("✕")
            self._close_btn.setStyleSheet(
                f"color:{FG_KEY}; font:bold 9pt 'Segoe UI'; background:transparent;")
            self._close_btn.setCursor(Qt.PointingHandCursor)
            self._close_btn.mousePressEvent = lambda e: _hud_close_from_ui()
            self._close_btn.enterEvent = lambda e: self._close_btn.setStyleSheet(
                f"color:{FG_ERR}; font:bold 9pt 'Segoe UI'; background:transparent;")
            self._close_btn.leaveEvent = lambda e: self._close_btn.setStyleSheet(
                f"color:{FG_KEY}; font:bold 9pt 'Segoe UI'; background:transparent;")
            title_row.addWidget(self._close_btn)
            outer.addLayout(title_row)

            sep = QFrame()
            sep.setFrameShape(QFrame.HLine)
            sep.setStyleSheet(f"background:{BORDER}; max-height:1px; border:none;")
            outer.addWidget(sep)

            self._rows = {}
            for cfg_key, label_text, val_color, val_key in rows_def:
                row_w = QWidget()
                row_w.setStyleSheet("background:transparent;")
                row_l = QHBoxLayout(row_w)
                row_l.setContentsMargins(8, 2, 8, 2)
                lbl_key = QLabel(label_text)
                lbl_key.setStyleSheet(
                    f"color:{FG_KEY}; font:9pt 'Segoe UI'; background:transparent;")
                lbl_key.setFixedWidth(70)
                fsize = "7" if val_key in ("hudMic", "hudListen") else "9"
                lbl_val = QLabel("—")
                lbl_val.setStyleSheet(
                    f"color:{val_color}; font:bold {fsize}pt 'Segoe UI'; background:transparent;")
                lbl_val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                row_l.addWidget(lbl_key)
                row_l.addWidget(lbl_val, 1)
                outer.addWidget(row_w)
                self._rows[val_key] = (row_w, lbl_val, cfg_key)
                _HUD_LABELS[val_key] = lbl_val

            outer.addSpacing(5)
            self.setFixedWidth(200)

        def set_opacity(self, pct):
            self._bg_alpha = max(10, min(255, int(pct * 2.55)))
            self.update()

        def apply_row_visibility(self):
            for val_key, (row_w, lbl_val, cfg_key) in self._rows.items():
                row_w.setVisible(AUDIO_CONFIG.get(cfg_key, True))
            self.adjustSize()

        def paintEvent(self, event):
            p = QPainter(self)
            p.setRenderHint(QPainter.Antialiasing)
            rect = self.rect().adjusted(0, 0, -1, -1)
            p.setBrush(QBrush(QColor(11, 15, 20, self._bg_alpha)))
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(rect, 8, 8)
            p.setBrush(Qt.NoBrush)
            p.setPen(QPen(QColor(BORDER), 1))
            p.drawRoundedRect(rect, 8, 8)
            p.end()

        def mousePressEvent(self, e):
            if e.button() == Qt.LeftButton:
                self._drag_pos = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

        def mouseMoveEvent(self, e):
            if e.buttons() == Qt.LeftButton and self._drag_pos:
                new_pos = e.globalPosition().toPoint() - self._drag_pos
                self.move(new_pos)
                AUDIO_CONFIG["mini_overlay_x"] = new_pos.x()
                AUDIO_CONFIG["mini_overlay_y"] = new_pos.y()

        def mouseReleaseEvent(self, e):
            self._drag_pos = None

    if _HUD_QT_WINDOW is not None:
        try:
            _HUD_QT_WINDOW.close()
        except Exception as e:
            stealth_print(f"⚠️ HUD previous window close error: {e}")

    _HUD_LABELS.clear()
    win = HUDWindow()
    _HUD_QT_WINDOW = win
    stealth_print(f"🔍 HUD debug: win.show() appelé, position=({win.x()},{win.y()})")
    win.show()
    from PySide6.QtWidgets import QApplication
    QApplication.processEvents()
    stealth_print(f"🔍 HUD visible={win.isVisible()} geometry={win.geometry()}")

    def _hud_set(key, text, color):
        lbl = _HUD_LABELS.get(key)
        if lbl:
            try:
                fsize = "7" if key in ("hudMic", "hudListen") else "9"
                lbl.setText(text)
                lbl.setStyleSheet(
                    f"color:{color}; font:bold {fsize}pt 'Segoe UI'; background:transparent;")
            except Exception as e:
                stealth_print(f"⚠️ HUD label update error ({key}): {e}")

    def _poll():
        if _HUD_QT_WINDOW is None:
            return
        try:
            import urllib.request
            with urllib.request.urlopen(
                    f"http://127.0.0.1:{VTP_CORE_PORT}/status", timeout=0.8) as resp:
                d = json.loads(resp.read())
            rt = d.get("listen_runtime") or d.get("pipeline_runtime") or {}
            try:
                stealth_print_rl(
                    "hud_status_keys",
                    f"🔍 HUD status keys={sorted(list(d.keys()))[:40]}",
                    cooldown=10.0,
                )
                stealth_print_rl(
                    "hud_runtime_keys",
                    f"🔍 HUD runtime keys={sorted(list(rt.keys()))[:40] if isinstance(rt, dict) else rt}",
                    cooldown=10.0,
                )
            except Exception:
                pass

            preset_value = d.get("ally_game_preset") or d.get("quality_preset") or "—"
            _hud_set("hudPreset", preset_value, FG_VAL)

            vf_state = d.get("voice_focus_v3_state") if isinstance(d.get("voice_focus_v3_state"), dict) else {}
            pipeline_rt = d.get("pipeline_runtime") if isinstance(d.get("pipeline_runtime"), dict) else {}
            modules_rt = d.get("modules_runtime") if isinstance(d.get("modules_runtime"), dict) else {}
            listen_health = d.get("listen_health") if isinstance(d.get("listen_health"), dict) else {}
            listen_runtime = d.get("listen_runtime") if isinstance(d.get("listen_runtime"), dict) else {}

            rms = None
            for candidate in (
                vf_state.get("noise_rms_ema"),
                d.get("ally_voice_focus_auto_noise_rms"),
                rt.get("noise_rms") if isinstance(rt, dict) else None,
                listen_runtime.get("noise_rms"),
                d.get("rms"),
            ):
                if candidate is not None:
                    rms = candidate
                    break
            if rms is not None:
                try:
                    rms_value = float(rms)
                    _hud_set("hudRMS", f"{rms_value:.4f}",
                             FG_WARN if rms_value > 0.1 else FG_VAL)
                except Exception:
                    _hud_set("hudRMS", str(rms), FG_VAL)
            else:
                _hud_set("hudRMS", "—", FG_VAL)

            snr = None
            for candidate in (
                vf_state.get("snr_approx_db"),
                rt.get("snr_db") if isinstance(rt, dict) else None,
                listen_runtime.get("snr_db"),
                d.get("snr_db"),
            ):
                if candidate is not None:
                    snr = candidate
                    break
            if snr is not None:
                try:
                    snr_value = float(snr)
                    snr = snr_value
                    _hud_set("hudSNR", f"{snr_value:.1f} dB",
                             FG_OK if snr_value > 20 else (FG_VAL if snr_value > 10 else FG_WARN))
                except Exception:
                    _hud_set("hudSNR", str(snr), FG_VAL)
            else:
                _hud_set("hudSNR", "—", FG_VAL)

            focus = d.get("ally_voice_focus_effective") or d.get("ally_voice_focus_mode") or "—"
            _hud_set("hudFocus", focus, FG_WARN if focus == "aggressive" else FG_VAL)

            up = None
            for candidate in (
                d.get("uptime_seconds"),
                pipeline_rt.get("uptime_seconds"),
                d.get("server_uptime_seconds"),
            ):
                if candidate is not None:
                    try:
                        up = float(candidate)
                        break
                    except Exception:
                        pass
            h2 = m2 = 0
            if up is not None and up > 0:
                h2, m2 = int(up // 3600), int((up % 3600) // 60)
            _hud_set("hudUptime",
                (f"{h2}h {m2}min" if h2 > 0 else f"{m2}min") if up is not None and up > 0 else "—", FG_OK)

            if d.get("recording"):
                _hud_set("hudMic", "🔴 REC", FG_ERR)
            else:
                _hud_set("hudMic", "✅ Prêt", FG_OK)

            _hud_set("hudListen",
                "ACTIF" if d.get("is_listening") else "INACTIF",
                FG_OK   if d.get("is_listening") else FG_WARN)

            game = ""
            for candidate in (
                d.get("game_detect_current_game"),
                d.get("detected_game"),
                d.get("current_game"),
                listen_health.get("current_game"),
                listen_runtime.get("current_game"),
                modules_rt.get("game_auto_detect", {}).get("detail") if isinstance(modules_rt.get("game_auto_detect"), dict) else None,
            ):
                if candidate:
                    game = str(candidate).strip()
                    if game:
                        break
            _hud_set("hudGame", game or "—", FG_VAL)

            try:
                stealth_print_rl(
                    "hud_values",
                    "🔍 HUD values "
                    f"preset={preset_value!r} "
                    f"rms={rms!r} "
                    f"snr={snr!r} "
                    f"focus={focus!r} "
                    f"uptime={up!r} "
                    f"recording={d.get('recording')!r} "
                    f"listening={d.get('is_listening')!r} "
                    f"game={game!r}",
                    cooldown=10.0,
                )
                stealth_print_rl(
                    "hud_sources",
                    "🔍 HUD sources "
                    f"vf_keys={sorted(list(vf_state.keys()))[:12] if isinstance(vf_state, dict) else vf_state!r} "
                    f"pipeline_keys={sorted(list(pipeline_rt.keys()))[:12] if isinstance(pipeline_rt, dict) else pipeline_rt!r} "
                    f"listen_health_keys={sorted(list(listen_health.keys()))[:12] if isinstance(listen_health, dict) else listen_health!r}",
                    cooldown=10.0,
                )
            except Exception:
                pass

            win.apply_row_visibility()

        except Exception as e:
            stealth_print_rl(
                "hud_poll_error",
                f"⚠️ HUD poll error: {e}",
                cooldown=20.0,
            )

    if _HUD_QT_TIMER is not None:
        try:
            _HUD_QT_TIMER.stop()
        except Exception as e:
            stealth_print(f"⚠️ HUD timer stop error: {e}")

    timer = QTimer()
    timer.timeout.connect(_poll)
    timer.start(1000)
    _HUD_QT_TIMER = timer
    globals()["_hud_qt_timer"] = timer
    globals()["_hud_set_fn"] = _hud_set

    _poll()
    stealth_print("✅ HUD PySide6 initialisé sur main thread")
    _hud_start_command_timer()
    return win

def _hud_close_from_ui():
    """Ferme le HUD PySide6 proprement sans quitter l'application Qt principale."""
    global _HUD_QT_WINDOW, _HUD_VISIBLE, _HUD_QT_THREAD, _HUD_QT_TIMER
    _HUD_VISIBLE = False
    win = _HUD_QT_WINDOW
    if _HUD_QT_TIMER is not None:
        try:
            _HUD_QT_TIMER.stop()
        except Exception as e:
            stealth_print(f"⚠️ HUD timer close error: {e}")
        _HUD_QT_TIMER = None
    if win is not None:
        try:
            win.hide()
        except Exception as e:
            stealth_print(f"⚠️ HUD close error: {e}")
    _HUD_QT_THREAD = None


def _hud_enqueue_command(action, **payload):
    """Empile une commande HUD à exécuter sur le thread principal Qt."""
    _HUD_CMD_QUEUE.put({"action": action, **payload})
    try:
        stealth_print(
            f"🔍 HUD queue push action={action} "
            f"qsize={_HUD_CMD_QUEUE.qsize()} "
            f"timer_started={_HUD_CMD_TIMER is not None} "
            f"window_exists={_HUD_QT_WINDOW is not None} "
            f"visible={_HUD_VISIBLE}"
        )
    except Exception:
        pass


def _hud_process_pending_commands():
    """Traite les commandes HUD émises depuis d'autres threads."""
    global _HUD_VISIBLE
    while True:
        try:
            cmd = _HUD_CMD_QUEUE.get_nowait()
        except queue.Empty:
            break

        action = cmd.get("action")
        try:
            stealth_print(
                f"🔍 HUD queue pop action={action} "
                f"timer_started={_HUD_CMD_TIMER is not None} "
                f"window_exists={_HUD_QT_WINDOW is not None} "
                f"visible={_HUD_VISIBLE}"
            )
        except Exception:
            pass
        if action == "show":
            AUDIO_CONFIG["mini_overlay_enabled"] = True
            if _HUD_QT_WINDOW is None:
                _HUD_VISIBLE = True
                _hud_build_window()
            else:
                _HUD_VISIBLE = True
                try:
                    _HUD_QT_WINDOW.show()
                    _HUD_QT_WINDOW.raise_()
                    _HUD_QT_WINDOW.activateWindow()
                except Exception as e:
                    stealth_print(f"⚠️ HUD show error: {e}")
        elif action == "hide":
            _hud_close_from_ui()
        elif action == "move":
            if _HUD_QT_WINDOW is not None:
                try:
                    x = int(cmd.get("x", AUDIO_CONFIG.get("mini_overlay_x", 40)))
                    y = int(cmd.get("y", AUDIO_CONFIG.get("mini_overlay_y", 40)))
                    _HUD_QT_WINDOW.move(x, y)
                    AUDIO_CONFIG["mini_overlay_x"] = x
                    AUDIO_CONFIG["mini_overlay_y"] = y
                except Exception as e:
                    stealth_print(f"⚠️ HUD queued move error: {e}")
        elif action == "opacity":
            if _HUD_QT_WINDOW is not None:
                try:
                    value = int(cmd.get("value", AUDIO_CONFIG.get("mini_overlay_opacity", 85)))
                    _HUD_QT_WINDOW.set_opacity(value)
                    AUDIO_CONFIG["mini_overlay_opacity"] = value
                except Exception as e:
                    stealth_print(f"⚠️ HUD queued opacity error: {e}")
        elif action == "refresh_rows":
            if _HUD_QT_WINDOW is not None:
                try:
                    _HUD_QT_WINDOW.apply_row_visibility()
                except Exception as e:
                    stealth_print(f"⚠️ HUD queued row refresh error: {e}")


def _hud_start_command_timer():
    """Démarre le polling Qt des commandes HUD sur le thread principal."""
    global _HUD_CMD_TIMER
    try:
        from PySide6.QtCore import QTimer
    except Exception as e:
        stealth_print(f"⚠️ PySide6 erreur QTimer HUD: {e}")
        return None
    if _HUD_CMD_TIMER is not None:
        return _HUD_CMD_TIMER

    timer = QTimer()
    timer.timeout.connect(_hud_process_pending_commands)

    def start_poll():
        try:
            _hud_process_pending_commands()
        except Exception as e:
            stealth_print(f"⚠️ HUD initial poll error: {e}")
        timer.start(100)
        stealth_print("🔍 HUD command timer started")

    QTimer.singleShot(500, start_poll)
    _HUD_CMD_TIMER = timer
    return timer


def _create_hud_window_if_enabled():
    """V5.3: Crée la fenêtre HUD Qt au démarrage puis applique son état visible/caché."""
    global _HUD_VISIBLE
    _ensure_hud_qt_app()
    _hud_start_command_timer()
    stealth_print(f"🔍 HUD debug: mini_overlay_enabled={AUDIO_CONFIG.get('mini_overlay_enabled')}")
    if not AUDIO_CONFIG.get("mini_overlay_enabled", False):
        stealth_print(
            f"🔍 HUD boot skipped: enabled=False "
            f"timer_started={_HUD_CMD_TIMER is not None} "
            f"window_exists={_HUD_QT_WINDOW is not None}"
        )
        return None
    window = _hud_build_window()
    _HUD_VISIBLE = True
    return window


def check_for_updates():
    if not AUDIO_CONFIG.get("auto_update_active", False):
        _set_module_runtime("autoupdate", "Inactif", "Vérification automatique désactivée")
        return
    if not UPDATE_CHECK_URL:
        _set_module_runtime("autoupdate", "Non configuré", "Aucun service de mise à jour configuré")
        return
    try:
        r = requests.get(
            UPDATE_CHECK_URL,
            params={
                "current": CURRENT_VERSION,
                "channel": UPDATE_CHANNEL,
                "platform": "windows",
            },
            timeout=(4, 12),
        )
        payload = r.json() if r.ok else {}
        if not r.ok or not payload.get("ok"):
            UPDATE_STATE["error"] = payload.get("error", f"update check failed ({r.status_code})")
            _set_module_runtime("autoupdate", "Erreur", _short_runtime_text(UPDATE_STATE["error"], 96))
            return

        UPDATE_STATE["checked_at"] = int(time.time())
        UPDATE_STATE["update_available"] = bool(payload.get("update_available"))
        UPDATE_STATE["latest_version"] = str(payload.get("latest_version") or CURRENT_VERSION)
        UPDATE_STATE["download_url"] = str(payload.get("download_url") or "").strip()
        UPDATE_STATE["changelog_url"] = str(payload.get("changelog_url") or "").strip()
        UPDATE_STATE["download_sha256"] = str(payload.get("download_sha256") or "").strip().lower()
        UPDATE_STATE["force_update"] = bool(payload.get("force_update"))
        UPDATE_STATE["minimum_version"] = str(payload.get("minimum_version") or "").strip()
        UPDATE_STATE["message"] = str(payload.get("message") or "").strip()
        UPDATE_STATE["error"] = ""

        if UPDATE_STATE["update_available"]:
            if UPDATE_STATE["force_update"]:
                add_subtitle(f"SYSTEM >> UPDATE OBLIGATOIRE {UPDATE_STATE['latest_version']}", "SYS")
                _set_module_runtime("autoupdate", "Update", f"Mise à jour obligatoire {UPDATE_STATE['latest_version']}")
            else:
                add_subtitle(f"SYSTEM >> UPDATE {UPDATE_STATE['latest_version']} DISPO", "SYS")
                _set_module_runtime("autoupdate", "Update", f"Version {UPDATE_STATE['latest_version']} disponible")
        else:
            _set_module_runtime("autoupdate", "À jour", f"Version {CURRENT_VERSION} confirmée")
    except Exception as e:
        UPDATE_STATE["error"] = str(e)
        _set_module_runtime("autoupdate", "Erreur", _short_runtime_text(str(e), 96))


def update_check_loop():
    while True:
        try:
            check_for_updates()
        except Exception:
            pass
        _PERF_STOP_EVENT.wait(3600)

def start_server():
    # En mode EXE (Production), on utilise un serveur WSGI robuste
    # pour éviter les conflits de Threads avec l'interface Webview.
    startup_trace(f"start_server: boot requested on port {VTP_CORE_PORT}")
    try:
        if WAITRESS_SERVE is not None:
            startup_trace("start_server: waitress available, serving with waitress")
            stealth_print("🚀 Serveur Waitress (Production) démarré sur le port 8770")
            WAITRESS_SERVE(app, host='0.0.0.0', port=VTP_CORE_PORT, threads=6)
            return
        startup_trace("start_server: waitress unavailable, fallback to Flask app.run")
        # Fallback si Waitress n'est pas là (Dev mode)
        stealth_print("⚠️ Waitress non trouvé, utilisation de Flask (Dev Mode)")
        app.run(host='0.0.0.0', port=VTP_CORE_PORT, debug=False, use_reloader=False)
    except Exception as e:
        startup_trace(f"start_server: fatal error: {e}")
        startup_trace(traceback.format_exc())
        stealth_print(f"❌ Serveur local indisponible sur {VTP_CORE_PORT}: {e}")
        stealth_print("ℹ️ Vérifie qu'une autre instance de Kommz Gamer n'utilise pas déjà le port 8770.")

SERVER_BOOTSTRAPPED = False

def get_startup_log_path() -> str:
    try:
        base = os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()
    except Exception:
        base = tempfile.gettempdir()
    target_dir = os.path.join(base, "KommzGamer")
    try:
        os.makedirs(target_dir, exist_ok=True)
    except Exception:
        pass
    return os.path.join(target_dir, "startup.log")

def startup_trace(msg: str):
    try:
        stamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        with open(get_startup_log_path(), "a", encoding="utf-8") as fh:
            fh.write(f"[{stamp}] {msg}\n")
    except Exception:
        pass

def ensure_local_server_started():
    global SERVER_BOOTSTRAPPED
    if SERVER_BOOTSTRAPPED:
        startup_trace("ensure_local_server_started: server already bootstrapped")
        return
    startup_trace("ensure_local_server_started: launching background server thread")
    SERVER_BOOTSTRAPPED = True
    threading.Thread(target=start_server, daemon=True).start()

def wait_for_local_server(port: int, timeout_s: float = 15.0) -> bool:
    """Attend que le serveur local soit réellement prêt avant d'ouvrir WebView."""
    deadline = time.time() + max(1.0, float(timeout_s or 15.0))
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", int(port)), timeout=0.75):
                return True
        except Exception:
            time.sleep(0.25)
    return False

def get_local_ip():
    def _is_private_ipv4(ip: str) -> bool:
        if not ip or ip.startswith("127.") or ip.startswith("169.254."):
            return False
        if ip.startswith("10.") or ip.startswith("192.168."):
            return True
        if ip.startswith("172."):
            try:
                second = int(ip.split(".")[1])
                return 16 <= second <= 31
            except Exception:
                return False
        return False

    candidates = []

    def _push(ip: str):
        if _is_private_ipv4(ip) and ip not in candidates:
            candidates.append(ip)

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        _push(s.getsockname()[0])
        s.close()
    except Exception:
        pass

    try:
        for ip in socket.gethostbyname_ex(socket.gethostname())[2]:
            _push(ip)
    except Exception:
        pass

    try:
        import psutil
        pref = []
        other = []
        for if_name, addrs in (psutil.net_if_addrs() or {}).items():
            for a in addrs:
                if getattr(a, "family", None) != socket.AF_INET:
                    continue
                ip = getattr(a, "address", "")
                if not _is_private_ipv4(ip):
                    continue
                lower = str(if_name).lower()
                if any(k in lower for k in ["wi-fi", "wifi", "wlan", "ethernet", "eth"]):
                    if ip not in pref:
                        pref.append(ip)
                else:
                    if ip not in other:
                        other.append(ip)
        for ip in pref + other:
            _push(ip)
    except Exception:
        pass

    return candidates[0] if candidates else "127.0.0.1"

def _toggle_monitoring_core(source="F3"):
    """Toggle monitoring avec anti double-trigger (hook + polling)."""
    global _last_monitoring_toggle_ts
    now = time.time()
    if (now - float(_last_monitoring_toggle_ts or 0.0)) < 0.35:
        return
    _last_monitoring_toggle_ts = now

    current = AUDIO_CONFIG.get("monitoring_enabled", False)
    AUDIO_CONFIG["monitoring_enabled"] = not current
    save_settings()

    etat = "🔊 ACTIVÉ" if AUDIO_CONFIG["monitoring_enabled"] else "🔇 DÉSACTIVÉ"
    stealth_print(f"\n🎧 {source} : RETOUR CASQUE (Monitoring) {etat}")
    add_subtitle(f"SYSTEM >> MONITORING {etat}", "SYS")

def toggle_monitoring():
    _toggle_monitoring_core(source="F3/HOTKEY")
    
def panic_reset():
    """ Réinitialise tout le système audio """
    global _ptt_rec
    stealth_print("\n🆘 RÉINITIALISATION AUDIO (PANIC KEY)...")
    
    # 1. Reset variables
    AUDIO_CONFIG["bypass_mode_active"] = False
    _ptt_rec = False
    
    # 2. Reset Sonore brutal
    try: sd.stop() 
    except: pass
    
    # 3. FEEDBACK VISUEL & SONORE (Ce qui manquait)
    add_subtitle("SYSTEM >> PANIC RESET OK", "SYS") # Message Violet
    try: 
        import winsound
        # Double Bip d'urgence
        winsound.Beep(1000, 100)
        time.sleep(0.1)
        winsound.Beep(1000, 100)
    except: pass
    
    stealth_print("✅ Audio réinitialisé. Prêt.")

def reset_to_factory():
    global AUDIO_CONFIG
    # Utilisation du nom direct pour éviter le NameError
    if os.path.exists(CONFIG_FILE):
        try:
            os.remove(CONFIG_FILE)
            stealth_print(f"🗑️ Fichier de config supprimé: {CONFIG_FILE}")
        except Exception as e:
            stealth_print(f"❌ Erreur suppression : {e}")
    
    # Valeurs par défaut
    AUDIO_CONFIG.update({
        "tts_engine": "WINDOWS",
        "game_output_device": "CABLE Input", 
        "game_input_device": "CABLE Output",
        "ptt_hotkey": "ctrl+shift"
    })
    save_settings()
    stealth_print("♻️ Paramètres d'usine restaurés.")

try:
    import keyboard
    # Monitoring (F3) : Retour son local
    if AUDIO_CONFIG.get('hotkey_f3_enabled', True): keyboard.add_hotkey('f3', toggle_monitoring)
    
    # Bypass (F4) : Désactivation de l'IA et passage en direct
    #keyboard.add_hotkey('f4', toggle_bypass_action)
    
    # Ajoute cette ligne pour activer F8
    keyboard.add_hotkey('f8', panic_reset)
    
    stealth_print("✅ Raccourcis F3 (Monitoring) et F4 (Bypass) activés.")
except Exception as e:
    stealth_print(f"❌ Erreur lors de l'activation des raccourcis globaux : {e}")
    
class JSApi:
    def save_audio_config(self, tts_name, listen_name, ptt_key):
        global AUDIO_CONFIG
        
        AUDIO_CONFIG["game_output_device_key"] = _normalize_device_signature(tts_name, "")
        AUDIO_CONFIG["game_input_device_key"] = _normalize_device_signature(listen_name, "")
        AUDIO_CONFIG["game_output_device_runtime"] = _resolve_device_signature(
            AUDIO_CONFIG["game_output_device_key"], as_output=True
        ) or {}
        AUDIO_CONFIG["game_input_device_runtime"] = _resolve_device_signature(
            AUDIO_CONFIG["game_input_device_key"], as_output=False
        ) or {}
        AUDIO_CONFIG["ptt_hotkey"] = ptt_key # On met à jour la touche
        
        save_settings()
        
        # 🛡️ SÉCURITÉ : On ne doit PAS lier ptt_key à toggle_bypass_action ici !
        try:
            keyboard.unhook_all_hotkeys()
            if AUDIO_CONFIG.get('hotkey_f2_enabled', True): keyboard.add_hotkey('f2', toggle_tts_action)
            keyboard.add_hotkey('f4', toggle_bypass_action) # Bypass = F4
            if AUDIO_CONFIG.get('hotkey_f3_enabled', True): keyboard.add_hotkey('f3', toggle_monitoring_action)
            keyboard.add_hotkey('f8', panic_reset)
        except: pass
        
        return {"status": "success"}

# --- FONCTIONS DES TOUCHES ---

def toggle_bypass_action():
    global AUDIO_CONFIG
    current = AUDIO_CONFIG.get("bypass_mode_active", False)
    new_state = not current
    AUDIO_CONFIG["bypass_mode_active"] = new_state
    save_settings()
    
    if new_state:
        # --- PAUSE ---
        msg = "PAUSE (BYPASS ACTIF)"
        # On vide l'ancien texte pour nettoyer l'écran
        global subs_buffer
        subs_buffer = [] 
        
        # Et on arrête l'enregistrement en cours s'il y en a un
        try: stop_rec() 
        except: pass
        freq = 500
    else:
        # --- REPRISE ---
        msg = "REPRISE (SYSTÈME PRÊT)"
        freq = 1500
    
    stealth_print(f"🔁 F4 : {msg}")
    add_subtitle(f"SYSTEM >> {msg}", "SYS") # <--- Affiche en violet (Message de pause)

    try: 
        import winsound
        winsound.Beep(freq, 200)
    except: pass

def toggle_tts_action():
    # 1. On déclare la variable globale pour être sûr de modifier la vraie config
    global AUDIO_CONFIG
    
    # 2. Inversion état
    curr = AUDIO_CONFIG.get("tts_active", True)
    new_state = not curr
    AUDIO_CONFIG["tts_active"] = new_state
    
    # 3. SAUVEGARDE IMMÉDIATE (C'est la ligne qui manquait !)
    # Cela permet de conserver le réglage même si tu fermes le logiciel
    save_settings()
    
    # 4. Message & Feedback
    if new_state:
        msg = "AUDIO IA (TTS) : ON"
        freq = 1000
    else:
        msg = "AUDIO IA (TTS) : MUET"
        freq = 400

    # 5. Overlay & Console
    stealth_print(f"🔊 F2 : {msg}")
    add_subtitle(f"SYSTEM >> {msg}", "SYS") # Affiche en violet

    try: 
        import winsound
        winsound.Beep(freq, 150)
    except: pass

def toggle_monitoring_action():
    _toggle_monitoring_core(source="F3")
    if AUDIO_CONFIG.get("monitoring_enabled", False):
        sound_freq = 1000
    else:
        sound_freq = 400
    
    try: 
        import winsound
        winsound.Beep(sound_freq, 150)
    except: pass

# V5.2: Raccourcis globaux toggle écoute + cycle presets
def toggle_ecoute_action():
    global AUDIO_CONFIG, DG_ENGINE
    curr = bool(AUDIO_CONFIG.get("is_listening", True))
    new_state = not curr
    AUDIO_CONFIG["is_listening"] = new_state
    save_settings()
    state_str = "OUVERT" if new_state else "MUTE"
    stealth_print(f"🎤 toggle_ecoute: Micro {state_str}")
    _push_toast(f"🎤 Micro {state_str}")
    try:
        import winsound
        winsound.Beep(1200 if new_state else 300, 120)
    except: pass
    if new_state:
        try:
            if "DG_ENGINE" in globals() and DG_ENGINE:
                DG_ENGINE.is_running = False
        except: pass
        in_id = AUDIO_CONFIG.get("game_input_device", 0)
        DG_ENGINE = DeepgramEngine()
        threading.Thread(target=DG_ENGINE.start_streaming, args=(in_id,), daemon=True).start()
    else:
        try:
            if "DG_ENGINE" in globals() and DG_ENGINE:
                DG_ENGINE.is_running = False
        except: pass

def cycle_preset_action(direction=1):
    """Cycle through LISTEN_GAME_PRESETS. direction: +1 = next, -1 = previous."""
    preset_keys = list(LISTEN_GAME_PRESETS.keys())
    if not preset_keys:
        return
    current = str(AUDIO_CONFIG.get("ally_game_preset", "custom") or "custom").strip().lower()
    try:
        idx = preset_keys.index(current)
    except ValueError:
        idx = -1 if direction > 0 else 0
    new_idx = (idx + direction) % len(preset_keys)
    new_key = preset_keys[new_idx]
    ok, info = _apply_listen_game_preset(new_key)
    if ok:
        stealth_print(f"🔄 cycle_preset: {info} ({new_key})")
        _push_toast(f"🔄 {info}")
        try:
            import winsound
            winsound.Beep(800, 80)
            winsound.Beep(1000, 80)
        except: pass


# V5.2 Bloc 6: Tray icon sante Windows (vert/jaune/rouge selon listen_health)
def _tray_icon_loop():
    """Boucle d'icone dans la zone de notification Windows avec couleur selon sante."""
    try:
        import pystray
        from PIL import Image, ImageDraw

        def _make_icon(color):
            img = Image.new('RGBA', (32, 32), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            draw.ellipse((4, 4, 28, 28), fill=color, outline=(255, 255, 255, 180))
            return img

        icon = pystray.Icon(
            'kommz_gamer',
            _make_icon((0, 200, 0)),  # vert par defaut
            menu=pystray.Menu(
                pystray.MenuItem('Kommz Gamer V5.2', None, enabled=False),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem('Quitter', lambda: os._exit(0))
            )
        )

        def _update_loop():
            last_color = None
            while True:
                try:
                    health = _listen_runtime.get('listen_health', {}).get('level', 'ok')
                    if health == 'critical':
                        color = (220, 40, 40)  # rouge
                    elif health == 'warning':
                        color = (220, 180, 20)  # jaune
                    else:
                        color = (40, 180, 40)  # vert
                    if color != last_color:
                        icon.icon = _make_icon(color)
                        last_color = color
                except: pass
                time.sleep(5)
        threading.Thread(target=_update_loop, daemon=True).start()
        icon.run()
    except Exception:
        pass  # pystray non disponible ou erreur silencieuse


class Bridge:
    def update_voice_id(self, new_id):
        """Compatibilite retro: moteur legacy retire."""
        stealth_print("INFO: Moteur legacy retire, update_voice_id ignore.")
        return False

    def show_hud(self):
        """V5.3: Ouvre le HUD Qt transparent."""
        try:
            _hud_enqueue_command("show")
            AUDIO_CONFIG["mini_overlay_enabled"] = True
            stealth_print("✅ HUD Qt demandé (Bridge.show_hud)")
            return True
        except Exception as e:
            stealth_print(f"⚠️ Bridge.show_hud erreur: {e}")
            return False

    def hide_hud(self):
        """V5.3: Ferme le HUD Qt."""
        try:
            _hud_enqueue_command("hide")
            stealth_print("✅ HUD Qt masquage demandé (Bridge.hide_hud)")
            return True
        except Exception as e:
            stealth_print(f"⚠️ Bridge.hide_hud erreur: {e}")
            return False

_tts_blueprint = register_tts_module(
    ALL_EDGE_VOICES=ALL_EDGE_VOICES,
    AUDIO_CONFIG=AUDIO_CONFIG,
    CURRENT_TARGET_LANG_GETTER=lambda: CURRENT_TARGET_LANG,
    FALLBACK_VOICES=FALLBACK_VOICES,
    LAST_USER_AUDIO_BUFFER_GETTER=lambda: LAST_USER_AUDIO_BUFFER,
    PRESET_VOICE_BUFFER_GETTER=lambda: PRESET_VOICE_BUFFER,
    VOICE_CLOUD_LIMIT_STATE=VOICE_CLOUD_LIMIT_STATE,
    _HTTP=_HTTP,
    _build_kommz_generate_candidates=_build_kommz_generate_candidates,
    _build_kommz_synthesis_candidates=_build_kommz_synthesis_candidates,
    _get_hybrid_rts_preset=_get_hybrid_rts_preset,
    _get_voice_library=_get_voice_library,
    _gpt_style_to_xtts_ref_bytes=_gpt_style_to_xtts_ref_bytes,
    _hybrid_style_ref_cache=_hybrid_style_ref_cache,
    _is_hybrid_supported_target_lang=_is_hybrid_supported_target_lang,
    _is_trial_voice_mode_enabled=_is_trial_voice_mode_enabled,
    _is_turbo_mode_active=_is_turbo_mode_active,
    _last_xtts_activity_ts_SETTER=lambda value: globals().__setitem__("_last_xtts_activity_ts", value),
    _looks_like_cloud_trial_limit=_looks_like_cloud_trial_limit,
    _normalize_voice_library_entry=_normalize_voice_library_entry,
    _normalize_xtts_request_lang=_normalize_xtts_request_lang,
    _register_tts_fallback=_register_tts_fallback,
    _repair_display_text=_repair_display_text,
    _resolve_kommz_synthesis_base=_resolve_kommz_synthesis_base,
    _resolve_kommz_voice_endpoint=_resolve_kommz_voice_endpoint,
    _set_hybrid_fast_runtime=_set_hybrid_fast_runtime,
    _set_pipeline_runtime=_set_pipeline_runtime,
    _set_voice_active_id=_set_voice_active_id,
    _short_runtime_text=_short_runtime_text,
    _short_runtime_url=_short_runtime_url,
    _to_bool=_to_bool,
    _wav_duration_seconds=_wav_duration_seconds,
    add_subtitle=add_subtitle,
    has_voice_license=has_voice_license,
    os=os,
    prewarm_kommz_xtts=prewarm_kommz_xtts,
    requests=requests,
    resample_and_play=resample_and_play,
    save_settings=save_settings,
    threading=threading,
)
app.register_blueprint(_tts_blueprint)


_stt_blueprint = register_stt_module(
    AUDIO_CONFIG=AUDIO_CONFIG,
    COMMUNITY_EDITION=COMMUNITY_EDITION,
    DEEPGRAM_API_KEY=DEEPGRAM_API_KEY,
    LICENSE_MGR=LICENSE_MGR,
    LAST_USER_AUDIO_BUFFER_SETTER=lambda value: globals().__setitem__("LAST_USER_AUDIO_BUFFER", value),
    _is_turbo_mode_active=_is_turbo_mode_active,
    _push_quality_log=_push_quality_log,
    _record_latency=_record_latency,
    _reinforce_laugh_transcript=_reinforce_laugh_transcript,
    _set_module_runtime=_set_module_runtime,
    _set_pipeline_runtime=_set_pipeline_runtime,
    _transcribe_via_modal_whisper=_transcribe_via_modal_whisper,
    clean_gaming_text=clean_gaming_text,
    enqueue_user_pipeline=enqueue_user_pipeline,
    io=io,
    np=np,
    re=re,
    requests=requests,
    resolve_input_device_cfg=resolve_input_device_cfg,
    sd=sd,
    soundfile=soundfile,
    stealth_print=stealth_print,
    time=time,
    _ptt_chunks_GETTER=lambda: _ptt_chunks,
    _ptt_chunks_SETTER=lambda value: globals().__setitem__("_ptt_chunks", value),
    _ptt_last_start_ts_GETTER=lambda: _ptt_last_start_ts,
    _ptt_last_start_ts_SETTER=lambda value: globals().__setitem__("_ptt_last_start_ts", value),
    _ptt_last_stop_ts_GETTER=lambda: _ptt_last_stop_ts,
    _ptt_last_stop_ts_SETTER=lambda value: globals().__setitem__("_ptt_last_stop_ts", value),
    _ptt_lock_GETTER=lambda: _ptt_lock,
    _ptt_preroll_GETTER=lambda: _ptt_preroll,
    _ptt_rec_GETTER=lambda: _ptt_rec,
    _ptt_rec_SETTER=lambda value: globals().__setitem__("_ptt_rec", value),
    _ptt_stream_GETTER=lambda: _ptt_stream,
    _ptt_stream_SETTER=lambda value: globals().__setitem__("_ptt_stream", value),
    _ptt_stream_device_GETTER=lambda: _ptt_stream_device,
    _ptt_stream_device_SETTER=lambda value: globals().__setitem__("_ptt_stream_device", value),
)
app.register_blueprint(_stt_blueprint)
register_scenes_runtime(
    AUDIO_CONFIG=AUDIO_CONFIG,
    _get_scene_library=_get_scene_library,
    logger=logger,
)
app.register_blueprint(privacy_bp)
app.register_blueprint(license_bp)
app.register_blueprint(overlay_bp)
app.register_blueprint(listen_bp)
app.register_blueprint(remote_bp)
app.register_blueprint(guide_bp)
app.register_blueprint(scenes_bp)
app.register_blueprint(config_bp)
app.register_blueprint(ui_bp)
app.register_blueprint(audio_bp)
app.register_blueprint(cloud_bp)

# ==================== MAIN CORRIGÉ & COMPLET ====================
if __name__ == "__main__":
    # V5.2: Mode debug / trace via CLI
    import argparse as _argparse
    _ap = _argparse.ArgumentParser(description="Kommz Gamer V5.2 — Voice translation for gamers")
    _ap.add_argument("--debug", action="store_true", help="Mode debug: active logging DEBUG + prints detailles")
    _ap.add_argument("--trace", action="store_true", help="Mode trace: encore plus verbeux que --debug")
    _cli_args, _ = _ap.parse_known_args()

    if _cli_args.debug or _cli_args.trace:
        AUDIO_CONFIG["debug_mode"] = True
        if _cli_args.trace:
            AUDIO_CONFIG["trace_mode"] = True
        logging.getLogger().setLevel(logging.DEBUG)
        try:
            print(f"[Kommz Gamer] Mode {'TRACE' if _cli_args.trace else 'DEBUG'} actif")
        except: pass
    else:
        AUDIO_CONFIG["debug_mode"] = False
        AUDIO_CONFIG["trace_mode"] = False

    startup_log_path = get_startup_log_path()
    try:
        with open(startup_log_path, "w", encoding="utf-8") as fh:
            fh.write("")
    except Exception:
        pass
    startup_trace("main: process start")
    AUDIO_CONFIG["_startup_ts"] = time.time()  # V5.2: timestamp demarrage pour uptime
    try: 
        with open("log_discret.txt", "w", encoding="utf-8") as f: f.write("")
    except: pass

    if _redirect_to_stable_launcher_if_needed():
        startup_trace("main: redirected to stable launcher, exiting current process")
        time.sleep(0.3)
        os._exit(0)
    
    # 1. D'ABORD ON CHARGE LES RÉGLAGES SAUVEGARDÉS
    startup_trace("main: load_settings begin")
    load_settings()
    startup_trace("main: load_settings done")
    # Réhydrate immédiatement LICENSE_MGR / VOICE_LICENSE_MGR depuis la config
    # persistée pour que /status réponde "activé" dès le 1er poll JS.
    startup_trace("main: sync_license_mgr begin")
    try:
        sync_license_mgr_from_config()
        startup_trace("main: sync_license_mgr done")
    except Exception as _e:
        startup_trace(f"main: sync_license_mgr failed: {_e}")
    # V5.2: Vérification immédiate des mises à jour au lancement (avant le thread périodique)
    try:
        check_for_updates()
        startup_trace("main: initial update check done")
    except Exception:
        startup_trace("main: initial update check failed (non bloquant)")
    ensure_local_server_started()
    if wait_for_local_server(VTP_CORE_PORT, timeout_s=12.0):
        startup_trace("main: local server reachable after initial bootstrap")
        stealth_print(f"✅ Serveur local prêt sur http://127.0.0.1:{VTP_CORE_PORT}/")
    else:
        startup_trace("main: local server NOT reachable after initial bootstrap")
        stealth_print(f"⚠️ Serveur local lent à démarrer sur {VTP_CORE_PORT}, poursuite du lancement.")
    if _to_bool(AUDIO_CONFIG.get("voice_default_at_startup", True), True):
        active_vid = str(AUDIO_CONFIG.get("voice_active_id") or "").strip()
        if active_vid and not str(AUDIO_CONFIG.get("kommz_client_id") or "").strip():
            AUDIO_CONFIG["kommz_client_id"] = active_vid
    apply_esport_profile(force_log=False)
    if AUDIO_CONFIG.get("shadow_ai_active", False):
        warm_shadow_services_async("startup")

    # Ne jamais bloquer le démarrage sur la vérification réseau des licences.
    # (Render peut répondre lentement; on laisse l'UI s'ouvrir puis on met à jour en arrière-plan.)
    def _refresh_licenses_safe():
        try:
            if not CLOUD_FEATURES_ENABLED:
                if AUDIO_CONFIG.get("tts_engine") == "KOMMZ_VOICE":
                    AUDIO_CONFIG["tts_engine"] = "WINDOWS"
                    save_settings()
                return
            if COMMUNITY_EDITION:
                if AUDIO_CONFIG.get("tts_engine") == "KOMMZ_VOICE":
                    prewarm_kommz_xtts(force=False)
                return
            refresh_license_states_from_server()
            if AUDIO_CONFIG.get("tts_engine") == "KOMMZ_VOICE" and not has_voice_license():
                AUDIO_CONFIG["tts_engine"] = "WINDOWS"
                save_settings()
                stealth_print("Blocage securite: moteur Kommz desactive (licence Voice absente).")
            elif AUDIO_CONFIG.get("tts_engine") == "KOMMZ_VOICE" and has_voice_license():
                prewarm_kommz_xtts(force=False)
        except Exception as e:
            stealth_print(f"[WARN] Verification licence differee: {e}")

    threading.Thread(target=_refresh_licenses_safe, daemon=True).start()
    threading.Thread(target=_user_pipeline_worker_loop, daemon=True).start()
    
    # Force le logiciel en mode actif par défaut à chaque démarrage.
    app_state["is_active"] = True
    AUDIO_CONFIG["is_listening"] = True
    AUDIO_CONFIG["monitoring_enabled"] = True
    AUDIO_CONFIG["tts_active"] = True
    stealth_print(f"🔍 PRE-SAVE: mini_overlay_enabled={AUDIO_CONFIG.get('mini_overlay_enabled')}")
    save_settings()
    
    # 2. VÉRIFICATION INTELLIGENTE DU PÉRIPHÉRIQUE (SORTIE)
    try:
        saved_out = int(AUDIO_CONFIG.get("game_output_device", 0))
    except:
        saved_out = 0
        AUDIO_CONFIG["game_output_device"] = 0
    if saved_out == 0:
        stealth_print("🔍 Premier lancement ? Recherche auto CABLE Input...")
        found_cable = None
        try:
            for i, dev in enumerate(sd.query_devices()):
                if dev['max_output_channels'] > 0 and ("CABLE INPUT" in dev['name'].upper() or "VB-AUDIO" in dev['name'].upper()):
                    found_cable = i
                    break
            if found_cable is not None:
                AUDIO_CONFIG["game_output_device"] = found_cable
                stealth_print(f"✅ Câble trouvé et configuré sur ID {found_cable}")
                save_settings()
        except: pass
    else:
        stealth_print(f"✅ Chargement Sortie sauvegardée : ID {saved_out}")

    # 3. VÉRIFICATION DU MICRO (ne pas écraser la config utilisateur)
    in_id = resolve_input_device_cfg(AUDIO_CONFIG.get("game_input_device"))
    if in_id is None:
        in_id = resolve_input_device_cfg(sd.default.device[0])
    if in_id is None:
        select_microphone_at_startup()
        in_id = resolve_input_device_cfg(AUDIO_CONFIG.get("game_input_device"))
    if in_id is None:
        in_id = 0
    AUDIO_CONFIG["game_input_device_key"] = _normalize_device_signature(
        sd.query_devices()[int(in_id)].get("name", ""),
        str(sd.query_hostapis()[int(sd.query_devices()[int(in_id)].get("hostapi", -1))].get("name", "")) if int(sd.query_devices()[int(in_id)].get("hostapi", -1)) >= 0 else ""
    )
    AUDIO_CONFIG["game_input_device_runtime"] = _device_runtime_payload(in_id)

    stealth_print(f"✅ START: Micro {in_id} | Sortie Jeu {AUDIO_CONFIG.get('game_output_device')}")

    # 4. LANCEMENT DES THREADS
    try:
        # Serveur local déjà amorcé plus haut pour garantir l'ouverture de l'UI.
        
        # Moteur Espion Deepgram
        DG_ENGINE = DeepgramEngine() 
        if bool(AUDIO_CONFIG.get("is_listening", True)):
            threading.Thread(target=DG_ENGINE.start_streaming, args=(in_id,), daemon=True).start()

            # Kick de demarrage optionnel (desactive par defaut pour eviter les doubles sessions ecoute).
            if bool(AUDIO_CONFIG.get("listen_startup_kick_enabled", False)):
                def _kick_listen_startup():
                    try:
                        time.sleep(1.2)
                        if not bool(AUDIO_CONFIG.get("is_listening", True)):
                            return
                        try:
                            if "DG_ENGINE" in globals() and DG_ENGINE:
                                DG_ENGINE.is_running = False
                        except Exception as e:
                            stealth_print(f"⚠️ Kick écoute: arrêt logique DG_ENGINE impossible : {e}")
                        time.sleep(0.35)
                        globals()["DG_ENGINE"] = DeepgramEngine()
                        threading.Thread(target=globals()["DG_ENGINE"].start_streaming, args=(in_id,), daemon=True).start()
                    except Exception as e:
                        stealth_print(f"⚠️ Kick écoute startup échoué : {e}")

                threading.Thread(target=_kick_listen_startup, daemon=True).start()

        # Threads systèmes
        threading.Thread(target=overlay_loop, daemon=True).start()
        threading.Thread(target=audio_bypass_loop, daemon=True).start()
        threading.Thread(target=monitoring_loop, daemon=True).start()
        threading.Thread(target=listen_watchdog_loop, daemon=True).start()
        threading.Thread(target=hybrid_activation_loop, daemon=True).start()
        threading.Thread(target=scene_auto_apply_loop, daemon=True).start()
        threading.Thread(target=game_auto_detect_loop, daemon=True).start()
        threading.Thread(target=_preset_schedule_check_loop, daemon=True).start()
        threading.Thread(target=hotkey_loop, daemon=True).start()
        threading.Thread(target=update_check_loop, daemon=True).start()
        # V5.2 Bloc 4: Mini overlay desktop stats
        threading.Thread(target=mini_stats_overlay_loop, daemon=True).start()
        # V5.3: Préparer le HUD Qt sur le thread principal (AVANT webview.start)
        _create_hud_window_if_enabled()
        # V5.2 Bloc 6: Tray icon sante (vert/jaune/rouge)
        if AUDIO_CONFIG.get("tray_icon_enabled", True):
            threading.Thread(target=_tray_icon_loop, daemon=True).start()
    except Exception as e:
        stealth_print(f"❌ Startup Error: {e}")

    # 5. CONFIGURATION DES RACCOURCIS CLAVIER
    try:
        import keyboard
        try: keyboard.unhook_all()
        except: pass
        if AUDIO_CONFIG.get('hotkey_f2_enabled', True): keyboard.add_hotkey('f2', toggle_tts_action, suppress=False)
        if AUDIO_CONFIG.get('hotkey_f3_enabled', True): keyboard.add_hotkey('f3', toggle_monitoring_action, suppress=False)
        keyboard.add_hotkey('f4', toggle_bypass_action, suppress=False)     
        keyboard.add_hotkey('f8', panic_reset, suppress=False)              
        # V5.2: Raccourcis globaux toggle écoute + cycle presets
        keyboard.add_hotkey('ctrl+shift+l', toggle_ecoute_action, suppress=False)
        keyboard.add_hotkey('ctrl+shift+right', lambda: cycle_preset_action(1), suppress=False)
        keyboard.add_hotkey('ctrl+shift+left', lambda: cycle_preset_action(-1), suppress=False)
    except: pass

    # 6. UI (VERSION FINALE & NETTOYÉE)
    stealth_print("🖥️ GUI Lancement...")
    startup_trace("main: GUI launch phase")
    import webview
    import os
    import sys
    
    # Instance de la passerelle
    api_bridge = Bridge()
    
    # Gestion du chemin pour EXE ou Script (fallback robuste)
    candidate_paths = []
    if getattr(sys, 'frozen', False):
        meipass_dir = getattr(sys, "_MEIPASS", "")
        if meipass_dir:
            candidate_paths.append(os.path.join(meipass_dir, "web", "index.html"))
        candidate_paths.append(os.path.join(os.path.dirname(sys.executable), "web", "index.html"))
    candidate_paths.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "web", "index.html"))
    candidate_paths.append(os.path.join(os.getcwd(), "web", "index.html"))

    html_path = next((p for p in candidate_paths if p and os.path.exists(p)), None)

    # Vérification fichier manquant (sans blocage input invisible)
    if not html_path:
        err = (
            "ERREUR: web/index.html introuvable.\n\n"
            "Chemins testés:\n- " + "\n- ".join(candidate_paths)
        )
        try:
            stealth_print(err)
            logger.error(err)
        except Exception:
            pass
        try:
            ctypes.windll.user32.MessageBoxW(0, err, "Kommz Gamer - Erreur de lancement", 0x10)
        except Exception:
            pass
        sys.exit(1)

    stealth_print(f"✅ Interface : {html_path}")

    # Lancement Fenêtre via serveur local Flask (UTF-8 stable, mêmes routes API)
    _cache_bust = int(time.time())
    ui_url = f"http://127.0.0.1:{VTP_CORE_PORT}/?v={_cache_bust}"
    if wait_for_local_server(VTP_CORE_PORT, timeout_s=18.0):
        startup_trace(f"main: ui_url ready {ui_url}")
        stealth_print(f"✅ UI locale prête sur {ui_url}")
    else:
        startup_trace(f"main: ui_url NOT ready {ui_url}")
        stealth_print(f"⚠️ UI locale lente à répondre sur {ui_url}, ouverture quand même de la fenêtre.")
        try:
            msg = (
                "Le serveur local de Kommz Gamer n'a pas démarré correctement.\n\n"
                f"Consultez le journal :\n{startup_log_path}"
            )
            ctypes.windll.user32.MessageBoxW(0, msg, "Kommz Gamer - Démarrage serveur", 0x30)
        except Exception:
            pass
    window = webview.create_window(
        title="Kommz Gamer", 
        url=ui_url, 
        width=1200, 
        height=850, 
        background_color='#0b0f14', 
        resizable=True,
        js_api=api_bridge # Active le lien JS->Python
    )

    try:
        # Forcer explicitement le backend réduit les échecs silencieux en EXE.
        startup_trace("main: entering webview.start(edgechromium)")
        # V5.3: Force la transparence EdgeChromium (nécessaire pour HUD frameless)
        os.environ.setdefault(
            'WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS',
            '--disable-gpu-compositing --enable-transparent-visuals'
        )
        webview.start(debug=False, gui="edgechromium")
    except Exception as e:
        startup_trace(f"main: webview.start exception: {e}")
        startup_trace(traceback.format_exc())
        msg = f"Erreur pywebview: {e}"
        try:
            stealth_print(msg)
            logger.exception(msg)
        except Exception:
            pass
        # Fallback de secours: ouvrir l'UI dans le navigateur local
        # plutôt que quitter immédiatement sans fenêtre.
        try:
            webbrowser.open(ui_url)
            stealth_print("ℹ️ Fallback UI: ouverture navigateur local.")
            while True:
                time.sleep(1)
        except Exception:
            pass
        try:
            ctypes.windll.user32.MessageBoxW(0, msg, "Kommz Gamer - Erreur UI", 0x10)
        except Exception:
            pass
    sys.exit(0)
