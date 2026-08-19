from collections.abc import Sequence
from typing import Protocol

from sentence_transformers import SentenceTransformer


class EmbeddingProvider(Protocol):
    def embed_documents(
        self,
        texts: Sequence[str],
    ) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class SentenceTransformerEmbeddingProvider:
    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self._model: SentenceTransformer | None = None

    @property
    def model(self) -> SentenceTransformer:
        if self._model is None:
            self._model = SentenceTransformer(self.model_name)

        return self._model

    @property
    def dimension(self) -> int:
        dimension = self.model.get_embedding_dimension()

        if dimension is None:
            raise RuntimeError(f"Embedding dimension is unavailable for '{self.model_name}'.")

        return dimension

    def embed_documents(
        self,
        texts: Sequence[str],
    ) -> list[list[float]]:
        if not texts:
            return []

        embeddings = self.model.encode(
            list(texts),
            normalize_embeddings=True,
            convert_to_numpy=True,
        )
        return embeddings.tolist()

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]
