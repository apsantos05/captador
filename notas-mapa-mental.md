# Notas para o mapa mental: modelo "Endereço → Proprietário" (Beam Broker)

> Arquivo atualizado ao longo da conversa. Estrutura hierárquica pronta para virar mapa mental.
> Última atualização: 2026-09-29

## Centro do mapa
**Ferramenta de captação: o corretor digita um endereço e recebe os dados do proprietário para contato**

---

## 1. Contexto
- Entrevista na Beam Broker: o desafio é descobrir ou desenvolver o modelo do buscacheckonn.com
- Referência: Busca Checkonn (A.S. Checkonn.com Inteligência de Dados Ltda, CNPJ 26.392.216/0001-33, Barueri/SP, desde 2016)
  - Data broker / bureau cadastral
  - Buscas: nome, CPF/CNPJ, endereço, placa, telefone, e-mail
  - Entrega: telefones/WhatsApp, CPF, empresas, parentes, "ciclo social", veículos
  - Segmentos: captação imobiliária, cobrança, antifraude, mailing PJ, higienização
  - Venda consultiva via WhatsApp; preço não público (provável modelo de créditos/pacotes + API)
  - Ponto fraco: risco de LGPD e reclamações de cobrança indevida (Reclame Aqui)
- Vaga do candidato: _a definir_
- O que a Beam faz: _a definir_

## 2. Problema / Proposta de valor
- O corretor vê um imóvel bom e tem só o endereço
- Não sabe quem é o dono nem como falar com ele
- Solução: endereço → dono → contato em segundos
- Valor: mais captações exclusivas, custo por captação menor

## 3. Como funciona (fluxo)
1. Endereço → padronização (Google Places / ViaCEP)
2. Endereço → imóvel (IPTU/SQL via prefeitura, ex. GeoSampa; matrícula via ONR/SAEC)
3. Matrícula → proprietário (nome + CPF; é pública por lei) + ônus/penhora/alienação
4. CPF → contatos (API de bureau licenciado: BigDataCorp, Assertiva, Serasa, Boa Vista, Procob, Directd)
5. Entrega → card para o corretor + "registrar contato" + CRM

## 4. Fontes de dados (só legais)
- Públicas: matrícula (cartório/ONR), IPTU (prefeituras)
- Automação: APIs de consulta pública (ex. InfoSimples)
- Contatos: bureaus licenciados, que respondem pela origem dos dados
- NÃO usar: bases vazadas ou "lotes" avulsos

### 4.1 Como obter a matrícula
- Base legal: Lei 6.015/73 (arts. 16 e 17), qualquer pessoa pode pedir certidão sem explicar o motivo
- Canal oficial online: ONR / SAEC (ridigital.org.br (RI Digital, antigo SAEC)), que cobre os cartórios do país
  - Visualização da matrícula: mais barata, só informativa (ideal para captação)
  - Certidão digital de inteiro teor: vale como documento, mais cara (emolumentos variam por estado)
  - Pesquisa de bens por CPF/CNPJ: caminho inverso (pessoa → imóveis)
- Para pedir, é preciso saber o CARTÓRIO (circunscrição do endereço) + o NÚMERO DA MATRÍCULA
- GARGALO: descobrir a matrícula só pelo endereço
  - Pedido de busca por endereço direto no cartório (pago, mais lento)
  - Cadastro da prefeitura (IPTU/SQL, GeoSampa em SP) para identificar o lote/imóvel
  - Matrícula de imóveis vizinhos/do condomínio (mesmo empreendimento → matrículas em sequência)
  - Bases/APIs de terceiros que já relacionam endereço ↔ matrícula
- Para escalar: automação/API (intermediários tipo InfoSimples) + cache interno do que já foi consultado
- Serviços úteis do RI Digital:
  - Visualização de Matrícula: instantânea, é a que o corretor usa
  - Certidão Digital: validade de 30 dias, para negociação
  - Pesquisa Nacional de Bens / Pesquisa Qualificada: CPF → imóveis
  - Monitor Registral: alerta quando a matrícula muda (venda, penhora, inventário) = GATILHO DE LEAD
  - Mapa do Registro de Imóveis: movimentações por região (inteligência de mercado)
  - Pagamento por créditos pré-comprados; valores = tabela de emolumentos de cada estado
### 4.2 Automação da matrícula
- SIM, dá para automatizar a parte "matrícula nº X → PDF → dono"
  - Infosimples: APIs "Registradores / Matrícula": Novo Pedido → Download (PDF) → Lista de pedidos
  - Parâmetros: login do RI Digital (e-mail/senha ou certificado digital A1) + UF + município + cartório + nº da matrícula + finalidade
  - Consome o saldo da conta RI Digital da Beam + custo por consulta da Infosimples
  - Oficial: ONR tem integração por API/webservice com cartórios (Certidão Automática); convênio direto para empresas = falar com o ONR
