# =====================================================================
# collector_bot_main.py (V61 - V50の動作ロジックに回帰)
# =====================================================================

import sys
import time
import traceback
from typing import Dict, Any, Optional, List
from selenium.common.exceptions import TimeoutException

# 依存モジュールのインポート
from config import MIN_LIKES_DEFAULT, WAITING_SCREENSHOT_CHECK, ERROR_NEEDS_REVIEW
# ★ V57 修正: configから全ての収集定数をインポート
from config import RECOMMENDED_VIDEOS_COUNT, SEARCHED_VIDEOS_COUNT
from config import IS_TEST_MODE, TEST_RECOMMENDED_VIDEOS_COUNT, TEST_SEARCHED_VIDEOS_COUNT
from config import APPIUM_HOST, APPIUM_PORT, LOG_LEVEL
from tiktok_appium_helper import TiktokAppiumHelper, AndroidConnectionError
from tiktok_db_manager import TikTokDBManager
from app_logger import logger, setup_logging_handlers

# --- グローバル変数 (Bot実行時に設定) ---
BOT_ID: Optional[int] = None
TARGET_COUNTRY_CODE: Optional[str] = None
MIN_LIKES_THRESHOLD: int = MIN_LIKES_DEFAULT
APPIUM_DRIVER_HELPER: Optional[TiktokAppiumHelper] = None
DB_MANAGER: Optional[TikTokDBManager] = None
BOT_CONFIG: Optional[Dict[str, Any]] = None


# =====================================================================
# I. メイン Bot ループ
# =====================================================================

def run_collector_bot():
    """Botのメイン処理ループを統括する"""

    # ★ V57 修正: BOT_IDのみを必須引数とする
    if len(sys.argv) < 2:
        print("Usage: python collector_bot_main.py <BOT_ID (integer)>")
        logger.critical("Usage: python collector_bot_main.py <BOT_ID (integer)>")
        sys.exit(1)

    global BOT_ID
    try:
        BOT_ID = int(sys.argv[1])
    except ValueError:
        print(f"Error: BOT_ID must be an integer. Received: {sys.argv[1]}")
        logger.critical(f"Error: BOT_ID must be an integer. Received: {sys.argv[1]}")
        sys.exit(1)

    # ★ V57 修正: config.IS_TEST_MODE の値を直接ログ出力
    if IS_TEST_MODE:
        logger.warning(f"!!! TEST MODE IS ACTIVE via config.py !!!")

    logger.info(f"Starting Collector Bot: {BOT_ID} (Test Mode: {IS_TEST_MODE})...")

    # 1. 接続と設定の初期化
    if not initialize_bot_resources():
        logger.error(f"MAIN: Initialization failed for BOT_ID={BOT_ID}. Exiting.")
        return

    logger.info(f"MAIN: Initialization successful. Starting main loop for Country: {TARGET_COUNTRY_CODE}")

    # ★ V57 修正: 収集件数をconfig.IS_TEST_MODEに基づき設定
    recommended_count = TEST_RECOMMENDED_VIDEOS_COUNT if IS_TEST_MODE else RECOMMENDED_VIDEOS_COUNT
    search_count = TEST_SEARCHED_VIDEOS_COUNT if IS_TEST_MODE else SEARCHED_VIDEOS_COUNT

    logger.info(f"MAIN: Collection Counts -> Recommended: {recommended_count}, Search: {search_count}")

    # ★★★ V55 修正: 「おすすめ」と「検索」を交互に実行するメインループ ★★★
    cycle_counter = 0
    while True:
        cycle_counter += 1
        logger.info(f"[{BOT_ID}] MAIN CYCLE {cycle_counter}: Starting full collection cycle.")

        try:
            # 1. オススメ収集 (機能①) を実行
            ########collect_via_recommended(recommended_count)

            # 2. オプティマイズ (検索) 収集 (機能②) を実行
            collect_via_search(search_count)

            logger.info(f"[{BOT_ID}] MAIN CYCLE {cycle_counter}: Cycle finished. Sleeping for 10 seconds.")
            time.sleep(10)  # 連続実行を防ぐための小休止

        except KeyboardInterrupt:
            logger.warning("MAIN: KeyboardInterrupt received. Shutting down.")
            break
        except Exception as e:
            logger.critical(f"FATAL ERROR IN MAIN LOOP ({BOT_ID}): {e}")
            logger.critical(traceback.format_exc())
            time.sleep(60)

            # Appium接続が切れた場合は再初期化を試みる
            try:
                if APPIUM_DRIVER_HELPER and APPIUM_DRIVER_HELPER.driver:
                    APPIUM_DRIVER_HELPER.driver.quit()
            except:
                pass

            logger.info("Attempting to re-initialize resources after fatal error.")
            if not initialize_bot_resources():
                logger.error("MAIN: Re-initialization failed. Waiting 5 minutes.")
                time.sleep(300)

    # ループ終了後のクリーンアップ
    logger.info("MAIN: Bot loop terminated. Cleaning up resources.")
    try:
        if APPIUM_DRIVER_HELPER and APPIUM_DRIVER_HELPER.driver:
            APPIUM_DRIVER_HELPER.driver.quit()
        if DB_MANAGER:
            DB_MANAGER.close()
    except Exception as e:
        logger.error(f"MAIN: Error during final cleanup: {e}")


