"""APIリクエスト間のウェイトタイムを管理するモジュール"""

import asyncio
import time


class RateLimiter:
    """APIリクエスト間のウェイトタイムを管理するクラス

    連続するAPIコール間に指定秒数の待機を挿入し、
    レートリミットエラーを防止する。
    """

    def __init__(self, wait_seconds: float = 1.0) -> None:
        self._wait_seconds = wait_seconds
        self._last_request_time: float = 0.0

    @property
    def wait_seconds(self) -> float:
        """現在のウェイトタイム設定値を返す"""
        return self._wait_seconds

    @wait_seconds.setter
    def wait_seconds(self, value: float) -> None:
        """ウェイトタイムを更新する"""
        self._wait_seconds = max(0.0, value)

    async def wait(self) -> None:
        """前回のリクエストからwait_seconds秒以上経過するまで待機する"""
        if self._wait_seconds <= 0:
            self._last_request_time = time.monotonic()
            return

        now = time.monotonic()
        elapsed = now - self._last_request_time
        remaining = self._wait_seconds - elapsed

        if remaining > 0:
            await asyncio.sleep(remaining)

        self._last_request_time = time.monotonic()
