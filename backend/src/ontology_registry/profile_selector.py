"""Select ontology profiles relevant to a document before graph extraction."""

from pydantic import BaseModel, Field

from .adapter import OntologyExtractionAdapter, ALWAYS_LOADED, DEFAULT_PROFILE_NOTES


class ProfileSelection(BaseModel):
    profiles: list[str] = Field(default_factory=list)
    reasoning: str = ""
    confidence: float = 0.0


async def select_profiles(llm, document_text: str) -> ProfileSelection:
    catalog = OntologyExtractionAdapter.profile_catalog()
    selectable = {
        name: description for name, description in catalog.items()
        if name not in ALWAYS_LOADED
    }
    options = "\n".join(f"- {name}: {description}" for name, description in selectable.items())
    default_notes = "\n".join(
        f"- {profile_id}: {note}" for profile_id, note in DEFAULT_PROFILE_NOTES.items()
    )
    prompt = f"""Choose the optional ontology profiles relevant to this document.
Return only profile IDs from the catalog. Select multiple profiles when needed.
Do not select a profile merely because a word appears once. Return an empty list
when no specialized profile is appropriate; business-common and iof-core are automatic.

    Always-loaded profile context:
{default_notes}

Available optional profiles:
{options}

Document:
{document_text}
"""
    structured = llm.with_structured_output(ProfileSelection)
    result = await structured.ainvoke(prompt)
    valid = set(selectable)
    result.profiles = list(dict.fromkeys(profile_id for profile_id in result.profiles if profile_id in valid))
    if not result.profiles:
        result.profiles = []
    result.confidence = max(0.0, min(1.0, float(result.confidence)))
    return result
