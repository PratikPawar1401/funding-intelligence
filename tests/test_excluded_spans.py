"""
Tests for category suppression over character ranges.

This exists so a section of an FOA can be disqualified from producing certain
tags (populations must not come from eligibility text) without deleting it —
deleting shifts Layer 2's chunk boundaries and perturbs unrelated categories,
which was measured at -0.049 global F1.
"""

from foa_pipeline.tagging.layer2_embedding import L2Tagger

POPULATION = frozenset({"population"})


class TestChunkSpans:
    def test_spans_locate_chunks_in_the_original_text(self):
        tagger = L2Tagger()
        text = " ".join(f"word{i}" for i in range(600))
        spans = tagger.chunk_text_with_spans(text, chunk_size=250, overlap=50)

        assert len(spans) > 1
        for chunk, start, end in spans:
            assert start < end <= len(text)
            # Chunks are whitespace-normalised, so compare first/last tokens
            # rather than expecting a byte-identical slice.
            original = text[start:end]
            assert original.split()[0] == chunk.split()[0]
            assert original.split()[-1] == chunk.split()[-1]

    def test_chunks_overlap_as_configured(self):
        tagger = L2Tagger()
        text = " ".join(f"w{i}" for i in range(500))
        spans = tagger.chunk_text_with_spans(text, chunk_size=100, overlap=20)
        assert spans[1][1] < spans[0][2], "second chunk should start before the first ends"

    def test_chunk_text_still_returns_plain_strings(self):
        """The original API is unchanged for callers that don't need spans."""
        tagger = L2Tagger()
        text = " ".join(f"w{i}" for i in range(300))
        plain = tagger.chunk_text(text)
        with_spans = tagger.chunk_text_with_spans(text)
        assert plain == [c for c, _s, _e in with_spans]
        assert all(isinstance(c, str) for c in plain)

    def test_empty_text(self):
        assert L2Tagger().chunk_text_with_spans("") == []
        assert L2Tagger().chunk_text_with_spans("   ") == []


class TestSuppressionRule:
    """A chunk counts as excluded only on majority overlap."""

    def test_no_spans_suppresses_nothing(self):
        assert L2Tagger._suppressed_categories(0, 100, None) == frozenset()
        assert L2Tagger._suppressed_categories(0, 100, []) == frozenset()

    def test_fully_inside_excluded_region_is_suppressed(self):
        assert L2Tagger._suppressed_categories(
            10, 20, [(0, 100, POPULATION)]
        ) == POPULATION

    def test_no_overlap_is_not_suppressed(self):
        assert L2Tagger._suppressed_categories(
            200, 300, [(0, 100, POPULATION)]
        ) == frozenset()

    def test_minority_overlap_is_not_suppressed(self):
        """A chunk that is mostly programme text keeps its tags."""
        # 10 of 100 characters fall inside the excluded region.
        assert L2Tagger._suppressed_categories(
            90, 190, [(0, 100, POPULATION)]
        ) == frozenset()

    def test_majority_overlap_is_suppressed(self):
        # 90 of 100 characters fall inside the excluded region.
        assert L2Tagger._suppressed_categories(
            10, 110, [(0, 100, POPULATION)]
        ) == POPULATION

    def test_exactly_half_is_not_suppressed(self):
        """Ties resolve toward keeping the tag."""
        assert L2Tagger._suppressed_categories(
            50, 150, [(0, 100, POPULATION)]
        ) == frozenset()

    def test_multiple_spans_union_their_categories(self):
        result = L2Tagger._suppressed_categories(
            0, 10,
            [(0, 100, frozenset({"population"})), (0, 100, frozenset({"method"}))],
        )
        assert result == frozenset({"population", "method"})
