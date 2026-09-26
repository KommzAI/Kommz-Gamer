#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Module Overlay - Kommz Gamer V5.3
Gestion des sous-titres live (WebVTT) et des overlays (gamesense + mini HUD)
"""

from .overlay import (
    # Flask Blueprint
    overlay_bp,
    
    # Fonctions publiques
    add_subtitle,
    get_subs_buffer,
    clear_subs_buffer,
    
    # Fonctions overlay
    overlay_loop,
    
    register_scenes_runtime,

    # Fonctions HUD
    hud_default_xy,
    hud_build_window,
    hud_close_from_ui,
    get_hud_state,
)

__all__ = [
    "overlay_bp",
    "add_subtitle",
    "get_subs_buffer",
    "clear_subs_buffer",
    "overlay_loop",
    "register_scenes_runtime",
    "hud_default_xy",
    "hud_build_window",
    "hud_close_from_ui",
    "get_hud_state",
]
