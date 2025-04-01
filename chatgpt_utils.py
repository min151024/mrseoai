import openai
import os
from dotenv import load_dotenv

load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

# ChatGPT用プロンプト生成
def build_prompt(target_url, competitors_info):
    prompt = f"""
以下は、順位が下がったWebページ「{target_url}」に対して、競合ページのタイトルとメタ情報の一覧です。
これらと比較して、{target_url} のタイトル・メタ情報の改善点やリライト案を具体的に提案してください。

競合ページ情報:
"""
    for i, info in enumerate(competitors_info, start=1):
        prompt += f"\n{i}. タイトル: {info['title']}\nメタディスクリプション: {info['meta_description']}\nURL: {info['url']}\n"

    prompt += "\n\n改善提案をお願いします。"
    return prompt


# ChatGPTに投げる
def get_chatgpt_response(prompt):
    openai.api_key = os.getenv("OPENAI_API_KEY")

    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",  # or "gpt-3.5-turbo"
            messages=[
                {"role": "system", "content": "あなたはSEOの専門家です。"},
                {"role": "user", "content": prompt}
            ],
            max_tokens=1000,
            temperature=0.7
        )
        return response['choices'][0]['message']['content'].strip()
    except Exception as e:
        print("❌ ChatGPT APIエラー:", e)
        return None
