#!/usr/bin/env python3
"""
人生RPGシステム
フィールド探索とクエストで人生を冒険する
"""

import os
import random

from rpg_bgm import bgm
import rpg_ui
from rpg_ui import get_current_date, input_with_prefill, show_menu, tprint
from rpg_data import load_data, save_data, log_adventure, LOG_FILE, SAVE_DIR

LOG_HISTORY_LINES = 100  # 未討伐履歴スキャン行数

# ==================== フィールド探索 ====================

def get_today_defeated_monsters():
    """今日すでに勝利したモンスター名のセットを返す（ログ末尾から高速スキャン）"""
    from rpg_data import get_current_date
    today = get_current_date()
    defeated = set()
    if not LOG_FILE.exists():
        return defeated
    lines = LOG_FILE.read_text(encoding='utf-8').splitlines()
    for line in reversed(lines):
        if not line.startswith(today):
            if line.startswith("20"):  # 今日以外の日付行に達したら終了
                break
        elif line.endswith(" ✓"):
            # 形式: "DATE TIME [field] monster ✓"
            bracket_end = line.index("]")
            monster = line[bracket_end + 2 : -2]  # "] " の後、" ✓" の前
            defeated.add(monster)
    return defeated


def get_monster_history(n_lines=LOG_HISTORY_LINES):
    """ログ末尾n行からモンスターごとの討伐日セットと全日付セットを返す。"""
    if not LOG_FILE.exists():
        return {}, set()
    lines = LOG_FILE.read_text(encoding='utf-8').splitlines()
    recent = lines[-n_lines:]
    history = {}
    all_dates = set()
    for line in recent:
        if not line.endswith(" ✓"):
            continue
        parts = line.split(" ", 1)
        if not parts or not parts[0].startswith("20"):
            continue
        date = parts[0]
        try:
            bracket_end = line.index("]")
            monster = line[bracket_end + 2:-2]
        except ValueError:
            continue
        all_dates.add(date)
        history.setdefault(monster, set()).add(date)
    return history, all_dates


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

    # undefeated_today モード: 今日未討伐のモンスターのみ
    if mode == "undefeated_today":
        defeated = get_today_defeated_monsters()
        undefeated = [(e, w) for e, w in zip(all_encounters, all_weights)
                      if e["monster"] not in defeated]
        if not undefeated:
            print()
            print("🎉 今日はすべてのモンスターを討伐済みです！")
            print()
            return
        all_encounters = [e for e, _ in undefeated]
        all_weights = [w for _, w in undefeated]
        indexed = list(zip(all_encounters, all_weights))
        indexed.sort(key=lambda x: -(x[1] * random.random()))
        session_encounters = [e for e, _ in indexed]

    # セッション開始（重み付きサンプリング）
    elif mode == "random":
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

def battle():
    """モンスターとエンカウント"""
    data = load_data()

    if not data["field_state"]["exploring"]:
        print("❌ フィールド探索中ではありません。")
        return

    if data["field_state"]["current_encounter"]:
        # すでにエンカウント中
        encounter = data["field_state"]["current_encounter"]
        print()
        print("⚔️  まだバトル中です！")
        print(f"   📍 {encounter['field']}")
        print(f"   👹 {encounter['monster']}")
        print()
        return

    # 次のエンカウント
    if not data["field_state"]["session_encounters"]:
        print()
        print("🎊 今回の探索は終了しました！")
        print(f"   勝利数: {data['field_state']['session_victories']}")
        print()
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

