"""Settings: identity, trash, snapshots."""

from __future__ import annotations

import customtkinter as ctk
from tkinter import simpledialog

from gui import theme as T
from gui.widgets import Badge, Card, DangerButton, Field, GhostButton, Helper, PrimaryButton, SecondaryButton


class SettingsFrame(ctk.CTkFrame):
    def __init__(self, master, app, *, tab: str = "identity"):
        super().__init__(master, fg_color=T.PAPER)
        self.app = app
        self.tab = tab
        self._build()

    def _build(self) -> None:
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", padx=32, pady=(28, 8))
        GhostButton(head, "← Projects", command=self.app.show_projects).pack(anchor="w")
        ctk.CTkLabel(head, text="Settings", font=("SF Pro Display", 22, "bold"), text_color=T.INK).pack(anchor="w", pady=(8, 0))

        tabs = ctk.CTkFrame(self, fg_color="transparent")
        tabs.pack(fill="x", padx=32, pady=(8, 0))
        for slug, label in [("identity", "Identity"), ("trash", "Trash"), ("snapshots", "Snapshots")]:
            active = slug == self.tab
            btn = ctk.CTkButton(
                tabs,
                text=label,
                command=lambda s=slug: self._set_tab(s),
                fg_color=T.PRISM_100 if active else "transparent",
                text_color=T.PRISM_700 if active else T.INK_SOFT,
                hover_color=T.PAPER_WARM,
                corner_radius=6,
                height=30,
                font=("SF Pro Text", 12, "bold"),
            )
            btn.pack(side="left", padx=(0, 6))

        self.body = ctk.CTkScrollableFrame(self, fg_color=T.PAPER)
        self.body.pack(fill="both", expand=True, padx=32, pady=12)
        self._render()

    def _set_tab(self, t: str) -> None:
        self.tab = t
        for c in self.winfo_children():
            c.destroy()
        self._build()

    def _render(self) -> None:
        if self.tab == "identity":
            self._render_identity()
        elif self.tab == "trash":
            self._render_trash()
        elif self.tab == "snapshots":
            self._render_snapshots()

    def _render_identity(self) -> None:
        idt = self.app.identity or {}
        card = Card(self.body)
        card.pack(fill="x", pady=4)
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=18, pady=14)
        Helper(inner, "Your name + ORCID/email travel with .prismaproj exports.").pack(anchor="w", pady=(0, 10))

        self.last_name = Field(inner, "Last name", required=True, initial=idt.get("last_name", ""))
        self.last_name.pack(fill="x", pady=(0, 8))
        self.orcid = Field(inner, "ORCID", initial=idt.get("orcid") or "")
        self.orcid.pack(fill="x", pady=(0, 8))
        self.email = Field(inner, "Affiliate email", initial=idt.get("email") or "")
        self.email.pack(fill="x", pady=(0, 8))
        self.institution = Field(inner, "Institution", initial=idt.get("institution") or "")
        self.institution.pack(fill="x", pady=(0, 12))
        PrimaryButton(inner, "Save", command=self._save_identity).pack(anchor="e")

    def _save_identity(self) -> None:
        try:
            idt = self.app.rpc.call(
                "identity.set",
                {
                    "last_name": self.last_name.get(),
                    "orcid": self.orcid.get() or None,
                    "email": self.email.get() or None,
                    "institution": self.institution.get() or None,
                },
            )
            self.app.set_identity(idt)
            self.app.toast("Identity saved", variant="ok")
        except Exception as e:  # noqa: BLE001
            self.app.toast("Couldn't save", str(e), variant="danger")

    def _render_trash(self) -> None:
        Helper(self.body, "Soft-deleted items, restorable for 30 days.").pack(anchor="w", pady=(0, 12))
        try:
            trash = self.app.rpc.call("trash.list", {})
        except Exception as e:  # noqa: BLE001
            Helper(self.body, f"Couldn't load trash: {e}").pack(anchor="w")
            return
        total = sum(len(rows) for rows in trash.values())
        if total == 0:
            ctk.CTkLabel(self.body, text="Trash is empty", font=("SF Pro Display", 14, "bold"), text_color=T.INK).pack(pady=30)
            return
        for kind, rows in trash.items():
            if not rows:
                continue
            card = Card(self.body)
            card.pack(fill="x", pady=4)
            inner = ctk.CTkFrame(card, fg_color="transparent")
            inner.pack(fill="x", padx=18, pady=14)
            ctk.CTkLabel(inner, text=f"{kind.title()} ({len(rows)})", font=("SF Pro Display", 13, "bold"), text_color=T.INK).pack(anchor="w")
            for r in rows:
                row = ctk.CTkFrame(inner, fg_color="transparent")
                row.pack(fill="x", pady=4)
                ctk.CTkLabel(row, text=r["summary"][:80], font=T.FONT_BODY, text_color=T.INK_SOFT, anchor="w").pack(side="left", fill="x", expand=True)
                ctk.CTkLabel(row, text=r["deleted_at"][:16].replace("T", " "), font=T.FONT_SMALL, text_color=T.INK_MUTE).pack(side="left", padx=8)
                SecondaryButton(row, "Restore", command=lambda k=kind, eid=r["id"]: self._restore(k, eid)).pack(side="right")

        DangerButton(self.body, "Empty trash…", command=self._empty_trash).pack(anchor="e", pady=12)

    def _restore(self, kind: str, eid: str) -> None:
        try:
            self.app.rpc.call("trash.restore", {"entity_type": kind, "entity_id": eid})
            self.app.toast("Restored", variant="ok")
            self._set_tab("trash")
        except Exception as e:  # noqa: BLE001
            self.app.toast("Couldn't restore", str(e), variant="danger")

    def _empty_trash(self) -> None:
        confirm = simpledialog.askstring(
            "Empty trash",
            'Type DELETE to confirm permanent deletion:',
            parent=self,
        )
        if confirm != "DELETE":
            return
        try:
            self.app.rpc.call("trash.empty", {"confirm": "DELETE"})
            self.app.toast("Trash emptied", variant="ok")
            self._set_tab("trash")
        except Exception as e:  # noqa: BLE001
            self.app.toast("Couldn't empty trash", str(e), variant="danger")

    def _render_snapshots(self) -> None:
        Helper(self.body, "Point-in-time copies of a project — auto on open, pre-import, pre-migration, plus manual.").pack(anchor="w", pady=(0, 12))
        try:
            projects = self.app.rpc.call("projects.list", {"include_trash": False})["projects"]
        except Exception as e:  # noqa: BLE001
            Helper(self.body, f"Couldn't load projects: {e}").pack(anchor="w")
            return
        if not projects:
            Helper(self.body, "No projects yet.").pack(anchor="w")
            return
        for p in projects:
            try:
                snaps = self.app.rpc.call("snapshots.list", {"project_id": p["id"]})["snapshots"]
            except Exception:
                snaps = []
            card = Card(self.body)
            card.pack(fill="x", pady=4)
            inner = ctk.CTkFrame(card, fg_color="transparent")
            inner.pack(fill="x", padx=18, pady=14)
            ctk.CTkLabel(inner, text=p["name"], font=("SF Pro Display", 13, "bold"), text_color=T.INK).pack(anchor="w")
            if not snaps:
                Helper(inner, "No snapshots yet.").pack(anchor="w", pady=(4, 0))
            else:
                for s in snaps:
                    row = ctk.CTkFrame(inner, fg_color="transparent")
                    row.pack(fill="x", pady=3)
                    Badge(row, s["kind"], variant="muted").pack(side="left", padx=(0, 6))
                    ctk.CTkLabel(row, text=s["label"], font=T.FONT_BODY, text_color=T.INK_SOFT).pack(side="left", padx=(0, 6))
                    ctk.CTkLabel(
                        row,
                        text=f"{s['created_at'][:16].replace('T', ' ')} · {s['size_bytes'] // 1024} KB",
                        font=T.FONT_SMALL,
                        text_color=T.INK_MUTE,
                    ).pack(side="right")
