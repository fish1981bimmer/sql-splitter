#!/usr/bin/env python3
"""
SQL 拆分工具 - GUI 界面
提供图形化界面进行 SQL 文件拆分操作 — 社区版
"""
import sys
import os
import tkinter as tk
from tkinter import filedialog, ttk, messagebox, scrolledtext

try:
    from split_sql_v21 import split_sql_file, SQLDialect
    from dm_converter import DMConverter
except ImportError:
    from .split_sql_v21 import split_sql_file, SQLDialect
    from .dm_converter import DMConverter


class SQLSplitterGUI:
    """SQL拆分工具 GUI - 社区版"""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("SQL Splitter - 社区版")
        self.root.geometry("600x440")
        self._build_ui()

    def _build_ui(self):
        frm = ttk.LabelFrame(self.root, text="输入", padding=8)
        frm.pack(fill=tk.X, padx=8, pady=4)

        row1 = ttk.Frame(frm); row1.pack(fill=tk.X, pady=2)
        ttk.Label(row1, text="SQL文件:").pack(side=tk.LEFT)
        self.input_var = tk.StringVar()
        ttk.Entry(row1, textvariable=self.input_var, width=45).pack(side=tk.LEFT, padx=4, fill=tk.X, expand=True)
        ttk.Button(row1, text="浏览...", command=self._browse_input).pack(side=tk.RIGHT)

        row2 = ttk.Frame(frm); row2.pack(fill=tk.X, pady=2)
        ttk.Label(row2, text="输出目录:").pack(side=tk.LEFT)
        self.output_var = tk.StringVar()
        ttk.Entry(row2, textvariable=self.output_var, width=45).pack(side=tk.LEFT, padx=4, fill=tk.X, expand=True)
        ttk.Button(row2, text="浏览...", command=self._browse_output).pack(side=tk.RIGHT)

        opt = ttk.Frame(frm); opt.pack(fill=tk.X, pady=2)
        ttk.Label(opt, text="方言:").pack(side=tk.LEFT)
        self.dialect_var = tk.StringVar(value='auto')
        ttk.Combobox(opt, textvariable=self.dialect_var,
                     values=['auto','sqlserver','oracle','mysql','postgresql','dm'],
                     state='readonly', width=12).pack(side=tk.LEFT, padx=4)
        self.convert_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(opt, text="转换为达梦语法", variable=self.convert_var).pack(side=tk.LEFT, padx=12)

        btn_frm = ttk.Frame(self.root); btn_frm.pack(fill=tk.X, padx=8, pady=4)
        self.run_btn = ttk.Button(btn_frm, text="开始拆分+转换", command=self._run)
        self.run_btn.pack(side=tk.LEFT, padx=4)
        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(btn_frm, textvariable=self.status_var).pack(side=tk.RIGHT, padx=4)

        self.log_text = scrolledtext.ScrolledText(self.root, height=12, font=("Menlo", 11))
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)
        ttk.Label(self.root, text="社区版 | 开源免费", foreground="gray").pack(pady=2)

    def _browse_input(self):
        p = filedialog.askopenfilename(filetypes=[("SQL", "*.sql"), ("All", "*.*")])
        if p:
            self.input_var.set(p)
            if not self.output_var.get():
                self.output_var.set(os.path.splitext(p)[0] + '_split')

    def _browse_output(self):
        p = filedialog.askdirectory()
        if p: self.output_var.set(p)

    def _log(self, msg):
        self.log_text.insert(tk.END, msg + '\n')
        self.log_text.see(tk.END)
        self.root.update_idletasks()

    def _run(self):
        inp = self.input_var.get().strip()
        out = self.output_var.get().strip()
        if not inp:
            messagebox.showwarning("提示", "请选择SQL文件"); return
        if not out:
            out = os.path.splitext(inp)[0] + '_split'
        if not os.path.isfile(inp):
            messagebox.showerror("错误", f"文件不存在: {inp}"); return
        self.run_btn.config(state='disabled')
        self.status_var.set("处理中...")
        self.log_text.delete('1.0', tk.END)
        try:
            self._do_split(inp, out)
        except Exception as e:
            self._log(f"错误: {e}")
        finally:
            self.run_btn.config(state='normal')
            self.status_var.set("就绪")

    def _do_split(self, inp, out):
        dialect_str = self.dialect_var.get()
        dialect = None
        if dialect_str != 'auto':
            try: dialect = SQLDialect[dialect_str.upper()]
            except: pass
        self._log(f"输入: {inp}")
        self._log(f"输出: {out}")
        result = split_sql_file(inp, out, dialect=dialect, verbose=False)
        if not result.success:
            self._log("拆分失败"); return
        self._log(f"拆分完成: {result.total} 个对象")
        for t, c in sorted(result.stats.items()):
            self._log(f"  {t}: {c}")
        if self.convert_var.get():
            dm_dir = out + '_dm'
            os.makedirs(dm_dir, exist_ok=True)
            converter = DMConverter()
            schema_prefix = os.path.basename(out).replace('_split', '')
            ok = err = 0
            type_map = {'proc':'procedure','func':'function','trig':'trigger',
                        'view':'view','table':'table','idx':'index','uidx':'index',
                        'con':'constraint','seq':'sequence'}
            for f in sorted(os.listdir(out)):
                if not f.endswith('.sql') or f == 'merge_all.sql': continue
                obj_type = f.split('_')[0]
                with open(os.path.join(out, f), 'r', encoding='utf-8') as fh: content = fh.read()
                try:
                    converted = converter.convert(content, type_map.get(obj_type,'generic'), schema_prefix=schema_prefix)
                    with open(os.path.join(dm_dir, f), 'w', encoding='utf-8') as fh: fh.write(converted.converted)
                    ok += 1
                    self._log(f"  {f}")
                except Exception as e:
                    err += 1
                    self._log(f"  {f}: {str(e)[:50]}")
            self._log(f"转换完成: {ok}成功 {err}失败 -> {dm_dir}")


def run_gui():
    root = tk.Tk()
    SQLSplitterGUI(root)
    root.mainloop()

if __name__ == '__main__':
    run_gui()
