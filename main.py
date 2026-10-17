# -*- coding: utf-8 -*-
"""
HealthTrack Pro - Smart Water Intake Tracker & Prescription Medicine Reminder
With Full Onboarding Flow, Categorized Settings, History Reports,
and Built-in Customizable Alarm Ringtones (Water Sounds, Rain Sounds, Chimes, Bells).
"""

import os
import sys
import time
import datetime
import sqlite3
import re
import shutil
import threading
import math
import wave
import struct
import random
import subprocess
import flet as ft

from device_services import LocalNotificationService, play_ringtone_sound, request_runtime_permissions

try:
    from auth_security import hash_password, verify_password
except ImportError:
    import hashlib
    def hash_password(pw): return hashlib.sha256(pw.encode()).hexdigest()
    def verify_password(pw, h): return hash_password(pw) == h

def get_safe_app_storage():
    if os.name == 'nt':
        appdata = os.getenv('LOCALAPPDATA') or os.path.expanduser('~')
        path = os.path.join(appdata, 'HealthTrackPro')
    else:
        path = os.path.join(os.path.expanduser('~'), '.healthtrackpro')
        if '/working_dir' in path or not os.access(os.path.dirname(path), os.W_OK):
            path = '/tmp/healthtrack_app'
    os.makedirs(path, exist_ok=True)
    return path

APP_STORAGE_DIR = get_safe_app_storage()
DB_NAME = os.path.join(APP_STORAGE_DIR, "healthtrack_water_meds.db")

def get_photos_dir():
    photos_dir = os.path.join(APP_STORAGE_DIR, "medicine_photos")
    os.makedirs(photos_dir, exist_ok=True)
    return photos_dir

PHOTOS_DIR = get_photos_dir()

# -------------------------------------------------------------
# AUDIO & SOUND ENGINE (WATER, RAIN, CHIME, BELL)
# -------------------------------------------------------------
RINGTONE_OPTIONS = [
    {
        "id": "water_droplets",
        "name": "Water Droplets / Pouring",
        "icon": "💧",
        "desc": "Calming natural water flow & soothing droplet splashes"
    },
    {
        "id": "rain_gentle",
        "name": "Gentle Rainfall",
        "icon": "🌧️",
        "desc": "Peaceful ambient rain drizzle sound"
    },
    {
        "id": "zen_chime",
        "name": "Peaceful Zen Chime",
        "icon": "🧘",
        "desc": "Harmonic meditation chime & peaceful melody"
    },
    {
        "id": "alarm_bell",
        "name": "Classic Alarm Bell",
        "icon": "🔔",
        "desc": "Traditional crisp ringing alarm bell"
    },
    {
        "id": "default_beep",
        "name": "Digital Alert Beep",
        "icon": "📱",
        "desc": "Loud and clear digital beep alert"
    }
]

def ensure_sound_assets():
    dirs = ['assets/sounds', 'sounds', os.path.join(APP_STORAGE_DIR, 'sounds')]
    for d in dirs:
        os.makedirs(d, exist_ok=True)
    
    sample_rate = 22050

    def gen_water(p):
        duration = 2.5
        num_samples = int(duration * sample_rate)
        with wave.open(p, 'w') as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(sample_rate)
            drops = [0.1, 0.4, 0.8, 1.2, 1.6, 2.0]
            freqs = [1200, 1600, 1400, 1800, 1300, 1700]
            data = bytearray()
            for i in range(num_samples):
                t = i / sample_rate
                val = 0.0
                for d_t, freq in zip(drops, freqs):
                    if t >= d_t and t < d_t + 0.35:
                        dt = t - d_t
                        f = freq + (dt * 2000)
                        env = math.exp(-15 * dt)
                        val += 0.6 * env * math.sin(2 * math.pi * f * dt)
                val += 0.08 * math.sin(2 * math.pi * 320 * t) * (1 - t/duration)
                val = max(-1.0, min(1.0, val))
                data.extend(struct.pack('<h', int(val * 32767)))
            w.writeframes(data)

    def gen_rain(p):
        duration = 3.0
        num_samples = int(duration * sample_rate)
        with wave.open(p, 'w') as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(sample_rate)
            data = bytearray()
            last_val = 0.0
            random.seed(42)
            for i in range(num_samples):
                t = i / sample_rate
                white = random.uniform(-1, 1)
                last_val = 0.92 * last_val + 0.08 * white
                val = last_val * 0.45
                if random.random() < 0.008:
                    val += random.uniform(0.2, 0.5)
                env = min(1.0, t * 3) * min(1.0, (duration - t) * 3)
                val = max(-1.0, min(1.0, val * env))
                data.extend(struct.pack('<h', int(val * 32767)))
            w.writeframes(data)

    def gen_chime(p):
        duration = 2.5
        num_samples = int(duration * sample_rate)
        with wave.open(p, 'w') as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(sample_rate)
            data = bytearray()
            notes = [(0.0, 523.25), (0.4, 659.25), (0.8, 783.99), (1.2, 1046.50)]
            for i in range(num_samples):
                t = i / sample_rate
                val = 0.0
                for n_t, freq in notes:
                    if t >= n_t:
                        dt = t - n_t
                        env = math.exp(-3.5 * dt)
                        val += 0.35 * env * math.sin(2 * math.pi * freq * dt)
                        val += 0.15 * env * math.sin(2 * math.pi * freq * 2 * dt)
                val = max(-1.0, min(1.0, val))
                data.extend(struct.pack('<h', int(val * 32767)))
            w.writeframes(data)

    def gen_bell(p):
        duration = 2.0
        num_samples = int(duration * sample_rate)
        with wave.open(p, 'w') as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(sample_rate)
            data = bytearray()
            for i in range(num_samples):
                t = i / sample_rate
                env = math.exp(-2.5 * (t % 0.5))
                val = env * (0.5 * math.sin(2 * math.pi * 880 * t) + 0.3 * math.sin(2 * math.pi * 1760 * t))
                val = max(-1.0, min(1.0, val))
                data.extend(struct.pack('<h', int(val * 32767)))
            w.writeframes(data)

    sound_gens = [
        ('water_droplets.wav', gen_water),
        ('rain_gentle.wav', gen_rain),
        ('zen_chime.wav', gen_chime),
        ('alarm_bell.wav', gen_bell)
    ]

    for fname, func in sound_gens:
        for folder in ['assets/sounds', 'sounds']:
            p = os.path.join(folder, fname)
            if not os.path.exists(p):
                try:
                    func(p)
                except Exception:
                    pass

ensure_sound_assets()

# -------------------------------------------------------------
# ASSET & IMAGE HELPERS (ZERO RED-BOX ERRORS)
# -------------------------------------------------------------
def resolve_photo_path(path):
    if not path or not isinstance(path, str):
        return ""
    path = path.strip()
    if not path:
        return ""
    if os.path.exists(path) and os.path.isfile(path):
        return os.path.abspath(path)
    fname = os.path.basename(path)
    for folder in ["assets", "assets/illustrations", "assets/sounds", PHOTOS_DIR, "medicine_photos", "profile_avatars"]:
        cand = os.path.join(folder, fname)
        if os.path.exists(cand) and os.path.isfile(cand):
            return os.path.abspath(cand)
    try:
        sdir = os.path.dirname(os.path.abspath(__file__))
        for folder in ["assets", "assets/illustrations", "assets/sounds", "medicine_photos", "profile_avatars"]:
            cand = os.path.join(sdir, folder, fname)
            if os.path.exists(cand) and os.path.isfile(cand):
                return os.path.abspath(cand)
    except Exception:
        pass
    return ""

def make_safe_image(path, width=74, height=74, fit="cover", fallback_icon=None, fallback_color=None):
    real_path = resolve_photo_path(path)
    if real_path and os.path.exists(real_path) and os.path.isfile(real_path):
        try:
            return ft.Image(src=real_path, width=width, height=height, fit=fit)
        except Exception:
            pass
    icon_name = fallback_icon or ft.Icons.MEDICATION
    icon_col = fallback_color or ft.Colors.TEAL_600
    icon_sz = int(min(width, height) * 0.55)
    return ft.Icon(icon_name, size=icon_sz, color=icon_col)

def ensure_sample_photos():
    try:
        from PIL import Image, ImageDraw
        for d in [PHOTOS_DIR, "assets", "assets/illustrations", "assets/sounds", "medicine_photos", "profile_avatars"]:
            os.makedirs(d, exist_ok=True)

        # Icon.png
        for folder in [PHOTOS_DIR, "assets", "."]:
            ic_p = os.path.join(folder, "icon.png")
            if not os.path.exists(ic_p):
                img_ic = Image.new("RGBA", (160, 160), color=(20, 80, 140, 255))
                d_ic = ImageDraw.Draw(img_ic)
                d_ic.ellipse([35, 35, 125, 125], fill=(255, 255, 255, 255))
                d_ic.rounded_rectangle([60, 50, 100, 110], radius=15, fill=(0, 240, 190, 255))
                img_ic.save(ic_p)

        # Onboarding Illustrations
        p_boy = "assets/illustrations/avatar_boy.png"
        if not os.path.exists(p_boy):
            im_boy = Image.new("RGBA", (200, 200), (0,0,0,0))
            d = ImageDraw.Draw(im_boy)
            d.ellipse([30, 30, 170, 170], fill=(230, 235, 245, 255))
            d.ellipse([65, 55, 135, 125], fill=(255, 224, 189, 255))
            d.pieslice([60, 45, 140, 95], 180, 360, fill=(139, 69, 19, 255))
            d.ellipse([80, 85, 90, 95], fill=(50, 50, 50, 255))
            d.ellipse([110, 85, 120, 95], fill=(50, 50, 50, 255))
            d.arc([85, 95, 115, 115], 0, 180, fill=(200, 50, 50, 255), width=3)
            d.pieslice([50, 125, 150, 220], 180, 360, fill=(33, 150, 243, 255))
            im_boy.save(p_boy)

        p_girl = "assets/illustrations/avatar_girl.png"
        if not os.path.exists(p_girl):
            im_girl = Image.new("RGBA", (200, 200), (0,0,0,0))
            d = ImageDraw.Draw(im_girl)
            d.ellipse([30, 30, 170, 170], fill=(250, 235, 240, 255))
            d.ellipse([65, 55, 135, 125], fill=(255, 224, 189, 255))
            d.pieslice([55, 40, 145, 110], 180, 360, fill=(160, 82, 45, 255))
            d.arc([60, 50, 140, 100], 180, 360, fill=(233, 30, 99, 255), width=6)
            d.ellipse([80, 85, 90, 95], fill=(50, 50, 50, 255))
            d.ellipse([110, 85, 120, 95], fill=(50, 50, 50, 255))
            d.arc([85, 95, 115, 115], 0, 180, fill=(200, 50, 50, 255), width=3)
            d.pieslice([50, 125, 150, 220], 180, 360, fill=(233, 30, 99, 255))
            im_girl.save(p_girl)

        p_weight = "assets/illustrations/illust_weight.png"
        if not os.path.exists(p_weight):
            im_w = Image.new("RGBA", (240, 320), (0,0,0,0))
            d = ImageDraw.Draw(im_w)
            d.rounded_rectangle([70, 270, 170, 305], radius=8, fill=(180, 190, 205, 255), outline=(100, 110, 130, 255), width=2)
            d.rectangle([105, 275, 135, 285], fill=(50, 50, 50, 255))
            d.rectangle([95, 180, 112, 275], fill=(255, 224, 189, 255))
            d.rectangle([128, 180, 145, 275], fill=(255, 224, 189, 255))
            d.rectangle([90, 140, 150, 185], fill=(33, 150, 243, 255))
            d.rectangle([85, 75, 155, 145], fill=(66, 165, 245, 255))
            d.ellipse([98, 25, 142, 69], fill=(255, 224, 189, 255))
            d.pieslice([96, 20, 144, 52], 180, 360, fill=(139, 69, 19, 255))
            im_w.save(p_weight)

        p_wake = "assets/illustrations/illust_wake.png"
        if not os.path.exists(p_wake):
            im_wk = Image.new("RGBA", (240, 320), (0,0,0,0))
            d = ImageDraw.Draw(im_wk)
            d.rounded_rectangle([40, 180, 200, 250], radius=6, fill=(200, 220, 245, 255))
            d.rectangle([45, 160, 90, 190], fill=(255, 255, 255, 255))
            d.rectangle([100, 120, 140, 185], fill=(33, 150, 243, 255))
            d.rectangle([102, 185, 138, 225], fill=(25, 118, 210, 255))
            d.rectangle([105, 225, 118, 290], fill=(255, 224, 189, 255))
            d.rectangle([122, 225, 135, 290], fill=(255, 224, 189, 255))
            d.ellipse([103, 65, 137, 105], fill=(255, 224, 189, 255))
            d.pieslice([101, 60, 139, 90], 180, 360, fill=(139, 69, 19, 255))
            d.line([(100, 130), (75, 75)], fill=(255, 224, 189, 255), width=10)
            d.line([(140, 130), (165, 75)], fill=(255, 224, 189, 255), width=10)
            im_wk.save(p_wake)

        p_sleep = "assets/illustrations/illust_sleep.png"
        if not os.path.exists(p_sleep):
            im_sl = Image.new("RGBA", (240, 320), (0,0,0,0))
            d = ImageDraw.Draw(im_sl)
            d.rounded_rectangle([70, 80, 170, 140], radius=15, fill=(225, 230, 240, 255))
            d.ellipse([85, 95, 135, 145], fill=(255, 224, 189, 255))
            d.pieslice([80, 88, 140, 125], 180, 360, fill=(139, 69, 19, 255))
            d.rectangle([90, 140, 145, 210], fill=(33, 150, 243, 255))
            d.rounded_rectangle([95, 205, 140, 275], radius=10, fill=(25, 118, 210, 255))
            d.text((160, 60), 'Z', fill=(33, 150, 243, 255))
            d.text((175, 45), 'z', fill=(33, 150, 243, 255))
            d.text((188, 35), 'z', fill=(33, 150, 243, 255))
            im_sl.save(p_sleep)

        # Standard preset pills & avatars
        presets = [
            (PHOTOS_DIR, "capsule_red.jpg", (239, 68, 68), "capsule"),
            (PHOTOS_DIR, "tablet_teal.jpg", (20, 184, 166), "tablet"),
            (PHOTOS_DIR, "syrup_bottle.jpg", (245, 158, 11), "syrup"),
            (PHOTOS_DIR, "drops_purple.jpg", (147, 51, 234), "drops"),
            ("medicine_photos", "capsule_red.jpg", (239, 68, 68), "capsule"),
            ("medicine_photos", "tablet_teal.jpg", (20, 184, 166), "tablet"),
            ("medicine_photos", "syrup_bottle.jpg", (245, 158, 11), "syrup"),
            ("medicine_photos", "drops_purple.jpg", (147, 51, 234), "drops"),
            (PHOTOS_DIR, "avatar_male.jpg", (13, 148, 136), "male"),
            (PHOTOS_DIR, "avatar_female.jpg", (225, 29, 72), "female"),
            (PHOTOS_DIR, "avatar_user.jpg", (59, 130, 246), "user"),
            ("profile_avatars", "avatar_male.jpg", (13, 148, 136), "male"),
            ("profile_avatars", "avatar_female.jpg", (225, 29, 72), "female"),
            ("profile_avatars", "avatar_user.jpg", (59, 130, 246), "user"),
        ]
        for folder, fname, col, kind in presets:
            fpath = os.path.join(folder, fname)
            if not os.path.exists(fpath):
                img = Image.new("RGB", (160, 160), color=(245, 248, 252))
                d = ImageDraw.Draw(img)
                if kind == "capsule":
                    d.rounded_rectangle([25, 60, 135, 100], radius=20, fill=col)
                    d.rounded_rectangle([80, 60, 135, 100], radius=20, fill=(255, 255, 255))
                    d.line([(80, 60), (80, 100)], fill=(203, 213, 225), width=2)
                elif kind == "tablet":
                    d.ellipse([30, 30, 130, 130], fill=col)
                    d.line([(45, 80), (115, 80)], fill=(255, 255, 255), width=2)
                elif kind == "syrup":
                    d.rounded_rectangle([45, 50, 115, 140], radius=10, fill=col)
                    d.rectangle([65, 30, 95, 50], fill=(217, 119, 6))
                elif kind == "drops":
                    d.rounded_rectangle([50, 60, 110, 135], radius=12, fill=col)
                    d.rectangle([65, 35, 95, 60], fill=(107, 33, 168))
                elif kind in ("male", "female", "user"):
                    d.ellipse([50, 25, 110, 85], fill=(255, 230, 200))
                    d.pieslice([20, 75, 140, 195], 180, 360, fill=col)
                img.save(fpath)
    except Exception:
        pass

ensure_sample_photos()

# -------------------------------------------------------------
# Application Localization (English)
# -------------------------------------------------------------
LANG = {"current": "en"}

TEXTS = {
    "hi": {
        "app_title": "HealthTrack",
        "home_tab": "Home",
        "meds_tab": "Medicines",
        "hist_tab": "History",
        "prof_tab": "Settings",
        "login": "Log In",
        "register": "Create Account",
        "next": "NEXT",
        "start": "START",
        "back": "Back"
    },
    "en": {
        "app_title": "HealthTrack",
        "home_tab": "Home",
        "meds_tab": "Medicines",
        "hist_tab": "History",
        "prof_tab": "Settings",
        "login": "Log In",
        "register": "Create Account",
        "next": "NEXT",
        "start": "START",
        "back": "Back"
    }
}

def t(key):
    lang_dict = TEXTS.get(LANG["current"], TEXTS["en"])
    return lang_dict.get(key, key)

def play_system_alert(alert_type=None):
    if not alert_type:
        alert_type = db_get_setting("reminder_sound", "water_droplets")
    def _run():
        play_ringtone_sound(alert_type)
    threading.Thread(target=_run, daemon=True).start()

def time_str_to_minutes(time_str):
    try:
        dt = datetime.datetime.strptime(time_str.strip().upper(), "%I:%M %p")
        return dt.hour * 60 + dt.minute
    except Exception:
        try:
            dt = datetime.datetime.strptime(time_str.strip(), "%H:%M")
            return dt.hour * 60 + dt.minute
        except Exception:
            return 360

