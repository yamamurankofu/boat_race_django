import requests
from lxml import html
import time
from datetime import datetime
from openai import OpenAI
import os
import sys

# OpenAI APIキーを設定
api_key = os.environ.get("OPENAI_API_KEY")
if not api_key:
    print("❌ エラー: OPENAI_API_KEY が設定されていません")
    sys.exit(1)

client = OpenAI(api_key=api_key)

KYOTEI_JO_CODE_LIST = {
    "桐生": "01",
    "戸田": "02",
    "江戸川": "03",
    "平和島": "04",
    "多摩川": "05",
    "蒲郡": "07",
    "住之江": "12",
    "下関": "19"
}

KYOTEI_ENTRY_URL = "https://www.boatrace.jp/owpc/pc/race/racelist?"

# ============================================
# 環境変数から動的に取得
# ============================================
j_name = os.environ.get('LOCATION', '江戸川')
date_str = os.environ.get('DATE', '2024-08-03')
race_num = int(os.environ.get('RACE_NUM', '5'))

# 日付を変換（YYYY-MM-DD → YYYYMMDD）
race_day = date_str.replace('-', '')

# 選択した場所からコードを取得
j_code = KYOTEI_JO_CODE_LIST.get(j_name, "03")
frame_weight = 0.05

print(f"📍 競艇場: {j_name}")
print(f"📅 日付: {date_str}")
print(f"🏁 レース: {race_num}R")
print(f"🔧 コード: jcd={j_code}, hd={race_day}\n")
# ============================================


def get_kyotei_entry_list_html(race: int, url: str):
    """競艇のエントリーリストHTMLを取得"""
    element_html = ""
    try:
        print(f"{race}R URL: {url}")
        response = requests.get(url, timeout=60)

        if response.status_code == 200:
            print(f"{race}R 成功しました")
            response.encoding = response.apparent_encoding
            tree = html.fromstring(response.content)
            element = tree.cssselect('body > main > div > div > div > div.contentsFrame1_inner > div.table1.is-tableFixed__3rdadd')

            if element:
                tables = element[0].xpath('.//table')
                for table in tables:
                    colgroups = table.xpath('./colgroup')
                    for colgroup in colgroups:
                        colgroup.getparent().remove(colgroup)

                print(f"{race}R 要素を取得しました")
                element_html = html.tostring(element[0], encoding='unicode')
                return element_html
            else:
                print(f"{race}R 指定した要素が見つかりません")
                return None
        else:
            print(f"{race}R リクエストが失敗しました。ステータスコード: {response.status_code}")
            return None

    except Exception as e:
        print(f"{race}R エラーが発生しました: {e}")
        return None


def generate_boat_race_prediction(race_num, entry_html, j_name, frame_weight):
    """第1段階: HTMLデータを基に競艇予想を生成"""
    try:
        system_prompt = """あなたは、競艇予想の専門家です。
ステップバイステップで予想をしてください。"""
        
        user_prompt = f"""あなたは、競艇予想の専門家です。
ステップバイステップで{j_name}競艇場の{race_num}Rの3連単の予想をしてください。

出走情報内容説明:
- 級別は、B2が最も弱く=>B1=>A2・A1の順に強くなります。
- 全国成績は、その選手の全ての競艇場でのこれまでの成績確率です。
- 当地成績は、その選手の{j_name}競艇場でのこれまでの成績確率です。
- モーターは、そのモーターのこれまでの成績確率です。
- ボートは、そのボートのこれまでの成績確率です。
- STは、スタートタイミングのことであり0に近いほどスタートが速い強い選手と言えます。
- 勝率は、その選手のこれまでの成績で1着になった確率です。
- 2連率は、その選手のこれまでの成績で1着、2着までに入った確率です。
- 3連率は、その選手のこれまでの成績で1着、2着、3着までに入った確率です。

ルール:
- 日本語で回答すること。
- 素早い回答よりも正確な回答を重視します。
- 級別と当地勝率とモーターの勝率、STを考慮して、専門家としての予想をすること。
- 枠の有利さは、1着にのみ考慮する。1が最も有利で=>2=>3=>4=>5=>6の順に有利さが{frame_weight}ずつ減少します。
- STの差が0.2以上大きい場合は、スタートの早い選手の有利さを増します。
- 出力フォーマットに従って回答すること。
- 予想理由を200文字程度で添える。

出走情報（HTMLテーブル）:
{entry_html}

出力フォーマット:
## ステップ1で確認した出走情報
[6選手の情報を出力]

## ステップ2で予想した1号艇が1着に来る確率
[確率を出力]

## ステップ3で予想した2連単
[2連単を出力]

## ステップ4で予想した3連単
[3連単を出力]

## ステップ5で予想した1着
[1着予想を出力]

## ステップ6で予想した2連単
[2連単を出力]

## ステップ7で予想した3連単
[3連単を出力]

## 予想理由:
[予想理由を出力]

## ステップ8で予想した各艇の1着に来る確率
[各艇の1着確率を出力]"""
        
        print(f"\n{race_num}R: 第1段階プロンプト実行中（予想生成）...")
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.7,
            max_tokens=2000
        )
        
        first_result = response.choices[0].message.content
        print(f"{race_num}R: 予想生成完了")
        
        return first_result

    except Exception as e:
        print(f"第1段階プロンプトエラー: {e}")
        return None


