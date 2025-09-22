import sqlite3, os, random, datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "erp.db")

def insert(conn, table, data):
    keys = ",".join(data.keys())
    qs = ",".join(["?"]*len(data))
    cur = conn.execute(f"INSERT INTO {table} ({keys}) VALUES ({qs})", list(data.values()))
    return cur.lastrowid

def set_setting(conn, key, value):
    conn.execute("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)", (key, str(value)))

def today():
    return datetime.date.today()

def date_days_ago(n):
    return (today() - datetime.timedelta(days=n)).isoformat()

def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # Settings
    set_setting(conn, "discount_limit_pct", "10")
    set_setting(conn, "rma_window_days", "30")
    set_setting(conn, "no_sale_days", "7")
    set_setting(conn, "theme_primary", "#2563eb")

    # Users
    admin_id = insert(conn, "users", {"nome":"Admin", "perfil":"admin", "pin_desconto":"0000"})
    gerente_id = insert(conn, "users", {"nome":"Gerente", "perfil":"gerente", "pin_desconto":"4321"})
    vendedor_id = insert(conn, "users", {"nome":"Vendedor", "perfil":"vendedor", "pin_desconto":None})

    # Suppliers
    sup_names = [("Tech Import", "São Paulo"), ("Giga Eletrônicos", "Ribeirão Preto"), ("Digital Max", "Campinas")]
    sup_ids = []
    for n,c in sup_names:
        sup_ids.append(insert(conn, "suppliers", {"nome":n, "cidade":c, "telefone":"", "email":"", "doc":""}))

    # Customers
    cli_names = [("Carlos Silva","Monte Alto"),("Ana Souza","Jaboticabal"),("Marcos Lima","Taquaritinga"),
                 ("Beatriz Costa","Araraquara"),("Paula Rocha","São Paulo")]
    cli_ids = []
    for n,c in cli_names:
        cli_ids.append(insert(conn, "customers", {"nome":n, "cidade":c, "telefone":"", "email":"", "doc":""}))

    # Products (10)
    prods = [
        {"nome":"PS4 Slim 500GB", "categoria":"Consoles","plataforma":"PS4","modelo":"Slim","capacidade":"500GB","cor":"Preto","regiao":"BR","condicao":"USADO","preco_lista":1800.00,"custo_base":1300.00,"estoque_minimo":1,"estoque_atual":2},
        {"nome":"Controle DualShock 4", "categoria":"Acessórios","plataforma":"PS4","modelo":"DS4","capacidade":"","cor":"Preto","regiao":"BR","condicao":"USADO","preco_lista":220.00,"custo_base":150.00,"estoque_minimo":2,"estoque_atual":5},
        {"nome":"Xbox One 1TB", "categoria":"Consoles","plataforma":"XBOX","modelo":"One","capacidade":"1TB","cor":"Preto","regiao":"US","condicao":"USADO","preco_lista":1700.00,"custo_base":1200.00,"estoque_minimo":1,"estoque_atual":1},
        # Product with a 43" 4K television.  Use single quotes around the
        # string so the embedded double quote in 43" does not terminate
        # the surrounding literal.  Without this change Python would
        # interpret the second double quote as the end of the string and
        # raise a syntax error when evaluating this dict.
        {"nome":'TV 43" 4K', "categoria":"TVs","plataforma":"TV","modelo":"43PFG","capacidade":"4K","cor":"Preto","regiao":"BR","condicao":"USADO","preco_lista":1600.00,"custo_base":1100.00,"estoque_minimo":1,"estoque_atual":0},
        {"nome":"Cabo HDMI 2.0", "categoria":"Acessórios","plataforma":"ACC","modelo":"HDMI","capacidade":"2m","cor":"Preto","regiao":"BR","condicao":"NOVO","preco_lista":30.00,"custo_base":12.00,"estoque_minimo":5,"estoque_atual":8},
        {"nome":"PS5 1TB", "categoria":"Consoles","plataforma":"PS5","modelo":"CFI-1215","capacidade":"1TB","cor":"Branco","regiao":"BR","condicao":"NOVO","preco_lista":3990.00,"custo_base":3200.00,"estoque_minimo":1,"estoque_atual":1},
        {"nome":"Xbox Series S 512GB", "categoria":"Consoles","plataforma":"XBOX","modelo":"Series S","capacidade":"512GB","cor":"Branco","regiao":"BR","condicao":"NOVO","preco_lista":2290.00,"custo_base":1800.00,"estoque_minimo":1,"estoque_atual":1},
        {"nome":"Memória SD 128GB", "categoria":"Acessórios","plataforma":"ACC","modelo":"SD","capacidade":"128GB","cor":"Preto","regiao":"BR","condicao":"NOVO","preco_lista":90.00,"custo_base":55.00,"estoque_minimo":5,"estoque_atual":6},
        # Similarly, wrap this product name in single quotes so the
        # embedded double quote does not prematurely end the literal.
        {"nome":'Monitor 27" 144Hz', "categoria":"Monitores","plataforma":"MON","modelo":"27G","capacidade":"144Hz","cor":"Preto","regiao":"BR","condicao":"NOVO","preco_lista":1490.00,"custo_base":1150.00,"estoque_minimo":1,"estoque_atual":1},
        {"nome":"Headset Gamer", "categoria":"Acessórios","plataforma":"ACC","modelo":"HS1","capacidade":"","cor":"Preto","regiao":"BR","condicao":"NOVO","preco_lista":190.00,"custo_base":110.00,"estoque_minimo":2,"estoque_atual":2}
    ]

    def gen_sku(p, seq):
        base = f"{p['plataforma']}-{p['modelo']}-{p['capacidade']}-{p['cor']}-{p['regiao']}-{p['condicao']}"
        suf = str(seq).zfill(5)
        return f"{base}-{suf}"

    prod_ids = []
    for i,p in enumerate(prods, start=1):
        sku = gen_sku(p, i)
        now = datetime.datetime.now().isoformat(timespec='seconds')
        pid = insert(conn, "products", {
            "sku": sku, "nome": p["nome"], "categoria": p["categoria"],
            "plataforma": p["plataforma"], "modelo": p["modelo"], "capacidade": p["capacidade"],
            "cor": p["cor"], "regiao": p["regiao"], "condicao": p["condicao"],
            "preco_lista": p["preco_lista"], "custo_base": p["custo_base"],
            "estoque_minimo": p["estoque_minimo"], "estoque_atual": p["estoque_atual"],
            "created_at": now, "updated_at": now
        })
        prod_ids.append(pid)

    # Compras (algumas para registrar movimentos de entrada)
    for i in range(5):
        data = date_days_ago(25 - i*5)
        supplier_id = random.choice(sup_ids)
        pid = insert(conn, "purchases", {"data": data, "supplier_id": supplier_id, "frete": random.uniform(0,50), "outras_despesas": 0, "obs":"seed"})
        # um item aleatório
        pr = random.choice(prod_ids)
        qtde = random.randint(1,3)
        custo = round(random.uniform(50, 500), 2)
        insert(conn, "purchase_items", {"purchase_id": pid, "product_id": pr, "qtde": qtde, "custo_unit": custo})
        # Mov IN
        conn.execute("INSERT INTO stock_moves(data, product_id, tipo, qtde, origem, ref_id, usuario_id) VALUES(?,?,?,?,?,?,?)",
                     (data, pr, "IN", qtde, "compra", pid, gerente_id))
        # Atualiza estoque_atual (simples)
        conn.execute("UPDATE products SET estoque_atual = COALESCE(estoque_atual,0)+? WHERE id=?", (qtde, pr))

    # Vendas nos últimos 30 dias
    sale_ids = []
    for d in range(30):
        dia = date_days_ago(29-d)
        # probabilisticamente cria uma venda
        if random.random() < 0.7:
            cust = random.choice(cli_ids)
            vend = random.choice([vendedor_id, gerente_id])
            sid = insert(conn, "sales", {"data": dia, "customer_id": cust, "vendedor_id": vend,
                                         "desconto_valor_total": 0, "desconto_pct_total": 0, "motivo_desconto": "", "pin_aprovacao": None,
                                         "cidade_snapshot": conn.execute("SELECT cidade FROM customers WHERE id=?", (cust,)).fetchone()["cidade"]})
            sale_ids.append(sid)
            # 1 item
            pr = random.choice(prod_ids)
            cur = conn.execute("SELECT preco_lista, custo_base, estoque_atual FROM products WHERE id=?", (pr,)).fetchone()
            if cur["estoque_atual"] <= 0:
                continue
            qtde = 1
            preco_lista = cur["preco_lista"] or 0
            preco_unit = round(preco_lista * random.uniform(0.9,1.05),2)
            custo_snap = cur["custo_base"] or 0
            insert(conn, "sale_items", {"sale_id": sid, "product_id": pr, "qtde": qtde,
                                        "preco_lista_snap": preco_lista, "preco_unit": preco_unit,
                                        "desconto_valor": 0, "desconto_pct": 0, "custo_snap": custo_snap})
            # Mov OUT
            conn.execute("INSERT INTO stock_moves(data, product_id, tipo, qtde, origem, ref_id, usuario_id) VALUES(?,?,?,?,?,?,?)",
                         (dia, pr, "OUT", qtde, "venda", sid, vend))
            conn.execute("UPDATE products SET estoque_atual = estoque_atual - ? WHERE id=?", (qtde, pr))

    # Criar 1 RMA de retorno e 1 de troca se houver vendas
    if sale_ids:
        # Retorno total de um item
        sid = random.choice(sale_ids)
        si = conn.execute("SELECT id, product_id, qtde FROM sale_items WHERE sale_id=? LIMIT 1", (sid,)).fetchone()
        if si:
            now = datetime.datetime.now().isoformat(timespec='seconds')
            codigo = "RMA-" + now.replace(":","").replace("-","").replace("T","")
            rmaid = insert(conn, "rmas", {"codigo_rma": codigo, "sale_id": sid, "tipo":"RETORNO", "motivo":"Defeito", "forma_compensacao":"reembolso",
                                          "valor_reembolso": 0, "status":"APROVADO", "usuario_id": gerente_id, "created_at": now, "updated_at": now})
            insert(conn, "rma_items", {"rma_id": rmaid, "sale_item_id": si["id"], "product_id": si["product_id"], "qtde": si["qtde"]})
            # Mov IN
            conn.execute("INSERT INTO stock_moves(data, product_id, tipo, qtde, origem, ref_id, usuario_id) VALUES(?,?,?,?,?,?,?)",
                         (now, si["product_id"], "IN", si["qtde"], "rma_retorno", rmaid, gerente_id))
            conn.execute("UPDATE products SET estoque_atual = estoque_atual + ? WHERE id=?", (si["qtde"], si["product_id"]))

        # Troca: devolve 1 e sai outro
        sid2 = random.choice(sale_ids)
        si2 = conn.execute("SELECT id, product_id, qtde FROM sale_items WHERE sale_id=? LIMIT 1", (sid2,)).fetchone()
        alt_prod = random.choice(prod_ids)
        if si2 and alt_prod:
            now = datetime.datetime.now().isoformat(timespec='seconds')
            codigo = "RMA-" + now.replace(":","").replace("-","").replace("T","") + "-T"
            rmaid = insert(conn, "rmas", {"codigo_rma": codigo, "sale_id": sid2, "tipo":"TROCA", "motivo":"Cliente quis trocar", "forma_compensacao":"troca",
                                          "valor_reembolso": 0, "status":"APROVADO", "usuario_id": gerente_id, "created_at": now, "updated_at": now})
            insert(conn, "rma_items", {"rma_id": rmaid, "sale_item_id": si2["id"], "product_id": si2["product_id"], "qtde": 1})
            # Entrada do devolvido
            conn.execute("INSERT INTO stock_moves(data, product_id, tipo, qtde, origem, ref_id, usuario_id) VALUES(?,?,?,?,?,?,?)",
                         (now, si2["product_id"], "IN", 1, "rma_troca", rmaid, gerente_id))
            conn.execute("UPDATE products SET estoque_atual = estoque_atual + 1 WHERE id=?", (si2["product_id"],))
            # Saída do novo
            stk = conn.execute("SELECT estoque_atual FROM products WHERE id=?", (alt_prod,)).fetchone()["estoque_atual"]
            if stk > 0:
                conn.execute("INSERT INTO stock_moves(data, product_id, tipo, qtde, origem, ref_id, usuario_id) VALUES(?,?,?,?,?,?,?)",
                             (now, alt_prod, "OUT", 1, "rma_troca", rmaid, gerente_id))
                conn.execute("UPDATE products SET estoque_atual = estoque_atual - 1 WHERE id=?", (alt_prod,))

    # Ajustes (2 exemplos)
    for _ in range(2):
        pr = random.choice(prod_ids)
        cur = conn.execute("SELECT estoque_atual FROM products WHERE id=?", (pr,)).fetchone()
        antes = cur["estoque_atual"]
        delta = random.choice([1, -1])
        depois = max(0, antes + delta)
        now = datetime.datetime.now().isoformat(timespec='seconds')
        aid = insert(conn, "stock_adjustments", {"product_id": pr, "ajuste_tipo":"OUTRO",
                     "qtde_delta": delta, "qtde_antes": antes, "qtde_depois": depois,
                     "motivo":"seed", "anexo_path": None, "usuario_id": gerente_id, "created_at": now})
        # Movimento
        tipo = "IN" if delta>0 else "OUT"
        conn.execute("INSERT INTO stock_moves(data, product_id, tipo, qtde, origem, ref_id, usuario_id) VALUES(?,?,?,?,?,?,?)",
                     (now, pr, tipo, abs(delta), "ajuste", aid, gerente_id))
        conn.execute("UPDATE products SET estoque_atual=? WHERE id=?", (depois, pr))

    conn.commit()
    conn.close()
    print("Seed criado.")
    
if __name__ == "__main__":
    main()
