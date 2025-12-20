from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from collections import defaultdict

from inventorylite import db
from inventorylite.ui_components import TableFrame
from inventorylite.utils import Settings


class ReportsTab:
    def __init__(self, parent: ttk.Notebook, settings: Settings):
        self.parent = parent
        self.settings = settings
        self.frame = ttk.Frame(parent)

        self.chart_palette = ["#2563eb", "#16a34a", "#f97316", "#a855f7", "#0ea5e9", "#ef4444", "#6366f1"]

        self._build()

    def _build(self) -> None:
        notebook = ttk.Notebook(self.frame)
        notebook.pack(fill=tk.BOTH, expand=True)

        # Dashboard
        dashboard_tab = ttk.Frame(notebook)
        notebook.add(dashboard_tab, text="Дашборд")
        dash_filters = ttk.Frame(dashboard_tab)
        dash_filters.pack(fill=tk.X, padx=8, pady=6)
        ttk.Label(dash_filters, text="Дата з:").pack(side=tk.LEFT)
        self.dashboard_from_var = tk.StringVar()
        ttk.Entry(dash_filters, textvariable=self.dashboard_from_var, width=10).pack(side=tk.LEFT, padx=2)
        ttk.Label(dash_filters, text="по:").pack(side=tk.LEFT)
        self.dashboard_to_var = tk.StringVar()
        ttk.Entry(dash_filters, textvariable=self.dashboard_to_var, width=10).pack(side=tk.LEFT, padx=2)
        ttk.Button(dash_filters, text="Оновити", command=self.refresh_dashboard).pack(side=tk.LEFT, padx=6)

        cards_frame = ttk.Frame(dashboard_tab)
        cards_frame.pack(fill=tk.X, padx=8, pady=(2, 6))
        self.dashboard_cards: dict[str, dict[str, object]] = {}
        for key, title, hint in [
            ("turnover", "Оборот", "оплачені продажі"),
            ("gross_profit", "Валовий прибуток", "дохід мінус собівартість та витрати"),
            ("margin_pct", "Маржа", "%"),
            ("stock_value", "Вартість залишків", "на зараз"),
        ]:
            frame = ttk.LabelFrame(cards_frame, text=title)
            frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=4)
            value_var = tk.StringVar(value="0.00")
            extra_var = tk.StringVar(value=hint)
            ttk.Label(frame, textvariable=value_var, font=("Segoe UI", 13, "bold")).pack(anchor="w", padx=8, pady=(6, 0))
            ttk.Label(frame, textvariable=extra_var, foreground="#555").pack(anchor="w", padx=8, pady=(0, 2))
            canvas = tk.Canvas(frame, height=42, bg="white", highlightthickness=1, highlightbackground="#e5e7eb")
            canvas.pack(fill=tk.X, padx=6, pady=(2, 6))
            self.dashboard_cards[key] = {"value": value_var, "extra": extra_var, "canvas": canvas}

        trend_frame = ttk.LabelFrame(dashboard_tab, text="Тренд обороту / валового прибутку")
        trend_frame.pack(fill=tk.BOTH, expand=False, padx=8, pady=(0, 6))
        self.dashboard_trend_canvas = tk.Canvas(
            trend_frame, height=240, background="white", highlightthickness=1, highlightbackground="#d9d9d9"
        )
        self.dashboard_trend_canvas.pack(fill=tk.BOTH, expand=True, padx=4, pady=6)

        dash_columns = [("name", "Показник", 260), ("value", "Значення", 200), ("extra", "Примітка", 200)]
        self.dashboard_table = TableFrame(dashboard_tab, dash_columns)
        self.dashboard_table.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        # Sales analysis
        sales_tab = ttk.Frame(notebook)
        notebook.add(sales_tab, text="Продажі")
        sales_filters = ttk.Frame(sales_tab)
        sales_filters.pack(fill=tk.X, padx=8, pady=6)
        ttk.Label(sales_filters, text="Дата з:").pack(side=tk.LEFT)
        self.sales_from_var = tk.StringVar()
        ttk.Entry(sales_filters, textvariable=self.sales_from_var, width=10).pack(side=tk.LEFT, padx=2)
        ttk.Label(sales_filters, text="по:").pack(side=tk.LEFT)
        self.sales_to_var = tk.StringVar()
        ttk.Entry(sales_filters, textvariable=self.sales_to_var, width=10).pack(side=tk.LEFT, padx=2)
        ttk.Button(sales_filters, text="Оновити", command=self.refresh_sales_analysis).pack(side=tk.LEFT, padx=6)
        charts_frame = ttk.Frame(sales_tab)
        charts_frame.pack(fill=tk.X, padx=8, pady=(4, 2))
        channel_box = ttk.LabelFrame(charts_frame, text="Структура по каналах")
        channel_box.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 4))
        self.sales_channel_pie = tk.Canvas(channel_box, height=240, bg="white", highlightthickness=1, highlightbackground="#d9d9d9")
        self.sales_channel_pie.pack(fill=tk.BOTH, expand=True, padx=4, pady=6)
        category_box = ttk.LabelFrame(charts_frame, text="Структура по категоріях")
        category_box.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(4, 0))
        self.sales_category_pie = tk.Canvas(category_box, height=240, bg="white", highlightthickness=1, highlightbackground="#d9d9d9")
        self.sales_category_pie.pack(fill=tk.BOTH, expand=True, padx=4, pady=6)

        sales_tables = ttk.Frame(sales_tab)
        sales_tables.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)
        channel_columns = [
            ("name", "Канал", 180),
            ("revenue", "Дохід", 140),
            ("gross_profit", "Валовий прибуток", 160),
            ("qty", "К-сть", 100),
        ]
        category_columns = [
            ("name", "Категорія", 200),
            ("revenue", "Дохід", 140),
            ("gross_profit", "Валовий прибуток", 160),
            ("qty", "К-сть", 100),
        ]
        ttk.Label(sales_tables, text="По каналах", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        self.sales_channels_table = TableFrame(sales_tables, channel_columns)
        self.sales_channels_table.pack(fill=tk.BOTH, expand=True, pady=4)
        ttk.Label(sales_tables, text="По категоріях", font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(10, 0))
        self.sales_categories_table = TableFrame(sales_tables, category_columns)
        self.sales_categories_table.pack(fill=tk.BOTH, expand=True, pady=4)

        # ABC/XYZ
        abc_tab = ttk.Frame(notebook)
        notebook.add(abc_tab, text="ABC/XYZ")
        abc_filters = ttk.Frame(abc_tab)
        abc_filters.pack(fill=tk.X, padx=8, pady=6)
        ttk.Label(abc_filters, text="Дата з:").pack(side=tk.LEFT)
        self.abc_from_var = tk.StringVar()
        ttk.Entry(abc_filters, textvariable=self.abc_from_var, width=10).pack(side=tk.LEFT, padx=2)
        ttk.Label(abc_filters, text="по:").pack(side=tk.LEFT)
        self.abc_to_var = tk.StringVar()
        ttk.Entry(abc_filters, textvariable=self.abc_to_var, width=10).pack(side=tk.LEFT, padx=2)
        ttk.Button(abc_filters, text="Оновити", command=self.refresh_abc_xyz).pack(side=tk.LEFT, padx=6)
        abc_columns = [
            ("name", "Товар", 220),
            ("sku", "SKU", 100),
            ("category", "Категорія", 160),
            ("revenue", "Дохід", 120),
            ("abc", "ABC", 60),
            ("xyz", "XYZ", 60),
        ]
        abc_body = ttk.Frame(abc_tab)
        abc_body.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)
        self.abc_table = TableFrame(abc_body, abc_columns)
        self.abc_table.pack(fill=tk.BOTH, expand=True, side=tk.LEFT, padx=(0, 6), pady=4)
        self.abc_table.tag_configure("abc_a", background="#ecfdf3")
        self.abc_table.tag_configure("abc_c", background="#fff1f2")
        self.abc_table.tag_configure("xyz_x", foreground="#166534")
        self.abc_table.tag_configure("xyz_z", foreground="#991b1b")

        legend = ttk.LabelFrame(abc_body, text="Легенда")
        legend.pack(fill=tk.Y, side=tk.LEFT, padx=(6, 0), pady=4)
        ttk.Label(legend, text="A/X — лідери та стабільні", foreground="#166534").pack(anchor="w", padx=8, pady=(6, 2))
        ttk.Label(legend, text="C/Z — дрібні та волатильні", foreground="#991b1b").pack(anchor="w", padx=8, pady=2)
        self.abc_distribution_canvas = tk.Canvas(
            legend, width=220, height=140, bg="white", highlightthickness=1, highlightbackground="#d9d9d9"
        )
        self.abc_distribution_canvas.pack(fill=tk.BOTH, expand=True, padx=6, pady=8)

        # Cash flow
        cash_tab = ttk.Frame(notebook)
        notebook.add(cash_tab, text="Каса")
        cash_filters = ttk.Frame(cash_tab)
        cash_filters.pack(fill=tk.X, padx=8, pady=6)
        ttk.Label(cash_filters, text="Дата з:").pack(side=tk.LEFT)
        self.cash_from_var = tk.StringVar()
        ttk.Entry(cash_filters, textvariable=self.cash_from_var, width=10).pack(side=tk.LEFT, padx=2)
        ttk.Label(cash_filters, text="по:").pack(side=tk.LEFT)
        self.cash_to_var = tk.StringVar()
        ttk.Entry(cash_filters, textvariable=self.cash_to_var, width=10).pack(side=tk.LEFT, padx=2)
        ttk.Label(cash_filters, text="Тип:").pack(side=tk.LEFT, padx=(10, 2))
        self.cash_type_var = tk.StringVar()
        self.cash_type_combo = ttk.Combobox(
            cash_filters,
            textvariable=self.cash_type_var,
            values=["", "sale_payment", "purchase_payment", "income", "expense", "transfer"],
            width=15,
        )
        self.cash_type_combo.pack(side=tk.LEFT)
        ttk.Label(cash_filters, text="Канал:").pack(side=tk.LEFT, padx=(10, 2))
        self.cash_channel_var = tk.StringVar()
        ttk.Entry(cash_filters, textvariable=self.cash_channel_var, width=12).pack(side=tk.LEFT, padx=2)
        ttk.Label(cash_filters, text="Контрагент:").pack(side=tk.LEFT, padx=(10, 2))
        self.cash_counterparty_var = tk.StringVar()
        self.cash_counterparty_combo = ttk.Combobox(cash_filters, textvariable=self.cash_counterparty_var, width=25)
        self.cash_counterparty_combo.pack(side=tk.LEFT)
        ttk.Button(cash_filters, text="Показати", command=self.refresh_cash_flow_report).pack(side=tk.LEFT, padx=6)

        cash_summary_box = ttk.LabelFrame(cash_tab, text="Рух коштів за типами")
        cash_summary_box.pack(fill=tk.X, padx=8, pady=(0, 6))
        self.cash_summary_canvas = tk.Canvas(
            cash_summary_box, height=200, bg="white", highlightthickness=1, highlightbackground="#d9d9d9"
        )
        self.cash_summary_canvas.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        cash_columns = [
            ("date", "Дата", 90),
            ("type", "Тип", 140),
            ("amount", "Сума", 100),
            ("counterparty", "Контрагент", 180),
            ("channel", "Канал", 120),
            ("comment", "Коментар", 200),
        ]
        self.cash_report_table = TableFrame(cash_tab, cash_columns)
        self.cash_report_table.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        self.frame.after_idle(self.refresh_all)

    def refresh_all(self) -> None:
        self.refresh_dashboard()
        self.refresh_sales_analysis()
        self.refresh_abc_xyz()
        self.refresh_cash_counterparties()
        self.refresh_cash_flow_report()

    def refresh_dashboard(self) -> None:
        metrics = db.dashboard_metrics(
            self.dashboard_from_var.get().strip() or None, self.dashboard_to_var.get().strip() or None
        )
        if hasattr(self, "dashboard_cards"):
            self.dashboard_cards["turnover"]["value"].set(f"{metrics['turnover']:.2f}")
            self.dashboard_cards["gross_profit"]["value"].set(f"{metrics['gross_profit']:.2f}")
            self.dashboard_cards["margin_pct"]["value"].set(f"{metrics['margin_pct']:.2f}%")
            self.dashboard_cards["stock_value"]["value"].set(f"{metrics['stock_value']:.2f}")
        self.dashboard_table.set_rows(
            [
                {"id": 1, "name": "Оборот", "value": f"{metrics['turnover']:.2f}", "extra": "оплачені продажі"},
                {
                    "id": 2,
                    "name": "Валовий прибуток",
                    "value": f"{metrics['gross_profit']:.2f}",
                    "extra": "дохід мінус собівартість та витрати продажів",
                },
                {"id": 3, "name": "Маржа", "value": f"{metrics['margin_pct']:.2f}%", "extra": ""},
                {"id": 4, "name": "Вартість залишків", "value": f"{metrics['stock_value']:.2f}", "extra": "на зараз"},
            ]
        )
        self.update_dashboard_trend()

    def refresh_sales_analysis(self) -> None:
        analysis = db.sales_analysis(self.sales_from_var.get().strip() or None, self.sales_to_var.get().strip() or None)
        self.sales_channels_table.set_rows(
            [
                {
                    "id": idx,
                    "name": r["name"],
                    "revenue": f"{r['revenue']:.2f}",
                    "gross_profit": f"{r['gross_profit']:.2f}",
                    "qty": f"{r['qty']:.2f}",
                }
                for idx, r in enumerate(analysis["channels"], 1)
            ]
        )
        self.sales_categories_table.set_rows(
            [
                {
                    "id": idx,
                    "name": r["name"],
                    "revenue": f"{r['revenue']:.2f}",
                    "gross_profit": f"{r['gross_profit']:.2f}",
                    "qty": f"{r['qty']:.2f}",
                }
                for idx, r in enumerate(analysis["categories"], 1)
            ]
        )
        self.draw_pie_chart(
            self.sales_channel_pie,
            [(r["name"], r["revenue"]) for r in analysis["channels"]],
            "Канали продажу",
        )
        self.draw_pie_chart(
            self.sales_category_pie,
            [(r["name"], r["revenue"]) for r in analysis["categories"]],
            "Категорії",
        )

    def refresh_abc_xyz(self) -> None:
        rows = db.abc_xyz_report(self.abc_from_var.get().strip() or None, self.abc_to_var.get().strip() or None)
        table_rows = []
        distribution: defaultdict[str, int] = defaultdict(int)
        for r in rows:
            tags = []
            if r["abc"] == "A":
                tags.append("abc_a")
            if r["abc"] == "C":
                tags.append("abc_c")
            if r["xyz"] == "X":
                tags.append("xyz_x")
            if r["xyz"] == "Z":
                tags.append("xyz_z")
            combo = f"{r['abc']}/{r['xyz']}"
            distribution[combo] += 1
            table_rows.append(
                {
                    "id": r["product_id"],
                    "name": r["name"],
                    "sku": r["sku"],
                    "category": r["category"],
                    "revenue": f"{r['revenue']:.2f}",
                    "abc": r["abc"],
                    "xyz": r["xyz"],
                    "tags": tags,
                }
            )
        self.abc_table.set_rows(table_rows)
        self.draw_bar_chart(
            self.abc_distribution_canvas,
            sorted(distribution.items()),
            title="Кількість товарів за групами",
            bar_color="#2563eb",
        )

    def refresh_cash_counterparties(self) -> None:
        counterparts = db.list_counterparties()
        names = ["Усі"] + [c["name"] for c in counterparts]
        self.cash_counterparty_combo["values"] = names
        if not self.cash_counterparty_var.get():
            self.cash_counterparty_combo.current(0) if names else None

    def refresh_cash_flow_report(self) -> None:
        cp_name = self.cash_counterparty_var.get().strip()
        cp_id = None
        if cp_name and cp_name != "Усі":
            for c in db.list_counterparties():
                if c["name"] == cp_name:
                    cp_id = c["id"]
                    break
        rows = db.cash_flow_detailed(
            self.cash_from_var.get().strip() or None,
            self.cash_to_var.get().strip() or None,
            self.cash_type_var.get().strip() or None,
            self.cash_channel_var.get().strip() or None,
            cp_id,
        )
        self.cash_report_table.set_rows(
            [
                {
                    "id": r["id"],
                    "date": r["date"],
                    "type": r["type"],
                    "amount": f"{r['amount']:.2f}",
                    "counterparty": r["counterparty"],
                    "channel": r["channel"],
                    "comment": r["comment"],
                }
                for r in rows
            ]
        )
        summary = db.cash_flow_summary(self.cash_from_var.get().strip() or None, self.cash_to_var.get().strip() or None)
        self.draw_bar_chart(
            self.cash_summary_canvas,
            [(r["type"], r["total"]) for r in summary],
            title="Сума за обраний період",
            bar_color="#0ea5e9",
        )

    def update_dashboard_trend(self) -> None:
        trend = db.dashboard_trends(
            self.dashboard_from_var.get().strip() or None, self.dashboard_to_var.get().strip() or None
        )
        periods = [row["period"] for row in trend]
        turnover = [row["turnover"] for row in trend]
        gross_profit = [row["gross_profit"] for row in trend]
        self.draw_line_chart(
            self.dashboard_trend_canvas,
            periods,
            [
                ("Оборот", turnover, self.chart_palette[0]),
                ("Валовий прибуток", gross_profit, self.chart_palette[1]),
            ],
        )
        if trend:
            self.draw_sparkline(self.dashboard_cards["turnover"]["canvas"], turnover, self.chart_palette[0])
            self.draw_sparkline(self.dashboard_cards["gross_profit"]["canvas"], gross_profit, self.chart_palette[1])
        else:
            self.draw_sparkline(self.dashboard_cards["turnover"]["canvas"], [], self.chart_palette[0])
            self.draw_sparkline(self.dashboard_cards["gross_profit"]["canvas"], [], self.chart_palette[1])
        self.draw_sparkline(self.dashboard_cards["margin_pct"]["canvas"], [], self.chart_palette[2])
        self.draw_sparkline(self.dashboard_cards["stock_value"]["canvas"], [], self.chart_palette[3])

    def _canvas_size(self, canvas: tk.Canvas) -> tuple[int, int]:
        canvas.update_idletasks()
        width = max(int(canvas.winfo_width() or canvas.cget("width")), 200)
        height = max(int(canvas.winfo_height() or canvas.cget("height")), 120)
        return width, height

    def draw_line_chart(self, canvas: tk.Canvas, labels: list[str], series: list[tuple[str, list[float], str]]) -> None:
        canvas.delete("all")
        width, height = self._canvas_size(canvas)
        margin = 40
        if not labels or not any(vals for _, vals, _ in series):
            canvas.create_text(width / 2, height / 2, text="Немає даних", fill="#6b7280")
            return
        max_val = max((max(vals) if vals else 0) for _, vals, _ in series)
        min_val = min((min(vals) if vals else 0) for _, vals, _ in series)
        span = max(max_val - min_val, 1)
        plot_height = height - 2 * margin
        plot_width = width - 2 * margin
        x_step = plot_width / max(len(labels) - 1, 1)
        canvas.create_line(margin, height - margin, width - margin, height - margin, fill="#9ca3af")
        canvas.create_line(margin, margin, margin, height - margin, fill="#9ca3af")
        for i, label in enumerate(labels):
            x = margin + i * x_step
            canvas.create_text(x, height - margin + 12, text=label, anchor="n", font=("Segoe UI", 8))
        for idx, (name, vals, color) in enumerate(series):
            if not vals:
                continue
            points = []
            for i, val in enumerate(vals):
                x = margin + i * x_step
                y = height - margin - ((val - min_val) / span * plot_height)
                points.extend([x, y])
            canvas.create_line(points, fill=color, width=2, smooth=True)
            canvas.create_text(width - margin + 6, margin + 14 * idx, anchor="w", text=name, fill=color)
        canvas.create_text(margin, margin - 10, text=f"макс {max_val:.2f}", anchor="w", fill="#6b7280", font=("Segoe UI", 8))
        canvas.create_text(margin, height - margin + 4, text=f"мін {min_val:.2f}", anchor="w", fill="#6b7280", font=("Segoe UI", 8))

    def draw_pie_chart(self, canvas: tk.Canvas, data: list[tuple[str, float]], title: str) -> None:
        canvas.delete("all")
        width, height = self._canvas_size(canvas)
        total = sum(val for _, val in data)
        if total <= 0:
            canvas.create_text(width / 2, height / 2, text="Немає даних", fill="#6b7280")
            return
        radius = min(width, height) // 4
        cx, cy = width // 3, height // 2
        start_angle = 0.0
        for idx, (label, value) in enumerate(data):
            if value <= 0:
                continue
            extent = value / total * 360
            color = self.chart_palette[idx % len(self.chart_palette)]
            canvas.create_arc(cx - radius, cy - radius, cx + radius, cy + radius, start=start_angle, extent=extent, fill=color, outline="white")
            canvas.create_rectangle(width * 0.6, 20 + idx * 20, width * 0.6 + 12, 20 + idx * 20 + 12, fill=color, outline=color)
            canvas.create_text(width * 0.6 + 16, 20 + idx * 20 + 6, anchor="w", text=f"{label} ({value:.2f})")
            start_angle += extent
        canvas.create_text(cx, 14, text=title, font=("Segoe UI", 10, "bold"))

    def draw_bar_chart(
        self, canvas: tk.Canvas, data: list[tuple[str, float]], title: str = "", bar_color: str | None = None
    ) -> None:
        canvas.delete("all")
        width, height = self._canvas_size(canvas)
        if not data:
            canvas.create_text(width / 2, height / 2, text="Немає даних", fill="#6b7280")
            return
        max_val = max(abs(v) for _, v in data) or 1
        margin = 30
        bar_space = (width - 2 * margin) / max(len(data), 1)
        bar_width = bar_space * 0.6
        for idx, (label, value) in enumerate(data):
            color = bar_color or self.chart_palette[idx % len(self.chart_palette)]
            x0 = margin + idx * bar_space
            x1 = x0 + bar_width
            y_base = height - margin
            y_val = y_base - (abs(value) / max_val) * (height - 2 * margin)
            canvas.create_rectangle(x0, y_val, x1, y_base, fill=color, outline=color)
            canvas.create_text((x0 + x1) / 2, y_val - 8, text=f"{value:.2f}", font=("Segoe UI", 8))
            canvas.create_text((x0 + x1) / 2, height - margin + 12, text=label, font=("Segoe UI", 8))
        if title:
            canvas.create_text(margin, margin - 12, text=title, anchor="w", font=("Segoe UI", 10, "bold"))

    def draw_sparkline(self, canvas: tk.Canvas, values: list[float], color: str) -> None:
        canvas.delete("all")
        width, height = self._canvas_size(canvas)
        if not values:
            canvas.create_text(width / 2, height / 2, text="—", fill="#9ca3af")
            return
        max_val = max(values)
        min_val = min(values)
        span = max(max_val - min_val, 1)
        margin = 6
        plot_width = width - 2 * margin
        plot_height = height - 2 * margin
        x_step = plot_width / max(len(values) - 1, 1)
        points = []
        for i, v in enumerate(values):
            x = margin + i * x_step
            y = height - margin - ((v - min_val) / span * plot_height)
            points.extend([x, y])
        canvas.create_line(points, fill=color, width=2, smooth=True)
