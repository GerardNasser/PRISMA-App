"""De-duplication panel."""

from __future__ import annotations

import customtkinter as ctk

from gui import theme as T
from gui.widgets import Badge, Card, Helper, PrimaryButton


class DedupPanel(ctk.CTkFrame):
    def __init__(self, master, app, project):
        super().__init__(master, fg_color=T.PAPER)
        self.app = app
        self.project = project
        self._build()
        self.refresh()

    def _build(self) -> None:
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(head, text="De-duplicate", font=("SF Pro Display", 16, "bold"), text_color=T.INK).pack(side="left")
        PrimaryButton(head, "Run dedup", command=self._run).pack(side="right")
        Helper(
            self,
            "DOI → PMID → normalised title+year → fuzzy title (rapidfuzz token-set + author Jaccard + year tolerance).",
        ).pack(anchor="w", pady=(0, 12))

        self.summary = Card(self)
        self.summary.pack(fill="x", pady=(0, 8))
        self.summary_inner = ctk.CTkFrame(self.summary, fg_color="transparent")
        self.summary_inner.pack(fill="x", padx=18, pady=14)

        self.list_wrap = ctk.CTkScrollableFrame(self, fg_color=T.PAPER, height=400)
        self.list_wrap.pack(fill="both", expand=True)

    def _run(self) -> None:
        try:
            self.app.rpc.call("dedup.run", {"project_id": self.project["id"]})
            self.app.toast("Dedup complete", variant="ok")
            self.refresh()
        except Exception as e:  # noqa: BLE001
            self.app.toast("Dedup failed", str(e), variant="danger")

    def refresh(self) -> None:
        for c in self.summary_inner.winfo_children():
            c.destroy()
        for c in self.list_wrap.winfo_children():
            c.destroy()
        try:
            clusters = self.app.rpc.call("dedup.clusters.list", {"project_id": self.project["id"]})["clusters"]
        except Exception as e:  # noqa: BLE001
            Helper(self.summary_inner, f"Couldn't load clusters: {e}").pack(anchor="w")
            return
        ctk.CTkLabel(
            self.summary_inner,
            text=f"{len(clusters)} cluster{'s' if len(clusters) != 1 else ''}",
            font=("SF Pro Display", 14, "bold"),
            text_color=T.INK,
        ).pack(anchor="w")
        Helper(self.summary_inner, "Each cluster represents one study; sizes >1 mean duplicates were folded in.").pack(anchor="w", pady=(2, 0))
        for c in clusters:
            row = Card(self.list_wrap)
            row.pack(fill="x", pady=3)
            inner = ctk.CTkFrame(row, fg_color="transparent")
            inner.pack(fill="x", padx=14, pady=8)
            title = c["members"][0]["title"] if c["members"] else "(no title)"
            ctk.CTkLabel(inner, text=title, font=T.FONT_BODY, text_color=T.INK, anchor="w").pack(side="left", fill="x", expand=True)
            Badge(inner, f"size {c['size']}", variant="muted").pack(side="right", padx=4)
            Badge(inner, c["method"], variant="info").pack(side="right", padx=4)
