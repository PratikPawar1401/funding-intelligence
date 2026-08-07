"""
Tests for the NSF award discipline benchmark.

Metric logic is tested against hand-built rankings rather than a live model, so
the arithmetic is verifiable by inspection and the suite stays fast.
"""

import json

import pytest

from foa_pipeline.evaluation.discipline_benchmark import (
    evaluate_predictions,
    format_benchmark_report,
    load_award_corpus,
    rank_concepts,
)


def record(primary, acceptable=None, abstract="text"):
    return {
        "award_id": "1",
        "abstract": abstract,
        "primary_concept_id": primary,
        "acceptable_concept_ids": acceptable or [primary],
    }


class TestRankConcepts:
    def test_orders_by_descending_score(self):
        ranked = rank_concepts({"a": 0.1, "b": 0.9, "c": 0.5})
        assert ranked == ["b", "c", "a"]

    def test_ties_break_deterministically_on_id(self):
        """Insertion order must not decide top-1 accuracy."""
        assert rank_concepts({"z": 0.5, "a": 0.5}) == ["a", "z"]
        assert rank_concepts({"a": 0.5, "z": 0.5}) == ["a", "z"]

    def test_empty_scores(self):
        assert rank_concepts({}) == []


class TestTopKAccuracy:
    def test_all_correct(self):
        records = [record("nsf_bio"), record("nsf_mps")]
        rankings = [["nsf_bio", "nsf_geo"], ["nsf_mps", "nsf_eng"]]
        report = evaluate_predictions(records, rankings)
        assert report["strict_top1_accuracy"] == 1.0
        assert report["mrr"] == 1.0

    def test_all_wrong(self):
        records = [record("nsf_bio"), record("nsf_mps")]
        rankings = [["nsf_geo", "nsf_eng"], ["nsf_geo", "nsf_eng"]]
        report = evaluate_predictions(records, rankings)
        assert report["strict_top1_accuracy"] == 0.0
        assert report["strict_topk_accuracy"] == 0.0
        assert report["mrr"] == 0.0

    def test_half_correct(self):
        records = [record("nsf_bio"), record("nsf_mps")]
        rankings = [["nsf_bio"], ["nsf_geo"]]
        assert evaluate_predictions(records, rankings)["strict_top1_accuracy"] == 0.5

    def test_top_k_credits_a_lower_ranked_correct_answer(self):
        records = [record("nsf_bio")]
        rankings = [["nsf_geo", "nsf_eng", "nsf_bio"]]
        report = evaluate_predictions(records, rankings, top_k=3)
        assert report["strict_top1_accuracy"] == 0.0
        assert report["strict_topk_accuracy"] == 1.0

    def test_top_k_respects_the_cutoff(self):
        records = [record("nsf_bio")]
        rankings = [["nsf_geo", "nsf_eng", "nsf_mps", "nsf_bio"]]
        assert evaluate_predictions(records, rankings, top_k=3)["strict_topk_accuracy"] == 0.0
        assert evaluate_predictions(records, rankings, top_k=4)["strict_topk_accuracy"] == 1.0

    def test_mrr_reflects_rank_position(self):
        records = [record("nsf_bio")]
        rankings = [["nsf_geo", "nsf_eng", "nsf_bio"]]
        assert evaluate_predictions(records, rankings)["mrr"] == pytest.approx(1 / 3)

    def test_mrr_is_zero_when_label_absent_from_ranking(self):
        records = [record("nsf_bio")]
        rankings = [["nsf_geo"]]
        assert evaluate_predictions(records, rankings)["mrr"] == 0.0


class TestLenientScoring:
    """Co-funded awards must not be scored as errors for naming a co-funder."""

    def test_cofunder_counts_as_lenient_but_not_strict(self):
        records = [record("nsf_eng", ["nsf_eng", "nsf_cise"])]
        rankings = [["nsf_cise", "nsf_eng"]]
        report = evaluate_predictions(records, rankings)
        assert report["strict_top1_accuracy"] == 0.0
        assert report["lenient_top1_accuracy"] == 1.0

    def test_unrelated_prediction_fails_both(self):
        records = [record("nsf_eng", ["nsf_eng", "nsf_cise"])]
        rankings = [["nsf_bio"]]
        report = evaluate_predictions(records, rankings)
        assert report["lenient_top1_accuracy"] == 0.0

    def test_lenient_topk(self):
        records = [record("nsf_eng", ["nsf_eng", "nsf_cise"])]
        rankings = [["nsf_bio", "nsf_geo", "nsf_cise"]]
        report = evaluate_predictions(records, rankings, top_k=3)
        assert report["lenient_topk_accuracy"] == 1.0
        assert report["lenient_top1_accuracy"] == 0.0

    def test_missing_acceptable_list_falls_back_to_primary(self):
        rec = {"award_id": "1", "abstract": "t", "primary_concept_id": "nsf_bio"}
        report = evaluate_predictions([rec], [["nsf_bio"]])
        assert report["lenient_top1_accuracy"] == 1.0


