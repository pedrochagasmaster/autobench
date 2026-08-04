# Guia de presets e configuração manual do Autobench

Este documento explica como os presets do Autobench alteram a ponderação,
a conformidade de privacidade, a consistência entre dimensões e a distorção dos
resultados. Ele também apresenta os principais parâmetros que podem ser
configurados manualmente por YAML ou pela linha de comando.

O objetivo não é apenas indicar qual preset escolher, mas permitir que o
operador antecipe o comportamento da ferramenta e interprete corretamente os
artefatos produzidos.

## 1. Modelo mental: o que o Autobench otimiza

O Autobench calcula um multiplicador para cada participante do grupo de pares.
Um peso igual a `1.0` mantém o volume original; pesos menores ou maiores reduzem
ou aumentam a contribuição daquele participante no benchmark balanceado.

O otimizador tenta conciliar quatro objetivos que podem competir entre si:

1. **Privacidade:** limitar a concentração de cada participante nas categorias
   analisadas, conforme a regra aplicável ao número de pares.
2. **Baixa distorção:** manter os pesos próximos de `1.0` e, portanto, os
   resultados balanceados próximos dos valores brutos.
3. **Preservação de ranking:** evitar que a ponderação inverta a ordem original
   dos participantes por volume.
4. **Consistência:** reutilizar o mesmo conjunto de pesos em todas as dimensões,
   períodos e tabelas do relatório.

Não existe configuração universalmente melhor. Quanto menos liberdade o
otimizador tiver para mudar pesos, maior pode ser a dificuldade de atender aos
limites de privacidade. Quanto mais rígida for a privacidade, maior pode ser a
distorção ou a necessidade de usar pesos diferentes em dimensões problemáticas.

### 1.1 Regras de privacidade

A regra principal é selecionada automaticamente a partir da quantidade de
pares:

- quatro pares: regra `4/35`, somente quando `analysis.merchant_mode: true`;
- cinco pares: regra `5/25`;
- seis pares: regra `6/30`;
- sete a nove pares: regra `7/35`;
- dez ou mais pares: regra `10/40`.

O primeiro número representa o requisito de participantes da regra e o segundo
representa a concentração percentual principal. As regras com condições
adicionais também são verificadas após a solução do LP.

O preset não escolhe a regra. Ele determina quanto o otimizador pode alterar os
pesos e como reage quando não consegue satisfazer a regra em todas as
categorias.

### 1.2 Peso global, subconjunto e peso por dimensão

No modo global, o Autobench tenta inicialmente usar um único vetor de pesos em
todas as dimensões. Se a solução usar slack acima do limite configurado ou o
solver falhar, a ferramenta pode procurar o maior subconjunto viável de
dimensões.

Uma dimensão retirada do conjunto global não é necessariamente excluída do
relatório. Ela pode ser resolvida separadamente, com pesos próprios. Isso
melhora a viabilidade e a privacidade daquela dimensão, mas reduz a consistência
entre tabelas.

Somente `optimization.constraints.enforce_single_weight_set: true` proíbe de
forma explícita a reponderação por dimensão. Desabilitar apenas
`subset_search.enabled` não é uma garantia absoluta contra todos os fallbacks
de dimensão em caso de falha do solver.

### 1.3 O que significa slack

Slack é a parcela de violação que o modelo precisa admitir para encontrar uma
solução. No LP principal, `tolerance` influencia o custo atribuído a esse slack;
quando `lambda_penalty` não é informado, o custo-base é aproximadamente
`100 / tolerance`. Nos caminhos heurísticos, a tolerância também participa da
comparação entre a concentração observada e o limite da regra.

Portanto, `tolerance: 2.0` deve ser entendido como maior disposição para aceitar
slack do que `tolerance: 0.0`, e não como uma promessa isolada de que toda
violação final ficará exatamente limitada a dois pontos percentuais. A
conformidade final deve sempre ser confirmada nas validações do relatório.

## 2. Ordem de resolução da configuração

O Autobench combina configurações nesta ordem, da menor para a maior
prioridade:

1. defaults internos;
2. preset selecionado;
3. arquivo passado em `--config`;
4. opções informadas no CLI.

Assim, é possível usar um preset como base e sobrescrever somente os parâmetros
necessários:

```powershell
py benchmark.py share `
  --csv .\dados.csv `
  --entity "BANCO ALVO" `
  --metric txn_cnt `
  --dimensions canal produto `
  --preset compliance_strict `
  --config .\minha-config.yaml
```

