#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Module overlay pour Kommz Gamer V5.3
Gère les sous-titres live (WebVTT), les overlays (gamesense + mini HUD)
et les routes Flask associées.

EXTRAIT DE vtp_core.py:
- Ligne 4186: subs_buffer global
- Lignes 10646-10675: Route /subs/live.vtt
- Lignes 10677-10691: Routes /api/set_overlay_color et /api/set_ally_color
- Lignes 4872-4955: Routes HUD (/hud_overlay/pos, /hud/config, /hud/move, /hud/status, /hud_overlay.html)
- Lignes 11112-11144: Fonction add_subtitle()
- Lignes 13812-13888: Fonction overlay_loop() (gamesense tkinter)
- Lignes 13905-14154: Mini HUD/overlay (PySide6) avec _hud_default_xy(), _hud_build_window(), _hud_close_from_ui()
"""

import time
import logging
import threading
from pathlib import Path
from typing import Any, Optional
from flask import Blueprint, Response, request, jsonify, send_from_directory

# Import des modules Kommz
from modules.config import AUDIO_CONFIG, save_settings, get_config_path

# Configuration du logger
logger = logging.getLogger(__name__)

# ============================================================================
# GLOBALS - SUBTITLE BUFFER
# ============================================================================

# Buffer de sous-titres pour live.vtt et overlay
subs_buffer: list[dict] = []

# ============================================================================
# GLOBALS - HUD/OVERLAY STATE
# ============================================================================

_HUD_TK_ROOT = None  # fenêtre PySide6 du HUD
_HUD_TK_THREAD = None  # thread PySide6
_HUD_VISIBLE = False
_HUD_QT_APP = None  # QApplication singleton
_HUD_LABELS = {}  # clé -> QLabel

# ============================================================================
# FLASK BLUEPRINT
# ============================================================================

overlay_bp = Blueprint("overlay", __name__)
_SCENES_RUNTIME: dict[str, Any] = {}

# ============================================================================
# SUBTITLE BUFFER - PUBLIC API
# ============================================================================

def add_subtitle(text: str, lang: str = "FR") -> None:
    """
    Ajoute un sous-titre au buffer pour affichage overlay et live.vtt.
    
    Args:
        text: Texte du sous-titre
        lang: Langue/source ("FR", "MOI", "ALLY", "SYS", etc.)
    
    EXTRAIT DE: vtp_core.py lignes 11112-11144
    """
    global subs_buffer
    
    if str(lang).upper() == "ALLY":
        lang = "ALLIÉ"
    
    is_user = (lang == "MOI")
    is_system = (str(lang).upper() == "SYS")
    
    # Stealth mode check (simplifié - à adapter selon besoins)
    # if _is_stealth_mode_active() and is_system and not _is_stealth_critical_message(text):
    #     return
    
    if is_user and not AUDIO_CONFIG.get("show_own_subs_active", True):
        return
    
    try:
        subs_buffer.append({
            "text": text,
            "lang": lang,
            "timestamp": time.time(),
            "is_user": is_user
        })
        if len(subs_buffer) > 10:
            subs_buffer.pop(0)
    except Exception as e:
        logger.error(f"Erreur add_subtitle: {e}")


def get_subs_buffer() -> list[dict]:
    """Retourne le buffer de sous-titres actuel."""
    return subs_buffer


def clear_subs_buffer() -> None:
    """Vide le buffer de sous-titres."""
    global subs_buffer
    subs_buffer = []


# ============================================================================
# FLASK ROUTES - SUBTITLES
# ============================================================================

@overlay_bp.route("/subs/live.vtt")
def route_live_vtt():
    """
    Génère un fichier WebVTT avec les sous-titres récents (10 dernières secondes).
    
    EXTRAIT DE: vtp_core.py lignes 10646-10675
    """
    o = ["WEBVTT", ""]
    n = time.time()
    
    # Filtre les sous-titres des 10 dernières secondes
    recent = [x for x in subs_buffer if (n - float(x.get("timestamp", 0) or 0)) < 10.0]
    
    for i, entry in enumerate(recent, start=1):
        try:
            text = entry.get("text", "")
            lang = entry.get("lang", "FR")
            is_user = entry.get("is_user", False)
            
            # Tag du locuteur
            speaker_tag = "USER" if is_user else ("ALLY" if str(lang).upper() == "ALLY" else "SYS")
            
            o.append(f"{i}")
            o.append(f"00:00:{i:02d}.000 --> 00:00:{i+1:02d}.000")
            o.append(f"[{speaker_tag}] {text}")
            o.append("")
        except Exception as e:
            logger.error(f"Erreur génération WebVTT entry: {e}")
            pass
    
    return Response("\n".join(o), mimetype="text/vtt")


@overlay_bp.route("/subs/stream")
def route_subs_stream():
    import json as _j, time as _t
    def _g():
        lk=""
        while True:
            try:
                _t.sleep(0.35); n=_t.time()
                rec=[x for x in subs_buffer if (n-float(x.get("timestamp",0)or 0))<10]
                if not rec: yield "data: {}\n\n"; continue
                last=rec[-1]; lang=str(last.get("lang","")or"")
                role="SYS" if "SYS" in lang.upper() else("USER" if last.get("is_user") else "ALLY")
                txt=str(last.get("text","")or"").strip(); key=role+"|"+txt
                if key!=lk and txt: lk=key; yield "data: "+_j.dumps({"role":role,"text":txt})+"\n\n"
                else: yield ": k\n\n"
            except GeneratorExit: break
            except: yield ": e\n\n"
    from flask import Response as _R
    r=_R(_g(),mimetype="text/event-stream")
    r.headers["Cache-Control"]="no-cache"; r.headers["X-Accel-Buffering"]="no"; return r


@overlay_bp.route('/api/set_overlay_color')
def route_set_overlay_color():
    """
    Configure la couleur de l'overlay utilisateur.
    
    EXTRAIT DE: vtp_core.py lignes 10677-10683
    """
    AUDIO_CONFIG["user_overlay_color"] = request.args.get('color', '#00FFFF')
    save_settings()
    return jsonify({"status": "ok"})


@overlay_bp.route('/api/set_ally_color')
def route_set_ally_color():
    """
    Configure la couleur de l'overlay allié.
    
    EXTRAIT DE: vtp_core.py lignes 10685-10691
    """
    AUDIO_CONFIG["ally_overlay_color"] = request.args.get('color', '#FFFF00')
    save_settings()
    return jsonify({"status": "ok"})


@overlay_bp.route("/audio/monitoring_mix/status", methods=["GET"])
def route_monitoring_mix_status():
    """V5.3: Retourne l'état du monitoring mix."""
    return jsonify({
        "ok": True,
        "enabled": bool(AUDIO_CONFIG.get("monitoring_mix_enabled", False)),
        "mic_gain": float(AUDIO_CONFIG.get("monitoring_mix_mic_gain", 0.8)),
        "game_gain": float(AUDIO_CONFIG.get("monitoring_mix_game_gain", 0.5)),
    })


