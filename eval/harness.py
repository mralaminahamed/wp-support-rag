"""Offline evaluation harness (FR-EV-1/4/5).

Runs the fixed golden dataset through the full retrieval + generation path with
no live external calls: embeddings come from a deterministic bag-of-words client
and generation from a scripted provider that grounds its answer in the rendered
prompt. The harness seeds a deterministic corpus derived from the dataset, scores
every record (eval/metrics.py), prints a report and a delta against the previous
run, and exits non-zero when the gated thresholds are not met so CI can block a
regression (FR-EV-3).

Run with ``python -m eval.harness``.

Author: Al Amin Ahamed.
"""

from __future__ import annotations

import asyncio
import hashlib
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import ClassVar

from apps.api.config import Settings, get_settings
from apps.api.db.engine import dispose_engine, get_sessionmaker
from apps.api.db.models import Chunk, Document, Plugin, Source
from apps.api.db.redis import close_redis, get_redis
from apps.api.llm.base import CompletionRequest, CompletionResult, TokenUsage
from apps.api.processing.chunker import count_tokens
from apps.api.prompts.registry import get_registry
from apps.api.rag.generator import generate
from apps.api.rag.retriever import RetrievedChunk
from apps.api.rag.service import retrieve
from pydantic import BaseModel
from sqlalchemy import delete

from eval.metrics import answer_similarity, citation_is_accurate, is_faithful, source_in_results

CONTEXT_RECALL_THRESHOLD = 0.85
CITATION_ACCURACY_THRESHOLD = 0.95

DATASET_PATH = Path(__file__).parent / "dataset" / "golden.jsonl"
RUNS_DIR = Path(__file__).parent / "runs"


class GoldenRecord(BaseModel):
    """One golden dataset record (SRS §6 shape)."""

    id: str
    plugin_slug: str
    question: str
    reference_answer: str
    expected_source_substrings: list[str]
    must_cite: bool
    category: str


class RetrievalConfig(BaseModel):
    """The retrieval configuration a run was measured under."""

    top_k: int
    ef_search: int
    rrf_k: int
    vector_weight: float
    lexical_weight: float
    similarity_threshold: float
    rerank_enabled: bool


class EvalMetrics(BaseModel):
    """Aggregate metrics for a run (FR-EV-2)."""

    context_recall: float
    citation_accuracy: float
    faithfulness: float
    mean_answer_similarity: float
    decline_accuracy: float
    n_records: int
    n_answerable: int
    n_must_cite: int
    n_unanswerable: int


class EvalRun(BaseModel):
    """A persisted run with its provenance (FR-EV-5)."""

    timestamp: str
    prompt_version: str
    retrieval_config: RetrievalConfig
    metrics: EvalMetrics


