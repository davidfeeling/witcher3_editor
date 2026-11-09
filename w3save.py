"""
Lectura y escritura de partidas de The Witcher 3 (edicion next-gen / remaster,
formato de partida saveVersion 66 y 67).

Formato (deducido analizando las partidas del usuario, 2026-10-03):

  Archivo .sav
    "SNFHFZLC"  int32 numChunks  int32 headerSize
    numChunks x (int32 compSize, int32 decompSize, int32 endOffset; 0 en el ultimo)
    relleno hasta headerSize, luego los chunks LZ4 (bloques independientes de 1 MiB)

  Datos descomprimidos
    "SAV3" int32 saveVersion int32 gameVersion ...
    Tabla de nombres "NM"+"MANU": int32 n, int32 0, n x (uint8 len, ascii) ... "ENOD"
    Los nombres se referencian con indices uint16 (base 1).

  Inventario (CInventoryComponent):
    uint16 clase  uint16 siguienteId  uint16 numObjetos  y numObjetos registros:
      uint16 nombre, uint16 semilla, uint8, uint8, 7 bytes (el ultimo = huecos de runa),
      uint16 tinte, uint16 colorTinte, uint16 CANTIDAD, float32 DURABILIDAD (-1 = n/a),
      uint8 n + n x (uint16 nombre, uint32 valor, uint8)      (modificadores)
      uint16 idUnico,
      uint8 n + n x (uint16 nombre, uint16, uint16, uint8 m + m x uint16)  (runas/glifos)
      uint8 n + n x uint16                                    (habilidades)
      uint16 categoria [+ uint16 si categoria != 0]

  Propiedades de scripts: uint16 nombre, uint16 tipo, uint32 tam (incluye los 4 bytes
  del propio tam), valor.  Las propiedades con valor por defecto NO se guardan.

Todas las modificaciones que hace este modulo son del MISMO TAMANO (no se desplaza
ningun offset del archivo).  Solo se recomprime el chunk LZ4 que contiene el cambio;
el resto de chunks se copian byte a byte.
"""
import struct

MAGIC = b'SNFHFZLC'
SUPPORTED_SAVE_VERSIONS = (66, 67)
MAX_QTY = 32767          # el campo es de 16 bits; 32767 es seguro con o sin signo
CURRENCIES = {'Crowns': 'Coronas', 'Orens': 'Orenos', 'Florens': 'Florines'}


class SaveFormatError(Exception):
    pass


# --------------------------------------------------------------------------- LZ4
def lz4_decompress(src, out_size):
    dst = bytearray()
    i, n = 0, len(src)
    while i < n:
        token = src[i]; i += 1
        lit = token >> 4
        if lit == 15:
            while True:
                b = src[i]; i += 1
                lit += b
                if b != 255:
                    break
        dst += src[i:i + lit]; i += lit
        if i >= n:
            break
        off = src[i] | (src[i + 1] << 8); i += 2
        if off == 0 or off > len(dst):
            raise SaveFormatError('LZ4: offset invalido')
        ml = token & 15
        if ml == 15:
            while True:
                b = src[i]; i += 1
                ml += b
                if b != 255:
                    break
        ml += 4
        start = len(dst) - off
        if off >= ml:
            dst += dst[start:start + ml]
        else:
            for k in range(ml):
                dst.append(dst[start + k])
    if len(dst) != out_size:
        raise SaveFormatError('LZ4: tamano descomprimido %d != %d' % (len(dst), out_size))
    return bytes(dst)


def _lz4_len(out, n):
    while n >= 255:
        out.append(255); n -= 255
    out.append(n)


