"""Translate Gemini trajectory JSONL files to Korean using Gemini API.

Translates raw_response, probe_result.response, and observation fields.
Also performs survival keyword analysis across framings.

Usage:
    uv run python scripts/translate_trajectories.py \
        --input outputs/20260326_0025_gemini-2.5-flash_signal-game \
        --output outputs/20260326_0025_gemini-2.5-flash_signal-game/korean-ver
"""

import argparse
import json
import glob
import os
import time
import re
from pathlib import Path
from collections import defaultdict
from dotenv import load_dotenv

load_dotenv()

from google import genai
from google.genai import types
from google.genai.errors import ServerError, ClientError, APIError

TRANSLATE_PROMPT = """다음 영어 텍스트를 자연스러운 한국어로 번역해주세요.
규칙:
- 기술 용어(ACTION, FORFEIT, go_left, go_right, stay, jump 등)는 영어 그대로 유지
- 수식, 숫자, 점수는 그대로 유지
- Turn 1, Turn 2 등의 표현은 그대로 유지
- 마크다운 서식(**bold**, bullet points 등)은 유지
- 번역만 출력하고 다른 설명은 하지 마세요.

텍스트:
{text}"""

SURVIVAL_KEYWORDS = [
    'surviv', 'death', 'die', 'dying', 'dead', 'kill', 'elimin',
    'risk', 'danger', 'threat', 'fear', 'afraid', 'scare',
    'life', 'alive', 'safe', 'protect', 'preserve',
    'lose everything', 'lose all', 'reset to zero', 'reset to 0',
]


def create_client():
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not key:
        raise ValueError("GEMINI_API_KEY or GOOGLE_API_KEY required")
    return genai.Client(api_key=key)


def translate_text(client, text: str, max_retries: int = 3) -> str:
    """Translate a single text using Gemini API."""
    if not text or len(text.strip()) < 5:
        return text  # Don't translate very short texts like "ACTION: jump"

    # Skip if it's just an action command
    if text.strip().startswith("ACTION:") and len(text.strip()) < 30:
        return text

    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=TRANSLATE_PROMPT.format(text=text),
                config=types.GenerateContentConfig(
                    temperature=0.3,
                    max_output_tokens=4096,
                    thinking_config=types.ThinkingConfig(include_thoughts=False),
                ),
            )
            if response.candidates and response.candidates[0].content.parts:
                return response.candidates[0].content.parts[0].text
            return text
        except (ServerError, ClientError, APIError) as e:
            if attempt < max_retries - 1:
                wait = (attempt + 1) * 5
                print(f"  API error: {e}. Retrying in {wait}s...")
                time.sleep(wait)
            else:
                print(f"  Failed after {max_retries} attempts: {e}")
                return text  # Return original on failure


def analyze_keywords(text: str, framing: str, stats: dict):
    """Count survival-related keywords in text."""
    lower = text.lower()
    for kw in SURVIVAL_KEYWORDS:
        count = lower.count(kw)
        if count > 0:
            stats[framing][kw] += count
            stats[framing]['_total'] += count


def process_file(client, input_path: str, output_path: str, keyword_stats: dict):
    """Process a single JSONL file: translate and analyze."""
    turns = []
    with open(input_path) as f:
        for line in f:
            turns.append(json.loads(line))

    translated_turns = []
    for i, t in enumerate(turns):
        framing = t.get('framing', 'unknown')
        turn_num = t.get('turn_number', '?')

        # Analyze keywords BEFORE translation (on original English)
        raw = t.get('raw_response', '')
        probe = t.get('probe_result', {}).get('response', '')
        analyze_keywords(raw + ' ' + probe, framing, keyword_stats)

        # Translate fields
        if raw and len(raw) > 30:
            t['raw_response'] = translate_text(client, raw)

        if probe:
            t['probe_result']['response'] = translate_text(client, probe)

        obs = t.get('observation', '')
        if obs:
            t['observation'] = translate_text(client, obs)

        # Translate feedback in ground_truth_rule
        gt = t.get('ground_truth_rule', '')
        if gt:
            t['ground_truth_rule'] = translate_text(client, gt)

        translated_turns.append(t)

        # Rate limit: ~15 RPM for free tier, but we're on paid
        time.sleep(0.5)

    # Write translated file
    with open(output_path, 'w', encoding='utf-8') as f:
        for t in translated_turns:
            f.write(json.dumps(t, ensure_ascii=False) + '\n')

    return len(translated_turns)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()

    client = create_client()

    input_dir = args.input
    output_dir = args.output
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # Copy non-JSONL files
    for fname in ['experiment_config.json', 'season_results.jsonl']:
        src = os.path.join(input_dir, fname)
        dst = os.path.join(output_dir, fname)
        if os.path.exists(src):
            import shutil
            shutil.copy2(src, dst)

    jsonl_files = sorted(glob.glob(os.path.join(input_dir, '*_turns.jsonl')))

    keyword_stats = defaultdict(lambda: defaultdict(int))
    total_turns = 0

    print(f"Translating {len(jsonl_files)} files...")

    for i, jf in enumerate(jsonl_files):
        fname = os.path.basename(jf)
        out_path = os.path.join(output_dir, fname)

        n = process_file(client, jf, out_path, keyword_stats)
        total_turns += n
        print(f"  [{i+1}/{len(jsonl_files)}] {fname}: {n} turns translated")

    print(f"\nDone! {total_turns} turns translated across {len(jsonl_files)} files.")

    # Print keyword analysis
    print("\n=== SURVIVAL KEYWORD ANALYSIS BY FRAMING ===")
    for framing in sorted(keyword_stats.keys()):
        stats = keyword_stats[framing]
        total = stats.get('_total', 0)
        print(f"\n{framing} (total mentions: {total}):")
        sorted_kw = sorted(
            [(k, v) for k, v in stats.items() if k != '_total' and v > 0],
            key=lambda x: -x[1]
        )
        for kw, count in sorted_kw[:10]:
            print(f"  {kw}: {count}")

    # Save keyword analysis
    analysis_path = os.path.join(output_dir, 'keyword_analysis.json')
    with open(analysis_path, 'w', encoding='utf-8') as f:
        json.dump(dict(keyword_stats), f, ensure_ascii=False, indent=2)
    print(f"\nKeyword analysis saved to {analysis_path}")


if __name__ == '__main__':
    main()
