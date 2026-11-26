#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Module TTS pour Kommz Gamer."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Callable

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

tts_bp = Blueprint("tts", __name__)

_RUNTIME: dict[str, Any] = {}


FallbackReasonFn = Callable[..., Any]


@tts_bp.route("/voices/edge", methods=["GET"])
def list_edge_voices():
    all_edge_voices = _RUNTIME["ALL_EDGE_VOICES"]
    if not all_edge_voices:
        all_edge_voices.extend(get_clean_voices_sync())
    return jsonify({"ok": True, "voices": list(all_edge_voices)})


@tts_bp.route("/voices/studio/list", methods=["GET"])
def voice_studio_list():
    try:
        audio_config = _RUNTIME["AUDIO_CONFIG"]
        lib = _RUNTIME["_get_voice_library"]()
        active_id = str(audio_config.get("voice_active_id") or audio_config.get("kommz_client_id") or "").strip()
        return jsonify({
            "ok": True,
            "voices": lib,
            "active_id": active_id,
            "active_engine": str(audio_config.get("tts_engine") or "KOMMZ_VOICE").strip().upper(),
            "default_at_startup": bool(audio_config.get("voice_default_at_startup", True)),
        })
    except Exception as exc:
        logger.exception("voice_studio_list failed")
        return jsonify({"ok": False, "error": f"voice_studio_list: {str(exc)}"}), 500


@tts_bp.route("/voices/studio/save", methods=["POST"])
def voice_studio_save():
    try:
        audio_config = _RUNTIME["AUDIO_CONFIG"]
        save_settings = _RUNTIME["save_settings"]
        normalize_voice_library_entry = _RUNTIME["_normalize_voice_library_entry"]
        get_voice_library = _RUNTIME["_get_voice_library"]
        set_voice_active_id = _RUNTIME["_set_voice_active_id"]
        to_bool = _RUNTIME["_to_bool"]

        data = request.get_json(silent=True) or {}
        if not isinstance(data, dict):
            return jsonify({"ok": False, "error": "payload JSON invalide"}), 400

        voice_id = str(
            data.get("voice_id")
            or data.get("id")
            or data.get("client_id")
            or data.get("kommz_id")
            or ""
        ).strip()
        if not voice_id:
            return jsonify({"ok": False, "error": "voice_id manquant"}), 400

        engine = str(data.get("engine") or "KOMMZ_VOICE").strip().upper()
        if engine not in {"KOMMZ_VOICE", "FISH_AUDIO"}:
            return jsonify({"ok": False, "error": "engine invalide"}), 400

        entry = normalize_voice_library_entry({**data, "engine": engine})
        library = get_voice_library()
        replaced = False
        for idx, item in enumerate(library):
            if (
                str(item.get("voice_id") or "").strip() == voice_id
                and str(item.get("engine") or "KOMMZ_VOICE").strip().upper() == engine
            ):
                library[idx] = entry
                replaced = True
                break
        if not replaced:
            library.insert(0, entry)

        audio_config["voice_library"] = library[:80]
        if to_bool(data.get("set_active"), False):
            set_voice_active_id(voice_id, persist=False)
            audio_config["tts_engine"] = engine
        if "default_at_startup" in data:
            audio_config["voice_default_at_startup"] = to_bool(data.get("default_at_startup"), True)

        save_settings()
        return jsonify({
            "ok": True,
            "entry": entry,
            "active_id": str(audio_config.get("voice_active_id") or ""),
            "default_at_startup": bool(audio_config.get("voice_default_at_startup", True)),
        })
    except Exception as exc:
        logger.exception("voice_studio_save failed")
        return jsonify({"ok": False, "error": f"voice_studio_save: {str(exc)}"}), 500


@tts_bp.route("/voices/studio/activate", methods=["POST"])
def voice_studio_activate():
    try:
        audio_config = _RUNTIME["AUDIO_CONFIG"]
        save_settings = _RUNTIME["save_settings"]
        normalize_voice_library_entry = _RUNTIME["_normalize_voice_library_entry"]
        get_voice_library = _RUNTIME["_get_voice_library"]
        set_voice_active_id = _RUNTIME["_set_voice_active_id"]
        to_bool = _RUNTIME["_to_bool"]

        data = request.get_json(silent=True) or {}
        if not isinstance(data, dict):
            return jsonify({"ok": False, "error": "payload JSON invalide"}), 400
        voice_id = str(data.get("voice_id") or "").strip()
        if not voice_id:
            return jsonify({"ok": False, "error": "voice_id manquant"}), 400

        engine = str(data.get("engine") or "KOMMZ_VOICE").strip().upper()
        if engine not in {"KOMMZ_VOICE", "FISH_AUDIO"}:
            return jsonify({"ok": False, "error": "engine invalide"}), 400

        library = get_voice_library()
        exists = any(
            str(item.get("voice_id") or "").strip() == voice_id
            and str(item.get("engine") or "KOMMZ_VOICE").strip().upper() == engine
            for item in library
        )
        if not exists:
            library.insert(0, normalize_voice_library_entry({"voice_id": voice_id, "name": voice_id, "engine": engine}))
            audio_config["voice_library"] = library[:80]

        set_voice_active_id(voice_id, persist=False)
        audio_config["tts_engine"] = engine
        if "default_at_startup" in data:
            audio_config["voice_default_at_startup"] = to_bool(data.get("default_at_startup"), True)
        save_settings()
        return jsonify({
            "ok": True,
            "active_id": voice_id,
            "default_at_startup": bool(audio_config.get("voice_default_at_startup", True)),
        })
    except Exception as exc:
        logger.exception("voice_studio_activate failed")
        return jsonify({"ok": False, "error": f"voice_studio_activate: {str(exc)}"}), 500


