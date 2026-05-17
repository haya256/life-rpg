#!/usr/bin/env python3
"""UI・I/O — キー入力、メニュー、表示ユーティリティ"""

import os
import shutil
import sys
import time
import unicodedata

from rpg_bgm import bgm

_IS_WINDOWS = sys.platform == 'win32'

if _IS_WINDOWS:
    import msvcrt
    os.system('')  # ANSI エスケープコードを有効化
else:
    import select
    import termios
    import tty

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


def _animated_getch_raw():
    """アニメーション付き1キー入力待ち（内部実装）"""
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


def animated_getch():
    """アニメーション付き1キー入力待ち（メニュー用）。m キーでBGMミュートトグル。"""
    while True:
        ch = _animated_getch_raw()
        if ch == 'm':
            bgm.toggle_mute()
            label = "ミュート" if bgm.muted else "ミュート解除"
            print(f"\r🔇 BGM {label}")
            continue
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
    cursor_row = 0  # カーソルがプロンプト起点から何行下にあるか

    def redraw():
        nonlocal cursor_row
        term_width = shutil.get_terminal_size().columns

        before = ''.join(buf[:pos])
        after = ''.join(buf[pos:])
        full = prompt + before + after

        prompt_before_w = display_width(prompt + before)
        full_w = display_width(full)

        # カーソルをプロンプト行の先頭まで戻す
        if cursor_row > 0:
            sys.stdout.write(f'\x1b[{cursor_row}A')
        sys.stdout.write('\r\x1b[J')  # 行頭へ移動 + 画面末まで消去
        sys.stdout.write(full)

        # カーソルを pos の位置に戻す（終端 → pos）
        new_cursor_row = prompt_before_w // term_width
        end_cursor_row = full_w // term_width
        rows_up = end_cursor_row - new_cursor_row
        if rows_up > 0:
            sys.stdout.write(f'\x1b[{rows_up}A')
        target_col = prompt_before_w % term_width
        sys.stdout.write('\r')
        if target_col > 0:
            sys.stdout.write(f'\x1b[{target_col}C')

        cursor_row = new_cursor_row
        sys.stdout.flush()

    redraw()  # 初期描画

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
                        pos += 1
                        redraw()
                    elif b2 == 'D' and pos > 0:  # ←
                        pos -= 1
                        redraw()
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

        # 1-9, a-z のキーを生成
        menu_keys = [str(i) for i in range(1, 10)] + [chr(c) for c in range(ord('a'), ord('z') + 1)]

        for i, (key, label) in enumerate(all_items):
            print(f"{menu_keys[i]}. {label}")
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

        ch_lower = ch.lower()
        if ch_lower in menu_keys[:n]:
            return all_items[menu_keys.index(ch_lower)][0]
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
