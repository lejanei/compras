import pandas as pd
from sqlalchemy import create_engine, text
from utils import agora, formatar_pedido_id, formatar_produto_id, get_config

DB_URL = str(get_config("DB_URL", ""))
if not DB_URL:
    raise RuntimeError("DB_URL não configurado. Configure no .env local ou no Secrets do Streamlit Cloud.")

engine = create_engine(DB_URL, pool_pre_ping=True, pool_recycle=280, future=True)


def executar(sql, params=None):
    with engine.begin() as conn:
        conn.execute(text(sql), params or {})


def buscar_um(sql, params=None):
    with engine.begin() as conn:
        row = conn.execute(text(sql), params or {}).mappings().first()
        return dict(row) if row else None


def carregar_df(sql, params=None):
    with engine.begin() as conn:
        return pd.read_sql_query(text(sql), conn, params=params or {})


def criar_tabelas():
    executar("""CREATE TABLE IF NOT EXISTS usuarios (
        id INT AUTO_INCREMENT PRIMARY KEY,
        usuario VARCHAR(100) UNIQUE NOT NULL,
        senha VARCHAR(255) NOT NULL,
        nome VARCHAR(150) NOT NULL,
        perfil VARCHAR(50) NOT NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")

    executar("""CREATE TABLE IF NOT EXISTS fornecedores (
        id INT AUTO_INCREMENT PRIMARY KEY,
        nome VARCHAR(255) NOT NULL,
        contato VARCHAR(255),
        telefone VARCHAR(100)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")

    executar("""CREATE TABLE IF NOT EXISTS produtos (
        id INT AUTO_INCREMENT PRIMARY KEY,
        codigo VARCHAR(50),
        nome VARCHAR(255) NOT NULL,
        unidade VARCHAR(50)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")

    executar("""CREATE TABLE IF NOT EXISTS pedidos (
        id INT AUTO_INCREMENT PRIMARY KEY,
        numero VARCHAR(50),
        data DATE NOT NULL,
        fornecedor_id INT NULL,
        status VARCHAR(50),
        prioridade VARCHAR(50) DEFAULT 'Normal',
        observacao LONGTEXT,
        criado_por VARCHAR(100),
        aprovado_por VARCHAR(100),
        data_aprovacao VARCHAR(50),
        comprado_por VARCHAR(100),
        data_compra VARCHAR(50),
        recebido_por VARCHAR(100),
        data_recebimento VARCHAR(50),
        cancelado_por VARCHAR(100),
        data_cancelamento VARCHAR(50),
        INDEX idx_pedidos_fornecedor (fornecedor_id),
        CONSTRAINT fk_pedidos_fornecedor FOREIGN KEY (fornecedor_id) REFERENCES fornecedores(id) ON DELETE SET NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")

    executar("""CREATE TABLE IF NOT EXISTS pedido_itens (
        id INT AUTO_INCREMENT PRIMARY KEY,
        pedido_id INT NOT NULL,
        produto_id INT NOT NULL,
        quantidade DECIMAL(15,3) NOT NULL,
        valor_unitario DECIMAL(15,2) NOT NULL,
        observacao_item TEXT,
        INDEX idx_itens_pedido (pedido_id),
        INDEX idx_itens_produto (produto_id),
        CONSTRAINT fk_itens_pedido FOREIGN KEY (pedido_id) REFERENCES pedidos(id) ON DELETE CASCADE,
        CONSTRAINT fk_itens_produto FOREIGN KEY (produto_id) REFERENCES produtos(id) ON DELETE RESTRICT
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")

    executar("""CREATE TABLE IF NOT EXISTS pedido_anexos (
        id INT AUTO_INCREMENT PRIMARY KEY,
        pedido_id INT NOT NULL,
        nome_arquivo VARCHAR(255) NOT NULL,
        caminho VARCHAR(500) NOT NULL,
        enviado_por VARCHAR(100),
        data_envio VARCHAR(50),
        INDEX idx_anexos_pedido (pedido_id),
        CONSTRAINT fk_anexos_pedido FOREIGN KEY (pedido_id) REFERENCES pedidos(id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")

    executar("""CREATE TABLE IF NOT EXISTS notificacoes (
        id INT AUTO_INCREMENT PRIMARY KEY,
        data VARCHAR(50) NOT NULL,
        tipo VARCHAR(100) NOT NULL,
        pedido_id INT,
        numero_pedido VARCHAR(50),
        mensagem LONGTEXT NOT NULL,
        destino TEXT,
        status_envio VARCHAR(100),
        usuario VARCHAR(100),
        lida TINYINT DEFAULT 0,
        INDEX idx_notificacao_pedido (pedido_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4""")

    inserir_usuarios_padrao()
    migrar_banco()


def coluna_existe(tabela, coluna):
    df = carregar_df("""SELECT COUNT(*) AS total FROM information_schema.columns
        WHERE table_schema = DATABASE() AND table_name = :tabela AND column_name = :coluna""", {"tabela": tabela, "coluna": coluna})
    return int(df["total"].iloc[0]) > 0


def adicionar_coluna_se_nao_existir(tabela, coluna, tipo):
    if not coluna_existe(tabela, coluna):
        executar(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {tipo}")


def migrar_banco():
    for coluna, tipo in [("numero","VARCHAR(50)"),("fornecedor_id","INT NULL"),("status","VARCHAR(50)"),("prioridade","VARCHAR(50) DEFAULT 'Normal'"),("observacao","LONGTEXT"),("criado_por","VARCHAR(100)"),("aprovado_por","VARCHAR(100)"),("data_aprovacao","VARCHAR(50)"),("comprado_por","VARCHAR(100)"),("data_compra","VARCHAR(50)"),("recebido_por","VARCHAR(100)"),("data_recebimento","VARCHAR(50)"),("cancelado_por","VARCHAR(100)"),("data_cancelamento","VARCHAR(50)")]:
        adicionar_coluna_se_nao_existir("pedidos", coluna, tipo)
    adicionar_coluna_se_nao_existir("produtos", "codigo", "VARCHAR(50)")
    adicionar_coluna_se_nao_existir("produtos", "unidade", "VARCHAR(50)")

    for _, row in carregar_df("SELECT id FROM produtos WHERE codigo IS NULL OR codigo = ''").iterrows():
        executar("UPDATE produtos SET codigo=:codigo WHERE id=:id", {"codigo": formatar_produto_id(row["id"]), "id": int(row["id"])})
    for _, row in carregar_df("SELECT id FROM pedidos WHERE numero IS NULL OR numero = ''").iterrows():
        executar("UPDATE pedidos SET numero=:numero WHERE id=:id", {"numero": formatar_pedido_id(row["id"]), "id": int(row["id"])})
    executar("UPDATE pedidos SET prioridade='Normal' WHERE prioridade IS NULL OR prioridade=''")


def inserir_usuarios_padrao():
    executar("""INSERT IGNORE INTO usuarios (usuario, senha, nome, perfil) VALUES
        ('admin','admin123','Administrador','admin'),
        ('aprovador','ap123','Aprovador','aprovador'),
        ('operador','op123','Operador','operador')""")


def login(usuario, senha):
    row = buscar_um("SELECT usuario,nome,perfil FROM usuarios WHERE usuario=:u AND senha=:s", {"u": usuario, "s": senha})
    return (row["usuario"], row["nome"], row["perfil"]) if row else None


def carregar_produtos():
    df = carregar_df("SELECT * FROM produtos ORDER BY nome")
    if not df.empty:
        df["codigo"] = df.apply(lambda r: r["codigo"] if r["codigo"] else formatar_produto_id(r["id"]), axis=1)
    return df


def inserir_produto(nome, unidade):
    with engine.begin() as conn:
        res = conn.execute(text("INSERT INTO produtos (nome,unidade) VALUES (:nome,:unidade)"), {"nome": nome, "unidade": unidade})
        pid = res.lastrowid
        conn.execute(text("UPDATE produtos SET codigo=:codigo WHERE id=:id"), {"codigo": formatar_produto_id(pid), "id": pid})


def atualizar_produto(id_produto, nome, unidade):
    executar("UPDATE produtos SET nome=:nome, unidade=:unidade WHERE id=:id", {"nome": nome, "unidade": unidade, "id": id_produto})


def excluir_produto(id_produto):
    executar("DELETE FROM produtos WHERE id=:id", {"id": id_produto})


def carregar_fornecedores():
    return carregar_df("SELECT * FROM fornecedores ORDER BY nome")


def inserir_fornecedor(nome, contato, telefone):
    executar("INSERT INTO fornecedores (nome,contato,telefone) VALUES (:nome,:contato,:telefone)", {"nome": nome, "contato": contato, "telefone": telefone})


def atualizar_fornecedor(id_fornecedor, nome, contato, telefone):
    executar("UPDATE fornecedores SET nome=:nome, contato=:contato, telefone=:telefone WHERE id=:id", {"nome": nome, "contato": contato, "telefone": telefone, "id": id_fornecedor})


def excluir_fornecedor(id_fornecedor):
    executar("DELETE FROM fornecedores WHERE id=:id", {"id": id_fornecedor})


def carregar_pedidos():
    df = carregar_df("""SELECT p.id,p.numero,p.data,f.nome AS fornecedor,p.status,p.prioridade,
        COALESCE(SUM(i.quantidade*i.valor_unitario),0) AS valor_total,
        COUNT(i.id) AS quantidade_itens,p.observacao,p.criado_por,p.aprovado_por,p.data_aprovacao,
        p.comprado_por,p.data_compra,p.recebido_por,p.data_recebimento,p.cancelado_por,p.data_cancelamento
        FROM pedidos p
        LEFT JOIN fornecedores f ON f.id=p.fornecedor_id
        LEFT JOIN pedido_itens i ON i.pedido_id=p.id
        GROUP BY p.id,p.numero,p.data,f.nome,p.status,p.prioridade,p.observacao,p.criado_por,p.aprovado_por,p.data_aprovacao,p.comprado_por,p.data_compra,p.recebido_por,p.data_recebimento,p.cancelado_por,p.data_cancelamento
        ORDER BY p.id DESC""")
    if not df.empty:
        df["numero"] = df.apply(lambda r: r["numero"] if r["numero"] else formatar_pedido_id(r["id"]), axis=1)
        df["prioridade"] = df["prioridade"].fillna("Normal")
    return df


def carregar_itens_pedido(id_pedido):
    return carregar_df("""SELECT i.id,i.pedido_id,i.produto_id,pr.codigo,pr.nome AS produto,pr.unidade,
        i.quantidade,i.valor_unitario,i.quantidade*i.valor_unitario AS valor_total,i.observacao_item
        FROM pedido_itens i LEFT JOIN produtos pr ON pr.id=i.produto_id
        WHERE i.pedido_id=:id ORDER BY i.id""", {"id": id_pedido})


def buscar_pedido(id_pedido):
    return buscar_um("SELECT * FROM pedidos WHERE id=:id", {"id": id_pedido})


def criar_pedido(data_pedido, fornecedor_id, prioridade, itens, observacao, usuario):
    log = f"[{agora()}] Pedido criado por {usuario}."
    obs_final = f"{observacao}\n\n{log}" if observacao else log
    with engine.begin() as conn:
        res = conn.execute(text("""INSERT INTO pedidos (data,fornecedor_id,status,prioridade,observacao,criado_por)
            VALUES (:data,:fornecedor_id,'Aberto',:prioridade,:observacao,:usuario)"""), {"data": str(data_pedido), "fornecedor_id": fornecedor_id, "prioridade": prioridade, "observacao": obs_final, "usuario": usuario})
        pedido_id = res.lastrowid
        numero = formatar_pedido_id(pedido_id)
        conn.execute(text("UPDATE pedidos SET numero=:numero WHERE id=:id"), {"numero": numero, "id": pedido_id})
        for item in itens:
            conn.execute(text("""INSERT INTO pedido_itens (pedido_id,produto_id,quantidade,valor_unitario,observacao_item)
                VALUES (:pedido_id,:produto_id,:quantidade,:valor_unitario,:obs)"""), {"pedido_id": pedido_id, "produto_id": item["produto_id"], "quantidade": item["quantidade"], "valor_unitario": item["valor_unitario"], "obs": item.get("observacao_item", "")})
    return pedido_id, numero


def atualizar_pedido(id_pedido, data_pedido, fornecedor_id, prioridade, itens, observacao, usuario):
    log = f"[{agora()}] Pedido editado por {usuario}."
    obs_final = f"{observacao}\n\n{log}"
    with engine.begin() as conn:
        conn.execute(text("""UPDATE pedidos SET data=:data, fornecedor_id=:fornecedor_id, prioridade=:prioridade, observacao=:observacao WHERE id=:id"""), {"data": str(data_pedido), "fornecedor_id": fornecedor_id, "prioridade": prioridade, "observacao": obs_final, "id": id_pedido})
        conn.execute(text("DELETE FROM pedido_itens WHERE pedido_id=:id"), {"id": id_pedido})
        for item in itens:
            conn.execute(text("""INSERT INTO pedido_itens (pedido_id,produto_id,quantidade,valor_unitario,observacao_item)
                VALUES (:pedido_id,:produto_id,:quantidade,:valor_unitario,:obs)"""), {"pedido_id": id_pedido, "produto_id": item["produto_id"], "quantidade": item["quantidade"], "valor_unitario": item["valor_unitario"], "obs": item.get("observacao_item", "")})


def alterar_status(id_pedido, novo_status, usuario):
    pedido = buscar_pedido(id_pedido)
    if not pedido:
        return
    obs = (pedido.get("observacao") or "") + f"\n\n[{agora()}] Status alterado de {pedido.get('status')} para {novo_status} por {usuario}."
    campos = {"Aprovado": ("aprovado_por", "data_aprovacao"), "Comprado": ("comprado_por", "data_compra"), "Recebido": ("recebido_por", "data_recebimento"), "Cancelado": ("cancelado_por", "data_cancelamento")}
    if novo_status in campos:
        usuario_col, data_col = campos[novo_status]
        executar(f"UPDATE pedidos SET status=:status, observacao=:obs, {usuario_col}=:usuario, {data_col}=:data WHERE id=:id", {"status": novo_status, "obs": obs, "usuario": usuario, "data": agora(), "id": id_pedido})
    else:
        executar("UPDATE pedidos SET status=:status, observacao=:obs WHERE id=:id", {"status": novo_status, "obs": obs, "id": id_pedido})


def excluir_pedido(id_pedido):
    executar("DELETE FROM pedidos WHERE id=:id", {"id": id_pedido})


def inserir_anexo(pedido_id, nome_arquivo, caminho, usuario):
    executar("INSERT INTO pedido_anexos (pedido_id,nome_arquivo,caminho,enviado_por,data_envio) VALUES (:pedido_id,:nome,:caminho,:usuario,:data)", {"pedido_id": pedido_id, "nome": nome_arquivo, "caminho": caminho, "usuario": usuario, "data": agora()})


def carregar_anexos_pedido(pedido_id):
    return carregar_df("SELECT * FROM pedido_anexos WHERE pedido_id=:id ORDER BY id DESC", {"id": pedido_id})


def registrar_notificacao(tipo, pedido_id, numero_pedido, mensagem, status_envio, usuario):
    executar("""INSERT INTO notificacoes (data,tipo,pedido_id,numero_pedido,mensagem,destino,status_envio,usuario,lida)
        VALUES (:data,:tipo,:pedido_id,:numero,:mensagem,'WhatsApp',:status,:usuario,0)""", {"data": agora(), "tipo": tipo, "pedido_id": pedido_id, "numero": numero_pedido, "mensagem": mensagem, "status": status_envio, "usuario": usuario})


def carregar_notificacoes():
    return carregar_df("SELECT * FROM notificacoes ORDER BY id DESC")


def marcar_notificacoes_lidas():
    executar("UPDATE notificacoes SET lida=1")
