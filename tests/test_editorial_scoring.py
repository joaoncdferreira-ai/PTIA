import unittest

from ptia_engine.editorial_scoring import score_signal, select_portfolio
from ptia_engine.models import RadarSignal


def _signal(
    signal_id: str,
    *,
    title: str,
    source: str,
    engagement: int = 60,
) -> RadarSignal:
    return RadarSignal(
        signal_id=signal_id,
        source_type="news",
        source_name=source,
        title=title,
        url=f"https://example.com/{signal_id}",
        published_at="2026-06-14T08:00:00+00:00",
        engagement_score=engagement,
        summary=(
            "A fonte publicou dados concretos sobre a adoção da tecnologia e descreveu "
            "os efeitos observados por equipas e empresas."
        ),
        why_it_matters=(
            "A mudança altera decisões de investimento, produto e operação no curto prazo."
        ),
        status="verified",
    )


class EditorialScoringTests(unittest.TestCase):
    def test_explicit_portugal_relevance_improves_score(self):
        local = _signal(
            "local",
            title="Empresa portuguesa lança novo modelo de IA em Lisboa",
            source="Publico",
        )
        global_signal = _signal(
            "global",
            title="Empresa lança novo modelo de IA",
            source="Reuters",
        )

        self.assertTrue(score_signal(local).local_relevance)
        self.assertGreater(score_signal(local).total, score_signal(global_signal).total)

    def test_portfolio_includes_local_story_and_limits_source_concentration(self):
        signals = [
            _signal("pt", title="Portugal cria centro de investigação em IA", source="Lusa"),
            _signal("a", title="Novo modelo melhora coding benchmark", source="Reuters", engagement=90),
            _signal("b", title="API de agentes chega a empresas", source="Reuters", engagement=88),
            _signal("c", title="Startup recebe investimento para IA", source="Reuters", engagement=86),
            _signal("d", title="Universidade publica estudo de segurança", source="Nature", engagement=70),
        ]

        selected, _alternatives = select_portfolio(signals, limit=4)

        self.assertIn("pt", {signal.signal_id for signal, _score in selected})
        self.assertLessEqual(
            sum(signal.source_name == "Reuters" for signal, _score in selected),
            2,
        )

    def test_portfolio_deduplicates_same_source_url(self):
        first = _signal("first", title="Novo modelo melhora coding benchmark", source="Reuters")
        duplicate = _signal(
            "duplicate",
            title="Benchmark mostra melhoria de novo modelo",
            source="Reuters",
        )
        duplicate.url = first.url

        selected, _alternatives = select_portfolio([first, duplicate], limit=2)

        self.assertEqual(len(selected), 1)


if __name__ == "__main__":
    unittest.main()
