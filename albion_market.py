"""Albion Online Data Project client + flip scanner (Americas / west).

Used by flip-widget.py (the desktop app).
Prices are crowd-sourced; every row carries the observation age and rows
older than max_age_h are dropped.
"""
import gzip, json, os, re, sys, time, urllib.request, urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path

UA = "albion-flips/1.0"
BASE = "https://west.albion-online-data.com/api/v2/stats"
SETUP = 0.025                # setup fee on both sell and buy orders
TAX = {True: 0.04, False: 0.08}   # sales tax with / without premium
SHARE = 0.10                 # assume we capture 10% of daily volume
DEBUG = bool(os.environ.get("ALBION_DEBUG"))
# bundled files (items.txt) live next to the script, or inside the exe when frozen;
# user files (watchlist.txt, settings.json) always live next to the script / exe
if getattr(sys, "frozen", False):
    BUNDLE, HERE = Path(sys._MEIPASS), Path(sys.executable).resolve().parent
else:
    BUNDLE = HERE = Path(__file__).resolve().parent

CITIES = ["Thetford", "Lymhurst", "Martlock", "Bridgewatch", "Fort Sterling", "Caerleon", "Brecilien"]

SKIP = re.compile(r"QUESTITEM|UNIQUE|SKIN|TOKEN|_LABOURER|JOURNAL_.*_EMPTY|TROPHY|FURNITURE|^T1_|^T2_|PLAYERISLAND|FARM_.*_(BABY|GROWN)|SEED|CAPEITEM_.*_FW|_SET\d|RANDOM|EVENT|BATTLEVAULT|KNOWLEDGE|SILVERBAG|_HERETIC_|_UNDEAD_|_KEEPER_|_MORGANA_|_AVALON_ARTEFACT|ARTEFACT|ESSENCE|RUNE|SOUL|RELIC|ALCHEMY|_SHARD")

SCOPES = {
    "All items": None,
    "Consumables (food, potions)": re.compile(r"_MEAL_|_POTION_|FISHSAUCE|_BUTTER|_FLOUR|_BREAD"),
    "Refined resources": re.compile(r"_(METALBAR|PLANKS|CLOTH|LEATHER|STONEBLOCK)(_LEVEL\d)?$"),
    "Farm goods": re.compile(r"^T\d_(WHEAT|CARROT|BEAN|TURNIP|CABBAGE|POTATO|CORN|PUMPKIN|AGARIC|COMFREY|BURDOCK|TEASEL|FOXGLOVE|MULLEIN|YARROW|MILK|EGG|MEAT|FARM_.*_(BABY|GROWN))$"),
    "Mounts": re.compile(r"_MOUNT_"),
    "Bags & capes": re.compile(r"_BAG|_CAPE"),
}


def get(url, retries=4, stop=None):
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Encoding": "gzip"})
            with urllib.request.urlopen(req, timeout=60) as r:
                body = r.read()
                if r.headers.get("Content-Encoding") == "gzip":
                    body = gzip.decompress(body)
                return json.loads(body.decode())
        except urllib.error.HTTPError as e:
            last = e
            if DEBUG:
                print(f"  HTTP {e.code} on {url[:90]}… headers={dict(e.headers)}")
            if e.code != 429:
                time.sleep(2 + 2 * i); continue
            # rate limited: honour Retry-After, else back off 15/30/45 s
            try:
                wait = int(e.headers.get("Retry-After", ""))
            except ValueError:
                wait = 15 * (i + 1)
            for _ in range(min(wait, 120)):
                if stop and stop():
                    raise RuntimeError("stopped")
                time.sleep(1)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError) as e:
            last = e
            time.sleep(2 + 2 * i)
    raise RuntimeError("rate limited by the price API" if getattr(last, "code", 0) == 429 else f"API failed: {last}")


# 7-day history moves slowly, so it's cached and only current prices are fetched every refresh
HIST_TTL = 30 * 60
_hist = {}      # (location, item_id, quality) -> (sold_per_day, avg_price)
_hist_at = {}   # (location, item_id) -> when its history was last fetched


def load_items(path=BUNDLE / "items.txt"):
    """Return (ids, names). ids skip junk; names covers every id."""
    ids, names = [], {}
    for line in open(path, encoding="utf-8", errors="ignore"):
        m = re.match(r"\s*\d+:\s*(\S+)\s*:\s*(.*)", line)
        if not m:
            continue
        iid, name = m.group(1), m.group(2).strip()
        names[iid] = name
        if not SKIP.search(iid):
            ids.append(iid)
    return ids, names


def pretty(iid, names):
    base, _, ench = iid.partition("@")
    plain = re.sub(r"_LEVEL\d+$", "", base)
    nm = names.get(base) or names.get(plain, base)
    return nm + (f" .{ench}" if ench else "")


