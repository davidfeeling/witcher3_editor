# Editor de partidas de The Witcher 3 (Remaster / next-gen)

Creado el 2026-10-03 analizando tus propias partidas
(`C:\Users\glown\OneDrive\Documents\The Witcher 3\gamesaves`, versión de juego 5.0+, formato de partida v66/v67).

## Cómo abrirlo

Doble clic en **`ABRIR_EDITOR_WITCHER3.cmd`**. Usa el Python 3.10 que ya tienes instalado y no necesita instalar nada.

## Qué se puede cambiar

| Qué | Cómo | Seguridad |
|---|---|---|
| **Coronas**, orenos, florines | Pestaña *Dinero y experiencia* | Segura (máximo 32767, ver abajo) |
| **Cantidad de cualquier objeto apilable** (ingredientes, materiales, comida, runas, glifos, mutágenos…) | Pestaña *Inventario*: seleccionar y pulsar **Duplicar (x2)**, **+10** o **Fijar** | Segura |
| **Copias de cartas de Gwynt** (señuelos, cuernos, tropas, cartas de héroe…) | Pestaña *Cartas de Gwynt*: seleccionar y pulsar **Fijar**, **+1**, **Duplicar (x2)** o **Fijar a 3** | Segura (1 a 99 copias) |
| Durabilidad del equipo | *Reparar seleccionados* / *Reparar todo el equipo* (lo deja al 100 %) | Segura |
| Experiencia | *Preparar +1/+3/+5 niveles* | Experimental: el nivel sube la **próxima vez que ganes XP** en el juego, y cada nivel da 1 punto de habilidad |
| Puntos de habilidad libres | Solo si ya tienes alguno sin gastar | Si tienes 0, el juego no guarda el campo y no se puede editar (usa la experiencia) |
| Cantidad > 1 en armas o armaduras | Se permite, con aviso | **Experimental**: el juego puede comportarse de forma rara |

**Qué no hace (a propósito):** crear objetos nuevos que no tengas, ni duplicar una espada única como un objeto aparte.
Para eso habría que insertar bytes y recalcular todas las tablas internas del archivo, y es fácil corromper la partida.
Todo lo que hace el editor cambia valores **del mismo tamaño**: ningún dato del archivo se desplaza.

## Uso paso a paso

1. Lo ideal es tener el juego **en el menú principal o cerrado**. Si lo tienes abierto, después de guardar con el editor
   carga la partida desde **Cargar partida**.
2. Elige una partida a la izquierda (la más reciente sale arriba). Verás la captura, las coronas, el nivel y la XP.
3. Haz los cambios. Se acumulan en **Cambios pendientes** y todavía no se ha tocado nada.
4. Pulsa **GUARDAR EN LA PARTIDA**. El editor hace esto, en orden:
   1. comprueba que la partida no ha cambiado en disco desde que la abriste;
   2. **hace una copia de seguridad** (`.sav` + `.png` + `.json`) y verifica la copia con SHA-256;
   3. reconstruye el archivo, recomprimiendo solo el bloque que contiene el cambio, y verifica que únicamente
      cambiaron los bytes previstos;
   4. escribe con reemplazo atómico, vuelve a leer la partida del disco y comprueba los valores;
   5. anota la operación en el histórico.
5. Carga la partida en el juego y comprueba el dinero.

## Copias de seguridad e histórico

Botón **Gestor de copias de seguridad / histórico**:

- Lista todas las copias, con la fecha, el motivo, el estado guardado (coronas, nivel, XP) y los cambios que se hicieron después.
- **Restaurar esta copia**: antes de restaurar, copia la versión actual, así que restaurar también se puede deshacer.
- **Verificar integridad**: comprueba el SHA-256 de los archivos de la copia.
- La pestaña **Histórico de operaciones** lista cada copia, modificación y restauración con sus valores de antes y después.
- **Copia completa de TODAS las partidas ahora**: copia toda la carpeta `gamesaves`.
  Ya existe una copia inicial: `backups\20261003_133432_602314_COMPLETA` (122 archivos).

