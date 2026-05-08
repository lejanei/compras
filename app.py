from datetime import date, datetime
from pathlib import Path
import pandas as pd
import streamlit as st
from database import *
from pdf_generator import gerar_pdf_pedido
from utils import emoji_prioridade, emoji_status, valor_moeda
from whatsapp import *

def tem_permissao_aprovar(): return st.session_state.perfil in ['admin','aprovador']
def tem_permissao_excluir(): return st.session_state.perfil=='admin'

def notificar(tipo,pedido_id,numero,msg,usuario,pdf=None,legenda=''):
    ok=enviar_whatsapp_texto(msg); okpdf=True
    if pdf: okpdf=enviar_whatsapp_pdf(pdf, legenda)
    registrar_notificacao(tipo,pedido_id,numero,msg,'Enviado' if ok and okpdf else 'Falhou/Parcial',usuario)

def tela_login():
    st.title('🔐 Login - Gerenciador de Compras'); c1,c2,c3=st.columns([1,1,1])
    with c2:
        u=st.text_input('Usuário'); s=st.text_input('Senha',type='password')
        if st.button('Entrar', use_container_width=True):
            user=login(u,s)
            if user:
                st.session_state.logado=True; st.session_state.usuario=user[0]; st.session_state.nome=user[1]; st.session_state.perfil=user[2]; st.rerun()
            else: st.error('Usuário ou senha inválidos.')
        st.info('admin/admin123 | aprovador/ap123 | operador/op123')

def tela_dashboard():
    st.subheader('📊 Dashboard'); pedidos=carregar_pedidos()
    if pedidos.empty: st.info('Nenhum pedido cadastrado.'); return
    a,b,c,d,e=st.columns(5); a.metric('Pedidos',len(pedidos)); b.metric('Abertos',len(pedidos[pedidos.status=='Aberto'])); c.metric('Aprovados',len(pedidos[pedidos.status=='Aprovado'])); d.metric('Urgentes',len(pedidos[pedidos.prioridade=='Urgente'])); e.metric('Valor Total',valor_moeda(pedidos.valor_total.sum()))
    df=pedidos.copy(); df['status']=df.status.apply(lambda x:f'{emoji_status(x)} {x}'); df['prioridade']=df.prioridade.apply(lambda x:f'{emoji_prioridade(x)} {x}'); df['valor_total']=df.valor_total.apply(valor_moeda); st.dataframe(df, use_container_width=True)

