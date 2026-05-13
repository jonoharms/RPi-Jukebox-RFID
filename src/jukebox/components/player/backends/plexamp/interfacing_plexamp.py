import logging
import asyncio
from typing import Optional
from plexapi.server import PlexServer
from plexapi.exceptions import NotFound

import jukebox.cfghandler
import jukebox.plugs as plugin
from components.player.backends import BackendPlayer, auto_update_status

logger = logging.getLogger('jb.plexamp')
cfg = jukebox.cfghandler.get_handler('player')


class PlexampBackend(BackendPlayer):
    def __init__(self, event_loop, player_status):
        self.loop = event_loop
        self.player_status = player_status
        
        # Load configuration
        self.server_url = cfg.setndefault('plexamp', 'server_url', value='http://localhost:32400')
        self.token = cfg.setndefault('plexamp', 'token', value='')
        self.client_name = cfg.setndefault('plexamp', 'client_name', value='phoniebox')
        
        self.server = None
        self.client = None
        self._connected = False
        
        # Connect to Plex Server
        self.connect()

    def connect(self):
        try:
            self.server = PlexServer(self.server_url, self.token)
            self.client = self.server.client(self.client_name)
            self._connected = True
            logger.info(f"Connected to Plex Server and client '{self.client_name}'")
        except Exception as e:
            logger.error(f"Failed to connect to Plex: {e}")
            self._connected = False

    def _check_connection(self):
        if not self._connected or self.client is None:
            self.connect()
        return self._connected

    def update_status(self):
        if not self._check_connection():
            return
        
        try:
            # Plex clients don't always push status, we often have to query the timeline
            timeline = self.client.timeline
            if not timeline:
                return

            status_map = {
                'playing': timeline.state == 'playing',
                'duration': float(timeline.duration or 0) / 1000.0,
                'elapsed': float(timeline.time or 0) / 1000.0,
                'title': timeline.title or '',
                'artist': timeline.grandparentTitle or '',  # Album Artist usually
                'album': timeline.parentTitle or '',
                'trackid': str(timeline.ratingKey or ''),
                'player': 'plexamp'
            }
            self.player_status.update(**status_map)
        except Exception as e:
            logger.debug(f"Failed to update Plexamp status: {e}")

    @plugin.tag
    def status(self):
        self.update_status()
        return self.player_status.status()

    @auto_update_status
    def next(self):
        if self._check_connection():
            self.client.skipNext()

    @auto_update_status
    def prev(self):
        if self._check_connection():
            self.client.skipPrevious()

    @auto_update_status
    def play(self):
        if self._check_connection():
            self.client.play()

    @auto_update_status
    def stop(self):
        if self._check_connection():
            self.client.stop()

    @auto_update_status
    def pause(self):
        if self._check_connection():
            self.client.pause()

    @auto_update_status
    def toggle(self):
        if self._check_connection():
            self.client.playPause()

    @auto_update_status
    def play_uri(self, uri: str, **kwargs):
        if not self._check_connection():
            return

        # Expected URI format: plexamp:url:https://listen.plex.tv/album/...
        if not uri.startswith("plexamp:url:"):
            logger.error(f"Unsupported URI format for Plexamp: {uri}")
            return

        url = uri.replace("plexamp:url:", "")
        try:
            # Simple URL parsing to find the item
            # Example: https://listen.plex.tv/album/5d9c66fc000c82003f905206
            # We can use server.fetchItem if we have the ratingKey or search
            logger.info(f"Parsing Plexamp URL: {url}")
            
            # For now, let's try a generic search or fetch if it's a numeric ID
            # In a production version, we'd want more robust URL-to-item resolution
            parts = url.split('/')
            item_id = parts[-1]
            
            item = None
            try:
                # Try to fetch by ratingKey if it's numeric
                item = self.server.fetchItem(int(item_id))
            except (ValueError, NotFound):
                # Fallback to GUID search or other methods
                logger.warning(f"Could not fetch item by ID {item_id}, advanced URL resolution needed.")
            
            if item:
                self.client.playMedia(item)
                logger.info(f"Started playback of {item.title}")
            else:
                logger.error(f"Could not resolve Plexamp item from URL: {url}")

        except Exception as e:
            logger.error(f"Error playing Plexamp URI: {e}")

    @auto_update_status
    def play_single(self, uri):
        self.play_uri(f"plexamp:url:{uri}")

    @auto_update_status
    def play_album(self, albumartist, album):
        # We can implement a search here
        if not self._check_connection():
            return
        try:
            results = self.server.search(album, libtype='album')
            for a in results:
                if a.artist().title.lower() == albumartist.lower():
                    self.client.playMedia(a)
                    return
        except Exception as e:
            logger.error(f"Error playing album {album}: {e}")

    def play_folder(self, folder: str, recursive: bool):
        pass

    def shuffle(self, option: str = 'toggle'):
        if not self._check_connection():
            return
        # Plex handles shuffle via setParameters
        current = self.client.timeline.shuffle if self.client.timeline else 0
        new_state = 1 if current == 0 else 0
        self.client.setParameters(shuffle=new_state)

    def repeat(self, option: str = 'toggle'):
        if not self._check_connection():
            return
        # 0=off, 1=track, 2=all
        self.client.setParameters(repeat=1) # Simple toggle for now

    def seek(self, new_time):
        if self._check_connection():
            # offset in ms
            self.client.seekTo(int(float(new_time) * 1000))

    def get_queue(self):
        return []

    def get_albums(self):
        return []

    def get_single_coverart(self, song_url):
        return None

    def get_album_coverart(self):
        return None

    def list_dirs(self):
        return []

    def get_song_by_url(self, song_url):
        return None

    def get_folder_content(self, folder):
        return []
