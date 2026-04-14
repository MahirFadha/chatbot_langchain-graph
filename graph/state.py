from typing import TypedDict, Annotated, Sequence
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

class AgentState(TypedDict):
    # Instruksi ke LangGraph: Setiap ada pesan baru, tambahkan ke bawah, jangan ditimpa!
    messages: Annotated[Sequence[BaseMessage], add_messages]