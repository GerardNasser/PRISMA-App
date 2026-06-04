"""Risk-of-bias panel — renders the tool defined by the field config."""

from __future__ import annotations

import customtkinter as ctk

from gui import theme as T
from gui.widgets import Badge, Card, Field, Helper, PrimaryButton, SecondaryButton


class RoBPanel(ctk.CTkFrame):
    def __init__(self, master, app, project, config):
        super().__init__(master, fg_color=T.PAPER)
        self.app = app
        self.project = project
        self.config = config
        self.clusters = []
        self.active_cluster = None
        self.spec = None
        self._fields: dict[str, dict] = {}
        self._build()
        self._load()

    def _build(self) -> None:
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(head, text="Risk of bias", font=("SF Pro Display", 16, "bold"), text_color=T.INK).pack(side="left")
        self.tool_badge = Badge(head, "—", variant="muted")
        self.tool_badge.pack(side="right")
        Helper(self, "Rendered from the field config's RoB tool spec.").pack(anchor="w", pady=(0, 12))

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True)

        side = ctk.CTkFrame(body, fg_color="transparent", width=240)
        side.pack(side="left", fill="y")
        side.pack_propagate(False)
        Card(side).pack(fill="both", expand=True)
        list_card = side.winfo_children()[0]
        ctk.CTkLabel(list_card, text="Clusters", font=("SF Pro Display", 13, "bold"), text_color=T.INK).pack(anchor="w", padx=10, pady=(10, 4))
        self.cluster_list = ctk.CTkScrollableFrame(list_card, fg_color=T.PAPER_CARD)
        self.cluster_list.pack(fill="both", expand=True, padx=4, pady=(0, 6))

        right = ctk.CTkFrame(body, fg_color="transparent")
        right.pack(side="left", fill="both", expand=True, padx=(16, 0))

        save_bar = ctk.CTkFrame(right, fg_color="transparent")
        save_bar.pack(fill="x")
        ctk.CTkLabel(save_bar, text="Per-study RoB judgement", font=("SF Pro Display", 14, "bold"), text_color=T.INK).pack(side="left")
        PrimaryButton(save_bar, "Save", command=self._save).pack(side="right")

        self.form_wrap = ctk.CTkScrollableFrame(right, fg_color=T.PAPER)
        self.form_wrap.pack(fill="both", expand=True, pady=(8, 0))

    def _load(self) -> None:
        try:
            self.spec = self.app.rpc.call("rob.tool", {"project_id": self.project["id"]})
        except Exception as e:  # noqa: BLE001
            Helper(self.form_wrap, f"RoB tool unavailable: {e}").pack(pady=20)
            return
        self.tool_badge.configure(text=self.spec["tool"])
        try:
            self.clusters = self.app.rpc.call(
                "dedup.clusters.list", {"project_id": self.project["id"], "limit": 1000}
            )["clusters"]
        except Exception:
            self.clusters = []
        for c in self.cluster_list.winfo_children():
            c.destroy()
        for cl in self.clusters:
            title = cl["members"][0]["title"] if cl["members"] else cl["id"][:8]
            btn = ctk.CTkButton(
                self.cluster_list,
                text=title[:36],
                command=lambda c=cl: self._pick(c),
                anchor="w",
                fg_color="transparent",
                text_color=T.INK_SOFT,
                hover_color=T.PAPER_WARM,
                corner_radius=6,
                font=T.FONT_SMALL,
                height=28,
            )
            btn.pack(fill="x", padx=2, pady=1)
        if self.clusters:
            self._pick(self.clusters[0])
        else:
            Helper(self.form_wrap, "No clusters yet.").pack(pady=20)

    def _pick(self, cluster: dict) -> None:
        self.active_cluster = cluster
        self._render_form()

    def _render_form(self) -> None:
        for c in self.form_wrap.winfo_children():
            c.destroy()
        self._fields = {}
        if not self.spec or not self.spec.get("domains"):
            Helper(self.form_wrap, "This tool has no inline domains.").pack(pady=20)
            return
        scale = self.spec.get("scale") or ["low", "some_concerns", "high", "no_information"]
        for d in self.spec["domains"]:
            card = Card(self.form_wrap)
            card.pack(fill="x", pady=4)
            inner = ctk.CTkFrame(card, fg_color="transparent")
            inner.pack(fill="x", padx=16, pady=12)
            ctk.CTkLabel(inner, text=d["label"], font=("SF Pro Display", 13, "bold"), text_color=T.INK).pack(anchor="w")
            if d.get("help"):
                Helper(inner, d["help"]).pack(anchor="w", pady=(2, 8))
            judgement = Field(inner, "Judgement", kind="select", options=[""] + list(scale))
            judgement.pack(fill="x", pady=(2, 6))
            justification = Field(inner, "Justification", kind="textbox")
            justification.pack(fill="x")
            self._fields[d["key"]] = {"judgement": judgement, "justification": justification}

    def _save(self) -> None:
        if self.active_cluster is None:
            return
        judgements = {}
        for key, fields in self._fields.items():
            j = fields["judgement"].get()
            if not j:
                continue
            judgements[key] = {"judgement": j, "justification": fields["justification"].get() or None}
        if not judgements:
            self.app.toast("Pick at least one judgement", variant="warn")
            return
        try:
            self.app.rpc.call(
                "rob.save",
                {
                    "project_id": self.project["id"],
                    "cluster_id": self.active_cluster["id"],
                    "judgements": judgements,
                },
            )
            self.app.toast("RoB saved", variant="ok")
        except Exception as e:  # noqa: BLE001
            self.app.toast("Save failed", str(e), variant="danger")
