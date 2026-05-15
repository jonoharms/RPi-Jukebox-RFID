import logging
import asyncio
from typing import Optional
from urllib import parse
from plexapi.server import PlexServer
from plexapi.client import PlexClient
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
        self.client_url = cfg.setndefault('plexamp', 'client_url', value='http://localhost:32500')
        self.client_name = cfg.setndefault('plexamp', 'client_name', value='phoniebox')
        
        
        self.server = None
        self.client = None
        self._connected = False
        
        # Connect to Plex Server
        self.connect()

    def connect(self):
        try:
            self.server = PlexServer(self.server_url, token=self.token)
            self.client = PlexClient(server=self.server, baseurl=self.client_url, token=self.token)
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
            item = self.server.fetchItem(timeline.key)
            status_map = {
                'playing': timeline.state == 'playing',
                'duration': float(timeline.duration or 0) / 1000.0,
                'elapsed': float(timeline.time or 0) / 1000.0,
                'title': item.title or '',
                'albumartist': item.grandparentTitle or '',
                'artist': item.grandparentTitle or '',
                'album': item.parentTitle or '',
                'trackid': str(timeline.ratingKey or ''),
                'player': 'plexamp', 
                'file': item.locations or '',
                'coverArt': item.posterUrl or '',
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
            if self.status()["playing"]:
                self.client.pause()
            else:
                self.client.play()

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
            logger.info(f"Parsing Plexamp URL: {url}")
            parsed_url = parse.urlsplit(parse.unquote(url))

            query_dict = parse.parse_qs(parsed_url.query)
            nested_link = query_dict["uri"][0]
            parsed = parse.urlsplit(nested_link)
            server_uuid = parsed.netloc
            metadata_key = parsed.path.replace("/com.plexapp.plugins.library", "") 

            logger.info(f"Parsed metadata path: {metadata_key}")
            item = self.server.fetchItem(metadata_key)
            if item:
                self.client.playMedia(item)
                logger.info(f"Started playback of {item.title}")
            else:
                logger.error(f"Could not resolve Plexamp item from URL: {url}")

        except Exception as e:
            logger.error(f"Error playing Plexamp URI: {e}")

    @auto_update_status
    def play_single(self, uri, **kwargs):
        self.play_uri(f"plexamp:url:{uri}", **kwargs)

    @auto_update_status
    def play_album(self, albumartist, album, **kwargs):
        # We can implement a search here
        if not self._check_connection():
            return
        try:
            results = self.server.search(album, mediatype='album')
            for a in results:
                if a.artist().title.lower() == albumartist.lower():
                    self.client.playMedia(a)
                    return
        except Exception as e:
            logger.error(f"Error playing album {album}: {e}")

    def play_folder(self, folder: str, recursive: bool, **kwargs):
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

    # -----------------------------------------------------
    # Queue / URI state  (save + restore e.g. random, resume, ...)

    def save_state(self):
        """Save the configuration and state of the current URI playback to the URIs state file"""
        pass

    def _restore_state(self):
        """
        Restore the configuration state and last played status for current active URI
        """
        pass

    def decode_card(self, card_id: str, card_data: Optional[str]):
        if card_data and 'listen.plex.tv' in card_data:
            logger.info(f"Recognized Plex URL on card: {card_data}")
            return {
                'package': 'player',
                'plugin': 'ctrl',
                'method': 'play_uri',
                'args': [f"plexamp:url:{card_data}"],
                'kwargs': {},
                'ignore_same_id_delay': False
            }
        return None