class DeterministicEmbeddingClient:
    """Offline bag-of-words embedding client (no live API; FR-EV-4).

    Content words drive the vector; common stop words are ignored so an
    out-of-corpus question scores near zero and is filtered by the similarity
    threshold, exercising the decline path (FR-GN-7) without a real model.
    """

    _TOKEN = re.compile(r"[a-z0-9]+")
    _STOPWORDS = frozenset(
        "a an the to for and or of in on with is are do does how can i you it "
        "what why where when which my your this that these those from at as be".split()
    )

    def __init__(self, dimensions: int) -> None:
        """Initialise with the target vector width."""
        self.dimensions = dimensions

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one deterministic bag-of-words vector per text."""
        return [self._vector(text) for text in texts]

    def _vector(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for token in self._TOKEN.findall(text.lower()):
            if token in self._STOPWORDS:
                continue
            index = int.from_bytes(hashlib.blake2s(token.encode()).digest()[:4], "big")
            vector[index % self.dimensions] += 1.0
        return vector


class ScriptedProvider:
    """Offline provider that grounds its answer in the rendered prompt (FR-EV-4).

    It extracts the source URLs and the first passage from the rendered user
    message, so a prompt regression that drops the sources or context degrades
    citation accuracy and the CI gate fails (FR-EV-3).
    """

    name: ClassVar[str] = "scripted"
    _SOURCE = re.compile(r"source: (\S+)")
    _FIRST_PASSAGE = re.compile(
        r"\[passage 1\] source: \S+\n(.*?)(?:\n\n|\n\[passage|\n</retrieved_context>)",
        re.S,
    )

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        """Produce a grounded answer citing the first source from the prompt."""
        urls = self._SOURCE.findall(request.user)
        match = self._FIRST_PASSAGE.search(request.user)
        body = match.group(1).strip() if match else ""
        text = f"{body} Source: {urls[0]}" if urls else body
        return CompletionResult(
            text=text,
            model=request.model,
            usage=TokenUsage(
                input_tokens=count_tokens(request.user), output_tokens=count_tokens(text)
            ),
        )


def load_golden(path: Path = DATASET_PATH) -> list[GoldenRecord]:
    """Load and validate the golden dataset.

    Args:
        path: Path to the JSONL dataset.

    Returns:
        list[GoldenRecord]: The parsed records.
    """
    return [
        GoldenRecord.model_validate_json(line)
        for line in path.read_text().splitlines()
        if line.strip()
    ]


async def _seed_corpus(records: list[GoldenRecord], embedder: DeterministicEmbeddingClient) -> None:
    """Seed a deterministic corpus derived from the answerable records.

    Args:
        records: The golden records.
        embedder: The offline embedding client.
    """
    answerable = [r for r in records if r.expected_source_substrings]
    slugs = {r.plugin_slug for r in records}
    factory = get_sessionmaker()

    async with factory() as session:
        await session.execute(delete(Plugin).where(Plugin.slug.in_(slugs)))
        await session.commit()

    async with factory() as session:
        plugins: dict[str, Plugin] = {}
        sources: dict[str, Source] = {}
        for record in answerable:
            if record.plugin_slug not in plugins:
                plugin = Plugin(
                    slug=record.plugin_slug, name=record.plugin_slug, wporg_slug=record.plugin_slug
                )
                session.add(plugin)
                await session.flush()
                source = Source(plugin_id=plugin.id, source_type="wporg_faq")
                session.add(source)
                await session.flush()
                plugins[record.plugin_slug] = plugin
                sources[record.plugin_slug] = source

            anchor = record.expected_source_substrings[-1]
            url = f"https://wordpress.org/plugins/{record.plugin_slug}/#{anchor}"
            content = f"{record.reference_answer} {record.question}"
            document = Document(
                source_id=sources[record.plugin_slug].id,
                plugin_id=plugins[record.plugin_slug].id,
                external_id=record.id,
                doc_type="wporg_faq",
                content_hash=hashlib.sha256(content.encode()).hexdigest(),
                source_url=url,
                title=anchor,
            )
            session.add(document)
            await session.flush()
            embedding = (await embedder.embed([f"{anchor}\n\n{content}"]))[0]
            session.add(
                Chunk(
                    document_id=document.id,
                    plugin_id=plugins[record.plugin_slug].id,
                    chunk_index=0,
                    content=content,
                    heading_path=anchor,
                    token_count=count_tokens(content),
                    embedding=embedding,
                    meta={
                        "plugin_slug": record.plugin_slug,
                        "doc_type": "wporg_faq",
                        "source_url": url,
                        "version": None,
                    },
                )
            )
        await session.commit()


async def _flush_answer_cache() -> None:
    """Clear cached answers so a prompt regression is not masked by the cache."""
    redis = get_redis()
    keys = [key async for key in redis.scan_iter(match="answer:*")]
    if keys:
        await redis.delete(*keys)


async def evaluate(
    settings: Settings,
    embedder: DeterministicEmbeddingClient,
    provider: ScriptedProvider,
) -> EvalMetrics:
    """Run the full path over the dataset and compute aggregate metrics.

    Args:
        settings: Application settings (retrieval/generation config).
        embedder: The offline embedding client.
        provider: The scripted offline generation provider.

    Returns:
        EvalMetrics: The aggregate metrics for the run.
    """
    records = load_golden()
    await _seed_corpus(records, embedder)
    await _flush_answer_cache()
    redis = get_redis()
    factory = get_sessionmaker()

    recall_hits = 0
    citation_hits = 0
    faithful_hits = 0
    similarity_sum = 0.0
    similarity_count = 0
    decline_hits = 0

    answerable = [r for r in records if r.expected_source_substrings]
    must_cite = [r for r in records if r.must_cite]
    unanswerable = [r for r in records if r.category == "unanswerable"]

    for record in records:
        async with factory() as session:
            result = await retrieve(
                session,
                redis,
                embedder,
                record.question,
                plugin_slug=record.plugin_slug,
                settings=settings,
            )
        chunks: list[RetrievedChunk] = result.chunks
        generation = await generate(
            redis, provider, record.question, chunks, model="eval-model", settings=settings
        )
        retrieved_urls = [chunk.source_url for chunk in chunks]
        supplied_urls = [chunk.source_url for chunk in generation.chunks]

        if record.expected_source_substrings and source_in_results(
            record.expected_source_substrings, retrieved_urls
        ):
            recall_hits += 1
        if record.must_cite and citation_is_accurate(
            record.expected_source_substrings, generation.citations
        ):
            citation_hits += 1
        if is_faithful(generation.citations, supplied_urls):
            faithful_hits += 1
        if record.expected_source_substrings and not generation.degraded:
            similarity_sum += answer_similarity(generation.answer, record.reference_answer)
            similarity_count += 1
        if record.category == "unanswerable" and generation.declined:
            decline_hits += 1

    return EvalMetrics(
        context_recall=recall_hits / max(len(answerable), 1),
        citation_accuracy=citation_hits / max(len(must_cite), 1),
        faithfulness=faithful_hits / max(len(records), 1),
        mean_answer_similarity=similarity_sum / max(similarity_count, 1),
        decline_accuracy=decline_hits / max(len(unanswerable), 1),
        n_records=len(records),
        n_answerable=len(answerable),
        n_must_cite=len(must_cite),
        n_unanswerable=len(unanswerable),
    )


def _retrieval_config(settings: Settings) -> RetrievalConfig:
    """Capture the retrieval configuration a run was measured under."""
    return RetrievalConfig(
        top_k=settings.retrieval_top_k,
        ef_search=settings.ef_search,
        rrf_k=settings.rrf_k,
        vector_weight=settings.vector_weight,
        lexical_weight=settings.lexical_weight,
        similarity_threshold=settings.similarity_threshold,
        rerank_enabled=settings.rerank_enabled,
    )


def _load_previous() -> EvalRun | None:
    """Return the previous run, if one was persisted."""
    latest = RUNS_DIR / "latest.json"
    if not latest.exists():
        return None
    return EvalRun.model_validate_json(latest.read_text())


def _persist(run: EvalRun) -> None:
    """Persist the run as the latest and append it to the history (FR-EV-5)."""
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    (RUNS_DIR / "latest.json").write_text(run.model_dump_json(indent=2))
    with (RUNS_DIR / "history.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(run.model_dump_json() + "\n")


def _format_report(run: EvalRun, previous: EvalRun | None) -> str:
    """Render the metrics report with a delta against the previous run."""
    metrics = run.metrics
    previous_metrics = previous.metrics if previous else None
    config = run.retrieval_config.model_dump()
    lines = [
        "=== wp-support-rag eval report ===",
        f"timestamp:      {run.timestamp}",
        f"prompt version: {run.prompt_version}",
        f"retrieval:      {config}",
        f"records:        {metrics.n_records} (answerable={metrics.n_answerable}, "
        f"must_cite={metrics.n_must_cite}, unanswerable={metrics.n_unanswerable})",
        "",
        f"{'metric':<24}{'value':>10}{'prev':>10}{'delta':>10}",
    ]
    gated = {"context_recall", "citation_accuracy"}
    for name in (
        "context_recall",
        "citation_accuracy",
        "faithfulness",
        "mean_answer_similarity",
        "decline_accuracy",
    ):
        value = getattr(metrics, name)
        prev = getattr(previous_metrics, name) if previous_metrics else None
        delta = f"{value - prev:+.3f}" if prev is not None else "  n/a"
        prev_str = f"{prev:.3f}" if prev is not None else "n/a"
        marker = " *" if name in gated else ""
        lines.append(f"{name:<24}{value:>10.3f}{prev_str:>10}{delta:>10}{marker}")
    lines.append("")
    lines.append(
        f"gate: context_recall>={CONTEXT_RECALL_THRESHOLD} "
        f"citation_accuracy>={CITATION_ACCURACY_THRESHOLD}  (* gated)"
    )
    return "\n".join(lines)


def _passes(metrics: EvalMetrics) -> bool:
    """Report whether the gated thresholds are met (FR-EV-3)."""
    return (
        metrics.context_recall >= CONTEXT_RECALL_THRESHOLD
        and metrics.citation_accuracy >= CITATION_ACCURACY_THRESHOLD
    )


async def _amain() -> int:
    """Run the harness end to end and return the process exit code."""
    settings = get_settings()
    embedder = DeterministicEmbeddingClient(settings.embedding_dimensions)
    provider = ScriptedProvider()
    try:
        metrics = await evaluate(settings, embedder, provider)
    finally:
        await dispose_engine()
        await close_redis()

    run = EvalRun(
        timestamp=datetime.now(UTC).isoformat(),
        prompt_version=get_registry().active("support_answer").version,
        retrieval_config=_retrieval_config(settings),
        metrics=metrics,
    )
    previous = _load_previous()
    print(_format_report(run, previous))
    _persist(run)

    if _passes(metrics):
        print("\nRESULT: PASS")
        return 0
    print("\nRESULT: FAIL (gated thresholds not met)")
    return 1


def main() -> None:
    """Entry point for ``python -m eval.harness``."""
    raise SystemExit(asyncio.run(_amain()))


if __name__ == "__main__":
    main()
