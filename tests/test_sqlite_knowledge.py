from pathlib import Path

from ally.knowledge import NewKnowledgeSource
from ally.knowledge.chunking import chunk_text
from ally.knowledge.ingestion import text_sha256
from ally.storage.sqlite import SQLiteDatabase, SQLiteKnowledgeStore


def build_store(path: Path) -> SQLiteKnowledgeStore:
    return SQLiteKnowledgeStore(SQLiteDatabase(path))


def ingest(
    store: SQLiteKnowledgeStore,
    *,
    uri: str,
    text: str,
):
    return store.ingest(
        NewKnowledgeSource(uri=uri, title="Synthetic Notes"),
        source_sha256=text_sha256(text),
        chunks=chunk_text(text),
    )


def test_unchanged_ingest_reuses_revision(tmp_path: Path) -> None:
    store = build_store(tmp_path / "ally.sqlite3")
    text = "Synthetic source content."

    source1, revision1 = ingest(store, uri="file:///synthetic.txt", text=text)
    source2, revision2 = ingest(store, uri="file:///synthetic.txt", text=text)

    assert source2.id == source1.id
    assert source2.current_revision == 1
    assert revision2.id == revision1.id
    assert len(store.list_revisions(source1.id)) == 1


def test_changed_ingest_creates_revision_and_preserves_history(tmp_path: Path) -> None:
    store = build_store(tmp_path / "ally.sqlite3")
    source1, revision1 = ingest(
        store,
        uri="file:///synthetic.txt",
        text="First synthetic version.",
    )
    source2, revision2 = ingest(
        store,
        uri="file:///synthetic.txt",
        text="Second synthetic version with changed content.",
    )

    assert source2.id == source1.id
    assert source2.current_revision == 2
    assert revision2.revision == 2

    revisions = store.list_revisions(source1.id)
    assert [item.revision for item in revisions] == [2, 1]

    old_chunks = store.list_revision_chunks(revision1.id)
    current_chunks = store.list_current_chunks(source1.id)
    assert "First synthetic version." in old_chunks[0].content
    assert "Second synthetic version" in current_chunks[0].content


def test_search_candidates_only_include_current_revisions(tmp_path: Path) -> None:
    store = build_store(tmp_path / "ally.sqlite3")
    source, _ = ingest(
        store,
        uri="file:///synthetic.txt",
        text="Obsolete orchard note.",
    )
    ingest(
        store,
        uri="file:///synthetic.txt",
        text="Current greenhouse note.",
    )

    candidates = store.list_search_candidates()

    assert {chunk.revision for chunk in candidates} == {2}
    assert all(chunk.source_id == source.id for chunk in candidates)


def test_delete_source_cascades_revisions_and_chunks(tmp_path: Path) -> None:
    database_path = tmp_path / "ally.sqlite3"
    store = build_store(database_path)
    source, revision = ingest(
        store,
        uri="file:///delete-me.txt",
        text="Synthetic deletion target.",
    )
    assert store.list_revisions(source.id)
    assert store.list_revision_chunks(revision.id)

    assert store.delete_source(source.id) is True
    assert store.get_source(source.id) is None
    assert store.list_revision_chunks(revision.id) == ()

    database = SQLiteDatabase(database_path)
    with database.connect() as connection:
        revisions = connection.execute(
            "SELECT COUNT(*) FROM knowledge_revisions WHERE source_id = ?",
            (str(source.id),),
        ).fetchone()
        chunks = connection.execute(
            "SELECT COUNT(*) FROM knowledge_chunks WHERE source_id = ?",
            (str(source.id),),
        ).fetchone()
    assert revisions == (0,)
    assert chunks == (0,)
    assert store.delete_source(source.id) is False
