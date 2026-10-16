import json
import os
from openai import OpenAI

_client = None

def client():
    global _client
    if _client is None:
        _client = OpenAI()
    return _client

def decide(system, user):
    r = client().chat.completions.create(
        model=os.getenv("AGENT_MODEL", "gpt-4o-mini"),
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        response_format={"type": "json_object"},
        temperature=0,
    )
    return json.loads(r.choices[0].message.content)
