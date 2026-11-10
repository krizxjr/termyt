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
from dbus_next.service import PropertyAccess, ServiceInterface, dbus_property, method

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

    def __init__(self, actions, set_volume, set_loop=lambda _on: None):
        super().__init__("org.mpris.MediaPlayer2.Player")
        self._actions = actions
        self._set_volume = set_volume
        self._set_loop = set_loop
        self.status = "Stopped"
        self.title = ""
        self.url = ""
        self.track_id = ""  # changes per track so plasma notices new songs
        self.volume = 1.0  # MPRIS uses 0..1; Player keeps 0..100
        self.loop_status = "Playlist"  # shown value; mutated by widget Set

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
        return False

    @Shuffle.setter
    def Shuffle(self, wrapped) -> None:
        # Shuffle isn't implemented yet; accept and remember so widget
        # toggles don't error, real shuffle is a roadmap item.
        pass

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
        return False

    @dbus_property(access=PropertyAccess.READ)
    def CanGoPrevious(self) -> "b":
        return True

    @dbus_property(access=PropertyAccess.READ)
    def CanGoNext(self) -> "b":
        return True

    @dbus_property(access=PropertyAccess.READ)
    def Position(self) -> "x":
        # Optional per spec but KMedia polls it; 0 vs not-declared is
        # the difference between "no progress bar info" and log spam.
        return 0

    @dbus_property(access=PropertyAccess.READ)
    def Metadata(self) -> "a{sv}":
        return {
            "mpris:trackid": Variant(
                "o", "/org/mpris/MediaPlayer2/track" + self.track_id
            )
            or "/org/mpris/MediaPlayer2/track/none",
            "xesam:title": Variant("s", self.title or "termyt"),
            "xesam:url": Variant("s", self.url or ""),
        }


class Reporter:
    """Owns the D-Bus thread; the Session thread only calls set_state."""

    def __init__(self, actions, set_volume, set_loop=lambda _on: None):
        self._actions = actions
        self._set_volume = set_volume
        self._set_loop = set_loop
        self._ready = threading.Event()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._bus: MessageBus | None = None
        self._player = _Player(actions, set_volume, self._set_loop)
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
        await bus.wait_for_disconnect()

    def _quit_session(self) -> None:
        self._actions.get("quit", lambda: None)()

    def set_state(
        self,
        *,
        status: str | None = None,
        title: str | None = None,
        url: str | None = None,
        volume: int | None = None,
        has_track: bool | None = None,
    ) -> None:
        """Update MPRIS-visible state from any thread."""
        if not self._alive or not self._ready.is_set():
            return
        payload = {
            "status": status,
            "title": title,
            "url": url,
            "volume": None if volume is None else max(0.0, min(1.0, volume / 100)),
            "has_track": has_track,
        }
        if self._loop:
            self._loop.call_soon_threadsafe(self._apply, payload)

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
        if payload["volume"] is not None:
            p.volume = payload["volume"]
            changed["Volume"] = p.volume
        if payload["status"] is not None:
            p.status = payload["status"]
            changed["PlaybackStatus"] = p.status
        if payload["has_track"] and payload["title"] is not None:
            changed["Metadata"] = {
                "mpris:trackid": Variant(
                    "o", "/org/mpris/MediaPlayer2/track" + (p.track_id or "/none")
                ),
                "xesam:title": Variant("s", p.title or "termyt"),
                "xesam:url": Variant("s", p.url or ""),
            }
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
