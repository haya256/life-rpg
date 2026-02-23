#!/usr/bin/env python3
"""データ管理 — RPGデータの読み書きとログ記録"""

import json
from pathlib import Path

from rpg_ui import get_current_date, get_current_time

SCRIPT_DIR = Path(__file__).parent
SAVE_DIR = SCRIPT_DIR / "savedata"
SAVE_DIR.mkdir(exist_ok=True)  # 初回起動時に自動作成
DATA_FILE = SAVE_DIR / "rpg_data.json"
SAMPLE_DATA_FILE = SCRIPT_DIR / "sample_data.json"
LOG_FILE = SAVE_DIR / "ADVENTURE_LOG.md"


def load_data():
    """RPGデータを読み込む"""
    if DATA_FILE.exists():
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if "chests" not in data:
            data["chests"] = []
        if "gold" not in data["hero"]:
            data["hero"]["gold"] = 0
        return data

    # 初回起動：サンプルデータで初期化
    data = {
        "field_tasks": {},
        "quests": [],
        "chests": [],
        "hero": {
            "level": 1,
            "exp": 0,
            "gold": 0,
            "total_battles": 0,
            "total_victories": 0,
            "quests_completed": 0
        },
        "field_state": {
            "exploring": False,
            "current_encounter": None,
            "current_category": None,
            "session_encounters": [],
            "session_victories": 0
        }
    }

    if SAMPLE_DATA_FILE.exists():
        with open(SAMPLE_DATA_FILE, 'r', encoding='utf-8') as f:
            sample = json.load(f)
        data["field_tasks"] = sample.get("field_tasks", {})
        data["quests"] = sample.get("quests", [])

    save_data(data)
    return data


def save_data(data):
    """RPGデータを保存"""
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def log_adventure(category, message, symbol="⚔️"):
    """冒険の記録をログの末尾に追記"""
    if not LOG_FILE.exists():
        LOG_FILE.write_text("# 冒険の記録\n", encoding='utf-8')

    date = get_current_date()
    time = get_current_time()
    entry = f"{date} {time} [{category}] {message} {symbol}\n"

    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(entry)