class TestPerConceptMetrics:
    def test_precision_and_recall_are_computed_per_directorate(self):
        # nsf_bio: 2 true, 1 recalled. nsf_geo predicted twice, right once.
        records = [record("nsf_bio"), record("nsf_bio"), record("nsf_geo")]
        rankings = [["nsf_bio"], ["nsf_geo"], ["nsf_geo"]]
        per = evaluate_predictions(records, rankings)["per_concept"]

        assert per["nsf_bio"]["support"] == 2
        assert per["nsf_bio"]["recall"] == 0.5
        assert per["nsf_bio"]["precision"] == 1.0

        assert per["nsf_geo"]["support"] == 1
        assert per["nsf_geo"]["predicted"] == 2
        assert per["nsf_geo"]["recall"] == 1.0
        assert per["nsf_geo"]["precision"] == 0.5

    def test_concept_never_correct_has_zero_f1_not_a_crash(self):
        records = [record("nsf_bio")]
        rankings = [["nsf_geo"]]
        per = evaluate_predictions(records, rankings)["per_concept"]
        assert per["nsf_bio"]["f1"] == 0.0
        assert per["nsf_geo"]["support"] == 0

    def test_macro_f1_ignores_concepts_with_no_support(self):
        """A never-occurring directorate must not drag the macro average down."""
        records = [record("nsf_bio")]
        rankings = [["nsf_bio", "nsf_geo"]]
        report = evaluate_predictions(records, rankings)
        assert report["per_concept"]["nsf_bio"]["f1"] == 1.0
        assert report["macro_f1"] == 1.0


class TestConfusionMatrix:
    def test_records_true_to_predicted_pairs(self):
        records = [record("nsf_bio"), record("nsf_bio")]
        rankings = [["nsf_geo"], ["nsf_geo"]]
        confusion = evaluate_predictions(records, rankings)["confusion"]
        assert confusion["nsf_bio->nsf_geo"] == 2

    def test_correct_predictions_appear_on_the_diagonal(self):
        records = [record("nsf_bio")]
        rankings = [["nsf_bio"]]
        assert evaluate_predictions(records, rankings)["confusion"]["nsf_bio->nsf_bio"] == 1


class TestDegenerateInputs:
    def test_empty_corpus(self):
        report = evaluate_predictions([], [])
        assert report["total"] == 0
        assert report["strict_top1_accuracy"] == 0.0
        assert report["macro_f1"] == 0.0

    def test_unranked_awards_are_counted_not_silently_dropped(self):
        """Dropping scoring failures would inflate accuracy."""
        records = [record("nsf_bio"), record("nsf_mps")]
        rankings = [["nsf_bio"], []]
        report = evaluate_predictions(records, rankings)
        assert report["total"] == 1
        assert report["unranked"] == 1
        assert report["strict_top1_accuracy"] == 1.0

    def test_mismatched_lengths_are_rejected(self):
        with pytest.raises(ValueError):
            evaluate_predictions([record("nsf_bio")], [])


class TestLoadAwardCorpus:
    def _write(self, tmp_path, lines):
        path = tmp_path / "nsf_awards.jsonl"
        path.write_text("\n".join(lines), encoding="utf-8")
        return tmp_path

    def test_missing_corpus_names_the_command_that_creates_it(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="harvest-nsf-awards"):
            load_award_corpus(tmp_path)

    def test_loads_valid_records(self, tmp_path):
        d = self._write(tmp_path, [json.dumps(record("nsf_bio"))])
        assert len(load_award_corpus(d)) == 1

    def test_skips_malformed_and_incomplete_lines(self, tmp_path):
        d = self._write(tmp_path, [
            json.dumps(record("nsf_bio")),
            "{not json",
            "",
            json.dumps({"award_id": "2", "abstract": "t"}),          # no label
            json.dumps({"award_id": "3", "primary_concept_id": "x"}),  # no abstract
        ])
        assert len(load_award_corpus(d)) == 1

    def test_limit_is_honoured(self, tmp_path):
        d = self._write(tmp_path, [json.dumps(record("nsf_bio")) for _ in range(10)])
        assert len(load_award_corpus(d, limit=3)) == 3


class TestReportFormatting:
    def test_report_contains_headline_metrics(self):
        records = [record("nsf_bio"), record("nsf_geo")]
        rankings = [["nsf_bio"], ["nsf_bio"]]
        text = format_benchmark_report(evaluate_predictions(records, rankings))
        assert "Top-1 accuracy (strict)" in text
        assert "Macro F1" in text
        assert "nsf_bio" in text

    def test_report_states_the_distribution_shift(self):
        """The genre caveat must travel with the numbers."""
        text = format_benchmark_report(evaluate_predictions([record("nsf_bio")], [["nsf_bio"]]))
        assert "not FOAs" in text

    def test_report_lists_confusions(self):
        records = [record("nsf_bio")]
        rankings = [["nsf_geo"]]
        text = format_benchmark_report(evaluate_predictions(records, rankings))
        assert "confusions" in text.lower()

    def test_report_handles_an_empty_corpus(self):
        assert "Awards scored" in format_benchmark_report(evaluate_predictions([], []))

    def test_labels_are_resolved_through_the_store_when_given(self):
        class FakeConcept:
            label = "Biological Sciences"

        class FakeStore:
            def get_concept_by_id(self, cid):
                return FakeConcept() if cid == "nsf_bio" else None

        text = format_benchmark_report(
            evaluate_predictions([record("nsf_bio")], [["nsf_bio"]]), FakeStore()
        )
        assert "Biological Sciences" in text
