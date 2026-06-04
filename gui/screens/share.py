"""Share / import .prismaproj files."""

from __future__ import annotations

import customtkinter as ctk
from tkinter import filedialog

from gui import theme as T
from gui.widgets import Badge, Card, Helper, PrimaryButton, SecondaryButton


class SharePanel(ctk.CTkFrame):
    def __init__(self, master, app, project):
        super().__init__(master, fg_color=T.PAPER)
        self.app = app
        self.project = project
        self.preview = None
        self.import_path = None
        self.resolutions: dict[str, str] = {}
        self._build()

    def _build(self) -> None:
        ctk.CTkLabel(self, text="Share / import", font=("SF Pro Display", 16, "bold"), text_color=T.INK).pack(anchor="w", pady=(0, 8))
        Helper(
            self,
            "Exchange a complete project state with a collaborator via .prismaproj — "
            "a deterministic content-addressed zip.",
        ).pack(anchor="w", pady=(0, 12))

        cards = ctk.CTkFrame(self, fg_color="transparent")
        cards.pack(fill="x")

        export = Card(cards)
        export.pack(side="left", fill="both", expand=True, padx=(0, 8))
        ei = ctk.CTkFrame(export, fg_color="transparent")
        ei.pack(fill="x", padx=18, pady=14)
        ctk.CTkLabel(ei, text="Export", font=("SF Pro Display", 14, "bold"), text_color=T.INK).pack(anchor="w")
        Helper(ei, "Save a .prismaproj you can hand to a collaborator.").pack(anchor="w", pady=(4, 10))
        PrimaryButton(ei, "Export…", command=self._export).pack(anchor="w")

        importc = Card(cards)
        importc.pack(side="left", fill="both", expand=True, padx=(8, 0))
        ii = ctk.CTkFrame(importc, fg_color="transparent")
        ii.pack(fill="x", padx=18, pady=14)
        ctk.CTkLabel(ii, text="Import", font=("SF Pro Display", 14, "bold"), text_color=T.INK).pack(anchor="w")
        Helper(ii, "Pick a .prismaproj. You'll see a non-destructive diff before merging.").pack(anchor="w", pady=(4, 10))
        SecondaryButton(ii, "Choose file…", command=self._preview_import).pack(anchor="w")

        self.preview_wrap = ctk.CTkScrollableFrame(self, fg_color=T.PAPER)
        self.preview_wrap.pack(fill="both", expand=True, pady=(16, 0))

    def _export(self) -> None:
        path = filedialog.asksaveasfilename(
            defaultextension=".prismaproj",
            initialfile=f"{self.project['slug']}.prismaproj",
            filetypes=[("PrismAPI project", "*.prismaproj"), ("All files", "*")],
        )
        if not path:
            return
        try:
            self.app.rpc.call("statefile.export", {"project_id": self.project["id"], "output_path": path})
            self.app.toast("Exported", path, variant="ok")
        except Exception as e:  # noqa: BLE001
            self.app.toast("Export failed", str(e), variant="danger")

    def _preview_import(self) -> None:
        path = filedialog.askopenfilename(
            filetypes=[("PrismAPI project", "*.prismaproj"), ("All", "*")],
        )
        if not path:
            return
        try:
            res = self.app.rpc.call("statefile.preview_import", {"input_path": path})
        except Exception as e:  # noqa: BLE001
            self.app.toast("Couldn't preview", str(e), variant="danger")
            return
        self.import_path = path
        self.preview = res
        self.resolutions = {}
        self._render_preview()

    def _render_preview(self) -> None:
        for c in self.preview_wrap.winfo_children():
            c.destroy()
        if not self.preview:
            return
        man = self.preview["manifest"]
        diff = self.preview["diff"]

        head_card = Card(self.preview_wrap)
        head_card.pack(fill="x", pady=4)
        inner = ctk.CTkFrame(head_card, fg_color="transparent")
        inner.pack(fill="x", padx=18, pady=14)
        ctk.CTkLabel(inner, text="Import preview", font=("SF Pro Display", 14, "bold"), text_color=T.INK).pack(anchor="w")
        Helper(inner, f"From {man['exporter']['display_name']} — {man['exported_at'][:19].replace('T', ' ')}").pack(anchor="w", pady=(2, 8))

        added = diff.get("counts_added", {})
        if added:
            grid = ctk.CTkFrame(inner, fg_color="transparent")
            grid.pack(fill="x", pady=(0, 8))
            for i, (k, v) in enumerate(added.items()):
                if not v:
                    continue
                box = ctk.CTkFrame(grid, fg_color=T.PAPER_WARM, corner_radius=8)
                box.grid(row=i // 4, column=i % 4, sticky="ew", padx=4, pady=4)
                ctk.CTkLabel(box, text=k.replace("_", " "), text_color=T.INK_MUTE, font=T.FONT_SMALL).pack(padx=10, pady=(8, 0))
                ctk.CTkLabel(box, text=f"+{v}", text_color=T.INK, font=("SF Pro Display", 14, "bold")).pack(padx=10, pady=(0, 8))

        conflicts = diff.get("conflicts") or []
        if conflicts:
            ctk.CTkLabel(
                self.preview_wrap,
                text=f"Conflicts ({len(conflicts)}) — pick a resolution for each",
                font=("SF Pro Display", 13, "bold"),
                text_color=T.INK,
            ).pack(anchor="w", pady=(8, 4))
            for c in conflicts:
                self._render_conflict(c)

        nav = ctk.CTkFrame(self.preview_wrap, fg_color="transparent")
        nav.pack(fill="x", pady=12)
        SecondaryButton(nav, "Discard", command=self._discard).pack(side="left")
        ready = all(self._key(c) in self.resolutions for c in conflicts)
        PrimaryButton(
            nav,
            "Apply merge",
            command=self._merge,
            state="normal" if ready else "disabled",
        ).pack(side="right")

    def _key(self, c: dict) -> str:
        return c["kind"] + ":" + "|".join(f"{k}={v}" for k, v in sorted(c["key"].items()))

    def _render_conflict(self, c: dict) -> None:
        card = Card(self.preview_wrap)
        card.pack(fill="x", pady=3)
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=16, pady=12)
        top = ctk.CTkFrame(inner, fg_color="transparent")
        top.pack(fill="x")
        Badge(top, c["kind"], variant="warn").pack(side="left")
        ctk.CTkLabel(top, text=" · ".join(f"{k}={v}" for k, v in c["key"].items()), font=("SF Mono", 10), text_color=T.INK_MUTE).pack(side="left", padx=(8, 0))

        comp = ctk.CTkFrame(inner, fg_color="transparent")
        comp.pack(fill="x", pady=8)
        for col, label, blob in [(0, "Local", c.get("local") or {}), (1, "Incoming", c.get("incoming") or {})]:
            side = ctk.CTkFrame(comp, fg_color=T.PAPER_WARM, corner_radius=6)
            side.grid(row=0, column=col, sticky="ew", padx=4)
            comp.grid_columnconfigure(col, weight=1)
            ctk.CTkLabel(side, text=label, font=("SF Pro Text", 11, "bold"), text_color=T.INK_SOFT).pack(anchor="w", padx=10, pady=(8, 2))
            ctk.CTkLabel(side, text=str(blob), font=("SF Mono", 10), text_color=T.INK, wraplength=300, justify="left").pack(anchor="w", padx=10, pady=(0, 8))

        opts = ctk.CTkFrame(inner, fg_color="transparent")
        opts.pack(fill="x", pady=(4, 0))
        key = self._key(c)
        for opt in ("keep_local", "keep_incoming", "keep_both"):
            active = self.resolutions.get(key) == opt
            btn = ctk.CTkButton(
                opts,
                text=opt.replace("_", " "),
                command=lambda k=key, o=opt: self._set_res(k, o),
                fg_color=T.PRISM_600 if active else T.PAPER_CARD,
                text_color="white" if active else T.INK_SOFT,
                hover_color=T.PRISM_700,
                border_color=T.BORDER,
                border_width=1,
                corner_radius=6,
                font=("SF Pro Text", 11),
                height=28,
            )
            btn.pack(side="left", padx=(0, 6))

    def _set_res(self, key: str, opt: str) -> None:
        self.resolutions[key] = opt
        self._render_preview()

    def _discard(self) -> None:
        self.preview = None
        self.import_path = None
        self.resolutions = {}
        for c in self.preview_wrap.winfo_children():
            c.destroy()

    def _merge(self) -> None:
        if not self.import_path:
            return
        try:
            self.app.rpc.call(
                "statefile.merge",
                {
                    "input_path": self.import_path,
                    "resolutions": self.resolutions,
                    "take_pre_import_snapshot": True,
                },
            )
            self.app.toast("Merge applied", variant="ok")
            self._discard()
        except Exception as e:  # noqa: BLE001
            self.app.toast("Merge failed", str(e), variant="danger")
