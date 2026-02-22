# docs/ Web デモ — 内部設計ノート（AIメンテナンス用）

> このドキュメントは将来のAIがこのコードを保守・修正する際に
> すぐに全体を把握できるよう、設計の勘所をまとめたものです。

---

## 全体像

```
[ブラウザ メインスレッド]             [Web Worker スレッド]
  index.html                           worker.js
  ├─ xterm.js（ターミナル表示）        ├─ Pyodide（WebAssembly CPython）
  ├─ localStorage（セーブデータ）      │   ├─ shim.py （実行前）
  ├─ keyQueue（キー入力バッファ）      │   ├─ rpg.py  （本体）
  └─ SharedArrayBuffer ─────────────────┤   └─ patch.py（実行後）
       statusArray[0]                  └─ interactive() でゲーム実行
       keyArray[0..32]

       ↑↑↑ スレッド間の唯一の同期手段 ↑↑↑
```

Python は **Web Worker で同期的に動く**。`getch()` で `Atomics.wait` してブロックし、
メインスレッドがキーを書いて `Atomics.notify` したら再開する。

---

## ファイル別の役割

### `index.html`
- xterm.js でターミナル表示
- `coi-serviceworker.js` を登録（SharedArrayBuffer に必要な COOP/COEP ヘッダ付与）
- `SharedArrayBuffer` を作成して Worker に渡す
- `keyQueue` でキーを管理し `tryFlushQueue()` で Worker に送る
- `worker.onmessage` で Worker からの出力・保存リクエストを処理

### `worker.js`
- Pyodide をロードし、以下を**この順**で実行する:
  1. `shim.py` — I/O・モジュールのモック
  2. `rpg.py` — ゲーム本体（関数定義のみ。`main()` は実行されない）
  3. `patch.py` — I/O・データ関数の上書き
  4. `interactive()` — ゲーム開始（ここが終わるまでブロック）
- `rpg.py` は `raw.githubusercontent.com` から fetch する（docs/ から親ディレクトリへのアクセス不可のため）

### `shim.py`
- `rpg.py` **実行前**に適用する「環境偽装」
- モックするもの: `termios`, `tty`, `select`, `subprocess`, `msvcrt`
- `sys.stdout` → `_WebOut`（postMessage で xterm.js へ転送）
- `sys.stdin` → `_WebIn`（`Atomics.wait` でブロッキング読み取り）
- `os.system` → `lambda cmd: 0`（`battle()` の `clear` コマンド無害化）
- `os.makedirs('/home/pyodide/savedata')` → Pyodide の memfs 上に作成
  （rpg.py が `savedata/` を参照しようとするが Web では使わないため）
- `isatty()` は **False を返す**こと。True にすると rpg.py が termios コードパスを通り複雑化する

### `patch.py`
- `rpg.py` **実行後**に適用する「関数上書き」
- Python のグローバル名前空間に直接上書きするため、rpg.py 内の関数からも反映される（重要）
- 上書きする関数:
  - `getch()` / `animated_getch()` — `Atomics.wait` + `clear_queue` 送信
  - `save_data()` / `load_data()` — `_data_cache` + localStorage 永続化
  - `log_adventure()` — localStorage へのログ追記

### `coi-serviceworker.js`
- GitHub Pages は SharedArrayBuffer に必要な COOP/COEP ヘッダを返さないため、
  Service Worker でヘッダを付与するワークアラウンド
- ほぼ定型コード。触る必要はない

---

## 重要な設計詳細

### 1. Python 関数のパッチ方法

Pyodide で複数の `runPython()` を呼ぶと**すべて同一グローバル名前空間を共有する**。

```
runPython(shimCode)   → グローバルに _WebOut, _WebIn 等を定義
runPython(rpgCode)    → グローバルに save_data, load_data, battle, interactive 等を定義
runPython(patchCode)  → グローバルの save_data, load_data, getch 等を**上書き**
```

Python の `LOAD_GLOBAL` は**実行時にグローバル辞書を参照する**ため、
`battle()` が `save_data()` を呼ぶとき、定義時ではなく**呼び出し時**のグローバルを見る。
つまり patch.py が上書きした後は、rpg.py の関数も自動的に新しい版を使う。

### 2. `if __name__ == "__main__"` 問題

rpg.py の末尾に `if __name__ == "__main__": main()` がある。
`runPython(rpgCode)` 時点では Pyodide の `__name__` が `'__main__'` なので、
このガードが機能せず `main()` → `interactive()` が即座に実行されてしまう。

