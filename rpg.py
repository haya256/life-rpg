#!/usr/bin/python3
#!/usr/bin/env python3
"""
人生RPGシステム
フィールド探索とクエストで人生を冒険する
"""

import json
import os
import random
import sys
import time
import unicodedata
from datetime import datetime
from pathlib import Path

_IS_WINDOWS = sys.platform == 'win32'

if _IS_WINDOWS:
    import msvcrt
    os.system('')  # ANSI エスケープコードを有効化
else:
    import select
    import termios
    import tty

# ファイルパス
SCRIPT_DIR = Path(__file__).parent
SAVE_DIR = SCRIPT_DIR / "savedata"
SAVE_DIR.mkdir(exist_ok=True)  # 初回起動時に自動作成
DATA_FILE = SAVE_DIR / "rpg_data.json"
SAMPLE_DATA_FILE = SCRIPT_DIR / "sample_data.json"
LOG_FILE = SAVE_DIR / "ADVENTURE_LOG.md"

# 神モード（デバッグモード）- セッション内のみ有効
god_mode = False

def getch():
    """1文字キー入力を受け取る（Enter不要）。Ctrl+C で KeyboardInterrupt を発生。"""
    if _IS_WINDOWS:
        ch = msvcrt.getwch()
        if ch == '\x03':
            raise KeyboardInterrupt
        if ch in ('\x00', '\xe0'):  # 特殊キー（矢印キーなど）は読み捨て
            msvcrt.getwch()
            return ''
        return ch
    if not sys.stdin.isatty():
        # 非インタラクティブ環境（パイプなど）ではフォールバック
        line = input()
        return line[0] if line else '\r'
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    if ch == '\x03':  # Ctrl+C
        raise KeyboardInterrupt
    return ch


def animated_getch():
    """アニメーション付き1キー入力待ち（メニュー用）"""
    frames = ["▶   ", "▶.  ", "▶.. ", "▶..."]
    frame_idx = 0

    if _IS_WINDOWS:
        while True:
            sys.stdout.write(f"\r{frames[frame_idx]}")
            sys.stdout.flush()
            if msvcrt.kbhit():
                ch = msvcrt.getwch()
                sys.stdout.write("\r▶  ")
                sys.stdout.flush()
                if ch == '\x03':
                    raise KeyboardInterrupt
                if ch in ('\x00', '\xe0'):  # 特殊キーは読み捨て
                    msvcrt.getwch()
                    continue
                return ch
            frame_idx = (frame_idx + 1) % len(frames)
            time.sleep(0.4)

    if not sys.stdin.isatty():
        sys.stdout.write("▶  ")
        sys.stdout.flush()
        line = input()
        return line[0] if line else '\r'

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        sys.stdout.write("\r▶   ")
        sys.stdout.flush()
        while True:
            ready, _, _ = select.select([sys.stdin], [], [], 0.4)
            if ready:
                ch = sys.stdin.read(1)
                sys.stdout.write("\r▶  ")
                sys.stdout.flush()
                break
            frame_idx = (frame_idx + 1) % len(frames)
            sys.stdout.write(f"\r{frames[frame_idx]}")
            sys.stdout.flush()
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

    if ch == '\x03':  # Ctrl+C
        raise KeyboardInterrupt
    return ch


def input_with_prefill(prompt, prefill=""):
    """既存のテキストを初期値として表示し、カーソルキーで編集できる入力欄を提供する"""
    if _IS_WINDOWS or not sys.stdin.isatty():
        # Windows: シンプルな入力（空Enterで元の値を維持）
        print(f"{prompt}[現在: {prefill}]")
        new_val = input("新しい値 (Enterで変更なし): ").strip()
        return new_val if new_val else prefill

    def display_width(s):
        """文字列のターミナル表示幅（全角文字は2）"""
        return sum(2 if unicodedata.east_asian_width(c) in ('W', 'F') else 1 for c in s)

    def read_char(fd):
        """UTF-8を考慮して1文字読み込む"""
        b = os.read(fd, 1)
        if not b:
            return ''
        first = b[0]
        if first < 0x80:
            return b.decode('utf-8')
        elif first < 0xE0:
            b += os.read(fd, 1)
        elif first < 0xF0:
            b += os.read(fd, 2)
        else:
            b += os.read(fd, 3)
        return b.decode('utf-8')

    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    buf = list(prefill)
    pos = len(buf)

    def redraw():
        before = ''.join(buf[:pos])
        after = ''.join(buf[pos:])
        sys.stdout.write('\r\x1b[K' + prompt + before + after)
        after_w = display_width(after)
        if after_w > 0:
            sys.stdout.write(f'\x1b[{after_w}D')
        sys.stdout.flush()

    sys.stdout.write(prompt + prefill)
    sys.stdout.flush()

    try:
        tty.setcbreak(fd)
        while True:
            ch = read_char(fd)
            if ch in ('\r', '\n'):
                sys.stdout.write('\n')
                sys.stdout.flush()
                break
            elif ch in ('\x7f', '\x08'):  # Backspace
                if pos > 0:
                    buf.pop(pos - 1)
                    pos -= 1
                    redraw()
            elif ch == '\x1b':  # エスケープシーケンス
                b1 = read_char(fd)
                if b1 == '[':
                    b2 = read_char(fd)
                    if b2 == 'C' and pos < len(buf):  # →
                        w = display_width(buf[pos])
                        pos += 1
                        sys.stdout.write(f'\x1b[{w}C')
                        sys.stdout.flush()
                    elif b2 == 'D' and pos > 0:  # ←
                        pos -= 1
                        w = display_width(buf[pos])
                        sys.stdout.write(f'\x1b[{w}D')
                        sys.stdout.flush()
                    elif b2 == '3':  # Delete キー (ESC[3~)
                        read_char(fd)  # ~ を読み捨て
                        if pos < len(buf):
                            buf.pop(pos)
                            redraw()
                    elif b2 == 'H':  # Home
                        pos = 0
                        redraw()
                    elif b2 == 'F':  # End
                        pos = len(buf)
                        redraw()
            elif ch == '\x01':  # Ctrl+A - 行頭
                pos = 0
                redraw()
            elif ch == '\x05':  # Ctrl+E - 行末
                pos = len(buf)
                redraw()
            elif ch == '\x0b':  # Ctrl+K - カーソル以降を削除
                buf = buf[:pos]
                redraw()
            elif ch == '\x03':  # Ctrl+C
                sys.stdout.write('\n')
                sys.stdout.flush()
                raise KeyboardInterrupt
            elif ch and ord(ch) >= 32:  # 印字可能文字（ASCII・日本語など）
                buf.insert(pos, ch)
                pos += 1
                redraw()
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

    return ''.join(buf)


def show_menu(items, god_items=None):
    """汎用メニュー表示・選択関数（単キー入力版）。
    items: [(key, label), ...] - 通常の選択肢
    god_items: [(key, label), ...] - 神モード時のみ表示される追加選択肢
    Returns: 選択された項目の key（str）、Esc/無効なら None
    """
    global god_mode

    while True:
        all_items = list(items)
        if god_items and god_mode:
            all_items.extend(god_items)

        for i, (key, label) in enumerate(all_items, 1):
            print(f"{i}. {label}")
        print()

        n = len(all_items)
        ch = animated_getch()

        if ch == '0':
            # 神モードトグル
            god_mode = not god_mode
            sys.stdout.write("0\n")
            sys.stdout.flush()
            if god_mode:
                print("\n👁 神モード：ON - 世界を掌握した\n")
            else:
                print("\n👁 神モード：OFF - 勇者に戻った\n")
            continue  # メニューを再表示

        sys.stdout.write(ch + '\n')
        sys.stdout.flush()

        if ch in ('\x1b', '\r', '\n'):  # Esc / Enter
            return None

        if ch.isdigit() and 1 <= int(ch) <= n:
            return all_items[int(ch) - 1][0]
        # 無効キーは無視してループ（再表示）

