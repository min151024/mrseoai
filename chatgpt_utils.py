import openai
import os
from dotenv import load_dotenv

load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

# ChatGPT用プロンプト生成
def build_prompt(target_url, competitors_info, ga_data):
    """対象URL、競合ページ情報、GAデータからChatGPT用のプロンプトを作成する"""

    # 競合ページ情報をテキスト化
    competitors_text = ""
    for comp in competitors_info:
        title = comp.get("title", "タイトルなし")
        description = comp.get("description", "ディスクリプションなし")
        competitors_text += f"・タイトル: {title}\n  ディスクリプション: {description}\n\n"

    # Google Analyticsデータをテキスト化
    if ga_data is not None and not ga_data.empty:
        ga_text = ga_data.to_string(index=False)
    else:
        ga_text = "Google Analytics データなし"

    # 最終プロンプト組み立て
    prompt = f"""
対象ページ: {target_url}

【競合ページのメタ情報】
{competitors_text}

【対象ページのGoogle Analyticsデータ】
{ga_text}

上記を参考にして、対象ページのタイトルとメタディスクリプションの改善案を提案してください。
"""
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