**対策**: rpg.py 実行直前に `pyodide.globals.set('__name__', 'rpg_module')` で変更、
実行後に `'__main__'` へ戻す。

### 3. Web Worker と localStorage

Web Worker は `localStorage` に**直接アクセスできない**。

**対策**:
- 起動時: メインスレッドが localStorage を読み、`init` メッセージで Worker に渡す
  （Worker は `self.initialSavedData` / `self.initialSavedLog` として保持）
- 保存時: Worker が `postMessage({type:'storage_set', key, value})` を送り、
  メインスレッドが `localStorage.setItem()` を実行

### 4. `_data_cache`（セッション内メモリキャッシュ）

patch.py の `load_data()` は初回だけ `js.initialSavedData` を参照し、
以降は `_data_cache` 変数（Python グローバル）をそのまま返す。

**この仕組みが必要な理由**:
`explore()` などで `save_data(data)` を呼んでも、postMessage は非同期であり
localStorage への反映はメインスレッド次第。もし毎回 `js.initialSavedData`
（起動時の固定値）を返すと、セッション中の変更が次の `load_data()` に反映されない。

`_data_cache = data` は **同じ dict オブジェクトへの参照代入**なので、
rpg.py 内で `data` dict を in-place 変更しても `_data_cache` に反映される。
（Python のオブジェクト参照の仕組みに依存した設計）

### 5. キー入力フロー（最重要・バグが集中しやすい）

```
[ユーザー入力]
  term.onKey → keyQueue.push(key)
              → tryFlushQueue()
                  if statusArray[0] == 0 かつ queue に何かある:
                    keyArray に書き込み
                    statusArray[0] = 1
                    Atomics.notify(statusArray, 0)

[setInterval 30ms]
  → tryFlushQueue() （onKey で送れなかったキーを拾う）

[Python側 getch()]
  Atomics.store(statusArray, 0, 0)   ← 「待機中」フラグ
  postMessage({type:'clear_queue'})  ← キューをクリア（後述）
  Atomics.wait(statusArray, 0, 0)    ← ブロック（notifyされるまで）
  → keyArray からキーを読む
```

### 6. `clear_queue` 機構（バグ修正の核心）

`getch()` が呼ばれる前に、`tprint()` 等の処理中にユーザーが誤ってキーを押すと
`keyQueue` に溜まる。これが次の `getch()` で即座に消費されると誤動作する。

**対策**: `getch()` は `Atomics.store(statusArray, 0, 0)` の直後に
`postMessage({type:'clear_queue'})` を送り、メインスレッドに `keyQueue.length = 0`
させてからブロックに入る。

**レースコンディションの存在について**:
`Atomics.store` は SharedArrayBuffer に即座に反映されるが、`postMessage` は非同期。
`clear_queue` が処理される前に `tryFlushQueue` が動くと、溜まったキーが送られてしまう可能性がある。
ただし実用上は `getch()` が呼ばれる時点で queue が空のケースが大半なため、
現状は許容範囲内の設計となっている。
（根本的に解決するには SharedArrayBuffer を使ったロック機構が必要だが、複雑になるため保留）

### 7. `input()` と `readline()` の注意点

rpg.py のいくつかの箇所で `input("\n[Enter] で続ける...")` を呼ぶ。
これは `sys.stdin.readline()` → `_WebIn.readline()` → `_WebIn.read()` と流れる。

`_WebIn.read()` は **`clear_queue` を送らない**（`getch()` だけが送る）。
このため `input()` の前に keyQueue に溜まったキーが残っていると即座に消費される。

---

## rpg.py の重要な構造

Web デモで関係する箇所のみ記載。

| 関数 | 役割 | 注意点 |
|------|------|--------|
| `interactive()` | メインループ。`interactive_field_explore()` などを呼ぶ | Web では `interactive()` だけを entry point として呼ぶ |
| `interactive_field_explore()` | フィールド探索の対話ループ | `current_encounter` の有無で分岐（後述） |
| `battle()` | エンカウント開始。`current_encounter` をセットして return | **入力を待たない**。表示して return するだけ |
| `victory()` / `flee()` | エンカウント終了。`session_encounters.pop(0)` する | `current_encounter = None` にリセット |
| `show_menu()` | `animated_getch()` を呼んで単キー選択 | Enter/Esc で None を返す。無効キーはループ |
| `tprint()` | 1文字ずつ `time.sleep(delay)` しながら出力 | デフォルト delay=0.02。battle では 0.2（遅い） |

### `interactive_field_explore()` のループ分岐

