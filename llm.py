import json
import os
from openai import OpenAI

_client = None

def client():
    global _client
    if _client is None:
        # Point to Groq instead of OpenAI
        _client = OpenAI(
            base_url="https://api.groq.com/openai/v1",
            api_key=os.getenv("GROQ_API_KEY"),
        )
    return _client

def decide(system, user):
    r = client().chat.completions.create(
        model=os.getenv("AGENT_MODEL", "openai/gpt-oss-120b"),
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        response_format={"type": "json_object"},
        temperature=0,
    )
    return json.loads(r.choices[0].message.content)
