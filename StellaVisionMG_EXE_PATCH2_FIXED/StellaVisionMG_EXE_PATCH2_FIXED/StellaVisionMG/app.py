import os, sqlite3, json, datetime, re, hashlib, sys, unicodedata
from flask import Flask, render_template, request, redirect, url_for, jsonify, send_file, flash, session, g
try:
    from flask_wtf import CSRFProtect  # type: ignore
except Exception:  # pragma: no cover - flask_wtf é opcional
    CSRFProtect = None
import init_db, seed
import webbrowser, threading, socket


# Base path aware of PyInstaller --onefile
def _base_dir():
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return os.path.dirname(sys.executable)
    return os.path.dirname(__file__)
APP_DIR = _base_dir()
DB_PATH = os.path.join(APP_DIR, "erp.db")
SECRET = os.environ.get("SECRET_KEY", "dev")

# Directory with bundled (read-only) resources when frozen (templates/static)
def _bundle_dir():
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return sys._MEIPASS
    return os.path.dirname(__file__)
BUNDLE_DIR = _bundle_dir()
os.makedirs(APP_DIR, exist_ok=True)




def check_files():
    try:
        print("[DEBUG] APP_DIR:", APP_DIR)
        print("[DEBUG] BUNDLE_DIR:", BUNDLE_DIR)
        print("[DEBUG] DB_PATH:", DB_PATH, "exists?", os.path.exists(DB_PATH))
        print("[DEBUG] Templates exist? ", os.path.exists(os.path.join(BUNDLE_DIR, 'templates')))
        print("[DEBUG] Static exist?    ", os.path.exists(os.path.join(BUNDLE_DIR, 'static')))
        try:
            print("[DEBUG] APP_DIR list:", os.listdir(APP_DIR))
        except Exception as e:
            print("[DEBUG] Could not list APP_DIR:", e)
        try:
            print("[DEBUG] BUNDLE_DIR list:", os.listdir(BUNDLE_DIR))
        except Exception as e:
            print("[DEBUG] Could not list BUNDLE_DIR:", e)
    except Exception as e:
        print("[DEBUG] check_files() error:", e)

# First-run DB creation when missing
if not os.path.exists(DB_PATH):
    try:
        init_db.DB_PATH = DB_PATH
        seed.DB_PATH = DB_PATH
        init_db.main()
        try:
            seed.main()
        except Exception:
            pass
    except Exception as _e:
        raise RuntimeError(f"Falha ao inicializar banco em {DB_PATH}: {_e}")
# =============================================================================

# Auth helpers
#
# A very small authentication layer is introduced to protect the ERP. A table
# called ``auth_users`` is created on startup and a default user ``MACHADO``
# with the password ``BH8EHEKGCC7QC`` is inserted if it does not exist.  The
# password is stored as a SHA‑256 hash.  Users are stored independently from
# the legacy ``users`` table to avoid altering existing data.

def hash_password(password: str) -> str:
    """Return a hexadecimal SHA‑256 hash of the given password."""
    return hashlib.sha256(password.encode()).hexdigest()

# Migração automática simples

def ensure_migrations():
    with sqlite3.connect(DB_PATH) as _c:
        _c.row_factory = sqlite3.Row
        try:
            cols = [r[1] for r in _c.execute("PRAGMA table_info(products)").fetchall()]
        except sqlite3.OperationalError:
            cols = []
        if cols and "supplier_id" not in cols:
            _c.execute("ALTER TABLE products ADD COLUMN supplier_id INTEGER REFERENCES suppliers(id)")
        if cols and "created_at" not in cols:
            _c.execute("ALTER TABLE products ADD COLUMN created_at TEXT")
        if cols and "updated_at" not in cols:
            _c.execute("ALTER TABLE products ADD COLUMN updated_at TEXT")
        _c.execute(
            "CREATE TABLE IF NOT EXISTS auth_users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL, password TEXT NOT NULL)"
        )
        row = _c.execute("SELECT id FROM auth_users WHERE username=?", ("MACHADO",)).fetchone()
        if not row:
            _c.execute("INSERT INTO auth_users (username, password) VALUES (?, ?)",
                       ("MACHADO", hashlib.sha256("BH8EHEKGCC7QC".encode()).hexdigest()))

        stock_sql = _c.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='stock_moves'"
        ).fetchone()
        if stock_sql:
            sql_def = stock_sql["sql"] if isinstance(stock_sql, sqlite3.Row) else stock_sql[0]
        else:
            sql_def = None
        if sql_def and ("ajuste_edit_prod" not in sql_def or "venda_edit" not in sql_def):
            _c.execute("PRAGMA foreign_keys = OFF")
            _c.execute("ALTER TABLE stock_moves RENAME TO stock_moves_old")
            _c.execute(
                """
                CREATE TABLE stock_moves(
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  data TEXT,
                  product_id INTEGER,
                  tipo TEXT CHECK(tipo IN ('IN','OUT')),
                  qtde INTEGER,
                  origem TEXT CHECK(origem IN ('compra','venda','ajuste','rma_retorno','rma_troca','ajuste_edit_prod','venda_edit')),
                  ref_id INTEGER,
                  usuario_id INTEGER,
                  FOREIGN KEY(product_id) REFERENCES products(id),
                  FOREIGN KEY(usuario_id) REFERENCES users(id)
                )
                """
            )
            _c.execute(
                """
                INSERT INTO stock_moves(id, data, product_id, tipo, qtde, origem, ref_id, usuario_id)
                SELECT id, data, product_id, tipo, qtde, origem, ref_id, usuario_id FROM stock_moves_old
                """
            )
            _c.execute("DROP TABLE stock_moves_old")
            _c.execute("PRAGMA foreign_keys = ON")
            _c.execute("CREATE INDEX IF NOT EXISTS idx_moves_prod_data ON stock_moves(product_id, data)")


# ---- Helpers to run server in EXE safely ----
def _free_port(preferred=5001):
    for p in [preferred, 5002, 5050, 8000, 8080]:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.2)
            res = sock.connect_ex(("127.0.0.1", p))
            if res != 0:
                return p
    return preferred

def _open_browser(url):
    try:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    except Exception:
        pass
app = Flask(
    __name__,
    template_folder=os.path.join(BUNDLE_DIR, "templates"),
    static_folder=os.path.join(BUNDLE_DIR, "static"),
)
app.secret_key = SECRET
if CSRFProtect:
    CSRFProtect(app)
# Executa migrações ao iniciar o aplicativo
ensure_migrations()


def _slug(s: str) -> str:
    if s is None:
        return ""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-")
    return s.upper()


def _build_prefix(platform, model, capacity, color, region, cond):
    parts = [platform, model, capacity, color, region, cond]
    parts = [_slug(p) for p in parts if p and str(p).strip()]
    prefix = "-".join(parts)
    return prefix[:80]


def _next_seq(db, prefix):
    base = prefix or "SKU"
    row = db.execute(
        "SELECT MAX(CAST(substr(sku, LENGTH(?) + 2) AS INTEGER)) AS maxseq "
        "FROM products WHERE sku LIKE ?",
        (base, base + '-%')
    ).fetchone()
    max_seq = 0
    if row is not None:
        try:
            max_seq = row['maxseq'] or 0
        except (KeyError, TypeError):
            max_seq = row[0] if row[0] is not None else 0
    return max_seq + 1


def get_db():
    if "_db_conn" not in g:
        conn_obj = sqlite3.connect(DB_PATH)
        conn_obj.row_factory = sqlite3.Row
        g._db_conn = conn_obj
    return g._db_conn


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("_db_conn", None)
    if db is not None:
        db.close()

@app.before_request
def require_login():
    """Redirect users to the login page unless they are already authenticated.

    O identificador do usuário autenticado é armazenado em ``g.user_id`` para
    ser utilizado nas rotas que gravam movimentações.
    """
    exempt = {"login", "logout", "dev_sku", "_dev_routes"}
    endpoint = request.endpoint or ""
    g.user_id = session.get("user_id")
    if endpoint in exempt or endpoint.startswith("static"):
        return
    if g.user_id is None:
        return redirect(url_for("login"))


