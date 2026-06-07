import sys
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                               QHBoxLayout, QLabel, QLineEdit, QTreeWidget,
                               QTreeWidgetItem, QPushButton, QFrame, QAbstractItemView,
                               QMessageBox, QGroupBox, QTabWidget, QListWidget,
                               QListWidgetItem, QSplitter, QFileDialog, QInputDialog,
                               QDialog, QDialogButtonBox, QTextEdit, QRadioButton)
from PySide6.QtCore import Qt, QMimeData
from PySide6.QtGui import QDrag, QFont, QColor
from neo4j import GraphDatabase

from archetypes import ARCHETYPES, resolve_archetype, archetypes_by_category
from io_manager import export_json, import_json, FORMAT_VERSION

# ── Icone ──────────────────────────────────────────────────────────────────────
CATEGORY_ICONS = {
    "illuminazione": "💡",
    "coperture":     "🪟",
    "clima":         "🌡",
    "interruttori":  "🔌",
    "sicurezza":     "🔒",
    "sensori":       "📡",
    "multimedia":    "🎵",
}
AREA_ICONS = {"root": "🏠", "child": "📦"}
DEVICE_ICON = "🔧"


def device_icon(archetype_id: str) -> str:
    cat = ARCHETYPES.get(archetype_id, {}).get("category", "")
    return CATEGORY_ICONS.get(cat, "🔧")