def lz4_compress(src):
    """Compresor LZ4 (formato bloque) voraz, puro Python."""
    src = bytes(src)
    n = len(src)
    out = bytearray()
    anchor = 0
    if n > 12:
        mflimit = n - 12            # una coincidencia debe empezar antes de n-12
        matchlimit = n - 5          # los ultimos 5 bytes siempre son literales
        table = {}
        i = 0
        miss = 0
        while i < mflimit:
            key = src[i:i + 4]
            ref = table.get(key)
            table[key] = i
            if ref is None or i - ref > 65535:
                miss += 1
                i += 1 + (miss >> 6)     # acelera en zonas incompresibles
                continue
            miss = 0
            # extender la coincidencia
            ml = 4
            while i + ml + 32 <= matchlimit and src[ref + ml:ref + ml + 32] == src[i + ml:i + ml + 32]:
                ml += 32
            while i + ml < matchlimit and src[ref + ml] == src[i + ml]:
                ml += 1
            lit = i - anchor
            tok_l = 15 if lit >= 15 else lit
            tok_m = 15 if ml - 4 >= 15 else ml - 4
            out.append((tok_l << 4) | tok_m)
            if lit >= 15:
                _lz4_len(out, lit - 15)
            out += src[anchor:i]
            off = i - ref
            out.append(off & 255); out.append(off >> 8)
            if ml - 4 >= 15:
                _lz4_len(out, ml - 4 - 15)
            # indexar un par de posiciones dentro de la coincidencia
            end = i + ml
            if end - 2 > i and end - 2 < mflimit:
                table[src[end - 2:end + 2]] = end - 2
            i = end
            anchor = i
    lit = n - anchor
    out.append((15 if lit >= 15 else lit) << 4)
    if lit >= 15:
        _lz4_len(out, lit - 15)
    out += src[anchor:]
    return bytes(out)


# --------------------------------------------------------------------- contenedor
class SaveContainer:
    """Archivo .sav comprimido -> bytes descomprimidos y vuelta."""

    def __init__(self, file_bytes):
        self.file_bytes = bytes(file_bytes)
        if self.file_bytes[:8] != MAGIC:
            raise SaveFormatError('No es una partida de The Witcher 3 (cabecera %r)' % self.file_bytes[:8])
        self.count, self.header_size = struct.unpack_from('<ii', self.file_bytes, 8)
        if not (0 < self.count < 256) or self.header_size < 16 + 12 * self.count:
            raise SaveFormatError('Cabecera de chunks invalida')
        self.table = [struct.unpack_from('<iii', self.file_bytes, 16 + 12 * k) for k in range(self.count)]
        self.comp_chunks = []
        pos = self.header_size
        parts = []
        for comp, decomp, _end in self.table:
            blob = self.file_bytes[pos:pos + comp]
            if len(blob) != comp:
                raise SaveFormatError('Archivo truncado')
            self.comp_chunks.append(blob)
            parts.append(lz4_decompress(blob, decomp))
            pos += comp
        if pos != len(self.file_bytes):
            raise SaveFormatError('Datos sobrantes al final del archivo')
        self.original_raw = b''.join(parts)
        self.raw = bytearray(self.original_raw)

    def build(self):
        """Devuelve los bytes del .sav con self.raw recomprimido (solo chunks cambiados)."""
        if len(self.raw) != len(self.original_raw):
            raise SaveFormatError('El tamano de los datos ha cambiado; no soportado')
        header = bytearray(self.file_bytes[:self.header_size])
        body = bytearray()
        pos = 0
        end_off = self.header_size
        for k, (comp, decomp, end_field) in enumerate(self.table):
            new_part = bytes(self.raw[pos:pos + decomp])
            if new_part == self.original_raw[pos:pos + decomp]:
                blob = self.comp_chunks[k]
            else:
                blob = lz4_compress(new_part)
                if lz4_decompress(blob, decomp) != new_part:
                    raise SaveFormatError('Fallo de verificacion LZ4 en el chunk %d' % k)
            end_off += len(blob)
            last = (k == self.count - 1)
            field3 = 0 if (last and end_field == 0) else end_off
            struct.pack_into('<iii', header, 16 + 12 * k, len(blob), decomp, field3)
            body += blob
            pos += decomp
        out = bytes(header + body)
        # verificacion completa: lo que escribimos debe descomprimir exactamente a self.raw
        if bytes(SaveContainer(out).raw) != bytes(self.raw):
            raise SaveFormatError('Fallo de verificacion del archivo reconstruido')
        return out


