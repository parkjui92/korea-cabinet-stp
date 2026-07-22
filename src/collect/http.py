"""korea.kr·행안부 등 정부 사이트를 상대하는 공용 HTTP 계층.

이 사이트들은 연속 요청에 연결을 끊는다(RemoteDisconnected). 지연·재시도·
원본 스냅샷 저장을 여기 한곳에 모아, 수집 모듈이 파싱에만 집중하게 한다.

스냅샷을 남기는 이유: 파서가 틀렸다는 걸 나중에 알게 되더라도 서버를 다시
때리지 않고 재파싱할 수 있어야 한다. 원본은 감사 추적이자 재실행 캐시다.
"""

from __future__ import annotations

import hashlib
import random
import time
from pathlib import Path

import requests

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"

# 정부 사이트를 상대하는 기본 예의. 늦더라도 차단되지 않는 쪽을 택한다.
DEFAULT_DELAY = 1.2
MAX_RETRIES = 5


class Fetcher:
    """지연·재시도·스냅샷 캐시를 갖춘 GET 전용 페처."""

    def __init__(
        self,
        snapshot_dir: Path | str | None = None,
        delay: float = DEFAULT_DELAY,
        max_retries: int = MAX_RETRIES,
    ):
        self.session = requests.Session()
        self.session.headers["User-Agent"] = UA
        self.snapshot_dir = Path(snapshot_dir) if snapshot_dir else None
        if self.snapshot_dir:
            self.snapshot_dir.mkdir(parents=True, exist_ok=True)
        self.delay = delay
        self.max_retries = max_retries
        self._last_request_at = 0.0

    # ------------------------------------------------------------------
    def get(self, url: str, params: dict | None = None, cache_key: str | None = None) -> str:
        """HTML을 반환한다. 스냅샷이 있으면 네트워크를 타지 않는다.

        cache_key가 None이면 캐시하지 않는다(목록처럼 매번 바뀌는 페이지용).
        """
        snapshot = self._snapshot_path(cache_key)
        if snapshot and snapshot.exists():
            return snapshot.read_text(encoding="utf-8")

        html = self._get_with_retry(url, params)

        if snapshot:
            snapshot.write_text(html, encoding="utf-8")
        return html

    # ------------------------------------------------------------------
    def get_bytes(self, url: str, params: dict | None = None) -> bytes:
        """첨부 파일처럼 바이너리를 받는다. 지연·재시도는 동일하게 적용된다."""
        last_error: Exception | None = None

        for attempt in range(self.max_retries):
            self._throttle()
            try:
                response = self.session.get(url, params=params, timeout=120)
                self._last_request_at = time.monotonic()
                response.raise_for_status()
                if not response.content:
                    raise requests.HTTPError("빈 응답")
                return response.content
            except (requests.ConnectionError, requests.Timeout, requests.HTTPError) as exc:
                self._last_request_at = time.monotonic()
                last_error = exc
                time.sleep((2**attempt) + random.uniform(0, 1))
                self._reset_session()

        raise RuntimeError(f"{self.max_retries}회 재시도 실패: {url}") from last_error

    # ------------------------------------------------------------------
    def _reset_session(self) -> None:
        """커넥션 풀이 오염됐을 수 있어 새로 연다."""
        self.session.close()
        self.session = requests.Session()
        self.session.headers["User-Agent"] = UA

    def _snapshot_path(self, cache_key: str | None) -> Path | None:
        if not (self.snapshot_dir and cache_key):
            return None
        # 파일명에 쓸 수 없는 문자가 섞여도 안전하도록 해시로 접미사를 단다.
        safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in cache_key)[:80]
        digest = hashlib.sha1(cache_key.encode("utf-8")).hexdigest()[:8]
        return self.snapshot_dir / f"{safe}.{digest}.html"

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        wait = self.delay - elapsed
        if wait > 0:
            time.sleep(wait)

    def _get_with_retry(self, url: str, params: dict | None) -> str:
        last_error: Exception | None = None

        for attempt in range(self.max_retries):
            self._throttle()
            try:
                response = self.session.get(url, params=params, timeout=30)
                self._last_request_at = time.monotonic()
                response.raise_for_status()
                response.encoding = response.apparent_encoding or "utf-8"
                return response.text
            except (requests.ConnectionError, requests.Timeout, requests.HTTPError) as exc:
                self._last_request_at = time.monotonic()
                last_error = exc
                # 연결이 끊겼다는 건 너무 빨리 두드렸다는 신호다. 지수적으로 물러선다.
                time.sleep((2**attempt) + random.uniform(0, 1))
                self._reset_session()

        raise RuntimeError(f"{self.max_retries}회 재시도 실패: {url} params={params}") from last_error
