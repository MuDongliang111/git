from typing import TypedDict

from langgraph.graph import StateGraph

from langgraph.graph import END




class State(TypedDict):
    name: str
    age: int

def name_node(state):
    print("name_node收到：", state)

# name返回为新名称
    return {
        "name": state["name"] + " -> 李四" 
    }



def age_node(state):
    print("age_node收到：", state)

    return {
        "age": state["age"] + 10
    }


def print_node(state):
    print("print_node收到：", state)

    return {}


builder = StateGraph(State)

builder.add_node("name", name_node)
builder.add_node("age", age_node)
builder.add_node("print", print_node)

builder.set_entry_point("name")

builder.add_edge("name", "age")
builder.add_edge("age", "print")
builder.add_edge("print", END)

graph = builder.compile()

result = graph.invoke(
    {
        "name": "张三",
        "age": 18
    }
)

print("最终结果：", result)