# =====================================================================
# element_ids.py (V95 - 相対パス戦略 + NameError修正)
#
# 1. V94のNameError (Tuple not defined) を修正
# 2. ユーザーの提案に基づき、ランダムなIDへの依存を減らし、
#    構造的XPath (相対パス) を使ったセレクタを導入
# =====================================================================
from appium.webdriver.common.appiumby import AppiumBy
from typing import Tuple, List  # ★ V95: NameError修正のためインポート

# --- 共通パッケージ名 ---
TIKTOK_PACKAGE_NAME = 'com.ss.android.ugc.trill'


# 内部ヘルパー (IDをフルパスに変換)
def ID(id_name: str) -> Tuple[str, str]:
    return (AppiumBy.ID, f'{TIKTOK_PACKAGE_NAME}:id/{id_name}')


# =====================================================================
# I. ホーム画面 (おすすめフィード)
# =====================================================================

HOME_ICON_SELECTORS = [
    (AppiumBy.XPATH, '//android.widget.FrameLayout[@content-desc="ホーム"]')
]

HOME_SEARCH_ICON_SELECTORS = [
    (AppiumBy.XPATH, '//android.widget.ImageView[@content-desc="検索"]'),
    ID('ia7')  # フォールバック
]

# =====================================================================
# II. 動画フィード画面 (おすすめ・検索共通)
# =====================================================================

# --- シェアボタン (URL取得用) ---
SHARE_BUTTON_SELECTORS = [
    # 戦略1: content-desc (V93 DOM分析) - 最も安定的
    (AppiumBy.XPATH, '//android.widget.Button[starts-with(@content-desc, "動画をシェアします")]'),
    # 戦略2: 旧ID (V91) (ロールバック対策)
    ID('sao')
]

# --- リンクをコピー ボタン (シェアメニュー内) ---
COPY_LINK_BUTTON_SELECTORS = [
    (AppiumBy.XPATH, '//*[@text="リンクをコピー"]')
]

# --- いいねボタン (メインのコンテナ) ---
LIKES_BUTTON_SELECTORS = [
    # 戦略1: content-desc (V93 DOM分析) - 最も安定的
    (AppiumBy.XPATH, '//android.widget.Button[starts-with(@content-desc, "動画に「いいね」をします")]'),
    # 戦略2: 旧ID (V91) (ロールバック対策)
    ID('ew7')
]

# --- いいね「数」 (テキスト) ---
LIKES_COUNT_TEXT_SELECTORS = [
    # ★ 戦略1: 構造的XPath (相対パス)
    # 「いいねボタン(content-desc)」の「中にある」Button要素を探す
    (AppiumBy.XPATH,
     '//android.widget.Button[starts-with(@content-desc, "動画に「いいね」をします")]/android.widget.RelativeLayout/android.widget.Button'),

    # 戦略2: 旧DOM(V91)のID (フォールバック)
    ID('evz')
]

# --- チャンネル名 (@username) ---
CHANNEL_NAME_SELECTORS = [
    # 戦略1: ID (V93 DOM分析: 変更なし)
    ID('title'),
    # ★ 戦略2: 構造的XPath (相対パス)
    # 「キャプション(id/desc)」の「前にある」LinearLayout(id/jd1)の「中にある」Button要素
    (AppiumBy.XPATH,
     '//android.widget.FrameLayout[@resource-id="com.ss.android.ugc.trill:id/b5z"]//android.widget.Button[@resource-id="com.ss.android.ugc.trill:id/title"]')
]

# --- キャプション (投稿文章) ---
CAPTION_TEXT_SELECTORS = [
    # 戦略1: ID (V93 DOM分析: 変更なし)
    ID('desc'),
    # ★ 戦略2: 構造的XPath (相対パス)
    # 「チャンネル名(id/title)」の「次にある」LinearLayout(id/du3)の「中にある」TuxTextLayoutView要素
    (AppiumBy.XPATH,
     '//android.widget.FrameLayout[@resource-id="com.ss.android.ugc.trill:id/b5z"]//com.bytedance.tux.input.TuxTextLayoutView[@resource-id="com.ss.android.ugc.trill:id/desc"]')

]

