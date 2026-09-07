"""Check what the RAG actually says for q001 and what's in context."""
import asyncio, sys
sys.path.insert(0, 'src')
from rag_testing_mcp.clients.rag_client import RAGClient
from rag_testing_mcp.config import get_settings

async def check():
    client = RAGClient(get_settings())
    resp = await client.run_query("What are the similarities between human DNA and other vertebrates DNA?", mode="prelims", top_k=5)
    print("=== ANSWER ===")
    print(resp.answer[:500])
    print()
    print("=== CHUNKS TEXT (for 96% check) ===")
    for i, c in enumerate(resp.chunks):
        if '96' in c.text or 'percent' in c.text.lower() or '%' in c.text:
            print(f"[chunk {i}] {c.text[:200]}")
            print()
    print("=== rich_citations.document ===")
    for rc in resp.rich_citations:
        print(f"  doc='{rc.document}'  chunk_id={rc.chunk_id}")
    await client.close()

asyncio.run(check())
