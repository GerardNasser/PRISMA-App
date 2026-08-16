"""Project page with sidebar nav over phases."""

from __future__ import annotations

import customtkinter as ctk

from gui import theme as T
from gui.screens.codebook import CodebookPanel
from gui.screens.dedup import DedupPanel
from gui.screens.extraction import ExtractionPanel
from gui.screens.protocol import ProtocolPanel
from gui.screens.rob import RoBPanel
from gui.screens.screening import ScreeningPanel
from gui.screens.search import SearchPanel
from gui.screens.share import SharePanel
from gui.widgets import Badge, Card, GhostButton, Helper

PHASES = [
    ("overview", "Overview"),
    ("protocol", "Protocol"),
    ("codebook", "Codebook"),
    ("search", "Search"),
    ("dedup", "De-duplicate"),
    ("screening", "Title/abstract"),
    ("fulltext", "Full text"),
    ("extraction", "Extraction"),
    ("rob", "Risk of bias"),
    ("share", "Share / import"),
]


# Sidebar slug -> domain Phase id (from prismapi.domain.phases.Phase values).
# Slugs without a phase mapping are always open (e.g., overview, share).
SLUG_TO_PHASE: dict[str, str] = {
    "protocol": "protocol",
    "codebook": "codebook",
    "search": "import",
    "dedup": "dedup",
    "screening": "title_abstract",
    "fulltext": "full_text",
    "extraction": "extraction",
    "rob": "rob",
}

LOCK_GLYPH = "\U0001F512 "