Integrações que fornecem overrides materiais diretamente ao `ConfigManager`
devem declarar também a postura final. No CLI público atual, os principais
parâmetros numéricos do otimizador são ajustados por um arquivo YAML passado em
`--config` ou pelos campos avançados da TUI; `--compliance-posture` continua
disponível para declarar explicitamente a postura da execução.

## 3. Comparação rápida dos presets

| Preset | Prioridade | Postura | Pesos | Tolerância | Subset search | Consistência |
| --- | --- | --- | ---: | ---: | --- | --- |
| `balanced_default` | Exploração equilibrada explícita | `best_effort` | `0.01` a `10` | `2.0` | aleatória determinística, até 200 tentativas | global, com fallback |
| `compliance_strict` | Privacidade; padrão em todas as interfaces | `strict` | `0.01` a `10` | `0.0` | greedy, em qualquer slack | global, com fallback |
| `strategic_consistency` | Um único vetor de pesos | `best_effort` | `0.01` a `15` | `25.0` | desabilitada | global obrigatório |
| `research_exploratory` | Viabilidade em dados difíceis | `best_effort` | `0.005` a `20` | `5.0` | aleatória determinística, até 400 tentativas | global flexível |
| `low_distortion` | Resultado quase bruto | `accuracy_first` | `1.0` a `1.0001` | `10.0` | desabilitada | normalmente global |
| `minimal_distortion` | Acurácia acima da privacidade | `accuracy_first` | `0.001` a `50` | `100.0` | desabilitada | normalmente global |

“Aleatória determinística” significa que a ordem de exploração é embaralhada,
mas usa uma semente fixa. A mesma entrada e configuração continuam gerando o
mesmo resultado, o que é necessário para auditoria.

## 4. Preset `balanced_default`

### Intenção

É uma escolha exploratória explícita para equilibrar privacidade, baixa
distorção e consistência entre dimensões. Não é o padrão: CLI, TUI, Python e
configuração usam `compliance_strict` quando nenhum preset é informado.

### Configuração principal

```yaml
compliance_posture: best_effort
optimization:
  bounds:
    min_weight: 0.01
    max_weight: 10.0
  linear_programming:
    max_iterations: 1000
    tolerance: 2.0
  constraints:
    volume_preservation: 1.0
  subset_search:
    enabled: true
    strategy: random
    max_attempts: 200
    trigger_on_slack: true
    max_slack_threshold: 0.05
    prefer_slacks_first: false
```

### Comportamento esperado

- Pressiona fortemente pela manutenção do ranking original.
- Permite pequena quantidade de slack para viabilizar uma solução global.
- Quando a soma do slack ultrapassa `0.05`, procura um subconjunto maior e mais
  viável de dimensões.
- As dimensões retiradas do conjunto global podem receber pesos próprios.
- Uma violação final gera advertência e `violations_detected`, mas a postura
  `best_effort` permite que a execução seja concluída.
- Essa flexibilidade vale apenas para avisos comuns de qualidade/otimização.
  Uma negativa das regras numéricas do Control 3 ou de um overlay obrigatório
  bloqueia todos os artefatos com valores de benchmark, mesmo em
  `best_effort`.

### Quando usar

- benchmarking operacional recorrente;
- relatórios analíticos internos;
- primeira execução sobre uma base nova;
- situações em que consistência e privacidade têm importância semelhante.

### Quando reconsiderar

- entrega regulatória: prefira `compliance_strict`;
- dashboard que exige exatamente os mesmos pesos em todas as visões: considere
  `strategic_consistency`;
- necessidade de reproduzir quase exatamente os dados brutos: considere
  `low_distortion`.

## 5. Preset `compliance_strict`

### Intenção

Prioriza conformidade e produz um estado não conforme quando qualquer violação
estrita permanece no resultado final.

### Configuração principal

```yaml
compliance_posture: strict
optimization:
  bounds:
    min_weight: 0.01
    max_weight: 10.0
  linear_programming:
    max_iterations: 1000
    tolerance: 0.0
  constraints:
    volume_preservation: 0.95
  subset_search:
    enabled: true
    strategy: greedy
    max_attempts: 200
    trigger_on_slack: true
    max_slack_threshold: 0.0
    prefer_slacks_first: false
```

### Comportamento esperado

- A tolerância zero torna o slack extremamente caro no LP.
- Qualquer slack dispara a busca de subconjunto.
- A estratégia greedy remove primeiro a dimensão com maior desequilíbrio.
- Há uma pequena flexibilização da preservação de ranking para aumentar a
  chance de encontrar pesos conformes.
