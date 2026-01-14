from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple, List

from kivy.graphics import Color, Rectangle, RoundedRectangle, InstructionGroup
from kivy.metrics import dp, sp
from kivy.resources import resource_find
from kivy.uix.image import Image

RGBA = Tuple[float, float, float, float]


@dataclass
class Theme:
    bg0: RGBA = (0.03, 0.04, 0.08, 1)
    bg1: RGBA = (0.06, 0.07, 0.12, 1)

    panel: RGBA = (0.06, 0.07, 0.12, 0.80)
    panel2: RGBA = (0.03, 0.04, 0.07, 0.65)

    accent: RGBA = (0.35, 0.80, 1.0, 1)
    danger: RGBA = (1.00, 0.35, 0.40, 1)
    ok: RGBA = (0.32, 0.93, 0.58, 1)

    text: RGBA = (0.95, 0.96, 1.0, 1)
    text_dim: RGBA = (0.80, 0.82, 0.92, 1)

    radius: float = dp(14)
    btn_h: float = dp(54)
    btn_h_small: float = dp(44)
    hud_h: float = dp(56)


def _replace_before_group(widget, group_attr: str, group: InstructionGroup) -> None:
    """Заменяет только нашу группу в canvas.before, не ломая внутренние инструкции Kivy."""
    old = getattr(widget, group_attr, None)
    if old is not None:
        try:
            widget.canvas.before.remove(old)
        except Exception:
            pass
    widget.canvas.before.add(group)
    setattr(widget, group_attr, group)


def add_rounded_bg(widget, rgba: RGBA, radius: float):
    g = InstructionGroup()
    c = Color(*rgba)
    rr = RoundedRectangle(pos=widget.pos, size=widget.size, radius=[radius])
    g.add(c)
    g.add(rr)

    _replace_before_group(widget, "_ui_bg_group", g)

    def _upd(*_):
        rr.pos = widget.pos
        rr.size = widget.size

    widget.bind(pos=_upd, size=_upd)
    _upd()
    return rr


def style_panel(widget, theme: Theme, strong: bool = False):
    add_rounded_bg(widget, theme.panel if strong else theme.panel2, theme.radius)
    return widget


def style_button(btn, theme: Theme, kind: str = "primary", small: bool = False):
    btn.background_normal = ""
    btn.background_down = ""
    btn.background_color = (0, 0, 0, 0)
    btn.color = theme.text
    btn.bold = True
    btn.font_size = sp(18 if not small else 16)

    btn.size_hint_y = None
    btn.height = theme.btn_h_small if small else theme.btn_h

    if kind == "primary":
        bg = (theme.accent[0] * 0.22, theme.accent[1] * 0.22, theme.accent[2] * 0.22, 0.95)
    elif kind == "danger":
        bg = (theme.danger[0] * 0.22, theme.danger[1] * 0.22, theme.danger[2] * 0.22, 0.95)
    elif kind == "ghost":
        bg = theme.panel2
    else:
        bg = theme.panel

    add_rounded_bg(btn, bg, theme.radius)
    return btn


def apply_screen_bg(screen, theme: Theme, *, vignette: bool = True, gradient_steps: int = 8):
    """Красивый фон для Screen/Widget (без canvas.before.clear())."""
    g = InstructionGroup()

    g.add(Color(*theme.bg0))
    base = Rectangle(pos=screen.pos, size=screen.size)
    g.add(base)

    steps = max(2, int(gradient_steps))
    grad_rects: List[Rectangle] = []
    for i in range(steps):
        t = i / (steps - 1)
        r = theme.bg0[0] * (1 - t) + theme.bg1[0] * t
        gg = theme.bg0[1] * (1 - t) + theme.bg1[1] * t
        b = theme.bg0[2] * (1 - t) + theme.bg1[2] * t
        k = 0.75 + 0.35 * (1.0 - abs(2 * t - 1.0))

        g.add(Color(r * k, gg * k, b * k, 0.55))
        rr = Rectangle(pos=(screen.x, screen.y + screen.height * t),
                       size=(screen.width, screen.height / steps))
        grad_rects.append(rr)
        g.add(rr)

    if vignette:
        g.add(Color(0, 0, 0, 0.28))
        v_left = Rectangle()
        v_right = Rectangle()
        v_bottom = Rectangle()
        v_top = Rectangle()
        g.add(v_left); g.add(v_right); g.add(v_bottom); g.add(v_top)
    else:
        v_left = v_right = v_bottom = v_top = None

    _replace_before_group(screen, "_ui_screen_bg_group", g)

    def _update(*_):
        base.pos = screen.pos
        base.size = screen.size

        for i, rr in enumerate(grad_rects):
            t = i / (steps - 1)
            rr.pos = (screen.x, screen.y + screen.height * t)
            rr.size = (screen.width, screen.height / steps)

        if vignette and v_left is not None:
            v_left.pos = (screen.x, screen.y)
            v_left.size = (screen.width * 0.06, screen.height)

            v_right.pos = (screen.right - screen.width * 0.06, screen.y)
            v_right.size = (screen.width * 0.06, screen.height)

            v_bottom.pos = (screen.x, screen.y)
            v_bottom.size = (screen.width, screen.height * 0.08)

            v_top.pos = (screen.x, screen.top - screen.height * 0.08)
            v_top.size = (screen.width, screen.height * 0.08)

    screen.bind(pos=_update, size=_update)
    _update()
    return screen
from kivy.graphics import Rectangle, Color
from kivy.resources import resource_find
from kivy.core.image import Image as CoreImage

def attach_icon_fancy(btn, icon_path: str, icon_bg: str = None, size_ratio: float = 0.85,
                     glow_scale: float = 1.0, glow_alpha: float = 0.85):
    icon_real = resource_find(icon_path) or icon_path
    bg_real = (resource_find(icon_bg) or icon_bg) if icon_bg else None

    icon_tex = None
    bg_tex = None

    try:
        icon_tex = CoreImage(icon_real).texture
    except Exception as e:
        print(f"[attach_icon_fancy] icon load failed: {icon_path} -> {icon_real} ({e})")

    if bg_real:
        try:
            bg_tex = CoreImage(bg_real).texture
        except Exception as e:
            print(f"[attach_icon_fancy] bg load failed: {icon_bg} -> {bg_real} ({e})")

    # Рисуем поверх кнопки
    with btn.canvas.after:
        # glow (может быть полупрозрачным)
        Color(1, 1, 1, float(glow_alpha))
        bg_rect = Rectangle(texture=bg_tex, pos=btn.pos, size=btn.size) if bg_tex else None

        # icon (полностью)
        Color(1, 1, 1, 1)
        ic_rect = Rectangle(texture=icon_tex, pos=btn.pos, size=btn.size) if icon_tex else None

    def update(*_):
        x, y = btn.pos
        w, h = btn.size
        cx, cy = x + w / 2.0, y + h / 2.0

        # glow чуть больше кнопки
        # glow аккуратно: чуть больше кнопки, но не огромный
        if bg_rect is not None:
            base = min(w, h)
            g = base * float(glow_scale)  # glow_scale ~ 1.10
            g = min(g, base * 1.20)  # жёсткий лимит (не разрастётся)
            bg_rect.size = (g, g)
            bg_rect.pos = (cx - g / 2.0, cy - g / 2.0)

        # icon меньше кнопки
        if ic_rect is not None:
            s = min(w, h) * float(size_ratio)
            ic_rect.size = (s, s)
            ic_rect.pos = (cx - s / 2.0, cy - s / 2.0)

    btn.bind(pos=update, size=update)
    update()