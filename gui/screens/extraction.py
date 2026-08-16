"""Extraction panel — renders form fields from the field config template."""

from __future__ import annotations

import customtkinter as ctk

from gui import theme as T
from gui.widgets import Badge, Card, Field, Helper, PrimaryButton, SecondaryButton


class ExtractionPanel(ctk.CTkFrame):
    def __init__(self, master, app, project, config):
        super().__init__(master, fg_color=T.PAPER)
        self.app = app
        self.project = project
        self.config = config
        self.clusters = []
        self.active_cluster = None
        self.template = self.config["extraction_template"]
        self._fields: dict[str, Field] = {}
        # My existing extraction per cluster id, so revisiting a study shows
        # what was saved instead of a blank form that would overwrite it.
        self.mine_by_cluster: dict[str, dict] = {}
        self._build()
        self._load_clusters()

    def _build(self) -> None:
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(head, text="Extraction", font=("SF Pro Display", 16, "bold"), text_color=T.INK).pack(side="left")
        Badge(head, self.template["base"], variant="muted").pack(side="right")
        Helper(self, "Form fields rendered from the field config's extraction template.").pack(anchor="w", pady=(0, 12))

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True)

        # Cluster list
        side = ctk.CTkFrame(body, fg_color="transparent", width=240)
        side.pack(side="left", fill="y")
        side.pack_propagate(False)
        Card(side).pack(fill="both", expand=True)
        list_card = side.winfo_children()[0]
        ctk.CTkLabel(list_card, text="Clusters", font=("SF Pro Display", 13, "bold"), text_color=T.INK).pack(anchor="w", padx=10, pady=(10, 4))
        self.cluster_list = ctk.CTkScrollableFrame(list_card, fg_color=T.PAPER_CARD)
        self.cluster_list.pack(fill="both", expand=True, padx=4, pady=(0, 6))

        # Form
        right = ctk.CTkFrame(body, fg_color="transparent")
        right.pack(side="left", fill="both", expand=True, padx=(16, 0))

        save_bar = ctk.CTkFrame(right, fg_color="transparent")
        save_bar.pack(fill="x")
        ctk.CTkLabel(save_bar, text="Per-study extraction", font=("SF Pro Display", 14, "bold"), text_color=T.INK).pack(side="left")
        SecondaryButton(save_bar, "Save draft", command=lambda: self._save(False)).pack(side="right", padx=4)
        PrimaryButton(save_bar, "Submit", command=lambda: self._save(True)).pack(side="right", padx=4)

        self.form_wrap = ctk.CTkScrollableFrame(right, fg_color=T.PAPER)
        self.form_wrap.pack(fill="both", expand=True, pady=(8, 0))

    def _load_clusters(self) -> None:
        try:
            self.clusters = self.app.rpc.call(
                "dedup.clusters.list", {"project_id": self.project["id"], "limit": 1000}
            )["clusters"]
        except Exception as e:
            self.app.toast("Couldn't load clusters", str(e), variant="danger")
            self.clusters = []
        try:
            rows = self.app.rpc.call(
                "extraction.list", {"project_id": self.project["id"]}
            )["extractions"]
            me = self.app.identity["id"]
            self.mine_by_cluster = {
                r["cluster_id"]: r for r in rows if r["reviewer_identity_id"] == me
            }
        except Exception as e:
            self.app.toast("Couldn't load saved extractions", str(e), variant="danger")
            self.mine_by_cluster = {}
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
            self._render_form()

    def _pick(self, cluster: dict) -> None:
        self.active_cluster = cluster
        self._render_form()

    def _render_form(self) -> None:
        for c in self.form_wrap.winfo_children():
            c.destroy()
        self._fields.clear()
        if self.active_cluster is None:
            Helper(self.form_wrap, "No cluster selected.").pack(pady=20)
            return

        existing = self.mine_by_cluster.get(self.active_cluster["id"])
        saved = (existing or {}).get("payload") or {}
        if existing:
            status_row = ctk.CTkFrame(self.form_wrap, fg_color="transparent")
            status_row.pack(fill="x", pady=(0, 4))
            Badge(
                status_row,
                f"saved: {existing['status']}",
                variant="ok" if existing["status"] == "submitted" else "warn",
            ).pack(side="left")

        def _initial(f: dict):
            v = saved.get(f["key"])
            if v is None:
                return ""
            if f["type"] == "boolean":
                return "yes" if v else "no"
            if f["type"] == "select_many" and isinstance(v, list):
                return ", ".join(str(x) for x in v)
            return str(v)

        # Group fields by `group`
        groups: dict[str, list[dict]] = {}
        for f in self.template["fields"]:
            groups.setdefault(f.get("group") or "other", []).append(f)

        for gname, gfields in groups.items():
            card = Card(self.form_wrap)
            card.pack(fill="x", pady=4)
            inner = ctk.CTkFrame(card, fg_color="transparent")
            inner.pack(fill="x", padx=16, pady=14)
            ctk.CTkLabel(inner, text=gname.replace("_", " ").title(), font=("SF Pro Display", 13, "bold"), text_color=T.INK).pack(anchor="w")
            grid = ctk.CTkFrame(inner, fg_color="transparent")
            grid.pack(fill="x", pady=(8, 0))
            grid.grid_columnconfigure(0, weight=1)
            grid.grid_columnconfigure(1, weight=1)
            row = 0
            col = 0
            for f in gfields:
                kind = "entry"
                options = None
                if f["type"] == "longtext":
                    kind = "textbox"
                elif f["type"] == "boolean":
                    kind = "select"
                    options = ["", "yes", "no"]
                elif f["type"] == "select_one":
                    kind = "select"
                    options = [""] + (f.get("options") or [])
                elif f["type"] == "select_many":
                    kind = "entry"  # comma-separated for now
                fld = Field(
                    grid,
                    f["label"],
                    required=bool(f.get("required")),
                    helper=f.get("help"),
                    kind=kind,
                    options=options,
                    initial=_initial(f),
                )
                span = 2 if kind == "textbox" else 1
                fld.grid(row=row, column=col, columnspan=span, sticky="ew", padx=(0, 12) if col == 0 else (0, 0), pady=(0, 8))
                self._fields[f["key"]] = fld
                if span == 2:
                    row += 1
                    col = 0
                else:
                    col += 1
                    if col >= 2:
                        col = 0
                        row += 1

    def _save(self, submit: bool) -> None:
        if self.active_cluster is None:
            return
        payload: dict = {}
        for k, fld in self._fields.items():
            v = fld.get()
            if v in ("", None):
                continue
            tpl = next(t for t in self.template["fields"] if t["key"] == k)
            if tpl["type"] == "boolean":
                payload[k] = True if v == "yes" else (False if v == "no" else None)
                if payload[k] is None:
                    del payload[k]
            elif tpl["type"] == "select_many":
                payload[k] = [s.strip() for s in str(v).split(",") if s.strip()]
            elif tpl["type"] in ("integer",):
                try:
                    payload[k] = int(v)
                except ValueError:
                    payload[k] = v
            elif tpl["type"] in ("number",):
                try:
                    payload[k] = float(v)
                except ValueError:
                    payload[k] = v
            else:
                payload[k] = v
        try:
            saved = self.app.rpc.call(
                "extraction.save",
                {
                    "project_id": self.project["id"],
                    "cluster_id": self.active_cluster["id"],
                    "status": "submitted" if submit else "draft",
                    "payload": payload,
                },
            )
            self.mine_by_cluster[self.active_cluster["id"]] = saved
            self.app.toast("Submitted" if submit else "Draft saved", variant="ok")
            if submit:
                # A submitted extraction can open the risk-of-bias gate.
                self.app.refresh_project_phases()
        except Exception as e:
            self.app.toast("Save failed", str(e), variant="danger")