- Dimensões problemáticas podem usar pesos separados.
- Violações finais, relaxamentos dinâmicos e falhas nas condições adicionais
  contam na validação estrita.
- Em execução pelo CLI, um resultado estritamente não conforme usa o código de
  saída reservado a não conformidade.

### Quando usar

- materiais regulatórios;
- entregas de auditoria;
- fluxos automatizados que devem falhar quando a validação final não passa;
- qualquer caso em que “melhor esforço” não seja suficiente.

### Principal trade-off

As tabelas podem deixar de usar exatamente o mesmo vetor de pesos. Privacidade
é priorizada sobre consistência transversal.

## 6. Preset `strategic_consistency`

### Intenção

Preservar uma única composição de pares em todas as dimensões, adequado a
dashboards e narrativas executivas nas quais os números precisam fechar sob o
mesmo vetor de pesos.

### Configuração principal

```yaml
compliance_posture: best_effort
optimization:
  bounds:
    min_weight: 0.01
    max_weight: 15.0
  linear_programming:
    max_iterations: 100000
    tolerance: 25.0
    lambda_penalty: 100000000
    volume_weighted_penalties: true
    volume_weighting_exponent: 1.5
  constraints:
    volume_preservation: 0.95
    enforce_single_weight_set: true
  subset_search:
    enabled: false
    trigger_on_slack: false
```

### Comportamento esperado

- Impede subset search, remoção de dimensão e reponderação por dimensão.
- Dá mais liberdade aos pesos para encontrar uma solução global.
- Aceita a possibilidade de slack para manter o vetor único.
- Aplica penalidade muito alta ao slack e pondera essa penalidade pelo volume
  da categoria; categorias grandes recebem maior proteção.
- Mantém forte pressão pela preservação do ranking.
- Como a postura é `best_effort`, violações residuais são reportadas sem serem
  apresentadas como conformidade estrita.
- `best_effort` não autoriza saída quando a decisão final de privacidade do
  Control 3 é negativa.

### Quando usar

- dashboards executivos;
- comparações entre abas ou dimensões que precisam recompor sob os mesmos pesos;
- análises estratégicas em que a consistência da população é parte do contrato.

### Principal trade-off

Uma categoria pequena ou estruturalmente difícil pode permanecer em violação,
pois o preset não aceita “resolver” o problema trocando os pesos daquela
dimensão.

## 7. Preset `research_exploratory`

### Intenção

Encontrar uma solução utilizável para bases esparsas, desequilibradas ou
difíceis, oferecendo mais liberdade ao otimizador.

### Configuração principal

```yaml
compliance_posture: best_effort
optimization:
  bounds:
    min_weight: 0.005
    max_weight: 20.0
  linear_programming:
    max_iterations: 1500
    tolerance: 5.0
  constraints:
    volume_preservation: 0.5
  subset_search:
    enabled: true
    strategy: random
    max_attempts: 400
    trigger_on_slack: false
    prefer_slacks_first: true
```

### Comportamento esperado

- Permite alterações maiores nos pesos.
- Reduz a pressão de preservação de ranking.
- Aceita uma solução com slack sem disparar automaticamente a busca de
  subconjunto.
- Se o LP falhar, tenta primeiro retirar a pressão de ranking antes de separar
  dimensões.
- Explora mais combinações de dimensões quando a busca de subconjunto é
  necessária.
- Pode gerar mudanças de ranking e distorções maiores que `balanced_default`.

### Quando usar

- diagnóstico de uma base que não funciona bem com o preset padrão;
- pesquisa exploratória;
- avaliação de viabilidade antes de definir um contrato de produção.

### Quando não usar como padrão

O fato de a execução terminar não significa que o resultado seja adequado para
publicação. É necessário verificar distorção, métodos de peso e conformidade
antes de promover a configuração para um fluxo recorrente.

## 8. Preset `low_distortion`

### Intenção

Manter o resultado balanceado praticamente idêntico ao resultado bruto.

### Configuração principal

```yaml
compliance_posture: accuracy_first
optimization:
  bounds:
    min_weight: 1.0
    max_weight: 1.0001
  linear_programming:
    max_iterations: 1000
    tolerance: 10.0
    lambda_penalty: 1000
    volume_weighted_penalties: true
    volume_weighting_exponent: 1.0
  constraints:
    volume_preservation: 0.5
  subset_search:
    enabled: false
    trigger_on_slack: false
```

