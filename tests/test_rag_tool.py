import math
from collections.abc import Sequence
from pathlib import Path

import chromadb
import pytest
from pydantic import ValidationError

from app.rag.indexer import index_engineering_documents
from app.schemas.rag import EngineeringDocumentSearchInput
from app.tools.exceptions import VectorStoreNotReadyError
from app.tools.rag import search_engineering_docs


class SemanticFakeEmbeddingProvider:
    @staticmethod
    def embed_text(text: str) -> list[float]:
        normalized_text = text.lower()

        mechanical_terms = (
            "vibration",
            "bearing",
            "alignment",
            "coupling",
            "motor",
        )
        hydraulic_terms = (
            "flow",
            "pressure",
            "cavitation",
            "suction",
            "impeller",
        )
        safety_terms = (
            "approval",
            "lockout",
            "isolation",
            "work order",
            "control",
        )

        vector = [
            float(sum(normalized_text.count(term) for term in mechanical_terms) + 0.1),
            float(sum(normalized_text.count(term) for term in hydraulic_terms) + 0.1),
            float(sum(normalized_text.count(term) for term in safety_terms) + 0.1),
        ]

        magnitude = math.sqrt(sum(value**2 for value in vector))

        return [value / magnitude for value in vector]

    def embed_documents(
        self,
        texts: Sequence[str],
    ) -> list[list[float]]:
        return [self.embed_text(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_text(text)


@pytest.fixture
def indexed_vector_store():
    client = chromadb.EphemeralClient()
    embedding_provider = SemanticFakeEmbeddingProvider()

    index_engineering_documents(
        client=client,
        embedding_provider=embedding_provider,
        documents_directory=Path("data/engineering_docs"),
        collection_name="test_engineering_docs",
    )

    return client, embedding_provider


def test_search_engineering_docs_returns_grounded_results(
    indexed_vector_store,
) -> None:
    client, embedding_provider = indexed_vector_store

    result = search_engineering_docs(
        client=client,
        embedding_provider=embedding_provider,
        collection_name="test_engineering_docs",
        tool_input=EngineeringDocumentSearchInput(
            query=("increasing pump and motor vibration coupling alignment"),
            asset_code="p-101",
            top_k=3,
            minimum_relevance=0.0,
        ),
    )

    assert result.asset_code == "P-101"
    assert result.returned_result_count == 3
    assert result.results[0].section in {
        "Elevated Vibration",
        "Correlated Pump and Motor Vibration",
    }
    assert result.results[0].document_id in {
        "ENG-PUMP-001",
        "ENG-MOTOR-001",
    }
    assert result.results[0].citation.endswith(".md")
    assert result.results[0].content


def test_search_engineering_docs_retrieves_safety_guidance(
    indexed_vector_store,
) -> None:
    client, embedding_provider = indexed_vector_store

    result = search_engineering_docs(
        client=client,
        embedding_provider=embedding_provider,
        collection_name="test_engineering_docs",
        tool_input=EngineeringDocumentSearchInput(
            query=("human approval lockout isolation machinery control"),
            asset_code="P-201",
            top_k=1,
            minimum_relevance=0.0,
        ),
    )

    assert result.returned_result_count == 1
    assert result.results[0].document_id == "SOP-MAINT-001"
    assert result.results[0].section in {
        "Work-Order Approval",
        "Machinery Control Boundary",
    }


def test_search_engineering_docs_raises_when_index_is_missing() -> None:
    client = chromadb.EphemeralClient()

    with pytest.raises(
        VectorStoreNotReadyError,
        match="is not ready",
    ):
        search_engineering_docs(
            client=client,
            embedding_provider=SemanticFakeEmbeddingProvider(),
            collection_name="missing_collection",
            tool_input=EngineeringDocumentSearchInput(
                query="pump vibration",
            ),
        )


def test_engineering_document_search_input_rejects_invalid_values() -> None:
    with pytest.raises(ValidationError):
        EngineeringDocumentSearchInput(
            query="  ",
            top_k=11,
        )