def current_user_id():
    return getattr(g, "user_id", None)


@app.route("/dev/routes")
def _dev_routes():
    return "<pre>" + "\n".join(sorted(r.rule for r in app.url_map.iter_rules())) + "</pre>"


@app.route("/dev/sku")
def dev_sku():
    db = get_db()
    pr = request.args
    prefix = _build_prefix(
        pr.get("platform"), pr.get("model"), pr.get("capacity"),
        pr.get("color"), pr.get("region"), pr.get("cond")
    )
    seq = _next_seq(db, prefix)
    sku = f"{prefix}-{seq:05d}" if prefix else f"SKU-{seq:05d}"
    return jsonify({"prefix": prefix, "seq": seq, "sku": sku})

# ==========================================================================================
#                                       Rotas de edição
# Estas rotas permitem atualizar registros existentes sem perder dados. Elas são
# adicionadas como parte das melhorias solicitadas para possibilitar a edição de
# vendas e produtos. Outras entidades podem seguir padrão semelhante.

@app.route("/produtos/<int:prod_id>/edit", methods=["GET", "POST"])
def produto_edit(prod_id):
    """Exibe e salva formulário de edição para um produto.

    Ao alterar o estoque atual, o sistema registra automaticamente a
    diferença como movimentação de estoque (IN/OUT). Todas as demais
    informações são atualizadas em linha.
    """
    with conn() as c:
        p = c.execute("SELECT * FROM products WHERE id=?", (prod_id,)).fetchone()
    if not p:
        flash("Produto não encontrado", "danger")
        return redirect(url_for("produtos"))
    if request.method == "POST":
        data = request.form
        now = datetime.datetime.now().isoformat(timespec="seconds")
        # Verifica mudança de estoque para registrar movimento
        try:
            new_estoque = int(data.get("estoque_atual") or 0)
        except (TypeError, ValueError):
            new_estoque = p["estoque_atual"] or 0
        old_estoque = p["estoque_atual"] or 0
        diff = new_estoque - old_estoque
        # Preparar campos normalizados
        sku = (data.get("sku") or p["sku"]).strip()
        nome = data.get("nome") or p["nome"]
        categoria = data.get("categoria") or None
        plataforma = data.get("plataforma") or None
        modelo = data.get("modelo") or None
        capacidade = data.get("capacidade") or None
        cor = data.get("cor") or None
        regiao = data.get("regiao") or None
        condicao = data.get("condicao") or p.get("condicao")
        # fornecedor inline: recupera, cria ou atualiza fornecedor e define supplier_id
        forn_id = None
        try:
            forn_id = p["supplier_id"] if "supplier_id" in p.keys() else None
        except Exception:
            forn_id = None
        nomef = (data.get("fornecedor_nome") or '').strip()
        cidadef = (data.get("fornecedor_cidade") or '').strip()
        telefonef = (data.get("fornecedor_telefone") or '').strip()
        emailf = (data.get("fornecedor_email") or '').strip()
        docf = (data.get("fornecedor_doc") or '').strip()
        if nomef:
            with conn() as c2:
                row = c2.execute("SELECT * FROM suppliers WHERE nome=?", (nomef,)).fetchone()
                if row:
                    forn_id = row['id']
                    updates = []
                    vals = []
                    if cidadef:
                        updates.append("cidade=?"); vals.append(cidadef)
                    if telefonef:
                        updates.append("telefone=?"); vals.append(telefonef)
                    if emailf:
                        updates.append("email=?"); vals.append(emailf)
                    if docf:
                        updates.append("doc=?"); vals.append(docf)
                    if updates:
                        vals.append(forn_id)
                        c2.execute("UPDATE suppliers SET " + ", ".join(updates) + " WHERE id=?", vals)
                else:
                    forn_id = c2.execute(
                        "INSERT INTO suppliers(nome, cidade, telefone, email, doc) VALUES(?,?,?,?,?)",
                        (nomef, cidadef or None, telefonef or None, emailf or None, docf or None),
                    ).lastrowid
        try:
            preco_lista = float(data.get("preco_lista") or 0)
        except (TypeError, ValueError):
            preco_lista = p.get("preco_lista") or 0
        try:
            custo_base = float(data.get("custo_base") or 0)
        except (TypeError, ValueError):
            custo_base = p.get("custo_base") or 0
        try:
            estoque_minimo = int(data.get("estoque_minimo") or 0)
        except (TypeError, ValueError):
            estoque_minimo = p.get("estoque_minimo") or 0
        with conn() as c:
            # valida SKU duplicado somente se foi alterado
            if sku != p["sku"]:
                dup = c.execute("SELECT 1 FROM products WHERE sku=? AND id<>?", (sku, prod_id)).fetchone()
                if dup:
                    flash("SKU duplicado. Escolha outro.", "danger")
                    return redirect(url_for("produto_edit", prod_id=prod_id))
            c.execute(
                "UPDATE products SET sku=?, nome=?, categoria=?, plataforma=?, modelo=?, capacidade=?, cor=?, regiao=?, condicao=?, preco_lista=?, custo_base=?, estoque_minimo=?, estoque_atual=?, updated_at=?, supplier_id=? WHERE id=?",
                (
                    sku,
                    nome,
                    categoria,
                    plataforma,
                    modelo,
                    capacidade,
                    cor,
                    regiao,
                    condicao,
                    preco_lista,
                    custo_base,
                    estoque_minimo,
                    new_estoque,
                    now,
                    forn_id,
                    prod_id,
                ),
            )
            # registra movimento de ajuste se necessário
            if diff != 0:
                tipo = "IN" if diff > 0 else "OUT"
                c.execute(
                    "INSERT INTO stock_moves(data, product_id, tipo, qtde, origem, ref_id, usuario_id) VALUES(?,?,?,?,?,?,?)",
                    (
                        datetime.date.today().isoformat(),
                        prod_id,
                        tipo,
                        abs(diff),
                        "ajuste_edit_prod",
                        prod_id,
                        current_user_id(),
                    ),
                )
        flash("Produto atualizado", "success")
        return redirect(url_for("produtos"))
    # GET: prepara dados para template
    # Carrega dados do fornecedor (se houver) para pré-preencher campos
    forn = None
    try:
        fid = p["supplier_id"] if "supplier_id" in p.keys() else None
    except Exception:
        fid = None
    if fid:
        with conn() as c2:
            forn = c2.execute("SELECT * FROM suppliers WHERE id=?", (fid,)).fetchone()
    return render_template("produto_editar.html", produto=p, fornecedor=forn)


