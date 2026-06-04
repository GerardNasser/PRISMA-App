"""First-run identity capture: last name + ORCID OR affiliate email."""

from __future__ import annotations

import customtkinter as ctk

from gui import theme as T
from gui.rpc_client import RpcError
from gui.widgets import Card, Field, Helper, PrimaryButton


class OnboardingFrame(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color=T.PAPER_WARM)
        self.app = app
        self._build()

    def _build(self) -> None:
        wrap = ctk.CTkFrame(self, fg_color="transparent")
        wrap.pack(expand=True)

        # Logo + title
        header = ctk.CTkFrame(wrap, fg_color="transparent")
        header.pack(pady=(40, 16))
        logo = ctk.CTkLabel(
            header,
            text="P",
            text_color="white",
            fg_color=T.PRISM_600,
            corner_radius=10,
            width=44,
            height=44,
            font=("SF Pro Display", 22, "bold"),
        )
        logo.grid(row=0, column=0, padx=(0, 10))
        ctk.CTkLabel(
            header,
            text="PrismAPI",
            text_color=T.INK,
            font=("SF Pro Display", 22, "bold"),
        ).grid(row=0, column=1)

        ctk.CTkLabel(
            wrap,
            text="Set up your reviewer profile",
            font=("SF Pro Display", 20, "bold"),
            text_color=T.INK,
        ).pack(pady=(0, 6))
        Helper(
            wrap,
            "This stays on your machine. Your name + ORCID or email travel "
            "with project exports so collaborators see attribution on your work.",
        ).pack(padx=24)

        card = Card(wrap, width=460)
        card.pack(pady=24, padx=24)

        body = ctk.CTkFrame(card, fg_color="transparent")
        body.pack(padx=24, pady=20, fill="x")

        self.last_name = Field(body, "Last name", required=True, placeholder="Nasser")
        self.last_name.pack(fill="x", pady=(0, 12))

        # Either-or container
        group = ctk.CTkFrame(body, fg_color=T.PAPER_WARM, corner_radius=8)
        group.pack(fill="x", pady=(2, 12))
        inner = ctk.CTkFrame(group, fg_color="transparent")
        inner.pack(padx=12, pady=10, fill="x")
        ctk.CTkLabel(
            inner,
            text="PROVIDE AT LEAST ONE",
            text_color=T.INK_MUTE,
            font=("SF Pro Text", 10, "bold"),
            anchor="w",
        ).pack(fill="x", pady=(0, 6))
        self.orcid = Field(
            inner,
            "ORCID",
            placeholder="0000-0001-2345-6789",
            helper="Free at orcid.org. Cross-install identity matching.",
        )
        self.orcid.pack(fill="x", pady=(2, 10))
        self.email = Field(
            inner,
            "Affiliate email",
            placeholder="gerard@uncc.edu",
            helper="University / work email recommended; drives your display name.",
        )
        self.email.pack(fill="x", pady=(2, 0))

        self.institution = Field(body, "Institution (optional)", placeholder="UNC Charlotte")
        self.institution.pack(fill="x", pady=(0, 12))

        self.error = ctk.CTkLabel(
            body, text="", text_color=T.DANGER, font=T.FONT_SMALL, anchor="w", wraplength=400, justify="left"
        )
        self.error.pack(fill="x", pady=(0, 8))

        PrimaryButton(body, "Continue", command=self._submit).pack(fill="x")

    def _submit(self) -> None:
        self.error.configure(text="")
        try:
            identity = self.app.rpc.call(
                "identity.set",
                {
                    "last_name": self.last_name.get(),
                    "orcid": self.orcid.get() or None,
                    "email": self.email.get() or None,
                    "institution": self.institution.get() or None,
                },
            )
            self.app.set_identity(identity)
            self.app.show_projects()
        except RpcError as e:
            self.error.configure(text=e.message)
        except Exception as e:  # noqa: BLE001
            self.error.configure(text=str(e))
