import asyncio
from typing import TypedDict
from langgraph.graph import StateGraph, END

class State(TypedDict):
    val: int

async def node_a(state: State):
    return {"val": state["val"] + 1}

async def main():
    graph = StateGraph(State)
    graph.add_node("a", node_a)
    graph.set_entry_point("a")
    graph.add_edge("a", END)
    app = graph.compile()
    
    res = await app.ainvoke({"val": 0})
    print(res)

asyncio.run(main())
asyncio.run(main())
asyncio.run(main())
