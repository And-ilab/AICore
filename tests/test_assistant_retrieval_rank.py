import os
import sys
import unittest
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sufler.settings")

import django  # noqa: E402

django.setup()

from django.test import TestCase  # noqa: E402

from ingest.models import AssistantProductionChunk, CCProductionChunk  # noqa: E402
from ingest.pipeline import deterministic_embedding  # noqa: E402
from qu.assistant_retrieval import (  # noqa: E402
    contact_fact_signal,
    permalink_signal,
    preview_assistant_query,
)
from qu.service import (  # noqa: E402
    expand_user_query,
    topical_relevance_score,
    _lookup_hit_count,
)


VISA_Q = (
    "За чей счёт оплачивают въездную визу и страховку "
    "при командировке за границу?"
)
HIRE_Q = (
    "Какие документы входят в электронный пакет "
    "при согласовании приёма на работу?"
)
TRAVEL_TEXT = (
    "При направлении в служебную командировку за границу въездная виза "
    "и медицинская страховка оплачиваются за счёт банка. Работник не "
    "несёт этих расходов самостоятельно."
)
HR_TEXT = (
    "Согласование назначения кандидата осуществляется в электронном виде. "
    "Непосредственный руководитель формирует пакет документов кандидата "
    "и направляет их для согласования приёма на работу."
)
BENEFITS_DUMP = (
    "Перечень документов для назначения государственного пособия семьям "
    "с детьми: заявление, паспорт, свидетельство о рождении, справка "
    "с места работы, сведения об оплате труда. "
) * 40


class TopicalRelevanceScoreTest(unittest.TestCase):
    def test_travel_article_beats_benefits_dump(self):
        travel = topical_relevance_score(
            VISA_Q,
            "Положение 28.9 командировки.doc",
            TRAVEL_TEXT,
            extra="Положение о командировках",
        )
        benefits = topical_relevance_score(
            VISA_Q,
            "10.07.2026_Perechen-AP-rabotniki_.doc",
            BENEFITS_DUMP,
            extra="Нормативные документы и бланки",
        )
        self.assertGreater(travel, benefits)
        self.assertGreaterEqual(travel, 0.45)

    def test_hr_article_beats_benefits_dump(self):
        hr = topical_relevance_score(
            HIRE_Q,
            "Регламент учета персонала.doc",
            HR_TEXT,
            extra="Регламент учета персонала",
        )
        benefits = topical_relevance_score(
            HIRE_Q,
            "10.07.2026_Perechen-AP-rabotniki_.doc",
            BENEFITS_DUMP,
            extra="Нормативные документы и бланки",
        )
        self.assertGreater(hr, benefits)


