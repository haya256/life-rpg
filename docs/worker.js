/**
 * worker.js — Pyodide を動かす Web Worker
 *
 * 処理の流れ:
 *   1. main スレッドから SharedArrayBuffer と初期保存データを受け取る
 *   2. Pyodide をロード
 *   3. rpg.py / shim.py / patch.py / sample_data.json を並列 fetch
 *   4. shim.py (モック・I/O) → rpg.py → patch.py の順で実行
 *   5. interactive() を呼び出してゲーム開始
 *
 * キー入力:
 *   main スレッドが keyArray にキーバイト列を書き込み Atomics.notify() を発火 →
 *   Python の Atomics.wait() がブロック解除 → getch() がキーを返す
 *
 * 画面出力:
 *   Python の sys.stdout.write() が postMessage({type:'output', text}) → xterm.js
 *
 * localStorage:
 *   Web Worker 内では localStorage 不可のため、
 *   保存時は postMessage({type:'storage_set', key, value}) でメインスレッドに委託。
 *   初期データは init メッセージで受け取り self.initialSavedData / self.initialSavedLog に保持。
 */

importScripts('https://cdn.jsdelivr.net/pyodide/v0.27.0/full/pyodide.js');

const REPO_RAW = 'https://raw.githubusercontent.com/haya256/life-rpg/main';

// -----------------------------------------------------------------------
self.onmessage = async (e) => {
  if (e.data.type !== 'init') return;

  // SharedArrayBuffer を self のプロパティとして保持
  // → Python 側で js.statusArray / js.keyArray としてアクセスできる
  self.statusArray = new Int32Array(e.data.statusBuffer);
  self.keyArray    = new Uint8Array(e.data.keyBuffer);

  // localStorage の初期値をメインスレッドから受け取り Python に渡す
  // (Web Worker は localStorage に直接アクセスできないため)
  self.initialSavedData = e.data.initialSavedData ?? null;
  self.initialSavedLog  = e.data.initialSavedLog  ?? null;

  try {
    await runGame();
  } catch (err) {
    postMessage({
      type: 'output',
      text: `\r\n\x1b[31m[エラーが発生しました]\r\n${err}\x1b[0m\r\n`,
    });
  }
};

// -----------------------------------------------------------------------
async function runGame() {
  postMessage({ type: 'status', text: '⏳ Pyodide を読み込み中 (初回は少し時間がかかります)...' });

  // Pyodide ロードと各ファイル fetch を並列実行
  const [pyodide, shimCode, patchCode, rpgCode, rpgUiCode, rpgDataCode, sampleData] = await Promise.all([
    loadPyodide({ indexURL: 'https://cdn.jsdelivr.net/pyodide/v0.27.0/full/' }),
    fetch('./shim.py').then((r) => {
      if (!r.ok) throw new Error(`shim.py の取得に失敗: ${r.status}`);
      return r.text();
    }),
    fetch('./patch.py').then((r) => {
      if (!r.ok) throw new Error(`patch.py の取得に失敗: ${r.status}`);
      return r.text();
    }),
    fetch(`${REPO_RAW}/rpg.py`).then((r) => {
      if (!r.ok) throw new Error(`rpg.py の取得に失敗: ${r.status}`);
      return r.text();
    }),
    fetch(`${REPO_RAW}/rpg_ui.py`).then((r) => {
      if (!r.ok) throw new Error(`rpg_ui.py の取得に失敗: ${r.status}`);
      return r.text();
    }),
    fetch(`${REPO_RAW}/rpg_data.py`).then((r) => {
      if (!r.ok) throw new Error(`rpg_data.py の取得に失敗: ${r.status}`);
      return r.text();
    }),
    fetch(`${REPO_RAW}/sample_data.json`).then((r) => {
      if (!r.ok) throw new Error(`sample_data.json の取得に失敗: ${r.status}`);
      return r.json();
    }),
  ]);

  postMessage({ type: 'status', text: '⚙️  初期化中...' });

  // sample_data を Python グローバル変数 _SAMPLE_DATA として注入
  // (patch.py の load_data() が初回起動時に参照する)
  pyodide.globals.set('_SAMPLE_DATA', pyodide.toPy(sampleData));

  // rpg_ui.py / rpg_data.py を Pyodide ファイルシステムに配置
  // → rpg.py の import rpg_ui / import rpg_data が通るようにする
  pyodide.FS.writeFile('/home/pyodide/rpg_ui.py', rpgUiCode);
  pyodide.FS.writeFile('/home/pyodide/rpg_data.py', rpgDataCode);

  // rpg.py が __file__ から SCRIPT_DIR を解決するために設定
  pyodide.globals.set('__file__', '/home/pyodide/rpg.py');

  // rpg.py 末尾の `if __name__ == "__main__": main()` を抑制するため
  // 一時的に __name__ を変更して実行後に戻す
  pyodide.globals.set('__name__', 'rpg_module');

  // 1. シム (モック・I/O パッチ) を適用
  pyodide.runPython(shimCode);

  // 2. rpg.py を実行 (関数・定数を Pyodide グローバル空間に定義)
  //    __name__ != '__main__' なので main() は自動実行されない
  pyodide.runPython(rpgCode);

  // __name__ を元に戻す（念のため）
  pyodide.globals.set('__name__', '__main__');

  // 3. パッチを適用 (getch / save_data / load_data などを上書き)
  //    rpg.py の関数は __globals__ で Pyodide グローバルを参照するため、
  //    ここで上書きするだけで rpg.py 内の呼び出しにも反映される
  pyodide.runPython(patchCode);

  postMessage({ type: 'ready' });

  // 4. 対話モードを開始 (ゲームが終了するまでここでブロック)
  try {
    pyodide.runPython('interactive()');
  } catch (e) {
    if (e.type === 'KeyboardInterrupt') {
      postMessage({ type: 'output', text: '\r\n\x1b[33m[終了しました。ページをリロードすると再プレイできます]\x1b[0m\r\n' });
    } else {
      throw e;
    }
  }

  postMessage({ type: 'done' });
}