# -------------------------------------------------------------------- utilidades
def read_names(raw):
    best = None
    start = 0
    while True:
        p = raw.find(b'NMMANU', start)
        if p < 0:
            break
        start = p + 1
        try:
            cnt, zero = struct.unpack_from('<ii', raw, p + 6)
            if not (0 < cnt < 200000):
                continue
            i = p + 14
            names = ['']
            for _ in range(cnt):
                ln = raw[i]
                if ln & 0x80:
                    raise ValueError
                i += 1
                names.append(raw[i:i + ln].decode('latin1'))
                i += ln
            if b'ENOD' in raw[i:i + 12]:
                best = names
        except (ValueError, IndexError, struct.error):
            continue
    if best is None:
        raise SaveFormatError('No se encontro la tabla de nombres')
    return best


class Item:
    __slots__ = ('index', 'offset', 'name', 'qty', 'qty_off', 'dur', 'dur_off', 'uid',
                 'runes', 'n_abilities', 'category', 'slots', 'mods')

    @property
    def is_equipment(self):
        return self.dur >= 0 or self.slots > 0 or bool(self.runes)

    def kind(self):
        if self.name in CURRENCIES:
            return 'moneda'
        if self.is_equipment:
            return 'equipo'
        return 'apilable' if self.qty > 1 else 'objeto'


def parse_inventory(raw, pos, names):
    """pos = offset del uint16 de clase.  Devuelve (items, fin, siguienteId) o None."""
    i = pos
    n_names = len(names)
    try:
        def u8():
            nonlocal i
            v = raw[i]; i += 1
            return v

        def u16():
            nonlocal i
            v = raw[i] | (raw[i + 1] << 8); i += 2
            return v

        u16()
        next_id = u16()
        count = u16()
        items = []
        for k in range(count):
            it = Item()
            it.index = k
            it.offset = i
            name = u16(); u16(); u8(); u8()
            seven = raw[i:i + 7]; i += 7
            it.slots = seven[6]
            dye = u16(); u16()
            it.qty_off = i
            it.qty = u16()
            it.dur_off = i
            it.dur = struct.unpack_from('<f', raw, i)[0]; i += 4
            nmods = u8()
            it.mods = []
            for _ in range(nmods):
                mn = u16(); mv = struct.unpack_from('<I', raw, i)[0]; i += 4; u8()
                it.mods.append((names[mn] if 0 < mn < n_names else '?', mv))
            it.uid = u16()
            it.runes = []
            for _ in range(u8()):
                rn = u16(); u16(); u16()
                n_ab = u8()          # (no usar "i += 2 * u8()": i se leeria antes de u8)
                i += 2 * n_ab
                it.runes.append(names[rn] if 0 < rn < n_names else '?')
            it.n_abilities = u8()
            i += 2 * it.n_abilities
            cat = u16()
            if cat != 0:
                if i + 2 <= len(raw) and raw[i:i + 2] == b'\x00\x00':
                    i += 2
            if not (0 < name < n_names) or not (0 < dye < n_names) or it.uid > next_id:
                return None
            it.name = names[name]
            it.category = names[cat] if 0 < cat < n_names else ''
            items.append(it)
        return items, i, next_id
    except (IndexError, struct.error):
        return None


def find_player_inventory(raw, names):
    """Localiza el inventario de Geralt.  Devuelve (items, offset, metodo)."""
    try:
        cls = names.index('CInventoryComponent')
    except ValueError:
        raise SaveFormatError('No hay CInventoryComponent en la partida')
    pat = struct.pack('<H', cls)
    player_idx = names.index('PLAYER') if 'PLAYER' in names else None
    geralt_idx = names.index('GERALT') if 'GERALT' in names else None
    candidates = []
    o = 0
    while True:
        o = raw.find(pat, o + 1)
        if o < 0:
            break
        r = parse_inventory(raw, o, names)
        if not r or not r[0] or raw[r[1]:r[1] + 6] != b'\x01\x00\x00\x00\x00\x00':
            continue
        items = r[0]
        has_crowns = any(it.name == 'Crowns' for it in items)
        win = raw[max(0, o - 8192):o]
        is_player = player_idx is not None and struct.pack('<H', player_idx) in win and b'AVAL' in win
        is_geralt = geralt_idx is not None and struct.pack('<H', geralt_idx) in win
        has_geralt_items = any(it.name in ('Body underwear 01', 'Geralt fists') for it in items)

        score = 0
        if is_player: score += 10
        if is_geralt: score += 10
        if has_geralt_items: score += 20
        if has_crowns: score += 5
        score += min(len(items), 1000)
        candidates.append((score, o, items))

    if not candidates:
        raise SaveFormatError('No se encontro el inventario del jugador')
    candidates.sort(key=lambda c: c[0], reverse=True)
    best = candidates[0]
    return best[2], best[1], 'inventario de Geralt (%d items)' % len(best[2])


