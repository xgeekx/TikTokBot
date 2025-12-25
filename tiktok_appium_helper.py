# =====================================================================
# tiktok_appium_helper.py (V94 - フォールバック・セレクタ戦略)
# =====================================================================

from appium import webdriver
from appium.options.common import AppiumOptions
from appium.webdriver.common.appiumby import AppiumBy
from selenium.common.exceptions import WebDriverException, NoSuchElementException, TimeoutException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from config import APPIUM_URL, APPIUM_CAPABILITIES_BASE, TIKTOK_PACKAGE_NAME
from config import APPIUM_HOST, APPIUM_PORT
from typing import Dict, Any, Optional, Tuple, List  # ★ Listを追加
import time
import re
import traceback
import subprocess
import random
from app_logger import logger
from typing import Any
import base64

# ★ V94 修正: 新しい element_ids ファイルからすべてのセレクタをインポート
import element_ids as ids


# --- 例外クラス ---
class AndroidConnectionError(Exception):
    def __init__(self, message: str, original_exception: Optional[Exception] = None):
        self.message = message
        self.original_exception = original_exception
        logger.critical(f"CRITICAL [AndroidConnectionError]: {message}")
        super().__init__(self.message)


# --- ヘルパークラス ---
class TiktokAppiumHelper:

    def __init__(self, driver: webdriver.Remote, tiktok_package_name: str, adb_host: str, adb_port: int):
        self.driver = driver
        self.tiktok_package_name = tiktok_package_name
        self.adb_host_port_str = f"-H {adb_host} -P {adb_port}"
        # 瞬時判定用
        self.wait_fast = WebDriverWait(driver, 0.5, poll_frequency=0.1)
        # 中速ポーリング (汎用)
        self.wait_medium = WebDriverWait(driver, 15, poll_frequency=0.5)

        try:
            self.driver.update_settings({"waitForIdleTimeout": 0})
            logger.info("STATUS: Applied critical setting: waitForIdleTimeout=0.")
        except Exception as e:
            logger.warning(f"WARNING: Failed to set waitForIdleTimeout: {e}")

    # -----------------------------------------------------------------
    # ★ V94 修正: コア・セレクタ・ロジック (フォールバック実装)
    # -----------------------------------------------------------------

    def _find_element_with_retry(self, by: str, value: str, max_retries: int = 2,
                                 wait_time_seconds: float = 2.0) -> Any:
        """
        [V94 内部関数]
        単一のセレクタ戦略で、指定された回数リトライする。
        (V91のロジックを継承し、リトライ回数を減らす)
        """
        last_exception = None
        logger.debug(
            f"FIND: Attempting (By: {by}, Value: {value}) with {max_retries} retries (Wait: {wait_time_seconds}s per retry).")

        for i in range(1, max_retries + 1):
            try:
                element = WebDriverWait(self.driver, wait_time_seconds, poll_frequency=0.5).until(
                    EC.presence_of_element_located((by, value))
                )
                logger.debug(f"FIND: Successfully found element {value}.")
                return element
            except TimeoutException as e:
                last_exception = e
                if i < max_retries:
                    logger.debug(
                        f"RETRY {i}/{max_retries}: Timeout finding {value}. Forcing DOM update.")
                    try:
                        _ = self.driver.page_source
                        logger.debug(f"RETRY {i}/{max_retries}: DOM refreshed successfully.")
                    except Exception as refresh_e:
                        logger.warning(f"RETRY {i}/{max_retries}: DOM refresh failed: {refresh_e}")
                continue
            except Exception as e:
                logger.error(f"FATAL Error during element finding ({value}): {e}")
                last_exception = e
                break

        # ★ V94: 失敗ログは呼び出し元の find_element_with_fallbacks で出す
        raise TimeoutException(f"Element {value} not found after {max_retries} retries.") from last_exception

    def find_element_with_fallbacks(self, selectors_list: List[Tuple[str, str]],
                                    max_retries_per_selector: int = 2) -> Any:
        """
        [V94 新規]
        セレクタの優先順位リストを受け取り、見つかるまで順に試行する。
        """
        last_exception = None
        if not selectors_list:
            logger.error("FAILURE: No selectors provided to find_element_with_fallbacks.")
            raise ValueError("Selector list cannot be empty.")

        # 1. セレクタリストをループ (優先順位順)
        for (by, value) in selectors_list:
            try:
                # 2. 各セレクタでリトライ (リトライ回数は少なく)
                element = self._find_element_with_retry(by, value, max_retries=max_retries_per_selector)

                # ★ 成功したら即時リターン
                logger.info(f"FIND: SUCCESS using selector (By: {by}, Value: {value})")
                return element

            except TimeoutException as e:
                last_exception = e
                logger.warning(f"FIND: FAILED selector (By: {by}, Value: {value}). Trying next fallback.")
                continue  # 次のセレクタへ
            except Exception as e:
                # セレクタが不正(XPath構文エラーなど)か、Appiumがクラッシュした
                logger.error(f"FIND: CRITICAL error on selector (By: {by}, Value: {value}): {e}")
                last_exception = e
                continue  # 次のセレクタへ

        # すべてのセレクタが失敗した場合
        logger.error(f"FAILURE: All {len(selectors_list)} fallback selectors failed.")
        raise TimeoutException(
            f"Element not found after trying all {len(selectors_list)} fallbacks.") from last_exception

    # -----------------------------------------------------------------
    # (クラス初期化・システム関数 - 変更なし)
    # -----------------------------------------------------------------

    @classmethod
    def initialize_driver(cls, device_name: str, udid: str, adb_host: str, adb_port: int):
        logger.info(f"ACTION: [START] Initializing Appium for Device: {device_name} ({udid}) at {adb_host}:{adb_port}")
        caps = APPIUM_CAPABILITIES_BASE.copy()
        caps['appium:deviceName'] = device_name
        caps['appium:udid'] = udid
        options = AppiumOptions()
        options.load_capabilities(caps)
        try:
            driver = webdriver.Remote(APPIUM_URL, options=options)
            logger.info(f"STATUS: Successfully connected to Appium at {APPIUM_URL}")
            return cls(driver, TIKTOK_PACKAGE_NAME, adb_host, adb_port)
        except WebDriverException as e:
            error_msg = f"ERROR: Failed to connect Appium driver (WebDriverException). Check Appium Server and device connection. UDID: {udid}. Error: {e}"
            logger.error(error_msg)
            logger.error(traceback.format_exc())
            raise AndroidConnectionError(error_msg, original_exception=e)
        except Exception as e:
            error_msg = f"ERROR: Unknown error during Appium driver initialization. Error: {e}"
            logger.error(error_msg)
            logger.error(traceback.format_exc())
            raise AndroidConnectionError(error_msg, original_exception=e)

    def reboot_tiktok_app(self):
        logger.debug("ACTION: Terminating and reactivating TikTok app.")
        try:
            self.driver.terminate_app(self.tiktok_package_name)
            time.sleep(1)
            self.driver.activate_app(self.tiktok_package_name)
            logger.info("STATUS: TikTok app activated. Waiting 7 seconds for stabilization (ads/popups)...")
            time.sleep(7)
            logger.info("STATUS: TikTok app restarted cleanly.")
            return True
        except Exception as e:
            logger.warning(f"Warning: Error during app reboot: {e}")
            return False

    def swipe_up(self, duration: int = 400):
        logger.debug("ACTION: Executing swipe up to next video.")
        try:
            size = self.driver.get_window_size()
            width = size['width']
            height = size['height']
            start_x = width // 2
            start_y = int(height * 0.75)
            end_y = int(height * 0.25)
            self.driver.swipe(start_x, start_y, start_x, end_y, duration)
            time.sleep(2.5)
            logger.debug("STATUS: Swipe completed.")
            return True
        except Exception as e:
            logger.error(f"Error during swipe_up: {e}")
            raise e

    # -----------------------------------------------------------------
    # ★ V94 修正: UI操作関数 (find_element_with_fallbacks を使用)
    # -----------------------------------------------------------------

    def collect_via_recommended(self):
        """「おすすめ」フィードに戻る"""
        logger.info("ACTION: Ensuring recommended feed is active.")

        # ★ V94 修正: find_element_with_fallbacks を使用
        home_button = self.find_element_with_fallbacks(ids.HOME_ICON_SELECTORS)
        try:
            if home_button.get_attribute("selected") != "true":
                logger.debug("NAV: Home button not selected. Clicking Home.")
                home_button.click()
                time.sleep(1.0)
            logger.info("STATUS: Successfully navigated to Recommended feed.")

        except TimeoutException:
            logger.warning("NAV: Home button not found (Timeout). Assuming already on feed or continuing.")
        except Exception as e:
            logger.error(f"FATAL Error during home navigation: {e}")
            raise e

    def is_video_post(self) -> bool:
        """ [V94 修正] 静止画（写真）投稿かどうかを瞬時に判定する """
        try:
            # ★ V94 修正: find_element_with_fallbacks を瞬時判定で使う
            # (wait_fast (0.5s) を _find_element_with_retry に渡す)
            selector = ids.PHOTO_MODE_INDICATOR_SELECTORS[0]  # 最初の戦略のみ試行
            self._find_element_with_retry(
                selector[0],
                selector[1],
                max_retries=1,
                wait_time_seconds=0.5
            )

            logger.debug(f"FILTER: Photo Mode element ({selector[1]}) found. (Type=Static Image)")
            return False
        except TimeoutException:
            logger.debug(f"FILTER: Photo Mode element not found. (Type=Video)")
            return True
        except Exception as e:
            logger.warning(f"FILTER: Error checking Photo Mode element: {e}. Assuming Video.")
            return True

    def _convert_count_to_int(self, count_str: str) -> int:
        """K/M/万表記を整数に変換する"""
        if not count_str: return 0
        count_str = str(count_str).upper().replace(',', '')
        if '万' in count_str:
            count_str = count_str.replace('万', '')
            try:
                return int(float(count_str) * 10000)
            except ValueError:
                return 0
        if 'M' in count_str:
            try:
                return int(float(count_str.replace('M', '')) * 1_000_000)
            except ValueError:
                return 0
        elif 'K' in count_str:
            try:
                return int(float(count_str.replace('K', '')) * 1_000)
            except ValueError:
                return 0
        try:
            return int(count_str)
        except ValueError:
            return 0

    def is_likes_above_threshold(self, current_likes: int, threshold: int) -> bool:
        return current_likes >= threshold

    def get_current_video_url_full(self) -> Optional[str]:
        """ [V94 修正] シェアメニューを開き、クリップボード経由でURLを取得する """
        logger.info(
            "ACTION: https://www.merriam-webster.com/dictionary/copy Attempting to copy video URL via Share menu.")
        try:
            try:
                self.driver.set_clipboard_text('')
                logger.debug("CLIPBOARD: Cleared clipboard before copy attempt.")
            except Exception as e:
                logger.warning(f"CLIPBOARD: Could not clear clipboard: {e}")

            # ★ V94 修正: find_element_with_fallbacks を使用
            share_button_parent = self.find_element_with_fallbacks(ids.SHARE_BUTTON_SELECTORS)
            share_button_parent.click()
            logger.debug(f"NAV: Share button clicked.")

            # ★ V94 修正: find_element_with_fallbacks を使用
            copy_link_button = self.find_element_with_fallbacks(ids.COPY_LINK_BUTTON_SELECTORS)
            copy_link_button.click()

            logger.debug("NAV: 'Copy Link' button clicked.")
            time.sleep(1.5)
            url = self.driver.get_clipboard_text()

            if not url or not url.startswith('http'):
                logger.warning(f"CLIPBOARD: Failed to get valid URL. Found: '{url}'")
                url = None
            else:
                logger.info(f"STATUS: Successfully retrieved URL: {url[:30]}...")

            if url:
                logger.debug("NAV: Copy successful. Assuming menu closed automatically.")
                return url

            logger.warning(f"NAV: URL not found in clipboard. Closing menu via driver.back().")
            try:
                self.driver.back()
                logger.debug("NAV: Share menu closed via driver.back().")
                time.sleep(0.5)
            except Exception as e_back:
                logger.error(f"NAV: driver.back() failed: {e_back}")
            return None

        except TimeoutException as e:
            logger.warning(f"NAV: Timeout while trying to find Share/Copy button.")
            try:
                logger.debug(f"NAV: Closing potentially open share menu via driver.back().")
                self.driver.back()
            except Exception as e_back:
                logger.error(f"NAV: driver.back() failed during Timeout recovery: {e_back}")
            raise Exception("Failed to complete share menu navigation (Timeout).") from e
        except Exception as e:
            logger.error(f"FATAL Error during URL copy: {e}")
            logger.warning(traceback.format_exc())
            raise e

    def _extract_video_id_from_url(self, url: str) -> Optional[str]:
        if not url: return None
        match_short = re.search(r'vt\.tiktok\.com/([a-zA-Z0-9]+)', url)
        if match_short: return match_short.group(1)
        match_long = re.search(r'/video/(\d+)', url)
        if match_long: return match_long.group(1)
        logger.warning(f"ID Extract: Could not extract ID from URL: {url}")
        return None

    def get_full_caption_text(self) -> str:
        """[V94 修正] 投稿文章を取得。「もっと見る」があればタップする"""
        try:
            try:
                # ★ V94 修正: find_element_with_fallbacks を使用 (リトライ1回)
                more_button = self.find_element_with_fallbacks(ids.CAPTION_MORE_BUTTON_SELECTORS,
                                                               max_retries_per_selector=1)
                more_button.click()
                logger.debug("CAPTION: 'More' button clicked.")
                time.sleep(0.5)
            except TimeoutException:
                pass  # 「もっと見る」がないだけ

            # ★ V94 修正: find_element_with_fallbacks を使用
            caption_element = self.find_element_with_fallbacks(ids.CAPTION_TEXT_SELECTORS)
            caption = caption_element.text.strip()

            if caption and re.fullmatch(r'[\d,.]+[KM万]?', caption):
                logger.debug(f"CAPTION: Found text ({caption}) but it looks like a number. Skipping.")
                return ""
            logger.debug(f"CAPTION: Extracted text: {caption[:30]}...")
            return caption
        except TimeoutException:
            logger.debug(f"CAPTION: Caption element not found (Timeout).")
            return ""
        except Exception as e:
            logger.warning(f"CAPTION: Error getting caption: {e}")
            return ""

    def get_like_count(self) -> int:
        """[V94 修正] いいね数を取得し、整数に変換して返す"""
        try:
            # ★ V94 修正: find_element_with_fallbacks を使用
            likes_button = self.find_element_with_fallbacks(ids.LIKES_BUTTON_SELECTORS)
            likes_desc = likes_button.get_attribute("content-desc")
            match = re.search(r'([\d,.]+[KM万]?)件', likes_desc)
            if match:
                likes_text = match.group(1)
                logger.debug(f"LIKES: Extracted from content-desc: {likes_text}")
                return self._convert_count_to_int(likes_text)
            else:
                # ★ V94 修正: find_element_with_fallbacks を使用
                logger.debug(f"LIKES: content-desc match failed ('{likes_desc}'), falling back to Text ID.")
                likes_element = self.find_element_with_fallbacks(ids.LIKES_COUNT_TEXT_SELECTORS)
                likes_text = likes_element.text
                logger.debug(f"LIKES: Extracted from Text ID: {likes_text}")
                return self._convert_count_to_int(likes_text)
        except TimeoutException:
            logger.error(f"FAILURE: Likes Count element not found after all fallbacks.")
            return 0
        except Exception as e:
            logger.warning(f"HELPER: ERROR during get_like_count: {e}")
            return 0

    def scrape_video_data(self, country_code: str) -> Dict[str, Any]:
        """[V94 修正] 動画のメタデータを抽出し、辞書として返す"""
        logger.debug("ACTION: Starting video metadata scrape.")
        data = {'channel_name': 'N/A', 'caption_text': self.get_full_caption_text(), 'country_code': country_code}
        try:
            # ★ V94 修正: find_element_with_fallbacks を使用
            channel_element = self.find_element_with_fallbacks(ids.CHANNEL_NAME_SELECTORS)
            channel_name = channel_element.text.strip()
            if channel_name:
                data['channel_name'] = channel_name
                logger.debug(f"SUCCESS: Channel Name found: {data['channel_name']}")
            else:
                logger.debug(f"SKIP: Channel Name element found but text is empty.")
        except TimeoutException:
            logger.debug(f"SKIP: Channel Name element not found (Timeout).")
        except Exception as e:
            logger.warning(f"Error during channel name scrape: {e}")
        logger.debug(f"STATUS: Scrape completed. Channel={data['channel_name']}")
        return data

    def get_screenshot_binary_via_adb(self) -> Optional[bytes]:
        """ [V33] ADBコマンドを直接呼び出して高速にスクショを取得する """
        logger.debug("ACTION: Taking screenshot via ADB command.")
        cmd_screencap = f"adb {self.adb_host_port_str} shell screencap -p /sdcard/tiktok_bot_ss.png"
        try:
            result_cap = subprocess.run(cmd_screencap, shell=True, capture_output=True, text=True, timeout=10)
            if result_cap.returncode != 0:
                logger.error(
                    f"ADB ERROR: Screencap failed (Code: {result_cap.returncode}). Output: {result_cap.stderr.strip()}")
                return None
            cmd_pull = f"adb {self.adb_host_port_str} pull /sdcard/tiktok_bot_ss.png /dev/stdout"
            result_pull = subprocess.run(cmd_pull, shell=True, capture_output=True, timeout=10)
            if result_pull.returncode != 0:
                logger.error(
                    f"ADB ERROR: Pull failed (Code: {result_pull.returncode}). Output: {result_pull.stderr.decode('utf-8', errors='ignore').strip()}")
                return None
            cmd_rm = f"adb {self.adb_host_port_str} shell rm /sdcard/tiktok_bot_ss.png"
            subprocess.run(cmd_rm, shell=True, capture_output=True, timeout=5)
            logger.debug(f"STATUS: Screenshot acquired via ADB (Size: {len(result_pull.stdout)} bytes).")
            return result_pull.stdout
        except subprocess.TimeoutExpired:
            logger.error("ADB ERROR: ADB command timed out.")
            return None
        except Exception as e:
            logger.error(f"ADB ERROR: Unknown error during ADB screenshot: {e}")
            return None

    def perform_search(self, search_word: str):
        """
        [V94 修正] 検索を実行する (セレクタをidsからインポート)
        """
        logger.info(f"ACTION: [START] Performing full search cycle for: {search_word}")

        try:
            # --- 1. ホーム画面から検索アイコンをタップ ---
            logger.debug(f"SEARCH: (Step 1) Tapping search icon on home screen.")
            search_icon = self.find_element_with_fallbacks(ids.HOME_SEARCH_ICON_SELECTORS, max_retries_per_selector=5)
            search_icon.click()
            logger.debug("SEARCH: (Step 1) Search icon tapped.")
            time.sleep(random.uniform(1.5, 2.5))

            # --- 2. 検索キーワードの入力と実行 ---
            logger.debug(f"SEARCH: (Step 2) Entering text '{search_word}' and submitting.")
            input_box = self.find_element_with_fallbacks(ids.SEARCH_INPUT_BOX_SELECTORS)
            input_box.send_keys(search_word)
            logger.debug("SEARCH: (Step 2) Text entered.")
            time.sleep(random.uniform(0.5, 1.0))
            submit_button = self.find_element_with_fallbacks(ids.SEARCH_SUBMIT_BUTTON_SELECTORS)
            submit_button.click()
            logger.debug("SEARCH: (Step 2) Search submitted.")
            time.sleep(random.uniform(4.0, 6.0))  # 検索結果のロード待ち

            # --- 3. フィルターアイコンをタップ ---
            logger.debug("SEARCH: (Step 3) Tapping filter icon.")
            filter_icon = self.find_element_with_fallbacks(ids.SEARCH_FILTER_ICON_SELECTORS)
            filter_icon.click()
            logger.debug("SEARCH: (Step 3) Filter icon tapped.")
            time.sleep(random.uniform(1.5, 2.5))

            # --- 3.5: 中間メニューの「フィルター」をタップ ---
            logger.debug("SEARCH: (Step 3.5) Tapping intermediate 'フィルター' button.")
            try:
                self.find_element_with_fallbacks(ids.FILTER_INTERMEDIATE_BUTTON_SELECTORS,
                                                 max_retries_per_selector=2).click()
                logger.debug("SEARCH: (Step 3.5) Intermediate 'フィルター' button tapped.")
                time.sleep(random.uniform(1.5, 2.5))
            except TimeoutException as e:
                logger.error("SEARCH: (Step 3.5) FAILED to find intermediate 'フィルター' button.")
                raise e

            # --- 4. フィルターの適用 ---
            logger.debug("SEARCH: (Step 4) Applying final filters (Sort by Date, Unwatched, Last 6 Months)...")
            self.find_element_with_fallbacks(ids.FILTER_SORT_DATE_SELECTORS, max_retries_per_selector=2).click()
            logger.debug("SEARCH: (Step 4) Filter applied: Sort by Date.")
            time.sleep(random.uniform(0.8, 1.5))
            try:
                # (オプション)
                self.find_element_with_fallbacks(ids.FILTER_UNWATCHED_SELECTORS, max_retries_per_selector=1).click()
                logger.debug("SEARCH: (Step 4) Filter applied: Unwatched.")
                time.sleep(random.uniform(0.8, 1.5))
            except TimeoutException:
                logger.warning("SEARCH: (Step 4) 'Unwatched' button not found (fast check). Skipping this filter.")
            logger.debug("SEARCH: (Step 4.5) Scrolling filter panel down...")
            try:
                size = self.driver.get_window_size()
                start_x, start_y, end_y = size['width'] // 2, int(size['height'] * 0.80), int(size['height'] * 0.30)
                self.driver.swipe(start_x, start_y, start_x, end_y, 600)
                logger.debug("SEARCH: (Step 4.5) Scroll swipe executed.")
                time.sleep(random.uniform(1.0, 1.5))
            except Exception as scroll_e:
                logger.warning(f"SEARCH: (Step 4.5) Failed to execute scroll swipe: {scroll_e}")
            self.find_element_with_fallbacks(ids.FILTER_6_MONTHS_SELECTORS, max_retries_per_selector=2).click()
            logger.debug("SEARCH: (Step 4) Filter applied: Last 6 Months.")
            time.sleep(random.uniform(0.8, 1.2))
            self.find_element_with_fallbacks(ids.FILTER_APPLY_BUTTON_SELECTORS, max_retries_per_selector=2).click()
            logger.info("SEARCH: (Step 4) Apply button tapped.")
            time.sleep(random.uniform(4.0, 6.0))

            # --- 5. 動画タブを明示的にクリックして動画一覧に切り替える ---
            try:
                video_tab = None
                tab_elements = self.driver.find_elements(AppiumBy.XPATH, '//android.widget.FrameLayout[@content-desc="動画"]')
                for el in tab_elements:
                    if el.get_attribute("selected") == "true":
                        video_tab = el
                        break
                if not video_tab and tab_elements:
                    video_tab = tab_elements[0]
                    video_tab.click()
                    logger.debug("SEARCH: (Step 5) '動画'タブをクリックしました。")
                    time.sleep(1.0)
                else:
                    logger.debug("SEARCH: (Step 5) '動画'タブは既に選択済み。")
            except Exception as e:
                logger.warning(f"SEARCH: (Step 5) 動画タブのクリックに失敗: {e}")

            # --- 検索結果から動画を開く処理を位置情報タップで実施（最新版） ---
            try:
                clicked = self.click_first_video_result_by_location()
                if not clicked:
                    self._recover_from_search_menu_to_home()
                    raise Exception("No video items found or could not click video in search results.")

                time.sleep(2.0)  # 動画画面のロード待ち

                # 動画プレイヤーが開くまでリトライ
                max_wait = 8
                for i in range(max_wait):
                    try:
                        WebDriverWait(self.driver, 2, poll_frequency=0.5).until(
                            EC.presence_of_element_located(ids.SHARE_BUTTON_SELECTORS[0])
                        )
                        break
                    except TimeoutException:
                        self.click_first_video_result_by_location()
                        time.sleep(1.0)
                else:
                    self._recover_from_search_menu_to_home()
                    raise Exception("Could not open video player after clicking video item.")

            except Exception as e:
                self._recover_from_search_menu_to_home()
                raise Exception("Could not find or open the target video item in search results.") from e

            logger.info(f"ACTION: [SUCCESS] Search cycle complete. Handing over to main loop for scraping.")
            return True

        except TimeoutException as e:
            logger.error(f"FATAL (Timeout) during perform_search: {e}")
            logger.error(traceback.format_exc())
            self._recover_from_search_menu_to_home()
            raise e
        except Exception as e:
            logger.error(f"FATAL (Unknown) during perform_search: {e}")
            logger.error(traceback.format_exc())
            self._recover_from_search_menu_to_home()
            raise e

    def click_first_video_result(self):
        """
        検索結果から最初の動画を開くための構造ベースの安定した処理
        """
        video_xpath = '//android.widget.FrameLayout[.//android.widget.Button[contains(@resource-id, "desc")] and .//android.widget.Button[contains(@resource-id, "lhs")]]'
        videos = self.driver.find_elements(AppiumBy.XPATH, video_xpath)
        if videos:
            target_video = videos[0]
            try:
                target_video.click()
            except Exception:
                # location = target_video.location
                # size = target_video.size
                # x = location['x'] + size['width'] / 2
                # y = location['y'] + size['height'] / 2
                # self.driver.tap([(x, y)])
                pass
            return True
        return False

    def click_first_video_result_by_location(self):
        """
        動画タブ選択後、中身が『描画されるまで』待ってから物理タップする。
        """
        try:
            logger.info("ACTION: Force refreshing DOM and waiting for 'desc'...")

            # 1. 検索対象を『GridView直下のクリック可能なFrameLayout』に絞る
            # ID検索（desc）が重い・見つからない問題を、クラス名検索で回避
            video_frame_xpath = "//android.widget.GridView/android.widget.FrameLayout[@clickable='true']"

            logger.info("ACTION: Scanning for video grid items (Fast Poll)...")

            # 2. 最大5秒待つが、0.5秒ごとにチェックし、見つかった瞬間に次へ進む
            wait = WebDriverWait(self.driver, 5, poll_frequency=0.5)
            first_video = wait.until(EC.presence_of_element_located((AppiumBy.XPATH, video_frame_xpath)))

            # 3. 見つかった要素から直接座標を取得（計算の手間を省く）
            rect = first_video.rect
            center_x = rect['x'] + (rect['width'] // 2)
            center_y = rect['y'] + (rect['height'] // 2)

            logger.info(f"SUCCESS: Video detected. Tapping ({center_x}, {center_y}) immediately.")

            # 4. 座標を物理タップ
            self.driver.tap([(center_x, center_y)])
            return True

        except Exception as e:
            logger.warning(f"SEARCH: Failed to locate or tap video item: {e}")
            return False

    def _recover_from_search_menu_to_home(self):
        """
        [V94 修正] 検索結果画面、または検索入力画面から、ホーム画面まで安全に戻るためのリカバリ処理
        """
        try:
            logger.debug("SEARCH: (RECOVERY) Attempting to return to home via BACK button.")
            # ★ V94 修正: find_element_with_fallbacks を使用
            BACK_BUTTON_SELECTORS = ids.SEARCH_BACK_BUTTON_SELECTORS

            try:
                self.find_element_with_fallbacks(BACK_BUTTON_SELECTORS, max_retries_per_selector=2).click()
                logger.debug("SEARCH: (RECOVERY) Back 1: Moved from Search Result to Search Input.")
                time.sleep(random.uniform(1.0, 1.5))
            except TimeoutException:
                logger.debug("SEARCH: (RECOVERY) Back 1 failed/already on search input screen.")
                pass
            try:
                self.find_element_with_fallbacks(BACK_BUTTON_SELECTORS, max_retries_per_selector=2).click()
                logger.debug("SEARCH: (RECOVERY) Back 2: Moved from Search Input to Home.")
                time.sleep(random.uniform(1.5, 2.5))
            except TimeoutException:
                logger.warning("SEARCH: (RECOVERY) Back 2 failed. App state unknown.")
                raise Exception("Failed to reliably return to the home screen.")
            logger.info("SEARCH: (RECOVERY) Successfully returned to home.")
        except Exception as back_e:
            logger.error(f"SEARCH: (RECOVERY) FATAL error during recovery: {back_e}")
            raise Exception(f"Failed to execute clean search recovery: {back_e}")