def tela_novo_pedido():
    st.subheader('📝 Novo Pedido de Compra'); produtos=carregar_produtos(); fornecedores=carregar_fornecedores()
    if produtos.empty: st.warning('Cadastre pelo menos um produto.'); return
    if fornecedores.empty: st.warning('Cadastre pelo menos um fornecedor.'); return
    with st.form('add_item'):
        st.markdown('### Adicionar produto ao pedido'); c1,c2,c3=st.columns([3,1,1])
        opts=[f'{r.codigo} - {r.nome} ({r.unidade or "UN"})' for r in produtos.itertuples()]
        with c1: escolhido=st.selectbox('Produto',opts)
        with c2: qtd=st.number_input('Quantidade',min_value=0.0,step=1.0)
        with c3: val=st.number_input('Valor unitário',min_value=0.0,step=1.0)
        obs_item=st.text_input('Observação do item')
        if st.form_submit_button('Adicionar Produto ao Pedido'):
            if qtd<=0: st.error('Quantidade precisa ser maior que zero.')
            else:
                r=produtos.iloc[opts.index(escolhido)]
                st.session_state.itens_novo_pedido.append({'produto_id':int(r.id),'codigo':r.codigo,'produto':r.nome,'unidade':r.unidade,'quantidade':float(qtd),'valor_unitario':float(val),'valor_total':float(qtd)*float(val),'observacao_item':obs_item})
                st.success('Produto adicionado.'); st.rerun()
    st.divider(); st.markdown('### Itens adicionados')
    if st.session_state.itens_novo_pedido:
        df=pd.DataFrame(st.session_state.itens_novo_pedido); ex=df.copy(); ex['valor_unitario']=ex.valor_unitario.apply(valor_moeda); ex['valor_total']=ex.valor_total.apply(valor_moeda); st.dataframe(ex[['codigo','produto','unidade','quantidade','valor_unitario','valor_total','observacao_item']], use_container_width=True)
        total=sum(i['valor_total'] for i in st.session_state.itens_novo_pedido); st.metric('Total do Pedido',valor_moeda(total))
        c1,c2=st.columns(2)
        with c1:
            if st.button('Limpar todos os itens'): st.session_state.itens_novo_pedido=[]; st.rerun()
        with c2:
            idx=st.number_input('Remover item nº',min_value=1,max_value=len(st.session_state.itens_novo_pedido),step=1)
            if st.button('Remover item selecionado'): st.session_state.itens_novo_pedido.pop(idx-1); st.rerun()
    else: st.info('Nenhum produto adicionado ainda.')
    st.divider()
    with st.form('finalizar'):
        st.markdown('### Dados do pedido'); data=st.date_input('Data do pedido',value=date.today()); fornecedor_nome=st.selectbox('Fornecedor',fornecedores.nome.tolist()); prioridade=st.selectbox('Prioridade',['Baixa','Normal','Alta','Urgente'],index=1); obs=st.text_area('Observação geral do pedido'); anexos=st.file_uploader('Anexos da compra',accept_multiple_files=True)
        if st.form_submit_button('Salvar Pedido de Compra'):
            if not st.session_state.itens_novo_pedido: st.error('Adicione pelo menos um produto ao pedido.')
            else:
                fornecedor_id=int(fornecedores[fornecedores.nome==fornecedor_nome].id.iloc[0]); pedido_id,numero=criar_pedido(data,fornecedor_id,prioridade,st.session_state.itens_novo_pedido,obs,st.session_state.usuario)
                adir=Path('anexos')/numero; adir.mkdir(parents=True,exist_ok=True)
                for arq in anexos:
                    dest=adir/arq.name; dest.write_bytes(arq.getbuffer()); inserir_anexo(pedido_id,arq.name,str(dest),st.session_state.usuario)
                total=sum(i['valor_total'] for i in st.session_state.itens_novo_pedido); pdf=gerar_pdf_pedido(pedido_id); msg=mensagem_pedido_criado(numero,pedido_id,st.session_state.usuario,fornecedor_nome,valor_moeda(total),prioridade); notificar('Pedido criado',pedido_id,numero,msg,st.session_state.usuario,pdf,f'📄 Ordem de Compra {numero}')
                st.session_state.itens_novo_pedido=[]; st.success(f'Pedido {numero} criado.'); st.rerun()