# =====================================================================
# II. 接続と設定の初期化
# =====================================================================

def initialize_bot_resources() -> bool:
    """DB, Appium接続、Bot設定、閾値設定の読み込みを全て実行する"""
    global DB_MANAGER, APPIUM_DRIVER_HELPER, BOT_CONFIG, TARGET_COUNTRY_CODE, MIN_LIKES_THRESHOLD

    logger.debug(f"[{BOT_ID}] INITIALIZE: Connecting to Database...")
    try:
        DB_MANAGER = TikTokDBManager()
    except Exception as e:
        logger.error(f"[{BOT_ID}] INITIALIZE: DB Manager initialization failed: {e}")
        logger.error(traceback.format_exc())
        return False

    logger.debug(f"[{BOT_ID}] INITIALIZE: Fetching bot configuration...")
    BOT_CONFIG = DB_MANAGER.fetch_bot_configuration(BOT_ID)
    if not BOT_CONFIG:
        logger.error(
            f"[{BOT_ID}] INITIALIZE: Configuration not found for BOT_ID={BOT_ID}. Check bot_configurations table.")
        return False

    TARGET_COUNTRY_CODE = BOT_CONFIG.get('target_country')
    DEVICE_NAME = BOT_CONFIG.get('appium_device_name')
    UDID = BOT_CONFIG.get('appium_udid')

    # ★ V33 修正: DBからADBホスト/ポートを取得 (なければconfig.pyのデフォルト値)
    ADB_HOST = BOT_CONFIG.get('appium_host', APPIUM_HOST)
    ADB_PORT = BOT_CONFIG.get('appium_port', APPIUM_PORT)

    if not TARGET_COUNTRY_CODE or not DEVICE_NAME or not UDID:
        logger.error(f"[{BOT_ID}] INITIALIZE: Bot config is incomplete (Country, DeviceName, UDID required).")
        return False

    logger.debug(f"[{BOT_ID}] INITIALIZE: Initializing Appium driver (Device: {DEVICE_NAME}, UDID: {UDID})...")
    try:
        # ★ 修正: ADB連携のため、ホストとポートも渡す
        APPIUM_DRIVER_HELPER = TiktokAppiumHelper.initialize_driver(DEVICE_NAME, UDID, ADB_HOST, ADB_PORT)
    except AndroidConnectionError as e:
        # ★ V44 修正: 初期化失敗時はFalseを返し、run_collector_bot側で正常終了させる
        logger.error(f"[{BOT_ID}] INITIALIZE: Appium connection failed. Bot will exit. Error: {e}")
        return False
    except Exception as e:
        logger.error(f"[{BOT_ID}] INITIALIZE: Unknown error during Appium init: {e}")
        logger.error(traceback.format_exc())
        return False

    logger.debug(f"[{BOT_ID}] INITIALIZE: Rebooting TikTok App...")
    if not APPIUM_DRIVER_HELPER.reboot_tiktok_app():
        logger.warning(f"[{BOT_ID}] INITIALIZE: TikTok app reboot failed, continuing anyway.")

    logger.debug(f"[{BOT_ID}] INITIALIZE: Fetching Like Threshold for {TARGET_COUNTRY_CODE}...")
    threshold = DB_MANAGER.get_like_threshold(TARGET_COUNTRY_CODE)
    MIN_LIKES_THRESHOLD = threshold if threshold is not None else MIN_LIKES_DEFAULT

    logger.info(f"[{BOT_ID}] INITIALIZE: Initialization complete. Threshold={MIN_LIKES_THRESHOLD}")
    return True


