"""Gateways utanför försäkringstjänstelagret (Fas 3c 3c-G, B-035, harness.md §4.3 och §5.2).

    regelverk = RegulatoryGateway()            # läsning av godkända regel- och källdokument via handtag
    utkast = DraftGateway()                    # Markdown-utkast i körningens egen arbetsyta

En gateway har ett eget litet kontrakt: indata- och utdatamodeller, sidoeffekt, dataklass och
tillåtna resurser (`GATEWAY_TOOLS`). Den ger aldrig modellen en sökväg, ett filhandtag eller
ett generellt filverktyg, och den nekar själv otillåten användning – även när den anropas
direkt utan harness. Monteringen som verktyg för teamen sker i körpolicyn (3c-T).
"""

from agents.gateways.common import GatewayError
from agents.gateways.drafts import (
    DraftGateway,
    DraftList,
    DraftReceipt,
    WriteDraftInput,
)
from agents.gateways.regulatory import (
    DocumentExcerpt,
    DocumentList,
    ListRegulatoryDocumentsInput,
    ReadRegulatoryDocumentInput,
    RegulatoryGateway,
)
from agents.gateways.tools import GATEWAY_TOOLS, GatewayTool

__all__ = [
    "GATEWAY_TOOLS",
    "DocumentExcerpt",
    "DocumentList",
    "DraftGateway",
    "DraftList",
    "DraftReceipt",
    "GatewayError",
    "GatewayTool",
    "ListRegulatoryDocumentsInput",
    "ReadRegulatoryDocumentInput",
    "RegulatoryGateway",
    "WriteDraftInput",
]
