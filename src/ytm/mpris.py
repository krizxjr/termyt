"""MPRIS desktop integration — the song shows up in KDE's media widget.

What "MPRIS" is: the standard FreeDesktop interface a media player exposes
on the user's *session D-Bus* (an OS-wide message bus) so any desktop
shell can discover it, read title/status, and send commands
(play/pause/next) without touching the app.

Architecture:
- D-Bus wants an asyncio event loop; our main loop is a blocking key
  listener. So a dedicated daemon thread runs its own asyncio loop,
  connects to the session bus, and exports two interfaces (root
  "org.mpris.MediaPlayer2" and ".Player").
- The UI thread never touches dbus-next objects (not thread-safe):
  `set_state` hands updates to the loop via `loop.call_soon_threadsafe`.
- Widget -> player direction (@method handlers run *inside* the loop
  thread) must not block it: each action is spawned as a small daemon
  thread that does the real work.
- If the bus name is taken (a second ytm instance), that instance just
  runs without desktop controls — the normal MPRIS convention.
"""

# Note: no `from __future__ import annotations` here — dbus-next reads the
# annotations of decorated methods/properties as raw D-Bus signatures and
# needs the plain None annotation for "no return value".
import asyncio
import threading
from typing import Callable

from dbus_next import Variant
from dbus_next.aio import MessageBus
from dbus_next.service import PropertyAccess, ServiceInterface, dbus_property, method, signal

BUS_NAME = "org.mpris.MediaPlayer2.termyt"
PATH = "/org/mpris/MediaPlayer2"


def _object_path_escape(s: str) -> str:
    """Fold arbitrary text into legal ObjectPath characters (letters,
    digits, '/'). Used for per-track ids so a bad title can't produce an
    invalid MPRIS path."""
    return "/" + "".join(c if c.isalnum() else "_" for c in s)[:200]


class _Root(ServiceInterface):
    """App-level interface; the manifest of what the player offers."""

    def __init__(self, on_quit: Callable[[], None]) -> None:
        super().__init__("org.mpris.MediaPlayer2")
        self._on_quit = on_quit

    @method()
    def Raise(self) -> None:
        pass  # a terminal app has no window to raise

    @method()
    def Quit(self) -> None:
        threading.Thread(target=self._on_quit, daemon=True).start()

    @dbus_property(access=PropertyAccess.READ)
    def CanQuit(self) -> "b":
        return True

    @dbus_property(access=PropertyAccess.READ)
    def CanRaise(self) -> "b":
        return False

    @dbus_property(access=PropertyAccess.READ)
    def CanSetFullscreen(self) -> "b":
        return False

    @dbus_property(access=PropertyAccess.READ)
    def HasTrackList(self) -> "b":
        return False

    @dbus_property(access=PropertyAccess.READ)
    def Identity(self) -> "s":
        return "termyt"

    @dbus_property(access=PropertyAccess.READ)
    def SupportedMimeTypes(self) -> "as":
        return []

    @dbus_property(access=PropertyAccess.READ)
    def SupportedUriSchemes(self) -> "as":
        return []


