"""
shim.py — rpg.py 読み込み前に適用するブラウザ用パッチ

ブラウザ環境に存在しない以下を差し替えます:
  - termios / tty / select / subprocess / msvcrt (モック)
  - sys.stdin  → SharedArrayBuffer 経由でブロッキング読み取り
  - sys.stdout → postMessage 経由で xterm.js に出力
  - shutil.get_terminal_size → 固定値 (80, 24) を返す
  - os.read(0, n) → sys.stdin.read(n) に転送
"""

import sys
import os
import shutil
from types import ModuleType

import js
from pyodide.ffi import to_js


def _post(msg_dict):
    """Python dict を plain JS Object として postMessage する。
    to_js のデフォルトは Map になり postMessage 不可なので
    dict_converter=js.Object.fromEntries で plain object に変換する。"""
    js.postMessage(to_js(msg_dict, dict_converter=js.Object.fromEntries))


# ===== モジュールモック =====

_termios = ModuleType('termios')
_termios.tcgetattr = lambda fd: [0] * 20
_termios.tcsetattr = lambda fd, when, attrs: None
_termios.TCSADRAIN = 1
sys.modules['termios'] = _termios

_tty = ModuleType('tty')
_tty.setraw = lambda fd: None
_tty.setcbreak = lambda fd: None
sys.modules['tty'] = _tty

_select_mod = ModuleType('select')
def _select_fn(rlist, wlist, xlist, timeout=None):
    # 常に「入力あり」として返す（実際の読み取りは Atomics.wait でブロック）
    return (rlist, [], [])
_select_mod.select = _select_fn
sys.modules['select'] = _select_mod

_subprocess = ModuleType('subprocess')
class _SubResult:
    def __init__(self, stdout=''):
        self.stdout = stdout
        self.returncode = 0

def _subrun(args, **kwargs):
    """date コマンドをブラウザの Date API で代替"""
    from js import Date
    d = Date.new()
    cmd = args[-1] if isinstance(args, list) else args
    if '%H:%M' in cmd:
        return _SubResult(f"{d.getHours():02d}:{d.getMinutes():02d}")
    elif '%Y-%m-%d' in cmd:
        return _SubResult(f"{d.getFullYear()}-{d.getMonth() + 1:02d}-{d.getDate():02d}")
    return _SubResult('')

_subprocess.run = _subrun
sys.modules['subprocess'] = _subprocess

_msvcrt = ModuleType('msvcrt')
_msvcrt.kbhit = lambda: False
_msvcrt.getwch = lambda: ''
sys.modules['msvcrt'] = _msvcrt

_rpg_bgm = ModuleType('rpg_bgm')
class _DummyBgm:
    def play(self, *a, **kw): pass
    def stop(self, *a, **kw): pass
_rpg_bgm.bgm = _DummyBgm()
sys.modules['rpg_bgm'] = _rpg_bgm

# ===== ターミナルサイズ（固定値） =====
shutil.get_terminal_size = lambda fallback=(80, 24): os.terminal_size((80, 24))

# ===== os.system モック（battle() の 'clear' コマンドなどを無害化） =====
os.system = lambda cmd: 0

# ===== 標準出力 → xterm.js =====
class _WebOut:
    def write(self, text):
        _post({'type': 'output', 'text': str(text)})
        return len(str(text))

    def flush(self):
        pass

    def isatty(self):
        return True

_web_out = _WebOut()
sys.stdout = _web_out
sys.stderr = _web_out

# ===== 標準入力 → SharedArrayBuffer 経由ブロッキング読み取り =====
class _WebIn:
    """
    キー入力を SharedArrayBuffer + Atomics.wait でブロッキング受信。
    isatty() は False を返し、rpg.py 内の複雑なターミナル処理を
    シンプルなフォールバックパスへ誘導します。
    実際の単キー読み取りは patch.py で getch() を上書きして実現します。
    """

    def read(self, n=1):
        from js import Atomics
        # 待機中フラグをリセット
        Atomics.store(js.statusArray, 0, 0)
        # キー入力まで Web Worker スレッドを真にブロック
        Atomics.wait(js.statusArray, 0, 0)
        # キーバッファから UTF-8 バイト列を取得
        length = int(js.keyArray[0])
        raw = bytes([int(js.keyArray[i + 1]) for i in range(min(length, 32))])
        return raw.decode('utf-8', errors='replace')

    def readline(self):
        """行入力（エコー・バックスペース対応）"""
        buf = []
        while True:
            ch = self.read(1)
            if ch in ('\r', '\n'):
                sys.stdout.write('\r\n')
                sys.stdout.flush()
                return ''.join(buf) + '\n'
            elif ch in ('\x7f', '\x08'):   # Backspace / Delete
                if buf:
                    buf.pop()
                    sys.stdout.write('\x08 \x08')
                    sys.stdout.flush()
            elif ch == '\x03':              # Ctrl+C
                raise KeyboardInterrupt
            elif ch and (len(ch) > 1 or ord(ch[0]) >= 32):  # 印字可能文字
                buf.append(ch)
                sys.stdout.write(ch)
                sys.stdout.flush()

    def fileno(self):
        return 0

    def isatty(self):
        # False を返すことで rpg.py の termios 処理を回避
        return False

sys.stdin = _WebIn()

# ===== os.read(0, n) パッチ（input_with_prefill の内部 os.read 対応） =====
_orig_os_read = os.read

def _patched_os_read(fd, n):
    if fd == 0:
        return sys.stdin.read(n).encode('utf-8')
    return _orig_os_read(fd, n)

os.read = _patched_os_read

# ===== savedata ディレクトリを Pyodide の memfs に作成 =====
os.makedirs('/home/pyodide/savedata', exist_ok=True)
