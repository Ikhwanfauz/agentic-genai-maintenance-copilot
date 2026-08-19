from chromadb.api import ClientAPI
from chromadb.errors import NotFoundError

from app.rag.embeddings import EmbeddingProvider
from app.schemas.rag import (
    EngineeringDocumentResult,
    EngineeringDocumentSearchInput,
    EngineeringDocumentSearchOutput,
)
from app.tools.exceptions import VectorStoreNotReadyError


def calculate_relevance_score(distance: float) -> float:
    return 1.0 / (1.0 + max(distance, 0.0))


def applies_to_asset(
    applicable_assets: str,
    asset_code: str | None,
) -> bool:
    if asset_code is None:
        return True

    normalized_assets = applicable_assets.lower()

    return asset_code.lower() in normalized_assets or "all rotating equipment" in normalized_assets


def search_engineering_docs(
    client: ClientAPI,
    embedding_provider: EmbeddingProvider,
    collection_name: str,
    tool_input: EngineeringDocumentSearchInput,
) -> EngineeringDocumentSearchOutput:
    try:
        collection = client.get_collection(name=collection_name)
    except NotFoundError as error:
        raise VectorStoreNotReadyError(collection_name) from error

    collection_count = collection.count()

    if collection_count == 0:
        raise VectorStoreNotReadyError(collection_name)

    candidate_count = min(
        collection_count,
        max(tool_input.top_k * 5, tool_input.top_k),
    )

    query_embedding = embedding_provider.embed_query(tool_input.query)

    query_result = collection.query(
        query_embeddings=[query_embedding],
        n_results=candidate_count,
        include=[
            "documents",
            "metadatas",
            "distances",
        ],
    )

    ids = query_result["ids"][0]
    documents = query_result["documents"][0] if query_result["documents"] is not None else []
    metadatas = query_result["metadatas"][0] if query_result["metadatas"] is not None else []
    distances = query_result["distances"][0] if query_result["distances"] is not None else []

    results: list[EngineeringDocumentResult] = []

    for (
        chunk_id,
        document,
        metadata,
        distance,
    ) in zip(
        ids,
        documents,
        metadatas,
        distances,
        strict=True,
    ):
        metadata = metadata or {}
        applicable_assets = str(
            metadata.get(
                "applicable_assets",
                "unspecified",
            )
        )
        relevance_score = calculate_relevance_score(float(distance))

        if not applies_to_asset(
            applicable_assets,
            tool_input.asset_code,
        ):
            continue

        if relevance_score < tool_input.minimum_relevance:
            continue

        document_id = str(metadata.get("document_id", "unknown"))
        section = str(metadata.get("section", "unknown"))
        source_path = str(metadata.get("source_path", "unknown"))

        results.append(
            EngineeringDocumentResult(
                chunk_id=chunk_id,
                document_id=document_id,
                title=str(metadata.get("title", "unknown")),
                section=section,
                source_path=source_path,
                applicable_assets=applicable_assets,
                content=document or "",
                distance=round(float(distance), 6),
                relevance_score=round(
                    relevance_score,
                    6,
                ),
                citation=(f"{document_id} | {section} | {source_path}"),
            )
        )

        if len(results) >= tool_input.top_k:
            break

    return EngineeringDocumentSearchOutput(
        query=tool_input.query,
        asset_code=tool_input.asset_code,
        returned_result_count=len(results),
        results=results,
    )