# --- 「もっと見る」ボタン (キャプション) ---
CAPTION_MORE_BUTTON_SELECTORS = [
    ID('tib'),
    (AppiumBy.XPATH, '//*[@text="もっと見る"]')
]

# --- 静止画 (Photo) 判定 ---
PHOTO_MODE_INDICATOR_SELECTORS = [
    ID('wex')
]

# =====================================================================
# III. 検索フロー
# =====================================================================

# --- 検索入力画面 ---
SEARCH_INPUT_BOX_SELECTORS = [
    ID('g6q'),
    # 追加: content-desc="検索"の直後のEditText
    (AppiumBy.XPATH, '//android.widget.ImageView[@content-desc="検索"]/following-sibling::android.widget.EditText'),
    # 追加: 画面上の最初のEditText
    (AppiumBy.XPATH, '(//android.widget.EditText)[1]'),
    # 追加: text属性が空のEditText
    (AppiumBy.XPATH, '//android.widget.EditText[@text=""]'),
    # 追加: text属性が"検索"のEditText
    (AppiumBy.XPATH, '//android.widget.EditText[@text="検索"]'),
]
SEARCH_SUBMIT_BUTTON_SELECTORS = [
    (AppiumBy.XPATH, '//android.widget.Button[@text="検索"]')
]

# --- 検索結果画面 ---
SEARCH_FILTER_ICON_SELECTORS = [
    (AppiumBy.XPATH, '//android.widget.ImageView[@content-desc="もっと見る"]')
]
SEARCH_RESULT_VIDEO_ITEM_SELECTORS = [
    # 1. 既存: Button型 (従来のバージョン)
    (AppiumBy.XPATH, f'(//android.widget.Button[@resource-id="{TIKTOK_PACKAGE_NAME}:id/rqc"])[1]'),
    # 2. 新しいパターン: FrameLayout内の動画サムネイル（よくあるパターン）
    (AppiumBy.XPATH, '(//android.widget.FrameLayout[contains(@resource-id, "root_view") or contains(@resource-id, "item_view")])[1]'),
    # 3. RecyclerView内の最初の動画アイテム
    (AppiumBy.XPATH, '(//androidx.recyclerview.widget.RecyclerView//android.view.ViewGroup)[1]'),
    # 4. 画面上の最初のImageView（サムネイル画像）
    (AppiumBy.XPATH, '(//android.widget.ImageView)[1]'),
    # 5. 画面上の最初のFrameLayout
    (AppiumBy.XPATH, '(//android.widget.FrameLayout)[1]'),
]

# --- 検索「戻る」ボタン ---
SEARCH_BACK_BUTTON_SELECTORS = [
    # 1. content-desc="戻る" のImageView
    (AppiumBy.XPATH, '//android.widget.ImageView[@content-desc="戻る"]'),
    # 2. 旧ID
    ID('b6p'),
    # 3. content-desc="Back" (英語UIや一部端末)
    (AppiumBy.XPATH, '//android.widget.ImageView[@content-desc="Back"]'),
    # 4. resource-idに"back"を含むImageView
    (AppiumBy.XPATH, '//android.widget.ImageView[contains(@resource-id, "back")]'),
    # 5. 画面左上のImageView (最終手段: 位置で推測)
    (AppiumBy.XPATH, '(//android.widget.ImageView)[1]'),
]

# --- フィルター画面 ---
FILTER_INTERMEDIATE_BUTTON_SELECTORS = [
    (AppiumBy.XPATH, '//*[contains(@content-desc, "フィルター")]')
]
FILTER_SORT_DATE_SELECTORS = [
    (AppiumBy.XPATH, '//*[@text="投稿日"]')
]
FILTER_UNWATCHED_SELECTORS = [
    (AppiumBy.XPATH, '//*[@text="未視聴"]')
]
FILTER_6_MONTHS_SELECTORS = [
    (AppiumBy.XPATH, '//*[@text="過去6か月間"]')
]
FILTER_APPLY_BUTTON_SELECTORS = [
    (AppiumBy.XPATH, '//*[@text="適用"]')
]