def tela_pedidos():
    st.subheader('📋 Pedidos'); pedidos=carregar_pedidos()
    if pedidos.empty: st.info('Nenhum pedido cadastrado.'); return
    sf=st.selectbox('Filtrar por status',['Todos','Aberto','Aprovado','Comprado','Recebido','Cancelado']); pf=st.selectbox('Filtrar por prioridade',['Todas','Baixa','Normal','Alta','Urgente'])
    df=pedidos.copy();
    if sf!='Todos': df=df[df.status==sf]
    if pf!='Todas': df=df[df.prioridade==pf]
    ex=df.copy(); ex['status']=ex.status.apply(lambda x:f'{emoji_status(x)} {x}'); ex['prioridade']=ex.prioridade.apply(lambda x:f'{emoji_prioridade(x)} {x}'); ex['valor_total']=ex.valor_total.apply(valor_moeda); st.dataframe(ex, use_container_width=True)
    st.divider(); opts=[f'{r.numero} | {r.data} | {r.fornecedor or "Sem fornecedor"} | {r.status} | {emoji_prioridade(r.prioridade)} {r.prioridade}' for r in pedidos.itertuples()]; esc=st.selectbox('Pedido',opts); pedido_id=int(pedidos.iloc[opts.index(esc)].id); pedido=buscar_pedido(pedido_id)
    st.markdown(f"### Pedido {pedido['numero']} - {emoji_status(pedido['status'])} {pedido['status']} - {emoji_prioridade(pedido['prioridade'])} {pedido['prioridade']}")
    pdf=gerar_pdf_pedido(pedido_id)
    if pdf and Path(pdf).exists():
        with open(pdf,'rb') as f: st.download_button('📄 Baixar Ordem de Compra PDF',f,file_name=Path(pdf).name,mime='application/pdf')
    itens=carregar_itens_pedido(pedido_id)
    if not itens.empty:
        it=itens.copy(); it['valor_unitario']=it.valor_unitario.apply(valor_moeda); it['valor_total']=it.valor_total.apply(valor_moeda); st.dataframe(it[['codigo','produto','unidade','quantidade','valor_unitario','valor_total','observacao_item']], use_container_width=True)
    st.markdown('### 📎 Anexos'); anexos=carregar_anexos_pedido(pedido_id)
    if anexos.empty: st.info('Nenhum anexo.')
    else:
        for a in anexos.itertuples():
            p=Path(a.caminho)
            if p.exists():
                with open(p,'rb') as f: st.download_button(f'Baixar {a.nome_arquivo}',f,file_name=a.nome_arquivo,key=f'anexo_{a.id}')
    novos=st.file_uploader('Adicionar anexo ao pedido',accept_multiple_files=True,key=f'up_{pedido_id}')
    if novos and st.button('Salvar anexos'):
        adir=Path('anexos')/pedido['numero']; adir.mkdir(parents=True,exist_ok=True)
        for arq in novos:
            dest=adir/arq.name; dest.write_bytes(arq.getbuffer()); inserir_anexo(pedido_id,arq.name,str(dest),st.session_state.usuario)
        st.success('Anexos salvos.'); st.rerun()
    st.divider(); st.subheader('✅ Aprovação / Status'); c1,c2,c3,c4=st.columns(4)
    def mudar(ns,leg):
        alterar_status(pedido_id,ns,st.session_state.usuario); pdf2=gerar_pdf_pedido(pedido_id); msg=mensagem_status_alterado(pedido['numero'],pedido_id,ns,st.session_state.usuario,pedido['prioridade']); notificar(f'Status {ns}',pedido_id,pedido['numero'],msg,st.session_state.usuario,pdf2,leg); st.success(f'Pedido marcado como {ns}.'); st.rerun()
    with c1:
        if tem_permissao_aprovar():
            if st.button('✅ Aprovar'): mudar('Aprovado',f"✅ Pedido {pedido['numero']} aprovado")
        else: st.info('Sem permissão para aprovar.')
    with c2:
        if st.button('🛒 Comprado'): mudar('Comprado',f"🛒 Pedido {pedido['numero']} comprado")
    with c3:
        if st.button('📦 Recebido'): mudar('Recebido',f"📦 Pedido {pedido['numero']} recebido")
    with c4:
        if st.button('🚫 Cancelado'): mudar('Cancelado',f"🚫 Pedido {pedido['numero']} cancelado")
    st.divider(); st.subheader('✏️ Editar Pedido'); produtos=carregar_produtos(); fornecedores=carregar_fornecedores()
    with st.form('editar'):
        try: data_atual=datetime.strptime(str(pedido['data']),'%Y-%m-%d').date()
        except Exception: data_atual=date.today()
        data=st.date_input('Data',value=data_atual); lista=fornecedores.nome.tolist(); fn=''
        if pedido['fornecedor_id']:
            m=fornecedores[fornecedores.id==pedido['fornecedor_id']]
            if not m.empty: fn=m.nome.iloc[0]
        fornecedor_nome=st.selectbox('Fornecedor',lista,index=lista.index(fn) if fn in lista else 0); prioridade=st.selectbox('Prioridade',['Baixa','Normal','Alta','Urgente'],index=['Baixa','Normal','Alta','Urgente'].index(pedido['prioridade'] or 'Normal')); obs=st.text_area('Observação / Log',value=pedido['observacao'] or '',height=220)
        edit=[]; pops=[f'{r.codigo} - {r.nome} ({r.unidade or "UN"})' for r in produtos.itertuples()]
        for idx,item in itens.iterrows():
            st.markdown(f'**Item {idx+1}**'); a,b,c=st.columns([3,1,1]); atual=f"{item['codigo']} - {item['produto']} ({item['unidade'] or 'UN'})"; pi=pops.index(atual) if atual in pops else 0
            with a: pl=st.selectbox(f'Produto item {idx+1}',pops,index=pi,key=f'p_{item.id}')
            with b: qtd=st.number_input(f'Quantidade item {idx+1}',min_value=0.0,step=1.0,value=float(item.quantidade),key=f'q_{item.id}')
            with c: val=st.number_input(f'Valor unitário item {idx+1}',min_value=0.0,step=1.0,value=float(item.valor_unitario),key=f'v_{item.id}')
            obsi=st.text_input(f'Observação item {idx+1}',value=item.observacao_item or '',key=f'o_{item.id}'); pr=produtos.iloc[pops.index(pl)]; edit.append({'produto_id':int(pr.id),'quantidade':float(qtd),'valor_unitario':float(val),'observacao_item':obsi})
        if st.checkbox('Adicionar mais um item neste pedido'):
            pl=st.selectbox('Novo produto',pops); qtd=st.number_input('Quantidade novo item',min_value=0.0,step=1.0); val=st.number_input('Valor unitário novo item',min_value=0.0,step=1.0); obsi=st.text_input('Observação novo item')
            if qtd>0: pr=produtos.iloc[pops.index(pl)]; edit.append({'produto_id':int(pr.id),'quantidade':float(qtd),'valor_unitario':float(val),'observacao_item':obsi})
        if st.form_submit_button('Salvar Alterações do Pedido'):
            fid=int(fornecedores[fornecedores.nome==fornecedor_nome].id.iloc[0]); valid=[i for i in edit if i['quantidade']>0]
            if not valid: st.error('O pedido precisa ter pelo menos um item.')
            else:
                atualizar_pedido(pedido_id,data,fid,prioridade,valid,obs,st.session_state.usuario); pdf2=gerar_pdf_pedido(pedido_id); msg=mensagem_pedido_editado(pedido['numero'],pedido_id,st.session_state.usuario,prioridade); notificar('Pedido editado',pedido_id,pedido['numero'],msg,st.session_state.usuario,pdf2,f"✏️ Pedido {pedido['numero']} editado"); st.success('Pedido atualizado.'); st.rerun()
    if tem_permissao_excluir():
        if st.checkbox('Confirmo que desejo excluir este pedido permanentemente.') and st.button('Excluir Pedido'):
            num=pedido['numero']; excluir_pedido(pedido_id); msg=mensagem_pedido_excluido(num,st.session_state.usuario); notificar('Pedido excluído',pedido_id,num,msg,st.session_state.usuario); st.success('Pedido excluído.'); st.rerun()

