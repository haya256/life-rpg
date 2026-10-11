# 人生RPG

日々のこまごまタスクや目標をRPGとして楽しむ人生冒険システム、を目指して開発中の、タスク管理＋αアプリ。

コンセプト・背景は [PROJECT.md](PROJECT.md) を参照してください。

---

## 動作環境

- **OS**: macOS / Linux / Windows
- **Python**: 3.6 以上
- **外部ライブラリ**: 不要（標準ライブラリのみ）
  - BGM を鳴らす場合のみ `pygame` と `numpy` が必要（任意）

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

### BGM を鳴らす（任意）

BGM には `pygame` と `numpy` を使います。未インストールでもゲームは無音で普通に遊べます。

```bash
# 1. 仮想環境を作成してライブラリをインストール（初回のみ）
python3 -m venv .venv
.venv/bin/pip install pygame numpy

# 2. 仮想環境の Python で起動
.venv/bin/python rpg.py
```

毎回の起動を楽にするなら、シェルの設定ファイル（`~/.zshrc` など）にエイリアスを追加しておくと便利です。

```bash
alias rpg='(cd /path/to/life-rpg && .venv/bin/python rpg.py)'
```

---