### Comportamento esperado

- Os pesos ficam praticamente travados em `1.0`.
- O solver quase não consegue alterar a composição dos pares.
- Se os dados brutos violarem a regra, os pesos preservam os dados, mas a
  saída não é publicável: com o reconhecimento explícito, a execução gera
  apenas um workbook de diagnóstico com prefixo `autobench_NON_PUBLISHABLE_`;
  publicação, CSV balanceado, relatório JSON e pacote de auditoria são
  retidos.
- A busca proativa de subconjunto fica desabilitada.
- A execução exige reconhecimento explícito da postura `accuracy_first`
  (flag de CLI, campo da API ou diálogo de consentimento na TUI, por
  execução).

### Quando usar

- comparação controlada entre bruto e balanceado;
- análise de sensibilidade;
- investigação da distorção introduzida por outros presets;
- análises internas em que fidelidade é prioritária e as violações serão
  tratadas explicitamente.

### Atenção

Este preset não deve ser interpretado como “privacidade com baixa distorção”.
Na prática, os limites quase identitários retiram do solver a principal
ferramenta usada para corrigir concentrações.

## 9. Preset `minimal_distortion`

### Intenção

Priorizar agressivamente a fidelidade dos resultados, tornando barato aceitar
slack de privacidade.

### Configuração principal

```yaml
compliance_posture: accuracy_first
optimization:
  bounds:
    min_weight: 0.001
    max_weight: 50.0
  linear_programming:
    max_iterations: 10000
    tolerance: 100.0
    lambda_penalty: 1
    volume_weighted_penalties: true
    volume_weighting_exponent: 2.0
  constraints:
    volume_preservation: 0.1
  subset_search:
    enabled: false
    trigger_on_slack: false
  bayesian:
    max_iterations: 500
    learning_rate: 0.1
```

### Comportamento esperado

- Os limites amplos não obrigam pesos extremos; eles apenas permitem grande
  movimentação quando o solver considera útil.
- A função objetivo continua tentando manter pesos próximos de `1.0`.
- `lambda_penalty: 1` torna o slack barato em relação à alteração de pesos.
- A ponderação quadrática por volume reduz ainda mais a importância relativa
  do slack em categorias pequenas.
- Há pouca pressão para preservar o ranking original.
- Violações são esperadas sob `accuracy_first`, mas o resultado de uma
  execução numericamente não conforme nunca é publicável: apenas o workbook
  de diagnóstico `autobench_NON_PUBLISHABLE_` é gravado.

### Diferença para `low_distortion`

- `low_distortion` preserva os valores brutos **travando os pesos** perto de
  `1.0`.
- `minimal_distortion` preserva os valores brutos principalmente
  **barateando a aceitação de slack**, embora mantenha limites de peso amplos.

### Quando usar

- exploração interna;
- testes de limite;
- comparação da solução do otimizador com uma referência orientada a
  fidelidade.

Não é uma escolha apropriada para uma entrega que exija conformidade estrita.

## 10. Principais parâmetros para configuração manual

Comece copiando `config/template.yaml`. Um arquivo personalizado precisa
declarar pelo menos a versão e a postura:

```yaml
version: "3.0"
compliance_posture: "strict"

optimization:
  linear_programming:
    tolerance: 0.0
  bounds:
    min_weight: 0.05
    max_weight: 8.0
```

### 10.1 Postura de conformidade

| Parâmetro | Valores | Efeito |
| --- | --- | --- |
| `compliance_posture` | `strict` | Violações geram estado não conforme; indicado para gates regulatórios. |
| `compliance_posture` | `best_effort` | A execução pode concluir com advertências e violações claramente identificadas. |
| `compliance_posture` | `accuracy_first` | Prioriza fidelidade; exige reconhecimento explícito por execução e, em caso de não conformidade numérica, grava apenas um diagnóstico não publicável. |

No CLI, use:

```powershell
--compliance-posture accuracy_first --acknowledge-accuracy-first
```

A postura muda a classificação e o gate do resultado. Ela não corrige por si
só os pesos nem transforma uma solução com violações em uma solução conforme.

### 10.2 Limites e distorção dos pesos

