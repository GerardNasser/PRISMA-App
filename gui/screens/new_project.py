"""6-step project creation wizard.

Field → Review type → Branch choices → Reviewer config → Details → Confirm.
"""

from __future__ import annotations

import re

import customtkinter as ctk

from gui import theme as T
from gui.rpc_client import RpcError
from gui.widgets import Badge, Card, Field, GhostButton, Helper, PrimaryButton
from prismapi.db.models.identity import ORCID_PATTERN


# Pretty labels per `field` cluster so the wizard reads like a human pamphlet.
_FIELD_BLURBS = {
    "health": (
        "Health sciences",
        "Clinical trials, observational studies, diagnostic accuracy, and microbiome / omics. "
        "Inherits PRISMA 2020 + the right risk-of-bias tool per design.",
    ),
    "preclinical": (
        "Preclinical / animal",
        "In-vivo animal studies with SYRCLE RoB and mandatory publication-bias diagnostics.",
    ),
    "social": (
        "Social sciences",
        "Psychology, education, economics, and management meta-analyses with field-specific "
        "publication-bias norms (p-curve, MAIVE, etc.).",
    ),
    "environmental": (
        "Environmental / ecology",
        "Ecology and conservation reviews with multilevel pooling and log-response-ratio defaults.",
    ),
    "engineering": (
        "Engineering / software",
        "Kitchenham-style systematic literature reviews. Narrative + vote-counting synthesis.",
    ),
    "qualitative": (
        "Qualitative synthesis",
        "Meta-ethnography, thematic and framework synthesis. ENTREQ + GRADE-CERQual.",
    ),
    "general": (
        "Custom / general",
        "Use this if no field-specific profile fits. PRISMA 2020 + sensible generic defaults.",
    ),
}


