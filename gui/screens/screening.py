"""Screening panel, codebook-driven. Serves both stages.

Each cluster (one logical study after de-duplication) is presented with
title + abstract + journal / authors / year. Decisions are tagged with
codebook rules so exclusions carry a structured reason — exactly the
shape PRISMA flow diagrams need. At the full-text stage an exclusion
must carry a reason (PRISMA 2020 item 16b); at title/abstract it may.

Keyboard
--------
- ``I`` / ``Y`` — include
- ``E`` / ``N`` — exclude (a reason must be picked first)
- ``M``         — maybe (revisit later)
- ``←`` / ``→`` — previous / next study
"""

from __future__ import annotations

import customtkinter as ctk

from gui import theme as T
from gui.widgets import Badge, Card, DangerButton, Helper, SecondaryButton


def _normalize_rules(codebook: dict | None) -> list[dict]:
    """Return a flat list of codebook rules, tolerating None/missing/None-valued shapes."""
    if not codebook:
        return []
    rules = codebook.get("rules")
    if not rules:
        return []
    return list(rules)


STAGE_LABELS = {
    "title_abstract": "Title / abstract screening",
    "full_text": "Full-text screening",
}


class ScreeningPanel(ctk.CTkFrame):
    def __init__(self, master, app, project, stage: str = "title_abstract"):
        super().__init__(master, fg_color=T.PAPER)
        self.app = app
        self.project = project
        self.stage = stage
        self.clusters: list[dict] = []
        self.decisions_by_cluster: dict[str, dict] = {}
        self.idx = 0
        self.codebook: dict | None = None
        self.protocol: dict | None = None
        self.irr_data: dict | None = None
        # Codebook rule currently selected as the active exclusion reason.
        self.active_exclude_rule: dict | None = None
        self.load_error: str | None = None
        self._build()
        self._load()
        # Key bindings — customtkinter forbids bind_all, so bind to the toplevel
        # window directly. The bindings are auto-cleared when the panel is destroyed
        # via the <Destroy> handler below.
        top = self.winfo_toplevel()
        self._key_bindings: list[tuple[str, str]] = []

        def _bind(seq: str, fn) -> None:
            funcid = top.bind(seq, fn, add="+")
            self._key_bindings.append((seq, funcid))

        _bind("<Key-i>", lambda _e: self._decide("include"))
        _bind("<Key-I>", lambda _e: self._decide("include"))
        _bind("<Key-y>", lambda _e: self._decide("include"))
        _bind("<Key-e>", lambda _e: self._decide("exclude"))
        _bind("<Key-E>", lambda _e: self._decide("exclude"))
        _bind("<Key-n>", lambda _e: self._decide("exclude"))
        _bind("<Key-m>", lambda _e: self._decide("maybe"))
        _bind("<Key-M>", lambda _e: self._decide("maybe"))
        _bind("<Right>", lambda _e: self._advance(1))
        _bind("<Left>", lambda _e: self._advance(-1))
        self.bind("<Destroy>", self._unbind_keys, add="+")

    def _unbind_keys(self, _event=None) -> None:
        top = self.winfo_toplevel()
        for seq, funcid in getattr(self, "_key_bindings", []):
            try:
                top.unbind(seq, funcid)
            except Exception:
                pass
        self._key_bindings = []

    # ------------------------------------------------------------------ build

    def _build(self) -> None:
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", pady=(0, 6))
        ctk.CTkLabel(
            head,
            text=STAGE_LABELS.get(self.stage, self.stage),
            font=("SF Pro Display", 16, "bold"),
            text_color=T.INK,
        ).pack(side="left")
        self.counter = ctk.CTkLabel(head, text="", text_color=T.INK_MUTE, font=("SF Mono", 12))
        self.counter.pack(side="right")
        Helper(
            self,
            "Press I include · E exclude · M maybe · ← → navigate. Pick a codebook "
            "rule on the right to apply it as the inclusion / exclusion reason.",
        ).pack(anchor="w", pady=(0, 10))

        # Use grid so neither column can starve the other.
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True)
        body.grid_columnconfigure(0, weight=1, minsize=420)
        body.grid_columnconfigure(1, weight=0, minsize=300)
        body.grid_rowconfigure(0, weight=1)

        # ---- left column: study card + decision controls -----------------
        left = ctk.CTkFrame(body, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 16))

        self.card = Card(left)
        self.card.pack(fill="both", expand=True)
        # Scrollable inside the card so long abstracts don't blow the layout.
        self.card_inner = ctk.CTkScrollableFrame(self.card, fg_color=T.PAPER_CARD)
        self.card_inner.pack(fill="both", expand=True, padx=10, pady=10)

        # Active rule strip — shows the codebook rule armed for the next E.
        self.rule_strip = ctk.CTkFrame(left, fg_color="#fff7ed", corner_radius=8)
        self.rule_strip_inner = ctk.CTkFrame(self.rule_strip, fg_color="transparent")
        self.rule_strip_inner.pack(fill="x", padx=12, pady=8)
        # (packed only when a rule is armed; see _render_rule_strip)

        # Decision buttons
        btns = ctk.CTkFrame(left, fg_color="transparent")
        btns.pack(fill="x", pady=(10, 0))
        self.inc_btn = ctk.CTkButton(
            btns,
            text="✓ Include  [I]",
            command=lambda: self._decide("include"),
            fg_color=T.OK,
            hover_color="#059669",
            text_color="white",
            height=42,
            font=("SF Pro Text", 13, "bold"),
        )
        self.inc_btn.pack(side="left", padx=(0, 8))
        self.exc_btn = DangerButton(btns, "✗ Exclude  [E]", command=lambda: self._decide("exclude"))
        self.exc_btn.configure(height=42)
        self.exc_btn.pack(side="left", padx=(0, 8))
        self.maybe_btn = SecondaryButton(btns, "? Maybe  [M]", command=lambda: self._decide("maybe"))
        self.maybe_btn.configure(height=42)
        self.maybe_btn.pack(side="left", padx=(0, 8))
        self.prev_btn = SecondaryButton(btns, "◀", command=lambda: self._advance(-1))
        self.prev_btn.configure(height=42, width=44)
        self.prev_btn.pack(side="right", padx=(8, 0))
        self.next_btn = SecondaryButton(btns, "▶", command=lambda: self._advance(1))
        self.next_btn.configure(height=42, width=44)
        self.next_btn.pack(side="right")

        # Existing-decision badge under the buttons.
        self.existing_decision_row = ctk.CTkFrame(left, fg_color="transparent")
        self.existing_decision_row.pack(fill="x", pady=(8, 0))

        # ---- right column: codebook + IRR --------------------------------
        side = ctk.CTkFrame(body, fg_color="transparent")
        side.grid(row=0, column=1, sticky="nsew")

        cb_card = Card(side)
        cb_card.pack(fill="both", expand=True, pady=(0, 10))
        ctk.CTkLabel(
            cb_card,
            text="Codebook rules",
            font=("SF Pro Display", 13, "bold"),
            text_color=T.INK,
        ).pack(anchor="w", padx=12, pady=(10, 0))
        Helper(
            cb_card,
            "Click a rule to arm it as the next decision's reason. Include rules "
            "fire ✓; exclude rules fire ✗ and the reason gets stamped on the decision.",
        ).pack(anchor="w", padx=12, pady=(2, 6))
        self.codebook_inner = ctk.CTkScrollableFrame(cb_card, fg_color=T.PAPER_CARD, height=260)
        self.codebook_inner.pack(fill="both", expand=True, padx=8, pady=(0, 10))

        self.irr_card = Card(side)
        self.irr_card.pack(fill="x")
        self.irr_inner = ctk.CTkFrame(self.irr_card, fg_color="transparent")
        self.irr_inner.pack(fill="x", padx=12, pady=10)

    # ------------------------------------------------------------------- load

    def _load(self) -> None:
        self.load_error = None
        try:
            self.clusters = self.app.rpc_fetch_all(
                "screening.queue",
                {"project_id": self.project["id"], "stage": self.stage},
                "clusters",
            )
        except Exception as e:
            self.clusters = []
            self.load_error = str(e)
            self.app.toast("Couldn't load clusters", str(e), variant="danger")
        try:
            self.codebook = self.app.rpc.call(
                "codebooks.latest", {"project_id": self.project["id"]}
            )
        except Exception:
            self.codebook = None
        try:
            self.protocol = self.app.rpc.call(
                "protocols.latest", {"project_id": self.project["id"]}
            )
        except Exception:
            self.protocol = None
        try:
            ds = self.app.rpc.call(
                "screening.decisions.list",
                {"project_id": self.project["id"], "stage": self.stage},
            )["decisions"]
            # Only MY decisions: a collaborator's imported votes must not
            # render as "already decided" for this reviewer.
            me = self.app.identity["id"]
            self.decisions_by_cluster = {
                d["cluster_id"]: d
                for d in ds
                if d["reviewer_identity_id"] == me
            }
        except Exception:
            self.decisions_by_cluster = {}
        self._refresh_irr()
        self._render()
        self._render_codebook()
        self._render_rule_strip()

    # ----------------------------------------------------------------- render

    def _current_cluster(self) -> dict | None:
        if not self.clusters:
            return None
        self.idx = max(0, min(self.idx, len(self.clusters) - 1))
        return self.clusters[self.idx]

    def _render(self) -> None:
        for c in self.card_inner.winfo_children():
            c.destroy()
        for c in self.existing_decision_row.winfo_children():
            c.destroy()

        cluster = self._current_cluster()
        if cluster is None:
            self.counter.configure(text="")
            ctk.CTkLabel(
                self.card_inner,
                text="Nothing to screen yet",
                font=("SF Pro Display", 16, "bold"),
                text_color=T.INK,
            ).pack(pady=20)
            if self.load_error:
                Helper(self.card_inner, f"Load error: {self.load_error}").pack(pady=(0, 4))
            Helper(
                self.card_inner,
                (
                    "No studies have advanced to full text yet. A study advances once "
                    "its title/abstract decision is include or maybe (unanimously, or "
                    "by conflict resolution)."
                    if self.stage == "full_text"
                    else "Run a search, then de-duplicate. Each cluster shows up here "
                    "for title / abstract screening."
                ),
            ).pack(pady=(0, 20))
            for b in (self.inc_btn, self.exc_btn, self.maybe_btn, self.prev_btn, self.next_btn):
                b.configure(state="disabled")
            return

        for b in (self.inc_btn, self.maybe_btn, self.prev_btn, self.next_btn):
            b.configure(state="normal")
        # Exclude requires either a code or the user to confirm w/o code.
        self.exc_btn.configure(state="normal")

        canonical = cluster.get("canonical") or {}
        title = canonical.get("title") or (
            cluster["members"][0]["title"] if cluster.get("members") else "(no title)"
        )

        # ---- header row: title + dedup-method badge ----------------------
        top = ctk.CTkFrame(self.card_inner, fg_color="transparent")
        top.pack(fill="x")
        ctk.CTkLabel(
            top,
            text=title,
            font=("SF Pro Display", 17, "bold"),
            text_color=T.INK,
            anchor="w",
            wraplength=560,
            justify="left",
        ).pack(side="left", fill="x", expand=True)
        Badge(top, cluster.get("method", "—"), variant="muted").pack(side="right", anchor="n")

        # ---- meta line ---------------------------------------------------
        meta_bits = []
        if canonical.get("authors"):
            meta_bits.append(canonical["authors"][:140])
        if canonical.get("year"):
            meta_bits.append(str(canonical["year"]))
        if canonical.get("journal"):
            meta_bits.append(canonical["journal"][:80])
        if meta_bits:
            ctk.CTkLabel(
                self.card_inner,
                text=" · ".join(meta_bits),
                text_color=T.INK_MUTE,
                font=T.FONT_SMALL,
                anchor="w",
                wraplength=580,
                justify="left",
            ).pack(anchor="w", pady=(6, 0))

        # ---- IDs (DOI / PMID) -------------------------------------------
        id_bits = []
        if canonical.get("doi"):
            id_bits.append(f"DOI {canonical['doi']}")
        if canonical.get("pmid"):
            id_bits.append(f"PMID {canonical['pmid']}")
        if id_bits:
            ctk.CTkLabel(
                self.card_inner,
                text="   ".join(id_bits),
                text_color=T.INK_MUTE,
                font=("SF Mono", 10),
                anchor="w",
            ).pack(anchor="w", pady=(2, 0))

        # ---- abstract ----------------------------------------------------
        abstract = canonical.get("abstract") or ""
        ctk.CTkLabel(
            self.card_inner,
            text="Abstract",
            font=("SF Pro Display", 12, "bold"),
            text_color=T.INK_SOFT,
            anchor="w",
        ).pack(anchor="w", pady=(14, 4))
        if abstract.strip():
            ctk.CTkLabel(
                self.card_inner,
                text=abstract,
                text_color=T.INK,
                font=T.FONT_BODY,
                anchor="w",
                justify="left",
                wraplength=580,
            ).pack(anchor="w")
        else:
            Helper(
                self.card_inner,
                "No abstract was captured. Decide on the title — or skip and add it during full-text screening.",
            ).pack(anchor="w")

        # ---- duplicate members (if cluster size > 1) --------------------
        if cluster.get("size", 1) > 1:
            ctk.CTkLabel(
                self.card_inner,
                text=f"Cluster size {cluster['size']} — duplicates folded in:",
                font=("SF Pro Display", 11, "bold"),
                text_color=T.INK_SOFT,
                anchor="w",
            ).pack(anchor="w", pady=(14, 4))
            for m in cluster.get("members", []):
                ctk.CTkLabel(
                    self.card_inner,
                    text="• " + (m.get("title") or "")[:160],
                    text_color=T.INK_MUTE,
                    font=T.FONT_SMALL,
                    anchor="w",
                    wraplength=560,
                    justify="left",
                ).pack(anchor="w", padx=4)

        self.counter.configure(text=f"{self.idx + 1} / {len(self.clusters)}")
        self._render_existing_decision(cluster)

    def _render_existing_decision(self, cluster: dict) -> None:
        existing = self.decisions_by_cluster.get(cluster["id"])
        if not existing:
            return
        variant = {"include": "ok", "exclude": "danger", "maybe": "warn"}.get(existing["decision"], "muted")
        Badge(self.existing_decision_row, f"already {existing['decision']}", variant=variant).pack(
            side="left", padx=(0, 8)
        )
        if existing.get("exclusion_code"):
            ctk.CTkLabel(
                self.existing_decision_row,
                text=f"reason: {existing['exclusion_code']}",
                font=("SF Mono", 10),
                text_color=T.INK_MUTE,
            ).pack(side="left")

    # ---------------------------------------------------------- codebook UI

    def _render_codebook(self) -> None:
        for c in self.codebook_inner.winfo_children():
            c.destroy()
        rules = _normalize_rules(self.codebook)
        if not rules:
            Helper(
                self.codebook_inner,
                "No codebook rules yet. Add rules in the Codebook phase to label "
                "include / exclude decisions with a structured reason.",
            ).pack(anchor="w", padx=4, pady=4)
            return
        for rule in rules:
            self._codebook_row(rule)

    def _codebook_row(self, rule: dict) -> None:
        wrap = ctk.CTkFrame(self.codebook_inner, fg_color="transparent")
        wrap.pack(fill="x", pady=3)
        tag = {"include": "ok", "exclude": "danger", "flag": "warn"}.get(rule["direction"], "muted")

        # Row header: action button + code badge.
        top = ctk.CTkFrame(wrap, fg_color="transparent")
        top.pack(fill="x")
        if rule["direction"] == "include":
            btn = ctk.CTkButton(
                top,
                text=f"✓ {rule['code']}",
                fg_color=T.OK,
                hover_color="#059669",
                text_color="white",
                height=26,
                width=110,
                font=("SF Pro Text", 11, "bold"),
                command=lambda r=rule: self._apply_rule(r),
            )
        elif rule["direction"] == "exclude":
            btn = ctk.CTkButton(
                top,
                text=f"✗ {rule['code']}",
                fg_color=T.DANGER,
                hover_color="#b91c1c",
                text_color="white",
                height=26,
                width=110,
                font=("SF Pro Text", 11, "bold"),
                command=lambda r=rule: self._arm_exclude_rule(r),
            )
        else:
            btn = ctk.CTkButton(
                top,
                text=f"⚑ {rule['code']}",
                fg_color=T.WARN,
                hover_color="#b45309",
                text_color="white",
                height=26,
                width=110,
                font=("SF Pro Text", 11, "bold"),
                command=lambda r=rule: self._apply_rule(r),
            )
        btn.pack(side="left", padx=(0, 6))
        Badge(top, rule["direction"], variant=tag).pack(side="left")
        Helper(wrap, rule.get("rationale") or "").pack(anchor="w", pady=(2, 0))

    def _render_rule_strip(self) -> None:
        for c in self.rule_strip_inner.winfo_children():
            c.destroy()
        # If a rule is armed, show the strip above the decision row.
        if self.active_exclude_rule:
            self.rule_strip.pack(fill="x", pady=(10, 0))
            ctk.CTkLabel(
                self.rule_strip_inner,
                text="Armed exclusion reason:",
                text_color=T.INK_MUTE,
                font=T.FONT_SMALL,
            ).pack(side="left")
            Badge(
                self.rule_strip_inner,
                self.active_exclude_rule["code"],
                variant="danger",
            ).pack(side="left", padx=8)
            ctk.CTkLabel(
                self.rule_strip_inner,
                text=self.active_exclude_rule.get("rationale", ""),
                text_color=T.INK,
                font=T.FONT_BODY,
                anchor="w",
            ).pack(side="left", fill="x", expand=True)
            SecondaryButton(self.rule_strip_inner, "Clear", command=self._clear_rule).pack(side="right")
        else:
            self.rule_strip.pack_forget()

    # ------------------------------------------------------------------- IRR

    def _refresh_irr(self) -> None:
        try:
            self.irr_data = self.app.rpc.call(
                "screening.irr",
                {"project_id": self.project["id"], "stage": self.stage},
            )
        except Exception:
            self.irr_data = None
        self._render_irr()

    def _render_irr(self) -> None:
        for c in self.irr_inner.winfo_children():
            c.destroy()
        ctk.CTkLabel(
            self.irr_inner,
            text="Inter-rater reliability",
            font=("SF Pro Display", 13, "bold"),
            text_color=T.INK,
        ).pack(anchor="w")

        irr = self.irr_data or {}
        target_alpha = (self.protocol or {}).get("reviewer_config", {}).get("alpha_threshold", 0.67)
        target_kappa = (self.protocol or {}).get("reviewer_config", {}).get("kappa_threshold", 0.60)
        n_rev = irr.get("n_reviewers", 0)
        n_items = irr.get("n_items", 0)

        if n_rev < 2:
            ctk.CTkLabel(
                self.irr_inner,
                text=f"Reviewers so far: {n_rev or 1}",
                text_color=T.INK_MUTE,
                font=T.FONT_SMALL,
            ).pack(anchor="w", pady=(6, 0))
            Helper(
                self.irr_inner,
                "Need ≥2 reviewers' decisions on the same items to compute α / κ. "
                "Import a collaborator's .prismaproj from Share to merge their decisions.",
            ).pack(anchor="w", pady=(2, 0))
            return

        def line(label: str, value, target=None, fmt="{:.3f}"):
            row = ctk.CTkFrame(self.irr_inner, fg_color="transparent")
            row.pack(fill="x", pady=2)
            ctk.CTkLabel(row, text=label, text_color=T.INK_MUTE, font=T.FONT_SMALL, anchor="w").pack(side="left")
            text = fmt.format(value) if isinstance(value, (int, float)) else str(value)
            colour = T.INK
            if target is not None and isinstance(value, (int, float)):
                colour = T.OK if value >= target else T.WARN
            ctk.CTkLabel(row, text=text, text_color=colour, font=("SF Mono", 11, "bold")).pack(side="right")

        alpha = irr.get("alpha_binary")
        kappa = irr.get("cohens_kappa") if n_rev == 2 else irr.get("fleiss_kappa")
        pa = irr.get("percent_agreement")
        line("Items rated by ≥2", n_items, fmt="{}")
        if alpha is not None:
            line("Krippendorff α", alpha, target=target_alpha)
        if kappa is not None:
            line(f"{'Cohen' if n_rev == 2 else 'Fleiss'} κ", kappa, target=target_kappa)
        if pa is not None:
            line("Percent agreement", pa * 100, fmt="{:.1f}%")
        line("Open conflicts", len(irr.get("conflicts") or []), fmt="{}")

        interp = irr.get("interpretation") or ""
        if interp:
            badge_variant = {
                "strong": "ok",
                "acceptable": "info",
                "weak": "warn",
                "no_better_than_chance": "danger",
            }.get(interp, "muted")
            row = ctk.CTkFrame(self.irr_inner, fg_color="transparent")
            row.pack(fill="x", pady=(6, 0))
            Badge(row, interp.replace("_", " "), variant=badge_variant).pack(side="left")

    # ---------------------------------------------------------------- actions

    def _arm_exclude_rule(self, rule: dict) -> None:
        """Arm an exclude rule as the next decision's reason."""
        self.active_exclude_rule = rule
        self._render_rule_strip()
        self.app.toast(
            f"Armed exclude reason: {rule['code']}",
            "Press E or click ✗ Exclude to apply.",
            variant="info",
        )

    def _clear_rule(self) -> None:
        self.active_exclude_rule = None
        self._render_rule_strip()

    def _apply_rule(self, rule: dict) -> None:
        """Apply an include / flag rule immediately to the current cluster."""
        if rule["direction"] == "include":
            self._decide("include", code=rule["code"])
        elif rule["direction"] == "flag":
            self._decide("maybe", code=rule["code"])
        else:
            self._arm_exclude_rule(rule)

    def _decide(self, decision: str, code: str | None = None) -> None:
        cluster = self._current_cluster()
        if cluster is None:
            return
        exclusion_code = None
        if decision == "exclude":
            if code is None and self.active_exclude_rule:
                exclusion_code = self.active_exclude_rule["code"]
            elif code is not None:
                exclusion_code = code
            if exclusion_code is None and self.stage == "full_text":
                self.app.toast(
                    "Reason required",
                    "Full-text exclusions need a codebook reason (PRISMA item 16b). "
                    "Arm an exclude rule on the right first.",
                    variant="warn",
                )
                return
        try:
            self.app.rpc.call(
                "screening.decision",
                {
                    "project_id": self.project["id"],
                    "cluster_id": cluster["id"],
                    "stage": self.stage,
                    "decision": decision,
                    "exclusion_code": exclusion_code,
                },
            )
        except Exception as e:
            self.app.toast("Couldn't record decision", str(e), variant="danger")
            return
        # Update local decisions cache + clear armed rule on exclude.
        self.decisions_by_cluster[cluster["id"]] = {
            "decision": decision,
            "exclusion_code": exclusion_code,
            "cluster_id": cluster["id"],
        }
        if decision == "exclude":
            self.active_exclude_rule = None
            self._render_rule_strip()
        self._refresh_irr()
        if self.idx >= len(self.clusters) - 1:
            # Last study: nothing to advance to, so re-render in place and
            # let the sidebar re-check whether the next phase just opened.
            self._render()
            self.app.refresh_project_phases()
        else:
            self._advance(1)

    def _advance(self, delta: int) -> None:
        if not self.clusters:
            return
        new_idx = self.idx + delta
        if 0 <= new_idx < len(self.clusters):
            self.idx = new_idx
            self._render()
