"""
Editor de partidas de The Witcher 3 - linea de comandos.

  python w3cli.py listar
  python w3cli.py info ultima [--objetos]
  python w3cli.py cambiar ultima --coronas 5000 [--orenos N] [--florines N] [--xp N]
                          [--cantidad "Nombre=N" ...] [--reparar] [--si]
  python w3cli.py copias
  python w3cli.py historial
  python w3cli.py restaurar <id_copia> [--si]
  python w3cli.py copia-completa

<partida> puede ser "ultima", el nombre (sin .sav) o la ruta completa.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from w3save import W3Save, SaveFormatError, CURRENCIES      # noqa: E402
from w3backup import BackupManager                          # noqa: E402
from w3traduccion import Translations                       # noqa: E402
import w3comun                                              # noqa: E402

try:
    sys.stdout.reconfigure(errors='replace')
except Exception:
    pass


def resolve(folder, ref):
    if os.path.isfile(ref):
        return ref
    saves = w3comun.list_saves(folder)
    if ref == 'ultima':
        for s in saves:
            try:
                W3Save(s['ruta'])
                return s['ruta']
            except SaveFormatError:
                continue
        sys.exit('No hay partidas compatibles en %s' % folder)
    for s in saves:
        if s['nombre'] == ref or s['nombre'] == ref.replace('.sav', ''):
            return s['ruta']
    sys.exit('No se encuentra la partida %s' % ref)


def confirm(args, msg):
    if args.si:
        return True
    return input(msg + ' [s/N] ').strip().lower() in ('s', 'si', 'y')


def cmd_listar(args, mgr):
    for s in w3comun.list_saves(args.carpeta):
        try:
            sm = W3Save(s['ruta']).summary()
            txt = 'coronas=%-6s nivel=%-3s xp=%s' % (sm['Crowns'], sm.get('nivel'), sm.get('xp_total'))
        except SaveFormatError as e:
            txt = '(no compatible: %s)' % str(e).split('.')[0]
        print('%s  %-42s %s' % (s['fecha'].strftime('%Y-%m-%d %H:%M'), s['nombre'], txt))


def cmd_info(args, mgr):
    s = W3Save(resolve(args.carpeta, args.partida))
    li = s.level
    print('Partida:  ', os.path.basename(s.path))
    print('Inventario localizado por:', s.inv_method, 'offset 0x%x' % s.inv_offset)
    for k, v in CURRENCIES.items():
        it = s.item_by_name(k)
        print('%-10s %s' % (v + ':', it.qty if it else '-'))
    if li:
        print('Nivel:     %s   XP total %d (%d en el nivel, siguiente nivel en %s)' % (
            li.level, li.xp_total, li.xp_free, li.next_level_total()))
        print('Habilidad: %d libres (%s), %d gastados' % (
            li.sp_free, 'editable' if li.sp_free_off else 'no editable', li.sp_used))
    print('Objetos:  ', len(s.items))
    print('Cartas Gwynt:', len(s.cards))
    if args.objetos:
        tr = Translations()
        for it in s.items:
            print('  %-40s %-32s x%-6d %-8s %s %s' % (
                tr.get(it.name, '-')[:40], it.name[:32], it.qty, it.kind(),
                ('dur %.1f' % it.dur) if it.dur >= 0 else '',
                ('runas: ' + ', '.join(tr.label(r) for r in it.runes)) if it.runes else ''))
    if getattr(args, 'cartas', False):
        tr = Translations()
        for c in s.cards:
            info = tr.card_info(c.card_index)
            lbl = info.get('nombre_es', f'Carta #{c.card_index}')
            tipo = 'Lider' if c.is_leader else ('Heroe' if info.get('is_hero') else 'Tropa')
            print('  %-40s #%-4d x%-3d poder=%-2s faccion=%-16s tipo=%s' % (
                lbl[:40], c.card_index, c.copies, info.get('power', 0) if not c.is_leader else '-',
                info.get('faction', 'Neutral')[:16], tipo))


def find_item(s, tr, name):
    """Busca por nombre interno o por nombre en espanol (sin distinguir mayusculas)."""
    it = s.item_by_name(name)
    if it:
        return it
    low = name.strip().lower()
    hits = [it for it in s.items if tr.get(it.name).lower() == low]
    if len({h.name for h in hits}) > 1:
        sys.exit('"%s" es ambiguo: %s' % (name, ', '.join(sorted({h.name for h in hits}))))
    return hits[0] if hits else None


def find_card(s, tr, name_or_id):
    """Busca una carta de Gwynt por su indice, nombre oficial o interno."""
    name_or_id = name_or_id.strip()
    if name_or_id.isdigit():
        return s.card_by_index(int(name_or_id))
    low = name_or_id.lower()
    for c in s.cards:
        info = tr.card_info(c.card_index)
        if info.get('internal_name', '').lower() == low:
            return c
        if info.get('nombre_es', '').lower() == low:
            return c
    # Busqueda parcial
    hits = []
    for c in s.cards:
        info = tr.card_info(c.card_index)
        if low in info.get('nombre_es', '').lower() or low in info.get('internal_name', '').lower():
            hits.append(c)
    if len(hits) == 1:
        return hits[0]
    if len(hits) > 1:
        names = [tr.card_info(h.card_index).get('nombre_es', str(h.card_index)) for h in hits]
        sys.exit('Carta "%s" es ambigua: %s' % (name_or_id, ', '.join(names[:5])))
    return None


def cmd_cambiar(args, mgr):
    s = W3Save(resolve(args.carpeta, args.partida))
    tr = Translations()
    s.label = tr.label
    for key, val in (('Crowns', args.coronas), ('Orens', args.orenos), ('Florens', args.florines)):
        if val is not None:
            it = s.item_by_name(key)
            if not it:
                sys.exit('La partida no tiene %s' % CURRENCIES[key])
            s.set_qty(it, val)
    if args.xp is not None:
        s.set_xp_free(args.xp)
    for spec in args.cantidad or []:
        name, _, val = spec.rpartition('=')
        it = find_item(s, tr, name)
        if not it:
            sys.exit('No existe el objeto "%s" en el inventario' % name)
        s.set_qty(it, int(val))
    for spec in getattr(args, 'carta', None) or []:
        name, _, val = spec.rpartition('=')
        c = find_card(s, tr, name)
        if not c:
            sys.exit('No se encontró la carta de Gwynt "%s" en tu colección' % name)
        lbl = tr.card_info(c.card_index).get('nombre_es', f'#{c.card_index}')
        s.set_card_copies(c, int(val), label=lbl)
    if args.reparar:
        for it in s.items:
            if 0 <= it.dur < 100:
                s.set_durability(it, 100)
    ch = s.change_list()
    if not ch:
        sys.exit('Nada que cambiar')
    print('Partida:', os.path.basename(s.path))
    for c in ch:
        print('  %s: %s -> %s' % (c['campo'], c['antes'], c['despues']))
    if w3comun.game_running():
        print('AVISO: el juego esta abierto; despues carga esta partida desde "Cargar partida".')
    if not confirm(args, 'Se hara copia de seguridad y se guardara. ¿Continuar?'):
        sys.exit('Cancelado')
    manifest, reloaded = w3comun.apply_changes(s, mgr)
    print('OK. Copia previa:', manifest['id'])
    print('Ahora:', reloaded.summary())


def cmd_copias(args, mgr):
    for m in mgr.list_backups():
        ch = '; '.join('%s %s->%s' % (c['campo'], c['antes'], c['despues']) for c in m.get('cambios', []))
        print(m['id'])
        print('    %-9s %s  %s' % (m['tipo'], m['motivo'], ch))


def cmd_historial(args, mgr):
    for e in mgr.history():
        extra = e.get('motivo') or ''
        if e.get('cambios'):
            extra = '; '.join('%s %s->%s' % (c['campo'], c['antes'], c['despues']) for c in e['cambios'])
        print('%s  %-16s %-40s %s' % (e['fecha'], e['accion'], e.get('partida', ''), extra))


def cmd_restaurar(args, mgr):
    m = mgr.get(args.id)
    print('Restaurar %s (%s, %s) en %s' % (m['id'], m['partida'], m['motivo'], m['carpeta_origen']))
    if not confirm(args, '¿Continuar? (antes se copia la version actual)'):
        sys.exit('Cancelado')
    pre = mgr.restore(args.id)
    print('Restaurado. Copia de lo que habia:', pre['id'] if pre else '-')


def cmd_copia_completa(args, mgr):
    m = mgr.backup_all(args.carpeta)
    print('Copia completa:', m['id'], '(%d archivos)' % len(m['archivos']))


def main():
    ap = argparse.ArgumentParser(description='Editor de partidas de The Witcher 3 (Remaster)')
    ap.add_argument('--carpeta', default=w3comun.saves_dir(), help='carpeta gamesaves')
    ap.add_argument('--copias-en', default=w3comun.EDITOR_DIR, help=argparse.SUPPRESS)
    sub = ap.add_subparsers(dest='cmd', required=True)
    sub.add_parser('listar')
    p = sub.add_parser('info'); p.add_argument('partida'); p.add_argument('--objetos', action='store_true'); p.add_argument('--cartas', action='store_true', help='listar cartas de Gwynt en la coleccion')
    p = sub.add_parser('cambiar'); p.add_argument('partida')
    p.add_argument('--coronas', type=int); p.add_argument('--orenos', type=int); p.add_argument('--florines', type=int)
    p.add_argument('--xp', type=int, help='XP acumulada dentro del nivel actual')
    p.add_argument('--cantidad', action='append', help='"Nombre interno=N" (repetible)')
    p.add_argument('--carta', action='append', help='"Nombre o ID=N" para cartas de Gwynt (repetible)')
    p.add_argument('--reparar', action='store_true', help='durabilidad 100%% en todo el equipo')
    p.add_argument('--si', action='store_true', help='no preguntar')
    sub.add_parser('copias')
    sub.add_parser('historial')
    p = sub.add_parser('restaurar'); p.add_argument('id'); p.add_argument('--si', action='store_true')
    sub.add_parser('copia-completa')
    args = ap.parse_args()
    mgr = BackupManager(args.copias_en)
    try:
        globals()['cmd_' + args.cmd.replace('-', '_')](args, mgr)
    except (SaveFormatError, ValueError, KeyError, OSError) as e:
        sys.exit('ERROR: %s' % e)


if __name__ == '__main__':
    main()