def load_watchlist(path=HERE / "watchlist.txt", bad=None):
    """Item ids or display names, one per line; '#' comments. Returns ids.

    Lines that don't match an item are appended to `bad` (when given) instead of vanishing silently.
    """
    _, names = load_items()
    by_name = {}
    for k, v in names.items():           # plain ids win over @1/@2/@3 variants that share the name
        if "@" not in k:
            by_name.setdefault(v.lower(), k)
    for k, v in names.items():
        by_name.setdefault(v.lower(), k)
    ids = []
    if not path.exists():
        return ids
    for line in open(path, encoding="utf-8", errors="ignore"):
        s = line.split("#")[0].strip()
        if not s:
            continue
        base, _, ench = s.partition("@")
        if base in names or re.sub(r"_LEVEL\d+$", "", base) in names:
            ids.append(s)
        else:
            m = re.match(r"(.*?)\s*\.([1-4])$", base)      # "Beef Stew .1", "Steel Bar .4"
            nm, e = (m.group(1), m.group(2)) if m else (base, ench)
            iid = by_name.get(nm.lower())
            if iid and e:
                # gear/food enchants are ID@n; resources are ID_LEVELn@n
                iid = next((c for c in (f"{iid}@{e}", f"{iid}_LEVEL{e}@{e}") if c in names), None)
            if iid:
                ids.append(iid)
            elif bad is not None:
                bad.append(s)
    return ids


def scan(city="Thetford", scope=None, min_margin=0.10, max_age_h=24, batch=100,
         progress=None, stop=None, ids=None, premium=True):
    """Return list of dict rows sorted by est_day desc.

    scope: None or a compiled regex applied to the item id.
    ids: explicit id list (watchlist) that bypasses scope.
    progress(done, total, msg) is called as work proceeds; stop() -> True aborts.
    """
    tax_sell, fee_buy = TAX[premium] + SETUP, SETUP
    all_ids, names = load_items()
    ids_given = ids is not None          # watchlist: show every row, even bad ones
    if ids_given:
        ids = list(ids)
    else:
        ids = all_ids if scope is None else [i for i in all_ids if scope.search(i)]
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_h)
    loc = city.replace(" ", "")
    cands = []
    total = (len(ids) + batch - 1) // batch
    for n, i in enumerate(range(0, len(ids), batch)):
        if stop and stop():
            return []
        chunk = ",".join(ids[i:i + batch])
        rows = get(f"{BASE}/prices/{chunk}.json?locations={loc}", stop=stop)
        for r in rows:
            s, b = r["sell_price_min"], r["buy_price_max"]
            if not s or not b:
                continue
            sd = datetime.fromisoformat(r["sell_price_min_date"]).replace(tzinfo=timezone.utc)
            bd = datetime.fromisoformat(r["buy_price_max_date"]).replace(tzinfo=timezone.utc)
            if not ids_given and (sd < cutoff or bd < cutoff):
                continue           # watchlist rows stay visible; the Age column shows staleness
            cost = (b + 1) * (1 + fee_buy)
            rev = (s - 1) * (1 - tax_sell)
            if ids_given or (rev - cost) / cost >= min_margin:
                cands.append(dict(id=r["item_id"], q=r["quality"], sell=s, buy=b,
                                  age_h=round((datetime.now(timezone.utc) - min(sd, bd)).total_seconds() / 3600, 1)))
        if progress:
            progress(n + 1, total + 1, f"prices {n + 1}/{total}, {len(cands)} candidates")
        time.sleep(1.0)

    now = time.time()
    uniq = sorted({c["id"] for c in cands})
    need = [i for i in uniq if now - _hist_at.get((loc, i), 0) > HIST_TTL]
    nh = (len(need) + 49) // 50
    for k, i in enumerate(range(0, len(need), 50)):
        if stop and stop():
            return []
        chunk = need[i:i + 50]
        if progress:
            progress(total + 1, total + 1, f"7-day history {k + 1}/{nh}")
        for r in get(f"{BASE}/history/{','.join(chunk)}.json?locations={loc}&time-scale=24", stop=stop):
            data = r["data"][-7:]
            n = sum(x["item_count"] for x in data)
            avg = sum(x["avg_price"] * x["item_count"] for x in data) / n if n else 0.0
            days = sorted(x["avg_price"] for x in data)
            if days:
                med = days[len(days) // 2]
                if avg > 1.5 * med:      # single-day outlier protection
                    avg = med
            _hist[(loc, r["item_id"], r["quality"])] = (n / 7.0, avg)
        for iid in chunk:                # items with no sales still count as fetched
            _hist_at[(loc, iid)] = now
        time.sleep(1.0)
    vol = {(iid, q): v for (l, iid, q), v in _hist.items() if l == loc}
    if progress:
        progress(total + 1, total + 1, "ranking")

    out = []
    for c in cands:
        v, avg = vol.get((c["id"], c["q"]), (0.0, 0.0))
        if not ids_given and (v < 3 or not avg):
            continue
        if not avg:
            avg = c["sell"]
        buy_at = max(c["buy"] + 1, 0.8 * avg)
        sell_at = min(c["sell"] - 1, avg)
        unit = sell_at * (1 - tax_sell) - buy_at * (1 + fee_buy)
        rm = unit / (buy_at * (1 + fee_buy))
        if not ids_given and rm < 0.08:
            continue
        out.append(dict(item=pretty(c["id"], names), id=c["id"], q=c["q"], ask=c["sell"], bid=c["buy"], buy_at=round(buy_at),
                        sell_at=round(sell_at), avg=round(avg), margin=rm, vol_day=v,
                        unit=unit, est_day=unit * v * SHARE, capital=buy_at * v * SHARE, age_h=c["age_h"]))
    out.sort(key=lambda r: -r["est_day"])
    return out