class NewProjectFrame(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color=T.PAPER)
        self.app = app
        self.step = "field"
        self.field = None
        self.config_id = None
        self.config = None
        self.branch = {}
        self.reviewer_cfg = {
            "n_reviewers": 2,
            "alpha_threshold": 0.67,
            "kappa_threshold": 0.6,
            "conflict_strategy": "third_reviewer",
        }
        self.name = ""
        self.slug = ""
        self.description = ""
        self.raters: list[dict] = []  # populated by the enroll step
        self.configs = []
        self._build()
        self._load_configs()

    def _build(self) -> None:
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=32, pady=(28, 8))
        GhostButton(header, "← Back to projects", command=self.app.show_projects).pack(anchor="w")
        ctk.CTkLabel(
            header, text="New project", font=("SF Pro Display", 22, "bold"), text_color=T.INK
        ).pack(anchor="w", pady=(8, 0))
        Helper(
            header,
            "Each project pins a field configuration version. Future config updates won't silently change your work.",
        ).pack(anchor="w", pady=(4, 0))

        self.stepper = ctk.CTkFrame(self, fg_color="transparent")
        self.stepper.pack(fill="x", padx=32, pady=(16, 8))

        self.body = ctk.CTkScrollableFrame(self, fg_color=T.PAPER)
        self.body.pack(fill="both", expand=True, padx=32, pady=(8, 24))

    def _load_configs(self) -> None:
        res = self.app.rpc.call("fields.configs")
        self.configs = res["configs"]
        self._render()

    def _render(self) -> None:
        for child in self.stepper.winfo_children():
            child.destroy()
        steps = [
            ("field", "Field"),
            ("review_type", "Review type"),
            ("branch", "Choices"),
            ("reviewers", "Reviewers"),
            ("enroll", "Enroll raters"),
            ("details", "Details"),
            ("confirm", "Confirm"),
        ]
        idx = next(i for i, (s, _) in enumerate(steps) if s == self.step)
        for i, (s, lbl) in enumerate(steps):
            current = i == idx
            colour = T.PRISM_700 if current or i < idx else T.INK_MUTE
            bg = T.PRISM_100 if current else "transparent"
            label = ctk.CTkLabel(
                self.stepper,
                text=f"{i + 1}. {lbl}",
                text_color=colour,
                fg_color=bg,
                corner_radius=8,
                padx=10,
                pady=4,
                font=("SF Pro Text", 11, "bold"),
            )
            label.pack(side="left", padx=(0, 6))

        for child in self.body.winfo_children():
            child.destroy()

        renderers = {
            "field": self._render_field_step,
            "review_type": self._render_review_step,
            "branch": self._render_branch_step,
            "reviewers": self._render_reviewers_step,
            "enroll": self._render_enroll_step,
            "details": self._render_details_step,
            "confirm": self._render_confirm_step,
        }
        renderers[self.step]()

    # ---- step 1: field ----
    def _render_field_step(self) -> None:
        ctk.CTkLabel(
            self.body, text="Pick your field", font=("SF Pro Display", 17, "bold"), text_color=T.INK
        ).pack(anchor="w", pady=(8, 4))
        Helper(self.body, "Drives the reporting checklist, RoB tool, and methodological defaults.").pack(anchor="w", pady=(0, 14))

        fields = sorted({c["field"] for c in self.configs})
        for f in fields:
            label, blurb = _FIELD_BLURBS.get(f, (f.replace("_", " ").title(), ""))
            count = sum(1 for c in self.configs if c["field"] == f)
            card = Card(self.body)
            card.pack(fill="x", pady=4)
            inner = ctk.CTkFrame(card, fg_color="transparent")
            inner.pack(fill="x", padx=18, pady=14)
            top = ctk.CTkFrame(inner, fg_color="transparent")
            top.pack(fill="x")
            ctk.CTkLabel(top, text=label, font=("SF Pro Display", 14, "bold"), text_color=T.INK, cursor="hand2").pack(side="left")
            Badge(top, f"{count} preset{'s' if count != 1 else ''}", variant="muted").pack(side="right")
            Helper(inner, blurb).pack(anchor="w", pady=(6, 0))
            for w in (card, inner, top, *top.winfo_children()):
                try:
                    w.configure(cursor="hand2")
                except Exception:
                    pass
                w.bind("<Button-1>", lambda _e, ff=f: self._pick_field(ff))

    def _pick_field(self, f: str) -> None:
        self.field = f
        # If only one review type, skip step 2.
        types = [c for c in self.configs if c["field"] == f]
        if len(types) == 1:
            self.config_id = types[0]["id"]
            self.config = self.app.rpc.call("fields.config.get", {"config_id": self.config_id})
            self.branch = {}
            self.step = "branch" if self.config.get("branch_choices") else "reviewers"
        else:
            self.step = "review_type"
        self._render()

    # ---- step 2: review type ----
    def _render_review_step(self) -> None:
        ctk.CTkLabel(
            self.body,
            text=f"Review type · {self.field.replace('_', ' ').title()}",
            font=("SF Pro Display", 17, "bold"),
            text_color=T.INK,
        ).pack(anchor="w", pady=(8, 14))
        for c in [c for c in self.configs if c["field"] == self.field]:
            card = Card(self.body)
            card.pack(fill="x", pady=6)
            inner = ctk.CTkFrame(card, fg_color="transparent")
            inner.pack(fill="x", padx=18, pady=14)
            top = ctk.CTkFrame(inner, fg_color="transparent")
            top.pack(fill="x")
            ctk.CTkLabel(top, text=c["label"], font=("SF Pro Display", 14, "bold"), text_color=T.INK).pack(side="left")
            Badge(top, f"v{c['version']}", variant="muted").pack(side="right")
            Helper(inner, c["summary"]).pack(anchor="w", pady=(6, 0))
            for w in (card, inner, top, *inner.winfo_children(), *top.winfo_children()):
                try:
                    w.configure(cursor="hand2")
                except Exception:
                    pass
                w.bind("<Button-1>", lambda _e, cid=c["id"]: self._pick_review(cid))
        GhostButton(self.body, "← Back", command=lambda: self._set_step("field")).pack(anchor="w", pady=(16, 0))

    def _pick_review(self, config_id: str) -> None:
        self.config_id = config_id
        self.config = self.app.rpc.call("fields.config.get", {"config_id": config_id})
        self.branch = {}
        self.step = "branch" if self.config.get("branch_choices") else "reviewers"
        self._render()

    # ---- step 3: branch (optional) ----
    def _render_branch_step(self) -> None:
        if not self.config.get("branch_choices"):
            self.step = "reviewers"
            self._render()
            return
        ctk.CTkLabel(self.body, text="Up-front choices", font=("SF Pro Display", 17, "bold"), text_color=T.INK).pack(anchor="w", pady=(8, 14))
        for b in self.config["branch_choices"]:
            card = Card(self.body)
            card.pack(fill="x", pady=6)
            inner = ctk.CTkFrame(card, fg_color="transparent")
            inner.pack(fill="x", padx=18, pady=14)
            ctk.CTkLabel(inner, text=b["label"], font=("SF Pro Display", 14, "bold"), text_color=T.INK).pack(anchor="w")
            if b.get("description"):
                Helper(inner, b["description"]).pack(anchor="w", pady=(4, 8))
            var = ctk.StringVar(value=self.branch.get(b["key"], ""))
            for opt in b["options"]:
                row = ctk.CTkFrame(inner, fg_color="transparent")
                row.pack(fill="x", pady=4)
                rb = ctk.CTkRadioButton(
                    row,
                    text=opt["label"],
                    value=opt["value"],
                    variable=var,
                    fg_color=T.PRISM_600,
                    text_color=T.INK,
                    font=("SF Pro Text", 12, "bold"),
                    command=lambda k=b["key"], v=var: self._set_branch(k, v.get()),
                )
                rb.pack(anchor="w")
                if opt.get("description"):
                    Helper(row, opt["description"]).pack(anchor="w", padx=(28, 0))

        nav = ctk.CTkFrame(self.body, fg_color="transparent")
        nav.pack(fill="x", pady=12)
        GhostButton(nav, "← Back", command=lambda: self._set_step("review_type")).pack(side="left")
        required = {b["key"] for b in self.config["branch_choices"] if b.get("required", True)}
        ready = all(k in self.branch for k in required)
        PrimaryButton(
            nav,
            "Continue →",
            command=lambda: self._set_step("reviewers"),
            state="normal" if ready else "disabled",
        ).pack(side="right")

    def _set_branch(self, key: str, value: str) -> None:
        self.branch[key] = value
        self._render()

    def _set_step(self, step: str) -> None:
        self.step = step
        self._render()

    # ---- step 4: reviewer config ----
    def _render_reviewers_step(self) -> None:
        ctk.CTkLabel(self.body, text="Reviewer team", font=("SF Pro Display", 17, "bold"), text_color=T.INK).pack(anchor="w", pady=(8, 4))
        Helper(
            self.body,
            "How many independent reviewers will screen and extract? PRISMA 2020 expects dual screening when feasible. "
            "The IRR thresholds set the bar for 'acceptable' agreement before you move on; defaults follow the published bands.",
        ).pack(anchor="w", pady=(0, 14))

        card = Card(self.body)
        card.pack(fill="x", pady=4)
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=18, pady=14)

        # Number of reviewers
        nr_row = ctk.CTkFrame(inner, fg_color="transparent")
        nr_row.pack(fill="x", pady=(0, 12))
        ctk.CTkLabel(
            nr_row, text="Number of reviewers per item", font=("SF Pro Text", 12, "bold"), text_color=T.INK_SOFT, anchor="w"
        ).pack(anchor="w")
        nr_var = ctk.IntVar(value=self.reviewer_cfg["n_reviewers"])

        def on_nr():
            self.reviewer_cfg["n_reviewers"] = nr_var.get()

        opts = ctk.CTkFrame(nr_row, fg_color="transparent")
        opts.pack(fill="x", pady=(4, 0))
        for n, label in [(1, "1 (solo)"), (2, "2 (recommended)"), (3, "3"), (4, "4+")]:
            ctk.CTkRadioButton(
                opts,
                text=label,
                value=n,
                variable=nr_var,
                command=on_nr,
                fg_color=T.PRISM_600,
                text_color=T.INK,
            ).pack(side="left", padx=(0, 12))
        Helper(
            nr_row,
            "Dual reviewing reduces selection bias. Solo is acceptable for rapid reviews if disclosed and justified.",
        ).pack(anchor="w", pady=(6, 0))

        # Alpha threshold
        a_row = ctk.CTkFrame(inner, fg_color="transparent")
        a_row.pack(fill="x", pady=(8, 12))
        ctk.CTkLabel(
            a_row, text="Krippendorff α target", font=("SF Pro Text", 12, "bold"), text_color=T.INK_SOFT, anchor="w"
        ).pack(anchor="w")
        a_var = ctk.DoubleVar(value=self.reviewer_cfg["alpha_threshold"])
        a_entry = ctk.CTkEntry(
            a_row,
            textvariable=a_var,
            width=80,
            fg_color=T.PAPER_CARD,
            border_color=T.BORDER,
            text_color=T.INK,
        )
        a_entry.pack(anchor="w", pady=(4, 0))
        Helper(
            a_row,
            "Krippendorff bands: ≥0.80 strong, 0.67–0.80 acceptable, <0.67 weak. 0.67 is a common SR cutoff.",
        ).pack(anchor="w", pady=(4, 0))

        # Kappa threshold
        k_row = ctk.CTkFrame(inner, fg_color="transparent")
        k_row.pack(fill="x", pady=(8, 12))
        ctk.CTkLabel(
            k_row, text="Cohen κ target (two-reviewer mode)", font=("SF Pro Text", 12, "bold"), text_color=T.INK_SOFT, anchor="w"
        ).pack(anchor="w")
        k_var = ctk.DoubleVar(value=self.reviewer_cfg["kappa_threshold"])
        k_entry = ctk.CTkEntry(
            k_row,
            textvariable=k_var,
            width=80,
            fg_color=T.PAPER_CARD,
            border_color=T.BORDER,
            text_color=T.INK,
        )
        k_entry.pack(anchor="w", pady=(4, 0))
        Helper(
            k_row,
            "Cohen κ Landis–Koch bands: 0.61–0.80 substantial, ≥0.81 almost perfect. 0.61 is a typical floor.",
        ).pack(anchor="w", pady=(4, 0))

        # Conflict strategy
        c_row = ctk.CTkFrame(inner, fg_color="transparent")
        c_row.pack(fill="x", pady=(8, 4))
        ctk.CTkLabel(
            c_row, text="Conflict resolution", font=("SF Pro Text", 12, "bold"), text_color=T.INK_SOFT, anchor="w"
        ).pack(anchor="w")
        c_var = ctk.StringVar(value=self.reviewer_cfg["conflict_strategy"])

        def on_c():
            self.reviewer_cfg["conflict_strategy"] = c_var.get()

        for val, label in [
            ("third_reviewer", "Third reviewer arbitrates"),
            ("discussion", "Discuss to consensus"),
            ("lead_arbiter", "Lead reviewer makes the call"),
        ]:
            ctk.CTkRadioButton(
                c_row,
                text=label,
                value=val,
                variable=c_var,
                command=on_c,
                fg_color=T.PRISM_600,
                text_color=T.INK,
            ).pack(anchor="w", pady=2)

        nav = ctk.CTkFrame(self.body, fg_color="transparent")
        nav.pack(fill="x", pady=12)

        def commit_and_continue():
            try:
                self.reviewer_cfg["alpha_threshold"] = float(a_var.get())
                self.reviewer_cfg["kappa_threshold"] = float(k_var.get())
            except Exception:
                self.app.toast("α and κ targets must be numbers 0.0–1.0", variant="warn")
                return
            self._set_step("enroll")

        back_to = "branch" if self.config.get("branch_choices") else (
            "review_type" if sum(1 for c in self.configs if c["field"] == self.field) > 1 else "field"
        )
        GhostButton(nav, "← Back", command=lambda: self._set_step(back_to)).pack(side="left")
        PrimaryButton(nav, "Continue →", command=commit_and_continue).pack(side="right")

    # ---- step 4b: enroll raters ----
    def _render_enroll_step(self) -> None:
        ctk.CTkLabel(
            self.body, text="Enroll raters", font=("SF Pro Display", 17, "bold"), text_color=T.INK
        ).pack(anchor="w", pady=(8, 4))
        Helper(
            self.body,
            "Lead pre-enrolls each rater. Each rater gets a per-rater envelope stamped with their identifier.",
        ).pack(anchor="w", pady=(0, 14))

        # Determine number of raters. The reviewers step stores an int via IntVar,
        # but defensively handle a "4+" string form too.
        n_raw = self.reviewer_cfg["n_reviewers"]
        if isinstance(n_raw, str):
            n = int(n_raw.rstrip("+"))
        else:
            n = int(n_raw)
        if n < 1:
            n = 1

        form_rows = [
            {
                "last_name": ctk.StringVar(value=""),
                "kind": ctk.StringVar(value="Email"),
                "identifier": ctk.StringVar(value=""),
                "role": ctk.StringVar(value="Lead" if i == 0 else "Rater"),
            }
            for i in range(n)
        ]

        # If we re-entered the step, prefill from prior state.
        if self.raters and len(self.raters) == n:
            for i, prior in enumerate(self.raters):
                form_rows[i]["last_name"].set(prior.get("last_name", ""))
                if prior.get("orcid"):
                    form_rows[i]["kind"].set("ORCID")
                    form_rows[i]["identifier"].set(prior["orcid"])
                elif prior.get("email"):
                    form_rows[i]["kind"].set("Email")
                    form_rows[i]["identifier"].set(prior["email"])
                form_rows[i]["role"].set("Lead" if prior.get("role") == "owner" else "Rater")

        for i, row in enumerate(form_rows):
            card = Card(self.body)
            card.pack(fill="x", pady=6)
            inner = ctk.CTkFrame(card, fg_color="transparent")
            inner.pack(fill="x", padx=18, pady=14)
            ctk.CTkLabel(
                inner,
                text=f"Rater {i + 1}",
                font=("SF Pro Display", 13, "bold"),
                text_color=T.INK,
            ).pack(anchor="w", pady=(0, 8))

            # Last name
            ln_row = ctk.CTkFrame(inner, fg_color="transparent")
            ln_row.pack(fill="x", pady=(0, 8))
            ctk.CTkLabel(
                ln_row,
                text="Last name *",
                font=("SF Pro Text", 12, "bold"),
                text_color=T.INK_SOFT,
                anchor="w",
            ).pack(anchor="w", pady=(0, 4))
            ctk.CTkEntry(
                ln_row,
                textvariable=row["last_name"],
                placeholder_text="Nasser",
                fg_color=T.PAPER_CARD,
                border_color=T.BORDER,
                text_color=T.INK,
                height=36,
            ).pack(fill="x")

            # Identifier kind + value
            id_row = ctk.CTkFrame(inner, fg_color="transparent")
            id_row.pack(fill="x", pady=(0, 8))
            ctk.CTkLabel(
                id_row,
                text="Identifier *",
                font=("SF Pro Text", 12, "bold"),
                text_color=T.INK_SOFT,
                anchor="w",
            ).pack(anchor="w", pady=(0, 4))
            id_pair = ctk.CTkFrame(id_row, fg_color="transparent")
            id_pair.pack(fill="x")
            kind_menu = ctk.CTkOptionMenu(
                id_pair,
                values=["Email", "ORCID"],
                variable=row["kind"],
                fg_color=T.PAPER_CARD,
                button_color=T.BORDER,
                button_hover_color=T.PAPER_WARM,
                text_color=T.INK,
                width=110,
            )
            kind_menu.pack(side="left", padx=(0, 8))
            id_entry = ctk.CTkEntry(
                id_pair,
                textvariable=row["identifier"],
                placeholder_text="name@university.edu",
                fg_color=T.PAPER_CARD,
                border_color=T.BORDER,
                text_color=T.INK,
                height=36,
            )
            id_entry.pack(side="left", fill="x", expand=True)

            def _swap_placeholder(_v=None, e=id_entry, k=row["kind"]):
                e.configure(
                    placeholder_text=(
                        "0000-0001-2345-6789" if k.get() == "ORCID" else "name@university.edu"
                    )
                )

            row["kind"].trace_add("write", lambda *_a, fn=_swap_placeholder: fn())
            _swap_placeholder()

            # Role
            role_row = ctk.CTkFrame(inner, fg_color="transparent")
            role_row.pack(fill="x")
            ctk.CTkLabel(
                role_row,
                text="Role",
                font=("SF Pro Text", 12, "bold"),
                text_color=T.INK_SOFT,
                anchor="w",
            ).pack(anchor="w", pady=(0, 4))
            ctk.CTkOptionMenu(
                role_row,
                values=["Lead", "Rater"],
                variable=row["role"],
                fg_color=T.PAPER_CARD,
                button_color=T.BORDER,
                button_hover_color=T.PAPER_WARM,
                text_color=T.INK,
                width=140,
            ).pack(anchor="w")

        Helper(
            self.body,
            "Exactly one rater must be marked Lead. ORCID format: 0000-0000-0000-000X.",
        ).pack(anchor="w", pady=(8, 0))

        nav = ctk.CTkFrame(self.body, fg_color="transparent")
        nav.pack(fill="x", pady=12)

        def commit_and_continue():
            collected = []
            seen_ids: set[str] = set()
            lead_count = 0
            for idx, r in enumerate(form_rows, start=1):
                last_name = r["last_name"].get().strip()
                kind = r["kind"].get()
                identifier = r["identifier"].get().strip()
                role = r["role"].get()
                if not last_name:
                    self.app.toast(f"Rater {idx}: last name is required", variant="warn")
                    return
                if not identifier:
                    self.app.toast(f"Rater {idx}: identifier is required", variant="warn")
                    return
                if kind == "ORCID":
                    if not re.match(ORCID_PATTERN, identifier):
                        self.app.toast(
                            f"Rater {idx}: ORCID must look like 0000-0000-0000-000X",
                            variant="warn",
                        )
                        return
                else:  # Email
                    if "@" not in identifier:
                        self.app.toast(
                            f"Rater {idx}: email must contain '@'", variant="warn"
                        )
                        return
                key = identifier.lower()
                if key in seen_ids:
                    self.app.toast(
                        f"Rater {idx}: identifier '{identifier}' is duplicated",
                        variant="warn",
                    )
                    return
                seen_ids.add(key)
                if role == "Lead":
                    lead_count += 1
                collected.append((last_name, kind, identifier, role))

            if lead_count != 1:
                self.app.toast(
                    "Exactly one rater must be marked Lead", variant="warn"
                )
                return

            self.raters = [
                {
                    "last_name": last_name,
                    "orcid": identifier if kind == "ORCID" else None,
                    "email": identifier if kind == "Email" else None,
                    "role": "owner" if role == "Lead" else "reviewer",
                }
                for (last_name, kind, identifier, role) in collected
            ]
            self._set_step("details")

        GhostButton(nav, "← Back", command=lambda: self._set_step("reviewers")).pack(side="left")
        PrimaryButton(nav, "Continue →", command=commit_and_continue).pack(side="right")

    # ---- step 5: details ----
    def _render_details_step(self) -> None:
        ctk.CTkLabel(self.body, text="Project details", font=("SF Pro Display", 17, "bold"), text_color=T.INK).pack(anchor="w", pady=(8, 14))

        self.name_field = Field(self.body, "Name", required=True, placeholder="Plant microbiome SR", initial=self.name)
        self.name_field.pack(fill="x", pady=(0, 12))
        self.slug_field = Field(
            self.body,
            "Slug",
            helper="Lowercase letters, numbers, and hyphens only.",
            initial=self.slug,
        )
        self.slug_field.pack(fill="x", pady=(0, 12))
        self.desc_field = Field(self.body, "Description (optional)", initial=self.description)
        self.desc_field.pack(fill="x", pady=(0, 12))

        self._last_auto_slug = ""

        def derive_slug(*_):
            name = self.name_field.get()
            current = self.slug_field.get()
            if not current or current == self._last_auto_slug:
                slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:60]
                self.slug_field.set(slug)
                self._last_auto_slug = slug

        self.name_field.widget.bind("<KeyRelease>", derive_slug)

        nav = ctk.CTkFrame(self.body, fg_color="transparent")
        nav.pack(fill="x", pady=12)
        GhostButton(nav, "← Back", command=lambda: self._set_step("enroll")).pack(side="left")
        PrimaryButton(nav, "Continue →", command=self._goto_confirm).pack(side="right")

    def _goto_confirm(self) -> None:
        self.name = self.name_field.get()
        self.slug = self.slug_field.get()
        self.description = self.desc_field.get()
        if not self.name or not self.slug:
            self.app.toast("Name and slug are required", variant="warn")
            return
        self._set_step("confirm")

    # ---- step 6: confirm ----
    def _render_confirm_step(self) -> None:
        ctk.CTkLabel(self.body, text="Confirm", font=("SF Pro Display", 17, "bold"), text_color=T.INK).pack(anchor="w", pady=(8, 14))
        card = Card(self.body)
        card.pack(fill="x")
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=18, pady=14)
        rev = self.reviewer_cfg
        for label, value in [
            ("Name", self.name),
            ("Slug", self.slug),
            ("Field", self.config["label"]),
            ("Reporting", ", ".join([self.config["reporting"]["primary"]] + self.config["reporting"]["extensions"])),
            ("Required databases", ", ".join(self.config["databases"]["required"]) or "—"),
            ("Risk of bias tool", self.config["risk_of_bias"]["tool"]),
            ("Effect size default", self.config["effect_sizes"]["default"]),
            ("Certainty framework", self.config["certainty"]["framework"]),
            ("Reviewers per item", f"{rev['n_reviewers']}"),
            ("Raters enrolled", ", ".join(
                f"{r['last_name']} ({'Lead' if r['role']=='owner' else 'Rater'})"
                for r in self.raters
            ) or "—"),
            ("IRR α target", f"{rev['alpha_threshold']:.2f}"),
            ("IRR κ target", f"{rev['kappa_threshold']:.2f}"),
            ("Conflict strategy", rev["conflict_strategy"].replace("_", " ")),
            ("Branch choices", ", ".join(f"{k}: {v}" for k, v in self.branch.items()) or "—"),
        ]:
            row = ctk.CTkFrame(inner, fg_color="transparent")
            row.pack(fill="x", pady=3)
            ctk.CTkLabel(row, text=label, text_color=T.INK_MUTE, width=180, anchor="w", font=T.FONT_SMALL).pack(side="left")
            ctk.CTkLabel(row, text=str(value), text_color=T.INK, anchor="w", justify="left", wraplength=520, font=T.FONT_BODY).pack(side="left", fill="x", expand=True)

        nav = ctk.CTkFrame(self.body, fg_color="transparent")
        nav.pack(fill="x", pady=12)
        GhostButton(nav, "← Back", command=lambda: self._set_step("details")).pack(side="left")
        PrimaryButton(nav, "Create project", command=self._submit).pack(side="right")

    def _submit(self) -> None:
        try:
            proj = self.app.rpc.call(
                "projects.create",
                {
                    "name": self.name,
                    "slug": self.slug,
                    "description": self.description or None,
                    "field_config_id": self.config_id,
                    "branch_choices": self.branch,
                },
            )
            # Save an initial protocol v1 carrying the reviewer config + a draft title.
            try:
                self.app.rpc.call(
                    "protocols.save",
                    {
                        "project_id": proj["id"],
                        "title": self.name,
                        "reviewer_config": self.reviewer_cfg,
                    },
                )
            except Exception:
                pass  # The Protocol screen lets them save later if this fails.
            for rater in self.raters:
                try:
                    self.app.rpc.call(
                        "members.enroll",
                        {"project_id": proj["id"], **rater},
                    )
                except Exception:
                    # Surface a single warning but do not block project creation:
                    self.app.toast(
                        f"Could not enroll {rater['last_name']} — add them later in Settings.",
                        variant="warn",
                    )
            self.app.toast("Project created", variant="ok")
            self.app.show_project(proj["id"])
        except RpcError as e:
            self.app.toast("Couldn't create project", e.message, variant="danger")
        except Exception as e:  # noqa: BLE001
            self.app.toast("Couldn't create project", str(e), variant="danger")