class _Player(ServiceInterface):
    """The playback interface: editable properties for the shell to read,
    methods for it to call. All mutations happen on the loop thread."""

    def __init__(self, actions, set_volume, set_loop=lambda _on: None,
                 set_shuffle=lambda _on: None, get_position=lambda: None,
                 seek_rel=lambda _secs: False, seek_to=lambda _secs: False):
        super().__init__("org.mpris.MediaPlayer2.Player")
        self._actions = actions
        self._set_volume = set_volume
        self._set_loop = set_loop
        self._set_shuffle = set_shuffle
        self._get_position = get_position
        self._seek_rel = seek_rel
        self._seek_to = seek_to
        self.status = "Stopped"
        self.title = ""
        self.url = ""
        self.duration = 0.0  # seconds; drives mpris:length (bar scale)
        self.track_id = ""  # changes per track so plasma notices new songs
        self.volume = 1.0  # MPRIS uses 0..1; Player keeps 0..100
        self.loop_status = "Playlist"  # shown value; mutated by widget Set
        self.shuffle_flag = False  # shown value; mutated by widget Set / key z

    def _run(self, action: str) -> None:
        fn = self._actions.get(action)
        if fn is not None:  # entered from the loop thread; do the real work
            # on a side thread so a slow yt-dlp resolve never stalls the bus
            threading.Thread(target=fn, daemon=True).start()

    @method()
    def Play(self) -> None:
        self._run("play")

    @method()
    def Pause(self) -> None:
        self._run("pause")

    @method()
    def PlayPause(self) -> None:
        self._run("toggle")

    @method()
    def Next(self) -> None:
        self._run("next")

    @method()
    def Previous(self) -> None:
        self._run("previous")

    @method()
    def Stop(self) -> None:
        self._run("stop")

    @dbus_property(access=PropertyAccess.READ)
    def PlaybackStatus(self) -> "s":
        return self.status

    @dbus_property(access=PropertyAccess.READWRITE)
    def LoopStatus(self) -> "s":
        # Writable because the media widget's repeat button does a
        # property Set here; read-only made it silently fail as a
        # "the property is readonly" bus error.
        return self.loop_status

    @LoopStatus.setter
    def LoopStatus(self, status) -> None:
        # dbus-next hands setters the already-unwrapped python value.
        status = str(status)
        self.loop_status = status
        self.emit_properties_changed({"LoopStatus": status})
        # "None" = no loop, anything else ("Playlist"/"Track") = loop;
        # only "None" vs on matters to our simple queue logic.
        threading.Thread(
            target=self._set_loop, args=(status != "None",), daemon=True
        ).start()

    @dbus_property(access=PropertyAccess.READWRITE)
    def Shuffle(self) -> "b":
        return self.shuffle_flag

    @Shuffle.setter
    def Shuffle(self, value) -> None:
        # dbus-next hands setters the already-unwrapped python value.
        self.shuffle_flag = bool(value)
        self.emit_properties_changed({"Shuffle": self.shuffle_flag})
        threading.Thread(
            target=self._set_shuffle, args=(self.shuffle_flag,), daemon=True
        ).start()

    @dbus_property(access=PropertyAccess.READ)
    def Rate(self) -> "d":
        return 1.0

    @dbus_property(access=PropertyAccess.READ)
    def MaximumRate(self) -> "d":
        return 1.0

    @dbus_property(access=PropertyAccess.READ)
    def MinimumRate(self) -> "d":
        return 1.0

    @dbus_property(access=PropertyAccess.READWRITE)
    def Volume(self) -> "d":
        return self.volume

    @Volume.setter
    def Volume(self, value) -> None:
        # dbus-next hands setters the already-unwrapped python value.
        self.volume = max(0.0, min(1.0, float(value)))
        self.emit_properties_changed({"Volume": self.volume})
        threading.Thread(
            target=self._set_volume, args=(round(self.volume * 100),), daemon=True
        ).start()

    @dbus_property(access=PropertyAccess.READ)
    def CanControl(self) -> "b":
        return True

    @dbus_property(access=PropertyAccess.READ)
    def CanPlay(self) -> "b":
        return True

    @dbus_property(access=PropertyAccess.READ)
    def CanPause(self) -> "b":
        return True

    @dbus_property(access=PropertyAccess.READ)
    def CanSeek(self) -> "b":
        return True

    @dbus_property(access=PropertyAccess.READ)
    def CanGoPrevious(self) -> "b":
        return True

    @dbus_property(access=PropertyAccess.READ)
    def CanGoNext(self) -> "b":
        return True

    @dbus_property(access=PropertyAccess.READ)
    def Position(self) -> "x":
        # Live read through the mpv IPC socket; microseconds per MPRIS.
        pos = self._get_position()
        return int(pos * 1_000_000) if pos is not None else 0

    @signal("Seeked")
    def Seeked(self, position: "x") -> None:
        """Emitted after a seek lands; the widget resnaps its bar."""

    @method()
    def Seek(self, offset: "x") -> None:
        seconds = offset / 1_000_000
        threading.Thread(
            target=self._seek_rel, args=(seconds,), daemon=True
        ).start()

    @method()
    def SetPosition(self, track_id: "o", position: "x") -> None:
        seconds = position / 1_000_000
        threading.Thread(
            target=self._seek_to, args=(seconds,), daemon=True
        ).start()

    @dbus_property(access=PropertyAccess.READ)
    def Metadata(self) -> "a{sv}":
        metadata = {
            "mpris:trackid": Variant(
                "o", "/org/mpris/MediaPlayer2/track" + self.track_id
            )
            or "/org/mpris/MediaPlayer2/track/none",
            "xesam:title": Variant("s", self.title or "termyt"),
            "xesam:url": Variant("s", self.url or ""),
        }
        if self.duration and self.duration > 0:
            metadata["mpris:length"] = Variant(
                "x", int(self.duration * 1_000_000)
            )
        return metadata


