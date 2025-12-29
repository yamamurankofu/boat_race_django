# prediction/views.py

from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.middleware.csrf import get_token
import json
import subprocess
import os
from datetime import datetime, timedelta

# すべての競艇場
ALL_VENUES = [
    '桐生', '戸田', '江戸川', '平和島', '多摩川', '浜名湖',
    '蒲郡', '常滑', '津', '三国', 'びわこ', '住之江',
    '尼崎', '鳴門', '丸亀', '児島', '宮島', '徳山',
    '下関', '若松', '芦屋', '福岡', '唐津', '大村'
]

@require_http_methods(["GET"])
def index(request):
    """メインページを表示"""
    get_token(request)
    return render(request, 'prediction/index.html')


@require_http_methods(["POST"])
def generate_prediction(request):
    """
    AJAX リクエストを受け取り、バリデーション後、
    Python スクリプトを実行して予想結果を JSON で返す
    """
    try:
        # リクエストから選択データを取得
        data = json.loads(request.body)
        location = data.get('location', '江戸川')
        date_str = data.get('date', '')
        race_num = data.get('race_num', 5)
        
        print(f"DEBUG: Request Method: {request.method}")
        print(f"DEBUG: Parsed Data - location: {location}, date: {date_str}, race_num: {race_num}")
        
        # ===== バリデーション：日付の検証 =====
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
        
        # ===== AI 予想生成処理 =====
        # 環境変数を設定
        env = os.environ.copy()
        env['LOCATION'] = location
        env['DATE'] = date_str
        env['RACE_NUM'] = str(race_num)
        env['OPENAI_API_KEY'] = os.environ.get('OPENAI_API_KEY', '')
        
        # Django の BASE_DIR を取得
        from django.conf import settings
        base_dir = settings.BASE_DIR
        
        # Python スクリプトを実行
        result = subprocess.run(
            ['python', 'boat_race_ai.py'],
            cwd=str(base_dir),
            capture_output=True,
            text=True,
            env=env,
            timeout=300
        )
        
        print(f"DEBUG: Subprocess Return Code: {result.returncode}")
        print(f"DEBUG: Subprocess stdout: {result.stdout}")
        print(f"DEBUG: Subprocess stderr: {result.stderr}")
        
        # 実行結果を返す
        if result.returncode == 0:
            return JsonResponse({
                'status': 'success',
                'message': '予想生成が完了しました',
                'output': result.stdout
            })
        else:
            # スクレイピング失敗時のメッセージをカスタマイズ
            url = f"https://www.boatrace.jp/owpc/pc/race/index?hd={date_str.replace('-', '')}"
            custom_message = f"{date_str} {location}競艇場の開催のレースはありません。\n詳細は以下をご確認ください\nURL：{url}"
            
            return JsonResponse({
                'status': 'error',
                'message': custom_message
            }, status=200)  # ← status=200 に変更（400ではなく）
    
    except json.JSONDecodeError as e:
        print(f"DEBUG: JSONDecodeError: {e}")
        return JsonResponse({
            'status': 'error',
            'message': 'リクエストフォーマットが不正です'
        }, status=400)
    except subprocess.TimeoutExpired:
        return JsonResponse({
            'status': 'error',
            'message': 'タイムアウト：予想生成に時間がかかっています'
        }, status=400)
    except Exception as e:
        print(f"DEBUG: Exception: {e}")
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)