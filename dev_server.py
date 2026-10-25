# -*- coding: utf-8 -*-
"""
dev_server.py —— 本地开发服务器
=================================

用途：在**不安装 EdgeOne CLI、不登录**的前提下，把出行决策 Agent 在本地跑起来，
      让 Vite 前端能像线上一样正常对话。

原理：EdgeOne Makers 注入给业务代码的 `context` 对象，这里本地实现一份替身，
      然后调用真正的业务入口 `agents/chat/index.py::handler` —— 业务代码零改动。

分工：
    dev_server.py  (本文件, 端口 8000)   context 协议 + SSE + 会话存储
    vite           (端口 5173)           前端页面，并把 /chat 等请求代理到本服务

启动：
    .\\.venv\\Scripts\\python.exe dev_server.py
    .\\.venv\\Scripts\\python.exe dev_server.py --port 8787
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import inspect
import json
import os
import sqlite3
import sys
import threading
import time
import types
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PORT = 8000
DB_PATH = os.path.join(ROOT, ".dev_sessions.db")

# stdout/stderr 被 Start-Process 重定向到文件后，Windows 上默认编码退回 GBK；
# 业务 logger 会 print 每段 text_delta，模型输出 emoji（如 🚇）时 GBK 编不了，
# 直接在流式生成器里抛 UnicodeEncodeError 打断整个回答。强制 UTF-8 + 容错。
for _stream in (sys.stdout, sys.stderr):
    if _stream is not None and hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

TEXT_ROLES = {"user", "assistant"}

# conversation_id -> (event_loop, asyncio.Event)
CANCEL_EVENTS: dict[str, tuple[asyncio.AbstractEventLoop, asyncio.Event]] = {}
CANCEL_LOCK = threading.Lock()

# 全局唯一的常驻事件循环（后台线程 run_forever）。
# 不能每个请求 asyncio.run 新开循环：Agents SDK 会缓存共享的 AsyncOpenAI/httpx
# 客户端，绑定在创建时的事件循环上；第二个请求换循环后复用旧客户端就会抛
# "RuntimeError: Event loop is closed"。
_ASYNC_LOOP: asyncio.AbstractEventLoop | None = None


def _start_async_loop() -> None:
    global _ASYNC_LOOP
    _ASYNC_LOOP = asyncio.new_event_loop()
    threading.Thread(target=_ASYNC_LOOP.run_forever, daemon=True, name="agent-asyncio").start()


# ---------------------------------------------------------------------------
# 加载业务代码
# ---------------------------------------------------------------------------
def load_chat_module():
    """加载 agents/chat/index.py。

    不能直接 `import agents.chat.index`：
      1. openai-agents SDK 的顶层包名也叫 agents，会遮蔽本仓库的 agents/ 目录；
      2. index.py 内部用 `from .._logger import` 相对导入，必须挂在某个包下面。
    合成顶层包名 devagents 承载相对导入，同时避开同名冲突。
    """
    top = types.ModuleType("devagents")
    top.__path__ = [os.path.join(ROOT, "agents")]
    sys.modules["devagents"] = top

    chat = types.ModuleType("devagents.chat")
    chat.__path__ = [os.path.join(ROOT, "agents", "chat")]
    sys.modules["devagents.chat"] = chat

    path = os.path.join(ROOT, "agents", "chat", "index.py")
    spec = importlib.util.spec_from_file_location("devagents.chat.index", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["devagents.chat.index"] = module
    spec.loader.exec_module(module)
    return module


CHAT = load_chat_module()


async def _maybe_await(value):
    """SDK 不同版本的 Session 方法有同步/异步两种实现，这里统一桥接。"""
    return await value if inspect.isawaitable(value) else value


def _text_of(content) -> str:
    """把 session item 的 content（str / 分块 list）压平成纯文本。"""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                parts.append(str(block.get("text") or block.get("content") or ""))
        return "".join(parts).strip()
    return ""


def _dedupe(messages: list[dict]) -> list[dict]:
    """去掉相邻重复消息（SDK 与业务代码都会写用户输入，容易重一份）。"""
    out: list[dict] = []
    for msg in messages:
        if out and out[-1]["role"] == msg["role"] and out[-1]["content"] == msg["content"]:
            continue
        out.append(msg)
    return out


# ---------------------------------------------------------------------------
# EdgeOne store 的本地替身 —— 记忆落在 SQLite 文件里
# ---------------------------------------------------------------------------
class LocalStore:
    """实现 index.py 用到的 store 接口：openai_session / get_messages / append_message。"""

    DB = DB_PATH

    def openai_session(self, conversation_id: str, **_kwargs):
        from agents import SQLiteSession

        return SQLiteSession(session_id=conversation_id, db_path=self.DB)

    async def get_messages(self, conversation_id: str, limit: int = 20, **_kwargs):
        session = self.openai_session(conversation_id)
        try:
            items = await _maybe_await(session.get_items(limit=limit))
        except Exception:
            return []

        messages: list[dict] = []
        for item in items or []:
            if not isinstance(item, dict):
                continue
            role = item.get("role")
            text = _text_of(item.get("content"))
            if role in TEXT_ROLES and text:
                messages.append(
                    {
                        "id": str(uuid.uuid4()),
                        "role": role,
                        "content": text,
                        "timestamp": int(time.time() * 1000),
                    }
                )
        return _dedupe(messages)

    async def append_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        user_id: str | None = None,
        **_kwargs,
    ) -> str:
        session = self.openai_session(conversation_id)
        try:
            existing = await _maybe_await(session.get_items(limit=1))
            last = existing[-1] if existing else None
            if isinstance(last, dict) and last.get("role") == role and _text_of(last.get("content")) == content:
                return "skipped-duplicate"
            await _maybe_await(session.add_items([{"role": role, "content": content}]))
        except Exception as exc:  # 写索引失败不该影响对话本身
            print(f"[dev_server] append_message failed: {type(exc).__name__}: {exc}", flush=True)
        return str(uuid.uuid4())

    def list_conversations(self, limit: int = 20) -> list[dict]:
        """列出本地 SQLite 里的全部会话（给左侧栏用）。"""
        if not os.path.exists(self.DB):
            return []
        out: list[dict] = []
        try:
            conn = sqlite3.connect(self.DB)
            conn.row_factory = sqlite3.Row
            sessions = conn.execute(
                "SELECT session_id, created_at FROM agent_sessions ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            for row in sessions:
                sid = row["session_id"]
                rows = conn.execute(
                    "SELECT message_data, created_at FROM agent_messages WHERE session_id=? ORDER BY id",
                    (sid,),
                ).fetchall()
                first_user = ""
                last_text = ""
                last_at = row["created_at"]
                for msg_row in rows:
                    try:
                        item = json.loads(msg_row["message_data"])
                    except Exception:
                        continue
                    role = item.get("role")
                    text = _text_of(item.get("content"))
                    if role not in TEXT_ROLES or not text:
                        continue
                    if role == "user" and not first_user:
                        first_user = text
                    last_text = text
                    last_at = msg_row["created_at"] or last_at
                out.append(
                    {
                        "id": sid,
                        "title": (first_user or "新对话")[:20],
                        "preview": (last_text or "")[:60],
                        "messageCount": len(rows),
                        "lastMessageAt": _to_ms(last_at),
                        "createdAt": _to_ms(row["created_at"]),
                    }
                )
            conn.close()
        except sqlite3.Error as exc:
            print(f"[dev_server] list_conversations failed: {exc}", flush=True)
        return out

    def delete_conversation(self, conversation_id: str) -> bool:
        if not os.path.exists(self.DB):
            return True
        try:
            conn = sqlite3.connect(self.DB)
            conn.execute("DELETE FROM agent_messages WHERE session_id=?", (conversation_id,))
            conn.execute("DELETE FROM agent_sessions WHERE session_id=?", (conversation_id,))
            conn.commit()
            conn.close()
            return True
        except sqlite3.Error as exc:
            print(f"[dev_server] delete_conversation failed: {exc}", flush=True)
            return False


def _to_ms(value) -> int:
    """SQLiteSession 的 created_at 是秒级 REAL，前端要毫秒。"""
    try:
        num = float(value)
    except (TypeError, ValueError):
        return int(time.time() * 1000)
    # 已经是毫秒的情况（时间戳 > 1e11）直接用
    return int(num * 1000) if num < 1e11 else int(num)


STORE = LocalStore()


# ---------------------------------------------------------------------------
# HTTP 服务
# ---------------------------------------------------------------------------
class AgentHTTPHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "DevAgentServer/0.1"

    # ---- 基础工具 ----
    def _read_body(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
        except Exception:
            return {}
        return data if isinstance(data, dict) else {}

    def _send_json(self, payload: dict, status: int = 200) -> None:
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(raw)

    def _send_sse_headers(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.send_header("X-Accel-Buffering", "no")  # 关掉 nginx/代理缓冲
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("[http] %s %s\n" % (self.address_string(), fmt % args))

    # ---- 路由 ----
    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        self._send_json(
            {
                "ok": True,
                "service": "dev_server",
                "routes": [
                    "POST /chat",
                    "POST /stop",
                    "POST /history",
                    "POST /conversations",
                    "POST /clear-history",
                    "POST /delete-conversation",
                ],
            }
        )

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0].rstrip("/") or "/"
        routes = {
            "/chat": self.handle_chat,
            "/stop": self.handle_stop,
            "/history": self.handle_history,
            "/conversations": self.handle_conversations,
            "/clear-history": self.handle_delete,
            "/delete-conversation": self.handle_delete,
        }
        route = routes.get(path)
        if route is None:
            self._send_json({"ok": False, "error": f"unknown route {path}"}, status=404)
            return
        try:
            route()
        except (BrokenPipeError, ConnectionResetError):
            pass  # 浏览器刷新/中止，忽略
        except Exception as exc:  # noqa: BLE001
            print(f"[dev_server] route {path} crashed: {type(exc).__name__}: {exc}", flush=True)
            self.close_connection = True

    # ---- /chat：把 handler 的 SSE 流原样转发给浏览器 ----
    def handle_chat(self) -> None:
        body = self._read_body()
        cid = (
            self.headers.get("makers-conversation-id")
            or body.get("conversation_id")
            or str(uuid.uuid4())
        )
        self._send_sse_headers()

        async def pump() -> None:
            signal = asyncio.Event()
            loop = asyncio.get_running_loop()
            with CANCEL_LOCK:
                CANCEL_EVENTS[cid] = (loop, signal)

            context = types.SimpleNamespace(
                request=types.SimpleNamespace(body=body, signal=signal),
                conversation_id=cid,
                run_id=str(uuid.uuid4()),
                store=STORE,
            )

            try:
                async for frame in CHAT.handler(context):
                    self.wfile.write(frame.encode("utf-8"))
                    self.wfile.flush()
            except Exception as exc:  # noqa: BLE001
                print(f"[dev_server] stream error: {type(exc).__name__}: {exc}", flush=True)
                try:
                    self.wfile.write(
                        CHAT.sse_event(
                            "error",
                            {"message": str(exc), "errorType": type(exc).__name__},
                        ).encode("utf-8")
                    )
                    self.wfile.flush()
                except Exception:
                    pass
            finally:
                with CANCEL_LOCK:
                    CANCEL_EVENTS.pop(cid, None)

        try:
            # 派发到全局常驻事件循环；handler 线程阻塞等待流式输出完成。
            asyncio.run_coroutine_threadsafe(pump(), _ASYNC_LOOP).result()
        finally:
            self.close_connection = True

    # ---- /stop：标记对应的 Event，让流式循环自然退出 ----
    def handle_stop(self) -> None:
        body = self._read_body()
        cid = (
            self.headers.get("makers-conversation-id") or body.get("conversation_id") or ""
        ).strip()
        entry = CANCEL_EVENTS.get(cid)
        if entry:
            loop, event = entry
            loop.call_soon_threadsafe(event.set)
        self._send_json({"ok": True})

    # ---- /history：从 SQLite session 读出消息，刷新页面可恢复 ----
    def handle_history(self) -> None:
        body = self._read_body()
        cid = (body.get("conversation_id") or self.headers.get("makers-conversation-id") or "").strip()
        messages = asyncio.run(STORE.get_messages(cid, limit=100)) if cid else []
        self._send_json({"ok": True, "messages": messages})

    def handle_conversations(self) -> None:
        body = self._read_body()
        limit = int(body.get("limit") or 20)
        self._send_json({"ok": True, "conversations": STORE.list_conversations(limit=limit)})

    def handle_delete(self) -> None:
        body = self._read_body()
        cid = (body.get("conversation_id") or self.headers.get("makers-conversation-id") or "").strip()
        self._send_json({"ok": STORE.delete_conversation(cid) if cid else True})


def main() -> None:
    parser = argparse.ArgumentParser(description="出行决策 Agent —— 本地开发服务器")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()

    ThreadingHTTPServer.daemon_threads = True
    _start_async_loop()
    server = ThreadingHTTPServer((args.host, args.port), AgentHTTPHandler)

    print("=" * 56, flush=True)
    print("  dev_server ready", flush=True)
    print(f"  agent http://{args.host}:{args.port}", flush=True)
    print(f"  sessions db {DB_PATH}", flush=True)
    print("  routes: /chat /stop /history /conversations /clear-history /delete-conversation", flush=True)
    print("=" * 56, flush=True)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[dev_server] stopped", flush=True)
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