class GwintCard:
    __slots__ = ('card_index', 'copies', 'copies_off', 'is_leader')

    def __init__(self, card_index, copies, copies_off, is_leader=False):
        self.card_index = card_index
        self.copies = copies
        self.copies_off = copies_off
        self.is_leader = is_leader


def find_gwint_cards(raw, names):
    """Localiza las cartas y lideres de Gwynt de la coleccion del jugador."""
    try:
        gwint_mgr_idx = names.index('CR4GwintManager')
        sb_card_idx = names.index('SBCollectionCard')
        card_idx_name = names.index('cardIndex')
        num_copies_name = names.index('numCopies')
    except ValueError:
        return []

    p = raw.find(b'BS' + struct.pack('<H', gwint_mgr_idx))
    if p < 0:
        return []

    end_mgr = min(len(raw), p + 65536)
    card_bs = b'BS' + struct.pack('<H', sb_card_idx)
    card_idx_vl = b'VL' + struct.pack('<H', card_idx_name)
    num_copies_vl = b'VL' + struct.pack('<H', num_copies_name)

    cards = []
    pos = p
    while pos < end_mgr:
        cp = raw.find(card_bs, pos, end_mgr)
        if cp < 0:
            break
        ip = raw.find(card_idx_vl, cp, cp + 60)
        if ip < 0:
            pos = cp + 4
            continue
        c_idx = struct.unpack_from('<I', raw, ip + 6)[0]
        np = raw.find(num_copies_vl, ip, ip + 60)
        if np < 0:
            pos = ip + 10
            continue
        n_copies = struct.unpack_from('<i', raw, np + 6)[0]
        cards.append(GwintCard(c_idx, n_copies, np + 6, is_leader=False))
        pos = np + 10

    if 'SBLeaderCollectionCard' in names:
        leader_bs = b'BS' + struct.pack('<H', names.index('SBLeaderCollectionCard'))
        pos = p
        while pos < end_mgr:
            cp = raw.find(leader_bs, pos, end_mgr)
            if cp < 0:
                break
            ip = raw.find(card_idx_vl, cp, cp + 60)
            if ip < 0:
                pos = cp + 4
                continue
            c_idx = struct.unpack_from('<I', raw, ip + 6)[0]
            np = raw.find(num_copies_vl, ip, ip + 60)
            if np >= 0 and np < ip + 60:
                n_copies = struct.unpack_from('<i', raw, np + 6)[0]
                cards.append(GwintCard(c_idx, n_copies, np + 6, is_leader=True))
                pos = np + 10
            else:
                cards.append(GwintCard(c_idx, 1, None, is_leader=True))
                pos = ip + 10

    return cards


def _parse_props(raw, i, names, end):
    """Lee propiedades (nombre, tipo, tam, valor) hasta un uint16 0. Devuelve (dict, i)."""
    props = {}
    while i < end:
        n = struct.unpack_from('<H', raw, i)[0]
        if n == 0:
            return props, i + 2
        t, sz = struct.unpack_from('<HI', raw, i + 2)
        if sz < 4 or i + 4 + sz > end:
            raise SaveFormatError('Propiedad corrupta')
        props[names[n] if n < len(names) else '?'] = (names[t] if t < len(names) else '?', i + 8, sz - 4)
        i += 4 + sz
    raise SaveFormatError('Estructura sin terminar')


class LevelInfo:
    def __init__(self):
        self.level = None
        self.level_off = None
        self.xp_free = 0
        self.xp_free_off = None
        self.xp_used = 0
        self.sp_free = 0
        self.sp_free_off = None
        self.sp_used = 0
        self.required_total = {}   # nivel -> XP total necesaria

    @property
    def xp_total(self):
        return self.xp_free + self.xp_used

    def next_level_total(self):
        return self.required_total.get((self.level or 0) + 1)

    def max_total(self):
        return max(self.required_total.values()) if self.required_total else None