class ProjectFrame(ctk.CTkFrame):
    def __init__(self, master, app, *, project_id: str):
        super().__init__(master, fg_color=T.PAPER)
        self.app = app
        self.project_id = project_id
        self.project = None
        self.config = None
        self.phase = "overview"
        self.panels: dict[str, ctk.CTkFrame] = {}
        self.phase_state: list[dict] = []
        # Registered so panels can ask the app to re-evaluate phase locks
        # after a mutation (protocol save, dedup, screening completion).
        app.active_project_frame = self
        self._load()
        self._build()

    def _load(self) -> None:
        self.project = self.app.rpc.call("projects.get", {"project_id": self.project_id})
        self.config = self.app.rpc.call(
            "fields.config.get", {"config_id": self.project["field_config_id"]}
        )
        try:
            self.phase_state = self.app.rpc.call(
                "phases.state", {"project_id": self.project_id}
            )
        except Exception:
            self.phase_state = []

    def _build(self) -> None:
        header = ctk.CTkFrame(self, fg_color=T.PAPER)
        header.pack(fill="x", padx=24, pady=(20, 0))
        GhostButton(header, "← Projects", command=self.app.show_projects).pack(anchor="w")
        title_row = ctk.CTkFrame(header, fg_color="transparent")
        title_row.pack(fill="x", pady=(8, 0))
        ctk.CTkLabel(
            title_row, text=self.project["name"], font=("SF Pro Display", 22, "bold"), text_color=T.INK
        ).pack(side="left")
        Badge(title_row, self.project["field_config_id"], variant="info").pack(side="right")
        Helper(header, self.config["label"]).pack(anchor="w", pady=(4, 0))

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=24, pady=16)

        side = ctk.CTkFrame(body, fg_color=T.PAPER_WARM, corner_radius=10, width=200)
        side.pack(side="left", fill="y")
        side.pack_propagate(False)
        state_by_phase = {entry["phase"]: entry for entry in self.phase_state}
        for slug, label in PHASES:
            phase_id = SLUG_TO_PHASE.get(slug)
            entry = state_by_phase.get(phase_id, {"open": True, "reason": ""}) if phase_id else {"open": True, "reason": ""}
            is_locked = not entry["open"]
            display_label = (LOCK_GLYPH + label) if is_locked else label
            # Locked buttons stay clickable so the click can explain the lock.
            btn = ctk.CTkButton(
                side,
                text=display_label,
                command=lambda s=slug, locked=is_locked, reason=entry["reason"]: self._on_phase_click(s, locked, reason),
                anchor="w",
                fg_color="transparent",
                text_color=T.INK_MUTE if is_locked else T.INK_SOFT,
                hover_color="#e9e3d2",
                corner_radius=6,
                height=30,
                font=T.FONT_BODY,
            )
            btn.pack(fill="x", padx=8, pady=2)
            self.panels[slug + "_btn"] = btn

        self.content = ctk.CTkFrame(body, fg_color="transparent")
        self.content.pack(side="left", fill="both", expand=True, padx=(16, 0))

        self._render_phase()

    def _on_phase_click(self, slug: str, locked: bool, reason: str) -> None:
        if locked:
            self.app.toast("Phase locked", reason or "Complete the earlier phases first.", variant="warn")
            return
        self._set_phase(slug)

    def _set_phase(self, phase: str) -> None:
        self.phase = phase
        self._render_phase()

    def refresh(self) -> None:
        """Re-fetch phase state and re-render the sidebar."""
        try:
            self.phase_state = self.app.rpc.call(
                "phases.state", {"project_id": self.project_id}
            )
        except Exception:
            self.phase_state = []
        state_by_phase = {entry["phase"]: entry for entry in self.phase_state}
        mapped = SLUG_TO_PHASE.get(self.phase)
        if mapped and not state_by_phase.get(mapped, {"open": True})["open"]:
            self.phase = "overview"
        for child in self.winfo_children():
            child.destroy()
        self.panels = {}
        self._build()

    def _render_phase(self) -> None:
        # Highlight active button
        for slug, _ in PHASES:
            btn = self.panels.get(slug + "_btn")
            if btn is not None:
                if slug == self.phase:
                    btn.configure(fg_color=T.PRISM_100, text_color=T.PRISM_700)
                else:
                    btn.configure(fg_color="transparent", text_color=T.INK_SOFT)
        for c in self.content.winfo_children():
            c.destroy()
        if self.phase == "overview":
            self._render_overview()
        elif self.phase == "protocol":
            ProtocolPanel(self.content, self.app, self.project, self.config).pack(fill="both", expand=True)
        elif self.phase == "codebook":
            CodebookPanel(self.content, self.app, self.project).pack(fill="both", expand=True)
        elif self.phase == "search":
            SearchPanel(self.content, self.app, self.project).pack(fill="both", expand=True)
        elif self.phase == "dedup":
            DedupPanel(self.content, self.app, self.project).pack(fill="both", expand=True)
        elif self.phase == "screening":
            ScreeningPanel(self.content, self.app, self.project, stage="title_abstract").pack(fill="both", expand=True)
        elif self.phase == "fulltext":
            ScreeningPanel(self.content, self.app, self.project, stage="full_text").pack(fill="both", expand=True)
        elif self.phase == "extraction":
            ExtractionPanel(self.content, self.app, self.project, self.config).pack(fill="both", expand=True)
        elif self.phase == "rob":
            RoBPanel(self.content, self.app, self.project, self.config).pack(fill="both", expand=True)
        elif self.phase == "share":
            SharePanel(self.content, self.app, self.project).pack(fill="both", expand=True)

    def _render_overview(self) -> None:
        wrap = ctk.CTkScrollableFrame(self.content, fg_color=T.PAPER)
        wrap.pack(fill="both", expand=True)

        card = Card(wrap)
        card.pack(fill="x", pady=(0, 12))
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=18, pady=14)
        ctk.CTkLabel(inner, text="Project at a glance", font=("SF Pro Display", 14, "bold"), text_color=T.INK).pack(anchor="w")
        Helper(inner, "Field configuration version is pinned to this project.").pack(anchor="w", pady=(2, 12))
        for label, value in [
            ("Reporting", ", ".join([self.config["reporting"]["primary"]] + self.config["reporting"]["extensions"])),
            ("Registry", self.config["registries"]["primary"]),
            ("Required databases", ", ".join(self.config["databases"]["required"]) or "—"),
            ("RoB tool", self.config["risk_of_bias"]["tool"]),
            ("Effect size default", self.config["effect_sizes"]["default"]),
            ("Certainty framework", self.config["certainty"]["framework"]),
            ("Branch choices", ", ".join(f"{k}: {v}" for k, v in self.project["branch_choices"].items()) or "—"),
        ]:
            row = ctk.CTkFrame(inner, fg_color="transparent")
            row.pack(fill="x", pady=2)
            ctk.CTkLabel(row, text=label, text_color=T.INK_MUTE, width=170, anchor="w", font=T.FONT_SMALL).pack(side="left")
            ctk.CTkLabel(row, text=value, text_color=T.INK, anchor="w", justify="left", wraplength=520, font=T.FONT_BODY).pack(side="left", fill="x", expand=True)

        warnings = self.config.get("qrp_warnings") or []
        if warnings:
            card = Card(wrap)
            card.pack(fill="x", pady=(0, 12))
            inner = ctk.CTkFrame(card, fg_color="transparent")
            inner.pack(fill="x", padx=18, pady=14)
            ctk.CTkLabel(inner, text="Field-specific cautions", font=("SF Pro Display", 14, "bold"), text_color=T.INK).pack(anchor="w")
            Helper(inner, "From the field config so reviewers don't trip these silently.").pack(anchor="w", pady=(2, 12))
            for w in warnings:
                box = ctk.CTkFrame(inner, fg_color="#fff7ed", corner_radius=8)
                box.pack(fill="x", pady=4)
                inside = ctk.CTkFrame(box, fg_color="transparent")
                inside.pack(fill="x", padx=12, pady=10)
                ctk.CTkLabel(inside, text=w["key"], text_color=T.INK_MUTE, font=("SF Mono", 10, "bold")).pack(anchor="w")
                Helper(inside, w["message"]).pack(anchor="w", pady=(4, 0))
