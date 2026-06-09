from typing import TypedDict

from langgraph.graph import StateGraph
from langgraph.graph import END


class State(TypedDict):
    message: str


def student_node(state):
    print("添加学生身份")

    return {
        "message": state["message"] + " -> 学生"
    }


def developer_node(state):
    print("添加开发者身份")

    return {
        "message": state["message"] + " -> Python开发者"
    }

def developer_node2(state):
    print("添加开发者身份2")

    return {
        "message": state["message"] + " -> Java开发者"    }


builder = StateGraph(State)

builder.add_node("student", student_node)

builder.add_node("developer", developer_node)

builder.add_node("developer2", developer_node2)

builder.set_entry_point("student")

builder.add_edge("student", "developer")

builder.add_edge("developer", "developer2")

builder.add_edge("developer2", END)

graph = builder.compile()

result = graph.invoke(
    {
        "message": "张三"
    }
)

print(graph.get_graph().draw_mermaid())
# graph = builder.compile()

# png_data = graph.get_graph().draw_mermaid_png()

# with open("graph.png", "wb") as f:
#     f.write(png_data)

print(result)