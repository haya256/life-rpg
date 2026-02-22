"""
patch.py — rpg.py 読み込み後に適用するオーバーライド

rpg.py で定義された関数を Web 向けに差し替えます:
  - getch / animated_getch  → SharedArrayBuffer で単キー入力（Enter 不要）
  - save_data / load_data   → localStorage で永続化
  - log_adventure           → localStorage に追記
"""

import json
import js
from js import Atomics, localStorage


# ===== 単キー入力（Enter 不要） =====

def getch():
    """1 文字キー入力。SharedArrayBuffer 経由でブロッキング受信。"""
    Atomics.store(js.statusArray, 0, 0)
    Atomics.wait(js.statusArray, 0, 0)
    length = int(js.keyArray[0])
    raw = bytes([int(js.keyArray[i + 1]) for i in range(min(length, 32))])
    ch = raw.decode('utf-8', errors='replace')
    if ch == '\x03':
        raise KeyboardInterrupt
    return ch


def animated_getch():
    """プロンプト表示付き単キー入力（Web 版: アニメーション省略）。"""
    import sys
    sys.stdout.write('\r▶  ')
    sys.stdout.flush()
    return getch()


# ===== localStorage 永続化 =====

_LS_SAVE_KEY = 'life_rpg_savedata'
_LS_LOG_KEY  = 'life_rpg_log'


def save_data(data):
    """RPG データを localStorage に保存。"""
    localStorage.setItem(_LS_SAVE_KEY,
                         json.dumps(data, ensure_ascii=False, indent=2))


def load_data():
    """RPG データを localStorage から読み込む。初回はサンプルデータで初期化。"""
    saved = localStorage.getItem(_LS_SAVE_KEY)
    if saved:
        data = json.loads(saved)
        # マイグレーション（旧データへの後方互換）
        if 'chests' not in data:
            data['chests'] = []
        if 'gold' not in data['hero']:
            data['hero']['gold'] = 0
        return data

    # 初回起動: _SAMPLE_DATA（worker.js が Python グローバルに注入）を使用
    data = {
        'field_tasks': _SAMPLE_DATA.get('field_tasks', {}),
        'quests':      _SAMPLE_DATA.get('quests', []),
        'chests':      [],
        'hero': {
            'level': 1, 'exp': 0, 'gold': 0,
            'total_battles': 0, 'total_victories': 0, 'quests_completed': 0,
        },
        'field_state': {
            'exploring': False, 'current_encounter': None,
            'current_category': None, 'session_encounters': [],
            'session_victories': 0,
        },
    }
    save_data(data)
    return data


def log_adventure(category, message, symbol='⚔️'):
    """冒険記録を localStorage に追記。"""
    existing = localStorage.getItem(_LS_LOG_KEY) or '# 冒険の記録\n'
    date_str = get_current_date()
    time_str = get_current_time()
    entry = f'{date_str} {time_str} [{category}] {message} {symbol}\n'
    localStorage.setItem(_LS_LOG_KEY, existing + entry)
