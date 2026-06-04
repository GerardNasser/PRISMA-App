"""Projects list with create + trash toggle."""

from __future__ import annotations

import customtkinter as ctk

from gui import theme as T
from gui.widgets import Badge, Card, GhostButton, Helper, PrimaryButton, SecondaryButton


class ProjectsFrame(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color=T.PAPER)
        self.app = app
        self.show_trash = False
        self._build()
        self.refresh()

    def _build(self) -> None:
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=32, pady=(32, 16))
        left = ctk.CTkFrame(header, fg_color="transparent")
        left.pack(side="left")
        ctk.CTkLabel(left, text="Projects", font=("SF Pro Display", 22, "bold"), text_color=T.INK).pack(anchor="w")
        Helper(
            left,
            "A project is one systematic review or meta-analysis. Each project has its own "
            "field configuration, codebook, and audit trail.",
        ).pack(anchor="w", pady=(4, 0))

        right = ctk.CTkFrame(header, fg_color="transparent")
        right.pack(side="right")
        self.trash_btn = SecondaryButton(right, "Show trash", command=self._toggle_trash)
        self.trash_btn.pack(side="left", padx=(0, 8))
        PrimaryButton(right, "+ New project", command=self.app.show_new_project).pack(side="left")

        self.list_container = ctk.CTkScrollableFrame(self, fg_color=T.PAPER)
        self.list_container.pack(fill="both", expand=True, padx=32, pady=(0, 24))

    def _toggle_trash(self) -> None:
        self.show_trash = not self.show_trash
        self.trash_btn.configure(text="Showing trash" if self.show_trash else "Show trash")
        self.refresh()

    def refresh(self) -> None:
        for child in self.list_container.winfo_children():
            child.destroy()
        try:
            res = self.app.rpc.call("projects.list", {"include_trash": self.show_trash})
        except Exception as e:  # noqa: BLE001
            self.app.toast("Couldn't load projects", str(e), variant="danger")
            return
        projects = [p for p in res["projects"] if (p["deleted_at"] is not None) == self.show_trash]
        if not projects:
            empty = ctk.CTkFrame(self.list_container, fg_color="transparent")
            empty.pack(fill="x", pady=40)
            ctk.CTkLabel(
                empty,
                text="Trash is empty" if self.show_trash else "No projects yet",
                font=("SF Pro Display", 16, "bold"),
                text_color=T.INK,
            ).pack()
            ctk.CTkLabel(
                empty,
                text=(
                    "Items you delete will appear here for 30 days."
                    if self.show_trash
                    else "Create your first project to start a systematic review."
                ),
                font=T.FONT_BODY,
                text_color=T.INK_MUTE,
            ).pack(pady=(6, 0))
            return

        for p in projects:
            self._render_card(p)

    def _render_card(self, p: dict) -> None:
        card = Card(self.list_container)
        card.pack(fill="x", pady=6)
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=20, pady=14)

        top = ctk.CTkFrame(inner, fg_color="transparent")
        top.pack(fill="x")
        name = ctk.CTkLabel(
            top,
            text=p["name"],
            font=("SF Pro Display", 15, "bold"),
            text_color=T.INK,
            cursor="hand2",
        )
        name.pack(side="left")
        name.bind("<Button-1>", lambda _e, pid=p["id"]: self.app.show_project(pid))

        if self.show_trash:
            GhostButton(
                top,
                "Restore",
                command=lambda pid=p["id"]: self._restore(pid),
            ).pack(side="right")

        meta = ctk.CTkFrame(inner, fg_color="transparent")
        meta.pack(fill="x", pady=(6, 0))
        field, rtype = p["field_config_id"].split("__", 1) if "__" in p["field_config_id"] else (p["field_config_id"], "")
        Badge(meta, field, variant="info").pack(side="left", padx=(0, 6))
        ctk.CTkLabel(meta, text=rtype, text_color=T.INK_MUTE, font=T.FONT_SMALL).pack(side="left")
        ctk.CTkLabel(
            meta,
            text=f"v{p['field_config_version']} · {p['created_at'][:10]}",
            text_color=T.INK_MUTE,
            font=T.FONT_SMALL,
        ).pack(side="right")

    def _restore(self, project_id: str) -> None:
        try:
            self.app.rpc.call("projects.restore", {"project_id": project_id})
            self.app.toast("Project restored", variant="ok")
            self.refresh()
        except Exception as e:  # noqa: BLE001
            self.app.toast("Couldn't restore", str(e), variant="danger")