def tela_notificacoes():
    st.subheader('🔔 Painel de Notificações'); df=carregar_notificacoes()
    if df.empty: st.info('Nenhuma notificação registrada.'); return
    c1,c2=st.columns(2); c1.metric('Total',len(df)); c2.metric('Não lidas',len(df[df.lida==0]))
    if st.button('Marcar todas como lidas'): marcar_notificacoes_lidas(); st.rerun()
    st.dataframe(df, use_container_width=True)

def tela_produtos():
    st.subheader('📦 Produtos')
    with st.form('produto'):
        nome=st.text_input('Nome do Produto'); unidade=st.text_input('Unidade',placeholder='UN, KG, MT, CX...')
        if st.form_submit_button('Salvar Produto'):
            if nome.strip(): inserir_produto(nome,unidade); st.success('Produto cadastrado.'); st.rerun()
            else: st.error('Informe o nome do produto.')
    produtos=carregar_produtos(); st.dataframe(produtos, use_container_width=True)
    if not produtos.empty:
        st.subheader('✏️ Editar / Excluir Produto'); opts=[f'{r.codigo} - {r.nome}' for r in produtos.itertuples()]; esc=st.selectbox('Selecione o produto',opts); p=produtos.iloc[opts.index(esc)]
        with st.form('edit_prod'):
            n=st.text_input('Nome',value=p.nome); u=st.text_input('Unidade',value=p.unidade or '')
            if st.form_submit_button('Salvar Alterações'): atualizar_produto(int(p.id),n,u); st.success('Produto atualizado.'); st.rerun()
        if tem_permissao_excluir() and st.checkbox('Confirmo que desejo excluir este produto.'):
            if st.button('Excluir Produto'): excluir_produto(int(p.id)); st.success('Produto excluído.'); st.rerun()

