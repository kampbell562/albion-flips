"""Albion market flip widget: a small window that refreshes itself.

Run:  pythonw flip-widget.py               (no console)
      python  flip-widget.py --selftest    (one watchlist scan, then exit)
"""
import argparse, ctypes, json, sys, threading, time, tkinter as tk
from datetime import datetime
from tkinter import ttk

import albion_market as am

# ---- theme --------------------------------------------------------------
BG, PANEL, ROW, ROW2 = "#15161a", "#1f2127", "#1a1c21", "#202228"
FG, DIM, MUTED, GOLD = "#e8e6e1", "#8b8d93", "#6c6e74", "#e9b949"
WARN, WARN_BG = "#f0c060", "#3a2f17"
GREEN, RED, SEL, LINE ="#5cc98a", "#d9675e", "#343a46", "#2a2d34"
FONT = ("Segoe UI", 10)
FONT_B = ("Segoe UI", 10, "bold")
FONT_S = ("Segoe UI", 9)
FONT_T = ("Segoe UI Semibold", 14)

# key, label, width, anchor, shown by default
COLS = [("item", "Item", 220, "w", True), ("q", "Q", 30, "center", False),
        ("bid", "Bid now", 80, "e", False), ("ask", "Ask now", 80, "e", False),
        ("buy_at", "Buy @", 80, "e", True), ("sell_at", "Sell @", 80, "e", True),
        ("unit", "Profit/unit", 96, "e", True), ("margin", "Margin", 64, "e", True),
        ("avg", "7d avg", 80, "e", False), ("vol_day", "Sold/day", 72, "e", True),
        ("est_day", "Est. profit/day", 124, "e", True), ("capital", "Capital/day", 100, "e", False),
        ("age_h", "Age", 52, "e", True)]
SETTINGS = am.HERE / "settings.json"
WATCH = "Watchlist (watchlist.txt)"


def compact(v):
    a = abs(v)
    if a >= 1e6:
        return f"{v / 1e6:.2f}M"
    if a >= 1e4:
        return f"{v / 1e3:.0f}k"
    return f"{v:,.0f}"


def fmt(col, v):
    if col in ("bid", "ask", "buy_at", "sell_at", "avg"):
        return f"{v:,.0f}"
    if col == "unit":
        return f"{v:+,.0f}"
    if col in ("est_day", "capital", "vol_day"):
        return compact(v)
    if col == "margin":
        return "0%" if abs(v) < 0.005 else f"{v:+.0%}"
    if col == "age_h":
        return f"{int(v * 60)}m" if v < 1 else f"{v:.0f}h"
    return str(v)