# ══════════════════════════════════════════════════════════════════════════════
# Neo4j
# ══════════════════════════════════════════════════════════════════════════════
class Neo4jManager:
    def __init__(self):
        self.uri      = "bolt://88.222.220.208:7687"
        self.user     = "neo4j"
        self.password = "password"
        self.driver   = GraphDatabase.driver(self.uri, auth=(self.user, self.password))

    # ── Struttura ──────────────────────────────────────────────────────────────
    def save_area(self, name: str):
        with self.driver.session() as s:
            s.run("MERGE (n:Area {id:$n}) SET n.name=$n", n=name)

    def save_device(self, name: str, archetype_id: str):
        """
        Crea/aggiorna il nodo Archetype nel grafo con i suoi alias di default,
        crea il Device, collega con INSTANCE_OF, crea i Command flat.
        """
        resolved = resolve_archetype(archetype_id)
        with self.driver.session() as s:

            # ── Nodo Archetype (unico per tipo) ───────────────────────────────
            s.run("""
                MERGE (a:Archetype {id:$aid})
                SET a.label=$lbl, a.category=$cat,
                    a.default_command=COALESCE(a.default_command, $dcmd),
                    a.default_item=COALESCE(a.default_item, $ditem)
            """, aid=archetype_id, lbl=resolved["label"], cat=resolved["category"],
                dcmd=resolved.get("default_command"),
                ditem=resolved.get("default_item"))

            # Alias di default sull'archetipo (MERGE = non duplica)
            for alias in resolved["default_aliases"]:
                s.run("""
                    MATCH (a:Archetype {id:$aid})
                    MERGE (al:Alias {value:$v, owner:$aid})
                    SET al.type='archetype'
                    MERGE (a)-[:HAS_ALIAS]->(al)
                """, aid=archetype_id, v=alias.strip().lower())

            # ── Nodo Device ───────────────────────────────────────────────────
            s.run("""
                MERGE (d:Device {id:$name})
                SET d.name=$name, d.archetype=$arch, d.ha_entity_id=''
            """, name=name, arch=archetype_id)

            # ── INSTANCE_OF ───────────────────────────────────────────────────
            s.run("""
                MATCH (d:Device {id:$name}), (a:Archetype {id:$aid})
                MERGE (d)-[:INSTANCE_OF]->(a)
            """, name=name, aid=archetype_id)

            # ── Command flat + HAS_COMMAND ─────────────────────────────────
            for cmd_id, cmd in resolved["commands"].items():
                s.run("""
                    MERGE (c:Command {id:$cid})
                    SET c.label=$lbl, c.ha_service_key=$ha
                """, cid=cmd_id, lbl=cmd["label"], ha=cmd["ha_service_key"])
                s.run("""
                    MATCH (d:Device {id:$dev}),(c:Command {id:$cid})
                    MERGE (d)-[:HAS_COMMAND]->(c)
                """, dev=name, cid=cmd_id)
                for p in cmd["params"]:
                    pid = f"{name}__{cmd_id}__{p['id']}"
                    s.run("""
                        MERGE (p:Parameter {id:$pid})
                        SET p.param_id=$pi, p.type=$t, p.unit=$u,
                            p.min=$mn, p.max=$mx, p.values=$v
                    """, pid=pid, pi=p["id"], t=p["type"],
                        u=p.get("unit", ""), mn=p.get("min"), mx=p.get("max"),
                        v=",".join(p["values"]) if p.get("values") else "")
                    s.run("""
                        MATCH (c:Command {id:$cid}),(p:Parameter {id:$pid})
                        MERGE (c)-[:HAS_PARAM]->(p)
                    """, cid=cmd_id, pid=pid)

    def set_ha_entity_id(self, device_id: str, entity_id: str):
        with self.driver.session() as s:
            s.run("MATCH (d:Device {id:$id}) SET d.ha_entity_id=$eid",
                  id=device_id, eid=entity_id.strip())

    def get_ha_entity_id(self, device_id: str) -> str:
        with self.driver.session() as s:
            r = s.run("MATCH (d:Device {id:$id}) RETURN d.ha_entity_id as eid",
                      id=device_id).single()
            return (r["eid"] or "") if r else ""

    def rename_node(self, old: str, new: str):
        with self.driver.session() as s:
            s.run("MATCH (n {id:$old}) SET n.id=$new, n.name=$new", old=old, new=new)

    def move_area(self, area_id: str, new_parent: str):
        with self.driver.session() as s:
            s.run("MATCH (:Area)-[r:CONTAINS]->(c {id:$c}) DELETE r", c=area_id)
            s.run("MATCH (p:Area {id:$p}),(c {id:$c}) MERGE (p)-[:CONTAINS]->(c)",
                  p=new_parent, c=area_id)

    def move_device(self, device_id: str, new_area: str):
        with self.driver.session() as s:
            s.run("MATCH (d:Device {id:$d})-[r:BELONGS]->(:Area) DELETE r", d=device_id)
            s.run("MATCH (d:Device {id:$d}),(a:Area {id:$a}) MERGE (d)-[:BELONGS]->(a)",
                  d=device_id, a=new_area)

    def delete_device(self, device_id: str):
        with self.driver.session() as s:
            # Elimina Parameter scoped
            s.run("""
                MATCH (d:Device {id:$id})-[:HAS_COMMAND]->(:Command)
                      -[:HAS_PARAM]->(p:Parameter)
                WHERE p.id STARTS WITH $pfx DETACH DELETE p
            """, id=device_id, pfx=device_id + "__")
            # Elimina alias custom sull'istanza (non quelli sull'archetipo)
            s.run("""
                MATCH (d:Device {id:$id})-[r:HAS_ALIAS]->(a:Alias)
                DELETE r, a
            """, id=device_id)
            s.run("MATCH (d:Device {id:$id}) DETACH DELETE d", id=device_id)

    def delete_area_simple(self, area_id: str):
        with self.driver.session() as s:
            s.run("MATCH (d:Device)-[:BELONGS]->(a:Area {id:$id}) DETACH DELETE d", id=area_id)
            s.run("MATCH (a:Area {id:$id}) DETACH DELETE a", id=area_id)

    def delete_area_recursive(self, area_id: str):
        with self.driver.session() as s:
            s.run("""
                MATCH (r:Area {id:$id})
                OPTIONAL MATCH (r)-[:CONTAINS*0..]->(sub:Area)
                OPTIONAL MATCH (d:Device)-[:BELONGS]->(sub)
                DETACH DELETE d
            """, id=area_id)
            s.run("""
                MATCH (r:Area {id:$id})
                OPTIONAL MATCH (r)-[:CONTAINS*0..]->(sub:Area)
                DETACH DELETE sub, r
            """, id=area_id)

    def get_node_label(self, node_id: str) -> str | None:
        with self.driver.session() as s:
            r = s.run("MATCH (n {id:$id}) RETURN labels(n)[0] as l", id=node_id).single()
            return r["l"] if r else None

    def get_node_archetype(self, node_id: str) -> str | None:
        with self.driver.session() as s:
            r = s.run("MATCH (d:Device {id:$id}) RETURN d.archetype as a", id=node_id).single()
            return r["a"] if r else None

    def is_descendant(self, ancestor: str, candidate: str) -> bool:
        with self.driver.session() as s:
            r = s.run("""
                MATCH ({id:$anc})-[:CONTAINS*]->({id:$cand})
                RETURN count(*) > 0 AS found
            """, anc=ancestor, cand=candidate).single()
            return r["found"] if r else False

    def get_full_hierarchy(self):
        with self.driver.session() as s:
            nodes = list(s.run(
                "MATCH (n) WHERE n:Area OR n:Device "
                "RETURN n.id as id, labels(n)[0] as label, "
                "n.archetype as archetype, n.ha_entity_id as ha_entity_id"
            ))
            cr = list(s.run(
                "MATCH (p:Area)-[:CONTAINS]->(c) RETURN p.id as parent, c.id as child"
            ))
            br = list(s.run(
                "MATCH (d:Device)-[:BELONGS]->(a:Area) RETURN a.id as parent, d.id as child"
            ))
            return nodes, cr, br

    # ── Alias su Area o Device (alias custom istanza) ──────────────────────────
    def get_aliases(self, node_id: str) -> list[str]:
        """Alias diretti sul nodo (Area, Device istanza, Archetype, Command)."""
        with self.driver.session() as s:
            return [r["v"] for r in s.run(
                "MATCH (n {id:$id})-[:HAS_ALIAS]->(a:Alias) "
                "RETURN a.value as v ORDER BY v", id=node_id)]

    def add_alias(self, node_id: str, value: str, alias_type: str):
        with self.driver.session() as s:
            s.run("""
                MATCH (n {id:$id})
                MERGE (a:Alias {value:$v, owner:$id})
                SET a.type=$t
                MERGE (n)-[:HAS_ALIAS]->(a)
            """, id=node_id, v=value.strip().lower(), t=alias_type)

    def delete_alias(self, node_id: str, value: str):
        with self.driver.session() as s:
            s.run("""
                MATCH (n {id:$id})-[r:HAS_ALIAS]->(a:Alias {value:$v, owner:$id})
                DELETE r, a
            """, id=node_id, v=value)

    # ── Archetipi vivi (con almeno un'istanza Device) ──────────────────────────
    def get_live_archetypes(self) -> list[dict]:
        with self.driver.session() as s:
            return [{"id": r["aid"], "label": r["lbl"],
                     "default_command": r["dcmd"], "default_item": r["ditem"]}
                    for r in s.run("""
                MATCH (d:Device)-[:INSTANCE_OF]->(a:Archetype)
                RETURN DISTINCT a.id as aid, a.label as lbl,
                       a.default_command as dcmd, a.default_item as ditem
                ORDER BY lbl
            """)]

    def set_archetype_defaults(self, arch_id: str,
                               default_command: str | None,
                               default_item: str | None):
        with self.driver.session() as s:
            s.run("""
                MATCH (a:Archetype {id:$aid})
                SET a.default_command=$dcmd, a.default_item=$ditem
            """, aid=arch_id, dcmd=default_command or None,
                ditem=default_item or None)

    def get_archetype_defaults(self, arch_id: str) -> dict:
        with self.driver.session() as s:
            r = s.run("""
                MATCH (a:Archetype {id:$aid})
                RETURN a.default_command as dcmd, a.default_item as ditem,
                       a.label as lbl
            """, aid=arch_id).single()
            if not r:
                return {"default_command": None, "default_item": None, "label": ""}
            return {"default_command": r["dcmd"],
                    "default_item":    r["ditem"],
                    "label":           r["lbl"]}

    def get_device_ids_by_archetype(self, arch_id: str) -> list[str]:
        """Lista id device di un archetipo — per il combobox default_item."""
        with self.driver.session() as s:
            return [r["did"] for r in s.run("""
                MATCH (d:Device)-[:INSTANCE_OF]->(:Archetype {id:$aid})
                RETURN d.id as did ORDER BY did
            """, aid=arch_id)]

    def get_devices_by_archetype(self, archetype_id: str) -> list[dict]:
        """Istanze Device di un archetipo con conteggio alias custom sull'istanza."""
        with self.driver.session() as s:
            return [{"id": r["id"], "alias_count": r["cnt"]} for r in s.run("""
                MATCH (d:Device)-[:INSTANCE_OF]->(:Archetype {id:$arch})
                OPTIONAL MATCH (d)-[:HAS_ALIAS]->(a:Alias)
                RETURN d.id as id, count(a) as cnt ORDER BY id
            """, arch=archetype_id)]

    # ── Comandi vivi ───────────────────────────────────────────────────────────
    def get_live_commands(self) -> list[dict]:
        with self.driver.session() as s:
            return [{"id": r["id"], "label": r["lbl"]} for r in s.run(
                "MATCH (c:Command) RETURN c.id as id, c.label as lbl ORDER BY lbl"
            )]


