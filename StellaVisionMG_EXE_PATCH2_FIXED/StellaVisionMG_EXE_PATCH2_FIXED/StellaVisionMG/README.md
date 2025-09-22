# ERP Machado Games (Gestão Visual) — com RMA & Ajustes

## Como executar (Windows em 4 passos)
1. **Baixe e extraia** esta pasta (`erp_machadogames/`).
2. **Clique 2x** em `start_erp.bat` (ele cria a venv, instala deps, cria e faz seed do banco se precisar).
3. Quando aparecer **Running on http://127.0.0.1:5000**, abra o link no navegador.
4. Faça seus testes. Para parar, feche a janela do terminal.

> Se o PowerShell bloquear scripts, use o `start_erp.bat`. O `start_erp.ps1` é apenas opcional.

## Login/Permissões
- Não há tela de login ainda (MVP). Por padrão o `current_user_id` é 1 (Admin) definido no `app.py`.
- Para validar PIN de desconto acima do limite, use o PIN do usuário **Gerente** gerado no seed (veja `seed.py`).

## Páginas
- `/` ou `/dashboard` — KPIs + gráficos filtráveis (período/categoria/cidade/vendedor, toggle incluir RMA).
- `/relatorios` — as mesmas métricas + extras (RMA, Ajustes, Reposição, Vendedor).
- `/produtos` — cadastro com **Fornecedor inline**, **SKU automático** editável e botão **Regenerar SKU**.
- `/compras` — lançamentos com despesas opcionais; atualiza estoque e custo_base.
- `/vendas` — itens com política de preço/desconto; exige PIN de gerente acima do limite; saída de estoque.
- `/rmas` — devolução/troca vinculada à venda original; movimenta estoque; estados; janela de RMA.
- `/ajustes` — ajustes auditáveis (motivo obrigatório, bloqueio de estoque negativo, anexo opcional).
- `/config` — limite de desconto, janela de RMA, X dias sem venda, tema.

## Observações
- Locale BR (datas dd/mm/aaaa e moeda R$) via funções utilitárias no frontend/backend.
- Gráfico "Vendas por dia" preenche **zerados** para dias sem venda.
- "Participação por categoria" inclui **Sem categoria**.
- "Margem por categoria (30d)" ignora custos nulos.
- "Sem dados ainda" aparece com dicas do que falta (ex.: cadastrar custo_base, registrar compra/venda).

## Exportação
- CSV simples disponível em algumas listas (ex.: ajustes, RMA, reposição). PDF opcional não incluso neste MVP.
