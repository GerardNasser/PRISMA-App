"""PrismAPI desktop GUI — top-level shell.

Architectural note for future-me:
    All screens are constructed with their *actual* container as `master`.
    We never use `pack(in_=other)` to re-parent after-the-fact — that has
    historically led to clicks not registering because Tk's event hit-test
    walks the real widget hierarchy and gets confused when the visual parent
    differs from the actual master.

    Widget hierarchy:

        PrismAPIApp (root)
        └── container (persistent host)
            └── _shell_wrap (sidebar + content_host)   ← rebuilt per nav
                ├── side  (sidebar nav)
                └── content_host
                    └── <ScreenFrame>                  ← rebuilt per nav
"""

from __future__ import annotations

import logging
import sys

import customtkinter as ctk

from gui import theme as T
from gui.rpc_client import RpcClient
from gui.screens.onboarding import OnboardingFrame
from gui.screens.projects import ProjectsFrame
from gui.screens.new_project import NewProjectFrame
from gui.screens.project import ProjectFrame
from gui.screens.settings import SettingsFrame
from gui.widgets import Toast

log = logging.getLogger("prismapi.gui")


class PrismAPIApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        logging.basicConfig(
            level=logging.INFO,
            stream=sys.stderr,
            format="[prismapi-gui] %(levelname)s %(name)s — %(message)s",
        )
        self.title("PrismAPI")
        self.geometry("1280x820")
        self.minsize(1024, 720)
        self.configure(fg_color=T.PAPER)

        self.rpc = RpcClient()
        self.identity = self.rpc.call("identity.get")
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # Persistent container — never destroyed; we destroy and rebuild its
        # single child on each navigation.
        self.container = ctk.CTkFrame(self, fg_color=T.PAPER)
        self.container.pack(fill="both", expand=True)
        self._current: ctk.CTkFrame | None = None

        if self.identity is None:
            self.show_onboarding()
        else:
            self.show_projects()

    # ---- low-level swap ----
    def _swap_full(self, builder) -> None:
        """`builder(parent)` returns the new top-level frame (full-screen)."""
        if self._current is not None:
            self._current.destroy()
        self._current = builder(self.container)
        self._current.pack(fill="both", expand=True)

    def _swap_with_shell(self, screen_cls, **screen_kwargs) -> None:
        """Build the sidebar shell + the requested screen as a content child."""

        def _build(parent: ctk.CTkFrame) -> ctk.CTkFrame:
            wrap = ctk.CTkFrame(parent, fg_color=T.PAPER)

            side = ctk.CTkFrame(wrap, fg_color=T.PAPER_WARM, width=200)
            side.pack(side="left", fill="y")
            side.pack_propagate(False)
            self._build_sidebar(side)

            host = ctk.CTkFrame(wrap, fg_color=T.PAPER)
            host.pack(side="left", fill="both", expand=True)

            # NOTE: screen master is `host` — the real container.
            screen = screen_cls(host, self, **screen_kwargs)
            screen.pack(fill="both", expand=True)
            return wrap

        self._swap_full(_build)

    def _build_sidebar(self, side: ctk.CTkFrame) -> None:
        # Logo row
        logo_row = ctk.CTkFrame(side, fg_color="transparent")
        logo_row.pack(fill="x", padx=14, pady=(16, 12))
        ctk.CTkLabel(
            logo_row,
            text="P",
            text_color="white",
            fg_color=T.PRISM_600,
            corner_radius=8,
            width=30,
            height=30,
            font=("SF Pro Display", 15, "bold"),
        ).pack(side="left", padx=(0, 8))
        sub = ctk.CTkFrame(logo_row, fg_color="transparent")
        sub.pack(side="left")
        ctk.CTkLabel(sub, text="PrismAPI", text_color=T.INK, font=("SF Pro Text", 13, "bold")).pack(
            anchor="w"
        )
        ctk.CTkLabel(
            sub,
            text="desktop · single user",
            text_color=T.INK_MUTE,
            font=("SF Pro Text", 9),
        ).pack(anchor="w")

        # Nav items
        for label, cmd in [
            ("Projects", self.show_projects),
            ("Identity", lambda: self.show_settings("identity")),
            ("Trash", lambda: self.show_settings("trash")),
            ("Snapshots", lambda: self.show_settings("snapshots")),
        ]:
            btn = ctk.CTkButton(
                side,
                text=label,
                command=cmd,
                anchor="w",
                fg_color="transparent",
                text_color=T.INK_SOFT,
                hover_color="#e9e3d2",
                corner_radius=6,
                height=30,
                font=("SF Pro Text", 13),
            )
            btn.pack(fill="x", padx=10, pady=2)

        # Footer (signed-in-as)
        if self.identity:
            footer = ctk.CTkFrame(side, fg_color=T.PAPER_CARD, corner_radius=8)
            footer.pack(side="bottom", fill="x", padx=12, pady=12)
            ctk.CTkLabel(
                footer,
                text="Signed in as",
                text_color=T.INK_MUTE,
                font=("SF Pro Text", 9),
                anchor="w",
            ).pack(anchor="w", padx=10, pady=(8, 0))
            ctk.CTkLabel(
                footer,
                text=self.identity["display_name"],
                text_color=T.INK,
                font=("SF Pro Text", 11, "bold"),
                anchor="w",
                wraplength=170,
            ).pack(anchor="w", padx=10, pady=(2, 8))

    # ---- navigation ----
    def show_onboarding(self) -> None:
        log.info("nav: onboarding")
        self._swap_full(lambda parent: OnboardingFrame(parent, self))

    def show_projects(self) -> None:
        log.info("nav: projects")
        self._swap_with_shell(ProjectsFrame)

    def show_new_project(self) -> None:
        log.info("nav: new project")
        self._swap_with_shell(NewProjectFrame)

    def show_project(self, project_id: str) -> None:
        log.info("nav: project %s", project_id)
        self._swap_with_shell(ProjectFrame, project_id=project_id)

    def show_settings(self, tab: str = "identity") -> None:
        log.info("nav: settings/%s", tab)
        self._swap_with_shell(SettingsFrame, tab=tab)

    # ---- state ----
    def set_identity(self, identity: dict) -> None:
        self.identity = identity

    def rpc_bg(
        self,
        method: str,
        params: dict | None,
        on_done,
        on_error=None,
        widget=None,
    ) -> None:
        """Run an RPC on the background loop and deliver the result on the
        Tk main thread. Slow handlers (dedup, imports, statefile) must come
        through here — a blocking `rpc.call` freezes the whole window.

        `widget`: when given, callbacks are dropped if it was destroyed
        while the call was in flight (the user navigated away).
        """
        future = self.rpc.call_async(method, params or {})

        def _poll() -> None:
            if not future.done():
                self.after(60, _poll)
                return
            if widget is not None:
                try:
                    if not widget.winfo_exists():
                        return
                except Exception:  # noqa: BLE001
                    return
            try:
                result = future.result()
            except Exception as exc:  # noqa: BLE001
                if on_error is not None:
                    on_error(exc)
                else:
                    self.toast("Operation failed", str(exc), variant="danger")
                return
            on_done(result)

        _poll()

    def refresh_project_phases(self) -> None:
        """Re-evaluate sidebar phase locks after a mutation, if a project is open.

        Deferred with after_idle so a panel can call this from inside its own
        event handler without being destroyed mid-callback.
        """
        frame = getattr(self, "active_project_frame", None)
        if frame is None:
            return
        try:
            if frame.winfo_exists():
                frame.after_idle(frame.refresh)
        except Exception:  # noqa: BLE001 - stale frame reference after nav
            self.active_project_frame = None

    def _on_close(self) -> None:
        """Stop the background asyncio loop before tearing down Tk."""
        try:
            self.rpc.shutdown()
        except Exception:  # noqa: BLE001
            pass
        self.destroy()

    # ---- toasts ----
    def toast(self, title: str, description: str = "", variant: str = "info") -> None:
        try:
            Toast(self, title, description, variant=variant)
        except Exception as exc:  # noqa: BLE001
            log.warning("toast failed: %s", exc)