# ============================================================================
# FLASK ROUTES - SCENES
# ============================================================================


def register_scenes_runtime(**deps: Any) -> None:
    required_keys = [
        "AUDIO_CONFIG",
        "_get_scene_library",
        "logger",
    ]
    missing = [key for key in required_keys if key not in deps]
    if missing:
        raise ValueError(f"register_scenes_runtime missing dependencies: {', '.join(missing)}")
    _SCENES_RUNTIME.clear()
    _SCENES_RUNTIME.update(deps)


@overlay_bp.route("/scenes/list", methods=["GET"])
def scenes_list_route():
    try:
        audio_config = _SCENES_RUNTIME["AUDIO_CONFIG"]
        get_scene_library = _SCENES_RUNTIME["_get_scene_library"]
        return jsonify({
            "ok": True,
            "scenes": get_scene_library(),
            "active_name": str(audio_config.get("scene_active_name") or ""),
            "last_applied_at": str(audio_config.get("scene_last_applied_at") or ""),
            "auto_apply": bool(audio_config.get("scene_auto_apply_enabled", False)),
            "auto_process": str(audio_config.get("scene_auto_process") or ""),
        })
    except Exception as e:
        _SCENES_RUNTIME["logger"].exception("scenes_list failed")
        return jsonify({"ok": False, "error": f"scenes_list: {str(e)}"}), 500


