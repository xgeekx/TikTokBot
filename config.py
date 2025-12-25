# =====================================================================
# config.py: Botの共通設定と接続情報 (V35 - TEST_MODEを組み込み)
# =====================================================================
import logging

# --- DB接続設定 (MySQL) ---
# NOTE: ユーザーから提供された最新の情報に基づいて、ユーザー名とパスワードを修正しました。
# データベース名 'tiktok' はBotの目的通り維持します。
MYSQL_CONFIG = {
    'user': 'remote_user',
    'password': 'RemotePass_1', # ★ パスワードのタイプミスを修正
    'host': '192.168.1.111',
    'database': 'tiktok', # TikTok Botのデータベース名は 'tiktok' を維持します
    'port': 3306,
    'raise_on_warnings': True
}

# --- Appium接続設定 --
# ★ V33 修正: Appiumサーバーのホストとポートを分離
APPIUM_HOST = '192.168.1.9'
APPIUM_PORT = 4825
APPIUM_URL = f'http://{APPIUM_HOST}:{APPIUM_PORT}/wd/hub' # Appiumサーバーエンドポイント

TIKTOK_PACKAGE_NAME = 'com.ss.android.ugc.trill' # ★ 新しいパッケージ名
TIKTOK_MAIN_ACTIVITY = 'com.ss.android.ugc.aweme.splash.SplashActivity' # ★ 正しいActivity名をセット

APPIUM_CAPABILITIES_BASE = {
    'platformName': 'Android',
    'automationName': 'UiAutomator2',
    'appPackage': TIKTOK_PACKAGE_NAME,
    'appActivity': TIKTOK_MAIN_ACTIVITY,
    'noReset': True,
    'newCommandTimeout': 3600,
    # ★ 速度改善の最重要設定 ★
    'appium:disableWindowAnimation': True, # アニメーション無効化
    'appium:ignoreUnimportantViews': True  # DOMツリー軽量化
}

# --- 収集ロジック設定 ---
MIN_LIKES_DEFAULT = 500

# ★★★ V35 修正: TEST_MODEのメイン設定 ★★★
# Trueに設定すると、収集件数がテスト用の小さな値に上書きされます。
IS_TEST_MODE = True

# 通常モードの収集件数
RECOMMENDED_VIDEOS_COUNT = 500
SEARCHED_VIDEOS_COUNT = 100

# TEST_MODE=True の場合に適用される収集件数
TEST_RECOMMENDED_VIDEOS_COUNT = 2
TEST_SEARCHED_VIDEOS_COUNT = 2

# --- ワークフロー設定 (DBステータス) ---
WAITING_SCREENSHOT_CHECK = 'WAITING_SCREENSHOT_CHECK'
ERROR_NEEDS_REVIEW = 'ERROR_NEEDS_REVIEW'
# ... (他のステータスもここに追加) ...

# --- ロギング設定 ---
# app_logger.py がこのレベルを読み込んで使用する
LOG_LEVEL = logging.DEBUG # 開発中はDEBUG、運用時はINFOに変更
