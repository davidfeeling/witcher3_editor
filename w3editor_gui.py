"""
Editor de partidas de The Witcher 3 (Remaster / next-gen) - interfaz grafica.
Ejecutar con:  python w3editor_gui.py   (o con ABRIR_EDITOR_WITCHER3.cmd)
"""
import os
import sys
import traceback
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from w3save import W3Save, SaveFormatError, CURRENCIES, MAX_QTY      # noqa: E402
from w3comun import (saves_dir, list_saves, game_running, apply_changes, backup_manager,  # noqa: E402
                     load_config, save_config)
from w3traduccion import Translations, find_game_dir                                     # noqa: E402

TITLE = 'Editor de partidas - The Witcher 3 (Remaster)'


def fmt_change(c):
    return '%s:  %s  ->  %s' % (c['campo'], c['antes'], c['despues'])


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(TITLE)
        self.geometry('1280x800')
        self.minsize(1000, 640)
        self.mgr = backup_manager()
        self.folder = saves_dir()
        self.save = None
        self.saves = []
        self.photo = None
        self.item_sort = None
        self.card_sort = None
        self.tr = Translations()
        self._build()
        self.refresh_saves()
        self.after(300, self.check_game)
        if not self.tr.juego:
            self.after(800, lambda: self.regen_translations(silent=True))

    def report_callback_exception(self, exc, val, tb):
        txt = ''.join(traceback.format_exception(exc, val, tb))
        try:
            with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'errores.log'), 'a',
                      encoding='utf-8') as f:
                f.write(txt + '\n')
        except OSError:
            pass
        messagebox.showerror(TITLE, 'Error inesperado (no se ha guardado nada a medias):\n\n%s' % txt[-1500:])

    # ------------------------------------------------------------------ interfaz
    def _build(self):
        style = ttk.Style(self)
        try:
            style.theme_use('vista')
        except tk.TclError:
            pass
        style.configure('Big.TButton', font=('Segoe UI', 10, 'bold'), padding=6)
        style.configure('Warn.TLabel', foreground='#8a4b00', background='#fff3cd', padding=6)
        style.configure('Val.TLabel', font=('Segoe UI', 10, 'bold'))

        self.banner = ttk.Label(self, style='Warn.TLabel', text='')

        main = ttk.PanedWindow(self, orient='horizontal')
        self.main_pane = main
        main.pack(fill='both', expand=True, padx=6, pady=6)

        # --- izquierda: partidas
        left = ttk.Frame(main)
        main.add(left, weight=1)
        ttk.Label(left, text='Partidas', font=('Segoe UI', 11, 'bold')).pack(anchor='w')
        self.lbl_folder = ttk.Label(left, text='', foreground='#555', wraplength=380)
        self.lbl_folder.pack(anchor='w', pady=(0, 4))
        bar = ttk.Frame(left)
        bar.pack(fill='x')
        ttk.Button(bar, text='Actualizar', command=self.refresh_saves).pack(side='left')
        ttk.Button(bar, text='Cambiar carpeta...', command=self.choose_folder).pack(side='left', padx=4)
        cols = ('fecha', 'tipo', 'nombre')
        self.tv_saves = ttk.Treeview(left, columns=cols, show='headings', selectmode='browse')
        for c, w, t in (('fecha', 130, 'Fecha'), ('tipo', 90, 'Tipo'), ('nombre', 200, 'Archivo')):
            self.tv_saves.heading(c, text=t)
            self.tv_saves.column(c, width=w, stretch=(c == 'nombre'))
        sb = ttk.Scrollbar(left, orient='vertical', command=self.tv_saves.yview)
        self.tv_saves.configure(yscrollcommand=sb.set)
        self.tv_saves.pack(side='left', fill='both', expand=True, pady=4)
        sb.pack(side='left', fill='y', pady=4)
        self.tv_saves.bind('<<TreeviewSelect>>', self.on_select_save)

        # --- derecha
        right = ttk.Frame(main)
        main.add(right, weight=3)

        info = ttk.Frame(right)
        info.pack(fill='x')
        self.lbl_img = ttk.Label(info)
        self.lbl_img.pack(side='left', padx=(0, 10))
        grid = ttk.Frame(info)
        grid.pack(side='left', fill='x', expand=True)
        self.info_vars = {}
        fields = [('partida', 'Partida'), ('coronas', 'Coronas'), ('orenos', 'Orens / Florines'),
                  ('nivel', 'Nivel'), ('xp', 'Experiencia'), ('sp', 'Puntos de habilidad'),
                  ('objetos', 'Objetos en inventario'), ('cartas', 'Cartas de Gwynt')]
        for r, (k, t) in enumerate(fields):
            ttk.Label(grid, text=t + ':').grid(row=r, column=0, sticky='w')
            v = tk.StringVar(value='-')
            ttk.Label(grid, textvariable=v, style='Val.TLabel').grid(row=r, column=1, sticky='w', padx=6)
            self.info_vars[k] = v

        nb = ttk.Notebook(right)
        nb.pack(fill='both', expand=True, pady=6)
        self.nb = nb
        self._build_tab_money(nb)
        self._build_tab_inventory(nb)
        self._build_tab_gwint(nb)

        # --- cambios pendientes
        pend = ttk.LabelFrame(right, text='Cambios pendientes (aún NO guardados en la partida)')
        pend.pack(fill='x')
        self.lb_pending = tk.Listbox(pend, height=5, font=('Consolas', 10))
        self.lb_pending.pack(side='left', fill='both', expand=True, padx=4, pady=4)
        pb = ttk.Frame(pend)
        pb.pack(side='left', fill='y', padx=4, pady=4)
        ttk.Button(pb, text='Quitar seleccionado', command=self.remove_pending).pack(fill='x')
        ttk.Button(pb, text='Descartar todos', command=self.discard_pending).pack(fill='x', pady=4)
        self.btn_save = ttk.Button(pb, text='GUARDAR EN LA PARTIDA\n(con copia de seguridad)',
                                   style='Big.TButton', command=self.do_save)
        self.btn_save.pack(fill='x', pady=(8, 0))

        # --- barra inferior
        bottom = ttk.Frame(self)
        bottom.pack(fill='x', padx=6, pady=(0, 6))
        ttk.Button(bottom, text='Gestor de copias de seguridad / histórico',
                   command=lambda: BackupWindow(self)).pack(side='left')
        ttk.Button(bottom, text='Copia completa de TODAS las partidas ahora',
                   command=self.backup_all).pack(side='left', padx=6)
        self.status = ttk.Label(bottom, text='', foreground='#555')
        self.status.pack(side='left', padx=10)

    def _build_tab_money(self, nb):
        tab = ttk.Frame(nb, padding=10)
        nb.add(tab, text='Dinero y experiencia')
        self.money_entries = {}
        r = 0
        ttk.Label(tab, text='Monedas (máximo %d)' % MAX_QTY, font=('Segoe UI', 10, 'bold')).grid(
            row=r, column=0, columnspan=4, sticky='w')
        for key in CURRENCIES:
            r += 1
            ttk.Label(tab, text=self.tr.label(key) + ':').grid(row=r, column=0, sticky='w', pady=2)
            e = ttk.Entry(tab, width=12)
            e.grid(row=r, column=1, sticky='w', padx=4)
            self.money_entries[key] = e
            f = ttk.Frame(tab)
            f.grid(row=r, column=2, sticky='w')
            for inc in (1000, 5000, 10000):
                ttk.Button(f, text='+%d' % inc, width=7,
                           command=lambda k=key, n=inc: self.bump_entry(self.money_entries[k], n)).pack(side='left', padx=1)
        r += 1
        ttk.Label(tab, text='Orens y florines son monedas de otros reinos: se cambian por coronas en el banco '
                            'de Novigrado.', foreground='#555').grid(row=r, column=0, columnspan=4, sticky='w', pady=(2, 10))

        r += 1
        ttk.Label(tab, text='Experiencia (experimental)', font=('Segoe UI', 10, 'bold')).grid(
            row=r, column=0, columnspan=4, sticky='w', pady=(6, 0))
        r += 1
        ttk.Label(tab, text='XP acumulada en el nivel:').grid(row=r, column=0, sticky='w')
        self.e_xp = ttk.Entry(tab, width=12)
        self.e_xp.grid(row=r, column=1, sticky='w', padx=4)
        f = ttk.Frame(tab)
        f.grid(row=r, column=2, sticky='w')
        for n in (1, 3, 5):
            ttk.Button(f, text='Preparar +%d nivel%s' % (n, 'es' if n > 1 else ''),
                       command=lambda n=n: self.prepare_levels(n)).pack(side='left', padx=1)
        r += 1
        self.lbl_xp_help = ttk.Label(tab, text='', foreground='#555', wraplength=760, justify='left')
        self.lbl_xp_help.grid(row=r, column=0, columnspan=4, sticky='w', pady=(2, 8))
        r += 1
        ttk.Label(tab, text='Puntos de habilidad libres:').grid(row=r, column=0, sticky='w')
        self.e_sp = ttk.Entry(tab, width=12)
        self.e_sp.grid(row=r, column=1, sticky='w', padx=4)
        r += 1
        self.lbl_sp_help = ttk.Label(tab, text='', foreground='#555', wraplength=760, justify='left')
        self.lbl_sp_help.grid(row=r, column=0, columnspan=4, sticky='w', pady=(2, 8))
        r += 1
        ttk.Button(tab, text='Añadir a cambios pendientes', style='Big.TButton',
                   command=self.stage_money).grid(row=r, column=0, columnspan=3, sticky='w', pady=10)

    def _build_tab_inventory(self, nb):
        tab = ttk.Frame(nb, padding=6)
        nb.add(tab, text='Inventario (duplicar objetos)')
        top = ttk.Frame(tab)
        top.pack(fill='x')
        ttk.Label(top, text='Buscar:').pack(side='left')
        self.v_search = tk.StringVar()
        self.v_search.trace_add('write', lambda *a: self.fill_items())
        ttk.Entry(top, textvariable=self.v_search, width=30).pack(side='left', padx=4)
        self.v_only_stack = tk.BooleanVar(value=False)
        ttk.Checkbutton(top, text='Ocultar equipo (armas/armaduras)', variable=self.v_only_stack,
                        command=self.fill_items).pack(side='left', padx=8)
        ttk.Button(top, text='Regenerar traducciones desde el juego',
                   command=self.regen_translations).pack(side='right')
        ttk.Label(top, text='Doble clic en un objeto para corregir su traducción', foreground='#777').pack(side='left')

        mid = ttk.Frame(tab)
        mid.pack(fill='both', expand=True, pady=4)
        cols = ('es', 'nombre', 'cantidad', 'durabilidad', 'tipo', 'runas')
        self.tv_items = ttk.Treeview(mid, columns=cols, show='headings', selectmode='extended')
        for c, w, t in (('es', 280, 'Nombre en español'), ('nombre', 220, 'Nombre interno'),
                        ('cantidad', 110, 'Cantidad'), ('durabilidad', 110, 'Durabilidad'), ('tipo', 80, 'Tipo'),
                        ('runas', 260, 'Runas / glifos')):
            self.tv_items.heading(c, text=t, command=lambda c=c: self.sort_items(c))
            self.tv_items.column(c, width=w, stretch=(c in ('es', 'nombre', 'runas')))
        self.tv_items.bind('<Double-1>', self.edit_translation)
        sb = ttk.Scrollbar(mid, orient='vertical', command=self.tv_items.yview)
        self.tv_items.configure(yscrollcommand=sb.set)
        self.tv_items.pack(side='left', fill='both', expand=True)
        sb.pack(side='left', fill='y')
        self.tv_items.tag_configure('changed', background='#fff3cd')

        ctl = ttk.Frame(tab)
        ctl.pack(fill='x')
        ttk.Label(ctl, text='Seleccionados ->  Cantidad:').pack(side='left')
        self.e_qty = ttk.Entry(ctl, width=8)
        self.e_qty.pack(side='left', padx=4)
        ttk.Button(ctl, text='Fijar', command=lambda: self.items_qty('set')).pack(side='left')
        ttk.Button(ctl, text='Duplicar (x2)', command=lambda: self.items_qty('x2')).pack(side='left', padx=4)
        ttk.Button(ctl, text='+10', command=lambda: self.items_qty('+10')).pack(side='left')
        ttk.Separator(ctl, orient='vertical').pack(side='left', fill='y', padx=10)
        ttk.Button(ctl, text='Reparar seleccionados', command=lambda: self.repair(False)).pack(side='left')
        ttk.Button(ctl, text='Reparar todo el equipo', command=lambda: self.repair(True)).pack(side='left', padx=4)

    def _build_tab_gwint(self, nb):
        tab = ttk.Frame(nb, padding=6)
        nb.add(tab, text='Cartas de Gwynt')

        top = ttk.Frame(tab)
        top.pack(fill='x')
        ttk.Label(top, text='Buscar:').pack(side='left')
        self.v_search_card = tk.StringVar()
        self.v_search_card.trace_add('write', lambda *a: self.fill_cards())
        ttk.Entry(top, textvariable=self.v_search_card, width=24).pack(side='left', padx=4)

        ttk.Label(top, text='Facción:').pack(side='left', padx=(6, 2))
        self.v_faction_filter = tk.StringVar(value='Todas')
        cb_fac = ttk.Combobox(top, textvariable=self.v_faction_filter, state='readonly', width=18,
                              values=('Todas', 'Neutral', 'Reinos del Norte', 'Nilfgaard', "Scoia'tael", 'Monstruos', 'Skellige'))
        cb_fac.pack(side='left', padx=4)
        cb_fac.bind('<<ComboboxSelected>>', lambda *a: self.fill_cards())

        self.v_hide_leaders = tk.BooleanVar(value=False)
        ttk.Checkbutton(top, text='Ocultar líderes', variable=self.v_hide_leaders,
                        command=self.fill_cards).pack(side='left', padx=8)

        self.lbl_cards_count = ttk.Label(top, text='', foreground='#555')
        self.lbl_cards_count.pack(side='right')

        mid = ttk.Frame(tab)
        mid.pack(fill='both', expand=True, pady=4)
        cols = ('es', 'copias', 'poder', 'faccion', 'tipo', 'nombre', 'idx')
        self.tv_cards = ttk.Treeview(mid, columns=cols, show='headings', selectmode='extended')
        for c, w, t in (('es', 290, 'Nombre de la carta'), ('copias', 90, 'Copias'),
                        ('poder', 70, 'Fuerza'), ('faccion', 130, 'Facción'),
                        ('tipo', 90, 'Tipo'), ('nombre', 170, 'Nombre interno'),
                        ('idx', 60, 'ID')):
            self.tv_cards.heading(c, text=t, command=lambda c=c: self.sort_cards(c))
            self.tv_cards.column(c, width=w, stretch=(c in ('es', 'nombre')))
        sb = ttk.Scrollbar(mid, orient='vertical', command=self.tv_cards.yview)
        self.tv_cards.configure(yscrollcommand=sb.set)
        self.tv_cards.pack(side='left', fill='both', expand=True)
        sb.pack(side='left', fill='y')
        self.tv_cards.tag_configure('changed', background='#fff3cd')

        ctl = ttk.Frame(tab)
        ctl.pack(fill='x')
        ttk.Label(ctl, text='Seleccionadas ->  Copias:').pack(side='left')
        self.e_card_copies = ttk.Entry(ctl, width=6)
        self.e_card_copies.pack(side='left', padx=4)
        ttk.Button(ctl, text='Fijar', command=lambda: self.cards_copies('set')).pack(side='left')
        ttk.Button(ctl, text='+1 copia', command=lambda: self.cards_copies('+1')).pack(side='left', padx=4)
        ttk.Button(ctl, text='Duplicar (x2)', command=lambda: self.cards_copies('x2')).pack(side='left')
        ttk.Separator(ctl, orient='vertical').pack(side='left', fill='y', padx=10)
        ttk.Button(ctl, text='Fijar a 3', command=lambda: self.cards_copies('set', 3)).pack(side='left')
        ttk.Button(ctl, text='Fijar a 1', command=lambda: self.cards_copies('set', 1)).pack(side='left', padx=4)

    # ------------------------------------------------------------------ partidas
    def check_game(self):
        if game_running():
            self.banner.configure(text='El juego está ABIERTO. Puedes editar, pero despues carga la partida '
                                       'desde "Cargar partida" del menú (no basta con seguir jugando). '
                                       'Lo más seguro es editar con el juego en el menú principal o cerrado.')
            self.banner.pack(fill='x', before=self.main_pane)
        else:
            self.banner.pack_forget()
        self.after(15000, self.check_game)

    def refresh_saves(self):
        self.lbl_folder.configure(text=self.folder)
        self.saves = list_saves(self.folder)
        sel = self.save.path if self.save else None
        self.tv_saves.delete(*self.tv_saves.get_children())
        for k, s in enumerate(self.saves):
            self.tv_saves.insert('', 'end', iid=str(k),
                                 values=(s['fecha'].strftime('%Y-%m-%d %H:%M'), s['tipo'], s['nombre']))
            if s['ruta'] == sel:
                self.tv_saves.selection_set(str(k))
                self.tv_saves.see(str(k))
        self.status.configure(text='%d partidas en la carpeta' % len(self.saves))

    def choose_folder(self):
        d = filedialog.askdirectory(initialdir=self.folder, title='Carpeta gamesaves de The Witcher 3')
        if d:
            self.folder = d
            cfg = load_config(); cfg['carpeta_partidas'] = d; save_config(cfg)
            self.refresh_saves()

    def on_select_save(self, _evt=None):
        sel = self.tv_saves.selection()
        if not sel:
            return
        s = self.saves[int(sel[0])]
        if self.save and s['ruta'] == self.save.path:
            return
        if self.save and self.save.changes:
            if not messagebox.askyesno(TITLE, 'Hay cambios sin guardar en la partida actual. ¿Descartarlos?'):
                return
        self.load_save(s['ruta'])

    def load_save(self, path):
        self.config(cursor='watch'); self.update()
        try:
            self.save = W3Save(path)
        except SaveFormatError as e:
            self.save = None
            self.clear_info(os.path.basename(path), str(e))
            return
        except Exception as e:
            self.save = None
            self.clear_info(os.path.basename(path), 'Error leyendo la partida: %s' % e)
            traceback.print_exc()
            return
        finally:
            self.config(cursor='')
        self.show_info()

    def clear_info(self, name, msg):
        for v in self.info_vars.values():
            v.set('-')
        self.info_vars['partida'].set(name)
        self.info_vars['coronas'].set(msg)
        self.tv_items.delete(*self.tv_items.get_children())
        self.tv_cards.delete(*self.tv_cards.get_children())
        self.lb_pending.delete(0, 'end')
        self.lbl_img.configure(image='')

    def show_info(self):
        s = self.save
        s.label = self.tr.label          # descripciones de cambios con el nombre en espanol
        png = s.path[:-4] + '.png'
        try:
            self.photo = tk.PhotoImage(file=png) if os.path.exists(png) else None
        except tk.TclError:
            self.photo = None
        self.lbl_img.configure(image=self.photo or '')
        sm = s.summary()
        li = s.level
        self.info_vars['partida'].set(os.path.basename(s.path)[:-4])
        self.info_vars['coronas'].set(str(sm['Crowns']))
        self.info_vars['orenos'].set('%s / %s' % (sm['Orens'] if sm['Orens'] is not None else '-',
                                                  sm['Florens'] if sm['Florens'] is not None else '-'))
        if li:
            nxt = li.next_level_total()
            self.info_vars['nivel'].set(str(li.level))
            self.info_vars['xp'].set('%d total  (%d en este nivel; el nivel %d llega a %s)' % (
                li.xp_total, li.xp_free, (li.level or 0) + 1, nxt if nxt else '?'))
            self.info_vars['sp'].set('%d libres, %d gastados' % (li.sp_free, li.sp_used))
        self.info_vars['objetos'].set(str(sm['objetos']))
        self.info_vars['cartas'].set(str(len(s.cards)))
        for key, e in self.money_entries.items():
            it = s.item_by_name(key)
            e.configure(state='normal'); e.delete(0, 'end')
            if it:
                e.insert(0, str(it.qty))
            else:
                e.configure(state='disabled')
        self.e_xp.configure(state='normal'); self.e_xp.delete(0, 'end')
        self.e_sp.configure(state='normal'); self.e_sp.delete(0, 'end')
        if li and li.xp_free_off is not None:
            self.e_xp.insert(0, str(li.xp_free))
            self.lbl_xp_help.configure(text=(
                'Es la XP ganada dentro del nivel actual (base %d). El nivel NO sube al cargar: sube la próxima vez '
                'que ganes experiencia (matar un monstruo, completar una misión...). Cada nivel da 1 punto de '
                'habilidad. "Preparar +N niveles" deja la XP justo en el umbral.' % li.xp_used))
        else:
            self.e_xp.configure(state='disabled')
            self.lbl_xp_help.configure(text='La experiencia no es editable en esta partida.')
        if li and li.sp_free_off is not None:
            self.e_sp.insert(0, str(li.sp_free))
            self.lbl_sp_help.configure(text='Puntos sin gastar. Se pueden cambiar directamente.')
        else:
            self.e_sp.insert(0, '0')
            self.e_sp.configure(state='disabled')
            self.lbl_sp_help.configure(text=(
                'Tienes 0 puntos libres y el juego no guarda el dato cuando vale 0, así que no se puede editar '
                'sin reescribir la estructura del archivo (arriesgado). Alternativa segura: usa "Preparar +N '
                'niveles" de la experiencia.'))
        self.fill_items()
        self.fill_cards()
        self.fill_pending()

    # ------------------------------------------------------------------ inventario
    def _pending_value(self, key, default):
        c = self.save.changes.get(key)
        return c['new'] if c else default

    def fill_items(self):
        if not self.save:
            return
        q = self.v_search.get().strip().lower()
        hide_eq = self.v_only_stack.get()
        items = list(self.save.items)
        if self.item_sort:
            col, rev = self.item_sort
            keyf = {'es': lambda it: self.tr.label(it.name).lower(),
                    'nombre': lambda it: it.name.lower(), 'cantidad': lambda it: it.qty,
                    'durabilidad': lambda it: it.dur, 'tipo': lambda it: it.kind(),
                    'runas': lambda it: ','.join(it.runes)}[col]
            items.sort(key=keyf, reverse=rev)
        self.tv_items.delete(*self.tv_items.get_children())
        for it in items:
            es = self.tr.get(it.name)
            if q and q not in it.name.lower() and q not in es.lower():
                continue
            if hide_eq and it.is_equipment:
                continue
            nq = self._pending_value(('qty', it.qty_off), it.qty)
            nd = self._pending_value(('dur', it.dur_off), round(it.dur, 2))
            qty_txt = str(it.qty) if nq == it.qty else '%d -> %d' % (it.qty, nq)
            if it.dur < 0:
                dur_txt = ''
            else:
                dur_txt = '%.1f' % it.dur if nd == round(it.dur, 2) else '%.1f -> %.1f' % (it.dur, nd)
            tags = ('changed',) if (nq != it.qty or (it.dur >= 0 and nd != round(it.dur, 2))) else ()
            self.tv_items.insert('', 'end', iid=str(it.index), tags=tags,
                                 values=(es or '(sin traducción)', it.name, qty_txt, dur_txt, it.kind(),
                                         ', '.join(self.tr.label(r) for r in it.runes)))

    def edit_translation(self, event):
        row = self.tv_items.identify_row(event.y)
        if not row or not self.save:
            return
        it = self.save.items[int(row)]
        game = self.tr.juego.get(it.name, '')
        txt = simpledialog.askstring(
            'Traducción', 'Nombre en español para "%s"\n(oficial del juego: %s)\n\n'
            'Déjalo vacío para volver al nombre oficial.' % (it.name, game or 'no tiene'),
            initialvalue=self.tr.get(it.name), parent=self)
        if txt is None:
            return
        self.tr.set_manual(it.name, '' if txt.strip() == game else txt)
        self.fill_items()

    def regen_translations(self, silent=False):
        gd = find_game_dir(load_config())
        if not gd:
            if silent:
                self.status.configure(text='Sin traducciones: no se encontró la instalación del juego')
                return
            gd = filedialog.askdirectory(title='Carpeta de instalación de The Witcher 3')
            if not gd:
                return
        self.config(cursor='watch'); self.update()
        try:
            n = self.tr.regenerate(gd)
        except Exception as e:
            self.config(cursor='')
            if not silent:
                messagebox.showerror(TITLE, 'No se pudieron extraer las traducciones:\n%s' % e)
            return
        self.config(cursor='')
        cfg = load_config(); cfg['carpeta_juego'] = gd; save_config(cfg)
        self.fill_items()
        msg = '%d nombres oficiales en español extraídos del juego (%s).' % (n, gd)
        self.status.configure(text=msg)
        if not silent:
            messagebox.showinfo(TITLE, msg + '\n\nTus correcciones manuales se conservan.')

    def sort_items(self, col):
        if self.item_sort and self.item_sort[0] == col:
            self.item_sort = (col, not self.item_sort[1])
        else:
            self.item_sort = (col, col in ('cantidad', 'durabilidad'))
        self.fill_items()

    def selected_items(self):
        return [self.save.items[int(i)] for i in self.tv_items.selection()]

    def items_qty(self, mode):
        if not self.save:
            return
        items = self.selected_items()
        if not items:
            messagebox.showinfo(TITLE, 'Selecciona uno o varios objetos de la lista (Ctrl+clic para varios).')
            return
        if mode == 'set':
            try:
                val = int(self.e_qty.get())
            except ValueError:
                messagebox.showerror(TITLE, 'Escribe una cantidad numérica.')
                return
        eq = [self.tr.label(it.name) for it in items if it.is_equipment]
        if eq and not messagebox.askyesno(TITLE, (
                'EXPERIMENTAL: estos objetos son equipo (no apilable):\n\n  %s\n\n'
                'Poner cantidad mayor que 1 en equipo puede comportarse de forma rara en el juego. '
                'Si algo va mal, restaura la copia de seguridad.\n\n¿Continuar?') % '\n  '.join(eq[:15])):
            return
        errors = []
        for it in items:
            cur = self._pending_value(('qty', it.qty_off), it.qty)
            new = val if mode == 'set' else (cur * 2 if mode == 'x2' else cur + 10)
            new = min(new, MAX_QTY)
            try:
                self.save.set_qty(it, new)
            except ValueError as e:
                errors.append('%s: %s' % (it.name, e))
        if errors:
            messagebox.showerror(TITLE, '\n'.join(errors[:20]))
        self.after_change()

    def repair(self, all_items):
        if not self.save:
            return
        items = [it for it in (self.save.items if all_items else self.selected_items()) if it.dur >= 0]
        if not items:
            messagebox.showinfo(TITLE, 'No hay equipo con durabilidad en la selección.')
            return
        for it in items:
            if round(it.dur, 2) < 100:
                self.save.set_durability(it, 100.0)
        self.after_change()

    # ------------------------------------------------------------------ cartas de gwynt
    def fill_cards(self):
        if not self.save:
            return
        q = self.v_search_card.get().strip().lower()
        fac_filter = self.v_faction_filter.get()
        hide_leaders = self.v_hide_leaders.get()
        cards = list(self.save.cards)

        if self.card_sort:
            col, rev = self.card_sort
            keyf = {
                'es': lambda c: self.tr.card_info(c.card_index).get('nombre_es', '').lower(),
                'copias': lambda c: self._pending_value(('card', c.copies_off), c.copies) if c.copies_off else c.copies,
                'poder': lambda c: self.tr.card_info(c.card_index).get('power', 0),
                'faccion': lambda c: self.tr.card_info(c.card_index).get('faction', '').lower(),
                'tipo': lambda c: ('Líder' if c.is_leader else ('Héroe' if self.tr.card_info(c.card_index).get('is_hero') else 'Tropa')),
                'nombre': lambda c: self.tr.card_info(c.card_index).get('internal_name', '').lower(),
                'idx': lambda c: c.card_index
            }[col]
            cards.sort(key=keyf, reverse=rev)

        self.tv_cards.delete(*self.tv_cards.get_children())
        shown = 0
        for c in cards:
            info = self.tr.card_info(c.card_index)
            nombre_es = info.get('nombre_es', f'Carta #{c.card_index}')
            internal = info.get('internal_name', '')
            faccion = info.get('faction', 'Neutral')
            power = info.get('power', 0)
            is_hero = info.get('is_hero', False)

            if hide_leaders and c.is_leader:
                continue
            if fac_filter != 'Todas' and faccion.lower() != fac_filter.lower():
                continue
            if q and (q not in nombre_es.lower() and q not in internal.lower() and q not in faccion.lower()):
                continue

            tipo = 'Líder' if c.is_leader else ('Héroe' if is_hero else ('Especial' if power == 0 else 'Tropa'))
            nc = self._pending_value(('card', c.copies_off), c.copies) if c.copies_off else c.copies
            copies_txt = str(c.copies) if nc == c.copies else f'{c.copies} -> {nc}'
            tags = ('changed',) if (c.copies_off and nc != c.copies) else ()

            self.tv_cards.insert('', 'end', iid=str(c.card_index), tags=tags,
                                 values=(nombre_es, copies_txt, power if not c.is_leader else '-',
                                         faccion, tipo, internal, c.card_index))
            shown += 1
        self.lbl_cards_count.configure(text=f'{shown} de {len(cards)} cartas en colección')

    def sort_cards(self, col):
        if self.card_sort and self.card_sort[0] == col:
            self.card_sort = (col, not self.card_sort[1])
        else:
            self.card_sort = (col, col in ('copias', 'poder', 'idx'))
        self.fill_cards()

    def selected_cards(self):
        if not self.save:
            return []
        res = []
        for iid in self.tv_cards.selection():
            c = self.save.card_by_index(int(iid))
            if c:
                res.append(c)
        return res

    def cards_copies(self, mode, fixed_val=None):
        if not self.save:
            return
        cards = self.selected_cards()
        if not cards:
            messagebox.showinfo(TITLE, 'Selecciona una o varias cartas de la lista.')
            return

        if fixed_val is not None:
            val = fixed_val
        elif mode == 'set':
            try:
                val = int(self.e_card_copies.get())
            except ValueError:
                messagebox.showerror(TITLE, 'Escribe un número de copias válido.')
                return

        errors = []
        for c in cards:
            if c.copies_off is None:
                errors.append(f'La carta #{c.card_index} (líder) no tiene campo editable de copias.')
                continue
            cur = self._pending_value(('card', c.copies_off), c.copies)
            new_val = val if mode == 'set' else (cur * 2 if mode == 'x2' else cur + 1)
            new_val = max(1, min(new_val, 99))
            info = self.tr.card_info(c.card_index)
            name_label = info.get('nombre_es', f'#{c.card_index}')
            try:
                self.save.set_card_copies(c, new_val, label=name_label)
            except ValueError as ex:
                errors.append(f'{name_label}: {ex}')

        if errors:
            messagebox.showerror(TITLE, '\n'.join(errors[:15]))
        self.after_change()

    # ------------------------------------------------------------------ dinero/xp
    def bump_entry(self, e, n):
        if str(e.cget('state')) == 'disabled':
            return
        try:
            v = int(e.get() or 0)
        except ValueError:
            v = 0
        e.delete(0, 'end'); e.insert(0, str(min(v + n, MAX_QTY)))

    def prepare_levels(self, n):
        li = self.save.level if self.save else None
        if not li or li.xp_free_off is None:
            return
        target = li.required_total.get((li.level or 0) + n)
        if target is None:
            messagebox.showerror(TITLE, 'No hay definición para el nivel %d.' % ((li.level or 0) + n))
            return
        self.e_xp.delete(0, 'end')
        self.e_xp.insert(0, str(target - li.xp_used))

    def stage_money(self):
        if not self.save:
            return
        errors = []
        for key, e in self.money_entries.items():
            it = self.save.item_by_name(key)
            if not it:
                continue
            try:
                self.save.set_qty(it, int(e.get()))
            except ValueError as ex:
                errors.append('%s: %s' % (self.tr.label(key), ex))
        li = self.save.level
        if li and li.xp_free_off is not None:
            try:
                self.save.set_xp_free(int(self.e_xp.get()))
            except ValueError as ex:
                errors.append('Experiencia: %s' % ex)
        if li and li.sp_free_off is not None:
            try:
                self.save.set_skill_points_free(int(self.e_sp.get()))
            except ValueError as ex:
                errors.append('Puntos de habilidad: %s' % ex)
        if errors:
            messagebox.showerror(TITLE, '\n'.join(errors))
        self.after_change()

    # ------------------------------------------------------------------ pendientes
    def after_change(self):
        self.fill_items()
        self.fill_cards()
        self.fill_pending()

    def fill_pending(self):
        self.lb_pending.delete(0, 'end')
        self._pending_keys = []
        if not self.save:
            return
        for key, c in self.save.changes.items():
            self.lb_pending.insert('end', fmt_change(dict(campo=c['desc'], antes=c['old'], despues=c['new'])))
            self._pending_keys.append(key)
        n = len(self.save.changes)
        self.status.configure(text='%d cambio(s) pendiente(s)' % n if n else 'Sin cambios pendientes')

    def remove_pending(self):
        sel = self.lb_pending.curselection()
        if sel and self.save:
            self.save.changes.pop(self._pending_keys[sel[0]], None)
            self.after_change()
            self.show_info()

    def discard_pending(self):
        if self.save and self.save.changes:
            self.save.changes.clear()
            self.show_info()

    def do_save(self):
        if not self.save or not self.save.changes:
            messagebox.showinfo(TITLE, 'No hay cambios pendientes.')
            return
        lines = '\n'.join('  - ' + fmt_change(c) for c in self.save.change_list())
        extra = ''
        if game_running():
            extra = ('\n\nEl juego está abierto: cuando termine, carga ESTA partida desde el menú "Cargar partida" '
                     'para ver los cambios.')
        if not messagebox.askyesno(TITLE, 'Se va a modificar:\n%s\n\n%s\n\nAntes se hara una copia de seguridad '
                                          'automática (se puede restaurar desde el gestor).%s\n\n¿Guardar?'
                                   % (os.path.basename(self.save.path), lines, extra)):
            return
        self.config(cursor='watch'); self.update()
        try:
            manifest, reloaded = apply_changes(self.save, self.mgr)
        except Exception as e:
            self.config(cursor='')
            traceback.print_exc()
            messagebox.showerror(TITLE, 'NO se ha guardado.\n\n%s' % e)
            return
        self.config(cursor='')
        self.save = reloaded
        self.show_info()
        self.refresh_saves()
        messagebox.showinfo(TITLE, 'Partida guardada y verificada.\n\nCopia de seguridad previa:\n%s\n\n'
                                   'Si el juego no la carga bien, restáurala desde "Gestor de copias".'
                            % manifest['id'])

    def backup_all(self):
        if not os.path.isdir(self.folder):
            return
        self.config(cursor='watch'); self.update()
        try:
            m = self.mgr.backup_all(self.folder)
        except Exception as e:
            messagebox.showerror(TITLE, 'Error en la copia: %s' % e)
            return
        finally:
            self.config(cursor='')
        messagebox.showinfo(TITLE, 'Copia completa creada (%d archivos):\n%s' % (len(m['archivos']), m['id']))