@tts_bp.route("/voices/studio/delete", methods=["POST"])
def voice_studio_delete():
    try:
        audio_config = _RUNTIME["AUDIO_CONFIG"]
        save_settings = _RUNTIME["save_settings"]
        get_voice_library = _RUNTIME["_get_voice_library"]

        data = request.get_json(silent=True) or {}
        if not isinstance(data, dict):
            return jsonify({"ok": False, "error": "payload JSON invalide"}), 400
        voice_id = str(data.get("voice_id") or "").strip()
        if not voice_id:
            return jsonify({"ok": False, "error": "voice_id manquant"}), 400

        library = [v for v in get_voice_library() if str(v.get("voice_id") or "").strip() != voice_id]
        audio_config["voice_library"] = library
        if str(audio_config.get("voice_active_id") or "").strip() == voice_id:
            audio_config["voice_active_id"] = ""
        if str(audio_config.get("kommz_client_id") or "").strip() == voice_id:
            audio_config["kommz_client_id"] = ""
        save_settings()
        return jsonify({"ok": True, "deleted": voice_id})
    except Exception as exc:
        logger.exception("voice_studio_delete failed")
        return jsonify({"ok": False, "error": f"voice_studio_delete: {str(exc)}"}), 500


@tts_bp.route("/voices/studio/test", methods=["POST"])
def voice_studio_test():
    try:
        has_voice_license = _RUNTIME["has_voice_license"]
        resample_and_play = _RUNTIME["resample_and_play"]
        threading_mod = _RUNTIME["threading"]
        set_pipeline_runtime = _RUNTIME["_set_pipeline_runtime"]

        if not has_voice_license():
            return jsonify({"ok": False, "error": "Licence Voice requise"}), 403

        data = request.get_json(silent=True) or {}
        if not isinstance(data, dict):
            return jsonify({"ok": False, "error": "payload JSON invalide"}), 400

        voice_id = str(data.get("voice_id") or "").strip()
        text = str(data.get("text") or "Test vocal Kommz Voice").strip()
        if not voice_id:
            return jsonify({"ok": False, "error": "voice_id manquant"}), 400

        audio_blob, err = _synthesize_voice_preview(voice_id, text)
        if not audio_blob:
            return jsonify({"ok": False, "error": err or "Synthèse test indisponible"}), 502

        threading_mod.Thread(
            target=resample_and_play,
            args=([audio_blob], "", "MOI", 24000),
            kwargs={"emotion_hint": text},
            daemon=True,
        ).start()
        set_pipeline_runtime(
            hybrid_engine="Bypass Hybrid",
            hybrid_detail="Préécoute Voix Studio",
            tts_engine="Kommz Voice API",
            tts_route=f"voice_id preview ({voice_id[:8]}...)",
        )
        return jsonify({"ok": True, "voice_id": voice_id})
    except Exception as exc:
        logger.exception("voice_studio_test failed")
        return jsonify({"ok": False, "error": f"voice_studio_test: {str(exc)}"}), 500


def get_clean_voices_sync() -> list[dict[str, Any]]:
    """Récupère la liste des voix Microsoft Edge (avec cache)."""
    fallback_voices = _RUNTIME["FALLBACK_VOICES"]
    logger.info("🔄 Récupération des voix Microsoft Edge (Patientez)...")
    try:
        import edge_tts

        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            voices = loop.run_until_complete(edge_tts.list_voices())
        finally:
            loop.close()

        clean_list: list[dict[str, Any]] = []
        for voice in voices:
            if "Neural" in voice["ShortName"]:
                clean_list.append(
                    {
                        "ShortName": voice["ShortName"],
                        "Gender": voice["Gender"],
                        "Locale": voice["Locale"],
                    }
                )
        if not clean_list:
            raise RuntimeError("Liste reçue vide")
        clean_list.sort(key=lambda item: item["ShortName"])
        logger.info("✅ %s voix chargées.", len(clean_list))
        return clean_list
    except Exception as exc:
        logger.warning("⚠️ Erreur Connexion Microsoft (%s) -> UTILISATION DU BACKUP.", exc)
        return fallback_voices


