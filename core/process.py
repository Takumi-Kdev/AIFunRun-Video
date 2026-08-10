"""堅牢な外部プロセス実行（OpenClaw exec-runner / exec-termination の移植）。

`core/agent.py`（opencode 等の外部CLI）や外部ツールを 24 時間安定で呼ぶための
実行層。OpenClaw（MIT）の exec-runner / exec-termination の設計を Python へ移植。

- **絶対タイムアウト**（timeout_ms）: 一定時間で打ち切り
- **アイドルタイムアウト**（no_output_timeout_ms）: 「出力が出ないまま一定時間」で打ち切り
  （外部エージェントのハング対策の要）
- **プロセスツリー回収**（kill_process_tree）: SIGTERM → grace → SIGKILL。子孫も含めて殺す
  （opencode は node/LSP 等の子を持つため必須。孤児プロセス防止）
- **出力上限**（max_output_bytes）: メモリ保護のため上限を超えたら打ち切り
- **出力ストリーミング**（on_output_chunk）: リアルタイム観測
- **終了理由の正規化**: exit / timeout / no_output_timeout / output_limit / error

shell はデフォルト無効（argv ベース実行）＝コマンドインジェクションを防ぐ。
"""
from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

from .logger import write_log


@dataclass
class ProcessResult:
    exit_code: int = -1
    reason: str = "error"            # exit / timeout / no_output_timeout / output_limit / error
    stdout: str = ""
    stderr: str = ""
    combined: str = ""
    timed_out: bool = False
    duration: float = 0.0
    error: str = ""

    @property
    def ok(self) -> bool:
        return self.reason == "exit" and self.exit_code == 0


def _kill_tree(proc: subprocess.Popen, grace_ms: int = 300) -> None:
    """プロセスグループごと終了。SIGTERM → grace → SIGKILL。"""
    pid = proc.pid
    if pid is None:
        return
    try:
        # 別セッション（start_new_session）で起動しているので killpg でツリー回収
        os.killpg(pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        pass
    # grace 後に残党を SIGKILL
    deadline = time.time() + grace_ms / 1000.0
    while time.time() < deadline:
        try:
            proc.poll()
            if proc.poll() is not None:
                return
        except Exception:  # noqa: BLE001
            pass
        time.sleep(0.02)
    try:
        os.killpg(pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


def run_command(
    argv: list[str],
    *,
    timeout_ms: float = 60000,
    no_output_timeout_ms: float | None = None,
    max_output_bytes: int | None = None,
    kill_process_tree: bool = True,
    cwd: str | None = None,
    env: dict | None = None,
    input_text: str | None = None,
    on_output_chunk: Callable[[str, str], None] | None = None,
) -> ProcessResult:
    """外部コマンドを堅牢に実行し、正規化された結果を返す。"""
    start = time.monotonic()
    stdout_lines: list[str] = []
    stderr_lines: list[str] = []
    captured_bytes = [0]  # stdout+stderr 合計バイト
    last_output_at = [time.monotonic()]
    lock = threading.Lock()
    timed_out = [False]

    popen_kwargs: dict = {
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "text": True,
        "cwd": cwd,
        "env": env,
    }
    if input_text is not None:
        popen_kwargs["stdin"] = subprocess.PIPE
    if kill_process_tree and os.name == "posix":
        # 別セッション＝別プロセスグループにしてツリーkillを可能に
        popen_kwargs["start_new_session"] = True

    try:
        proc = subprocess.Popen(argv, **popen_kwargs)
    except Exception as e:  # noqa: BLE001
        write_log(f"process 起動失敗: {e}", "ERROR")
        return ProcessResult(reason="error", error=str(e), duration=time.monotonic() - start)

    def _append(stream: str, text: str) -> None:
        with lock:
            captured_bytes[0] += len(text)
            (stdout_lines if stream == "stdout" else stderr_lines).append(text)
            last_output_at[0] = time.monotonic()
            if on_output_chunk is not None:
                try:
                    on_output_chunk(text, stream)
                except Exception:  # noqa: BLE001
                    pass

    def _reader(stream: str):
        pipe = proc.stdout if stream == "stdout" else proc.stderr
        assert pipe is not None
        for line in pipe:
            _append(stream, line)

    readers = [
        threading.Thread(target=_reader, args=("stdout",), daemon=True),
        threading.Thread(target=_reader, args=("stderr",), daemon=True),
    ]
    for t in readers:
        t.start()

    if input_text is not None and proc.stdin is not None:
        try:
            proc.stdin.write(input_text)
            proc.stdin.close()
        except Exception:  # noqa: BLE001
            pass

    reason = "exit"
    try:
        while True:
            code = proc.poll()
            if code is not None:
                reason = "exit"
                break
            elapsed = time.monotonic() - start
            if timeout_ms and elapsed > timeout_ms / 1000.0:
                reason = "timeout"
                timed_out[0] = True
                break
            if no_output_timeout_ms and (time.monotonic() - last_output_at[0]) > no_output_timeout_ms / 1000.0:
                reason = "no_output_timeout"
                timed_out[0] = True
                break
            if max_output_bytes and captured_bytes[0] > max_output_bytes:
                reason = "output_limit"
                break
            time.sleep(0.05)
    finally:
        if timed_out[0] or reason in ("timeout", "no_output_timeout", "output_limit"):
            if kill_process_tree:
                _kill_tree(proc)
            else:
                try:
                    proc.kill()
                except Exception:  # noqa: BLE001
                    pass
        # ストリーム閉鎖
        for t in readers:
            t.join(timeout=0.5)
        if proc.stdout:
            proc.stdout.close()
        if proc.stderr:
            proc.stderr.close()

    exit_code = proc.poll() if proc.poll() is not None else -1
    with lock:
        stdout = "".join(stdout_lines)
        stderr = "".join(stderr_lines)
    return ProcessResult(
        exit_code=exit_code if reason == "exit" else -1,
        reason=reason,
        stdout=stdout,
        stderr=stderr,
        combined=stdout + stderr,
        timed_out=timed_out[0],
        duration=time.monotonic() - start,
    )
