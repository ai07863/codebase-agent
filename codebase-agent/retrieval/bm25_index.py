import math
import re
from collections import Counter
from code_parser.ast_parser import CodeNode
from retrieval.vector_store import SearchResult


_WORD_RE = re.compile(r"[A-Za-z0-9_]+")
_CAMEL_RE = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|[0-9]+")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]+")


def tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    for word in _WORD_RE.findall(text):
        for chunk in word.split("_"):
            tokens.extend(piece.lower() for piece in _CAMEL_RE.findall(chunk))
    for run in _CJK_RE.findall(text):
        tokens.extend(run)
        tokens.extend(run[i:i + 2] for i in range(len(run) - 1))
    return [t for t in tokens if t]


class BM25Index:
    def __init__(self, nodes: list[CodeNode], k1: float = 1.5, b: float = 0.75):
        self.nodes = list(nodes)
        self.k1 = k1
        self.b = b
        self._freqs = [Counter(tokenize(f"{n.name} {n.signature} {n.docstring}")) for n in self.nodes]
        self._lengths = [sum(f.values()) for f in self._freqs]
        self._avgdl = sum(self._lengths) / len(self._lengths) if self._lengths else 0.0
        self._df: Counter = Counter()
        for freqs in self._freqs:
            for term in freqs:
                self._df[term] += 1

    def _idf(self, term: str) -> float:
        n = len(self.nodes)
        df = self._df.get(term, 0)
        return math.log(1 + (n - df + 0.5) / (df + 0.5))

    def search(self, query: str, k: int = 5) -> list[SearchResult]:
        if not self.nodes or self._avgdl == 0:
            return []
        query_terms = tokenize(query)
        scored: list[tuple[float, int]] = []
        for i, freqs in enumerate(self._freqs):
            length = self._lengths[i]
            score = 0.0
            for term in query_terms:
                freq = freqs.get(term, 0)
                if freq == 0:
                    continue
                denom = freq + self.k1 * (1 - self.b + self.b * length / self._avgdl)
                score += self._idf(term) * (freq * (self.k1 + 1)) / denom
            if score > 0:
                scored.append((score, i))
        scored.sort(key=lambda item: item[0], reverse=True)
        results = []
        for score, i in scored[:k]:
            node = self.nodes[i]
            results.append(SearchResult(
                node_id=node.node_id,
                name=node.name,
                file_path=node.file_path,
                start_line=node.start_line,
                end_line=node.end_line,
                score=score,
            ))
        return results