| Parâmetro | Efeito ao aumentar | Efeito ao diminuir |
| --- | --- | --- |
| `optimization.bounds.max_weight` | Permite amplificar mais um participante; aumenta a flexibilidade e o risco de distorção. | Limita amplificações; preserva mais os dados, mas pode dificultar a privacidade. |
| `optimization.bounds.min_weight` | Impede reduções fortes; mantém pesos mais próximos do bruto. | Permite reduzir fortemente participantes concentrados; aumenta flexibilidade e distorção potencial. |

Regras práticas:

- limites próximos de `1.0` produzem pesos quase identitários;
- limites muito amplos não garantem pesos extremos, mas os tornam possíveis;
- `min_weight` deve ser positivo e menor que `max_weight`;
- sempre avalie o efeito no relatório de impacto e nas mudanças de ranking.

Esses limites são configurados no YAML ou nos campos avançados da TUI; não há
flags públicas `--min-weight` e `--max-weight` no CLI atual.

### 10.3 Tolerância e penalidade de slack

| Parâmetro | Efeito |
| --- | --- |
| `optimization.linear_programming.tolerance` | Valores maiores tornam o modelo e o fallback heurístico mais tolerantes a violações; `0.0` ativa o comportamento de viabilidade estrita. |
| `optimization.linear_programming.lambda_penalty` | Define diretamente o custo do slack no LP. Valor alto força o solver a preferir mudar pesos; valor baixo favorece fidelidade com violações. |
| `optimization.linear_programming.volume_weighted_penalties` | Quando `true`, diferencia o custo do slack pelo volume das categorias. |
| `optimization.linear_programming.volume_weighting_exponent` | Controla quanto a diferença de volume influencia a penalidade. Expoentes maiores concentram proteção nas categorias grandes. |

Se `lambda_penalty` não for informado, o LP deriva a penalidade-base da
tolerância. Quando ele é informado, passa a ser o controle direto do custo de
slack.

Esses parâmetros são configurados no YAML ou nos campos avançados da TUI; não
há uma flag pública `--tolerance` no CLI atual.

### 10.4 Preservação de ranking

| Parâmetro | Efeito |
| --- | --- |
| `optimization.constraints.volume_preservation` | Força entre `0.0` e `1.0`; valores maiores aumentam a penalidade para inversões do ranking original. |
| `optimization.linear_programming.rank_penalty_weight` | Multiplica a força efetiva de preservação de ranking. |
| `optimization.linear_programming.rank_constraints.mode` | `all` compara todos os pares ordenados; `neighbor` restringe apenas vizinhos e reduz o custo em grupos grandes. |
| `optimization.linear_programming.rank_constraints.neighbor_k` | Quantidade de vizinhos protegidos quando o modo é `neighbor`. |

A força efetiva usada pelo analisador é
`volume_preservation * rank_penalty_weight`. Preservação de ranking é uma
penalidade da otimização, não uma prova isolada de que nenhuma inversão ocorrerá.

Esses parâmetros são configurados no YAML ou nos campos avançados da TUI; não
há uma flag pública `--volume-preservation` no CLI atual.

### 10.5 Consistência dos pesos

| Parâmetro | Efeito |
| --- | --- |
| `optimization.constraints.consistency_mode: global` | Tenta um vetor compartilhado entre dimensões. |
| `optimization.constraints.consistency_mode: per_dimension` | Otimiza cada dimensão separadamente. |
| `optimization.constraints.enforce_single_weight_set: true` | Proíbe fallbacks com pesos diferentes por dimensão. |

Atalho no CLI:

```powershell
--per-dimension-weights
```

Pesos por dimensão aumentam a chance de conformidade local, mas os resultados
de tabelas diferentes deixam de compartilhar exatamente a mesma população
ponderada.

### 10.6 Busca de subconjunto

| Parâmetro | Efeito |
| --- | --- |
| `optimization.subset_search.enabled` | Habilita a busca automática do maior subconjunto global viável quando o LP principal falha. |
| `strategy: greedy` | Remove iterativamente a dimensão mais desequilibrada; é rápida e determinística. |
| `strategy: random` | Testa combinações em ordem pseudoaleatória com semente fixa; explora mais possibilidades. |
| `max_attempts` | Limita quantas combinações serão testadas. |
| `trigger_on_slack` | Dispara a busca mesmo quando o LP conclui, caso o slack exceda o limite. |
| `max_slack_threshold` | Soma de slack a partir da qual ocorre o disparo. |
| `prefer_slacks_first` | Em falha do LP, tenta novamente sem pressão de ranking antes de separar dimensões. |

Opções disponíveis no CLI:

