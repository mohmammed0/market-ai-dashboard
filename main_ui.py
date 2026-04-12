import sys
import traceback
import json
import importlib
import time
import pandas as pd

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QTextEdit, QLabel, QLineEdit, QFileDialog,
    QTableWidget, QTableWidgetItem, QMessageBox, QFrame, QListWidget,
    QListWidgetItem, QSplitter
)

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from live_market_engine import LiveMarketEngine
from app_logger import get_logger
from ranking_engine import (
    rank_analysis_result,
    build_ranked_scan_rows,
    summarize_top_candidates_by_signal,
)

logger = get_logger("main_ui")


class StatCard(QFrame):
    def __init__(self, title, value="-"):
        super().__init__()
        self.setObjectName("StatCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)

        self.title_label = QLabel(title)
        self.title_label.setObjectName("CardTitle")

        self.value_label = QLabel(value)
        self.value_label.setObjectName("CardValue")

        layout.addWidget(self.title_label)
        layout.addWidget(self.value_label)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Market AI Dashboard")
        self.resize(1700, 1020)

        self.latest_result = None
        self.scan_results = []
        self.live_db_last_saved = {}
        self.live_db_min_interval_sec = 15

        logger.info("Main window initialization started")

        self.setStyleSheet("""
            QMainWindow {
                background-color: #0f172a;
            }
            QLabel {
                color: #e5e7eb;
                font-size: 13px;
            }
            QLineEdit, QTextEdit, QTableWidget, QListWidget {
                background-color: #111827;
                color: #f9fafb;
                border: 1px solid #374151;
                border-radius: 10px;
                padding: 8px;
                font-size: 13px;
            }
            QPushButton {
                background-color: #2563eb;
                color: white;
                border: none;
                border-radius: 10px;
                padding: 10px 16px;
                font-size: 13px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1d4ed8;
            }
            QPushButton:disabled {
                background-color: #475569;
                color: #cbd5e1;
            }
            QHeaderView::section {
                background-color: #1f2937;
                color: white;
                padding: 6px;
                border: none;
            }
            #TitleLabel {
                font-size: 24px;
                font-weight: bold;
                color: white;
                padding: 6px 0;
            }
            #SectionLabel {
                font-size: 16px;
                font-weight: bold;
                color: white;
                padding: 4px 0;
            }
            #StatCard {
                background-color: #111827;
                border: 1px solid #374151;
                border-radius: 14px;
            }
            #CardTitle {
                color: #94a3b8;
                font-size: 12px;
            }
            #CardValue {
                color: white;
                font-size: 20px;
                font-weight: bold;
            }
        """)

        central = QWidget()
        self.setCentralWidget(central)

        outer_layout = QHBoxLayout(central)
        outer_layout.setContentsMargins(14, 14, 14, 14)
        outer_layout.setSpacing(12)

        left_panel = QFrame()
        left_panel.setStyleSheet("QFrame { background-color: #0b1220; border-radius: 14px; }")
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(12, 12, 12, 12)
        left_layout.setSpacing(10)

        watchlist_title = QLabel("Watchlist")
        watchlist_title.setObjectName("SectionLabel")

        self.watchlist = QListWidget()
        self.watchlist.itemDoubleClicked.connect(self.load_symbol_from_watchlist)

        self.add_watchlist_button = QPushButton("Add Symbol")
        self.add_watchlist_button.clicked.connect(self.add_to_watchlist)

        self.remove_watchlist_button = QPushButton("Remove Selected")
        self.remove_watchlist_button.clicked.connect(self.remove_selected_symbol)

        self.scan_button = QPushButton("Scan Watchlist")
        self.scan_button.clicked.connect(self.scan_watchlist)

        self.news_list = QListWidget()

        left_layout.addWidget(watchlist_title)
        left_layout.addWidget(self.watchlist)
        left_layout.addWidget(self.add_watchlist_button)
        left_layout.addWidget(self.remove_watchlist_button)
        left_layout.addWidget(self.scan_button)
        left_layout.addWidget(QLabel("Latest News"))
        left_layout.addWidget(self.news_list)

        for symbol in ["AAPL", "MSFT", "NVDA", "SPY"]:
            self.watchlist.addItem(QListWidgetItem(symbol))
        right_panel = QWidget()
        main_layout = QVBoxLayout(right_panel)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(12)

        self.title_label = QLabel("Market AI Dashboard")
        self.title_label.setObjectName("TitleLabel")

        input_row = QHBoxLayout()

        self.symbol_input = QLineEdit()
        self.symbol_input.setPlaceholderText("Instrument")
        self.symbol_input.setText("AAPL")

        self.start_input = QLineEdit()
        self.start_input.setPlaceholderText("Start Date")
        self.start_input.setText("2024-01-01")

        self.end_input = QLineEdit()
        self.end_input.setPlaceholderText("End Date")
        self.end_input.setText("2026-04-02")

        input_row.addWidget(QLabel("Symbol"))
        input_row.addWidget(self.symbol_input)
        input_row.addWidget(QLabel("Start"))
        input_row.addWidget(self.start_input)
        input_row.addWidget(QLabel("End"))
        input_row.addWidget(self.end_input)

        button_row = QHBoxLayout()

        self.run_button = QPushButton("Run Analysis")
        self.run_button.clicked.connect(self.run_analysis)

        self.save_button = QPushButton("Save CSV")
        self.save_button.clicked.connect(self.save_csv)
        self.save_button.setEnabled(False)

        self.save_scan_button = QPushButton("Save Scan CSV")
        self.save_scan_button.clicked.connect(self.save_scan_csv)
        self.save_scan_button.setEnabled(False)

        button_row.addWidget(self.run_button)
        button_row.addWidget(self.save_button)
        button_row.addWidget(self.save_scan_button)
        button_row.addStretch()

        cards_row = QHBoxLayout()

        self.instrument_card = StatCard("Instrument")
        self.signal_card = StatCard("Final Signal")
        self.close_card = StatCard("Last Close")
        self.tech_score_card = StatCard("Tech Score")
        self.news_score_card = StatCard("News Score")
        self.mtf_score_card = StatCard("MTF Score")
        self.combined_score_card = StatCard("Enhanced Score")
        self.date_card = StatCard("Date")

        cards_row.addWidget(self.instrument_card)
        cards_row.addWidget(self.signal_card)
        cards_row.addWidget(self.close_card)
        cards_row.addWidget(self.tech_score_card)
        cards_row.addWidget(self.news_score_card)
        cards_row.addWidget(self.mtf_score_card)
        cards_row.addWidget(self.combined_score_card)
        cards_row.addWidget(self.date_card)

        self.figure = Figure(figsize=(8, 4))
        self.canvas = FigureCanvas(self.figure)
        self.ax = self.figure.add_subplot(111)
        self.figure.patch.set_facecolor("#111827")
        self.ax.set_facecolor("#111827")

        self.table = QTableWidget()
        self.table.setColumnCount(18)
        self.table.setHorizontalHeaderLabels([
            "Date", "Open", "High", "Low", "Close", "Volume",
            "MA20", "MA50", "RSI14", "MACD", "MACD Sig", "MACD Hist",
            "BB Upper", "BB Lower", "ATR14", "Vol Ratio", "Tech Score", "Tech Signal"
        ])

        self.scan_table = QTableWidget()
        self.scan_table.setColumnCount(11)
        self.scan_table.setHorizontalHeaderLabels([
            "Rank", "Symbol", "Final Signal", "Confidence", "Best Setup",
            "Tech Score", "AI News Score", "Combined Score", "Close", "Date", "AI Enabled"
        ])
        self.scan_table.cellDoubleClicked.connect(self.load_symbol_from_scan)
        self.scan_table.setMinimumHeight(260)

        self.live_ticker_label = QLabel("LIVE TICKER: waiting...")
        self.live_ticker_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #93c5fd; padding: 6px;")

        self.output = QTextEdit()
        self.output.setReadOnly(True)

        self.mtf_table = QTableWidget()
        self.mtf_table.setColumnCount(10)
        self.mtf_table.setHorizontalHeaderLabels([
            "Timeframe", "Signal", "Score", "Close", "RSI14", "ADX14", "Regime", "Trend", "Bars", "Date"
        ])
        self.mtf_table.setAlternatingRowColors(True)
        self.mtf_table.setMinimumHeight(130)
        self.mtf_table.setMaximumHeight(180)

        self.live_table = QTableWidget()
        self.live_table.setColumnCount(8)
        self.live_table.setHorizontalHeaderLabels([
            "Symbol", "Price", "Change", "Change %", "Day High", "Day Low", "Volume", "Source"
        ])
        self.live_table.setAlternatingRowColors(True)
        self.live_table.setMinimumHeight(180)
        self.output.setMaximumHeight(220)

        splitter = QSplitter(Qt.Vertical)
        top_widget = QWidget()
        top_layout = QVBoxLayout(top_widget)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.addWidget(self.canvas)
        top_layout.addWidget(self.table)

        bottom_widget = QWidget()
        bottom_layout = QVBoxLayout(bottom_widget)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.addWidget(QLabel("Watchlist Scan Results"))
        bottom_layout.addWidget(self.scan_table)
        bottom_layout.addWidget(QLabel("Live Watchlist Quotes"))
        bottom_layout.addWidget(self.live_table)
        bottom_layout.addWidget(self.live_ticker_label)
        bottom_layout.addWidget(QLabel("Multi-Timeframe"))
        bottom_layout.addWidget(self.mtf_table)
        bottom_layout.addWidget(self.output)

        splitter.addWidget(top_widget)
        splitter.addWidget(bottom_widget)
        splitter.setSizes([470, 430])

        main_layout.addWidget(self.title_label)
        main_layout.addLayout(input_row)
        main_layout.addLayout(button_row)
        main_layout.addLayout(cards_row)
        main_layout.addWidget(splitter)

        outer_layout.addWidget(left_panel, 1)
        outer_layout.addWidget(right_panel, 4)

        self.clear_chart()

        self.live_quotes = {}
        self.live_engine = None
        self.live_timer = QTimer(self)
        self.live_timer.timeout.connect(self.pump_live_events)
        self.restart_live_engine()

        logger.info("Main window ready")

    def add_to_watchlist(self):
        symbol = self.symbol_input.text().strip().upper()
        if not symbol:
            QMessageBox.warning(self, "Warning", "Enter a symbol first")
            return

        existing = [self.watchlist.item(i).text() for i in range(self.watchlist.count())]
        if symbol in existing:
            QMessageBox.information(self, "Info", "Symbol already in watchlist")
            return

        self.watchlist.addItem(QListWidgetItem(symbol))
        logger.info(f"Watchlist symbol added: {symbol}")

    def remove_selected_symbol(self):
        item = self.watchlist.currentItem()
        if not item:
            QMessageBox.warning(self, "Warning", "Select a symbol first")
            return

        row = self.watchlist.row(item)
        removed_symbol = item.text().strip().upper()
        self.watchlist.takeItem(row)
        logger.info(f"Watchlist symbol removed: {removed_symbol}")
        self.restart_live_engine()

    def load_symbol_from_watchlist(self, item):
        self.symbol_input.setText(item.text())

    def load_symbol_from_scan(self, row, column):
        item = self.scan_table.item(row, 1)
        if item:
            self.symbol_input.setText(item.text())
            self.run_analysis()

    def clear_chart(self):
        self.ax.clear()
        self.ax.set_title("Technical Chart", color="white")
        self.ax.tick_params(axis="x", colors="white")
        self.ax.tick_params(axis="y", colors="white")
        for spine in self.ax.spines.values():
            spine.set_color("#475569")
        self.canvas.draw()

    def _color_signal_label(self, label, signal_text):
        signal_text = str(signal_text).upper()
        if signal_text == "BUY":
            label.setStyleSheet("color: #22c55e; font-size: 20px; font-weight: bold;")
        elif signal_text == "SELL":
            label.setStyleSheet("color: #ef4444; font-size: 20px; font-weight: bold;")
        else:
            label.setStyleSheet("color: #facc15; font-size: 20px; font-weight: bold;")

    def _color_score_label(self, label, score):
        try:
            score = int(score)
        except Exception:
            score = 0

        if score > 0:
            label.setStyleSheet("color: #22c55e; font-size: 20px; font-weight: bold;")
        elif score < 0:
            label.setStyleSheet("color: #ef4444; font-size: 20px; font-weight: bold;")
        else:
            label.setStyleSheet("color: #facc15; font-size: 20px; font-weight: bold;")

    def update_cards(self, result):
        final_signal = result.get("enhanced_signal", result.get("signal", "-"))
        final_score = result.get("enhanced_combined_score", result.get("combined_score", "-"))

        self.instrument_card.value_label.setText(str(result.get("instrument", "-")))
        self.signal_card.value_label.setText(str(final_signal))
        self.close_card.value_label.setText(str(result.get("close", "-")))
        self.close_card.value_label.setToolTip("Historical / analysis close. Live quote may override when available.")
        self.tech_score_card.value_label.setText(str(result.get("technical_score", "-")))
        self.news_score_card.value_label.setText(str(result.get("ai_news_score", result.get("news_score", "-"))))
        self.mtf_score_card.value_label.setText(str(result.get("mtf_score", "-")))
        self.combined_score_card.value_label.setText(str(final_score))
        self.date_card.value_label.setText(str(result.get("date", "-")))

        self._color_signal_label(self.signal_card.value_label, final_signal)
        self._color_score_label(self.tech_score_card.value_label, result.get("technical_score", 0))
        self._color_score_label(self.news_score_card.value_label, result.get("ai_news_score", result.get("news_score", 0)))
        self._color_score_label(self.mtf_score_card.value_label, result.get("mtf_score", 0))
        self._color_score_label(self.combined_score_card.value_label, final_score)

    def draw_chart(self, chart_data, instrument):
        self.ax.clear()
        self.ax.set_facecolor("#111827")

        dates = chart_data.get("dates", [])
        close_prices = chart_data.get("close", [])
        ma20 = chart_data.get("ma20", [])
        ma50 = chart_data.get("ma50", [])
        bb_upper = chart_data.get("bb_upper", [])
        bb_lower = chart_data.get("bb_lower", [])

        if not dates or not close_prices:
            self.ax.set_title("No chart data", color="white")
            self.canvas.draw()
            return

        x = list(range(len(dates)))

        self.ax.plot(x, close_prices, label="Close")
        self.ax.plot(x, ma20, label="MA20")
        self.ax.plot(x, ma50, label="MA50")
        self.ax.plot(x, bb_upper, label="BB Upper", linestyle="--")
        self.ax.plot(x, bb_lower, label="BB Lower", linestyle="--")

        step = max(1, len(dates) // 8)
        tick_positions = x[::step]
        tick_labels = dates[::step]

        self.ax.set_xticks(tick_positions)
        self.ax.set_xticklabels(tick_labels, rotation=45, ha="right", color="white")
        self.ax.tick_params(axis="y", colors="white")
        self.ax.set_title(f"{instrument} Technical Chart", color="white")
        self.ax.grid(True, alpha=0.3)
        self.ax.legend()

        for spine in self.ax.spines.values():
            spine.set_color("#475569")

        self.figure.tight_layout()
        self.canvas.draw()

    def fill_table(self, table_data):
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(table_data))

        for row_index, row_data in enumerate(table_data):
            values = [
                row_data.get("date", ""),
                row_data.get("open", ""),
                row_data.get("high", ""),
                row_data.get("low", ""),
                row_data.get("close", ""),
                row_data.get("volume", ""),
                row_data.get("ma20", ""),
                row_data.get("ma50", ""),
                row_data.get("rsi14", ""),
                row_data.get("macd", ""),
                row_data.get("macd_signal", ""),
                row_data.get("macd_hist", ""),
                row_data.get("bb_upper", ""),
                row_data.get("bb_lower", ""),
                row_data.get("atr14", ""),
                row_data.get("volume_ratio", ""),
                row_data.get("technical_score", ""),
                row_data.get("technical_signal", ""),
            ]

            for col_index, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setTextAlignment(Qt.AlignCenter)

                if col_index == 17:
                    signal_text = str(value).upper()
                    if signal_text == "BUY":
                        item.setForeground(QColor("#22c55e"))
                    elif signal_text == "SELL":
                        item.setForeground(QColor("#ef4444"))
                    else:
                        item.setForeground(QColor("#facc15"))

                self.table.setItem(row_index, col_index, item)

        self.table.resizeColumnsToContents()
        self.table.setSortingEnabled(True)

    def fill_mtf_table(self, multi_timeframe):
        keys = ["daily", "weekly", "monthly"]
        self.mtf_table.setSortingEnabled(False)
        self.mtf_table.setRowCount(len(keys))

        for row_index, key in enumerate(keys):
            tf = multi_timeframe.get(key, {})
            values = [
                str(tf.get("label", key)).upper(),
                tf.get("signal", "-"),
                tf.get("technical_score", "-"),
                tf.get("close", "-"),
                tf.get("rsi14", "-"),
                tf.get("adx14", "-"),
                tf.get("market_regime", "-"),
                tf.get("trend_mode", "-"),
                tf.get("bars", "-"),
                tf.get("date", "-"),
            ]

            for col_index, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setTextAlignment(Qt.AlignCenter)

                if col_index == 1:
                    signal_text = str(value).upper()
                    if signal_text == "BUY":
                        item.setForeground(QColor("#22c55e"))
                    elif signal_text == "SELL":
                        item.setForeground(QColor("#ef4444"))
                    else:
                        item.setForeground(QColor("#facc15"))

                if col_index == 2:
                    try:
                        n = int(value)
                        if n > 0:
                            item.setForeground(QColor("#22c55e"))
                        elif n < 0:
                            item.setForeground(QColor("#ef4444"))
                        else:
                            item.setForeground(QColor("#facc15"))
                    except Exception:
                        pass

                self.mtf_table.setItem(row_index, col_index, item)

        self.mtf_table.resizeColumnsToContents()
        self.mtf_table.setSortingEnabled(False)

    def fill_scan_table(self, rows):
        self.scan_table.setSortingEnabled(False)
        self.scan_table.setRowCount(len(rows))

        for row_index, row_data in enumerate(rows):
            values = [
                row_data.get("rank", ""),
                row_data.get("instrument", ""),
                row_data.get("signal", ""),
                row_data.get("confidence", ""),
                row_data.get("best_setup", ""),
                row_data.get("technical_score", ""),
                row_data.get("ai_news_score", ""),
                row_data.get("combined_score", ""),
                row_data.get("close", ""),
                row_data.get("date", ""),
                row_data.get("ai_enabled", ""),
            ]

            for col_index, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setTextAlignment(Qt.AlignCenter)

                if col_index == 2:
                    signal_text = str(value).upper()
                    if signal_text == "BUY":
                        item.setForeground(QColor("#22c55e"))
                    elif signal_text == "SELL":
                        item.setForeground(QColor("#ef4444"))
                    else:
                        item.setForeground(QColor("#facc15"))

                if col_index in [0, 3, 5, 6, 7]:
                    try:
                        n = int(value)
                        if n > 0:
                            item.setForeground(QColor("#22c55e"))
                        elif n < 0:
                            item.setForeground(QColor("#ef4444"))
                        else:
                            item.setForeground(QColor("#facc15"))
                    except Exception:
                        pass

                self.scan_table.setItem(row_index, col_index, item)

        self.scan_table.resizeColumnsToContents()
        self.scan_table.setSortingEnabled(True)

    def fill_news_list(self, news_items):
        self.news_list.clear()

        if not news_items:
            self.news_list.addItem("No news")
            return

        for item in news_items[:12]:
            sentiment = item.get("sentiment", "NEUTRAL")
            title = item.get("title", "")
            source = item.get("source", "")
            published = item.get("published", "")
            self.news_list.addItem(f"[{sentiment}] {title} | {source} | {published}")

    def current_watchlist_symbols(self):
        return [
            self.watchlist.item(i).text().strip().upper()
            for i in range(self.watchlist.count())
            if self.watchlist.item(i).text().strip()
        ]

    def _fmt_live_value(self, value, pct=False):
        if value is None or value == "":
            return "-"
        try:
            num = float(value)
            if pct:
                return f"{num:.2f}%"
            if abs(num) >= 1000000:
                return f"{num:,.0f}"
            return f"{num:.2f}"
        except Exception:
            return str(value)

    def maybe_save_live_quote(self, quote):
        symbol = str(quote.get("symbol", "")).strip().upper()
        if not symbol:
            return

        now_ts = time.time()
        last_ts = self.live_db_last_saved.get(symbol, 0)

        if now_ts - last_ts < self.live_db_min_interval_sec:
            return

        try:
            from db import init_db
            from db_ops import save_live_quote
            init_db()
            save_live_quote(quote)
            self.live_db_last_saved[symbol] = now_ts
        except Exception as db_error:
            logger.warning(f"Live DB save error: {db_error}")
            self.statusBar().showMessage(f"Live DB save error: {db_error}")

    def restart_live_engine(self):
        if not hasattr(self, "live_table"):
            return
        try:
            if self.live_engine is not None:
                self.live_engine.stop()
        except Exception:
            pass

        self.live_quotes = {}
        self.live_db_last_saved = {}
        symbols = self.current_watchlist_symbols() or ["AAPL", "MSFT", "NVDA", "SPY"]

        self.live_engine = LiveMarketEngine(
            symbols=symbols,
            feed="iex",
            use_test_stream=False,
            poll_interval=3,
        )
        self.live_engine.start()
        if not hasattr(self, "live_timer"):
            self.live_timer = QTimer(self)
            self.live_timer.timeout.connect(self.pump_live_events)
        self.live_timer.start(1000)
        self.refresh_live_table()

    def pump_live_events(self):
        if self.live_engine is None:
            return

        updated = False

        while True:
            event = self.live_engine.get_event(timeout=0.01)
            if event is None:
                break

            event_type = event.get("type")
            payload = event.get("payload", {})

            if event_type == "quote":
                symbol = payload.get("symbol")
                if symbol:
                    self.live_quotes[symbol] = payload
                    self.maybe_save_live_quote(payload)
                    updated = True
            elif event_type == "status":
                self.statusBar().showMessage(f"Live: {payload.get('message', '')}")
            elif event_type == "error":
                logger.warning(f"Live event error: {payload.get('message', '')}")
                self.statusBar().showMessage(f"Live error: {payload.get('message', '')}")

        if updated:
            self.refresh_live_table()

    def update_live_selected_symbol_cards(self):
        selected_symbol = self.symbol_input.text().strip().upper()
        if not selected_symbol:
            return

        quote = self.live_quotes.get(selected_symbol, {})
        if not quote:
            return

        price = quote.get("price")
        change = quote.get("change")
        change_pct = quote.get("change_pct")

        if price is not None:
            self.close_card.value_label.setText(self._fmt_live_value(price))

        if change is not None:
            try:
                n = float(change)
                if n > 0:
                    self.close_card.value_label.setStyleSheet("color: #22c55e; font-size: 20px; font-weight: bold;")
                elif n < 0:
                    self.close_card.value_label.setStyleSheet("color: #ef4444; font-size: 20px; font-weight: bold;")
                else:
                    self.close_card.value_label.setStyleSheet("color: white; font-size: 20px; font-weight: bold;")
            except Exception:
                pass

        self.statusBar().showMessage(
            f"{selected_symbol} | Live: {self._fmt_live_value(price)} | Change: {self._fmt_live_value(change)} | Change %: {self._fmt_live_value(change_pct, pct=True)}"
        )

    def update_live_ticker_label(self):
        symbols = self.current_watchlist_symbols() or ["AAPL", "MSFT", "NVDA", "SPY"]
        parts = []

        for symbol in symbols:
            quote = self.live_quotes.get(symbol, {})
            if not quote:
                parts.append(f"{symbol}: ...")
                continue

            price = self._fmt_live_value(quote.get("price"))
            pct = self._fmt_live_value(quote.get("change_pct"), pct=True)
            parts.append(f"{symbol}: {price} ({pct})")

        self.live_ticker_label.setText("LIVE TICKER:  " + "   |   ".join(parts))

    def refresh_live_table(self):
        self.live_table.setSortingEnabled(False)
        symbols = self.current_watchlist_symbols() or ["AAPL", "MSFT", "NVDA", "SPY"]
        symbols = sorted(symbols)
        self.live_table.setRowCount(len(symbols))

        for row_index, symbol in enumerate(symbols):
            quote = self.live_quotes.get(symbol, {})
            change_value = quote.get("change")

            values = [
                symbol,
                self._fmt_live_value(quote.get("price")),
                self._fmt_live_value(change_value),
                self._fmt_live_value(quote.get("change_pct"), pct=True),
                self._fmt_live_value(quote.get("day_high")),
                self._fmt_live_value(quote.get("day_low")),
                self._fmt_live_value(quote.get("volume")),
                quote.get("source", "-"),
            ]

            for col_index, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setTextAlignment(Qt.AlignCenter)

                if col_index == 0 and symbol == self.symbol_input.text().strip().upper():
                    item.setBackground(QColor("#1e293b"))
                    item.setForeground(QColor("#93c5fd"))

                if col_index in [1, 2, 3]:
                    try:
                        if col_index == 1:
                            n = float(change_value or 0)
                        elif col_index == 2:
                            n = float(change_value or 0)
                        else:
                            n = float(quote.get("change_pct") or 0)
                        if n > 0:
                            item.setForeground(QColor("#22c55e"))
                        elif n < 0:
                            item.setForeground(QColor("#ef4444"))
                        else:
                            item.setForeground(QColor("#facc15"))
                    except Exception:
                        pass

                self.live_table.setItem(row_index, col_index, item)

        self.live_table.resizeColumnsToContents()
        self.live_table.setSortingEnabled(True)
        self.update_live_ticker_label()
        self.update_live_selected_symbol_cards()
        self.statusBar().showMessage(f"Live symbols: {len(symbols)} | Last refresh: polling")

    def build_output_text(self, result):
        result = rank_analysis_result(result)
        lines = []
        lines.append(f"Instrument: {result.get('instrument', '-')}")
        lines.append(f"Final Signal: {result.get('signal', '-')}")
        lines.append(f"Rank: {result.get('rank', '-')}")
        lines.append(f"Confidence: {result.get('confidence', '-')}")
        lines.append(f"Best Setup: {result.get('best_setup', '-')}")
        lines.append(f"Setup Type: {result.get('setup_type', '-')}")
        lines.append(f"Technical Signal: {result.get('technical_signal', '-')}")
        lines.append(f"Technical Score: {result.get('technical_score', '-')}")
        lines.append(f"News Score: {result.get('news_score', '-')}")
        lines.append(f"AI News Score: {result.get('ai_news_score', '-')}")
        lines.append(f"Combined Score: {result.get('combined_score', '-')}")
        lines.append(f"Enhanced Combined Score: {result.get('enhanced_combined_score', '-')}")
        lines.append(f"Enhanced Signal: {result.get('enhanced_signal', '-')}")
        lines.append(f"MTF Score: {result.get('mtf_score', '-')}")
        lines.append(f"MTF Alignment: {result.get('mtf_alignment', '-')}")
        lines.append(f"RS Benchmark: {result.get('rs_benchmark', '-')}")
        lines.append(f"RS Score: {result.get('rs_score', '-')}")
        lines.append(f"RS vs SPY 20D: {result.get('rs_spy_20', '-')}")
        lines.append(f"RS vs SPY 63D: {result.get('rs_spy_63', '-')}")
        lines.append(f"RS State: {result.get('rs_state', '-')}")
        lines.append(f"ML Enabled: {result.get('ml_enabled', False)}")
        lines.append(f"ML Signal: {result.get('ml_signal', '-')}")
        lines.append(f"ML Confidence: {result.get('ml_confidence', '-')}")
        lines.append(f"ML Score: {result.get('ml_score', '-')}")
        lines.append(f"ML Prob SELL: {result.get('ml_prob_sell', '-')}")
        lines.append(f"ML Prob HOLD: {result.get('ml_prob_hold', '-')}")
        lines.append(f"ML Prob BUY: {result.get('ml_prob_buy', '-')}")
        lines.append(f"Market Regime: {result.get('market_regime', '-')}")
        lines.append(f"Trend Mode: {result.get('trend_mode', '-')}")
        lines.append(f"Regime Score: {result.get('regime_score', '-')}")
        lines.append(f"News Sentiment: {result.get('news_sentiment', '-')}")
        lines.append(f"AI News Sentiment: {result.get('ai_news_sentiment', '-')}")
        lines.append(f"AI Enabled: {result.get('ai_enabled', False)}")
        lines.append(f"Date: {result.get('date', '-')}")
        lines.append(f"52W High: {result.get('high_52w', '-')}")
        lines.append(f"52W Low: {result.get('low_52w', '-')}")
        lines.append(f"Dist From 52W High %: {result.get('dist_from_52w_high_pct', '-')}")
        lines.append(f"Dist From 52W Low %: {result.get('dist_from_52w_low_pct', '-')}")
        lines.append(f"Gap %: {result.get('gap_pct', '-')}")
        lines.append(f"Gap Signal: {result.get('gap_signal', '-')}")
        lines.append(f"Candle Signal: {result.get('candle_signal', '-')}")
        lines.append(f"Squeeze Ready: {result.get('squeeze_ready', False)}")
        lines.append(f"Trend Quality Score: {result.get('trend_quality_score', 0)}")
        best_setup_values = result.get("best_setup_values", {})
        if best_setup_values:
            lines.append(f"Best Setup Win Rate %: {best_setup_values.get('overall_win_rate_pct', '-')}")
            lines.append(f"Best Setup Avg Trade Return %: {best_setup_values.get('avg_trade_return_pct', '-')}")
            lines.append(f"Best Setup Stability: {best_setup_values.get('stability_score', '-')}")

        multi_timeframe = result.get("multi_timeframe", {})
        if multi_timeframe:
            lines.append("")
            lines.append("Multi-Timeframe:")

            for key in ["daily", "weekly", "monthly"]:
                tf = multi_timeframe.get(key, {})
                lines.append(
                    f"{str(tf.get('label', key)).upper()} | "
                    f"Signal: {tf.get('signal', '-')} | "
                    f"Score: {tf.get('technical_score', '-')} | "
                    f"Close: {tf.get('close', '-')} | "
                    f"RSI14: {tf.get('rsi14', '-')} | "
                    f"ADX14: {tf.get('adx14', '-')} | "
                    f"Regime: {tf.get('market_regime', '-')} | "
                    f"Trend: {tf.get('trend_mode', '-')} | "
                    f"Bars: {tf.get('bars', '-')} | "
                    f"Date: {tf.get('date', '-')}"
                )

        lines.append("")
        lines.append("Reasons:")
        lines.append(str(result.get("reasons", "-")))
        lines.append("")
        lines.append("AI Summary:")
        lines.append(str(result.get("ai_summary", "-")))

        ai_error = result.get("ai_error")
        if ai_error:
            lines.append("")
            lines.append("AI Error:")
            lines.append(str(ai_error))

        ml_error = result.get("ml_error")
        if ml_error:
            lines.append("")
            lines.append("ML Error:")
            lines.append(str(ml_error))

        return "\n".join(lines)

    def save_csv(self):
        if not self.latest_result or "table_data" not in self.latest_result:
            QMessageBox.warning(self, "Warning", "No data to save")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save CSV",
            "market_data.csv",
            "CSV Files (*.csv)"
        )

        if not file_path:
            return

        df = pd.DataFrame(self.latest_result["table_data"])
        df.to_csv(file_path, index=False, encoding="utf-8-sig")

        QMessageBox.information(self, "Saved", f"CSV saved successfully:\n{file_path}")

    def save_scan_csv(self):
        if not self.scan_results:
            QMessageBox.warning(self, "Warning", "No scan data to save")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Scan CSV",
            "watchlist_scan.csv",
            "CSV Files (*.csv)"
        )

        if not file_path:
            return

        df = pd.DataFrame(self.scan_results)
        df.to_csv(file_path, index=False, encoding="utf-8-sig")
        QMessageBox.information(self, "Saved", f"Scan CSV saved successfully:\n{file_path}")

    def run_analysis(self):
        self.output.clear()
        self.table.setRowCount(0)
        self.news_list.clear()
        self.latest_result = None
        self.save_button.setEnabled(False)
        self.clear_chart()


        try:
            import analysis_engine
            importlib.reload(analysis_engine)

            symbol = self.symbol_input.text().strip()
            start_date = self.start_input.text().strip()
            end_date = self.end_input.text().strip()

            logger.info(f"UI run_analysis clicked | symbol={symbol} | start={start_date} | end={end_date}")

            if hasattr(analysis_engine, "run_analysis"):
                result = analysis_engine.run_analysis(
                    instrument=symbol,
                    start_date=start_date,
                    end_date=end_date
                )
                result = rank_analysis_result(result)

                self.latest_result = result

                if "error" in result:
                    logger.warning(f"Analysis returned error for symbol={symbol}: {result.get('error')}")
                    self.output.append(json.dumps(result, indent=2, ensure_ascii=False))
                    return

                logger.info(
                    f"UI analysis success | symbol={result.get('instrument')} | signal={result.get('signal')} | "
                    f"combined_score={result.get('combined_score')}"
                )
                self.update_cards(result)
                self.fill_mtf_table(result.get("multi_timeframe", {}))

                chart_data = result.get("chart_data")
                if chart_data:
                    self.draw_chart(chart_data, result.get("instrument", symbol))

                table_data = result.get("table_data", [])
                if table_data:
                    self.fill_table(table_data)
                    self.save_button.setEnabled(True)

                news_items = result.get("news_items", [])
                self.fill_news_list(news_items)

                try:
                    from db import init_db
                    from db_ops import save_analysis_result, save_news_items
                    init_db()
                    save_analysis_result(result)
                    save_news_items(result.get("instrument"), news_items)
                except Exception as db_error:
                    self.statusBar().showMessage(f"DB save error: {db_error}")

                self.output.setPlainText(self.build_output_text(result))
            else:
                self.output.append("analysis_engine.py ????? ??? ?? ??? ???? ????? run_analysis")
        except Exception:
            logger.exception("UI run_analysis crashed")
            self.output.append(traceback.format_exc())

    def scan_watchlist(self):
        self.output.clear()
        self.scan_results = []
        self.save_scan_button.setEnabled(False)

        try:
            import analysis_engine
            importlib.reload(analysis_engine)

            start_date = self.start_input.text().strip()
            end_date = self.end_input.text().strip()

            symbols = [self.watchlist.item(i).text().strip().upper() for i in range(self.watchlist.count())]
            symbols = [s for s in symbols if s]

            if not symbols:
                QMessageBox.warning(self, "Warning", "Watchlist is empty")
                return

            logger.info(f"Watchlist scan started | symbols={symbols} | start={start_date} | end={end_date}")

            for symbol in symbols:
                try:
                    result = analysis_engine.run_analysis(
                        instrument=symbol,
                        start_date=start_date,
                        end_date=end_date
                    )
                    if "error" not in result:
                        result = rank_analysis_result(result)
                        try:
                            from db import init_db
                            from db_ops import save_analysis_result, save_news_items
                            init_db()
                            save_analysis_result(result)
                            save_news_items(result.get("instrument"), result.get("news_items", []))
                        except Exception as db_error:
                            self.statusBar().showMessage(f"DB save error: {db_error}")

                        self.scan_results.append({
                            "rank": result.get("rank", ""),
                            "instrument": result.get("instrument"),
                            "signal": result.get("enhanced_signal", result.get("signal")),
                            "confidence": result.get("confidence", ""),
                            "best_setup": result.get("best_setup", ""),
                            "setup_type": result.get("setup_type", ""),
                            "best_setup_values": result.get("best_setup_values", {}),
                            "technical_score": result.get("technical_score"),
                            "ai_news_score": result.get("ai_news_score", result.get("news_score")),
                            "combined_score": result.get("enhanced_combined_score", result.get("combined_score")),
                            "enhanced_combined_score": result.get("enhanced_combined_score", result.get("combined_score")),
                            "close": result.get("close"),
                            "date": result.get("date"),
                            "ai_enabled": result.get("ai_enabled"),
                            "ml_confidence": result.get("ml_confidence"),
                            "mtf_score": result.get("mtf_score"),
                            "rs_score": result.get("rs_score"),
                            "trend_quality_score": result.get("trend_quality_score"),
                            "candle_signal": result.get("candle_signal"),
                            "squeeze_ready": result.get("squeeze_ready"),
                            "rank_score": result.get("rank_score"),
                        })
                except Exception as e:
                    self.scan_results.append({
                        "rank": "",
                        "instrument": symbol,
                        "signal": "ERROR",
                        "confidence": "",
                        "best_setup": "",
                        "setup_type": "",
                        "best_setup_values": {},
                        "technical_score": "",
                        "ai_news_score": "",
                        "combined_score": "",
                        "close": "",
                        "date": "",
                        "ai_enabled": False,
                        "error": str(e)
                    })

            self.scan_results = build_ranked_scan_rows(self.scan_results)
            self.fill_scan_table(self.scan_results)
            self.save_scan_button.setEnabled(True)

            top = self.scan_results[0] if self.scan_results else {}
            top_long_lines = summarize_top_candidates_by_signal(self.scan_results, "BUY", limit=3)
            top_short_lines = summarize_top_candidates_by_signal(self.scan_results, "SELL", limit=3)
            self.output.setPlainText(
                f"Scanned symbols: {len(symbols)}\n"
                f"Successful results: {len([x for x in self.scan_results if x.get('signal') != 'ERROR'])}\n"
                f"Top Pick: {top.get('instrument', '-')}\n"
                f"Top Pick Rank: {top.get('rank', '-')}\n"
                f"Top Pick Signal: {top.get('signal', '-')}\n"
                f"Top Pick Confidence: {top.get('confidence', '-')}\n"
                f"Top Pick Best Setup: {top.get('best_setup', '-')}\n"
                f"Top Pick Combined Score: {top.get('combined_score', '-')}\n"
                f"Top Pick Close: {top.get('close', '-')}\n"
                f"Top Pick Date: {top.get('date', '-')}\n\n"
                f"Top Long Candidates Today:\n" + ("\n".join(top_long_lines) if top_long_lines else "No BUY candidates today") + "\n\n"
                f"Top Short Candidates Today:\n" + ("\n".join(top_short_lines) if top_short_lines else "No SELL candidates today")
            )

            logger.info(
                f"Watchlist scan completed | scanned={len(symbols)} | "
                f"successful={len([x for x in self.scan_results if x.get('signal') != 'ERROR'])} | "
                f"top_pick={top.get('instrument', '-')}"
            )

        except Exception:
            logger.exception("UI scan_watchlist crashed")
            self.output.append(traceback.format_exc())


if __name__ == "__main__":
    from db import init_db
    init_db()

    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())