def victory():
    """バトル勝利（タスク完了）"""
    data = load_data()

    if not data["field_state"]["exploring"]:
        print("❌ フィールド探索中ではありません。")
        return

    if not data["field_state"]["current_encounter"]:
        print("❌ 現在エンカウント中ではありません。")
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

    bgm.play("victory")  # 勝利ファンファーレ（1回再生）

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
    else:
        print()
        tprint("🎊 今回の探索は終了しました！")
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
    else:
        print()
        print("🎊 今回の探索は終了しました！")
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

    # 封印したモンスターをセッションから取り除く
    data["field_state"]["session_encounters"].pop(0)
    data["hero"]["total_battles"] += 1  # バトル数だけカウント

    # 代替モンスターを選出（セッションにまだ入っていないアクティブモンスターから）
    scheduled = {(e["field"], e["monster"]) for e in data["field_state"]["session_encounters"]}
    active_monsters = []
    active_weights = []
    for field_name, monsters in data["field_tasks"].items():
        for monster_obj in monsters:
            if monster_obj.get("active", 1) == 1:
                key = (field_name, monster_obj["monster"])
                if key not in scheduled:
                    active_monsters.append({"field": field_name, "monster": monster_obj["monster"]})
                    w = monster_obj.get("weight", 0)
                    active_weights.append(max(1, 3 + w))

    print()
    print("=" * 48)
    tprint("🔒 封印！")
    print("=" * 48)
    tprint(f"👹 {encounter['monster']} を封印した！")
    print(f"   二軍（active: 0）に移動しました。")
    print()

    if active_monsters:
        # 代替モンスターをセッション先頭に挿入して即エンカウント
        replacement = random.choices(active_monsters, weights=active_weights, k=1)[0]
        data["field_state"]["session_encounters"].insert(0, replacement)
        data["field_state"]["current_encounter"] = replacement
        data["field_state"]["current_category"] = replacement["field"]
        save_data(data)
        tprint(f"⚔️  代わりに {replacement['monster']} が現れた！")
        tprint(f"📍 {replacement['field']}")
        remaining = len(data["field_state"]["session_encounters"])
        print(f"📊 残り {remaining}体")
        print()
    else:
        # セッション外の代替モンスターがいない場合は戦闘終了
        data["field_state"]["current_encounter"] = None
        save_data(data)
        remaining = len(data["field_state"]["session_encounters"])
        if remaining > 0:
            print(f"   残り {remaining}体")
            print()
        else:
            print()
            tprint("🎊 今回の探索は終了しました！")
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
        print()
        return

    # ランダムに一つ選ぶ
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

# ==================== 修行の旅 ====================

def generate_training_journey():
    """修行の旅：テキストファイルを生成して出発"""
    from datetime import datetime
    data = load_data()

    # アクティブなモンスターを収集
    monsters = []
    for field_name, monster_list in data["field_tasks"].items():
        for monster_obj in monster_list:
            if monster_obj.get("active", 1) == 1:
                monsters.append({
                    "field": field_name,
                    "name": monster_obj["monster"],
                    "gold": monster_obj.get("gold", 1),
                })

    if not monsters:
        print("❌ アクティブなモンスターがいません。")
        return

    now = datetime.now()
    timestamp = now.strftime("%Y%m%d_%H%M%S")
    departure = now.strftime("%Y-%m-%d %H:%M")
    filename = f"修行の書_{timestamp}.txt"
    filepath = SAVE_DIR / filename

    lines = []
    lines.append("# 修行の書")
    lines.append(f"# 出発: {departure}")
    lines.append("")
    lines.append("## モンスター一覧")
    for i, m in enumerate(monsters, 1):
        lines.append(f"{i}. [{m['field']}] {m['name']} (10 EXP, {m['gold']} G)")
    lines.append("")
    lines.append("## 修行記録")
    lines.append("# 倒したモンスターを以下のフォーマットで1行ずつ記入してください")
    lines.append("# フォーマット: 日時 | モンスター番号 | メモ（省略可）")
    lines.append(f"# 例: {departure} | 1 | 片付けた")
    lines.append(f"# 例: {departure} | 3")
    lines.append("")

    filepath.write_text("\n".join(lines), encoding="utf-8")

    print()
    print("=" * 48)
    tprint("🏔️  修行の旅に出発！")
    print("=" * 48)
    print()
    tprint(f"📜 修行の書を作成しました: {filepath}")
    tprint(f"📝 モンスター数: {len(monsters)}体")
    print()
    tprint("テキストファイルに修行記録を書き込んで、")
    tprint("帰還時に読み込んでください。")
    print()


