"""Funciones compartidas por la interfaz grafica y la linea de comandos."""
import ctypes
import datetime
import hashlib
import json
import os
import subprocess
import sys

from w3backup import BackupManager, replace_with_retry
from w3save import W3Save, SaveFormatError

EDITOR_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(EDITOR_DIR, 'config.json')


def documents_dir():
    """Carpeta Documentos real (puede estar redirigida a OneDrive)."""
    try:
        from ctypes import wintypes

        class GUID(ctypes.Structure):
            _fields_ = [('a', wintypes.DWORD), ('b', wintypes.WORD), ('c', wintypes.WORD), ('d', ctypes.c_ubyte * 8)]
        # FOLDERID_Documents {FDD39AD0-238F-46AF-ADB4-6C85480369C7}
        g = GUID(0xFDD39AD0, 0x238F, 0x46AF, (ctypes.c_ubyte * 8)(0xAD, 0xB4, 0x6C, 0x85, 0x48, 0x03, 0x69, 0xC7))
        p = ctypes.c_wchar_p()
        if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(g), 0, None, ctypes.byref(p)) == 0:
            path = p.value
            ctypes.windll.ole32.CoTaskMemFree(p)
            return path
    except Exception:
        pass
    return os.path.join(os.path.expanduser('~'), 'Documents')


def load_config():
    try:
        with open(CONFIG_PATH, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_config(cfg):
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def saves_dir():
    cfg = load_config()
    if cfg.get('carpeta_partidas') and os.path.isdir(cfg['carpeta_partidas']):
        return cfg['carpeta_partidas']
    return os.path.join(documents_dir(), 'The Witcher 3', 'gamesaves')


def backup_manager():
    return BackupManager(EDITOR_DIR)


def list_saves(folder):
    """Lista de partidas (.sav) ordenadas de mas reciente a mas antigua."""
    out = []
    if not os.path.isdir(folder):
        return out
    for n in os.listdir(folder):
        if n.lower().endswith('.sav'):
            p = os.path.join(folder, n)
            out.append(dict(ruta=p, nombre=n[:-4], tipo=n.split('_')[0],
                            fecha=datetime.datetime.fromtimestamp(os.path.getmtime(p)),
                            png=p[:-4] + '.png' if os.path.exists(p[:-4] + '.png') else None))
    out.sort(key=lambda s: s['fecha'], reverse=True)
    return out


def game_running():
    try:
        flags = 0x08000000 if sys.platform == 'win32' else 0   # CREATE_NO_WINDOW
        r = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq witcher3.exe', '/NH'],
                           capture_output=True, text=True, creationflags=flags, timeout=10)
        return 'witcher3.exe' in r.stdout.lower()
    except Exception:
        return False


def apply_changes(save, mgr):
    """Copia de seguridad -> escritura atomica -> verificacion.  Devuelve (manifest, W3Save recargada)."""
    changes = save.change_list()
    if not changes:
        raise ValueError('No hay cambios pendientes')
    before = save.summary()
    # 1) construir en memoria (verifica LZ4 y que solo cambian los bytes previstos)
    data = save.build_bytes()
    # 2) el archivo no debe haber cambiado desde que se cargo (p.ej. el juego lo sobrescribio)
    with open(save.path, 'rb') as f:
        if hashlib.sha256(f.read()).digest() != hashlib.sha256(save.container.file_bytes).digest():
            raise SaveFormatError('La partida ha cambiado en disco desde que se abrio. '
                                  'Vuelve a cargarla y repite los cambios.')
    # 3) copia de seguridad SIEMPRE antes de tocar nada
    manifest = mgr.backup_save(save.path, 'antes de modificar', changes=changes, summary=before)
    # 4) escritura atomica
    tmp = save.path + '.editor_tmp'
    try:
        with open(tmp, 'wb') as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        replace_with_retry(tmp, save.path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    # 5) releer del disco y comprobar
    reloaded = W3Save(save.path)
    with open(save.path, 'rb') as f:
        if f.read() != data:
            raise SaveFormatError('Lo escrito en disco no coincide; restaura la copia %s' % manifest['id'])
    mgr.log('modificacion', partida=os.path.basename(save.path)[:-4], copia_previa=manifest['id'],
            cambios=changes, resumen_antes=before, resumen_despues=reloaded.summary())
    return manifest, reloaded
