"""
Module de configuration pour KommzGamer V5.4

Ce module centralise toute la gestion de la configuration :
- AUDIO_CONFIG : dictionnaire principal de configuration
- Fonctions de sauvegarde/chargement : save_settings(), load_settings()
- Constantes d'édition : COMMUNITY_EDITION, CLOUD_FEATURES_ENABLED
- Constantes d'API : LICENSE_API_URL, etc.
"""

from flask import Blueprint, Response
import requests
from urllib.parse import urlsplit

# Création du blueprint pour les routes de configuration
config_bp = Blueprint('config', __name__, url_prefix='/update')

from .config import (
    # Constantes d'édition
    EDITION_PROFILE,
    COMMUNITY_EDITION,
    CLOUD_FEATURES_ENABLED,

    # Helpers de réparation/normalisation
    _repair_display_text,
    _repair_payload_strings,

    # URLs par défaut
    DEFAULT_KOMMZ_VOICE_URL,
    DEFAULT_KOMMZ_SYNTHESIS_URL,
    DEFAULT_KOMMZ_WHISPER_URL,
    DEFAULT_KOMMZ_HEALTH_URL,
    DEFAULT_KOMMZ_WARMUP_URL,

    # Configuration principale
    AUDIO_CONFIG,
    CONFIG_FILE,

    # Fonctions de gestion
    save_settings,
    load_settings,
    get_config_path,

    # Constantes d'API de licence
    LICENSE_API_URL,
    LICENSE_API_CONNECT_TIMEOUT,
    LICENSE_API_READ_TIMEOUT,
    LICENSE_API_RETRIES,
    LICENSE_ACTIVATE_CONNECT_TIMEOUT,
    LICENSE_ACTIVATE_READ_TIMEOUT,
    LICENSE_ACTIVATE_RETRIES,
    EMAIL_RE,
)

__all__ = [
    "EDITION_PROFILE",
    "COMMUNITY_EDITION",
    "CLOUD_FEATURES_ENABLED",
    "_repair_display_text",
    "_repair_payload_strings",
    "DEFAULT_KOMMZ_VOICE_URL",
    "DEFAULT_KOMMZ_SYNTHESIS_URL",
    "DEFAULT_KOMMZ_WHISPER_URL",
    "DEFAULT_KOMMZ_HEALTH_URL",
    "DEFAULT_KOMMZ_WARMUP_URL",
    "AUDIO_CONFIG",
    "CONFIG_FILE",
    "save_settings",
    "load_settings",
    "get_config_path",
    "LICENSE_API_URL",
    "LICENSE_API_CONNECT_TIMEOUT",
    "LICENSE_API_READ_TIMEOUT",
    "LICENSE_API_RETRIES",
    "LICENSE_ACTIVATE_CONNECT_TIMEOUT",
    "LICENSE_ACTIVATE_READ_TIMEOUT",
    "LICENSE_ACTIVATE_RETRIES",
    "EMAIL_RE",
]


@config_bp.route("/changelog", methods=["GET"])
def update_changelog():
    from flask import request
    url = (request.args.get("url") or "").strip()
    if not url:
        return jsonify({"ok": False, "error": "URL du changelog indisponible"}), 400
    try:
        parts = urlsplit(url)
        if parts.scheme not in {"http", "https"}:
            return jsonify({"ok": False, "error": "URL du changelog invalide"}), 400
        r = requests.get(
            url,
            timeout=(8, 20),
            headers={
                "User-Agent": "KommzGamer/5.4",
                "Accept": "text/plain, text/markdown;q=0.9, text/html;q=0.5, */*;q=0.1",
            },
            allow_redirects=True,
        )
        r.raise_for_status()
        txt = r.text or ""
        if not txt.strip():
            return jsonify({"ok": False, "error": "Changelog vide"}), 502
        return Response(txt[:40000], content_type="text/plain; charset=utf-8")
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 502


@config_bp.route("/update/open-download", methods=["POST"])
def open_update_download():
    from flask import jsonify
    import webbrowser
    import vtp_core as core
    url = (core.UPDATE_STATE.get("download_url") or "").strip()
    if not url:
        return jsonify({"ok": False, "error": "URL de téléchargement indisponible"}), 400
    try:
        webbrowser.open(url)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@config_bp.route("/update/install", methods=["POST"])
def install_update():
    from flask import jsonify
    import threading
    import vtp_core as core
    if core.UPDATE_STATE.get("installing"):
        return jsonify({"ok": False, "error": "Installation déjà en cours"}), 409
    url = (core.UPDATE_STATE.get("download_url") or "").strip()
    if not url:
        return jsonify({"ok": False, "error": "Aucune URL de mise à jour disponible"}), 400
    threading.Thread(target=core._install_update_background, daemon=True).start()
    return jsonify({"ok": True, "message": "Mise à jour démarrée"})