@app.route("/vendas/<int:sale_id>/edit", methods=["GET", "POST"])
def venda_edit(sale_id):
    """Exibe e salva formulário de edição para uma venda.

    Permite alterar dados do cliente, data, vendedor e itens da venda. Ao ajustar
    quantidades nos itens, o estoque é corrigido com movimentos IN/OUT e o total
    de desconto é recalculado automaticamente. Para manter a rastreabilidade,
    as movimentações adicionais são registradas com origem 'venda_edit'.
    """
    with conn() as c:
        sale = c.execute("SELECT * FROM sales WHERE id=?", (sale_id,)).fetchone()
        if not sale:
            flash("Venda não encontrada", "danger")
            return redirect(url_for("vendas"))
        # carrega cliente associado
        cust = None
        if sale["customer_id"]:
            cust = c.execute("SELECT * FROM customers WHERE id=?", (sale["customer_id"],)).fetchone()
        # carrega itens da venda com info de produto
        items = c.execute(
            """
            SELECT
              si.id,
              si.sale_id,
              si.product_id,
              si.qtde,
              si.preco_unit,
              si.desconto_pct,
              si.desconto_valor,
              p.sku,
              p.nome AS produto
            FROM sale_items si
            JOIN products p ON p.id = si.product_id
            WHERE si.sale_id = ?
            ORDER BY si.id
            """,
            (sale_id,),
        ).fetchall()
    if request.method == "POST":
        f = request.form
        data_v = parse_date(f.get("data")) or datetime.date.fromisoformat(sale["data"])
        vendedor_id = int(f.get("vendedor_id") or sale["vendedor_id"] or 2)
        motivo_desconto = f.get("motivo_desconto")
        # Atualiza cliente
        with conn() as c:
            if cust:
                c.execute(
                    "UPDATE customers SET nome=?, cidade=?, telefone=?, doc=? WHERE id=?",
                    (
                        f.get("cliente_nome") or cust["nome"],
                        f.get("cliente_cidade"),
                        f.get("cliente_telefone"),
                        f.get("cliente_doc"),
                        cust["id"],
                    ),
                )
                cust_id = cust["id"]
            else:
                cust_id = c.execute(
                    "INSERT INTO customers(nome,cidade,telefone,doc) VALUES(?,?,?,?)",
                    (
                        f.get("cliente_nome"),
                        f.get("cliente_cidade"),
                        f.get("cliente_telefone"),
                        f.get("cliente_doc"),
                    ),
                ).lastrowid
            # calcula novas quantidades e descontos
            total_bruto = 0.0
            total_desc_val = 0.0
            # iterar cada item pelo índice, usando tamanho de items
            for idx, it in enumerate(items):
                try:
                    new_qtde = int(f.get(f"item_{idx}_qtde") or it["qtde"])
                except (TypeError, ValueError):
                    new_qtde = it["qtde"]
                try:
                    new_preco = float(f.get(f"item_{idx}_preco_unit") or it["preco_unit"])
                except (TypeError, ValueError):
                    new_preco = it["preco_unit"]
                try:
                    new_desc_pct = float(f.get(f"item_{idx}_desconto_pct") or it["desconto_pct"] or 0)
                except (TypeError, ValueError):
                    new_desc_pct = it["desconto_pct"] or 0
                try:
                    new_desc_val = float(f.get(f"item_{idx}_desconto_valor") or it["desconto_valor"] or 0)
                except (TypeError, ValueError):
                    new_desc_val = it["desconto_valor"] or 0
                old_qtde = it["qtde"] or 0
                diff_qtde = new_qtde - old_qtde
                # Ajuste de estoque se quantidade mudou
                if diff_qtde != 0:
                    tipo = "OUT" if diff_qtde > 0 else "IN"
                    qtde_mov = abs(diff_qtde)
                    # registra movimento
                    c.execute(
                        "INSERT INTO stock_moves(data, product_id, tipo, qtde, origem, ref_id, usuario_id) VALUES(?,?,?,?,?,?,?)",
                        (
                            datetime.date.today().isoformat(),
                            it["product_id"],
                            tipo,
                            qtde_mov,
                            "venda_edit",
                            sale_id,
                            current_user_id(),
                        ),
                    )
                    # ajusta estoque em products
                    c.execute(
                        "UPDATE products SET estoque_atual = estoque_atual - ? WHERE id=?",
                        (diff_qtde, it["product_id"]),
                    )
                # atualiza sale_items
                c.execute(
                    "UPDATE sale_items SET qtde=?, preco_unit=?, desconto_pct=?, desconto_valor=? WHERE id=?",
                    (
                        new_qtde,
                        new_preco,
                        new_desc_pct,
                        new_desc_val,
                        it["id"],
                    ),
                )
                total_bruto += new_preco * new_qtde
                total_desc_val += new_desc_val
            # Recalcula percentual total de desconto
            if total_bruto > 0:
                new_desc_pct_total = min(100.0, (total_desc_val / total_bruto) * 100.0)
            else:
                new_desc_pct_total = 0.0
            # atualiza a venda
            cidade_snap = (
                c.execute(
                    "SELECT cidade FROM customers WHERE id=?", (cust_id,)
                ).fetchone()["cidade"]
                if cust_id
                else None
            )
            c.execute(
                "UPDATE sales SET data=?, customer_id=?, vendedor_id=?, desconto_valor_total=?, desconto_pct_total=?, motivo_desconto=?, cidade_snapshot=? WHERE id=?",
                (
                    data_v.isoformat(),
                    cust_id,
                    vendedor_id,
                    total_desc_val,
                    new_desc_pct_total,
                    motivo_desconto,
                    cidade_snap,
                    sale_id,
                ),
            )
            flash("Venda atualizada", "success")
        return redirect(url_for("vendas"))
    # GET
    return render_template(
        "venda_editar.html",
        sale=sale,
        cliente=cust,
        items=items,
    )

def conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c

def br_money(v):
    if v is None: v = 0
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def parse_date(s):
    # aceita yyyy-mm-dd e dd/mm/yyyy
    if not s: return None
    try:
        return datetime.datetime.strptime(s, "%Y-%m-%d").date()
    except:
        try:
            return datetime.datetime.strptime(s, "%d/%m/%Y").date()
        except:
            return None

def date_range_labels(d0, d1):
    out = []
    while d0 <= d1:
        out.append(d0.isoformat())
        d0 += datetime.timedelta(days=1)
    return out

def get_settings():
    with conn() as c:
        rows = {r["key"]: r["value"] for r in c.execute("SELECT key,value FROM settings")}
    # defaults
    return {
        "discount_limit_pct": float(rows.get("discount_limit_pct","10")),
        "rma_window_days": int(rows.get("rma_window_days","30")),
        "no_sale_days": int(rows.get("no_sale_days","7")),
        "theme_primary": rows.get("theme_primary", "#2563eb"),
    }

def get_filters():
    today = datetime.date.today()
    ini = parse_date(request.args.get("ini")) or (today - datetime.timedelta(days=29))
    fim = parse_date(request.args.get("fim")) or today
    categoria = request.args.get("categoria") or None
    cidade = request.args.get("cidade") or None
    vendedor = request.args.get("vendedor") or None
    incluir_rma = request.args.get("incluir_rma","1") == "1"
    return ini, fim, categoria, cidade, vendedor, incluir_rma

def apply_filters_where(ini,fim,categoria,cidade,vendedor):
    where = ["date(s.data) BETWEEN ? AND ?"]
    params = [ini.isoformat(), fim.isoformat()]
    if categoria:
        where.append("(p.categoria = ? OR (p.categoria IS NULL AND ?='Sem categoria') )")
        params.append(categoria); params.append(categoria)
    if cidade:
        where.append("(s.cidade_snapshot = ?)")
        params.append(cidade)
    if vendedor:
        where.append("(s.vendedor_id = ?)")
        params.append(vendedor)
    return " AND ".join(where), params

@app.context_processor
def inject_helpers():
    def q_toggle_top(metric):
        # keep query args but set 'top' metric
        args = request.args.to_dict()
        args["top"] = metric
        return "&".join([f"{k}={v}" for k,v in args.items()])
    return {"br_money": br_money, "q_toggle_top": q_toggle_top}

