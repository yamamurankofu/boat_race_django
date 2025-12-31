# prediction/views.py

from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.middleware.csrf import get_token
import json
import os
from datetime import datetime, timedelta
import requests
from lxml import html
from openai import OpenAI

@require_http_methods(["GET"])
def index(request):
    """メインページを表示"""
    get_token(request)
    return render(request, 'prediction/index.html')


@require_http_methods(["POST"])
def generate_prediction(request):
    """
    AJAX リクエストを受け取り、予想結果を JSON で返す
    """
    try:
        # リクエストから選択データを取得
        data = json.loads(request.body)
        location = data.get('location', '江戸川')
        date_str = data.get('date', '')
        race_num = data.get('race_num', 5)
        
        # 日付検証
        today = datetime.now().date()
        tomorrow = today + timedelta(days=1)
        
        try:
            selected_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            return JsonResponse({
                'status': 'error',
                'message': '日付形式が不正です'
            }, status=400)
        
        if selected_date > tomorrow:
            return JsonResponse({
                'status': 'error',
                'message': '明日までの日付のみ選択可能です'
            }, status=400)
        
        # AI予想生成
        result = run_prediction(location, date_str, race_num)
        
        if result['success']:
            return JsonResponse({
                'status': 'success',
                'message': '予想生成が完了しました',
                'output': result['output']
            })
        else:
            url = f"https://www.boatrace.jp/owpc/pc/race/index?hd={date_str.replace('-', '')}"
            return JsonResponse({
                'status': 'error',
                'message': f"{date_str} {location}競艇場の開催のレースはありません。\n詳細は以下をご確認ください\nURL：{url}"
            }, status=200)
    
    except Exception as e:
        print(f"DEBUG: Exception: {e}")
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)


def run_prediction(location, date_str, race_num):
    """AI予想を実行"""
    KYOTEI_JO_CODE_LIST = {
        "桐生": "01", "戸田": "02", "江戸川": "03", "平和島": "04",
        "多摩川": "05", "蒲郡": "07", "住之江": "12", "下関": "19"
    }
    
    j_code = KYOTEI_JO_CODE_LIST.get(location, "03")
    race_day = date_str.replace('-', '')
    
    # HTMLデータ取得
    url = f"https://www.boatrace.jp/owpc/pc/race/racelist?rno={race_num}&jcd={j_code}&hd={race_day}"
    
    try:
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            return {'success': False, 'output': ''}
        
        response.encoding = response.apparent_encoding
        tree = html.fromstring(response.content)
        element = tree.cssselect('body > main > div > div > div > div.contentsFrame1_inner > div.table1.is-tableFixed__3rdadd')
        
        if not element:
            return {'success': False, 'output': ''}
        
        tables = element[0].xpath('.//table')
        for table in tables:
            colgroups = table.xpath('./colgroup')
            for colgroup in colgroups:
                colgroup.getparent().remove(colgroup)
        
        entry_html = html.tostring(element[0], encoding='unicode')
        
        # OpenAI API呼び出し
        api_key = os.environ.get('OPENAI_API_KEY')
        if not api_key:
            return {'success': False, 'output': 'OpenAI APIキーが設定されていません'}
        
        client = OpenAI(api_key=api_key)
        
        # 予想生成
        prediction = generate_boat_race_prediction(client, race_num, entry_html, location)
        
        return {'success': True, 'output': prediction}
        
    except Exception as e:
        print(f"Prediction Error: {e}")
        return {'success': False, 'output': str(e)}


def generate_boat_race_prediction(client, race_num, entry_html, j_name):
    """OpenAI APIで予想生成"""
    system_prompt = "あなたは、競艇予想の専門家です。ステップバイステップで予想をしてください。"
    
    user_prompt = f"""あなたは、競艇予想の専門家です。
ステップバイステップで{j_name}競艇場の{race_num}Rの3連単の予想をしてください。

出走情報（HTMLテーブル）:
{entry_html}

出力フォーマット:
## {race_num}R 予想結果

### 1号艇が1着に来る確率
[確率]

### 推奨3連単
[3連単の買い目]

### 予想理由
[200文字程度の理由]
"""
    
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.7,
            max_tokens=2000
        )
        
        return response.choices[0].message.content
    except Exception as e:
        return f"AI予想エラー: {e}"