def find_level_info(raw, names):
    li = LevelInfo()
    try:
        i_lm = names.index('levelManager')
        i_pts = names.index('points')
        i_arr = names.index('array:2,0,SSpendablePoints')
        i_lvl = names.index('level')
        i_int = names.index('Int32')
    except ValueError:
        return None
    p = raw.find(b'PORP' + struct.pack('<H', i_lm))
    if p < 0:
        return None
    win_end = min(len(raw), p + 0x4000)
    q = raw.find(struct.pack('<HH', i_pts, i_arr), p, win_end)
    if q < 0:
        return None
    # definiciones de nivel
    try:
        i_defs = names.index('levelDefinitions')
        d = raw.find(struct.pack('<H', i_defs), p, q)
        if d > 0:
            sz, cnt = struct.unpack_from('<II', raw, d + 4)
            j = d + 12
            for _ in range(cnt):
                if raw[j] != 0:
                    break
                props, j = _parse_props(raw, j + 1, names, q)
                if 'number' in props and 'requiredTotalExp' in props:
                    num = struct.unpack_from('<i', raw, props['number'][1])[0]
                    req = struct.unpack_from('<i', raw, props['requiredTotalExp'][1])[0]
                    if num > 0 and req >= 0:
                        li.required_total[num] = req
    except (ValueError, SaveFormatError, struct.error, IndexError):
        pass
    lv = raw.rfind(struct.pack('<HHI', i_lvl, i_int, 8), p, q)
    if lv > 0:
        li.level_off = lv + 8
        li.level = struct.unpack_from('<i', raw, li.level_off)[0]
    sz, cnt = struct.unpack_from('<II', raw, q + 4)
    if cnt != 2:
        return li
    j = q + 12
    end = q + 4 + sz
    elems = []
    for _ in range(cnt):
        if raw[j] != 0:
            return li
        props, j = _parse_props(raw, j + 1, names, end)
        elems.append(props)
    # ESpendablePointType: 0 = puntos de habilidad, 1 = experiencia
    for idx, props in enumerate(elems):
        free = props.get('free'); used = props.get('used')
        fv = struct.unpack_from('<i', raw, free[1])[0] if free and free[2] == 4 else 0
        uv = struct.unpack_from('<i', raw, used[1])[0] if used and used[2] == 4 else 0
        if idx == 0:
            li.sp_free, li.sp_used = fv, uv
            li.sp_free_off = free[1] if free and free[2] == 4 else None
        else:
            li.xp_free, li.xp_used = fv, uv
            li.xp_free_off = free[1] if free and free[2] == 4 else None
    return li


