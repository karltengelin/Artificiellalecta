"""Kanoniska typer för AI-lagret.

Det här är det enda formatet agent- och skillkod ser. Adaptrarna i
`ai.providers` översätter till och från respektive leverantörs API.
Alla typer är Pydantic-modeller så att hela konversationer kan sparas som
JSON i körjournaler. Se 02_system/ai_abstraktion.md §5.3.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ai.schema import strict_json_schema

#: Resonemangsnivå. Översätts till `output_config.effort` (Anthropic) och
#: `reasoning.effort` (OpenAI). Ignoreras för modeller som saknar stödet.
Effort = Literal["low", "medium", "high"]

#: Varför modellen slutade generera, oberoende av leverantör.
StopReason = Literal["end_turn", "tool_use", "max_tokens", "refusal", "other"]

#: Verktygsnamn måste fungera hos alla leverantörer: ASCII, max 64 tecken.
TOOL_NAME_PATTERN = r"^[a-zA-Z0-9_-]{1,64}$"

#: Team-id ingår i miljövariabelnamn för team-nycklar (B-026).
TEAM_ID_PATTERN = r"^[a-z][a-z0-9_]*$"


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True)


class ToolSpec(_Frozen):
    """Ett verktyg (en skill) som modellen får anropa."""

    name: str = Field(pattern=TOOL_NAME_PATTERN)
    description: str
    parameters: dict[str, Any]  # JSON Schema för verktygets indata (type: object)
    strict: bool = False  # True kräver strikt schema – se ToolSpec.from_model

    @classmethod
    def from_model(
        cls, name: str, description: str, model: type[BaseModel]
    ) -> ToolSpec:
        """Bygger ett strikt verktyg ur en Pydantic-modell för indata."""
        return cls(
            name=name,
            description=description,
            parameters=strict_json_schema(model),
            strict=True,
        )


class ToolCall(_Frozen):
    """Modellens begäran att köra ett verktyg."""

    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolResult(_Frozen):
    """Resultatet av ett verktygsanrop, skickas tillbaka till modellen."""

    call_id: str
    content: str
    is_error: bool = False


class ProviderState(_Frozen):
    """Opak leverantörsdata för att återspela ett assistentsvar troget.

    Innehåller de råa svarsblocken (t.ex. Anthropics tänkande-block eller
    OpenAIs krypterade resonemangs-items). Adaptern återanvänder dem bara när
    meddelandet skickas till samma leverantör; annars återskapas meddelandet
    ur de kanoniska fälten. Anropande kod ska aldrig läsa eller ändra detta.
    """

    provider: str  # adaptertyp, t.ex. "anthropic"
    model: str  # modell-ID som efterfrågades när svaret skapades
    payload: list[dict[str, Any]]


class Message(_Frozen):
    """Ett meddelande i en konversation."""

    role: Literal["user", "assistant"]
    text: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    tool_results: tuple[ToolResult, ...] = ()
    provider_state: ProviderState | None = None

    @model_validator(mode="after")
    def _check_role_fields(self) -> Message:
        if self.role == "user" and self.tool_calls:
            raise ValueError("Ett user-meddelande kan inte innehålla verktygsanrop")
        if self.role == "assistant" and self.tool_results:
            raise ValueError("Ett assistant-meddelande kan inte innehålla verktygsresultat")
        if self.role == "user" and not self.text and not self.tool_results:
            raise ValueError("Ett user-meddelande måste ha text eller verktygsresultat")
        return self

    @classmethod
    def user(cls, text: str) -> Message:
        return cls(role="user", text=text)

    @classmethod
    def assistant(cls, text: str, tool_calls: tuple[ToolCall, ...] = ()) -> Message:
        return cls(role="assistant", text=text, tool_calls=tuple(tool_calls))

    @classmethod
    def from_tool_results(cls, results: list[ToolResult] | tuple[ToolResult, ...]) -> Message:
        """Alla resultat från ett modellsvar skickas tillbaka i ett och samma meddelande."""
        return cls(role="user", tool_results=tuple(results))


class Usage(_Frozen):
    """Tokenförbrukning för ett anrop, normaliserad mellan leverantörer."""

    input_tokens: int = 0  # alla inputtokens, inklusive cachade
    output_tokens: int = 0  # inklusive resonemangstokens
    cached_input_tokens: int = 0  # lästa ur prompt-cache
    cache_write_tokens: int = 0  # skrivna till prompt-cache
    reasoning_tokens: int = 0  # del av output_tokens som gick till resonemang

    def __add__(self, other: Usage) -> Usage:
        return Usage(
            **{
                name: getattr(self, name) + getattr(other, name)
                for name in Usage.model_fields
            }
        )


class CallContext(_Frozen):
    """Var ett anrop hör hemma – styr nyckelval och spårbarhet."""

    team: str | None = Field(default=None, pattern=TEAM_ID_PATTERN)
    agent: str | None = None
    run_id: str | None = None
    step: str | None = None

    def merged(self, **updates: str | None) -> CallContext:
        data = self.model_dump()
        data.update({k: v for k, v in updates.items() if v is not None})
        return CallContext(**data)


class ModelResponse(BaseModel):
    """Svar från AI-lagret, oberoende av vilken leverantör som svarade."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    text: str
    tool_calls: tuple[ToolCall, ...] = ()
    stop_reason: StopReason
    usage: Usage
    cost_usd: float | None  # uppskattning enligt prislistan i ai_config.yaml
    provider: str  # leverantörsnamn i konfigurationen
    model: str  # modell-ID som faktiskt svarade (enligt leverantören)
    model_ref: str  # konfigurationens referens, t.ex. "anthropic:claude-opus-5"
    requested: str  # det anroparen bad om, t.ex. "deep"
    latency_ms: float
    request_id: str | None = None
    fallback_from: tuple[str, ...] = ()  # modeller som provades först utan att svara
    parsed: Any = None  # validerad Pydantic-instans vid strukturerat svar
    provider_state: ProviderState | None = None

    def to_message(self) -> Message:
        """Assistentmeddelande att lägga till i historiken (bär leverantörsstate)."""
        return Message(
            role="assistant",
            text=self.text,
            tool_calls=self.tool_calls,
            provider_state=self.provider_state,
        )