# =====================================================================
# III. 収集戦略
# =====================================================================

def collect_via_search(count: int):
    """オプティマイズ: 検索フィードから収集"""
    logger.info(f"[{BOT_ID}] COLLECTION: Starting search collection cycle (Count: {count}).")

    if not DB_MANAGER or not APPIUM_DRIVER_HELPER:
        logger.error("COLLECTION: DB_MANAGER or APPIUM_DRIVER_HELPER not initialized. Skipping search.")
        return

    # 1. 最も古い未使用キーワードを取得し、タイムスタンプを更新 (設計通り)
    search_record = DB_MANAGER.get_oldest_search_word(TARGET_COUNTRY_CODE)
    if not search_record:
        logger.warning(
            f"[{BOT_ID}] COLLECTION: No active search words found for {TARGET_COUNTRY_CODE}. Skipping search.")
        return

    search_word = search_record['search_word']
    logger.info(f"[{BOT_ID}] COLLECTION: Using search word: '{search_word}' for optimization.")

    # 2. Appiumで検索を実行し、フィードを再教育
    try:
        APPIUM_DRIVER_HELPER.perform_search(search_word)

    except TimeoutException as e_timeout:
        logger.error(f"COLLECTION: perform_search failed (Timeout): {e_timeout}. Rebooting.")
        APPIUM_DRIVER_HELPER.reboot_tiktok_app()
        return

    except Exception as e:
        logger.warning(
            f"COLLECTION: perform_search failed (e.g., no videos found or ad-only): {e}. Skipping this search word.")
        # ★ V61 修正: 検索失敗時はホームに戻る
        try:
            APPIUM_DRIVER_HELPER._recover_from_search_menu_to_home()
        except Exception as recover_e:
            logger.error(f"COLLECTION: Recovery failed: {recover_e}. Rebooting.")
            APPIUM_DRIVER_HELPER.reboot_tiktok_app()
        return

    # perform_searchが成功した場合のみ、以下のループが実行される
    processed_count = 0
    for i in range(count):
        logger.debug(
            f"[{BOT_ID}] COLLECTION: Processing search video {i + 1}/{count} (Keyword: {search_word}).")

        try:
            # 3. 情報を収集し、DBに保存
            video_processed = process_single_video('SEARCHED', search_word)
            if video_processed:
                processed_count += 1

            # 4. 次の動画へスワイプ (★V61 修正: V50ロジック)
            logger.debug("COLLECTION: Swiping to next search video.")
            APPIUM_DRIVER_HELPER.swipe_up()

        except TimeoutException as e:
            logger.warning(f"[{BOT_ID}] TIMEOUT: Error processing search video (Timeout): {e}. Skipping video.")
            try:
                APPIUM_DRIVER_HELPER.swipe_up()
            except Exception as swipe_e:
                logger.error(f"[{BOT_ID}] CRITICAL: Swipe failed after Timeout. Rebooting App. Error: {swipe_e}")
                break
        except Exception as e:
            logger.error(f"[{BOT_ID}] CRITICAL: Error processing search video: {e}. Rebooting App.")
            logger.error(traceback.format_exc())
            APPIUM_DRIVER_HELPER.reboot_tiktok_app()
            break

    logger.info(f"[{BOT_ID}] COLLECTION: Finished search collection (Target: {count}, Processed: {processed_count}).")
    # ★ V61 修正: 検索終了後、ホームに戻る
    try:
        logger.debug("COLLECTION: Returning to home after search cycle.")
        APPIUM_DRIVER_HELPER._recover_from_search_menu_to_home()
    except Exception as e:
        logger.error(f"COLLECTION: Failed to return home after search: {e}. Rebooting.")
        APPIUM_DRIVER_HELPER.reboot_tiktok_app()


