"""Garde reseau du serveur local (port 8770).

Le serveur ecoute sur 0.0.0.0 pour que le telephone joigne /remote. Sans
garde, deux portes restaient ouvertes :

1. Le reseau local : toute machine du meme Wi-Fi pouvait appeler n'importe
   quelle route, y compris celles qui ecrivent la configuration (cles d'API,
   adresse du serveur de synthese), remettent le logiciel a zero ou lancent
   une mise a jour.
2. Le navigateur du joueur : CORS(app) autorise toutes les origines. Un site
   web ouvert dans le navigateur pouvait appeler http://127.0.0.1:8770, et
   la requete venant de la machine elle-meme, /status renvoyait les cles en
   clair.

Regles :
- Toute requete portant une origine etrangere est refusee. Une origine est
  acceptee si elle designe ce serveur (meme hote) ou l'une de ses adresses de
  bouclage sur le meme port. Sans en-tete Origin, une requete marquee
  `Sec-Fetch-Site: cross-site` par le navigateur est refusee aussi (image ou
  script charge par un autre site).
- Depuis le reseau local, seules les routes de la telecommande, de l'overlay
  OBS et des sous-titres repondent. Tout le reste est reserve a la machine.
"""
from __future__ import annotations

from urllib.parse import urlsplit

from flask import jsonify, request

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1", "[::1]"})
LOOPBACK_ADDRS = frozenset({"127.0.0.1", "::1", "localhost", "::ffff:127.0.0.1"})

# Routes joignables depuis une autre machine du reseau local.
LAN_ALLOWED_PREFIXES = ("/remote/",)
LAN_ALLOWED_PATHS = frozenset({
    # Telecommande mobile (web/remote.html) et ses appels.
    "/remote",
    "/status",  # masque hors de la machine, voir _redact_status_payload
    "/toggle",
    "/panic",
    "/api/set_volume",
    "/config/target",
    "/config/toggle_feature",
    "/config/gender_update",
    "/module/bypass/toggle",
    "/audio/listen/toggle",
    "/preset/cycle",
    "/kommz/xtts/warmup",
    # Overlay OBS et sous-titres, utilisables depuis un second PC de stream.
    "/overlay.html",
    "/hud_overlay.html",
    "/hud/status",
    "/subs/live.vtt",
    "/subs/stream",
    "/favicon.ico",
})


def _is_loopback_addr(addr: str) -> bool:
    return (addr or "").strip() in LOOPBACK_ADDRS


def _origin_is_ours(origin: str, port: int) -> bool:
    if not origin or origin == "null":
        return False
    try:
        parts = urlsplit(origin)
    except ValueError:
        return False
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        return False
    if parts.netloc.lower() == (request.host or "").lower():
        return True
    host = (parts.hostname or "").lower()
    return host in LOOPBACK_HOSTS and parts.port == port


def _lan_path_allowed(path: str) -> bool:
    clean = path.rstrip("/") or "/"
    return clean in LAN_ALLOWED_PATHS or any(path.startswith(p) for p in LAN_ALLOWED_PREFIXES)


def install_network_guard(app, port: int, log=print) -> None:
    refused_seen: set = set()

    def _refuse(reason: str):
        key = (reason, request.remote_addr, request.path)
        if key not in refused_seen and len(refused_seen) < 256:
            refused_seen.add(key)
            log(f"[SECURITE] requete refusee ({reason}) : {request.method} {request.path} depuis {request.remote_addr}")
        return jsonify({"error": "forbidden", "reason": reason}), 403

    @app.before_request
    def _network_guard():
        origin = request.headers.get("Origin")
        if origin is not None:
            if not _origin_is_ours(origin, port):
                return _refuse("origine etrangere")
        elif (request.headers.get("Sec-Fetch-Site") or "").lower() == "cross-site":
            return _refuse("requete d'un autre site")

        if not _is_loopback_addr(request.remote_addr or "") and not _lan_path_allowed(request.path):
            return _refuse("reserve a cette machine")
        return None