def is_in_sleep_window(cur_min, wake_min, sleep_min):
    if sleep_min > wake_min:
        return cur_min >= sleep_min or cur_min < wake_min
    elif sleep_min < wake_min:
        return cur_min >= sleep_min and cur_min < wake_min
    else:
        return False

def calculate_water_schedule(gender, weight_kg, age, sleep_t="11:00 PM", wake_t="08:00 AM", cup_ml=203, height_cm=170.0):
    try:
        w = float(weight_kg)
    except Exception:
        w = 70.0
    try:
        a = int(age)
    except Exception:
        a = 28
    try:
        h = float(height_cm)
    except Exception:
        h = 170.0

    # Scientific hydration: ~29ml per kg body weight (e.g. 70kg -> ~2030 ml)
    base_ml = w * 29.0
    if h > 175: base_ml += 100
    elif h < 160: base_ml -= 100

    if gender and str(gender).strip().lower() == "male":
        base_ml *= 1.0
    else:
        base_ml *= 0.95

    target_liters = max(1.5, min(4.5, round(base_ml / 1000.0, 2)))
    target_ml = int(target_liters * 1000)

    w_min = time_str_to_minutes(wake_t)
    s_min = time_str_to_minutes(sleep_t)
    if s_min > w_min:
        active_hours = (s_min - w_min) / 60.0
    else:
        active_hours = ((1440 - w_min) + s_min) / 60.0
    active_hours = max(8.0, min(18.0, active_hours))

    cup_ml = max(100, int(cup_ml or 203))
    total_target_glasses = max(6, round(target_ml / cup_ml))
    interval_min = max(45, round((active_hours * 60.0) / max(total_target_glasses, 1)))

    return target_liters, total_target_glasses, interval_min, w_min, s_min

# -------------------------------------------------------------
# DATABASE ENGINE (SQLite)
# -------------------------------------------------------------
def init_database():
    with sqlite3.connect(DB_NAME, timeout=15) as conn:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE,
                phone TEXT UNIQUE,
                gender TEXT DEFAULT 'Male',
                weight_kg REAL DEFAULT 70.0,
                age INTEGER DEFAULT 28,
                default_sleep_time TEXT DEFAULT '11:00 PM',
                default_wake_time TEXT DEFAULT '08:00 AM',
                daily_water_liters REAL DEFAULT 2.03,
                water_cup_ml INTEGER DEFAULT 203,
                streak_days INTEGER DEFAULT 1,
                password_hash TEXT NOT NULL,
                has_rated INTEGER DEFAULT 0,
                height_cm REAL DEFAULT 170.0,
                profile_photo_path TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS water_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                log_date DATE NOT NULL,
                glasses_count INTEGER DEFAULT 0,
                drank_liters REAL DEFAULT 0.0,
                last_drank_epoch REAL DEFAULT 0.0,
                FOREIGN KEY (user_id) REFERENCES accounts(id),
                UNIQUE(user_id, log_date)
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS medicines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                med_name TEXT NOT NULL,
                photo_path TEXT,
                morning_slot INTEGER DEFAULT 0,
                morning_time TEXT DEFAULT '08:00 AM',
                afternoon_slot INTEGER DEFAULT 0,
                afternoon_time TEXT DEFAULT '01:30 PM',
                evening_slot INTEGER DEFAULT 0,
                evening_time TEXT DEFAULT '06:00 PM',
                night_slot INTEGER DEFAULT 0,
                night_time TEXT DEFAULT '09:00 PM',
                instructions TEXT,
                FOREIGN KEY (user_id) REFERENCES accounts(id)
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS medicine_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                log_date DATE NOT NULL,
                med_id INTEGER NOT NULL,
                slot TEXT NOT NULL,
                taken_status INTEGER DEFAULT 1,
                taken_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, log_date, med_id, slot)
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                val TEXT
            )
        """)
        conn.commit()

        # Set default ringtone if unset
        cur.execute("SELECT val FROM app_settings WHERE key = 'reminder_sound'")
        if not cur.fetchone():
            cur.execute("INSERT INTO app_settings (key, val) VALUES ('reminder_sound', 'water_droplets')")
            conn.commit()

def db_get_setting(key, default_val=None):
    with sqlite3.connect(DB_NAME, timeout=15) as conn:
        cur = conn.cursor()
        cur.execute("SELECT val FROM app_settings WHERE key = ?", (key,))
        row = cur.fetchone()
        return row[0] if row else default_val

def db_set_setting(key, val):
    with sqlite3.connect(DB_NAME, timeout=15) as conn:
        cur = conn.cursor()
        cur.execute("INSERT OR REPLACE INTO app_settings (key, val) VALUES (?, ?)", (key, str(val)))
        conn.commit()

def db_set_active_session(user_id):
    db_set_setting("active_user_id", str(user_id))

def db_get_active_session():
    uid = db_get_setting("active_user_id", None)
    return int(uid) if uid and uid.isdigit() else None

def db_clear_active_session():
    with sqlite3.connect(DB_NAME, timeout=15) as conn:
        conn.execute("DELETE FROM app_settings WHERE key = 'active_user_id'")
        conn.commit()

def db_get_user_by_id(user_id):
    if not user_id: return None
    with sqlite3.connect(DB_NAME, timeout=15) as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM accounts WHERE id = ?", (int(user_id),))
        return cur.fetchone()

def db_update_cup_size(user_id, cup_ml):
    if not user_id: return
    with sqlite3.connect(DB_NAME, timeout=15) as conn:
        conn.execute("UPDATE accounts SET water_cup_ml = ? WHERE id = ?", (int(cup_ml), int(user_id)))
        conn.commit()

def db_mark_rating_shown(user_id):
    if not user_id: return
    with sqlite3.connect(DB_NAME, timeout=15) as conn:
        conn.execute("UPDATE accounts SET has_rated = 1 WHERE id = ?", (int(user_id),))
        conn.commit()

def db_register_simple(user, pw="WaterPass123!", email="", phone="", gender='Male', weight=70.0, age=28, wake_t="08:00 AM", sleep_t="11:00 PM"):
    u_clean = (user or "User").strip()
    e_clean = email.strip().lower() if email else ""
    p_clean = re.sub(r'[^0-9]', '', phone or "")

    target_l, _, _, _, _ = calculate_water_schedule(gender, weight, age, sleep_t, wake_t)
    pw_hash = hash_password(pw or "WaterPass123!")

    with sqlite3.connect(DB_NAME, timeout=15) as conn:
        cur = conn.cursor()
        cur.execute("SELECT id FROM accounts WHERE username = ? OR (email != '' AND email = ?) OR (phone != '' AND phone = ?)", (u_clean, e_clean, p_clean))
        existing = cur.fetchone()
        if existing:
            uid = existing[0]
            cur.execute("""
                UPDATE accounts SET gender = ?, weight_kg = ?, default_wake_time = ?, default_sleep_time = ?, daily_water_liters = ?
                WHERE id = ?
            """, (gender, float(weight), wake_t, sleep_t, target_l, uid))
            conn.commit()
            return True, "Account updated successfully!", uid

        cur.execute("""
            INSERT INTO accounts (username, email, phone, password_hash, gender, weight_kg, age, default_sleep_time, default_wake_time, daily_water_liters, water_cup_ml)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (u_clean, e_clean, p_clean, pw_hash, gender, float(weight), int(age), sleep_t, wake_t, target_l, 203))
        conn.commit()
        return True, "Account created successfully!", cur.lastrowid

def db_authenticate(ident, pw):
    ident_clean = ident.strip()
    phone_clean = re.sub(r'[^0-9]', '', ident_clean)
    with sqlite3.connect(DB_NAME, timeout=15) as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT * FROM accounts 
            WHERE username = ? OR email = ? OR (phone != '' AND phone = ?)
        """, (ident_clean, ident_clean.lower(), phone_clean))
        row = cur.fetchone()
        if row and verify_password(pw, row[12]):
            return row
        return None

def db_update_full_profile(user_id, username, email, phone, gender, weight, height, age, sleep_t, wake_t, cup_ml, photo_path=None, custom_target=None):
    if not user_id: return False, 2.03
    with sqlite3.connect(DB_NAME, timeout=15) as conn:
        cur = conn.cursor()
        if custom_target is not None and custom_target > 0:
            target_liters = float(custom_target)
        else:
            target_liters, _, _, _, _ = calculate_water_schedule(gender, weight, age, sleep_t, wake_t, cup_ml, height)

        if photo_path is not None:
            cur.execute("""
                UPDATE accounts SET
                    username = ?, email = ?, phone = ?, gender = ?, weight_kg = ?,
                    height_cm = ?, age = ?, default_sleep_time = ?, default_wake_time = ?,
                    daily_water_liters = ?, water_cup_ml = ?, profile_photo_path = ?
                WHERE id = ?
            """, (username, email, phone, gender, float(weight), float(height), int(age), sleep_t, wake_t, target_liters, int(cup_ml), photo_path, int(user_id)))
        else:
            cur.execute("""
                UPDATE accounts SET
                    username = ?, email = ?, phone = ?, gender = ?, weight_kg = ?,
                    height_cm = ?, age = ?, default_sleep_time = ?, default_wake_time = ?,
                    daily_water_liters = ?, water_cup_ml = ?
                WHERE id = ?
            """, (username, email, phone, gender, float(weight), float(height), int(age), sleep_t, wake_t, target_liters, int(cup_ml), int(user_id)))
        conn.commit()
        return True, target_liters

def db_get_today_water(user_id, date_str):
    if not user_id: return (0, 0.0, 0.0)
    with sqlite3.connect(DB_NAME, timeout=15) as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT glasses_count, drank_liters, last_drank_epoch FROM water_logs
            WHERE user_id = ? AND log_date = ?
        """, (int(user_id), date_str))
        row = cur.fetchone()
        return row if row else (0, 0.0, 0.0)

def db_save_water_intake(user_id, date_str, glasses_count, drank_liters, epoch_time):
    if not user_id: return 1
    with sqlite3.connect(DB_NAME, timeout=15) as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO water_logs (user_id, log_date, glasses_count, drank_liters, last_drank_epoch)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id, log_date) DO UPDATE SET
                glasses_count = excluded.glasses_count,
                drank_liters = excluded.drank_liters,
                last_drank_epoch = excluded.last_drank_epoch
        """, (int(user_id), date_str, int(glasses_count), float(drank_liters), float(epoch_time)))

        cur.execute("SELECT streak_days FROM accounts WHERE id = ?", (int(user_id),))
        row = cur.fetchone()
        streak = row[0] if row else 1
        conn.commit()
        return streak

def db_reset_today_water(user_id, date_str):
    if not user_id: return
    with sqlite3.connect(DB_NAME, timeout=15) as conn:
        cur = conn.cursor()
        cur.execute("""
            UPDATE water_logs SET glasses_count = 0, drank_liters = 0.0, last_drank_epoch = 0.0
            WHERE user_id = ? AND log_date = ?
        """, (int(user_id), date_str))
        conn.commit()

def db_undo_last_glass(user_id, date_str, cup_ml):
    if not user_id: return 0, 0.0
    with sqlite3.connect(DB_NAME, timeout=15) as conn:
        cur = conn.cursor()
        cur.execute("SELECT glasses_count FROM water_logs WHERE user_id = ? AND log_date = ?", (int(user_id), date_str))
        row = cur.fetchone()
        if row and row[0] > 0:
            new_g = row[0] - 1
            new_l = round((new_g * cup_ml) / 1000.0, 2)
            cur.execute("""
                UPDATE water_logs SET glasses_count = ?, drank_liters = ?, last_drank_epoch = ?
                WHERE user_id = ? AND log_date = ?
            """, (new_g, new_l, 0.0 if new_g == 0 else time.time(), int(user_id), date_str))
            conn.commit()
            return new_g, new_l
        return 0, 0.0

def db_get_past_water_logs(user_id, limit=30):
    if not user_id: return []
    with sqlite3.connect(DB_NAME, timeout=15) as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT log_date, glasses_count, drank_liters
            FROM water_logs
            WHERE user_id = ?
            ORDER BY log_date DESC
            LIMIT ?
        """, (int(user_id), limit))
        return cur.fetchall()

def db_add_medicine(user_id, name, photo_p, m_slot, m_time, a_slot, a_time, e_slot, e_time, n_slot, n_time, instructions):
    if not user_id: return None
    with sqlite3.connect(DB_NAME, timeout=15) as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO medicines (
                user_id, med_name, photo_path, 
                morning_slot, morning_time, 
                afternoon_slot, afternoon_time, 
                evening_slot, evening_time, 
                night_slot, night_time, 
                instructions
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            int(user_id), name, photo_p,
            int(m_slot), m_time,
            int(a_slot), a_time,
            int(e_slot), e_time,
            int(n_slot), n_time,
            instructions
        ))
        conn.commit()
        return cur.lastrowid

def db_get_medicines(user_id):
    if not user_id: return []
    with sqlite3.connect(DB_NAME, timeout=15) as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT id, user_id, med_name, photo_path, 
                   morning_slot, morning_time, 
                   afternoon_slot, afternoon_time, 
                   evening_slot, evening_time, 
                   night_slot, night_time, 
                   instructions 
            FROM medicines 
            WHERE user_id = ? 
            ORDER BY id ASC
        """, (int(user_id),))
        return cur.fetchall()

def db_delete_medicine(med_id, user_id):
    if not user_id: return
    with sqlite3.connect(DB_NAME, timeout=15) as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM medicines WHERE id = ? AND user_id = ?", (int(med_id), int(user_id)))
        cur.execute("DELETE FROM medicine_logs WHERE med_id = ? AND user_id = ?", (int(med_id), int(user_id)))
        conn.commit()

def db_mark_medicine_taken(user_id, date_str, med_id, slot):
    if not user_id: return
    with sqlite3.connect(DB_NAME, timeout=15) as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO medicine_logs (user_id, log_date, med_id, slot, taken_status)
            VALUES (?, ?, ?, ?, 1)
            ON CONFLICT(user_id, log_date, med_id, slot) DO UPDATE SET taken_status = 1
        """, (int(user_id), date_str, int(med_id), slot))
        conn.commit()

