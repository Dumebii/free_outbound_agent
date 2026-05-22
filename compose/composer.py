import os
import json


def _build_prompt(lead: dict, config: dict) -> str:
    company = config["company"]
    compose = config["compose"]
    links   = config.get("links", [])

    banned = ", ".join(f'"{w}"' for w in compose.get("banned_words", []))
    link_list = "\n".join(f'- {l["label"]}: {l["url"]}' for l in links)

    return f"""You are writing a cold outreach email on behalf of {company["name"]}.

About {company["name"]}:
{company["description"].strip()}

About the recipient:
- Name: {lead.get("Name", "")}
- Bio: {lead.get("Bio", "(no bio)")}
- Company/Org: {lead.get("Company", "(independent)")}
- Followers: {lead.get("Followers", 0)}
- Profile: {lead.get("Profile", "")}

Write a short, personalized cold email that:
1. Opens with one specific, genuine observation about this person (based on their bio or work — not generic flattery)
2. Connects their work to a real problem {company["name"]} solves
3. Ends with ONE low-friction CTA using one of the links below
4. Reads like a smart founder wrote it personally — not a marketing team

Tone: {compose.get("tone", "Direct and conversational.").strip()}

Hard constraints:
- Maximum 120 words in the body
- Do NOT use these words or phrases: {banned}
- Do NOT open with "I hope this email finds you well" or any variant
- Do NOT use bullet points or numbered lists in the email body
- Do NOT mention the recipient's follower count
- Use plain paragraphs separated by blank lines

Available links (pick 1-2 that feel natural — do NOT use all of them):
{link_list}

Respond with valid JSON only — no markdown, no explanation:
{{
  "subject": "subject line (max 8 words, no clickbait, no ALL CAPS)",
  "body": "email body as HTML — use <br><br> between paragraphs, <a href=\\"url\\">text</a> for links. Start with Hey [FirstName],<br><br>"
}}"""


def _call_claude(prompt: str, model: str) -> tuple[str, str]:
    import anthropic
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    message = client.messages.create(
        model=model,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = message.content[0].text.strip()
    data = json.loads(raw)
    return data["subject"], data["body"]


def _call_openai(prompt: str, model: str) -> tuple[str, str]:
    from openai import OpenAI
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
    )
    raw = response.choices[0].message.content.strip()
    data = json.loads(raw)
    return data["subject"], data["body"]


def generate_email(lead: dict, config: dict) -> tuple[str, str]:
    """
    Generate a personalized email for a lead using the configured LLM.

    Returns:
        (subject, html_body)
    """
    compose   = config["compose"]
    provider  = compose.get("provider", "claude").lower()
    model     = compose.get("model", "claude-opus-4-5")
    prompt    = _build_prompt(lead, config)

    if provider == "claude":
        return _call_claude(prompt, model)
    elif provider == "openai":
        return _call_openai(prompt, model)
    else:
        raise ValueError(f"Unknown compose provider: {provider!r}. Use 'claude' or 'openai'.")
