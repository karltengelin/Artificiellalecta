"""Tester för AI-lagrets konfiguration och nyckelval (02_system/ai_abstraktion.md §6–7)."""

import pytest

from ai.config import AIConfig, ProviderConfig, load_config
from ai.errors import ConfigError, MissingKeyError
from ai.keys import candidate_key_vars, resolve_api_key
from ai.types import CallContext, Usage


def _minimal(**overrides) -> dict:
    data = {
        "providers": {"alpha": {"type": "fake", "api_key_env": "ALPHA_KEY"}},
        "models": {"alpha:m1": {"price": {"input": 1, "output": 2}}},
        "roles": {"standard": {"model": "alpha:m1"}},
    }
    data.update(overrides)
    return data


class TestStandardkonfigurationen:
    def test_laddas_och_alla_roller_loses_upp(self):
        config = load_config(environ={})
        for role in config.roles:
            resolution = config.resolve(role, environ={})
            assert resolution.chain, role

    def test_varje_roll_har_reserv_hos_annan_leverantor(self):
        # Designprincip: en driftstörning hos en leverantör ska inte stoppa en roll
        config = load_config(environ={})
        for name, role in config.roles.items():
            providers = {config.models[ref].provider for ref in (role.model, *role.fallbacks)}
            assert len(providers) >= 2, name

    def test_alla_modeller_har_pris(self):
        config = load_config(environ={})
        for spec in config.models.values():
            assert spec.price.input > 0 and spec.price.output > 0, spec.ref

    def test_standardroll_anvands_utan_angiven_modell(self):
        config = load_config(environ={})
        assert config.resolve(None, environ={}).requested == config.defaults.role


class TestUpplosning:
    def test_explicit_modellreferens_ger_kedja_utan_reserv(self):
        config = AIConfig.from_dict(_minimal())
        resolution = config.resolve("alpha:m1", environ={})
        assert [s.ref for s in resolution.chain] == ["alpha:m1"]
        assert resolution.effort is None

    def test_okand_roll_ger_configerror(self):
        config = AIConfig.from_dict(_minimal())
        with pytest.raises(ConfigError, match="Okänd modellroll"):
            config.resolve("superdeep", environ={})

    def test_miljovariabel_byter_primarmodell(self):
        data = _minimal(
            models={
                "alpha:m1": {"price": {"input": 1, "output": 2}},
                "alpha:m2": {"price": {"input": 1, "output": 2}},
            },
            roles={"standard": {"model": "alpha:m1", "fallbacks": ["alpha:m2"]}},
        )
        config = AIConfig.from_dict(data)
        resolution = config.resolve("standard", environ={"AI_ROLE_STANDARD": "alpha:m2"})
        # Överstyrd modell först, och den dupliceras inte som reserv
        assert [s.ref for s in resolution.chain] == ["alpha:m2"]

    def test_overstyrning_till_okand_modell_ger_configerror(self):
        config = AIConfig.from_dict(_minimal())
        with pytest.raises(ConfigError, match="finns inte"):
            config.resolve("standard", environ={"AI_ROLE_STANDARD": "alpha:saknas"})


class TestValidering:
    def test_felaktig_modellreferens(self):
        with pytest.raises(ConfigError, match="leverantör:modell"):
            AIConfig.from_dict(_minimal(models={"utanprefix": {"price": {"input": 1, "output": 1}}}))

    def test_modell_med_okand_leverantor(self):
        with pytest.raises(ConfigError, match="okänd leverantör"):
            AIConfig.from_dict(_minimal(models={"gamma:m1": {"price": {"input": 1, "output": 1}}}))

    def test_roll_med_okand_modell(self):
        with pytest.raises(ConfigError, match="okänd modell"):
            AIConfig.from_dict(_minimal(roles={"standard": {"model": "alpha:saknas"}}))

    def test_ogiltigt_falt_ger_configerror(self):
        with pytest.raises(ConfigError, match="Ogiltig"):
            AIConfig.from_dict(_minimal(roles={"standard": {"model": "alpha:m1", "effort": "max"}}))

    def test_alternativ_fil_via_miljovariabel(self, tmp_path):
        path = tmp_path / "alt.yaml"
        path.write_text(
            "providers: {alpha: {type: fake}}\n"
            "models: {'alpha:m1': {price: {input: 1, output: 1}}}\n"
            "roles: {standard: {model: 'alpha:m1'}}\n",
            encoding="utf-8",
        )
        config = load_config(environ={"AI_CONFIG_FILE": str(path)})
        assert list(config.models) == ["alpha:m1"]


class TestPris:
    def test_kostnad_med_cache(self):
        config = AIConfig.from_dict(
            _minimal(
                models={
                    "alpha:m1": {
                        "price": {"input": 5, "output": 25, "cached_input": 0.5, "cache_write": 6.25}
                    }
                }
            )
        )
        price = config.models["alpha:m1"].price
        usage = Usage(
            input_tokens=1_000_000, cached_input_tokens=400_000, cache_write_tokens=100_000,
            output_tokens=200_000,
        )
        # 500k okachade × 5 + 400k × 0,5 + 100k × 6,25 + 200k × 25 (per miljon)
        assert price.cost_usd(usage) == pytest.approx(2.5 + 0.2 + 0.625 + 5.0)

    def test_cachepris_faller_tillbaka_pa_inputpris(self):
        config = AIConfig.from_dict(_minimal())
        usage = Usage(input_tokens=1_000_000, cached_input_tokens=1_000_000)
        assert config.models["alpha:m1"].price.cost_usd(usage) == pytest.approx(1.0)


class TestNyckelval:
    provider = ProviderConfig(name="anthropic", type="anthropic", api_key_env="ANTHROPIC_API_KEY")

    def test_team_nyckel_har_foretrade(self):
        env = {"ANTHROPIC_API_KEY": "gemensam", "ANTHROPIC_API_KEY_KAPITAL": "team"}
        assert resolve_api_key(self.provider, "kapital", env) == ("team", "ANTHROPIC_API_KEY_KAPITAL")

    def test_gemensam_nyckel_som_reserv(self):
        env = {"ANTHROPIC_API_KEY": "gemensam"}
        assert resolve_api_key(self.provider, "kapital", env) == ("gemensam", "ANTHROPIC_API_KEY")

    def test_tom_varde_raknas_som_saknad(self):
        env = {"ANTHROPIC_API_KEY_KAPITAL": "  ", "ANTHROPIC_API_KEY": "gemensam"}
        assert resolve_api_key(self.provider, "kapital", env)[1] == "ANTHROPIC_API_KEY"

    def test_saknad_nyckel_namnger_variablerna(self):
        with pytest.raises(MissingKeyError) as info:
            resolve_api_key(self.provider, "kapital", {})
        assert info.value.variables == ["ANTHROPIC_API_KEY_KAPITAL", "ANTHROPIC_API_KEY"]

    def test_leverantor_utan_nyckel(self):
        fake = ProviderConfig(name="fake", type="fake")
        assert candidate_key_vars(fake, "kapital") == []
        assert resolve_api_key(fake, "kapital", {}) == (None, None)


class TestKontext:
    def test_team_id_maste_vara_ascii_gemener(self):
        with pytest.raises(ValueError):
            CallContext(team="Försäkring")

    def test_merged_behaller_befintliga_falt(self):
        ctx = CallContext(team="kapital", agent="portfolio_manager").merged(run_id="r1", agent=None)
        assert (ctx.team, ctx.agent, ctx.run_id) == ("kapital", "portfolio_manager", "r1")
