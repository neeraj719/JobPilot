"""JobPilot theme tokens: OKLCH source of truth -> HSL triplets for index.css, plus a
WCAG 2.x / APCA contrast matrix for every text/background pair the UI uses.

usage: python tokens.py css      -> prints the :root and .dark blocks
       python tokens.py matrix   -> prints the markdown matrix (exit 1 on any failure)
"""
import math
import sys

# --------------------------------------------------------------------------- colour maths


def oklch_to_srgb(L, C, h):
    a = C * math.cos(math.radians(h))
    b = C * math.sin(math.radians(h))
    l_ = L + 0.3963377774 * a + 0.2158037573 * b
    m_ = L - 0.1055613458 * a - 0.0638541728 * b
    s_ = L - 0.0894841775 * a - 1.2914855480 * b
    l, m, s = l_ ** 3, m_ ** 3, s_ ** 3
    r = 4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s
    g = -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s
    bb = -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s

    def enc(x):
        return 12.92 * x if x <= 0.0031308 else 1.055 * (x ** (1 / 2.4)) - 0.055

    return [enc(v) for v in (r, g, bb)]


def in_gamut(rgb):
    return all(-0.0005 <= v <= 1.0005 for v in rgb)


def oklch(L, C, h):
    """sRGB (0..1) for an OKLCH colour, reducing chroma until it is in gamut."""
    c = C
    while c > 0:
        rgb = oklch_to_srgb(L, c, h)
        if in_gamut(rgb):
            return [min(1, max(0, v)) for v in rgb]
        c -= 0.002
    return [min(1, max(0, v)) for v in oklch_to_srgb(L, 0, h)]


def rgb_to_hsl(rgb):
    r, g, b = rgb
    mx, mn = max(rgb), min(rgb)
    l = (mx + mn) / 2
    if mx == mn:
        return 0.0, 0.0, l * 100
    d = mx - mn
    s = d / (2 - mx - mn) if l > 0.5 else d / (mx + mn)
    if mx == r:
        h = (g - b) / d + (6 if g < b else 0)
    elif mx == g:
        h = (b - r) / d + 2
    else:
        h = (r - g) / d + 4
    return h * 60, s * 100, l * 100