# ============================================================================
# FLASK ROUTES - HUD
# ============================================================================

@overlay_bp.route("/hud/config", methods=["POST"])
def route_hud_config():
    """
    Reçoit opacité + visibilité des lignes depuis index.html et les sauvegarde.
    
    EXTRAIT DE: vtp_core.py lignes 4887-4911
    """
    try:
        data = request.json or {}
        opacity = data.get("opacity")
        if opacity is not None:
            AUDIO_CONFIG["hud_opacity"] = float(opacity)
        
        rows = data.get("rows", {})
        for key, visible in rows.items():
            config_key = f"hud_row_{key}_visible"
            AUDIO_CONFIG[config_key] = bool(visible)
        
        save_settings()
        return jsonify({"status": "ok"})
    except Exception as e:
        logger.error(f"Erreur route_hud_config: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@overlay_bp.route("/hud/move", methods=["POST"])
def route_hud_move():
    """
    Déplace la fenêtre HUD tkinter à la position demandée.
    
    EXTRAIT DE: vtp_core.py lignes 4914-4931
    """
    try:
        data = request.json or {}
        x = int(data.get("x", 100))
        y = int(data.get("y", 100))
        
        global _HUD_TK_ROOT
        if _HUD_TK_ROOT:
            try:
                _HUD_TK_ROOT.move(x, y)
            except Exception as e:
                logger.error(f"Erreur déplacement HUD: {e}")
        
        return jsonify({"status": "ok"})
    except Exception as e:
        logger.error(f"Erreur route_hud_move: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@overlay_bp.route("/hud/status", methods=["GET"])
def route_hud_status():
    """V5.3: Retourne la config HUD courante pour que hud_floatant.html puisse se synchroniser."""
    return jsonify({
        "opacity":       AUDIO_CONFIG.get("hud_opacity", 85),
        "hudShowPreset": AUDIO_CONFIG.get("hudShowPreset", True),
        "hudShowRMS":    AUDIO_CONFIG.get("hudShowRMS", True),
        "hudShowSNR":    AUDIO_CONFIG.get("hudShowSNR", True),
        "hudShowFocus":  AUDIO_CONFIG.get("hudShowFocus", True),
        "hudShowUptime": AUDIO_CONFIG.get("hudShowUptime", True),
        "hudShowMic":    AUDIO_CONFIG.get("hudShowMic", True),
    })


@overlay_bp.route("/hud_overlay.html")
def route_hud_overlay():
    """Sert le HUD externe depuis le dossier web du projet ou du bundle Nuitka."""
    web_dir = Path(__file__).resolve().parents[2] / "web"
    return send_from_directory(str(web_dir), "hud_overlay.html")


# ============================================================================
# OVERLAY FUNCTIONS - GAMESENSE (TKINTER)
# ============================================================================

def overlay_loop():
    """
    Overlay gamesense avec tkinter (fenêtre transparente always-on-top).
    Affiche les sous-titres récents avec couleurs configurables.
    
    EXTRAIT DE: vtp_core.py lignes 13812-13888
    """
    try:
        import tkinter as tk
        from tkinter import font as tkfont
    except ImportError:
        logger.error("tkinter non disponible pour overlay_loop")
        return
    
    root = tk.Tk()
    root.attributes("-topmost", True)
    root.attributes("-alpha", 0.85)
    root.overrideredirect(True)
    
    # Position et taille
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    overlay_width = 800
    overlay_height = 200
    x = (screen_width - overlay_width) // 2
    y = screen_height - overlay_height - 100
    root.geometry(f"{overlay_width}x{overlay_height}+{x}+{y}")
    
    # Fond noir semi-transparent
    root.configure(bg="black")
    
    # tk.Text pour afficher les sous-titres avec couleurs par ligne
    custom_font = tkfont.Font(family="Arial", size=16, weight="bold")
    text_widget = tk.Text(
        root,
        font=custom_font,
        bg="black",
        fg="white",
        bd=0,
        highlightthickness=0,
        wrap="word",
        state="disabled",
        cursor="arrow",
    )
    text_widget.pack(expand=True, fill="both", padx=10, pady=10)

    # Définir les tags de couleur
    text_widget.tag_configure("user",  foreground=AUDIO_CONFIG.get("user_overlay_color", "#00FFFF"))
    text_widget.tag_configure("ally",  foreground=AUDIO_CONFIG.get("ally_overlay_color", "#FFFF00"))
    text_widget.tag_configure("sys",   foreground="#a855f7")   # violet pour messages système
    text_widget.tag_configure("other", foreground="#FFFFFF")

    def update_overlay():
        """Met à jour l'affichage des sous-titres récents avec couleurs par rôle."""
        try:
            n = time.time()
            # Filtre les 4 dernières secondes
            recent = [x for x in subs_buffer if (n - float(x.get("timestamp", 0) or 0)) < 4.0]

            text_widget.configure(state="normal")
            text_widget.delete("1.0", "end")

            if recent:
                # Rafraîchir les couleurs configurables à chaque tick
                text_widget.tag_configure("user", foreground=AUDIO_CONFIG.get("user_overlay_color", "#00FFFF"))
                text_widget.tag_configure("ally", foreground=AUDIO_CONFIG.get("ally_overlay_color", "#FFFF00"))

                for i, entry in enumerate(recent[-3:]):
                    txt  = str(entry.get("text", "") or "").strip()
                    lang = str(entry.get("lang", "") or "").upper()
                    is_user = bool(entry.get("is_user", False))

                    if "SYS" in lang:
                        tag = "sys"
                    elif is_user:
                        tag = "user"
                    elif "ALLY" in lang or "ALLIÉ" in lang:
                        tag = "ally"
                    else:
                        tag = "other"

                    if i > 0:
                        text_widget.insert("end", "\n")
                    text_widget.insert("end", txt, tag)

            text_widget.configure(state="disabled")
        except Exception as e:
            logger.error(f"Erreur update_overlay: {e}")

        # Rafraîchissement toutes les 100ms
        root.after(100, update_overlay)
    
    update_overlay()
    
    try:
        root.mainloop()
    except Exception as e:
        logger.error(f"Erreur overlay_loop mainloop: {e}")


# ============================================================================
# HUD FUNCTIONS - MINI OVERLAY (PYSIDE6)
# ============================================================================

def _hud_default_xy() -> tuple[int, int]:
    """
    Retourne la position sauvegardée du HUD ou une position par défaut.
    
    EXTRAIT DE: vtp_core.py lignes 13912-13923
    """
    try:
        screen_w = ctypes.windll.user32.GetSystemMetrics(0)
        screen_h = ctypes.windll.user32.GetSystemMetrics(1)
    except Exception:
        screen_w, screen_h = 1920, 1080
    try:
        x = int(AUDIO_CONFIG.get("mini_overlay_x", -1) or -1)
        y = int(AUDIO_CONFIG.get("mini_overlay_y", 40) or 40)
        if x < 0 or x > screen_w - 50:
            x = screen_w - 240
        if y < 0 or y > screen_h - 50:
            y = 40
        return (x, y)
    except Exception as e:
        logger.error(f"Erreur _hud_default_xy: {e}")
        return (screen_w - 240, 40)


def hud_default_xy() -> tuple[int, int]:
    """Alias public pour _hud_default_xy."""
    return _hud_default_xy()


def _hud_build_window():
    """
    Construit la fenêtre HUD PySide6 avec affichage temps réel des stats.
    Fenêtre transparente, draggable, always-on-top.
    
    EXTRAIT DE: vtp_core.py lignes 13926-14143
    """
    global _HUD_TK_ROOT, _HUD_VISIBLE, _HUD_QT_APP, _HUD_LABELS
    
    try:
        from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QLabel, QPushButton
        from PySide6.QtCore import Qt, QTimer, QPoint
        from PySide6.QtGui import QFont
    except ImportError:
        logger.error("PySide6 non disponible pour HUD")
        return
    
    import sys
    import requests
    
    # QApplication singleton
    if _HUD_QT_APP is None:
        _HUD_QT_APP = QApplication.instance()
        if _HUD_QT_APP is None:
            _HUD_QT_APP = QApplication(sys.argv)
    
    class HUDWindow(QWidget):
        def __init__(self):
            super().__init__()
            self.drag_position = None
            self.init_ui()
        
        def init_ui(self):
            # Configuration fenêtre
            self.setWindowFlags(
                Qt.WindowType.FramelessWindowHint |
                Qt.WindowType.WindowStaysOnTopHint |
                Qt.WindowType.Tool
            )
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            
            # Position
            x, y = _hud_default_xy()
            self.setGeometry(x, y, 300, 400)
            
            # Layout
            layout = QVBoxLayout()
            layout.setContentsMargins(10, 10, 10, 10)
            layout.setSpacing(5)
            
            # Style de base
            opacity = AUDIO_CONFIG.get("hud_opacity", 0.85)
            bg_color = f"rgba(0, 0, 0, {int(opacity * 255)})"
            
            self.setStyleSheet(f"""
                QWidget {{
                    background-color: {bg_color};
                    border-radius: 10px;
                }}
                QLabel {{
                    color: white;
                    font-size: 14px;
                    padding: 5px;
                }}
                QPushButton {{
                    background-color: rgba(255, 0, 0, 180);
                    color: white;
                    border: none;
                    border-radius: 5px;
                    padding: 5px;
                    font-size: 12px;
                }}
                QPushButton:hover {{
                    background-color: rgba(255, 50, 50, 220);
                }}
            """)
            
            # Labels pour chaque stat
            global _HUD_LABELS
            _HUD_LABELS = {}
            
            stats_keys = [
                ("preset", "Preset"),
                ("rms", "RMS"),
                ("snr", "SNR"),
                ("focus", "Focus"),
                ("uptime", "Uptime"),
                ("mic", "Micro"),
                ("listen", "Écoute"),
                ("game", "Jeu")
            ]
            
            for key, label_text in stats_keys:
                if AUDIO_CONFIG.get(f"hud_row_{key}_visible", True):
                    label = QLabel(f"{label_text}: --")
                    label.setFont(QFont("Arial", 12, QFont.Weight.Bold))
                    layout.addWidget(label)
                    _HUD_LABELS[key] = label
            
            # Bouton fermer
            close_btn = QPushButton("✕ Fermer")
            close_btn.clicked.connect(self.close_hud)
            layout.addWidget(close_btn)
            
            self.setLayout(layout)
            
            # Timer pour mise à jour des stats
            self.timer = QTimer()
            self.timer.timeout.connect(self.update_stats)
            self.timer.start(1000)  # Mise à jour toutes les secondes
        
        def update_stats(self):
            """Récupère les stats depuis /status et met à jour les labels."""
            try:
                resp = requests.get("http://127.0.0.1:5000/status", timeout=1)
                if resp.status_code == 200:
                    data = resp.json()
                    
                    # Mise à jour des labels
                    if "preset" in _HUD_LABELS:
                        preset = data.get("quality_preset", "unknown")
                        _HUD_LABELS["preset"].setText(f"Preset: {preset}")
                    
                    if "rms" in _HUD_LABELS:
                        rms = data.get("rms_db", 0)
                        _HUD_LABELS["rms"].setText(f"RMS: {rms:.1f} dB")
                    
                    if "snr" in _HUD_LABELS:
                        snr = data.get("snr_db", 0)
                        _HUD_LABELS["snr"].setText(f"SNR: {snr:.1f} dB")
                    
                    if "focus" in _HUD_LABELS:
                        focus = data.get("voice_focus_mode", "off")
                        _HUD_LABELS["focus"].setText(f"Focus: {focus}")
                    
                    if "uptime" in _HUD_LABELS:
                        uptime = data.get("uptime_seconds", 0)
                        hours = int(uptime // 3600)
                        minutes = int((uptime % 3600) // 60)
                        _HUD_LABELS["uptime"].setText(f"Uptime: {hours}h{minutes:02d}m")
                    
                    if "mic" in _HUD_LABELS:
                        mic = data.get("mic_device_name", "N/A")
                        _HUD_LABELS["mic"].setText(f"Micro: {mic[:20]}")
                    
                    if "listen" in _HUD_LABELS:
                        listen = "ON" if data.get("is_listening", False) else "OFF"
                        _HUD_LABELS["listen"].setText(f"Écoute: {listen}")
                    
                    if "game" in _HUD_LABELS:
                        game = data.get("detected_game", "N/A")
                        _HUD_LABELS["game"].setText(f"Jeu: {game[:20]}")
            except Exception as e:
                logger.error(f"Erreur update_stats HUD: {e}")
        
        def close_hud(self):
            """Ferme le HUD proprement."""
            global _HUD_VISIBLE
            _HUD_VISIBLE = False
            self.timer.stop()
            self.close()
        
        def mousePressEvent(self, event):
            """Début du drag."""
            if event.button() == Qt.MouseButton.LeftButton:
                self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        
        def mouseMoveEvent(self, event):
            """Déplacement de la fenêtre."""
            if event.buttons() == Qt.MouseButton.LeftButton and self.drag_position:
                self.move(event.globalPosition().toPoint() - self.drag_position)
        
        def mouseReleaseEvent(self, event):
            """Fin du drag - sauvegarde position."""
            if event.button() == Qt.MouseButton.LeftButton:
                pos = self.pos()
                AUDIO_CONFIG["mini_overlay_x"] = pos.x()
                AUDIO_CONFIG["mini_overlay_y"] = pos.y()
                save_settings()
                self.drag_position = None
    
    # Création et affichage de la fenêtre
    _HUD_TK_ROOT = HUDWindow()
    _HUD_TK_ROOT.show()
    _HUD_VISIBLE = True


def hud_build_window():
    """Alias public pour _hud_build_window."""
    _hud_build_window()


def _hud_close_from_ui():
    """
    Ferme le HUD proprement depuis l'UI.
    
    EXTRAIT DE: vtp_core.py lignes 14145-14154
    """
    global _HUD_TK_ROOT, _HUD_VISIBLE
    
    try:
        if _HUD_TK_ROOT:
            _HUD_TK_ROOT.close()
            _HUD_TK_ROOT = None
        _HUD_VISIBLE = False
    except Exception as e:
        logger.error(f"Erreur _hud_close_from_ui: {e}")


def hud_close_from_ui():
    """Alias public pour _hud_close_from_ui."""
    _hud_close_from_ui()


def get_hud_state() -> dict:
    """Retourne l'état actuel du HUD."""
    global _HUD_VISIBLE
    return {
        "visible": _HUD_VISIBLE,
        "enabled": AUDIO_CONFIG.get("mini_overlay_enabled", False),
        "position": _hud_default_xy()
    }
    
    
@overlay_bp.route("/hud_overlay/pos", methods=["POST"])
def route_hud_overlay_pos():
    from flask import request, jsonify
    from modules.config.config import AUDIO_CONFIG, save_settings
    try:
        data = request.get_json(silent=True) or {}
        x = int(data.get("x", -1))
        y = int(data.get("y", 40))
        AUDIO_CONFIG["mini_overlay_x"] = x
        AUDIO_CONFIG["mini_overlay_y"] = y
        save_settings()
        return jsonify({"ok": True, "x": x, "y": y})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@overlay_bp.route("/api/set_overlay_color")
def set_overlay_color_api():
    from flask import request, jsonify
    from modules.config.config import AUDIO_CONFIG, save_settings
    color = request.args.get("color")
    if color:
        AUDIO_CONFIG["user_overlay_color"] = color.strip()
        save_settings()
    return jsonify({"status": "ok", "color": AUDIO_CONFIG.get("user_overlay_color", "#00FFFF")})


@overlay_bp.route("/api/set_ally_color")
def set_ally_color_api():
    from flask import request, jsonify
    from modules.config.config import AUDIO_CONFIG, save_settings
    color = request.args.get("color")
    if color:
        AUDIO_CONFIG["ally_overlay_color"] = color.strip()
        save_settings()
    return jsonify({"status": "ok", "color": AUDIO_CONFIG.get("ally_overlay_color", "#FFFF00")})    


# ============================================================================
# MODULE INITIALIZATION
# ============================================================================

logger.info("Module overlay initialisé")
