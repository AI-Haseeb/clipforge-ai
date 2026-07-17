# src/utils/license_manager.py
from __future__ import annotations  # enables future Python language features
import calendar  # works with calendar month/date logic
import hashlib  # creates cryptographic hashes
import json  # handles JSON encode and decode
import re  # matches and cleans text with regular expressions
import sys  # accesses Python runtime and CLI state
from dataclasses import dataclass, asdict  # creates lightweight data classes
from datetime import date, datetime, timezone  # works with dates and timestamps
from pathlib import Path  # provides object-oriented file paths
from typing import Tuple, Optional  # adds type hint helpers

# ---------------------------
# Config paths / filenames
# ---------------------------

CONFIG_DIR_NAME = "config"
LICENSE_STATE_FILENAME = "license_state.json"

# ⚠️ IMPORTANT:
# Is secret ko apni marzi ka long random string bana do.
# Issi se saari keys generate / verify hongi.
MASTER_SALT = "ClipForge_AI_PRO_2026_x9K7LmP4Qa2Zt8Vf3R1uS6YwC0DhN5B"

# --------------------------------
# Dataclass: LicenseState (MONTHLY ONLY)
# --------------------------------

@dataclass
class LicenseState:  # stores validated data and related behavior for License State
    provider: str = "none"   # "offline" / "none"
    email: str = ""
    license_key: str = ""
    is_active: bool = False

    # monthly fields
    activated_at_utc: str = ""   # ISO string
    expires_at_utc: str = ""     # ISO string


# --------------------------------
# Time helpers
# --------------------------------
def _utc_now() -> datetime:  # returns the current UTC time for auth/license timestamps
    return datetime.now(timezone.utc)
def _iso_utc(dt: datetime) -> str:  # formats a UTC datetime for license metadata
    return dt.astimezone(timezone.utc).isoformat()
def _parse_iso_utc(s: str) -> Optional[datetime]:  # turns raw text/API data into structured values
    try:
        if not s:
            return None
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None


# --------------------------------
# Calendar month add (real calendar)
# --------------------------------
def add_months_calendar(d: date, months: int = 1) -> date:  # adds calendar months while preserving valid month-end dates
    """
    Calendar-based add months:
      Jan 31 + 1 month => Feb 28/29
    """
    y = d.year + (d.month - 1 + months) // 12
    m = (d.month - 1 + months) % 12 + 1
    last_day = calendar.monthrange(y, m)[1]
    day = min(d.day, last_day)
    return date(y, m, day)
def _today_yyyymmdd() -> str:  # returns today as a compact YYYYMMDD date string
    d = _utc_now().date()
    return d.strftime("%Y%m%d")
def compute_expiry_yyyymmdd_from_generated(generated_yyyymmdd: str, months: int = 1) -> str:  # computes license expiry from a generated date and plan duration
    """
    Given generated date YYYYMMDD, return calendar-based expiry YYYYMMDD.
    """
    try:
        y = int(generated_yyyymmdd[0:4])
        m = int(generated_yyyymmdd[4:6])
        d = int(generated_yyyymmdd[6:8])
        gen_date = date(y, m, d)
    except Exception:
        # fallback to today if parsing fails
        gen_date = _utc_now().date()

    exp = add_months_calendar(gen_date, months=months)
    return exp.strftime("%Y%m%d")
def compute_expiry_yyyymmdd_from_today(months: int = 1) -> str:  # computes license expiry from the current date and plan duration
    """
    Generator helper:
      Today + 1 calendar month -> expiry date (YYYYMMDD)
    """
    return compute_expiry_yyyymmdd_from_generated(_today_yyyymmdd(), months=months)
def format_yyyymmdd_pretty(yyyymmdd: str) -> str:  # formats a YYYYMMDD date for readable UI display
    """
    20260216 -> 16 Feb 2026
    """
    try:
        y = int(yyyymmdd[0:4])
        m = int(yyyymmdd[4:6])
        d = int(yyyymmdd[6:8])
        dt = date(y, m, d)
        return dt.strftime("%d %b %Y")
    except Exception:
        return yyyymmdd
