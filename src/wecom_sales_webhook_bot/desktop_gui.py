"""Browser-free local control panel for the sales push bot."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tkinter as tk
from datetime import datetime, timedelta
from pathlib import Path
from tkinter import messagebox, ttk

import yaml

from wecom_sales_webhook_bot.db import create_session_factory, initialize_database
from wecom_sales_webhook_bot.message_template_engine import TemplateRenderError, render_message_template
from wecom_sales_webhook_bot.message_template_service import (
    DEFAULT_TEMPLATE_NAME, TemplateDeleteError, activate_message_template,
    build_preview_template_context, delete_message_template,
    load_or_initialize_message_template_store, save_message_template,
)
from wecom_sales_webhook_bot.rule_models import JobRun, PushRecord, RuleCondition, RuleGroup
from wecom_sales_webhook_bot.rule_service import operators_for_field
from wecom_sales_webhook_bot.sales_fields import FIELD_LABELS, selectable_fields
from wecom_sales_webhook_bot.state_store import PushStateStore


OPERATOR_LABELS = {
    "equals": "等于", "not_equals": "不等于", "contains": "包含", "not_contains": "不包含",
    "in": "属于列表", "not_in": "不属于列表", "starts_with": "开头是", "ends_with": "结尾是",
    "gt": "大于", "gte": "大于等于", "lt": "小于", "lte": "小于等于", "between": "介于",
    "date_between": "日期区间", "between_time": "时段", "before": "早于", "after": "晚于",
    "is_empty": "为空", "is_not_empty": "不为空",
}
OPERATOR_FORMATS = {
    "equals": "精确值", "not_equals": "精确值", "contains": "文本", "not_contains": "文本",
    "in": "值1,值2", "not_in": "值1,值2", "starts_with": "文本", "ends_with": "文本",
    "gt": "数字", "gte": "数字", "lt": "数字", "lte": "数字", "between": "最小值,最大值",
    "date_between": "YYYY-MM-DD,YYYY-MM-DD（结束可留空）", "between_time": "HH:MM,HH:MM",
    "before": "YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS", "after": "YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS",
    "is_empty": "无需填写", "is_not_empty": "无需填写",
}
OPERATOR_CHOICE_TO_KEY = {
    f"{label}（{OPERATOR_FORMATS[key]}）": key for key, label in OPERATOR_LABELS.items()
}


def _operator_choice(operator: str) -> str:
    return next(choice for choice, key in OPERATOR_CHOICE_TO_KEY.items() if key == operator)


def _operator_choices(field_name: str) -> list[str]:
    return [_operator_choice(operator) for operator in operators_for_field(field_name)]
EMS_SERVER_FIELDS = {"store_name", "total_amount", "document_type", "unit_price", "discount", "season", "shipment_group"}
CONDITION_GROUP_LABELS = {"all": "全部满足", "any": "任一满足"}
CONDITION_GROUP_LABEL_TO_KEY = {label: key for key, label in CONDITION_GROUP_LABELS.items()}

def _field_choice(key: str, label: str) -> str:
    location = "EMS服务器筛选" if key in EMS_SERVER_FIELDS else "下载后本地筛选"
    return f"{label} [{key}] [{location}]"

FIELD_CHOICES = [_field_choice(key, label) for key, label, _ in selectable_fields()]
FIELD_FROM_CHOICE = {_field_choice(key, label): key for key, label, _ in selectable_fields()}
FIELD_CHOICE_BY_KEY = {key: _field_choice(key, label) for key, label, _ in selectable_fields()}
FIELD_DROPDOWN_WIDTH = max((len(choice) for choice in FIELD_CHOICES), default=52)


class DesktopApp:
    def __init__(self, root: tk.Tk, config_path: Path) -> None:
        self.root, self.config_path, self.schedule_process = root, config_path, None
        self.raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        root.title("企业微信销售单推送 - 本地控制台")
        root.minsize(980, 680)
        root.protocol("WM_DELETE_WINDOW", self._on_close)
        tabs = ttk.Notebook(root)
        tabs.pack(fill="both", expand=True, padx=10, pady=10)
        self._build_runtime_tab(tabs)
        self._build_webhook_tab(tabs)
        self._build_source_tab(tabs)
        self._build_rules_tab(tabs)
        self._build_templates_tab(tabs)
        self._build_history_tab(tabs)

    def _database_url(self) -> str:
        url = (self.raw.get("backend") or {}).get("database_url")
        if not url:
            raise ValueError("配置文件缺少 backend.database_url")
        return str(url)

    def _factory(self):
        factory = create_session_factory(self._database_url())
        initialize_database(factory)
        # Return an actual SQLAlchemy session.  All callers use this helper
        # as ``with self._factory() as session``; a ``sessionmaker`` factory
        # itself is callable but is not a context manager.
        return factory()

    def _build_runtime_tab(self, tabs) -> None:
        page = ttk.Frame(tabs, padding=16); tabs.add(page, text="运行")
        runtime = self.raw.get("runtime", {})
        fields = {
            "scan_interval_seconds": ("扫描间隔（秒；1200 = 20 分钟）", 1200),
            "max_images_per_message": ("每条消息最多图片数", 8),
            "push_interval_seconds": ("两张销售单推送间隔（秒）", 10),
            "push_window_start": ("每日推送开始（HH:MM）", "10:00"),
            "push_window_end": ("每日推送结束（HH:MM）", "22:00"),
        }
        self.runtime_vars = {key: tk.StringVar(value=str(runtime.get(key, default))) for key, (_, default) in fields.items()}
        self.dry_run = tk.BooleanVar(value=bool(runtime.get("dry_run", True)))
        self.return_whole_order = tk.BooleanVar(value=bool(runtime.get("return_whole_order", True)))
        for row, (key, (label, _)) in enumerate(fields.items()):
            ttk.Label(page, text=label).grid(row=row, column=0, sticky="w", pady=6)
            ttk.Entry(page, textvariable=self.runtime_vars[key], width=28).grid(row=row, column=1, sticky="w", padx=8)
        ttk.Checkbutton(page, text="演练模式（只读取和筛选，不实际推送）", variable=self.dry_run).grid(row=5, column=0, columnspan=2, sticky="w", pady=10)
        ttk.Checkbutton(page, text="返回包含筛选条件的整个销售单", variable=self.return_whole_order).grid(row=6, column=0, columnspan=2, sticky="w", pady=4)
        buttons = ttk.Frame(page); buttons.grid(row=7, column=0, columnspan=2, sticky="w", pady=10)
        ttk.Button(buttons, text="保存运行配置", command=self.save_config).pack(side="left")
        ttk.Button(buttons, text="立即执行一轮", command=lambda: self._run_cli("run-once")).pack(side="left", padx=8)
        ttk.Button(buttons, text="启动持续扫描", command=lambda: self._run_cli("schedule", True)).pack(side="left")
        ttk.Button(buttons, text="停止持续扫描", command=self.stop_schedule).pack(side="left", padx=8)
        self.status = tk.StringVar(value="就绪")
        ttk.Label(page, textvariable=self.status, wraplength=850).grid(row=8, column=0, columnspan=3, sticky="w", pady=20)

    def _build_webhook_tab(self, tabs) -> None:
        page = ttk.Frame(tabs, padding=16); tabs.add(page, text="Webhook")
        ttk.Label(page, text="企业微信群机器人地址（每行一个；每条销售单会发送给全部地址）").pack(anchor="w")
        urls = (self.raw.get("wecom") or {}).get("webhook_urls") or [(self.raw.get("wecom") or {}).get("webhook_url", "")]
        self.webhook_text = tk.Text(page, width=105, height=14); self.webhook_text.pack(fill="x", pady=8); self.webhook_text.insert("1.0", "\n".join(urls))
        ttk.Label(page, text="任一地址发送失败时，该销售单不会标记为已推送，下一轮将补发。真实地址仅保存于 config.local.yaml，不要提交 Git。").pack(anchor="w")
        ttk.Button(page, text="保存 Webhook 配置", command=self.save_config).pack(anchor="w", pady=12)

    def _build_source_tab(self, tabs) -> None:
        page = ttk.Frame(tabs, padding=16); tabs.add(page, text="EMS 登录")
        source = self.raw.get("data_source") or {}
        self.source_kind = tk.StringVar(value=str(source.get("kind", "ems")))
        self.ems_path = tk.StringVar(value=str(source.get("config_path", "./ems_config.json")))
        self.ems_username, self.ems_password = tk.StringVar(), tk.StringVar()
        ttk.Label(page, text="数据源类型").grid(row=0, column=0, sticky="w", pady=6)
        ttk.Combobox(page, values=("ems", "sqlserver", "csv"), textvariable=self.source_kind, state="readonly", width=26).grid(row=0, column=1, sticky="w")
        ttk.Label(page, text="本地 EMS 配置文件").grid(row=1, column=0, sticky="w", pady=6)
        ttk.Entry(page, textvariable=self.ems_path, width=55).grid(row=1, column=1, sticky="w")
        ttk.Button(page, text="读取", command=self._load_ems).grid(row=1, column=2, padx=8)
        ttk.Label(page, text="EMS 账号").grid(row=2, column=0, sticky="w", pady=6)
        ttk.Entry(page, textvariable=self.ems_username, width=28).grid(row=2, column=1, sticky="w")
        ttk.Label(page, text="EMS 密码").grid(row=3, column=0, sticky="w", pady=6)
        ttk.Entry(page, textvariable=self.ems_password, show="*", width=28).grid(row=3, column=1, sticky="w")
        ttk.Button(page, text="保存本地账号配置", command=self._save_ems).grid(row=4, column=0, columnspan=2, sticky="w", pady=12)
        ttk.Label(page, text="账号密码只保存到本机 ems_config.json；EMS 模块只执行已验证的只读登录、初始化和销售详单查询。", wraplength=850).grid(row=5, column=0, columnspan=3, sticky="w")
        self._load_ems(silent=True)

    def _ems_file(self) -> Path:
        path = Path(self.ems_path.get().strip())
        return path if path.is_absolute() else (self.config_path.parent / path).resolve()

    def _load_ems(self, silent: bool = False) -> None:
        try:
            path = self._ems_file()
            if not path.exists():
                if not silent: messagebox.showinfo("尚未配置", f"未找到 {path}；填写账号密码后保存即可创建。")
                return
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.ems_username.set(str(payload.get("username", ""))); self.ems_password.set(str(payload.get("password", "")))
        except Exception as exc:
            if not silent: messagebox.showerror("读取失败", str(exc))

    def _save_ems(self) -> None:
        try:
            path = self._ems_file()
            payload = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
            payload["username"], payload["password"] = self.ems_username.get().strip(), self.ems_password.get()
            path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            source = self.raw.setdefault("data_source", {}); source["kind"], source["config_path"] = self.source_kind.get(), self.ems_path.get().strip()
            self.config_path.write_text(yaml.safe_dump(self.raw, allow_unicode=True, sort_keys=False), encoding="utf-8")
            self.status.set("EMS 本地账号配置已保存")
        except Exception as exc: messagebox.showerror("保存失败", str(exc))

    def _build_rules_tab(self, tabs) -> None:
        page = ttk.Frame(tabs, padding=12); tabs.add(page, text="筛选规则")
        columns = ("name", "enabled", "summary")
        self.rule_tree = ttk.Treeview(page, columns=columns, show="headings", height=18)
        for key, label, width in (("name", "规则名称", 210), ("enabled", "状态", 75), ("summary", "条件（全部 AND；任一 OR）", 650)):
            self.rule_tree.heading(key, text=label); self.rule_tree.column(key, width=width, anchor="w")
        self.rule_tree.pack(fill="both", expand=True); self.rule_tree.bind("<Double-1>", lambda _: self.edit_rule())
        bar = ttk.Frame(page); bar.pack(fill="x", pady=8)
        ttk.Button(bar, text="新建规则", command=self.new_rule).pack(side="left")
        ttk.Button(bar, text="编辑选中规则", command=self.edit_rule).pack(side="left", padx=8)
        ttk.Button(bar, text="删除选中规则", command=self.delete_rule).pack(side="left")
        ttk.Button(bar, text="刷新", command=self.refresh_rules).pack(side="left", padx=8)
        ttk.Label(page, text="所有“全部”条件必须命中；存在“任一”条件时至少命中一项；两组同时成立。商品字段会在订单的任一商品行中匹配。", wraplength=900).pack(anchor="w")
        self.refresh_rules()

    def refresh_rules(self) -> None:
        self.rule_tree.delete(*self.rule_tree.get_children())
        try:
            with self._factory() as session:
                for rule in session.query(RuleGroup).order_by(RuleGroup.updated_at.desc()).all():
                    conditions = session.query(RuleCondition).filter_by(rule_group_id=rule.id).all()
                    summary = "；".join(f"{'全部' if c.condition_group == 'all' else '任一'}：{FIELD_LABELS.get(c.field_name, c.field_name)} {OPERATOR_LABELS.get(c.operator, c.operator)} {c.value_json}" for c in conditions)
                    self.rule_tree.insert("", "end", iid=str(rule.id), values=(rule.name, "启用" if rule.is_enabled else "停用", summary))
        except Exception as exc: self.status.set(f"规则读取失败：{exc}")

    def new_rule(self) -> None: self._rule_dialog()

    def edit_rule(self) -> None:
        selected = self.rule_tree.selection()
        if not selected: messagebox.showinfo("请选择规则", "请先选中一条规则。"); return
        with self._factory() as session:
            rule = session.get(RuleGroup, int(selected[0]))
            if rule: self._rule_dialog(rule, session.query(RuleCondition).filter_by(rule_group_id=rule.id).all())

    def _rule_dialog(self, existing: RuleGroup | None = None, conditions: list[RuleCondition] | None = None) -> None:
        dialog = tk.Toplevel(self.root); dialog.title("编辑筛选规则" if existing else "新建筛选规则"); dialog.geometry("1380x620")
        dialog.minsize(1180, 520)
        dialog.columnconfigure(1, weight=1)
        dialog.columnconfigure(2, weight=1)
        dialog.rowconfigure(2, weight=1)
        name, enabled = tk.StringVar(value=existing.name if existing else ""), tk.BooleanVar(value=existing.is_enabled if existing else True)
        ttk.Label(dialog, text="规则名称").grid(row=0, column=0, padx=12, pady=8, sticky="w")
        ttk.Entry(dialog, textvariable=name, width=42).grid(row=0, column=1, sticky="ew", padx=8)
        ttk.Checkbutton(dialog, text="启用", variable=enabled).grid(row=0, column=2, sticky="w", padx=8)
        headers = (
            ("条件组", 0, "w"),
            ("EMS销售详单字段（括号内为字段类型）", 1, "w"),
            ("运算符（括号内为输入格式）", 2, "w"),
            ("值", 3, "w"),
        )
        for title, col, anchor in headers:
            ttk.Label(dialog, text=title).grid(row=1, column=col, padx=8, pady=(8, 4), sticky=anchor)
        frame = ttk.Frame(dialog)
        frame.grid(row=2, column=0, columnspan=4, sticky="nsew", padx=4)
        frame.columnconfigure(1, weight=1)
        frame.columnconfigure(2, weight=1)
        rows: list[dict] = []
        def add_row(group="all", choice=FIELD_CHOICES[0], operator=None, value=""):
            line = ttk.Frame(frame); line.pack(fill="x", pady=3)
            group_var = tk.StringVar(value=CONDITION_GROUP_LABELS.get(group, group))
            field_var = tk.StringVar(value=choice)
            key = FIELD_FROM_CHOICE.get(choice, "order_no")
            operator_var = tk.StringVar(value=_operator_choice(operator or operators_for_field(key)[0]))
            ttk.Combobox(line, values=tuple(CONDITION_GROUP_LABELS.values()), textvariable=group_var, width=12, state="readonly").pack(side="left", padx=4)
            field_box = ttk.Combobox(
                line,
                values=FIELD_CHOICES,
                width=52,
                state="readonly",
            )
            field_box.configure(postcommand=lambda box=field_box: box.configure(width=max(52, FIELD_DROPDOWN_WIDTH)))
            field_box.pack(side="left", padx=4, fill="x", expand=True)
            op_box = ttk.Combobox(line, values=_operator_choices(key), textvariable=operator_var, width=42, state="readonly")
            op_box.pack(side="left", padx=4, fill="x", expand=True)
            entry = ttk.Entry(line, width=34); entry.insert(0, value); entry.pack(side="left", padx=4, fill="x", expand=True)
            row = {"line": line, "group": group_var, "field": field_var, "operator": operator_var, "entry": entry}
            def update(*_):
                selected_key = FIELD_FROM_CHOICE.get(field_var.get(), "order_no")
                allowed = operators_for_field(selected_key)
                choices = _operator_choices(selected_key)
                op_box["values"] = choices
                if OPERATOR_CHOICE_TO_KEY.get(operator_var.get()) not in allowed: operator_var.set(choices[0])
            field_var.trace_add("write", update)
            update()
            ttk.Button(line, text="删除", command=lambda: (line.destroy(), rows.remove(row))).pack(side="left"); rows.append(row)
        for c in conditions or []:
            label = FIELD_LABELS.get(c.field_name, c.field_name); choice = FIELD_CHOICE_BY_KEY.get(c.field_name, FIELD_CHOICES[0])
            add_row(c.condition_group or "all", choice if choice in FIELD_FROM_CHOICE else FIELD_CHOICES[0], c.operator, c.value_json)
        if not rows:
            add_row("all", FIELD_CHOICE_BY_KEY["store_name"], "in")
            add_row("any", FIELD_CHOICE_BY_KEY["performance_org"], "in")
        ttk.Button(dialog, text="增加条件", command=add_row).grid(row=3, column=0, sticky="w", padx=8, pady=12)
        ttk.Label(
            dialog,
            text="日期筛选示例：选择“销售日期” + “日期区间（YYYY-MM-DD,YYYY-MM-DD）”，填写 2026-09-18, 表示从 2026-09-18 起（含当天）；填写 2026-09-18,2026-09-30 表示闭区间。",
            wraplength=780,
        ).grid(row=4, column=0, columnspan=4, sticky="w", padx=8)
        def save():
            if not name.get().strip(): messagebox.showerror("无法保存", "请填写规则名称"); return
            payloads = []
            for row in rows:
                op, value = OPERATOR_CHOICE_TO_KEY[row["operator"].get()], row["entry"].get().strip()
                if op not in {"is_empty", "is_not_empty"} and not value: continue
                field = FIELD_FROM_CHOICE[row["field"].get()]
                payloads.append((CONDITION_GROUP_LABEL_TO_KEY.get(row["group"].get(), "all"), field, op, value))
            if not payloads: messagebox.showerror("无法保存", "至少填写一条有效条件，避免无条件推送全部销售单。"); return
            try:
                with self._factory() as session:
                    target = session.get(RuleGroup, existing.id) if existing else None
                    if target is None: target = RuleGroup(name=name.get().strip(), is_enabled=enabled.get(), match_mode="all", updated_by="desktop"); session.add(target); session.flush()
                    else: target.name, target.is_enabled, target.match_mode, target.updated_by = name.get().strip(), enabled.get(), "all", "desktop"; session.query(RuleCondition).filter_by(rule_group_id=target.id).delete()
                    for group, field, op, value in payloads: session.add(RuleCondition(rule_group_id=target.id, field_name=field, operator=op, condition_group=group, value_json=value))
                    session.commit()
                dialog.destroy(); self.refresh_rules()
            except Exception as exc: messagebox.showerror("保存失败", str(exc))
        ttk.Button(dialog, text="保存规则", command=save).grid(row=3, column=3, sticky="e", padx=8, pady=12)

    def delete_rule(self) -> None:
        selected = self.rule_tree.selection()
        if not selected or not messagebox.askyesno("确认", "删除选中的规则？"): return
        with self._factory() as session:
            for item in selected:
                session.query(RuleCondition).filter_by(rule_group_id=int(item)).delete()
                rule = session.get(RuleGroup, int(item))
                if rule: session.delete(rule)
            session.commit()
        self.refresh_rules()

    def _build_templates_tab(self, tabs) -> None:
        page = ttk.Frame(tabs, padding=12); tabs.add(page, text="消息模板")
        bar = ttk.Frame(page); bar.pack(fill="x")
        ttk.Label(bar, text="模板").pack(side="left"); self.template_choice = tk.StringVar()
        self.template_box = ttk.Combobox(bar, textvariable=self.template_choice, width=42, state="readonly"); self.template_box.pack(side="left", padx=8); self.template_box.bind("<<ComboboxSelected>>", lambda _: self._load_template())
        ttk.Button(bar, text="新建", command=self._new_template).pack(side="left"); ttk.Button(bar, text="启用选中", command=self._activate_template).pack(side="left", padx=8); ttk.Button(bar, text="删除选中", command=self._delete_template).pack(side="left")
        row = ttk.Frame(page); row.pack(fill="x", pady=8); ttk.Label(row, text="模板名称").pack(side="left"); self.template_name = tk.StringVar(); ttk.Entry(row, textvariable=self.template_name, width=45).pack(side="left", padx=8); ttk.Button(row, text="保存模板", command=self._save_template).pack(side="left")
        self.template_text = tk.Text(page, width=110, height=20, undo=True); self.template_text.pack(fill="both", expand=True)
        ttk.Button(page, text="预览", command=self._preview_template).pack(anchor="w", pady=8)
        self.template_store = {}; self._refresh_templates()

    def _refresh_templates(self) -> None:
        try:
            with self._factory() as session: self.template_store = load_or_initialize_message_template_store(session)
            items = self.template_store["templates"]; active = self.template_store["active_template_id"]
            self.template_box["values"] = [f"{x['name']} [{'启用' if x['id'] == active else '未启用'}]" for x in items]
            self.template_box.current(next(i for i, x in enumerate(items) if x["id"] == active)); self._load_template()
        except Exception as exc: self.status.set(f"模板读取失败：{exc}")

    def _selected_template(self):
        index = self.template_box.current(); items = self.template_store.get("templates", [])
        return items[index] if index >= 0 and index < len(items) else None
    def _load_template(self) -> None:
        item = self._selected_template()
        if item: self.template_name.set(item["name"]); self.template_text.delete("1.0", "end"); self.template_text.insert("1.0", item["template_body"])
    def _new_template(self) -> None: self.template_box.set(""); self.template_name.set(DEFAULT_TEMPLATE_NAME); self.template_text.delete("1.0", "end")
    def _save_template(self) -> None:
        try:
            item = self._selected_template()
            with self._factory() as session: save_message_template(session, template_id=item["id"] if item else None, template_name=self.template_name.get(), template_body=self.template_text.get("1.0", "end-1c"), preset_key="standard", activate=bool(item and item["id"] == self.template_store.get("active_template_id")))
            self._refresh_templates(); self.status.set("消息模板已保存")
        except Exception as exc: messagebox.showerror("保存失败", str(exc))
    def _activate_template(self) -> None:
        item = self._selected_template()
        if not item: return
        with self._factory() as session: activate_message_template(session, item["id"])
        self._refresh_templates()
    def _delete_template(self) -> None:
        item = self._selected_template()
        if not item or not messagebox.askyesno("确认", "删除选中的模板？"): return
        try:
            with self._factory() as session: delete_message_template(session, item["id"])
            self._refresh_templates()
        except TemplateDeleteError as exc: messagebox.showinfo("无法删除", str(exc))
    def _preview_template(self) -> None:
        try:
            text = render_message_template(self.template_text.get("1.0", "end-1c"), build_preview_template_context()).text
            dialog = tk.Toplevel(self.root); dialog.title("模板预览"); box = tk.Text(dialog, width=100, height=28); box.pack(fill="both", expand=True, padx=10, pady=10); box.insert("1.0", text); box.configure(state="disabled")
        except TemplateRenderError as exc: messagebox.showerror("模板错误", str(exc))

    def _build_history_tab(self, tabs) -> None:
        page = ttk.Frame(tabs, padding=12); tabs.add(page, text="推送记录与状态")
        controls = ttk.Frame(page); controls.pack(fill="x")
        ttk.Button(controls, text="刷新状态与最近记录", command=self.refresh_history).pack(side="left")
        ttk.Button(controls, text="全选当前记录", command=self.select_all_records).pack(side="left", padx=8)
        ttk.Button(controls, text="删除选中并允许重新推送", command=self.delete_selected_records).pack(side="left")
        ttk.Button(controls, text="清空全部推送状态", command=self.clear_all_push_state).pack(side="left", padx=8)
        date_bar = ttk.Frame(page); date_bar.pack(fill="x", pady=(10, 0))
        ttk.Label(date_bar, text="重新读取起始日期（YYYY-MM-DD）：").pack(side="left")
        self.rescan_start_date = tk.StringVar(value=str((self.raw.get("runtime") or {}).get("rescan_start_date") or datetime.now().date().isoformat()))
        ttk.Entry(date_bar, textvariable=self.rescan_start_date, width=16).pack(side="left", padx=6)
        ttk.Button(date_bar, text="保存日期", command=self.save_rescan_start_date).pack(side="left", padx=4)
        ttk.Label(date_bar, text="删除记录后会从此日期重新读取；删除后点击“立即执行一轮”才会重新推送。清空全部前请务必设置合适的起始日期。", wraplength=650).pack(side="left", padx=8)
        self.history_status = tk.StringVar(value="点击刷新以查看最近执行情况"); ttk.Label(page, textvariable=self.history_status, wraplength=900).pack(anchor="w", pady=10)
        columns = ("time", "order", "store", "amount", "rule", "status", "error"); self.record_tree = ttk.Treeview(page, columns=columns, show="headings", height=18)
        for key, label, width in (("time", "时间", 135), ("order", "销售单号", 150), ("store", "销售机构", 100), ("amount", "金额", 80), ("rule", "规则", 130), ("status", "状态", 80), ("error", "错误", 260)): self.record_tree.heading(key, text=label); self.record_tree.column(key, width=width, anchor="w")
        self.record_tree.pack(fill="both", expand=True); self.refresh_history()
    def refresh_history(self) -> None:
        self.record_tree.delete(*self.record_tree.get_children())
        try:
            with self._factory() as session:
                latest = session.query(JobRun).order_by(JobRun.created_at.desc()).first(); rows = session.query(PushRecord).order_by(PushRecord.created_at.desc()).limit(50).all()
                self.history_status.set(f"最近扫描：{(latest.created_at + timedelta(hours=8)):%Y-%m-%d %H:%M:%S}；状态 {latest.status}；成功 {latest.success_count}；失败 {latest.failed_count}。" if latest else "尚未执行扫描任务。")
                for row in rows: self.record_tree.insert("", "end", iid=str(row.id), values=(row.created_at + timedelta(hours=8), row.order_no, row.store_name, f"{row.total_amount:.2f}", row.rule_name, row.status, row.error_message or ""))
        except Exception as exc: self.history_status.set(f"读取记录失败：{exc}")

    def _state_file(self) -> Path:
        configured = str((self.raw.get("runtime") or {}).get("state_file", "./var/push-state.json"))
        path = Path(configured)
        return path if path.is_absolute() else (self.config_path.parent / path).resolve()

    def save_rescan_start_date(self) -> None:
        try:
            value = self.rescan_start_date.get().strip()
            datetime.strptime(value, "%Y-%m-%d")
            self.raw.setdefault("runtime", {})["rescan_start_date"] = value
            self.config_path.write_text(yaml.safe_dump(self.raw, allow_unicode=True, sort_keys=False), encoding="utf-8")
            self.history_status.set(f"重推起始日期已保存：{value}")
        except ValueError:
            messagebox.showerror("日期格式错误", "请输入 YYYY-MM-DD，例如 2026-09-19")
        except Exception as exc:
            messagebox.showerror("保存日期失败", str(exc))

    def _rescan_from(self) -> datetime:
        try:
            return datetime.strptime(self.rescan_start_date.get().strip(), "%Y-%m-%d")
        except ValueError as exc:
            raise ValueError("重新读取起始日期必须填写 YYYY-MM-DD，例如 2026-09-18") from exc

    def select_all_records(self) -> None:
        self.record_tree.selection_set(self.record_tree.get_children())

    def delete_selected_records(self) -> None:
        selected = self.record_tree.selection()
        if not selected:
            messagebox.showinfo("请选择记录", "请先选择需要允许重新推送的销售单；也可以点击“全选当前记录”。")
            return
        try:
            rescan_from = self._rescan_from()
            if not messagebox.askyesno("确认重新推送", f"删除 {len(selected)} 条推送记录，并从 {rescan_from:%Y-%m-%d} 重新读取销售单？\n\n删除后请点击“立即执行一轮”或等待下一次扫描。"):
                return
            with self._factory() as session:
                records = session.query(PushRecord).filter(PushRecord.id.in_([int(item) for item in selected])).all()
                order_nos = [record.order_no for record in records]
                session.query(PushRecord).filter(PushRecord.id.in_([int(item) for item in selected])).delete(synchronize_session=False)
                session.commit()
            state = PushStateStore(self._state_file())
            state.remove_orders(order_nos)
            state.set_last_scan_at(rescan_from)
            self.refresh_history()
            self.history_status.set(f"已删除 {len(order_nos)} 条记录；下一轮将从 {rescan_from:%Y-%m-%d} 重新读取。")
        except Exception as exc:
            messagebox.showerror("无法删除记录", str(exc))

    def clear_all_push_state(self) -> None:
        try:
            rescan_from = self._rescan_from()
            if not messagebox.askyesno("高风险确认", f"将删除全部推送记录并清空全部已推送标记，下一轮会从 {rescan_from:%Y-%m-%d} 重新推送所有符合当前规则的销售单。\n\n这通常会产生大量重复消息，确认继续？"):
                return
            with self._factory() as session:
                session.query(PushRecord).delete()
                session.commit()
            state = PushStateStore(self._state_file())
            state.clear()
            state.set_last_scan_at(rescan_from)
            self.refresh_history()
            self.history_status.set(f"已清空全部推送状态；下一轮将从 {rescan_from:%Y-%m-%d} 重新读取。")
        except Exception as exc:
            messagebox.showerror("无法清空推送状态", str(exc))

    def save_config(self) -> bool:
        try:
            runtime = self.raw.setdefault("runtime", {})
            for key, var in self.runtime_vars.items(): runtime[key] = int(var.get()) if key.endswith("seconds") or key == "max_images_per_message" else var.get().strip()
            runtime["dry_run"] = self.dry_run.get()
            runtime["return_whole_order"] = self.return_whole_order.get()
            urls = [x.strip() for x in self.webhook_text.get("1.0", "end").splitlines() if x.strip()]
            if not urls: raise ValueError("至少填写一个 Webhook 地址")
            wecom = self.raw.setdefault("wecom", {}); wecom.pop("webhook_url", None); wecom["webhook_urls"] = urls
            self.config_path.write_text(yaml.safe_dump(self.raw, allow_unicode=True, sort_keys=False), encoding="utf-8"); self.status.set("配置已保存；持续扫描需重启后加载新配置。"); return True
        except Exception as exc: messagebox.showerror("保存失败", str(exc)); return False
    def _run_cli(self, command: str, keep: bool = False) -> None:
        if not self.save_config(): return
        args = [sys.executable, "-u", "-m", "wecom_sales_webhook_bot.cli", command, "--config", str(self.config_path)]
        env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1])}
        if keep:
            if self.schedule_process and self.schedule_process.poll() is None: self.status.set("持续扫描已经在运行。"); return
            self.schedule_process = subprocess.Popen(args, cwd=self.config_path.parent, env=env, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)); self.status.set("持续扫描已启动。")
        else: subprocess.Popen(args, cwd=self.config_path.parent, env=env, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)); self.status.set("已启动单次扫描；完成后刷新记录查看结果。")
    def stop_schedule(self) -> None:
        if self.schedule_process and self.schedule_process.poll() is None: self.schedule_process.terminate(); self.status.set("持续扫描已停止。")
        else: self.status.set("此窗口未启动持续扫描进程。")
    def _on_close(self) -> None:
        if self.schedule_process and self.schedule_process.poll() is None and not messagebox.askyesno("持续扫描仍在运行", "关闭窗口不会停止扫描。确定关闭吗？"): return
        self.root.destroy()


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--config", required=True); args = parser.parse_args()
    root = tk.Tk(); DesktopApp(root, Path(args.config).resolve()); root.mainloop()


if __name__ == "__main__":
    main()