- NÃO automatizável ainda: endereço → nº da matrícula (continua sendo o gargalo)
  - Solução: base própria + busca no cartório/IPTU; com o tempo o gargalo diminui
- Não fazer: robô próprio raspando o RI Digital sem autorização (termos de uso, captcha, risco de bloqueio)
- Fluxo automatizado: operador informa cartório+matrícula → API pede → baixa PDF → sistema lê → dono → bureau → corretor
- Oportunidade: montar a PRÓPRIA base endereço ↔ matrícula ao longo do tempo = vantagem competitiva

### 4.3 Ideia avaliada: conta de água/luz → dados
- Estrutura do raciocínio está CERTA: [quem é] → [como contatar] → [corretor]
- Fonte errada no passo 1:
  - Titular da conta ≠ proprietário (inquilino, imobiliária, falecido, parente)
  - Concessionárias não oferecem API pública por endereço; dados do consumidor são sigilosos
  - Quem vende "base de energia/água" normalmente tem origem irregular → risco LGPD
- Correção: trocar por "busca por endereço" de bureau licenciado (pessoas vinculadas ao endereço)
  - Rápido e barato, mas entrega OCUPANTE, não necessariamente dono (~2/3 dos domicílios são próprios, estimativa)
  - Confirmar o dono pela matrícula quando o lead for bom
- Fluxo híbrido final:
  1. Endereço → bureau (pessoas no endereço) = candidato
  2. CPF → bureau (telefones)
  3. Validação do dono: matrícula (lead quente) ou pergunta na abordagem
  4. Corretor

## 5. Compliance / LGPD
- Base legal: legítimo interesse (art. 7º, IX) + teste de balanceamento
- Transparência na abordagem + opt-out + lista de bloqueio
- Log de toda consulta (quem, quando, finalidade) contra uso indevido
- DPO + RIPD
- WhatsApp: abordagem 1:1 humana, sem disparo em massa

## 6. Modelo de negócio
- A) Ferramenta interna (recomendado para começar)
  - Ganho: mais captação, custo menor
- B) SaaS para o mercado (fase 2)
  - Receita: créditos (~R$ 10 a 30 por consulta completa) ou planos mensais
  - Clientes: corretores autônomos, imobiliárias

## 7. Custos (estimativas a validar)
- Matrícula: ~R$ 20 a 90 cada
- Consulta no bureau: ~R$ 0,30 a 3
- Otimização: consultar o bureau primeiro (barato) e a matrícula só nos leads bons
- Infra + desenvolvimento do MVP

## 8. Métricas / Unit economics
- Hipótese: 1 em cada 20 consultas vira captação → ~R$ 1.000 por captação
- Venda de R$ 600 mil × 6% = R$ 36 mil de comissão
- KPIs: consultas → contatos → reuniões → captações → vendas

## 9. Concorrentes / referências
- Busca Checkonn, bureaus (Serasa, Boa Vista, Assertiva, BigDataCorp)
- _mapear proptechs de captação_

## 10. Riscos
- Jurídico (LGPD/ANPD) se a fonte for irregular
- Custo alto da matrícula
- Dados desatualizados (imóvel vendido, telefone antigo)
- Banimento no WhatsApp
- Rejeição do proprietário (abordagem fria)

## 11. Roadmap
- MVP interno → medir conversão → decidir sobre o SaaS

## 12. Software (MVP construído: pasta captador/)
- Stack: Python + FastAPI + SQLite + tela web simples
- Telas: Consulta | Fila de matrículas | Relatório
- Fluxo: CEP+nº → ViaCEP → base própria → (se novo) fila de matrícula → PDF da matrícula lido automaticamente → CPF → bureau → card do corretor
- Diferenciais embutidos:
  - Cache: cada consulta alimenta a base própria (fica mais barato com o tempo)
  - Bureau só é chamado 1x por CPF
  - LGPD: finalidade obrigatória, log, opt-out automático, CPF mascarado
  - Registro de abordagem → funil (consulta → contato → captação)
- Hoje com bureau SIMULADO; para produção: contratar bureau e plugar a API
- v2 (fluxo híbrido, 2026-09-29): bureau por endereço → contatos → botão "Confirmar dono" (matrícula automática)
  - Card mostra: dono confirmado / morador provável dono / morador que não é o dono (inquilino)
  - Modos: simulado (demo) ou produção (BUREAU_MODO=http, MATRICULA_MODO=infosimples)
  - Relatório: % respondido pela base própria (sem custo), custo total, captações por corretor
- Próximos: login, lote CSV, CRM, Monitor Registral, hospedagem

## 13. Decisões tomadas / pendentes
- [x] Objetivo: replicar o esquema "endereço → dados do proprietário" para os corretores
- [ ] Formato da entrega (apresentação / protótipo / ambos)
- [ ] Vaga (produto / comercial / tech)
