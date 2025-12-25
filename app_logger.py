import logging
import sys
import os

# config.py から LOG_LEVEL をインポートすることを想定
try:
    from config import LOG_LEVEL
except ImportError:
    LOG_LEVEL = logging.DEBUG  # config が読み込めない場合のデフォルト

# -------------------------------------------------
# 1. グローバルLoggerインスタンスの作成
# -------------------------------------------------
# Bot全体でこの 'logger' インスタンスを共有する
# 他のファイル (helper, manager) はこれをインポートする
logger = logging.getLogger('TikTokBot')

# ★ V49 修正: ログが INFO にリセットされるのを防ぐため、
# グローバルロガーのレベルを DEBUG に強制設定する
logger.setLevel(logging.DEBUG)


# -------------------------------------------------
# 2. ログハンドラの設定関数
# -------------------------------------------------
def setup_logging_handlers():
    """
    メインスクリプト (collector_bot_main.py) から呼び出され、
    ログの出力先（コンソールやファイル）を設定する。
    """
    # ハンドラが既に追加されている場合は、重複して追加しない
    if not logger.hasHandlers():
        # 1. コンソールへのハンドラ
        console_handler = logging.StreamHandler(sys.stdout)

        # ★ V49 修正: ハンドラのレベルも DEBUG に強制設定
        console_handler.setLevel(logging.DEBUG)

        # 詳細なログフォーマット
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - (%(filename)s:%(lineno)d) - %(message)s'
        )
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        # TODO: (オプション) ファイルへのハンドラ
        # file_handler = logging.FileHandler('bot_log.log')
        # logger.addHandler(file_handler)

        logger.info("Logger handlers configured successfully and set to DEBUG verbosity.")