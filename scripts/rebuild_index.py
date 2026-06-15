"""
rebuild_index.py — Recreate the Foundry IQ (Azure AI Search) index with the
unified pipeline schema so it matches what the code actually writes/reads.

The original `foundry-iq-index` had a legacy 9-field schema that no longer
matches the unified archive schema (entry_type, content, stage:int, etc.),
causing two runtime errors:
  - search: "Could not find a property named 'requirement_id'"
  - archive: "Cannot convert the literal '1' to the expected type 'Edm.String'"

This script DROPS and RECREATES the index with correct field types, then
re-seeds the demo data. Run once:

    python3 scripts/rebuild_index.py
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchIndex,
    SimpleField,
    SearchableField,
    SearchFieldDataType,
)

from config.config import AI_SEARCH_ENDPOINT, AI_SEARCH_KEY, AI_SEARCH_INDEX
from pipeline.foundry_iq import seed_demo_data, _DEMO_STORE


def build_index() -> SearchIndex:
    fields = [
        SimpleField(name="id", type=SearchFieldDataType.String, key=True, filterable=True),
        SimpleField(name="requirement_id", type=SearchFieldDataType.String, filterable=True, facetable=True),
        SearchableField(name="requirement_title", type=SearchFieldDataType.String),
        SimpleField(name="entry_type", type=SearchFieldDataType.String, filterable=True, facetable=True),
        SimpleField(name="stage", type=SearchFieldDataType.Int32, filterable=True, sortable=True),
        SimpleField(name="revision", type=SearchFieldDataType.Int32, filterable=True),
        SimpleField(name="status", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="author", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="timestamp", type=SearchFieldDataType.DateTimeOffset, filterable=True, sortable=True),
        SimpleField(name="last_modified", type=SearchFieldDataType.DateTimeOffset, filterable=True, sortable=True),
        SimpleField(name="tags", type=SearchFieldDataType.Collection(SearchFieldDataType.String), filterable=True, facetable=True),
        SearchableField(name="searchable_text", type=SearchFieldDataType.String),
        # content/retraction are stored as JSON strings (Azure has no nested object type without complex fields)
        SimpleField(name="content", type=SearchFieldDataType.String),
        SimpleField(name="retraction", type=SearchFieldDataType.String),
    ]
    return SearchIndex(name=AI_SEARCH_INDEX, fields=fields)


def main() -> None:
    idx_client = SearchIndexClient(
        endpoint=AI_SEARCH_ENDPOINT, credential=AzureKeyCredential(AI_SEARCH_KEY)
    )

    # Drop existing index
    try:
        idx_client.delete_index(AI_SEARCH_INDEX)
        print(f"[rebuild] deleted existing index '{AI_SEARCH_INDEX}'")
    except Exception as e:
        print(f"[rebuild] no existing index to delete ({e})")

    # Create new index
    idx_client.create_index(build_index())
    print(f"[rebuild] created index '{AI_SEARCH_INDEX}' with unified schema")

    # Re-seed demo data (content serialized to JSON string)
    _DEMO_STORE.clear()
    seed_demo_data()
    docs = []
    for doc in _DEMO_STORE.values():
        d = dict(doc)
        if isinstance(d.get("content"), (dict, list)):
            d["content"] = json.dumps(d["content"], ensure_ascii=False)
        if isinstance(d.get("retraction"), (dict, list)):
            d["retraction"] = json.dumps(d["retraction"], ensure_ascii=False)
        docs.append(d)

    search_client = SearchClient(
        endpoint=AI_SEARCH_ENDPOINT, index_name=AI_SEARCH_INDEX,
        credential=AzureKeyCredential(AI_SEARCH_KEY),
    )
    result = search_client.upload_documents(docs)
    ok = sum(1 for r in result if r.succeeded)
    print(f"[rebuild] seeded {ok}/{len(docs)} demo documents")
    print("[rebuild] done.")


if __name__ == "__main__":
    main()
