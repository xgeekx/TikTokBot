# =====================================================================
# base_db.py: 全てのDBクラスが継承する基盤層 (V26 - 安定版)
# =====================================================================
import pymysql
import pymysql.cursors
from typing import Dict, Any, Optional, List, Tuple
import time
import traceback
from app_logger import logger
from config import MYSQL_CONFIG  # 接続設定を読み込む


class BaseDB:
    """
    DB接続の確立と、トランザクション管理を提供する基盤クラス。
    """

    def __init__(self, db_config: Dict[str, Any]):
        """接続を確立し、接続オブジェクトとカーソルを保持する"""
        self.config = db_config
        self._conn: Optional[pymysql.connections.Connection] = None
        self._cur: Optional[pymysql.cursors.DictCursor] = None
        self.connect()

    def connect(self) -> bool:
        """データベース接続の確立を試行する"""
        logger.debug("DB: Connecting...")
        if self._conn and self._conn.open:
            logger.debug("DB: Connection already established.")
            return True

        try:
            # PyMySQLで接続を確立。結果は辞書形式、トランザクションは手動管理。
            self._conn = pymysql.connect(
                host=self.config['host'],
                user=self.config['user'],
                password=self.config['password'],
                database=self.config['database'],
                port=self.config.get('port', 3306),
                cursorclass=pymysql.cursors.DictCursor,
                autocommit=False,
                connect_timeout=10,
                # ★ UTF-8MB4 (絵文字) 対応
                charset='utf8mb4'
            )
            if self._conn:
                self._cur = self._conn.cursor()
                logger.info("DB: Database connection established.")
                return True
            else:
                logger.error("DB ERROR: _conn is None after connect call.")
                return False
        except pymysql.Error as e:
            logger.error(f"DB ERROR: Database connection failed: {e}")
            logger.error(traceback.format_exc())
            self._conn = None
            self._cur = None
            return False

    def close(self):
        """DB接続とカーソルを閉じる"""
        try:
            if self._cur:
                self._cur.close()
            if self._conn:
                self._conn.close()
            logger.info("DB: Database connection closed.")
        except Exception as e:
            logger.warning(f"DB WARNING: Error while closing DB connection: {e}")

    def commit(self):
        """トランザクションを確定（コミット）する"""
        logger.debug("DB: Committing transaction.")
        if self._conn:
            try:
                self._conn.commit()
            except Exception as e:
                logger.error(f"DB ERROR: Commit failed: {e}")
                self.rollback()
                raise

    def rollback(self):
        """トランザクションをロールバック（取り消し）する"""
        logger.warning("DB: Rolling back transaction.")
        if self._conn:
            self._conn.rollback()

    def start_transaction(self):
        """[V18 設計復元] トランザクションを明示的に開始する"""
        logger.debug("DB: Starting transaction.")
        if self._conn:
            self._conn.begin()
        else:
            logger.error("DB: Cannot start transaction, no connection.")
            raise ConnectionError("DB接続がありません。")

    def execute_query(self, sql: str, params: Optional[Tuple[Any, ...]] = None) -> int:
        """
        クエリを実行し、影響を与えた行数を返す汎用メソッド。
        ★ バイナリダンプ撲滅: params のログ出力を制御する。
        """
        if not self._conn or not self._cur:
            logger.warning("DB WARNING: Connection lost. Reconnecting...")
            if not self.connect():
                logger.error("DB ERROR: Connection failed. Query aborted.")
                raise ConnectionError("DB接続が失われています。")

        # SQLクエリをログに出力
        logger.debug(f"DB EXECUTE: {sql[:100].strip()}...")

        # ★ バイナリダンプ撲滅対策 ★
        # params が存在し、それが bytes を含んでいないかチェック
        if params:
            # params がタプルでない場合はタプルに変換 (pymysqlはタプルを期待)
            if not isinstance(params, (list, tuple)):
                params_tuple = (params,)
            else:
                params_tuple = tuple(params)

            # ログ出力用の安全なパラメータリストを作成
            safe_params_log = []
            has_bytes = False
            for p in params_tuple:
                if isinstance(p, bytes):
                    safe_params_log.append(f"<bytes data size={len(p)}>")
                    has_bytes = True
                elif isinstance(p, str) and len(p) > 50:
                    # 文字列が長すぎる場合も省略 (例: キャプション)
                    safe_params_log.append(f"'{p[:50]}...'")
                else:
                    safe_params_log.append(repr(p))  # repr() を使って文字列をクォートする

            # bytes が含まれていない場合のみ、パラメータをログに出力
            # V26: ログが冗長すぎるため、bytes以外の場合でもデバッグレベルを下げるか検討
            # V34: ログレベルはDEBUGで固定
            if not has_bytes:
                logger.debug(f"DB PARAMS: {safe_params_log}")
        else:
            params_tuple = None  # パラメータなし

        try:
            # 実行時はオリジナルの params_tuple を使用
            if self._cur:
                row_count = self._cur.execute(sql, params_tuple)
                return row_count
            else:
                logger.error("DB ERROR: Cursor is not initialized.")
                return 0
        except pymysql.Error as e:
            logger.error(f"DB ERROR: SQL execution failed: {e}")
            logger.error(f"Failed SQL: {sql[:100].strip()}...")
            self.rollback()
            raise

    def fetchone(self, sql: str, params: Optional[Tuple[Any, ...]] = None) -> Optional[Dict[str, Any]]:
        """単一のレコードを取得する（読み取り操作）"""
        self.execute_query(sql, params)
        if self._cur:
            return self._cur.fetchone()
        return None

    def fetchall(self, sql: str, params: Optional[Tuple[Any, ...]] = None) -> List[Dict[str, Any]]:
        """複数のレコードを取得する（読み取り操作）"""
        self.execute_query(sql, params)
        if self._cur:
            records_tuple = self._cur.fetchall()
            return list(records_tuple)
        return []