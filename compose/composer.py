import os
import json


def _build_prompt(lead: dict, config: dict, step: int = 1) -> str:
    company = config["company"]
    compose = config["compose"]
    links   = config.get("links", [])

    banned    = ", ".join(f'"{w}"' for w in compose.get("banned_words", []))
    link_list = "\n".join(f'- {l["label"]}: {l["url"]}' for l in links)

    # ── Step-specific instructions ─────────────────────────────────────────
    if step == 1:
        task = f"""Write a short, personalized cold email that:
1. Opens with one specific, genuine observation about this person (based on their bio or work — not generic flattery)
2. Connects their work to a real problem {company["name"]} solves
3. Ends with ONE low-friction CTA using one of the links below
4. Reads like a smart founder wrote it personally — not a marketing team"""

        constraints = f"""- Maximum 120 words in the body
- Do NOT use these words or phrases: {banned}
- Do NOT open with "I hope this email finds you well" or any variant
- Do NOT use bullet points or numbered lists in the email body
- Do NOT mention the recipient's follower count
- Use plain paragraphs separated by blank lines"""

    else:
        # Follow-up steps — shorter, warmer, reference the previous email
        seq_steps  = config.get("sequences", {}).get("steps", [])
        step_cfg   = next((s for s in seq_steps if s.get("step") == step), {})
        hint       = step_cfg.get("subject_hint", f"follow-up")
        step_label = {2: "first follow-up", 3: "second follow-up", 4: "final note"}.get(step, f"follow-up #{step-1}")

        task = f"""Write a {step_label} email to someone who received an initial cold email from {company["name"]} but hasn't replied yet.

This is NOT a new introduction — they already know who you are. Your goal is to:
1. Be brief (3–5 sentences max)
2. Add a new angle, insight, or piece of value — don't just say "following up"
3. Keep the tone warm and human — no pressure, no guilt
4. End with one low-friction option from the links below
5. Subject hint: "{hint}" """

        constraints = f"""- Maximum 80 words in the body
- Do NOT repeat the original pitch word-for-word
- Do NOT use these words or phrases: {banned}
- Do NOT open with "Just wanted to follow up" or "Bumping this up"
- Do NOT use bullet points
- One short paragraph is ideal"""

    return f"""You are writing on behalf of {company["name"]}.

About {company["name"]}:
{company["description"].strip()}

About the recipient:
- Name: {lead.get("Name", "")}
- Bio: {lead.get("Bio", "(no bio)")}
- Company/Org: {lead.get("Company", "(independent)")}
- Profile: {lead.get("Profile", "")}

{task}

Tone: {compose.get("tone", "Direct and conversational.").strip()}

Hard constraints:
{constraints}

Available links (pick 1 that feels natural):
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
    raw  = message.content[0].text.strip()
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
    raw  = response.choices[0].message.content.strip()
    data = json.loads(raw)
    return data["subject"], data["body"]


def _build_linkedin_prompt(lead: dict, config: dict, step: int, note_max_chars: int = 300) -> str:
    company  = config["company"]
    compose  = config["compose"]
    banned   = ", ".join(f'"{w}"' for w in compose.get("banned_words", []))
    links    = config.get("links", [])
    link_list = "\n".join(f'- {l["label"]}: {l["url"]}' for l in links)

    first = lead.get("Name", "").strip().split()[0] if lead.get("Name") else "there"

    if step == 1:
        return (
            f"Write a LinkedIn connection request note for {lead.get('Name', '')}.\n\n"
            f"About {company['name']}: {company['description'].strip()}\n\n"
            f"About the recipient:\n"
            f"- Bio: {lead.get('Bio', '(no bio)')}\n"
            f"- Company: {lead.get('Company', '(independent)')}\n\n"
            f"Requirements:\n"
            f"- MUST be under {note_max_chars} characters total (hard LinkedIn limit)\n"
            f"- Start with 'Hi {first},'\n"
            f"- End with 'Would love to connect.'\n"
            f"- Personal and warm — reference something specific from their bio\n"
            f"- Do NOT use these words: {banned}\n"
            f"- No emojis, no URLs\n"
            f"- Return ONLY the note text, nothing else"
        )
    elif step == 2:
        link = links[0]["url"] if links else ""
        return (
            f"Write a LinkedIn DM for {lead.get('Name', '')} who just accepted a connection request "
            f"from {company['from_name']} at {company['name']}.\n\n"
            f"About {company['name']}: {company['description'].strip()}\n\n"
            f"About the recipient:\n"
            f"- Bio: {lead.get('Bio', '(no bio)')}\n"
            f"- Company: {lead.get('Company', '(independent)')}\n\n"
            f"Requirements:\n"
            f"- 2-3 short sentences max\n"
            f"- Start with 'Hey {first} —'\n"
            f"- Include one link naturally: {link}\n"
            f"- Conversational, no hard sell\n"
            f"- Do NOT use these words: {banned}\n"
            f"- No emojis\n"
            f"- Return ONLY the message text"
        )
    else:  # step 3 — closing
        return (
            f"Write a short closing LinkedIn DM for {lead.get('Name', '')} who connected with "
            f"{company['from_name']} at {company['name']} but hasn't replied to the follow-up.\n\n"
            f"Requirements:\n"
            f"- 2 sentences max\n"
            f"- Start with 'Hey {first} —'\n"
            f"- Leave the door open without pressure\n"
            f"- Do NOT use these words: {banned}\n"
            f"- No emojis\n"
            f"- Return ONLY the message text"
        )


def generate_linkedin_message(lead: dict, config: dict, step: int = 1) -> str:
    """
    Generate a LinkedIn message for a lead.

    step 1 = connection request note (<=300 chars)
    step 2 = first DM after connecting
    step 3 = closing DM
    """
    compose  = config["compose"]
    provider = compose.get("provider", "claude").lower()
    model    = compose.get("model", "claude-haiku-4-5-20251001")
    note_max = config.get("linkedin", {}).get("note_max_chars", 300)
    prompt   = _build_linkedin_prompt(lead, config, step=step, note_max_chars=note_max)

    if provider == "claude":
        import anthropic
        client  = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        message = client.messages.create(
            model=model,
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text.strip()
    elif provider == "openai":
        from openai import OpenAI
        client   = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content.strip()
    else:
        raise ValueError(f"Unknown compose provider: {provider!r}. Use 'claude' or 'openai'.")


def generate_email(lead: dict, config: dict, step: int = 1) -> tuple[str, str]:
    """
    Generate a personalized email for a lead.

    Args:
        lead:   Lead dict (Name, Bio, Company, Profile, etc.)
        config: Full config.yaml contents
        step:   Sequence step (1 = initial outreach, 2+ = follow-ups)

    Returns:
        (subject, html_body)
    """
    compose  = config["compose"]
    provider = compose.get("provider", "claude").lower()
    model    = compose.get("model", "claude-opus-4-5")
    prompt   = _build_prompt(lead, config, step=step)

    if provider == "claude":
        return _call_claude(prompt, model)
    elif provider == "openai":
        return _call_openai(prompt, model)
    else:
        raise ValueError(
            f"Unknown compose provider: {provider!r}. Use 'claude' or 'openai'."
        )