def load_settings():
    try:
        return json.loads(SETTINGS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


class Widget(tk.Tk):
    def __init__(self, selftest=False):
        super().__init__()
        cfg = {} if selftest else load_settings()
        self.title("Albion Flips")
        self.minsize(780, 300)
        self.configure(bg=BG)
        self._icon()
        self.rows, self.sort_col, self.sort_desc = [], "est_day", True
        self._scanning, self._stop, self._again, self.next_at, self._base = False, False, False, 0, ""
        self.selftest = selftest
        self._style()

        # header: title + last update on the left, refresh on the right
        head = tk.Frame(self, bg=BG); head.pack(fill="x", padx=16, pady=(12, 8))
        if self._logo:
            tk.Label(head, image=self._logo, bg=BG).pack(side="left", padx=(0, 8))
        tk.Label(head, text="Albion Flips", font=FONT_T, fg=GOLD, bg=BG).pack(side="left")
        self.status = tk.StringVar(value="")
        tk.Label(head, textvariable=self.status, font=FONT, fg=DIM, bg=BG).pack(side="left", padx=(14, 0), pady=(3, 0))
        self.btn = ttk.Button(head, text="Refresh", command=self.refresh, style="Gold.TButton", cursor="hand2")
        self.btn.pack(side="right")

        # controls: what to scan on the left, view options on the right
        bar = tk.Frame(self, bg=PANEL, padx=12, pady=8); bar.pack(fill="x", padx=16)
        self.city = tk.StringVar(value=cfg.get("city", "Thetford"))
        self._field(bar, "City", ttk.Combobox(bar, textvariable=self.city, values=am.CITIES, width=12, state="readonly"))
        scopes = [WATCH] + list(am.SCOPES)
        self.scope = tk.StringVar(value=cfg.get("scope") if cfg.get("scope") in scopes else WATCH)
        self._field(bar, "Scope", ttk.Combobox(bar, textvariable=self.scope, values=scopes, width=24, state="readonly"))
        self.margin = tk.IntVar(value=cfg.get("margin", 10))
        self._field(bar, "Min margin %", ttk.Spinbox(bar, from_=5, to=50, textvariable=self.margin, width=4))
        self.every = tk.IntVar(value=cfg.get("every", 2))
        self._field(bar, "Refresh (min)", ttk.Spinbox(bar, from_=1, to=120, textvariable=self.every, width=4))

        self.top = tk.BooleanVar(value=cfg.get("on_top", False))
        self.all_cols = tk.BooleanVar(value=cfg.get("all_cols", False))
        self.premium = tk.BooleanVar(value=cfg.get("premium", True))
        for text, var, cmd in (("Keep on top", self.top, self._apply_top),
                               ("All columns", self.all_cols, self._apply_cols),
                               ("Premium", self.premium, self.refresh)):
            ttk.Checkbutton(head, text=text, variable=var, style="Head.TCheckbutton", command=cmd,
                            cursor="hand2").pack(side="right", padx=(0, 18))
        for var in (self.city, self.scope):
            var.trace_add("write", lambda *_: self.refresh())

        # warning strip (only shown when watchlist lines don't match an item)
        self.warnbar = tk.Frame(self, bg=WARN_BG, padx=12, pady=6)
        self.warn = tk.StringVar()
        tk.Label(self.warnbar, textvariable=self.warn, font=FONT_S, fg=WARN, bg=WARN_BG, anchor="w",
                 justify="left").pack(fill="x")
        self.warnbar.bind("<Configure>", lambda e: e.widget.winfo_children()[0].configure(wraplength=e.width - 24))

        # table
        wrap = self.wrap = tk.Frame(self, bg=LINE, padx=1, pady=1)
        wrap.pack(fill="both", expand=True, padx=16, pady=(10, 0))
        self.tree = ttk.Treeview(wrap, columns=[c[0] for c in COLS], show="headings", style="Dark.Treeview")
        for key, label, w, anchor, _ in COLS:
            self.tree.heading(key, text=label, anchor=anchor, command=lambda k=key: self.sort(k))
            self.tree.column(key, width=w, anchor=anchor, stretch=(key == "item"), minwidth=40)
        ys = self.ys = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview, style="Dark.Vertical.TScrollbar")
        xs = self.xs = ttk.Scrollbar(wrap, orient="horizontal", command=self.tree.xview, style="Dark.Horizontal.TScrollbar")
        self.tree.configure(yscrollcommand=ys.set, xscrollcommand=self._xset)
        xs.pack(side="bottom", fill="x"); xs.pack_forget()      # only shown when columns don't fit
        self.tree.pack(side="left", fill="both", expand=True); ys.pack(side="left", fill="y")
        self.tree.tag_configure("pos", foreground=FG)
        self.tree.tag_configure("neg", foreground=MUTED)
        self.tree.tag_configure("odd", background=ROW2)
        self.tree.tag_configure("even", background=ROW)
        self.tree.bind("<Double-1>", self.copy_item)

        # footer: legend on the left, live status on the right
        # footer: last update on the right (packed first so it never gets cut), fee legend on the left
        foot = tk.Frame(self, bg=BG); foot.pack(side="bottom", fill="x", padx=16, pady=(6, 10), before=self.wrap)
        self.updated = tk.StringVar(value="")
        tk.Label(foot, textvariable=self.updated, anchor="e", font=FONT_S, fg=DIM, bg=BG).pack(side="right")
        self.legend = tk.StringVar()
        tk.Label(foot, textvariable=self.legend, anchor="w", font=FONT_S, fg=MUTED, bg=BG).pack(side="left")
        self._set_legend()

        self.protocol("WM_DELETE_WINDOW", self.quit_app)
        self.geometry(cfg.get("geometry", "1000x480+40+40"))
        self._fitted = False
        self._apply_top()
        self._apply_cols()
        self.after(50, self._dark_titlebar)
        self.after(200, self.refresh)
        self.after(1000, self.tick)

    # ---- window chrome --------------------------------------------------
    def _icon(self):
        """Shield emblem for the title bar / taskbar, plus a small copy for the header."""
        self._img = self._logo = None
        try:
            self._img = tk.PhotoImage(file=str(am.BUNDLE / "icon.png"))
            small = tk.PhotoImage(file=str(am.BUNDLE / "icon-64.png"))
            self.iconphoto(True, self._img, small)
            self._logo = tk.PhotoImage(file=str(am.BUNDLE / "icon-30.png"))
        except tk.TclError:          # icon files missing: keep the default
            pass

    def _dark_titlebar(self):
        """Match the Windows title bar to the dark theme (Windows 10 20H1+ / 11)."""
        if sys.platform != "win32":
            return
        try:
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
            on = ctypes.c_int(1)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(on), ctypes.sizeof(on))
            self.withdraw(); self.deiconify()        # repaint the frame with the new colour
        except (AttributeError, OSError):
            pass

    def _xset(self, first, last):
        self.xs.set(first, last)
        if float(first) <= 0 and float(last) >= 1:
            self.xs.pack_forget()
        elif not self.xs.winfo_ismapped():
            self.xs.pack(side="bottom", fill="x", before=self.tree)

    def _apply_top(self):
        self.attributes("-topmost", self.top.get())

    def _apply_cols(self):
        show = [c[0] for c in COLS if c[4] or self.all_cols.get()]
        self.tree.configure(displaycolumns=show)
        self._fitted = False
        self.after(80, self._fit)

    def _set_legend(self):
        tax = am.TAX[self.premium.get()]
        self.legend.set(f"{tax:.0%} tax + 2.5% setup  ·  Est./day = 10% of volume  ·  Double-click copies name")

    def _field(self, parent, label, widget):
        tk.Label(parent, text=label, font=FONT, fg=DIM, bg=PANEL).pack(side="left")
        widget.pack(side="left", padx=(6, 16))

    def _style(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure(".", background=PANEL, foreground=FG, fieldbackground=PANEL, font=FONT, borderwidth=0,
                    bordercolor=LINE, lightcolor=PANEL, darkcolor=PANEL, focuscolor=PANEL)
        s.configure("Dark.Treeview", background=ROW, fieldbackground=ROW, foreground=FG, rowheight=28, borderwidth=0)
        s.layout("Dark.Treeview", [("Treeview.treearea", {"sticky": "nswe"})])     # drop the white focus border
        s.configure("Dark.Treeview.Heading", background=PANEL, foreground=DIM, font=FONT_B, relief="flat",
                    padding=(6, 6), bordercolor=PANEL, lightcolor=PANEL, darkcolor=PANEL)
        s.map("Dark.Treeview", background=[("selected", SEL)], foreground=[("selected", FG)])
        s.map("Dark.Treeview.Heading", background=[("active", "#2a2d35")], foreground=[("active", FG)])
        s.configure("Gold.TButton", background=GOLD, foreground="#1b1b1b", font=FONT_B, padding=(16, 5),
                    bordercolor=GOLD, lightcolor=GOLD, darkcolor=GOLD)
        s.map("Gold.TButton", background=[("active", "#f3c95a"), ("disabled", "#6b5a2a")],
              foreground=[("disabled", "#2a2a2a")])
        s.configure("Dark.TCheckbutton", background=PANEL, foreground=FG, indicatorbackground=ROW2,
                    indicatorforeground=GOLD, indicatormargin=(0, 0, 6, 0))
        s.map("Dark.TCheckbutton", background=[("active", PANEL)], indicatorbackground=[("selected", ROW2)])
        s.configure("Head.TCheckbutton", background=BG, foreground=DIM, indicatorbackground=ROW2,
                    indicatorforeground=GOLD, indicatormargin=(0, 0, 6, 0))
        s.map("Head.TCheckbutton", background=[("active", BG)], foreground=[("active", FG), ("selected", FG)],
              indicatorbackground=[("selected", ROW2)])
        for w in ("TCombobox", "TSpinbox"):
            s.configure(w, arrowcolor=DIM, background=ROW2, foreground=FG, fieldbackground=ROW2,
                        selectbackground=ROW2, selectforeground=FG, bordercolor=LINE, lightcolor=ROW2,
                        darkcolor=ROW2, insertcolor=FG, padding=(6, 3))
            s.map(w, fieldbackground=[("readonly", ROW2)], foreground=[("readonly", FG)],
                  background=[("active", SEL)], arrowcolor=[("active", FG)],
                  selectbackground=[("readonly", ROW2)], selectforeground=[("readonly", FG)])
        s.configure("Dark.Vertical.TScrollbar", background=PANEL, troughcolor=ROW, arrowcolor=DIM,
                    bordercolor=ROW, lightcolor=PANEL, darkcolor=PANEL, gripcount=0)
        s.map("Dark.Vertical.TScrollbar", background=[("active", SEL)])
        s.configure("Dark.Horizontal.TScrollbar", background=PANEL, troughcolor=ROW, arrowcolor=DIM,
                    bordercolor=ROW, lightcolor=PANEL, darkcolor=PANEL, gripcount=0)
        s.map("Dark.Horizontal.TScrollbar", background=[("active", SEL)])
        self.option_add("*TCombobox*Listbox.background", PANEL)
        self.option_add("*TCombobox*Listbox.foreground", FG)
        self.option_add("*TCombobox*Listbox.selectBackground", SEL)
        self.option_add("*TCombobox*Listbox.font", FONT)

    # ---- scanning -------------------------------------------------------
    def refresh(self):
        self._set_legend()
        if self._scanning:
            self._again = True       # settings changed mid-scan: rescan when this one finishes
            return
        self._scanning = True
        self.btn.state(["disabled"])
        try:
            mm = self.margin.get() / 100
        except tk.TclError:          # spinbox mid-edit
            mm = 0.10
        city = self.city.get()
        if self.scope.get() == WATCH:
            bad = []
            ids = am.load_watchlist(bad=bad)
            scope = None
            self._show_bad(bad)
            if not ids:
                self._scanning = False; self.btn.state(["!disabled"])
                found = (am.HERE / "watchlist.txt").exists()
                self.status.set("no items in watchlist.txt" if found
                                else "watchlist.txt not found next to the app (unzip the folder first)")
                return
        else:
            scope, ids = am.SCOPES[self.scope.get()], None
            self._show_bad([])
        self.status.set("scanning…")
        threading.Thread(target=self._worker, args=(city, scope, mm, ids, self.premium.get()), daemon=True).start()

    def _worker(self, city, scope, mm, ids, premium):
        try:
            rows = am.scan(city=city, scope=scope, min_margin=mm, ids=ids, premium=premium,
                           progress=lambda d, t, m: self.after(0, self.status.set, m),
                           stop=lambda: self._stop)
            self.after(0, self._done, rows, city, None)
        except Exception as e:  # network down, API error
            self.after(0, self._done, [], city, str(e))

    def _show_bad(self, bad):
        """Amber strip above the table listing watchlist lines that didn't match an item."""
        if not bad:
            self.warnbar.pack_forget()
            return
        shown = ", ".join(bad[:4]) + (f" (+{len(bad) - 4} more)" if len(bad) > 4 else "")
        n = len(bad)
        self.warn.set(f"⚠  {n} line{'s' if n > 1 else ''} in watchlist.txt didn't match an item and "
                      f"{'are' if n > 1 else 'is'} skipped: {shown}. Check the spelling against the game.")
        if not self.warnbar.winfo_ismapped():
            self.warnbar.pack(fill="x", padx=16, pady=(10, 0), before=self.wrap)

    def _every_min(self):
        try:
            return max(1, self.every.get())
        except tk.TclError:
            return 2

    def _done(self, rows, city, err):
        if self._stop:
            return
        self._scanning = False
        self.btn.state(["!disabled"])
        self.next_at = time.time() + self._every_min() * 60
        if err:
            self.status.set(f"scan failed ({err[:50]}), retrying in {self._every_min()} min")
        else:
            self.rows = rows
            self.render()
            self.after(80, self._fit)
            self._base = f"{city}  ·  {len(rows)} items  ·  updated {datetime.now():%H:%M}"
            self.updated.set(self._base)
            self.status.set("")
        if self._again:
            self._again = False
            self.after(10, self.refresh)
        if self.selftest:
            print(f"selftest: {len(rows)} rows" + (f", error: {err}" if err else ""))
            for r in rows[:5]:
                print(f"  {r['item']:40} bid {r['bid']:>8,} ask {r['ask']:>8,} net {r['unit']:>7,.0f}")
            self.after(300, self.quit_app)

    def tick(self):
        if not self._scanning and self.next_at:
            if time.time() >= self.next_at:
                self.refresh()
            else:
                left = int(self.next_at - time.time())
                self.updated.set(f"{self._base}  ·  next in {left // 60}:{left % 60:02d}")
        self.after(1000, self.tick)

    # ---- table ----------------------------------------------------------
    def _fit(self):
        """Widen the window once so every shown column is visible (Windows DPI scaling widens cells)."""
        if self._fitted:
            return
        kids = self.tree.get_children()
        if not kids:
            return
        shown = [c for c in COLS if c[4] or self.all_cols.get()]
        seen_px, seen_req = 0, 0
        for key, _, req, _, _ in shown:
            bb = self.tree.bbox(kids[0], key)      # empty for columns clipped off-screen
            if bb:
                seen_px += bb[2]; seen_req += req
        if not seen_req:
            return
        scale = seen_px / seen_req                  # real px per requested px (DPI scaling)
        total = int(sum(c[2] for c in shown) * scale)
        overflow = total + self.ys.winfo_reqwidth() + 4 - self.wrap.winfo_width()
        if self.selftest:
            print(f"fit: scale={scale:.3f} total={total} wrap={self.wrap.winfo_width()} win={self.winfo_width()} "
                  f"overflow={overflow}")
        if overflow > 0:      # grow to fit, but never past the screen edge (scrollbar takes over)
            room = self.winfo_screenwidth() - self.winfo_rootx() - 8
            w = min(self.winfo_width() + overflow + 8, max(room, self.winfo_width()))
            self.geometry(f"{w}x{self.winfo_height()}")
        self._fitted = True

    def sort(self, col):
        self.sort_desc = not self.sort_desc if col == self.sort_col else col != "item"
        self.sort_col = col
        self.render()

    def render(self):
        for key, label, *_ in COLS:
            arrow = (" ▾" if self.sort_desc else " ▴") if key == self.sort_col else ""
            self.tree.heading(key, text=label + arrow)
        self.tree.delete(*self.tree.get_children())
        key = (lambda r: r["item"].lower()) if self.sort_col == "item" else (lambda r: r[self.sort_col])
        rows = sorted(self.rows, key=key, reverse=self.sort_desc)
        for i, r in enumerate(rows[:600]):
            tags = ("pos" if r["unit"] > 0 else "neg", "odd" if i % 2 else "even")
            self.tree.insert("", "end", values=[fmt(c[0], r[c[0]]) for c in COLS], tags=tags)
        if not rows:
            self.status.set("no flips above your margin right now")

    def copy_item(self, _):
        sel = self.tree.selection()
        if sel:
            name = str(self.tree.item(sel[0])["values"][0])
            self.clipboard_clear(); self.clipboard_append(name)
            self.status.set(f"copied “{name}”")

    def quit_app(self):
        self._stop = True
        if not self.selftest:
            try:
                SETTINGS.write_text(json.dumps(dict(
                    city=self.city.get(), scope=self.scope.get(), margin=self.margin.get(),
                    every=self._every_min(), on_top=self.top.get(), all_cols=self.all_cols.get(),
                    premium=self.premium.get(), geometry=self.geometry()), indent=1), encoding="utf-8")
            except (OSError, tk.TclError):
                pass
        self.destroy()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    Widget(selftest=a.selftest).mainloop()
