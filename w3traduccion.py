"""
Traduccion al espanol de los nombres internos de los objetos.

Base de datos: traducciones_es.json
  "juego":  nombres oficiales extraidos de los archivos del juego (se pueden regenerar)
  "manual": traducciones puestas a mano (prevalecen sobre las del juego)

Extraccion (solo lectura de los archivos del juego):
  1. bundles/*.bundle ("POTATO70", entradas zlib/lz4) -> XML gameplay\\items\\def_*.xml
     <item name="Venom extract" ... localisation_key_name="item_name_venom_extract">
  2. es.w3strings ("RTSW"): tabla clave(hash h*31+c) -> id, tabla id -> texto cifrado (XOR).
     Formato v164 (next-gen): texto de 1 byte por caracter (cp1252), clave = byte bajo.
"""
import datetime
import glob
import json
import os
import re
import struct
import zlib

from w3save import lz4_decompress

EDITOR_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(EDITOR_DIR, 'traducciones_es.json')
ES_MAGIC = 0x42387566          # "magia" del idioma espanol (es)

# Objetos internos sin nombre en el juego (partes del cuerpo, pelo, vainas...)
MANUAL_INICIAL = {
    'Body feet 01': 'Cuerpo: pies (interno)',
    'Body palms 01': 'Cuerpo: manos (interno)',
    'Body underwear 01': 'Cuerpo: ropa interior (interno)',
    'Body torso medalion': 'Cuerpo: torso con medallón (interno)',
    'Body torso towel': 'Cuerpo: torso con toalla (interno)',
    'Geralt fists': 'Puños de Geralt (interno)',
    'fists': 'Puños (interno)',
    'Half With Tail Hairstyle': 'Peinado: media melena con coleta',
    'Preview Hair': 'Peinado de vista previa (interno)',
    'head_2': 'Cabeza de Geralt (interno)',
    'head_4': 'Cabeza de Geralt (interno)',
    'scabbard_silver_1_08': 'Vaina de espada de plata (interno)',
    'scabbard_silver_3_01': 'Vaina de espada de plata (interno)',
    'scabbard_steel_1_05': 'Vaina de espada de acero (interno)',
    'scabbard_steel_3_03': 'Vaina de espada de acero (interno)',
    'scabbard_steel_nomansland_01': 'Vaina de espada de acero (interno)',
    'scabbard_steel_novigradian_01': 'Vaina de espada de acero (interno)',
    'scabbard_steel_novigradian_03': 'Vaina de espada de acero (interno)',
    'mq1058_contract': 'Contrato (misión mq1058)',
}


