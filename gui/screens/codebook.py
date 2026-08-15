"""Codebook editor."""

from __future__ import annotations

import customtkinter as ctk

from gui import theme as T
from gui.widgets import Badge, Card, Field, GhostButton, Helper, PrimaryButton, SecondaryButton


class CodebookPanel(ctk.CTkFrame):
    def __init__(self, master, app, project):
        super().__init__(master, fg_color=T.PAPER)
        self.app = app
        self.project = project
        self.rules: list[dict] = []
        self._build()
        self._load()

    def _build(self) -> None:
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(head, text="Codebook", font=("SF Pro Display", 16, "bold"), text_color=T.INK).pack(side="left")
        self.version_badge = Badge(head, "v—", variant="muted")
        self.version_badge.pack(side="right")
        Helper(self, "Inclusion / exclusion rules that anchor your screening decisions.").pack(anchor="w", pady=(0, 12))

        self.list_wrap = ctk.CTkScrollableFrame(self, fg_color=T.PAPER, height=400)
        self.list_wrap.pack(fill="both", expand=True)

        tools = ctk.CTkFrame(self, fg_color="transparent")
        tools.pack(fill="x", pady=12)
        SecondaryButton(tools, "+ Add rule", command=self._add_rule).pack(side="left")
        PrimaryButton(tools, "Save new version", command=self._save).pack(side="right")

    def _load(self) -> None:
        try:
            latest = self.app.rpc.call("codebooks.latest", {"project_id": self.project["id"]})
        except Exception:
            latest = None
        if latest is None:
            self.rules = []
            self.version_badge.configure(text="v1 next")
        else:
            self.rules = [
                {
                    "code": r["code"],
                    "direction": r["direction"],
                    "category": r.get("category") or "",
                    "rationale": r["rationale"],
                }
                for r in latest["rules"]
            ]
            self.version_badge.configure(text=f"v{latest['version'] + 1} next")
        self._refresh()

    def _refresh(self) -> None:
        self._rationale_fields: dict[int, Field] = {}
        for c in self.list_wrap.winfo_children():
            c.destroy()
        if not self.rules:
            ctk.CTkLabel(
                self.list_wrap,
                text="No rules yet. Click “+ Add rule”.",
                text_color=T.INK_MUTE,
                font=T.FONT_BODY,
            ).pack(pady=24)
            return
        for i, r in enumerate(self.rules):
            self._render_rule(i, r)

    def _render_rule(self, idx: int, r: dict) -> None:
        card = Card(self.list_wrap)
        card.pack(fill="x", pady=4)
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=16, pady=12)

        top = ctk.CTkFrame(inner, fg_color="transparent")
        top.pack(fill="x")
        Badge(top, r["direction"], variant={"include": "ok", "exclude": "danger", "flag": "warn"}.get(r["direction"], "muted")).pack(side="left", padx=(0, 8))
        ctk.CTkLabel(top, text=r["code"], font=("SF Mono", 11, "bold"), text_color=T.INK).pack(side="left")
        GhostButton(top, "Remove", command=lambda i=idx: self._remove(i)).pack(side="right")

        code_field = Field(inner, "Code", initial=r["code"], placeholder="EXC-OUTDOOR")
        code_field.pack(fill="x", pady=(8, 4))
        code_field.var.trace_add("write", lambda *_: self._update(idx, "code", code_field.get()))

        dir_field = Field(inner, "Direction", kind="select", options=["include", "exclude", "flag"], initial=r["direction"])
        dir_field.pack(fill="x", pady=4)
        dir_field.var.trace_add("write", lambda *_: self._update(idx, "direction", dir_field.get()))

        cat_field = Field(inner, "Category (optional)", initial=r.get("category", ""))
        cat_field.pack(fill="x", pady=4)
        cat_field.var.trace_add("write", lambda *_: self._update(idx, "category", cat_field.get()))

        rat_field = Field(inner, "Rationale", kind="textbox", initial=r["rationale"])
        rat_field.pack(fill="x", pady=4)
        # Textboxes have no StringVar. FocusOut keeps self.rules roughly in
        # sync, but _save reads the widgets directly — FocusOut does not fire
        # when a button is clicked on macOS.
        rat_field.widget.bind("<FocusOut>", lambda _e, i=idx, w=rat_field: self._update(i, "rationale", w.get()))
        self._rationale_fields[idx] = rat_field

    def _update(self, idx: int, key: str, value) -> None:
        if idx < len(self.rules):
            self.rules[idx][key] = value

    def _add_rule(self) -> None:
        self.rules.append({"code": "", "direction": "include", "category": "", "rationale": ""})
        self._refresh()

    def _remove(self, idx: int) -> None:
        if 0 <= idx < len(self.rules):
            self.rules.pop(idx)
        self._refresh()

    def _save(self) -> None:
        # Read rationale straight from the live widgets: relying on FocusOut
        # loses freshly typed text when Save is clicked directly.
        for idx, fld in getattr(self, "_rationale_fields", {}).items():
            try:
                self._update(idx, "rationale", fld.get())
            except Exception:  # noqa: BLE001 - widget already destroyed
                continue
        valid = [r for r in self.rules if r["code"].strip() and r["rationale"].strip()]
        if not valid:
            self.app.toast("Need at least one rule with code + rationale", variant="warn")
            return
        try:
            res = self.app.rpc.call(
                "codebooks.save",
                {
                    "project_id": self.project["id"],
                    "rules": [
                        {
                            "code": r["code"],
                            "direction": r["direction"],
                            "category": r.get("category") or None,
                            "rationale": r["rationale"],
                            "examples": [],
                        }
                        for r in valid
                    ],
                },
            )
            self.app.toast(f"Codebook saved (v{res['version']})", variant="ok")
            self._load()
        except Exception as e:  # noqa: BLE001
            self.app.toast("Couldn't save codebook", str(e), variant="danger")
