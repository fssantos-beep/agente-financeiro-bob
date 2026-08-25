import unittest
from decimal import Decimal

from pydantic import ValidationError

from src.chatbot import build_prompt, load_products
from src.database import profile_for_ai
from src.main import ProfilePayload


def profile(**overrides):
    data = {
        "renda_mensal": 5000,
        "gastos_moradia": 1500,
        "gastos_alimentacao": 800,
        "gastos_transporte": 300,
        "gastos_contas": 250,
        "gastos_educacao": 0,
        "gastos_saude": 100,
        "gastos_lazer": 200,
        "outros_gastos": 150,
        "possui_dividas": False,
        "valor_dividas": 0,
        "reserva_emergencia": 2000,
        "possui_investimentos": False,
        "valor_investido": 0,
        "tipos_investimentos": None,
        "objetivo_financeiro": "comprar_veiculo",
        "tolerancia_risco": "moderado",
    }
    data.update(overrides)
    return data


class ProfileContextTests(unittest.TestCase):
    def test_existing_objective_remains_available_to_bob(self):
        context = build_prompt(
            profile_for_ai({"nome": "Ana"}, profile()),
            load_products(),
        )

        self.assertIn("Objetivo financeiro: Comprar um veículo", context)
        self.assertNotIn("Detalhamento do objetivo:", context)

    def test_other_objective_is_validated_and_sent_to_bob(self):
        payload = ProfilePayload(**profile(
            objetivo_financeiro="outro",
            objetivo_outro="  Fazer intercâmbio em dois anos.  ",
        ))
        self.assertEqual(payload.objetivo_outro, "Fazer intercâmbio em dois anos.")

        context = build_prompt(
            profile_for_ai(
                {"nome": "Ana"},
                profile(objetivo_financeiro="outro", objetivo_outro=payload.objetivo_outro),
            ),
            load_products(),
        )

        self.assertIn("Objetivo financeiro: Outro", context)
        self.assertIn("Detalhamento do objetivo: Fazer intercâmbio em dois anos.", context)

    def test_other_objective_requires_description(self):
        with self.assertRaises(ValidationError):
            ProfilePayload(**profile(objetivo_financeiro="outro", objetivo_outro="  "))

    def test_investments_are_sent_to_bob(self):
        financial_profile = profile(
            possui_investimentos=True,
            tipos_investimentos="CDB, Tesouro Selic",
            valor_investido=Decimal("5000.00"),
        )
        context = build_prompt(profile_for_ai({"nome": "Ana"}, financial_profile), load_products())

        self.assertIn("Tipo(s): CDB, Tesouro Selic", context)
        self.assertIn("Valor investido: R$ 5.000,00", context)

    def test_no_investments_does_not_send_investment_data(self):
        financial_profile = profile(
            possui_investimentos=False,
            tipos_investimentos="CDB",
            valor_investido=Decimal("5000.00"),
        )
        context = build_prompt(profile_for_ai({"nome": "Ana"}, financial_profile), load_products())

        self.assertIn("Não possui investimentos informados", context)
        self.assertNotIn("Tipo(s): CDB", context)

    def test_debt_value_remains_available_in_context(self):
        context = build_prompt(
            profile_for_ai(
                {"nome": "Ana"},
                profile(possui_dividas=True, valor_dividas=Decimal("1200.00")),
            ),
            load_products(),
        )

        self.assertIn("Dívidas: R$ 1.200,00", context)


if __name__ == "__main__":
    unittest.main()