class Reporter:
    """Owns the D-Bus thread; the Session thread only calls set_state."""

    def __init__(self, actions, set_volume, set_loop=lambda _on: None,
                 set_shuffle=lambda _on: None, get_position=lambda: None,
                 seek_rel=lambda _secs: False, seek_to=lambda _secs: False):
        self._actions = actions
        self._set_volume = set_volume
        self._set_loop = set_loop
        self._set_shuffle = set_shuffle
        self._get_position = get_position
        self._seek_rel = seek_rel
        self._seek_to = seek_to
        self._ready = threading.Event()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._bus: MessageBus | None = None
        self._player = _Player(actions, set_volume, self._set_loop,
                               self._set_shuffle, self._get_position,
                               self._seek_rel, self._seek_to)
        self._thread = threading.Thread(target=self._run_bus, daemon=True)
        self._thread.start()
        if not self._ready.wait(timeout=5):
            raise RuntimeError("MPRIS: no reply from the session bus")
        self._alive = self._bus is not None

    def _run_bus(self) -> None:
        asyncio.run(self._bus_main())

    async def _bus_main(self) -> None:
        try:
            self._loop = asyncio.get_running_loop()
            bus = await MessageBus().connect()
            self._bus = bus
            bus.export(PATH, _Root(self._quit_session))
            bus.export(PATH, self._player)
            await bus.request_name(BUS_NAME)  # queues if another ytm owns it
        except Exception:
            # no session bus (SSH, headless login) is survivable
            self._bus = None
            self._ready.set()
            return
        self._ready.set()
        # The loop must live as long as the service does: exiting this
        # coroutine would let asyncio.run() close the loop — and the bus
        # socket with it (that was the smoke-test bug: name registered,
        # then instantly "recipient disconnected").
        asyncio.create_task(self._position_poller())
        await bus.wait_for_disconnect()

    def _quit_session(self) -> None:
        self._actions.get("quit", lambda: None)()

    async def _position_poller(self) -> None:
        """Emit Position periodically so widget bars move without polling.

        Reads happen off the loop thread (asyncio.to_thread) because the
        IPC socket call can block for up to the socket timeout.
        """
        while True:
            await asyncio.sleep(2.0)
            if self._player.status != "Playing":
                continue
            pos = await asyncio.to_thread(self._get_position)
            if pos is not None:
                self._player.emit_properties_changed(
                    {"Position": int(pos * 1_000_000)}
                )

    def note_seeked(self) -> None:
        """Tell widgets the bar moved (seek from the terminal side)."""
        if not (self._alive and self._loop):
            return
        pos = self._get_position()
        try:
            self._loop.call_soon_threadsafe(
                self._player.Seeked,
                int((pos or 0) * 1_000_000),
            )
        except RuntimeError:
            pass

    def set_state(
        self,
        *,
        status: str | None = None,
        title: str | None = None,
        url: str | None = None,
        duration: float | None = None,
        volume: int | None = None,
        has_track: bool | None = None,
        shuffle: bool | None = None,
    ) -> None:
        """Update MPRIS-visible state from any thread."""
        if not self._alive or not self._ready.is_set():
            return
        payload = {
            "status": status,
            "title": title,
            "url": url,
            "duration": duration,
            "volume": None if volume is None else max(0.0, min(1.0, volume / 100)),
            "has_track": has_track,
            "shuffle": shuffle,
        }
        if self._loop:
            try:
                self._loop.call_soon_threadsafe(self._apply, payload)
            except RuntimeError:
                # Loop already closed (quit raced a widget action); the
                # desktop side simply doesn't get this update.
                self._alive = False

    def _apply(self, payload: dict) -> None:
        if not self._bus:
            return
        p = self._player
        changed: dict[str, object] = {}
        if payload["has_track"] and payload["title"] is not None:
            p.title = payload["title"]
            p.track_id = _object_path_escape(payload["url"] or "/none")
        if payload["url"]:
            p.url = payload["url"]
        if payload["duration"] is not None:
            p.duration = payload["duration"]
        if payload["volume"] is not None:
            p.volume = payload["volume"]
            changed["Volume"] = p.volume
        if payload["shuffle"] is not None:
            p.shuffle_flag = bool(payload["shuffle"])
            changed["Shuffle"] = p.shuffle_flag
        if payload["status"] is not None:
            p.status = payload["status"]
            changed["PlaybackStatus"] = p.status
        if payload["has_track"] and payload["title"] is not None:
            metadata = {
                "mpris:trackid": Variant(
                    "o", "/org/mpris/MediaPlayer2/track" + (p.track_id or "/none")
                ),
                "xesam:title": Variant("s", p.title or "termyt"),
                "xesam:url": Variant("s", p.url or ""),
            }
            if p.duration and p.duration > 0:
                # Widgets won't draw a seek bar without a track length.
                metadata["mpris:length"] = Variant("x", int(p.duration * 1_000_000))
            changed["Metadata"] = metadata
        if changed:
            # Official emissions API for read-only properties: mutates only
            # plain fields above, then signals clients in one message.
            p.emit_properties_changed(changed)

    def stop(self) -> None:
        if not (self._bus and self._loop):
            return
        try:
            self._loop.call_soon_threadsafe(self._shutdown_async)
        except RuntimeError:
            pass  # loop already closed (bus died on its own)

    def _shutdown_async(self) -> None:
        """Runs on the loop thread: unexport, then disconnect, which makes
        wait_for_disconnect() return and the loop close cleanly."""
        if self._bus is not None:
            asyncio.create_task(self._do_shutdown())

    async def _do_shutdown(self) -> None:
        try:
            if self._bus is not None:
                self._bus.unexport(PATH)
                await self._bus.disconnect()
        except Exception:
            pass