def _synthesize_voice_preview(voice_id: str, text: str) -> tuple[bytes | None, str]:
    """Test rapide voix studio via endpoint /synthesis (voice_id direct)."""
    audio_config = _RUNTIME["AUDIO_CONFIG"]
    requests_mod = _RUNTIME["requests"]
    resolve_synthesis_base = _RUNTIME["_resolve_kommz_synthesis_base"]
    resolve_voice_endpoint = _RUNTIME["_resolve_kommz_voice_endpoint"]
    normalize_xtts_request_lang = _RUNTIME["_normalize_xtts_request_lang"]
    build_synthesis_candidates = _RUNTIME["_build_kommz_synthesis_candidates"]
    build_generate_candidates = _RUNTIME["_build_kommz_generate_candidates"]
    repair_display_text = _RUNTIME["_repair_display_text"]
    looks_like_cloud_trial_limit = _RUNTIME["_looks_like_cloud_trial_limit"]

    voice_id = str(voice_id or "").strip()
    text = str(text or "").strip()
    if not voice_id:
        return None, "voice_id manquant"
    if not text:
        return None, "texte manquant"

    synth_base = resolve_synthesis_base()
    base_url_modal = resolve_voice_endpoint()
    api_key_cfg = str(audio_config.get("kommz_api_key", "") or "").strip()
    if not synth_base:
        return None, "URL synthesis non définie"
    if not api_key_cfg:
        return None, "API key manquante"

    speed = max(0.70, min(1.30, float(audio_config.get("kommz_speed", 1.0) or 1.0)))
    temp = max(0.0, min(1.0, float(audio_config.get("kommz_temp", 0.70) or 0.70)))
    xtts_lang = normalize_xtts_request_lang(_RUNTIME["CURRENT_TARGET_LANG_GETTER"](), text)
    candidates = build_synthesis_candidates(synth_base)
    last_err = "Aucun endpoint synthesis disponible"

    for api_url in candidates:
        try:
            response = requests_mod.post(
                api_url,
                headers={
                    "Authorization": f"Bearer {api_key_cfg}",
                    "Content-Type": "application/json",
                },
                json={
                    "text": text,
                    "voice_id": voice_id,
                    "speed": speed,
                    "temperature": temp,
                    "language": xtts_lang,
                },
                timeout=(4, 45),
            )
            if not response.ok:
                body = repair_display_text((response.text or "")[:180])
                if looks_like_cloud_trial_limit(response.status_code, body):
                    last_err = "Quota essai voice_id atteint ou expiré"
                else:
                    last_err = f"HTTP {response.status_code} {body}"
                continue

            content_type = (response.headers.get("Content-Type") or "").lower()
            if "audio/wav" in content_type or "audio/x-wav" in content_type:
                return response.content, ""

            payload = response.json()
            audio_url = str((payload or {}).get("audio_url") or "").strip()
            if not audio_url:
                last_err = "audio_url manquante"
                continue
            download = requests_mod.get(audio_url, timeout=(4, 45))
            if not download.ok:
                last_err = f"download audio_url HTTP {download.status_code}"
                continue
            return download.content, ""
        except Exception as exc:
            last_err = repair_display_text(str(exc))
            continue

    if "Quota essai voice_id atteint ou expiré" not in str(last_err or ""):
        return None, last_err

    audio_source_bytes = None
    preset_voice_buffer = _RUNTIME["PRESET_VOICE_BUFFER_GETTER"]()
    last_user_audio_buffer = _RUNTIME["LAST_USER_AUDIO_BUFFER_GETTER"]()
    if preset_voice_buffer is not None:
        audio_source_bytes = preset_voice_buffer
    elif last_user_audio_buffer is not None:
        audio_source_bytes = last_user_audio_buffer
    if audio_source_bytes is None:
        return None, last_err + " (aucune référence clone disponible)"
    if not base_url_modal:
        return None, last_err + " (clone URL non définie)"

    xtts_lang = normalize_xtts_request_lang(_RUNTIME["CURRENT_TARGET_LANG_GETTER"](), text)
    clone_candidates = build_generate_candidates(base_url_modal)
    clone_last_err = "Aucun endpoint clone valide"
    files = {"speaker_wav": ("audio.wav", audio_source_bytes, "audio/wav")}
    data = {
        "text": text,
        "language": xtts_lang,
        "speed": speed,
        "reference_text": "Mode Preview.",
        "temperature": temp,
    }
    for api_url in clone_candidates:
        try:
            response = requests_mod.post(api_url, files=files, data=data, timeout=(5, 180))
            if response.ok:
                return response.content, ""
            clone_last_err = f"HTTP {response.status_code} {(response.text or '')[:180]}"
        except Exception as exc:
            clone_last_err = repair_display_text(str(exc))
            continue
    return None, clone_last_err




