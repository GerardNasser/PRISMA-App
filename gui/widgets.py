"""Small composable widgets used across screens."""

from __future__ import annotations

from typing import Callable

import customtkinter as ctk

from gui import theme as T


class Card(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(
            master,
            fg_color=T.PAPER_CARD,
            border_color=T.BORDER,
            border_width=1,
            corner_radius=10,
            **kwargs,
        )


class SectionLabel(ctk.CTkLabel):
    def __init__(self, master, text: str, **kwargs):
        super().__init__(
            master,
            text=text,
            text_color=T.INK_SOFT,
            font=("SF Pro Display", 14, "bold"),
            anchor="w",
            **kwargs,
        )


class Helper(ctk.CTkLabel):
    def __init__(self, master, text: str, **kwargs):
        super().__init__(
            master,
            text=text,
            text_color=T.INK_MUTE,
            font=T.FONT_SMALL,
            anchor="w",
            wraplength=520,
            justify="left",
            **kwargs,
        )


class PrimaryButton(ctk.CTkButton):
    def __init__(self, master, text: str, command: Callable | None = None, **kwargs):
        super().__init__(
            master,
            text=text,
            command=command,
            fg_color=T.PRISM_600,
            hover_color=T.PRISM_700,
            text_color="white",
            corner_radius=8,
            font=("SF Pro Text", 13, "bold"),
            height=36,
            **kwargs,
        )


class SecondaryButton(ctk.CTkButton):
    def __init__(self, master, text: str, command: Callable | None = None, **kwargs):
        super().__init__(
            master,
            text=text,
            command=command,
            fg_color=T.PAPER_CARD,
            hover_color=T.PAPER_WARM,
            text_color=T.INK,
            border_color=T.BORDER,
            border_width=1,
            corner_radius=8,
            font=("SF Pro Text", 13),
            height=36,
            **kwargs,
        )


class DangerButton(ctk.CTkButton):
    def __init__(self, master, text: str, command: Callable | None = None, **kwargs):
        super().__init__(
            master,
            text=text,
            command=command,
            fg_color=T.DANGER,
            hover_color="#b91c1c",
            text_color="white",
            corner_radius=8,
            font=("SF Pro Text", 13, "bold"),
            height=36,
            **kwargs,
        )


class GhostButton(ctk.CTkButton):
    def __init__(self, master, text: str, command: Callable | None = None, **kwargs):
        super().__init__(
            master,
            text=text,
            command=command,
            fg_color="transparent",
            hover_color=T.PAPER_WARM,
            text_color=T.INK_SOFT,
            corner_radius=8,
            font=("SF Pro Text", 13),
            height=32,
            **kwargs,
        )


class Badge(ctk.CTkLabel):
    def __init__(self, master, text: str, variant: str = "info", **kwargs):
        colors = {
            "info": (T.PRISM_100, T.PRISM_700),
            "ok": ("#d1fae5", "#065f46"),
            "warn": ("#fef3c7", "#92400e"),
            "danger": ("#fee2e2", "#991b1b"),
            "muted": ("#e2e8f0", T.INK_SOFT),
        }
        bg, fg = colors.get(variant, colors["info"])
        super().__init__(
            master,
            text=text,
            fg_color=bg,
            text_color=fg,
            corner_radius=10,
            padx=8,
            pady=2,
            font=("SF Pro Text", 10, "bold"),
            **kwargs,
        )


class Field(ctk.CTkFrame):
    """A labelled input with optional helper text."""

    def __init__(
        self,
        master,
        label: str,
        *,
        required: bool = False,
        helper: str | None = None,
        placeholder: str = "",
        kind: str = "entry",
        options: list[str] | None = None,
        initial: str = "",
        **kwargs,
    ):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.label_text = label
        self.required = required
        title = label + (" *" if required else "")
        self.label_widget = ctk.CTkLabel(
            self,
            text=title,
            text_color=T.INK_SOFT,
            font=("SF Pro Text", 12, "bold"),
            anchor="w",
        )
        self.label_widget.pack(fill="x", padx=2, pady=(0, 4))
        if kind == "entry":
            self.var = ctk.StringVar(value=initial)
            self.widget = ctk.CTkEntry(
                self,
                textvariable=self.var,
                placeholder_text=placeholder,
                fg_color=T.PAPER_CARD,
                border_color=T.BORDER,
                text_color=T.INK,
                height=36,
            )
            self.widget.pack(fill="x")
        elif kind == "textbox":
            self.widget = ctk.CTkTextbox(
                self,
                height=120,
                fg_color=T.PAPER_CARD,
                border_color=T.BORDER,
                text_color=T.INK,
                border_width=1,
            )
            if initial:
                self.widget.insert("1.0", initial)
            self.widget.pack(fill="x")
            self.var = None
        elif kind == "select":
            self.var = ctk.StringVar(value=initial or (options[0] if options else ""))
            self.widget = ctk.CTkOptionMenu(
                self,
                values=options or [""],
                variable=self.var,
                fg_color=T.PAPER_CARD,
                button_color=T.BORDER,
                button_hover_color=T.PAPER_WARM,
                text_color=T.INK,
            )
            self.widget.pack(fill="x")
        elif kind == "checkbox":
            self.var = ctk.BooleanVar(value=bool(initial))
            self.widget = ctk.CTkCheckBox(
                self,
                text="",
                variable=self.var,
                fg_color=T.PRISM_600,
                hover_color=T.PRISM_700,
                text_color=T.INK,
            )
            self.widget.pack(anchor="w")
        else:
            raise ValueError(f"Unknown field kind: {kind}")

        if helper:
            self.helper_widget = Helper(self, helper)
            self.helper_widget.pack(fill="x", padx=2, pady=(4, 0))

    def get(self) -> str:
        if isinstance(self.widget, ctk.CTkTextbox):
            return self.widget.get("1.0", "end").strip()
        if hasattr(self, "var") and self.var is not None:
            value = self.var.get()
            if isinstance(value, bool):
                return value
            return value.strip() if isinstance(value, str) else value
        return ""

    def set(self, value: str) -> None:
        if isinstance(self.widget, ctk.CTkTextbox):
            self.widget.delete("1.0", "end")
            self.widget.insert("1.0", value)
        elif self.var is not None:
            self.var.set(value)


class Toast(ctk.CTkToplevel):
    """Brief floating notification."""

    def __init__(self, master, title: str, description: str = "", variant: str = "info"):
        super().__init__(master)
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        color = {
            "info": T.PRISM_600,
            "ok": T.OK,
            "warn": T.WARN,
            "danger": T.DANGER,
        }.get(variant, T.PRISM_600)
        frame = ctk.CTkFrame(self, fg_color=T.PAPER_CARD, border_color=color, border_width=2, corner_radius=10)
        frame.pack(padx=6, pady=6)
        ctk.CTkLabel(frame, text=title, font=("SF Pro Text", 13, "bold"), text_color=T.INK).pack(
            padx=14, pady=(10, 2), anchor="w"
        )
        if description:
            ctk.CTkLabel(frame, text=description, font=T.FONT_SMALL, text_color=T.INK_MUTE, wraplength=300, justify="left").pack(
                padx=14, pady=(0, 10), anchor="w"
            )
        # Position bottom-right of the master window
        self.update_idletasks()
        try:
            mx = master.winfo_rootx() + master.winfo_width() - self.winfo_width() - 20
            my = master.winfo_rooty() + master.winfo_height() - self.winfo_height() - 20
            self.geometry(f"+{mx}+{my}")
        except Exception:
            pass
        self.after(3500, self.destroy)