def get_current_time():
    """日本時間の現在時刻を取得"""
    import subprocess
    result = subprocess.run(
        ["bash", "-c", "TZ='Asia/Tokyo' date '+%H:%M'"],
        capture_output=True,
        text=True
    )
    return result.stdout.strip()

def get_current_date():
    """日本時間の現在日付を取得"""
    import subprocess
    result = subprocess.run(
        ["bash", "-c", "TZ='Asia/Tokyo' date '+%Y-%m-%d'"],
        capture_output=True,
        text=True
    )
    return result.stdout.strip()

def tprint(text='', delay=0.02, end='\n'):
    """タイプライター風テキスト表示"""
    for char in str(text):
        sys.stdout.write(char)
        sys.stdout.flush()
        time.sleep(delay)
    sys.stdout.write(end)
    sys.stdout.flush()


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

# ==================== フィールド探索 ====================

def explore(mode="random", count=5):
    """フィールド探索を開始"""
    data = load_data()

    if data["field_state"]["exploring"]:
        print("⚠️  すでにフィールド探索中です。")
        print("   'rpg return' で街に戻ってから、再度探索を開始してください。")
        return

    # アクティブなモンスターを収集（出現率重みも取得）
    all_encounters = []
    all_weights = []
    for field_name, monsters in data["field_tasks"].items():
        for monster_obj in monsters:
            if monster_obj.get("active", 1) == 1:
                all_encounters.append({
                    "field": field_name,
                    "monster": monster_obj["monster"]
                })
                # weight: -2〜+2 → 実際の重み 1〜5（デフォルト 3）
                w = monster_obj.get("weight", 0)
                all_weights.append(max(1, 3 + w))

    if not all_encounters:
        print("❌ フィールドにモンスターがいません。")
        print("   'rpg add-monster' でモンスターを追加してください。")
        return

    # セッション開始（重み付きサンプリング）
    if mode == "random":
        # 重み付きで重複なしサンプリング
        pool = list(range(len(all_encounters)))
        weights = all_weights.copy()
        selected = []
        for _ in range(min(count, len(pool))):
            idx = random.choices(pool, weights=weights, k=1)[0]
            selected.append(all_encounters[idx])
            pos = pool.index(idx)
            pool.pop(pos)
            weights.pop(pos)
        session_encounters = selected
    else:  # mode == "all"
        # 重みに基づいた順番でシャッフル（重みが高いほど前に出やすい）
        indexed = list(zip(all_encounters, all_weights))
        indexed.sort(key=lambda x: -(x[1] * random.random()))
        session_encounters = [e for e, _ in indexed]

    data["field_state"]["exploring"] = True
    data["field_state"]["session_encounters"] = session_encounters
    data["field_state"]["session_victories"] = 0
    data["field_state"]["current_encounter"] = None
    data["field_state"]["current_category"] = None

    save_data(data)

    print()
    print("=" * 48)
    print("🌍 フィールド探索開始！")
    print("=" * 48)
    print(f"🎯 今回の探索: {len(session_encounters)}体のモンスターと遭遇予定")
    print()
    print("📜 コマンド:")
    print("   rpg battle   - 次のモンスターと遭遇")
    print("   rpg victory  - モンスターを倒した！")
    print("   rpg flee     - 逃げる（スキップ）")
    print("   rpg return   - 街に戻る（探索終了）")
    print()

def battle():
    """モンスターとエンカウント"""
    data = load_data()

    if not data["field_state"]["exploring"]:
        print("❌ フィールド探索中ではありません。")
        print("   'rpg explore' でフィールドに出かけてください。")
        return

    if data["field_state"]["current_encounter"]:
        # すでにエンカウント中
        encounter = data["field_state"]["current_encounter"]
        print()
        print("⚔️  まだバトル中です！")
        print(f"   📍 {encounter['field']}")
        print(f"   👹 {encounter['monster']}")
        print()
        print("   'rpg victory' でバトルを完了するか、")
        print("   'rpg flee' で逃げてください。")
        return

    # 次のエンカウント
    if not data["field_state"]["session_encounters"]:
        print()
        print("🎊 今回の探索は終了しました！")
        print(f"   勝利数: {data['field_state']['session_victories']}")
        print()
        print("   'rpg return' で街に戻ってください。")
        return

    encounter = data["field_state"]["session_encounters"][0]
    data["field_state"]["current_encounter"] = encounter
    data["field_state"]["current_category"] = encounter["field"]
    save_data(data)

    remaining = len(data["field_state"]["session_encounters"])
    victories = data["field_state"]["session_victories"]

    os.system('cls' if os.name == 'nt' else 'clear')
    print()
    print("=" * 48)
    tprint("⚔️  モンスターが現れた！")
    print("=" * 48)
    tprint(f"📍 {encounter['field']}")
    tprint(f"👹 {encounter['monster']}")
    print()
    print(f"📊 進捗: {victories}勝 / 残り{remaining}体")
    print()
    print("💪 タスクを実行して、'rpg victory' で勝利を報告してください。")
    print("🏃 または 'rpg flee' で逃げることもできます。")
    print()

