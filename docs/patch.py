"""
patch.py — rpg.py 読み込み後に適用するオーバーライド

rpg.py で定義された関数を Web 向けに差し替えます:
  - getch / animated_getch  → SharedArrayBuffer で単キー入力（Enter 不要）
  - save_data / load_data   → インメモリキャッシュ + postMessage で localStorage 永続化
  - log_adventure           → postMessage 経由でメインスレッドの localStorage へ

【localStorage と Web Worker の制約】
Web Worker 内では localStorage にアクセスできないため、
保存はメインスレッドへ postMessage({type:'storage_set',...}) を送り、
メインスレッドが localStorage に書き込む。

【インメモリキャッシュの必要性】
毎回 js.initialSavedData (起動時の初期値) を読んでしまうと、
セッション中の変更 (explore() での exploring=True など) が
次の load_data() 呼び出しに反映されない。
→ _data_cache でセッション内変更を保持し、
  save_data() でキャッシュ更新 + localStorage への永続化を行う。
"""

import json
import js
from js import Atomics
from pyodide.ffi import to_js


def _post(msg_dict):
    """plain JS Object として postMessage（Map 変換回避）"""
    js.postMessage(to_js(msg_dict, dict_converter=js.Object.fromEntries))


# ===== 単キー入力（Enter 不要） =====

def getch():
    """1 文字キー入力。SharedArrayBuffer 経由でブロッキング受信。"""
    Atomics.store(js.statusArray, 0, 0)
    # tprint() などの処理中に溜まったキーを破棄してから待機
    _post({'type': 'clear_queue'})
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


# ===== インメモリキャッシュ + localStorage 永続化 =====

_LS_SAVE_KEY = 'life_rpg_savedata'
_LS_LOG_KEY  = 'life_rpg_log'

# セッション中のデータキャッシュ（None = 未初期化）
_data_cache = None
_log_cache  = None


def save_data(data):
    """RPG データをキャッシュに保存し、localStorage にも永続化。"""
    global _data_cache
    _data_cache = data  # セッション内キャッシュを更新
    _post({
        'type':  'storage_set',
        'key':   _LS_SAVE_KEY,
        'value': json.dumps(data, ensure_ascii=False, indent=2),
    })


def load_data():
    """RPG データを読み込む。キャッシュ済みならキャッシュを返す。"""
    global _data_cache
    if _data_cache is not None:
        return _data_cache  # セッション内で更新済みのデータを返す

    # 初回のみ: メインスレッドから渡された localStorage の値を使用
    raw = js.initialSavedData
    if raw and str(raw) != 'None':
        data = json.loads(str(raw))
        # マイグレーション（旧データへの後方互換）
        if 'chests' not in data:
            data['chests'] = []
        if 'gold' not in data['hero']:
            data['hero']['gold'] = 0
        _data_cache = data
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


# ===== 勝利BGM トリガー =====

_original_victory = victory

def victory():
    """バトル勝利（Web版）: 元の処理を実行してから勝利BGMを再生。"""
    _original_victory()
    _post({'type': 'play_bgm', 'name': 'victory'})


def log_adventure(category, message, symbol='⚔️'):
    """冒険記録をメインスレッドの localStorage に追記。"""
    global _log_cache
    if _log_cache is None:
        raw = js.initialSavedLog
        _log_cache = str(raw) if raw and str(raw) != 'None' else '# 冒険の記録\n'
    date_str = get_current_date()
    time_str = get_current_time()
    entry = f'{date_str} {time_str} [{category}] {message} {symbol}\n'
    _log_cache += entry
    _post({
        'type':  'storage_set',
        'key':   _LS_LOG_KEY,
        'value': _log_cache,
    })
