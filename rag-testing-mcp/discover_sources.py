"""Discover actual filenames from Qdrant via live RAG queries."""
import asyncio, json, sys
sys.path.insert(0, 'src')
from rag_testing_mcp.clients.rag_client import RAGClient
from rag_testing_mcp.config import get_settings

questions = [
    ("q001", "similarities between human DNA and other vertebrates", "prelims"),
    ("q002", "What is cultural ecology?", "prelims"),
    ("q003", "Indus Valley Civilization urban planning", "prelims"),
    ("q004", "fundamental rights guaranteed by Indian Constitution", "prelims"),
    ("q005", "Non-Cooperation Movement India freedom struggle", "mains"),
    ("q007", "brachiation in primates", "prelims"),
    ("q008", "73rd and 74th Constitutional Amendments significance", "prelims"),
    ("q010", "social stratification anthropological perspective", "prelims"),
    ("q011", "causes consequences Revolt of 1857", "mains"),
    ("q012", "Green Revolution impact Indian agriculture", "prelims"),
]

async def discover():
    client = RAGClient(get_settings())
    results = {}
    for qid, question, mode in questions:
        resp = await client.run_query(question, mode=mode, top_k=3)
        filenames = list({
            c.metadata.get("file_name", "") 
            for c in resp.chunks 
            if c.metadata.get("file_name")
        })
        results[qid] = {
            "question": question,
            "answered": resp.answered,
            "routing": resp.routing,
            "filenames": filenames,
            "top_chunk_preview": resp.chunks[0].text[:80] if resp.chunks else "",
        }
        print(f"[{qid}] answered={resp.answered} routing={resp.routing}")
        print(f"       files: {filenames}")
    await client.close()
    with open("discovered_sources.json", "w") as f:
        json.dump(results, f, indent=2)
    print("\nSaved to discovered_sources.json")

asyncio.run(discover())
