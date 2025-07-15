from flask import Blueprint, jsonify, request
from neo4j import GraphDatabase

from neo4j_graphrag.retrievers import VectorRetriever
from neo4j_graphrag.generation import GraphRAG
from neo4j_graphrag.embeddings.base import Embedder
from neo4j_graphrag.llm.base import LLMInterface
import requests
from types import SimpleNamespace

askAI_bp = Blueprint('askAI', __name__)

API_KEY = "sk-CIfMuTY9OSFC4Ifs32FofujSJ28bDoCHRp8nEXsJPc4wWs2S"
BASE_URL = "https://api.agicto.cn/v1"
EMBED_MODEL = "text-embedding-3-small"
CHAT_MODEL = "deepseek-chat"

# NEO4J_URI = "neo4j://localhost:7687"
# NEO4J_USER = "neo4j"
# NEO4J_PASSWORD = "24721tianyue@"
NEO4J_URI = "bolt://172.18.18.5:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "20040725"
driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

class DeepSeekEmbedder(Embedder):
    def embed_query(self, text: str):
        url = f"{BASE_URL}/embeddings"
        headers = {
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json"
        }
        payload = {"input": text, "model": EMBED_MODEL}
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
        return data["data"][0]["embedding"]

class DeepSeekChatLLM(LLMInterface):
    def __init__(self, model_name=CHAT_MODEL):
        super().__init__(model_name)

    def invoke(
        self,
        input: str,
        message_history=None,
        system_instruction=None
    ):
        url = f"{BASE_URL}/chat/completions"
        headers = {
            "Authorization": f"Bearer {API_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": input}],
            "temperature": 0.7
        }
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
        answer_text = data["choices"][0]["message"]["content"]

        return SimpleNamespace(content=answer_text)

    async def ainvoke(
        self,
        input: str,
        message_history=None,
        system_instruction=None
    ):
        pass

embedder = DeepSeekEmbedder()
retriever = VectorRetriever(
    driver=driver,
    index_name="contentEmbedding",
    embedder=embedder,
    return_properties=["context"]
)
llm = DeepSeekChatLLM()
rag = GraphRAG(retriever=retriever, llm=llm)

# 这里只对包含project_id属性的KnowledgeNode类型节点进行编码，对节点的context属性进行编码
def update_embeddings(projectId):
    with driver.session() as session:
        result = session.run(
            """
            MATCH (n:KnowledgeNode)
            WHERE n.project_id = $projectId AND n.embedding IS NULL AND n.context IS NOT NULL
            RETURN elementId(n) AS id, n.context AS context
            """,
            {"projectId": projectId}
        )

        for record in result:
            node_id = record["id"]
            context = record["context"]
            if not context:
                print(f"Skipping node with id {node_id} because it has no context")
                continue

            try:
                embedding = embedder.embed_query(context)
                session.run(
                    """
                    MATCH (n)
                    WHERE elementId(n) = $id
                    SET n.embedding = $embedding
                    """,
                    {"id": node_id, "embedding": embedding}
                )
                print(f"Embedding stored for node_id {node_id}")
            except Exception as e:
                print(f"Embedding failed for node_id {node_id}: {e}")


# 查询的时候，应该只查询KnowledgeNode类型且project_id属性等于传入的projectId的节点
def ask_question(query_text, projectId):
    retriever_config = {
        "top_k": 5,
        "filters": {
            "project_id": projectId
        }
    }
    response = rag.search(query_text=query_text, retriever_config=retriever_config)
    print(f"\nLLM Answer:\n{response.answer}")
    return response.answer

@askAI_bp.route("/askAI", methods = ['POST'])
def getAIResponse():
    data = request.get_json()
    projectId = data.get("id")
    query = data.get("query")
    print(projectId)
    print(query)
    update_embeddings(projectId)
    answer = ask_question(query, projectId)
    return jsonify({
        "status": 200,
        "answer": answer
    })
