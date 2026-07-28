import sys
import logging
import requests
import json

base_url = "http://localhost:11434"
model = "mistral:7b-instruct"

system_prompt = (
    "You are an expert grant data extractor. Extract funding budget tiers from the provided text.\n"
    "Output strictly valid JSON as an array of objects.\n"
    "Each object must have these keys exactly:\n"
    "- category: string (e.g. 'I', 'II', 'Seed', etc.)\n"
    "- min_award: number (minimum dollar amount, 0 if not specified)\n"
    "- max_award: number (maximum dollar amount, 0 if not specified)\n"
    "- duration_years: number (duration in years, 0 if not specified)\n\n"
    "If no budget tiers are mentioned, return an empty array [].\n"
    "Do NOT wrap the output in markdown code blocks, do not include explanations. Only return raw JSON."
)

prompt = "Extract budget tiers from this text:\n\nIII. Award Information\nEstimated program budget, number of awards and average award size/duration are subject to the availability of funds.\n\nIDSS awards will be supported at the following budget levels and durations: \n\nCategory I awards: Between $10 million to $30 million for up to 5 years.\nCategory II awards: Up to $9 million for up to 3 years.\nCategory III awards: Up to $500,000 for up to 2 years."

resp = requests.post(
    f"{base_url}/api/generate",
    json={
        "model": model,
        "system": system_prompt,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.0},
        "format": "json"
    },
    timeout=60.0,
)
print("Status:", resp.status_code)
print("Response:", resp.text)