# === KPI computations ===
def compute_kpis(ini, fim, categoria, cidade, vendedor, incluir_rma):
    with conn() as c:
        where, params = apply_filters_where(ini,fim,categoria,cidade,vendedor)
        # Receita bruta período
        sql = f"""
        SELECT SUM(si.qtde * si.preco_unit) AS receita,
               SUM(si.qtde * si.custo_snap) AS custo
        FROM sale_items si
        JOIN sales s ON s.id = si.sale_id
        JOIN products p ON p.id = si.product_id
        WHERE {where}
        """
        row = c.execute(sql, params).fetchone()
        receita = row["receita"] or 0
        custo = row["custo"] or 0

        # RMA (contra) no período (considera created_at em rmas para simplicidade)
        rma_rec = 0; rma_custo = 0
        if incluir_rma:
            pass
        else:
            r = c.execute(f"""
              SELECT SUM(ri.qtde * si.preco_unit) AS rec, SUM(ri.qtde * si.custo_snap) AS cus
              FROM rma_items ri
              JOIN rmas r ON r.id = ri.rma_id
              JOIN sale_items si ON si.id = ri.sale_item_id
              JOIN sales s ON s.id = si.sale_id
              JOIN products p ON p.id = si.product_id
              WHERE date(r.created_at) BETWEEN ? AND ?
                AND ({where})
            """, [ini.isoformat(), fim.isoformat(), *params]).fetchone()
            if r:
                rma_rec = r["rec"] or 0
                rma_custo = r["cus"] or 0

        receita_liq = receita - rma_rec
        custo_liq = custo - rma_custo
        lucro_bruto = receita - custo
        lucro_liq = receita_liq - custo_liq

        # Nº vendas
        total_vendas = c.execute(f"""
          SELECT COUNT(*) AS n FROM sales s
          JOIN sale_items si ON si.sale_id = s.id
          JOIN products p ON p.id = si.product_id
          WHERE {where}
        """, params).fetchone()["n"] or 0

        # Estoque (venda/custo)
        est = c.execute("""
          SELECT SUM(estoque_atual * preco_lista) AS estoque_venda,
                 SUM(estoque_atual * COALESCE(custo_base,0)) AS estoque_custo
          FROM products
        """).fetchone()
        estoque_venda = est["estoque_venda"] or 0
        estoque_custo = est["estoque_custo"] or 0

        # Últimos 30 dias (rolling receita)
        ult30_ini = fim - datetime.timedelta(days=29)
        r30 = c.execute(f"""
          SELECT date(s.data) AS d, SUM(si.qtde*si.preco_unit) v
          FROM sales s JOIN sale_items si ON si.sale_id=s.id
          JOIN products p ON p.id=si.product_id
          WHERE date(s.data) BETWEEN ? AND ? AND ({where})
          GROUP BY date(s.data)
        """, [ult30_ini.isoformat(), fim.isoformat(), *params]).fetchall()
        mapa30 = {row["d"]: row["v"] for row in r30}
        labels30 = date_range_labels(ult30_ini, fim)
        valores30 = [round(mapa30.get(d,0),2) for d in labels30]

        # Margem média % (ignora custo nulo)
        m = c.execute(f"""
          SELECT SUM(si.qtde*si.preco_unit) rec, SUM(si.qtde*si.custo_snap) cus
          FROM sale_items si JOIN sales s ON s.id=si.sale_id JOIN products p ON p.id=si.product_id
          WHERE {where} AND si.custo_snap IS NOT NULL AND si.custo_snap > 0
        """, params).fetchone()
        margem_pct = 0.0
        if m and m["rec"] and m["cus"] is not None and m["rec"]>0:
            margem_pct = max(0.0, ((m["rec"]-m["cus"])/m["rec"])*100)

        # Produtos sem venda há X dias
        settings = get_settings()
        xdays = settings["no_sale_days"]
        limite = datetime.date.today() - datetime.timedelta(days=xdays)
        sem_venda = c.execute("""
          SELECT p.id, p.nome, COALESCE(MAX(date(s.data)),'1900-01-01') AS ultima_data
          FROM products p
          LEFT JOIN sale_items si ON si.product_id=p.id
          LEFT JOIN sales s ON s.id=si.sale_id
          GROUP BY p.id
        """).fetchall()
        sem_venda_list = []
        for r in sem_venda:
            ud = datetime.date.fromisoformat(r["ultima_data"])
            if ud < limite:
                dias = (datetime.date.today()-ud).days if r["ultima_data"]!='1900-01-01' else 9999
                sem_venda_list.append({"id": r["id"], "nome": r["nome"], "dias": dias})

        # Cidades vendidas (faturamento)
        rows_cid = c.execute(f"""
          SELECT s.cidade_snapshot AS cid, SUM(si.qtde*si.preco_unit) v
          FROM sales s JOIN sale_items si ON si.sale_id=s.id JOIN products p ON p.id=si.product_id
          WHERE {where} GROUP BY s.cidade_snapshot
        """, params).fetchall()
        cidades = [{"cidade": r["cid"] or "(sem cidade)", "v": r["v"] or 0} for r in rows_cid]

        kpis = {
            "faturamento": receita_liq if not incluir_rma else receita,
            "num_vendas": total_vendas,
            "estoque_venda": estoque_venda,
            "estoque_custo": estoque_custo,
            "ultimos_30": sum(valores30),
            "margem_media_pct": margem_pct,
            "prod_sem_venda": len(sem_venda_list),
            "cidades_qtd": len([x for x in cidades if x["v"]>0]),
            "lucro_bruto": lucro_bruto,
            "lucro_liquido": lucro_liq,
            "sem_venda_list": sem_venda_list,
            "vendas_dia_labels": labels30,
            "vendas_dia_values": valores30,
            "cidades": cidades,
        }
        return kpis

def compute_graphs(ini,fim,categoria,cidade,vendedor,incluir_rma, top_metric):
    with conn() as c:
        where, params = apply_filters_where(ini,fim,categoria,cidade,vendedor)

        # Top 10 por faturamento/quantidade
        if top_metric == "quantidade":
            sql_top = f"""
              SELECT p.nome AS label, SUM(si.qtde) v
              FROM sale_items si JOIN sales s ON s.id=si.sale_id JOIN products p ON p.id=si.product_id
              WHERE {where} GROUP BY p.id ORDER BY v DESC LIMIT 10
            """
            label = "Quantidade"
        else:
            sql_top = f"""
              SELECT p.nome AS label, SUM(si.qtde*si.preco_unit) v
              FROM sale_items si JOIN sales s ON s.id=si.sale_id JOIN products p ON p.id=si.product_id
              WHERE {where} GROUP BY p.id ORDER BY v DESC LIMIT 10
            """
            label = "Faturamento (R$)"
        top = c.execute(sql_top, params).fetchall()
        top_labels = [r["label"] for r in top]
        top_values = [round(r["v"] or 0,2) for r in top]

        # Pizza por categoria (inclui "Sem categoria")
        pie = c.execute(f"""
          SELECT COALESCE(p.categoria, 'Sem categoria') AS cat, SUM(si.qtde*si.preco_unit) v
          FROM sale_items si JOIN sales s ON s.id=si.sale_id JOIN products p ON p.id=si.product_id
          WHERE {where} GROUP BY COALESCE(p.categoria, 'Sem categoria')
        """, params).fetchall()
        cat_labels = [r["cat"] for r in pie]
        cat_values = [round(r["v"] or 0,2) for r in pie]

        # Margem por categoria (últimos 30d, ignora custo nulo)
        ult30_ini = fim - datetime.timedelta(days=29)
        mc = c.execute(f"""
          SELECT COALESCE(p.categoria,'Sem categoria') AS cat,
                 SUM(CASE WHEN si.custo_snap>0 THEN (si.qtde*si.preco_unit - si.qtde*si.custo_snap) ELSE 0 END) lucro,
                 SUM(CASE WHEN si.custo_snap>0 THEN (si.qtde*si.preco_unit) ELSE 0 END) receita
          FROM sale_items si JOIN sales s ON s.id=si.sale_id JOIN products p ON p.id=si.product_id
          WHERE date(s.data) BETWEEN ? AND ? AND ({where})
          GROUP BY COALESCE(p.categoria,'Sem categoria')
        """, [ult30_ini.isoformat(), fim.isoformat(), *params]).fetchall()
        m_labels = [r["cat"] for r in mc]
        m_values = [round((r["lucro"]/r["receita"]*100) if r["receita"] else 0,2) for r in mc]

        # Vendas por dia (com zeros)
        r30 = c.execute(f"""
          SELECT date(s.data) AS d, SUM(si.qtde*si.preco_unit) v
          FROM sale_items si JOIN sales s ON s.id=si.sale_id JOIN products p ON p.id=si.product_id
          WHERE date(s.data) BETWEEN ? AND ? AND ({where})
          GROUP BY date(s.data)
        """, [ult30_ini.isoformat(), fim.isoformat(), *params]).fetchall()
        mapa30 = {row["d"]: row["v"] for row in r30}
        labels30 = [ (ult30_ini + datetime.timedelta(days=i)).isoformat() for i in range(30) ]
        valores30 = [round(mapa30.get(d,0),2) for d in labels30]

        # Cidades vendidas
        rows_cid = c.execute(f"""
          SELECT s.cidade_snapshot AS cid, SUM(si.qtde*si.preco_unit) v
          FROM sale_items si JOIN sales s ON s.id=si.sale_id JOIN products p ON p.id=si.product_id
          WHERE {where} GROUP BY s.cidade_snapshot
        """, params).fetchall()
        cid_labels = [ (r["cid"] or "(sem cidade)") for r in rows_cid ]
        cid_values = [ round(r["v"] or 0,2) for r in rows_cid ]

        return {
            "top10": {"labels": top_labels, "values": top_values, "label": label},
            "categoria": {"labels": cat_labels, "values": cat_values},
            "margem_categoria": {"labels": m_labels, "values": m_values},
            "vendas_dia": {"labels": labels30, "values": valores30},
            "cidades": {"labels": cid_labels, "values": cid_values}
        }