def victory():
    """バトル勝利（タスク完了）"""
    data = load_data()

    if not data["field_state"]["exploring"]:
        print("❌ フィールド探索中ではありません。")
        return

    if not data["field_state"]["current_encounter"]:
        print("❌ 現在エンカウント中ではありません。")
        print("   'rpg battle' でモンスターと遭遇してください。")
        return

    encounter = data["field_state"]["current_encounter"]

    # 経験値・統計更新
    data["hero"]["total_battles"] += 1
    data["hero"]["total_victories"] += 1
    exp_gain = 10
    data["hero"]["exp"] += exp_gain

    # ゴールド獲得（モンスターに gold フィールドがあればそれを使用、なければ 1）
    gold_gain = 1
    for monster_obj in data["field_tasks"].get(encounter["field"], []):
        if monster_obj["monster"] == encounter["monster"]:
            gold_gain = monster_obj.get("gold", 1)
            break
    data["hero"]["gold"] = data["hero"].get("gold", 0) + gold_gain

    # レベルアップチェック
    old_level = data["hero"]["level"]
    new_level = 1 + (data["hero"]["exp"] // 100)  # 100 EXPで1レベルアップ
    data["hero"]["level"] = new_level

    # セッション統計更新
    data["field_state"]["session_victories"] += 1
    data["field_state"]["session_encounters"].pop(0)
    data["field_state"]["current_encounter"] = None

    save_data(data)

    # ログ記録
    log_adventure(
        encounter["field"],
        encounter["monster"],
        "✓"
    )

    # 結果表示
    print()
    print("=" * 48)
    tprint("🎉 勝利！")
    print("=" * 48)
    tprint(f"👹 {encounter['monster']} を倒した！")
    tprint(f"✨ EXP +{exp_gain} (総EXP: {data['hero']['exp']})")
    tprint(f"💰 GOLD +{gold_gain} (所持GOLD: {data['hero']['gold']})")

    if new_level > old_level:
        print()
        tprint("🎊" * 20, delay=0.005)
        tprint(f"🌟 レベルアップ！ Lv.{old_level} → Lv.{new_level}")
        tprint("🎊" * 20, delay=0.005)

    print()
    print(f"📊 セッション進捗: {data['field_state']['session_victories']}勝")

    remaining = len(data["field_state"]["session_encounters"])
    if remaining > 0:
        print(f"   残り {remaining}体")
        print()
        print("   'rpg battle' で次のモンスターへ")
    else:
        print()
        tprint("🎊 今回の探索は終了しました！")
        print("   'rpg return' で街に戻ってください。")
    print()

def flee():
    """逃げる（スキップ）"""
    data = load_data()

    if not data["field_state"]["exploring"]:
        print("❌ フィールド探索中ではありません。")
        return

    if not data["field_state"]["current_encounter"]:
        print("❌ 現在エンカウント中ではありません。")
        return

    encounter = data["field_state"]["current_encounter"]

    # エンカウントをスキップ（ログには残さない）
    data["field_state"]["session_encounters"].pop(0)
    data["field_state"]["current_encounter"] = None
    data["hero"]["total_battles"] += 1  # バトル数だけカウント

    save_data(data)

    print()
    print(f"🏃 {encounter['monster']} から逃げた！")

    remaining = len(data["field_state"]["session_encounters"])
    if remaining > 0:
        print(f"   残り {remaining}体")
        print()
        print("   'rpg battle' で次のモンスターへ")
    else:
        print()
        print("🎊 今回の探索は終了しました！")
        print("   'rpg return' で街に戻ってください。")
    print()

def seal():
    """封印（現在のモンスターをactiveを0にして二軍に移動）"""
    data = load_data()

    if not data["field_state"]["exploring"]:
        print("❌ フィールド探索中ではありません。")
        return

    if not data["field_state"]["current_encounter"]:
        print("❌ 現在エンカウント中ではありません。")
        return

    encounter = data["field_state"]["current_encounter"]

    # field_tasks で該当するモンスターを探して active を 0 に
    found = False
    for field_name, monsters in data["field_tasks"].items():
        if field_name == encounter["field"]:
            for monster_obj in monsters:
                if monster_obj["monster"] == encounter["monster"]:
                    monster_obj["active"] = 0
                    found = True
                    break
            if found:
                break

    if not found:
        print(f"⚠️  モンスター '{encounter['monster']}' が見つかりませんでした。")
        return

    # エンカウントをスキップ（ログには残さない）
    data["field_state"]["session_encounters"].pop(0)
    data["field_state"]["current_encounter"] = None
    data["hero"]["total_battles"] += 1  # バトル数だけカウント

    save_data(data)

    print()
    print("=" * 48)
    tprint("🔒 封印！")
    print("=" * 48)
    tprint(f"👹 {encounter['monster']} を封印した！")
    print(f"   二軍（active: 0）に移動しました。")
    print()

    remaining = len(data["field_state"]["session_encounters"])
    if remaining > 0:
        print(f"   残り {remaining}体")
        print()
        print("   'rpg battle' で次のモンスターへ")
    else:
        print()
        tprint("🎊 今回の探索は終了しました！")
        print("   'rpg return' で街に戻ってください。")
    print()

def unseal():
    """封印解除（active=0のモンスターをランダムに復活させて現在のモンスターと入れ替え）"""
    data = load_data()

    if not data["field_state"]["exploring"]:
        print("❌ フィールド探索中ではありません。")
        return

    if not data["field_state"]["current_encounter"]:
        print("❌ 現在エンカウント中ではありません。")
        return

    # active が 0 のモンスターを収集
    sealed_monsters = []
    for field_name, monsters in data["field_tasks"].items():
        for monster_obj in monsters:
            if monster_obj.get("active", 1) == 0:
                sealed_monsters.append({
                    "field": field_name,
                    "monster": monster_obj["monster"]
                })

    if not sealed_monsters:
        print()
        print("❌ 封印されたモンスターがいません。")
        print("   'rpg seal' でモンスターを封印できます。")
        print()
        return

    # ランダムに一つ選ぶ
    import random
    unsealed = random.choice(sealed_monsters)

    # field_tasks で該当するモンスターを探して active を 1 に
    for field_name, monsters in data["field_tasks"].items():
        if field_name == unsealed["field"]:
            for monster_obj in monsters:
                if monster_obj["monster"] == unsealed["monster"]:
                    monster_obj["active"] = 1
                    break
            break

    # 現在のモンスターをセッションの最後に追加
    current_encounter = data["field_state"]["current_encounter"]
    data["field_state"]["session_encounters"].append(current_encounter)

    # 復活したモンスターを現在のエンカウントに設定
    data["field_state"]["current_encounter"] = unsealed
    data["field_state"]["current_category"] = unsealed["field"]

    save_data(data)

    print()
    print("=" * 48)
    tprint("🔓 封印解除！")
    print("=" * 48)
    tprint(f"👹 {unsealed['monster']} が復活した！")
    tprint(f"📍 {unsealed['field']}")
    print()
    print(f"💡 {current_encounter['monster']} は後回しになりました。")
    print()
    print("💪 タスクを実行して、'rpg victory' で勝利を報告してください。")
    print()

def create_monster():
    """神モード専用：新しいモンスターを創造する"""
    data = load_data()

    print()
    print("=" * 48)
    print("✨ モンスター創造")
    print("=" * 48)
    print()

    # 既存のフィールド一覧を表示
    fields = list(data["field_tasks"].keys())
    if fields:
        print("既存のフィールド:")
        for i, field in enumerate(fields, 1):
            print(f"  {i}. {field}")
        print()

    # フィールド選択または新規作成
    field_choice = input("フィールドを選択（番号）または新規フィールド名を入力: ").strip()

    if field_choice.isdigit() and 1 <= int(field_choice) <= len(fields):
        # 既存のフィールドを選択
        field_name = fields[int(field_choice) - 1]
    else:
        # 新規フィールド作成
        if field_choice:
            # 絵文字がない場合は追加
            if not field_choice.startswith("🌱"):
                field_name = f"🌱 {field_choice}"
            else:
                field_name = field_choice

            # 新しいフィールドを作成
            if field_name not in data["field_tasks"]:
                data["field_tasks"][field_name] = []
        else:
            print("❌ キャンセルしました。")
            return

    # モンスター（タスク）の内容を入力
    print()
    monster_description = input("モンスターの内容（タスク）を入力: ").strip()

    if not monster_description:
        print("❌ キャンセルしました。")
        return

    # モンスターを追加
    data["field_tasks"][field_name].append({
        "active": 1,
        "monster": monster_description
    })

    save_data(data)

    print()
    print("=" * 48)
    tprint("✨ モンスター創造完了！")
    print("=" * 48)
    tprint(f"📍 {field_name}")
    tprint(f"👹 {monster_description}")
    print()
    tprint("   新しいモンスターが世界に現れた！")
    print()

def unleash_all_monsters():
    """神モード専用：全モンスターの封印を解除する（闇の時代の再来）"""
    data = load_data()

    unleashed_count = 0
    for field_name, monsters in data["field_tasks"].items():
        for monster_obj in monsters:
            if monster_obj.get("active", 1) == 0:
                monster_obj["active"] = 1
                unleashed_count += 1

    if unleashed_count == 0:
        print()
        print("❌ 封印されたモンスターがいません。")
        print()
        return

    save_data(data)

    print()
    print("=" * 48)
    tprint("🌑 闇の時代の再来...", delay=0.05)
    print("=" * 48)
    print()
    tprint(f"   {unleashed_count}体のモンスターの封印が解かれた！")
    print()
    tprint("🌑 全てのモンスターが目覚めた！")
    print()

def delete_monster():
    """神モード専用：現在のモンスターを世界から完全削除"""
    data = load_data()

    if not data["field_state"]["exploring"]:
        print("❌ フィールド探索中ではありません。")
        return

    if not data["field_state"]["current_encounter"]:
        print("❌ 現在エンカウント中ではありません。")
        return

    encounter = data["field_state"]["current_encounter"]

    # field_tasks から該当するモンスターを完全削除
    found = False
    for field_name, monsters in data["field_tasks"].items():
        if field_name == encounter["field"]:
            for monster_obj in monsters:
                if monster_obj["monster"] == encounter["monster"]:
                    monsters.remove(monster_obj)
                    found = True
                    break
            if found:
                break

    if not found:
        print(f"⚠️  モンスター '{encounter['monster']}' が見つかりませんでした。")
        return

    # エンカウントをスキップ（ログには残さない - 神の行為は記録されない）
    data["field_state"]["session_encounters"].pop(0)
    data["field_state"]["current_encounter"] = None

    save_data(data)

    print()
    print("=" * 48)
    tprint("🔥 世界改変")
    print("=" * 48)
    tprint(f"👹 {encounter['monster']} を世界から消滅させた！")
    tprint(f"   もう二度と現れない。")
    print()

    remaining = len(data["field_state"]["session_encounters"])
    if remaining > 0:
        print(f"   残り {remaining}体")
        print()
        print("   次のモンスターへ")
    else:
        print()
        tprint("🎊 今回の探索は終了しました！")
        print("   街に戻ってください。")
    print()

def rename_monster():
    """神モード専用：現在のモンスターの名前を変更する"""
    data = load_data()

    if not data["field_state"]["exploring"]:
        print("❌ フィールド探索中ではありません。")
        return

    if not data["field_state"]["current_encounter"]:
        print("❌ 現在エンカウント中ではありません。")
        return

    encounter = data["field_state"]["current_encounter"]
    old_name = encounter["monster"]

    print()
    new_name = input_with_prefill("名前を編集: ", old_name).strip()

    if not new_name:
        print("❌ キャンセルしました。")
        return

    # field_tasks の該当モンスターを更新
    for field_name, monsters in data["field_tasks"].items():
        if field_name == encounter["field"]:
            for monster_obj in monsters:
                if monster_obj["monster"] == old_name:
                    monster_obj["monster"] = new_name
                    break
            break

    # current_encounter も更新
    data["field_state"]["current_encounter"]["monster"] = new_name

    save_data(data)

    print()
    print("=" * 48)
    tprint("✏️  名前変更")
    print("=" * 48)
    tprint(f"   {old_name}  →  {new_name}")
    print()

def _offer_rate_change(encounter):
    """神モード：戦闘後に出現率変更を提案する"""
    print()
    ans = input(f"⚖️  [{encounter['monster']}] の出現率を変更しますか？ (y/N): ").strip().lower()
    if ans == "y":
        set_monster_rate(encounter=encounter)
        input("\n[Enter] で続ける...")

def set_monster_rate(encounter=None):
    """神モード専用：現在のモンスターの出現率を設定する"""
    data = load_data()

    if encounter is None:
        if not data["field_state"]["current_encounter"]:
            print("❌ 現在エンカウント中ではありません。")
            return
        encounter = data["field_state"]["current_encounter"]

    # 現在の weight を取得
    current_weight = 0
    for monster_obj in data["field_tasks"].get(encounter["field"], []):
        if monster_obj["monster"] == encounter["monster"]:
            current_weight = monster_obj.get("weight", 0)
            break

    sign = lambda v: ("+" if v > 0 else "") + str(v)

    print()
    print(f"⚖️  出現率設定: {encounter['monster']}")
    print(f"   現在の出現率: {sign(current_weight)}")
    print()

    choice = show_menu([
        ("p2", f"+2  かなり遭遇しやすい{'  ← 現在' if current_weight == 2 else ''}"),
        ("p1", f"+1  やや遭遇しやすい{'  ← 現在' if current_weight == 1 else ''}"),
        ("z0", f" 0  標準{'  ← 現在' if current_weight == 0 else ''}"),
        ("m1", f"-1  やや遭遇しにくい{'  ← 現在' if current_weight == -1 else ''}"),
        ("m2", f"-2  かなり遭遇しにくい{'  ← 現在' if current_weight == -2 else ''}"),
    ])

    weight_map = {"p2": 2, "p1": 1, "z0": 0, "m1": -1, "m2": -2}
    if choice not in weight_map:
        print("❌ キャンセルしました。")
        return

    new_weight = weight_map[choice]

    for monster_obj in data["field_tasks"].get(encounter["field"], []):
        if monster_obj["monster"] == encounter["monster"]:
            monster_obj["weight"] = new_weight
            break

    save_data(data)

    print()
    print("=" * 48)
    tprint("⚖️  出現率変更")
    print("=" * 48)
    tprint(f"   {encounter['monster']}")
    tprint(f"   {sign(current_weight)}  →  {sign(new_weight)}")
    print()

def return_to_town():
    """街に戻る（探索終了）"""
    data = load_data()

    if not data["field_state"]["exploring"]:
        print("❌ フィールド探索中ではありません。")
        return

    victories = data["field_state"]["session_victories"]

    # 探索終了
    data["field_state"]["exploring"] = False
    data["field_state"]["current_encounter"] = None
    data["field_state"]["session_encounters"] = []
    data["field_state"]["session_victories"] = 0

    save_data(data)

    print()
    print("=" * 48)
    print("🏠 街に戻りました")
    print("=" * 48)
    print(f"📊 今回の探索結果:")
    print(f"   勝利数: {victories}")
    print(f"   総EXP: {data['hero']['exp']}")
    print(f"   勇者レベル: Lv.{data['hero']['level']}")
    print()
    print("💪 お疲れさまでした！")
    print()

# ==================== クエスト ====================

def list_quests():
    """クエスト一覧を表示"""
    data = load_data()

    if not data["quests"]:
        print()
        print("📜 現在受注中のクエストはありません。")
        print("   'rpg accept \"クエスト名\"' でクエストを受注してください。")
        print()
        return

    print()
    print("=" * 48)
    print("📜 クエスト一覧")
    print("=" * 48)

    for quest in data["quests"]:
        total_checkpoints = len(quest["checkpoints"])
        completed_checkpoints = sum(1 for m in quest["checkpoints"] if m["completed"])
        status_icon = "✅" if quest["status"] == "completed" else "📝"

        print()
        print(f"{status_icon} クエスト {quest['id']}: {quest['title']}")
        print(f"   進捗: {completed_checkpoints}/{total_checkpoints} チェックポイント")
        print(f"   作成日: {quest['created']}")

        if quest["status"] == "completed":
            print(f"   ✅ 完了済み！")

    print()
    print("詳細を見る: rpg show <id>")
    print()

def accept_quest(title):
    """新しいクエストを受注"""
    data = load_data()

    # 次のID番号を取得
    max_id = 0
    for quest in data["quests"]:
        try:
            quest_num = int(quest["id"])
            max_id = max(max_id, quest_num)
        except ValueError:
            pass

    quest_id = str(max_id + 1)

    new_quest = {
        "id": quest_id,
        "title": title,
        "checkpoints": [],
        "current_checkpoint": 0,
        "created": get_current_date(),
        "status": "active"
    }

    data["quests"].append(new_quest)
    save_data(data)

    print()
    print("=" * 48)
    print("📜 クエスト受注完了！")
    print("=" * 48)
    print(f"   ID: {quest_id}")
    print(f"   タイトル: {title}")
    print()
    print(f"次は: rpg add-checkpoint {quest_id} \"最初のチェックポイント\"")
    print()

def show_quest(quest_id):
    """クエストの詳細を表示"""
    data = load_data()

    quest = None
    for q in data["quests"]:
        if q["id"] == quest_id:
            quest = q
            break

    if not quest:
        print(f"❌ クエスト '{quest_id}' が見つかりません。")
        return

    total_checkpoints = len(quest["checkpoints"])
    completed_checkpoints = sum(1 for m in quest["checkpoints"] if m["completed"])
    current = quest.get("current_checkpoint", 0)

    print()
    print("=" * 48)
    print(f"📜 クエスト {quest['id']}: {quest['title']}")
    print("=" * 48)
    print(f"作成日: {quest['created']}")
    print(f"進捗: {completed_checkpoints}/{total_checkpoints} チェックポイント")

    if quest["status"] == "completed":
        print(f"ステータス: ✅ 完了済み")
    else:
        print(f"ステータス: 📝 進行中")

    print()
    print("チェックポイント一覧:")

    if not quest["checkpoints"]:
        print("  （まだチェックポイントが設定されていません）")
    else:
        for i, checkpoint in enumerate(quest["checkpoints"]):
            if checkpoint["completed"]:
                icon = "✅"
            elif i == current:
                icon = "👉"
            else:
                icon = "⬜"
            print(f"  {icon} {i+1}. {checkpoint['description']}")

    print()

    if quest["status"] != "completed" and current < total_checkpoints:
        print(f"現在のチェックポイント: {quest['checkpoints'][current]['description']}")
        print()
        print("コマンド:")
        print(f"  rpg advance {quest_id}  - チェックポイント完了、次へ進む")
        print(f"  rpg add-checkpoint {quest_id} \"新しいチェックポイント\" - チェックポイント追加")

    print()

def add_checkpoint(quest_id, checkpoint_description):
    """クエストにチェックポイントを追加"""
    data = load_data()

    quest = None
    for q in data["quests"]:
        if q["id"] == quest_id:
            quest = q
            break

    if not quest:
        print(f"❌ クエスト '{quest_id}' が見つかりません。")
        return

    quest["checkpoints"].append({
        "description": checkpoint_description,
        "completed": False
    })

    save_data(data)

    print()
    print(f"✅ チェックポイント追加完了！")
    print(f"   「{checkpoint_description}」")
    print()
    print(f"進捗を確認: rpg show {quest_id}")
    print()

def advance_quest(quest_id):
    """クエストを次のチェックポイントに進める"""
    data = load_data()

    quest = None
    quest_index = -1
    for i, q in enumerate(data["quests"]):
        if q["id"] == quest_id:
            quest = q
            quest_index = i
            break

    if not quest:
        print(f"❌ クエスト '{quest_id}' が見つかりません。")
        return

    current = quest.get("current_checkpoint", 0)

    if current >= len(quest["checkpoints"]):
        print("❌ すでに全チェックポイントが完了しています。")
        return

    # 現在のチェックポイントを完了
    quest["checkpoints"][current]["completed"] = True
    quest["current_checkpoint"] = current + 1

    # ログ記録
    log_adventure(
        f"📜 クエスト {quest_id}",
        quest["checkpoints"][current]["description"],
        "✓"
    )

    # 経験値獲得
    exp_gain = 50  # チェックポイント完了は50 EXP
    old_level = data["hero"]["level"]
    data["hero"]["exp"] += exp_gain
    data["hero"]["level"] = 1 + (data["hero"]["exp"] // 100)

    # クエスト完了チェック
    if quest["current_checkpoint"] >= len(quest["checkpoints"]):
        quest["status"] = "completed"
        data["hero"]["quests_completed"] += 1

        # クエスト完了ボーナス
        bonus_exp = 100
        data["hero"]["exp"] += bonus_exp
        data["hero"]["level"] = 1 + (data["hero"]["exp"] // 100)

        save_data(data)

        print()
        print("=" * 48)
        tprint("🎊 クエスト完了！")
        print("=" * 48)
        tprint(f"📜 {quest['title']}")
        print(f"✨ EXP +{exp_gain + bonus_exp} (チェックポイント+ボーナス)")
        print(f"🏆 総EXP: {data['hero']['exp']}")

        if data["hero"]["level"] > old_level:
            print()
            tprint("🎊" * 20, delay=0.005)
            tprint(f"🌟 レベルアップ！ Lv.{old_level} → Lv.{data['hero']['level']}")
            tprint("🎊" * 20, delay=0.005)

        print()
        tprint("💰 報酬を獲得しました！")
        print()
        return

    save_data(data)

    # 次のチェックポイント表示
    next_checkpoint = quest["checkpoints"][quest["current_checkpoint"]]

    print()
    print("=" * 48)
    tprint("✅ チェックポイント完了！")
    print("=" * 48)
    print(f"✨ EXP +{exp_gain}")

    if data["hero"]["level"] > old_level:
        print()
        tprint("🎊" * 20, delay=0.005)
        tprint(f"🌟 レベルアップ！ Lv.{old_level} → Lv.{data['hero']['level']}")
        tprint("🎊" * 20, delay=0.005)

    print()
    print("次のチェックポイント:")
    print(f"👉 {next_checkpoint['description']}")
    print()
    print(f"進捗: {quest['current_checkpoint']}/{len(quest['checkpoints'])} チェックポイント完了")
    print()

# ==================== チェスト管理 ====================

def list_chests(data):
    """チェスト一覧を表示"""
    chests = data["chests"]
    if not chests:
        print("📦 登録されたチェストはまだありません。")
        return

    print("=" * 48)
    print("📦 チェスト一覧")
    print("=" * 48)
    for chest in chests:
        item_count = len(chest["items"])
        print(f"  [{chest['id']}] {chest['name']}")
        print(f"       📍 {chest['location']}  |  🎒 {item_count}個のアイテム")
    print()


def show_chest(chest):
    """チェスト詳細とアイテム一覧を表示"""
    print()
    print("=" * 48)
    print(f"📦 {chest['name']}")
    print("=" * 48)
    print(f"📍 保管場所: {chest['location']}")
    print(f"📅 登録日: {chest['created']}")
    print(f"🎒 アイテム数: {len(chest['items'])}個")
    print()

    if not chest["items"]:
        print("  （アイテムなし）")
    else:
        print("アイテム一覧:")
        for item in chest["items"]:
            memo_str = f"  ✏️  {item['memo']}" if item["memo"] else ""
            print(f"  [{item['id']}] {item['name']}{memo_str}")
    print()


def create_chest():
    """新しいチェストを登録"""
    print()
    print("=" * 48)
    print("📦 チェスト登録")
    print("=" * 48)
    print()

    name = input("チェストの名前（例: 押し入れ左の段ボール）: ").strip()
    if not name:
        print("❌ キャンセルしました。")
        return

    location = input("保管場所（例: 家の中 / 貸し倉庫）: ").strip()
    if not location:
        location = "未設定"

    data = load_data()

    max_id = 0
    for chest in data["chests"]:
        try:
            max_id = max(max_id, int(chest["id"]))
        except ValueError:
            pass
    new_id = str(max_id + 1)

    new_chest = {
        "id": new_id,
        "name": name,
        "location": location,
        "created": get_current_date(),
        "items": []
    }

    data["chests"].append(new_chest)
    save_data(data)

    print()
    print("=" * 48)
    tprint("📦 チェスト登録完了！")
    print("=" * 48)
    tprint(f"   [{new_id}] {name}")
    tprint(f"   📍 {location}")
    print()
    tprint("   アイテムを追加してチェストを充実させよう！")
    print()


def add_chest_item(chest_id):
    """チェストにアイテムを追加"""
    data = load_data()

    chest = None
    for c in data["chests"]:
        if c["id"] == chest_id:
            chest = c
            break

    if not chest:
        print(f"❌ チェスト '{chest_id}' が見つかりません。")
        return

    print()
    print(f"📦 {chest['name']} にアイテムを追加")
    print()

    item_name = input("アイテム名: ").strip()
    if not item_name:
        print("❌ キャンセルしました。")
        return

    memo = input("メモ（省略可、Enterでスキップ）: ").strip()

    max_item_id = 0
    for item in chest["items"]:
        try:
            max_item_id = max(max_item_id, int(item["id"]))
        except ValueError:
            pass
    new_item_id = str(max_item_id + 1)

    new_item = {
        "id": new_item_id,
        "name": item_name,
        "added": get_current_date(),
        "memo": memo
    }

    chest["items"].append(new_item)
    save_data(data)

    print()
    print("=" * 48)
    tprint("✅ アイテム追加完了！")
    print("=" * 48)
    tprint(f"   {item_name}")
    if memo:
        tprint(f"   ✏️  {memo}")
    print()


def remove_chest_item(chest_id, item_id):
    """チェストからアイテムを削除"""
    data = load_data()

    chest = None
    for c in data["chests"]:
        if c["id"] == chest_id:
            chest = c
            break

    if not chest:
        print(f"❌ チェスト '{chest_id}' が見つかりません。")
        return

    item = None
    for it in chest["items"]:
        if it["id"] == item_id:
            item = it
            break

    if not item:
        print(f"❌ アイテム '{item_id}' が見つかりません。")
        return

    chest["items"].remove(item)
    save_data(data)

    print()
    print("=" * 48)
    tprint("🗑️  アイテムを削除しました")
    print("=" * 48)
    tprint(f"   {item['name']}")
    print()


def rename_chest_item(chest_id, item_id):
    """チェスト内のアイテム名を変更する"""
    data = load_data()

    chest = None
    for c in data["chests"]:
        if c["id"] == chest_id:
            chest = c
            break

    if not chest:
        print(f"❌ チェスト '{chest_id}' が見つかりません。")
        return

    item = None
    for it in chest["items"]:
        if it["id"] == item_id:
            item = it
            break

    if not item:
        print(f"❌ アイテム '{item_id}' が見つかりません。")
        return

    print()
    new_name = input_with_prefill("アイテム名を編集: ", item["name"]).strip()

    if not new_name:
        print("❌ キャンセルしました。")
        return

    old_name = item["name"]
    item["name"] = new_name
    save_data(data)

    print()
    print("=" * 48)
    tprint("✏️  アイテム名変更")
    print("=" * 48)
    tprint(f"   {old_name}  →  {new_name}")
    print()


def rename_chest(chest_id):
    """チェストの名前を変更する"""
    data = load_data()

    chest = None
    for c in data["chests"]:
        if c["id"] == chest_id:
            chest = c
            break

    if not chest:
        print(f"❌ チェスト '{chest_id}' が見つかりません。")
        return

    print()
    new_name = input_with_prefill("チェスト名を編集: ", chest["name"]).strip()

    if not new_name:
        print("❌ キャンセルしました。")
        return

    old_name = chest["name"]
    chest["name"] = new_name
    save_data(data)

    print()
    print("=" * 48)
    tprint("✏️  チェスト名変更")
    print("=" * 48)
    tprint(f"   {old_name}  →  {new_name}")
    print()


# ==================== ステータス ====================

def show_status():
    """勇者のステータスを表示"""
    data = load_data()
    hero = data["hero"]

    # 次のレベルまでの経験値
    current_level_exp = (hero["level"] - 1) * 100
    next_level_exp = hero["level"] * 100
    exp_to_next = next_level_exp - hero["exp"]
    exp_progress = hero["exp"] - current_level_exp
    exp_bar_length = 20
    exp_bar_filled = int((exp_progress / 100) * exp_bar_length)
    exp_bar = "█" * exp_bar_filled + "░" * (exp_bar_length - exp_bar_filled)

    # 勝率計算
    if hero["total_battles"] > 0:
        win_rate = (hero["total_victories"] / hero["total_battles"]) * 100
    else:
        win_rate = 0

    print()
    print("=" * 48)
    print("⚔️  勇者のステータス")
    print("=" * 48)
    print(f"レベル: Lv.{hero['level']}")
    print(f"経験値: {hero['exp']} EXP")
    print(f"   [{exp_bar}] 次のレベルまで {exp_to_next} EXP")
    print(f"所持金: {hero.get('gold', 0)} G")
    print()
    print("📊 戦績:")
    print(f"   総バトル数: {hero['total_battles']}")
    print(f"   勝利数: {hero['total_victories']}")
    print(f"   勝率: {win_rate:.1f}%")
    print()
    print("🏆 クエスト:")
    print(f"   完了数: {hero['quests_completed']}")
    print()

    # 現在の状態
    if data["field_state"]["exploring"]:
        print("📍 現在の状態: フィールド探索中")
        victories = data["field_state"]["session_victories"]
        remaining = len(data["field_state"]["session_encounters"])
        if data["field_state"]["current_encounter"]:
            remaining += 1  # 現在のエンカウントも含める
        print(f"   今回の探索: {victories}勝 / 残り{remaining}体")
    else:
        print("📍 現在の状態: 街で休憩中")

    print()

def show_log():
    """冒険の記録を表示"""
    if not LOG_FILE.exists():
        print()
        print("📖 まだ冒険の記録がありません。")
        print()
        return

    with open(LOG_FILE, 'r', encoding='utf-8') as f:
        content = f.read()

    print()
    print(content)

# ==================== 対話モード ====================

def interactive():
    """完全対話型RPGモード（ゴマタスク interactive 風）"""
    print()
    print("=" * 48)
    tprint("🎮 人生RPG - Interactive Mode")
    print("=" * 48)
    print()

    while True:
        data = load_data()
        hero = data["hero"]

        print()
        print("-" * 48)
        god_indicator = " | 👁 神" if god_mode else ""
        print(f"⚔️  勇者 Lv.{hero['level']} | EXP {hero['exp']} | 💰 {hero.get('gold', 0)} G{god_indicator}")
        print("-" * 48)
        print()
        print("どうする？")
        print()
        choice = show_menu([
            ("explore", "🌍 フィールド探索（モンスター討伐で経験値稼ぎ）"),
            ("quest", "📜 クエスト（大きな目標に挑戦）"),
            ("chest", "📦 チェスト管理（物の収納場所を管理）"),
            ("status", "📊 ステータス確認"),
            ("log", "📖 冒険の記録"),
            ("quit", "🚪 終了"),
        ], god_items=[
            ("create", "✨ モンスターを創造する"),
            ("unleash", "🌑 闇の時代の再来（全モンスター解放）"),
        ])

        if choice == "explore":
            interactive_field_explore()
        elif choice == "quest":
            interactive_quest()
        elif choice == "chest":
            interactive_chest()
        elif choice == "status":
            show_status()
            input("\n[Enter] で続ける...")
        elif choice == "log":
            show_log()
            input("\n[Enter] で続ける...")
        elif choice == "quit":
            print()
            print("=" * 48)
            tprint("👋 またね、勇者！冒険の記録は ADVENTURE_LOG.md に残っているよ。")
            print("=" * 48)
            print()
            break
        elif choice == "create":
            create_monster()
        elif choice == "unleash":
            unleash_all_monsters()
        else:
            print("❌ 無効な選択です。")

def interactive_field_explore():
    """対話型フィールド探索"""
    data = load_data()

    # すでに探索中かチェック
    if data["field_state"]["exploring"]:
        print()
        print("⚠️  前回の探索が中断されています。続きから再開しますか？")
        print()
        choice = show_menu([
            ("resume", "続きから再開"),
            ("abort", "探索を中止して街に戻る"),
            ("cancel", "キャンセル"),
        ])

        if choice == "abort":
            return_to_town()
            return
        elif choice == "cancel" or choice is None:
            return
        # choice == "1" の場合は continue

    else:
        # 新しい探索を開始
        print()
        print("=" * 48)
        print("🌍 フィールド探索")
        print("=" * 48)
        print()
        print("何体のモンスターと戦いますか？")
        print()
        choice = show_menu([
            ("r3", "ランダムに3体"),
            ("r5", "ランダムに5体"),
            ("r10", "ランダムに10体"),
            ("all", "全てのモンスター"),
            ("cancel", "キャンセル"),
        ])

        if choice == "r3":
            explore("random", 3)
        elif choice == "r5":
            explore("random", 5)
        elif choice == "r10":
            explore("random", 10)
        elif choice == "all":
            explore("all")
        else:
            return

    # 探索ループ
    while True:
        data = load_data()

        if not data["field_state"]["exploring"]:
            # 探索終了
            break

        # 残りのモンスター数チェック
        remaining = len(data["field_state"]["session_encounters"])
        if data["field_state"]["current_encounter"]:
            remaining += 1

        if remaining == 0:
            # 全て終了
            return_to_town()
            input("\n[Enter] で続ける...")
            break

        # 現在のエンカウント状態チェック
        if data["field_state"]["current_encounter"]:
            # すでにエンカウント中 -> バトル結果を選択
            encounter = data["field_state"]["current_encounter"]
            print()
            print("-" * 48)
            tprint(f"⚔️  {encounter['monster']}", delay=0.2)
            print("-" * 48)
            print(f"📍 {encounter['field']}")
            print(f"📊 進捗: {data['field_state']['session_victories']}勝 / 残り{remaining}体")
            print()
            print("タスクを実行しましたか？")
            print()
            choice = show_menu([
                ("victory", "✅ 完了！（勝利）"),
                ("flee", "🏃 逃げる（スキップ）"),
                ("seal", "🔒 封印（このモンスターを二軍に移動）"),
                ("unseal", "🔓 封印解除（二軍のモンスターと入れ替え）"),
                ("return", "🏠 街に戻る（探索中断）"),
            ], god_items=[
                ("rename", "✏️  このモンスターの名前を変更する"),
                ("set_rate", "⚖️  このモンスターの出現率を変更する"),
                ("delete", "🔥 このモンスターを世界から消す"),
            ])

            if choice == "victory":
                last_encounter = data["field_state"]["current_encounter"].copy()
                victory()
                input("\n[Enter] で続ける...")
                if god_mode:
                    _offer_rate_change(last_encounter)
            elif choice == "flee":
                last_encounter = data["field_state"]["current_encounter"].copy()
                flee()
                if god_mode:
                    _offer_rate_change(last_encounter)
            elif choice == "seal":
                seal()
                input("\n[Enter] で続ける...")
            elif choice == "unseal":
                unseal()
                input("\n[Enter] で続ける...")
            elif choice == "return":
                return_to_town()
                input("\n[Enter] で続ける...")
                break
            elif choice == "rename":
                rename_monster()
                input("\n[Enter] で続ける...")
            elif choice == "set_rate":
                set_monster_rate()
                input("\n[Enter] で続ける...")
            elif choice == "delete":
                delete_monster()
                input("\n[Enter] で続ける...")
            else:
                print("❌ 無効な選択です。")

        else:
            # 次のモンスターとエンカウント
            print()
            print("-" * 48)
            print(f"📊 進捗: {data['field_state']['session_victories']}勝 / 残り{remaining}体")
            print("-" * 48)
            print()
            choice = show_menu([
                ("battle", "⚔️  次のモンスターとバトル"),
                ("return", "🏠 街に戻る（探索終了）"),
            ])

            if choice == "battle":
                battle()
            elif choice == "return":
                return_to_town()
                input("\n[Enter] で続ける...")
                break
            else:
                print("❌ 無効な選択です。")

def interactive_quest():
    """対話型クエスト"""
    while True:
        data = load_data()

        print()
        print("=" * 48)
        print("📜 クエスト")
        print("=" * 48)
        print()
        choice = show_menu([
            ("list", "📋 クエスト一覧"),
            ("new", "➕ 新しいクエストを受注"),
            ("back", "⬅️  メインメニューに戻る"),
        ])

        if choice == "list":
            # クエスト一覧
            if not data["quests"]:
                print()
                print("📜 現在受注中のクエストはありません。")
                print("   新しいクエストを受注してみましょう！")
                input("\n[Enter] で続ける...")
                continue

            list_quests()
            print()

            quest_id = input("クエストIDを選択（空でキャンセル）: ").strip()

            if not quest_id:
                continue

            # クエスト詳細ループ
            while True:
                quest = None
                for q in data["quests"]:
                    if q["id"] == quest_id:
                        quest = q
                        break

                if not quest:
                    print(f"❌ クエスト '{quest_id}' が見つかりません。")
                    break

                show_quest(quest_id)

                if quest["status"] == "completed":
                    input("\n[Enter] で続ける...")
                    break

                current = quest.get("current_checkpoint", 0)
                total_checkpoints = len(quest["checkpoints"])

                if current >= total_checkpoints:
                    input("\n[Enter] で続ける...")
                    break

                print()
                action = show_menu([
                    ("done", "✅ 現在のチェックポイントを完了"),
                    ("add", "➕ 新しいチェックポイントを追加"),
                    ("back", "⬅️  戻る"),
                ])

                if action == "done":
                    advance_quest(quest_id)
                    input("\n[Enter] で続ける...")
                    # クエスト完了チェック
                    data = load_data()
                    quest = None
                    for q in data["quests"]:
                        if q["id"] == quest_id:
                            quest = q
                            break
                    if quest and quest["status"] == "completed":
                        break
                elif action == "add":
                    mission = input("新しいチェックポイント内容: ").strip()
                    if mission:
                        add_checkpoint(quest_id, mission)
                        input("\n[Enter] で続ける...")
                elif action == "back":
                    break
                else:
                    print("❌ 無効な選択です。")

        elif choice == "new":
            # 新しいクエスト受注
            print()
            title = input("クエスト名（空でキャンセル）: ").strip()
            if title:
                accept_quest(title)
                input("\n[Enter] で続ける...")

        elif choice == "back":
            # 戻る
            break

        else:
            print("❌ 無効な選択です。")

def interactive_chest():
    """対話型チェスト管理"""
    while True:
        data = load_data()

        print()
        print("=" * 48)
        print("📦 チェスト管理")
        print("=" * 48)
        print()

        chest_count = len(data["chests"])
        total_items = sum(len(c["items"]) for c in data["chests"])
        print(f"   登録チェスト: {chest_count}個  |  総アイテム: {total_items}個")
        print()

        choice = show_menu([
            ("list", "📋 チェスト一覧を見る"),
            ("new", "➕ 新しいチェストを登録"),
            ("back", "⬅️  メインメニューに戻る"),
        ])

        if choice == "list":
            if not data["chests"]:
                print()
                print("📦 登録されたチェストはまだありません。")
                print("   新しいチェストを登録してみましょう！")
                input("\n[Enter] で続ける...")
                continue

            list_chests(data)
            chest_id = input("チェストIDを選択（空でキャンセル）: ").strip()

            if not chest_id:
                continue

            while True:
                data = load_data()

                chest = None
                for c in data["chests"]:
                    if c["id"] == chest_id:
                        chest = c
                        break

                if not chest:
                    print(f"❌ チェスト '{chest_id}' が見つかりません。")
                    break

                show_chest(chest)

                action = show_menu([
                    ("add_item", "➕ アイテムを追加"),
                    ("remove_item", "🗑️  アイテムを削除"),
                    ("rename_item", "✏️  アイテム名を変更"),
                    ("rename", "🏷️  チェスト名を変更"),
                    ("back", "⬅️  チェスト一覧に戻る"),
                ])

                if action == "add_item":
                    add_chest_item(chest_id)
                    input("\n[Enter] で続ける...")
                elif action == "remove_item":
                    if not chest["items"]:
                        print()
                        print("❌ 削除できるアイテムがありません。")
                        input("\n[Enter] で続ける...")
                    else:
                        item_id = input("削除するアイテムIDを入力: ").strip()
                        if item_id:
                            remove_chest_item(chest_id, item_id)
                            input("\n[Enter] で続ける...")
                elif action == "rename_item":
                    if not chest["items"]:
                        print()
                        print("❌ 変更できるアイテムがありません。")
                        input("\n[Enter] で続ける...")
                    else:
                        item_id = input("変更するアイテムIDを入力: ").strip()
                        if item_id:
                            rename_chest_item(chest_id, item_id)
                            input("\n[Enter] で続ける...")
                elif action == "rename":
                    rename_chest(chest_id)
                    input("\n[Enter] で続ける...")
                elif action == "back" or action is None:
                    break

        elif choice == "new":
            create_chest()
            input("\n[Enter] で続ける...")

        elif choice == "back" or choice is None:
            break

def play():
    """RPG対話モード（シンプル版、後方互換性のため残す）"""
    data = load_data()

    print()
    print("=" * 48)
    print("🎮 人生RPG")
    print("=" * 48)
    print()
    print(f"⚔️  勇者のステータス: Lv.{data['hero']['level']} (EXP {data['hero']['exp']})")
    print()
    print("どうする？")
    print()
    choice = show_menu([
        ("field", "🌍 フィールド探索（モンスターを倒して経験値稼ぎ）"),
        ("quest", "📜 クエスト（大きな目標に挑戦）"),
        ("status", "📊 ステータス確認"),
        ("log", "📖 冒険の記録"),
        ("quit", "🚪 終了"),
    ])

    if choice == "field":
        field_menu()
    elif choice == "quest":
        quest_menu()
    elif choice == "status":
        show_status()
    elif choice == "log":
        show_log()
    elif choice == "quit":
        print()
        print("👋 またね、勇者！")
        print()
    else:
        print("❌ 無効な選択です。")

def field_menu():
    """フィールド探索メニュー（シンプル版）"""
    data = load_data()

    if data["field_state"]["exploring"]:
        # すでに探索中
        print()
        print("現在フィールド探索中です。")
        print()
        choice = show_menu([
            ("battle", "⚔️  次のモンスターとバトル"),
            ("return", "🏠 街に戻る"),
        ])

        if choice == "battle":
            battle()

            # バトル後の選択
            if data["field_state"]["current_encounter"]:
                result = show_menu([
                    ("victory", "✅ 勝利！"),
                    ("flee", "🏃 逃げる"),
                ])

                if result == "victory":
                    victory()
                elif result == "flee":
                    flee()
        elif choice == "return":
            return_to_town()
    else:
        # 新しい探索
        print()
        print("フィールド探索を開始しますか？")
        print()
        choice = show_menu([
            ("r5", "ランダムに5体のモンスター"),
            ("all", "全てのモンスター"),
            ("cancel", "キャンセル"),
        ])

        if choice == "r5":
            explore("random", 5)
        elif choice == "all":
            explore("all")

def quest_menu():
    """クエストメニュー（シンプル版）"""
    data = load_data()

    print()
    print("クエストメニュー")
    print()
    choice = show_menu([
        ("list", "📜 クエスト一覧"),
        ("new", "➕ 新しいクエストを受注"),
        ("back", "⬅️  戻る"),
    ])

    if choice == "list":
        list_quests()

        if data["quests"]:
            quest_id = input("詳細を見るクエストID (空でキャンセル): ").strip()
            if quest_id:
                show_quest(quest_id)
    elif choice == "new":
        title = input("クエスト名: ").strip()
        if title:
            accept_quest(title)

# ==================== メイン ====================

def show_help():
    """ヘルプを表示"""
    print("""
🎮 人生RPG - コマンド一覧

【おすすめ】
  ./rpg.py                           対話モード（インタラクティブRPG）
  ./rpg.py interactive               対話モード（明示的）

【フィールド探索】
  rpg explore [--random N | --all]  フィールド探索開始
  rpg battle                         次のモンスターとバトル
  rpg victory                        勝利（タスク完了）
  rpg flee                           逃げる（スキップ）
  rpg seal                           封印（モンスターを二軍に移動）
  rpg unseal                         封印解除（二軍のモンスターと入れ替え）
  rpg return                         街に戻る（探索終了）

【クエスト】
  rpg quests                         クエスト一覧
  rpg accept "タイトル"              新しいクエスト受注
  rpg show <id>                      クエスト詳細
  rpg add-checkpoint <id> "内容"        チェックポイント追加
  rpg advance <id>                   次のチェックポイントへ進む

【ステータス】
  rpg status                         勇者のステータス表示
  rpg log                            冒険の記録

【その他】
  rpg play                           シンプル対話モード
  rpg help                           このヘルプ

【用語】
  フィールド探索 = ゴマタスク（草原でモンスター討伐、経験値稼ぎ）
  クエスト = エピックタスク（大きな目標、順序付きチェックポイント）

【推奨される使い方】
  1. ./rpg.py で対話モード起動
  2. フィールド探索またはクエストを選択
  3. 対話形式で冒険を進める
  4. 終了するまでループ
""")

def main():
    if len(sys.argv) < 2:
        interactive()
        return

    command = sys.argv[1]

    # 対話モード
    if command == "interactive":
        interactive()

    # フィールド探索
    elif command == "explore":
        mode = "random"
        count = 5
        if len(sys.argv) > 2:
            if sys.argv[2] == "--all":
                mode = "all"
            elif sys.argv[2] == "--random" and len(sys.argv) > 3:
                count = int(sys.argv[3])
        explore(mode, count)

    elif command == "battle":
        battle()

    elif command == "victory":
        victory()

    elif command == "flee":
        flee()

    elif command == "seal":
        seal()

    elif command == "unseal":
        unseal()

    elif command == "return":
        return_to_town()

    # クエスト
    elif command == "quests":
        list_quests()

    elif command == "accept":
        if len(sys.argv) < 3:
            print("❌ クエスト名を指定してください。")
            print("   例: rpg accept \"iPhoneアプリを作る\"")
            return
        accept_quest(sys.argv[2])

    elif command == "show":
        if len(sys.argv) < 3:
            print("❌ クエストIDを指定してください。")
            print("   例: rpg show 1")
            return
        show_quest(sys.argv[2])

    elif command == "add-checkpoint":
        if len(sys.argv) < 4:
            print("❌ クエストIDとチェックポイント内容を指定してください。")
            print("   例: rpg add-checkpoint 1 \"最初のステップ\"")
            return
        add_checkpoint(sys.argv[2], sys.argv[3])

    elif command == "advance":
        if len(sys.argv) < 3:
            print("❌ クエストIDを指定してください。")
            print("   例: rpg advance 1")
            return
        advance_quest(sys.argv[2])

    # ステータス
    elif command == "status":
        show_status()

    elif command == "log":
        show_log()

    # 対話モード
    elif command == "play":
        play()

    # ヘルプ
    elif command == "help":
        show_help()

    else:
        print(f"❌ 不明なコマンド: {command}")
        print("   'rpg help' でヘルプを表示")

if __name__ == "__main__":
    main()
