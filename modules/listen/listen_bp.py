#!/usr/bin/env python3
"""
Kommz Gamer - Listen Blueprint Routes V5.2
Routes extraites de vtp_core.py pour modularisation
"""

from flask import Blueprint, jsonify, request
import sys
import time
import os
from datetime import datetime

# Import des dépendances nécessaires
try:
    from modules.config.config import (
        AUDIO_CONFIG, 
        EDITION_PROFILE, 
        _repair_payload_strings,
        _repair_display_text,
        save_settings,
    )
except ImportError:
    AUDIO_CONFIG = {}
    EDITION_PROFILE = "community"
    def _repair_payload_strings(obj):
        if isinstance(obj, dict):
            return {k: _repair_payload_strings(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [_repair_payload_strings(item) for item in obj]
        elif isinstance(obj, str):
            return obj.encode("utf-8", errors="ignore").decode("utf-8", errors="ignore")
        else:
            return obj
    def _repair_display_text(text):
        return str(text or "")

# Runtime state simulation pour les routes
LATENCY_RUNTIME_STATE = {
    "stt_ms": None,
    "translate_ms": None,
    "tts_ms": None,
    "total_ms": None,
    "updated_at": time.time(),
}

_listen_runtime = {
    "ally_text_events": 0,
    "ally_voice_played": 0,
    "ally_voice_skipped": 0,
    "ally_voice_rate_limited": 0,
    "ally_short_merged": 0,
    "last_event_at": time.time(),
    "listen_conn_state": "idle",
    "listen_conn_detail": "En attente audio",
    "watchdog_restarts": 0,
    "watchdog_flaps": 0,
    "watchdog_cooldown_hits": 0,
    "watchdog_idle_restarts": 0,
    "watchdog_stream_stale_restarts": 0,
    "watchdog_last_idle_age_s": 0.0,
    "watchdog_last_restart_reason": "",
    "last_audio_seen_at": 0.0,
}

_listen_focus_auto_state = {
    "mode_effective": "balanced",
    "noise_rms_ema": 0.0,
    "crest_ema": 0.0,
}

CURRENT_VERSION = "5.2"

# Version globale pour la compatibilité
last_expressive_preset_key = ""

# Création du blueprint
listen_bp = Blueprint('listen', __name__, url_prefix='/audio/listen')

# Fonctions utilitaires
def _build_listen_health_snapshot():
    """Construit un snapshot de la santé de l'écoute"""
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
        summary = "Système stable"
        
        if state not in {"connected", "waiting_audio", "paused"}:
            level = "warn"
            summary = f"Connexion {state} - vérifie le loopback"
        
        if flaps > 3 or cooldown_hits > 5 or idle_restarts > 3:
            level = "warn"
            summary = f"Instabilité détectée: restarts={flaps+idle_restarts}, cooldown={cooldown_hits}"
        
        if voice_played == 0 and stream_age > 60.0:
            level = "warn"
            summary = f"Aucune voix détectée depuis {int(stream_age)}s"
        
        return {
            "level": level,
            "summary": summary,
            "connection_state": state,
            "watchdog_restarts": flaps + idle_restarts,
            "voice_activity": voice_played + voice_skipped,
            "idle_age_s": idle_age,
            "stream_age_s": stream_age,
        }
    except Exception:
        return {"level": "err", "summary": "Erreur snapshot santé"}

def _build_pipeline_runtime_payload():
    """Construit le payload runtime du pipeline"""
    try:
        from modules.license import PIPELINE_RUNTIME_STATE
        return dict(PIPELINE_RUNTIME_STATE)
    except ImportError:
        return {"pipeline_state": "simulated", "updated_at": time.time()}

def _build_latency_runtime_payload():
    """Construit le payload runtime de latence"""
    try:
        payload = dict(LATENCY_RUNTIME_STATE)
    except:
        payload = {}
    
    payload["age_seconds"] = _runtime_age_seconds(payload.get("updated_at", 0.0))
    try:
        from modules.config.config import _normalize_quality_preset
        payload["quality_preset"] = _normalize_quality_preset(AUDIO_CONFIG.get("quality_preset", "balanced"))
    except:
        payload["quality_preset"] = "balanced"
    
    return payload

def _build_tts_fallback_runtime_payload():
    """Construit le payload runtime de fallback TTS"""
    try:
        from modules.license import TTS_FALLBACK_RUNTIME_STATE
        return dict(TTS_FALLBACK_RUNTIME_STATE)
    except ImportError:
        return {"fallback_state": "simulated", "updated_at": time.time()}

def _build_quality_log_payload():
    """Construit le payload des logs de qualité"""
    try:
        from modules.license import _build_quality_log_payload
        return _build_quality_log_payload()
    except ImportError:
        return []

def get_cloud_endpoints_diag(force=False, cache_ttl=25):
    """Diagnostic des endpoints cloud"""
    return {
        "summary": "Diagnostic cloud simulé",
        "level": "ok",
        "endpoints": {
            "supabase": {"status": "ok", "latency_ms": 45},
            "deepgram": {"status": "ok", "latency_ms": 120},
            "gpt": {"status": "ok", "latency_ms": 800},
        }
    }

def _runtime_age_seconds(updated_at):
    """Calcule l'âge en secondes du runtime state"""
    try:
        now = time.time()
        ts = float(updated_at)
        return max(0.0, now - ts)
    except Exception:
        return 0.0

def _normalize_quality_preset(preset):
    """Normalise un preset qualité"""
    value = str(preset or "balanced").strip().lower()
    if value not in {"fast", "balanced", "ultra", "debug"}:
        return "balanced"
    return value


# ── Routes extraites de vtp_core.py ─────────────────────────────────────

@listen_bp.route("/benchmark", methods=["GET"])
def benchmark_listen_preset():
    """Mesure live: STT/TTS latency, CPU%, RAM, preset actif, watchdog."""
    try:
        import psutil
        import os as _os
        proc = psutil.Process(_os.getpid())
        cpu_pct = round(proc.cpu_percent(interval=0.15), 1)
        mem_info = proc.memory_info()
        ram_mb = round(mem_info.rss / (1024 * 1024), 1)

        latency = dict(LATENCY_RUNTIME_STATE)
        latency["age_seconds"] = round(time.time() - float(latency.get("updated_at", 0.0) or 0.0), 1)

        game_preset = str(AUDIO_CONFIG.get("ally_game_preset", "custom") or "custom")
        quality = _normalize_quality_preset(AUDIO_CONFIG.get("quality_preset", "balanced"))
        voice_focus = str(AUDIO_CONFIG.get("ally_voice_focus_mode", "balanced") or "balanced")
        voice_focus_eff = str(_listen_focus_auto_state.get("mode_effective", "balanced") or "balanced")
        expressive = str(last_expressive_preset_key or "libre")
        uptime_s = int(time.time() - float(AUDIO_CONFIG.get("_startup_ts", time.time()) or time.time()))

        health = _build_listen_health_snapshot()
        wd_restarts = int(_listen_runtime.get("watchdog_restarts", 0) or 0)
        voice_played = int(_listen_runtime.get("ally_voice_played", 0) or 0)

        return jsonify({
            "ok": True,
            "generated_at": _listen_now_utc_iso(),
            "preset": game_preset,
            "quality": quality,
            "voice_focus": voice_focus,
            "voice_focus_effective": voice_focus_eff,
            "expressive": expressive,
            "uptime_seconds": uptime_s,
            "system": {
                "cpu_percent": cpu_pct,
                "ram_mb": ram_mb,
                "python_v": sys.version.split()[0] if hasattr(sys, "version") else "?",
            },
            "latency": latency,
            "watchdog": {
                "restarts": wd_restarts,
                "health": health.get("level", "ok"),
                "summary": health.get("summary", ""),
            },
            "activity": {
                "voice_played": voice_played,
                "text_events": int(_listen_runtime.get("ally_text_events", 0) or 0),
            },
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@listen_bp.route("/session_report/export", methods=["GET"])
def export_listen_session_report():
    try:
        listen_health = _build_listen_health_snapshot()
        report = {
            "report_type": "kommz_v5_listen_session",
            "generated_at": _listen_now_utc_iso(),
            "version": str(CURRENT_VERSION or "5.2"),
            "edition_profile": str(EDITION_PROFILE or "unknown"),
            "cloud_features_enabled": False,  # Simulé pour le moment
            "listen_profile": str(AUDIO_CONFIG.get("ally_listen_profile", "default") or "default"),
            "listen_game_preset": str(AUDIO_CONFIG.get("ally_game_preset", "custom") or "custom"),
            "quality_preset": _normalize_quality_preset(AUDIO_CONFIG.get("quality_preset", "balanced")),
            "voice_focus_mode": str(AUDIO_CONFIG.get("ally_voice_focus_mode", "balanced") or "balanced"),
            "listen_health": listen_health,
            "listen_runtime": {
                "ally_text_events": int(_listen_runtime.get("ally_text_events", 0) or 0),
                "ally_voice_played": int(_listen_runtime.get("ally_voice_played", 0) or 0),
                "ally_voice_skipped": int(_listen_runtime.get("ally_voice_skipped", 0) or 0),
                "ally_voice_rate_limited": int(_listen_runtime.get("ally_voice_rate_limited", 0) or 0),
                "ally_short_merged": int(_listen_runtime.get("ally_short_merged", 0) or 0),
                "listen_conn_state": str(_listen_runtime.get("listen_conn_state", "idle") or "idle"),
                "listen_conn_detail": str(_listen_runtime.get("listen_conn_detail", "") or ""),
                "watchdog_restarts": int(_listen_runtime.get("watchdog_restarts", 0) or 0),
                "watchdog_flaps": int(_listen_runtime.get("watchdog_flaps", 0) or 0),
                "watchdog_cooldown_hits": int(_listen_runtime.get("watchdog_cooldown_hits", 0) or 0),
                "watchdog_idle_restarts": int(_listen_runtime.get("watchdog_idle_restarts", 0) or 0),
                "watchdog_stream_stale_restarts": int(_listen_runtime.get("watchdog_stream_stale_restarts", 0) or 0),
                "watchdog_last_idle_age_s": float(_listen_runtime.get("watchdog_last_idle_age_s", 0.0) or 0.0),
                "watchdog_last_restart_reason": str(_listen_runtime.get("watchdog_last_restart_reason", "") or ""),
                "last_event_at": float(_listen_runtime.get("last_event_at", 0.0) or 0.0),
            },
            "pipeline_runtime": _build_pipeline_runtime_payload(),
            "latency_runtime": _build_latency_runtime_payload(),
            "tts_fallback_runtime": _build_tts_fallback_runtime_payload(),
            "cloud_endpoints_diag": get_cloud_endpoints_diag(force=True, cache_ttl=0),
            "quality_log": _build_quality_log_payload()[:20],
        }
        repaired = _repair_payload_strings(report)

        # V5.2: Export CSV si demandé
        export_format = str(request.args.get("format", "json")).strip().lower()
        if export_format == "csv":
            import csv, io
            output = io.StringIO()
            writer = csv.writer(output, delimiter=";", quoting=csv.QUOTE_MINIMAL)
            writer.writerow(["Champ", "Valeur"])
            # Aplatir le rapport en lignes clé/valeur
            def _flatten(prefix, obj):
                rows = []
                if isinstance(obj, dict):
                    for k, v in obj.items():
                        rows.extend(_flatten(f"{prefix}.{k}" if prefix else k, v))
                elif isinstance(obj, list):
                    for i, v in enumerate(obj):
                        rows.extend(_flatten(f"{prefix}[{i}]", v))
                else:
                    rows.append([prefix, str(obj)])
                return rows
            for row in _flatten("", repaired):
                writer.writerow(row)
            csv_text = output.getvalue()
            return csv_text, 200, {"Content-Type": "text/csv; charset=utf-8", "Content-Disposition": "attachment; filename=kommz_session_report.csv"}

        return jsonify({"ok": True, "report": repaired})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@listen_bp.route("/quickcheck", methods=["GET"])
def listen_quickcheck_v5():
    try:
        listen_health = _build_listen_health_snapshot()
        conn_state = str(_listen_runtime.get("listen_conn_state", "idle") or "idle").strip().lower()
        wd_flaps = int(_listen_runtime.get("watchdog_flaps", 0) or 0)
        wd_cooldowns = int(_listen_runtime.get("watchdog_cooldown_hits", 0) or 0)
        wd_idle = int(_listen_runtime.get("watchdog_idle_restarts", 0) or 0)
        wd_stale = int(_listen_runtime.get("watchdog_stream_stale_restarts", 0) or 0)
        voice_played = int(_listen_runtime.get("ally_voice_played", 0) or 0)
        voice_skipped = int(_listen_runtime.get("ally_voice_skipped", 0) or 0)
        rate_limited = int(_listen_runtime.get("ally_voice_rate_limited", 0) or 0)

        checks = []

        is_listening = bool(AUDIO_CONFIG.get("is_listening", True))
        checks.append({
            "id": "listen_enabled",
            "label": "Mode écoute activé",
            "status": "ok" if is_listening else "warn",
            "detail": "Actif" if is_listening else "Désactivé",
        })

        conn_ok = conn_state in {"connected", "waiting_audio", "paused"}
        checks.append({
            "id": "listen_conn_state",
            "label": "État connexion écoute",
            "status": "ok" if conn_ok else "warn",
            "detail": conn_state or "unknown",
        })

        health_level = str(listen_health.get("level", "info") or "info").strip().lower()
        checks.append({
            "id": "listen_health",
            "label": "Santé écoute",
            "status": "ok" if health_level == "ok" else ("warn" if health_level in {"warn", "info"} else "err"),
            "detail": str(listen_health.get("summary", "") or ""),
        })

        watchdog_ok = (wd_flaps <= 2 and wd_cooldowns <= 3 and wd_idle <= 3 and wd_stale <= 3)
        checks.append({
            "id": "watchdog_stability",
            "label": "Stabilité watchdog",
            "status": "ok" if watchdog_ok else "warn",
            "detail": f"flaps={wd_flaps}, cooldown={wd_cooldowns}, idle={wd_idle}, stale={wd_stale}",
        })

        audio_activity_ok = (voice_played + voice_skipped) > 0
        checks.append({
            "id": "voice_activity",
            "label": "Activité voix alliés",
            "status": "ok" if audio_activity_ok else "warn",
            "detail": f"played={voice_played}, skipped={voice_skipped}, rate_limited={rate_limited}",
        })

        cloud_diag = get_cloud_endpoints_diag(force=False, cache_ttl=20)
        cloud_summary = str(cloud_diag.get("summary", "Diagnostic cloud indisponible") or "Diagnostic cloud indisponible")
        cloud_ok = str(cloud_diag.get("level", "warn") or "warn").strip().lower() in {"ok", "info"}
        checks.append({
            "id": "cloud_diag",
            "label": "Diagnostic cloud",
            "status": "ok" if cloud_ok else "warn",
            "detail": cloud_summary,
        })

        score_ok = len([c for c in checks if c.get("status") == "ok"])
        score_total = len(checks)
        global_status = "ok" if all(c.get("status") == "ok" for c in checks) else "warn"
        if any(c.get("status") == "err" for c in checks):
            global_status = "err"

        return jsonify({
            "ok": True,
            "status": global_status,
            "score_ok": score_ok,
            "score_total": score_total,
            "summary": f"Quick Check V5: {score_ok}/{score_total}",
            "checks": checks,
            "listen_profile": str(AUDIO_CONFIG.get("ally_listen_profile", "default") or "default"),
            "listen_game_preset": str(AUDIO_CONFIG.get("ally_game_preset", "custom") or "custom"),
            "quality_preset": _normalize_quality_preset(AUDIO_CONFIG.get("quality_preset", "balanced")),
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@listen_bp.route("/debug_bundle", methods=["GET"])
def listen_debug_bundle_v51():
    try:
        quick_resp = listen_quickcheck_v5()
        quick_payload = {}
        if hasattr(quick_resp, "get_json"):
            quick_payload = quick_resp.get_json(silent=True) or {}

        listen_health = _build_listen_health_snapshot()
        bundle = {
            "bundle_type": "kommz_v5.2_debug_bundle",
            "generated_at": _listen_now_utc_iso(),
            "version": str(CURRENT_VERSION or "5.2"),
            "edition_profile": str(EDITION_PROFILE or "unknown"),
            "cloud_features_enabled": False,  # Simulé
            "quickcheck": quick_payload if isinstance(quick_payload, dict) else {},
            "listen_health": listen_health,
            "listen_config": {
                "listen_profile": str(AUDIO_CONFIG.get("ally_listen_profile", "default") or "default"),
                "listen_game_preset": str(AUDIO_CONFIG.get("ally_game_preset", "custom") or "custom"),
                "voice_focus_mode": str(AUDIO_CONFIG.get("ally_voice_focus_mode", "balanced") or "balanced"),
                "voice_focus_effective": str(_listen_focus_auto_state.get("mode_effective", "balanced") or "balanced"),
                "quality_preset": _normalize_quality_preset(AUDIO_CONFIG.get("quality_preset", "balanced")),
                "watchdog_idle_threshold_s": int(AUDIO_CONFIG.get("listen_watchdog_idle_threshold_s", 75) or 75),
                "watchdog_stream_stale_s": int(AUDIO_CONFIG.get("listen_watchdog_stream_stale_s", 22) or 22),
            },
            "listen_runtime": {
                "ally_text_events": int(_listen_runtime.get("ally_text_events", 0) or 0),
                "ally_voice_played": int(_listen_runtime.get("ally_voice_played", 0) or 0),
                "ally_voice_skipped": int(_listen_runtime.get("ally_voice_skipped", 0) or 0),
                "ally_voice_rate_limited": int(_listen_runtime.get("ally_voice_rate_limited", 0) or 0),
                "ally_short_merged": int(_listen_runtime.get("ally_short_merged", 0) or 0),
                "listen_conn_state": str(_listen_runtime.get("listen_conn_state", "idle") or "idle"),
                "listen_conn_detail": str(_listen_runtime.get("listen_conn_detail", "") or ""),
                "watchdog_restarts": int(_listen_runtime.get("watchdog_restarts", 0) or 0),
                "watchdog_flaps": int(_listen_runtime.get("watchdog_flaps", 0) or 0),
                "watchdog_cooldown_hits": int(_listen_runtime.get("watchdog_cooldown_hits", 0) or 0),
                "watchdog_idle_restarts": int(_listen_runtime.get("watchdog_idle_restarts", 0) or 0),
                "watchdog_stream_stale_restarts": int(_listen_runtime.get("watchdog_stream_stale_restarts", 0) or 0),
                "watchdog_last_idle_age_s": float(_listen_runtime.get("watchdog_last_idle_age_s", 0.0) or 0.0),
                "watchdog_last_restart_reason": str(_listen_runtime.get("watchdog_last_restart_reason", "") or ""),
                "last_event_at": float(_listen_runtime.get("last_event_at", 0.0) or 0.0),
            },
            "cloud_endpoints_diag": get_cloud_endpoints_diag(force=False, cache_ttl=15),
            "tts_fallback_runtime": _build_tts_fallback_runtime_payload(),
            "latency_runtime": _build_latency_runtime_payload(),
            "quality_log_tail": _build_quality_log_payload()[:15],
        }
        return jsonify({"ok": True, "bundle": _repair_payload_strings(bundle)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@listen_bp.route("/toggle", methods=["POST"])
def alt():
    """
    Active/desactive le mode ecoute (traduction allies/loopback).
    Important: quand on reactive, il faut relancer le thread Deepgram, sinon
    l'ancien stream reste arrete (et l'utilisateur doit changer de langue pour le relancer).
    """
    try:
        from vtp_core import DG_ENGINE, DeepgramEngine, _push_toast, stealth_print, save_settings
        import threading

        payload = request.get_json(silent=True) or {}
        requested = payload.get("toggle", None) if isinstance(payload, dict) else None

        curr = bool(AUDIO_CONFIG.get("is_listening", True))
        if requested is None:
            enabled = not curr
        else:
            enabled = bool(requested)

        AUDIO_CONFIG["is_listening"] = enabled
        save_settings()

        # Start/stop the listen engine deterministically.
        dg_engine = DG_ENGINE
        if enabled:
            try:
                if dg_engine:
                    dg_engine.is_running = False
            except Exception:
                pass
            dg_engine = DeepgramEngine()
            listen_dev_id = AUDIO_CONFIG.get("game_input_device", 0)
            try:
                listen_dev_id = int(listen_dev_id)
            except Exception:
                listen_dev_id = 0
            threading.Thread(target=dg_engine.start_streaming, args=(listen_dev_id,), daemon=True).start()
            _push_toast("🎤 Écoute activée")
        else:
            try:
                if dg_engine:
                    dg_engine.is_running = False
            except Exception:
                pass
            _push_toast("🔇 Écoute désactivée")

        return jsonify({"ok": True, "is_listening": enabled})
    except Exception as e:
        from vtp_core import stealth_print
        stealth_print(f"❌ Erreur toggle ecoute: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


@listen_bp.route("/profile/competitive", methods=["POST"])
def apply_competitive_listen_profile():
    """
    Preset écoute orienté jeu vocal (Discord / ingame):
    - meilleure accroche des phrases courtes
    - moins de blocage audio sur répétitions proches
    - mode multi-langue robuste
    """
    try:
        from vtp_core import _is_competitive_listen_locked, _listen_lock_block_response, _apply_quality_preset, _maybe_enable_competitive_lock_auto, stealth_print, save_settings
        if _is_competitive_listen_locked():
            return _listen_lock_block_response()
        AUDIO_CONFIG["is_listening"] = True
        AUDIO_CONFIG["ally_recognition_lang"] = "multi"
        AUDIO_CONFIG["ally_block_french"] = False
        AUDIO_CONFIG["ally_sentence_punct_min_words"] = 2
        AUDIO_CONFIG["ally_sentence_hard_flush_words"] = 6
        AUDIO_CONFIG["ally_tts_similarity_play_below"] = 0.93
        AUDIO_CONFIG["ally_tts_duplicate_window_s"] = 1.6
        AUDIO_CONFIG["ally_tts_force_on_speech_final"] = True
        AUDIO_CONFIG["ally_tts_force_min_chars"] = 8
        AUDIO_CONFIG["ally_tts_min_gap_s"] = 0.55
        AUDIO_CONFIG["ally_tts_short_merge_words"] = 3
        AUDIO_CONFIG["ally_tts_short_merge_chars"] = 18
        AUDIO_CONFIG["ally_tts_short_merge_window_s"] = 1.20
        AUDIO_CONFIG["ally_tts_rate_limit_window_s"] = 9.0
        AUDIO_CONFIG["ally_tts_rate_limit_max_plays"] = 5
        AUDIO_CONFIG["ally_voice_focus_mode"] = "aggressive"
        AUDIO_CONFIG["ally_autotune_enabled"] = True
        AUDIO_CONFIG["ally_listen_profile"] = "competitive"
        AUDIO_CONFIG["ally_game_preset"] = "custom"
        _maybe_enable_competitive_lock_auto()
        AUDIO_CONFIG["vad_threshold"] = 0.018
        AUDIO_CONFIG["quality_preset"] = "balanced"
        _apply_quality_preset("balanced", emit_log=False)
        save_settings()
        stealth_print("🎮 Profil écoute compétitif appliqué (multi, flush court, dedupe assoupli).")
        return jsonify({
            "ok": True,
            "profile": "competitive",
            "is_listening": True,
            "ally_recognition_lang": AUDIO_CONFIG["ally_recognition_lang"],
            "ally_block_french": AUDIO_CONFIG["ally_block_french"],
            "ally_sentence_punct_min_words": AUDIO_CONFIG["ally_sentence_punct_min_words"],
            "ally_sentence_hard_flush_words": AUDIO_CONFIG["ally_sentence_hard_flush_words"],
            "ally_tts_similarity_play_below": AUDIO_CONFIG["ally_tts_similarity_play_below"],
            "ally_tts_duplicate_window_s": AUDIO_CONFIG["ally_tts_duplicate_window_s"],
            "ally_tts_force_on_speech_final": AUDIO_CONFIG["ally_tts_force_on_speech_final"],
            "ally_tts_force_min_chars": AUDIO_CONFIG["ally_tts_force_min_chars"],
            "ally_tts_min_gap_s": AUDIO_CONFIG["ally_tts_min_gap_s"],
            "ally_tts_short_merge_words": AUDIO_CONFIG["ally_tts_short_merge_words"],
            "ally_tts_short_merge_chars": AUDIO_CONFIG["ally_tts_short_merge_chars"],
            "ally_tts_short_merge_window_s": AUDIO_CONFIG["ally_tts_short_merge_window_s"],
            "ally_tts_rate_limit_window_s": AUDIO_CONFIG["ally_tts_rate_limit_window_s"],
            "ally_tts_rate_limit_max_plays": AUDIO_CONFIG["ally_tts_rate_limit_max_plays"],
            "ally_voice_focus_mode": AUDIO_CONFIG["ally_voice_focus_mode"],
            "ally_autotune_enabled": AUDIO_CONFIG["ally_autotune_enabled"],
            "vad_threshold": AUDIO_CONFIG["vad_threshold"],
            "quality_preset": AUDIO_CONFIG["quality_preset"],
            "ally_listen_profile": AUDIO_CONFIG["ally_listen_profile"],
            "ally_competitive_lock": bool(AUDIO_CONFIG.get("ally_competitive_lock", False)),
        })
    except Exception as e:
        from vtp_core import stealth_print
        stealth_print(f"❌ Erreur preset écoute compétitif: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


@listen_bp.route("/preset/apply", methods=["POST"])
def apply_listen_game_preset():
    try:
        from vtp_core import _is_competitive_listen_locked, _listen_lock_block_response, _apply_listen_game_preset, _push_toast, stealth_print, save_settings
        if _is_competitive_listen_locked():
            return _listen_lock_block_response()
        data = request.get_json(silent=True) or {}
        key = str(data.get("preset", "") or "").strip().lower()
        ok, info = _apply_listen_game_preset(key)
        if not ok:
            return jsonify({"ok": False, "error": info}), 400
        stealth_print(f"🎮 Preset jeu écoute appliqué: {info} ({key})")
        _push_toast(f"🎮 Preset jeu: {info}")
        return jsonify({
            "ok": True,
            "preset": key,
            "label": info,
            "ally_game_preset": AUDIO_CONFIG.get("ally_game_preset", "custom"),
            "ally_voice_focus_mode": AUDIO_CONFIG.get("ally_voice_focus_mode", "balanced"),
        })
    except Exception as e:
        from vtp_core import stealth_print
        stealth_print(f"❌ Erreur preset jeu écoute: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


# === PRESET MANAGEMENT (depuis vtp_core.py) ===

@listen_bp.route("/preset/import", methods=["POST"])
def import_listen_custom_preset():
    """Importe un preset de écoute depuis JSON"""
    try:
        from vtp_core import _is_competitive_listen_locked, _listen_lock_block_response, save_settings, LISTEN_PRESET_EXPORT_KEYS, _sanitize_listen_config_guards, stealth_print
        if _is_competitive_listen_locked():
            return _listen_lock_block_response()
        data = request.get_json(silent=True) or {}
        if not isinstance(data, dict):
            return jsonify({"ok": False, "error": "payload JSON invalide"}), 400
        preset = data.get("preset") if isinstance(data.get("preset"), dict) else data
        cfg = preset.get("config") if isinstance(preset.get("config"), dict) else {}
        if not cfg:
            return jsonify({"ok": False, "error": "config manquante"}), 400
        for k in LISTEN_PRESET_EXPORT_KEYS:
            if k in cfg:
                AUDIO_CONFIG[k] = cfg[k]
        _sanitize_listen_config_guards()
        save_settings()
        stealth_print(f"📥 Preset écoute importé: {AUDIO_CONFIG.get('ally_game_preset', 'custom')}")
        return jsonify({
            "ok": True,
            "ally_game_preset": AUDIO_CONFIG.get("ally_game_preset", "custom"),
            "ally_voice_focus_mode": AUDIO_CONFIG.get("ally_voice_focus_mode", "balanced"),
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@listen_bp.route("/preset/library/save", methods=["POST"])
def save_listen_preset_library_entry():
    """Sauvegarde un preset dans la bibliothèque locale"""
    try:
        from vtp_core import _is_competitive_listen_locked, _listen_lock_block_response, save_settings, _sanitize_listen_preset_name, _capture_listen_preset_config, _get_listen_preset_library, LISTEN_PRESET_LIBRARY_MAX, _listen_now_utc_iso, stealth_print
        if _is_competitive_listen_locked():
            return _listen_lock_block_response()
        data = request.get_json(silent=True) or {}
        name = _sanitize_listen_preset_name(data.get("name") if isinstance(data, dict) else "")
        if not name:
            return jsonify({"ok": False, "error": "Nom preset requis"}), 400
        entry = {
            "name": name,
            "config": _capture_listen_preset_config(),
            "updated_at": _listen_now_utc_iso(),
        }
        lib = _get_listen_preset_library()
        key = name.lower()
        replaced = False
        for i, it in enumerate(lib):
            if str(it.get("name") or "").strip().lower() == key:
                lib[i] = entry
                replaced = True
                break
        if not replaced:
            lib.insert(0, entry)
        AUDIO_CONFIG["ally_preset_library"] = lib[:LISTEN_PRESET_LIBRARY_MAX]
        save_settings()
        stealth_print(f"💾 Preset écoute sauvegardé: {name}")
        return jsonify({
            "ok": True,
            "saved": name,
            "replaced": replaced,
            "presets": [str(it.get("name") or "") for it in AUDIO_CONFIG["ally_preset_library"]],
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@listen_bp.route("/preset/library/load", methods=["POST"])
def load_listen_preset_library_entry():
    """Charge un preset depuis la bibliothèque locale"""
    try:
        from vtp_core import _is_competitive_listen_locked, _listen_lock_block_response, save_settings, _sanitize_listen_preset_name, _get_listen_preset_library, LISTEN_PRESET_EXPORT_KEYS, _sanitize_listen_config_guards, stealth_print
        if _is_competitive_listen_locked():
            return _listen_lock_block_response()
        data = request.get_json(silent=True) or {}
        name = _sanitize_listen_preset_name(data.get("name") if isinstance(data, dict) else "")
        if not name:
            return jsonify({"ok": False, "error": "Nom preset requis"}), 400
        key = name.lower()
        lib = _get_listen_preset_library()
        item = next((it for it in lib if str(it.get("name") or "").strip().lower() == key), None)
        if not item:
            return jsonify({"ok": False, "error": "Preset introuvable"}), 404
        cfg = item.get("config") if isinstance(item.get("config"), dict) else {}
        for k in LISTEN_PRESET_EXPORT_KEYS:
            if k in cfg:
                AUDIO_CONFIG[k] = cfg[k]
        _sanitize_listen_config_guards()
        save_settings()
        stealth_print(f"📂 Preset écoute chargé: {name}")
        return jsonify({
            "ok": True,
            "loaded": name,
            "ally_game_preset": AUDIO_CONFIG.get("ally_game_preset", "custom"),
            "ally_voice_focus_mode": AUDIO_CONFIG.get("ally_voice_focus_mode", "balanced"),
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@listen_bp.route("/preset/library/delete", methods=["POST"])
def delete_listen_preset_library_entry():
    """Supprime un preset de la bibliothèque locale"""
    try:
        from vtp_core import _is_competitive_listen_locked, _listen_lock_block_response, save_settings, _sanitize_listen_preset_name, _get_listen_preset_library, stealth_print
        if _is_competitive_listen_locked():
            return _listen_lock_block_response()
        data = request.get_json(silent=True) or {}
        name = _sanitize_listen_preset_name(data.get("name") if isinstance(data, dict) else "")
        if not name:
            return jsonify({"ok": False, "error": "Nom preset requis"}), 400
        key = name.lower()
        lib = _get_listen_preset_library()
        new_lib = [it for it in lib if str(it.get("name") or "").strip().lower() != key]
        if len(new_lib) == len(lib):
            return jsonify({"ok": False, "error": "Preset introuvable"}), 404
        AUDIO_CONFIG["ally_preset_library"] = new_lib
        save_settings()
        stealth_print(f"🗑️ Preset écoute supprimé: {name}")
        return jsonify({
            "ok": True,
            "deleted": name,
            "presets": [str(it.get("name") or "") for it in new_lib],
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@listen_bp.route("/preset/library/rename", methods=["POST"])
def rename_listen_preset_library_entry():
    """Renomme un preset dans la bibliothèque locale"""
    try:
        from vtp_core import _is_competitive_listen_locked, _listen_lock_block_response, save_settings, _sanitize_listen_preset_name, _get_listen_preset_library, LISTEN_PRESET_LIBRARY_MAX, _listen_now_utc_iso, stealth_print
        if _is_competitive_listen_locked():
            return _listen_lock_block_response()
        data = request.get_json(silent=True) or {}
        old_name = _sanitize_listen_preset_name(data.get("old_name") if isinstance(data, dict) else "")
        new_name = _sanitize_listen_preset_name(data.get("new_name") if isinstance(data, dict) else "")
        if not old_name or not new_name:
            return jsonify({"ok": False, "error": "Ancien et nouveau nom requis"}), 400
        old_key = old_name.lower()
        new_key = new_name.lower()
        lib = _get_listen_preset_library()
        idx_old = -1
        idx_new = -1
        for i, it in enumerate(lib):
            k = str(it.get("name") or "").strip().lower()
            if k == old_key:
                idx_old = i
            if k == new_key:
                idx_new = i
        if idx_old < 0:
            return jsonify({"ok": False, "error": "Preset source introuvable"}), 404
        if idx_new >= 0 and idx_new != idx_old:
            return jsonify({"ok": False, "error": "Un preset avec ce nom existe déjà"}), 409
        lib[idx_old]["name"] = new_name
        lib[idx_old]["updated_at"] = _listen_now_utc_iso()
        AUDIO_CONFIG["ally_preset_library"] = lib[:LISTEN_PRESET_LIBRARY_MAX]
        save_settings()
        stealth_print(f"✏️ Preset écoute renommé: {old_name} -> {new_name}")
        return jsonify({
            "ok": True,
            "old_name": old_name,
            "new_name": new_name,
            "presets": [str(it.get("name") or "") for it in AUDIO_CONFIG["ally_preset_library"]],
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@listen_bp.route("/preset/library/import", methods=["POST"])
def import_listen_preset_library_entry():
    """Importe un preset nommé dans la bibliothèque"""
    try:
        from vtp_core import _is_competitive_listen_locked, _listen_lock_block_response, save_settings, _sanitize_listen_preset_name, _get_listen_preset_library, LISTEN_PRESET_LIBRARY_MAX, _normalize_listen_preset_entry, _listen_now_utc_iso, stealth_print
        if _is_competitive_listen_locked():
            return _listen_lock_block_response()
        data = request.get_json(silent=True) or {}
        if not isinstance(data, dict):
            return jsonify({"ok": False, "error": "Payload JSON invalide"}), 400
        preset = data.get("preset") if isinstance(data.get("preset"), dict) else data
        name = _sanitize_listen_preset_name(preset.get("name") if isinstance(preset, dict) else "")
        cfg = preset.get("config") if isinstance(preset, dict) and isinstance(preset.get("config"), dict) else {}
        if not name or not cfg:
            return jsonify({"ok": False, "error": "Preset invalide (name/config)"}), 400
        entry = _normalize_listen_preset_entry({
            "name": name,
            "config": cfg,
            "updated_at": _listen_now_utc_iso(),
        })
        lib = _get_listen_preset_library()
        key = name.lower()
        replaced = False
        for i, it in enumerate(lib):
            if str(it.get("name") or "").strip().lower() == key:
                lib[i] = entry
                replaced = True
                break
        if not replaced:
            lib.insert(0, entry)
        AUDIO_CONFIG["ally_preset_library"] = lib[:LISTEN_PRESET_LIBRARY_MAX]
        save_settings()
        stealth_print(f"📥 Preset nommé importé: {name}")
        return jsonify({
            "ok": True,
            "imported": name,
            "replaced": replaced,
            "presets": [str(it.get("name") or "") for it in AUDIO_CONFIG["ally_preset_library"]],
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@listen_bp.route("/preset/store/download", methods=["POST"])
def download_community_preset():
    """Télécharge et applique un preset communautaire"""
    try:
        from vtp_core import _is_competitive_listen_locked, _listen_lock_block_response, save_settings, COMMUNITY_PRESET_STORE, LISTEN_PRESET_EXPORT_KEYS, _sanitize_listen_config_guards, _push_toast, stealth_print
        if _is_competitive_listen_locked():
            return _listen_lock_block_response()
        data = request.get_json(silent=True) or {}
        preset_id = str(data.get("id", "") or "").strip()
        found = None
        for p in COMMUNITY_PRESET_STORE:
            if p.get("id") == preset_id:
                found = p
                break
        if not found:
            return jsonify({"ok": False, "error": "Preset communautaire introuvable"}), 404
        cfg = found.get("config") or {}
        for k in LISTEN_PRESET_EXPORT_KEYS:
            if k in cfg:
                AUDIO_CONFIG[k] = cfg[k]
        _sanitize_listen_config_guards()
        save_settings()
        AUDIO_CONFIG.setdefault("ally_community_preset_ratings", {})
        ratings = AUDIO_CONFIG.get("ally_community_preset_ratings", {})
        if isinstance(ratings, str):
            import json as _json
            ratings = _json.loads(ratings)
        found_id = found.get("id", "")
        my_rating = ratings.get(found_id, 0)
        stealth_print(f"🏪 Preset communautaire téléchargé: {found.get('name', found_id)}")
        _push_toast(f"🏪 Preset appliqué: {found.get('name', found_id)}")
        return jsonify({
            "ok": True,
            "preset": found_id,
            "name": found.get("name", ""),
            "ally_game_preset": AUDIO_CONFIG.get("ally_game_preset", "custom"),
            "ally_voice_focus_mode": AUDIO_CONFIG.get("ally_voice_focus_mode", "balanced"),
            "my_rating": my_rating,
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@listen_bp.route("/preset/store/rate", methods=["POST"])
def rate_community_preset():
    """Note un preset communautaire"""
    try:
        from vtp_core import save_settings, COMMUNITY_PRESET_STORE, stealth_print
        data = request.get_json(silent=True) or {}
        preset_id = str(data.get("id", "") or "").strip()
        rating = int(data.get("rating", 0) or 0)
        if rating < 1 or rating > 5:
            return jsonify({"ok": False, "error": "Note entre 1 et 5"}), 400
        found = False
        for p in COMMUNITY_PRESET_STORE:
            if p.get("id") == preset_id:
                found = True
                break
        if not found:
            return jsonify({"ok": False, "error": "Preset introuvable"}), 404
        AUDIO_CONFIG.setdefault("ally_community_preset_ratings", {})
        if isinstance(AUDIO_CONFIG["ally_community_preset_ratings"], str):
            import json as _json
            AUDIO_CONFIG["ally_community_preset_ratings"] = _json.loads(AUDIO_CONFIG["ally_community_preset_ratings"])
        ratings = AUDIO_CONFIG["ally_community_preset_ratings"]
        if not isinstance(ratings, dict):
            ratings = {}
        ratings[preset_id] = rating
        AUDIO_CONFIG["ally_community_preset_ratings"] = ratings
        save_settings()
        stealth_print(f"⭐ Preset communautaire noté: {preset_id} → {rating}/5")
        return jsonify({"ok": True, "id": preset_id, "rating": rating})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# === SCHEDULE, PROFILE, FOCUS (depuis vtp_core.py) ===

@listen_bp.route("/preset/schedule/add", methods=["POST"])
def add_preset_schedule():
    """Ajoute un planning de preset"""
    try:
        from vtp_core import save_settings, LISTEN_GAME_PRESETS, stealth_print
        data = request.get_json(silent=True) or {}
        name = str(data.get("name", "") or "").strip()
        preset = str(data.get("preset", "") or "").strip()
        days = data.get("days", [])
        hour = int(data.get("hour", 0) or 0)
        minute = int(data.get("minute", 0) or 0)
        enabled = bool(data.get("enabled", True))
        if not name or not preset:
            return jsonify({"ok": False, "error": "Nom et preset requis"}), 400
        valid_presets = set(LISTEN_GAME_PRESETS.keys()) | {"custom"}
        valid_presets.update(k for k in AUDIO_CONFIG.get("ally_preset_library", []) if isinstance(k, dict) and k.get("name"))
        if preset not in LISTEN_GAME_PRESETS and preset != "custom":
            lib_names = [str(it.get("name", "")).strip().lower() for it in (AUDIO_CONFIG.get("ally_preset_library") or []) if isinstance(it, dict)]
            if preset.lower() not in lib_names and preset not in LISTEN_GAME_PRESETS:
                return jsonify({"ok": False, "error": f"Preset inconnu: {preset}"}), 400
        entry = {
            "name": name,
            "preset": preset,
            "days": days if isinstance(days, list) else [],
            "hour": max(0, min(23, hour)),
            "minute": max(0, min(59, minute)),
            "enabled": enabled,
            "last_applied": "",
        }
        schedules = AUDIO_CONFIG.get("ally_preset_schedule", [])
        if not isinstance(schedules, list):
            schedules = []
        schedules.append(entry)
        AUDIO_CONFIG["ally_preset_schedule"] = schedules
        save_settings()
        stealth_print(f"📅 Planning preset ajouté: {name} ({preset})")
        return jsonify({"ok": True, "schedule": entry, "schedules": schedules})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@listen_bp.route("/preset/schedule/remove", methods=["POST"])
def remove_preset_schedule():
    """Supprime un planning de preset"""
    try:
        from vtp_core import save_settings, stealth_print
        data = request.get_json(silent=True) or {}
        name = str(data.get("name", "") or "").strip()
        if not name:
            return jsonify({"ok": False, "error": "Nom du planning requis"}), 400
        schedules = AUDIO_CONFIG.get("ally_preset_schedule", [])
        if not isinstance(schedules, list):
            schedules = []
        new_schedules = [s for s in schedules if str(s.get("name", "")).strip() != name]
        if len(new_schedules) == len(schedules):
            return jsonify({"ok": False, "error": "Planning introuvable"}), 404
        AUDIO_CONFIG["ally_preset_schedule"] = new_schedules
        save_settings()
        stealth_print(f"📅 Planning preset supprimé: {name}")
        return jsonify({"ok": True, "schedules": new_schedules})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@listen_bp.route("/preset/schedule/toggle", methods=["POST"])
def toggle_preset_schedule():
    """Active/désactive un planning de preset"""
    try:
        from vtp_core import save_settings
        data = request.get_json(silent=True) or {}
        name = str(data.get("name", "") or "").strip()
        if not name:
            return jsonify({"ok": False, "error": "Nom du planning requis"}), 400
        schedules = AUDIO_CONFIG.get("ally_preset_schedule", [])
        if not isinstance(schedules, list):
            schedules = []
        found = False
        for s in schedules:
            if str(s.get("name", "")).strip() == name:
                s["enabled"] = not s.get("enabled", True)
                found = True
                break
        if not found:
            return jsonify({"ok": False, "error": "Planning introuvable"}), 404
        AUDIO_CONFIG["ally_preset_schedule"] = schedules
        save_settings()
        return jsonify({"ok": True, "schedules": schedules})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@listen_bp.route("/profile/default", methods=["POST"])
def apply_default_listen_profile():
    """Retour aux réglages écoute stables par défaut"""
    try:
        from vtp_core import _is_competitive_listen_locked, _listen_lock_block_response, _apply_quality_preset, save_settings, stealth_print
        if _is_competitive_listen_locked():
            return _listen_lock_block_response()
        AUDIO_CONFIG["is_listening"] = True
        AUDIO_CONFIG["ally_recognition_lang"] = "multi"
        AUDIO_CONFIG["ally_block_french"] = True
        AUDIO_CONFIG["ally_sentence_punct_min_words"] = 3
        AUDIO_CONFIG["ally_sentence_hard_flush_words"] = 10
        AUDIO_CONFIG["ally_tts_similarity_play_below"] = 0.85
        AUDIO_CONFIG["ally_tts_duplicate_window_s"] = 3.0
        AUDIO_CONFIG["ally_tts_force_on_speech_final"] = True
        AUDIO_CONFIG["ally_tts_force_min_chars"] = 8
        AUDIO_CONFIG["ally_tts_min_gap_s"] = 0.55
        AUDIO_CONFIG["ally_voice_focus_mode"] = "balanced"
        AUDIO_CONFIG["ally_autotune_enabled"] = True
        AUDIO_CONFIG["ally_listen_profile"] = "default"
        AUDIO_CONFIG["ally_game_preset"] = "custom"
        AUDIO_CONFIG["vad_threshold"] = 0.025
        AUDIO_CONFIG["quality_preset"] = "balanced"
        _apply_quality_preset("balanced", emit_log=False)
        save_settings()
        stealth_print("↩️ Profil écoute par défaut appliqué.")
        return jsonify({
            "ok": True,
            "profile": "default",
            "is_listening": True,
            "ally_voice_focus_mode": AUDIO_CONFIG["ally_voice_focus_mode"],
            "ally_listen_profile": AUDIO_CONFIG["ally_listen_profile"],
        })
    except Exception as e:
        stealth_print(f"❌ Erreur preset écoute par défaut: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


@listen_bp.route("/focus", methods=["POST"])
def set_listen_voice_focus():
    """Réglage direct du filtre vocal écoute"""
    try:
        from vtp_core import _is_competitive_listen_locked, _listen_lock_block_response, _voice_focus_v3_reset_calibration, _voice_focus_v3_state, _listen_focus_auto_state, save_settings, stealth_print
        if _is_competitive_listen_locked():
            return _listen_lock_block_response()
        data = request.get_json(silent=True) or {}
        mode = str(data.get("mode", "balanced") or "balanced").strip().lower()
        if mode not in {"off", "balanced", "aggressive", "auto", "v3"}:
            return jsonify({"ok": False, "error": "Mode invalide. Modes: off, balanced, aggressive, auto, v3"}), 400
        AUDIO_CONFIG["ally_voice_focus_mode"] = mode
        if mode == "v3":
            _voice_focus_v3_reset_calibration()
            stealth_print("🎛️ Voice Focus V3 activé — calibration en cours (30s)...")
        save_settings()
        stealth_print(f"🎛️ Voice Focus écoute -> {mode}")
        return jsonify({
            "ok": True,
            "mode": mode,
            "ally_voice_focus_mode": AUDIO_CONFIG["ally_voice_focus_mode"],
            "ally_voice_focus_effective": str(_listen_focus_auto_state.get("mode_effective", "balanced") or "balanced"),
            "v3_calibrated": _voice_focus_v3_state["calibrated"] if mode == "v3" else None,
        })
    except Exception as e:
        stealth_print(f"❌ Erreur réglage Voice Focus: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


@listen_bp.route("/focus/v3/calibrate/start", methods=["POST"])
@listen_bp.route("/v3/calibrate", methods=["POST"])
def v3_calibrate_start():
    """Lance la calibration Voice Focus V3"""
    try:
        from vtp_core import _voice_focus_v3_reset_calibration, _voice_focus_v3_state, _push_toast, save_settings
        _voice_focus_v3_reset_calibration()
        AUDIO_CONFIG["ally_voice_focus_mode"] = "v3"
        save_settings()
        _push_toast("🎛️ Voice Focus V3: calibration 30s lancée")
        return jsonify({
            "ok": True,
            "message": "Calibration Voice Focus V3 lancée (30s). Parle normalement pendant la calibration.",
            "v3_calibrated": False,
            "calibration_duration_s": _voice_focus_v3_state["calibration_duration_s"],
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@listen_bp.route("/focus/v3/reset", methods=["POST"])
def v3_reset():
    """Réinitialise Voice Focus V3"""
    try:
        from vtp_core import _voice_focus_v3_reset_calibration
        _voice_focus_v3_reset_calibration()
        return jsonify({"ok": True, "message": "Voice Focus V3 réinitialisé", "calibrated": False})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@listen_bp.route("/competitive_lock", methods=["POST"])
def set_competitive_listen_lock():
    """Active/désactive le verrou compétition"""
    try:
        from vtp_core import _is_competitive_listen_locked, save_settings, stealth_print
        data = request.get_json(silent=True) or {}
        enabled = bool(data.get("enabled", False)) if isinstance(data, dict) else False
        AUDIO_CONFIG["ally_competitive_lock"] = enabled
        if not enabled:
            AUDIO_CONFIG["ally_competitive_unlock_until_ts"] = 0.0
        save_settings()
        if enabled:
            stealth_print("🔒 Verrou compétition écoute activé.")
        else:
            stealth_print("🔓 Verrou compétition écoute désactivé.")
        return jsonify({
            "ok": True,
            "ally_competitive_lock": bool(AUDIO_CONFIG.get("ally_competitive_lock", False)),
            "ally_competitive_lock_effective": bool(_is_competitive_listen_locked()),
            "ally_competitive_unlock_remaining_s": max(
                0,
                int((float(AUDIO_CONFIG.get("ally_competitive_unlock_until_ts", 0.0) or 0.0) - time.time()) + 0.999)
            ),
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

# === COMPETITIVE LOCK, RUNTIME, HEALTH, FINGERPRINT, AUTO_DETECT ===

@listen_bp.route("/competitive_lock/auto", methods=["POST"])
def set_competitive_listen_lock_auto():
    """Active/désactive le verrou auto compétition"""
    try:
        from vtp_core import save_settings, stealth_print
        data = request.get_json(silent=True) or {}
        enabled = bool(data.get("enabled", True)) if isinstance(data, dict) else True
        AUDIO_CONFIG["ally_competitive_lock_auto"] = enabled
        save_settings()
        stealth_print("🛡️ Verrou auto compétition -> " + ("ON" if enabled else "OFF"))
        return jsonify({
            "ok": True,
            "ally_competitive_lock_auto": bool(AUDIO_CONFIG.get("ally_competitive_lock_auto", True)),
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@listen_bp.route("/competitive_lock/temp_unlock", methods=["POST"])
def temp_unlock_competitive_listen_lock():
    """Déverrouille temporairement le verrou compétition"""
    try:
        from vtp_core import save_settings, _is_competitive_listen_locked, stealth_print
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


@listen_bp.route("/runtime/reset", methods=["POST"])
def reset_listen_runtime():
    """Réinitialise les stats runtime d'écoute"""
    try:
        from vtp_core import _reset_listen_runtime_stats
        _reset_listen_runtime_stats()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@listen_bp.route("/health/reset", methods=["POST"])
def reset_listen_health_runtime():
    """Réinitialise les stats health d'écoute"""
    try:
        from vtp_core import _reset_listen_health_runtime
        _reset_listen_health_runtime()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@listen_bp.route("/detect_game_fingerprint", methods=["POST"])
def detect_game_fingerprint():
    """Détecte le jeu via fingerprint audio"""
    try:
        from vtp_core import _afp, _get_foreground_process_name
        duration = float((request.get_json(silent=True) or {}).get("duration_s", 2.5))
        duration = max(1.0, min(duration, 5.0))
        if not _afp:
            return jsonify({"ok": False, "error": "Module fingerprint non disponible"}), 500
        fp = _afp.capture_and_fingerprint(duration_s=duration)
        if not fp:
            return jsonify({"ok": False, "error": "Aucun audio capturé. Lance un jeu ou vérifie le loopback."}), 500
        match = _afp.match_fingerprint(fp)
        proc = _get_foreground_process_name()
        _afp.set_cached_match(proc, match)
        return jsonify({
            "ok": True,
            "fingerprint_hash": fp["hash"],
            "duration_s": fp["duration_s"],
            "features_summary": {
                "centroid": fp["features"]["centroid"],
                "rolloff": fp["features"]["rolloff"],
                "flatness": fp["features"]["flatness"],
                "rms": fp["features"]["rms"],
            },
            "match": match,
            "hint": "Utilise POST /audio/listen/fingerprint/contribute pour ajouter ce fingerprint à la BDD" if match is None else None,
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@listen_bp.route("/fingerprint/contribute", methods=["POST"])
def contribute_fingerprint():
    """Ajoute un fingerprint à la BDD"""
    try:
        from vtp_core import _afp, _get_foreground_process_name, detect_current_game
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


@listen_bp.route("/fingerprint/db/import", methods=["POST"])
def fingerprint_db_import():
    """Importe une base de fingerprints"""
    try:
        from vtp_core import _afp
        if not _afp:
            return jsonify({"ok": False, "error": "Module fingerprint non disponible"}), 500
        data = request.get_json(silent=True) or {}
        db = data.get("database")
        if not isinstance(db, dict):
            return jsonify({"ok": False, "error": "Format invalide: 'database' dict requis"}), 400
        _afp.import_fingerprint_db(db)
        return jsonify({"ok": True, "message": "Base de fingerprints importée"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@listen_bp.route("/auto_detect/toggle", methods=["POST"])
def toggle_auto_detect():
    """Active/désactive la détection automatique de jeu"""
    from vtp_core import _game_detect_auto_mode, save_settings
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
