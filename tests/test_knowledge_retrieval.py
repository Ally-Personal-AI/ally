from pathlib import Path

from ally.knowledge import NewKnowledgeSource
from ally.knowledge.chunking import chunk_text
from ally.knowledge.ingestion import text_sha256
from ally.knowledge.retrieval import KnowledgeContextProvider, LexicalKnowledgeRetriever
from ally.storage.sqlite import SQLiteDatabase, SQLiteKnowledgeStore


def test_knowledge_retrieval_preserves_safe_provenance_without_uri(
    tmp_path: Path,
) -> None:
    store = SQLiteKnowledgeStore(SQLiteDatabase(tmp_path / "ally.sqlite3"))
    source, _ = store.ingest(
        NewKnowledgeSource(
            uri="file:///private/example.txt",
            title="Example Notes",
        ),
        source_sha256=text_sha256("The greenhouse uses drip irrigation."),
        chunks=chunk_text("The greenhouse uses drip irrigation."),
    )

    provider = KnowledgeContextProvider(LexicalKnowledgeRetriever(store))
    blocks = provider.retrieve("greenhouse irrigation")

    assert len(blocks) == 1
    assert str(source.id) in blocks[0].source
    assert "Example Notes" in blocks[0].content
    assert "file:///private/example.txt" not in blocks[0].content
    assert "file:///private/example.txt" not in blocks[0].source