def _expiry_end_of_day_utc(yyyymmdd: str) -> Optional[datetime]:  # converts an expiry date into its final UTC second
    """
    Expiry is end-of-day UTC of that YYYYMMDD.
    """
    try:
        y = int(yyyymmdd[0:4])
        m = int(yyyymmdd[4:6])
        d = int(yyyymmdd[6:8])
        return datetime(y, m, d, 23, 59, 59, tzinfo=timezone.utc)
    except Exception:
        return None


# --------------------------------
# Helpers: paths
# --------------------------------
def _get_config_dir() -> Path:  # returns a resolved value used by later code
    """
    EXE + dev dono ko handle karta hai:
      - PyInstaller EXE ho to usi folder/config/
      - Dev mode me project root/config/
    """
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).resolve().parent
    else:
        # src/utils/license_manager.py -> utils -> src -> project root
        base = Path(__file__).resolve().parents[2]
    return base / CONFIG_DIR_NAME
def _get_license_state_path() -> Path:  # returns a resolved value used by later code
    return _get_config_dir() / LICENSE_STATE_FILENAME


# --------------------------------
# Public API: load/save / query
# --------------------------------
def load_license_state() -> LicenseState:  # loads required data/settings into memory
    path = _get_license_state_path()
    try:
        if path.is_file():
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            return LicenseState(**data)
    except Exception:
        pass
    return LicenseState()
def _save_license_state(state: LicenseState) -> None:  # saves generated state or output files
    try:
        cfg = _get_config_dir()
        cfg.mkdir(parents=True, exist_ok=True)
        path = _get_license_state_path()
        with path.open("w", encoding="utf-8") as f:
            json.dump(asdict(state), f, indent=2)
    except Exception:
        # disk fail = ignore
        pass
def is_pro_unlocked(state: LicenseState | None) -> bool:  # checks whether local Pro license access is currently valid
    """
    Monthly unlock:
      - must be active
      - must have valid expires_at_utc
      - now must be <= expires
    """
    if not state or not state.is_active:
        return False

    exp = _parse_iso_utc(state.expires_at_utc)
    if not exp:
        return False

    return _utc_now() <= exp


# --------------------------------
# Offline monthly license algo
# Key format: YYYYMMDD-XXXX-XXXX-XXXX
# --------------------------------
def _normalize_email(email: str) -> str:  # standardizes values before comparison or rendering
    return (email or "").strip().lower()
def _normalize_key(key: str) -> str:  # standardizes values before comparison or rendering
    # remove spaces / hyphens, uppercase
    k = (key or "").replace("-", "").replace(" ", "")
    return k.upper()
def _parse_expiry_from_key(key: str) -> str:  # turns raw text/API data into structured values
    """
    Extract YYYYMMDD from beginning of key.
    """
    k = (key or "").strip()
    first = k.split("-", 1)[0]
    return first if re.fullmatch(r"\d{8}", first or "") else ""
def _raw_hash_for_email_and_expiry(email: str, expiry_yyyymmdd: str) -> str:  # hashes license identity data before signature formatting
    base = f"{email}|{expiry_yyyymmdd}|{MASTER_SALT}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest().upper()
def _format_sig_from_hash(h: str, groups: int = 3, group_size: int = 4) -> str:  # formats a license hash into the visible key signature
    core = h[: groups * group_size]
    parts = [core[i:i + group_size] for i in range(0, len(core), group_size)]
    return "-".join(parts)
def generate_monthly_license_key(email: str, expiry_yyyymmdd: str) -> str:  # generates text, media, metadata, captions, or thumbnails
    """
    Generate monthly key for given email + expiry date (YYYYMMDD).
    Output: YYYYMMDD-XXXX-XXXX-XXXX
    """
    email_norm = _normalize_email(email)
    h = _raw_hash_for_email_and_expiry(email_norm, expiry_yyyymmdd)
    sig = _format_sig_from_hash(h, groups=3, group_size=4)
    return f"{expiry_yyyymmdd}-{sig}"