```powershell
--auto-subset-search `
--subset-search-max-tests 300 `
--trigger-subset-on-slack `
--max-cap-slack 0.5
```

Não use `strategy: exhaustive` em novas configurações. Embora o validador ainda
aceite o valor por compatibilidade, o fluxo atual distingue operacionalmente
`greedy` dos demais valores, que seguem o caminho de combinações embaralhadas.

### 10.7 Iterações e fallback heurístico

| Parâmetro | Efeito |
| --- | --- |
| `optimization.linear_programming.max_iterations` | Limite de iterações enviado ao solver LP; aumentar pode ajudar problemas grandes, com maior tempo de execução. |
| `optimization.bayesian.max_iterations` | Limite do solver heurístico usado em fallbacks e correções de condições adicionais. |
| `optimization.bayesian.learning_rate` | Tamanho dos ajustes do solver heurístico; valores altos podem avançar mais rápido, mas oscilar. |
| `optimization.bayesian.violation_penalty_weight` | Custo das violações no solver heurístico. |

Esses parâmetros não devem ser a primeira resposta a uma base inviável.
Antes de aumentar iterações, verifique quantidade de pares, categorias
estruturalmente concentradas, limites de peso e método efetivamente usado.

### 10.8 Condições adicionais e buckets esparsos

`optimization.constraints.enforce_additional_constraints` controla a
verificação das condições adicionais das regras `6/30`, `7/35` e `10/40`.
Desabilitá-la reduz a proteção e não deve ser usado como atalho para fazer uma
execução passar.

`dynamic_constraints.enabled` permite relaxar essas condições em buckets pouco
representativos. Os principais limiares são:

- `min_peer_count`: mínimo de participantes no bucket;
- `min_effective_peer_count`: diversidade efetiva mínima;
- `min_category_volume_share`: representatividade dentro da dimensão/período;
- `min_overall_volume_share`: representatividade no volume total;
- `min_representativeness`: score mínimo para aplicação integral.

Uma linha relaxada dinamicamente ainda conta como violação na validação final
estrita. O recurso deve ser usado para diagnóstico e transparência, não para
renomear um resultado relaxado como plenamente conforme.

### 10.9 Best-in-Class e modo merchant

| Parâmetro | Efeito |
| --- | --- |
| `analysis.best_in_class_percentile` | Percentil usado como referência para share e aprovação; `0.85` representa o percentil 85. |
| `analysis.fraud_percentile` | Percentil de referência para métricas em que menor é melhor, quando configurado. |
| `analysis.auto_detect_dimensions` | Permite descoberta automática de dimensões; dimensões explícitas são preferíveis em produção. |
| `analysis.merchant_mode` | Habilita a exceção `4/35` quando existem exatamente quatro pares. |

`merchant_mode` é uma declaração operacional explícita em YAML; não é inferido
automaticamente pelo nome das colunas.

### 10.10 Política Control 3 e elegibilidade anterior ao Autobench

O único campo aceito em `control3` é `privacy_basis`. Para fraude ou chargeback
em benchmark de emissores, ele deve ser `clearing_spend`, e a coluna escolhida
como `total_col` deve conter o valor de clearing spend: o motor usa essa própria
coluna como base de concentração e não tenta descobrir outra.

As demais decisões de negócio pertencem ao processo de Privacidade/governança
anterior ao Autobench. Antes de carregar os dados, o analista deve resolver:

- revisão para métricas de carteira digital;
- proteção quando há dois eixos de entidades protegidas;
- rechecagem de entregáveis recorrentes, inclusive após alteração do peer group;
- revisão contra engenharia reversa e Control 3.3;
- proibição de entregáveis que listam top merchants.

Não existem flags, campos de TUI, chaves YAML nem campos Python para declarar
essas decisões. O Autobench confia na elegibilidade aprovada pelo analista; ele
não a infere dos dados e não substitui o processo upstream.

Exemplo:

```yaml
control3:
  privacy_basis: clearing_spend
