#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Module TTS pour Kommz Gamer."""

from __future__ import annotations

import asyncio
import logging
import re
import time
from datetime import datetime
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


def kommz_tts_generator(text: str):
    audio_config = _RUNTIME["AUDIO_CONFIG"]
    http_client = _RUNTIME["_HTTP"]
    resolve_voice_endpoint = _RUNTIME["_resolve_kommz_voice_endpoint"]
    resolve_synthesis_base = _RUNTIME["_resolve_kommz_synthesis_base"]
    to_bool = _RUNTIME["_to_bool"]
    is_hybrid_supported_target_lang = _RUNTIME["_is_hybrid_supported_target_lang"]
    is_turbo_mode_active = _RUNTIME["_is_turbo_mode_active"]
    get_hybrid_rts_preset = _RUNTIME["_get_hybrid_rts_preset"]
    build_synthesis_candidates = _RUNTIME["_build_kommz_synthesis_candidates"]
    repair_display_text = _RUNTIME["_repair_display_text"]
    looks_like_cloud_trial_limit = _RUNTIME["_looks_like_cloud_trial_limit"]
    short_runtime_url = _RUNTIME["_short_runtime_url"]
    set_pipeline_runtime = _RUNTIME["_set_pipeline_runtime"]
    register_tts_fallback: FallbackReasonFn = _RUNTIME["_register_tts_fallback"]
    set_hybrid_fast_runtime = _RUNTIME["_set_hybrid_fast_runtime"]
    gpt_style_to_xtts_ref_bytes = _RUNTIME["_gpt_style_to_xtts_ref_bytes"]
    build_generate_candidates = _RUNTIME["_build_kommz_generate_candidates"]
    prewarm_kommz_xtts = _RUNTIME["prewarm_kommz_xtts"]
    wav_duration_seconds = _RUNTIME["_wav_duration_seconds"]
    is_trial_voice_mode_enabled = _RUNTIME["_is_trial_voice_mode_enabled"]
    add_subtitle = _RUNTIME["add_subtitle"]
    save_settings = _RUNTIME["save_settings"]
    short_runtime_text = _RUNTIME["_short_runtime_text"]
    normalize_xtts_request_lang = _RUNTIME["_normalize_xtts_request_lang"]

    audio_source_bytes = None
    source_mode = "none"
    client_id_cfg = str(audio_config.get("kommz_client_id", "") or "").strip()
    api_key_cfg = str(audio_config.get("kommz_api_key", "") or "").strip()
    target_lang = str(audio_config.get("target_lang", "en") or "en").lower()
    xtts_lang = normalize_xtts_request_lang(target_lang, text)
    tts_speed = float(audio_config.get("kommz_speed", 1.0) or 1.0)
    tts_temp = float(audio_config.get("kommz_temp", 0.7) or 0.7)
    tts_top_k = max(1, min(200, int(audio_config.get("kommz_top_k", 60) or 60)))
    tts_top_p = max(0.1, min(1.0, float(audio_config.get("kommz_top_p", 0.90) or 0.90)))
    tts_repetition_penalty = max(1.0, min(10.0, float(audio_config.get("kommz_repetition_penalty", 2.2) or 2.2)))
    tts_length_penalty = max(0.1, min(5.0, float(audio_config.get("kommz_length_penalty", 1.0) or 1.0)))
    tts_enable_split = bool(audio_config.get("kommz_enable_text_splitting", True))
    tts_gpt_cond_len = max(1, min(30, int(audio_config.get("kommz_gpt_cond_len", 12) or 12)))
    tts_gpt_cond_chunk_len = max(1, min(10, int(audio_config.get("kommz_gpt_cond_chunk_len", 4) or 4)))
    tts_max_ref_len = max(3, min(20, int(audio_config.get("kommz_max_ref_len", 10) or 10)))
    tts_sound_norm_refs = bool(audio_config.get("kommz_sound_norm_refs", False))
    base_url_modal = resolve_voice_endpoint()
    synth_base = resolve_synthesis_base()
    hybrid_enabled = to_bool(audio_config.get("gpt_style_to_xtts_fr", False), False) and is_hybrid_supported_target_lang(target_lang)
    turbo_mode = is_turbo_mode_active()
    if turbo_mode:
        tts_enable_split = True
    if xtts_lang != target_lang:
        logger.info("ℹ️ XTTS langue adaptée: %s -> %s", target_lang, xtts_lang)

    hybrid_cache = _RUNTIME["_hybrid_style_ref_cache"]
    hybrid_cache_key = "|".join([
        xtts_lang,
        str(audio_config.get("gpt_api_url", "") or "").strip(),
        str(audio_config.get("gpt_ref_audio_path", "") or "").strip().lower(),
        str(audio_config.get("gpt_prompt_text", "") or "").strip(),
        str(audio_config.get("gpt_style_text", "") or "").strip(),
        "fast" if (hybrid_enabled and turbo_mode and get_hybrid_rts_preset() == "fast") else "quality",
    ])

    def _try_voice_id_api() -> bytes | None:
        if client_id_cfg and api_key_cfg and synth_base:
            synth_candidates = build_synthesis_candidates(synth_base)
            logger.info("🎯 Mode voice_id forcé actif: %s", client_id_cfg)
            last_api_err = ""
            last_api_status = 0
            last_api_url = ""
            attempt_notes: list[str] = []
            trial_quota_hit = False
            for idx, api_url in enumerate(synth_candidates, start=1):
                try:
                    logger.info("📤 API synthesis -> %s (%s/%s)", api_url, idx, len(synth_candidates))
                    last_api_url = api_url
                    response = http_client.post(
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
                    if not response.ok:
                        last_api_status = int(response.status_code or 0)
                        body = repair_display_text((response.text or "")[:240])
                        if looks_like_cloud_trial_limit(response.status_code, body):
                            last_api_err = "Quota essai voice_id atteint ou expiré"
                            trial_quota_hit = True
                        else:
                            last_api_err = repair_display_text(f"HTTP {response.status_code} {body}")
                        attempt_notes.append(f"{idx}:{short_runtime_url(api_url, 72)}=HTTP{response.status_code}")
                        continue

                    content_type = (response.headers.get("Content-Type") or "").lower()
                    if "audio/wav" in content_type or "audio/x-wav" in content_type:
                        attempt_notes.append(f"{idx}:{short_runtime_url(api_url, 72)}=OK")
                        logger.info("✅ Voice_id forcé OK (audio direct).")
                        set_pipeline_runtime(
                            hybrid_engine="Bypass Hybrid",
                            hybrid_detail="voice_id prioritaire",
                            tts_engine="Kommz Voice API",
                            tts_route="voice_id / audio direct",
                        )
                        return response.content

                    payload = response.json()
                    audio_url = (payload or {}).get("audio_url", "")
                    if not audio_url:
                        last_api_err = "audio_url manquante dans réponse /v1/synthesis"
                        attempt_notes.append(f"{idx}:{short_runtime_url(api_url, 72)}=NO_AUDIO_URL")
                        continue
                    download = http_client.get(audio_url, timeout=(4, 60) if turbo_mode else 120)
                    if not download.ok:
                        last_api_err = f"download audio_url HTTP {download.status_code}"
                        attempt_notes.append(f"{idx}:{short_runtime_url(api_url, 72)}=DL_HTTP{download.status_code}")
                        continue
                    attempt_notes.append(f"{idx}:{short_runtime_url(api_url, 72)}=OK_URL")
                    logger.info("✅ Voice_id forcé OK (audio_url).")
                    set_pipeline_runtime(
                        hybrid_engine="Bypass Hybrid",
                        hybrid_detail="voice_id prioritaire",
                        tts_engine="Kommz Voice API",
                        tts_route="voice_id / audio_url",
                    )
                    return download.content
                except Exception as api_exc:
                    last_api_err = repair_display_text(str(api_exc))
                    attempt_notes.append(f"{idx}:{short_runtime_url(api_url, 72)}=ERR")
                    continue

            logger.warning("⚠️ Voice_id forcé indisponible, fallback clone. Détail: %s", last_api_err)
            register_tts_fallback(
                "VOICE_ID_TRIAL_QUOTA" if trial_quota_hit else "VOICE_ID_UNAVAILABLE",
                last_api_err or "voice_id fallback clone",
                endpoint=short_runtime_url(last_api_url or synth_base, 120),
                http_status=last_api_status,
                attempts=" | ".join(attempt_notes[-6:]),
            )
            return None

        if client_id_cfg and api_key_cfg and not synth_base:
            logger.warning("⚠️ Voice_id forcé ignoré: Synthesis URL non configurée.")
            logger.info("ℹ️ Définir kommz_synthesis_url (ou env KOMMZ_SYNTHESIS_URL) vers votre serveur web /v1/synthesis.")
            register_tts_fallback("VOICE_ID_URL_MISSING", "synth_base vide")
        return None

    if client_id_cfg and api_key_cfg:
        voice_audio = _try_voice_id_api()
        if voice_audio:
            yield voice_audio
            return

    if hybrid_enabled:
        hybrid_rts_preset = get_hybrid_rts_preset()
        hybrid_fast_mode = turbo_mode and hybrid_rts_preset == "fast"
        try:
            style_wav = None
            if hybrid_fast_mode:
                now_ts = time.time()
                cached = hybrid_cache.get("bytes")
                cached_lang = str(hybrid_cache.get("lang") or "")
                cached_key = str(hybrid_cache.get("key") or "")
                cached_ts = float(hybrid_cache.get("ts") or 0.0)
                if cached and cached_lang == xtts_lang and cached_key == hybrid_cache_key and (now_ts - cached_ts) <= 150.0:
                    style_wav = cached
                    set_hybrid_fast_runtime(
                        fast_path=True,
                        cache_hot=True,
                        cache_age_seconds=(now_ts - cached_ts),
                        detail=f"Cache Hybrid réutilisé · {target_lang.upper()}",
                    )
                    logger.info("🧪 Hybrid cache réutilisé (%s).", target_lang.upper())
                    set_pipeline_runtime(
                        hybrid_engine="GPT-SoVITS Hybrid",
                        hybrid_detail=f"Référence cache · {target_lang.upper()}",
                    )

            if style_wav is None:
                style_wav = gpt_style_to_xtts_ref_bytes(text, fast_mode=hybrid_fast_mode)
                if hybrid_fast_mode and style_wav:
                    hybrid_cache["bytes"] = style_wav
                    hybrid_cache["lang"] = xtts_lang
                    hybrid_cache["key"] = hybrid_cache_key
                    hybrid_cache["ts"] = time.time()
                    set_hybrid_fast_runtime(
                        fast_path=True,
                        cache_hot=False,
                        cache_age_seconds=0,
                        detail=f"Référence Hybrid régénérée · {target_lang.upper()}",
                    )

            if style_wav:
                audio_source_bytes = style_wav
                source_mode = "gpt_style_cache" if hybrid_fast_mode else "gpt_style_ref"
                if not hybrid_fast_mode:
                    set_hybrid_fast_runtime(
                        fast_path=False,
                        cache_hot=False,
                        cache_age_seconds=-1,
                        detail=f"Hybrid qualité actif · {target_lang.upper()}",
                    )
                logger.info("🧪 Hybrid prioritaire actif (%s): GPT-SoVITS -> XTTS", target_lang.upper())
                set_pipeline_runtime(hybrid_detail=f"Timbre prioritaire · {target_lang.upper()}")
        except Exception as hybrid_exc:
            logger.warning("⚠️ Hybrid GPT->XTTS indisponible, fallback voice_id/local: %s", hybrid_exc)
            set_hybrid_fast_runtime(
                fast_path=hybrid_fast_mode,
                cache_hot=False,
                cache_age_seconds=-1,
                detail=f"Fallback Hybrid · {short_runtime_text(hybrid_exc, 96)}",
            )
            set_pipeline_runtime(
                hybrid_engine="Fallback",
                hybrid_detail=f"GPT indisponible · {short_runtime_text(hybrid_exc, 96)}",
            )
            voice_audio = _try_voice_id_api()
            if voice_audio:
                yield voice_audio
                return
    else:
        set_hybrid_fast_runtime(
            fast_path=False,
            cache_hot=False,
            cache_age_seconds=-1,
            detail="Hybrid non actif · voice_id / clone direct",
        )
        set_pipeline_runtime(
            hybrid_engine="Bypass Hybrid",
            hybrid_detail="voice_id / clone direct prioritaire",
        )
        voice_audio = _try_voice_id_api()
        if voice_audio:
            yield voice_audio
            return

    if audio_source_bytes is None:
        preset_voice_buffer = _RUNTIME["PRESET_VOICE_BUFFER_GETTER"]()
        last_user_audio_buffer = _RUNTIME["LAST_USER_AUDIO_BUFFER_GETTER"]()
        if preset_voice_buffer is not None:
            logger.info("🎛️ Référence preset utilisée (fallback).")
            audio_source_bytes = preset_voice_buffer
            source_mode = "preset_buffer"
        elif last_user_audio_buffer is not None:
            logger.info("🎤 Micro Joueur utilisé (Mode Normal).")
            audio_source_bytes = last_user_audio_buffer
            source_mode = "micro_buffer"
        else:
            logger.warning("⚠️ Kommz Voice ignoré: aucune référence audio en RAM (micro/preset).")
            logger.info("ℹ️ Fallback reason: NO_REFERENCE_AUDIO_BUFFER")
            register_tts_fallback("NO_REFERENCE_AUDIO_BUFFER", "reference audio buffer absent")
            return

    logger.info(
        "🧭 TTS route | engine=%s | source=%s | client_id=%s | api_key=%s",
        audio_config.get("tts_engine", "WINDOWS"),
        source_mode,
        "set" if client_id_cfg else "empty",
        "set" if api_key_cfg else "empty",
    )
    route_labels = {
        "gpt_style_ref": "Clone direct · référence Hybrid",
        "gpt_style_cache": "Clone direct · cache Hybrid rapide",
        "micro_buffer": "Clone direct · buffer micro",
        "preset_buffer": "Clone direct · preset voix",
    }
    set_pipeline_runtime(
        tts_engine="XTTS Modal",
        tts_route=route_labels.get(source_mode, f"Clone direct · {source_mode}") + (" · turbo" if turbo_mode else ""),
    )
    if client_id_cfg:
        logger.info("ℹ️ Note: clone direct en fallback (voice_id indisponible/non configuré).")

    try:
        if not base_url_modal:
            logger.warning("⚠️ Kommz Voice ignoré: URL Modal vide.")
            logger.info("ℹ️ Fallback reason: EMPTY_MODAL_URL")
            register_tts_fallback(
                "EMPTY_MODAL_URL",
                "base_url_modal vide",
                endpoint=short_runtime_url(resolve_voice_endpoint(), 120),
            )
            return
        candidate_urls = build_generate_candidates(base_url_modal)
        if hybrid_enabled and turbo_mode and get_hybrid_rts_preset() == "fast":
            candidate_urls = candidate_urls[:2]
        if not candidate_urls:
            logger.warning("⚠️ Kommz Voice ignoré: aucune URL Modal candidate.")
            logger.info("ℹ️ Fallback reason: NO_MODAL_CANDIDATE_URL")
            register_tts_fallback(
                "NO_MODAL_CANDIDATE_URL",
                "candidate_urls vide",
                endpoint=short_runtime_url(base_url_modal, 120),
            )
            return
        prewarm_kommz_xtts(force=False, timeout_connect=2 if turbo_mode else 3, timeout_read=10 if turbo_mode else 20)

        files = {"speaker_wav": ("audio.wav", audio_source_bytes, "audio/wav")}
        data = {
            "text": text,
            "language": xtts_lang,
            "speed": tts_speed,
            "reference_text": "Mode Normal.",
            "temperature": tts_temp,
            "top_k": tts_top_k,
            "top_p": tts_top_p,
            "repetition_penalty": tts_repetition_penalty,
            "length_penalty": tts_length_penalty,
            "enable_text_splitting": "1" if tts_enable_split else "0",
            "gpt_cond_len": tts_gpt_cond_len,
            "gpt_cond_chunk_len": tts_gpt_cond_chunk_len,
            "max_ref_len": tts_max_ref_len,
            "sound_norm_refs": "1" if tts_sound_norm_refs else "0",
        }

        response = None
        used_url = ""
        last_err = ""
        attempt_notes: list[str] = []
        for idx, url_modal in enumerate(candidate_urls, start=1):
            try:
                logger.info("📤 Envoi requête vers %s... (%s/%s)", url_modal, idx, len(candidate_urls))
                if hybrid_enabled and turbo_mode and get_hybrid_rts_preset() == "fast":
                    req_timeout = (3, 35)
                else:
                    req_timeout = (5, 180) if turbo_mode else 300
                response = http_client.post(url_modal, files=files, data=data, timeout=req_timeout)
                logger.info("📥 Réponse reçue, status: %s", response.status_code)
                if response.status_code == 200:
                    used_url = url_modal
                    attempt_notes.append(f"{idx}:{short_runtime_url(url_modal, 72)}=OK")
                    break
                body = response.text[:300] if response.text else ""
                last_err = f"HTTP {response.status_code} {body}"
                attempt_notes.append(f"{idx}:{short_runtime_url(url_modal, 72)}=HTTP{response.status_code}")
                if response.status_code in (400, 404, 405):
                    response = None
                    continue
                used_url = url_modal
                break
            except Exception as exc_try:
                last_err = str(exc_try)
                attempt_notes.append(f"{idx}:{short_runtime_url(url_modal, 72)}=ERR")
                response = None
                continue

        if response is None:
            logger.error("❌ Erreur Serveur: aucune URL Modal valide. Dernière erreur: %s", last_err)
            logger.info("ℹ️ Fallback reason: ALL_MODAL_ENDPOINTS_FAILED")
            register_tts_fallback(
                "ALL_MODAL_ENDPOINTS_FAILED",
                str(last_err or ""),
                endpoint=short_runtime_url(base_url_modal, 120),
                attempts=" | ".join(attempt_notes[-6:]),
            )
            return

        if used_url and used_url != base_url_modal:
            audio_config["kommz_api_url"] = used_url
            save_settings()
            logger.info("✅ URL Modal corrigée automatiquement: %s", used_url)

        if response.status_code == 200:
            _RUNTIME["_last_xtts_activity_ts_SETTER"](time.time())
            voice_cloud_limit_state = _RUNTIME["VOICE_CLOUD_LIMIT_STATE"]
            voice_cloud_limit_state["reached"] = False
            voice_cloud_limit_state["message"] = ""
            if is_trial_voice_mode_enabled():
                used = int(audio_config.get("trial_voice_seconds_used_local", 0) or 0)
                duration = wav_duration_seconds(response.content)
                if duration <= 0:
                    duration = max(1, int(len(text.split()) / 2.2))
                used = max(0, min(1800, used + duration))
                audio_config["trial_voice_seconds_used_local"] = used
                remaining = max(0, 1800 - used)
                voice_cloud_limit_state["remaining_seconds_local"] = remaining
                voice_cloud_limit_state["message"] = f"Temps essai clonage restant: {remaining//60:02d}:{remaining%60:02d}"
                save_settings()
            try:
                if audio_config.get("save_debug_audio_files", False):
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    filename = f"debug_audio_{timestamp}.wav"
                    with open(filename, "wb") as handle:
                        handle.write(response.content)
                    logger.info("📁 Audio sauvegardé dans %s", filename)

                keep_last = int(audio_config.get("debug_audio_keep_last", 2) or 2)
                keep_last = max(0, keep_last)
                os_mod = _RUNTIME["os"]
                debug_files = [
                    fn for fn in os_mod.listdir(".")
                    if fn.startswith("debug_audio_") and fn.endswith(".wav")
                ]
                debug_files.sort(key=lambda path: os_mod.path.getmtime(path), reverse=True)
                for old_file in debug_files[keep_last:]:
                    try:
                        os_mod.remove(old_file)
                    except Exception as cleanup_exc:
                        logger.warning("Suppression debug audio échouée pour %s: %s", old_file, cleanup_exc)
            except Exception as dbg_err:
                logger.warning("⚠️ Nettoyage debug_audio ignoré: %s", dbg_err)

            yield response.content
        else:
            body = response.text[:2000] if response.text else ""
            logger.error("❌ Erreur Serveur: %s - %s", response.status_code, body[:200])
            if looks_like_cloud_trial_limit(response.status_code, body):
                msg = "Quota essai Kommz Voice atteint (30 min). Passage automatique en voix Windows."
                voice_cloud_limit_state = _RUNTIME["VOICE_CLOUD_LIMIT_STATE"]
                voice_cloud_limit_state["reached"] = True
                voice_cloud_limit_state["message"] = msg
                audio_config["trial_voice_seconds_used_local"] = 1800
                audio_config["tts_engine"] = "WINDOWS"
                save_settings()
                add_subtitle("SYSTEM >> QUOTA ESSAI VOICE ATTEINT (30 MIN)", "SYS")
                logger.warning("⚠️ %s", msg)
                logger.info("ℹ️ Fallback reason: TRIAL_QUOTA_REACHED -> WINDOWS")
                register_tts_fallback("TRIAL_QUOTA_REACHED", "quota essai 30m atteint")
            else:
                logger.info("ℹ️ Fallback reason: HTTP_%s", response.status_code)
                register_tts_fallback(
                    "HTTP_ERROR",
                    f"HTTP_{response.status_code} {body[:140]}",
                    endpoint=short_runtime_url(used_url or base_url_modal, 120),
                    http_status=response.status_code,
                    attempts=" | ".join(attempt_notes[-6:]),
                )
    except Exception as exc:
        logger.exception("❌ Erreur lors de l'envoi")
        logger.info("ℹ️ Fallback reason: EXCEPTION_DURING_KOMMZ_TTS")
        register_tts_fallback(
            "EXCEPTION_DURING_KOMMZ_TTS",
            str(exc),
            endpoint=short_runtime_url(resolve_voice_endpoint(), 120),
        )


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
        "VOICE_CLOUD_LIMIT_STATE",
        "_HTTP",
        "_build_kommz_generate_candidates",
        "_build_kommz_synthesis_candidates",
        "_get_hybrid_rts_preset",
        "_get_voice_library",
        "_gpt_style_to_xtts_ref_bytes",
        "_hybrid_style_ref_cache",
        "_is_hybrid_supported_target_lang",
        "_is_trial_voice_mode_enabled",
        "_is_turbo_mode_active",
        "_last_xtts_activity_ts_SETTER",
        "_looks_like_cloud_trial_limit",
        "_normalize_voice_library_entry",
        "_normalize_xtts_request_lang",
        "_register_tts_fallback",
        "_repair_display_text",
        "_resolve_kommz_synthesis_base",
        "_resolve_kommz_voice_endpoint",
        "_set_hybrid_fast_runtime",
        "_set_pipeline_runtime",
        "_set_voice_active_id",
        "_short_runtime_text",
        "_short_runtime_url",
        "_to_bool",
        "_wav_duration_seconds",
        "add_subtitle",
        "has_voice_license",
        "os",
        "prewarm_kommz_xtts",
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