class AssistantRetrievalRankTest(TestCase):
    def _chunk(self, **kwargs):
        content = kwargs["content"]
        AssistantProductionChunk.objects.create(
            version_id=1,
            permalink="https://kb.local/doc",
            locale="ru",
            visibility_scope=["assistant"],
            checksum=kwargs.get("checksum", f"sha256:{kwargs['article_id']}"),
            embedding_model="deterministic-dev",
            embedding=deterministic_embedding(content),
            **{key: value for key, value in kwargs.items() if key != "checksum"},
        )

    def test_all_kbs_return_travel_not_benefits(self):
        self._chunk(
            kb_slug="assistant_polozhenie_komandirovki",
            article_id=9_100_001,
            chunk_index=0,
            title="Положение 28.9 командировки.doc",
            content=TRAVEL_TEXT,
        )
        self._chunk(
            kb_slug="assistant_7_dokov",
            article_id=9_100_002,
            chunk_index=0,
            title="10.07.2026_Perechen-AP-rabotniki_.doc",
            content=BENEFITS_DUMP,
        )
        CCProductionChunk.objects.create(
            article_id=2000000008,
            version_id=1,
            chunk_index=0,
            title="avtokredit-belarusbank.txt",
            content=(
                "Автокредит: ставка по кредиту 12 % годовых. "
                "Документы для оформления кредита в банке."
            ),
            permalink="https://kb.local/avto",
            locale="ru",
            visibility_scope=["kc_operator"],
            checksum="sha256:avto",
            embedding_model="deterministic-dev",
            embedding=deterministic_embedding("автокредит ставка документы"),
        )
        result = preview_assistant_query(VISA_Q, search_all=True, limit=5)
        titles = [doc["title"] for doc in result["documents"]]
        self.assertIn("Положение 28.9 командировки.doc", titles)
        self.assertEqual(titles[0], "Положение 28.9 командировки.doc")

    def test_all_kbs_return_hr_pack_not_benefits(self):
        self._chunk(
            kb_slug="assistant_reglament_ucheta_personala",
            article_id=9_100_003,
            chunk_index=0,
            title="Регламент учета персонала.doc",
            content=HR_TEXT,
        )
        self._chunk(
            kb_slug="assistant_7_dokov",
            article_id=9_100_004,
            chunk_index=0,
            title="10.07.2026_Perechen-AP-rabotniki_.doc",
            content=BENEFITS_DUMP,
        )
        result = preview_assistant_query(HIRE_Q, search_all=True, limit=5)
        titles = [doc["title"] for doc in result["documents"]]
        self.assertEqual(titles[0], "Регламент учета персонала.doc")

    def test_picks_aid_chapter_not_cover_page(self):
        self._chunk(
            kb_slug="assistant_mat_pomosh",
            article_id=9_100_113,
            chunk_index=0,
            title="Положение 113.1 мат помощь.doc",
            content=(
                "ОАО АСБ Беларусбанк. УТВЕРЖДЕНО протокол 08.08.2023 № 113.1 "
                "ПОЛОЖЕНИЕ о единовременном материальном поощрении. "
                "Перечень внесенных дополнений и изменений: Дополнение 1."
            ),
        )
        self._chunk(
            kb_slug="assistant_mat_pomosh",
            article_id=9_100_113,
            chunk_index=4,
            title="Положение 113.1 мат помощь.doc",
            content=(
                "ГЛАВА 3 МАТЕРИАЛЬНАЯ ПОМОЩЬ. Оказание материальной помощи "
                "на оздоровление. Работникам при предоставлении трудового "
                "отпуска выплачивается материальная помощь на оздоровление "
                "в размере 2 окладов. При рождении ребенка выплачивается "
                "помощь в размере 5 БПМ."
            ),
            checksum="sha256:113-ch3",
        )
        result = preview_assistant_query(
            "Кому и в каких случаях банк даёт материальную помощь "
            "по положению 113.1?",
            limit=5,
        )
        joined = " ".join(doc.get("content") or "" for doc in result["documents"])
        self.assertIn("2 окладов", joined)
        self.assertIn("рождении", joined)

    def test_matpomosh_alias_finds_material_aid(self):
        self.assertIn("материальная помощь", expand_user_query("подать на матпомощь"))
        self._chunk(
            kb_slug="assistant_mat_pomosh_docs",
            article_id=9_100_114,
            chunk_index=0,
            title="Положение 113.1 мат помощь.doc",
            content=(
                "Порядок оформления. Для получения материальной помощи "
                "работник подаёт заявление и копию свидетельства о рождении."
            ),
        )
        result = preview_assistant_query(
            "Какие документы нужны, чтобы подать на матпомощь?",
            limit=5,
        )
        joined = " ".join(doc.get("content") or "" for doc in result["documents"])
        self.assertIn("заявление", joined)

    def test_website_hotline_beats_contact_center_bonus(self):
        query = "Контакты: телефон горячей линии, адрес головного офиса"
        self.assertIn("147", expand_user_query(query))
        self._chunk(
            kb_slug="assistant_bank_sayt",
            article_id=9_100_200,
            chunk_index=4,
            title="Вход в интернет-банкинг",
            content=(
                "Обратная связь +375 17 218 84 31 +375 25 767 88 77 Life 147 "
                "Единый справочный номер доступен по Беларуси. "
                "Режим работы Контакт-центра: пн—пт 8:30. "
                "Юридический адрес: 220002, г. Минск, пр. Дзержинского, 18."
            ),
            checksum="sha256:site-footer",
        )
        self._chunk(
            kb_slug="assistant_polozhenie_55_3_premirovanie",
            article_id=9_100_201,
            chunk_index=0,
            title="Положение 55.3 премирование.doc",
            content=(
                "Положение 55.3 о премировании. Порядок расчета премии "
                "работников контакт-центра, осуществляющих дистанционное "
                "взаимодействие с клиентами. Контакты подразделения HR."
            ),
            checksum="sha256:55-3",
        )
        self.assertGreater(
            contact_fact_signal(
                query,
                "Вход в интернет-банкинг",
                "+375 17 218 84 31 147 Единый справочный номер",
            ),
            0.3,
        )
        result = preview_assistant_query(query, search_all=True, limit=5)
        titles = [doc["title"] for doc in result["documents"]]
        self.assertEqual(titles[0], "Вход в интернет-банкинг")
        self.assertGreaterEqual(result["documents"][0]["relevance_percent"], 60)
        self.assertIn("147", result["documents"][0].get("content") or "")

    def test_tenure_question_prefers_the_pay_regulation(self):
        self._chunk(
            kb_slug="assistant_mat_pomosh",
            article_id=9_100_301,
            chunk_index=0,
            title="Положение о материальной помощи",
            content=(
                "Материальная помощь работникам банка выплачивается по заявлению "
                "в связи со смертью работника. Решение принимается по заявлению "
                "установленной формы."
            ),
            checksum="sha256:mat-death",
        )
        self._chunk(
            kb_slug="assistant_oplata",
            article_id=9_100_302,
            chunk_index=3,
            title="Положение об оплате труда",
            content=(
                "Периоды трудовой деятельности, засчитываемые в стаж работы в банках, "
                "суммируются независимо от сроков перерыва в работе. Расчет стажа "
                "работы в банках производится программным путем."
            ),
            checksum="sha256:pay-tenure",
        )
        result = preview_assistant_query(
            "как считается стаж работы в банках",
            search_all=True,
            limit=5,
        )
        self.assertEqual(result["documents"][0]["title"], "Положение об оплате труда")
        self.assertIn("суммируются", result["documents"][0]["content"])

    def test_night_pay_prefers_the_percent_clause(self):
        self._chunk(
            kb_slug="assistant_vremya",
            article_id=9_100_303,
            chunk_index=0,
            title="Положение о рабочем времени и отпусках",
            content=(
                "В табеле работа в ночное время указывается через дробь: "
                "количество ночных часов, например 10:00/Нч02:00."
            ),
            checksum="sha256:time-night",
        )
        self._chunk(
            kb_slug="assistant_oplata",
            article_id=9_100_304,
            chunk_index=2,
            title="Положение об оплате труда",
            content=(
                "За каждый час работы в ночное время с 22 часов до 6 часов "
                "устанавливается доплата в размере 40 % часовой ставки. "
                "Ночной считается смена, в которой более 50 % рабочего времени "
                "приходится на ночное время."
            ),
            checksum="sha256:pay-night",
        )
        result = preview_assistant_query(
            "какая доплата за ночные смены",
            search_all=True,
            limit=5,
        )
        self.assertEqual(result["documents"][0]["title"], "Положение об оплате труда")
        self.assertIn("40", result["documents"][0]["content"])

    def test_loss_clause_is_kept_not_the_death_chapter(self):
        self._chunk(
            kb_slug="assistant_mat_pomosh",
            article_id=9_100_305,
            chunk_index=0,
            title="Положение о материальной помощи",
            content=(
                "Материальная помощь, в частности, оказывается в связи со смертью "
                "работника, и решение принимается по заявлению установленной формы. "
            ) * 8,
            checksum="sha256:mat-cover",
        )
        self._chunk(
            kb_slug="assistant_mat_pomosh",
            article_id=9_100_305,
            chunk_index=6,
            title="Положение о материальной помощи",
            content=(
                "Если банк с начала года работает в убытке, материальная помощь "
                "не выплачивается."
            ),
            checksum="sha256:mat-loss",
        )
        result = preview_assistant_query(
            "платят ли материальную помощь если банк с начала года в убытке",
            limit=5,
        )
        joined = " ".join(doc.get("content") or "" for doc in result["documents"])
        self.assertIn("убытке", joined)


class LookupHitTest(unittest.TestCase):
    def test_tenure_word_does_not_match_internship(self):
        self.assertEqual(_lookup_hit_count("как считается стаж", "направление на стажировку"), 0)
        self.assertGreater(
            _lookup_hit_count(
                "как считается стаж работы в банках",
                "Расчет стажа работы в банках производится программным путем.",
            ),
            0,
        )


class WebsitePermalinkSignalTest(unittest.TestCase):
    def test_contacts_path_beats_homepage(self):
        query = "Контакты: телефон горячей линии, адрес головного офиса"
        home = permalink_signal(query, "https://belarusbank.by/ru")
        page = permalink_signal(query, "https://belarusbank.by/ru/kontakty")
        self.assertGreater(page, home)
        self.assertGreater(page, 0)
        self.assertLess(home, 0)