# ══════════════════════════════════════════════════════════════════════════════
# Helpers UI condivisi
# ══════════════════════════════════════════════════════════════════════════════
def build_structure_tree(tree: QTreeWidget, all_nodes, cr, br, children_ids: set):
    tree.clear()
    nodes = {}

    def make_item(rec):
        nid  = rec["id"]
        lbl  = rec["label"]
        arch = rec["archetype"]
        eid  = rec.get("ha_entity_id") or ""
        if lbl == "Area":
            icon = AREA_ICONS["root"] if nid not in children_ids else AREA_ICONS["child"]
            text = f"{icon}  {nid}"
        else:
            icon    = device_icon(arch) if arch else DEVICE_ICON
            eid_tag = f"  [{eid}]" if eid else "  [⚠ entity id mancante]"
            text    = f"{icon}  {nid}{eid_tag}"
        item = QTreeWidgetItem([text])
        item.setData(0, Qt.UserRole,     nid)
        item.setData(0, Qt.UserRole + 1, lbl)
        if lbl == "Device" and not eid:
            item.setForeground(0, QColor("#e07b39"))
        return item

    for rec in all_nodes:
        if rec["id"] not in children_ids:
            item = make_item(rec)
            tree.addTopLevelItem(item)
            nodes[rec["id"]] = item

    for rec in all_nodes:
        nid = rec["id"]
        if nid in children_ids and nid not in nodes:
            nodes[nid] = make_item(rec)

    for rel in cr:
        p, c = rel["parent"], rel["child"]
        if p in nodes and c in nodes:
            nodes[p].addChild(nodes[c])

    for rel in br:
        p, c = rel["parent"], rel["child"]
        if p in nodes and c in nodes:
            nodes[p].addChild(nodes[c])

    tree.expandAll()
    return nodes


class AliasPanel(QWidget):
    """Pannello alias riusabile per aree, archetipi, istanze device e comandi."""

    def __init__(self, db: Neo4jManager, parent=None):
        super().__init__(parent)
        self.db         = db
        self._node_id   = None
        self._node_type = None
        self._init_ui()

    def _init_ui(self):
        lay = QVBoxLayout(self)
        self.title = QLabel("← Seleziona un elemento")
        f = QFont(); f.setBold(True); f.setPointSize(11)
        self.title.setFont(f)
        self.alias_list = QListWidget()
        row = QHBoxLayout()
        self.inp = QLineEdit()
        self.inp.setPlaceholderText("Nuovo alias...")
        self.inp.setEnabled(False)
        self.inp.returnPressed.connect(self._add)
        add_btn = QPushButton("+"); add_btn.setFixedWidth(32)
        add_btn.clicked.connect(self._add)
        row.addWidget(self.inp); row.addWidget(add_btn)
        self.del_btn = QPushButton("🗑 Rimuovi selezionato")
        self.del_btn.setEnabled(False)
        self.del_btn.clicked.connect(self._delete)
        self.status = QLabel(""); self.status.setStyleSheet("color:#888;")
        lay.addWidget(self.title)
        lay.addWidget(QLabel("Alias:"))
        lay.addWidget(self.alias_list)
        lay.addLayout(row)
        lay.addWidget(self.del_btn)
        lay.addWidget(self.status)
        self.alias_list.itemSelectionChanged.connect(
            lambda: self.del_btn.setEnabled(bool(self.alias_list.selectedItems())))

    def load(self, node_id: str, node_type: str, title: str):
        self._node_id   = node_id
        self._node_type = node_type
        self.title.setText(title)
        self.inp.setEnabled(True)
        self.inp.setFocus()
        self._refresh()

    def clear(self):
        self._node_id = self._node_type = None
        self.title.setText("← Seleziona un elemento")
        self.alias_list.clear()
        self.inp.setEnabled(False); self.inp.clear()
        self.del_btn.setEnabled(False); self.status.setText("")

    def _refresh(self):
        self.alias_list.clear()
        if not self._node_id:
            return
        for a in self.db.get_aliases(self._node_id):
            self.alias_list.addItem(a)
        self.status.setText(f"{self.alias_list.count()} alias")

    def _add(self):
        v = self.inp.text().strip().lower()
        if not v or not self._node_id:
            return
        existing = [self.alias_list.item(i).text() for i in range(self.alias_list.count())]
        if v in existing:
            self.status.setText("⚠ Alias già presente"); return
        try:
            self.db.add_alias(self._node_id, v, self._node_type)
            self.inp.clear(); self._refresh()
        except Exception as e:
            self.status.setText(f"✗ {e}")

    def _delete(self):
        items = self.alias_list.selectedItems()
        if not items or not self._node_id:
            return
        try:
            self.db.delete_alias(self._node_id, items[0].text())
            self._refresh()
        except Exception as e:
            self.status.setText(f"✗ {e}")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — World Builder
# ══════════════════════════════════════════════════════════════════════════════
class ArchetypeTree(QTreeWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.setDragDropMode(QAbstractItemView.DragOnly)
        self.setDefaultDropAction(Qt.CopyAction)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self._populate()

    def _populate(self):
        ai = QTreeWidgetItem(self, ["🏠  Area"])
        ai.setData(0, Qt.UserRole, "Area")
        ai.setFlags(ai.flags() | Qt.ItemIsDragEnabled)
        for cat, items in archetypes_by_category().items():
            ci = QTreeWidgetItem(self, [f"{CATEGORY_ICONS.get(cat, '📦')}  {cat.capitalize()}"])
            ci.setFlags(ci.flags() & ~Qt.ItemIsDragEnabled)
            for aid, lbl in items:
                ch = QTreeWidgetItem(ci, [f"  {lbl}"])
                ch.setData(0, Qt.UserRole, aid)
                ch.setFlags(ch.flags() | Qt.ItemIsDragEnabled)
        self.expandAll()

    def startDrag(self, _):
        item = self.currentItem()
        if not item: return
        aid = item.data(0, Qt.UserRole)
        if not aid: return
        mime = QMimeData(); mime.setText(f"archetype:{aid}")
        drag = QDrag(self); drag.setMimeData(mime); drag.exec(Qt.CopyAction)


class DropTree(QTreeWidget):
    def __init__(self, on_archetype_drop, on_internal_drop, on_item_selected, parent=None):
        super().__init__(parent)
        self.on_archetype_drop = on_archetype_drop
        self.on_internal_drop  = on_internal_drop
        self.on_item_selected  = on_item_selected
        self.setAcceptDrops(True); self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragDrop)
        self.setDefaultDropAction(Qt.MoveAction)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self._src = None
        self.itemClicked.connect(self._clicked)

    def _clicked(self, item, _):
        nid = item.data(0, Qt.UserRole)
        if nid: self.on_item_selected(nid)

    def mousePressEvent(self, e):
        super().mousePressEvent(e)
        item = self.itemAt(e.pos())
        self._src = item.data(0, Qt.UserRole) if item else None

    def startDrag(self, _):
        if not self.currentItem() or not self._src: return
        mime = QMimeData(); mime.setText(f"node:{self._src}")
        drag = QDrag(self); drag.setMimeData(mime); drag.exec(Qt.MoveAction)

    def _is_area(self, pos):
        item = self.itemAt(pos)
        return item.data(0, Qt.UserRole + 1) == "Area" if item else False

    def dragEnterEvent(self, e):
        e.acceptProposedAction() if e.mimeData().hasText() else e.ignore()

    def dragMoveEvent(self, e):
        if not e.mimeData().hasText(): e.ignore(); return
        if e.mimeData().text().startswith("node:"):
            e.acceptProposedAction() if self._is_area(e.pos()) else e.ignore(); return
        e.acceptProposedAction()

    def dropEvent(self, e):
        if not e.mimeData().hasText(): e.ignore(); return
        payload = e.mimeData().text()
        ti = self.itemAt(e.pos())
        tid = ti.data(0, Qt.UserRole) if ti else None
        is_area = self._is_area(e.pos())
        if payload.startswith("archetype:"):
            self.on_archetype_drop(payload.split(":", 1)[1], tid if is_area else None)
            e.acceptProposedAction()
        elif payload.startswith("node:"):
            sid = payload.split(":", 1)[1]
            if not tid or not is_area: e.ignore(); return
            self.on_internal_drop(sid, tid); e.acceptProposedAction()