# === ROUTES ===
@app.route("/")
@app.route("/dashboard")
def dashboard():
    ini,fim,categoria,cidade,vendedor,incluir_rma = get_filters()
    top_metric = request.args.get("top","faturamento")
    kpis = compute_kpis(ini,fim,categoria,cidade,vendedor,incluir_rma)
    with conn() as c:
        top_rows = c.execute(
            """
            SELECT
              COALESCE(NULLIF(MIN(TRIM(p.nome)), ''), '(SEM NOME)') AS nome,
              SUM(COALESCE(si.preco_unit,0) - COALESCE(si.custo_snap,0)) AS lucro_liquido
            FROM products p
            LEFT JOIN sale_items si ON si.product_id = p.id
            GROUP BY UPPER(TRIM(COALESCE(p.nome,'')))
            ORDER BY lucro_liquido DESC
            LIMIT 10
            """
        ).fetchall()
        daily_rows = c.execute(
            """
            SELECT DATE(COALESCE(s.data, CURRENT_TIMESTAMP)) AS dia,
                   SUM(COALESCE(si.preco_unit,0) - COALESCE(si.custo_snap,0)) AS lucro_liquido
            FROM sale_items si
            JOIN sales s ON s.id = si.sale_id
            GROUP BY DATE(COALESCE(s.data, CURRENT_TIMESTAMP))
            ORDER BY dia ASC
            """
        ).fetchall()
    rows = [
        {
            "nome": r["nome"],
            "lucro_liquido": r["lucro_liquido"] or 0,
        }
        for r in top_rows
    ]
    chart_labels = [r["dia"] for r in daily_rows]
    chart_values = [float(r["lucro_liquido"] or 0) for r in daily_rows]
    # KPI cards
    kpi_cards = [
        {"title":"Faturamento", "value": br_money(kpis["faturamento"]), "badge":"ok" if kpis["faturamento"]>0 else None, "hint": None if kpis["faturamento"]>0 else "Registre vendas."},
        {"title":"Nº de vendas", "value": kpis["num_vendas"], "badge": None, "hint": None if kpis["num_vendas"]>0 else "Registre vendas."},
        {"title":"Estoque (venda)", "value": br_money(kpis["estoque_venda"]), "badge": None, "hint": None},
        {"title":"Estoque (custo)", "value": br_money(kpis["estoque_custo"]), "badge": None, "hint": None},
        {"title":"Últimos 30 dias", "value": br_money(kpis["ultimos_30"]), "badge": None, "hint": None},
        {"title":"Margem média %", "value": f"{kpis['margem_media_pct']:.1f}%", "badge": None, "hint": "Defina custo_base ou registre compras para calcular margem." if kpis["margem_media_pct"]==0 else None},
        {"title":"Sem venda há X dias", "value": kpis["prod_sem_venda"], "badge":"aten" if kpis["prod_sem_venda"]>0 else "ok", "hint": None},
        {"title":"Cidades vendidas", "value": kpis["cidades_qtd"], "badge": None, "hint": None},
        {"title":"Lucro bruto", "value": br_money(kpis["lucro_bruto"]), "badge": None, "hint": None},
        {"title":"Lucro líquido (mês/período)", "value": br_money(kpis["lucro_liquido"]), "badge": None, "hint": None},
    ]
    return render_template(
        "dashboard.html",
        kpi_cards=kpi_cards,
        top_metric=top_metric,
        rows=rows,
        chart_labels=chart_labels,
        chart_values=chart_values,
    )

@app.route("/api/graficos")
def api_graficos():
    ini,fim,categoria,cidade,vendedor,incluir_rma = get_filters()
    top_metric = request.args.get("top","faturamento")
    charts = compute_graphs(ini,fim,categoria,cidade,vendedor,incluir_rma, top_metric)
    return jsonify(charts)

@app.route("/relatorios")
def relatorios():
    ini,fim,categoria,cidade,vendedor,incluir_rma = get_filters()
    kpis = compute_kpis(ini,fim,categoria,cidade,vendedor,incluir_rma)
    # reposição
    with conn() as c:
        repos = c.execute("SELECT sku,nome,estoque_atual,estoque_minimo FROM products WHERE estoque_atual < estoque_minimo").fetchall()
        # por vendedor
        rows = c.execute("""
          SELECT u.nome, COALESCE(SUM(si.qtde*si.preco_unit),0) faturamento,
                 COALESCE(SUM(si.qtde*si.preco_unit - si.qtde*si.custo_snap),0) margem,
                 AVG(si.preco_unit) ticket
          FROM sales s JOIN sale_items si ON si.sale_id=s.id JOIN users u ON u.id=s.vendedor_id
          GROUP BY u.id
        """).fetchall()
        # RMA hist
        rma_hist = c.execute("""
          SELECT codigo_rma, sale_id, tipo, status, motivo, substr(created_at,1,10) AS created_at
          FROM rmas ORDER BY id DESC LIMIT 20
        """).fetchall()
        # Ajustes hist
        ajustes_hist = c.execute("""
          SELECT a.id, p.nome, a.ajuste_tipo, a.qtde_delta, a.qtde_antes, a.qtde_depois, substr(a.created_at,1,16) created_at
          FROM stock_adjustments a JOIN products p ON p.id=a.product_id ORDER BY a.id DESC LIMIT 20
        """).fetchall()
    return render_template("relatorios.html",
        reposicao=repos, sem_venda=kpis["sem_venda_list"], no_sale_days=get_settings()["no_sale_days"],
        por_vendedor=rows, rma_hist=rma_hist, ajustes_hist=ajustes_hist)