Las copias están en `witcher3_editor\backups\` y el histórico en `witcher3_editor\historial.jsonl`. Nunca se borran solas.

## Primera prueba recomendada

1. Con el juego en el menú, abre el editor y selecciona tu última partida **manual**.
2. Sube las coronas (por ejemplo a 5000) y guarda.
3. En el juego: Cargar partida → esa partida → mira el inventario.
4. Si carga bien, el formato queda validado en tu juego. Si diera error, restaura desde el gestor.

## Límites y notas

- **Máximo 32767 por objeto**: el juego guarda la cantidad en 16 bits. No hay ninguna muestra que confirme si la lee
  con signo o sin él (tu máximo histórico son 1633 coronas), así que el editor no pasa de 32767, que es seguro en ambos casos.
- Cada objeto se muestra con su **nombre oficial en español** y con su nombre interno (ver más abajo).
- Las partidas de 2019-2020 (formato v64, anteriores al remaster) se detectan y **se rechazan**.
- Steam Cloud o la sincronización de OneDrive subirán la partida modificada como cualquier otra.

## Traducción al español

La pestaña *Inventario* tiene la columna **Nombre en español** con los nombres **oficiales** que ves en el juego.
Por ejemplo, `Light armor 03` es *Gambesón kaedweni*, `Gloryofthenorth` es *Gloria del Norte* y `Venom extract` es *Extracto venenoso*.
El buscador encuentra los objetos tanto por el nombre en español como por el interno, y las runas también salen traducidas.

- **Origen**: el editor lee, sin modificar nada, los archivos de tu instalación (`X:\games\witcher3\The Witcher 3 Wild Hunt GOTY`).
  De las definiciones de objetos (`bundles\*.bundle`) saca la clave de cada nombre, y de los textos en español
  (`es.w3strings`) saca el nombre. Así se obtuvieron 4269 nombres, base y expansiones, que cubren el 100 % de tu inventario.
- **Base de datos**: `traducciones_es.json`, con dos secciones:
  - `juego`: los nombres oficiales. Se regeneran con el botón **Regenerar traducciones desde el juego** (útil tras una actualización).
  - `manual`: traducciones puestas a mano, que tienen prioridad sobre las del juego. Incluye 19 objetos internos que el juego
    no traduce (partes del cuerpo, peinado, vainas…).
- **Corregir una traducción**: haz doble clic en el objeto y escribe el nombre. Si lo dejas vacío, vuelve al oficial.
- Las descripciones de los cambios pendientes y del histórico usan también el nombre en español.
- Con la línea de comandos puedes usar el nombre en español: `--cantidad "extracto venenoso=99"`.

## Línea de comandos (opcional)

```
python w3cli.py listar
python w3cli.py info ultima --objetos
python w3cli.py info ultima --cartas
python w3cli.py cambiar ultima --coronas 5000 --cantidad "Venom extract=90" --carta "Señuelo=3" --reparar
python w3cli.py copias
python w3cli.py historial
python w3cli.py restaurar <id o prefijo del id>
python w3cli.py copia-completa
```

## Archivos

| Archivo | Para qué |
|---|---|
| `w3save.py` | Lee y escribe el formato: LZ4, tabla de nombres, inventario, experiencia |
| `w3backup.py` | Copias, restauración e histórico |
| `w3comun.py` | Detecta la carpeta de partidas y aplica los cambios en orden (copia → escritura → verificación) |
| `w3editor_gui.py` | Interfaz gráfica |
| `w3cli.py` | Línea de comandos |
| `w3traduccion.py` | Extrae los nombres en español del juego y gestiona la base de datos de traducciones |
| `traducciones_es.json` | Base de datos de traducciones (secciones `juego`, `manual` y `cartas_gwynt`) |

## Formato (resumen técnico)

- `.sav` = cabecera `SNFHFZLC` + tabla de bloques + bloques **LZ4** independientes de 1 MiB (unos 4,8 MB descomprimidos).
- Datos descomprimidos: `SAV3`, versión 66/67. Los nombres (`Crowns`, `level`…) están en una tabla `NM`/`MANU`
  y se referencian con índices de 16 bits.
- Inventario de Geralt: el `CInventoryComponent` precedido de las etiquetas `PLAYER`/`GERALT`. Cada objeto guarda
  `nombre, semilla, flags, 7 bytes, tinte, color, CANTIDAD (u16), DURABILIDAD (float), modificadores, id, runas, habilidades, categoría`.
- Cartas de Gwynt: el objeto `CR4GwintManager` → `SBCollectionCard` (colección de cartas) y `SBLeaderCollectionCard` (líderes).
  Cada carta guarda `cardIndex` (int32) y `numCopies` (int32). Al editar copias se modifica el valor exacto sin alterar la estructura.
- Experiencia: el objeto `levelManager` → `points` (`SSpendablePoints`): [0] = puntos de habilidad, [1] = experiencia
  (`used` = XP base del nivel actual, `free` = XP ganada dentro del nivel). Las propiedades que valen 0 no se guardan.