```

### 10.11 Entrada, memória e desempenho

Os parâmetros mais relevantes para arquivos grandes são:

- `input.project_csv_columns`: carrega somente as colunas necessárias quando as
  dimensões são explícitas;
- `input.adaptive_batching`: faz pré-agregação por chunks quando o volume
  ultrapassa os limiares;
- `input.batch_row_threshold` e `input.batch_file_size_mb`: definem quando o
  batching adaptativo entra em ação;
- `input.csv_chunk_size`: tamanho explícito do chunk;
- `runtime.lean_mode`: reduz uso de memória desabilitando artefatos pesados,
  validações opcionais e subset search.

Atalho:

```powershell
--lean
```

O modo lean mantém a aplicação dos caps de privacidade, mas muda o conjunto de
diagnósticos produzidos. Ele exige dimensões explícitas para permitir
pré-agregação segura.

### 10.12 Saídas e diagnósticos

| Parâmetro | Efeito |
| --- | --- |
| `output.format` | `xlsx` ou `json`; `json` adiciona um sidecar legível por máquina ao workbook analítico. |
| `output.output_format` | `analysis`, `publication` ou `both`. |
| `include_debug_sheets` | Inclui detalhes de pesos e métricas não ponderadas. |
| `include_privacy_validation` | Inclui a validação detalhada de privacidade. |
| `include_impact_summary` | Compara métricas brutas e balanceadas. |
| `include_preset_comparison` | Executa comparações adicionais entre presets. |
| `include_audit_log` | Inclui o log de auditoria. |
| `include_audit_package` | Gera pacote com relatórios e snapshot de configuração. |
| `validate_export` | Cruza o CSV balanceado com o workbook. |

Opções úteis:

```powershell
--debug `
--analyze-impact `
--compare-presets `
--export-balanced-csv `
--validate-export `
--audit-package `
--output-format both
```

`--compare-presets` faz análises adicionais e pode aumentar
significativamente o tempo e o consumo de memória.

## 11. Receitas de configuração

### 11.1 Privacidade estrita com fallback por dimensão

Use `compliance_strict`. Ele já aplica tolerância zero e antecipa a busca greedy
de subconjunto quando qualquer slack aparece; nenhum override YAML é necessário.
Se o vetor global não for viável, o preset pode calcular pesos por dimensão.
Confirme o método realmente usado na aba `Weight Methods`.

### 11.2 Menos distorção com advertências explícitas

Restrinja os pesos sem travá-los totalmente:

```yaml
version: "3.0"
compliance_posture: "best_effort"

optimization:
  bounds:
    min_weight: 0.8
    max_weight: 1.25
  linear_programming:
    tolerance: 5.0
  subset_search:
    trigger_on_slack: false
```

Essa configuração deve ser validada contra a base real; limites estreitos podem
tornar categorias concentradas estruturalmente impossíveis de corrigir.

### 11.3 Consistência obrigatória para dashboard

```yaml
version: "3.0"
compliance_posture: "best_effort"

optimization:
  constraints:
    consistency_mode: global
    enforce_single_weight_set: true
  subset_search:
    enabled: false
    trigger_on_slack: false
```

Antes de publicar, confirme se as violações residuais são aceitáveis para o uso
pretendido. Consistência global não equivale a conformidade.

### 11.4 Pesos independentes por dimensão

```powershell
py benchmark.py share `
  --csv .\dados.csv `
  --entity "BANCO ALVO" `
  --metric txn_cnt `
  --dimensions canal produto regiao `
  --preset compliance_strict `
  --per-dimension-weights `
  --compliance-posture strict
```

Esse modo tende a melhorar a viabilidade local, mas deve ser sinalizado ao
consumidor do relatório porque os resultados deixam de compartilhar um único
vetor de pesos.

### 11.5 Ler e tratar supressões

Uma categoria ausente pode ser uma decisão de privacidade. O Autobench aplica
a supressão depois da análise e antes de gravar os artefatos. A origem não é
alterada.

Há duas causas possíveis:

1. `below_min_entities`: o grupo tem menos peers contribuintes que o mínimo da
   regra ativa. O alvo não entra na contagem. Somente valores governados
   positivos contam.
2. `structurally_infeasible`: nenhum peso dentro dos limites configurados reduz
   a participação dominante até o teto permitido.

O mínimo de participantes depende da regra autorizadora:

| Regra | Mínimo de peers contribuintes |
| --- | ---: |
| `5/25` | 5 |
| `6/30` | 6 |
| `7/35` | 7 |
| `10/40` | 10 |
| merchant `4/35` | 4 |

O escopo também depende do tipo de análise:

- **Share:** uma categoria insegura na métrica principal remove a linha
  completa. Uma métrica secundária insegura pode ser omitida sem remover a
  métrica principal.
- **Taxa:** aprovação e fraude podem ter conjuntos visíveis diferentes. A
  contagem usa o denominador governado. Para fraude de emissor, use clearing
  spend. Poucos eventos de fraude, sozinhos, não causam a supressão.
