#!/usr/bin/env python3
"""
Kommz Gamer - Listen Module
Module pour les fonctionnalités d'écoute et de support
"""

from flask import Blueprint, jsonify
import time
import sys

# Import des dépendances du module config
try:
    from modules.config.config import AUDIO_CONFIG
except ImportError:
    AUDIO_CONFIG = {}

# Voice Focus V3 State (simulé pour extraction)
_voice_focus_v3_state = {
    "calibrated": False,
    "vad_threshold_adaptive": 0.5,
    "voice_target_rms": 0.1,
    "noise_floor_low": 0.01,
    "noise_floor_mid": 0.02,
    "noise_floor_high": 0.03,
    "gain_riding_ema": 0.8,
    "sibilance_threshold": 0.7,
    "click_threshold": 0.3,
    "room_decay_ema": 0.1,
    "voiceprint_centroid_ema": 1000.0,
    "voiceprint_spread_ema": 200.0,
    "voiceprint_initialized": False,
    "calibration_samples": 0,
}

# Création du blueprint pour les routes d'écoute
listen_bp = Blueprint('listen', __name__, url_prefix='/audio/listen')

# Import des routes supplémentaires depuis listen_bp.py
try:
    from .listen_bp import *
except ImportError:
    pass

@listen_bp.route("/support_links", methods=["GET"])
def get_support_links():
    """V5.2: Support links centralisés"""
    try:
        return jsonify({
            "ok": True,
            "links": {
                "discord": "https://discord.gg/kommz-gamer",
                "github_issues": "https://github.com/Kommz-Gamer/Kommz-Gamer/issues/new?template=bug_report.md",
                "github_discussions": "https://github.com/Kommz-Gamer/Kommz-Gamer/discussions",
                "patreon": "https://patreon.com/KommzInnovations",
                "docs": "https://docs.kommz.app",
            }
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500