def hsl_to_rgb(h, s, l):
    s, l = s / 100, l / 100
    c = (1 - abs(2 * l - 1)) * s
    x = c * (1 - abs((h / 60) % 2 - 1))
    m = l - c / 2
    seg = int(h // 60) % 6
    r, g, b = [(c, x, 0), (x, c, 0), (0, c, x), (0, x, c), (x, 0, c), (c, 0, x)][seg]
    return [r + m, g + m, b + m]


def hsl_triplet(rgb):
    h, s, l = rgb_to_hsl(rgb)
    return f"{round(h)} {round(s, 1):g}% {round(l, 1):g}%"


def rendered(rgb):
    """What the browser actually paints: the rounded HSL triplet back to sRGB."""
    h, s, l = rgb_to_hsl(rgb)
    return hsl_to_rgb(round(h), round(s, 1), round(l, 1))


def hex_of(rgb):
    return "#" + "".join(f"{round(v * 255):02x}" for v in rgb)


def from_hex(hx):
    hx = hx.lstrip("#")
    return [int(hx[i:i + 2], 16) / 255 for i in (0, 2, 4)]


def lin(v):
    return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4


def luminance(rgb):
    r, g, b = (lin(v) for v in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def wcag(fg, bg):
    a, b = luminance(fg), luminance(bg)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


def apca(txt, bg):
    def y(rgb):
        r, g, b = (v ** 2.4 for v in rgb)
        return 0.2126729 * r + 0.7151522 * g + 0.0721750 * b

    yt, yb = y(txt), y(bg)
    thr, clamp = 0.022, 1.414
    yt = yt + (thr - yt) ** clamp if yt < thr else yt
    yb = yb + (thr - yb) ** clamp if yb < thr else yb
    if abs(yb - yt) < 0.0005:
        return 0.0
    if yb > yt:
        sapc = (yb ** 0.56 - yt ** 0.57) * 1.14
        lc = 0 if sapc < 0.1 else sapc - 0.027
    else:
        sapc = (yb ** 0.65 - yt ** 0.62) * 1.14
        lc = 0 if sapc > -0.1 else sapc + 0.027
    return lc * 100


def over(fg, alpha, bg):
    return [f * alpha + b * (1 - alpha) for f, b in zip(fg, bg)]


# --------------------------------------------------------------------------- palette

NEUTRAL_H = 265  # cool slate, a hair toward the indigo brand
BRAND_H = 272

# Brand (indigo) scale, mode-independent. Lightness steps follow Tailwind-like 50..950.
BRAND = {
    50: (0.970, 0.016), 100: (0.940, 0.032), 200: (0.885, 0.062), 300: (0.805, 0.105),
    400: (0.705, 0.155), 500: (0.610, 0.195), 600: (0.505, 0.205), 700: (0.460, 0.190),
    800: (0.395, 0.155), 900: (0.335, 0.115), 950: (0.245, 0.080),
}


def brand(step):
    L, C = BRAND[step]
    return oklch(L, C, BRAND_H)


def n(L, C=0.008):
    return oklch(L, C, NEUTRAL_H)


def hue(L, C, h):
    return oklch(L, C, h)


GREEN, AMBER, RED, BLUE, VIOLET = 152, 62, 25, 238, 298
VIOLET_G, FUCHSIA = 295, 335  # brand gradient hues (theme-modern)

LIGHT = {
    "background": n(0.977, 0.004),
    "foreground": n(0.205, 0.022),
    "card": n(1.0, 0),
    "card-foreground": n(0.205, 0.022),
    "popover": n(1.0, 0),
    "popover-foreground": n(0.205, 0.022),
    "primary": brand(600),
    "primary-foreground": n(1.0, 0),
    "secondary": n(0.958, 0.006),
    "secondary-foreground": n(0.255, 0.022),
    "muted": n(0.962, 0.005),
    "muted-foreground": n(0.505, 0.020),
    "accent": n(0.953, 0.008),
    "accent-foreground": n(0.205, 0.022),
    "destructive": hue(0.510, 0.190, RED),
    "destructive-foreground": n(1.0, 0),
    "success": hue(0.480, 0.110, GREEN),
    "success-foreground": n(1.0, 0),
    "warning": hue(0.505, 0.115, AMBER),
    "warning-foreground": n(1.0, 0),
    "info": hue(0.490, 0.120, BLUE),
    "info-foreground": n(1.0, 0),
    "destructive-soft": hue(0.968, 0.016, RED),
    "destructive-soft-foreground": hue(0.445, 0.165, RED),
    "success-soft": hue(0.968, 0.022, GREEN),
    "success-soft-foreground": hue(0.415, 0.095, GREEN),
    "warning-soft": hue(0.972, 0.030, 85),
    "warning-soft-foreground": hue(0.445, 0.105, 55),
    "info-soft": hue(0.968, 0.016, BLUE),
    "info-soft-foreground": hue(0.425, 0.115, BLUE),
    # AI-made content (suggestions, tailored bullets, AI version badges). Not a status.
    "ai": hue(0.500, 0.200, VIOLET),
    "ai-foreground": n(1.0, 0),
    "ai-soft": hue(0.966, 0.020, VIOLET),
    "ai-soft-foreground": hue(0.445, 0.190, VIOLET),
    "border": n(0.920, 0.006),
    "input": n(0.640, 0.014),
    "ring": brand(500),
    "surface-1": n(1.0, 0),
    "surface-2": n(0.972, 0.004),
    "surface-3": n(0.945, 0.007),
    # Navigation rail (theme-identity): deep indigo-navy in BOTH themes, the Linear / Vercel
    # dashboard pattern. Light = brand-950-ish, slightly desaturated.
    "sidebar": hue(0.240, 0.060, BRAND_H),
    "sidebar-foreground": hue(0.900, 0.020, BRAND_H),  # inactive item labels
    "sidebar-primary": brand(400),  # active bar + active icon (bright)
    "sidebar-primary-foreground": brand(950),
    "sidebar-accent": hue(0.345, 0.085, BRAND_H),  # active pill (hover = /60)
    "sidebar-accent-foreground": hue(0.985, 0.006, BRAND_H),  # active label, names
    "sidebar-border": hue(0.325, 0.055, BRAND_H),
    "sidebar-ring": brand(300),
    "sidebar-muted": hue(0.760, 0.040, BRAND_H),  # icons, captions ("Module")
    "sidebar-section": brand(300),  # section titles (small caps)
    "sidebar-raised": hue(0.290, 0.065, BRAND_H),  # module switcher surface, rail tooltips
    "sidebar-glow": hue(0.800, 0.110, 345),  # v2: far end of the active-bar gradient
    "overlay": n(0.205, 0.022),
    # ---- v2 (theme-modern) ------------------------------------------------------------
    # Brand gradient indigo -> violet -> fuchsia. The three stops are TEXT-SAFE: white copy
    # passes 4.5:1 on each stop and on both midpoints, so `bg-gradient-brand` can carry a
    # primary button label. Identical in both themes (the dark block repeats them).
    "gradient-from": brand(600),
    "gradient-via": hue(0.500, 0.220, VIOLET_G),
    "gradient-to": hue(0.520, 0.220, FUCHSIA),
    "gradient-foreground": n(1.0, 0),
    # Gradient TEXT (display headlines, wordmark) needs its own stops per theme.
    "gradient-text-from": brand(600),
    "gradient-text-via": hue(0.500, 0.220, VIOLET_G),
    "gradient-text-to": hue(0.520, 0.220, FUCHSIA),
    # Soft gradient: tinted panels (AI content, hero tiles). Body text sits on it.
    "gradient-soft-from": hue(0.962, 0.024, BRAND_H),
    "gradient-soft-to": hue(0.962, 0.026, FUCHSIA),
    # Glow colour (used at low alpha in shadows / blurred blobs) and glass surfaces.
    "glow-brand": brand(500),
    "glass": n(1.0, 0),
    "glass-border": n(1.0, 0),
    # Skeleton placeholders (loading): base fill + the shimmer highlight that sweeps across.
    "skeleton": n(0.938, 0.009),
    "skeleton-highlight": n(0.985, 0.004),
}

DARK = {
    "background": n(0.192, 0.013),
    "foreground": n(0.955, 0.005),
    "card": n(0.224, 0.014),
    "card-foreground": n(0.955, 0.005),
    "popover": n(0.248, 0.015),
    "popover-foreground": n(0.955, 0.005),
    "primary": hue(0.750, 0.130, BRAND_H),
    "primary-foreground": brand(950),
    "secondary": n(0.288, 0.015),
    "secondary-foreground": n(0.955, 0.005),
    "muted": n(0.270, 0.014),
    "muted-foreground": n(0.790, 0.016),
    "accent": n(0.295, 0.017),
    "accent-foreground": n(0.955, 0.005),
    "destructive": hue(0.745, 0.150, RED),
    "destructive-foreground": hue(0.200, 0.060, RED),
    "success": hue(0.780, 0.145, GREEN),
    "success-foreground": hue(0.200, 0.045, GREEN),
    "warning": hue(0.810, 0.140, 78),
    "warning-foreground": hue(0.230, 0.050, 60),
    "info": hue(0.780, 0.110, BLUE),
    "info-foreground": hue(0.210, 0.050, BLUE),
    "destructive-soft": hue(0.280, 0.050, RED),
    "destructive-soft-foreground": hue(0.850, 0.080, RED),
    "success-soft": hue(0.280, 0.040, GREEN),
    "success-soft-foreground": hue(0.860, 0.100, GREEN),
    "warning-soft": hue(0.290, 0.040, 70),
    "warning-soft-foreground": hue(0.880, 0.105, 82),
    "info-soft": hue(0.280, 0.040, BLUE),
    "info-soft-foreground": hue(0.860, 0.075, BLUE),
    "ai": hue(0.790, 0.120, VIOLET),
    "ai-foreground": hue(0.210, 0.070, VIOLET),
    "ai-soft": hue(0.290, 0.055, VIOLET),
    "ai-soft-foreground": hue(0.870, 0.075, VIOLET),
    "border": n(0.318, 0.015),
    "input": n(0.565, 0.018),
    "ring": brand(400),
    "surface-1": n(0.224, 0.014),
    "surface-2": n(0.208, 0.013),
    "surface-3": n(0.288, 0.016),
    # One step darker than the canvas, faint indigo tint, same accent logic as light.
    "sidebar": hue(0.165, 0.020, BRAND_H),
    "sidebar-foreground": hue(0.860, 0.015, BRAND_H),
    "sidebar-primary": brand(400),
    "sidebar-primary-foreground": brand(950),
    "sidebar-accent": hue(0.300, 0.075, BRAND_H),
    "sidebar-accent-foreground": hue(0.975, 0.008, BRAND_H),
    "sidebar-border": hue(0.255, 0.028, BRAND_H),
    "sidebar-ring": brand(400),
    "sidebar-muted": hue(0.720, 0.030, BRAND_H),
    "sidebar-section": brand(300),
    "sidebar-raised": hue(0.215, 0.030, BRAND_H),
    "sidebar-glow": hue(0.800, 0.110, 345),
    "overlay": n(0.08, 0.01),
    # ---- v2 (theme-modern) ------------------------------------------------------------
    "gradient-from": brand(600),
    "gradient-via": hue(0.500, 0.220, VIOLET_G),
    "gradient-to": hue(0.520, 0.220, FUCHSIA),
    "gradient-foreground": n(1.0, 0),
    "gradient-text-from": brand(300),
    "gradient-text-via": hue(0.780, 0.120, 300),
    "gradient-text-to": hue(0.800, 0.110, 345),
    "gradient-soft-from": hue(0.262, 0.050, BRAND_H),
    "gradient-soft-to": hue(0.258, 0.050, 320),
    "glow-brand": hue(0.640, 0.200, 290),
    "glass": n(0.224, 0.014),
    "glass-border": n(0.420, 0.020),
    "skeleton": n(0.275, 0.015),
    "skeleton-highlight": n(0.335, 0.017),
}

# Categorical chart slots (dataviz reference palette; validated with its validator).
CHART_LIGHT = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300"]
CHART_DARK = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300"]

# The sign-in hero: identical in both themes (white copy sits on it).
HERO = {"hero-from": hue(0.360, 0.150, BRAND_H), "hero-to": hue(0.400, 0.090, 230)}
# theme-identity: the brand gradient family (sign-in hero + launcher band). The two stops are
# the only gradient colours in the app; hero-to moved from teal (230) to a deep indigo-navy so
# the band reads as "indigo", not "teal". Copy on it uses hero-foreground / hero-muted.
HERO = {
    "hero-from": hue(0.380, 0.155, BRAND_H),
    "hero-to": hue(0.255, 0.085, 262),
    "hero-foreground": hue(0.985, 0.006, BRAND_H),
    "hero-muted": hue(0.870, 0.040, BRAND_H),
}

# Raw brand steps, so brand-on-brand pairs (the logo mark) can be gated too.
BRANDS = {f"brand-{s}": brand(s) for s in BRAND}

# --------------------------------------------------------------------------- pairs

T, L_, U = "text", "large", "ui"  # 4.5 / 3.0 / 3.0


def pairs(t):
    p = []
    surf = ["background", "card", "popover", "muted", "accent", "secondary", "surface-2", "surface-3"]
    for s in surf:
        p.append(("foreground", s, T))
    for s in ["background", "card", "popover", "muted", "accent", "surface-2", "surface-3", ("muted", 0.6, "card"),
              ("muted", 0.4, "background")]:
        p.append(("muted-foreground", s, T))
    for a, b in [("card-foreground", "card"), ("popover-foreground", "popover"), ("primary-foreground", "primary"),
                 ("secondary-foreground", "secondary"), ("accent-foreground", "accent"),
                 ("destructive-foreground", "destructive"), ("success-foreground", "success"),
                 ("warning-foreground", "warning"), ("info-foreground", "info"), ("ai-foreground", "ai"),
                 ("sidebar-foreground", "sidebar"), ("sidebar-accent-foreground", "sidebar-accent"),
                 ("sidebar-primary-foreground", "sidebar-primary")]:
        p.append((a, b, T))
    for k in ["primary", "destructive", "success", "warning", "info", "ai"]:
        p.append((f"{k}", "background", T))
        p.append((f"{k}", "card", T))
        p.append((f"{k}", "muted", T))
        p.append((f"{k}", (k, 0.10, "card"), T))
        p.append((f"{k}", (k, 0.15, "background"), T))
        if k != "primary":
            p.append((f"{k}-soft-foreground", f"{k}-soft", T))
    # Non-text: control boundaries, focus ring, solid buttons against the page.
    for s in ["background", "card", "popover"]:
        p.append(("input", s, U))
        p.append(("ring", s, U))
    p.append(("primary", "background", U))
    p.append(("sidebar-ring", "sidebar", U))
    # theme-identity: the dark indigo rail. Every text tone on every rail surface it can sit on
    # (rail, raised switcher / tooltip, active pill, hover = accent/60 over the rail).
    rail = ["sidebar", "sidebar-raised", "sidebar-accent", ("sidebar-accent", 0.6, "sidebar")]
    for s in rail:
        p.append(("sidebar-foreground", s, T))
        p.append(("sidebar-accent-foreground", s, T))
        p.append(("sidebar-muted", s, T))
    p.append(("sidebar-section", "sidebar", T))
    p.append(("sidebar-primary", "sidebar", U))  # active bar
    p.append(("sidebar-primary", "sidebar-accent", U))  # active icon on the pill
    p.append(("sidebar-glow", "sidebar", U))  # v2 gradient active bar, far end
    p.append(("sidebar-glow", "sidebar-accent", U))
    p.append(("sidebar-ring", "sidebar-raised", U))
    p.append(("sidebar-ring", "sidebar-accent", U))
    # Module tile on the rail (solid accent tile: icon on solid, tile against the rail).
    for k in ["primary", "info", "warning", "success"]:
        p.append((f"{k}-foreground", k, T))
    # Logo mark: light = brand-600 tile + brand-50 glyph; dark = brand-400 tile + brand-950 glyph.
    if t is LIGHT:
        p.append(("brand-50", "brand-600", T))
    else:
        p.append(("brand-950", "brand-400", T))
    # Brand gradient (sign-in hero, launcher band): both stops and their sRGB midpoint.
    for s in ["hero-from", "hero-to", ("hero-from", 0.5, "hero-to")]:
        p.append(("hero-foreground", s, T))
        p.append(("hero-muted", s, T))
    # ---- v2 (theme-modern) ------------------------------------------------------------
    # White copy on the brand gradient: each stop and both sRGB midpoints.
    for st in ["gradient-from", "gradient-via", "gradient-to", ("gradient-from", 0.5, "gradient-via"),
               ("gradient-via", 0.5, "gradient-to")]:
        p.append(("gradient-foreground", st, T))
    # Gradient text on the page surfaces (each stop is a possible glyph colour).
    for k in ["gradient-text-from", "gradient-text-via", "gradient-text-to"]:
        for st in ["background", "card"]:
            p.append((k, st, T))
    # Body copy on the soft gradient (both ends).
    for st in ["gradient-soft-from", "gradient-soft-to"]:
        p.append(("foreground", st, T))
        p.append(("muted-foreground", st, T))
        p.append(("primary", st, T))
    # Glass (topbar, switcher, floating panels) measured on its real backdrops: the canvas and a
    # card scrolled under it, at the 90 % opacity the `.glass` class paints.
    for back in ["background", "card"]:
        p.append(("foreground", ("glass", 0.9, back), T))
        p.append(("muted-foreground", ("glass", 0.9, back), T))
        p.append(("ring", ("glass", 0.9, back), U))
    # ---- landing page (theme-identity amendment 2) ----------------------------------------
    # Hero pill / mini cards: hero copy on a 10 % hero-foreground wash over either stop.
    for st in ["hero-from", "hero-to"]:
        p.append(("hero-foreground", ("hero-foreground", 0.10, st), T))
        p.append(("hero-muted", ("hero-foreground", 0.10, st), T))
        # Sticky glass navbar and the floating hero notes when they sit over the hero.
        p.append(("foreground", ("glass", 0.9, st), T))
        p.append(("muted-foreground", ("glass", 0.9, st), T))
        p.append(("ring", ("glass", 0.9, st), U))
    # Rows inside the bento tiles (background/60 over card), the How-it-works band and footer
    # (card/50 over background), FAQ hover (accent/60 over card).
    p.append(("foreground", ("background", 0.6, "card"), T))
    p.append(("muted-foreground", ("background", 0.6, "card"), T))
    p.append(("muted-foreground", ("card", 0.5, "background"), T))
    p.append(("gradient-text-from", ("card", 0.5, "background"), T))
    p.append(("gradient-text-to", ("card", 0.5, "background"), T))
    p.append(("foreground", ("accent", 0.6, "card"), T))
    # Gradient headline on the soft gradient panel (Safety section) and on popover (modal).
    for st in ["gradient-soft-from", "gradient-soft-to", "popover"]:
        for k in ["gradient-text-from", "gradient-text-via", "gradient-text-to"]:
            p.append((k, st, T))
    # ---- landing-perf: light hero mesh, featured tile, pills -------------------------------
    # Light hero / final CTA (`heroShared.tsx` LIGHT_MESH): the canvas under radial brand tints.
    # The tints peak (glow-brand 24 %, gradient-via 14 %, stacked where the ellipses overlap)
    # behind the 3D box and in the empty top corners, where no copy sits — reported as info.
    # Under the copy column the strongest tint measured on rendered pixels (landing-perf
    # contrast sweep, 1440 + 390, every hero / CTA text element) is equivalent to glow-brand at
    # 10.8 %; the gate uses 14 % (margin) for every text tone that can sit there.
    if t is LIGHT:
        peaks = [("glow-brand", 0.24, "background"), ("gradient-via", 0.14, ("glow-brand", 0.24, "background"))]
        copy = [("glow-brand", 0.14, "background"), ("gradient-via", 0.10, "background"), ("gradient-to", 0.10, "background")]
        for st in copy:
            p.append(("foreground", st, T))
            p.append(("muted-foreground", st, T))
            p.append(("primary", st, T))
            for k in ["gradient-text-from", "gradient-text-via", "gradient-text-to"]:
                p.append((k, st, T))
        for st in peaks:
            p.append(("muted-foreground", st, "info"))
        # Hero pill (card/80 over the strongest peak — it may drift over one at narrow widths).
        p.append(("foreground", ("card", 0.8, peaks[1]), T))
        # Featured bento tile (light): soft gradient + sub-cards / chips at card/80 on either end.
        for st in ["gradient-soft-from", "gradient-soft-to"]:
            p.append(("foreground", ("card", 0.8, st), T))
            p.append(("muted-foreground", ("card", 0.8, st), T))
            p.append(("primary", ("card", 0.8, st), U))
        # Landing skeleton text bars on the mesh (decorative, reported).
        p.append(("skeleton", copy[0], "info"))
    else:
        # Featured bento tile, hero pill and chips (dark): hero copy on hero-foreground/10 over
        # the band with the glow-brand bloom. The bloom peaks at 32 % in the top-right corner
        # (behind the illustration, no copy) — info. Measured under copy: ≈ 17 % for text on the
        # band (gate 20 %), ≈ 0 % under the sub-cards / chips at the bottom of the tile (gate 10 %).
        bloom = ("glow-brand", 0.20, "hero-from")
        chip_bloom = ("glow-brand", 0.10, "hero-from")
        p.append(("hero-foreground", ("hero-foreground", 0.10, bloom), T))
        p.append(("hero-muted", ("hero-foreground", 0.10, chip_bloom), T))
        p.append(("hero-muted", bloom, T))
        p.append(("hero-muted", ("hero-foreground", 0.10, ("glow-brand", 0.32, "hero-from")), "info"))
        # Landing skeleton text bars on the band (decorative, reported).
        p.append((("hero-foreground", 0.12, "hero-from"), "hero-from", "info"))
    # Skeletons are decorative placeholders (WCAG exempt) but must read as shapes on both
    # surfaces they appear on - reported, not gated.
    for st in ["background", "card"]:
        p.append(("skeleton", st, "info"))
    p.append(("skeleton-highlight", "skeleton", "info"))
    # Hairline between rail and canvas / inside the rail (decorative).
    p.append(("sidebar-border", "sidebar", "info"))
    # Hairline borders are decorative separators (WCAG exempt) - reported, not gated.
    p.append(("border", "card", "info"))
    p.append(("border", "background", "info"))
    return p


def resolve(theme, spec):
    theme = {**BRANDS, **HERO, **theme}
    if isinstance(spec, tuple):
        # (colour, alpha, backdrop) — the backdrop may itself be a composite (stacked layers).
        fg, alpha, bg = spec
        back, bname = resolve(theme, bg)
        return over(rendered(theme[fg]), alpha, back), f"{fg}/{int(alpha * 100)} on ({bname})" if isinstance(bg, tuple) else f"{fg}/{int(alpha * 100)} on {bname}"
    return rendered(theme[spec]), spec


def matrix():
    failures = 0
    out = []
    for name, theme in (("Light", LIGHT), ("Dark", DARK)):
        out.append(f"\n#### {name} theme\n")
        out.append("| Text / element | Background | WCAG ratio | Needed | APCA Lc | Result |")
        out.append("|---|---|---:|---:|---:|---|")
        worst = (99, None)
        worst_rail_text = worst_rail_ui = (99, None)
        for fg, bg, kind in pairs(theme):
            f, _ = resolve(theme, fg)
            b, bname = resolve(theme, bg)
            r = wcag(f, b)
            lc = abs(apca(f, b))
            need = {T: 4.5, L_: 3.0, U: 3.0, "info": 0}[kind]
            ok = r >= need
            if kind != "info" and r < worst[0]:
                worst = (r, f"{fg} on {bname}")
            on_rail = "sidebar" in str(fg) + bname
            if kind == T and on_rail and r < worst_rail_text[0]:
                worst_rail_text = (r, f"{fg} on {bname}")
            if kind == U and on_rail and r < worst_rail_ui[0]:
                worst_rail_ui = (r, f"{fg} on {bname}")
            if not ok:
                failures += 1
            res = "pass" if ok else "**FAIL**"
            if kind == "info":
                res = "decorative (exempt)"
            elif kind == U:
                res = "pass (UI 3:1)" if ok else "**FAIL**"
            out.append(f"| `{fg}` | `{bname}` | {r:.2f} | {need or '-'} | {lc:.0f} | {res} |")
        out.append(f"\nWorst gated pair ({name.lower()}): {worst[1]} at {worst[0]:.2f}:1\n")
        out.append(f"Worst sidebar text pair ({name.lower()}): {worst_rail_text[1]} at {worst_rail_text[0]:.2f}:1 (needs 4.5)\n")
        out.append(f"Worst sidebar UI pair ({name.lower()}): {worst_rail_ui[1]} at {worst_rail_ui[0]:.2f}:1 (needs 3.0)\n")
    # Chart slots vs card (informational: relief rule - legends + direct labels)
    out.append("\n#### Chart slots against the card surface (relief rule: legend + labels always shown)\n")
    out.append("| Slot | Light | ratio on card | Dark | ratio on card |")
    out.append("|---|---|---:|---|---:|")
    lc, dc = rendered(LIGHT["card"]), rendered(DARK["card"])
    for i, (lh, dh) in enumerate(zip(CHART_LIGHT, CHART_DARK), 1):
        out.append(f"| chart-{i} | `{lh}` | {wcag(from_hex(lh), lc):.2f} | `{dh}` | {wcag(from_hex(dh), dc):.2f} |")
    for k in ("hero-from", "hero-to"):
        out.append(f"\nHero `{k}` with white copy: {wcag([1, 1, 1], rendered(HERO[k])):.2f}:1")
    return "\n".join(out), failures


def css_block(theme, chart):
    lines = []
    order = list(theme.keys())
    for k in order:
        lines.append(f"    --{k}: {hsl_triplet(theme[k])}; /* {hex_of(rendered(theme[k]))} */")
    for i, hx in enumerate(chart, 1):
        lines.append(f"    --chart-{i}: {hsl_triplet(from_hex(hx))}; /* {hx} */")
    return "\n".join(lines)


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "matrix"
    if mode == "css":
        print(":root {")
        for s in BRAND:
            print(f"    --brand-{s}: {hsl_triplet(brand(s))}; /* {hex_of(rendered(brand(s)))} */")
        for k, v in HERO.items():
            print(f"    --{k}: {hsl_triplet(v)}; /* {hex_of(rendered(v))} */")
        print(css_block(LIGHT, CHART_LIGHT))
        print("}\n.dark {")
        print(css_block(DARK, CHART_DARK))
        print("}")
        return 0
    text, failures = matrix()
    print(text)
    print(f"\nfailures: {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
