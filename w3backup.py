"""
Gestor de copias de seguridad de partidas de The Witcher 3, con historico.

Estructura (dentro de la carpeta del editor):
  backups/<AAAAMMDD_HHMMSS_ffffff>_<partida>/   archivos .sav/.png/.json + manifest.json
  backups/<AAAAMMDD_HHMMSS_ffffff>_COMPLETA/    copia de TODAS las partidas
  historial.jsonl                               una linea JSON por operacion (solo se anade)

Reglas:
  - Antes de modificar una partida se copia (sav+png+json) y se verifica el SHA-256 de la copia.
  - Antes de restaurar, se hace copia de lo que hay ahora (la restauracion tambien se puede deshacer).
  - Las copias nunca se borran solas.
"""
import datetime
import hashlib
import json
import os
import shutil
import time

SAVE_EXTS = ('.sav', '.png', '.json')


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def _now():
    return datetime.datetime.now()


def replace_with_retry(src, dst, tries=10):
    """os.replace con reintentos (OneDrive o el juego pueden bloquear el archivo un instante)."""
    for k in range(tries):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if k == tries - 1:
                raise
            time.sleep(0.5)


class BackupManager:
    def __init__(self, root):
        self.root = os.path.abspath(root)
        self.backup_dir = os.path.join(self.root, 'backups')
        self.log_path = os.path.join(self.root, 'historial.jsonl')
        os.makedirs(self.backup_dir, exist_ok=True)

    # ------------------------------------------------------------------ historico
    def log(self, action, **data):
        entry = dict(fecha=_now().isoformat(timespec='seconds'), accion=action)
        entry.update(data)
        with open(self.log_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry, ensure_ascii=False) + '\n')
        return entry

    def history(self):
        out = []
        if os.path.exists(self.log_path):
            with open(self.log_path, encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            out.append(json.loads(line))
                        except ValueError:
                            pass
        return out

    # -------------------------------------------------------------------- copias
    @staticmethod
    def files_of_save(sav_path):
        stem = os.path.splitext(sav_path)[0]
        return [stem + ext for ext in SAVE_EXTS if os.path.exists(stem + ext)]

    def _new_folder(self, label):
        bid = _now().strftime('%Y%m%d_%H%M%S_%f') + '_' + label
        path = os.path.join(self.backup_dir, bid)
        os.makedirs(path)
        return bid, path

    def _copy_verified(self, files, dest):
        info = []
        for src in files:
            name = os.path.basename(src)
            h_src = sha256_file(src)
            dst = os.path.join(dest, name)
            shutil.copy2(src, dst)
            if sha256_file(dst) != h_src:
                raise IOError('La copia de %s no coincide (SHA-256)' % name)
            info.append(dict(nombre=name, sha256=h_src, bytes=os.path.getsize(dst)))
        return info

    def backup_save(self, sav_path, reason, changes=None, summary=None):
        """Copia una partida (sav+png+json).  Devuelve el manifest."""
        files = self.files_of_save(sav_path)
        if not any(f.lower().endswith('.sav') for f in files):
            raise FileNotFoundError(sav_path)
        save_name = os.path.splitext(os.path.basename(sav_path))[0]
        bid, folder = self._new_folder(save_name)
        try:
            manifest = dict(id=bid, fecha=_now().isoformat(timespec='seconds'), tipo='partida',
                            partida=save_name, motivo=reason,
                            carpeta_origen=os.path.dirname(os.path.abspath(sav_path)),
                            archivos=self._copy_verified(files, folder),
                            cambios=changes or [], resumen=summary or {})
            with open(os.path.join(folder, 'manifest.json'), 'w', encoding='utf-8') as f:
                json.dump(manifest, f, ensure_ascii=False, indent=2)
        except Exception:
            shutil.rmtree(folder, ignore_errors=True)
            raise
        self.log('backup', id=bid, partida=save_name, motivo=reason)
        return manifest

    def backup_all(self, saves_dir, reason='copia completa manual'):
        files = sorted(os.path.join(saves_dir, n) for n in os.listdir(saves_dir)
                       if os.path.splitext(n)[1].lower() in SAVE_EXTS
                       and os.path.isfile(os.path.join(saves_dir, n)))
        bid, folder = self._new_folder('COMPLETA')
        try:
            manifest = dict(id=bid, fecha=_now().isoformat(timespec='seconds'), tipo='completa',
                            partida='(todas: %d archivos)' % len(files), motivo=reason,
                            carpeta_origen=os.path.abspath(saves_dir),
                            archivos=self._copy_verified(files, folder), cambios=[], resumen={})
            with open(os.path.join(folder, 'manifest.json'), 'w', encoding='utf-8') as f:
                json.dump(manifest, f, ensure_ascii=False, indent=2)
        except Exception:
            shutil.rmtree(folder, ignore_errors=True)
            raise
        self.log('backup_completo', id=bid, archivos=len(files), motivo=reason)
        return manifest

    def list_backups(self):
        out = []
        for bid in os.listdir(self.backup_dir):
            mp = os.path.join(self.backup_dir, bid, 'manifest.json')
            if os.path.exists(mp):
                try:
                    with open(mp, encoding='utf-8') as f:
                        m = json.load(f)
                    m['_ruta'] = os.path.join(self.backup_dir, bid)
                    out.append(m)
                except ValueError:
                    pass
        out.sort(key=lambda m: m['id'], reverse=True)
        return out

    def get(self, bid):
        """Busca una copia por id completo o por un prefijo unico del id."""
        backups = self.list_backups()
        for m in backups:
            if m['id'] == bid:
                return m
        hits = [m for m in backups if m['id'].startswith(bid)]
        if len(hits) == 1:
            return hits[0]
        raise KeyError('Copia no encontrada o ambigua: %s' % bid)

    def verify(self, bid):
        """Comprueba que los archivos de la copia siguen intactos."""
        m = self.get(bid)
        bad = [a['nombre'] for a in m['archivos']
               if not os.path.exists(os.path.join(m['_ruta'], a['nombre']))
               or sha256_file(os.path.join(m['_ruta'], a['nombre'])) != a['sha256']]
        return bad

    # --------------------------------------------------------------- restaurar
    def restore(self, bid, dest_dir=None, only_names=None):
        """Restaura una copia.  Antes guarda lo que hay ahora en otra copia."""
        m = self.get(bid)
        dest_dir = dest_dir or m['carpeta_origen']
        if not os.path.isdir(dest_dir):
            raise FileNotFoundError(dest_dir)
        bad = self.verify(bid)
        if bad:
            raise IOError('La copia esta danada: %s' % ', '.join(bad))
        files = [a for a in m['archivos'] if not only_names or a['nombre'] in only_names]
        # 1) copia de lo actual
        current = [os.path.join(dest_dir, a['nombre']) for a in files
                   if os.path.exists(os.path.join(dest_dir, a['nombre']))]
        pre = None
        if current:
            label = (m['partida'] if m['tipo'] == 'partida' else 'COMPLETA') + '_PRE-RESTAURAR'
            pbid, folder = self._new_folder(label)
            pre = dict(id=pbid, fecha=_now().isoformat(timespec='seconds'),
                       tipo=m['tipo'], partida=m['partida'],
                       motivo='antes de restaurar la copia %s' % bid,
                       carpeta_origen=dest_dir, archivos=self._copy_verified(current, folder),
                       cambios=[], resumen={})
            with open(os.path.join(folder, 'manifest.json'), 'w', encoding='utf-8') as f:
                json.dump(pre, f, ensure_ascii=False, indent=2)
            self.log('backup', id=pbid, partida=m['partida'], motivo=pre['motivo'])
        # 2) restaurar (tmp + replace atomico) y verificar
        for a in files:
            src = os.path.join(m['_ruta'], a['nombre'])
            dst = os.path.join(dest_dir, a['nombre'])
            tmp = dst + '.restaurando'
            shutil.copy2(src, tmp)
            replace_with_retry(tmp, dst)
            if sha256_file(dst) != a['sha256']:
                raise IOError('Verificacion fallida al restaurar %s' % a['nombre'])
        self.log('restauracion', id=bid, partida=m['partida'], archivos=len(files),
                 copia_previa=pre['id'] if pre else None)
        return pre

    def delete(self, bid):
        m = self.get(bid)
        shutil.rmtree(m['_ruta'])
        self.log('borrado_copia', id=bid, partida=m['partida'])
