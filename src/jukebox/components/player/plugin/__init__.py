# Copyright: 2022
# SPDX License Identifier: MIT License

import asyncio
import logging
import threading
import importlib
from typing import Optional

import jukebox.plugs as plugin
import jukebox.cfghandler
from components.player.core import PlayerCtrl
from components.player.core.player_status import PlayerStatus

from components.player.core.player_content import PlayerData


logger = logging.getLogger('jb.player')
cfg = jukebox.cfghandler.get_handler('jukebox')
cfg_player = jukebox.cfghandler.get_handler('player')

# Background event loop in a separate thread to be used by backends as needed for asyncio tasks
event_loop: asyncio.AbstractEventLoop

# The top-level player arbiter that acts as the single interface to the outside
player_arbiter: PlayerCtrl

# Player status needed for webapp
player_status: PlayerStatus

# The various backends
backends = {}


def start_event_loop(loop: asyncio.AbstractEventLoop):
    # https://docs.python.org/3/library/asyncio-eventloop.html#asyncio.loop.shutdown_asyncgens
    logger.debug("Start player AsyncIO Background Event Loop")
    try:
        loop.run_forever()
    finally:
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()


def load_backend(name: str):
    global event_loop
    global player_arbiter
    global player_status
    global backends

    backend_cfg = cfg_player.getn('players', 'backends', name, default=None)
    if backend_cfg is None:
        logger.error(f"No configuration found for player backend '{name}'")
        return

    module_name = backend_cfg.get('module')
    class_name = backend_cfg.get('class')

    if not module_name or not class_name:
        logger.error(f"Backend '{name}' configuration missing 'module' or 'class'")
        return

    try:
        logger.debug(f"Loading player backend '{name}' from {module_name}:{class_name}")
        module = importlib.import_module(module_name)
        backend_class = getattr(module, class_name)
        backend = backend_class(event_loop, player_status)
        
        backends[name] = backend
        # Register with plugin interface to call directly
        plugin.register(backend, package='player', name=name)
        player_arbiter.register(name, backend)
    except Exception as e:
        logger.error(f"Failed to load player backend '{name}': {e}")


@plugin.initialize
def initialize():
    global event_loop
    global player_arbiter
    global player_status

    jukebox.cfghandler.load_yaml(cfg_player, '../../shared/settings/player.yaml')
    # Create the event loop and start it in a background task
    # the event loop can be shared across different backends (if the backends require a async event loop)
    event_loop = asyncio.new_event_loop()
    t = threading.Thread(target=start_event_loop, args=(event_loop,), daemon=True, name='PlayerEventLoop')
    t.start()

    player_arbiter = PlayerCtrl()

    player_status = PlayerStatus()
    player_arbiter.player_status = player_status

    # ToDo: remove player_content
    # player_content = PlayerData()

    # Create and register the players (this is dynamic)
    enabled_players = cfg_player.getn('players', 'enabled', default=['mpd'])
    for p in enabled_players:
        load_backend(p)

    plugin.register(player_arbiter, package='player', name='ctrl')
    plugin.register(player_status, package='player', name='playerstatus')
    # plugin.register(player_content, package='player', name='content')


@plugin.atexit
def atexit(**ignored_kwargs):
    global event_loop
    event_loop.stop()