@app.route("/produtos", methods=["GET","POST"])
def produtos():
    generated_sku = None
    if request.method == "POST":
        data = request.form
        # fornecedor inline: cria ou atualiza cadastro com dados fornecidos
        forn_id = None
        nomef = (data.get("fornecedor_nome") or '').strip()
        cidadef = (data.get("fornecedor_cidade") or '').strip()
        telefonef = (data.get("fornecedor_telefone") or '').strip()
        emailf = (data.get("fornecedor_email") or '').strip()
        docf = (data.get("fornecedor_doc") or '').strip()
        if nomef:
            with conn() as c:
                row = c.execute("SELECT * FROM suppliers WHERE nome=?", (nomef,)).fetchone()
                if row:
                    forn_id = row['id']
                    # atualiza campos existentes somente se valores informados
                    updates = []
                    vals = []
                    if cidadef:
                        updates.append("cidade=?")
                        vals.append(cidadef)
                    if telefonef:
                        updates.append("telefone=?")
                        vals.append(telefonef)
                    if emailf:
                        updates.append("email=?")
                        vals.append(emailf)
                    if docf:
                        updates.append("doc=?")
                        vals.append(docf)
                    if updates:
                        vals.append(forn_id)
                        c.execute("UPDATE suppliers SET " + ", ".join(updates) + " WHERE id=?", vals)
                else:
                    forn_id = c.execute(
                        "INSERT INTO suppliers(nome, cidade, telefone, email, doc) VALUES(?,?,?,?,?)",
                        (nomef, cidadef or None, telefonef or None, emailf or None, docf or None),
                    ).lastrowid
        # sku
        sku = data.get("sku","").strip()
        if not sku:
            sku = generate_sku(data)
        # Data de criação do produto: permite informar manualmente via campo data_produto
        data_input = data.get('data_produto') or ''
        try:
            now = datetime.datetime.fromisoformat(data_input).isoformat() if data_input else datetime.datetime.now().isoformat(timespec='seconds')
        except Exception:
            now = datetime.datetime.now().isoformat(timespec='seconds')
        with conn() as c:
            try:
                c.execute("""INSERT INTO products
                    (sku,nome,categoria,plataforma,modelo,capacidade,cor,regiao,condicao,preco_lista,custo_base,estoque_minimo,estoque_atual,created_at,updated_at,supplier_id)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
                    sku,
                    data.get("nome"),
                    data.get("categoria") or None,
                    data.get("plataforma") or None,
                    data.get("modelo") or None,
                    data.get("capacidade") or None,
                    data.get("cor") or None,
                    data.get("regiao") or None,
                    data.get("condicao") or None,
                    float(data.get("preco_lista") or 0),
                    float(data.get("custo_base") or 0),
                    int(data.get("estoque_minimo") or 0),
                    int(data.get("estoque_atual") or 0),
                    now,
                    now,
                    forn_id
                ))
                flash("Produto salvo", "success")
            except sqlite3.IntegrityError:
                flash("SKU duplicado. Edite ou regenere.", "danger")
    with conn() as c:
        produtos = c.execute("SELECT * FROM products ORDER BY id DESC LIMIT 50").fetchall()
    # constrói mapa modelo->min e soma estoque para checar nível por modelo
    # Constrói mapa de agregação baseado apenas no campo ``modelo``.  Para cada
    # modelo de produto, registra o maior estoque mínimo entre variantes e soma
    # o estoque atual.  Isto permite analisar o estoque mínimo ao nível do
    # modelo, conforme solicitado.
    modelo_minmap: dict[str, dict[str, int]] = {}
    for p in produtos:
        key = (p['modelo'] or '').strip()
        if key:
            entry = modelo_minmap.get(key, {'min': 0, 'sum': 0})
            try:
                em = p['estoque_minimo'] or 0
            except Exception:
                em = 0
            try:
                ea = p['estoque_atual'] or 0
            except Exception:
                ea = 0
            entry['min'] = max(entry['min'], em)
            entry['sum'] += ea
            modelo_minmap[key] = entry
    return render_template("produtos.html", produtos=produtos, generated_sku=generated_sku, modelo_minmap=modelo_minmap)

@app.route("/produtos/sku/regenerar")
def produtos_regenerar_sku():
    # Gera SKU genérico com base em query atual? Aqui só um exemplo simples
    params = {k:v for k,v in request.args.items()}
    sku = generate_sku(params)
    flash(f"SKU gerado: {sku}", "info")
    return redirect(url_for("produtos"))

def generate_sku(p):
    """
    Gera um SKU baseado no nome, modelo e capacidade do produto.

    O formato retornado é ``NOME-MODELO[-CAPACIDADE]-#####`` onde
    ``CAPACIDADE`` só aparece se estiver preenchida.  Cada parte é
    normalizada removendo caracteres que não são alfanuméricos e
    convertendo espaços e pontuações em hifens.  O sufixo numérico tem
    cinco dígitos e é incrementado a partir do maior sufixo existente
    para o mesmo prefixo.
    """
    def norm(v):
        # Normaliza o texto: remove acentos, converte para ASCII, substitui
        # sequência de caracteres não alfanuméricos por hífen e deixa em
        # maiúsculas. Retorna ``None`` para valores vazios.
        if not v:
            return None
        txt = str(v).strip().upper()
        # Substitui caracteres não alfanuméricos por hífen
        txt = re.sub(r"[^A-Z0-9]+", "-", txt)
        txt = txt.strip("-")
        return txt or None

    nome = norm(p.get("nome"))
    modelo = norm(p.get("modelo"))
    capacidade = norm(p.get("capacidade"))
    parts = []
    if nome:
        parts.append(nome)
    if modelo:
        parts.append(modelo)
    if capacidade:
        parts.append(capacidade)
    base = "-".join(parts).strip("-")
    if not base:
        base = "GEN"
    # Sufixo sequencial de 5 dígitos por prefixo
    with conn() as c:
        rows = c.execute(
            "SELECT sku FROM products WHERE sku LIKE ?||'-%'",
            (base,),
        ).fetchall()
        seq = 1
        for r in rows:
            try:
                suf = str(r["sku"]).split("-")[-1]
                if suf.isdigit():
                    seq = max(seq, int(suf) + 1)
            except Exception:
                pass
    return f"{base}-{str(seq).zfill(5)}"

@app.route("/compras", methods=["GET","POST"])
def compras():
    if request.method == "POST":
        f = request.form
        data = parse_date(f.get("data")) or datetime.date.today()
        # fornecedor (inline by name)
        with conn() as c:
            row = c.execute("SELECT id FROM suppliers WHERE nome=?", (f.get("fornecedor_nome"),)).fetchone()
            if row: sup_id = row["id"]
            else:
                sup_id = c.execute("INSERT INTO suppliers(nome) VALUES(?)", (f.get("fornecedor_nome"),)).lastrowid
            pid = c.execute("INSERT INTO purchases(data, supplier_id, frete, outras_despesas, obs) VALUES(?,?,?,?,?)",
                            (data.isoformat(), sup_id, float(f.get('frete') or 0), float(f.get('outras_despesas') or 0), f.get('obs'))).lastrowid
            pr = c.execute("SELECT id FROM products WHERE sku=?", (f.get("product_sku"),)).fetchone()
            if not pr:
                flash("Produto não encontrado pelo SKU", "danger"); return redirect(url_for("compras"))
            pr_id = pr["id"]
            qtde = int(f.get("qtde") or 1)
            custo_unit = float(f.get("custo_unit") or 0)
            c.execute("INSERT INTO purchase_items(purchase_id,product_id,qtde,custo_unit) VALUES(?,?,?,?)", (pid, pr_id, qtde, custo_unit))
            # mov IN + atualiza estoque e custo_base
            c.execute("INSERT INTO stock_moves(data,product_id,tipo,qtde,origem,ref_id,usuario_id) VALUES(?,?,?,?,?,?,?)",
                      (data.isoformat(), pr_id, "IN", qtde, "compra", pid, current_user_id()))
            c.execute("UPDATE products SET estoque_atual=COALESCE(estoque_atual,0)+?, custo_base=COALESCE(?, custo_base) WHERE id=?",
                      (qtde, custo_unit, pr_id))
            flash("Compra registrada", "success")
    with conn() as c:
        compras = c.execute("SELECT p.id, p.data, s.nome as fornecedor, p.frete, p.obs FROM purchases p LEFT JOIN suppliers s ON s.id=p.supplier_id ORDER BY p.id DESC LIMIT 30").fetchall()
    return render_template("compras.html", compras=compras)

@app.route("/vendas", methods=["GET","POST"])
def vendas():
    """Página e endpoint de criação de vendas.

    Além de registrar novas vendas, agora lista os últimos itens de venda com
    mais detalhes (cliente, telefone, produto, quantidades etc.) e oferece
    link para editar cada venda registrada.
    """
    if request.method == "POST":
        f = request.form
        data = parse_date(f.get("data")) or datetime.date.today()
        # cliente inline: procura por nome; atualiza ou insere
        with conn() as c:
            row = c.execute("SELECT id FROM customers WHERE nome=?", (f.get("cliente_nome"),)).fetchone()
            if row:
                cust_id = row["id"]
                # atualiza dados do cliente com cidade/telefone/doc informados
                c.execute(
                    "UPDATE customers SET cidade=?, telefone=?, doc=? WHERE id=?",
                    (
                        f.get("cliente_cidade"),
                        f.get("cliente_telefone"),
                        f.get("cliente_doc"),
                        cust_id,
                    ),
                )
            else:
                cust_id = c.execute(
                    "INSERT INTO customers(nome,cidade,telefone,doc) VALUES(?,?,?,?)",
                    (
                        f.get("cliente_nome"),
                        f.get("cliente_cidade"),
                        f.get("cliente_telefone"),
                        f.get("cliente_doc"),
                    ),
                ).lastrowid
            cidade_snap = (
                c.execute("SELECT cidade FROM customers WHERE id=?", (cust_id,))
                .fetchone()["cidade"]
            )
            vend_id = int(f.get("vendedor_id") or 2)
            # Política de desconto
            desconto_pct = float(f.get("desconto_pct") or 0)
            settings = get_settings()
            pin = f.get("pin_aprovacao")
            pin_ok = True
            if desconto_pct > settings["discount_limit_pct"]:
                # precisa validar PIN de gerente
                ger = c.execute(
                    "SELECT pin_desconto FROM users WHERE perfil='gerente' ORDER BY id LIMIT 1"
                ).fetchone()
                pin_ok = bool(
                    ger and ger["pin_desconto"] and pin == ger["pin_desconto"]
                )
                if not pin_ok:
                    flash(
                        "Desconto acima do limite requer PIN de gerente.",
                        "danger",
                    )
                    return redirect(url_for("vendas"))
            # cria venda
            sid = c.execute(
                "INSERT INTO sales(data, customer_id, vendedor_id, desconto_valor_total, desconto_pct_total, motivo_desconto, pin_aprovacao, cidade_snapshot) VALUES(?,?,?,?,?,?,?,?)",
                (
                    data.isoformat(),
                    cust_id,
                    vend_id,
                    float(f.get("desconto_valor") or 0),
                    desconto_pct,
                    f.get("motivo_desconto"),
                    pin if pin_ok else None,
                    cidade_snap,
                ),
            ).lastrowid
            # produto
            pr = c.execute(
                "SELECT id, estoque_atual, preco_lista, custo_base FROM products WHERE sku=?",
                (f.get("product_sku"),),
            ).fetchone()
            if not pr:
                flash("Produto não encontrado", "danger")
                return redirect(url_for("vendas"))
            qtde = int(f.get("qtde") or 1)
            if pr["estoque_atual"] < qtde:
                flash("Estoque insuficiente — venda bloqueada.", "danger")
                return redirect(url_for("vendas"))
            preco_unit = float(f.get("preco_unit") or 0)
            c.execute(
                "INSERT INTO sale_items(sale_id,product_id,qtde,preco_lista_snap,preco_unit,desconto_valor,desconto_pct,custo_snap) VALUES(?,?,?,?,?,?,?,?)",
                (
                    sid,
                    pr["id"],
                    qtde,
                    pr["preco_lista"] or 0,
                    preco_unit,
                    float(f.get("desconto_valor") or 0),
                    desconto_pct,
                    pr["custo_base"] or 0,
                ),
            )
            # movimentação OUT
            c.execute(
                "INSERT INTO stock_moves(data,product_id,tipo,qtde,origem,ref_id,usuario_id) VALUES(?,?,?,?,?,?,?)",
                (
                    data.isoformat(),
                    pr["id"],
                    "OUT",
                    qtde,
                    "venda",
                    sid,
                    vend_id,
                ),
            )
            c.execute(
                "UPDATE products SET estoque_atual=estoque_atual-? WHERE id=?",
                (qtde, pr["id"]),
            )
            flash("Venda registrada", "success")
    # Lista das últimas 50 linhas de itens de venda, com mais detalhes
    with conn() as c:
        vendas = c.execute(
            """
            SELECT
              si.id AS sale_item_id,
              s.id AS sale_id,
              s.data AS data,
              c.nome AS cliente,
              c.telefone AS telefone,
              s.cidade_snapshot AS cidade,
              u.nome AS vendedor,
              p.nome AS produto,
              p.sku AS sku,
              si.qtde AS qtde,
              si.preco_unit AS preco_unit,
              si.desconto_pct AS desconto_pct,
              si.desconto_valor AS desconto_valor
            FROM sales s
            JOIN sale_items si ON si.sale_id = s.id
            JOIN products p ON p.id = si.product_id
            LEFT JOIN customers c ON c.id = s.customer_id
            LEFT JOIN users u ON u.id = s.vendedor_id
            ORDER BY s.id DESC, si.id DESC
            LIMIT 50
            """,
        ).fetchall()
    return render_template("vendas.html", vendas=vendas)

@app.route("/rmas", methods=["GET","POST"])
def rmas():
    if request.method == "POST":
        f = request.form
        sale_id = int(f.get("sale_id"))
        tipo = f.get("tipo")
        forma = f.get("forma")
        motivo = f.get("motivo")
        valor_reembolso = float(f.get("valor_reembolso") or 0)
        sale_item_id = int(f.get("sale_item_id"))
        qtde = int(f.get("qtde") or 1)
        sku = f.get("product_sku")

        now = datetime.datetime.now()
        codigo = "RMA-" + now.strftime("%Y%m%d%H%M%S")
        with conn() as c:
            # janela RMA
            settings = get_settings()
            venda = c.execute("SELECT data FROM sales WHERE id=?", (sale_id,)).fetchone()
            if not venda:
                flash("Venda não encontrada", "danger"); return redirect(url_for("rmas"))
            dt_venda = datetime.date.fromisoformat(venda["data"])
            if (datetime.date.today() - dt_venda).days > settings["rma_window_days"]:
                flash("Fora da janela de RMA.", "danger"); return redirect(url_for("rmas"))

            rma_id = c.execute("INSERT INTO rmas(codigo_rma,sale_id,tipo,motivo,forma_compensacao,valor_reembolso,status,usuario_id,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                               (codigo, sale_id, tipo, motivo, forma, valor_reembolso, "APROVADO", current_user_id(), now.isoformat(), now.isoformat())).lastrowid
            pr = c.execute("SELECT id FROM products WHERE sku=?", (sku,)).fetchone()
            if not pr:
                flash("Produto não encontrado", "danger"); return redirect(url_for("rmas"))
            c.execute("INSERT INTO rma_items(rma_id,sale_item_id,product_id,qtde) VALUES(?,?,?,?)", (rma_id, sale_item_id, pr["id"], qtde))
            # Movimentações
            # entrada do devolvido
            c.execute("INSERT INTO stock_moves(data,product_id,tipo,qtde,origem,ref_id,usuario_id) VALUES(?,?,?,?,?,?,?)",
                      (now.isoformat(), pr["id"], "IN", qtde, "rma_retorno" if tipo=="RETORNO" else "rma_troca", rma_id, current_user_id()))
            c.execute("UPDATE products SET estoque_atual=estoque_atual+? WHERE id=?", (qtde, pr["id"]))
            # se TROCA, saída do novo é feita manualmente em outra venda/lançamento ou poderia ser estendida aqui.
            flash("RMA criado", "success")
    with conn() as c:
        rmas = c.execute("SELECT codigo_rma, sale_id, tipo, status, substr(created_at,1,16) created_at FROM rmas ORDER BY id DESC LIMIT 30").fetchall()
    return render_template("rmas.html", rmas=rmas)

@app.route("/ajustes", methods=["GET","POST"])
def ajustes():
    if request.method == "POST":
        f = request.form
        sku = f.get("product_sku")
        tipo = f.get("ajuste_tipo")
        delta = int(f.get("qtde_delta"))
        motivo = f.get("motivo")
        if not motivo or motivo.strip() == "":
            flash("Motivo é obrigatório.", "danger"); return redirect(url_for("ajustes"))
        with conn() as c:
            pr = c.execute("SELECT id, estoque_atual FROM products WHERE sku=?", (sku,)).fetchone()
            if not pr:
                flash("Produto não encontrado", "danger"); return redirect(url_for("ajustes"))
            antes = pr["estoque_atual"] or 0
            depois = antes + delta
            if depois < 0:
                flash("Bloqueado: estoque não pode ficar negativo.", "danger"); return redirect(url_for("ajustes"))
            now = datetime.datetime.now().isoformat(timespec='seconds')
            aid = c.execute("INSERT INTO stock_adjustments(product_id,ajuste_tipo,qtde_delta,qtde_antes,qtde_depois,motivo,anexo_path,usuario_id,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                            (pr["id"], tipo, delta, antes, depois, motivo, None, current_user_id(), now)).lastrowid
            mov_tipo = "IN" if delta>0 else "OUT"
            c.execute("INSERT INTO stock_moves(data,product_id,tipo,qtde,origem,ref_id,usuario_id) VALUES(?,?,?,?,?,?,?)",
                      (now, pr["id"], mov_tipo, abs(delta), "ajuste", aid, current_user_id()))
            c.execute("UPDATE products SET estoque_atual=? WHERE id=?", (depois, pr["id"]))
            flash("Ajuste lançado.", "success")
    with conn() as c:
        ajustes = c.execute("SELECT a.id, p.nome, a.ajuste_tipo, a.qtde_delta, a.qtde_antes, a.qtde_depois, substr(a.created_at,1,16) created_at FROM stock_adjustments a JOIN products p ON p.id=a.product_id ORDER BY a.id DESC LIMIT 50").fetchall()
    return render_template("ajustes.html", ajustes=ajustes)

@app.route("/config", methods=["GET","POST"])
def config():
    if request.method == "POST":
        with conn() as c:
            for k in ["discount_limit_pct","rma_window_days","no_sale_days","theme_primary"]:
                c.execute("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)", (k, request.form.get(k)))
            flash("Configurações salvas", "success")
    return render_template("config.html", settings=get_settings())

# === EXPORTS ===
@app.route("/export/ajustes.csv")
def export_ajustes_csv():
    import csv, io
    with conn() as c:
        rows = c.execute("SELECT a.id, p.sku, p.nome, a.ajuste_tipo, a.qtde_delta, a.qtde_antes, a.qtde_depois, a.motivo, a.created_at FROM stock_adjustments a JOIN products p ON p.id=a.product_id ORDER BY a.id DESC").fetchall()
    out = io.StringIO()
    w = csv.writer(out, delimiter=';')
    w.writerow(["id","sku","nome","tipo","delta","antes","depois","motivo","created_at"])
    for r in rows: w.writerow([r["id"], r["sku"], r["nome"], r["ajuste_tipo"], r["qtde_delta"], r["qtde_antes"], r["qtde_depois"], r["motivo"], r["created_at"]])
    out.seek(0)
    return app.response_class(out.read(), mimetype="text/csv")

@app.route("/export/reposicao.csv")
def export_reposicao_csv():
    import csv, io
    with conn() as c:
        rows = c.execute("SELECT sku,nome,estoque_atual,estoque_minimo FROM products WHERE estoque_atual < estoque_minimo").fetchall()
    out = io.StringIO()
    w = csv.writer(out, delimiter=';')
    w.writerow(["sku","nome","estoque_atual","estoque_minimo"])
    for r in rows: w.writerow([r["sku"], r["nome"], r["estoque_atual"], r["estoque_minimo"]])
    out.seek(0)
    return app.response_class(out.read(), mimetype="text/csv")

@app.route("/api/product_suggestions")
def product_suggestions():
    """Retorna lista de produtos para autocomplete (SKU e nome)."""
    q = (request.args.get("q") or "").strip().lower()
    with conn() as c:
        # Retorna somente produtos com estoque disponível (> 0) para o autocomplete.
        rows = c.execute(
            "SELECT sku, nome FROM products WHERE estoque_atual > 0 ORDER BY updated_at DESC, created_at DESC LIMIT 500"
        ).fetchall()
    results = []
    for r in rows:
        label = f"{r['sku']} - {r['nome']}"
        if not q or q in r['sku'].lower() or (r['nome'] or '').lower().find(q) >= 0:
            results.append({"label": label, "sku": r["sku"], "nome": r["nome"]})
    return jsonify(results)

# ----------------------------------------------------------------------------
# Login/logout views
@app.route("/login", methods=["GET", "POST"])
def login():
    """Displays the login form and handles authentication.

    On POST the username and password provided by the user are checked
    against the ``auth_users`` table.  The password stored in the database
    is compared using ``hash_password``.  Successful login stores the
    ``user_id`` in the session and redirects to the dashboard.  Errors
    trigger a flash message.  GET simply renders the login page.
    """
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        with conn() as c:
            row = c.execute(
                "SELECT id, password FROM auth_users WHERE username=?",
                (username,),
            ).fetchone()
        if row and row[1] == hash_password(password):
            session["user_id"] = row[0]
            flash("Login realizado com sucesso.", "success")
            return redirect(url_for("dashboard"))
        flash("Credenciais inválidas.", "danger")
    return render_template("login.html")


@app.route("/logout")
def logout():
    """Clears the current session and redirects to the login page."""
    session.pop("user_id", None)
    flash("Logout efetuado.", "info")
    return redirect(url_for("login"))

@app.route("/produtos/<int:prod_id>/delete", methods=["POST"])
def produto_delete(prod_id):
    """Exclui um produto, se não houver itens de venda vinculados."""
    with conn() as c:
        ref = c.execute("SELECT 1 FROM sale_items WHERE product_id=?", (prod_id,)).fetchone()
        if ref:
            flash("Produto vinculado a vendas; exclusão bloqueada.", "warning")
            return redirect(url_for("produtos"))
        c.execute("DELETE FROM products WHERE id=?", (prod_id,))
    flash("Produto excluído", "success")
    return redirect(url_for("produtos"))

@app.route("/vendas/<int:sale_id>/delete", methods=["POST"])
def venda_delete(sale_id):
    """Exclui uma venda e reverte o estoque dos itens."""
    with conn() as c:
        items = c.execute("SELECT product_id, qtde FROM sale_items WHERE sale_id=?", (sale_id,)).fetchall()
        for it in items:
            # Devolve estoque
            c.execute("UPDATE products SET estoque_atual = COALESCE(estoque_atual,0) + ? WHERE id=?", (it['qtde'], it['product_id']))
            c.execute(
                "INSERT INTO stock_moves(data,product_id,tipo,qtde,origem,ref_id,usuario_id) VALUES(?,?,?,?,?,?,?)",
                (datetime.date.today().isoformat(), it['product_id'], 'IN', it['qtde'], 'ajuste', sale_id, current_user_id())
            )
        c.execute("DELETE FROM sale_items WHERE sale_id=?", (sale_id,))
        c.execute("DELETE FROM sales WHERE id=?", (sale_id,))
    flash("Venda excluída e estoque revertido.", "success")
    return redirect(url_for("vendas"))

if __name__ == "__main__":
    check_files()

    import os

    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "5001"))

    # Se eu quiser ativar a escolha automática de porta livre:
    if os.environ.get("AUTO_FREE_PORT", "0") == "1":
        port = _free_port(port)  # usa a porta escolhida como base (5001 por padrão)

    url = f"http://{host}:{port}"
    _open_browser(url)

    app.run(host=host, port=port, debug=False, use_reloader=False)
import os

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5001"))  # DEV padrão 5001
    # Não use host="0.0.0.0" no seu PC; use loopback
    app.run(host="127.0.0.1", port=port, debug=False)
@app.get("/health")
def health():
    # ajuda a confirmar em qual instância você está
    return f"DEV-{os.environ.get('PORT','?')} OK", 200

@app.context_processor
def inject_env_flag():
    return {"IS_DEV": os.environ.get("PORT") == "5001"}