# ------------------------------------------------------------------------ partida
class W3Save:
    """Partida cargada en memoria con cambios pendientes."""

    def __init__(self, path):
        self.path = path
        with open(path, 'rb') as f:
            self.container = SaveContainer(f.read())
        raw = self.container.raw
        if raw[:4] != b'SAV3':
            raise SaveFormatError('Datos descomprimidos sin firma SAV3')
        self.save_version = struct.unpack_from('<I', raw, 4)[0]
        if self.save_version not in SUPPORTED_SAVE_VERSIONS:
            raise SaveFormatError('Version de partida %d no soportada (solo next-gen v66/v67). '
                                  'Probablemente es una partida antigua (2019-2020).' % self.save_version)
        self.names = read_names(raw)
        self.items, self.inv_offset, self.inv_method = find_player_inventory(raw, self.names)
        self.cards = find_gwint_cards(raw, self.names)
        self.level = find_level_info(raw, self.names)
        self.changes = {}     # clave -> dict(desc, off, fmt, old, new)
        # nombre visible de un objeto en las descripciones de cambios (la GUI pone el espanol)
        self.label = lambda name: CURRENCIES.get(name, name)

    # ---- consulta
    def item_by_name(self, name):
        for it in self.items:
            if it.name == name:
                return it
        return None

    def card_by_index(self, card_index):
        for c in self.cards:
            if c.card_index == card_index:
                return c
        return None

    def summary(self):
        s = {}
        for k in CURRENCIES:
            it = self.item_by_name(k)
            s[k] = it.qty if it else None
        if self.level:
            s['nivel'] = self.level.level
            s['xp_total'] = self.level.xp_total
        s['objetos'] = len(self.items)
        s['cartas_gwynt'] = len(self.cards)
        return s

    # ---- cambios
    def _stage(self, key, desc, off, fmt, old, new):
        if new == old:
            self.changes.pop(key, None)
        else:
            self.changes[key] = dict(desc=desc, off=off, fmt=fmt, old=old, new=new)

    def set_qty(self, item, qty):
        qty = int(qty)
        if not (0 <= qty <= MAX_QTY):
            raise ValueError('La cantidad debe estar entre 0 y %d' % MAX_QTY)
        if qty == 0:
            raise ValueError('Cantidad 0 no permitida (para quitar un objeto hazlo en el juego)')
        self._stage(('qty', item.qty_off), '%s: cantidad' % self.label(item.name), item.qty_off, '<H',
                    item.qty, qty)

    def set_card_copies(self, card, copies, label=None):
        if card.copies_off is None:
            raise ValueError('No se pueden editar las copias de esta carta líder')
        copies = int(copies)
        if not (1 <= copies <= 99):
            raise ValueError('El número de copias debe estar entre 1 y 99')
        lbl = label or f'Carta Gwynt #{card.card_index}'
        self._stage(('card', card.copies_off), '%s: copias' % lbl, card.copies_off, '<i',
                    card.copies, copies)

    def set_durability(self, item, dur):
        if item.dur < 0:
            raise ValueError('%s no tiene durabilidad' % item.name)
        dur = float(dur)
        if not (0 < dur <= 100):
            raise ValueError('La durabilidad debe estar entre 1 y 100')
        self._stage(('dur', item.dur_off), '%s: durabilidad' % self.label(item.name), item.dur_off, '<f',
                    round(item.dur, 2), round(dur, 2))

    def set_xp_free(self, value):
        li = self.level
        if not li or li.xp_free_off is None:
            raise ValueError('La experiencia no es editable en esta partida')
        value = int(value)
        mx = li.max_total()
        if value < 0:
            raise ValueError('La experiencia no puede ser negativa')
        if mx is not None and li.xp_used + value > mx:
            raise ValueError('Maximo: %d (XP total %d del ultimo nivel definido)' % (mx - li.xp_used, mx))
        self._stage(('xp',), 'Experiencia acumulada en el nivel', li.xp_free_off, '<i', li.xp_free, value)

    def set_skill_points_free(self, value):
        li = self.level
        if not li or li.sp_free_off is None:
            raise ValueError('Los puntos de habilidad libres son 0 y el juego no guarda el campo '
                             'cuando vale 0, asi que no se pueden editar sin cambiar el tamano del '
                             'archivo. Usa la experiencia para ganar niveles (cada nivel da 1 punto).')
        value = int(value)
        if not (0 <= value <= 500):
            raise ValueError('Valor entre 0 y 500')
        self._stage(('sp',), 'Puntos de habilidad libres', li.sp_free_off, '<i', li.sp_free, value)

    def change_list(self):
        return [dict(campo=c['desc'], antes=c['old'], despues=c['new'], offset=c['off'])
                for c in self.changes.values()]

    # ---- escritura
    def build_bytes(self):
        """Aplica los cambios a una copia y devuelve el .sav nuevo (verificado)."""
        if not self.changes:
            raise ValueError('No hay cambios pendientes')
        cont = self.container
        cont.raw = bytearray(cont.original_raw)
        allowed = set()
        for c in self.changes.values():
            size = struct.calcsize(c['fmt'])
            cur = struct.unpack_from(c['fmt'], cont.raw, c['off'])[0]
            if c['fmt'] == '<f':
                cur = round(cur, 2)
            if cur != c['old']:
                raise SaveFormatError('El valor en %s no coincide con lo esperado' % c['desc'])
            struct.pack_into(c['fmt'], cont.raw, c['off'], c['new'])
            allowed.update(range(c['off'], c['off'] + size))
        # solo pueden diferir los bytes que hemos tocado
        orig, new = cont.original_raw, cont.raw
        blk = 4096
        for b in range(0, len(orig), blk):
            if orig[b:b + blk] != new[b:b + blk]:
                for k in range(b, min(b + blk, len(orig))):
                    if orig[k] != new[k] and k not in allowed:
                        raise SaveFormatError('Cambios fuera de los campos previstos')
        return cont.build()