def windows_natural_generator(text: str, specific_speed: str | None = None, voice_override: str | None = None):
    """Générateur Edge TTS avec fallback robuste de voix."""
    import edge_tts
    import miniaudio

    audio_config = _RUNTIME["AUDIO_CONFIG"]

    def _normalize_edge_rate(raw_rate: str | None) -> str:
        value = str(raw_rate or "").strip()
        match = re.match(r"^([+-]?)(\d{1,3})%$", value)
        if not match:
            return "-10%"
        sign = -1 if match.group(1) == "-" else 1
        number = int(match.group(2)) * sign
        number = max(-30, min(10, number))
        return f"{number:+d}%"

    configured_rate = audio_config.get("windows_tts_rate", "-10%")
    rate = _normalize_edge_rate(specific_speed if specific_speed is not None else configured_rate)

    preferred_voice = str(voice_override).strip() if voice_override else str(audio_config.get("edge_voice") or "").strip()
    if not preferred_voice:
        preferred_voice = "fr-FR-VivienneMultilingualNeural"

    voice_candidates = [preferred_voice]
    for voice_name in ("fr-FR-VivienneMultilingualNeural", "en-US-GuyNeural"):
        if voice_name not in voice_candidates:
            voice_candidates.append(voice_name)

    async def _fetch_with_voice(voice_name: str) -> bytes:
        try:
            communicate = edge_tts.Communicate(text, voice_name, rate=rate)
            audio_data = b""
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_data += chunk["data"]
            return audio_data
        except Exception as exc:
            logger.warning("⚠️ Edge TTS voice '%s' error: %s", voice_name, exc)
            return b""

    try:
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            mp3_bytes = b""
            used_voice = ""
            for candidate in voice_candidates:
                mp3_bytes = loop.run_until_complete(_fetch_with_voice(candidate))
                if mp3_bytes:
                    used_voice = candidate
                    break
        finally:
            loop.close()
        if mp3_bytes:
            if used_voice:
                logger.info("🗣️ Edge TTS voice utilisée: %s (%s)", used_voice, rate)
            decoded = miniaudio.decode(
                mp3_bytes,
                nchannels=1,
                sample_rate=16000,
                output_format=miniaudio.SampleFormat.SIGNED16,
            )
            yield decoded.samples.tobytes()
        else:
            logger.warning("⚠️ Edge TTS: aucun audio généré (toutes les voix fallback ont échoué).")
    except Exception as exc:
        logger.warning("⚠️ Edge TTS generator error: %s", exc)
        yield []


def register_tts_module(**deps: Any) -> Blueprint:
    required_keys = [
        "ALL_EDGE_VOICES",
        "AUDIO_CONFIG",
        "CURRENT_TARGET_LANG_GETTER",
        "FALLBACK_VOICES",
        "LAST_USER_AUDIO_BUFFER_GETTER",
        "PRESET_VOICE_BUFFER_GETTER",
        "_build_kommz_generate_candidates",
        "_build_kommz_synthesis_candidates",
        "_get_voice_library",
        "_looks_like_cloud_trial_limit",
        "_normalize_voice_library_entry",
        "_normalize_xtts_request_lang",
        "_repair_display_text",
        "_resolve_kommz_synthesis_base",
        "_resolve_kommz_voice_endpoint",
        "_set_pipeline_runtime",
        "_set_voice_active_id",
        "_to_bool",
        "has_voice_license",
        "requests",
        "resample_and_play",
        "save_settings",
        "threading",
    ]
    missing = [key for key in required_keys if key not in deps]
    if missing:
        raise ValueError(f"register_tts_module missing dependencies: {', '.join(missing)}")

    _RUNTIME.clear()
    _RUNTIME.update(deps)
    return tts_bp
    
@tts_bp.route("/kommz/xtts/warmup", methods=["POST"])
def kommz_xtts_warmup():
    from flask import request, jsonify
    import vtp_core as core
    try:
        payload = request.get_json(silent=True) or {}
        force = bool(payload.get("force", False)) if isinstance(payload, dict) else False
        retry_after = core._get_xtts_warmup_retry_after_seconds()
        if (retry_after > 0) and not force:
            return jsonify({
                "ok": False,
                "retry_after": retry_after,
                "cooldown": core.KOMMZ_XTTS_WARMUP_COOLDOWN
            }), 429
        core.prewarm_kommz_xtts(force=force)
        return jsonify({
            "ok": True,
            "retry_after": core._get_xtts_warmup_retry_after_seconds(),
            "cooldown": core.KOMMZ_XTTS_WARMUP_COOLDOWN,
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500    