- **Tempo:** a supressão pode atingir uma categoria em um período. Um registro
  sem período remove essa categoria de todos os períodos.

A omissão é propagada para todas as saídas que poderiam revelar o grupo:

- Abas de dimensão e métricas secundárias.
- CSV balanceado e JSON.
- Privacy Validation, Impact e comparação de presets.
- Pacote de auditoria e artefato de publicação.
- Diagnósticos de peers que aparecem somente em grupos suprimidos.

Os metadados persistidos não guardam o nome da categoria suprimida. Eles guardam
somente motivo, contagem de participantes, métrica ou tipo de saída. Essa regra
impede que o aviso revele o próprio grupo protegido.

No consumo do resultado:

1. Leia a quantidade de supressões e o aviso geral em `Summary`.
2. Trate o valor ausente como indisponível, nunca como zero.
3. Não reconstrua a categoria com abas de diagnóstico ou categorias visíveis.
4. Ao reutilizar pesos em SQL, aplique as mesmas supressões e verificações.
5. Não confunda supressão com fallback. Fallback mantém o grupo com outros
   pesos. Supressão remove o grupo inseguro.

Se nenhum candidato receber autorização verificável do Control 3, não há
supressão parcial. O Autobench retém todas as saídas normais. A exceção
`accuracy_first` grava somente um workbook interno marcado como não publicável,
quando todas as condições dessa postura forem atendidas.

## 12. Como validar uma configuração

Não avalie uma configuração apenas pelo fato de o comando terminar. Verifique,
nesta ordem:

1. **Summary:** preset, postura final, status da execução e veredito de
   conformidade.
2. **Privacy Validation:** violações da regra principal, contagem de
   participantes, condições adicionais e relaxamentos.
3. **Weight Methods:** quais dimensões usaram LP global, heurística ou pesos por
   dimensão.
4. **Rank Changes:** inversões relevantes após a ponderação.
5. **Impact:** diferença entre valores brutos e balanceados.
6. **Subset Search:** dimensões testadas, retiradas e slack das tentativas.
7. **Audit/config snapshot:** confirmação de que a configuração resolvida é a
   esperada.
8. **Supressões:** quantidade registrada em `Summary`, diferenças entre saídas
   de aprovação e fraude, e ausência dos grupos no CSV/JSON.

Para comparar alternativas:

```powershell
py benchmark.py share `
  --csv .\dados.csv `
  --entity "BANCO ALVO" `
  --metric txn_cnt `
  --dimensions canal produto `
  --preset compliance_strict `
  --compare-presets `
  --analyze-impact
```

Presets `accuracy_first` aparecem bloqueados na comparação se o reconhecimento
explícito não for fornecido.

## 13. Comandos de consulta

Listar presets:

```powershell
py benchmark.py config list
```

Exibir a configuração declarada de um preset:

```powershell
py benchmark.py config show compliance_strict
```

Executar uma análise Share:

```powershell
py benchmark.py share `
  --csv .\dados.csv `
  --entity "BANCO ALVO" `
  --entity-col issuer_name `
  --metric txn_cnt `
  --dimensions canal produto `
  --time-col year_month `
  --preset compliance_strict `
  --output .\benchmark-share.xlsx
```

Executar uma análise de taxa de aprovação:

```powershell
py benchmark.py rate `
  --csv .\dados.csv `
  --entity "BANCO ALVO" `
  --entity-col issuer_name `
  --total-col total `
  --approved-col approved `
  --dimensions canal produto `
  --time-col year_month `
  --preset compliance_strict `
  --output .\benchmark-rate.xlsx
```

## 14. Recomendação final

Comece com `compliance_strict`, habilite análise de impacto e leia a coluna ou
aba de métodos de peso. O preset estrito pode recorrer a pesos por dimensão;
somente `strategic_consistency` garante um único vetor global. Mude de preset
somente em resposta a um requisito explícito:

- conformidade fail-closed: mantenha `compliance_strict`;
- exploração best-effort explicitamente autorizada: `balanced_default`;
- vetor único entre todas as visões: `strategic_consistency`;
- diagnóstico de base difícil: `research_exploratory`;
- referência quase bruta: `low_distortion`;
- exploração accuracy-first extrema: `minimal_distortion`.

Quando uma combinação específica funcionar de forma recorrente, registre-a em
um arquivo YAML versionado e explique o motivo de cada override. Um número
“melhor” em uma execução isolada não substitui um contrato claro de privacidade,
consistência e distorção.
