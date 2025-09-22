import sqlite3, os, datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "erp.db")

schema_sql = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS categories(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  nome TEXT
);

CREATE TABLE IF NOT EXISTS suppliers(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  nome TEXT NOT NULL,
  cidade TEXT, telefone TEXT, email TEXT, doc TEXT
);

CREATE TABLE IF NOT EXISTS customers(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  nome TEXT NOT NULL,
  cidade TEXT, telefone TEXT, email TEXT, doc TEXT
);

CREATE TABLE IF NOT EXISTS users(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  nome TEXT NOT NULL,
  perfil TEXT CHECK(perfil IN ('admin','gerente','vendedor')) NOT NULL,
  pin_desconto TEXT
);

CREATE TABLE IF NOT EXISTS products(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  sku TEXT UNIQUE NOT NULL,
  nome TEXT NOT NULL,
  categoria TEXT,
  plataforma TEXT, modelo TEXT, capacidade TEXT, cor TEXT, regiao TEXT, condicao TEXT,
  preco_lista REAL DEFAULT 0,
  custo_base REAL,
  estoque_minimo INTEGER DEFAULT 0,
  estoque_atual INTEGER DEFAULT 0,
  created_at TEXT, updated_at TEXT
);

CREATE TABLE IF NOT EXISTS purchases(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  data TEXT, supplier_id INTEGER,
  frete REAL DEFAULT 0, outras_despesas REAL DEFAULT 0, obs TEXT,
  FOREIGN KEY(supplier_id) REFERENCES suppliers(id)
);

CREATE TABLE IF NOT EXISTS purchase_items(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  purchase_id INTEGER, product_id INTEGER, qtde INTEGER, custo_unit REAL,
  FOREIGN KEY(purchase_id) REFERENCES purchases(id),
  FOREIGN KEY(product_id) REFERENCES products(id)
);

CREATE TABLE IF NOT EXISTS sales(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  data TEXT, customer_id INTEGER, vendedor_id INTEGER,
  desconto_valor_total REAL, desconto_pct_total REAL,
  motivo_desconto TEXT, pin_aprovacao TEXT, cidade_snapshot TEXT,
  FOREIGN KEY(customer_id) REFERENCES customers(id),
  FOREIGN KEY(vendedor_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS sale_items(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  sale_id INTEGER, product_id INTEGER, qtde INTEGER,
  preco_lista_snap REAL, preco_unit REAL,
  desconto_valor REAL, desconto_pct REAL,
  custo_snap REAL,
  FOREIGN KEY(sale_id) REFERENCES sales(id),
  FOREIGN KEY(product_id) REFERENCES products(id)
);

CREATE TABLE IF NOT EXISTS stock_moves(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  data TEXT, product_id INTEGER, tipo TEXT CHECK(tipo IN ('IN','OUT')),
  qtde INTEGER,
  origem TEXT CHECK(origem IN ('compra','venda','ajuste','rma_retorno','rma_troca','ajuste_edit_prod','venda_edit')),
  ref_id INTEGER, usuario_id INTEGER,
  FOREIGN KEY(product_id) REFERENCES products(id),
  FOREIGN KEY(usuario_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS rmas(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  codigo_rma TEXT UNIQUE,
  sale_id INTEGER,
  tipo TEXT CHECK(tipo IN ('RETORNO','TROCA')),
  motivo TEXT,
  forma_compensacao TEXT CHECK(forma_compensacao IN ('reembolso','credito','troca')),
  valor_reembolso REAL,
  status TEXT CHECK(status IN ('ABERTO','APROVADO','CONCLUIDO','CANCELADO')) DEFAULT 'ABERTO',
  usuario_id INTEGER,
  created_at TEXT, updated_at TEXT,
  FOREIGN KEY(sale_id) REFERENCES sales(id),
  FOREIGN KEY(usuario_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS rma_items(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  rma_id INTEGER, sale_item_id INTEGER, product_id INTEGER, qtde INTEGER,
  FOREIGN KEY(rma_id) REFERENCES rmas(id),
  FOREIGN KEY(sale_item_id) REFERENCES sale_items(id),
  FOREIGN KEY(product_id) REFERENCES products(id)
);

CREATE TABLE IF NOT EXISTS stock_adjustments(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  product_id INTEGER, ajuste_tipo TEXT,
  qtde_delta INTEGER, qtde_antes INTEGER, qtde_depois INTEGER,
  motivo TEXT, anexo_path TEXT, usuario_id INTEGER, created_at TEXT,
  FOREIGN KEY(product_id) REFERENCES products(id),
  FOREIGN KEY(usuario_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS settings(
  key TEXT PRIMARY KEY,
  value TEXT
);

-- Índices úteis
CREATE INDEX IF NOT EXISTS idx_sales_data ON sales(data);
CREATE INDEX IF NOT EXISTS idx_sale_items_prod ON sale_items(product_id);
CREATE INDEX IF NOT EXISTS idx_moves_prod_data ON stock_moves(product_id, data);
"""

def main():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(schema_sql)
    conn.commit()
    conn.close()
    print("Schema criado em", DB_PATH)

if __name__ == "__main__":
    main()