class BackupWindow(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.mgr = app.mgr
        self.title('Copias de seguridad e histórico')
        self.geometry('1150x620')
        nb = ttk.Notebook(self)
        nb.pack(fill='both', expand=True, padx=6, pady=6)

        # --- copias
        t1 = ttk.Frame(nb, padding=6)
        nb.add(t1, text='Copias de seguridad')
        cols = ('fecha', 'partida', 'tipo', 'motivo', 'cambios')
        self.tv = ttk.Treeview(t1, columns=cols, show='headings', selectmode='browse', height=12)
        for c, w, t in (('fecha', 140, 'Fecha'), ('partida', 280, 'Partida'), ('tipo', 80, 'Tipo'),
                        ('motivo', 260, 'Motivo'), ('cambios', 340, 'Cambios que se hicieron después')):
            self.tv.heading(c, text=t)
            self.tv.column(c, width=w, stretch=(c in ('cambios', 'motivo')))
        self.tv.pack(fill='both', expand=True)
        self.tv.bind('<<TreeviewSelect>>', self.on_sel)
        self.txt = tk.Text(t1, height=9, font=('Consolas', 9), wrap='none')
        self.txt.pack(fill='x', pady=4)
        bar = ttk.Frame(t1)
        bar.pack(fill='x')
        ttk.Button(bar, text='Restaurar esta copia', command=self.restore).pack(side='left')
        ttk.Button(bar, text='Verificar integridad', command=self.verify).pack(side='left', padx=4)
        ttk.Button(bar, text='Abrir carpeta', command=self.open_folder).pack(side='left')
        ttk.Button(bar, text='Borrar copia', command=self.delete).pack(side='left', padx=4)
        ttk.Button(bar, text='Actualizar', command=self.fill).pack(side='right')

        # --- historico
        t2 = ttk.Frame(nb, padding=6)
        nb.add(t2, text='Histórico de operaciones')
        cols = ('fecha', 'accion', 'partida', 'detalle')
        self.tv_h = ttk.Treeview(t2, columns=cols, show='headings')
        for c, w, t in (('fecha', 150, 'Fecha'), ('accion', 130, 'Acción'), ('partida', 280, 'Partida'),
                        ('detalle', 560, 'Detalle')):
            self.tv_h.heading(c, text=t)
            self.tv_h.column(c, width=w, stretch=(c == 'detalle'))
        sb = ttk.Scrollbar(t2, orient='vertical', command=self.tv_h.yview)
        self.tv_h.configure(yscrollcommand=sb.set)
        self.tv_h.pack(side='left', fill='both', expand=True)
        sb.pack(side='left', fill='y')
        self.fill()

    def fill(self):
        self.backups = self.mgr.list_backups()
        self.tv.delete(*self.tv.get_children())
        for k, m in enumerate(self.backups):
            ch = '; '.join(fmt_change(c) for c in m.get('cambios', []))
            self.tv.insert('', 'end', iid=str(k), values=(m['fecha'].replace('T', ' '), m['partida'],
                                                         m['tipo'], m['motivo'], ch))
        self.tv_h.delete(*self.tv_h.get_children())
        for e in reversed(self.mgr.history()):
            det = ''
            if e.get('cambios'):
                det = '; '.join(fmt_change(c) for c in e['cambios'])
            elif e.get('motivo'):
                det = e['motivo']
            if e.get('copia_previa'):
                det += '   [copia previa: %s]' % e['copia_previa']
            if e.get('accion') == 'backup_completo':
                det = '%s archivos - %s' % (e.get('archivos'), e.get('motivo', ''))
            self.tv_h.insert('', 'end', values=(e['fecha'].replace('T', ' '), e['accion'],
                                                e.get('partida', ''), det))

    def current(self):
        sel = self.tv.selection()
        return self.backups[int(sel[0])] if sel else None

    def on_sel(self, _e=None):
        m = self.current()
        self.txt.delete('1.0', 'end')
        if not m:
            return
        lines = ['Copia:   %s' % m['id'], 'Origen:  %s' % m['carpeta_origen'], 'Motivo:  %s' % m['motivo']]
        if m.get('resumen'):
            r = m['resumen']
            lines.append('Estado guardado: coronas=%s  orenos=%s  florines=%s  nivel=%s  xp=%s' % (
                r.get('Crowns'), r.get('Orens'), r.get('Florens'), r.get('nivel'), r.get('xp_total')))
        for c in m.get('cambios', []):
            lines.append('Cambio aplicado después: ' + fmt_change(c))
        lines.append('Archivos: ' + ', '.join(a['nombre'] for a in m['archivos'][:6]) +
                     (' ... (%d)' % len(m['archivos']) if len(m['archivos']) > 6 else ''))
        self.txt.insert('1.0', '\n'.join(lines))

    def restore(self):
        m = self.current()
        if not m:
            return
        if m['tipo'] == 'completa':
            q = ('Restaurar la copia COMPLETA %s\n(%d archivos) en:\n%s\n\nSe sobrescriben las partidas con el mismo '
                 'nombre (las creadas después no se borran). Antes se copiará lo que hay ahora.\n\n¿Continuar?'
                 % (m['id'], len(m['archivos']), m['carpeta_origen']))
        else:
            q = ('¿Restaurar la partida %s a como estaba el %s?\n\nAntes se hara una copia de la version actual, '
                 'así que esta acción también se puede deshacer.' % (m['partida'], m['fecha'].replace('T', ' ')))
        if not messagebox.askyesno('Restaurar', q, parent=self):
            return
        try:
            pre = self.mgr.restore(m['id'])
        except Exception as e:
            messagebox.showerror('Restaurar', 'Error: %s' % e, parent=self)
            return
        messagebox.showinfo('Restaurar', 'Restaurado y verificado.%s' % (
            '\nCopia de la versión anterior: %s' % pre['id'] if pre else ''), parent=self)
        self.fill()
        app = self.app
        if app.save and os.path.basename(app.save.path) in [a['nombre'] for a in m['archivos']]:
            app.load_save(app.save.path)
        app.refresh_saves()

    def verify(self):
        m = self.current()
        if not m:
            return
        bad = self.mgr.verify(m['id'])
        if bad:
            messagebox.showerror('Verificar', 'Archivos dañados o ausentes:\n' + '\n'.join(bad), parent=self)
        else:
            messagebox.showinfo('Verificar', 'Copia intacta (%d archivos, SHA-256 correcto).' % len(m['archivos']),
                                parent=self)

    def open_folder(self):
        m = self.current()
        os.startfile(m['_ruta'] if m else self.mgr.backup_dir)

    def delete(self):
        m = self.current()
        if not m:
            return
        if messagebox.askyesno('Borrar', '¿Borrar definitivamente la copia %s?' % m['id'], parent=self):
            self.mgr.delete(m['id'])
            self.fill()


def main():
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    App().mainloop()


if __name__ == '__main__':
    main()