def import_training_journey(filepath):
    """修行の旅：テキストファイルを読み込んで結果を反映"""
    import re
    content = filepath.read_text(encoding="utf-8")

    # モンスター一覧をパース
    monster_map = {}
    in_monster_section = False
    for line in content.split("\n"):
        if line.strip() == "## モンスター一覧":
            in_monster_section = True
            continue
        if line.strip().startswith("## ") and in_monster_section:
            break
        if in_monster_section:
            m = re.match(r"^(\d+)\.\s+\[(.+?)\]\s+(.+?)\s+\((\d+)\s+EXP,\s+(\d+)\s+G\)", line.strip())
            if m:
                num = int(m.group(1))
                field = m.group(2)
                name = m.group(3)
                gold = int(m.group(5))
                monster_map[num] = {"field": field, "name": name, "gold": gold}

    # 修行記録をパース
    records = []
    in_record_section = False
    for line in content.split("\n"):
        if line.strip() == "## 修行記録":
            in_record_section = True
            continue
        if in_record_section:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = [p.strip() for p in line.split("|")]
            if len(parts) >= 2:
                datetime_str = parts[0]
                try:
                    monster_num = int(parts[1])
                except ValueError:
                    continue
                memo = parts[2] if len(parts) >= 3 else ""
                if monster_num in monster_map:
                    records.append({
                        "datetime": datetime_str,
                        "monster_num": monster_num,
                        "memo": memo,
                    })

    if not records:
        print()
        print("❌ 修行記録が見つかりませんでした。")
        print()
        return False

    # 結果を反映
    data = load_data()
    total_exp = 0
    total_gold = 0

    for rec in records:
        monster = monster_map[rec["monster_num"]]
        exp_gain = 10
        gold_gain = monster["gold"]

        data["hero"]["exp"] += exp_gain
        data["hero"]["gold"] = data["hero"].get("gold", 0) + gold_gain
        data["hero"]["total_battles"] += 1
        data["hero"]["total_victories"] += 1

        total_exp += exp_gain
        total_gold += gold_gain

        # 日時をパースしてログに記録
        date_str = None
        time_str = None
        dt_parts = rec["datetime"].split()
        if len(dt_parts) >= 1:
            date_str = dt_parts[0]
        if len(dt_parts) >= 2:
            time_str = dt_parts[1]

        log_message = monster["name"]
        if rec["memo"]:
            log_message += f"（{rec['memo']}）"

        log_adventure(
            monster["field"],
            log_message,
            "✓",
            date=date_str,
            time=time_str,
        )

    # レベルアップチェック
    old_level = data["hero"]["level"]
    new_level = 1 + (data["hero"]["exp"] // 100)
    data["hero"]["level"] = new_level

    save_data(data)

    # 結果サマリー表示
    print()
    print("=" * 48)
    tprint("🏔️  修行の旅から帰還！")
    print("=" * 48)
    print()
    tprint(f"⚔️  討伐数: {len(records)}体")
    tprint(f"✨ 獲得EXP: +{total_exp} (総EXP: {data['hero']['exp']})")
    tprint(f"💰 獲得GOLD: +{total_gold} (所持GOLD: {data['hero']['gold']})")

    if new_level > old_level:
        print()
        tprint("🎊" * 20, delay=0.005)
        tprint(f"🌟 レベルアップ！ Lv.{old_level} → Lv.{new_level}")
        tprint("🎊" * 20, delay=0.005)

    print()

    # 処理済みファイルをリネーム
    done_path = filepath.with_name(filepath.stem + "_済.txt")
    filepath.rename(done_path)
    tprint(f"📜 修行の書を処理済みにしました: {done_path.name}")
    print()

    return True


def interactive_training_journey():
    """修行の旅のサブメニュー"""
    while True:
        print()
        print("=" * 48)
        tprint("🏔️  修行の旅")
        print("=" * 48)
        print()

        choice = show_menu([
            ("depart", "🚶 出発（修行の書を作成）"),
            ("return", "🏠 帰還（修行の書を読み込み）"),
            ("back", "🔙 戻る"),
        ])

        if choice == "depart":
            generate_training_journey()
            input("\n[Enter] で続ける...")
        elif choice == "return":
            # 未処理の修行の書を検索
            files = sorted(SAVE_DIR.glob("修行の書_*.txt"))
            # _済.txt を除外
            files = [f for f in files if not f.stem.endswith("_済")]

            if not files:
                print()
                print("❌ 未処理の修行の書がありません。")
                print()
                input("[Enter] で続ける...")
                continue

            print()
            print("📜 修行の書一覧:")
            print()
            menu_items = []
            for i, f in enumerate(files):
                menu_items.append((str(i), f.name))
            menu_items.append(("back", "🔙 戻る"))

            file_choice = show_menu(menu_items)

            if file_choice == "back" or file_choice is None:
                continue

            try:
                idx = int(file_choice)
                selected_file = files[idx]
            except (ValueError, IndexError):
                print("❌ 無効な選択です。")
                continue

            import_training_journey(selected_file)
            input("\n[Enter] で続ける...")
        elif choice == "back" or choice is None:
            break


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
    tprint("🌑 闇の時代の再来...", delay=0.1)
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

        if quest["status"] == "completed":
            print(f"   ✅ 完了済み！")

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
    """冒険の記録を表示（今日分のみ）"""
    from collections import Counter

    today = get_current_date()

    print()
    print("=" * 48)
    print(f"📖 冒険の記録 — {today}")
    print("=" * 48)

    # 今日のログ行を抽出
    today_lines = []
    if LOG_FILE.exists():
        for line in LOG_FILE.read_text(encoding='utf-8').splitlines():
            if line.startswith(today):
                today_lines.append(line)

    # --- 1. 今日のログ全件表示 ---
    print()
    if not today_lines:
        print("   今日はまだ冒険していません。")
    else:
        for line in today_lines:
            print(f"  {line}")

    # --- 2. 討伐モンスター（回数順） ---
    monster_counts = Counter()
    for line in today_lines:
        if not line.endswith("✓"):
            continue
        # フォーマット: "date time [field] monster_name ✓"
        bracket_end = line.find("] ")
        if bracket_end == -1:
            continue
        monster_name = line[bracket_end + 2:].rstrip(" ✓").rstrip()
        # クエストログは除外
        bracket_start = line.find("[")
        category = line[bracket_start + 1:bracket_end]
        if category.startswith("📜"):
            continue
        monster_counts[monster_name] += 1

    print()
    print("-" * 48)
    print("⚔️  討伐モンスター（回数順）")
    print()
    if not monster_counts:
        print("   今日はまだ討伐していません。")
    else:
        for monster, count in monster_counts.most_common():
            bar = "★" * min(count, 10)
            print(f"  {bar} ×{count}  {monster}")

    # --- 3. 未討伐モンスター ---
    data = load_data()
    active_monsters = []
    for monsters in data["field_tasks"].values():
        active_monsters.extend(m["monster"] for m in monsters if m.get("active", 1) == 1)

    defeated_today = set(monster_counts.keys())
    undefeated = [m for m in active_monsters if m not in defeated_today]

    print()
    print("-" * 48)
    print("💤 未討伐モンスター")
    print()
    if not undefeated:
        print("   全モンスター討伐済み！完璧な一日！")
    else:
        from datetime import date as dt_date
        history, all_dates = get_monster_history()
        total_days = len(all_dates)
        today_dt = dt_date.fromisoformat(today)

        def days_since_last(monster):
            defeated_dates = history.get(monster, set())
            if not defeated_dates:
                return float('inf')
            last_dt = dt_date.fromisoformat(max(defeated_dates))
            return (today_dt - last_dt).days

        undefeated_sorted = sorted(undefeated, key=days_since_last)
        for monster in undefeated_sorted:
            defeated_dates = history.get(monster, set())
            if defeated_dates:
                last_dt = dt_date.fromisoformat(max(defeated_dates))
                days_ago = (today_dt - last_dt).days
                suffix = f"最終: {days_ago}日前"
            else:
                suffix = "履歴なし"
            print(f"  ・{monster}  ({suffix})")

    # --- 4. 統計情報 ---
    total_active = len(active_monsters)
    covered = sum(1 for m in active_monsters if m in defeated_today)
    coverage = covered / total_active * 100 if total_active > 0 else 0
    total_victories = sum(monster_counts.values())

    print()
    print("-" * 48)
    print("📊 統計")
    print()
    print(f"  討伐数（延べ）  : {total_victories} 回")
    print(f"  討伐種数        : {covered} / {total_active} 体")
    print(f"  カバー率        : {coverage:.1f}%")
    print()
    input("[Enter] で続ける...")

# ==================== モンスター図鑑 ====================

def show_monster_encyclopedia():
    """神モード専用：全モンスターの一覧を表示する"""
    data = load_data()

    print()
    print("=" * 48)
    print("📖 モンスター図鑑")
    print("=" * 48)

    if not data["field_tasks"]:
        print()
        print("   モンスターがまだいません。")
        print()
        input("[Enter] で続ける...")
        return

    sign = lambda v: ("+" if v > 0 else "") + str(v)

    total_monsters = 0
    total_active = 0

    for field_name, monsters in data["field_tasks"].items():
        if not monsters:
            continue
        active_count = sum(1 for m in monsters if m.get("active", 1) == 1)
        print()
        print(f"  {field_name}  ({len(monsters)}体 / 活動中 {active_count}体)")
        print()
        for m in monsters:
            active = m.get("active", 1)
            weight = m.get("weight", 0)
            gold = m.get("gold", 1)
            status = "✅" if active else "🔒"
            sealed_label = "  [封印中]" if not active else ""
            print(f"    {status} {m['monster']}")
            print(f"         出現率 {sign(weight)}  💰 {gold}G{sealed_label}")
        total_monsters += len(monsters)
        total_active += active_count

    print()
    print("-" * 48)
    print(f"合計: {total_monsters}体  活動中: {total_active}体  封印中: {total_monsters - total_active}体")
    print()
    input("[Enter] で続ける...")


def god_nominate_monster():
    """神モード専用：モンスターを指名して即座に討伐する"""
    data = load_data()

    # 全フィールドのモンスターをフラットなリストに収集（封印中も含む）
    all_monsters = []
    for field_name, monsters in data["field_tasks"].items():
        for m in monsters:
            all_monsters.append((field_name, m))

    if not all_monsters:
        print()
        print("   モンスターがまだいません。")
        print()
        input("[Enter] で続ける...")
        return

    print()
    print("=" * 48)
    print("🎯 モンスター指名討伐")
    print("=" * 48)
    print()

    for i, (field_name, m) in enumerate(all_monsters, 1):
        active = m.get("active", 1)
        status = "✅" if active else "🔒"
        gold = m.get("gold", 1)
        print(f"  {i:2}. {status} [{field_name}] {m['monster']}  💰{gold}G")

    print()
    try:
        raw = input("討伐するモンスターの番号を入力（Enterでキャンセル）: ").strip()
    except (EOFError, KeyboardInterrupt):
        return

    if not raw:
        return

    if not raw.isdigit() or not (1 <= int(raw) <= len(all_monsters)):
        print("❌ 無効な番号です。")
        input("[Enter] で続ける...")
        return

    field_name, monster_obj = all_monsters[int(raw) - 1]
    monster_name = monster_obj["monster"]
    gold_gain = monster_obj.get("gold", 1)
    exp_gain = 10

    # 統計・EXP・ゴールド更新
    data["hero"]["total_battles"] += 1
    data["hero"]["total_victories"] += 1
    data["hero"]["exp"] += exp_gain
    data["hero"]["gold"] = data["hero"].get("gold", 0) + gold_gain

    old_level = data["hero"]["level"]
    new_level = 1 + (data["hero"]["exp"] // 100)
    data["hero"]["level"] = new_level

    save_data(data)

    # ログ記録
    log_adventure(field_name, monster_name, "✓")

    # 結果表示
    print()
    print("=" * 48)
    tprint("⚡ 神の裁き！")
    print("=" * 48)
    tprint(f"👹 {monster_name} を討伐した！")
    tprint(f"✨ EXP +{exp_gain} (総EXP: {data['hero']['exp']})")
    tprint(f"💰 GOLD +{gold_gain} (所持GOLD: {data['hero']['gold']})")

    if new_level > old_level:
        print()
        tprint("🎊" * 20, delay=0.005)
        tprint(f"🌟 レベルアップ！ Lv.{old_level} → Lv.{new_level}")
        tprint("🎊" * 20, delay=0.005)

    print()
    input("[Enter] で続ける...")


# ==================== 対話モード ====================

def interactive():
    """完全対話型RPGモード（ゴマタスク interactive 風）"""
    print()
    print("=" * 48)
    tprint("🎮 人生RPG - Interactive Mode")
    print("=" * 48)
    print()

    while True:
        # bgm.stop()  # メインメニューでは BGM を停止
        bgm.play("field")  # いや、メインメニューにもBGMつけたい
        data = load_data()
        hero = data["hero"]

        print()
        print("-" * 48)
        god_indicator = " | 👁 神" if rpg_ui.god_mode else ""
        print(f"⚔️  勇者 Lv.{hero['level']} | EXP {hero['exp']} | 💰 {hero.get('gold', 0)} G{god_indicator}")
        print("-" * 48)
        print()
        print("どうする？")
        print()
        choice = show_menu([
            ("explore", "🌍 フィールド探索（モンスター討伐で経験値稼ぎ）"),
            ("quest", "📜 クエスト（大きな目標に挑戦）"),
            ("training", "🏔️  修行の旅（オフラインで経験値稼ぎ）"),
            ("chest", "📦 チェスト管理（物の収納場所を管理）"),
            ("status", "📊 ステータス確認"),
            ("log", "📖 冒険の記録"),
            ("quit", "🚪 終了"),
        ], god_items=[
            ("encyclopedia", "📖 モンスター図鑑"),
            ("nominate", "🎯 モンスター指名討伐"),
            ("create", "✨ モンスターを創造する"),
            ("unleash", "🌑 闇の時代の再来（全モンスター解放）"),
        ])

        if choice == "explore":
            interactive_field_explore()
        elif choice == "quest":
            interactive_quest()
        elif choice == "training":
            interactive_training_journey()
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
        elif choice == "encyclopedia":
            show_monster_encyclopedia()
        elif choice == "nominate":
            god_nominate_monster()
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
            ("undefeated", "今日まだ勝利していないモンスター"),
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
        elif choice == "undefeated":
            explore("undefeated_today")
        else:
            return

    bgm.play("field")  # フィールド探索 BGM 開始

    # 探索ループ
    last_encounter = None
    while True:
        data = load_data()

        if not data["field_state"]["exploring"]:
            # 探索終了
            break

        # 残りのモンスター数チェック
        remaining = len(data["field_state"]["session_encounters"])
        if data["field_state"]["current_encounter"]:
            remaining += 1

        # 現在のエンカウント状態チェック
        if data["field_state"]["current_encounter"]:
            bgm.play("battle")  # エンカウント中はバトル BGM
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
                ("quest", "📜 クエスト確認"),
                ("return", "🏠 街に戻る（探索中断）"),
            ], god_items=[
                ("rename", "✏️  このモンスターの名前を変更する"),
                ("set_rate", "⚖️  このモンスターの出現率を変更する"),
                ("seal", "🔒 封印（このモンスターを二軍に移動）"),
                ("unseal", "🔓 封印解除（二軍のモンスターと入れ替え）"),
                ("delete", "🔥 このモンスターを世界から消す"),
            ])

            if choice == "victory":
                last_encounter = data["field_state"]["current_encounter"].copy()
                victory()
                input("\n[Enter] で続ける...")
            elif choice == "flee":
                last_encounter = data["field_state"]["current_encounter"].copy()
                flee()
            elif choice == "seal":
                seal()
                input("\n[Enter] で続ける...")
            elif choice == "unseal":
                unseal()
                input("\n[Enter] で続ける...")
            elif choice == "quest":
                interactive_quest()
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
            bgm.play("field")  # エンカウント待機中はフィールド BGM に戻す
            print()
            print("-" * 48)
            print(f"📊 進捗: {data['field_state']['session_victories']}勝 / 残り{remaining}体")
            print("-" * 48)
            print()
            main_items = []
            if remaining > 0:
                main_items.append(("battle", "⚔️  次のモンスターとバトル"))
            main_items.append(("return", "🏠 街に戻る（探索終了）"))
            choice = show_menu(main_items, god_items=[
                ("set_rate", "⚖️  直前のモンスターの出現率を変更する"),
            ])

            if choice == "battle":
                battle()
            elif choice == "return":
                return_to_town()
                input("\n[Enter] で続ける...")
                break
            elif choice == "set_rate":
                if last_encounter:
                    set_monster_rate(encounter=last_encounter)
                    input("\n[Enter] で続ける...")
                else:
                    print("❌ 直前のモンスターがありません。")
            else:
                print("❌ 無効な選択です。")

def interactive_quest():
    """対話型クエスト"""
    bgm.play("quest")  # クエスト BGM 開始
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

# ==================== メイン ====================

def main():
    interactive()

if __name__ == "__main__":
    main()