def collect_via_recommended(count: int):
    """[V61 修正] メイン: おすすめフィードから収集 (V50の動作ロジックに回帰)"""
    logger.info(f"[{BOT_ID}] COLLECTION: Starting recommended feed cycle (Count: {count}).")

    if not DB_MANAGER or not APPIUM_DRIVER_HELPER:
        logger.error("COLLECTION: DB_MANAGER or APPIUM_DRIVER_HELPER not initialized. Skipping recommended.")
        return

    # 1. ホーム画面への移動
    try:
        APPIUM_DRIVER_HELPER.collect_via_recommended()
    except TimeoutException as e:
        logger.error(f"[{BOT_ID}] CRITICAL: Timeout navigating to recommended feed: {e}. Rebooting App.")
        APPIUM_DRIVER_HELPER.reboot_tiktok_app()
        return
    except Exception as e:
        logger.error(f"[{BOT_ID}] CRITICAL: Error navigating to recommended feed: {e}. Rebooting App.")
        APPIUM_DRIVER_HELPER.reboot_tiktok_app()
        return

    # ★★★ V61 修正: 「予防的スワイプ」を削除 ★★★
    # V50 (動作していたバージョン) は1本目の動画から処理していた。

    processed_count = 0
    for i in range(count):
        logger.debug(f"[{BOT_ID}] COLLECTION: Processing recommended video {i + 1}/{count}")

        try:
            # 2. 情報を収集し、DBに保存 (1本目の動画から)
            video_processed = process_single_video('RECOMMENDED', None)
            if video_processed:
                processed_count += 1

            # 3. 次の動画へスワイプ (★V61 修正: V50ロジック)
            logger.debug("COLLECTION: Swiping to next recommended video.")
            APPIUM_DRIVER_HELPER.swipe_up()

        except TimeoutException as e:
            logger.warning(f"[{BOT_ID}] TIMEOUT: Error processing recommended video (Timeout): {e}. Skipping video.")
            try:
                APPIUM_DRIVER_HELPER.swipe_up()
            except Exception as swipe_e:
                logger.error(f"[{BOT_ID}] CRITICAL: Swipe failed after Timeout. Rebooting App. Error: {swipe_e}")
                break
        except Exception as e:
            logger.error(f"[{BOT_ID}] CRITICAL: Error processing recommended video: {e}. Rebooting App.")
            logger.error(traceback.format_exc())
            APPIUM_DRIVER_HELPER.reboot_tiktok_app()
            break

    logger.info(
        f"[{BOT_ID}] COLLECTION: Finished recommended collection (Target: {count}, Processed: {processed_count}).")


# =====================================================================
# IV. 単一動画の収集ロジック (エラーハンドリング含む)
# =====================================================================