```python
while True:
    data = load_data()

    if data["field_state"]["current_encounter"]:
        # エンカウント中 → 「完了/逃げる」メニュー
        choice = show_menu([victory, flee, seal, unseal, return])
        if choice == "victory": victory(); input("[Enter]...")
        ...
    else:
        # 非エンカウント → 「次のモンスター/街へ戻る」メニュー
        choice = show_menu([battle, return])
        if choice == "battle": battle()
        ...
```

`battle()` は `current_encounter` をセットして return する（入力待ちなし）。
次のループ iteration で `current_encounter` が set されているため、エンカウント分岐に入る。

---

## 過去に踏んだバグと教訓

### Bug 1: `if __name__ == "__main__"` によるデッドロック
- **現象**: ページが永遠にロード中のまま
- **原因**: `runPython(rpgCode)` 時に `main()` → `interactive()` が実行され、
  パッチ適用前に `Atomics.wait` でブロック。Worker が `'ready'` を送れず詰む
- **修正**: rpg.py 実行前に `__name__ = 'rpg_module'` に設定

### Bug 2: `localStorage` アクセス不可 / `DataCloneError`
- **原因①**: Web Worker では `localStorage` にアクセスできない
- **修正①**: メインスレッドに postMessage で委託
- **原因②**: `to_js(dict)` のデフォルトは JS `Map` を生成。`Map` は `postMessage` で送れない
- **修正②**: `to_js(d, dict_converter=js.Object.fromEntries)` で plain Object に変換

### Bug 3: セッション中の変更がリセットされる
- **現象**: `explore()` で探索開始しても、次の操作でトップメニューに戻る
- **原因**: `load_data()` が毎回 `js.initialSavedData`（起動時の固定値）を返していた
- **修正**: `_data_cache` による in-memory キャッシュ

### Bug 4: 素早く2キー押すと先のキーが消える
- **原因**: SharedArrayBuffer のキーバッファは1つ分しかなく、上書きされる
- **修正**: `keyQueue` を導入し、`statusArray == 0` のときだけ送る

### Bug 5: バトル中の堂々めぐり（最も複雑）
- **現象**: モンスターが出ても「戦う/逃げる」が出ず、同じ画面をループ
- **原因**: `tprint()` の遅延中に押されたキーが keyQueue に溜まり、
  次の `getch()` が即座にそのキーを受け取り誤動作
- **修正**: `getch()` は `clear_queue` を送ってからブロックに入る

---

## デバッグの指針

### Python 側のログ出力
```python
# patch.py 等に一時追加
_post({'type': 'output', 'text': f'[DBG] 変数={変数!r}\n'})
```
xterm.js に直接表示されるので手軽。

### SharedArrayBuffer の状態確認
```javascript
// ブラウザの DevTools Console から
statusArray[0]  // 0=Python待機中, 1=処理中
keyArray[0]     // 現在のキーバイト長
```

### よくある詰まりパターン
| 症状 | 疑うべき箇所 |
|------|-------------|
| ページが永遠にロード中 | `__name__` 問題 / `Atomics.wait` で詰んでいる / 'ready' が送られない |
| キー入力が効かない | statusArray が 1 のまま / clear_queue で詰んでいる |
| 保存が反映されない | `_data_cache` が古い / save_data が呼ばれていない |
| 意図しないメニュー選択 | keyQueue に stale キーが残っている |
| クラッシュ（エラー出力） | Python 例外 → worker.js の catch で赤文字表示 |

---

## rpg.py を変更した際の影響チェックリスト

rpg.py に変更を加えた場合、以下を確認する:

- [ ] `getch()` / `animated_getch()` の呼び出しを追加・変更した → patch.py のオーバーライドが適用されているか
- [ ] `input()` を追加した → `_WebIn.readline()` が処理できるか（複雑な入力は要確認）
- [ ] `save_data()` / `load_data()` の呼び出しを追加した → patch.py のオーバーライドが適用されているか
- [ ] `subprocess` / `termios` / `os.system` 等を追加した → shim.py でモックが必要
- [ ] `if __name__ == "__main__":` のガードが維持されているか
- [ ] 新しい `time.sleep()` の長い処理を追加した → その間キーが溜まらないか確認

---

## バージョン情報

- Pyodide: `v0.27.0`
- xterm.js: `v5.3.0`
- rpg.py 取得元: `https://raw.githubusercontent.com/haya256/life-rpg/main/rpg.py`
  （GitHub Pages の docs/ から親ディレクトリのファイルへ直接アクセスできないための措置）