class WorldBuilderTab(QWidget):
    def __init__(self, db: Neo4jManager, parent=None):
        super().__init__(parent)
        self.db = db
        self._sel_id = self._sel_lbl = None
        self._pend_arch = self._pend_par = None
        self._init_ui()
        self.refresh()

    def _init_ui(self):
        root = QHBoxLayout(self)
        left = QVBoxLayout()

        self.arch_tree = ArchetypeTree()
        self.arch_tree.setMaximumHeight(300)

        cb = QGroupBox("Crea nodo"); cl = QVBoxLayout(cb)
        self.name_inp = QLineEdit(); self.name_inp.setPlaceholderText("Nome nodo...")
        self.pend_lbl = QLabel(""); self.pend_lbl.setStyleSheet("color:#aaa;font-style:italic;")
        cl.addWidget(self.name_inp); cl.addWidget(self.pend_lbl)

        ab = QGroupBox("Nodo selezionato"); al = QVBoxLayout(ab)
        self.sel_lbl = QLabel("—"); self.sel_lbl.setWordWrap(True)

        # ha_entity_id — visibile solo per device
        self.eid_row = QWidget()
        eid_lay = QHBoxLayout(self.eid_row); eid_lay.setContentsMargins(0, 0, 0, 0)
        self.eid_inp = QLineEdit(); self.eid_inp.setPlaceholderText("es. light.luce_soggiorno")
        eid_save = QPushButton("💾"); eid_save.setFixedWidth(32)
        eid_save.setToolTip("Salva ha_entity_id")
        eid_save.clicked.connect(self._save_eid)
        self.eid_inp.returnPressed.connect(self._save_eid)
        eid_lay.addWidget(QLabel("HA entity id:"))
        eid_lay.addWidget(self.eid_inp)
        eid_lay.addWidget(eid_save)
        self.eid_row.setVisible(False)

        self.rename_btn = QPushButton("✏ Rinomina"); self.rename_btn.setEnabled(False)
        self.rename_btn.clicked.connect(self._rename)
        self.del_btn = QPushButton("🗑 Elimina"); self.del_btn.setEnabled(False)
        self.del_btn.clicked.connect(self._delete)

        al.addWidget(self.sel_lbl)
        al.addWidget(self.eid_row)
        al.addWidget(self.rename_btn)
        al.addWidget(self.del_btn)

        self.status = QLabel("← Trascina un archetipo sull'albero")
        self.status.setFrameStyle(QFrame.Panel | QFrame.Sunken)
        self.status.setWordWrap(True)
        rb = QPushButton("↻ Aggiorna"); rb.clicked.connect(self.refresh)

        io_box = QGroupBox("Import / Export")
        io_lay = QHBoxLayout(io_box)
        exp_btn = QPushButton("📤 Esporta JSON"); exp_btn.clicked.connect(self._export)
        imp_btn = QPushButton("📥 Importa JSON"); imp_btn.clicked.connect(self._import)
        io_lay.addWidget(exp_btn); io_lay.addWidget(imp_btn)

        left.addWidget(QLabel("Archetipi"))
        left.addWidget(self.arch_tree)
        left.addWidget(cb); left.addWidget(ab)
        left.addWidget(io_box)
        left.addWidget(self.status); left.addWidget(rb)

        right = QVBoxLayout()
        self.tree = DropTree(self._arch_drop, self._int_drop, self._sel)
        self.tree.setHeaderLabel("Struttura domotica  [arancio = entity id mancante]")
        right.addWidget(self.tree)

        root.addLayout(left, 1); root.addLayout(right, 2)

    def refresh(self):
        try:
            nodes, cr, br = self.db.get_full_hierarchy()
        except Exception as e:
            self.status.setText(f"✗ {e}"); return
        cids = {r["child"] for r in cr} | {r["child"] for r in br}
        build_structure_tree(self.tree, nodes, cr, br, cids)

    def _sel(self, node_id: str):
        self._sel_id  = node_id
        self._sel_lbl = self.db.get_node_label(node_id)
        arch = self.db.get_node_archetype(node_id) if self._sel_lbl == "Device" else None
        self.name_inp.setText(node_id)
        self.rename_btn.setEnabled(True); self.del_btn.setEnabled(True)
        if self._sel_lbl == "Area":
            self.sel_lbl.setText(f"🏠 {node_id}  [Area]")
            self.del_btn.setText("🗑 Elimina area...")
            self.eid_row.setVisible(False)
        else:
            icon = device_icon(arch) if arch else "🔧"
            lbl  = ARCHETYPES[arch]["label"] if arch else ""
            self.sel_lbl.setText(f"{icon} {node_id}  [{lbl}]")
            self.del_btn.setText("🗑 Elimina dispositivo")
            self.eid_inp.setText(self.db.get_ha_entity_id(node_id))
            self.eid_row.setVisible(True)
        self.status.setText(f"Selezionato: {node_id}")

    def _save_eid(self):
        if not self._sel_id or self._sel_lbl != "Device": return
        eid = self.eid_inp.text().strip()
        try:
            self.db.set_ha_entity_id(self._sel_id, eid)
            self.status.setText(f"✓ entity id '{eid}' salvato per '{self._sel_id}'")
            self.refresh()
        except Exception as e:
            self.status.setText(f"✗ {e}")

    def _clear(self):
        self._sel_id = self._sel_lbl = None
        self.rename_btn.setEnabled(False); self.del_btn.setEnabled(False)
        self.del_btn.setText("🗑 Elimina"); self.sel_lbl.setText("—")
        self.name_inp.clear(); self.eid_inp.clear(); self.eid_row.setVisible(False)

    def _arch_drop(self, arch_id: str, parent_id: str | None = None):
        name = self.name_inp.text().strip()
        if not name:
            self._pend_arch = arch_id; self._pend_par = parent_id
            lbl = ARCHETYPES[arch_id]["label"] if arch_id != "Area" else "Area"
            self.pend_lbl.setText(f"In attesa: {lbl} — inserisci nome e premi Invio")
            self.name_inp.setFocus(); self.name_inp.returnPressed.connect(self._confirm)
            return
        self._create(arch_id, name, parent_id)

    def _confirm(self):
        try: self.name_inp.returnPressed.disconnect(self._confirm)
        except RuntimeError: pass
        name = self.name_inp.text().strip()
        if name and self._pend_arch:
            self._create(self._pend_arch, name, self._pend_par)
        self._pend_arch = self._pend_par = None; self.pend_lbl.setText("")

    def _create(self, arch_id: str, name: str, parent_id: str | None = None):
        try:
            if arch_id == "Area":
                self.db.save_area(name)
                if parent_id: self.db.move_area(name, parent_id)
                self.status.setText(
                    f"✓ Area '{name}' creata" + (f" in '{parent_id}'" if parent_id else ""))
            else:
                self.db.save_device(name, arch_id)
                if parent_id: self.db.move_device(name, parent_id)
                lbl = ARCHETYPES[arch_id]["label"]
                n_aliases = len(resolve_archetype(arch_id)["default_aliases"])
                self.status.setText(
                    f"✓ {lbl} '{name}' creato"
                    + (f" in '{parent_id}'" if parent_id else "")
                    + f"  ({n_aliases} alias su archetipo)")
            self._clear(); self.refresh()
        except Exception as e:
            self.status.setText(f"✗ {e}")

    def _rename(self):
        new = self.name_inp.text().strip()
        if not new or not self._sel_id or new == self._sel_id: return
        try:
            self.db.rename_node(self._sel_id, new)
            self.status.setText(f"✓ '{self._sel_id}' → '{new}'")
            self._sel_id = new; self.refresh()
        except Exception as e:
            self.status.setText(f"✗ {e}")

    def _delete(self):
        if not self._sel_id: return
        nid, lbl = self._sel_id, self._sel_lbl
        if lbl == "Device":
            if QMessageBox.question(self, "Elimina dispositivo",
                    f"Eliminare '{nid}'?",
                    QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes:
                try:
                    self.db.delete_device(nid)
                    self.status.setText(f"✓ '{nid}' eliminato")
                    self._clear(); self.refresh()
                except Exception as e: self.status.setText(f"✗ {e}")
        elif lbl == "Area":
            msg = QMessageBox(self)
            msg.setWindowTitle("Elimina area"); msg.setText(f"Come eliminare '{nid}'?")
            msg.setInformativeText(
                "Semplice: area + dispositivi diretti\nRicorsiva: tutto il sottoalbero")
            bs = msg.addButton("Semplice",  QMessageBox.DestructiveRole)
            br = msg.addButton("Ricorsiva", QMessageBox.DestructiveRole)
            msg.addButton("Annulla", QMessageBox.RejectRole)
            msg.setDefaultButton(br); msg.exec()
            clicked = msg.clickedButton()
            if clicked not in (bs, br): return
            try:
                if clicked == bs: self.db.delete_area_simple(nid)
                else:             self.db.delete_area_recursive(nid)
                self.status.setText(f"✓ '{nid}' eliminata")
                self._clear(); self.refresh()
            except Exception as e: self.status.setText(f"✗ {e}")

    def _int_drop(self, src: str, tgt: str):
        if src == tgt: return
        try:
            sl = self.db.get_node_label(src); tl = self.db.get_node_label(tgt)
            if sl == "Area" and tl == "Area":
                if self.db.is_descendant(src, tgt):
                    self.status.setText("⚠ Non puoi spostare un'area dentro un suo discendente!")
                    return
                self.db.move_area(src, tgt)
                self.status.setText(f"✓ CONTAINS: {tgt} → {src}")
            elif sl == "Device" and tl == "Area":
                self.db.move_device(src, tgt)
                self.status.setText(f"✓ BELONGS: {src} → {tgt}")
            self.refresh()
        except Exception as e: self.status.setText(f"✗ {e}")

    # ── Export ────────────────────────────────────────────────────────────────
    def _export(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Esporta struttura", "vicky_structure.json", "JSON (*.json)")
        if not path:
            return
        desc, ok = QInputDialog.getText(
            self, "Descrizione", "Descrizione opzionale (es. 'Casa Rossi'):")
        try:
            export_json(self.db, path, description=desc if ok else "")
            self.status.setText(f"✓ Struttura esportata in '{path}'")
        except Exception as e:
            self.status.setText(f"✗ Errore export: {e}")

    # ── Import ────────────────────────────────────────────────────────────────
    def _import(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Importa struttura", "", "JSON (*.json)")
        if not path:
            return

        # Dialogo conflitti
        dlg = QDialog(self)
        dlg.setWindowTitle("Conflitti")
        dlg_lay = QVBoxLayout(dlg)
        dlg_lay.addWidget(QLabel("Cosa fare se un nodo esiste già nel grafo?"))
        rb_skip  = QRadioButton("Skip — mantieni il nodo esistente (consigliato)")
        rb_merge = QRadioButton("Merge — aggiorna ha_entity_id e alias")
        rb_skip.setChecked(True)
        dlg_lay.addWidget(rb_skip); dlg_lay.addWidget(rb_merge)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept); btns.rejected.connect(dlg.reject)
        dlg_lay.addWidget(btns)
        if dlg.exec() != QDialog.Accepted:
            return

        on_conflict = "skip" if rb_skip.isChecked() else "merge"

        try:
            report = import_json(self.db, path, on_conflict=on_conflict)
        except Exception as e:
            self.status.setText(f"✗ Errore import: {e}")
            return

        # Report
        report_dlg = QDialog(self)
        report_dlg.setWindowTitle("Report import")
        report_dlg.resize(560, 400)
        rl = QVBoxLayout(report_dlg)
        te = QTextEdit(); te.setReadOnly(True)
        te.setPlainText(report.summary())
        rl.addWidget(te)
        close_btn = QPushButton("Chiudi")
        close_btn.clicked.connect(report_dlg.accept)
        rl.addWidget(close_btn)
        report_dlg.exec()

        self.refresh()
        if report.has_errors:
            self.status.setText("⚠ Import completato con errori — vedi report")
        else:
            self.status.setText("✓ Import completato")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — Alias Aree
# ══════════════════════════════════════════════════════════════════════════════
class AliasAreeTab(QWidget):
    def __init__(self, db: Neo4jManager, parent=None):
        super().__init__(parent); self.db = db; self._init_ui()

    def _init_ui(self):
        root = QHBoxLayout(self); left = QVBoxLayout()
        self.tree = QTreeWidget()
        self.tree.setHeaderLabel("Aree (read-only)")
        self.tree.setDragDropMode(QAbstractItemView.NoDragDrop)
        self.tree.itemClicked.connect(self._clicked)
        rb = QPushButton("↻ Aggiorna"); rb.clicked.connect(self.refresh)
        left.addWidget(QLabel("Seleziona un'area per gestirne gli alias"))
        left.addWidget(self.tree); left.addWidget(rb)
        self.panel = AliasPanel(self.db)
        sp = QSplitter(Qt.Horizontal)
        lw = QWidget(); lw.setLayout(left)
        sp.addWidget(lw); sp.addWidget(self.panel); sp.setSizes([350, 450])
        root.addWidget(sp)

    def refresh(self):
        try:
            nodes, cr, _ = self.db.get_full_hierarchy()
        except Exception: return
        area_nodes = [n for n in nodes if n["label"] == "Area"]
        area_ids   = {n["id"] for n in area_nodes}
        cids       = {r["child"] for r in cr if r["child"] in area_ids}
        build_structure_tree(self.tree, area_nodes, cr, [], cids)
        self.panel.clear()

    def _clicked(self, item, _):
        nid = item.data(0, Qt.UserRole)
        lbl = item.data(0, Qt.UserRole + 1)
        if nid and lbl == "Area":
            self.panel.load(nid, "area", f"🏠  {nid}")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — Alias Dispositivi
# Lavora sugli Archetype nel grafo. Le istanze mostrano alias custom aggiuntivi.
# ══════════════════════════════════════════════════════════════════════════════
class AliasDispositiviTab(QWidget):
    def __init__(self, db: Neo4jManager, parent=None):
        super().__init__(parent); self.db = db; self._cur_arch = None; self._init_ui()

    def _init_ui(self):
        root = QHBoxLayout(self)
        left = QVBoxLayout()
        self.arch_list = QListWidget()
        self.arch_list.currentItemChanged.connect(self._arch_selected)
        rb = QPushButton("↻ Aggiorna"); rb.clicked.connect(self.refresh)
        left.addWidget(QLabel("Archetipi nel grafo"))
        left.addWidget(self.arch_list); left.addWidget(rb)

        right = QVBoxLayout()

        # ── Alias archetipo ──────────────────────────────────────────────────
        arch_box = QGroupBox("Alias archetipo  (condivisi da tutte le istanze via INSTANCE_OF)")
        arch_lay = QVBoxLayout(arch_box)
        self.arch_panel = AliasPanel(self.db)
        arch_lay.addWidget(self.arch_panel)

        # ── Default command e default item ───────────────────────────────────
        def_box = QGroupBox("Defaults archetipo")
        def_lay = QVBoxLayout(def_box)

        # default_command
        dc_row = QHBoxLayout()
        dc_row.addWidget(QLabel("Default command:"))
        self.dc_inp = QLineEdit(); self.dc_inp.setPlaceholderText("es. toggle")
        dc_row.addWidget(self.dc_inp)

        # default_item
        di_row = QHBoxLayout()
        di_row.addWidget(QLabel("Default item:"))
        self.di_inp = QLineEdit()
        self.di_inp.setPlaceholderText("ID device | ALL | (vuoto = ambiguo)")
        di_row.addWidget(self.di_inp)

        save_def_btn = QPushButton("💾 Salva defaults")
        save_def_btn.clicked.connect(self._save_defaults)

        self.def_status = QLabel(""); self.def_status.setStyleSheet("color:#888;")

        def_lay.addLayout(dc_row)
        def_lay.addLayout(di_row)
        def_lay.addWidget(save_def_btn)
        def_lay.addWidget(self.def_status)

        # ── Istanze ──────────────────────────────────────────────────────────
        inst_box = QGroupBox("Istanze  (alias custom aggiuntivi per singolo device)")
        inst_lay = QVBoxLayout(inst_box)
        self.inst_list  = QListWidget()
        self.inst_panel = AliasPanel(self.db)
        self.inst_list.currentItemChanged.connect(self._inst_selected)
        inst_sp = QSplitter(Qt.Horizontal)
        inst_sp.addWidget(self.inst_list); inst_sp.addWidget(self.inst_panel)
        inst_sp.setSizes([200, 320])
        inst_lay.addWidget(inst_sp)

        right.addWidget(arch_box, 3)
        right.addWidget(def_box, 2)
        right.addWidget(inst_box, 2)

        sp = QSplitter(Qt.Horizontal)
        lw = QWidget(); lw.setLayout(left)
        rw = QWidget(); rw.setLayout(right)
        sp.addWidget(lw); sp.addWidget(rw); sp.setSizes([220, 680])
        root.addWidget(sp)

    def refresh(self):
        self.arch_list.clear(); self.inst_list.clear()
        self.arch_panel.clear(); self.inst_panel.clear(); self._cur_arch = None
        self.dc_inp.clear(); self.di_inp.clear(); self.def_status.setText("")
        for a in self.db.get_live_archetypes():
            icon = device_icon(a["id"])
            item = QListWidgetItem(f"{icon}  {a['label']}")
            item.setData(Qt.UserRole,     a["id"])
            item.setData(Qt.UserRole + 1, a["label"])
            item.setData(Qt.UserRole + 2, a.get("default_command") or "")
            item.setData(Qt.UserRole + 3, a.get("default_item") or "")
            self.arch_list.addItem(item)

    def _arch_selected(self, item):
        if not item: return
        arch_id  = item.data(Qt.UserRole)
        arch_lbl = item.data(Qt.UserRole + 1)
        self._cur_arch = arch_id

        # Alias
        self.arch_panel.load(arch_id, "archetype",
                             f"{device_icon(arch_id)}  {arch_lbl}  [Archetype]")

        # Defaults
        defaults = self.db.get_archetype_defaults(arch_id)
        self.dc_inp.setText(defaults.get("default_command") or "")
        self.di_inp.setText(defaults.get("default_item") or "")
        self.def_status.setText("")

        # Istanze
        self.inst_list.clear(); self.inst_panel.clear()
        for dev in self.db.get_devices_by_archetype(arch_id):
            cnt = dev["alias_count"]
            it  = QListWidgetItem(
                f"  {dev['id']}  ({cnt} alias custom{'  *' if cnt else ''})")
            it.setData(Qt.UserRole, dev["id"])
            self.inst_list.addItem(it)

    def _save_defaults(self):
        if not self._cur_arch:
            self.def_status.setText("⚠ Nessun archetipo selezionato"); return
        dc = self.dc_inp.text().strip() or None
        di = self.di_inp.text().strip() or None
        try:
            self.db.set_archetype_defaults(self._cur_arch, dc, di)
            self.def_status.setText(
                f"✓ Salvato  default_command='{dc or '—'}'  "
                f"default_item='{di or '—'}'")
        except Exception as e:
            self.def_status.setText(f"✗ {e}")

    def _inst_selected(self, item):
        if not item: return
        dev_id = item.data(Qt.UserRole)
        icon   = device_icon(self._cur_arch) if self._cur_arch else "🔧"
        self.inst_panel.load(dev_id, "device",
                             f"{icon}  {dev_id}  [alias custom istanza]")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — Alias Comandi
# ══════════════════════════════════════════════════════════════════════════════
class AliasCommandiTab(QWidget):
    def __init__(self, db: Neo4jManager, parent=None):
        super().__init__(parent); self.db = db; self._init_ui()

    def _init_ui(self):
        root = QHBoxLayout(self); left = QVBoxLayout()
        self.cmd_list = QListWidget()
        self.cmd_list.currentItemChanged.connect(self._cmd_selected)
        rb = QPushButton("↻ Aggiorna"); rb.clicked.connect(self.refresh)
        left.addWidget(QLabel("Comandi nel grafo"))
        left.addWidget(self.cmd_list); left.addWidget(rb)
        self.panel = AliasPanel(self.db)
        sp = QSplitter(Qt.Horizontal)
        lw = QWidget(); lw.setLayout(left)
        sp.addWidget(lw); sp.addWidget(self.panel); sp.setSizes([280, 520])
        root.addWidget(sp)

    def refresh(self):
        self.cmd_list.clear(); self.panel.clear()
        for c in self.db.get_live_commands():
            item = QListWidgetItem(f"⚡  {c['label']}  [{c['id']}]")
            item.setData(Qt.UserRole,     c["id"])
            item.setData(Qt.UserRole + 1, c["label"])
            self.cmd_list.addItem(item)

    def _cmd_selected(self, item):
        if not item: return
        self.panel.load(item.data(Qt.UserRole), "command",
                        f"⚡  {item.data(Qt.UserRole + 1)}  [{item.data(Qt.UserRole)}]")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 5 — Query Test
# ══════════════════════════════════════════════════════════════════════════════
class QueryTestTab(QWidget):
    def __init__(self, db: Neo4jManager, parent=None):
        super().__init__(parent)
        self.db     = db
        self.engine = None   # inizializzato al primo uso
        self._init_ui()

    def _get_engine(self):
        from query_engine import QueryEngine
        if self.engine is None:
            self.engine = QueryEngine(self.db)
        return self.engine

    def _init_ui(self):
        root = QVBoxLayout(self)

        # ── Frase libera (NLP) ────────────────────────────────────────────────
        nlp_box = QGroupBox("Frase libera  (NLP → slot automatici)")
        nlp_lay = QVBoxLayout(nlp_box)
        nlp_row = QHBoxLayout()
        self.nlp_inp = QLineEdit()
        self.nlp_inp.setPlaceholderText(
            "es. 'accendi la luce in soggiorno' — premi Invio o Analizza")
        self.nlp_inp.returnPressed.connect(self._run_nlp)
        nlp_btn = QPushButton("🧠 Analizza")
        nlp_btn.clicked.connect(self._run_nlp)
        rebuild_btn = QPushButton("↻ Rebuild indice")
        rebuild_btn.setToolTip(
            "Rigenera l'indice embedding dagli alias nel grafo.\n"
            "Va fatto dopo ogni modifica agli alias.")
        rebuild_btn.clicked.connect(self._rebuild_index)
        nlp_row.addWidget(self.nlp_inp)
        nlp_row.addWidget(nlp_btn)
        nlp_row.addWidget(rebuild_btn)
        self.nlp_status = QLabel("Indice non caricato — premi 'Rebuild indice'")
        self.nlp_status.setStyleSheet("color:#888; font-style:italic;")
        nlp_lay.addLayout(nlp_row)
        nlp_lay.addWidget(self.nlp_status)

        # ── Slot input ────────────────────────────────────────────────────────
        slot_box = QGroupBox("Slot di input  (usa alias in linguaggio naturale)")
        slot_lay = QVBoxLayout(slot_box)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Area:"))
        self.area_inp = QLineEdit(); self.area_inp.setPlaceholderText("es. soggiorno")
        row1.addWidget(self.area_inp)
        row1.addSpacing(16)
        row1.addWidget(QLabel("Device:"))
        self.dev_inp = QLineEdit(); self.dev_inp.setPlaceholderText("es. luce")
        row1.addWidget(self.dev_inp)
        row1.addSpacing(16)
        row1.addWidget(QLabel("Command:"))
        self.cmd_inp = QLineEdit(); self.cmd_inp.setPlaceholderText("es. accendi")
        row1.addWidget(self.cmd_inp)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Params JSON:"))
        self.params_inp = QLineEdit()
        self.params_inp.setPlaceholderText('es. {"temperature": 21.0}  — lascia vuoto se non serve')
        row2.addWidget(self.params_inp)

        resolve_btn = QPushButton("🔍 Risolvi")
        resolve_btn.setFixedWidth(110)
        resolve_btn.clicked.connect(self._resolve)
        # Invio da qualsiasi campo triggera la risoluzione
        for inp in (self.area_inp, self.dev_inp, self.cmd_inp, self.params_inp):
            inp.returnPressed.connect(self._resolve)

        clear_btn = QPushButton("✕ Pulisci")
        clear_btn.setFixedWidth(80)
        clear_btn.clicked.connect(self._clear)

        btn_row = QHBoxLayout()
        btn_row.addStretch(); btn_row.addWidget(resolve_btn); btn_row.addWidget(clear_btn)

        slot_lay.addLayout(row1)
        slot_lay.addLayout(row2)
        slot_lay.addLayout(btn_row)

        # ── Output ────────────────────────────────────────────────────────────
        out_box = QGroupBox("Risultato")
        out_lay = QVBoxLayout(out_box)

        # Badge status
        self.status_badge = QLabel("")
        self.status_badge.setAlignment(Qt.AlignCenter)
        f = QFont(); f.setBold(True); f.setPointSize(12)
        self.status_badge.setFont(f)

        # JSON risultato
        self.result_view = QTextEdit()
        self.result_view.setReadOnly(True)
        self.result_view.setFont(QFont("Courier New", 10))

        # Tabella service call leggibile
        self.call_list = QListWidget()

        sp = QSplitter(Qt.Horizontal)
        sp.addWidget(self.result_view)
        sp.addWidget(self.call_list)
        sp.setSizes([500, 400])

        out_lay.addWidget(self.status_badge)
        out_lay.addWidget(sp)

        # ── Esempi rapidi ─────────────────────────────────────────────────────
        ex_box = QGroupBox("Esempi rapidi")
        ex_lay = QHBoxLayout(ex_box)
        examples = [
            ("Completo",         "soggiorno", "luce",   "accendi", ""),
            ("No area",          "",          "luce",   "spegni",  ""),
            ("Default command",  "cucina",    "luce",   "",        ""),
            ("Solo device",      "",          "luce",   "",        ""),
            ("Con parametro",    "camera",    "termostato", "imposta_temperatura",
             '{"temperature": 21.0}'),
        ]
        for label, area, dev, cmd, params in examples:
            btn = QPushButton(label)
            btn.clicked.connect(
                lambda _, a=area, d=dev, c=cmd, p=params:
                    self._fill_and_resolve(a, d, c, p))
            ex_lay.addWidget(btn)

        root.addWidget(nlp_box)
        root.addWidget(slot_box)
        root.addWidget(ex_box)
        root.addWidget(out_box, 1)

    def _fill_and_resolve(self, area, dev, cmd, params):
        self.area_inp.setText(area)
        self.dev_inp.setText(dev)
        self.cmd_inp.setText(cmd)
        self.params_inp.setText(params)
        self._resolve()

    def _resolve(self):
        import json as _json
        area    = self.area_inp.text().strip()   or None
        device  = self.dev_inp.text().strip()    or None
        command = self.cmd_inp.text().strip()    or None
        params_txt = self.params_inp.text().strip()
        params  = {}
        if params_txt:
            try:
                params = _json.loads(params_txt)
            except Exception:
                self.status_badge.setText("⚠ Params JSON non valido")
                self.status_badge.setStyleSheet("color: #e07b39;")
                return

        try:
            result = self._get_engine().resolve(
                area=area, device=device, command=command, params=params)
        except Exception as e:
            self.status_badge.setText(f"✗ Errore engine: {e}")
            self.status_badge.setStyleSheet("color: #cc3333;")
            return

        # Badge colore per status
        colors = {"ok": "#4caf50", "ambiguous": "#e07b39",
                  "not_found": "#cc3333", "error": "#cc3333"}
        icons  = {"ok": "✓ OK", "ambiguous": "⚠ AMBIGUOUS",
                  "not_found": "✗ NOT FOUND", "error": "✗ ERROR"}
        self.status_badge.setText(icons.get(result.status, result.status))
        self.status_badge.setStyleSheet(
            f"color: {colors.get(result.status, '#888')};")

        # JSON completo
        self.result_view.setPlainText(
            _json.dumps(result.to_dict(), ensure_ascii=False, indent=2))

        # Lista service call leggibile
        self.call_list.clear()
        if result.message:
            msg_item = QListWidgetItem(f"ℹ {result.message}")
            msg_item.setForeground(QColor("#888"))
            self.call_list.addItem(msg_item)
        if result.candidates:
            self.call_list.addItem(QListWidgetItem("Candidati:"))
            for c in result.candidates:
                self.call_list.addItem(QListWidgetItem(
                    f"  • {c['id']}  (area: {c.get('area') or '—'})"))
        for sc in result.results:
            self.call_list.addItem(QListWidgetItem(
                f"🔧 {sc.device_id}  ({sc.area_id or 'no area'})"))
            self.call_list.addItem(QListWidgetItem(
                f"   entity:  {sc.entity_id}"))
            self.call_list.addItem(QListWidgetItem(
                f"   service: {sc.service}"))
            if sc.service_data:
                self.call_list.addItem(QListWidgetItem(
                    f"   data:    {sc.service_data}"))
            self.call_list.addItem(QListWidgetItem(""))

    # ── NLP handlers ─────────────────────────────────────────────────────────
    def _get_nlp(self):
        from nlp_engine import NLPEngine
        if not hasattr(self, "_nlp") or self._nlp is None:
            self._nlp = NLPEngine(self.db, common_yaml_path='_common.yaml')
            if self._nlp.load_index():
                self.nlp_status.setText("✓ Indice caricato da disco")
                self.nlp_status.setStyleSheet("color:#4caf50;")
            else:
                self.nlp_status.setText(
                    "⚠ Indice non trovato — premi 'Rebuild indice'")
                self.nlp_status.setStyleSheet("color:#e07b39;")
        return self._nlp

    def _rebuild_index(self):
        import json as _json
        self.nlp_status.setText("⏳ Costruzione indice in corso...")
        self.nlp_status.setStyleSheet("color:#888;")
        QApplication.processEvents()
        try:
            nlp = self._get_nlp()
            nlp.build_index()
            self.nlp_status.setText("✓ Indice ricostruito")
            self.nlp_status.setStyleSheet("color:#4caf50;")
        except Exception as e:
            self.nlp_status.setText(f"✗ Errore: {e}")
            self.nlp_status.setStyleSheet("color:#cc3333;")

    def _run_nlp(self):
        import json as _json

        import traceback
        self.nlp_status.setText(traceback.format_exc())

        sentence = self.nlp_inp.text().strip()
        if not sentence:
            return
        try:
            nlp    = self._get_nlp()
            result = nlp.extract(sentence)
        except Exception as e:
            self.nlp_status.setText(f"✗ Errore NLP: {e}")
            self.nlp_status.setStyleSheet("color:#cc3333;")
            return

        # Popola i campi slot con i valori estratti
        self.area_inp.setText(result.area    or "")
        self.dev_inp.setText(result.device   or "")
        self.cmd_inp.setText(result.command  or "")

        # Mostra scores nello status
        d = result.to_dict()
        scores = d.get("scores", {})
        parts  = []
        for k, v in scores.items():
            if v is not None:
                parts.append(f"{k}={v:.2f}")
        score_str = "  |  ".join(parts) if parts else "nessun match"
        self.nlp_status.setText(
            f"{'✓' if result.confident else '⚠'} {score_str}")
        self.nlp_status.setStyleSheet(
            "color:#4caf50;" if result.confident else "color:#e07b39;")

        # Risolvi automaticamente se tutti gli slot principali sono stati trovati
        if result.device or result.command:
            self._resolve()

    def _clear(self):
        for inp in (self.area_inp, self.dev_inp, self.cmd_inp, self.params_inp):
            inp.clear()
        self.nlp_inp.clear()
        self.result_view.clear()
        self.call_list.clear()
        self.status_badge.setText("")


# ══════════════════════════════════════════════════════════════════════════════
# Finestra principale
# ══════════════════════════════════════════════════════════════════════════════
class VickyBuilder(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Vicky World Builder")
        self.db = Neo4jManager()
        self._init_ui()

    def _init_ui(self):
        self._tabs = QTabWidget()
        self.wb_tab = WorldBuilderTab(self.db)
        self.aa_tab = AliasAreeTab(self.db)
        self.ad_tab = AliasDispositiviTab(self.db)
        self.ac_tab = AliasCommandiTab(self.db)
        self.qt_tab = QueryTestTab(self.db)
        self._tabs.addTab(self.wb_tab, "🏗  World Builder")
        self._tabs.addTab(self.aa_tab, "🏠  Alias Aree")
        self._tabs.addTab(self.ad_tab, "💡  Alias Dispositivi")
        self._tabs.addTab(self.ac_tab, "⚡  Alias Comandi")
        self._tabs.addTab(self.qt_tab, "🔍  Query Test")
        self._tabs.currentChanged.connect(
            lambda idx: getattr(self._tabs.widget(idx), "refresh", lambda: None)())
        self.setCentralWidget(self._tabs)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStartDragDistance(2)
    window = VickyBuilder()
    window.resize(1200, 760)
    window.show()
    sys.exit(app.exec())