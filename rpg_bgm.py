"""BGMシステム - シーン別BGMをサイン波合成で生成・再生する"""

# pygame と numpy が両方ある場合のみ有効。なければ静かにスルー。

try:
    import threading as _threading
    import pygame as _pygame
    import numpy as _np
    _pygame.mixer.init(frequency=44100, size=-16, channels=1, buffer=512)
    _BGM_AVAILABLE = True
except Exception:
    _BGM_AVAILABLE = False

if _BGM_AVAILABLE:
    class _BGMPlayer:
        """シーン別BGMをサイン波合成で生成・再生するプレイヤー"""

        _SR = 44100  # サンプルレート

        def __init__(self):
            self._sounds = {}
            self._current = None
            self._channel = None
            self._ready = False
            # 音の生成はバックグラウンドスレッドで（起動をブロックしない）
            _threading.Thread(target=self._build_all, daemon=True).start()

        def _note(self, freq, duration):
            """指定周波数・長さのサイン波サンプル列を生成（float32）"""
            n = int(self._SR * duration)
            if freq == 0 or n == 0:
                return _np.zeros(n, dtype=_np.float32)
            t = _np.arange(n) / self._SR
            # 基音 + 倍音で温かみのある音色に
            wave = (
                _np.sin(2 * _np.pi * freq * t)
                + 0.30 * _np.sin(2 * _np.pi * freq * 2 * t)
                + 0.10 * _np.sin(2 * _np.pi * freq * 3 * t)
            ).astype(_np.float32)
            # アタック/リリースエンベロープ
            atk = min(int(0.015 * self._SR), n)
            rel = min(int(0.08 * self._SR), n)
            if atk > 0:
                wave[:atk] *= _np.linspace(0, 1, atk, dtype=_np.float32)
            if rel > 0:
                wave[-rel:] *= _np.linspace(1, 0, rel, dtype=_np.float32)
            return wave

        def _build_song(self, notes, bpm):
            """(freq_hz, beats) のリストから pygame.Sound を生成してループ再生用に返す"""
            beat = 60.0 / bpm
            parts = [self._note(f, beat * b) for f, b in notes]
            combined = _np.concatenate(parts)
            mx = _np.max(_np.abs(combined))
            if mx > 0:
                combined = combined / mx
            arr = (combined * 32767 * 0.01).astype(_np.int16)
            return _pygame.sndarray.make_sound(arr)

        def _build_all(self):
            """3シーン分の BGM を生成してキャッシュ"""
            try:
                # 音名 → 周波数 (Hz)
                C4, D4, E4, F4, G4, A4, B4 = 262, 294, 330, 349, 392, 440, 494
                C5, D5, E5, G5             = 523, 587, 659, 784
                Bb4                        = 466

                # ── フィールド探索: G メジャー、のどかな冒険感、80 BPM ──
                field_notes = [
                    (G4, 1.0), (B4, 0.5), (D5, 0.5), (B4, 1.0),
                    (G4, 0.5), (A4, 0.5), (C5, 1.0), (A4, 1.0),
                    (B4, 0.5), (D5, 0.5), (G5, 1.0), (D5, 1.0),
                    (E5, 0.5), (D5, 0.5), (B4, 1.0), (G4, 1.0),
                ]
                self._sounds['field'] = self._build_song(field_notes, bpm=80)

                # ── バトル: D マイナー、テンポ速め、140 BPM ──
                battle_notes = [
                    (D4, 0.5), (D4, 0.25), (F4, 0.25), (A4, 0.5), (D5, 0.5),
                    (C5, 0.5), (Bb4, 0.5), (A4, 0.5), (G4, 0.5),
                    (F4, 0.5), (A4, 0.25), (D4, 0.25), (F4, 0.5), (A4, 0.5),
                    (G4, 0.5), (F4, 0.5),  (D4, 1.0),
                ]
                self._sounds['battle'] = self._build_song(battle_notes, bpm=140)

                # ── クエスト: C メジャー、落ち着いた、65 BPM ──
                quest_notes = [
                    (C4, 1.5), (E4, 0.5), (G4, 1.0), (E4, 1.0),
                    (F4, 1.5), (A4, 0.5), (G4, 2.0),
                    (E4, 1.0), (G4, 0.5), (C4, 0.5), (E4, 1.0),
                    (G4, 1.0), (F4, 0.5), (E4, 0.5), (C4, 2.0),
                ]
                self._sounds['quest'] = self._build_song(quest_notes, bpm=65)

                # ── 勝利ファンファーレ: C メジャー、明るい、120 BPM（1回再生） ──
                victory_notes = [
                    (C4, 0.25), (E4, 0.25), (G4, 0.25), (C5, 0.75),
                    (G4, 0.25), (C5, 1.0),
                ]
                self._sounds['victory'] = self._build_song(victory_notes, bpm=120)

                self._ready = True
                # 既に play() が呼ばれていたら遅延再生
                if self._current:
                    self._do_play(self._current)
            except Exception:
                pass

        def _do_play(self, scene):
            sound = self._sounds.get(scene)
            if sound is None:
                return
            if self._channel:
                try:
                    self._channel.stop()
                except Exception:
                    pass
            try:
                loops = 0 if scene == 'victory' else -1
                self._channel = sound.play(loops=loops)
            except Exception:
                pass

        def play(self, scene):
            """指定シーンの BGM を再生（同じシーンなら何もしない）"""
            if scene == self._current:
                return
            self._current = scene
            if scene is None:
                if self._channel:
                    try:
                        self._channel.stop()
                    except Exception:
                        pass
                return
            if self._ready:
                self._do_play(scene)
            # 未完成なら _build_all() 完了時に自動再生される

        def stop(self):
            self.play(None)

    bgm = _BGMPlayer()

else:
    class _NullBGM:
        """BGM 非対応環境用のダミー（何もしない）"""
        def play(self, scene): pass
        def stop(self): pass

    bgm = _NullBGM()