def tela_fornecedores():
    st.subheader('🏢 Fornecedores')
    with st.form('forn'):
        nome=st.text_input('Nome'); contato=st.text_input('Contato'); telefone=st.text_input('Telefone')
        if st.form_submit_button('Salvar Fornecedor'):
            if nome.strip(): inserir_fornecedor(nome,contato,telefone); st.success('Fornecedor cadastrado.'); st.rerun()
            else: st.error('Informe o nome do fornecedor.')
    fornecedores=carregar_fornecedores(); st.dataframe(fornecedores, use_container_width=True)
    if not fornecedores.empty:
        st.subheader('✏️ Editar / Excluir Fornecedor'); opts=[f'{r.id} - {r.nome}' for r in fornecedores.itertuples()]; esc=st.selectbox('Selecione o fornecedor',opts); f=fornecedores.iloc[opts.index(esc)]
        with st.form('edit_forn'):
            n=st.text_input('Nome',value=f.nome); c=st.text_input('Contato',value=f.contato or ''); t=st.text_input('Telefone',value=f.telefone or '')
            if st.form_submit_button('Salvar Alterações'): atualizar_fornecedor(int(f.id),n,c,t); st.success('Fornecedor atualizado.'); st.rerun()
        if tem_permissao_excluir() and st.checkbox('Confirmo que desejo excluir este fornecedor.'):
            if st.button('Excluir Fornecedor'): excluir_fornecedor(int(f.id)); st.success('Fornecedor excluído.'); st.rerun()

def tela_configuracoes():
    st.subheader('⚙️ Configurações'); st.markdown('### Logo do PDF'); logo=st.file_uploader('Enviar logo PNG',type=['png'])
    if logo and st.button('Salvar logo'):
        Path('assets').mkdir(exist_ok=True); (Path('assets')/'logo.png').write_bytes(logo.getbuffer()); st.success('Logo salva.')
    st.markdown('### WhatsApp'); st.write('Status:', '✅ Configurado' if whatsapp_configurado() else '⚠️ Não configurado')

def main():
    criar_tabelas(); st.set_page_config(page_title='Gerenciador de Compras',layout='wide')
    if 'logado' not in st.session_state: st.session_state.logado=False
    if 'itens_novo_pedido' not in st.session_state: st.session_state.itens_novo_pedido=[]
    if not st.session_state.logado: tela_login(); st.stop()
    st.sidebar.success(f"Usuário: {st.session_state.nome}")
    st.sidebar.info(f"Perfil: {st.session_state.perfil}")

    if whatsapp_configurado():
        st.sidebar.success("WhatsApp configurado")
    else:
        st.sidebar.warning("WhatsApp não configurado")
    if st.sidebar.button('Sair'): st.session_state.clear(); st.rerun()
    st.title('🛒 Gerenciador de Compras')
    menu=st.sidebar.radio('Menu',['Dashboard','Novo Pedido','Pedidos','Notificações','Produtos','Fornecedores','Configurações'])
    {'Dashboard':tela_dashboard,'Novo Pedido':tela_novo_pedido,'Pedidos':tela_pedidos,'Notificações':tela_notificacoes,'Produtos':tela_produtos,'Fornecedores':tela_fornecedores,'Configurações':tela_configuracoes}[menu]()
if __name__=='__main__': main()
