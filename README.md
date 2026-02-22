# 人生RPG

日々のこまごまタスクや目標をRPGとして楽しむ人生冒険システム、を目指して開発中の、タスク管理＋αアプリ。

コンセプト・背景は [PROJECT.md](PROJECT.md) を参照してください。

---

## 動作環境

- **OS**: macOS / Linux / Windows
- **Python**: 3.6 以上
- **外部ライブラリ**: 不要（標準ライブラリのみ）

## セットアップ

```bash
# 1. リポジトリをクローン（またはフォルダを配置）
git clone <repo-url>
cd life-rpg

# 2. 実行権限を付与（初回のみ）
chmod +x rpg.py

# 3. 起動
./rpg.py
```

データは `savedata/` に自動保存されます（初回起動時に自動作成）。
初回起動時は `sample_data.json` のサンプルデータが自動的に読み込まれます。

---
