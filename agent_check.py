# -*- coding: utf-8 -*-
"""
端到端自检 —— 把 agents/chat/index.py 里的 Agent 拉起来跑一轮真实对话，
验证「大模型 → 工具调用 → 结论」这条完整链路。

与 tools_check.py 的区别：
    tools_check.py   只测数据层（直接调 _map_tools 的函数）
    agent_check.py   测 Agent 编排层（大模型自己决定调哪个工具、怎么组织答案）

本脚本绕开 EdgeOne 注入的 context 对象，因此不需要 edgeone CLI，也不需要登录。

用法（项目根目录执行）：

    python agent_check.py
    python agent_check.py "我在深圳北站，想去一个有喜茶和优衣库的商场"
"""

from __future__ import annotations

import asyncio
import importlib.util
import os
import sys
import types

DEFAULT_QUESTION = "我在红莲南路地铁站附近，想去一个既有倍轻松又有西厅村屋的离得近的商场，帮我推荐"

ROOT = os.path.dirname(os.path.abspath(__file__))


def load_chat_module():
    """加载 agents/chat/index.py 并返回模块对象。

    不能直接 `import agents.chat.index`：
      1. 安装 openai-agents 后，SDK 的顶层包名同样叫 agents，会遮蔽本仓库的 agents/ 目录；
      2. index.py 内部用 `from .._logger import` 相对导入，必须挂在某个包下面。
    这里合成一个顶层包名 localagents 来承载相对导入，同时避开与 SDK 的同名冲突。
    """
    top = types.ModuleType("localagents")
    top.__path__ = [os.path.join(ROOT, "agents")]
    sys.modules["localagents"] = top

    chat = types.ModuleType("localagents.chat")
    chat.__path__ = [os.path.join(ROOT, "agents", "chat")]
    sys.modules["localagents.chat"] = chat

    path = os.path.join(ROOT, "agents", "chat", "index.py")
    spec = importlib.util.spec_from_file_location("localagents.chat.index", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["localagents.chat.index"] = module
    spec.loader.exec_module(module)
    return module


async def run(question: str) -> None:
    from agents import Runner

    chat = load_chat_module()
    agent = chat.agent

    print("=" * 60)
    print(f"问题：{question}")
    print("=" * 60)

    from openai.types.responses import ResponseTextDeltaEvent

    result = Runner.run_streamed(agent, input=question)

    answer_parts: list[str] = []
    tools: list[str] = []
    raw_event_types: list[str] = []

    async for event in result.stream_events():
        # 记录原始事件类型，便于诊断模型实际吐出的 delta 形态
        raw_event_types.append(event.type)

        if event.type == "raw_response_event":
            data = event.data
            raw_event_types.append(f"raw:{type(data).__name__}")
            if isinstance(data, ResponseTextDeltaEvent):
                answer_parts.append(data.delta)
            else:
                # Chat Completions 形态
                delta = getattr(data, "delta", None)
                if isinstance(delta, str):
                    answer_parts.append(delta)
                else:
                    choices = getattr(data, "choices", None) or []
                    for choice in choices:
                        piece = getattr(getattr(choice, "delta", None), "content", None)
                        if piece:
                            answer_parts.append(piece)

        elif event.type == "run_item_stream_event" and event.name == "tool_called":
            item = event.item
            name = (
                getattr(item, "name", None)
                or getattr(getattr(item, "raw_item", None), "name", None)
            )
            if name:
                tools.append(name)
                print(f"[工具调用] {name}")

    answer = "".join(answer_parts)
    print()
    print("--- Agent 回答 ---")
    print(answer if answer.strip() else "(未捕获到任何文本输出)")
    print()
    print(f"[工具调用] {len(tools)} 次：" + (" → ".join(tools) if tools else "无"))
    print(f"[回答字数] {len(answer)}")

    # 打印原始事件类型分布 —— 用来判断 index.py 里的事件过滤是否会漏掉文本流。
    # index.py 只认 ResponseTextDeltaEvent（Responses API 形态），
    # 但项目用的是 OpenAIChatCompletionsModel（Chat Completions 形态）。
    from collections import Counter

    counts = Counter(raw_event_types)
    print("[事件类型分布] " + ", ".join(f"{k}={v}" for k, v in counts.items()))


if __name__ == "__main__":
    question = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_QUESTION
    asyncio.run(run(question))
