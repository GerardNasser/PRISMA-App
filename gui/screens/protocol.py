"""Protocol editor (versioned)."""

from __future__ import annotations

import customtkinter as ctk

from gui import theme as T
from gui.widgets import Badge, Card, Field, GhostButton, Helper, PrimaryButton


class ProtocolPanel(ctk.CTkFrame):
    def __init__(self, master, app, project, config):
        super().__init__(master, fg_color=T.PAPER)
        self.app = app
        self.project = project
        self.config = config
        self._build()

    def _build(self) -> None:
        wrap = ctk.CTkScrollableFrame(self, fg_color=T.PAPER)
        wrap.pack(fill="both", expand=True)

        head = ctk.CTkFrame(wrap, fg_color="transparent")
        head.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(head, text="Protocol", font=("SF Pro Display", 16, "bold"), text_color=T.INK).pack(side="left")
        try:
            versions = self.app.rpc.call("protocols.versions", {"project_id": self.project["id"]})["versions"]
        except Exception:
            versions = []
        Badge(head, f"v{len(versions) + 1} next", variant="muted").pack(side="right")
        Helper(wrap, "Each save creates a new version. Old versions stay queryable.").pack(anchor="w", pady=(0, 12))

        latest = None
        try:
            latest = self.app.rpc.call("protocols.latest", {"project_id": self.project["id"]})
        except Exception:
            pass
        pico = (latest or {}).get("pico") or {}

        card = Card(wrap)
        card.pack(fill="x", pady=4)
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=18, pady=14)

        self.title = Field(inner, "Title", required=True, initial=(latest or {}).get("title", ""))
        self.title.pack(fill="x", pady=(0, 10))

        self.background = Field(inner, "Background", kind="textbox", initial=(latest or {}).get("background", "") or "")
        self.background.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(inner, text="PICO(TS)", text_color=T.INK_SOFT, font=("SF Pro Text", 12, "bold")).pack(anchor="w", pady=(4, 4))
        self.pico_fields = {}
        for k, label in [
            ("P", "Population"),
            ("I", "Intervention"),
            ("C", "Comparator"),
            ("O", "Outcomes"),
            ("T", "Timing"),
            ("S", "Study design"),
        ]:
            f = Field(inner, f"{label} ({k})", initial=pico.get(k, "") or "")
            f.pack(fill="x", pady=(0, 8))
            self.pico_fields[k] = f

        self.notes = Field(inner, "Reviewer notes", kind="textbox", initial=(latest or {}).get("notes", "") or "")
        self.notes.pack(fill="x", pady=(8, 12))

        PrimaryButton(inner, "Save new version", command=self._save).pack(anchor="e")

    def _save(self) -> None:
        try:
            res = self.app.rpc.call(
                "protocols.save",
                {
                    "project_id": self.project["id"],
                    "title": self.title.get(),
                    "background": self.background.get() or None,
                    "pico": {k: f.get() or None for k, f in self.pico_fields.items()},
                    "notes": self.notes.get() or None,
                },
            )
            self.app.toast(f"Protocol saved (v{res['version']})", variant="ok")
        except Exception as e:  # noqa: BLE001
            self.app.toast("Couldn't save protocol", str(e), variant="danger")
