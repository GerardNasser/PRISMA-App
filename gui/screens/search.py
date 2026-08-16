"""Search panel — script generator + RIS / results importer.

The app no longer makes live API calls. Instead you:
  1. Pick a database + write a query + set parameters.
  2. The app writes a self-contained Python script with those parameters baked in.
  3. You run that script outside the app (with your API keys configured).
  4. The script produces a JSON file that you import back here.

Why: keeps API keys, rate limits, and network policy out of the desktop app.
The .py file is auditable, modifiable, and re-runnable.
"""

from __future__ import annotations

from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk

from gui import theme as T
from gui.widgets import Badge, Card, Field, GhostButton, Helper, PrimaryButton, SecondaryButton


_DB_BLURBS = {
    "pubmed": "NCBI E-utilities (no key needed; bumped rate limit with NCBI_API_KEY).",
    "openalex": "OpenAlex; polite-pool email via OPENALEX_EMAIL.",
    "crossref": "CrossRef metadata; polite-pool via OPENALEX_EMAIL.",
}


class SearchPanel(ctk.CTkFrame):
    def __init__(self, master, app, project):
        super().__init__(master, fg_color=T.PAPER)
        self.app = app
        self.project = project
        try:
            self.adapters = self.app.rpc.call("searches.adapters")["adapters"]
        except Exception:
            self.adapters = []
        self._build()
        self.refresh()

    def _build(self) -> None:
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(head, text="Search", font=("SF Pro Display", 16, "bold"), text_color=T.INK).pack(side="left")
        Helper(
            self,
            "PrismAPI doesn't run live API calls itself. Generate a Python script with your "
            "search parameters baked in, run it where you have API keys configured, then import "
            "the resulting JSON. Or upload a RIS export directly.",
        ).pack(anchor="w", pady=(0, 12))

        wrap = ctk.CTkScrollableFrame(self, fg_color=T.PAPER)
        wrap.pack(fill="both", expand=True)

        # === Generate API script card ===
        card = Card(wrap)
        card.pack(fill="x", pady=4)
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=18, pady=14)
        ctk.CTkLabel(
            inner, text="Generate a search script", font=("SF Pro Display", 14, "bold"), text_color=T.INK
        ).pack(anchor="w")
        Helper(
            inner,
            "Pick the database + a query. We'll save a Python file you can run wherever you "
            "want. The script writes a prismapi-search/1 JSON file you import back here.",
        ).pack(anchor="w", pady=(2, 10))

        # Choices: only template-supported databases here. For other DBs use RIS import.
        db_choices = [a["id"] for a in self.adapters if a["id"] in ("pubmed", "openalex", "crossref")]
        if not db_choices:
            db_choices = ["pubmed", "openalex", "crossref"]
        self.db_field = Field(inner, "Database", kind="select", options=db_choices, initial=db_choices[0])
        self.db_field.pack(fill="x", pady=(0, 6))

        # Live blurb for the chosen database.
        self.db_blurb = Helper(inner, _DB_BLURBS.get(db_choices[0], ""))
        self.db_blurb.pack(anchor="w", pady=(0, 8))

        def _on_db(*_):
            self.db_blurb.configure(text=_DB_BLURBS.get(self.db_field.get(), ""))

        if self.db_field.var is not None:
            self.db_field.var.trace_add("write", _on_db)

        self.query_field = Field(
            inner,
            "Query",
            placeholder='(indoor plant OR green wall) AND microbiome',
            kind="textbox",
        )
        self.query_field.pack(fill="x", pady=(0, 8))

        grid = ctk.CTkFrame(inner, fg_color="transparent")
        grid.pack(fill="x", pady=(0, 8))
        grid.grid_columnconfigure(0, weight=1)
        grid.grid_columnconfigure(1, weight=1)
        grid.grid_columnconfigure(2, weight=1)

        self.max_field = Field(grid, "Max results", initial="500")
        self.max_field.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.df_field = Field(grid, "Date from (YYYY/MM/DD)", placeholder="2010/01/01")
        self.df_field.grid(row=0, column=1, sticky="ew", padx=8)
        self.dt_field = Field(grid, "Date to (YYYY/MM/DD)", placeholder="")
        self.dt_field.grid(row=0, column=2, sticky="ew", padx=(8, 0))

        btn_row = ctk.CTkFrame(inner, fg_color="transparent")
        btn_row.pack(fill="x", pady=(2, 0))
        PrimaryButton(btn_row, "Save script…", command=self._generate).pack(side="right")

        # === Import results card ===
        card = Card(wrap)
        card.pack(fill="x", pady=4)
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=18, pady=14)
        ctk.CTkLabel(
            inner, text="Import results", font=("SF Pro Display", 14, "bold"), text_color=T.INK
        ).pack(anchor="w")
        Helper(
            inner,
            "Pick the JSON file the script wrote. It looks like "
            "`{project-slug}_{database}_{timestamp}.json` by default.",
        ).pack(anchor="w", pady=(2, 10))
        SecondaryButton(inner, "Pick JSON…", command=self._import_results).pack(side="left", padx=(0, 8))

        # === RIS upload card ===
        card = Card(wrap)
        card.pack(fill="x", pady=4)
        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=18, pady=14)
        ctk.CTkLabel(
            inner, text="…or upload a RIS export", font=("SF Pro Display", 14, "bold"), text_color=T.INK
        ).pack(anchor="w")
        Helper(
            inner,
            "For databases without an open API (Web of Science, CINAHL, EBSCO, etc.) export "
            "from the vendor UI as .ris/.nbib and upload directly.",
        ).pack(anchor="w", pady=(2, 10))
        SecondaryButton(inner, "Pick RIS file…", command=self._import_ris).pack(side="left")

        # === History ===
        self.history = Card(wrap)
        self.history.pack(fill="x", pady=4)
        self.history_inner = ctk.CTkFrame(self.history, fg_color="transparent")
        self.history_inner.pack(fill="x", padx=18, pady=14)

    def refresh(self) -> None:
        for c in self.history_inner.winfo_children():
            c.destroy()
        ctk.CTkLabel(
            self.history_inner,
            text="Search history",
            font=("SF Pro Display", 14, "bold"),
            text_color=T.INK,
        ).pack(anchor="w")
        try:
            res = self.app.rpc.call("searches.list", {"project_id": self.project["id"]})
        except Exception as e:  # noqa: BLE001
            Helper(self.history_inner, f"Couldn't load history: {e}").pack(anchor="w", pady=(8, 0))
            return
        if not res["searches"]:
            Helper(self.history_inner, "No searches yet.").pack(anchor="w", pady=(8, 0))
            return
        for s in res["searches"]:
            row = ctk.CTkFrame(self.history_inner, fg_color="transparent")
            row.pack(fill="x", pady=6)
            Badge(row, s["database"], variant="info").pack(side="left", padx=(0, 8))
            ctk.CTkLabel(
                row,
                text=(s["query_string"][:90] + "…") if len(s["query_string"]) > 90 else s["query_string"],
                font=T.FONT_BODY,
                text_color=T.INK,
                anchor="w",
                wraplength=420,
                justify="left",
            ).pack(side="left", fill="x", expand=True)
            ctk.CTkLabel(
                row,
                text=f"{s['hit_count']} hits · {s['status']}",
                font=T.FONT_SMALL,
                text_color={"completed": T.OK, "failed": T.DANGER}.get(s["status"], T.INK_MUTE),
            ).pack(side="right")

    # ---- actions ----

    def _generate(self) -> None:
        query = self.query_field.get()
        if not query.strip():
            self.app.toast("Type a query first", variant="warn")
            return
        try:
            max_results = int(self.max_field.get() or "500")
        except ValueError:
            self.app.toast("Max results must be a number", variant="warn")
            return

        try:
            res = self.app.rpc.call(
                "searches.generate_script",
                {
                    "project_id": self.project["id"],
                    "database": self.db_field.get(),
                    "query": query,
                    "max_results": max_results,
                    "date_from": self.df_field.get() or "",
                    "date_to": self.dt_field.get() or "",
                },
            )
        except Exception as e:  # noqa: BLE001
            self.app.toast("Couldn't generate script", str(e), variant="danger")
            return

        target = filedialog.asksaveasfilename(
            title="Save search script",
            defaultextension=".py",
            initialfile=res["suggested_filename"],
            filetypes=[("Python file", "*.py"), ("All files", "*")],
        )
        if not target:
            return
        try:
            Path(target).write_text(res["script"], encoding="utf-8")
        except Exception as e:  # noqa: BLE001
            self.app.toast("Couldn't write script", str(e), variant="danger")
            return

        self.app.toast(
            "Script saved",
            f"Run: python {Path(target).name}\nThen import the JSON it writes.",
            variant="ok",
        )

    def _import_results(self) -> None:
        path = filedialog.askopenfilename(
            title="Pick a search-results JSON",
            filetypes=[("JSON", "*.json"), ("All", "*")],
        )
        if not path:
            return
        def _done(res: dict) -> None:
            self.app.toast(
                f"Imported {res['inserted']} records",
                f"from {res['database']}; skipped {res['skipped']}",
                variant="ok",
            )
            self.refresh()
            self.app.refresh_project_phases()

        self.app.rpc_bg(
            "searches.import_results",
            {"project_id": self.project["id"], "input_path": path},
            on_done=_done,
            on_error=lambda e: self.app.toast("Import failed", str(e), variant="danger"),
            widget=self,
        )

    def _import_ris(self) -> None:
        path = filedialog.askopenfilename(
            title="Pick a RIS export",
            filetypes=[("RIS / NBIB / text", "*.ris *.nbib *.txt"), ("All", "*")],
        )
        if not path:
            return
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                payload = fh.read()
        except Exception as e:  # noqa: BLE001
            self.app.toast("Couldn't read file", str(e), variant="danger")
            return
        def _done(res: dict) -> None:
            self.app.toast(f"Imported {res['hit_count']} records", variant="ok")
            self.refresh()
            self.app.refresh_project_phases()

        self.app.rpc_bg(
            "searches.run",
            {
                "project_id": self.project["id"],
                "database": "ris_import",
                "query": f"RIS upload: {Path(path).name}",
                "payload": payload,
            },
            on_done=_done,
            on_error=lambda e: self.app.toast("Import failed", str(e), variant="danger"),
            widget=self,
        )
