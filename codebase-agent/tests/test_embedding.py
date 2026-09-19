from embedding.embedder import Embedder


def test_embedder_returns_float_vectors():
    embedder = Embedder()
    texts = ["hello world", "def foo(): pass"]
    vectors = embedder.encode(texts)
    assert len(vectors) == 2
    assert len(vectors[0]) > 0
    assert isinstance(vectors[0][0], float)