def format_prediction_result(race_num, first_result):
    """第2段階: 第1段階の結果を指定フォーマットに整形"""
    try:
        system_prompt = """あなたは、データ整形の専門家です。
与えられた予想情報から必要な情報を抽出して、指定されたフォーマットで出力してください。"""
        
        # ===== 修正：第2段階プロンプトを改善 =====
        # ChatGPT が「1号艇が1着」と「1号艇以外が1着」の違いを理解できるように、
        # より詳細で明確なルールを追加しました
        user_prompt = f"""下記の予想情報から出力フォーマットを参考に情報を全て抜き出して、出力フォーマットの形式で出力してください。

重要なルール:
- 「1号艇が1着に来る」セクションと「1号艇以外の選手が1着に来る」セクションは、完全に異なります。
- 「1号艇以外の選手の1着に来る3連単」には、絶対に1号艇(1)を含めてはいけません。
- 例：「2-3-4」「3-2-5」「4-3-6」など、最初の数字が2以上で始まる組み合わせのみを出力します。
- 「1-2-4」や「1-2-5」のように1が含まれている組み合わせは出力しないでください。
- ステップ6とステップ7は、1号艇が1着ではない場合の対抗馬の予想です。

出力フォーマット:
◆ 1号艇が1着に来る確率
{{##ステップ2で予想した1号艇が1着に来る確率}}

◆ 1号艇が1着に来る2連単
{{##ステップ3で予想した2連単}}

◆ 1号艇が1着に来る3連単
{{##ステップ4で予想した3連単}}

◆ 1号艇以外の選手の1着に来る2連単
{{##ステップ6で予想した2連単（1号艇が1着ではない場合の2連単。1は含めない）}}

◆ 1号艇以外の選手の1着に来る3連単
{{##ステップ7で予想した3連単（1号艇が1着ではない場合の3連単。最初の数字が2以上のみ。絶対に1を含めない）}}

◆ 予想理由
{{##予想理由}}

◆ 各艇の1着確率
{{##ステップ8で予想した各艇の1着に来る確率}}

予想情報:
{first_result}"""
        # ===== 修正終了 =====
        
        print(f"\n{race_num}R: 第2段階プロンプト実行中（結果整形）...")
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.3,
            max_tokens=1000
        )
        
        formatted_result = response.choices[0].message.content
        print(f"{race_num}R: 結果整形完了")
        
        return formatted_result

    except Exception as e:
        print(f"第2段階プロンプトエラー: {e}")
        return None


def main():
    """メイン処理：2段階プロンプト実行"""
    entry_url = f"{KYOTEI_ENTRY_URL}rno={race_num}&jcd={j_code}&hd={race_day}"
    entry_html = get_kyotei_entry_list_html(race_num, entry_url)
    
    if entry_html is None:
        print(f"\n❌ エラー: {race_day} {j_name}競艇場 {race_num}Rの情報取得に失敗しました")
        print(f"詳細は以下をご確認ください")
        print(f"https://www.boatrace.jp/owpc/pc/race/index?hd={race_day}")
        sys.exit(1)
    
    # 第1段階：予想生成
    first_result = generate_boat_race_prediction(race_num, entry_html, j_name, frame_weight)
    
    if first_result is None:
        print(f"\n❌ エラー: 予想生成に失敗しました")
        sys.exit(1)
    
    print(f"\n{'='*80}")
    print(f"【{race_num}R 第1段階結果】")
    print(f"{'='*80}")
    print(first_result)
    
    time.sleep(2)
    
    # 第2段階：結果整形
    formatted_result = format_prediction_result(race_num, first_result)
    
    if formatted_result is None:
        print(f"\n❌ エラー: 結果の整形に失敗しました")
        sys.exit(1)
    
    print(f"\n{'='*80}")
    print(f"【{race_num}R 最終予想（整形済み）】")
    print(f"{'='*80}")
    print(formatted_result)


if __name__ == "__main__":
    main()