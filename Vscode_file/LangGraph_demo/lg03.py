from typing import TypedDict

from langgraph.graph import StateGraph
from langgraph.graph import END


class State(TypedDict):
    question: str


def router(state):
    print("Router收到：", state)

    if "天气" in state["question"]:
        return "weather"

    return "chat"


def weather_node(state):
    print("进入天气节点")

    return {}


def chat_node(state):
    print("进入聊天节点")

    return {}


builder = StateGraph(State)

builder.add_node("router", lambda x: x) # type: ignore

builder.add_node("weather_node", weather_node)

builder.add_node("chat_node", chat_node)

builder.set_entry_point("router")

builder.add_conditional_edges(
    "router",
    router,
    {
        "weather": "weather_node",
        "chat": "chat_node"
    }
)

builder.add_edge("weather_node", END)
builder.add_edge("chat_node", END)

graph = builder.compile()

graph.invoke(
    {
        "question": "北京天气怎么样"
    }
)