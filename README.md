# 人生RPG - コマンドリファレンス

すべての機能は `rpg.py` に統合されています。
コンセプト・背景は [PROJECT.md](PROJECT.md) を参照してください。

---

## 動作環境

- **OS**: macOS / Linux（`termios` を使用するため Windows 非対応）
- **Python**: 3.6 以上
- **外部ライブラリ**: 不要（標準ライブラリのみ）

## セットアップ

```bash
# 1. リポジトリをクローン（またはフォルダを配置）
git clone <repo-url>
cd Tasks

# 2. 実行権限を付与（初回のみ）
chmod +x rpg.py

# 3. 起動
./rpg.py
```

データは `savedata/` に自動保存されます（初回起動時に自動作成）。
初回起動時は `sample_data.json` のサンプルデータが自動的に読み込まれます。

---

## 🌍 フィールド探索

日常の細々したタスクをモンスター討伐として実行する。

```bash
./rpg.py                      # 対話モード起動（推奨）

./rpg.py explore --random 5   # 探索開始（ランダムに5体）
./rpg.py explore --all        # 探索開始（全モンスター）
./rpg.py battle               # 次のモンスターと対峙
./rpg.py victory              # 討伐完了（タスク完了）
./rpg.py flee                 # 逃げる（スキップ）
./rpg.py seal                 # 封印（一時的に非アクティブ化）
./rpg.py return               # 街に戻る（探索終了）
```

---

## 🎯 ミニクエスト

目標をミッションに分解して、順番に達成していく。

```bash
./rpg.py quests                          # クエスト一覧
./rpg.py accept "目標タイトル"           # 新しいクエストを受注
./rpg.py show <id>                       # クエストの詳細・進捗
./rpg.py add-mission <id> "ミッション"   # ミッションを追加
./rpg.py advance <id>                    # 現在のミッションを完了して次へ
```

---

## ステータス・ログ

```bash
./rpg.py status   # 勇者のステータス
./rpg.py log      # 冒険の記録
./rpg.py help     # コマンド一覧
```