def process_single_video(source: str, keyword: Optional[str]) -> bool:
    """
    [V58 修正] 単一の動画を処理し、DB挿入まで行う。
    (スキップログ強化とNoneチェック)
    """
    global APPIUM_DRIVER_HELPER, DB_MANAGER, TARGET_COUNTRY_CODE, MIN_LIKES_THRESHOLD, BOT_ID

    if not APPIUM_DRIVER_HELPER or not DB_MANAGER:
        logger.error("PROCESS: Helper or DB Manager not initialized!")
        raise Exception("Helper or DB Manager not initialized")

    video_id: Optional[str] = None
    status_from = 'INITIAL_COLLECTION'
    metadata: Dict[str, Any] = {}

    logger.debug(f"PROCESS: [START] Executing single video scrape (Source: {source}).")

    try:
        # ★ V38 新ロジック 1: URLとVideoIDの取得 (最優先)
        logger.debug("PROCESS: (Step 1) Extracting URL...")
        url = APPIUM_DRIVER_HELPER.get_current_video_url_full()

        if not url:
            logger.warning("PROCESS: (Step 1) URL/Video ID extraction failed. Skipping record (Return False).")
            return False

        video_id = APPIUM_DRIVER_HELPER._extract_video_id_from_url(url)
        if not video_id:
            logger.warning(
                f"PROCESS: (Step 1) Could not parse Video ID from URL: {url}. Skipping record (Return False).")
            return False

        metadata['url'] = url
        metadata['video_id'] = video_id
        status_from = f'COLLECTING (ID: {video_id})'

        # ★ V38 新ロジック 2: フィルタリング (いいね数取得)
        logger.debug("PROCESS: (Step 2) Checking likes threshold.")
        likes = APPIUM_DRIVER_HELPER.get_like_count()
        logger.debug(f"PROCESS: Read Likes={likes:,}. Threshold={MIN_LIKES_THRESHOLD:,}")

        if not APPIUM_DRIVER_HELPER.is_likes_above_threshold(likes, MIN_LIKES_THRESHOLD):
            # ★ V58 修正: スキップ理由を明確にログ出力
            log_message = f"Skipped: Likes ({likes}) below threshold ({MIN_LIKES_THRESHOLD})."
            logger.info(f"PROCESS: SKIPPED (ID: {video_id}). Reason: {log_message}")
            DB_MANAGER.isolate_record_due_to_error(video_id, log_message, status_from, str(BOT_ID))
            return False

        # ★ V38 新ロジック 3: メタデータの取得
        logger.debug("PROCESS: (Step 3) Extracting metadata from UI (Channel/Caption).")
        metadata_ui = APPIUM_DRIVER_HELPER.scrape_video_data(TARGET_COUNTRY_CODE)
        metadata['likes_count'] = likes
        metadata['found_source'] = source
        metadata['searched_by_keyword'] = keyword
        metadata['channel_name'] = metadata_ui.get('channel_name', 'N/A')
        metadata['caption_text'] = metadata_ui.get('caption_text', '')
        metadata['country_code'] = TARGET_COUNTRY_CODE

        # ★ V38 新ロジック 4: スクショ取得 (コメントアウト中)
        logger.debug("PROCESS: (Step 4) Acquiring screenshot binary via ADB.")
        # screenshot_binary_data = APPIUM_DRIVER_HELPER.get_screenshot_binary_via_adb()
        # if screenshot_binary_data is None:
        #     logger.warning("PROCESS: Failed to acquire screenshot binary data via ADB. Proceeding without image.")
        screenshot_binary_data = None

        # ★ V38 新ロジック 5: 静止画フィルタリング (最後)
        logger.debug("PROCESS: (Step 5) Checking if static image post.")
        if not APPIUM_DRIVER_HELPER.is_video_post():
            # ★ V58 修正: スキップ理由を明確にログ出力
            log_message = f"Skipped: Static Image Post detected."
            logger.info(f"PROCESS: SKIPPED (ID: {video_id}). Reason: {log_message}")
            DB_MANAGER.isolate_record_due_to_error(video_id, log_message, status_from, str(BOT_ID))
            return False

        # 6. DBへの挿入
        # ★ V58 修正: video_id が None でないことを最終確認
        if not video_id:
            logger.error(f"PROCESS: FATAL (Step 6) video_id became None before DB Insert. Metadata: {metadata}")
            return False

        logger.debug(f"PROCESS: (Step 6) Inserting record into DB for ID: {video_id} (Source: {source})")
        insert_result = DB_MANAGER.insert_new_video_record(metadata, screenshot_binary_data)

        if insert_result == 'DUPLICATE':
            # ★ V58 修正: スキップ理由を明確にログ出力
            logger.info(f"PROCESS: SKIPPED (ID {video_id} is DUPLICATE).")
            return False
        elif insert_result.startswith('ERROR_'):
            logger.error(f"PROCESS: DB Insert failed: {insert_result}")
            DB_MANAGER.isolate_record_due_to_error(video_id, insert_result, status_from, str(BOT_ID))
            return False

        # 7. 成功履歴を記録 (V42: ログメッセージ修正)
        log_message = f"Successfully collected. Likes={likes:,}"
        DB_MANAGER.log_history(video_id, status_from, WAITING_SCREENSHOT_CHECK, log_message, str(BOT_ID))
        logger.info(f"SUCCESS: Collected new video. DB_ID: {video_id} (Likes: {likes:,})")
        return True

    except TimeoutException as e:
        # 要素探索のタイムアウト (リカバリ可能)
        logger.warning(f"PROCESS: TimeoutException during video processing: {e}")
        if video_id:
            DB_MANAGER.isolate_record_due_to_error(video_id, str(e), status_from, str(BOT_ID))
        raise e

    except Exception as e:
        # Appiumクラッシュ、ハングアップなど、予期せぬ致命的エラー
        logger.error(f"PROCESS: FATAL error during video processing: {e}")
        logger.error(traceback.format_exc())
        if video_id:
            DB_MANAGER.isolate_record_due_to_error(video_id, str(e), status_from, str(BOT_ID))
        raise e


# =====================================================================
# V. メインエントリポイント
# =====================================================================

if __name__ == '__main__':
    # --- ロガーの初期設定 (一度だけ実行) ---
    setup_logging_handlers()

    logger.info(f"Config LOG_LEVEL is ({LOG_LEVEL}). Logger forced to DEBUG by app_logger.py.")

    logger.info("==================================================")
    logger.info("Application starting...")
    logger.info("==================================================")

    run_collector_bot()