# ----------------------------------------------------------------- juego
def find_game_dir(cfg=None):
    """Carpeta de instalacion de The Witcher 3 (GOG, Steam o configurada a mano)."""
    cands = []
    if cfg and cfg.get('carpeta_juego'):
        cands.append(cfg['carpeta_juego'])
    try:
        import winreg
        for root, path, val in (
                (winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\WOW6432Node\GOG.com\Games\1495134320', 'path'),
                (winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\WOW6432Node\GOG.com\Games\1207664663', 'path'),
                (winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\WOW6432Node\GOG.com\Games\1207664643', 'path')):
            try:
                with winreg.OpenKey(root, path) as k:
                    cands.append(winreg.QueryValueEx(k, val)[0])
            except OSError:
                pass
        for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            for base in (r'SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall',
                         r'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall'):
                try:
                    with winreg.OpenKey(root, base) as k:
                        for n in range(winreg.QueryInfoKey(k)[0]):
                            try:
                                with winreg.OpenKey(k, winreg.EnumKey(k, n)) as sk:
                                    name = winreg.QueryValueEx(sk, 'DisplayName')[0]
                                    if 'witcher 3' in name.lower():
                                        cands.append(winreg.QueryValueEx(sk, 'InstallLocation')[0])
                            except OSError:
                                pass
                except OSError:
                    pass
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\WOW6432Node\Valve\Steam') as k:
                steam = winreg.QueryValueEx(k, 'InstallPath')[0]
                cands.append(os.path.join(steam, 'steamapps', 'common', 'The Witcher 3'))
        except OSError:
            pass
    except ImportError:
        pass
    for c in cands:
        if c and glob.glob(os.path.join(c, 'content', '*', 'es.w3strings')):
            return os.path.normpath(c)
    return None


def _bundle_entries(path):
    with open(path, 'rb') as f:
        hdr = f.read(0x20)
        if hdr[:8] != b'POTATO70':
            return []
        toc = struct.unpack_from('<I', hdr, 16)[0]
        t = f.read(toc)
    out = []
    for k in range(toc // 0x130):
        o = k * 0x130
        name = t[o:o + 0x100].split(b'\0')[0].decode('latin1')
        off, _z, size, csize, _crc, comp = struct.unpack_from('<IIIIII', t, o + 0x110)
        out.append((name, off, size, csize, comp))
    return out


def _bundle_read(f, entry):
    name, off, size, csize, comp = entry
    f.seek(off)
    blob = f.read(csize)
    if comp == 0:
        return blob
    if comp == 1:
        return zlib.decompress(blob)
    if comp in (4, 5):
        return lz4_decompress(blob, size)
    raise ValueError('compresion %d no soportada' % comp)


_ITEM_RE = re.compile(rb'<item\s([^>]*?)>', re.S)
_ATTR_RE = re.compile(rb'(\w+)\s*=\s*"([^"]*)"')


def item_keys_from_game(game_dir):
    """{nombre interno: clave de localizacion} de todas las definiciones de objetos."""
    keys = {}
    bundles = glob.glob(os.path.join(game_dir, 'content', '*', 'bundles', '*.bundle')) + \
        glob.glob(os.path.join(game_dir, 'dlc', '*', 'content', 'bundles', '*.bundle'))
    for bp in sorted(bundles):
        ents = [e for e in _bundle_entries(bp)
                if e[0].lower().endswith('.xml') and 'items' in e[0].lower()]
        if not ents:
            continue
        with open(bp, 'rb') as f:
            for e in ents:
                try:
                    data = _bundle_read(f, e)
                except Exception:
                    continue
                for m in _ITEM_RE.finditer(data):
                    a = dict(_ATTR_RE.findall(m.group(1)))
                    name = a.get(b'name')
                    if not name:
                        continue
                    name = name.decode('latin1')
                    key = a.get(b'localisation_key_name')
                    if key:
                        keys.setdefault(name, key.decode('latin1').strip())
                    else:
                        keys.setdefault(name, None)
    return keys


def _bit6(d, i):
    b = d[i]; i += 1
    val, neg, shift, cont = b & 0x3f, b & 0x80, 6, b & 0x40
    while cont:
        b = d[i]; i += 1
        val |= (b & 0x7f) << shift
        shift += 7
        cont = b & 0x80
    return (-val if neg else val), i


def hash_key(s):
    h = 0
    for c in s:
        h = (h * 31 + ord(c)) & 0xffffffff
    return h


def read_w3strings(path, magic=ES_MAGIC, wanted_hashes=None):
    """Devuelve {hash_clave: texto} para las claves pedidas (o todas las que tienen clave)."""
    with open(path, 'rb') as f:
        d = f.read()
    if d[:4] != b'RTSW':
        raise ValueError('%s no es un w3strings' % path)
    ver = struct.unpack_from('<I', d, 4)[0]
    i = 10
    n1, i = _bit6(d, i)
    b1 = i
    i += 12 * n1
    n2, i = _bit6(d, i)
    key_to_id = {}
    for k in range(n2):
        kh, hid = struct.unpack_from('<II', d, i + 8 * k)
        if wanted_hashes is None or kh in wanted_hashes:
            key_to_id[kh] = hid ^ magic
    i += 8 * n2
    n3, start = _bit6(d, i)
    unit = 1 if ver >= 164 else 2
    if start + unit * n3 != len(d) - 2:
        raise ValueError('Estructura de %s no reconocida (version %d)' % (path, ver))
    ids = {v: kh for kh, v in key_to_id.items()}
    out = {}
    sk0 = (magic >> 8) & 0xffff
    for k in range(n1):
        hid, off, ln = struct.unpack_from('<III', d, b1 + 12 * k)
        sid = hid ^ magic
        if sid not in ids:
            continue
        sk, mult = sk0, ln + 1
        if unit == 1:
            raw = d[start + off:start + off + ln]
            buf = bytearray(ln)
            for j in range(ln):
                buf[j] = raw[j] ^ ((mult * sk) & 0xff)
                sk = ((sk << 1) | (sk >> 15)) & 0xffff
            try:
                txt = buf.decode('utf-8')
            except UnicodeDecodeError:
                txt = buf.decode('cp1252', 'replace')
        else:
            raw = struct.unpack_from('<%dH' % ln, d, start + off * 2)
            chars = []
            for c in raw:
                chars.append(chr(c ^ ((mult * sk) & 0xffff)))
                sk = ((sk << 1) | (sk >> 15)) & 0xffff
            txt = ''.join(chars)
        out[ids[sid]] = txt
    return out


def extract_from_game(game_dir):
    """{nombre interno: nombre oficial en espanol}"""
    keys = item_keys_from_game(game_dir)
    cand = {}
    for name, key in keys.items():
        opts = [key] if key else []
        opts.append('item_name_' + name.lower().replace(' ', '_'))
        cand[name] = opts
    wanted = {hash_key(k) for opts in cand.values() for k in opts}
    texts = {}
    for sp in sorted(glob.glob(os.path.join(game_dir, 'content', '*', 'es.w3strings')) +
                     glob.glob(os.path.join(game_dir, 'dlc', '*', 'content', 'es.w3strings'))):
        texts.update(read_w3strings(sp, ES_MAGIC, wanted))
    result = {}
    for name, opts in cand.items():
        for k in opts:
            t = texts.get(hash_key(k))
            if t and t.strip():
                result[name] = t.strip()
                break
    return result, len(keys)


def extract_gwint_from_game(game_dir):
    """Extrae las definiciones y nombres en espanol de todas las cartas de Gwynt."""
    import xml.etree.ElementTree as ET
    bundle_path = os.path.join(game_dir, 'content', 'content0', 'bundles', 'xml.bundle')
    w3s_file = os.path.join(game_dir, 'content', 'content0', 'es.w3strings')
    if not (os.path.isfile(bundle_path) and os.path.isfile(w3s_file)):
        return {}

    faction_names = {
        'F_NEUTRAL': 'Neutral',
        'F_NORTHERN_KINGDOM': 'Reinos del Norte',
        'F_NILFGAARD': 'Nilfgaard',
        'F_SCOIATAEL': "Scoia'tael",
        'F_NO_MANS_LAND': 'Monstruos',
        'F_SKELLIGE': 'Skellige'
    }

    xml_targets = [
        r'gameplay\items\def_gwint_cards_final.xml',
        r'gameplay\items\def_gwint_battle_king_cards.xml',
        r'gameplay\items\def_gwint_king_cards.xml'
    ]

    cards_data = {}
    title_keys = set()
    with open(bundle_path, 'rb') as f:
        for e in _bundle_entries(bundle_path):
            if e[0] in xml_targets:
                try:
                    data = _bundle_read(f, e)
                    root = ET.fromstring(data)
                    is_king = 'king' in e[0]
                    for card in root.iter('card'):
                        idx_str = card.get('index')
                        if idx_str is not None:
                            idx = int(idx_str)
                            title = card.get('title', '')
                            name = card.get('name', '')
                            power = int(card.get('power', '0'))
                            faction = card.get('faction_index', 'F_NEUTRAL')
                            desc = card.get('description', '')
                            flags = [flag.get('name') for flag in card.iter('flag')]
                            is_hero = 'TYPE_HERO' in flags
                            if title: title_keys.add(title)
                            if desc: title_keys.add(desc)
                            cards_data[str(idx)] = {
                                'internal_name': name,
                                'title_key': title,
                                'desc_key': desc,
                                'power': power,
                                'faction': faction_names.get(faction, faction),
                                'is_leader': is_king or idx >= 1000,
                                'is_hero': is_hero
                            }
                except Exception:
                    pass

    title_hashes = {hash_key(k): k for k in title_keys}
    translations = read_w3strings(w3s_file, wanted_hashes=set(title_hashes.keys()))
    hash_to_text = {title_hashes[h]: txt for h, txt in translations.items() if h in title_hashes}

    for idx_str, c in cards_data.items():
        es_title = hash_to_text.get(c['title_key'])
        es_desc = hash_to_text.get(c['desc_key'])
        if c['is_leader'] and es_desc and not es_desc.startswith('[['):
            desc_clean = es_desc.replace('<br>', ' - ')
            c['nombre_es'] = f"{es_title or c['internal_name']} - {desc_clean}"
        else:
            c['nombre_es'] = (es_title or c['internal_name']).replace('<br>', ' - ')

    return cards_data


# ------------------------------------------------------------- base de datos
class Translations:
    def __init__(self, path=DB_PATH):
        self.path = path
        self.info = {}
        self.juego = {}
        self.manual = {}
        self.cartas = {}
        self.load()

    def load(self):
        try:
            with open(self.path, encoding='utf-8') as f:
                db = json.load(f)
            self.info = db.get('_info', {})
            self.juego = db.get('juego', {})
            self.manual = db.get('manual', {})
            self.cartas = db.get('cartas_gwynt', {})
        except (OSError, ValueError):
            self.info, self.juego, self.manual, self.cartas = {}, {}, dict(MANUAL_INICIAL), {}

    def save(self):
        tmp = self.path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            data = {
                '_info': self.info,
                'manual': dict(sorted(self.manual.items())),
                'juego': dict(sorted(self.juego.items()))
            }
            if self.cartas:
                data['cartas_gwynt'] = self.cartas
            json.dump(data, f, ensure_ascii=False, indent=1)
        os.replace(tmp, self.path)

    @property
    def available(self):
        return bool(self.juego or self.manual)

    def get(self, name, default=''):
        if name in self.manual:
            return self.manual[name]
        if name in self.juego:
            return self.juego[name]
        return default

    def label(self, name):
        """Nombre en espanol si existe; si no, el interno."""
        return self.get(name) or name

    def card_info(self, card_index):
        """Metadatos de la carta de Gwynt por su indice numerico."""
        info = self.cartas.get(str(card_index))
        if info:
            return info
        return {
            'nombre_es': f'Carta #{card_index}',
            'internal_name': f'card_{card_index}',
            'power': 0,
            'faction': 'Desconocida',
            'is_leader': card_index >= 1000,
            'is_hero': False
        }

    def set_manual(self, name, text):
        text = (text or '').strip()
        if text:
            self.manual[name] = text
        else:
            self.manual.pop(name, None)
        self.save()

    def regenerate(self, game_dir):
        result, n_defs = extract_from_game(game_dir)
        if not result:
            raise ValueError('No se pudo extraer ninguna traduccion de %s' % game_dir)
        self.juego = result
        cards = extract_gwint_from_game(game_dir)
        if cards:
            self.cartas = cards
        for k, v in MANUAL_INICIAL.items():
            self.manual.setdefault(k, v)
        self.info = dict(generado=datetime.datetime.now().isoformat(timespec='seconds'),
                         carpeta_juego=game_dir, definiciones=n_defs, traducciones_juego=len(result),
                         cartas_gwynt=len(self.cartas), idioma='es')
        self.save()
        return len(result)


if __name__ == '__main__':
    import sys
    gd = sys.argv[1] if len(sys.argv) > 1 else find_game_dir()
    if not gd:
        sys.exit('No se encuentra la instalacion del juego; pasa la carpeta como argumento.')
    tr = Translations()
    n = tr.regenerate(gd)
    print('Traducciones extraidas del juego: %d  (manuales: %d)  ->  %s' % (n, len(tr.manual), tr.path))
