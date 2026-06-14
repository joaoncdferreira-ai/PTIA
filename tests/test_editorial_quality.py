import unittest

from ptia_engine.editorial_quality import EditorialFactPack, validate_fact_pack, validate_package
from ptia_engine.models import FinalPost


class EditorialQualityTests(unittest.TestCase):
    def setUp(self):
        self.pack = EditorialFactPack(
            fact_pack_id="facts_1",
            signal_id="signal_1",
            title="Feedzai lança sistema de deteção de fraude com IA",
            source_url="https://example.com/feedzai",
            source_name="Example",
            published_at="2026-06-14T08:00:00+00:00",
            facts=[
                "A Feedzai lançou um sistema de deteção de fraude com inteligência artificial.",
                "O produto analisa transações em tempo real para reduzir falsos positivos.",
            ],
            entities=["Feedzai"],
            numbers=[],
            thesis="A redução de falsos positivos pode alterar a operação das equipas de risco.",
            consequence="Os bancos podem rever custos e tempos de resposta das análises de fraude.",
            portugal_angle="A Feedzai tem origem portuguesa e impacto no ecossistema nacional.",
        )

    def _post(self, channel: str) -> FinalPost:
        return FinalPost(
            post_id=f"post_{channel}",
            topic_id="topic_1",
            channel=channel,
            title=self.pack.title,
            body=(
                "A Feedzai lançou deteção de fraude com inteligência artificial. "
                "O sistema analisa transações e pretende reduzir falsos positivos.\n\n"
                f"Fonte: {self.pack.source_url}"
            ),
            hashtags="#IA #PTIA",
            image_prompt="Editorial photograph about fraud detection technology.",
            source_urls=[self.pack.source_url],
            image_path="master.jpg",
        )

    def test_generic_fact_pack_is_blocked(self):
        self.pack.facts = ["A fonte publicou uma nova informação sobre inteligência artificial."]

        report = validate_fact_pack(self.pack)

        self.assertFalse(report.passed)
        self.assertTrue(any("genérico" in issue for issue in report.issues))

    def test_valid_package_passes_required_gates(self):
        report = validate_package(
            self.pack,
            [self._post("linkedin"), self._post("instagram"), self._post("site")],
        )

        self.assertTrue(report.passed, report.issues)

    def test_semantically_unrelated_copy_is_blocked(self):
        posts = [self._post("linkedin"), self._post("instagram"), self._post("site")]
        posts[0].title = "Receita de pão"
        posts[0].body = f"Farinha, água e fermento.\n\nFonte: {self.pack.source_url}"

        report = validate_package(self.pack, posts)

        self.assertFalse(report.passed)
        self.assertTrue(any("semântica" in issue for issue in report.issues))

    def test_url_title_and_generic_section_page_are_blocked(self):
        self.pack.title = "https://example.com/inteligencia-artificial/"
        self.pack.source_url = "https://example.com/inteligencia-artificial/"

        report = validate_fact_pack(self.pack)

        self.assertFalse(report.passed)
        self.assertTrue(any("URL no lugar" in issue for issue in report.issues))
        self.assertTrue(any("página índice" in issue for issue in report.issues))


if __name__ == "__main__":
    unittest.main()