def create_monthly_license(email: str, months: int = 1):  # creates an output artifact or runtime object
    """
    Helper for backend / CLI.

    Steps:
      - email ko normalize karega
      - generated date = aaj (YYYYMMDD)
      - expiry date   = aaj + `months` calendar months (YYYYMMDD)
      - key           = generate_monthly_license_key(email_norm, expiry)

    Returns:
      (email_norm, generated_yyyymmdd, expiry_yyyymmdd, license_key)
    """
    email_norm = _normalize_email(email)
    if not email_norm:
        raise ValueError("Email is required.")

    # same calendar logic that rest of the file uses
    generated = _today_yyyymmdd()
    expiry = compute_expiry_yyyymmdd_from_generated(generated, months=months)
    key = generate_monthly_license_key(email_norm, expiry)
    return email_norm, generated, expiry, key
def validate_license_key(email: str, license_key: str):  # validates a local license key against email and expiry data
    """
    Developer/test helper:
    Pure offline validator that mirrors activate_license logic
    but WITHOUT saving state anywhere.

    Returns:
      (True,  "License valid until YYYYMMDD.")
      (False, "Error message...")
    """
    email_norm = _normalize_email(email) or "no-email"
    key_raw = (license_key or "").strip()

    if not key_raw:
        return False, "License key is missing."

    # 1) Key ke start se expiry nikaalo (YYYYMMDD)
    expiry_yyyymmdd = _parse_expiry_from_key(key_raw)
    if not expiry_yyyymmdd:
        return False, "Invalid key format (expiry missing)."

    # 2) Expiry ko datetime banaao (end of day UTC)
    exp_dt = _expiry_end_of_day_utc(expiry_yyyymmdd)
    if not exp_dt:
        return False, "Invalid expiry date inside key."

    # 3) Agar already expire ho chuki hai
    if _utc_now() > exp_dt:
        return False, f"License expired on {expiry_yyyymmdd}."

    # 4) Signature verify karo (email + expiry + MASTER_SALT)
    expected = _expected_key_for(email_norm, expiry_yyyymmdd)
    if _normalize_key(key_raw) != _normalize_key(expected):
        return False, "Invalid license key for this email."

    # 5) Sab OK
    return True, f"License valid until {expiry_yyyymmdd}."
def _expected_key_for(email: str, expiry_yyyymmdd: str) -> str:  # generates the license key expected for a user/date pair
    return generate_monthly_license_key(email, expiry_yyyymmdd)


# --------------------------------
# Public API: activate_license (MONTHLY)
# --------------------------------
def activate_license(  # stores a valid license activation locally
    provider: str,
    license_key: str,
    email: str = "",
) -> Tuple[bool, str, LicenseState]:
    """
    App activation:
      - key must include expiry (YYYYMMDD-...)
      - key must match email + expiry signature
      - key must not be expired
      - saves activated_at_utc + expires_at_utc
    """
    provider = "offline"

    email_norm = _normalize_email(email) or "no-email"
    key_raw = (license_key or "").strip()

    if not key_raw:
        return False, "License key is missing.", load_license_state()

    expiry_yyyymmdd = _parse_expiry_from_key(key_raw)
    if not expiry_yyyymmdd:
        return False, "Invalid key format (expiry missing).", load_license_state()

    exp_dt = _expiry_end_of_day_utc(expiry_yyyymmdd)
    if not exp_dt:
        return False, "Invalid expiry date inside key.", load_license_state()

    if _utc_now() > exp_dt:
        return False, "License expired. Please renew ($29/month).", load_license_state()

    expected = _expected_key_for(email_norm, expiry_yyyymmdd)
    if _normalize_key(key_raw) != _normalize_key(expected):
        return False, "Invalid license key for this email.", load_license_state()

    now = _utc_now()
    new_state = LicenseState(
        provider="offline",
        email=email_norm,
        license_key=expected,
        is_active=True,
        activated_at_utc=_iso_utc(now),
        expires_at_utc=_iso_utc(exp_dt),
    )
    _save_license_state(new_state)
    return True, "License activated ($29/month).", new_state
