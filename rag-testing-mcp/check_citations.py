"""Print what rich_citations.document actually contains from the live RAG."""
import asyncio, sys
sys.path.insert(0, 'src')
from rag_testing_mcp.clients.rag_client import RAGClient
from rag_testing_mcp.config import get_settings

async def check():
    client = RAGClient(get_settings())
    resp = await client.run_query("What are the similarities between human DNA and vertebrates?", mode="prelims", top_k=3)
    print("=== rich_citations ===")
    for rc in resp.rich_citations:
        print(f"  chunk_id={rc.chunk_id}  document='{rc.document}'  preview='{rc.preview[:40] if rc.preview else ''}'")
    print()
    print("=== chunks metadata ===")
    for c in resp.chunks[:3]:
        print(f"  chunk_id={c.chunk_id}  source={c.source}")
        print(f"    file_name={c.metadata.get('file_name', 'N/A')}")
        print(f"    page_numbers={c.metadata.get('page_numbers', 'N/A')}")
    await client.close()

asyncio.run(check())
