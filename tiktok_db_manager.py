# =====================================================================
# tiktok_db_manager.py: TikTok BotのDB操作ロジック (V26 - 安定版)
# =====================================================================
from base_db import BaseDB
from config import MYSQL_CONFIG, MIN_LIKES_DEFAULT, WAITING_SCREENSHOT_CHECK, ERROR_NEEDS_REVIEW
from typing import Dict, Any, Optional, List
import time
import pymysql.err
from app_logger import logger  # ★ グローバルロガーをインポート

# ★ V49 修正: collector_bot_main から TARGET_COUNTRY_CODE をインポートできないため、
# config.py から直接インポートするか、渡す必要がある。
# ここでは config.py から直接インポートする代わりに、
# collector_bot_main のグローバル変数を参照することを期待する (DB挿入時のフォールバック)
# (より良い設計は、insert_new_video_record に country_code を必須引数として渡すこと)
try:
    # V49: フォールバックのためのインポート試行
    from collector_bot_main import TARGET_COUNTRY_CODE
except ImportError:
    TARGET_COUNTRY_CODE = 'N/A'  # フォールバックのデフォルト


class TikTokDBManager(BaseDB):

    def __init__(self):
        """
        BaseDBを継承し、接続情報を渡す。
        接続成功後、テーブル作成を試みる。
        """
        logger.info("Initializing TikTokDBManager...")
        # BaseDBの __init__ に MYSQL_CONFIG を渡す
        super().__init__(MYSQL_CONFIG)

        if self._conn:
            self._create_all_tables()

    def _create_all_tables(self):
        """システムに必要な全てのテーブルを作成する"""
        logger.debug("Checking/Creating all required tables...")
        try:
            # 1. Bot設定
            self._create_bot_configurations_table()
            # 2. 収集フィルター
            self._create_like_thresholds_table()
            # 3. 検索キーワード
            self._create_search_words_table()
            # 4. メインデータ
            self._create_tiktok_videos_table()
            # 5. 履歴ログ
            self._create_history_table()

            self.commit()
            logger.info("-> [Manager] 全てのテーブルの作成/チェックが完了しました。")
        except Exception as e:
            logger.error(f"Error: テーブル作成中に致命的なエラーが発生しました: {e}")
            raise

    # ----------------------------------------------------------------
    # I. テーブル作成ロジック (全カラムの定義を含む)
    # ----------------------------------------------------------------

    def _create_bot_configurations_table(self):
        """Botの設定を管理するテーブルの作成"""
        logger.debug("Checking table: bot_configurations")
        sql = """
            CREATE TABLE IF NOT EXISTS bot_configurations
            (
                  bot_id              INT             NOT NULL    PRIMARY KEY COMMENT 'Botの通し番号'
                , appium_device_name  VARCHAR(100)    NOT NULL
                , appium_udid         VARCHAR(100)    NOT NULL
                , target_country      VARCHAR(10)     NOT NULL
                , bot_type            VARCHAR(20)     NOT NULL
                , is_active           TINYINT(1)      NOT NULL    DEFAULT 1
                , last_started_at     DATETIME        NULL
                , appium_host         VARCHAR(100)    NULL        COMMENT 'V33 ADB連携用ホスト'
                , appium_port         INT             NULL        COMMENT 'V33 ADB連携用ポート'
            )
            COMMENT 'Botの実行設定とリソース管理'
        ;
        """
        self.execute_query(sql)

    def _create_like_thresholds_table(self):
        """国別いいね閾値 (LIKE_THRESHOLDS_BY_COUNTRY) の作成"""
        logger.debug("Checking table: LIKE_THRESHOLDS_BY_COUNTRY")
        sql = """
            CREATE TABLE IF NOT EXISTS LIKE_THRESHOLDS_BY_COUNTRY
            (
                  filter_id             INT             NOT NULL    AUTO_INCREMENT PRIMARY KEY
                , target_country        VARCHAR(10)     NOT NULL    UNIQUE
                , min_likes_threshold   INT             NOT NULL
                , is_active             TINYINT(1)      NOT NULL    DEFAULT 1
                , description           VARCHAR(255)    NULL
            )
            COMMENT 'Botの収集閾値設定'
        ;
        """
        self.execute_query(sql)

    def _create_search_words_table(self):
        """検索キーワード (search_words) の作成"""
        logger.debug("Checking table: search_words")
        sql = """
            CREATE TABLE IF NOT EXISTS search_words
            (
                  word_id               INT             NOT NULL    AUTO_INCREMENT PRIMARY KEY
                , search_word           VARCHAR(100)    NOT NULL    UNIQUE
                , target_country        VARCHAR(10)     NOT NULL
                , last_used             DATETIME        NOT NULL    DEFAULT CURRENT_TIMESTAMP
                , is_active             TINYINT(1)      NOT NULL    DEFAULT 1
            )
            COMMENT 'フィード最適化のための検索キーワード'
        ;
        """
        self.execute_query(sql)

    def _create_tiktok_videos_table(self):
        """動画データテーブル (BLOB含む) の作成"""
        logger.debug("Checking table: tiktok_videos")
        sql = """
            CREATE TABLE IF NOT EXISTS tiktok_videos
            (
                  video_id                  VARCHAR(255)    NOT NULL    COMMENT 'TikTok動画の不変ID (PK)'
                , url                       VARCHAR(512)    NOT NULL    COMMENT 'ユーザーアクセス用URL'
                , channel_name              VARCHAR(100)    NOT NULL
                , likes_count               INT             NOT NULL
                , caption_text              TEXT            NULL
                , country_code              VARCHAR(10)     NOT NULL
                , created_at                DATETIME        NOT NULL    DEFAULT CURRENT_TIMESTAMP
                , last_processed_at         DATETIME        NULL
                , analysis_status           VARCHAR(50)     NOT NULL    COMMENT 'Botのワークフロー管理ステータス'
                , ai_screenshot_verdict     VARCHAR(20)     NULL
                , ai_translation_verdict    VARCHAR(20)     NULL
                , user_reviewed_at          DATETIME        NULL
                , screenshot_data           MEDIUMBLOB      NULL        COMMENT 'スクリーンショットのBLOBデータ'
                , feature_person_detected   TINYINT(1)      NOT NULL    DEFAULT 0
                , found_source              VARCHAR(20)     NOT NULL
                , searched_by_keyword       VARCHAR(100)    NULL
                , video_summary             VARCHAR(255)    NULL
                , full_translation_text     LONGTEXT        NULL
                , severity_score            INT             NULL
                , file_deleted              TINYINT(1)      NOT NULL    DEFAULT 0
                ,
                PRIMARY KEY (video_id)
            )
            COMMENT 'TikTok動画データと分析結果'
        ;
        """
        self.execute_query(sql)

    def _create_history_table(self):
        """履歴ログ (tiktok_video_history) の作成"""
        logger.debug("Checking table: tiktok_video_history")
        sql = """
            CREATE TABLE IF NOT EXISTS tiktok_video_history
            (
                  id                BIGINT          NOT NULL    AUTO_INCREMENT PRIMARY KEY
                , video_id          VARCHAR(255)    NOT NULL
                , status_from       VARCHAR(50)     NOT NULL
                , status_to         VARCHAR(50)     NOT NULL
                , processed_by      VARCHAR(50)     NOT NULL
                , log_message       TEXT            NULL
                , created_at        TIMESTAMP       NOT NULL    DEFAULT CURRENT_TIMESTAMP
            )
            COMMENT 'Botの処理履歴とエラーログ'
        ;
        """
        self.execute_query(sql)

    # ----------------------------------------------------------------
    # II. 収集 Bot 専用の操作
    # ----------------------------------------------------------------

    def fetch_bot_configuration(self, bot_id: int) -> Optional[Dict[str, Any]]:
        """Botの設定を bot_configurations テーブルから取得する"""
        sql = "SELECT * FROM bot_configurations WHERE bot_id = %s"
        return self.fetchone(sql, (bot_id,))

    def get_like_threshold(self, country_code: str) -> Optional[int]:
        """国別いいね閾値を取得する"""
        sql = "SELECT min_likes_threshold FROM LIKE_THRESHOLDS_BY_COUNTRY WHERE target_country = %s AND is_active = 1"
        record = self.fetchone(sql, (country_code,))

        if record and 'min_likes_threshold' in record:
            return int(record['min_likes_threshold'])

        logger.warning(f"DB: Like threshold not found for {country_code}. Using default.")
        return None

    def insert_new_video_record(self, metadata: Dict[str, Any], screenshot_binary_data: Optional[bytes]) -> str:
        """
        [V18 設計復元] BLOBを含む新規レコードを挿入し、PKを返す。重複時は'DUPLICATE'を返す。
        """
        sql = """
            INSERT INTO tiktok_videos 
            (video_id, url, channel_name, country_code, likes_count, caption_text, 
             analysis_status, screenshot_data, found_source, searched_by_keyword, last_processed_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
            ON DUPLICATE KEY UPDATE 
                likes_count = VALUES(likes_count), 
                last_processed_at = NOW()
        ;
        """

        # メタデータ辞書から安全に値を取得
        video_id = metadata.get('video_id')
        url = metadata.get('url')
        channel_name = metadata.get('channel_name', 'N/A')
        # ★ V49 修正: country_code を metadata から取得
        country_code = metadata.get('country_code', 'N/A')
        likes_count = metadata.get('likes_count', 0)
        caption_text = metadata.get('caption_text', '')
        found_source = metadata.get('found_source', 'UNKNOWN')
        searched_by_keyword = metadata.get('searched_by_keyword')

        if not video_id or not url:
            logger.error(f"DB Insert: Missing video_id or url in metadata. Cannot insert.")
            return 'ERROR_MISSING_DATA'

        # ★ V49 修正: country_code が 'N/A' の場合、挿入を試みない
        if country_code == 'N/A':
            logger.error(f"DB Insert: Missing country_code for video_id {video_id}. Cannot insert.")
            return 'ERROR_MISSING_DATA'

        values = (
            video_id, url, channel_name, country_code,
            likes_count, caption_text, WAITING_SCREENSHOT_CHECK,
            screenshot_binary_data, found_source, searched_by_keyword
        )

        try:
            self.execute_query(sql, values)
            self.commit()
            return video_id  # PK (video_id) を文字列で返す

        except pymysql.err.IntegrityError as e:
            if 'Duplicate entry' in str(e):
                logger.warning(f"DB: Duplicate entry found for video_id {video_id}. Skipping.")
                self.rollback()
                return 'DUPLICATE'
            logger.error(f"DB IntegrityError: {e}")
            self.rollback()
            return f'ERROR_DB: {e}'
        except Exception as e:
            logger.error(f"DB Insert Failed: {e}")
            self.rollback()
            return f'ERROR_DB: {e}'

    def log_history(self, video_id: str, status_from: str, status_to: str, log_message: str, processed_by_bot: str):
        """tiktok_video_historyテーブルにログを記録する"""
        if not video_id:
            logger.warning("DB LogHistory: Attempted to log with no video_id.")
            return

        sql = """
        INSERT INTO tiktok_video_history 
        (video_id, status_from, status_to, log_message, processed_by)
        VALUES (%s, %s, %s, %s, %s)
        """
        values = (video_id, status_from, status_to, log_message, processed_by_bot)

        try:
            self.execute_query(sql, values)
            self.commit()
        except Exception as e:
            logger.error(f"FATAL: Could not log history for {video_id}: {e}")
            self.rollback()

    def isolate_record_due_to_error(self, video_id: str, error_message: str, current_status: str, bot_id: str):
        """
        [V26 修正] 致命的エラー発生時にレコードを隔離し、履歴を記録する。
        video_id が None の場合はログ出力のみ。
        """
        if not video_id:
            logger.error(f"DB Isolate: Cannot isolate record without video_id. Error: {error_message}")
            return

        sql_update = """
        UPDATE tiktok_videos 
        SET analysis_status = %s, last_processed_at = NOW() 
        WHERE video_id = %s
        """

        try:
            # 1. メインテーブルのステータスをERROR_NEEDS_REVIEWに更新
            self.execute_query(sql_update, (ERROR_NEEDS_REVIEW, video_id))
            self.commit()  # ★ 隔離のUPDATEをコミット

            # 2. 履歴ログの記録 (別トランザクションとして実行)
            log_message = f"Error during status '{current_status}': {error_message}"
            self.log_history(video_id, current_status, ERROR_NEEDS_REVIEW, log_message, bot_id)

        except Exception as e:
            logger.error(f"FATAL: Failed to isolate record {video_id}. Error: {e}")
            self.rollback()

    def get_oldest_search_word(self, country_code: str) -> Optional[Dict[str, Any]]:
        """
        [V18 設計復元] 最も古い未使用の検索キーワードを取得し、last_usedを更新する (アトミック処理)
        """
        record = None
        try:
            # トランザクションを開始し、レコードをロックして競合を防ぐ
            self.start_transaction()
            logger.debug("DB: Transaction started for get_oldest_search_word.")

            # 1. 最も古いレコードをロックして取得
            sql_select = """
            SELECT word_id, search_word FROM search_words 
            WHERE target_country = %s AND is_active = 1
            ORDER BY last_used ASC 
            LIMIT 1 FOR UPDATE
            """
            record = self.fetchone(sql_select, (country_code,))

            if record:
                # 2. 取得したレコードのタイムスタンプを更新
                logger.debug(f"DB: Updating last_used for word_id {record['word_id']}")
                sql_update = "UPDATE search_words SET last_used = NOW() WHERE word_id = %s"
                self.execute_query(sql_update, (record['word_id'],))
            else:
                logger.debug(f"DB: No active search words found for {country_code}.")

            self.commit()
            logger.debug("DB: Transaction committed for get_oldest_search_word.")
            return record

        except Exception as err:
            logger.error(f"DB Error during search word rotation: {err}")
            self.rollback()
            logger.debug("DB: Transaction rolled back for get_oldest_search_word.")
            return None