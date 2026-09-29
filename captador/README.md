# Captador: endereço → proprietário → contato

Ferramenta para corretores: digita CEP + número e recebe quem mora e quem é o dono do imóvel,
com telefones/WhatsApp. Segue o fluxograma em `../fluxo.html`.

## Rodar no computador
```bash
pip install -r requirements.txt
python -m uvicorn app.main:app --reload
```
Abra http://localhost:8000 e entre como corretora ou gestora (modo demonstração).
Teste automático de tudo (segurança, fluxo, limites): `python test_fluxo.py`

## Colocar online (Render)
O arquivo `render.yaml` na raiz do repositório já descreve o serviço.
1. Suba o repositório para o GitHub.
2. No Render: **New → Blueprint** → escolha o repositório → **Apply**.
3. Em ~3 minutos o link `https://captador-xxxx.onrender.com` fica no ar.

Observações do plano gratuito: o serviço "dorme" após 15 min sem uso (o 1º acesso demora ~50 s)
e o banco SQLite é recriado a cada reinício — na demonstração isso é bom, porque volta sempre
com os dados de exemplo. Para uso real: disco persistente do Render ou Postgres.

## Usuários e permissões
| Papel | Pode |
|---|---|
| corretor | buscar dono, confirmar dono pela matrícula, registrar contato |
| gestor | tudo do corretor + painel da equipe, fila de matrículas, bloquear contatos |

Em produção (`DEMO_MODE=0`) crie usuários com:
```bash
python -m app.criar_usuario email@beam.com.br "Nome Sobrenome" gestor
```

## Fluxo
| Passo | O que acontece | Fonte | Custo |
|---|---|---|---|
| 1-2 | CEP + nº → endereço padronizado | ViaCEP | grátis |
| 3 | Já está na base própria? → responde na hora | banco local | zero |
| 4 | Quem mora no endereço (nome + CPF) | bureau licenciado | ~R$ 0,30–3 |
| 5 | Telefones/WhatsApp do CPF (1x por CPF, depois cache) | bureau licenciado | ~R$ 0,30–3 |
| 6 | Remove quem pediu opt-out + grava log LGPD | banco local | zero |
| 7 | **Lead quente:** botão "Confirmar dono" puxa a matrícula e mostra o dono real | RI Digital via Infosimples | ~R$ 20–90 |
| 8 | Tudo salvo na base própria → card do corretor | banco local | zero |
| 9-10 | Corretor registra a abordagem; "não contatar" vira bloqueio | banco local | zero |

Endereço sem ninguém no bureau → vai para a **Fila de matrículas** (preenchimento manual, com leitura do PDF).

## Modo demonstração × produção
Por padrão tudo roda **simulado** (pessoas e telefones fictícios). Para produção, defina as variáveis:

```bash
# Bureau (contratar: BigDataCorp, Assertiva, Procob, Directd...)
BUREAU_MODO=http
BUREAU_URL=https://api.do-bureau.com.br
BUREAU_TOKEN=...
BUREAU_CUSTO_ENDERECO=1.00
BUREAU_CUSTO_CONTATOS=1.00

# Matrícula automática (conta RI Digital da empresa + conta Infosimples)
MATRICULA_MODO=infosimples
INFOSIMPLES_TOKEN=...
RIDIGITAL_EMAIL=...
RIDIGITAL_SENHA=...
MATRICULA_CUSTO=45.00
```

Os adaptadores reais estão prontos em `app/providers/bureau.py` e `app/providers/matricula.py`,
mas **precisam ser conferidos com a documentação de cada contrato** (rotas e nomes de campos
estão marcados com `TODO`).

## LGPD e segurança (já embutido)
- Login obrigatório; o log de consultas usa o usuário da sessão (não dá para falsificar)
- Limite diário de consultas por corretor (`LIMITE_CONSULTAS_DIA`) contra abuso e raspagem
- Finalidade obrigatória e log de toda consulta (quem, quando, qual imóvel, custo)
- Opt-out por CPF/telefone respeitado em todas as consultas
- CPF sempre mascarado para o corretor
- Aviso de transparência para a abordagem
- Fontes: bureau licenciado + matrícula (pública, Lei 6.015/73). **Não usar bases vazadas/compradas avulsas.**

## Próximos passos
- Lote de endereços (CSV) e integração com CRM
- Monitor Registral (RI Digital) → alerta de lead quando a matrícula muda
- Hospedar (Render/Railway) + trocar SQLite por Postgres