def db_get_today_taken_meds(user_id, date_str):
    if not user_id: return set()
    with sqlite3.connect(DB_NAME, timeout=15) as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT med_id, slot FROM medicine_logs 
            WHERE user_id = ? AND log_date = ? AND taken_status = 1
        """, (int(user_id), date_str))
        rows = cur.fetchall()
        return {(r[0], r[1]) for r in rows}

# -------------------------------------------------------------
# FLET MAIN APPLICATION
# -------------------------------------------------------------
def main(page: ft.Page):
    init_database()
    page.title = "HealthTrack"
    
    # Configure App / Window Icon
    app_icon_file = resolve_photo_path("icon.png") or resolve_photo_path("assets/icon.png") or "icon.png"
    try:
        if hasattr(page, "window") and hasattr(page.window, "icon"):
            page.window.icon = app_icon_file
    except Exception:
        pass
    try:
        page.window_icon = app_icon_file
    except Exception:
        pass

    saved_theme = db_get_setting("theme_mode", "LIGHT")
    page.theme_mode = ft.ThemeMode.DARK if saved_theme == "DARK" else ft.ThemeMode.LIGHT
    try:
        page.theme = ft.Theme(color_scheme_seed=ft.Colors.BLUE_700)
    except Exception:
        pass
    try:
        page.dark_theme = ft.Theme(color_scheme_seed=ft.Colors.BLUE_700)
    except Exception:
        pass

    try:
        page.scroll = ft.ScrollMode.AUTO
    except Exception:
        page.scroll = "auto"
    page.padding = 0
    page.assets_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")

    def make_padding(horizontal=0, vertical=0, left=0, top=0, right=0, bottom=0):
        l = left or horizontal
        r = right or horizontal
        t = top or vertical
        b = bottom or vertical
        try:
            if hasattr(ft, "Padding"):
                return ft.Padding(l, t, r, b)
        except Exception:
            pass
        return max(horizontal, vertical, left, top, right, bottom)

    def make_border(width=1, color=None):
        try:
            if hasattr(ft, "Border") and hasattr(ft.Border, "all"):
                return ft.Border.all(width, color)
        except Exception:
            pass
        return None

    def safe_open_dialog(dlg):
        dlg.open = True
        try:
            if hasattr(page, "open"):
                page.open(dlg)
        except Exception:
            pass
        try:
            page.dialog = dlg
        except Exception:
            pass
        try:
            if dlg not in page.overlay:
                page.overlay.append(dlg)
        except Exception:
            pass
        try:
            page.update()
        except Exception:
            pass

    def safe_close_dialog(dlg):
        dlg.open = False
        try:
            if hasattr(page, "close"):
                page.close(dlg)
        except Exception:
            pass
        try:
            if dlg in page.overlay:
                page.overlay.remove(dlg)
        except Exception:
            pass
        try:
            page.update()
        except Exception:
            pass

    user_session = {
        "id": None, "username": "Gaurav", "email": "", "phone": "",
        "gender": "Male", "weight": 70.0, "height": 170.0, "age": 28,
        "sleep_t": "11:00 PM", "wake_t": "08:00 AM",
        "water_target": 2.03, "water_cup_ml": 203,
        "streak": 5, "rating_shown": 0, "photo_path": ""
    }

    today_water_glasses = [0]
    last_drink_time = [0.0]
    snooze_delay_until = [0.0]
    water_alarm_rung = [False]
    active_ticker_token = [0]
    timer_cancel_event = threading.Event()
    active_tab = [0]
    is_adding_med_inline = [False]
    expanded_med_id = [None]
    active_viewing_med = [None]
    active_setting_view = [None]
    profile_photo_preview_ctrl = [None]
    file_picker = None
    med_picker_selected_path = [""]
    med_picker_preview_container = [None]

    def on_file_picked_result(e: ft.FilePickerResultEvent):
        if e.files and len(e.files) > 0:
            chosen = e.files[0]
            try:
                dest_dir = get_photos_dir()
                ext = os.path.splitext(chosen.name)[1] or ".jpg"
                dest_name = f"upload_{int(time.time())}{ext}"
                dest_path = os.path.join(dest_dir, dest_name)
                if hasattr(chosen, "path") and chosen.path:
                    shutil.copyfile(chosen.path, dest_path)
                elif hasattr(chosen, "bytes") and chosen.bytes:
                    with open(dest_path, "wb") as f_out:
                        f_out.write(chosen.bytes)

                med_picker_selected_path[0] = dest_path
                if med_picker_preview_container[0]:
                    med_picker_preview_container[0].content = make_safe_image(dest_path, width=80, height=80, fallback_icon=ft.Icons.MEDICATION)
                    med_picker_preview_container[0].update()

                if profile_photo_preview_ctrl[0]:
                    user_session["photo_path"] = dest_path
                    profile_photo_preview_ctrl[0].content = make_safe_image(dest_path, width=80, height=80, fallback_icon=ft.Icons.PERSON)
                    profile_photo_preview_ctrl[0].update()
            except Exception as err:
                print("File copy error:", err)

    def trigger_universal_file_picker(is_profile=False):
        chosen_path = None
        if os.name == "nt":
            try:
                ps_script = (
                    "[System.Reflection.Assembly]::LoadWithPartialName('System.windows.forms') | Out-Null; "
                    "$dlg = New-Object System.Windows.Forms.OpenFileDialog; "
                    "$dlg.Filter = 'Image Files (*.jpg;*.jpeg;*.png;*.webp)|*.jpg;*.jpeg;*.png;*.webp|All Files (*.*)|*.*'; "
                    "$dlg.Title = 'Select Photo'; "
                    "if ($dlg.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) { Write-Output $dlg.FileName }"
                )
                res = subprocess.run(
                    ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
                    capture_output=True, text=True, timeout=60
                )
                out = res.stdout.strip()
                if out and os.path.exists(out):
                    chosen_path = out
            except Exception:
                pass

        if not chosen_path:
            try:
                import tkinter as tk
                from tkinter import filedialog
                root = tk.Tk()
                root.withdraw()
                root.wm_attributes("-topmost", 1)
                fpath = filedialog.askopenfilename(
                    title="Select Photo",
                    filetypes=[("Image files", "*.jpg;*.jpeg;*.png;*.webp;*.bmp")]
                )
                root.destroy()
                if fpath and os.path.exists(fpath):
                    chosen_path = fpath
            except Exception:
                pass

        if chosen_path and os.path.exists(chosen_path):
            try:
                dest_dir = get_photos_dir()
                ext = os.path.splitext(chosen_path)[1] or ".jpg"
                dest_name = f"photo_{int(time.time())}{ext}"
                dest_path = os.path.join(dest_dir, dest_name)
                shutil.copyfile(chosen_path, dest_path)

                if is_profile:
                    user_session["photo_path"] = dest_path
                    if user_session.get("id"):
                        with sqlite3.connect(DB_NAME, timeout=15) as conn:
                            conn.execute("UPDATE accounts SET profile_photo_path = ? WHERE id = ?", (dest_path, int(user_session["id"])))
                            conn.commit()
                    show_profile_settings_screen()
                else:
                    med_picker_selected_path[0] = dest_path
                    if med_picker_preview_container[0]:
                        med_picker_preview_container[0].content = make_safe_image(dest_path, width=75, height=75)
                        med_picker_preview_container[0].update()
                return
            except Exception as e_copy:
                print("Error copying photo:", e_copy)

        try:
            nonlocal file_picker
            if not file_picker and hasattr(ft, "FilePicker"):
                file_picker = ft.FilePicker(on_result=on_file_picked_result)
                page.overlay.append(file_picker)
                page.update()
            if file_picker:
                pick_res = file_picker.pick_files(allow_multiple=False, allowed_extensions=["jpg", "jpeg", "png", "webp"])
                if asyncio.iscoroutine(pick_res):
                    if hasattr(page, "run_task"):
                        page.run_task(lambda: pick_res)
                    else:
                        try:
                            import asyncio
                            asyncio.create_task(pick_res)
                        except Exception:
                            pass
        except Exception as ex:
            print("FilePicker error:", ex)

    def toggle_theme_action(e=None):
        if page.theme_mode == ft.ThemeMode.DARK:
            page.theme_mode = ft.ThemeMode.LIGHT
            page.bgcolor = ft.Colors.WHITE
            db_set_setting("theme_mode", "LIGHT")
        else:
            page.theme_mode = ft.ThemeMode.DARK
            page.bgcolor = ft.Colors.GREY_900
            db_set_setting("theme_mode", "DARK")
        
        # Refresh current screen to instantly update all backgrounds and font colors
        if active_tab[0] == 0: show_dashboard()
        elif active_tab[0] == 1: show_medicines_screen()
        elif active_tab[0] == 2: show_history_screen()
        elif active_tab[0] == 3: show_profile_settings_screen()
        else: page.update()

    def toggle_language_action(e=None):
        LANG["current"] = "en" if LANG["current"] == "hi" else "hi"
        if user_session.get("id"):
            show_dashboard()
        else:
            show_login_screen()

    def user_logout_action(e=None):
        timer_cancel_event.set()
        db_clear_active_session()
        user_session["id"] = None
        show_login_screen()

    # -------------------------------------------------------------
    # TOP BLUE APP BAR WITH SCREEN TABS (EXACTLY AS SCREENSHOTS)
    # -------------------------------------------------------------
    def get_top_app_bar(selected_idx=0):
        is_dark = (page.theme_mode == ft.ThemeMode.DARK)
        bar_bg = ft.Colors.BLUE_700 if not is_dark else ft.Colors.GREY_900

        def make_tab_btn(idx, icon_name, label):
            is_active = (idx == selected_idx)
            indicator_color = ft.Colors.WHITE if is_active else ft.Colors.TRANSPARENT
            text_color = ft.Colors.WHITE if is_active else ft.Colors.BLUE_100

            def on_tab_click(e):
                if idx == 0: show_dashboard()
                elif idx == 1: show_medicines_screen()
                elif idx == 2: show_history_screen()
                elif idx == 3: show_profile_settings_screen()

            return ft.Container(
                content=ft.Column([
                    ft.Row([
                        ft.Icon(icon_name, size=18, color=text_color),
                        ft.Text(label, size=14, weight=ft.FontWeight.BOLD if is_active else ft.FontWeight.NORMAL, color=text_color)
                    ], alignment=ft.MainAxisAlignment.CENTER, spacing=6),
                    ft.Container(height=3, width=70, bgcolor=indicator_color, border_radius=2)
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN, horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=4),
                padding=make_padding(horizontal=10, top=10, bottom=4),
                on_click=on_tab_click
            )

        tabs_row = ft.Row([
            make_tab_btn(0, ft.Icons.WATER_DROP_ROUNDED, "Home"),
            make_tab_btn(1, ft.Icons.MEDICATION_ROUNDED, "Meds"),
            make_tab_btn(2, ft.Icons.HISTORY_ROUNDED, "History"),
            make_tab_btn(3, ft.Icons.SETTINGS_ROUNDED, "Settings"),
        ], alignment=ft.MainAxisAlignment.SPACE_AROUND)

        return ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Row([
                        ft.Icon(ft.Icons.WATER_DROP_ROUNDED, color=ft.Colors.WHITE, size=20),
                        ft.Text("HealthTrack", size=18, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE)
                    ], spacing=6),
                    ft.IconButton(
                        icon=ft.Icons.LIGHT_MODE if page.theme_mode == ft.ThemeMode.DARK else ft.Icons.DARK_MODE,
                        icon_color=ft.Colors.WHITE,
                        on_click=toggle_theme_action
                    )
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                tabs_row
            ], spacing=2),
            bgcolor=bar_bg,
            padding=make_padding(left=14, right=14, top=8, bottom=0)
        )

    # -------------------------------------------------------------
    # RINGTONE PICKER MODAL (WATER, RAIN, CHIME, BELL)
    # -------------------------------------------------------------
    def show_ringtone_picker(on_selected_callback=None):
        cur_sound = db_get_setting("reminder_sound", "water_droplets")
        sound_status_label = ft.Text("", size=12, color=ft.Colors.CYAN_700, weight=ft.FontWeight.BOLD)

        def play_preview(sid):
            play_ringtone_sound(sid)
            sound_status_label.value = f"▶️ Playing: {sid}..."
            page.update()

        options_controls = []
        for opt in RINGTONE_OPTIONS:
            sid = opt["id"]
            is_active = (sid == cur_sound)

            def make_select_handler(target_id=sid):
                def handler(e):
                    db_set_setting("reminder_sound", target_id)
                    play_ringtone_sound(target_id)
                    safe_close_dialog(ringtone_dlg)
                    if on_selected_callback:
                        on_selected_callback()
                    else:
                        show_profile_settings_screen()
                return handler

            def make_preview_handler(target_id=sid):
                def handler(e):
                    play_preview(target_id)
                return handler

            card = ft.Container(
                content=ft.Row([
                    ft.Text(opt["icon"], size=24),
                    ft.Column([
                        ft.Text(opt["name"], size=13, weight=ft.FontWeight.BOLD if is_active else ft.FontWeight.NORMAL),
                        ft.Text(opt["desc"], size=10, color=ft.Colors.GREY_500)
                    ], expand=True, spacing=1),
                    ft.IconButton(icon=ft.Icons.PLAY_CIRCLE_FILL, icon_color=ft.Colors.BLUE_700, tooltip="Preview sound", on_click=make_preview_handler()),
                    ft.Button(
                        content=ft.Text("✓ Selected" if is_active else "Select", size=11, color=ft.Colors.WHITE if is_active else None),
                        bgcolor=ft.Colors.GREEN_700 if is_active else None,
                        on_click=make_select_handler()
                    )
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                padding=8, border_radius=10, bgcolor=ft.Colors.BLUE_50 if is_active else None,
                border=make_border(1.5 if is_active else 1, ft.Colors.BLUE_500 if is_active else ft.Colors.GREY_300)
            )
            options_controls.append(card)

        ringtone_dlg = ft.AlertDialog(
            title=ft.Row([
                ft.Icon(ft.Icons.MUSIC_NOTE_ROUNDED, color=ft.Colors.BLUE_700),
                ft.Text("Select Alarm Sound", size=16, weight=ft.FontWeight.BOLD)
            ], spacing=6),
            content=ft.Container(
                content=ft.Column([
                    ft.Text("Select your alarm ringtone for water and medication reminders. Tap preview to listen:", size=12, color=ft.Colors.GREY_600),
                    sound_status_label,
                    ft.Column(options_controls, spacing=6, scroll=ft.ScrollMode.AUTO)
                ], spacing=8, tight=True),
                width=360, height=380
            ),
            actions=[
                ft.TextButton("Close", on_click=lambda _: safe_close_dialog(ringtone_dlg))
            ]
        )
        safe_open_dialog(ringtone_dlg)

    # -------------------------------------------------------------
    # -------------------------------------------------------------
    # PERMISSIONS CONSENT SCREEN (FIRST LAUNCH & SETTINGS REVIEW)
    # -------------------------------------------------------------
    def show_permissions_screen(is_review=False):
        timer_cancel_event.set()
        page.clean()
        page.navigation_bar = None

        is_dark = (page.theme_mode == ft.ThemeMode.DARK)
        page.bgcolor = ft.Colors.GREY_900 if is_dark else ft.Colors.WHITE
        txt_main = ft.Colors.WHITE if is_dark else ft.Colors.BLACK
        card_bg = ft.Colors.GREY_800 if is_dark else ft.Colors.WHITE
        border_c = ft.Colors.GREY_800 if is_dark else ft.Colors.GREY_200

        def make_perm_tile(icon_name, icon_c, bg_c, title, desc, badge_text):
            return ft.Container(
                content=ft.Row([
                    ft.Container(
                        content=ft.Icon(icon_name, size=24, color=icon_c),
                        bgcolor=bg_c, border_radius=12, width=48, height=48,
                        alignment=ft.Alignment(0, 0)
                    ),
                    ft.Column([
                        ft.Row([
                            ft.Text(title, size=14, weight=ft.FontWeight.BOLD, color=txt_main),
                            ft.Container(
                                content=ft.Text(badge_text, size=10, weight=ft.FontWeight.BOLD, color=ft.Colors.GREEN_800),
                                bgcolor=ft.Colors.GREEN_100, border_radius=6, padding=make_padding(horizontal=6, vertical=2)
                            )
                        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                        ft.Text(desc, size=11, color=ft.Colors.GREY_600)
                    ], expand=True, spacing=2)
                ], spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                padding=12, bgcolor=card_bg, border_radius=14, border=make_border(1, border_c)
            )

        perm_list = ft.Column([
            make_perm_tile(
                ft.Icons.NOTIFICATIONS_ACTIVE_ROUNDED, ft.Colors.BLUE_700, ft.Colors.BLUE_50,
                "Notifications & Alarms",
                "Displays water intake alerts and countdowns on your screen even when phone is locked.",
                "Essential"
            ),
            make_perm_tile(
                ft.Icons.CAMERA_ALT_ROUNDED, ft.Colors.TEAL_700, ft.Colors.TEAL_50,
                "Camera & Photo Storage",
                "Allows taking pictures of prescription medicines, pill strips, and avatar photos.",
                "Allowed"
            ),
            make_perm_tile(
                ft.Icons.VOLUME_UP_ROUNDED, ft.Colors.ORANGE_700, ft.Colors.ORANGE_50,
                "Sound & Ringtone Alerts",
                "Plays realistic water droplets and gentle rain alarm tones through your speaker.",
                "Enabled"
            ),
            make_perm_tile(
                ft.Icons.BATTERY_CHARGING_FULL_ROUNDED, ft.Colors.GREEN_700, ft.Colors.GREEN_50,
                "Background WakeLock",
                "Prevents Android from pausing reminder timers when your screen is off.",
                "Active"
            ),
        ], spacing=10)

        def on_grant_clicked(e):
            # Request native Android runtime permissions
            request_runtime_permissions()
            db_set_setting("permissions_granted", "1")
            play_ringtone_sound("water_droplets")

            if is_review:
                show_profile_settings_screen()
            else:
                active_uid = db_get_active_session()
                if active_uid:
                    show_dashboard()
                else:
                    show_onboarding_flow(step=1)

        def on_skip_clicked(e):
            db_set_setting("permissions_granted", "1")
            if is_review:
                show_profile_settings_screen()
            else:
                active_uid = db_get_active_session()
                if active_uid:
                    show_dashboard()
                else:
                    show_onboarding_flow(step=1)

        page.add(
            ft.SafeArea(
                ft.Container(
                    content=ft.Column([
                        ft.Container(height=10),
                        ft.Container(
                            content=ft.Column([
                                make_safe_image("icon.png", width=75, height=75, fit="contain", fallback_icon=ft.Icons.SHIELD_ROUNDED, fallback_color=ft.Colors.BLUE_700),
                                ft.Text("App Permissions Required", size=22, weight=ft.FontWeight.BOLD, color=txt_main),
                                ft.Text(
                                    "HealthTrack needs the following permissions to ensure water reminders ring on time and prescription photos work properly:",
                                    size=12, color=ft.Colors.GREY_600, text_align=ft.TextAlign.CENTER
                                ),
                            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=6),
                            alignment=ft.Alignment(0, 0), padding=make_padding(bottom=10)
                        ),
                        perm_list,
                        ft.Container(height=15),
                        ft.Button(
                            content=ft.Row([
                                ft.Icon(ft.Icons.CHECK_CIRCLE, size=18, color=ft.Colors.WHITE),
                                ft.Text("Allow All Permissions & Continue", size=15, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE)
                            ], alignment=ft.MainAxisAlignment.CENTER),
                            bgcolor=ft.Colors.BLUE_700, width=400, height=50,
                            on_click=on_grant_clicked
                        ),
                        ft.TextButton(
                            content=ft.Text("Skip / Continue with Default Settings", size=12, color=ft.Colors.GREY_500),
                            on_click=on_skip_clicked
                        )
                    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=8),
                    padding=16, expand=True
                )
            )
        )

        # ONBOARDING FLOW (SCREENSHOTS 05-1 TO 05-6)
    # -------------------------------------------------------------
    onboarding_state = {
        "gender": "Male",
        "weight_kg": 70,
        "weight_unit": "kg",
        "wake_hour": 8,
        "wake_minute": 0,
        "bed_hour": 23,
        "bed_minute": 0
    }

    def show_onboarding_flow(step=1):
        active_ticker_token[0] += 1
        timer_cancel_event.set()
        page.clean()
        page.navigation_bar = None

        is_dark = (page.theme_mode == ft.ThemeMode.DARK)
        txt_main = ft.Colors.WHITE if is_dark else ft.Colors.BLACK
        card_bg = ft.Colors.GREY_900 if is_dark else ft.Colors.WHITE
        border_c = ft.Colors.GREY_800 if is_dark else ft.Colors.BLUE_GREY_100

        # Formatted strings
        wake_str = f"{onboarding_state['wake_hour']:02d}:{onboarding_state['wake_minute']:02d} {'AM' if onboarding_state['wake_hour'] < 12 else 'PM'}"
        bed_str = f"{onboarding_state['bed_hour']:02d}:{onboarding_state['bed_minute']:02d} {'AM' if onboarding_state['bed_hour'] < 12 else 'PM'}"

        # Top stepper indicator (matching 05-1, 05-2, 05-3, 05-4)
        def make_step_chip(num, icon_name, label, is_active, is_completed):
            bg = ft.Colors.BLUE_700 if is_active else (ft.Colors.BLUE_100 if is_completed else ft.Colors.GREY_200)
            fg = ft.Colors.WHITE if is_active else (ft.Colors.BLUE_900 if is_completed else ft.Colors.GREY_500)
            return ft.Container(
                content=ft.Column([
                    ft.Icon(icon_name, size=18, color=fg),
                    ft.Text(label, size=10, weight=ft.FontWeight.BOLD if is_active else ft.FontWeight.NORMAL, color=fg)
                ], alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=2),
                width=65, height=52, border_radius=12, bgcolor=bg
            )

        step_bar = ft.Container(
            content=ft.Row([
                make_step_chip(1, ft.Icons.WC, onboarding_state["gender"], step == 1, step > 1),
                ft.Text("---", color=ft.Colors.GREY_400),
                make_step_chip(2, ft.Icons.MONITOR_WEIGHT, f"{onboarding_state['weight_kg']} kg", step == 2, step > 2),
                ft.Text("---", color=ft.Colors.GREY_400),
                make_step_chip(3, ft.Icons.ALARM, f"{onboarding_state['wake_hour']:02d}:00", step == 3, step > 3),
                ft.Text("---", color=ft.Colors.GREY_400),
                make_step_chip(4, ft.Icons.BEDTIME, f"{onboarding_state['bed_hour']:02d}:00", step == 4, step > 4),
            ], alignment=ft.MainAxisAlignment.CENTER),
            padding=make_padding(top=10, bottom=10)
        )

        body_content = []

        # ---------------- STEP 1: GENDER ----------------
        if step == 1:
            title_text = ft.Text("Your Gender", size=22, weight=ft.FontWeight.BOLD, color=txt_main)

            def select_gender(g):
                onboarding_state["gender"] = g
                show_onboarding_flow(step=1)

            is_m = (onboarding_state["gender"] == "Male")
            is_f = (onboarding_state["gender"] == "Female")

            boy_card = ft.Container(
                content=ft.Column([
                    make_safe_image("assets/illustrations/avatar_boy.png", width=120, height=120, fallback_icon=ft.Icons.FACE),
                    ft.Text("Male", size=16, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_700 if is_m else ft.Colors.GREY_500)
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=8),
                padding=15, border_radius=20,
                border=make_border(2.5 if is_m else 1, ft.Colors.BLUE_600 if is_m else ft.Colors.GREY_300),
                bgcolor=ft.Colors.BLUE_50 if is_m else None,
                on_click=lambda _: select_gender("Male")
            )

            girl_card = ft.Container(
                content=ft.Column([
                    make_safe_image("assets/illustrations/avatar_girl.png", width=120, height=120, fallback_icon=ft.Icons.FACE_3),
                    ft.Text("Female", size=16, weight=ft.FontWeight.BOLD, color=ft.Colors.PINK_600 if is_f else ft.Colors.GREY_500)
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=8),
                padding=15, border_radius=20,
                border=make_border(2.5 if is_f else 1, ft.Colors.PINK_500 if is_f else ft.Colors.GREY_300),
                bgcolor=ft.Colors.PINK_50 if is_f else None,
                on_click=lambda _: select_gender("Female")
            )

            body_content = [
                title_text,
                ft.Container(height=35),
                ft.Row([boy_card, girl_card], alignment=ft.MainAxisAlignment.SPACE_EVENLY),
                ft.Container(height=40)
            ]

        # ---------------- STEP 2: YOUR WEIGHT (SLIDING NUMBER WHEEL) ----------------
        # Exactly as screenshot 05-2.jpeg: numbers slide up/down without +/- buttons
        elif step == 2:
            title_text = ft.Text("Your Weight", size=22, weight=ft.FontWeight.BOLD, color=txt_main)
            cur_w = onboarding_state["weight_kg"]

            def shift_weight(new_w):
                onboarding_state["weight_kg"] = max(35, min(160, new_w))
                show_onboarding_flow(step=2)

            def toggle_unit(u):
                onboarding_state["weight_unit"] = u
                page.update()

            # Interactive sliding wheel with 5 stacked numbers
            w_m2 = cur_w - 2
            w_m1 = cur_w - 1
            w_p1 = cur_w + 1
            w_p2 = cur_w + 2

            wheel_column = ft.Column([
                # Above number 2
                ft.Container(
                    content=ft.Text(f"{w_m2}", size=16, color=ft.Colors.GREY_400),
                    alignment=ft.Alignment(0, 0), height=32,
                    on_click=lambda _: shift_weight(w_m2)
                ),
                # Above number 1
                ft.Container(
                    content=ft.Text(f"{w_m1}", size=22, color=ft.Colors.GREY_500, weight=ft.FontWeight.W_500),
                    alignment=ft.Alignment(0, 0), height=36,
                    on_click=lambda _: shift_weight(w_m1)
                ),
                # Divider line above center
                ft.Container(height=1.5, width=180, bgcolor=ft.Colors.GREY_300),
                # Selected number in center (bold blue, large)
                ft.Container(
                    content=ft.Row([
                        ft.Text(f"{cur_w}", size=38, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_700),
                        ft.Text("kg", size=18, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_700)
                    ], alignment=ft.MainAxisAlignment.CENTER, spacing=6),
                    alignment=ft.Alignment(0, 0), height=52
                ),
                # Divider line below center
                ft.Container(height=1.5, width=180, bgcolor=ft.Colors.GREY_300),
                # Below number 1
                ft.Container(
                    content=ft.Text(f"{w_p1}", size=22, color=ft.Colors.GREY_500, weight=ft.FontWeight.W_500),
                    alignment=ft.Alignment(0, 0), height=36,
                    on_click=lambda _: shift_weight(w_p1)
                ),
                # Below number 2
                ft.Container(
                    content=ft.Text(f"{w_p2}", size=16, color=ft.Colors.GREY_400),
                    alignment=ft.Alignment(0, 0), height=32,
                    on_click=lambda _: shift_weight(w_p2)
                ),
                # Wheel slide hint
                ft.Text("↕ Tap or scroll numbers to slide", size=11, color=ft.Colors.GREY_400)
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=2)

            body_content = [
                title_text,
                ft.Container(height=15),
                ft.Row([
                    make_safe_image("assets/illustrations/illust_weight.png", width=140, height=230, fallback_icon=ft.Icons.MONITOR_WEIGHT),
                    ft.Container(content=wheel_column, width=180, alignment=ft.Alignment(0, 0))
                ], alignment=ft.MainAxisAlignment.SPACE_EVENLY, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Container(height=20)
            ]

        # ---------------- STEP 3: WAKE-UP TIME (SLIDING TIME WHEEL) ----------------
        # Exactly as screenshot 05-3.jpeg: dual column hours and minutes wheel without buttons
        elif step == 3:
            title_text = ft.Text("Wake-up time", size=22, weight=ft.FontWeight.BOLD, color=txt_main)
            cur_h = onboarding_state["wake_hour"]
            cur_m = onboarding_state["wake_minute"]

            def shift_hour(new_h):
                onboarding_state["wake_hour"] = (new_h) % 24
                show_onboarding_flow(step=3)

            def shift_min(new_m):
                onboarding_state["wake_minute"] = (new_m) % 60
                show_onboarding_flow(step=3)

            h_prev = (cur_h - 1) % 24
            h_next = (cur_h + 1) % 24
            m_prev = (cur_m - 1) % 60
            m_next = (cur_m + 1) % 60

            # Dual sliding column: Hours | Minutes
            hours_col = ft.Column([
                ft.Container(content=ft.Text(f"{h_prev:02d}", size=22, color=ft.Colors.GREY_400), alignment=ft.Alignment(0, 0), height=36, on_click=lambda _: shift_hour(h_prev)),
                ft.Container(height=1.5, width=70, bgcolor=ft.Colors.GREY_300),
                ft.Container(content=ft.Text(f"{cur_h:02d}", size=36, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_700), alignment=ft.Alignment(0, 0), height=50),
                ft.Container(height=1.5, width=70, bgcolor=ft.Colors.GREY_300),
                ft.Container(content=ft.Text(f"{h_next:02d}", size=22, color=ft.Colors.GREY_400), alignment=ft.Alignment(0, 0), height=36, on_click=lambda _: shift_hour(h_next)),
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=2)

            mins_col = ft.Column([
                ft.Container(content=ft.Text(f"{m_prev:02d}", size=22, color=ft.Colors.GREY_400), alignment=ft.Alignment(0, 0), height=36, on_click=lambda _: shift_min(m_prev)),
                ft.Container(height=1.5, width=70, bgcolor=ft.Colors.GREY_300),
                ft.Container(content=ft.Text(f"{cur_m:02d}", size=36, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_700), alignment=ft.Alignment(0, 0), height=50),
                ft.Container(height=1.5, width=70, bgcolor=ft.Colors.GREY_300),
                ft.Container(content=ft.Text(f"{m_next:02d}", size=22, color=ft.Colors.GREY_400), alignment=ft.Alignment(0, 0), height=36, on_click=lambda _: shift_min(m_next)),
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=2)

            time_wheel = ft.Column([
                ft.Row([
                    hours_col,
                    ft.Text(":", size=32, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_700),
                    mins_col
                ], alignment=ft.MainAxisAlignment.CENTER, vertical_alignment=ft.CrossAxisAlignment.CENTER, spacing=8),
                ft.Text("↕ Tap or scroll numbers to slide time", size=11, color=ft.Colors.GREY_400)
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=6)

            body_content = [
                title_text,
                ft.Container(height=15),
                ft.Row([
                    make_safe_image("assets/illustrations/illust_wake.png", width=140, height=230, fallback_icon=ft.Icons.ALARM),
                    ft.Container(content=time_wheel, width=180, alignment=ft.Alignment(0, 0))
                ], alignment=ft.MainAxisAlignment.SPACE_EVENLY, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Container(height=20)
            ]

        # ---------------- STEP 4: BEDTIME (SLIDING TIME WHEEL) ----------------
        # Exactly as screenshot 05-4.jpeg: bedtime sliding time wheel without buttons
        elif step == 4:
            title_text = ft.Text("Bedtime", size=22, weight=ft.FontWeight.BOLD, color=txt_main)
            cur_h = onboarding_state["bed_hour"]
            cur_m = onboarding_state["bed_minute"]

            def shift_bed_hour(new_h):
                onboarding_state["bed_hour"] = (new_h) % 24
                show_onboarding_flow(step=4)

            def shift_bed_min(new_m):
                onboarding_state["bed_minute"] = (new_m) % 60
                show_onboarding_flow(step=4)

            h_prev = (cur_h - 1) % 24
            h_next = (cur_h + 1) % 24
            m_prev = (cur_m - 1) % 60
            m_next = (cur_m + 1) % 60

            bed_hours_col = ft.Column([
                ft.Container(content=ft.Text(f"{h_prev:02d}", size=22, color=ft.Colors.GREY_400), alignment=ft.Alignment(0, 0), height=36, on_click=lambda _: shift_bed_hour(h_prev)),
                ft.Container(height=1.5, width=70, bgcolor=ft.Colors.GREY_300),
                ft.Container(content=ft.Text(f"{cur_h:02d}", size=36, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_700), alignment=ft.Alignment(0, 0), height=50),
                ft.Container(height=1.5, width=70, bgcolor=ft.Colors.GREY_300),
                ft.Container(content=ft.Text(f"{h_next:02d}", size=22, color=ft.Colors.GREY_400), alignment=ft.Alignment(0, 0), height=36, on_click=lambda _: shift_bed_hour(h_next)),
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=2)

            bed_mins_col = ft.Column([
                ft.Container(content=ft.Text(f"{m_prev:02d}", size=22, color=ft.Colors.GREY_400), alignment=ft.Alignment(0, 0), height=36, on_click=lambda _: shift_bed_min(m_prev)),
                ft.Container(height=1.5, width=70, bgcolor=ft.Colors.GREY_300),
                ft.Container(content=ft.Text(f"{cur_m:02d}", size=36, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_700), alignment=ft.Alignment(0, 0), height=50),
                ft.Container(height=1.5, width=70, bgcolor=ft.Colors.GREY_300),
                ft.Container(content=ft.Text(f"{m_next:02d}", size=22, color=ft.Colors.GREY_400), alignment=ft.Alignment(0, 0), height=36, on_click=lambda _: shift_bed_min(m_next)),
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=2)

            bed_time_wheel = ft.Column([
                ft.Row([
                    bed_hours_col,
                    ft.Text(":", size=32, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_700),
                    bed_mins_col
                ], alignment=ft.MainAxisAlignment.CENTER, vertical_alignment=ft.CrossAxisAlignment.CENTER, spacing=8),
                ft.Text("↕ Tap or scroll numbers to slide time", size=11, color=ft.Colors.GREY_400)
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=6)

            body_content = [
                title_text,
                ft.Container(height=15),
                ft.Row([
                    make_safe_image("assets/illustrations/illust_sleep.png", width=140, height=230, fallback_icon=ft.Icons.BEDTIME),
                    ft.Container(content=bed_time_wheel, width=180, alignment=ft.Alignment(0, 0))
                ], alignment=ft.MainAxisAlignment.SPACE_EVENLY, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ft.Container(height=20)
            ]

        # ---------------- STEP 5: PERSONAL HYDRATION PLAN (DIRECT START & AUTO-LOGIN) ----------------
        # Seamless: Clicking START immediately logs in and takes user straight to Home! No repeated login!
        elif step == 5:
            w_h = onboarding_state["wake_hour"]
            w_m = onboarding_state["wake_minute"]
            b_h = onboarding_state["bed_hour"]
            b_m = onboarding_state["bed_minute"]

            w_str = f"{w_h:02d}:{w_m:02d} {'AM' if w_h < 12 else 'PM'}"
            b_str = f"{b_h:02d}:{b_m:02d} {'AM' if b_h < 12 else 'PM'}"

            target_l, glasses, interval, _, _ = calculate_water_schedule(
                onboarding_state["gender"], onboarding_state["weight_kg"], 28,
                b_str, w_str
            )
            cup_ml = int(round((target_l * 1000) / max(glasses, 1)))

            name_input = ft.TextField(
                label="Your Name (Optional)",
                value=user_session.get("username") or "Gaurav",
                prefix_icon=ft.Icons.PERSON,
                width=300
            )

            glass_card = ft.Container(
                content=ft.Column([
                    ft.Icon(ft.Icons.LOCAL_DRINK_ROUNDED, size=75, color=ft.Colors.BLUE_600),
                    ft.Text(f"{cup_ml} ml", size=24, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_800),
                    ft.Container(
                        content=ft.Text(f"×{glasses}", size=16, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
                        bgcolor=ft.Colors.BLUE_700, border_radius=15, padding=make_padding(horizontal=12, vertical=4)
                    )
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=6),
                padding=20, border_radius=20, bgcolor=ft.Colors.BLUE_50, alignment=ft.Alignment(0, 0)
            )

            def on_start_clicked(e):
                u_name = name_input.value.strip() if name_input.value else (user_session.get("username") or "Gaurav")
                # 1. Update or create account in SQLite
                ok, msg, uid = db_register_simple(
                    u_name, "WaterPass123!", "", "",
                    onboarding_state["gender"], onboarding_state["weight_kg"], 28,
                    w_str, b_str
                )
                # 2. IMMEDIATE AUTO-LOGIN: Sets active session & user state
                user_session["id"] = uid
                user_session["username"] = u_name
                user_session["gender"] = onboarding_state["gender"]
                user_session["weight"] = onboarding_state["weight_kg"]
                user_session["wake_t"] = w_str
                user_session["sleep_t"] = b_str
                user_session["water_target"] = target_l
                user_session["water_cup_ml"] = cup_ml
                db_set_active_session(uid)

                # 3. DIRECTLY LAUNCH DASHBOARD! ZERO LOGIN REDIRECTION!
                show_dashboard()

            body_content = [
                ft.Row([
                    ft.Icon(ft.Icons.PERSON, color=ft.Colors.BLUE_700),
                    ft.Text("Personal hydration plan", size=16, weight=ft.FontWeight.BOLD, color=txt_main)
                ], spacing=6),
                ft.Container(height=10),
                glass_card,
                ft.Container(height=10),
                ft.Text("How much should you drink", size=18, weight=ft.FontWeight.BOLD, color=txt_main),
                ft.Text(f"{glasses} times a day", size=15, color=ft.Colors.BLUE_700, weight=ft.FontWeight.BOLD),
                ft.Text(f"{cup_ml}ml each time • Daily Target: {target_l:.2f} L", size=13, color=ft.Colors.GREY_600),
                ft.Container(height=10),
                name_input,
                ft.Container(height=15),
                ft.Button(
                    content=ft.Text("START", size=16, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
                    bgcolor=ft.Colors.BLUE_700, width=280, height=48,
                    on_click=on_start_clicked
                ),
                ft.TextButton("Already have an account? Log In", on_click=lambda _: show_login_screen())
            ]

        # Navigation Bottom Bar: [< Back] and [NEXT]
        def go_next(e):
            if step < 5:
                show_onboarding_flow(step=step + 1)
            else:
                show_dashboard()

        def go_back(e):
            if step > 1:
                show_onboarding_flow(step=step - 1)
            else:
                show_dashboard()

        nav_bottom = ft.Row([
            ft.IconButton(icon=ft.Icons.ARROW_BACK_IOS, icon_color=ft.Colors.WHITE, bgcolor=ft.Colors.BLUE_700, on_click=go_back) if step > 1 else ft.Container(width=40),
            ft.Button(
                content=ft.Text("NEXT", color=ft.Colors.WHITE, size=15, weight=ft.FontWeight.BOLD),
                bgcolor=ft.Colors.BLUE_700, width=120, height=44, on_click=go_next
            ) if step < 5 else ft.Container()
        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)

        page.add(
            ft.SafeArea(
                ft.Container(
                    content=ft.Column([
                        step_bar if step <= 4 else ft.Container(height=10),
                        ft.Column(body_content, horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=10),
                        ft.Container(expand=True),
                        nav_bottom if step <= 4 else ft.Container()
                    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                    padding=16, expand=True
                )
            )
        )

        # SCREEN 1: HOME (WATER TRACKER & COUNTDOWN LOCK)
    # -------------------------------------------------------------
    def show_dashboard():
        if not user_session.get("id"):
            show_login_screen()
            return

        active_ticker_token[0] += 1
        current_token = active_ticker_token[0]
        timer_cancel_event.set()
        timer_cancel_event.clear()
        page.clean()

        is_dark = (page.theme_mode == ft.ThemeMode.DARK)
        txt_main = ft.Colors.WHITE if is_dark else ft.Colors.BLACK
        card_bg = ft.Colors.GREY_900 if is_dark else ft.Colors.WHITE
        border_c = ft.Colors.GREY_800 if is_dark else ft.Colors.BLUE_GREY_100

        today_iso = datetime.date.today().isoformat()
        today_data = db_get_today_water(user_session["id"], today_iso)

        today_water_glasses[0] = int(today_data[0] or 0)
        try:
            last_drink_time[0] = float(today_data[2] or 0.0)
        except Exception:
            last_drink_time[0] = 0.0

        if today_water_glasses[0] == 0:
            last_drink_time[0] = 0.0

        snooze_delay_until[0] = 0.0
        water_alarm_rung[0] = False
        current_cup_ml = [user_session["water_cup_ml"] or 203]

        target_liters, total_target_glasses, interval_min, wake_min, sleep_min = calculate_water_schedule(
            user_session["gender"], user_session["weight"], user_session["age"],
            user_session["sleep_t"], user_session["wake_t"], current_cup_ml[0], user_session["height"]
        )

        saved_interval = db_get_setting("reminder_interval", None)
        if saved_interval:
            try:
                interval_min = int(saved_interval)
            except Exception:
                pass
        interval_sec = interval_min * 60

        top_bar = get_top_app_bar(selected_idx=0)

        drank_liters = round((today_water_glasses[0] * current_cup_ml[0]) / 1000.0, 2)
        pct = drank_liters / (target_liters or 2.03)

        # Big Progress Ring
        ring_progress = ft.ProgressRing(
            value=min(pct, 1.0),
            width=180, height=180, stroke_width=18,
            color=ft.Colors.BLUE_700, bgcolor=ft.Colors.BLUE_100
        )
        ring_text_val = ft.Text(f"{drank_liters:.2f} L", size=26, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_800 if not is_dark else ft.Colors.BLUE_200)
        ring_text_target = ft.Text(f"Target: {target_liters:.2f} L", size=12, color=ft.Colors.GREY_600)
        ring_text_pct = ft.Text(f"{int(min(pct, 1.0) * 100)}% Achieved", size=13, weight=ft.FontWeight.BOLD, color=ft.Colors.TEAL_700 if not is_dark else ft.Colors.TEAL_300)

        ring_stack = ft.Stack([
            ring_progress,
            ft.Column([
                ring_text_val,
                ring_text_target,
                ring_text_pct
            ], alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER, width=180, height=180)
        ], alignment=ft.Alignment(0, 0))

        circular_card = ft.Container(
            content=ring_stack,
            padding=15, bgcolor=card_bg, border_radius=20,
            border=make_border(1, border_c), alignment=ft.Alignment(0, 0)
        )

        # Cup row presets
        cup_row = ft.Row(alignment=ft.MainAxisAlignment.SPACE_AROUND)
        cup_options = [150, 203, 250, 350, 500]

        def render_cup_cards():
            cup_row.controls.clear()
            for c in cup_options:
                is_selected = (current_cup_ml[0] == c)
                c_bg = ft.Colors.BLUE_100 if is_selected else (ft.Colors.GREY_800 if is_dark else ft.Colors.GREY_100)
                c_border = ft.Colors.BLUE_700 if is_selected else border_c

                def make_click_handler(val=c):
                    def handler(e):
                        current_cup_ml[0] = val
                        user_session["water_cup_ml"] = val
                        db_update_cup_size(user_session["id"], val)
                        show_dashboard()
                    return handler

                card = ft.Container(
                    content=ft.Column([
                        ft.Icon(ft.Icons.LOCAL_DRINK, size=18, color=ft.Colors.BLUE_700 if is_selected else ft.Colors.GREY_500),
                        ft.Text(f"{c}ml", size=11, weight=ft.FontWeight.BOLD if is_selected else ft.FontWeight.NORMAL, color=ft.Colors.BLUE_800 if is_selected else txt_main)
                    ], alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=2),
                    width=60, height=55, border_radius=12, bgcolor=c_bg, border=make_border(2 if is_selected else 1, c_border),
                    on_click=make_click_handler(c)
                )
                cup_row.controls.append(card)

        render_cup_cards()

        # Water Drink Actions
        def execute_drink_log():
            today_water_glasses[0] += 1
            now_epoch = time.time()
            last_drink_time[0] = now_epoch
            snooze_delay_until[0] = 0.0
            water_alarm_rung[0] = False

            current_l = round((today_water_glasses[0] * current_cup_ml[0]) / 1000.0, 2)
            new_streak = db_save_water_intake(user_session["id"], today_iso, today_water_glasses[0], current_l, now_epoch)
            user_session["streak"] = new_streak

            play_system_alert()
            show_dashboard()

        def drink_water_action(e):
            execute_drink_log()

        def undo_drink_action(e):
            new_g, new_l = db_undo_last_glass(user_session["id"], today_iso, current_cup_ml[0])
            today_water_glasses[0] = new_g
            show_dashboard()

        def reset_water_action(e):
            db_reset_today_water(user_session["id"], today_iso)
            today_water_glasses[0] = 0
            last_drink_time[0] = 0.0
            show_dashboard()

        def snooze_action(e):
            snooze_delay_until[0] = time.time() + 15 * 60
            page.update()

        # Initial Countdown Calculations
        now_init = time.time()
        cur_dt_init = datetime.datetime.now()
        cur_min_init = cur_dt_init.hour * 60 + cur_dt_init.minute
        in_sleep_init = is_in_sleep_window(cur_min_init, wake_min, sleep_min)

        if in_sleep_init:
            init_timer_str = "--:--:--"
            init_sub_str = f"🌙 Sleeping Hours ({user_session['sleep_t']} - {user_session['wake_t']})"
            init_progress = 0.0
            btn_icon_name = ft.Icons.BEDTIME
            btn_str = f"🌙 Sleeping Hours (Tap to drink anyway)"
            btn_color = ft.Colors.BLUE_GREY_700
        elif snooze_delay_until[0] > now_init:
            sec_left_init = int(snooze_delay_until[0] - now_init)
            init_timer_str = f"{sec_left_init//60:02d}:{sec_left_init%60:02d}"
            init_sub_str = "⏰ Snooze Active - Alarm paused"
            init_progress = max(0.0, min(1.0, 1.0 - (sec_left_init / (15 * 60))))
            btn_icon_name = ft.Icons.SNOOZE
            btn_str = f"⏰ Snooze Active ({sec_left_init//60:02d}:{sec_left_init%60:02d})"
            btn_color = ft.Colors.AMBER_800
        elif last_drink_time[0] == 0.0 or today_water_glasses[0] == 0:
            init_timer_str = "READY 💧"
            init_sub_str = "Drink your first glass to start today's hydration!"
            init_progress = 1.0
            btn_icon_name = ft.Icons.LOCAL_DRINK
            btn_str = f"💧 Drink First Glass ({current_cup_ml[0]}ml)"
            btn_color = ft.Colors.BLUE_700
        else:
            sec_passed_init = now_init - last_drink_time[0]
            sec_left_init = interval_sec - sec_passed_init
            if sec_left_init <= 0:
                init_timer_str = "00:00:00 🔔"
                init_sub_str = f"Time to hydrate! Drink {current_cup_ml[0]}ml water now"
                init_progress = 1.0
                btn_icon_name = ft.Icons.CHECK_CIRCLE
                btn_str = f"💧 Drink {current_cup_ml[0]}ml Water (Ready Now)"
                btn_color = ft.Colors.GREEN_700
            else:
                h_left = int(sec_left_init // 3600)
                m_left = int((sec_left_init % 3600) // 60)
                s_left = int(sec_left_init % 60)
                if h_left > 0:
                    init_timer_str = f"{h_left:02d}:{m_left:02d}:{s_left:02d}"
                else:
                    init_timer_str = f"{m_left:02d}:{s_left:02d}"
                next_alarm_time = datetime.datetime.fromtimestamp(now_init + sec_left_init).strftime("%I:%M %p")
                init_sub_str = f"Next reminder at {next_alarm_time} (Interval: {interval_min}m)"
                init_progress = max(0.0, min(1.0, sec_passed_init / float(interval_sec)))
                btn_icon_name = ft.Icons.LOCK_CLOCK
                btn_str = f"🔒 Next in {m_left:02d}:{s_left:02d} (or Tap to Log)"
                btn_color = ft.Colors.BLUE_GREY_700

        # Dedicated Live Countdown Display Card
        countdown_display_text = ft.Text(
            init_timer_str,
            size=28, weight=ft.FontWeight.BOLD,
            color=ft.Colors.BLUE_800 if not is_dark else ft.Colors.BLUE_200,
            font_family="monospace"
        )
        countdown_sub_text = ft.Text(
            init_sub_str,
            size=11, color=ft.Colors.GREY_600 if not is_dark else ft.Colors.GREY_400
        )
        countdown_progress_bar = ft.ProgressBar(
            value=init_progress,
            width=340, height=8, border_radius=4,
            color=ft.Colors.BLUE_700, bgcolor=ft.Colors.BLUE_100 if not is_dark else ft.Colors.GREY_800
        )
        live_chip = ft.Container(
            content=ft.Row([
                ft.Icon(ft.Icons.CIRCLE, size=8, color=ft.Colors.GREEN_600),
                ft.Text("Live Ticker", size=10, weight=ft.FontWeight.BOLD, color=ft.Colors.GREEN_800 if not is_dark else ft.Colors.GREEN_300)
            ], spacing=4),
            bgcolor=ft.Colors.GREEN_50 if not is_dark else ft.Colors.GREY_800,
            border_radius=8, padding=make_padding(horizontal=6, vertical=2)
        )

        countdown_card = ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Row([
                        ft.Icon(ft.Icons.TIMER_OUTLINED, color=ft.Colors.BLUE_700, size=18),
                        ft.Text("Hydration Reminder Countdown", size=12, weight=ft.FontWeight.BOLD, color=txt_main)
                    ], spacing=6),
                    live_chip
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                ft.Row([countdown_display_text], alignment=ft.MainAxisAlignment.CENTER),
                countdown_progress_bar,
                countdown_sub_text
            ], spacing=6, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            padding=12, bgcolor=card_bg, border_radius=16, border=make_border(1, border_c), width=400
        )

        btn_icon = ft.Icon(btn_icon_name, color=ft.Colors.WHITE)
        btn_text = ft.Text(btn_str, color=ft.Colors.WHITE, size=15, weight=ft.FontWeight.BOLD)

        main_drink_btn = ft.Button(
            content=ft.Row([btn_icon, btn_text], alignment=ft.MainAxisAlignment.CENTER),
            bgcolor=btn_color,
            disabled=False,
            width=400, height=50, on_click=drink_water_action
        )

        snooze_btn = ft.OutlinedButton(
            content=ft.Row([
                ft.Icon(ft.Icons.ACCESS_TIME, size=16, color=ft.Colors.BLUE_900 if not is_dark else ft.Colors.BLUE_200),
                ft.Text("15 Min Snooze Timer", size=13, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_900 if not is_dark else ft.Colors.BLUE_200)
            ], alignment=ft.MainAxisAlignment.CENTER),
            width=400, height=44, on_click=snooze_action
        )

        # Performance summary
        rem_liters = max(0.0, target_liters - drank_liters)
        perf_card = ft.Container(
            content=ft.Column([
                ft.Text("Today's Hydration Performance", size=13, weight=ft.FontWeight.BOLD, color=txt_main),
                ft.Row([
                    ft.Column([
                        ft.Text(f"{today_water_glasses[0]} Glasses", size=16, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_700),
                        ft.Text("Total Drank", size=10, color=ft.Colors.GREY_500)
                    ], alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                    ft.Column([
                        ft.Text(f"{user_session['streak']} Days", size=16, weight=ft.FontWeight.BOLD, color=ft.Colors.ORANGE_700),
                        ft.Text("Current Streak", size=10, color=ft.Colors.GREY_500)
                    ], alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                    ft.Column([
                        ft.Text(f"{rem_liters:.2f} L", size=16, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_GREY_600),
                        ft.Text("Remaining", size=10, color=ft.Colors.GREY_500)
                    ], alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                ], alignment=ft.MainAxisAlignment.SPACE_AROUND)
            ], spacing=8),
            padding=14, bgcolor=card_bg, border_radius=16, border=make_border(1, border_c)
        )

        page.add(
            ft.SafeArea(
                ft.Column([
                    top_bar,
                    ft.Container(
                        content=ft.Column([
                            ft.Text(f"Hello, {user_session['username']}! 💧", size=20, weight=ft.FontWeight.BOLD, color=txt_main),
                            ft.Text(f"Daily Water Target: {target_liters:.2f} L ({total_target_glasses} times a day)", size=12, color=ft.Colors.GREY_500),
                            circular_card,
                            ft.Text("Quick Add Water (Cup Size)", size=13, weight=ft.FontWeight.BOLD, color=txt_main),
                            cup_row,
                            countdown_card,
                            main_drink_btn,
                            snooze_btn,
                            perf_card,
                            ft.Container(height=10)
                        ], spacing=8),
                        padding=12
                    )
                ], spacing=0)
            )
        )

        # Background Ticker with Guaranteed Second-to-Second Live Countdown
        def run_countdown_ticker():
            while active_ticker_token[0] == current_token and not timer_cancel_event.is_set():
                time.sleep(1)
                if active_ticker_token[0] != current_token or timer_cancel_event.is_set():
                    break

                now_t = time.time()
                now_dt = datetime.datetime.now()
                cur_min = now_dt.hour * 60 + now_dt.minute

                in_sleep = is_in_sleep_window(cur_min, wake_min, sleep_min)

                if in_sleep:
                    countdown_display_text.value = "--:--:--"
                    countdown_sub_text.value = f"🌙 Sleeping Hours ({user_session['sleep_t']} - {user_session['wake_t']})"
                    countdown_progress_bar.value = 0.0
                    btn_text.value = f"🌙 Sleeping Hours (Tap to drink anyway)"
                    btn_icon.name = ft.Icons.BEDTIME
                    main_drink_btn.bgcolor = ft.Colors.BLUE_GREY_700
                elif snooze_delay_until[0] > now_t:
                    sec_left = int(snooze_delay_until[0] - now_t)
                    m_left = sec_left // 60
                    s_left = sec_left % 60
                    countdown_display_text.value = f"{m_left:02d}:{s_left:02d}"
                    countdown_sub_text.value = "⏰ Snooze Active - Alarm paused"
                    countdown_progress_bar.value = max(0.0, min(1.0, 1.0 - (sec_left / (15 * 60))))
                    btn_text.value = f"⏰ Snooze Active ({m_left:02d}:{s_left:02d})"
                    btn_icon.name = ft.Icons.SNOOZE
                    main_drink_btn.bgcolor = ft.Colors.AMBER_800
                elif last_drink_time[0] == 0.0 or today_water_glasses[0] == 0:
                    countdown_display_text.value = "READY 💧"
                    countdown_sub_text.value = "Drink your first glass to start today's hydration!"
                    countdown_progress_bar.value = 1.0
                    btn_text.value = f"💧 Drink First Glass ({current_cup_ml[0]}ml)"
                    btn_icon.name = ft.Icons.LOCAL_DRINK
                    main_drink_btn.bgcolor = ft.Colors.BLUE_700
                else:
                    sec_passed = now_t - last_drink_time[0]
                    sec_left = interval_sec - sec_passed
                    if sec_left <= 0:
                        countdown_display_text.value = "00:00:00 🔔"
                        countdown_sub_text.value = f"Time to hydrate! Drink {current_cup_ml[0]}ml water now"
                        countdown_progress_bar.value = 1.0
                        btn_text.value = f"💧 Drink {current_cup_ml[0]}ml Water (Ready Now)"
                        btn_icon.name = ft.Icons.CHECK_CIRCLE
                        main_drink_btn.bgcolor = ft.Colors.GREEN_700
                        if not water_alarm_rung[0]:
                            water_alarm_rung[0] = True
                            play_system_alert()
                    else:
                        h_left = int(sec_left // 3600)
                        m_left = int((sec_left % 3600) // 60)
                        s_left = int(sec_left % 60)
                        if h_left > 0:
                            countdown_display_text.value = f"{h_left:02d}:{m_left:02d}:{s_left:02d}"
                        else:
                            countdown_display_text.value = f"{m_left:02d}:{s_left:02d}"
                        next_alarm_time = datetime.datetime.fromtimestamp(now_t + sec_left).strftime("%I:%M %p")
                        countdown_sub_text.value = f"Next reminder at {next_alarm_time} (Interval: {interval_min}m)"
                        elapsed_ratio = max(0.0, min(1.0, sec_passed / float(interval_sec)))
                        countdown_progress_bar.value = elapsed_ratio

                        btn_text.value = f"🔒 Next in {m_left:02d}:{s_left:02d} (or Tap to Log)"
                        btn_icon.name = ft.Icons.LOCK_CLOCK
                        main_drink_btn.bgcolor = ft.Colors.BLUE_GREY_700

                # Live push update
                try:
                    page.update()
                except Exception:
                    try:
                        countdown_display_text.update()
                        countdown_sub_text.update()
                        countdown_progress_bar.update()
                        btn_text.update()
                        btn_icon.update()
                        main_drink_btn.update()
                    except Exception:
                        pass

        threading.Thread(target=run_countdown_ticker, daemon=True).start()

    # -------------------------------------------------------------
    # SCREEN 2: MEDICINES SCREEN (WITH PRESETS & INLINE PHOTO)
    # -------------------------------------------------------------
    def show_medicines_screen():
        active_ticker_token[0] += 1
        timer_cancel_event.set()
        page.clean()

        is_dark = (page.theme_mode == ft.ThemeMode.DARK)
        txt_main = ft.Colors.WHITE if is_dark else ft.Colors.BLACK
        card_bg = ft.Colors.GREY_900 if is_dark else ft.Colors.WHITE
        border_c = ft.Colors.GREY_800 if is_dark else ft.Colors.BLUE_GREY_100

        top_bar = get_top_app_bar(selected_idx=1)
        today_iso = datetime.date.today().isoformat()
        taken_dict = db_get_today_taken_meds(user_session["id"], today_iso)
        meds_list = db_get_medicines(user_session["id"])

        # Photo viewer banner if active
        photo_viewer_banner = None
        if active_viewing_med[0]:
            view_data = active_viewing_med[0]
            v_photo = view_data.get("photo", "")
            img_disp = make_safe_image(v_photo, width=320, height=220, fit="contain", fallback_icon=ft.Icons.MEDICATION)

            def close_photo_viewer(ev=None):
                active_viewing_med[0] = None
                show_medicines_screen()

            photo_viewer_banner = ft.Container(
                content=ft.Column([
                    ft.Row([
                        ft.Row([
                            ft.Icon(ft.Icons.PHOTO_CAMERA_BACK_ROUNDED, color=ft.Colors.BLUE_700),
                            ft.Text(f"Prescription Photo: {view_data['name']}", size=15, weight=ft.FontWeight.BOLD, color=txt_main)
                        ], spacing=6),
                        ft.IconButton(icon=ft.Icons.CLOSE, tooltip="Close Photo", on_click=close_photo_viewer)
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    ft.Container(
                        content=img_disp,
                        width=340, height=230, border_radius=12,
                        bgcolor=ft.Colors.GREY_100 if not is_dark else ft.Colors.GREY_800,
                        alignment=ft.Alignment(0, 0), border=make_border(1.5, ft.Colors.BLUE_500)
                    ),
                    ft.Text(f"📋 Dosage & Instructions: {view_data.get('instr') or 'After Food'}", size=12, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_900 if not is_dark else ft.Colors.BLUE_200),
                    ft.Button(
                        content=ft.Row([
                            ft.Icon(ft.Icons.CLOSE, size=15, color=ft.Colors.WHITE),
                            ft.Text("✖ Close Photo", color=ft.Colors.WHITE, size=13, weight=ft.FontWeight.BOLD)
                        ], alignment=ft.MainAxisAlignment.CENTER),
                        bgcolor=ft.Colors.RED_700, width=280, height=38, on_click=close_photo_viewer
                    )
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=8),
                padding=14, bgcolor=card_bg, border_radius=16, border=make_border(2, ft.Colors.BLUE_600)
            )

        # Inline Add Medicine Card
        inline_add_card = None
        if is_adding_med_inline[0]:
            add_name_ctrl = ft.TextField(label="Medicine Name*", autofocus=True)
            add_instr_ctrl = ft.Dropdown(
                label="Dosage & Instructions",
                options=[
                    ft.dropdown.Option("After Food"),
                    ft.dropdown.Option("Before Food / Empty Stomach"),
                    ft.dropdown.Option("With Lunch"),
                    ft.dropdown.Option("With Warm Milk at Bedtime")
                ],
                value="After Food"
            )
            ch_m = ft.Checkbox(label="Morning (08:00 AM)", value=True)
            ch_a = ft.Checkbox(label="Afternoon (01:30 PM)", value=False)
            ch_e = ft.Checkbox(label="Evening (06:00 PM)", value=False)
            ch_n = ft.Checkbox(label="Night (09:00 PM)", value=True)
            err_label = ft.Text("", color=ft.Colors.RED_600, size=12, weight=ft.FontWeight.BOLD)

            med_photo_preview = ft.Container(
                content=make_safe_image(med_picker_selected_path[0] or "capsule_red.jpg", width=75, height=75, fit="cover", fallback_icon=ft.Icons.MEDICATION),
                width=75, height=75, border_radius=10, border=make_border(1, ft.Colors.BLUE_400), alignment=ft.Alignment(0, 0)
            )

            def pick_preset(p_name):
                sel_p = os.path.join(PHOTOS_DIR, p_name)
                if not os.path.exists(sel_p):
                    alt_p = os.path.join("medicine_photos", p_name)
                    if os.path.exists(alt_p): sel_p = alt_p
                med_picker_selected_path[0] = sel_p
                med_photo_preview.content = make_safe_image(sel_p, width=75, height=75, fit="cover", fallback_icon=ft.Icons.MEDICATION)
                page.update()

            def pick_from_files(ev):
                trigger_universal_file_picker(is_profile=False)
                if med_picker_selected_path[0]:
                    med_photo_preview.content = make_safe_image(med_picker_selected_path[0], width=75, height=75, fit="cover", fallback_icon=ft.Icons.MEDICATION)
                    page.update()

            def do_save_medicine(ev):
                m_name = add_name_ctrl.value.strip() if add_name_ctrl.value else ""
                if len(m_name) < 2:
                    err_label.value = "⚠️ Please enter medicine name!"
                    page.update()
                    return

                p_to_save = med_picker_selected_path[0] or "capsule_red.jpg"
                db_add_medicine(
                    user_session["id"], m_name, p_to_save,
                    1 if ch_m.value else 0, "08:00 AM",
                    1 if ch_a.value else 0, "01:30 PM",
                    1 if ch_e.value else 0, "06:00 PM",
                    1 if ch_n.value else 0, "09:00 PM",
                    add_instr_ctrl.value
                )
                is_adding_med_inline[0] = False
                show_medicines_screen()

            inline_add_card = ft.Container(
                content=ft.Column([
                    ft.Row([
                        ft.Text("➕ Add New Medicine & Photo", size=15, weight=ft.FontWeight.BOLD, color=txt_main),
                        ft.IconButton(icon=ft.Icons.CLOSE, on_click=lambda _: (is_adding_med_inline.__setitem__(0, False), show_medicines_screen()))
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    add_name_ctrl,
                    err_label,
                    add_instr_ctrl,
                    ft.Text("Select Time Slots:", size=12, weight=ft.FontWeight.BOLD, color=txt_main),
                    ft.Row([ch_m, ch_a]),
                    ft.Row([ch_e, ch_n]),
                    ft.Divider(height=1),
                    ft.Text("Select Medicine Photo:", size=12, weight=ft.FontWeight.BOLD, color=txt_main),
                    ft.Row([
                        med_photo_preview,
                        ft.Column([
                            ft.Button(content=ft.Row([ft.Icon(ft.Icons.CAMERA_ALT, size=15), ft.Text("📁 Choose from PC / Phone")]), on_click=pick_from_files),
                            ft.Text("Or pick an instant preset:", size=10, color=ft.Colors.GREY_600),
                            ft.Row([
                                ft.TextButton("🔴 Capsule", on_click=lambda _: pick_preset("capsule_red.jpg")),
                                ft.TextButton("🟢 Tablet", on_click=lambda _: pick_preset("tablet_teal.jpg")),
                                ft.TextButton("🟡 Syrup", on_click=lambda _: pick_preset("syrup_bottle.jpg")),
                                ft.TextButton("🟣 Drops", on_click=lambda _: pick_preset("drops_purple.jpg")),
                            ], wrap=True, spacing=1)
                        ], spacing=3, expand=True)
                    ], vertical_alignment=ft.CrossAxisAlignment.CENTER, spacing=10),
                    ft.Divider(height=1),
                    ft.Row([
                        ft.Button(content=ft.Text("💾 Save Medicine", color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD), bgcolor=ft.Colors.BLUE_700, on_click=do_save_medicine),
                        ft.TextButton("Cancel", on_click=lambda _: (is_adding_med_inline.__setitem__(0, False), show_medicines_screen()))
                    ], alignment=ft.MainAxisAlignment.END, spacing=8)
                ], spacing=8),
                padding=14, bgcolor=card_bg, border_radius=16, border=make_border(2, ft.Colors.BLUE_600)
            )

        med_cards = []
        if not meds_list:
            med_cards.append(
                ft.Container(
                    content=ft.Column([
                        ft.Icon(ft.Icons.MEDICATION_LIQUID_ROUNDED, size=55, color=ft.Colors.BLUE_400),
                        ft.Text("No medicines added yet.", size=15, weight=ft.FontWeight.BOLD, color=txt_main),
                        ft.Text("Add your daily prescriptions, times, and pill photos below.", size=12, color=ft.Colors.GREY_500, text_align=ft.TextAlign.CENTER)
                    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=6),
                    padding=25, alignment=ft.Alignment(0, 0)
                )
            )
        else:
            for m in meds_list:
                m_id, u_id, name, p_path, m_slot, m_time, a_slot, a_time, e_slot, e_time, n_slot, n_time, instr = m

                resolved_photo = resolve_photo_path(p_path) or p_path

                def make_view_photo_handler(med_id=m_id, med_title=name, med_photo=resolved_photo, med_instr=instr):
                    def handler(ev):
                        if active_viewing_med[0] and active_viewing_med[0].get("id") == med_id:
                            active_viewing_med[0] = None
                        else:
                            active_viewing_med[0] = {"id": med_id, "name": med_title, "photo": med_photo, "instr": med_instr}
                        show_medicines_screen()
                    return handler

                is_current_viewed = (active_viewing_med[0] and active_viewing_med[0].get("id") == m_id)

                photo_ctrl = ft.Container(
                    content=ft.Stack([
                        make_safe_image(resolved_photo, width=74, height=74, fit="cover", fallback_icon=ft.Icons.MEDICATION),
                        ft.Container(
                            content=ft.Icon(ft.Icons.ZOOM_IN, size=16, color=ft.Colors.WHITE),
                            bgcolor=getattr(ft.Colors, "BLACK_54", "black54"), border_radius=8, padding=2,
                            alignment=ft.Alignment(1, 1)
                        )
                    ]),
                    width=74, height=74, border_radius=10,
                    border=make_border(2, ft.Colors.BLUE_600 if is_current_viewed else ft.Colors.BLUE_GREY_200),
                    on_click=make_view_photo_handler(),
                    tooltip="Tap to view large photo"
                )

                slot_controls = []
                slots_data = [
                    ("morning", "Morning", m_slot, m_time),
                    ("afternoon", "Afternoon", a_slot, a_time),
                    ("evening", "Evening", e_slot, e_time),
                    ("night", "Night", n_slot, n_time)
                ]

                for s_key, s_label, is_enabled, s_time in slots_data:
                    if is_enabled:
                        is_taken = (m_id, s_key) in taken_dict
                        if is_taken:
                            badge = ft.Container(
                                content=ft.Row([
                                    ft.Icon(ft.Icons.CHECK_CIRCLE, size=14, color=ft.Colors.GREEN_700),
                                    ft.Text(f"{s_label}: {s_time} (Taken)", size=11, weight=ft.FontWeight.BOLD, color=ft.Colors.GREEN_800)
                                ], spacing=4),
                                bgcolor=ft.Colors.GREEN_50, border_radius=8, padding=make_padding(horizontal=8, vertical=4)
                            )
                        else:
                            def make_take_handler(mid=m_id, skey=s_key):
                                def handler(e):
                                    db_mark_medicine_taken(user_session["id"], today_iso, mid, skey)
                                    play_system_alert()
                                    show_medicines_screen()
                                return handler

                            badge = ft.Button(
                                content=ft.Row([
                                    ft.Icon(ft.Icons.CHECK, size=14, color=ft.Colors.WHITE),
                                    ft.Text(f"{s_label}: {s_time} (Take)", size=11, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE)
                                ], spacing=4),
                                bgcolor=ft.Colors.ORANGE_800, height=32, on_click=make_take_handler()
                            )
                        slot_controls.append(badge)

                def make_del_handler(mid=m_id):
                    def handler(e):
                        db_delete_medicine(mid, user_session["id"])
                        if active_viewing_med[0] and active_viewing_med[0].get("id") == mid:
                            active_viewing_med[0] = None
                        show_medicines_screen()
                    return handler

                card = ft.Container(
                    content=ft.Column([
                        ft.Row([
                            photo_ctrl,
                            ft.Column([
                                ft.Text(name, size=16, weight=ft.FontWeight.BOLD, color=txt_main),
                                ft.Text(f"Instructions: {instr or 'After Food'}", size=11, color=ft.Colors.BLUE_600 if not is_dark else ft.Colors.BLUE_300),
                                ft.TextButton(
                                    content=ft.Row([
                                        ft.Icon(ft.Icons.IMAGE, size=13, color=ft.Colors.BLUE_700 if not is_dark else ft.Colors.BLUE_300),
                                        ft.Text("🔍 View Photo" if not is_current_viewed else "✖ Close Photo", size=11, color=ft.Colors.BLUE_700 if not is_dark else ft.Colors.BLUE_300)
                                    ], spacing=2),
                                    on_click=make_view_photo_handler()
                                )
                            ], spacing=2, expand=True),
                            ft.IconButton(icon=ft.Icons.DELETE_OUTLINE, tooltip="Delete Medicine", on_click=make_del_handler())
                        ], vertical_alignment=ft.CrossAxisAlignment.CENTER, spacing=10),
                        ft.Row(slot_controls, wrap=True, spacing=6)
                    ], spacing=8),
                    padding=12, bgcolor=card_bg, border_radius=14, border=make_border(1, border_c)
                )
                med_cards.append(card)

        def toggle_inline_add(e):
            is_adding_med_inline[0] = not is_adding_med_inline[0]
            show_medicines_screen()

        add_med_btn = ft.Button(
            content=ft.Row([ft.Icon(ft.Icons.CLOSE if is_adding_med_inline[0] else ft.Icons.ADD, color=ft.Colors.WHITE), ft.Text("✖ Close Form" if is_adding_med_inline[0] else "➕ Add Medicine & Photo", color=ft.Colors.WHITE, size=15, weight=ft.FontWeight.BOLD)], alignment=ft.MainAxisAlignment.CENTER),
            bgcolor=ft.Colors.RED_800 if is_adding_med_inline[0] else ft.Colors.BLUE_700, width=400, height=50, on_click=toggle_inline_add
        )

        page.add(
            ft.SafeArea(
                ft.Column([
                    top_bar,
                    ft.Container(
                        content=ft.Column([
                            photo_viewer_banner if photo_viewer_banner else ft.Container(height=0),
                            inline_add_card if inline_add_card else ft.Container(height=0),
                            ft.Column(med_cards, spacing=10),
                            ft.Container(content=add_med_btn, padding=make_padding(top=10, bottom=15))
                        ], spacing=8),
                        padding=12
                    )
                ], spacing=0)
            )
        )

    # -------------------------------------------------------------
    # SCREEN 3: SETTINGS (EXACTLY AS SCREENSHOTS setting-1 & setting-2)
    # -------------------------------------------------------------
    def show_profile_settings_screen():
        active_ticker_token[0] += 1
        timer_cancel_event.set()
        page.clean()
        active_tab[0] = 3

        is_dark = (page.theme_mode == ft.ThemeMode.DARK)
        # 100% High Contrast: Pure White background in Light mode, Pure Dark in Dark mode!
        page.bgcolor = ft.Colors.GREY_900 if is_dark else ft.Colors.WHITE
        txt_main = ft.Colors.WHITE if is_dark else ft.Colors.BLACK
        txt_sub = ft.Colors.GREY_400 if is_dark else ft.Colors.GREY_600
        card_bg = ft.Colors.GREY_900 if is_dark else ft.Colors.WHITE
        panel_bg = ft.Colors.GREY_800 if is_dark else ft.Colors.BLUE_50
        border_c = ft.Colors.GREY_800 if is_dark else ft.Colors.GREY_200

        top_bar = get_top_app_bar(selected_idx=3)

        cur_sound_id = db_get_setting("reminder_sound", "water_droplets")
        sound_names_map = {opt["id"]: opt["name"] for opt in RINGTONE_OPTIONS}
        cur_sound_display = sound_names_map.get(cur_sound_id, "💧 Water Droplets")

        interval_min = int(db_get_setting("reminder_interval", "90"))
        try:
            _, _, calc_interval, _, _ = calculate_water_schedule(
                user_session["gender"], user_session["weight"], user_session["age"],
                user_session["sleep_t"], user_session["wake_t"]
            )
            if not db_get_setting("reminder_interval", None):
                interval_min = calc_interval
        except Exception:
            pass

        cur_mode = db_get_setting("reminder_mode", "Sound and vibrate")
        target_ml = int(round(user_session["water_target"] * 1000))

        # ---------------- IN-PAGE EXPANDABLE ACTIVE PANEL ----------------
        # 100% Guaranteed: Opens instantly on the screen even if popup dialogs are blocked!
        active_panel = None

        def close_active_panel(e=None):
            active_setting_view[0] = None
            show_profile_settings_screen()

        if active_setting_view[0] == "schedule":
            intervals = [30, 45, 60, 90, 120]
            def pick_sched(m):
                db_set_setting("reminder_interval", str(m))
                active_setting_view[0] = None
                show_profile_settings_screen()

            sched_buttons = [
                ft.Button(
                    content=ft.Row([
                        ft.Icon(ft.Icons.CHECK if m == interval_min else ft.Icons.SCHEDULE, size=16, color=ft.Colors.WHITE if m == interval_min else ft.Colors.BLUE_700),
                        ft.Text(f"Every {m} minutes", size=13, color=ft.Colors.WHITE if m == interval_min else txt_main, weight=ft.FontWeight.BOLD if m == interval_min else ft.FontWeight.NORMAL)
                    ], alignment=ft.MainAxisAlignment.CENTER, spacing=6),
                    bgcolor=ft.Colors.BLUE_700 if m == interval_min else (ft.Colors.WHITE if not is_dark else ft.Colors.GREY_800),
                    width=320, height=42,
                    on_click=lambda _, val=m: pick_sched(val)
                ) for m in intervals
            ]

            active_panel = ft.Container(
                content=ft.Column([
                    ft.Row([
                        ft.Row([ft.Icon(ft.Icons.SCHEDULE, color=ft.Colors.BLUE_700), ft.Text("Choose Reminder Interval", size=15, weight=ft.FontWeight.BOLD, color=txt_main)], spacing=6),
                        ft.IconButton(icon=ft.Icons.CLOSE, on_click=close_active_panel)
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    ft.Text("Select how often you would like to be reminded to drink water:", size=12, color=txt_sub),
                    ft.Column(sched_buttons, spacing=6, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                    ft.Container(height=4)
                ], spacing=8),
                padding=14, bgcolor=panel_bg, border_radius=14, border=make_border(1.5, ft.Colors.BLUE_400)
            )

        elif active_setting_view[0] == "sound":
            sound_rows = []
            for opt in RINGTONE_OPTIONS:
                sid = opt["id"]
                is_sel = (sid == cur_sound_id)

                def make_sel(target_id=sid):
                    def handler(e):
                        db_set_setting("reminder_sound", target_id)
                        play_ringtone_sound(target_id)
                        active_setting_view[0] = None
                        show_profile_settings_screen()
                    return handler

                def make_prev(target_id=sid):
                    def handler(e):
                        play_ringtone_sound(target_id)
                    return handler

                sound_rows.append(
                    ft.Container(
                        content=ft.Row([
                            ft.Text(opt["icon"], size=22),
                            ft.Column([
                                ft.Text(opt["name"], size=13, weight=ft.FontWeight.BOLD if is_sel else ft.FontWeight.NORMAL, color=txt_main),
                                ft.Text(opt["desc"], size=10, color=txt_sub)
                            ], expand=True, spacing=1),
                            ft.IconButton(icon=ft.Icons.PLAY_CIRCLE_FILL, icon_color=ft.Colors.BLUE_700, tooltip="Play Preview", on_click=make_prev()),
                            ft.Button(
                                content=ft.Text("✓ Selected" if is_sel else "Select", size=11, color=ft.Colors.WHITE if is_sel else None),
                                bgcolor=ft.Colors.GREEN_700 if is_sel else None,
                                on_click=make_sel()
                            )
                        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                        padding=8, border_radius=10, bgcolor=ft.Colors.BLUE_100 if (is_sel and not is_dark) else (ft.Colors.GREY_800 if is_sel else None),
                        border=make_border(1.5 if is_sel else 1, ft.Colors.BLUE_600 if is_sel else ft.Colors.GREY_300)
                    )
                )

            active_panel = ft.Container(
                content=ft.Column([
                    ft.Row([
                        ft.Row([ft.Icon(ft.Icons.MUSIC_NOTE, color=ft.Colors.BLUE_700), ft.Text("Choose Reminder Sound", size=15, weight=ft.FontWeight.BOLD, color=txt_main)], spacing=6),
                        ft.IconButton(icon=ft.Icons.CLOSE, on_click=close_active_panel)
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    ft.Text("Tap preview to listen, tap Select to set your alarm tone:", size=12, color=txt_sub),
                    ft.Column(sound_rows, spacing=6),
                    ft.Container(height=4)
                ], spacing=8),
                padding=14, bgcolor=panel_bg, border_radius=14, border=make_border(1.5, ft.Colors.BLUE_400)
            )

        elif active_setting_view[0] == "mode":
            modes = ["Sound and vibrate", "Sound only", "Vibrate only", "Silent"]
            def pick_mode(m):
                db_set_setting("reminder_mode", m)
                active_setting_view[0] = None
                show_profile_settings_screen()

            mode_buttons = [
                ft.Button(
                    content=ft.Row([
                        ft.Icon(ft.Icons.CHECK if m == cur_mode else ft.Icons.NOTIFICATIONS, size=16, color=ft.Colors.WHITE if m == cur_mode else ft.Colors.BLUE_700),
                        ft.Text(m, size=13, color=ft.Colors.WHITE if m == cur_mode else txt_main, weight=ft.FontWeight.BOLD if m == cur_mode else ft.FontWeight.NORMAL)
                    ], alignment=ft.MainAxisAlignment.CENTER, spacing=6),
                    bgcolor=ft.Colors.BLUE_700 if m == cur_mode else (ft.Colors.WHITE if not is_dark else ft.Colors.GREY_800),
                    width=320, height=42,
                    on_click=lambda _, val=m: pick_mode(val)
                ) for m in modes
            ]

            active_panel = ft.Container(
                content=ft.Column([
                    ft.Row([
                        ft.Row([ft.Icon(ft.Icons.TUNE, color=ft.Colors.BLUE_700), ft.Text("Reminder Alert Mode", size=15, weight=ft.FontWeight.BOLD, color=txt_main)], spacing=6),
                        ft.IconButton(icon=ft.Icons.CLOSE, on_click=close_active_panel)
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    ft.Column(mode_buttons, spacing=6, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                    ft.Container(height=4)
                ], spacing=8),
                padding=14, bgcolor=panel_bg, border_radius=14, border=make_border(1.5, ft.Colors.BLUE_400)
            )

        elif active_setting_view[0] == "goal":
            goal_in = ft.TextField(label="Daily Water Goal (ml)", value=str(target_ml), keyboard_type=ft.KeyboardType.NUMBER)
            def save_goal_panel(e):
                try:
                    new_ml = int(goal_in.value)
                    new_l = round(new_ml / 1000.0, 2)
                    user_session["water_target"] = new_l
                    if user_session.get("id"):
                        with sqlite3.connect(DB_NAME, timeout=15) as conn:
                            conn.execute("UPDATE accounts SET daily_water_liters = ? WHERE id = ?", (new_l, int(user_session["id"])))
                            conn.commit()
                except Exception:
                    pass
                active_setting_view[0] = None
                show_profile_settings_screen()

            active_panel = ft.Container(
                content=ft.Column([
                    ft.Row([
                        ft.Row([ft.Icon(ft.Icons.EDIT, color=ft.Colors.BLUE_700), ft.Text("Custom Intake Goal", size=15, weight=ft.FontWeight.BOLD, color=txt_main)], spacing=6),
                        ft.IconButton(icon=ft.Icons.CLOSE, on_click=close_active_panel)
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    goal_in,
                    ft.Button(content=ft.Text("Save Goal", color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD), bgcolor=ft.Colors.BLUE_700, width=280, height=44, on_click=save_goal_panel)
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=10),
                padding=14, bgcolor=panel_bg, border_radius=14, border=make_border(1.5, ft.Colors.BLUE_400)
            )

        elif active_setting_view[0] == "faq":
            active_panel = ft.Container(
                content=ft.Column([
                    ft.Row([
                        ft.Row([ft.Icon(ft.Icons.HELP, color=ft.Colors.BLUE_700), ft.Text("Why does Reminder not work?", size=15, weight=ft.FontWeight.BOLD, color=txt_main)], spacing=6),
                        ft.IconButton(icon=ft.Icons.CLOSE, on_click=close_active_panel)
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    ft.Text("To ensure alarms ring on time in the background:", weight=ft.FontWeight.BOLD, size=13, color=txt_main),
                    ft.Text("1. Settings > Apps > HealthTrack > Battery > Set to 'Unrestricted / Don't Optimize'.", size=12, color=txt_sub),
                    ft.Text("2. Allow 'Autostart' or 'Background Activity'.", size=12, color=txt_sub),
                    ft.Text("3. Enable 'Allow Notifications' with sound and vibration enabled.", size=12, color=txt_sub),
                    ft.Text("4. Ensure your device is not in Silent or Do Not Disturb (DND) mode.", size=12, color=txt_sub),
                    ft.Button(content=ft.Text("Got it / OK", color=ft.Colors.WHITE), bgcolor=ft.Colors.BLUE_700, width=200, on_click=close_active_panel)
                ], spacing=8),
                padding=14, bgcolor=panel_bg, border_radius=14, border=make_border(1.5, ft.Colors.BLUE_400)
            )

        elif active_setting_view[0] == "privacy":
            active_panel = ft.Container(
                content=ft.Column([
                    ft.Row([
                        ft.Row([ft.Icon(ft.Icons.SECURITY, color=ft.Colors.GREEN_700), ft.Text("Privacy Policy", size=15, weight=ft.FontWeight.BOLD, color=txt_main)], spacing=6),
                        ft.IconButton(icon=ft.Icons.CLOSE, on_click=close_active_panel)
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    ft.Text("1. 100% Offline: All hydration logs, schedules and prescription records remain exclusively on your device.", size=12, color=txt_sub),
                    ft.Text("2. Zero Data Uploads: Your personal data, metrics and prescription photos are never sent to external servers or sold.", size=12, color=txt_sub),
                    ft.Text("3. Local Alarms: Reminder notifications and ringtones are generated locally by your operating system.", size=12, color=txt_sub),
                    ft.Text("4. Security: Your health data belongs entirely to you.", size=12, color=txt_sub),
                    ft.Button(content=ft.Text("Close Policy", color=ft.Colors.WHITE), bgcolor=ft.Colors.BLUE_700, width=200, on_click=close_active_panel)
                ], spacing=8),
                padding=14, bgcolor=panel_bg, border_radius=14, border=make_border(1.5, ft.Colors.GREEN_600)
            )

        elif active_setting_view[0] == "feedback":
            user_stars = [int(db_get_setting("user_rating", "5"))]
            rating_labels = {
                1: "⭐ Needs Improvement (1/5)",
                2: "⭐⭐ Fair (2/5)",
                3: "⭐⭐⭐ Good (3/5)",
                4: "⭐⭐⭐⭐ Very Good (4/5)",
                5: "⭐⭐⭐⭐⭐ Excellent (5/5)"
            }

            stars_row = ft.Row(alignment=ft.MainAxisAlignment.CENTER, spacing=4)
            rating_desc_text = ft.Text(rating_labels.get(user_stars[0], "⭐⭐⭐⭐⭐ Excellent (5/5)"), size=14, weight=ft.FontWeight.BOLD, color=ft.Colors.AMBER_800 if not is_dark else ft.Colors.AMBER_400)
            feed_txt = ft.TextField(label="Your Feedback / Suggestion (Optional)", multiline=True, min_lines=2)
            fb_status = ft.Text("", size=12, color=ft.Colors.GREEN_700, weight=ft.FontWeight.BOLD)
            submit_btn_text = ft.Text(f"⭐ Submit Rating ({user_stars[0]} Stars)", color=ft.Colors.WHITE, weight=ft.FontWeight.BOLD)

            def render_interactive_stars():
                stars_row.controls.clear()
                for idx in range(1, 6):
                    is_filled = (idx <= user_stars[0])
                    def make_star_click(star_num=idx):
                        def on_star_click(e):
                            user_stars[0] = star_num
                            rating_desc_text.value = rating_labels.get(star_num, f"{star_num}/5")
                            submit_btn_text.value = f"⭐ Submit Rating ({star_num} Star{'s' if star_num > 1 else ''})"
                            render_interactive_stars()
                            page.update()
                        return on_star_click

                    star_btn = ft.IconButton(
                        icon=ft.Icons.STAR if is_filled else ft.Icons.STAR_BORDER,
                        icon_color=ft.Colors.AMBER if is_filled else ft.Colors.GREY_400,
                        icon_size=32,
                        tooltip=f"Rate {idx} Star{'s' if idx > 1 else ''}",
                        on_click=make_star_click(idx)
                    )
                    stars_row.controls.append(star_btn)

            render_interactive_stars()

            def do_feed(ev):
                chosen_stars = user_stars[0]
                db_set_setting("user_rating", str(chosen_stars))
                fb_status.value = f"✓ Thank you! You rated {chosen_stars} Star{'s' if chosen_stars > 1 else ''}."
                page.update()
                time.sleep(0.5)
                if chosen_stars >= 4:
                    try:
                        if hasattr(page, "launch_url"):
                            page.launch_url("https://play.google.com/store/apps/details?id=com.healthtrack.water")
                    except Exception:
                        pass
                active_setting_view[0] = None
                show_profile_settings_screen()

            active_panel = ft.Container(
                content=ft.Column([
                    ft.Row([
                        ft.Row([ft.Icon(ft.Icons.STAR, color=ft.Colors.AMBER_600), ft.Text("Rate & Feedback", size=15, weight=ft.FontWeight.BOLD, color=txt_main)], spacing=6),
                        ft.IconButton(icon=ft.Icons.CLOSE, on_click=close_active_panel)
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    ft.Text("Tap on any star (1 to 5) to set your rating:", size=12, color=txt_sub),
                    stars_row,
                    rating_desc_text,
                    feed_txt,
                    fb_status,
                    ft.Button(content=submit_btn_text, bgcolor=ft.Colors.AMBER_800, width=280, height=44, on_click=do_feed)
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=8),
                padding=14, bgcolor=panel_bg, border_radius=14, border=make_border(1.5, ft.Colors.AMBER_600)
            )

        elif active_setting_view[0] == "share":
            active_panel = ft.Container(
                content=ft.Column([
                    ft.Row([
                        ft.Row([ft.Icon(ft.Icons.SHARE, color=ft.Colors.BLUE_700), ft.Text("Share HealthTrack", size=15, weight=ft.FontWeight.BOLD, color=txt_main)], spacing=6),
                        ft.IconButton(icon=ft.Icons.CLOSE, on_click=close_active_panel)
                    ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                    ft.Text("Share this smart water intake & medicine reminder app with family and friends:", size=12, color=txt_sub),
                    ft.TextField(value="Download HealthTrack - Smart Hydration & Medicine Tracker: https://play.google.com/store/apps/details?id=com.healthtrack.water", read_only=True),
                    ft.Button(content=ft.Text("Copy Link / Done", color=ft.Colors.WHITE), bgcolor=ft.Colors.BLUE_700, width=200, on_click=close_active_panel)
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=8),
                padding=14, bgcolor=panel_bg, border_radius=14, border=make_border(1.5, ft.Colors.BLUE_400)
            )

        def make_section_header(title):
            return ft.Container(
                content=ft.Text(title, size=13, weight=ft.FontWeight.BOLD, color=ft.Colors.GREY_500),
                padding=make_padding(left=4, top=16, bottom=4)
            )

        def make_setting_row(title, subtitle=None, value_text=None, trailing_widget=None, on_click=None):
            left_col = [ft.Text(title, size=15, weight=ft.FontWeight.W_500, color=txt_main)]
            if subtitle:
                left_col.append(ft.Text(subtitle, size=12, color=txt_sub))

            right_items = []
            if value_text:
                right_items.append(ft.Text(value_text, size=14, color=ft.Colors.BLUE_700 if not is_dark else ft.Colors.BLUE_300, weight=ft.FontWeight.W_500))
            if trailing_widget:
                right_items.append(trailing_widget)

            return ft.Container(
                content=ft.Row([
                    ft.Column(left_col, spacing=2, expand=True),
                    ft.Row(right_items, spacing=6, vertical_alignment=ft.CrossAxisAlignment.CENTER)
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                padding=make_padding(horizontal=8, vertical=12),
                border=ft.Border(bottom=ft.BorderSide(1, border_c)),
                on_click=on_click
            )

        # Setting Handlers (Toggles active in-page panel AND opens dialog)
        def trigger_sched(e):
            active_setting_view[0] = "schedule" if active_setting_view[0] != "schedule" else None
            show_profile_settings_screen()

        def trigger_sound(e):
            active_setting_view[0] = "sound" if active_setting_view[0] != "sound" else None
            show_profile_settings_screen()

        def trigger_mode(e):
            active_setting_view[0] = "mode" if active_setting_view[0] != "mode" else None
            show_profile_settings_screen()

        def trigger_goal(e):
            active_setting_view[0] = "goal" if active_setting_view[0] != "goal" else None
            show_profile_settings_screen()

        def trigger_faq(e):
            active_setting_view[0] = "faq" if active_setting_view[0] != "faq" else None
            show_profile_settings_screen()

        def trigger_privacy(e):
            active_setting_view[0] = "privacy" if active_setting_view[0] != "privacy" else None
            show_profile_settings_screen()

        def trigger_feedback(e):
            active_setting_view[0] = "feedback" if active_setting_view[0] != "feedback" else None
            show_profile_settings_screen()

        def trigger_share(e):
            active_setting_view[0] = "share" if active_setting_view[0] != "share" else None
            show_profile_settings_screen()

        # 1. Reminder settings
        reminder_schedule_row = make_setting_row(
            "Reminder schedule",
            subtitle=f"Every {interval_min} minutes ({user_session['wake_t']} - {user_session['sleep_t']})",
            value_text=f"{interval_min} min",
            trailing_widget=ft.Icon(ft.Icons.ARROW_FORWARD_IOS, size=14, color=ft.Colors.BLUE_700),
            on_click=trigger_sched
        )

        reminder_sound_row = make_setting_row(
            "Reminder sound",
            subtitle="Water droplets, gentle rain, zen chime, or bell",
            value_text=cur_sound_display,
            trailing_widget=ft.Icon(ft.Icons.ARROW_FORWARD_IOS, size=14, color=ft.Colors.BLUE_700),
            on_click=trigger_sound
        )

        reminder_mode_row = make_setting_row(
            "Reminder mode",
            value_text=cur_mode,
            trailing_widget=ft.Icon(ft.Icons.ARROW_FORWARD_IOS, size=14, color=ft.Colors.BLUE_700),
            on_click=trigger_mode
        )

        further_switch = ft.Switch(value=True)
        further_reminder_row = make_setting_row(
            "Further reminder",
            subtitle="Still remind when your goal is achieved",
            trailing_widget=further_switch
        )

        # 2. General
        interface_mode_row = make_setting_row(
            "Light or dark interface",
            value_text="Dark" if is_dark else "Light",
            trailing_widget=ft.Icon(ft.Icons.DARK_MODE if not is_dark else ft.Icons.LIGHT_MODE, size=16, color=ft.Colors.BLUE_700),
            on_click=toggle_theme_action
        )

        unit_row = make_setting_row("Unit", value_text="kg, ml")

        intake_goal_row = make_setting_row(
            "Intake goal",
            value_text=f"{target_ml} ml",
            trailing_widget=ft.Icon(ft.Icons.EDIT, size=14, color=ft.Colors.BLUE_700),
            on_click=trigger_goal
        )

        language_row = make_setting_row(
            "Language",
            value_text="English",
            trailing_widget=ft.Icon(ft.Icons.LANGUAGE, size=16, color=ft.Colors.BLUE_700)
        )

        # 3. Personal information
        gender_row = make_setting_row("Gender", value_text=user_session["gender"], on_click=lambda _: show_onboarding_flow(step=1))
        weight_row = make_setting_row("Weight", value_text=f"{int(user_session['weight'])} kg", on_click=lambda _: show_onboarding_flow(step=2))
        wake_row = make_setting_row("Wake-up time", value_text=user_session["wake_t"].lower(), on_click=lambda _: show_onboarding_flow(step=3))
        bed_row = make_setting_row("Bedtime", value_text=user_session["sleep_t"].lower(), on_click=lambda _: show_onboarding_flow(step=4))

        edit_profile_btn = ft.Container(
            content=ft.Row([
                ft.Icon(ft.Icons.TUNE_ROUNDED, color=ft.Colors.BLUE_700),
                ft.Text("Personal hydration plan (Recalculate)", size=14, weight=ft.FontWeight.BOLD, color=ft.Colors.BLUE_700)
            ], spacing=8),
            padding=make_padding(horizontal=8, vertical=12),
            border=ft.Border(bottom=ft.BorderSide(1, border_c)),
            on_click=lambda _: show_onboarding_flow(step=1)
        )

        # 4. Other
        app_perm_row = make_setting_row(
            "App permissions",
            subtitle="Notifications 🔔 • Camera 📸 • Audio 🔊 • Battery ⚡",
            value_text="Granted",
            trailing_widget=ft.Icon(ft.Icons.VERIFIED_USER_ROUNDED, size=16, color=ft.Colors.GREEN_700),
            on_click=lambda _: show_permissions_screen(is_review=True)
        )

        tips_switch = ft.Switch(value=False)
        tips_row = make_setting_row(
            "Hide tips on how to drink water",
            trailing_widget=tips_switch
        )

        faq_row = make_setting_row(
            "Why does Drink Water Reminder not work?",
            trailing_widget=ft.Icon(ft.Icons.HELP_OUTLINE, size=16, color=ft.Colors.BLUE_700),
            on_click=trigger_faq
        )

        def confirm_reset_data(e):
            def do_reset(ev):
                safe_close_dialog(res_dlg)
                db_reset_today_water(user_session["id"], datetime.date.today().isoformat())
                show_onboarding_flow(step=1)

            res_dlg = ft.AlertDialog(
                title=ft.Text("Reset Data"),
                content=ft.Text("Are you sure you want to reset all water intake records and restart your hydration plan from scratch?"),
                actions=[
                    ft.TextButton("Cancel", on_click=lambda _: safe_close_dialog(res_dlg)),
                    ft.Button(content=ft.Text("Yes, Reset", color=ft.Colors.WHITE), bgcolor=ft.Colors.RED_600, on_click=do_reset)
                ]
            )
            safe_open_dialog(res_dlg)

        reset_data_row = make_setting_row(
            "Reset data",
            trailing_widget=ft.Icon(ft.Icons.RESTORE, size=16, color=ft.Colors.RED_600),
            on_click=confirm_reset_data
        )

        feedback_row = make_setting_row(
            "Feedback & Rating",
            subtitle=f"Tap to rate (Currently: {db_get_setting('user_rating', '5')} Stars)",
            trailing_widget=ft.Icon(ft.Icons.STAR, size=16, color=ft.Colors.AMBER_600),
            on_click=trigger_feedback
        )

        share_row = make_setting_row(
            "Share",
            trailing_widget=ft.Icon(ft.Icons.SHARE, size=16, color=ft.Colors.BLUE_700),
            on_click=trigger_share
        )

        privacy_row = make_setting_row(
            "Privacy policy",
            trailing_widget=ft.Icon(ft.Icons.SECURITY, size=16, color=ft.Colors.GREEN_700),
            on_click=trigger_privacy
        )

        logout_row = make_setting_row(
            "Logout",
            trailing_widget=ft.Icon(ft.Icons.LOGOUT, size=16, color=ft.Colors.RED_600),
            on_click=user_logout_action
        )

        settings_container = ft.Container(
            content=ft.Column([
                active_panel if active_panel else ft.Container(height=0),
                make_section_header("Reminder settings"),
                reminder_schedule_row,
                reminder_sound_row,
                reminder_mode_row,
                further_reminder_row,

                make_section_header("General"),
                interface_mode_row,
                unit_row,
                intake_goal_row,
                language_row,

                make_section_header("Personal information"),
                gender_row,
                weight_row,
                wake_row,
                bed_row,
                edit_profile_btn,

                make_section_header("Other"),
                app_perm_row,
                tips_row,
                faq_row,
                reset_data_row,
                feedback_row,
                share_row,
                privacy_row,
                logout_row,
                ft.Container(height=30)
            ], spacing=0),
            bgcolor=card_bg,
            border_radius=16,
            padding=make_padding(left=14, right=14, top=4)
        )

        page.add(
            ft.SafeArea(
                ft.Column([
                    top_bar,
                    settings_container
                ], spacing=0)
            )
        )

        # SCREEN 4: HISTORY (EXACTLY AS SCREENSHOT histroy.jpeg)
    # -------------------------------------------------------------
    def show_history_screen():
        active_ticker_token[0] += 1
        timer_cancel_event.set()
        page.clean()

        is_dark = (page.theme_mode == ft.ThemeMode.DARK)
        txt_main = ft.Colors.WHITE if is_dark else ft.Colors.BLACK
        card_bg = ft.Colors.GREY_900 if is_dark else ft.Colors.WHITE
        border_c = ft.Colors.GREY_800 if is_dark else ft.Colors.BLUE_GREY_100

        top_bar = get_top_app_bar(selected_idx=2)
        logs = db_get_past_water_logs(user_session["id"], 30)

        # Calculate reports
        total_days = max(1, len(logs))
        sum_l = sum(l[2] for l in logs) if logs else 0.0
        avg_ml = int((sum_l / total_days) * 1000)
        target_ml = int(round(user_session["water_target"] * 1000))
        avg_pct = int(min(1.0, (avg_ml / max(target_ml, 1))) * 100)

        now_m_name = datetime.date.today().strftime("%B %Y")

        month_selector = ft.Row([
            ft.IconButton(icon=ft.Icons.ARROW_BACK_IOS, icon_size=16),
            ft.Text(now_m_name, size=16, weight=ft.FontWeight.BOLD, color=txt_main),
            ft.IconButton(icon=ft.Icons.ARROW_FORWARD_IOS, icon_size=16),
        ], alignment=ft.MainAxisAlignment.CENTER, spacing=15)

        # Graph mockup / Bar chart
        bar_chart_card = ft.Container(
            content=ft.Column([
                month_selector,
                ft.Container(
                    content=ft.Column([
                        ft.Row([
                            ft.Text("100%", size=10, color=ft.Colors.GREY_500),
                            ft.Container(height=1, bgcolor=ft.Colors.GREY_200, expand=True)
                        ]),
                        ft.Row([
                            ft.Text("80%", size=10, color=ft.Colors.GREY_500),
                            ft.Container(height=1, bgcolor=ft.Colors.GREY_200, expand=True)
                        ]),
                        ft.Row([
                            ft.Text("60%", size=10, color=ft.Colors.GREY_500),
                            ft.Container(height=1, bgcolor=ft.Colors.GREY_200, expand=True)
                        ]),
                        ft.Row([
                            ft.Text("40%", size=10, color=ft.Colors.GREY_500),
                            ft.Container(height=1, bgcolor=ft.Colors.GREY_200, expand=True)
                        ]),
                        ft.Row([
                            ft.Text("20%", size=10, color=ft.Colors.GREY_500),
                            ft.Container(height=1, bgcolor=ft.Colors.GREY_200, expand=True)
                        ]),
                        ft.Row([
                            ft.Text("0%", size=10, color=ft.Colors.GREY_500),
                            ft.Container(height=1, bgcolor=ft.Colors.GREY_300, expand=True)
                        ]),
                        ft.Row([
                            ft.Text("4 Oct", size=10, color=ft.Colors.GREY_500),
                            ft.Text("11", size=10, color=ft.Colors.GREY_500),
                            ft.Text("18", size=10, color=ft.Colors.GREY_500),
                            ft.Text("25", size=10, color=ft.Colors.GREY_500),
                        ], alignment=ft.MainAxisAlignment.SPACE_AROUND)
                    ], spacing=10),
                    padding=10
                ),
                ft.Row([
                    ft.Button(content=ft.Text("Month", size=12), bgcolor=ft.Colors.BLUE_50),
                    ft.Button(content=ft.Text("Year", size=12), bgcolor=ft.Colors.BLUE_700),
                    ft.TextButton("+ Add record", on_click=lambda _: show_dashboard())
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)
            ]),
            padding=12, bgcolor=card_bg, border_radius=14, border=make_border(1, border_c)
        )

        # Weekly completion card (7 blue circles as in histroy.jpeg)
        days_names = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
        cur_day_idx = datetime.date.today().weekday()
        # Monday is 0 in python, convert to Sun=0
        cur_day_sun = (cur_day_idx + 1) % 7

        week_circles = []
        for d_idx, d_name in enumerate(days_names):
            is_done = (d_idx <= cur_day_sun)
            week_circles.append(
                ft.Column([
                    ft.Container(
                        content=ft.Icon(ft.Icons.CHECK, size=14, color=ft.Colors.WHITE) if is_done else None,
                        width=36, height=36, border_radius=18,
                        bgcolor=ft.Colors.BLUE_700 if is_done else ft.Colors.BLUE_100,
                        alignment=ft.Alignment(0, 0)
                    ),
                    ft.Text(d_name, size=11, color=ft.Colors.WHITE)
                ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=4)
            )

        weekly_card = ft.Container(
            content=ft.Column([
                ft.Text("Weekly completion", size=14, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE),
                ft.Row(week_circles, alignment=ft.MainAxisAlignment.SPACE_AROUND)
            ], spacing=10),
            padding=14, bgcolor=ft.Colors.BLUE_700, border_radius=14
        )

        # Drink water report (Weekly avg, Monthly avg, Average completion)
        report_card = ft.Container(
            content=ft.Column([
                ft.Text("Drink water report", size=14, weight=ft.FontWeight.BOLD, color=txt_main),
                ft.Row([
                    ft.Row([
                        ft.Container(width=10, height=10, border_radius=5, bgcolor=ft.Colors.GREEN_600),
                        ft.Text("Weekly average", size=13, color=txt_main)
                    ], spacing=6),
                    ft.Text(f"{avg_ml} ml / day", size=13, color=ft.Colors.BLUE_700, weight=ft.FontWeight.BOLD)
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                ft.Divider(height=1),
                ft.Row([
                    ft.Row([
                        ft.Container(width=10, height=10, border_radius=5, bgcolor=ft.Colors.BLUE_600),
                        ft.Text("Monthly average", size=13, color=txt_main)
                    ], spacing=6),
                    ft.Text(f"{avg_ml} ml / day", size=13, color=ft.Colors.BLUE_700, weight=ft.FontWeight.BOLD)
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                ft.Divider(height=1),
                ft.Row([
                    ft.Row([
                        ft.Container(width=10, height=10, border_radius=5, bgcolor=ft.Colors.ORANGE_600),
                        ft.Text("Average completion", size=13, color=txt_main)
                    ], spacing=6),
                    ft.Text(f"{avg_pct} %", size=13, color=ft.Colors.BLUE_700, weight=ft.FontWeight.BOLD)
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)
            ], spacing=10),
            padding=14, bgcolor=card_bg, border_radius=14, border=make_border(1, border_c)
        )

        page.add(
            ft.SafeArea(
                ft.Column([
                    top_bar,
                    ft.Container(
                        content=ft.Column([
                            bar_chart_card,
                            weekly_card,
                            report_card,
                            ft.Container(height=20)
                        ], spacing=10),
                        padding=12
                    )
                ], spacing=0)
            )
        )

    # -------------------------------------------------------------
    # LOGIN & REGISTER
    # -------------------------------------------------------------
    def show_login_screen():
        active_ticker_token[0] += 1
        timer_cancel_event.set()
        page.clean()

        is_dark = (page.theme_mode == ft.ThemeMode.DARK)
        txt_main = ft.Colors.WHITE if is_dark else ft.Colors.BLACK

        login_ident = ft.TextField(label="Mobile Number or Email", prefix_icon=ft.Icons.PERSON, autofocus=True)
        login_pass = ft.TextField(label="Password", password=True, can_reveal_password=True, prefix_icon=ft.Icons.LOCK)
        login_status = ft.Text("", color=ft.Colors.RED_600)

        def login_action(e):
            res = db_authenticate(login_ident.value or "", login_pass.value or "")
            if res:
                user_session["id"] = res[0]
                user_session["username"] = res[1] or "Gaurav"
                user_session["email"] = res[2] or ""
                user_session["phone"] = res[3] or ""
                user_session["gender"] = res[4] or "Male"
                user_session["weight"] = res[5] or 70.0
                user_session["age"] = res[6] or 28
                user_session["sleep_t"] = res[7] or "11:00 PM"
                user_session["wake_t"] = res[8] or "08:00 AM"
                user_session["water_target"] = res[9] or 2.03
                user_session["water_cup_ml"] = res[10] or 203
                user_session["streak"] = res[11] or 1
                user_session["rating_shown"] = res[13] or 0
                user_session["height"] = res[14] if len(res) > 14 and res[14] else 170.0
                user_session["photo_path"] = res[15] if len(res) > 15 and res[15] else ""

                db_set_active_session(user_session["id"])
                show_dashboard()
            else:
                login_status.value = "Incorrect username or password!"
                page.update()

        page.add(
            ft.SafeArea(
                ft.Container(
                    content=ft.Column([
                        ft.Row([
                            ft.IconButton(icon=ft.Icons.LIGHT_MODE if page.theme_mode == ft.ThemeMode.DARK else ft.Icons.DARK_MODE, on_click=toggle_theme_action),
                            ft.Button(content=ft.Text("🌐 English"), on_click=toggle_language_action)
                        ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                        ft.Container(
                            content=ft.Column([
                                make_safe_image("icon.png", width=85, height=85, fit="contain", fallback_icon=ft.Icons.WATER_DROP_ROUNDED, fallback_color=ft.Colors.BLUE_700),
                                ft.Text("HealthTrack", size=24, weight=ft.FontWeight.BOLD, color=txt_main),
                                ft.Text("Smart Water Reminder & Health Engine", size=13, color=ft.Colors.GREY_500),
                            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=4),
                            alignment=ft.Alignment(0, 0),
                            padding=15
                        ),
                        login_ident, login_pass, login_status,
                        ft.Button(content=ft.Text("LOG IN", color=ft.Colors.WHITE, size=15), bgcolor=ft.Colors.BLUE_700, width=400, height=48, on_click=login_action),
                        ft.TextButton("New User? Start Personal Hydration Plan", on_click=lambda _: show_register_screen())
                    ], spacing=10),
                    padding=16
                )
            )
        )

    def show_register_screen():
        active_ticker_token[0] += 1
        timer_cancel_event.set()
        page.clean()

        reg_user = ft.TextField(label="Full Name", prefix_icon=ft.Icons.PERSON, autofocus=True)
        reg_email = ft.TextField(label="Email Address", prefix_icon=ft.Icons.EMAIL, keyboard_type=ft.KeyboardType.EMAIL)
        reg_phone = ft.TextField(label="Mobile (10 digits)", prefix_icon=ft.Icons.PHONE, max_length=10, keyboard_type=ft.KeyboardType.PHONE)
        reg_pass = ft.TextField(label="Password", password=True, can_reveal_password=True, prefix_icon=ft.Icons.LOCK)
        reg_status = ft.Text("", size=12)

        def register_action(e):
            u_name = reg_user.value.strip() if reg_user.value else "Gaurav"
            w_str = f"{onboarding_state['wake_hour']:02d}:00 AM"
            b_str = f"{onboarding_state['bed_hour']:02d}:00 PM"
            ok, msg, uid = db_register_simple(
                u_name, reg_pass.value or "WaterPass123!", reg_email.value or "", reg_phone.value or "",
                onboarding_state["gender"], onboarding_state["weight_kg"], 28, w_str, b_str
            )
            if ok:
                user_session["id"] = uid
                user_session["username"] = u_name
                user_session["phone"] = reg_phone.value or ""
                user_session["email"] = reg_email.value or ""
                db_set_active_session(uid)
                show_dashboard()
            else:
                reg_status.value = msg
                reg_status.color = ft.Colors.RED_600
                page.update()

        page.add(
            ft.SafeArea(
                ft.Container(
                    content=ft.Column([
                        ft.Row([
                            ft.IconButton(icon=ft.Icons.ARROW_BACK, on_click=lambda _: show_login_screen()),
                            ft.Text("Sign Up", size=18, weight=ft.FontWeight.BOLD)
                        ], spacing=6),
                        reg_user, reg_email, reg_phone, reg_pass, reg_status,
                        ft.Button(content=ft.Text("Create Account & Set Plan", color=ft.Colors.WHITE), bgcolor=ft.Colors.BLUE_700, width=400, height=48, on_click=register_action),
                        ft.TextButton("Already have an account? Log In", on_click=lambda _: show_login_screen())
                    ], spacing=10),
                    padding=16
                )
            )
        )

    # Auto-login check
    # 1. On initial install / launch, show Permissions Consent Popup first!
    if db_get_setting("permissions_granted", "0") == "0":
        show_permissions_screen(is_review=False)
        return

    # 2. Existing session check
    active_uid = db_get_active_session()
    if active_uid:
        user_row = db_get_user_by_id(active_uid)
        if user_row:
            user_session["id"] = user_row[0]
            user_session["username"] = user_row[1]
            user_session["email"] = user_row[2] or ""
            user_session["phone"] = user_row[3] or ""
            user_session["gender"] = user_row[4] or "Male"
            user_session["weight"] = user_row[5] or 70.0
            user_session["age"] = user_row[6] or 28
            user_session["sleep_t"] = user_row[7] or "11:00 PM"
            user_session["wake_t"] = user_row[8] or "08:00 AM"
            user_session["water_target"] = user_row[9] or 2.03
            user_session["water_cup_ml"] = user_row[10] or 203
            user_session["streak"] = user_row[11] or 1
            user_session["rating_shown"] = user_row[13] or 0
            user_session["height"] = user_row[14] if len(user_row) > 14 and user_row[14] else 170.0
            user_session["photo_path"] = user_row[15] if len(user_row) > 15 and user_row[15] else ""

            show_dashboard()
            return

    show_onboarding_flow(step=1)

if __name__ == "__main__":
    assets_dir_path = "assets" if os.path.exists("assets") else None
    if hasattr(ft, "run"):
        try:
            ft.run(main, assets_dir=assets_dir_path)
        except Exception:
            try:
                ft.run(target=main, assets_dir=assets_dir_path)
            except Exception:
                ft.run(main)
    elif hasattr(ft, "app"):
        try:
            ft.app(target=main, assets_dir=assets_dir_path)
        except Exception:
            try:
                ft.app(main, assets_dir=assets_dir_path)
            except Exception:
                ft.app(main)
    else:
        flet_entry = getattr(ft, "run", getattr(ft, "app", None))
        if flet_entry:
            try:
                flet_entry(main, assets_dir=assets_dir_path)
            except Exception:
                flet_entry(target=main)